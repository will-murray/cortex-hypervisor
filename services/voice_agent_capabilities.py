"""
Voice-agent capability metadata — mirror of voice_agent_builder/capabilities.py.

The hypervisor doesn't build VAPI tool JSON or compose prompt fragments; that
is voice_agent_builder's job. But the hypervisor DOES need to know:
  - what capability IDs exist (to validate toggle requests)
  - their display_name / description (to render in the dashboard)
  - their supported_pms (to reject incompatible toggles)
  - whether they're always-on (to exclude from dashboard toggle UI)

These two repos are deployed separately, so we duplicate the metadata here
rather than introducing a shared package. **This list must stay in sync
with voice_agent_builder/capabilities.py.**

When adding a capability:
  1. Add the class in voice_agent_builder/capabilities.py.
  2. Add the matching metadata entry here.
  3. Redeploy both services.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CapabilityMetadata:
    id: str
    display_name: str
    description: str
    # None = PMS-agnostic; otherwise a tuple of compatible Users.clinics.pms_type values.
    supported_pms: tuple[str, ...] | None
    always_on: bool


# Order matters: this is the order capabilities appear in the dashboard.
CAPABILITY_METADATA: list[CapabilityMetadata] = [
    CapabilityMetadata(
        id="patient_match",
        display_name="Patient identity verification",
        description=(
            "Confirm an existing patient by first + last name and the last 4 "
            "digits of the phone number on file. Requires the patient record "
            "to already exist in the PMS."
        ),
        supported_pms=("blueprint",),
        always_on=False,
    ),
    CapabilityMetadata(
        id="list_appointment_types",
        display_name="Appointment type lookup",
        description=(
            "Look up the clinic's bookable appointment types (e.g. 'Hearing "
            "test', 'Fitting') and their durations. Required precondition for "
            "finding available slots — every availability search needs an "
            "appointment type ID."
        ),
        supported_pms=("blueprint",),
        always_on=False,
    ),
    CapabilityMetadata(
        id="find_available_slots",
        display_name="Bookable appointment slot search",
        description=(
            "Find concrete bookable time slots in a date range for a specific "
            "appointment type. Returns dates and times the clinic actually has "
            "open — not just provider work blocks. Requires an event_type_id, "
            "obtained via list_appointment_types."
        ),
        supported_pms=("blueprint",),
        always_on=False,
    ),
    CapabilityMetadata(
        id="submit_ticket",
        display_name="Submit ticket",
        description=(
            "Foundational. Every call produces one ticket summarising the "
            "caller's need, collected info, and a suggested follow-up for "
            "clinic staff."
        ),
        supported_pms=None,
        always_on=True,
    ),
]

CAPABILITY_METADATA_BY_ID: dict[str, CapabilityMetadata] = {
    c.id: c for c in CAPABILITY_METADATA
}


def is_pms_compatible(cap: CapabilityMetadata, pms_type: str | None) -> bool:
    """Return True if the capability can be enabled for a clinic with this pms_type."""
    if cap.supported_pms is None:
        return True
    return (pms_type or "none") in cap.supported_pms
