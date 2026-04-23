"""
Provisioning orchestration.

Handles the full flow of setting up a new instance.

NOTE: BigQuery does not support multi-table transactions. write_provision_to_bq
attempts best-effort compensating deletes on failure, but rows written to the
streaming buffer cannot be deleted for up to 90 minutes.
"""
import logging
import uuid
from typing import List

log = logging.getLogger(__name__)


def provision_instance(
    instance_name: str,
    primary_contact_name: str,
    primary_contact_email: str,
    primary_contact_uid: str,
) -> dict:
    """
    Create a new instance record.

    Returns:
        dict with instance_id and core fields
    """
    return {k: v for k, v in {
        "instance_id": str(uuid.uuid4()),
        "instance_name": instance_name,
        "primary_contact_name": primary_contact_name,
        "primary_contact_email": primary_contact_email,
        "primary_contact_uid": primary_contact_uid,
        "google_ads_customer_id": None,
        "invoca_profile_id": None,
    }.items() if v is not None}


def provision_clinic(
    clinic_data: dict,
    instance_id: str,
) -> tuple[dict, str, str]:
    """
    Create a new clinic record.

    Args:
        clinic_data: ClinicCreate fields as dict (includes ref_id)
        instance_id: Parent instance ID

    Returns:
        tuple of (clinic dict for storage, ref_id, clinic_id)
    """
    clinic_id = str(uuid.uuid4())
    ref_id = clinic_data.pop("ref_id", None)  # Remove ref_id, not stored in BigQuery

    clinic = {k: v for k, v in {
        **clinic_data,
        "clinic_id": clinic_id,
        "instance_id": instance_id,
        "google_ads_campaign_id": None,
        "invoca_campaign_id": None,
    }.items() if v is not None}

    return clinic, ref_id, clinic_id


def provision_full_account(
    instance_create: dict,
    clinics_create: List[dict],
    primary_contact_uid: str,
) -> dict:
    """
    Full provisioning flow for a new account.

    Args:
        instance_create: InstanceCreate fields as dict
        clinics_create: List of ClinicCreate fields as dicts (each with ref_id)
        primary_contact_uid: Firebase UID of the owner

    Returns:
        dict with:
        - instance: Full instance data for BigQuery
        - clinics: List of full clinic data for BigQuery
        - clinic_id_map: Mapping of ref_id -> clinic_id for linking staff/services/insurance
    """
    instance = provision_instance(
        instance_name=instance_create["instance_name"],
        primary_contact_name=instance_create["primary_contact_name"],
        primary_contact_email=instance_create["primary_contact_email"],
        primary_contact_uid=primary_contact_uid,
    )

    clinics = []
    clinic_id_map = {}
    for clinic_data in clinics_create:
        clinic, ref_id, clinic_id = provision_clinic(
            clinic_data=clinic_data.copy(),
            instance_id=instance["instance_id"],
        )
        clinics.append(clinic)
        if ref_id:
            clinic_id_map[ref_id] = clinic_id

    return {
        "instance": instance,
        "clinics": clinics,
        "clinic_id_map": clinic_id_map,
    }


def write_provision_to_bq(
    instance: dict,
    clinics: list[dict],
    staff: list[dict],
    services: list[dict],
    insurance: list[dict],
) -> None:
    """
    Write provisioned account data to BigQuery in dependency order.

    On failure, attempts best-effort compensating deletes of already-written tables.
    Compensating deletes may not succeed if data is still in the streaming buffer.
    """
    from api.deps import bq_insert, bq_delete  # imported here to avoid circular import at module load

    instance_id = instance["instance_id"]
    _INSERT_ORDER = ["instances", "clinics", "staff", "services", "insurance"]
    writes = {
        "instances": [instance],
        "clinics": clinics,
        "staff": staff,
        "services": services,
        "insurance": insurance,
    }
    written: list[str] = []

    try:
        for table in _INSERT_ORDER:
            rows = writes[table]
            if rows:
                bq_insert(table, rows)
                written.append(table)
    except Exception as exc:
        next_table = next((t for t in _INSERT_ORDER if t not in written), "unknown")
        _compensate(instance_id, written, bq_delete)
        raise RuntimeError(
            f"Provisioning failed on '{next_table}' insert. "
            f"Attempted compensating deletes for: {written}."
        ) from exc


def _compensate(instance_id: str, written: list[str], bq_delete) -> None:
    """Best-effort rollback — deletes rows by instance_id in reverse insert order.

    Failures are logged but not raised; partial cleanup is expected because of
    BigQuery's streaming buffer (90-minute delay before rows can be deleted).
    """
    for table in reversed(written):
        try:
            bq_delete(table, {"instance_id": instance_id})
            log.warning("Compensated: deleted %s rows for instance_id=%s", table, instance_id)
        except Exception as e:
            log.error(
                "Compensating delete FAILED for table=%s instance_id=%s: %s. "
                "Manual cleanup may be required once the streaming buffer clears.",
                table, instance_id, e,
            )
