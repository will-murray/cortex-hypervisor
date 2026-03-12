"""
Provisioning orchestration.

Handles the full flow of setting up a new instance with all external services.
"""
import uuid
from typing import List

from integrations import invoca, google_ads


def provision_instance(
    instance_name: str,
    primary_contact_name: str,
    primary_contact_uid: str,
    invoca_network_id: str,
) -> dict:
    """
    Provision external services for a new instance.

    Creates:
    - Google Ads customer account
    - Google Ads campaign
    - Invoca profile

    Returns:
        dict with instance_id and all external service IDs
    """
    instance_id = str(uuid.uuid4())

    # Create Google Ads customer account
    google_ads_customer_id = google_ads.create_customer(
        customer_name=instance_name
    )

    # Create campaign under that account
    google_ads_campaign_id = google_ads.create_campaign(
        customer_id=google_ads_customer_id,
        campaign_name=instance_name
    )

    # Create Invoca profile
    invoca_profile_id = invoca.create_profile(
        network_id=invoca_network_id,
        profile_name=instance_name
    )

    return {
        "instance_id": instance_id,
        "instance_name": instance_name,
        "primary_contact_name": primary_contact_name,
        "primary_contact_uid": primary_contact_uid,
        "google_ads_customer_id": google_ads_customer_id,
        "google_ads_campaign_id": google_ads_campaign_id,
        "invoca_profile_id": invoca_profile_id,
    }


def provision_clinic(
    clinic_data: dict,
    instance_id: str,
    google_ads_customer_id: str,
    google_ads_campaign_id: str,
    invoca_profile_id: str,
) -> tuple[dict, str, str]:
    """
    Provision external services for a new clinic.

    Creates:
    - Google Ads ad group under instance's campaign
    - Invoca campaign under instance's profile

    Args:
        clinic_data: ClinicCreate fields as dict (includes ref_id)
        instance_id: Parent instance ID
        google_ads_customer_id: Instance's Google Ads account
        google_ads_campaign_id: Instance's campaign
        invoca_profile_id: Instance's Invoca profile

    Returns:
        tuple of (clinic dict for storage, ref_id, clinic_id)
    """
    clinic_id = str(uuid.uuid4())
    ref_id = clinic_data.pop("ref_id", None)  # Remove ref_id, not stored in BigQuery
    clinic_name = clinic_data["clinic_name"]
    transfer_number = clinic_data["transfer_number"]

    # Create Google Ads ad group
    google_ads_ad_group_id = google_ads.create_ad_group(
        customer_id=google_ads_customer_id,
        campaign_id=google_ads_campaign_id,
        ad_group_name=clinic_name
    )

    # Create Invoca campaign
    invoca_campaign_id = invoca.create_campaign(
        profile_id=invoca_profile_id,
        campaign_name=clinic_name,
        destination_number=transfer_number
    )

    clinic = {
        **clinic_data,
        "clinic_id": clinic_id,
        "instance_id": instance_id,
        "google_ads_ad_group_id": google_ads_ad_group_id,
        "invoca_campaign_id": invoca_campaign_id,
    }

    return clinic, ref_id, clinic_id


def provision_full_account(
    instance_create: dict,
    clinics_create: List[dict],
    primary_contact_uid: str,
    invoca_network_id: str,
) -> dict:
    """
    Full provisioning flow for a new account.

    Args:
        instance_create: InstanceCreate fields as dict
        clinics_create: List of ClinicCreate fields as dicts (each with ref_id)
        primary_contact_uid: Firebase UID of the owner
        invoca_network_id: Your Invoca network ID

    Returns:
        dict with:
        - instance: Full instance data for BigQuery
        - clinics: List of full clinic data for BigQuery
        - clinic_id_map: Mapping of ref_id -> clinic_id for linking staff/services/insurance
    """
    # Provision instance-level resources
    instance = provision_instance(
        instance_name=instance_create["instance_name"],
        primary_contact_name=instance_create["primary_contact_name"],
        primary_contact_uid=primary_contact_uid,
        invoca_network_id=invoca_network_id,
    )

    # Provision each clinic
    clinics = []
    clinic_id_map = {}  # ref_id -> clinic_id
    for clinic_data in clinics_create:
        clinic, ref_id, clinic_id = provision_clinic(
            clinic_data=clinic_data.copy(),  # Copy to avoid mutating original
            instance_id=instance["instance_id"],
            google_ads_customer_id=instance["google_ads_customer_id"],
            google_ads_campaign_id=instance["google_ads_campaign_id"],
            invoca_profile_id=instance["invoca_profile_id"],
        )
        clinics.append(clinic)
        if ref_id:
            clinic_id_map[ref_id] = clinic_id

    return {
        "instance": instance,
        "clinics": clinics,
        "clinic_id_map": clinic_id_map,
    }
