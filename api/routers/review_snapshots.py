from fastapi import APIRouter, Depends
from google.cloud import bigquery
from api.deps import bq_client, bq_table, bq_insert, verify_token, require_read_access, require_write_access
from api.models import ReviewSnapshot

router = APIRouter()

# BigQuery DDL (run once to create the table):
# CREATE TABLE IF NOT EXISTS `project-demo-2-482101.Users.review_snapshots` (
#   instance_id   STRING,
#   clinic_id     STRING,
#   snapshot_date STRING,
#   review_count  INT64,
#   avg_rating    FLOAT64
# );

@router.post("/review_snapshots/{instance_id}")
def add_review_snapshot(instance_id: str, snapshot: ReviewSnapshot, caller: dict = Depends(verify_token)):
    require_write_access(instance_id, caller)
    row = snapshot.model_dump()
    # bq_insert coerces all values to STRING via DML; numeric fields stored as strings
    bq_insert("review_snapshots", [row])
    return {"status": "success"}


@router.get("/review_snapshots/{instance_id}")
def get_review_snapshots(instance_id: str, clinic_id: str = None, caller: dict = Depends(verify_token)):
    require_read_access(instance_id, caller)

    params = [bigquery.ScalarQueryParameter("instance_id", "STRING", instance_id)]
    clinic_filter = ""
    if clinic_id:
        clinic_filter = "AND clinic_id = @clinic_id"
        params.append(bigquery.ScalarQueryParameter("clinic_id", "STRING", clinic_id))

    rows = list(bq_client.query(
        f"""
        SELECT instance_id, clinic_id, snapshot_date,
               CAST(review_count AS INT64) AS review_count,
               CAST(avg_rating AS FLOAT64) AS avg_rating
        FROM {bq_table('review_snapshots')}
        WHERE instance_id = @instance_id
          {clinic_filter}
        ORDER BY clinic_id, snapshot_date ASC
        """,
        job_config=bigquery.QueryJobConfig(query_parameters=params)
    ).result())
    return [dict(r) for r in rows]
