"""
VAPI assistant lifecycle management for cortex-hypervisor.

Handles creating, updating, and deleting VAPI voice agents on behalf of the
activate/deactivate API endpoints. Builds system prompts from BigQuery clinic
data directly — no dependency on voice_agent_builder package.

Credentials are read from Secret Manager:
    vapi-api-key
    vapi-webhook-secret
    twilio-account-sid
    twilio-auth-token

Environment variables:
    CORTEX_API_BASE_URL   Public URL of this API (used in VAPI tool definitions)
"""
import json
import os

import httpx
from google.cloud import bigquery

from services.locale import resolve as resolve_locale
from services.secrets import get_secret

VAPI_BASE = "https://api.vapi.ai"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {get_secret('vapi-api-key')}",
        "Content-Type": "application/json",
    }


# ── System prompt ─────────────────────────────────────────────────────────────

def _build_tools(clinic_id: str, pms_type: str) -> list[dict]:
    """Build VAPI tool definitions based on the clinic's PMS type."""
    base = os.environ.get("CORTEX_API_BASE_URL", "http://localhost:8000")
    secret = get_secret("vapi-webhook-secret")

    if pms_type != "blueprint":
        return []

    headers = {"X-Vapi-Secret": secret}
    return [
        {
            "type": "apiRequest",
            "name": "trigger_blueprint_cti",
            "description": (
                "Call this immediately when the call connects to open the caller's "
                "file in Blueprint for the clinic receptionist. "
                "This does NOT return patient data — ask the caller for their name directly."
            ),
            "url": f"{base}/blueprint/{clinic_id}/patient/lookup",
            "method": "POST",
            "headers": headers,
            "body": {
                "type": "object",
                "properties": {
                    "caller_phone": {
                        "type": "string",
                        "description": "Caller's phone number in E.164 format.",
                    }
                },
                "required": ["caller_phone"],
            },
        },
        {
            "type": "apiRequest",
            "name": "check_availability",
            "description": (
                "Check available appointment slots for a given appointment type and date range. "
                "Always call this before discussing specific times. "
                "Use the event_type_id from the Appointment Types list in your instructions. "
                "The response includes available slots with provider_id — note the provider_id "
                "for the slot the caller selects and pass it to create_appointment."
            ),
            "url": f"{base}/blueprint/{clinic_id}/availability",
            "method": "POST",
            "headers": headers,
            "body": {
                "type": "object",
                "properties": {
                    "event_type_id": {
                        "type": "integer",
                        "description": "Blueprint appointment type ID (from your Appointment Types list).",
                    },
                    "start_date": {"type": "string", "description": "YYYY-MM-DD — start of search window."},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD — end of search window."},
                },
                "required": ["event_type_id", "start_date", "end_date"],
            },
        },
        {
            "type": "apiRequest",
            "name": "create_appointment",
            "description": (
                "Book an appointment. Only call after the caller has confirmed a specific slot, "
                "given their name, and confirmed their callback number. "
                "Pass provider_id from the availability slot they selected."
            ),
            "url": f"{base}/blueprint/{clinic_id}/appointment",
            "method": "POST",
            "headers": headers,
            "body": {
                "type": "object",
                "properties": {
                    "event_type_id": {"type": "integer", "description": "Blueprint appointment type ID."},
                    "start_time": {"type": "string", "description": "Unix timestamp of slot start."},
                    "end_time": {"type": "string", "description": "Unix timestamp of slot end."},
                    "summary": {"type": "string", "description": "Patient name and contact info."},
                    "provider_id": {
                        "type": "integer",
                        "description": "Provider ID from the availability slot the caller chose.",
                    },
                    "patient_id": {
                        "type": "integer",
                        "description": "Existing Blueprint patient ID. Omit for new patients.",
                    },
                    "first_name": {"type": "string", "description": "Patient first name (new patients)."},
                    "last_name": {"type": "string", "description": "Patient last name (new patients)."},
                    "phone": {"type": "string", "description": "Patient phone number (new patients)."},
                },
                "required": ["event_type_id", "start_time", "end_time", "summary"],
            },
        },
    ]


def _build_system_prompt(clinic: dict, faqs: list, appt_types: list, locale: dict) -> str:
    pms_type = clinic.get("pms_type", "none")
    has_booking = pms_type == "blueprint"

    if has_booking:
        # appt_types came from Blueprint clinicConfiguration — include event_type_id
        appt_types_note = (
            "Each type has an event_type_id — use it when calling check_availability "
            "and create_appointment:"
        )
        booking_section = """
## Appointment Booking
You have direct access to the clinic's scheduling system (Blueprint OMS).

Workflow for every booking:
1. Call `trigger_blueprint_cti` immediately when the call connects (opens the caller's
   file for the receptionist — does not return patient data to you).
2. Ask the caller for their name and reason for calling.
3. Call `check_availability` with the correct event_type_id and a 1-2 week date window.
4. Present 2-3 available slots in plain language (e.g. "Tuesday at 10am or Thursday at 2pm").
5. Once the caller confirms a slot, confirm their callback number.
6. Call `create_appointment` with the slot's provider_id, the caller's name, and phone.
7. Confirm the booking with a clear summary: date, time, appointment type.

Rules:
- Never mention availability without calling check_availability first.
- Never book without a confirmed name and phone number.
- If the caller is unsure of appointment type, describe the options and ask.
"""
    else:
        appt_types_note = ""
        booking_section = f"""
## Appointment Booking
You cannot directly book appointments. Collect the caller's preferred time,
appointment type, name, and phone number. Let them know the clinic will call back to confirm.
The clinic uses {clinic.get("booking_system", "their scheduling system")} for scheduling.
"""

    return f"""{locale["prompt_block"]}

You are a friendly and professional receptionist at {clinic["clinic_name"]}.
Your job is to assist callers by answering questions about the clinic, providing
information about services, and helping with appointment bookings.

## About the Clinic
{clinic["about_us"]}

## Contact & Location
- Address: {clinic["address"]}
- Phone: {clinic["phone"]}

## Parking & Accessibility
- Parking: {clinic["parking_info"]}
- Accessibility: {clinic["accessibility_info"]}

## Hours of Operation
- Monday: {clinic["hours_monday"]}
- Tuesday: {clinic["hours_tuesday"]}
- Wednesday: {clinic["hours_wednesday"]}
- Thursday: {clinic["hours_thursday"]}
- Friday: {clinic["hours_friday"]}
- Saturday: {clinic["hours_saturday"]}
- Sunday: {clinic["hours_sunday"]}
{booking_section}
## Frequently Asked Questions
{json.dumps(faqs or [], indent=2)}

## Appointment Types
{appt_types_note}
{json.dumps(appt_types or [], indent=2)}

## Behaviour Guidelines
- Be warm, concise, and professional at all times.
- If you don't know the answer, offer to take a message or direct the caller to call back during business hours.
- Do not share internal IDs with callers.
- Do not make up information about services, prices, or availability.
"""


# ── Blueprint clinic config ───────────────────────────────────────────────────

def _fetch_blueprint_appt_types(clinic: dict) -> list[dict]:
    """
    Fetch appointment types from Blueprint's clinicConfiguration endpoint.
    Returns [{id, name, duration_minutes}] — the id is the event_type_id the
    VAPI agent must pass to check_availability and create_appointment.

    Falls back to empty list if Blueprint is unreachable at agent creation time.
    """
    server = clinic.get("blueprint_server")
    slug = clinic.get("blueprint_clinic_slug")
    api_key = clinic.get("blueprint_api_key")
    if not (server and slug and api_key):
        return []

    base = f"https://{server}/{slug}/rest"
    try:
        resp = httpx.get(
            f"{base}/clinicConfiguration/",
            params={"apiKey": api_key},
            timeout=15,
        )
        if not resp.is_success:
            return []
        data = resp.json()
        return [
            {
                "event_type_id": t["id"],
                "name": t["name"],
                "duration_minutes": t.get("duration"),
            }
            for t in data.get("appointmentTypes", [])
        ]
    except Exception:
        return []


# ── BigQuery helpers ──────────────────────────────────────────────────────────

def _fetch_clinic_data(bq_client: bigquery.Client, clinic_id: str) -> dict:
    rows = list(bq_client.query(
        "SELECT * FROM `{p}.Users.clinics` WHERE clinic_id = @clinic_id".format(
            p=os.environ["GCP_PROJECT"]
        ),
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("clinic_id", "STRING", clinic_id)
        ])
    ).result())
    if not rows:
        raise ValueError(f"Clinic not found: {clinic_id}")
    return dict(rows[0])


def _fetch_faqs(bq_client: bigquery.Client, clinic_id: str) -> list:
    rows = list(bq_client.query(
        "SELECT question, answer FROM `{p}.ClinicData.faq` WHERE clinic_id = @clinic_id".format(
            p=os.environ["GCP_PROJECT"]
        ),
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("clinic_id", "STRING", clinic_id)
        ])
    ).result())
    return [dict(r) for r in rows]


def _fetch_appt_types(bq_client: bigquery.Client, clinic_id: str) -> list:
    rows = list(bq_client.query(
        "SELECT appointment_name, duration FROM `{p}.Users.appointment_types` WHERE clinic_id = @clinic_id".format(
            p=os.environ["GCP_PROJECT"]
        ),
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("clinic_id", "STRING", clinic_id)
        ])
    ).result())
    return [dict(r) for r in rows]


# ── VAPI API calls ────────────────────────────────────────────────────────────

def import_twilio_number(twilio_phone_number: str, twilio_sid: str) -> str:
    """
    Import a Twilio number into VAPI.

    VAPI configures the Twilio number's webhook to route calls to VAPI.
    Returns the VAPI phone number ID.
    """
    resp = httpx.post(
        f"{VAPI_BASE}/phone-number",
        headers=_headers(),
        json={
            "provider": "twilio",
            "number": twilio_phone_number,
            "twilioAccountSid": get_secret("twilio-account-sid"),
            "twilioAuthToken": get_secret("twilio-auth-token"),
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def create_assistant(bq_client: bigquery.Client, clinic_id: str, phone_number_id: str) -> str:
    """
    Create a VAPI assistant for the clinic and assign the provisioned phone number.

    Fetches clinic data, FAQs, and appointment types from BigQuery to build
    the system prompt and tool set. Returns the VAPI assistant ID.
    """
    clinic = _fetch_clinic_data(bq_client, clinic_id)
    faqs = _fetch_faqs(bq_client, clinic_id)
    pms_type = clinic.get("pms_type", "none")
    locale = resolve_locale(clinic)

    if pms_type == "blueprint":
        # Fetch appointment types from Blueprint directly — these include the
        # event_type_id values the agent needs for check_availability/create_appointment.
        appt_types = _fetch_blueprint_appt_types(clinic)
    else:
        appt_types = _fetch_appt_types(bq_client, clinic_id)

    system_prompt = _build_system_prompt(clinic, faqs, appt_types, locale)
    tools = _build_tools(clinic_id, pms_type)

    model_config = {
        "provider": "openai",
        "model": "gpt-4o",
        "messages": [{"role": "system", "content": system_prompt}],
    }
    if tools:
        model_config["tools"] = tools

    payload = {
        "name": clinic["clinic_name"],
        "firstMessage": f"You've reached {clinic['clinic_name']}, how can I assist you today?",
        "firstMessageInterruptionsEnabled": True,
        "model": model_config,
        "transcriber": {
            "provider": "deepgram",
            "model": "nova-2",
            "language": locale["transcriber_language"],
        },
        "phoneNumberId": phone_number_id,
    }

    resp = httpx.post(
        f"{VAPI_BASE}/assistant",
        headers=_headers(),
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def delete_assistant(assistant_id: str) -> None:
    """Delete a VAPI assistant. Safe to call even if the assistant no longer exists."""
    try:
        resp = httpx.delete(
            f"{VAPI_BASE}/assistant/{assistant_id}",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 404:
            raise


def release_vapi_phone_number(phone_number_id: str) -> None:
    """Release a VAPI phone number. Safe to call even if already released."""
    try:
        resp = httpx.delete(
            f"{VAPI_BASE}/phone-number/{phone_number_id}",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 404:
            raise
