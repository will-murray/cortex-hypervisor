"""
Voice agent lifecycle + capability toggles + ticket ingest.

Backed by Cloud SQL for the operational state (status, twilio_*, vapi_*) and
the capability toggles. The submit_ticket endpoint still writes to BigQuery
(`Users.voice_agent_tickets`) — call outcomes are analytics-shaped, append-only,
and the BQ-vs-Cloud-SQL boundary established by the migration plan keeps them
on the analytics side.

The previous activation gate (`services.script_approval.require_full_approval`)
is intentionally removed: the underlying `Users.agent_script_sections` table is
being dropped as part of the transcript-analysis rebuild. The new voice-agent
system (whatever replaces voice_agent_builder/) will reintroduce its own gate.

TODO (Round 3): wire activate/deactivate/verify_caller_id to Twilio + VAPI via
services/twilio_client.py and services/vapi_provisioner.py.
"""
import json
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from google.cloud import bigquery
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import bq_client, bq_table, require_write_access, verify_token
from api.voice_agent.blueprint import verify_vapi_secret
from api.core.db import get_session
from api.core.orm import Clinic, ClinicVoiceAgentConfiguration, VoiceAgentCapability
from api.voice_agent.capabilities import (
    CAPABILITY_METADATA,
    CAPABILITY_METADATA_BY_ID,
    is_pms_compatible,
)


router = APIRouter()


def _get_clinic_or_404(db: Session, clinic_id: str) -> Clinic:
    clinic = db.get(Clinic, clinic_id)
    if not clinic or clinic.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Clinic not found")
    return clinic


def _get_voice_agent_or_create(db: Session, clinic_id: str) -> ClinicVoiceAgentConfiguration:
    """Voice-agent config row should always exist (provisioned with the clinic).
    Defensively create on demand for clinics imported before that invariant held."""
    va = db.get(ClinicVoiceAgentConfiguration, clinic_id)
    if va is None:
        va = ClinicVoiceAgentConfiguration(clinic_id=clinic_id)
        db.add(va)
    return va


@router.post("/clinics/{clinic_id}/voice_agent/activate")
def activate_voice_agent(
    clinic_id: str,
    caller: dict = Depends(verify_token),
    db: Session = Depends(get_session),
):
    """
    Opt a clinic into Cortex Intercept (AI call handling).

    TODO (Round 3): Replace the placeholder with actual Twilio number purchase
    + VAPI assistant creation via services/twilio_client.py + services/vapi_provisioner.py.
    """
    clinic = _get_clinic_or_404(db, clinic_id)
    require_write_access(clinic.instance_id, caller)

    va = _get_voice_agent_or_create(db, clinic_id)
    if va.voice_agent_status == "active":
        raise HTTPException(status_code=409, detail="Voice agent is already active for this clinic")

    va.voice_agent_status = "provisioning"

    return {
        "status": "provisioning",
        "clinic_id": clinic_id,
        "message": (
            "Voice agent provisioning initiated. "
            "Twilio number purchase and VAPI assistant creation will be completed in the next deployment. "
            "Once active, configure your phone system to forward unanswered calls to the provisioned number."
        ),
    }


@router.delete("/clinics/{clinic_id}/voice_agent")
def deactivate_voice_agent(
    clinic_id: str,
    caller: dict = Depends(verify_token),
    db: Session = Depends(get_session),
):
    """
    Deactivate and deprovision the voice agent for this clinic.

    TODO (Round 3): release Twilio number + delete VAPI assistant before clearing fields.
    """
    clinic = _get_clinic_or_404(db, clinic_id)
    require_write_access(clinic.instance_id, caller)

    va = _get_voice_agent_or_create(db, clinic_id)
    if va.voice_agent_status == "inactive":
        raise HTTPException(status_code=409, detail="Voice agent is not active for this clinic")

    va.voice_agent_status = "inactive"
    va.twilio_phone_number = None
    va.twilio_phone_sid = None
    va.twilio_verified_caller_id = False
    va.vapi_assistant_id = None
    va.vapi_phone_number_id = None

    return {"status": "success", "clinic_id": clinic_id, "voice_agent_status": "inactive"}


@router.post("/clinics/{clinic_id}/voice_agent/verify_caller_id")
def verify_caller_id(
    clinic_id: str,
    caller: dict = Depends(verify_token),
    db: Session = Depends(get_session),
):
    """
    Initiate Twilio outbound caller ID verification for the clinic's primary phone.

    TODO (Round 3): Implement via services/twilio_client.initiate_caller_id_verification.
    """
    clinic = _get_clinic_or_404(db, clinic_id)
    require_write_access(clinic.instance_id, caller)

    va = _get_voice_agent_or_create(db, clinic_id)
    if va.voice_agent_status not in ("active", "provisioning"):
        raise HTTPException(
            status_code=400,
            detail="Voice agent must be activated before verifying caller ID",
        )

    raise HTTPException(
        status_code=501,
        detail="Twilio caller ID verification not yet implemented — coming in Round 3",
    )


# ── VAPI-authed: submit_ticket (writes to BigQuery) ──────────────────────────


class TicketSubmitRequest(BaseModel):
    vapi_call_id: str | None = None
    caller_phone: str | None = None
    caller_name: str | None = None
    patient_match_status: Literal["matched", "unmatched", "new", "ambiguous"]
    blueprint_patient_id: str | None = None
    last4_confirmed: bool = False
    intent_category: str | None = None
    summary: str | None = None
    details: dict | None = None
    suggested_followup: str | None = None
    urgency: Literal["normal", "urgent"] = "normal"


class TicketSubmitResponse(BaseModel):
    ticket_id: str


@router.post(
    "/clinics/{clinic_id}/voice_agent/tickets",
    response_model=TicketSubmitResponse,
)
def submit_ticket(
    clinic_id: str,
    body: TicketSubmitRequest,
    _: None = Depends(verify_vapi_secret),
    db: Session = Depends(get_session),
):
    """
    Called by VAPI's submit_ticket tool at the end of a voice call.

    Validates the clinic exists in Cloud SQL, then appends one row to
    `Users.voice_agent_tickets` in BigQuery (analytics store, intentionally
    separate from the operational config in Cloud SQL).
    """
    clinic = db.get(Clinic, clinic_id)
    if not clinic or clinic.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Clinic not found")

    ticket_id = str(uuid.uuid4())
    details_json = json.dumps(body.details) if body.details is not None else None

    bq_client.query(
        f"""
        INSERT INTO {bq_table('voice_agent_tickets')} (
          ticket_id, clinic_id, vapi_call_id, created_at, caller_phone, caller_name,
          patient_match_status, blueprint_patient_id, last4_confirmed, intent_category,
          summary, details, suggested_followup, urgency, status
        ) VALUES (
          @ticket_id, @clinic_id, @vapi_call_id, CURRENT_TIMESTAMP(), @caller_phone, @caller_name,
          @patient_match_status, @blueprint_patient_id, @last4_confirmed, @intent_category,
          @summary, @details, @suggested_followup, @urgency, 'open'
        )
        """,
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("ticket_id", "STRING", ticket_id),
            bigquery.ScalarQueryParameter("clinic_id", "STRING", clinic_id),
            bigquery.ScalarQueryParameter("vapi_call_id", "STRING", body.vapi_call_id),
            bigquery.ScalarQueryParameter("caller_phone", "STRING", body.caller_phone),
            bigquery.ScalarQueryParameter("caller_name", "STRING", body.caller_name),
            bigquery.ScalarQueryParameter("patient_match_status", "STRING", body.patient_match_status),
            bigquery.ScalarQueryParameter("blueprint_patient_id", "STRING", body.blueprint_patient_id),
            bigquery.ScalarQueryParameter("last4_confirmed", "BOOL", body.last4_confirmed),
            bigquery.ScalarQueryParameter("intent_category", "STRING", body.intent_category),
            bigquery.ScalarQueryParameter("summary", "STRING", body.summary),
            bigquery.ScalarQueryParameter("details", "STRING", details_json),
            bigquery.ScalarQueryParameter("suggested_followup", "STRING", body.suggested_followup),
            bigquery.ScalarQueryParameter("urgency", "STRING", body.urgency),
        ])
    ).result()

    return TicketSubmitResponse(ticket_id=ticket_id)


# ── Capability toggles ────────────────────────────────────────────────────────


class CapabilityItem(BaseModel):
    id: str
    display_name: str
    description: str
    supported_pms: list[str] | None
    pms_compatible: bool
    enabled: bool
    updated_at: str | None = None
    updated_by: str | None = None


class CapabilitiesListResponse(BaseModel):
    clinic_id: str
    pms_type: str
    capabilities: list[CapabilityItem]


class CapabilityToggleRequest(BaseModel):
    enabled: bool
    config: dict | None = None


def _isoformat(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@router.get(
    "/clinics/{clinic_id}/voice_agent/capabilities",
    response_model=CapabilitiesListResponse,
)
def list_capabilities(
    clinic_id: str,
    caller: dict = Depends(verify_token),
    db: Session = Depends(get_session),
):
    """
    List toggleable voice-agent capabilities with per-clinic enablement state.
    Always-on capabilities are excluded.
    """
    clinic = _get_clinic_or_404(db, clinic_id)
    require_write_access(clinic.instance_id, caller)  # read gated by write

    pms_type = clinic.pms_type or "none"

    rows = list(db.scalars(
        select(VoiceAgentCapability).where(VoiceAgentCapability.clinic_id == clinic_id)
    ))
    state = {r.capability_id: r for r in rows}

    items: list[CapabilityItem] = []
    for cap in CAPABILITY_METADATA:
        if cap.always_on:
            continue
        row = state.get(cap.id)
        items.append(CapabilityItem(
            id=cap.id,
            display_name=cap.display_name,
            description=cap.description,
            supported_pms=list(cap.supported_pms) if cap.supported_pms is not None else None,
            pms_compatible=is_pms_compatible(cap, pms_type),
            enabled=bool(row.enabled) if row else False,
            updated_at=_isoformat(row.updated_at) if row else None,
            updated_by=row.updated_by if row else None,
        ))

    return CapabilitiesListResponse(clinic_id=clinic_id, pms_type=pms_type, capabilities=items)


@router.put(
    "/clinics/{clinic_id}/voice_agent/capabilities/{capability_id}",
    response_model=CapabilityItem,
)
def toggle_capability(
    clinic_id: str,
    capability_id: str,
    body: CapabilityToggleRequest,
    caller: dict = Depends(verify_token),
    db: Session = Depends(get_session),
):
    """
    Upsert a capability toggle for this clinic.
    """
    cap = CAPABILITY_METADATA_BY_ID.get(capability_id)
    if cap is None:
        raise HTTPException(status_code=404, detail=f"Unknown capability: {capability_id}")
    if cap.always_on:
        raise HTTPException(
            status_code=400,
            detail=f"Capability {capability_id} is always-on and cannot be toggled",
        )

    clinic = _get_clinic_or_404(db, clinic_id)
    require_write_access(clinic.instance_id, caller)

    pms_type = clinic.pms_type or "none"
    if body.enabled and not is_pms_compatible(cap, pms_type):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Capability {capability_id} is not supported for pms_type={pms_type!r}. "
                f"Supported: {cap.supported_pms}"
            ),
        )

    updater = caller.get("email") or caller.get("uid") or "unknown"

    row = db.get(VoiceAgentCapability, (clinic_id, capability_id))
    if row is None:
        row = VoiceAgentCapability(
            clinic_id=clinic_id,
            capability_id=capability_id,
            enabled=body.enabled,
            config=body.config,
            updated_by=updater,
        )
        db.add(row)
    else:
        row.enabled = body.enabled
        row.config = body.config
        row.updated_by = updater

    db.flush()  # ensure updated_at gets populated for the response
    db.refresh(row)

    return CapabilityItem(
        id=cap.id,
        display_name=cap.display_name,
        description=cap.description,
        supported_pms=list(cap.supported_pms) if cap.supported_pms is not None else None,
        pms_compatible=is_pms_compatible(cap, pms_type),
        enabled=bool(row.enabled),
        updated_at=_isoformat(row.updated_at),
        updated_by=row.updated_by,
    )
