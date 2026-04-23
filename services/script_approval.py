"""
Script-section approval gate helpers.

The voice agent requires all four script sections
(scope_of_practice, not_offered, callers_needs, protocols) to have at least
one row with state='approved' before it can be provisioned. See
voice_agent_builder/CLAUDE.md "Agent Specification" for the full contract.
"""
from fastapi import HTTPException
from google.cloud import bigquery

from api.deps import bq_client, bq_table

SECTION_NAMES: list[str] = ["scope_of_practice", "not_offered", "callers_needs", "protocols"]


def missing_approved_sections(clinic_id: str) -> list[str]:
    """Return the list of section_name values that have no approved row for this clinic."""
    sql = f"""
        SELECT DISTINCT section_name
        FROM {bq_table('agent_script_sections')}
        WHERE clinic_id = @clinic_id AND state = 'approved'
    """
    rows = list(bq_client.query(
        sql,
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("clinic_id", "STRING", clinic_id)
        ])
    ).result())
    approved = {row["section_name"] for row in rows}
    return [name for name in SECTION_NAMES if name not in approved]


def require_full_approval(clinic_id: str) -> None:
    """Raises HTTPException(409) if any section is missing an approved row."""
    missing = missing_approved_sections(clinic_id)
    if missing:
        raise HTTPException(
            status_code=409,
            detail=(
                "Voice agent activation blocked: script sections are not fully approved. "
                f"Missing approved rows for: {missing}"
            ),
        )