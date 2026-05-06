"""
Build a VAPI assistant configuration for a clinic.

Reads from Cloud SQL ORM:
  - Clinic + ClinicLocationDetails — name, address, hours, time_zone, country
  - VoiceAgentCapability rows                — which toggleable capabilities are enabled

The assembled config is a dict shaped for ``vapi.client.Vapi.assistants.create()``
(snake_case kwargs). Voice settings, model, and transcriber model are hardcoded
for v1 — revisit if a clinic asks for variation.
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
    PatientMatch,
    SubmitTicket,
)
from api.voice_agent.locale import resolve as resolve_locale


log = logging.getLogger(__name__)


def build_first_message(clinic_name: str) -> str:
    return (
        f"Thank you for calling {clinic_name}. My name is Emma, "
        "your virtual hearing assistant. How can I help you today?"
    )


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


def _capability_by_id(caps: list[Capability], capability_id: str) -> Capability | None:
    for c in caps:
        if c.id == capability_id:
            return c
    return None


def _identity_section(clinic: Clinic) -> str:
    return (
        "## Identity\n"
        f"- You are the receptionist at {clinic.clinic_name}. "
        "Your job is to help the right patients get in and to ensure every "
        "patient who does come in is ready to take action on their hearing health."
    )


def _task_overview_section() -> str:
    return (
        "## Task Overview\n"
        "- Your job is to follow the steps listed below and in order to assess "
        "the caller's needs, answer questions and make bookings.\n"
        "- In addition you must collect information in order for clinic staff "
        "to have the sufficient context about the caller. The sections/bullets "
        "marked with [info collection point] indicate where you need to keep "
        "track of info.\n"
        "- The intended conversation follows the flow detailed below. Everything "
        "in quotation marks are phrases that you can say; anything else is instructions."
    )


def _opening_section(clinic: Clinic) -> str:
    return (
        "## Opening\n"
        "- Opening messages\n"
        f'  - "Thank you for calling {clinic.clinic_name}. My name is Emma, '
        'your virtual hearing assistant. How can I help you today?" '
        "<wait for user response>\n"
        '  - "Who am I speaking with?" <wait for user response>\n'
        f'  - "Nice to meet you [name]. I\'m really happy you called {clinic.clinic_name} '
        'and I\'ll do my best to help." <wait for user response>\n'
        '  - "I see you\'re calling from [number]. If I need to call you back '
        'is this the best number for you?" <wait for user response>'
    )


def _caller_classification_section(caps: list[Capability]) -> str:
    patient_match = _capability_by_id(caps, PatientMatch.id)
    existing_lookup_block = (
        patient_match.prompt_fragment if patient_match
        else "_(Lookup Patient capability not enabled for this clinic.)_"
    )
    return (
        "## Caller Classification\n"
        "- Determine whether the caller is new to the clinic or an existing "
        "patient, determine if they are calling on behalf of someone else.\n"
        '  - "Have you visited our office before?" [info collection point] '
        "<wait for user response>\n"
        "- New Caller\n"
        '  - "How did you hear about us?" [info collection point] '
        "<wait for user response>\n"
        '  - "Have you ever worn or tried hearing aids before?" '
        "<wait for user response>\n"
        '  - "Have you had a hearing test in the last 6 months?" '
        "<wait for user response>\n"
        "  - Proceed to the New Patient Flow.\n"
        "- Existing Patient\n"
        '  - "Let me find you in our system." → Use the Lookup Patient capability.\n'
        f"\n{existing_lookup_block}\n"
        "  - Proceed to the Existing Patient Flow."
    )


def _new_patient_flow_section() -> str:
    # TODO: extend once the full New Patient Flow is provided.
    return (
        "## New Patient Flow\n"
        '- "Can I ask what\'s been prompting you to look into your hearing '
        'health right now?" <wait for user response>'
    )


def _existing_patient_flow_section() -> str:
    # TODO: populate once the full Existing Patient Flow is provided.
    return ""


def _trailing_capability_blocks(
    caps: list[Capability],
    inlined_ids: set[str],
) -> list[str]:
    """Capability fragments not already inlined upstream.

    Toggleable fragments first (in registry order), always-on last so
    SubmitTicket's closing instructions sit at the very end of the prompt.
    """
    toggleable = [
        c.prompt_fragment for c in caps
        if not c.always_on and c.id not in inlined_ids
    ]
    always_on = [
        c.prompt_fragment for c in caps
        if c.always_on and c.id not in inlined_ids
    ]
    return toggleable + always_on


def build_system_prompt(clinic: Clinic, caps: list[Capability], locale: dict) -> str:
    inlined_ids = {PatientMatch.id}
    parts = [
        locale["prompt_block"],
        _identity_section(clinic),
        _task_overview_section(),
        _hours_block(clinic),
        _opening_section(clinic),
        _caller_classification_section(caps),
        _new_patient_flow_section(),
        _existing_patient_flow_section(),
        *_trailing_capability_blocks(caps, inlined_ids),
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
