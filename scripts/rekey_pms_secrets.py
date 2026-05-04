"""
One-shot: re-key Blueprint PMS secrets in Secret Manager.

Old name format (clinic_name-based, spaces→underscores):
    {clinic_name}_BLUEPRINT_API_key
    {clinic_name}_BLUEPRINT_AWS_Access_Key_ID
    {clinic_name}_BLUEPRINT_AWS_Secret_Access_Key
    {clinic_name}_BLUEPRINT_ZIP_password

New name format (clinic_id-based — clinic_name is mutable, clinic_id isn't):
    clinic_{clinic_id}_blueprint_api_key
    clinic_{clinic_id}_blueprint_aws_access_key_id
    clinic_{clinic_id}_blueprint_aws_secret_access_key
    clinic_{clinic_id}_blueprint_zip_password

This script is **additive**: it creates new secrets with clinic_id-keyed
names but never deletes the old ones. Old secrets stay as backup until
all readers (routers, ETL) are pointing at the new names. Manual cleanup
later — `gcloud secrets delete` once everyone has migrated.

Usage:
    cd cortex-hypervisor
    CLOUD_SQL_IAM_USER=<your-email-or-sa> python -m scripts.rekey_pms_secrets [--dry-run]
"""
import argparse
import logging
import sys

from google.api_core.exceptions import AlreadyExists, NotFound
from google.cloud import secretmanager
from sqlalchemy import select

from services.db import session_scope
from services.models import Clinic


logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("rekey_pms_secrets")

PROJECT = "project-demo-2-482101"
SM_PARENT = f"projects/{PROJECT}"

# (old-suffix, new-suffix) — the old prefix is the clinic_name; the new prefix
# is `clinic_{clinic_id}_blueprint`.
_SUFFIX_PAIRS = [
    ("BLUEPRINT_API_key",                "api_key"),
    ("BLUEPRINT_AWS_Access_Key_ID",      "aws_access_key_id"),
    ("BLUEPRINT_AWS_Secret_Access_Key",  "aws_secret_access_key"),
    ("BLUEPRINT_ZIP_password",           "zip_password"),
]


def _old_secret_name(clinic_name: str, old_suffix: str) -> str:
    return f"{clinic_name.replace(' ', '_')}_{old_suffix}"


def _new_secret_name(clinic_id: str, new_suffix: str) -> str:
    return f"clinic_{clinic_id}_blueprint_{new_suffix}"


def _get_secret_value(sm: secretmanager.SecretManagerServiceClient, name: str) -> str | None:
    path = f"{SM_PARENT}/secrets/{name}/versions/latest"
    try:
        return sm.access_secret_version(request={"name": path}).payload.data.decode("utf-8")
    except NotFound:
        return None


def _create_secret_with_value(
    sm: secretmanager.SecretManagerServiceClient, name: str, value: str
) -> None:
    try:
        sm.create_secret(request={
            "parent": SM_PARENT,
            "secret_id": name,
            "secret": {"replication": {"automatic": {}}},
        })
    except AlreadyExists:
        log.info("    secret %s already exists; appending new version", name)
    sm.add_secret_version(request={
        "parent": f"{SM_PARENT}/secrets/{name}",
        "payload": {"data": value.encode("utf-8")},
    })


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be migrated without writing")
    args = parser.parse_args()

    sm = secretmanager.SecretManagerServiceClient()

    with session_scope() as db:
        clinics = list(db.scalars(
            select(Clinic).where(Clinic.pms_type == "blueprint")
        ))

    if not clinics:
        log.info("No Blueprint clinics found; nothing to rekey.")
        return 0

    log.info("Found %d Blueprint clinics", len(clinics))
    if args.dry_run:
        log.info("(dry run — no Secret Manager writes will be performed)")

    migrated, missing, errors = 0, 0, 0

    for c in clinics:
        log.info("\n%s  (clinic_id=%s)", c.clinic_name, c.clinic_id)
        for old_suffix, new_suffix in _SUFFIX_PAIRS:
            old_name = _old_secret_name(c.clinic_name, old_suffix)
            new_name = _new_secret_name(c.clinic_id, new_suffix)

            value = _get_secret_value(sm, old_name)
            if value is None:
                log.warning("  ✗ missing source secret %s", old_name)
                missing += 1
                continue

            log.info("  → %s  (from %s)", new_name, old_name)
            if args.dry_run:
                migrated += 1
                continue

            try:
                _create_secret_with_value(sm, new_name, value)
                # Verify
                roundtrip = _get_secret_value(sm, new_name)
                if roundtrip != value:
                    log.error("    ✗ roundtrip mismatch for %s", new_name)
                    errors += 1
                else:
                    migrated += 1
            except Exception as e:  # noqa: BLE001
                log.error("    ✗ failed: %s", e)
                errors += 1

    log.info("\nSummary: migrated=%d  missing-source=%d  errors=%d",
             migrated, missing, errors)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
