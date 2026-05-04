"""
One-shot importer: BigQuery `Users.*` → Cloud SQL config tables.

Idempotent. DELETEs all child rows then re-INSERTs from BQ in FK-safe order
inside a single transaction. Safe to re-run; the only state it ever leaves
is what's currently in BQ.

Usage:
    cd cortex-hypervisor
    CLOUD_SQL_IAM_USER=<your-email-or-sa> python -m scripts.import_from_bq

Field mapping highlights:
  - BQ Users.clinics is split into 3 Cloud SQL tables:
      clinics                          (IDs / operational toggles / soft delete)
      clinic_location_details          (hours / about / contact / timezone)
      clinic_voice_agent_configuration (twilio + vapi state)
  - BQ Users.clinics.etl_enabled is STRING 'true' / NULL → Cloud SQL TINYINT(1)
  - BQ Users.clinics.timezone (one word) → Cloud SQL clinic_location_details.time_zone
  - Dropped per migration plan: parking_info, accessibility_info, booking_system,
    transfer_number, google_ads_campaign_id, invoca_campaign_id (the latter two
    move into google_ads_campaigns / invoca_campaigns instead).
  - BQ Users.clinic_pms_config.config is a JSON string; we parse and pull
    {clinic_code, api_url, aws_url} into clinic_blueprint_config (only for
    pms_type='blueprint').
  - BQ Users.clinic_campaigns is split by campaign_type into google_ads_campaigns
    and invoca_campaigns.
  - BQ Users.clinic_voice_agent_capabilities.config is JSON-as-string in BQ but
    JSON column type in Cloud SQL — parsed on import.
"""
import json
import logging
import sys
from typing import Any

from google.cloud import bigquery
from sqlalchemy import delete

from services.db import session_scope
from services.models import (
    Clinic, ClinicBlueprintConfig, ClinicLocationDetails,
    ClinicVoiceAgentConfiguration, GoogleAdsCampaign, Instance,
    InvocaCampaign, VoiceAgentCapability,
)


logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("import_from_bq")


PROJECT = "project-demo-2-482101"
BQ = bigquery.Client(project=PROJECT)


def _bq_rows(table: str) -> list[dict]:
    rows = list(BQ.query(f"SELECT * FROM `{PROJECT}.Users.{table}`").result())
    return [dict(r) for r in rows]


_COUNTRY_NAME_TO_CODE = {
    "canada": "CA",
    "united states": "US",
    "united states of america": "US",
    "usa": "US",
}


def _country(v: Any) -> str | None:
    """Coerce country-ish input to ISO-3166 alpha-2. Returns None if unknown."""
    if not v:
        return None
    s = str(v).strip()
    if len(s) == 2:
        return s.upper()
    code = _COUNTRY_NAME_TO_CODE.get(s.lower())
    if code is None:
        log.warning("  unknown country %r — leaving NULL", s)
    return code


def _bool(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("true", "1", "yes", "y")


def _json_or_none(v: Any) -> dict | None:
    if v is None or v == "":
        return None
    if isinstance(v, dict):
        return v
    try:
        return json.loads(v)
    except (ValueError, TypeError):
        return None


def main() -> None:
    log.info("Reading from BigQuery…")
    bq_instances = _bq_rows("instances")
    bq_clinics = _bq_rows("clinics")
    bq_pms_configs = _bq_rows("clinic_pms_config")
    bq_campaigns = _bq_rows("clinic_campaigns")
    bq_caps = _bq_rows("clinic_voice_agent_capabilities")

    log.info(
        "  instances=%d  clinics=%d  pms_configs=%d  campaigns=%d  capabilities=%d",
        len(bq_instances), len(bq_clinics), len(bq_pms_configs),
        len(bq_campaigns), len(bq_caps),
    )

    with session_scope() as db:
        # ── Wipe in reverse FK order ─────────────────────────────
        log.info("Clearing Cloud SQL config tables…")
        for model in (
            InvocaCampaign,
            GoogleAdsCampaign,
            VoiceAgentCapability,
            ClinicBlueprintConfig,
            ClinicVoiceAgentConfiguration,
            ClinicLocationDetails,
            Clinic,
            Instance,
        ):
            db.execute(delete(model))

        # ── instances ────────────────────────────────────────────
        log.info("Inserting instances…")
        for row in bq_instances:
            if not row.get("instance_id"):
                continue
            db.add(Instance(
                instance_id=row["instance_id"],
                instance_name=row.get("instance_name") or "",
                primary_contact_name=row.get("primary_contact_name"),
                primary_contact_email=row.get("primary_contact_email"),
                primary_contact_uid=row.get("primary_contact_uid"),
                google_ads_customer_id=row.get("google_ads_customer_id"),
                invoca_profile_id=row.get("invoca_profile_id"),
            ))
        db.flush()

        # ── clinics + location_details + voice_agent_config ──────
        log.info("Inserting clinics + sub-tables…")
        for row in bq_clinics:
            cid = row.get("clinic_id")
            if not cid:
                continue
            pms_type = (row.get("pms_type") or "none").lower()
            if pms_type not in ("blueprint", "audit_data", "none"):
                pms_type = "none"

            db.add(Clinic(
                clinic_id=cid,
                instance_id=row["instance_id"],
                clinic_name=row.get("clinic_name") or "",
                address=row.get("address"),
                place_id=row.get("place_id"),
                gbp_location_id=row.get("gbp_location_id"),
                pms_type=pms_type,
                etl_enabled=_bool(row.get("etl_enabled")),
                country=_country(row.get("country")),
                deleted_at=None,
            ))
            db.add(ClinicLocationDetails(
                clinic_id=cid,
                hours_monday=row.get("hours_monday"),
                hours_tuesday=row.get("hours_tuesday"),
                hours_wednesday=row.get("hours_wednesday"),
                hours_thursday=row.get("hours_thursday"),
                hours_friday=row.get("hours_friday"),
                hours_saturday=row.get("hours_saturday"),
                hours_sunday=row.get("hours_sunday"),
                about_us=row.get("about_us"),
                email=None,  # not present in BQ Users.clinics
                phone=row.get("phone"),
                time_zone=row.get("timezone"),  # rename: BQ `timezone` → SQL `time_zone`
            ))
            db.add(ClinicVoiceAgentConfiguration(
                clinic_id=cid,
                voice_agent_status=(row.get("voice_agent_status") or "inactive"),
                twilio_phone_number=row.get("twilio_phone_number"),
                twilio_phone_sid=row.get("twilio_phone_sid"),
                twilio_verified_caller_id=_bool(row.get("twilio_verified_caller_id")),
                vapi_assistant_id=row.get("vapi_assistant_id"),
                vapi_phone_number_id=row.get("vapi_phone_number_id"),
            ))
        db.flush()

        # ── clinic_blueprint_config ──────────────────────────────
        log.info("Inserting clinic_blueprint_config…")
        for row in bq_pms_configs:
            if (row.get("pms_type") or "").lower() != "blueprint":
                continue
            cfg = _json_or_none(row.get("config")) or {}
            db.add(ClinicBlueprintConfig(
                clinic_id=row["clinic_id"],
                clinic_code=cfg.get("clinic_code"),
                api_url=cfg.get("api_url"),
                aws_url=cfg.get("aws_url"),
            ))
        db.flush()

        # ── voice_agent_capabilities ─────────────────────────────
        log.info("Inserting voice_agent_capabilities…")
        for row in bq_caps:
            db.add(VoiceAgentCapability(
                clinic_id=row["clinic_id"],
                capability_id=row["capability_id"],
                enabled=_bool(row.get("enabled")),
                config=_json_or_none(row.get("config")),
                updated_by=row.get("updated_by"),
            ))
        db.flush()

        # ── google_ads_campaigns + invoca_campaigns ──────────────
        log.info("Inserting campaigns (split by type)…")
        gads, invoca = 0, 0
        for row in bq_campaigns:
            ctype = (row.get("campaign_type") or "").lower()
            ext_id = row.get("external_campaign_id")
            if not ext_id:
                continue
            if ctype == "google_ads":
                db.add(GoogleAdsCampaign(
                    clinic_id=row["clinic_id"],
                    google_ads_campaign_id=ext_id,
                    active=True,
                ))
                gads += 1
            elif ctype == "invoca":
                db.add(InvocaCampaign(
                    clinic_id=row["clinic_id"],
                    invoca_campaign_id=ext_id,
                    active=True,
                ))
                invoca += 1
            else:
                log.warning("  skipping unknown campaign_type=%r", ctype)
        db.flush()

        log.info(
            "Imported: %d instances, %d clinics, %d blueprint_configs, "
            "%d capabilities, %d google_ads, %d invoca",
            len(bq_instances), len(bq_clinics),
            sum(1 for r in bq_pms_configs if (r.get("pms_type") or "").lower() == "blueprint"),
            len(bq_caps), gads, invoca,
        )

    log.info("Done.")


if __name__ == "__main__":
    sys.exit(main())
