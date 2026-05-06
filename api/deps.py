import json
import os

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import firebase_admin
from firebase_admin import credentials, auth
from google.cloud import bigquery
from sqlalchemy import select

from api.core.db import session_scope
from api.core.orm import ClinicAdmin, Instance
from api.core.secrets import get_secret

PROJECT = "project-demo-2-482101"
DATASET = "Users"

# BigQuery: uses Application Default Credentials (ADC)
bq_client = bigquery.Client(project=PROJECT)

# Firebase Admin: SA lives in Secret Manager (different GCP project — cortex-2b256)
_firebase_sa = json.loads(get_secret("firebase-admin-service-account"))
_cred = credentials.Certificate(_firebase_sa)
firebase_admin.initialize_app(_cred)

bearer_scheme = HTTPBearer()


def bq_table(table: str) -> str:
    """BigQuery table reference for SQL queries (backtick-quoted, fully qualified).

    Cloud SQL config tables are accessed via SQLAlchemy ORM (services/models.py).
    This helper is for the BQ tables that remain (voice_agent_tickets in Users,
    Blueprint_PHI dataset, ClinicData analytics tables)."""
    return f"`{PROJECT}.{DATASET}.{table}`"


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
    """Lookup the instance owned by the given Firebase uid. Reads Cloud SQL."""
    with session_scope() as db:
        return db.scalar(
            select(Instance.instance_id).where(Instance.primary_contact_uid == uid)
        )


def _is_instance_member(instance_id: str, uid: str) -> bool:
    """
    True if uid is the primary contact of the instance OR a clinic admin for it.

    Reads Cloud SQL. The clinic_admins table replaces the legacy BQ users table —
    same role, scoped to (uid, instance_id).
    """
    with session_scope() as db:
        is_primary = db.scalar(
            select(Instance.instance_id).where(
                Instance.instance_id == instance_id,
                Instance.primary_contact_uid == uid,
            )
        )
        if is_primary:
            return True
        return db.scalar(
            select(ClinicAdmin.id).where(
                ClinicAdmin.instance_id == instance_id,
                ClinicAdmin.uid == uid,
            )
        ) is not None


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
