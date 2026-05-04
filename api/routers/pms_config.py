"""
PMS configuration — per-clinic, typed per PMS.

Non-secret config lives in Cloud SQL:
    blueprint  → clinic_blueprint_config (clinic_code, api_url, aws_url)
    audit_data → reserved; clinic_audit_data_config will be added when the
                 AuditData integration lands.

Secrets live in Google Secret Manager and never touch the DB. Naming convention
matches what the ETL pipeline reads:
    clinic_{clinic_id}_blueprint_api_key
    clinic_{clinic_id}_blueprint_aws_access_key_id
    clinic_{clinic_id}_blueprint_aws_secret_access_key
    clinic_{clinic_id}_blueprint_zip_password
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.deps import require_read_access, require_write_access, verify_token
from api.models import PmsConfigSet
from services.db import get_session
from services.models import Clinic, ClinicBlueprintConfig
from services.secrets import get_secret


router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_clinic_or_404(db: Session, clinic_id: str) -> Clinic:
    clinic = db.get(Clinic, clinic_id)
    if not clinic or clinic.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Clinic not found")
    return clinic


def _sm_secret_name(clinic_id: str, pms_type: str, key: str) -> str:
    return f"clinic_{clinic_id}_{pms_type}_{key}"


def _write_pms_secret(clinic_id: str, pms_type: str, key: str, value: str) -> None:
    """Write a per-clinic PMS secret to SM (create or add a new version)."""
    from google.cloud import secretmanager

    sm = secretmanager.SecretManagerServiceClient()
    secret_id = _sm_secret_name(clinic_id, pms_type, key)
    project = "project-demo-2-482101"  # mirrors services/secrets.py
    parent = f"projects/{project}"
    secret_path = f"{parent}/secrets/{secret_id}"

    try:
        sm.get_secret(request={"name": secret_path})
        sm.add_secret_version(
            request={"parent": secret_path, "payload": {"data": value.encode("utf-8")}}
        )
    except Exception:
        sm.create_secret(
            request={
                "parent": parent,
                "secret_id": secret_id,
                "secret": {"replication": {"automatic": {}}},
            }
        )
        sm.add_secret_version(
            request={"parent": secret_path, "payload": {"data": value.encode("utf-8")}}
        )
    # Force any cached read of the previous version to refresh.
    get_secret.cache_clear()


# ── Per-PMS config column maps ────────────────────────────────────────────────

_BLUEPRINT_CONFIG_FIELDS = {"clinic_code", "api_url", "aws_url"}
_BLUEPRINT_SECRET_KEYS = (
    "api_key", "aws_access_key_id", "aws_secret_access_key", "zip_password",
)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/clinics/{clinic_id}/pms")
def get_pms_config(
    clinic_id: str,
    caller: dict = Depends(verify_token),
    db: Session = Depends(get_session),
):
    """Returns the PMS configuration for a clinic. Secrets are never returned."""
    clinic = _get_clinic_or_404(db, clinic_id)
    require_read_access(clinic.instance_id, caller)

    pms_type = clinic.pms_type or "none"
    if pms_type == "blueprint":
        bp = db.get(ClinicBlueprintConfig, clinic_id)
        config = {
            "clinic_code": bp.clinic_code if bp else None,
            "api_url": bp.api_url if bp else None,
            "aws_url": bp.aws_url if bp else None,
        } if bp else {}
    else:
        config = {}

    return {"pms_type": pms_type, "config": config}


@router.post("/clinics/{clinic_id}/pms")
def set_pms_config(
    clinic_id: str,
    body: PmsConfigSet,
    caller: dict = Depends(verify_token),
    db: Session = Depends(get_session),
):
    """Set or replace the PMS configuration for a clinic."""
    clinic = _get_clinic_or_404(db, clinic_id)
    require_write_access(clinic.instance_id, caller)

    config = body.config or {}

    if body.pms_type == "blueprint":
        unknown = set(config.keys()) - _BLUEPRINT_CONFIG_FIELDS
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown blueprint config fields: {sorted(unknown)}",
            )

        bp = db.get(ClinicBlueprintConfig, clinic_id)
        if bp is None:
            bp = ClinicBlueprintConfig(clinic_id=clinic_id)
            db.add(bp)
        for field in _BLUEPRINT_CONFIG_FIELDS:
            if field in config:
                setattr(bp, field, config[field])

        if body.secrets:
            unknown_secrets = set(body.secrets.keys()) - set(_BLUEPRINT_SECRET_KEYS)
            if unknown_secrets:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown blueprint secret keys: {sorted(unknown_secrets)}",
                )
            for key, value in body.secrets.items():
                if value:
                    _write_pms_secret(clinic_id, "blueprint", key, str(value))

    elif body.pms_type == "audit_data":
        raise HTTPException(
            status_code=501,
            detail=(
                "AuditData PMS support is not yet implemented. "
                "clinic_audit_data_config will be added when AuditData lands."
            ),
        )

    elif body.pms_type == "none":
        # Clear blueprint config if any. Secrets remain in SM as backup.
        bp = db.get(ClinicBlueprintConfig, clinic_id)
        if bp is not None:
            db.delete(bp)

    clinic.pms_type = body.pms_type

    return {"status": "success", "clinic_id": clinic_id, "pms_type": body.pms_type}


@router.delete("/clinics/{clinic_id}/pms")
def clear_pms_config(
    clinic_id: str,
    caller: dict = Depends(verify_token),
    db: Session = Depends(get_session),
):
    """
    Clear all PMS configuration for a clinic.
    Deletes the per-PMS config row and sets pms_type='none'. SM secrets are
    intentionally left in place — manual cleanup once you're certain.
    """
    clinic = _get_clinic_or_404(db, clinic_id)
    require_write_access(clinic.instance_id, caller)

    bp = db.get(ClinicBlueprintConfig, clinic_id)
    if bp is not None:
        db.delete(bp)
    clinic.pms_type = "none"

    return {"status": "success", "clinic_id": clinic_id, "pms_type": "none"}
