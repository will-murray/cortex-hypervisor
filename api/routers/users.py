from fastapi import APIRouter, Depends
from google.cloud import bigquery

from api.deps import (
    bq_client, bq_table, bq_insert, bq_delete, get_instance_id_or_404,
    verify_token, require_read_access, require_write_access,
)
from api.models import User

router = APIRouter()


@router.get("/users/{instance_id}")
def get_users(instance_id: str, caller: dict = Depends(verify_token)):
    require_read_access(instance_id, caller)
    rows = list(bq_client.query(
        f"SELECT * FROM {bq_table('users')} WHERE instance_id = @instance_id",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("instance_id", "STRING", instance_id)
        ])
    ).result())
    return [dict(r) for r in rows]


@router.post("/users/")
def add_user(user: User, caller: dict = Depends(verify_token)):
    require_write_access(user.instance_id, caller)
    bq_insert("users", [user.model_dump()])
    return {"status": "success"}


@router.delete("/users/{uid}")
def delete_user(uid: str, caller: dict = Depends(verify_token)):
    instance_id = get_instance_id_or_404("users", "uid", uid, "User not found")
    require_write_access(instance_id, caller)
    bq_delete("users", {"uid": uid})
    return {"status": "success"}
