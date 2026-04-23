#!/usr/bin/env python3
"""
Configure Blueprint OMS credentials for a clinic.

Prompts for each value via input(). Non-secret config goes to
Users.clinic_pms_config.config (JSON). Secrets go to Google Secret Manager
with the naming convention:

    <clinic_name>_BLUEPRINT_<secret_name>

where clinic_name has spaces replaced with underscores.

Example: Audiology_Clinic_of_Northern_Alberta_BLUEPRINT_API_key

Stored secrets:
    <clinic_name>_BLUEPRINT_API_key
    <clinic_name>_BLUEPRINT_AWS_Access_Key_ID
    <clinic_name>_BLUEPRINT_AWS_Secret_Access_Key
    <clinic_name>_BLUEPRINT_ZIP_password

Prerequisites:
    gcloud auth application-default login
    gcloud auth application-default set-quota-project project-demo-2-482101

Usage:
    python3 configure_blueprint.py
"""
import json
import re
import sys

import google.auth
from google.cloud import bigquery, secretmanager


BQ_DATASET = "Users"
SECRET_NAMES = ("API_key", "AWS_Access_Key_ID", "AWS_Secret_Access_Key", "ZIP_password")


def _resolve_project() -> str:
    _, project = google.auth.default()
    if not project:
        print("ERROR: could not resolve GCP project. Run: "
              "gcloud auth application-default set-quota-project <project>")
        sys.exit(1)
    return project


def _normalize_clinic_name(clinic_name: str) -> str:
    """
    Convert clinic name to a Secret Manager-safe identifier.
    SM secret IDs must match [a-zA-Z0-9_-]+.
    """
    normalized = clinic_name.strip().replace(" ", "_")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", normalized):
        print(f"ERROR: clinic_name '{clinic_name}' contains characters that are not "
              f"safe for Secret Manager IDs after normalization. "
              f"Got: '{normalized}'. Allowed: letters, digits, underscore, hyphen.")
        sys.exit(1)
    return normalized


def _find_clinic(bq_client: bigquery.Client, project: str, clinic_name: str) -> dict:
    rows = list(bq_client.query(
        f"""
        SELECT clinic_id, clinic_name, pms_type
        FROM `{project}.{BQ_DATASET}.clinics`
        WHERE clinic_name = @name
        """,
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("name", "STRING", clinic_name)
        ])
    ).result())
    if not rows:
        print(f"ERROR: clinic '{clinic_name}' not found in {BQ_DATASET}.clinics")
        print("Run this to see available clinics:")
        print(f"  bq query --use_legacy_sql=false 'SELECT clinic_name FROM `{project}.{BQ_DATASET}.clinics`'")
        sys.exit(1)
    return dict(rows[0])


def _get_existing_config(bq_client: bigquery.Client, project: str, clinic_id: str) -> dict | None:
    rows = list(bq_client.query(
        f"""
        SELECT pms_type, config
        FROM `{project}.{BQ_DATASET}.clinic_pms_config`
        WHERE clinic_id = @cid
        """,
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("cid", "STRING", clinic_id)
        ])
    ).result())
    if not rows:
        return None
    row = dict(rows[0])
    return {
        "pms_type": row["pms_type"],
        "config": json.loads(row["config"]) if row.get("config") else {},
    }


def _prompt(label: str, default: str = "") -> str:
    """Prompt for a value. Shows default in brackets and returns it on empty input."""
    suffix = f" [{default[:40]}{'…' if len(default) > 40 else ''}]" if default else ""
    val = input(f"  {label}{suffix}: ").strip()
    return val if val else default


def _upsert_pms_config(
    bq_client: bigquery.Client, project: str, clinic_id: str, config: dict
) -> str:
    config_json = json.dumps(config)
    existing = _get_existing_config(bq_client, project, clinic_id)

    params = [
        bigquery.ScalarQueryParameter("cid", "STRING", clinic_id),
        bigquery.ScalarQueryParameter("cfg", "STRING", config_json),
    ]
    if existing:
        bq_client.query(
            f"""
            UPDATE `{project}.{BQ_DATASET}.clinic_pms_config`
            SET pms_type = 'blueprint', config = @cfg
            WHERE clinic_id = @cid
            """,
            job_config=bigquery.QueryJobConfig(query_parameters=params),
        ).result()
        return "updated"
    else:
        bq_client.query(
            f"""
            INSERT INTO `{project}.{BQ_DATASET}.clinic_pms_config` (clinic_id, pms_type, config)
            VALUES (@cid, 'blueprint', @cfg)
            """,
            job_config=bigquery.QueryJobConfig(query_parameters=params),
        ).result()
        return "inserted"


def _set_clinic_pms_type(bq_client: bigquery.Client, project: str, clinic_id: str):
    bq_client.query(
        f"""
        UPDATE `{project}.{BQ_DATASET}.clinics`
        SET pms_type = 'blueprint'
        WHERE clinic_id = @cid
        """,
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("cid", "STRING", clinic_id)
        ])
    ).result()


def _upsert_secret(
    sm_client: secretmanager.SecretManagerServiceClient,
    project: str,
    secret_id: str,
    value: str,
) -> str:
    parent = f"projects/{project}"
    path = f"{parent}/secrets/{secret_id}"
    try:
        sm_client.get_secret(request={"name": path})
        sm_client.add_secret_version(
            request={"parent": path, "payload": {"data": value.encode("utf-8")}}
        )
        return "updated"
    except Exception:
        sm_client.create_secret(
            request={
                "parent": parent,
                "secret_id": secret_id,
                "secret": {"replication": {"automatic": {}}},
            }
        )
        sm_client.add_secret_version(
            request={"parent": path, "payload": {"data": value.encode("utf-8")}}
        )
        return "created"


def main():
    project = _resolve_project()
    bq_client = bigquery.Client(project=project)
    sm_client = secretmanager.SecretManagerServiceClient()

    print("=" * 60)
    print("  Blueprint OMS credential configuration")
    print("=" * 60)

    clinic_name = input("\nClinic name (must match Users.clinics.clinic_name exactly): ").strip()
    if not clinic_name:
        print("ERROR: clinic_name is required")
        sys.exit(1)

    clinic = _find_clinic(bq_client, project, clinic_name)
    normalized = _normalize_clinic_name(clinic_name)
    existing = _get_existing_config(bq_client, project, clinic["clinic_id"])

    print(f"\n✓ Found clinic: {clinic['clinic_name']}")
    print(f"  clinic_id:          {clinic['clinic_id']}")
    print(f"  current pms_type:   {clinic.get('pms_type') or 'none'}")
    print(f"  SM secret prefix:   {normalized}_BLUEPRINT_")
    if existing and existing.get("config"):
        print(f"  existing config:    {existing['config']}")
        print(f"  (press Enter at prompts to keep existing values)")

    existing_config = existing.get("config") if existing else {}

    print("\n── Non-secret config (→ Users.clinic_pms_config.config) ──")
    clinic_code    = _prompt("Clinic code (e.g. AB_acn)",       existing_config.get("clinic_code", ""))
    api_url        = _prompt("API URL",                          existing_config.get("api_url", ""))
    aws_url        = _prompt("AWS URL (s3://...)",               existing_config.get("aws_url", ""))
    default_region = _prompt("Default region (e.g. ca-central-1)", existing_config.get("default_region", ""))

    print("\n── Secrets (→ Google Secret Manager) ──")
    print("  (leave blank to keep existing secret value unchanged)")
    api_key        = input(f"  API Key: ").strip()
    aws_access_key = input(f"  AWS Access Key ID: ").strip()
    aws_secret_key = input(f"  AWS Secret Access Key: ").strip()
    zip_password   = input(f"  ZIP password: ").strip()

    # Summary
    print("\n" + "=" * 60)
    print("  Summary")
    print("=" * 60)
    print(f"  Clinic:              {clinic_name} ({clinic['clinic_id']})")
    print(f"  BQ table:            {project}.{BQ_DATASET}.clinic_pms_config")
    print(f"  Config JSON:")
    for k, v in {"clinic_code": clinic_code, "api_url": api_url, "aws_url": aws_url, "default_region": default_region}.items():
        print(f"    {k}: {v or '(empty)'}")
    print(f"  SM secrets (will upsert only those you entered):")
    for name, val in (
        ("API_key", api_key),
        ("AWS_Access_Key_ID", aws_access_key),
        ("AWS_Secret_Access_Key", aws_secret_key),
        ("ZIP_password", zip_password),
    ):
        sid = f"{normalized}_BLUEPRINT_{name}"
        marker = f"({len(val)} chars)" if val else "(skip — no change)"
        print(f"    {sid}: {marker}")

    if input("\nProceed? [y/N] ").strip().lower() != "y":
        print("Aborted")
        sys.exit(0)

    # Write non-secrets to BQ
    config = {
        "clinic_code": clinic_code,
        "api_url": api_url,
        "aws_url": aws_url,
        "default_region": default_region,
    }
    result = _upsert_pms_config(bq_client, project, clinic["clinic_id"], config)
    print(f"\n  ✓ clinic_pms_config row {result}")

    _set_clinic_pms_type(bq_client, project, clinic["clinic_id"])
    print(f"  ✓ Users.clinics.pms_type set to 'blueprint'")

    # Write secrets to SM (only those provided)
    secrets_provided = [
        ("API_key", api_key),
        ("AWS_Access_Key_ID", aws_access_key),
        ("AWS_Secret_Access_Key", aws_secret_key),
        ("ZIP_password", zip_password),
    ]
    for name, value in secrets_provided:
        if not value:
            continue
        secret_id = f"{normalized}_BLUEPRINT_{name}"
        status = _upsert_secret(sm_client, project, secret_id, value)
        print(f"  ✓ {secret_id}: {status}")

    print(f"\nDone. Blueprint configuration complete for '{clinic_name}'.")


if __name__ == "__main__":
    main()
