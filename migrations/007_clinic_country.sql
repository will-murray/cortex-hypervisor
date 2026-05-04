-- Migration 007: Add country (ISO-3166 alpha-2) to clinics
--
-- The country drives Twilio number purchase region, VAPI transcriber language
-- (e.g. en-CA vs en-US), and the locale block injected into the voice agent's
-- system prompt. Existing clinics default to US except ACNA (Canada).
--
-- Run against: BigQuery
-- Usage:
--   bq query --use_legacy_sql=false < 007_clinic_country.sql

ALTER TABLE `{GCP_PROJECT}.{BQ_DATASET}.clinics`
  ADD COLUMN IF NOT EXISTS country STRING
    OPTIONS(description="ISO-3166 alpha-2 country code, e.g. US, CA, GB, AU");

-- Backfill: ACNA is in Alberta (Canada); everything else assumed US.
UPDATE `{GCP_PROJECT}.{BQ_DATASET}.clinics`
   SET country = 'CA'
 WHERE clinic_name = 'Audiology Clinic of Northern Alberta';

UPDATE `{GCP_PROJECT}.{BQ_DATASET}.clinics`
   SET country = 'US'
 WHERE country IS NULL;
