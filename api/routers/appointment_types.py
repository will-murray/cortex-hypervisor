import uuid

from fastapi import APIRouter, Depends, HTTPException
from google.cloud import bigquery

from api.deps import (
    bq_client, bq_table, bq_insert, bq_update, bq_delete, get_instance_id_or_404,
    verify_token, require_read_access, require_write_access,
)
from api.models import AppointmentType, AppointmentTypeUpdate

router = APIRouter()


@router.get("/appointment_types/{instance_id}")
def get_appointment_types(instance_id: str, caller: dict = Depends(verify_token)):
    require_read_access(instance_id, caller)
    rows = list(bq_client.query(
        f"SELECT * FROM {bq_table('appointment_types')} WHERE instance_id = @instance_id ORDER BY clinic_name, appointment_name",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("instance_id", "STRING", instance_id)
        ])
    ).result())
    return [dict(r) for r in rows]


@router.post("/appointment_types/")
def add_appointment_type(appt: AppointmentType, caller: dict = Depends(verify_token)):
    require_write_access(appt.instance_id, caller)
    appt = appt.model_copy(update={"appointment_type_id": str(uuid.uuid4())})
    bq_insert("appointment_types", [appt.model_dump()])
    return {"status": "success", "appointment_type_id": appt.appointment_type_id}


@router.patch("/appointment_types/{appointment_type_id}")
def update_appointment_type(appointment_type_id: str, body: AppointmentTypeUpdate, caller: dict = Depends(verify_token)):
    instance_id = get_instance_id_or_404("appointment_types", "appointment_type_id", appointment_type_id, "Appointment type not found")
    require_write_access(instance_id, caller)

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided")

    bq_update("appointment_types", {"appointment_type_id": appointment_type_id}, updates)
    return {"status": "success", "updated": updates}


@router.delete("/appointment_types/{appointment_type_id}")
def delete_appointment_type(appointment_type_id: str, caller: dict = Depends(verify_token)):
    instance_id = get_instance_id_or_404("appointment_types", "appointment_type_id", appointment_type_id, "Appointment type not found")
    require_write_access(instance_id, caller)
    bq_delete("appointment_types", {"appointment_type_id": appointment_type_id})
    return {"status": "success"}
