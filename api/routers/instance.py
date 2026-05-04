"""Instance lifecycle endpoints — backed by Cloud SQL."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from api.deps import (
    get_instance_id_for_uid, require_write_access, verify_token,
)
from api.models import InstanceUpdate, ProvisionRequest
from services.db import get_session
from services.models import Clinic, Instance
from services.provisioning import provision_full_account


router = APIRouter()


def _instance_dict(i: Instance) -> dict:
    return {
        "instance_id": i.instance_id,
        "instance_name": i.instance_name,
        "primary_contact_name": i.primary_contact_name,
        "primary_contact_email": i.primary_contact_email,
        "primary_contact_uid": i.primary_contact_uid,
        "google_ads_customer_id": i.google_ads_customer_id,
        "invoca_profile_id": i.invoca_profile_id,
    }


def _clinic_dict(c: Clinic) -> dict:
    return {
        "clinic_id": c.clinic_id,
        "instance_id": c.instance_id,
        "clinic_name": c.clinic_name,
        "address": c.address,
        "place_id": c.place_id,
        "gbp_location_id": c.gbp_location_id,
        "pms_type": c.pms_type,
        "etl_enabled": bool(c.etl_enabled),
        "country": c.country,
    }


@router.post("/provision_account/")
def provision_account(
    payload: ProvisionRequest,
    caller: dict = Depends(verify_token),
    db: Session = Depends(get_session),
):
    role = caller.get("role")
    if role not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Access denied")

    if payload.uid != caller["uid"] and role != "super_admin":
        raise HTTPException(status_code=403, detail="Cannot provision for another user")

    # Block duplicate provisioning unless super_admin (mirror prior behavior).
    existing = db.scalar(
        select(Instance.instance_id).where(Instance.primary_contact_uid == payload.uid)
    )
    if existing and role != "super_admin":
        return {"status": "error", "message": f"{payload.uid} already has an instance provisioned"}

    result = provision_full_account(
        db,
        instance_create=payload.instance.model_dump(),
        clinics_create=[c.model_dump() for c in payload.clinics],
        primary_contact_uid=payload.uid,
    )

    return {
        "status": "success",
        "message": "Instance provisioned",
        "instance_id": result["instance_id"],
        "clinic_ids": result["clinic_id_map"],
    }


@router.get("/instance/{uid}")
def get_instance(
    uid: str,
    caller: dict = Depends(verify_token),
    db: Session = Depends(get_session),
):
    role = caller.get("role")
    if role not in ("admin", "super_admin", "viewer"):
        raise HTTPException(status_code=403, detail="Access denied")
    if role != "super_admin" and caller["uid"] != uid:
        raise HTTPException(status_code=403, detail="Access denied")

    instance = db.scalar(select(Instance).where(Instance.primary_contact_uid == uid))
    if not instance:
        raise HTTPException(status_code=404, detail=f"No instance found for uid {uid}")

    clinics = list(db.scalars(
        select(Clinic).where(
            Clinic.instance_id == instance.instance_id,
            Clinic.deleted_at.is_(None),
        )
    ))

    # Response shape kept loosely compatible with the prior endpoint: arrays at
    # each key. Dropped routers (staff/services/insurance/users) are no longer
    # returned — those tables are gone.
    return {
        "instance": [_instance_dict(instance)],
        "clinics": [_clinic_dict(c) for c in clinics],
    }


@router.patch("/instance/{instance_id}")
def update_instance(
    instance_id: str,
    body: InstanceUpdate,
    caller: dict = Depends(verify_token),
    db: Session = Depends(get_session),
):
    require_write_access(instance_id, caller)

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided")

    instance = db.get(Instance, instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    for key, value in updates.items():
        setattr(instance, key, value)

    return {"status": "success", "updated": updates}


@router.delete("/instance/{uid}")
def delete_instance(
    uid: str,
    caller: dict = Depends(verify_token),
    db: Session = Depends(get_session),
):
    role = caller.get("role")
    if role not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Access denied")
    if role != "super_admin" and caller["uid"] != uid:
        raise HTTPException(status_code=403, detail="Access denied")

    instance_id = get_instance_id_for_uid(uid)
    if not instance_id:
        raise HTTPException(status_code=404, detail=f"No instance found for uid {uid}")

    # clinics → instances FK is RESTRICT, so clinics must die first. Each clinic's
    # 1:1 sub-tables CASCADE from clinics.clinic_id.
    db.execute(delete(Clinic).where(Clinic.instance_id == instance_id))
    db.execute(delete(Instance).where(Instance.instance_id == instance_id))

    return {"status": "success", "message": f"Instance {instance_id} and clinics deleted"}
