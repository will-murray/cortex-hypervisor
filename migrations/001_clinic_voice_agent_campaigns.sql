-- Migration 001: Add voice agent + PMS fields to clinics; create clinic_campaigns table
--
-- Run against: BigQuery
-- Project/dataset: set GCP_PROJECT and BQ_DATASET env vars, then substitute below.
-- BigQuery does not support transactions — run each statement individually.
-- All new columns are NULLABLE so existing rows are unaffected.
--
-- Usage:
--   bq query --use_legacy_sql=false < 001_clinic_voice_agent_campaigns.sql
-- Or substitute @project and @dataset with actual values.

-- ── Voice agent fields ──────────────────────────────────────────────────────

ALTER TABLE `{GCP_PROJECT}.{BQ_DATASET}.clinics`
  ADD COLUMN IF NOT EXISTS voice_agent_status STRING
    OPTIONS(description="inactive | provisioning | active | error"),
  ADD COLUMN IF NOT EXISTS twilio_phone_number STRING
    OPTIONS(description="E.164 format e.g. +16045551234"),
  ADD COLUMN IF NOT EXISTS twilio_phone_sid STRING
    OPTIONS(description="Twilio SID for the provisioned number"),
  ADD COLUMN IF NOT EXISTS twilio_verified_caller_id BOOL
    OPTIONS(description="Whether the clinic primary number is verified for outbound caller ID"),
  ADD COLUMN IF NOT EXISTS vapi_assistant_id STRING
    OPTIONS(description="VAPI assistant ID"),
  ADD COLUMN IF NOT EXISTS vapi_phone_number_id STRING
    OPTIONS(description="VAPI internal ID after importing Twilio number");

-- ── PMS (Blueprint OMS) fields ──────────────────────────────────────────────

ALTER TABLE `{GCP_PROJECT}.{BQ_DATASET}.clinics`
  ADD COLUMN IF NOT EXISTS pms_type STRING
    OPTIONS(description="none | blueprint"),
  ADD COLUMN IF NOT EXISTS blueprint_server STRING
    OPTIONS(description="Blueprint API server e.g. wp2.bp-solutions.net:8443"),
  ADD COLUMN IF NOT EXISTS blueprint_clinic_slug STRING
    OPTIONS(description="[CLINIC] path segment in Blueprint REST URLs"),
  ADD COLUMN IF NOT EXISTS blueprint_api_key STRING
    OPTIONS(description="Blueprint API key — treat as a credential, restrict column access"),
  ADD COLUMN IF NOT EXISTS blueprint_location_id INT64
    OPTIONS(description="Numeric Blueprint location ID for this clinic"),
  ADD COLUMN IF NOT EXISTS blueprint_user_id INT64
    OPTIONS(description="Numeric Blueprint user ID used as service account for API writes");

-- ── clinic_campaigns table ───────────────────────────────────────────────────
--
-- Replaces the single google_ads_campaign_id / invoca_campaign_id columns on clinics
-- (those columns are kept for backwards compatibility but should not receive new data).

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.{BQ_DATASET}.clinic_campaigns` (
  id              STRING  NOT NULL OPTIONS(description="UUID primary key"),
  clinic_id       STRING  NOT NULL OPTIONS(description="Foreign key to clinics.clinic_id"),
  instance_id     STRING  NOT NULL OPTIONS(description="Foreign key to instances.instance_id"),
  campaign_type   STRING  NOT NULL OPTIONS(description="google_ads | invoca"),
  external_campaign_id STRING NOT NULL OPTIONS(description="The campaign ID in the external system"),
  campaign_name   STRING           OPTIONS(description="Human-readable campaign name")
);
