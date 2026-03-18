import uuid

from fastapi import APIRouter, Depends, HTTPException
from google.cloud import bigquery

from api.deps import (
    bq_client, bq_table, bq_insert, bq_update, bq_delete, get_instance_id_or_404,
    verify_token, require_read_access, require_write_access,
)
from api.models import Service, ServiceUpdate

router = APIRouter()


@router.get("/services/{instance_id}")
def get_services(instance_id: str, caller: dict = Depends(verify_token)):
    require_read_access(instance_id, caller)
    rows = list(bq_client.query(
        f"SELECT * FROM {bq_table('services')} WHERE instance_id = @instance_id",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("instance_id", "STRING", instance_id)
        ])
    ).result())
    return [dict(r) for r in rows]


@router.post("/services/")
def add_service(service: Service, caller: dict = Depends(verify_token)):
    require_write_access(service.instance_id, caller)
    service = service.model_copy(update={"service_id": str(uuid.uuid4())})
    bq_insert("services", [service.model_dump()])
    return {"status": "success", "service_id": service.service_id}


@router.patch("/services/{service_id}")
def update_service(service_id: str, body: ServiceUpdate, caller: dict = Depends(verify_token)):
    instance_id = get_instance_id_or_404("services", "service_id", service_id, "Service not found")
    require_write_access(instance_id, caller)

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided")

    bq_update("services", {"service_id": service_id}, updates)
    return {"status": "success", "updated": updates}


@router.delete("/services/{service_id}")
def delete_service(service_id: str, caller: dict = Depends(verify_token)):
    instance_id = get_instance_id_or_404("services", "service_id", service_id, "Service not found")
    require_write_access(instance_id, caller)
    bq_delete("services", {"service_id": service_id})
    return {"status": "success"}
