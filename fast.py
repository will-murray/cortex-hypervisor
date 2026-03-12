from typing import List, Optional
import uuid
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import firebase_admin
from firebase_admin import credentials, auth
from google.cloud import bigquery
from google.api_core.exceptions import BadRequest
from pydantic import BaseModel
from dotenv import load_dotenv
from services.provisioning import provision_full_account, provision_clinic
import json
import os

load_dotenv()

# --- Request Models (what client sends) ---

class InstanceCreate(BaseModel):
    instance_name: str
    primary_contact_name: str


class ClinicCreate(BaseModel):
    ref_id: Optional[str] = None  # For linking staff/services/insurance during provisioning
    clinic_name: str
    address: str
    place_id: str
    about_us: str
    hours_monday: str
    hours_tuesday: str
    hours_wednesday: str
    hours_thursday: str
    hours_friday: str
    hours_saturday: str
    hours_sunday: str
    phone: str
    parking_info: str
    accessibility_info: str
    timezone: str
    booking_system: str
    transfer_number: str


# --- Storage Models (what gets saved to BigQuery) ---

class Instance(BaseModel):
    instance_name: str
    primary_contact_name: str
    primary_contact_uid: str
    instance_id: str
    # Google Ads (created during provisioning)
    google_ads_customer_id: str
    google_ads_campaign_id: str
    # Invoca (created during provisioning)
    invoca_profile_id: str


class Clinic(BaseModel):
    clinic_name: str
    address: str
    place_id: str
    about_us: str
    hours_monday: str
    hours_tuesday: str
    hours_wednesday: str
    hours_thursday: str
    hours_friday: str
    hours_saturday: str
    hours_sunday: str
    clinic_id: str
    instance_id: str
    phone: str
    parking_info: str
    accessibility_info: str
    timezone: str
    booking_system: str
    transfer_number: str
    # Google Ads (created during provisioning)
    google_ads_ad_group_id: str
    # Invoca (created during provisioning)
    invoca_campaign_id: str


class Service(BaseModel):
    service_id: str
    service_name: str
    description: str
    duration_minutes: str
    cost: str
    insurance_covered: str
    clinic_id: str
    instance_id: str


class Insurance(BaseModel):
    insurance_id: str
    plan_name: str
    provider_org: str
    notes: str
    clinic_id: str
    instance_id: str


class Staff(BaseModel):
    name: str
    title: str
    credentials: str
    clinic_id: str
    bio: str
    years_experience: str
    instance_id: str


class User(BaseModel):
    uid: str
    name: str
    instance_id: str
    access_level: str


class ProvisionRequest(BaseModel):
    uid: str
    instance: InstanceCreate
    staff: List[Staff]
    clinics: List[ClinicCreate]
    services: Optional[List[Service]] = []
    insurance: Optional[List[Insurance]] = []



bq_client = bigquery.Client.from_service_account_info(json.loads(os.environ["GCS_SERVICE_ACCOUNT"]))
cred = credentials.Certificate(json.loads(os.environ["FIREBASE_ADMIN_SERVICE_ACCOUNT"]))

fb_app = firebase_admin.initialize_app(cred)
app = FastAPI()

bearer_scheme = HTTPBearer()

PROJECT = os.environ["GCP_PROJECT"]
DATASET = os.environ["BQ_DATASET"]
INVOCA_NETWORK_ID = os.environ.get("INVOCA_NETWORK_ID", "")  # Optional until implemented


def bq_table(table: str) -> str:
    return f"`{PROJECT}.{DATASET}.{table}`"


def verify_token(token: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
    try:
        return auth.verify_id_token(token.credentials)
    except auth.ExpiredIdTokenError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except auth.InvalidIdTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception:
        raise HTTPException(status_code=401, detail="Could not validate credentials")


def get_instance_id_for_uid(uid: str) -> str | None:
    rows = list(bq_client.query(
        f"SELECT instance_id FROM {bq_table('instances')} WHERE primary_contact_uid = @uid",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("uid", "STRING", uid)
        ])
    ).result())
    return rows[0]["instance_id"] if rows else None


def require_instance_owner(instance_id: str, caller_uid: str):
    rows = list(bq_client.query(
        f"SELECT primary_contact_uid FROM {bq_table('instances')} WHERE instance_id = @instance_id",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("instance_id", "STRING", instance_id)
        ])
    ).result())
    if not rows:
        raise HTTPException(status_code=404, detail="Instance not found")
    if rows[0]["primary_contact_uid"] != caller_uid:
        raise HTTPException(status_code=403, detail="Access denied")


def get_instance_external_ids(instance_id: str) -> dict | None:
    """Fetch the external service IDs for an instance."""
    rows = list(bq_client.query(
        f"SELECT google_ads_customer_id, google_ads_campaign_id, invoca_profile_id "
        f"FROM {bq_table('instances')} WHERE instance_id = @instance_id",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("instance_id", "STRING", instance_id)
        ])
    ).result())
    return dict(rows[0]) if rows else None


@app.get("/")
def hello():
    return {"message": "This is "}


# --- Instance ---

@app.post("/provision_account/")
def provision_account(payload: ProvisionRequest, caller: dict = Depends(verify_token)):
    if payload.uid != caller["uid"]:
        raise HTTPException(status_code=403, detail="Cannot provision for another user")

    uid = caller["uid"]

    if get_instance_id_for_uid(uid):
        return {"status": "error", "message": f"{uid} already has an instance provisioned"}

    # Provision instance and clinics with external services (Google Ads, Invoca)
    result = provision_full_account(
        instance_create=payload.instance.model_dump(),
        clinics_create=[c.model_dump() for c in payload.clinics],
        primary_contact_uid=uid,
        invoca_network_id=INVOCA_NETWORK_ID,
    )

    instance = result["instance"]
    clinics = result["clinics"]
    clinic_id_map = result["clinic_id_map"]  # ref_id -> clinic_id
    instance_id = instance["instance_id"]

    # Update staff, services, insurance with generated IDs
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

    # Insert into BigQuery
    errors = bq_client.insert_rows_json(bq_table("instances"), [instance])
    if errors:
        return {"status": "error", "message": "Failed to insert instance", "errors": errors}

    errors = bq_client.insert_rows_json(bq_table("clinics"), clinics)
    if errors:
        return {"status": "error", "message": "Failed to insert clinics", "errors": errors}

    errors = bq_client.insert_rows_json(bq_table("staff"), [s.model_dump() for s in staff])
    if errors:
        return {"status": "error", "message": "Failed to insert staff", "errors": errors}

    if services:
        errors = bq_client.insert_rows_json(bq_table("services"), [s.model_dump() for s in services])
        if errors:
            return {"status": "error", "message": "Failed to insert services", "errors": errors}

    if insurance:
        errors = bq_client.insert_rows_json(bq_table("insurance"), [i.model_dump() for i in insurance])
        if errors:
            return {"status": "error", "message": "Failed to insert insurance", "errors": errors}

    return {
        "status": "success",
        "message": "Instance provisioned",
        "instance_id": instance_id,
        "clinic_ids": clinic_id_map,
    }


@app.get("/instance/{uid}")
def get_instance(uid: str, caller: dict = Depends(verify_token)):
    if caller["uid"] != uid:
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


@app.delete("/instance/{uid}")
def delete_instance(uid: str, caller: dict = Depends(verify_token)):
    if caller["uid"] != uid:
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
        # Delete by primary_contact_uid to catch any duplicate instance rows
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



@app.get("/clinics/{instance_id}")
def get_clinics(instance_id: str, caller: dict = Depends(verify_token)):
    require_instance_owner(instance_id, caller["uid"])
    rows = list(bq_client.query(
        f"SELECT * FROM {bq_table('clinics')} WHERE instance_id = @instance_id",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("instance_id", "STRING", instance_id)
        ])
    ).result())
    return [dict(r) for r in rows]


@app.post("/clinics/{instance_id}")
def add_clinic(instance_id: str, clinic: ClinicCreate, caller: dict = Depends(verify_token)):
    require_instance_owner(instance_id, caller["uid"])

    # Get instance's external service IDs
    external_ids = get_instance_external_ids(instance_id)
    if not external_ids:
        raise HTTPException(status_code=404, detail="Instance not found")

    # Provision external services for the clinic
    clinic_data, _, clinic_id = provision_clinic(
        clinic_data=clinic.model_dump(),
        instance_id=instance_id,
        google_ads_customer_id=external_ids["google_ads_customer_id"],
        google_ads_campaign_id=external_ids["google_ads_campaign_id"],
        invoca_profile_id=external_ids["invoca_profile_id"],
    )

    errors = bq_client.insert_rows_json(bq_table("clinics"), [clinic_data])
    if errors:
        return {"status": "error", "errors": errors}
    return {"status": "success", "clinic_id": clinic_id}


@app.delete("/clinics/{clinic_id}")
def delete_clinic(clinic_id: str, caller: dict = Depends(verify_token)):
    try:
        bq_client.query(
            f"DELETE FROM {bq_table('clinics')} WHERE clinic_id = @clinic_id "
            f"AND instance_id IN (SELECT instance_id FROM {bq_table('instances')} WHERE primary_contact_uid = @uid)",
            job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("clinic_id", "STRING", clinic_id),
                bigquery.ScalarQueryParameter("uid", "STRING", caller["uid"]),
            ])
        ).result()
    except BadRequest as e:
        if "streaming buffer" in str(e):
            return JSONResponse(status_code=409, content={"status": "error", "message": "Record is still in streaming buffer."})
        raise
    return {"status": "success"}



@app.get("/staff/{instance_id}")
def get_staff(instance_id: str, caller: dict = Depends(verify_token)):
    require_instance_owner(instance_id, caller["uid"])
    rows = list(bq_client.query(
        f"SELECT * FROM {bq_table('staff')} WHERE instance_id = @instance_id",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("instance_id", "STRING", instance_id)
        ])
    ).result())
    return [dict(r) for r in rows]


@app.post("/staff/")
def add_staff(staff: Staff, caller: dict = Depends(verify_token)):
    require_instance_owner(staff.instance_id, caller["uid"])
    errors = bq_client.insert_rows_json(bq_table("staff"), [staff.model_dump()])
    if errors:
        return {"status": "error", "errors": errors}
    return {"status": "success"}


@app.delete("/staff/{instance_id}/{clinic_id}/{name}")
def delete_staff(instance_id: str, clinic_id: str, name: str, caller: dict = Depends(verify_token)):
    require_instance_owner(instance_id, caller["uid"])
    try:
        bq_client.query(
            f"DELETE FROM {bq_table('staff')} WHERE instance_id = @instance_id AND clinic_id = @clinic_id AND name = @name",
            job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("instance_id", "STRING", instance_id),
                bigquery.ScalarQueryParameter("clinic_id", "STRING", clinic_id),
                bigquery.ScalarQueryParameter("name", "STRING", name),
            ])
        ).result()
    except BadRequest as e:
        if "streaming buffer" in str(e):
            return JSONResponse(status_code=409, content={"status": "error", "message": "Record is still in streaming buffer."})
        raise
    return {"status": "success"}



@app.get("/services/{instance_id}")
def get_services(instance_id: str, caller: dict = Depends(verify_token)):
    require_instance_owner(instance_id, caller["uid"])
    rows = list(bq_client.query(
        f"SELECT * FROM {bq_table('services')} WHERE instance_id = @instance_id",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("instance_id", "STRING", instance_id)
        ])
    ).result())
    return [dict(r) for r in rows]


@app.post("/services/")
def add_service(service: Service, caller: dict = Depends(verify_token)):
    require_instance_owner(service.instance_id, caller["uid"])
    service = service.model_copy(update={"service_id": str(uuid.uuid4())})
    errors = bq_client.insert_rows_json(bq_table("services"), [service.model_dump()])
    if errors:
        return {"status": "error", "errors": errors}
    return {"status": "success", "service_id": service.service_id}


@app.delete("/services/{service_id}")
def delete_service(service_id: str, caller: dict = Depends(verify_token)):
    try:
        bq_client.query(
            f"DELETE FROM {bq_table('services')} WHERE service_id = @service_id "
            f"AND instance_id IN (SELECT instance_id FROM {bq_table('instances')} WHERE primary_contact_uid = @uid)",
            job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("service_id", "STRING", service_id),
                bigquery.ScalarQueryParameter("uid", "STRING", caller["uid"]),
            ])
        ).result()
    except BadRequest as e:
        if "streaming buffer" in str(e):
            return JSONResponse(status_code=409, content={"status": "error", "message": "Record is still in streaming buffer."})
        raise
    return {"status": "success"}



@app.get("/insurance/{instance_id}")
def get_insurance(instance_id: str, caller: dict = Depends(verify_token)):
    require_instance_owner(instance_id, caller["uid"])
    rows = list(bq_client.query(
        f"SELECT * FROM {bq_table('insurance')} WHERE instance_id = @instance_id",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("instance_id", "STRING", instance_id)
        ])
    ).result())
    return [dict(r) for r in rows]


@app.post("/insurance/")
def add_insurance(insurance: Insurance, caller: dict = Depends(verify_token)):
    require_instance_owner(insurance.instance_id, caller["uid"])
    insurance = insurance.model_copy(update={"insurance_id": str(uuid.uuid4())})
    errors = bq_client.insert_rows_json(bq_table("insurance"), [insurance.model_dump()])
    if errors:
        return {"status": "error", "errors": errors}
    return {"status": "success", "insurance_id": insurance.insurance_id}


@app.delete("/insurance/{insurance_id}")
def delete_insurance(insurance_id: str, caller: dict = Depends(verify_token)):
    try:
        bq_client.query(
            f"DELETE FROM {bq_table('insurance')} WHERE insurance_id = @insurance_id "
            f"AND instance_id IN (SELECT instance_id FROM {bq_table('instances')} WHERE primary_contact_uid = @uid)",
            job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("insurance_id", "STRING", insurance_id),
                bigquery.ScalarQueryParameter("uid", "STRING", caller["uid"]),
            ])
        ).result()
    except BadRequest as e:
        if "streaming buffer" in str(e):
            return JSONResponse(status_code=409, content={"status": "error", "message": "Record is still in streaming buffer."})
        raise
    return {"status": "success"}



@app.get("/users/{instance_id}")
def get_users(instance_id: str, caller: dict = Depends(verify_token)):
    require_instance_owner(instance_id, caller["uid"])
    rows = list(bq_client.query(
        f"SELECT * FROM {bq_table('users')} WHERE instance_id = @instance_id",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("instance_id", "STRING", instance_id)
        ])
    ).result())
    return [dict(r) for r in rows]


@app.post("/users/")
def add_user(user: User, caller: dict = Depends(verify_token)):
    require_instance_owner(user.instance_id, caller["uid"])
    errors = bq_client.insert_rows_json(bq_table("users"), [user.model_dump()])
    if errors:
        return {"status": "error", "errors": errors}
    return {"status": "success"}


@app.delete("/users/{uid}")
def delete_user(uid: str, caller: dict = Depends(verify_token)):
    # Allow self-deletion or deletion by the instance owner
    if caller["uid"] != uid:
        rows = list(bq_client.query(
            f"SELECT instance_id FROM {bq_table('users')} WHERE uid = @uid",
            job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("uid", "STRING", uid)
            ])
        ).result())
        if not rows:
            raise HTTPException(status_code=404, detail="User not found")
        require_instance_owner(rows[0]["instance_id"], caller["uid"])
    try:
        bq_client.query(
            f"DELETE FROM {bq_table('users')} WHERE uid = @uid",
            job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("uid", "STRING", uid)
            ])
        ).result()
    except BadRequest as e:
        if "streaming buffer" in str(e):
            return JSONResponse(status_code=409, content={"status": "error", "message": "Record is still in streaming buffer."})
        raise
    return {"status": "success"}


def reset_user(uid):
    auth.set_custom_user_claims(uid, None)
