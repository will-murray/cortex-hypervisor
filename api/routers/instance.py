import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from google.api_core.exceptions import BadRequest
from google.cloud import bigquery

from api.deps import (
    bq_client, bq_table, bq_insert, bq_update, bq_delete,
    verify_token, get_instance_id_for_uid, require_write_access,
)
from api.models import ProvisionRequest, InstanceUpdate
from services.provisioning import provision_full_account, write_provision_to_bq

router = APIRouter()


@router.post("/provision_account/")
def provision_account(payload: ProvisionRequest, caller: dict = Depends(verify_token)):
    role = caller.get("role")
    if role not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Access denied")

    if payload.uid != caller["uid"] and role != "super_admin":
        raise HTTPException(status_code=403, detail="Cannot provision for another user")

    uid = payload.uid

    if get_instance_id_for_uid(uid) and role != "super_admin":
        return {"status": "error", "message": f"{uid} already has an instance provisioned"}

    result = provision_full_account(
        instance_create=payload.instance.model_dump(),
        clinics_create=[c.model_dump() for c in payload.clinics],
        primary_contact_uid=uid,
    )

    instance = result["instance"]
    clinics = result["clinics"]
    clinic_id_map = result["clinic_id_map"]
    instance_id = instance["instance_id"]

    staff = [s.model_copy(update={
        "instance_id": instance_id,
        "clinic_id": clinic_id_map.get(s.clinic_id, s.clinic_id),
    }) for s in payload.staff]
    services = [s.model_copy(update={
        "instance_id": instance_id,
        "clinic_id": clinic_id_map.get(s.clinic_id, s.clinic_id),
        "service_id": str(uuid.uuid4()),
    }) for s in payload.services]
    insurance = [i.model_copy(update={
        "instance_id": instance_id,
        "clinic_id": clinic_id_map.get(i.clinic_id, i.clinic_id),
        "insurance_id": str(uuid.uuid4()),
    }) for i in payload.insurance]

    write_provision_to_bq(
        instance=instance,
        clinics=clinics,
        staff=[s.model_dump() for s in staff],
        services=[s.model_dump() for s in services],
        insurance=[i.model_dump() for i in insurance],
    )

    return {
        "status": "success",
        "message": "Instance provisioned",
        "instance_id": instance_id,
        "clinic_ids": clinic_id_map,
    }


@router.get("/instance/{uid}")
def get_instance(uid: str, caller: dict = Depends(verify_token)):
    role = caller.get("role")
    if role not in ("admin", "super_admin", "viewer"):
        raise HTTPException(status_code=403, detail="Access denied")
    if role != "super_admin" and caller["uid"] != uid:
        raise HTTPException(status_code=403, detail="Access denied")

    instance_id = get_instance_id_for_uid(uid)
    if not instance_id:
        raise HTTPException(status_code=404, detail=f"No instance found for uid {uid}")

    def query_table(table: str, id_col: str, id_val: str):
        return [dict(row) for row in bq_client.query(
            f"SELECT * FROM {bq_table(table)} WHERE {id_col} = @val",
            job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("val", "STRING", id_val)
            ])
        ).result()]

    return {
        "instance": query_table("instances", "instance_id", instance_id),
        "clinics": query_table("clinics", "instance_id", instance_id),
        "staff": query_table("staff", "instance_id", instance_id),
        "services": query_table("services", "instance_id", instance_id),
        "insurance": query_table("insurance", "instance_id", instance_id),
        "users": query_table("users", "instance_id", instance_id),
    }


@router.patch("/instance/{instance_id}")
def update_instance(instance_id: str, body: InstanceUpdate, caller: dict = Depends(verify_token)):
    require_write_access(instance_id, caller)

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided")

    bq_update("instances", {"instance_id": instance_id}, updates)
    return {"status": "success", "updated": updates}


@router.delete("/instance/{uid}")
def delete_instance(uid: str, caller: dict = Depends(verify_token)):
    role = caller.get("role")
    if role not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Access denied")
    if role != "super_admin" and caller["uid"] != uid:
        raise HTTPException(status_code=403, detail="Access denied")

    instance_id = get_instance_id_for_uid(uid)
    if not instance_id:
        raise HTTPException(status_code=404, detail=f"No instance found for uid {uid}")

    tables = ["services", "insurance", "staff", "users", "clinics"]
    try:
        for table in tables:
            bq_client.query(
                f"DELETE FROM {bq_table(table)} WHERE instance_id = @instance_id",
                job_config=bigquery.QueryJobConfig(query_parameters=[
                    bigquery.ScalarQueryParameter("instance_id", "STRING", instance_id)
                ])
            ).result()
        bq_client.query(
            f"DELETE FROM {bq_table('instances')} WHERE primary_contact_uid = @uid",
            job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("uid", "STRING", uid)
            ])
        ).result()
    except BadRequest as e:
        if "streaming buffer" in str(e):
            return JSONResponse(status_code=409, content={
                "status": "error",
                "message": "Instance was recently created and is still in BigQuery's streaming buffer. Deletion will be available within 90 minutes.",
                "instance_id": instance_id
            })
        raise

    return {"status": "success", "message": f"Instance {instance_id} and all associated records deleted"}
