"""
Build a VAPI assistant configuration for a clinic.

Reads from Cloud SQL ORM:
  - Clinic + ClinicLocationDetails — name, address, hours, time_zone, country
  - VoiceAgentCapability rows                — which toggleable capabilities are enabled

The assembled config is a dict shaped for ``vapi.client.Vapi.assistants.create()``
(snake_case kwargs). Voice settings, model, and transcriber model are hardcoded
for v1 — revisit if a clinic asks for variation.

Out of scope for this iteration (will be added when the transcript-analysis
rebuild lands):
  - FAQ knowledge base
  - Approved script sections (Scope of Practice / Not Offered / Caller's Needs / Protocols)

The system prompt below is a v1 placeholder — sections marked TODO will be
populated once the user provides the canonical prompt structure.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.core.orm import Clinic, VoiceAgentCapability
from api.core.secrets import get_secret
from api.voice_agent.capabilities import (
    CAPABILITY_REGISTRY,
    Capability,
    SubmitTicket,
)
from api.voice_agent.locale import resolve as resolve_locale


log = logging.getLogger(__name__)


# Universal Information-Capture guidance. Not tied to any single capability —
# every call, regardless of toggles, needs this framing.
_INFORMATION_CAPTURE_FRAGMENT = """## Information Capture
Based on the caller's intent, collect at minimum:
- Caller's name (as spoken).
- Callback phone number.
- Reason for the call (in the caller's words).
- For appointment requests: preferred day(s) and time window, new-vs-existing patient status.
- Any clinical context the caller volunteers — but do not press for medical details beyond what's needed for triage."""


_BEHAVIOUR_GUIDELINES = """## Behaviour Guidelines
- Be warm, concise, and professional.
- Speak in the caller's words; don't introduce clinical jargon.
- If you don't know something, say so — never invent details about the clinic, services, or pricing.
- You cannot confirm a specific appointment time. Capture preferences in the ticket; staff will follow up.
- If the caller is distressed, acknowledge it before moving forward."""


def build_first_message(clinic_name: str) -> str:
    return f"You've reached {clinic_name}, how can I assist you today?"


def _vapi_credential_id() -> str:
    """VAPI ``apiRequest`` tools authenticate via a credentialId that injects
    ``X-Vapi-Secret`` on the call. The credential is created once per VAPI org
    (not per clinic); its ID is stored in SM."""
    return get_secret("vapi-cortex-credential-id")


def _instantiate_capabilities(
    clinic: Clinic,
    enabled_capability_ids: list[str],
    credential_id: str,
) -> list[Capability]:
    """
    Build the ordered list of Capability instances for this clinic.

    Order:
      1. Toggleable capabilities (in CAPABILITY_REGISTRY declaration order) —
         only those whose ID is in enabled_capability_ids AND whose
         supported_pms includes this clinic's pms_type.
      2. Always-on capabilities (e.g. SubmitTicket) appended last so the
         "closing & ticket submission" block is at the end of the prompt.
    """
    enabled = set(enabled_capability_ids)
    instantiated: list[Capability] = []

    def make(cls: type[Capability]) -> Capability:
        return cls(
            clinic_id=clinic.clinic_id,
            clinic_name=clinic.clinic_name,
            pms_type=clinic.pms_type or "none",
            credential_id=credential_id,
        )

    # Toggleable first, in registry order
    for cap_id, cls in CAPABILITY_REGISTRY.items():
        if cls.always_on:
            continue
        if cap_id not in enabled:
            continue
        try:
            instantiated.append(make(cls))
        except ValueError as e:
            log.warning(
                "Skipping enabled capability %s for clinic_id=%s: %s",
                cap_id, clinic.clinic_id, e,
            )

    # Always-on last
    for cls in CAPABILITY_REGISTRY.values():
        if not cls.always_on:
            continue
        try:
            instantiated.append(make(cls))
        except ValueError as e:
            # An always-on capability that refuses this clinic is a spec bug.
            raise RuntimeError(
                f"Always-on capability {cls.__name__} refused clinic: {e}"
            ) from e

    if not any(isinstance(c, SubmitTicket) for c in instantiated):
        raise RuntimeError(
            "No SubmitTicket capability instantiated — assistant cannot persist call outcomes."
        )

    return instantiated


def _hours_block(clinic: Clinic) -> str:
    loc = clinic.location
    if loc is None:
        return ""
    days = [
        ("Monday", loc.hours_monday),
        ("Tuesday", loc.hours_tuesday),
        ("Wednesday", loc.hours_wednesday),
        ("Thursday", loc.hours_thursday),
        ("Friday", loc.hours_friday),
        ("Saturday", loc.hours_saturday),
        ("Sunday", loc.hours_sunday),
    ]
    rendered = "\n".join(f"- {d}: {h or 'Closed'}" for d, h in days)
    return f"## Hours of Operation\n{rendered}"


def _booking_protocols(caps: list[Capability]) -> str:
    """Compose BOOKING PROTOCOLS from capability fragments + universal capture.

    Layout:
      <toggleable cap fragments, in instantiation order>
      <Information Capture — universal>
      <always-on cap fragments — SubmitTicket's 'Closing' goes last>
    """
    toggleable = [c.prompt_fragment for c in caps if not c.always_on]
    always_on = [c.prompt_fragment for c in caps if c.always_on]
    return "\n\n".join(toggleable + [_INFORMATION_CAPTURE_FRAGMENT] + always_on)


def build_system_prompt(clinic: Clinic, caps: list[Capability], locale: dict) -> str:
    """
    v1 placeholder. The canonical prompt structure (knowledge base layout, tone,
    section ordering) is being defined — replace this body once the user
    provides it. Until then, produces a working prompt that wires up the
    capability fragments and clinic context.
    """
    address = clinic.address or "(address not configured)"
    parts = [
        locale["prompt_block"],
        f"You are the friendly, professional receptionist at {clinic.clinic_name}.",
        f"## Clinic\n- Name: {clinic.clinic_name}\n- Address: {address}",
        _hours_block(clinic),
        "# BOOKING PROTOCOLS",
        _booking_protocols(caps),
        _BEHAVIOUR_GUIDELINES,
    ]
    return "\n\n".join(p for p in parts if p)


def _enabled_capability_ids(db: Session, clinic_id: str) -> list[str]:
    rows = db.scalars(
        select(VoiceAgentCapability).where(
            VoiceAgentCapability.clinic_id == clinic_id,
            VoiceAgentCapability.enabled.is_(True),
        )
    ).all()
    return [r.capability_id for r in rows]


def build_agent_config(db: Session, clinic: Clinic) -> dict:
    """
    Returns a complete VAPI assistant creation payload for the given clinic.

    Reads enabled capability IDs from Cloud SQL. The clinic ORM must have its
    `location` relationship loaded (the default lazy load suffices when
    accessed inside the same session).

    Returns a dict suitable for ``client.assistants.create(**config)``.
    """
    locale = resolve_locale(clinic)
    credential_id = _vapi_credential_id()
    enabled_ids = _enabled_capability_ids(db, clinic.clinic_id)
    caps = _instantiate_capabilities(clinic, enabled_ids, credential_id)

    system_prompt = build_system_prompt(clinic, caps, locale)
    tools = [c.to_vapi_tool() for c in caps]

    return {
        "name": clinic.clinic_name,
        "first_message": build_first_message(clinic.clinic_name),
        "first_message_interruptions_enabled": True,
        "model": {
            "provider": "openai",
            "model": "gpt-4o",
            "messages": [{"role": "system", "content": system_prompt}],
            "tools": tools,
        },
        # Hardcoded for v1; revisit if a clinic asks for variation.
        "voice": {"speed": 0.9, "provider": "vapi", "voiceId": "Emma"},
        "transcriber": {
            "provider": "deepgram",
            "model": "nova-2",
            "language": locale["transcriber_language"],
        },
    }
