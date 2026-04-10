import json
import os

from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import firebase_admin
from firebase_admin import credentials, auth
from google.api_core.exceptions import BadRequest
from google.cloud import bigquery

load_dotenv(dotenv_path=".env")

PROJECT = os.environ["GCP_PROJECT"]
DATASET = os.environ["BQ_DATASET"]

bq_client = bigquery.Client.from_service_account_info(json.loads(os.environ["GCS_SERVICE_ACCOUNT"]))
_cred = credentials.Certificate(json.loads(os.environ["FIREBASE_ADMIN_SERVICE_ACCOUNT"]))
firebase_admin.initialize_app(_cred)

bearer_scheme = HTTPBearer()


def bq_table(table: str) -> str:
    """Table reference for SQL queries (with backticks)."""
    return f"`{PROJECT}.{DATASET}.{table}`"


def bq_insert(table: str, rows: list[dict]):
    """Insert rows using DML INSERT to avoid the streaming buffer, allowing immediate UPDATE/DELETE."""
    for row in rows:
        filtered = {k: v for k, v in row.items() if v is not None}
        columns = ", ".join(filtered.keys())
        placeholders = ", ".join(f"@{k}" for k in filtered.keys())
        params = [bigquery.ScalarQueryParameter(k, "STRING", str(v)) for k, v in filtered.items()]
        bq_client.query(
            f"INSERT INTO {bq_table(table)} ({columns}) VALUES ({placeholders})",
            job_config=bigquery.QueryJobConfig(query_parameters=params)
        ).result()


def bq_update(table: str, where: dict, updates: dict):
    """Run a parameterized UPDATE. Raises 409 if the row is still in the streaming buffer."""
    set_clause = ", ".join(f"{k} = @{k}" for k in updates)
    where_clause = " AND ".join(f"{k} = @_w_{k}" for k in where)
    params = [bigquery.ScalarQueryParameter(k, "STRING", v) for k, v in updates.items()]
    params += [bigquery.ScalarQueryParameter(f"_w_{k}", "STRING", v) for k, v in where.items()]
    try:
        bq_client.query(
            f"UPDATE {bq_table(table)} SET {set_clause} WHERE {where_clause}",
            job_config=bigquery.QueryJobConfig(query_parameters=params)
        ).result()
    except BadRequest as e:
        if "streaming buffer" in str(e):
            raise HTTPException(status_code=409, detail="Record is still in streaming buffer.")
        raise


def bq_delete(table: str, where: dict):
    """Run a parameterized DELETE. Raises 409 if the row is still in the streaming buffer."""
    where_clause = " AND ".join(f"{k} = @_w_{k}" for k in where)
    params = [bigquery.ScalarQueryParameter(f"_w_{k}", "STRING", v) for k, v in where.items()]
    try:
        bq_client.query(
            f"DELETE FROM {bq_table(table)} WHERE {where_clause}",
            job_config=bigquery.QueryJobConfig(query_parameters=params)
        ).result()
    except BadRequest as e:
        if "streaming buffer" in str(e):
            raise HTTPException(status_code=409, detail="Record is still in streaming buffer.")
        raise


def get_instance_id_or_404(table: str, id_col: str, id_val: str, detail: str = "Not found") -> str:
    """Look up instance_id for an entity, raising 404 if not found."""
    rows = list(bq_client.query(
        f"SELECT instance_id FROM {bq_table(table)} WHERE {id_col} = @id",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("id", "STRING", id_val)
        ])
    ).result())
    if not rows:
        raise HTTPException(status_code=404, detail=detail)
    return rows[0]["instance_id"]


def verify_token(token: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
    try:
        return auth.verify_id_token(token.credentials)
    except auth.ExpiredIdTokenError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except auth.InvalidIdTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except auth.UserNotFoundError:
        raise HTTPException(status_code=401, detail="User not found")
    except Exception:
        raise HTTPException(status_code=500, detail="Token verification failed unexpectedly")


def get_instance_id_for_uid(uid: str) -> str | None:
    rows = list(bq_client.query(
        f"SELECT instance_id FROM {bq_table('instances')} WHERE primary_contact_uid = @uid",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("uid", "STRING", uid)
        ])
    ).result())
    return rows[0]["instance_id"] if rows else None


def _is_instance_member(instance_id: str, uid: str) -> bool:
    """True if uid is the primary contact or linked in the users table for this instance."""
    rows = list(bq_client.query(
        f"SELECT 1 FROM {bq_table('instances')} WHERE instance_id = @instance_id AND primary_contact_uid = @uid "
        f"UNION ALL "
        f"SELECT 1 FROM {bq_table('users')} WHERE instance_id = @instance_id AND uid = @uid "
        f"LIMIT 1",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("instance_id", "STRING", instance_id),
            bigquery.ScalarQueryParameter("uid", "STRING", uid),
        ])
    ).result())
    return bool(rows)


def require_write_access(instance_id: str, caller: dict):
    """
    Grants write access to super_admins unconditionally.
    Admins must be associated with the instance.
    Viewers and unauthenticated roles are rejected.
    """
    role = caller.get("role")
    if role == "super_admin":
        return
    if role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    if not _is_instance_member(instance_id, caller["uid"]):
        raise HTTPException(status_code=403, detail="Access denied")


def require_read_access(instance_id: str, caller: dict):
    """
    Grants read access to super_admins unconditionally.
    Admins and viewers must be associated with the instance.
    """
    role = caller.get("role")
    if role == "super_admin":
        return
    if role not in ("admin", "viewer"):
        raise HTTPException(status_code=403, detail="Access denied")
    if not _is_instance_member(instance_id, caller["uid"]):
        raise HTTPException(status_code=403, detail="Access denied")
