from fastapi import APIRouter, Depends, HTTPException
from google.cloud import bigquery
from api.deps import (
    bq_client, bq_table, bq_insert, bq_update, bq_delete, get_instance_id_or_404,
    verify_token, require_read_access, require_write_access,
)
from api.models import ClinicCreate, ClinicUpdate
from services.provisioning import provision_clinic

router = APIRouter()

@router.get("/clinics/{instance_id}")
def get_clinics(instance_id: str, caller: dict = Depends(verify_token)):
    require_read_access(instance_id, caller)

    rows = list(bq_client.query(
        f"SELECT * FROM {bq_table('clinics')} WHERE instance_id = @instance_id",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("instance_id", "STRING", instance_id)
        ])
    ).result())
    return [dict(r) for r in rows]

@router.get("/clinics/{instance_id}/{clinic_id}")
def get_clinic(instance_id: str, clinic_id: str, caller: dict = Depends(verify_token)):
    require_read_access(instance_id, caller)
    
    rows = list(bq_client.query(
        f"SELECT * FROM {bq_table('clinics')} WHERE instance_id = @instance_id AND clinic_id = @clinic_id",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("instance_id", "STRING", instance_id),
            bigquery.ScalarQueryParameter("clinic_id", "STRING", clinic_id)
        ])
    ).result())
    if not rows:
        raise HTTPException(status_code=404, detail="Clinic not found")
    return dict(rows[0])

@router.post("/clinics/{instance_id}")
def add_clinic(instance_id: str, clinic: ClinicCreate, caller: dict = Depends(verify_token)):
    require_write_access(instance_id, caller)

    clinic_data, _, clinic_id = provision_clinic(
        clinic_data=clinic.model_dump(),
        instance_id=instance_id,
    )

    bq_insert("clinics", [clinic_data])
    return {"status": "success", "clinic_id": clinic_id}


@router.patch("/clinics/{clinic_id}")
def update_clinic(clinic_id: str, body: ClinicUpdate, caller: dict = Depends(verify_token)):
    instance_id = get_instance_id_or_404("clinics", "clinic_id", clinic_id, "Clinic not found")
    require_write_access(instance_id, caller)

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided")

    bq_update("clinics", {"clinic_id": clinic_id}, updates)
    return {"status": "success", "updated": updates}


@router.delete("/clinics/{clinic_id}")
def delete_clinic(clinic_id: str, caller: dict = Depends(verify_token)):
    instance_id = get_instance_id_or_404("clinics", "clinic_id", clinic_id, "Clinic not found")
    require_write_access(instance_id, caller)
    bq_delete("clinics", {"clinic_id": clinic_id})
    return {"status": "success"}
