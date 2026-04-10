"""
Blueprint OMS PMS configuration — per clinic, opt-in.

Stores connection credentials for the Blueprint REST API. The api_key field
is write-only and is never returned in GET responses.

Blueprint API base URL pattern:
    https://{blueprint_server}/{blueprint_clinic_slug}/rest/...
"""
from fastapi import APIRouter, Depends, HTTPException
from google.cloud import bigquery

from api.deps import (
    bq_update, bq_table, bq_client,
    verify_token, require_read_access, require_write_access,
)
from api.models import PmsConfigSet

router = APIRouter()

_PMS_READ_FIELDS = [
    "pms_type",
    "blueprint_server",
    "blueprint_clinic_slug",
    "blueprint_location_id",
    "blueprint_user_id",
    # blueprint_api_key intentionally excluded
]

_PMS_CLEAR = {
    "pms_type": "none",
    "blueprint_server": None,
    "blueprint_clinic_slug": None,
    "blueprint_api_key": None,
    "blueprint_location_id": None,
    "blueprint_user_id": None,
}


def _get_clinic_or_404(clinic_id: str) -> dict:
    rows = list(bq_client.query(
        f"SELECT * FROM {bq_table('clinics')} WHERE clinic_id = @clinic_id",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("clinic_id", "STRING", clinic_id)
        ])
    ).result())
    if not rows:
        raise HTTPException(status_code=404, detail="Clinic not found")
    return dict(rows[0])


@router.get("/clinics/{clinic_id}/pms")
def get_pms_config(clinic_id: str, caller: dict = Depends(verify_token)):
    """
    Returns the PMS configuration for a clinic. The blueprint_api_key is never returned.
    """
    clinic = _get_clinic_or_404(clinic_id)
    require_read_access(clinic["instance_id"], caller)

    return {field: clinic.get(field) for field in _PMS_READ_FIELDS}


@router.post("/clinics/{clinic_id}/pms")
def set_pms_config(clinic_id: str, body: PmsConfigSet, caller: dict = Depends(verify_token)):
    """
    Set or replace the PMS configuration for a clinic.

    For Blueprint: provide blueprint_server, blueprint_clinic_slug, blueprint_api_key,
    blueprint_location_id, and blueprint_user_id.

    The api_key is stored in BigQuery and is never returned by the GET endpoint.
    """
    clinic = _get_clinic_or_404(clinic_id)
    require_write_access(clinic["instance_id"], caller)

    if body.pms_type == "blueprint":
        missing = [
            f for f in ("blueprint_server", "blueprint_clinic_slug", "blueprint_api_key",
                        "blueprint_location_id", "blueprint_user_id")
            if getattr(body, f) is None
        ]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Blueprint PMS requires: {', '.join(missing)}"
            )

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    updates["pms_type"] = body.pms_type  # always set even if "none"

    bq_update("clinics", {"clinic_id": clinic_id}, updates)

    return {
        "status": "success",
        "clinic_id": clinic_id,
        "pms_type": body.pms_type,
    }


@router.delete("/clinics/{clinic_id}/pms")
def clear_pms_config(clinic_id: str, caller: dict = Depends(verify_token)):
    """
    Clear all PMS configuration for a clinic, setting pms_type back to 'none'.
    """
    clinic = _get_clinic_or_404(clinic_id)
    require_write_access(clinic["instance_id"], caller)

    bq_update("clinics", {"clinic_id": clinic_id}, _PMS_CLEAR)

    return {"status": "success", "clinic_id": clinic_id, "pms_type": "none"}
