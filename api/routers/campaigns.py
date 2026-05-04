"""
Multi-campaign ID management per clinic — backed by Cloud SQL.

The legacy `clinic_campaigns` BQ table (single table, `campaign_type`
discriminator) has been split into two typed tables:
    google_ads_campaigns  → (id, clinic_id, google_ads_campaign_id, active)
    invoca_campaigns      → (id, clinic_id, invoca_campaign_id, active)

URL shape:
    GET    /campaigns/{instance_id}                  → both types, all clinics
    GET    /campaigns/{instance_id}/{clinic_id}      → both types, one clinic
    POST   /campaigns/{clinic_id}  body{campaign_type, external_campaign_id, active}
    DELETE /campaigns/{campaign_type}/{id}           → explicit type required
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.deps import require_read_access, require_write_access, verify_token
from api.models import ClinicCampaignCreate
from services.db import get_session
from services.models import Clinic, GoogleAdsCampaign, InvocaCampaign


router = APIRouter()


def _gads_dict(c: GoogleAdsCampaign) -> dict:
    return {
        "id": c.id,
        "clinic_id": c.clinic_id,
        "campaign_type": "google_ads",
        "external_campaign_id": c.google_ads_campaign_id,
        "active": bool(c.active),
    }


def _invoca_dict(c: InvocaCampaign) -> dict:
    return {
        "id": c.id,
        "clinic_id": c.clinic_id,
        "campaign_type": "invoca",
        "external_campaign_id": c.invoca_campaign_id,
        "active": bool(c.active),
    }


@router.get("/campaigns/{instance_id}")
def list_campaigns_for_instance(
    instance_id: str,
    caller: dict = Depends(verify_token),
    db: Session = Depends(get_session),
):
    """List all campaign associations for every clinic in an instance."""
    require_read_access(instance_id, caller)

    gads = db.scalars(
        select(GoogleAdsCampaign)
        .join(Clinic, Clinic.clinic_id == GoogleAdsCampaign.clinic_id)
        .where(Clinic.instance_id == instance_id, Clinic.deleted_at.is_(None))
    ).all()
    invoca = db.scalars(
        select(InvocaCampaign)
        .join(Clinic, Clinic.clinic_id == InvocaCampaign.clinic_id)
        .where(Clinic.instance_id == instance_id, Clinic.deleted_at.is_(None))
    ).all()

    return [_gads_dict(c) for c in gads] + [_invoca_dict(c) for c in invoca]


@router.get("/campaigns/{instance_id}/{clinic_id}")
def list_campaigns_for_clinic(
    instance_id: str,
    clinic_id: str,
    caller: dict = Depends(verify_token),
    db: Session = Depends(get_session),
):
    """List campaign associations for a specific clinic."""
    require_read_access(instance_id, caller)

    clinic = db.get(Clinic, clinic_id)
    if not clinic or clinic.instance_id != instance_id or clinic.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Clinic not found")

    gads = db.scalars(
        select(GoogleAdsCampaign).where(GoogleAdsCampaign.clinic_id == clinic_id)
    ).all()
    invoca = db.scalars(
        select(InvocaCampaign).where(InvocaCampaign.clinic_id == clinic_id)
    ).all()

    return [_gads_dict(c) for c in gads] + [_invoca_dict(c) for c in invoca]


@router.post("/campaigns/{clinic_id}")
def add_campaign(
    clinic_id: str,
    body: ClinicCampaignCreate,
    caller: dict = Depends(verify_token),
    db: Session = Depends(get_session),
):
    """Add a campaign ID association to a clinic. Type-specific."""
    clinic = db.get(Clinic, clinic_id)
    if not clinic or clinic.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Clinic not found")
    require_write_access(clinic.instance_id, caller)

    if body.campaign_type == "google_ads":
        row = GoogleAdsCampaign(
            clinic_id=clinic_id,
            google_ads_campaign_id=body.external_campaign_id,
            active=body.active,
        )
    else:  # invoca
        row = InvocaCampaign(
            clinic_id=clinic_id,
            invoca_campaign_id=body.external_campaign_id,
            active=body.active,
        )

    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        # UNIQUE(clinic_id, external_id) — already linked.
        raise HTTPException(status_code=409, detail="Campaign already associated with this clinic")

    return {"status": "success", "id": row.id, "campaign_type": body.campaign_type}


@router.delete("/campaigns/{campaign_type}/{campaign_id}")
def remove_campaign(
    campaign_type: str,
    campaign_id: int,
    caller: dict = Depends(verify_token),
    db: Session = Depends(get_session),
):
    """Remove a campaign association. Type must be 'google_ads' or 'invoca'."""
    if campaign_type == "google_ads":
        row = db.get(GoogleAdsCampaign, campaign_id)
    elif campaign_type == "invoca":
        row = db.get(InvocaCampaign, campaign_id)
    else:
        raise HTTPException(
            status_code=400,
            detail="campaign_type must be 'google_ads' or 'invoca'",
        )

    if row is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    clinic = db.get(Clinic, row.clinic_id)
    require_write_access(clinic.instance_id, caller)

    db.delete(row)
    return {"status": "success"}
