-- Migration 005: Clinic voice agent capability toggles
--
-- Run against: BigQuery
-- Project/dataset: substitute {GCP_PROJECT} and {BQ_DATASET} with actual values.
-- BigQuery does not support transactions — run each statement individually.
--
-- Usage:
--   bq query --use_legacy_sql=false < 005_clinic_voice_agent_capabilities.sql
-- Or substitute {GCP_PROJECT} and {BQ_DATASET} with actual values first.
--
-- Per-clinic toggles for voice-agent capabilities. Each capability bundles a
-- VAPI tool + prompt fragment + PMS compatibility requirement. Capability
-- definitions live in code (voice_agent_builder/capabilities.py); this table
-- records which ones are switched on per clinic.
--
-- Mutable (unlike the append-only agent_script_sections / voice_agent_tickets).
-- The (clinic_id, capability_id) pair is unique by convention — enforced by
-- the hypervisor's upsert logic, since BigQuery has no PK constraints.

-- ── Users.clinic_voice_agent_capabilities ──────────────────────────────────

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.{BQ_DATASET}.clinic_voice_agent_capabilities` (
  clinic_id     STRING    NOT NULL OPTIONS(description="FK to clinics.clinic_id"),
  capability_id STRING    NOT NULL OPTIONS(description="Stable slug from voice_agent_builder/capabilities.py CAPABILITY_REGISTRY"),
  enabled       BOOL      NOT NULL OPTIONS(description="True = exposed to the agent as a VAPI tool + prompt fragment"),
  config        STRING             OPTIONS(description="JSON — capability-specific tuning knobs (nullable)"),
  updated_at    TIMESTAMP NOT NULL OPTIONS(description="UTC; updated on every toggle"),
  updated_by    STRING             OPTIONS(description="Firebase email of the admin who flipped the switch")
)
CLUSTER BY clinic_id;

-- ── Backfill: preserve existing behavior for Blueprint clinics ─────────────
-- Before this migration, every pms_type='blueprint' clinic got both
-- patient_match and search_availability attached by agent_factory. Flip those
-- on so the next sync_assistant run produces the same tool set.

INSERT INTO `{GCP_PROJECT}.{BQ_DATASET}.clinic_voice_agent_capabilities`
  (clinic_id, capability_id, enabled, config, updated_at, updated_by)
SELECT
  c.clinic_id,
  cap.capability_id,
  TRUE                       AS enabled,
  NULL                       AS config,
  CURRENT_TIMESTAMP()        AS updated_at,
  'migration:005'            AS updated_by
FROM `{GCP_PROJECT}.{BQ_DATASET}.clinics` c
CROSS JOIN UNNEST([
  STRUCT('patient_match' AS capability_id),
  STRUCT('search_availability' AS capability_id)
]) cap
WHERE c.pms_type = 'blueprint';
