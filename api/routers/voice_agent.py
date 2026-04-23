"""
Voice agent lifecycle management — per clinic, opt-in.

Call flow:
    Patient → clinic primary number → no answer → forwards to Twilio number → VAPI agent

Activate provisions a Twilio phone number and VAPI assistant for the clinic.
Deactivate releases both.

Activation is gated by script-section approval: all four sections in
Users.agent_script_sections must have at least one row with state='approved'
for this clinic — see services/script_approval.py.

Also hosts the VAPI-authed submit_ticket endpoint, called by the voice agent
at the end of a call to write a row to Users.voice_agent_tickets.

TODO (Round 3): Wire activate/deactivate to Twilio + VAPI APIs via
services/twilio.py and services/vapi.py once those clients are implemented.
"""
import json
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from google.cloud import bigquery
from pydantic import BaseModel

from api.deps import (
    bq_update, bq_table, bq_client,
    verify_token, require_write_access, get_instance_id_or_404,
)
from api.routers.blueprint import verify_vapi_secret
from services.script_approval import require_full_approval

router = APIRouter()

_VOICE_AGENT_FIELDS = [
    "voice_agent_status",
    "twilio_phone_number",
    "twilio_phone_sid",
    "twilio_verified_caller_id",
    "vapi_assistant_id",
    "vapi_phone_number_id",
]


def _get_clinic_or_404(clinic_id: str) -> dict:
    rows = list(bq_client.query(
        f"SELECT * FROM {bq_table('clinics')} WHERE clinic_id = @clinic_id",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("clinic_id", "STRING", clinic_id)
        ])
    ).result())
    if not rows:
        raise HTTPException(status_code=404, detail="Clinic not found")
    return dict(rows[0])


@router.post("/clinics/{clinic_id}/voice_agent/activate")
def activate_voice_agent(clinic_id: str, caller: dict = Depends(verify_token)):
    """
    Opt a clinic into Cortex Intercept (AI call handling).

    Provisions a Twilio phone number and VAPI assistant for the clinic, then stores
    the resulting IDs. The clinic's existing phone system must be configured to
    forward unanswered calls to the provisioned Twilio number.

    TODO (Round 3): Replace the placeholder response with actual Twilio number
    purchase + VAPI assistant creation via services/twilio.py and services/vapi.py.
    """
    clinic = _get_clinic_or_404(clinic_id)
    instance_id = clinic["instance_id"]
    require_write_access(instance_id, caller)

    if clinic.get("voice_agent_status") == "active":
        raise HTTPException(status_code=409, detail="Voice agent is already active for this clinic")

    # Hard gate: refuse unless all four script sections are approved. Raises 409.
    require_full_approval(clinic_id)

    # Mark as provisioning — Round 3 will replace this with actual Twilio/VAPI calls
    bq_update("clinics", {"clinic_id": clinic_id}, {"voice_agent_status": "provisioning"})

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
def deactivate_voice_agent(clinic_id: str, caller: dict = Depends(verify_token)):
    """
    Deactivate and deprovision the voice agent for this clinic.

    Releases the Twilio phone number and deletes the VAPI assistant, then clears
    all voice agent fields on the clinic record.

    TODO (Round 3): Add Twilio number release + VAPI assistant deletion before
    clearing the fields.
    """
    clinic = _get_clinic_or_404(clinic_id)
    instance_id = clinic["instance_id"]
    require_write_access(instance_id, caller)

    if clinic.get("voice_agent_status") == "inactive":
        raise HTTPException(status_code=409, detail="Voice agent is not active for this clinic")

    # TODO (Round 3): release Twilio number + delete VAPI assistant here

    bq_update("clinics", {"clinic_id": clinic_id}, {
        "voice_agent_status": "inactive",
        "twilio_phone_number": None,
        "twilio_phone_sid": None,
        "twilio_verified_caller_id": False,
        "vapi_assistant_id": None,
        "vapi_phone_number_id": None,
    })

    return {"status": "success", "clinic_id": clinic_id, "voice_agent_status": "inactive"}


@router.post("/clinics/{clinic_id}/voice_agent/verify_caller_id")
def verify_caller_id(clinic_id: str, caller: dict = Depends(verify_token)):
    """
    Initiate Twilio outbound caller ID verification for the clinic's primary phone number.

    When verified, outbound calls from the VAPI agent will display the clinic's
    familiar number rather than the Twilio number.

    TODO (Round 3): Implement Twilio caller ID verification via services/twilio.py.
    """
    clinic = _get_clinic_or_404(clinic_id)
    require_write_access(clinic["instance_id"], caller)

    if clinic.get("voice_agent_status") not in ("active", "provisioning"):
        raise HTTPException(
            status_code=400,
            detail="Voice agent must be activated before verifying caller ID"
        )

    raise HTTPException(
        status_code=501,
        detail="Twilio caller ID verification not yet implemented — coming in Round 3"
    )


# ── VAPI-authed: submit_ticket ─────────────────────────────────────────────────


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
):
    """
    Called by VAPI's submit_ticket tool at the end of a voice call. Appends one
    row to Users.voice_agent_tickets with status='open'. No webhook fallback —
    if the agent fails to call this, the ticket is lost. The VAPI recording
    remains available.
    """
    exists = list(bq_client.query(
        f"SELECT 1 FROM {bq_table('clinics')} WHERE clinic_id = @clinic_id LIMIT 1",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("clinic_id", "STRING", clinic_id)
        ])
    ).result())
    if not exists:
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
