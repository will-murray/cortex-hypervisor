"""
Blueprint OMS API proxy — called by VAPI tool definitions.

These endpoints are NOT for end users. They are called by VAPI during live
calls when the voice agent needs to trigger Blueprint, check availability,
or create an appointment. Auth is via X-Vapi-Secret header.

The /clinic-config endpoint IS for end users (Firebase auth) and lets admins
see Blueprint appointment types, providers, and locations before activating
the voice agent.

Blueprint credentials are read from clinic_pms_config (non-secret config) +
Secret Manager (API key) per request — never stored in environment variables.

Blueprint API base URL: https://{server}/{clinic_slug}/rest/
"""
import json
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from google.cloud import bigquery
from pydantic import BaseModel

from api.deps import PROJECT, bq_client, bq_table, verify_token, require_read_access
from services.secrets import get_secret

router = APIRouter(prefix="/blueprint")


# ── Auth ──────────────────────────────────────────────────────────────────────

def verify_vapi_secret(x_vapi_secret: str = Header(None)) -> None:
    expected = get_secret("vapi-webhook-secret")
    if not expected or x_vapi_secret != expected:
        raise HTTPException(status_code=403, detail="Invalid or missing Vapi secret")


# ── Blueprint credentials ─────────────────────────────────────────────────────

def _get_blueprint_config(clinic_id: str) -> dict:
    """
    Fetch Blueprint config + API key + timezone for a clinic.

    Non-secret config comes from clinic_pms_config.config JSON (fields:
    clinic_code, api_url, aws_url, default_region).
    API key comes from Secret Manager using the clinic-name-based naming:
      <clinic_name>_BLUEPRINT_API_key
    """
    # Get PMS config + clinic name
    rows = list(bq_client.query(
        f"""
        SELECT c.clinic_name, c.timezone, p.pms_type, p.config
        FROM {bq_table('clinics')} c
        JOIN {bq_table('clinic_pms_config')} p ON p.clinic_id = c.clinic_id
        WHERE c.clinic_id = @clinic_id
        """,
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("clinic_id", "STRING", clinic_id)
        ])
    ).result())

    if not rows:
        raise HTTPException(status_code=400, detail="Clinic has no PMS configuration")

    row = dict(rows[0])
    if row.get("pms_type") != "blueprint":
        raise HTTPException(status_code=400, detail="Clinic is not configured for Blueprint OMS")

    config = json.loads(row["config"]) if row.get("config") else {}

    if not config.get("api_url"):
        raise HTTPException(status_code=400, detail="Blueprint config incomplete: api_url is missing")

    # Fetch API key from SM
    sm_prefix = row["clinic_name"].replace(" ", "_") + "_BLUEPRINT_"
    try:
        api_key = get_secret(f"{sm_prefix}API_key")
    except Exception:
        raise HTTPException(status_code=400, detail="Blueprint API key not found in Secret Manager")

    return {
        "clinic_name": row["clinic_name"],
        "api_url": config["api_url"],
        "clinic_code": config.get("clinic_code"),
        "api_key": api_key,
        "timezone": row.get("timezone"),
    }


def _get_full_clinic(clinic_id: str) -> dict:
    """
    Fetch full clinic row (for instance_id access control) + Blueprint config.
    """
    clinic_rows = list(bq_client.query(
        f"SELECT instance_id, timezone FROM {bq_table('clinics')} WHERE clinic_id = @clinic_id",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("clinic_id", "STRING", clinic_id)
        ])
    ).result())
    if not clinic_rows:
        raise HTTPException(status_code=404, detail="Clinic not found")

    clinic = dict(clinic_rows[0])

    # Merge in Blueprint config
    bp_config = _get_blueprint_config(clinic_id)
    clinic.update(bp_config)
    return clinic


def _blueprint_base(config: dict) -> str:
    """
    Derive the REST base URL from api_url.

    api_url is the full URL as stored by configure_blueprint.py (e.g.
    "https://ca-alb1.aws.bp-solutions.net:8443/ca_mst1/AB/acn/?rest/hello").
    We strip the trailing rest/... path and return the base.
    """
    url = config["api_url"].replace("\u200b", "").strip()
    # Strip query string and any trailing /rest/... path
    import re
    url = re.split(r"[?]", url, maxsplit=1)[0].rstrip("/")
    # Remove any trailing /rest or /rest/... segments
    url = re.sub(r"/rest(/.*)?$", "", url)
    return f"{url}/rest"


def _int_field(config: dict, key: str, default: int = 0) -> int:
    val = config.get(key)
    return int(val) if val else default


# ── Request models ────────────────────────────────────────────────────────────

class LookupPatientRequest(BaseModel):
    caller_phone: str


class AvailabilityRequest(BaseModel):
    event_type_id: int
    start_date: str   # YYYY-MM-DD
    end_date: str     # YYYY-MM-DD


class AvailabilitySearchRequest(BaseModel):
    start_date: str                              # YYYY-MM-DD (clinic local time)
    end_date: str                                # YYYY-MM-DD (clinic local time, inclusive)
    locations: list[int] | None = None           # defaults to the clinic's configured location
    available_for_online_booking_only: bool | None = None


class CreateAppointmentRequest(BaseModel):
    event_type_id: int
    start_time: str
    end_time: str
    summary: str
    provider_id: int | None = None
    patient_id: int | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None


class FindAvailableSlotsRequest(BaseModel):
    event_type_id: int
    start_date: str   # YYYY-MM-DD (clinic local time)
    end_date: str     # YYYY-MM-DD (clinic local time, inclusive)
    providers: list[int] | None = None
    locations: list[int] | None = None


# ── Admin endpoint ────────────────────────────────────────────────────────────

@router.get("/{clinic_id}/clinic-config")
def get_clinic_config(clinic_id: str, caller: dict = Depends(verify_token)):
    """
    Fetch Blueprint clinic configuration: appointment types, providers, locations.
    """
    clinic = _get_full_clinic(clinic_id)
    require_read_access(clinic["instance_id"], caller)

    base = _blueprint_base(clinic)
    resp = httpx.get(
        f"{base}/clinicConfiguration/",
        params={"apiKey": clinic["api_key"]},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    return {
        "appointment_types": [
            {
                "id": t["id"],
                "name": t.get("name"),
                "duration_minutes": t.get("duration"),
                "description": t.get("description", ""),
            }
            for t in data.get("appointmentTypes", [])
        ],
        "providers": [
            {
                "id": p["id"],
                "name": (p.get("onlineDisplayName") or
                         f"{p.get('firstName', '')} {p.get('lastName', '')}".strip()),
                "job_title": p.get("jobTitle"),
                "qualifications": p.get("qualifications"),
                "location_ids": p.get("locations", []),
            }
            for p in data.get("providers", [])
        ],
        "locations": [
            {
                "id": loc["id"],
                "name": loc.get("name"),
                "address": loc.get("formattedAddress") or loc.get("street"),
                "timezone": loc.get("timeZone"),
            }
            for loc in data.get("locations", [])
        ],
    }


# ── VAPI tool endpoints ───────────────────────────────────────────────────────

@router.post("/{clinic_id}/patient/lookup")
def lookup_patient(
    clinic_id: str,
    body: LookupPatientRequest,
    _: None = Depends(verify_vapi_secret),
):
    """CTI trigger: opens the patient's file in Blueprint for the receptionist."""
    config = _get_blueprint_config(clinic_id)
    base = _blueprint_base(config)
    user_id = _int_field(config, "user_id", default=1)
    callerid = "".join(c for c in body.caller_phone if c.isdigit())

    try:
        httpx.get(
            f"{base}/client/show",
            params={
                "apiKey": config["api_key"],
                "event": "ringing",
                "user": str(user_id),
                "callerid": callerid,
            },
            timeout=10,
        )
    except httpx.RequestError:
        pass  # Best-effort — the UI trigger failing shouldn't block the call

    return {"triggered": True}


@router.post("/{clinic_id}/availability")
def check_availability(
    clinic_id: str,
    body: AvailabilityRequest,
    _: None = Depends(verify_vapi_secret),
):
    """Return available appointment slots for a date range and event type."""
    config = _get_blueprint_config(clinic_id)
    base = _blueprint_base(config)
    location_id = _int_field(config, "location_id")

    tz = ZoneInfo(config.get("timezone") or "America/Vancouver")
    start_dt = datetime.strptime(body.start_date, "%Y-%m-%d").replace(tzinfo=tz)
    end_dt = (datetime.strptime(body.end_date, "%Y-%m-%d") + timedelta(days=1)).replace(tzinfo=tz)

    params: dict = {
        "apiKey": config["api_key"],
        "startTime": int(start_dt.timestamp()),
        "endTime": int(end_dt.timestamp()),
        "eventTypeId": body.event_type_id,
        "bookingTimeSlotInterval": "30",
        "minimumAdvanceBookingTime": "60",
    }
    if location_id:
        params["locations"] = location_id

    resp = httpx.get(f"{base}/availability/", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


@router.post("/{clinic_id}/availability/search")
def search_availability(
    clinic_id: str,
    body: AvailabilitySearchRequest,
    _: None = Depends(verify_vapi_secret),
):
    """
    Search scheduled provider availability blocks in a date range.

    Proxies Blueprint: POST /rest/availability/search. Returns summary info
    about availability blocks (when providers are scheduled to work) — NOT
    bookable appointment slots. Use `check_availability` for bookable slots
    tied to a specific event type; use this endpoint for broad "when does the
    clinic have capacity next week?" questions.
    """
    config = _get_blueprint_config(clinic_id)
    base = _blueprint_base(config)

    tz = ZoneInfo(config.get("timezone") or "America/Vancouver")
    start_dt = datetime.strptime(body.start_date, "%Y-%m-%d").replace(tzinfo=tz)
    end_dt = (datetime.strptime(body.end_date, "%Y-%m-%d") + timedelta(days=1)).replace(tzinfo=tz)

    payload: dict = {
        "apiKey": config["api_key"],
        "startTime": int(start_dt.timestamp()),
        "endTime": int(end_dt.timestamp()),
    }

    # If the caller didn't specify locations, fall back to the clinic's
    # configured location_id. Matches check_availability's behaviour.
    if body.locations is not None:
        payload["locations"] = body.locations
    else:
        location_id = _int_field(config, "location_id")
        if location_id:
            payload["locations"] = [location_id]

    if body.available_for_online_booking_only is not None:
        payload["availableForOnlineBookingOnly"] = body.available_for_online_booking_only

    resp = httpx.post(f"{base}/availability/search", json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


# ── Voice agent v1: list_appointment_types + find_available_slots ─────────────


# Hardcoded for v1. /clinicConfiguration also returns these per-clinic, but we
# default to platform-wide values to avoid the extra Blueprint round-trip.
# If a clinic needs different defaults, lift these into clinic_pms_config.
_DEFAULT_BOOKING_TIME_SLOT_INTERVAL = "30"     # minutes; "60" / "30" / "15" / "DURATION"
_DEFAULT_MINIMUM_ADVANCE_BOOKING_TIME = 30      # minutes


@router.post("/{clinic_id}/appointment-types")
def list_appointment_types(
    clinic_id: str,
    _: None = Depends(verify_vapi_secret),
):
    """
    Voice-agent capability: list the clinic's bookable appointment types.

    Hits Blueprint's GET /rest/clinicConfiguration/ and returns a stripped
    list — just id, name, and duration_minutes. The agent uses this to map a
    caller's stated need to an event_type_id before calling
    find_available_slots.

    Strips: providers, locations, configuration knobs, requiredResourceTypeIds,
    description (often empty / verbose).
    """
    config = _get_blueprint_config(clinic_id)
    base = _blueprint_base(config)

    resp = httpx.get(
        f"{base}/clinicConfiguration/",
        params={"apiKey": config["api_key"]},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    # Filter out null-named placeholder rows. Blueprint returns the full
    # appointmentTypes pool (active + inactive + deleted) with name=null on
    # anything not currently in use. The agent can't reason about anonymous
    # IDs, so drop them. We keep entries that have a name regardless of the
    # active/onlineBookingEnabled flags — clinics in mid-configuration may
    # still want their types surfaced; staff handle the activation separately.
    return {
        "appointment_types": [
            {
                "id": t["id"],
                "name": t.get("name"),
                "duration_minutes": t.get("duration"),
            }
            for t in data.get("appointmentTypes", [])
            if t.get("name")
        ],
    }


@router.post("/{clinic_id}/availability/find")
def find_available_slots(
    clinic_id: str,
    body: FindAvailableSlotsRequest,
    _: None = Depends(verify_vapi_secret),
):
    """
    Voice-agent capability: find concrete bookable time slots in a date range
    for a specific appointment type.

    Proxies Blueprint's GET /rest/availability/?... Hardcodes the booking
    interval and minimum-advance-booking values; the agent doesn't need to
    care about those.

    Response is aggressively stripped — only date + bookable times remain. No
    provider IDs, no location IDs, no resource info reach the agent. The
    agent's job is to capture preference; clinic staff confirm the actual
    provider / location at booking time.
    """
    config = _get_blueprint_config(clinic_id)
    base = _blueprint_base(config)

    tz = ZoneInfo(config.get("timezone") or "America/Vancouver")
    start_dt = datetime.strptime(body.start_date, "%Y-%m-%d").replace(tzinfo=tz)
    end_dt = (datetime.strptime(body.end_date, "%Y-%m-%d") + timedelta(days=1)).replace(tzinfo=tz)

    params: dict = {
        "apiKey": config["api_key"],
        "startTime": int(start_dt.timestamp()),
        "endTime": int(end_dt.timestamp()),
        "eventTypeId": body.event_type_id,
        "bookingTimeSlotInterval": _DEFAULT_BOOKING_TIME_SLOT_INTERVAL,
        "minimumAdvanceBookingTime": _DEFAULT_MINIMUM_ADVANCE_BOOKING_TIME,
    }

    if body.providers is not None:
        params["providers"] = ",".join(str(p) for p in body.providers)
    if body.locations is not None:
        params["locations"] = ",".join(str(loc) for loc in body.locations)
    else:
        clinic_location_id = _int_field(config, "location_id")
        if clinic_location_id:
            params["locations"] = clinic_location_id

    resp = httpx.get(f"{base}/availability/", params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    # Strip: keep date + the time strings only. Drop providerId/locationId
    # arrays and resource info. Skip days flagged unavailable.
    days = []
    for day in data:
        if not day.get("available"):
            continue
        times = []
        for slot in day.get("availabilityTimes", []) or []:
            t = slot.get("time")
            if not t:
                continue
            # Trim "08:00:00-0600" → "08:00"
            hhmm = t.split(":")
            if len(hhmm) >= 2:
                times.append(f"{hhmm[0]}:{hhmm[1]}")
            else:
                times.append(t)
        if not times:
            continue
        days.append({"date": day.get("date"), "available_times": times})

    return {"days": days}


@router.post("/{clinic_id}/appointment")
def create_appointment(
    clinic_id: str,
    body: CreateAppointmentRequest,
    _: None = Depends(verify_vapi_secret),
):
    """Create an appointment in Blueprint OMS."""
    config = _get_blueprint_config(clinic_id)
    base = _blueprint_base(config)
    user_id = _int_field(config, "user_id", default=1)
    location_id = _int_field(config, "location_id")

    if not location_id:
        raise HTTPException(status_code=400, detail="location_id not configured for this clinic")

    payload: dict = {
        "apiKey": config["api_key"],
        "userId": user_id,
        "eventTypeId": body.event_type_id,
        "startTime": int(body.start_time),
        "endTime": int(body.end_time),
        "summary": body.summary,
        "status": 2,
    }

    if body.provider_id:
        payload["locationId"] = location_id
        payload["providerId"] = body.provider_id
    else:
        payload["availableProviders"] = [{"locationId": location_id}]

    if body.patient_id:
        payload["patientId"] = body.patient_id
    elif body.first_name and body.last_name:
        phone_digits = "".join(c for c in (body.phone or "") if c.isdigit())
        payload["patient"] = {
            "quickAdd": True,
            "firstName": body.first_name,
            "lastName": body.last_name,
            "locationId": location_id,
            **({"mobilePhoneNumber": phone_digits} if phone_digits else {}),
        }
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide either patient_id or first_name + last_name"
        )

    resp = httpx.post(f"{base}/appointments/", json=payload, timeout=15)
    resp.raise_for_status()
    return {"status": "created"}


# ── Patient name match (voice agent v1) ───────────────────────────────────────


class PatientMatchRequest(BaseModel):
    first_name: str
    last_name: str
    last4_phone: str
    dob: str | None = None  # YYYY-MM-DD; optional tie-breaker when ambiguous


class PatientMatchResponse(BaseModel):
    status: Literal["matched", "ambiguous", "unmatched"]
    patient_id: str | None = None
    candidates_count: int


@router.post("/{clinic_id}/patient/match", response_model=PatientMatchResponse)
def match_patient_by_name(
    clinic_id: str,
    body: PatientMatchRequest,
    _: None = Depends(verify_vapi_secret),
):
    """
    Server-side patient match against Blueprint_PHI.ClientDemographics.

    **The _clinic_id filter is mandatory and non-negotiable** — a match for a
    patient belonging to clinic A must never be returnable when querying
    clinic B's endpoint. This is a PHI isolation requirement, not a style
    choice.

    Matches on first_name + last_name (case-insensitive), then filters by any
    phone field (mobile/home/work) ending in last4_phone. If >1 candidates
    remain and dob is provided, adds dob as a tie-breaker.

    Returns only a status + opaque patient_id — no names, phones, or DOB leak
    back to the caller.
    """
    last4 = "".join(c for c in body.last4_phone if c.isdigit())
    if len(last4) != 4:
        raise HTTPException(status_code=400, detail="last4_phone must be exactly 4 digits")

    params = [
        bigquery.ScalarQueryParameter("clinic_id", "STRING", clinic_id),
        bigquery.ScalarQueryParameter("first_name", "STRING", body.first_name.strip()),
        bigquery.ScalarQueryParameter("last_name", "STRING", body.last_name.strip()),
        bigquery.ScalarQueryParameter("last4", "STRING", last4),
    ]
    dob_clause = ""
    if body.dob:
        dob_clause = "AND birthdate = @dob"
        params.append(bigquery.ScalarQueryParameter("dob", "STRING", body.dob))

    sql = f"""
        SELECT client_id
        FROM `{PROJECT}.Blueprint_PHI.ClientDemographics`
        WHERE _clinic_id = @clinic_id
          AND LOWER(given_name) = LOWER(@first_name)
          AND LOWER(surname) = LOWER(@last_name)
          AND (
            ENDS_WITH(IFNULL(mobile_telephone_no, ''), @last4)
            OR ENDS_WITH(IFNULL(home_telephone_no, ''), @last4)
            OR ENDS_WITH(IFNULL(work_telephone_no, ''), @last4)
          )
          {dob_clause}
    """
    rows = list(bq_client.query(
        sql,
        job_config=bigquery.QueryJobConfig(query_parameters=params),
    ).result())

    count = len(rows)
    if count == 0:
        return PatientMatchResponse(status="unmatched", candidates_count=0)
    if count == 1:
        return PatientMatchResponse(status="matched", patient_id=rows[0]["client_id"], candidates_count=1)
    return PatientMatchResponse(status="ambiguous", candidates_count=count)
