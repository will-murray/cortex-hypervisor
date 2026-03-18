from fastapi import APIRouter, Depends, HTTPException
from google.cloud import bigquery

from api.deps import (
    bq_client, bq_table, bq_insert, bq_update, bq_delete,
    verify_token, require_read_access, require_write_access,
)
from api.models import Staff, StaffUpdate

router = APIRouter()


@router.get("/staff/{instance_id}")
def get_staff(instance_id: str, caller: dict = Depends(verify_token)):
    require_read_access(instance_id, caller)
    rows = list(bq_client.query(
        f"SELECT * FROM {bq_table('staff')} WHERE instance_id = @instance_id",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("instance_id", "STRING", instance_id)
        ])
    ).result())
    return [dict(r) for r in rows]


@router.post("/staff/")
def add_staff(staff: Staff, caller: dict = Depends(verify_token)):
    require_write_access(staff.instance_id, caller)
    bq_insert("staff", [staff.model_dump()])
    return {"status": "success"}


@router.patch("/staff/{instance_id}/{clinic_id}/{name}")
def update_staff(instance_id: str, clinic_id: str, name: str, body: StaffUpdate, caller: dict = Depends(verify_token)):
    require_write_access(instance_id, caller)

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided")

    bq_update("staff", {"instance_id": instance_id, "clinic_id": clinic_id, "name": name}, updates)
    return {"status": "success", "updated": updates}


@router.delete("/staff/{instance_id}/{clinic_id}/{name}")
def delete_staff(instance_id: str, clinic_id: str, name: str, caller: dict = Depends(verify_token)):
    require_write_access(instance_id, caller)
    bq_delete("staff", {"instance_id": instance_id, "clinic_id": clinic_id, "name": name})
    return {"status": "success"}
