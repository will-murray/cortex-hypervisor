-- Migration 004: Voice Agent v1 tables — agent_script_sections, voice_agent_tickets
--
-- Run against: BigQuery
-- Project/dataset: set GCP_PROJECT and BQ_DATASET env vars, then substitute below.
-- BigQuery does not support transactions — run each statement individually.
--
-- Usage:
--   bq query --use_legacy_sql=false < 004_voice_agent_v1_tables.sql
-- Or substitute {GCP_PROJECT} and {BQ_DATASET} with actual values first.
--
-- See voice_agent_builder/CLAUDE.md "Agent Specification" for the spec these
-- tables implement. Retires the legacy Users.agent_script table (kept until
-- the compiler migration in big-query-ingestion lands — Phase 1 of the plan).

-- ── Users.agent_script_sections ─────────────────────────────────────────────
--
-- Append-only. One row per state transition for a given (clinic_id, section_name).
-- Agent read path: for each section, select the most recent row with state='approved'.
-- Compiler write path: one 'draft' row per section per run, source='compiler'.
-- Dashboard edits/approvals append 'draft' or 'approved' rows, source='manual'.

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.{BQ_DATASET}.agent_script_sections` (
  section_id   STRING    NOT NULL OPTIONS(description="UUID primary key"),
  clinic_id    STRING    NOT NULL OPTIONS(description="FK to clinics.clinic_id"),
  section_name STRING    NOT NULL OPTIONS(description="scope_of_practice | not_offered | callers_needs | protocols"),
  content      STRING    NOT NULL OPTIONS(description="Free text — the section body the agent reads verbatim"),
  state        STRING    NOT NULL OPTIONS(description="draft | approved"),
  created_at   TIMESTAMP NOT NULL OPTIONS(description="UTC"),
  approved_by  STRING             OPTIONS(description="Firebase email of approver; NULL while state='draft'"),
  approved_at  TIMESTAMP          OPTIONS(description="When state transitioned to 'approved'; NULL while draft"),
  source       STRING    NOT NULL OPTIONS(description="compiler | manual — compiler = ETL-generated, manual = dashboard-edited")
)
CLUSTER BY clinic_id, section_name;

-- ── Users.voice_agent_tickets ───────────────────────────────────────────────
--
-- Append-only. One row per ticket at creation. Written by the voice agent's
-- submit_ticket tool via cortex-hypervisor. Status lifecycle (open → handled
-- → ...) is tracked in a separate table (future — out of v1 scope).
--
-- details is STRING-encoded JSON for consistency with clinic_pms_config.config
-- (migration 003). Use CAST(details AS JSON) in queries for JSON functions.

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.{BQ_DATASET}.voice_agent_tickets` (
  ticket_id            STRING    NOT NULL OPTIONS(description="UUID primary key, server-generated"),
  clinic_id            STRING    NOT NULL OPTIONS(description="FK to clinics.clinic_id"),
  vapi_call_id         STRING             OPTIONS(description="VAPI call ID — join key to transcript/recording"),
  created_at           TIMESTAMP NOT NULL OPTIONS(description="UTC"),
  caller_phone         STRING             OPTIONS(description="E.164 format"),
  caller_name          STRING             OPTIONS(description="Name as given by the caller (may differ from patient record)"),
  patient_match_status STRING             OPTIONS(description="matched | unmatched | new | ambiguous"),
  blueprint_patient_id STRING            OPTIONS(description="Blueprint client_id; matches Blueprint_PHI.ClientDemographics.client_id (STRING). Set when patient_match_status='matched'"),
  last4_confirmed      BOOL               OPTIONS(description="TRUE if caller confirmed last 4 of on-file phone"),
  intent_category      STRING             OPTIONS(description="Free-string label chosen by the agent; typically a Caller's Needs label"),
  summary              STRING             OPTIONS(description="Agent-written 1–2 sentence recap"),
  details              STRING             OPTIONS(description="JSON — intent-specific collected fields"),
  suggested_followup   STRING             OPTIONS(description="Agent's recommended next action"),
  urgency              STRING             OPTIONS(description="normal | urgent"),
  status               STRING             OPTIONS(description="Initial 'open' at creation; lifecycle tracked elsewhere")
)
PARTITION BY DATE(created_at)
CLUSTER BY clinic_id;
