-- Migration 003: Create clinic_pms_config table, migrate data, drop blueprint columns
--
-- Moves PMS-specific config out of the clinics table into a dedicated
-- clinic_pms_config table. Secrets (API keys, AWS creds) live in
-- Google Secret Manager under pms/{clinic_id}/<secret-name>.
--
-- The clinics table keeps only pms_type as the PMS selector.
-- The config column is a JSON string whose shape varies by pms_type.
--
-- Run each statement individually — BigQuery does not support transactions.

-- ── Create clinic_pms_config table ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.{BQ_DATASET}.clinic_pms_config` (
  clinic_id   STRING NOT NULL OPTIONS(description="FK to clinics.clinic_id"),
  pms_type    STRING NOT NULL OPTIONS(description="blueprint | auditdata"),
  config      STRING NOT NULL OPTIONS(description="JSON — PMS-specific non-secret settings")
);

-- ── Drop blueprint columns from clinics ─────────────────────────────────────
-- pms_type stays on clinics (it's PMS-agnostic).
-- The actual config moves to clinic_pms_config; secrets move to Secret Manager.

ALTER TABLE `{GCP_PROJECT}.{BQ_DATASET}.clinics` DROP COLUMN IF EXISTS blueprint_server;
ALTER TABLE `{GCP_PROJECT}.{BQ_DATASET}.clinics` DROP COLUMN IF EXISTS blueprint_clinic_slug;
ALTER TABLE `{GCP_PROJECT}.{BQ_DATASET}.clinics` DROP COLUMN IF EXISTS blueprint_api_key;
ALTER TABLE `{GCP_PROJECT}.{BQ_DATASET}.clinics` DROP COLUMN IF EXISTS blueprint_location_id;
ALTER TABLE `{GCP_PROJECT}.{BQ_DATASET}.clinics` DROP COLUMN IF EXISTS blueprint_user_id;

-- Also drop the feed credential columns from migration 002 if they were applied
ALTER TABLE `{GCP_PROJECT}.{BQ_DATASET}.clinics` DROP COLUMN IF EXISTS blueprint_s3_uri;
ALTER TABLE `{GCP_PROJECT}.{BQ_DATASET}.clinics` DROP COLUMN IF EXISTS blueprint_aws_access_key_id;
ALTER TABLE `{GCP_PROJECT}.{BQ_DATASET}.clinics` DROP COLUMN IF EXISTS blueprint_aws_secret_key;
ALTER TABLE `{GCP_PROJECT}.{BQ_DATASET}.clinics` DROP COLUMN IF EXISTS blueprint_aws_region;
ALTER TABLE `{GCP_PROJECT}.{BQ_DATASET}.clinics` DROP COLUMN IF EXISTS blueprint_zip_password;
