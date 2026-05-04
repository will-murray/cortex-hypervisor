-- Migration 006: Retire search_availability capability; enable
-- list_appointment_types + find_available_slots in its place.
--
-- Run against: BigQuery
-- BigQuery does not support transactions — run each statement individually.
--
-- Usage:
--   bq query --use_legacy_sql=false < 006_replace_search_availability.sql
-- Substitute {GCP_PROJECT} and {BQ_DATASET} first.
--
-- Why: the old search_availability capability hit Blueprint's POST
-- /rest/availability/search (provider work blocks). The replacement uses GET
-- /rest/availability/?... which returns concrete bookable slots, but requires
-- an event_type_id. Splitting into two capabilities (list types, then find
-- slots) lets the agent pick the right type before searching.
--
-- For every clinic that had search_availability=TRUE, this migration:
--   1. Sets search_availability=FALSE (effectively retired — the capability
--      is no longer in the registry, but we flip it off explicitly so the
--      dashboard's "enabled count" stays consistent).
--   2. Inserts enabled=TRUE rows for list_appointment_types + find_available_slots
--      (using the same MERGE pattern as the dashboard PUT to be idempotent).
--
-- Re-running this migration is safe — the MERGE leaves existing rows alone
-- if they already match the target state.

-- ── Step 1: flip search_availability rows to FALSE ──────────────────────────

UPDATE `{GCP_PROJECT}.{BQ_DATASET}.clinic_voice_agent_capabilities`
SET enabled = FALSE,
    updated_at = CURRENT_TIMESTAMP(),
    updated_by = 'migration:006'
WHERE capability_id = 'search_availability'
  AND enabled = TRUE;

-- ── Step 2: enable the two replacement capabilities for those clinics ───────
-- Find clinics that had search_availability turned on at some point (the row
-- above may have just been flipped off, but it tells us who used it). Enable
-- both replacements for them via MERGE so re-runs don't duplicate rows.

MERGE `{GCP_PROJECT}.{BQ_DATASET}.clinic_voice_agent_capabilities` T
USING (
  SELECT DISTINCT c.clinic_id, cap.capability_id
  FROM `{GCP_PROJECT}.{BQ_DATASET}.clinic_voice_agent_capabilities` c
  CROSS JOIN UNNEST([
    STRUCT('list_appointment_types' AS capability_id),
    STRUCT('find_available_slots' AS capability_id)
  ]) cap
  WHERE c.capability_id = 'search_availability'
) S
ON T.clinic_id = S.clinic_id AND T.capability_id = S.capability_id
WHEN MATCHED THEN
  UPDATE SET enabled = TRUE,
             updated_at = CURRENT_TIMESTAMP(),
             updated_by = 'migration:006'
WHEN NOT MATCHED THEN
  INSERT (clinic_id, capability_id, enabled, config, updated_at, updated_by)
  VALUES (S.clinic_id, S.capability_id, TRUE, NULL,
          CURRENT_TIMESTAMP(), 'migration:006');
