"""
Agent script section management.

Endpoints:
    GET  /clinics/{clinic_id}/agent_script/sections
        List the latest draft + latest approved row per section.
    POST /clinics/{clinic_id}/agent_script/sections/{section_name}/approve
        Approve a specific row by section_id (appends a new 'approved' row).

Both endpoints are user-facing (Firebase auth). Approval requires write access
to the clinic's instance (admin for the instance, or super_admin globally).

The script table is append-only — every state transition creates a new row.
See voice_agent_builder/CLAUDE.md "Agent Specification" for the contract.
"""
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from google.cloud import bigquery
from pydantic import BaseModel

from api.deps import (
    bq_client,
    bq_table,
    verify_token,
    require_read_access,
    require_write_access,
)
from services.script_approval import SECTION_NAMES

router = APIRouter()


class ScriptSectionRow(BaseModel):
    section_id: str
    clinic_id: str
    section_name: str
    content: str
    state: Literal["draft", "approved"]
    created_at: str
    approved_by: str | None = None
    approved_at: str | None = None
    source: str


class SectionStatus(BaseModel):
    latest_draft: ScriptSectionRow | None = None
    latest_approved: ScriptSectionRow | None = None


class SectionsListResponse(BaseModel):
    clinic_id: str
    sections: dict[str, SectionStatus]
    all_approved: bool


class ApproveSectionRequest(BaseModel):
    section_id: str


def _get_clinic_or_404(clinic_id: str) -> dict:
    rows = list(bq_client.query(
        f"SELECT instance_id FROM {bq_table('clinics')} WHERE clinic_id = @clinic_id",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("clinic_id", "STRING", clinic_id)
        ])
    ).result())
    if not rows:
        raise HTTPException(status_code=404, detail="Clinic not found")
    return dict(rows[0])


def _row_to_model(row: dict) -> ScriptSectionRow:
    return ScriptSectionRow(
        section_id=row["section_id"],
        clinic_id=row["clinic_id"],
        section_name=row["section_name"],
        content=row["content"],
        state=row["state"],
        created_at=row["created_at"],
        approved_by=row.get("approved_by"),
        approved_at=row.get("approved_at"),
        source=row["source"],
    )


@router.get(
    "/clinics/{clinic_id}/agent_script/sections",
    response_model=SectionsListResponse,
)
def list_sections(clinic_id: str, caller: dict = Depends(verify_token)):
    """
    For each of the four script sections, return the most recent draft and the
    most recent approved row. Either may be null if none exists yet.
    """
    clinic = _get_clinic_or_404(clinic_id)
    require_read_access(clinic["instance_id"], caller)

    query = f"""
    WITH ranked AS (
        SELECT
          section_id, clinic_id, section_name, content, state,
          FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', created_at, 'UTC') AS created_at,
          approved_by,
          IF(approved_at IS NULL, NULL,
             FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', approved_at, 'UTC')) AS approved_at,
          source,
          ROW_NUMBER() OVER (PARTITION BY section_name, state ORDER BY created_at DESC) AS rn
        FROM {bq_table('agent_script_sections')}
        WHERE clinic_id = @clinic_id
    )
    SELECT section_id, clinic_id, section_name, content, state, created_at,
           approved_by, approved_at, source
    FROM ranked
    WHERE rn = 1
    """
    rows = list(bq_client.query(
        query,
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("clinic_id", "STRING", clinic_id)
        ])
    ).result())

    sections: dict[str, SectionStatus] = {name: SectionStatus() for name in SECTION_NAMES}
    for row in rows:
        d = dict(row)
        if d["section_name"] not in sections:
            continue
        model = _row_to_model(d)
        if d["state"] == "draft":
            sections[d["section_name"]].latest_draft = model
        else:
            sections[d["section_name"]].latest_approved = model

    all_approved = all(sections[name].latest_approved is not None for name in SECTION_NAMES)
    return SectionsListResponse(clinic_id=clinic_id, sections=sections, all_approved=all_approved)


@router.post(
    "/clinics/{clinic_id}/agent_script/sections/{section_name}/approve",
    response_model=ScriptSectionRow,
)
def approve_section(
    clinic_id: str,
    section_name: str,
    body: ApproveSectionRequest,
    caller: dict = Depends(verify_token),
):
    """
    Approve a draft section by its section_id. Appends a new row with
    state='approved', content copied verbatim from the referenced row, and
    approved_by/approved_at populated. The prior row is left untouched.
    """
    if section_name not in SECTION_NAMES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid section_name. Must be one of: {SECTION_NAMES}",
        )

    clinic = _get_clinic_or_404(clinic_id)
    require_write_access(clinic["instance_id"], caller)

    source_rows = list(bq_client.query(
        f"""
        SELECT content, section_name
        FROM {bq_table('agent_script_sections')}
        WHERE clinic_id = @clinic_id AND section_id = @section_id
        """,
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("clinic_id", "STRING", clinic_id),
            bigquery.ScalarQueryParameter("section_id", "STRING", body.section_id),
        ])
    ).result())
    if not source_rows:
        raise HTTPException(status_code=404, detail="section_id not found for this clinic")
    source = dict(source_rows[0])
    if source["section_name"] != section_name:
        raise HTTPException(
            status_code=400,
            detail=(
                f"section_id belongs to section '{source['section_name']}', "
                f"not '{section_name}'"
            ),
        )

    approver_email = caller.get("email") or caller.get("uid") or "unknown"
    new_section_id = str(uuid.uuid4())

    bq_client.query(
        f"""
        INSERT INTO {bq_table('agent_script_sections')} (
          section_id, clinic_id, section_name, content, state, created_at,
          approved_by, approved_at, source
        ) VALUES (
          @section_id, @clinic_id, @section_name, @content, 'approved',
          CURRENT_TIMESTAMP(), @approved_by, CURRENT_TIMESTAMP(), 'manual'
        )
        """,
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("section_id", "STRING", new_section_id),
            bigquery.ScalarQueryParameter("clinic_id", "STRING", clinic_id),
            bigquery.ScalarQueryParameter("section_name", "STRING", section_name),
            bigquery.ScalarQueryParameter("content", "STRING", source["content"]),
            bigquery.ScalarQueryParameter("approved_by", "STRING", approver_email),
        ])
    ).result()

    inserted = list(bq_client.query(
        f"""
        SELECT section_id, clinic_id, section_name, content, state,
               FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', created_at, 'UTC') AS created_at,
               approved_by,
               FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', approved_at, 'UTC') AS approved_at,
               source
        FROM {bq_table('agent_script_sections')}
        WHERE section_id = @section_id
        """,
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("section_id", "STRING", new_section_id),
        ])
    ).result())
    if not inserted:
        raise HTTPException(status_code=500, detail="Approval row not found after insert")
    return _row_to_model(dict(inserted[0]))