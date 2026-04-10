"""
Multi-campaign ID management per clinic.

Clinics can have multiple Google Ads campaign IDs and multiple Invoca campaign IDs.
These are stored in the clinic_campaigns table.

The legacy single-value google_ads_campaign_id and invoca_campaign_id columns on the
clinics table are retained for backwards compatibility but should not be used for new
campaign associations — use this router instead.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from google.cloud import bigquery

from api.deps import (
    bq_client, bq_table, bq_insert, bq_delete,
    verify_token, require_read_access, require_write_access,
    get_instance_id_or_404,
)
from api.models import ClinicCampaign, ClinicCampaignCreate

router = APIRouter()


@router.get("/campaigns/{instance_id}")
def list_campaigns_for_instance(instance_id: str, caller: dict = Depends(verify_token)):
    """List all campaign associations for every clinic in an instance."""
    require_read_access(instance_id, caller)

    rows = list(bq_client.query(
        f"SELECT * FROM {bq_table('clinic_campaigns')} WHERE instance_id = @instance_id",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("instance_id", "STRING", instance_id)
        ])
    ).result())
    return [dict(r) for r in rows]


@router.get("/campaigns/{instance_id}/{clinic_id}")
def list_campaigns_for_clinic(
    instance_id: str, clinic_id: str, caller: dict = Depends(verify_token)
):
    """List campaign associations for a specific clinic."""
    require_read_access(instance_id, caller)

    rows = list(bq_client.query(
        f"""
        SELECT * FROM {bq_table('clinic_campaigns')}
        WHERE instance_id = @instance_id AND clinic_id = @clinic_id
        """,
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("instance_id", "STRING", instance_id),
            bigquery.ScalarQueryParameter("clinic_id", "STRING", clinic_id),
        ])
    ).result())
    return [dict(r) for r in rows]


@router.post("/campaigns/{clinic_id}")
def add_campaign(
    clinic_id: str, body: ClinicCampaignCreate, caller: dict = Depends(verify_token)
):
    """Add a campaign ID association to a clinic."""
    instance_id = get_instance_id_or_404("clinics", "clinic_id", clinic_id, "Clinic not found")
    require_write_access(instance_id, caller)

    # Prevent duplicate (clinic_id, campaign_type, external_campaign_id)
    existing = list(bq_client.query(
        f"""
        SELECT id FROM {bq_table('clinic_campaigns')}
        WHERE clinic_id = @clinic_id
          AND campaign_type = @campaign_type
          AND external_campaign_id = @external_campaign_id
        """,
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("clinic_id", "STRING", clinic_id),
            bigquery.ScalarQueryParameter("campaign_type", "STRING", body.campaign_type),
            bigquery.ScalarQueryParameter("external_campaign_id", "STRING", body.external_campaign_id),
        ])
    ).result())
    if existing:
        raise HTTPException(status_code=409, detail="Campaign already associated with this clinic")

    campaign_id = str(uuid.uuid4())
    row = {
        "id": campaign_id,
        "clinic_id": clinic_id,
        "instance_id": instance_id,
        "campaign_type": body.campaign_type,
        "external_campaign_id": body.external_campaign_id,
    }
    if body.campaign_name:
        row["campaign_name"] = body.campaign_name

    bq_insert("clinic_campaigns", [row])
    return {"status": "success", "id": campaign_id}


@router.delete("/campaigns/entry/{campaign_id}")
def remove_campaign(campaign_id: str, caller: dict = Depends(verify_token)):
    """Remove a campaign association by its ID."""
    instance_id = get_instance_id_or_404(
        "clinic_campaigns", "id", campaign_id, "Campaign not found"
    )
    require_write_access(instance_id, caller)
    bq_delete("clinic_campaigns", {"id": campaign_id})
    return {"status": "success"}
