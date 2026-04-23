"""
PMS configuration — per clinic, PMS-agnostic.

Non-secret config lives in Users.clinic_pms_config (JSON `config` column).
Secrets (API keys, AWS creds) live in Google Secret Manager under
pms/{clinic_id}/<secret-name>.

Supported pms_type values: "none", "blueprint", "auditdata"
"""
import json
import subprocess

from fastapi import APIRouter, Depends, HTTPException
from google.cloud import bigquery

from api.deps import (
    bq_client, bq_table, bq_update,
    verify_token, require_read_access, require_write_access,
)
from api.models import PmsConfigSet
from services.secrets import get_secret

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

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


def _get_pms_config(clinic_id: str) -> dict | None:
    """Fetch the clinic_pms_config row, or None if not configured."""
    rows = list(bq_client.query(
        f"SELECT * FROM {bq_table('clinic_pms_config')} WHERE clinic_id = @clinic_id",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("clinic_id", "STRING", clinic_id)
        ])
    ).result())
    if not rows:
        return None
    row = dict(rows[0])
    row["config"] = json.loads(row["config"]) if row.get("config") else {}
    return row


def _sm_secret_name(clinic_id: str, key: str) -> str:
    """Build the Secret Manager secret name for a per-clinic PMS secret."""
    return f"pms--{clinic_id}--{key}"


def _read_pms_secret(clinic_id: str, key: str) -> str | None:
    """Read a per-clinic PMS secret from SM. Returns None if not found."""
    try:
        return get_secret(_sm_secret_name(clinic_id, key))
    except Exception:
        return None


def _write_pms_secret(clinic_id: str, key: str, value: str):
    """Write a per-clinic PMS secret to SM (create or add version)."""
    import os
    from google.cloud import secretmanager

    project = os.environ["GCP_PROJECT"]
    sm_client = secretmanager.SecretManagerServiceClient()
    secret_id = _sm_secret_name(clinic_id, key)
    parent = f"projects/{project}"
    secret_path = f"{parent}/secrets/{secret_id}"

    try:
        sm_client.get_secret(request={"name": secret_path})
        # Secret exists — add a new version
        sm_client.add_secret_version(
            request={"parent": secret_path, "payload": {"data": value.encode("utf-8")}}
        )
    except Exception:
        # Secret doesn't exist — create it
        sm_client.create_secret(
            request={"parent": parent, "secret_id": secret_id, "secret": {"replication": {"automatic": {}}}}
        )
        sm_client.add_secret_version(
            request={"parent": secret_path, "payload": {"data": value.encode("utf-8")}}
        )
    # Clear the lru_cache so subsequent reads see the new value
    get_secret.cache_clear()


def _delete_pms_secrets(clinic_id: str, keys: list[str]):
    """Delete per-clinic PMS secrets from SM."""
    import os
    from google.cloud import secretmanager

    project = os.environ["GCP_PROJECT"]
    sm_client = secretmanager.SecretManagerServiceClient()

    for key in keys:
        secret_path = f"projects/{project}/secrets/{_sm_secret_name(clinic_id, key)}"
        try:
            sm_client.delete_secret(request={"name": secret_path})
        except Exception:
            pass  # Already gone
    get_secret.cache_clear()


# ── Known secret keys per PMS type ────────────────────────────────────────────

_PMS_SECRET_KEYS: dict[str, list[str]] = {
    "blueprint": ["api-key", "aws-access-key-id", "aws-secret-access-key", "zip-password"],
    "auditdata": ["api-key"],
}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/clinics/{clinic_id}/pms")
def get_pms_config(clinic_id: str, caller: dict = Depends(verify_token)):
    """
    Returns the PMS configuration for a clinic.
    Secrets are never returned — only non-secret config from clinic_pms_config.
    """
    clinic = _get_clinic_or_404(clinic_id)
    require_read_access(clinic["instance_id"], caller)

    pms = _get_pms_config(clinic_id)
    if not pms:
        return {"pms_type": clinic.get("pms_type", "none"), "config": {}}

    return {
        "pms_type": pms["pms_type"],
        "config": pms["config"],
    }


@router.post("/clinics/{clinic_id}/pms")
def set_pms_config(clinic_id: str, body: PmsConfigSet, caller: dict = Depends(verify_token)):
    """
    Set or replace the PMS configuration for a clinic.

    `config` is a JSON object with PMS-specific non-secret settings.
    `secrets` is a JSON object with PMS-specific secrets (stored in SM, never in BQ).
    """
    clinic = _get_clinic_or_404(clinic_id)
    require_write_access(clinic["instance_id"], caller)

    config_json = json.dumps(body.config or {})

    # Upsert clinic_pms_config row
    existing = _get_pms_config(clinic_id)
    if existing:
        # Update
        bq_client.query(
            f"UPDATE {bq_table('clinic_pms_config')} "
            f"SET pms_type = @pms_type, config = @config "
            f"WHERE clinic_id = @clinic_id",
            job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("pms_type", "STRING", body.pms_type),
                bigquery.ScalarQueryParameter("config", "STRING", config_json),
                bigquery.ScalarQueryParameter("clinic_id", "STRING", clinic_id),
            ])
        ).result()
    else:
        # Insert
        bq_client.query(
            f"INSERT INTO {bq_table('clinic_pms_config')} (clinic_id, pms_type, config) "
            f"VALUES (@clinic_id, @pms_type, @config)",
            job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("clinic_id", "STRING", clinic_id),
                bigquery.ScalarQueryParameter("pms_type", "STRING", body.pms_type),
                bigquery.ScalarQueryParameter("config", "STRING", config_json),
            ])
        ).result()

    # Update pms_type on the clinics table too (used for agent_factory tool selection)
    bq_update("clinics", {"clinic_id": clinic_id}, {"pms_type": body.pms_type})

    # Store secrets in SM
    if body.secrets:
        for key, value in body.secrets.items():
            if value:
                _write_pms_secret(clinic_id, key, str(value))

    return {
        "status": "success",
        "clinic_id": clinic_id,
        "pms_type": body.pms_type,
    }


@router.delete("/clinics/{clinic_id}/pms")
def clear_pms_config(clinic_id: str, caller: dict = Depends(verify_token)):
    """
    Clear all PMS configuration for a clinic.
    Deletes the clinic_pms_config row, sets pms_type='none' on clinics,
    and removes all per-clinic secrets from SM.
    """
    clinic = _get_clinic_or_404(clinic_id)
    require_write_access(clinic["instance_id"], caller)

    # Get current pms_type to know which secrets to clean up
    pms = _get_pms_config(clinic_id)
    if pms:
        pms_type = pms["pms_type"]
        # Delete SM secrets
        secret_keys = _PMS_SECRET_KEYS.get(pms_type, [])
        if secret_keys:
            _delete_pms_secrets(clinic_id, secret_keys)

        # Delete the config row
        bq_client.query(
            f"DELETE FROM {bq_table('clinic_pms_config')} WHERE clinic_id = @clinic_id",
            job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("clinic_id", "STRING", clinic_id)
            ])
        ).result()

    # Reset pms_type on clinics
    bq_update("clinics", {"clinic_id": clinic_id}, {"pms_type": "none"})

    return {"status": "success", "clinic_id": clinic_id, "pms_type": "none"}
