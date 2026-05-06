"""
Clinic CRUD endpoints — backed by Cloud SQL.

A clinic spans three tables:
  - `clinics`                          — IDs / operational toggles / soft delete
  - `clinic_location_details`          — hours, about_us, phone, email, time_zone
  - `clinic_voice_agent_configuration` — managed by /clinics/{id}/voice_agent/* (untouched here)

GETs assemble a flat dict from clinics + clinic_location_details. PATCH
dispatches each field to the appropriate table based on a hard-coded mapping.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import require_read_access, require_write_access, verify_token
from api.models import ClinicCreate, ClinicUpdate
from api.core.db import get_session
from api.core.orm import Clinic, ClinicLocationDetails
from api.account.provisioning import provision_clinic


router = APIRouter()


# Field → owning table for PATCH dispatch.
_CLINIC_FIELDS = {"address", "place_id", "country", "gbp_location_id"}
_LOCATION_FIELDS = {
    "hours_monday", "hours_tuesday", "hours_wednesday", "hours_thursday",
    "hours_friday", "hours_saturday", "hours_sunday",
    "about_us", "email", "phone", "time_zone",
}


def _merged_dict(clinic: Clinic, loc: ClinicLocationDetails | None) -> dict:
    out = {
        "clinic_id": clinic.clinic_id,
        "instance_id": clinic.instance_id,
        "clinic_name": clinic.clinic_name,
        "address": clinic.address,
        "place_id": clinic.place_id,
        "gbp_location_id": clinic.gbp_location_id,
        "pms_type": clinic.pms_type,
        "etl_enabled": bool(clinic.etl_enabled),
        "country": clinic.country,
    }
    if loc:
        out.update({
            "hours_monday": loc.hours_monday,
            "hours_tuesday": loc.hours_tuesday,
            "hours_wednesday": loc.hours_wednesday,
            "hours_thursday": loc.hours_thursday,
            "hours_friday": loc.hours_friday,
            "hours_saturday": loc.hours_saturday,
            "hours_sunday": loc.hours_sunday,
            "about_us": loc.about_us,
            "email": loc.email,
            "phone": loc.phone,
            "time_zone": loc.time_zone,
        })
    return out


def _get_clinic_or_404(db: Session, clinic_id: str) -> Clinic:
    clinic = db.get(Clinic, clinic_id)
    if not clinic or clinic.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Clinic not found")
    return clinic


@router.get("/clinics/{instance_id}")
def get_clinics(
    instance_id: str,
    caller: dict = Depends(verify_token),
    db: Session = Depends(get_session),
):
    require_read_access(instance_id, caller)

    clinics = list(db.scalars(
        select(Clinic).where(
            Clinic.instance_id == instance_id,
            Clinic.deleted_at.is_(None),
        )
    ))
    return [_merged_dict(c, c.location) for c in clinics]


@router.get("/clinics/{instance_id}/{clinic_id}")
def get_clinic(
    instance_id: str,
    clinic_id: str,
    caller: dict = Depends(verify_token),
    db: Session = Depends(get_session),
):
    require_read_access(instance_id, caller)

    clinic = db.get(Clinic, clinic_id)
    if not clinic or clinic.deleted_at is not None or clinic.instance_id != instance_id:
        raise HTTPException(status_code=404, detail="Clinic not found")
    return _merged_dict(clinic, clinic.location)


@router.post("/clinics/{instance_id}")
def add_clinic(
    instance_id: str,
    clinic: ClinicCreate,
    caller: dict = Depends(verify_token),
    db: Session = Depends(get_session),
):
    require_write_access(instance_id, caller)

    clinic_id, _ = provision_clinic(
        db,
        clinic_data=clinic.model_dump(),
        instance_id=instance_id,
    )
    return {"status": "success", "clinic_id": clinic_id}


@router.patch("/clinics/{clinic_id}")
def update_clinic(
    clinic_id: str,
    body: ClinicUpdate,
    caller: dict = Depends(verify_token),
    db: Session = Depends(get_session),
):
    clinic = _get_clinic_or_404(db, clinic_id)
    require_write_access(clinic.instance_id, caller)

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided")

    # Dispatch each field to its owning table.
    location: ClinicLocationDetails | None = clinic.location
    for field, value in updates.items():
        if field in _CLINIC_FIELDS:
            setattr(clinic, field, value)
        elif field in _LOCATION_FIELDS:
            if location is None:
                # Defensive: provisioning always creates the row, but treat
                # missing as something to lazily create rather than 500.
                location = ClinicLocationDetails(clinic_id=clinic.clinic_id)
                db.add(location)
                clinic.location = location
            setattr(location, field, value)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown field: {field}")

    return {"status": "success", "updated": updates}


@router.delete("/clinics/{clinic_id}")
def delete_clinic(
    clinic_id: str,
    caller: dict = Depends(verify_token),
    db: Session = Depends(get_session),
):
    clinic = _get_clinic_or_404(db, clinic_id)
    require_write_access(clinic.instance_id, caller)

    # Hard delete — child config tables CASCADE. If we want to preserve history
    # later, switch to setting deleted_at instead.
    db.delete(clinic)
    return {"status": "success"}
