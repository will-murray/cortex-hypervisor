import uuid

from fastapi import APIRouter, Depends, HTTPException
from google.cloud import bigquery

from api.deps import (
    bq_client, bq_table, bq_insert, bq_update, bq_delete, get_instance_id_or_404,
    verify_token, require_read_access, require_write_access,
)
from api.models import Insurance, InsuranceUpdate

router = APIRouter()


@router.get("/insurance/{instance_id}")
def get_insurance(instance_id: str, caller: dict = Depends(verify_token)):
    require_read_access(instance_id, caller)
    rows = list(bq_client.query(
        f"SELECT * FROM {bq_table('insurance')} WHERE instance_id = @instance_id",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("instance_id", "STRING", instance_id)
        ])
    ).result())
    return [dict(r) for r in rows]


@router.post("/insurance/")
def add_insurance(insurance: Insurance, caller: dict = Depends(verify_token)):
    require_write_access(insurance.instance_id, caller)
    insurance = insurance.model_copy(update={"insurance_id": str(uuid.uuid4())})
    bq_insert("insurance", [insurance.model_dump()])
    return {"status": "success", "insurance_id": insurance.insurance_id}


@router.patch("/insurance/{insurance_id}")
def update_insurance(insurance_id: str, body: InsuranceUpdate, caller: dict = Depends(verify_token)):
    instance_id = get_instance_id_or_404("insurance", "insurance_id", insurance_id, "Insurance not found")
    require_write_access(instance_id, caller)

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided")

    bq_update("insurance", {"insurance_id": insurance_id}, updates)
    return {"status": "success", "updated": updates}


@router.delete("/insurance/{insurance_id}")
def delete_insurance(insurance_id: str, caller: dict = Depends(verify_token)):
    instance_id = get_instance_id_or_404("insurance", "insurance_id", insurance_id, "Insurance not found")
    require_write_access(instance_id, caller)
    bq_delete("insurance", {"insurance_id": insurance_id})
    return {"status": "success"}
