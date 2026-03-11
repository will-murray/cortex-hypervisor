from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import firebase_admin
from firebase_admin import credentials, auth
from google.cloud import bigquery
from google.api_core.exceptions import BadRequest
from pydantic import BaseModel


class Instance(BaseModel):
    instance_name: str
    invoca_id: str
    google_ads_id: str
    primary_contact_name: str
    primary_contact_uid: str
    instance_id: str


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
    instance: Instance
    staff: List[Staff]
    clinics: List[Clinic]
    services: Optional[List[Service]] = []
    insurance: Optional[List[Insurance]] = []


bq_client = bigquery.Client.from_service_account_json(json_credentials_path="secrets/project-demo-2-482101-7c1c68a849ba.json")

cred = credentials.Certificate("secrets/cortex-2b256-firebase-service_account.json")
fb_app = firebase_admin.initialize_app(cred)
app = FastAPI()

bearer_scheme = HTTPBearer()

PROJECT = "project-demo-2-482101"
DATASET = "Users"


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


@app.get("/")
def hello():
    return {"message": "This is "}


# --- Instance ---

@app.post("/provision_account/")
def provision_account(payload: ProvisionRequest, caller: dict = Depends(verify_token)):
    uid = payload.uid
    instance = payload.instance

    if get_instance_id_for_uid(uid):
        return {"status": "error", "message": f"{uid} already has an instance provisioned"}

    errors = bq_client.insert_rows_json(bq_table("instances"), [instance.model_dump()])
    if errors:
        return {"status": "error", "message": "Failed to insert instance", "errors": errors}

    errors = bq_client.insert_rows_json(bq_table("clinics"), [c.model_dump() for c in payload.clinics])
    if errors:
        return {"status": "error", "message": "Failed to insert clinics", "errors": errors}

    errors = bq_client.insert_rows_json(bq_table("staff"), [s.model_dump() for s in payload.staff])
    if errors:
        return {"status": "error", "message": "Failed to insert staff", "errors": errors}

    if payload.services:
        errors = bq_client.insert_rows_json(bq_table("services"), [s.model_dump() for s in payload.services])
        if errors:
            return {"status": "error", "message": "Failed to insert services", "errors": errors}

    if payload.insurance:
        errors = bq_client.insert_rows_json(bq_table("insurance"), [i.model_dump() for i in payload.insurance])
        if errors:
            return {"status": "error", "message": "Failed to insert insurance", "errors": errors}

    return {"status": "success", "message": "Instance provisioned"}


@app.get("/instance/{uid}")
def get_instance(uid: str, caller: dict = Depends(verify_token)):
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
    instance_id = get_instance_id_for_uid(uid)
    if not instance_id:
        raise HTTPException(status_code=404, detail=f"No instance found for uid {uid}")

    tables = ["services", "insurance", "staff", "users", "clinics", "instances"]
    try:
        for table in tables:
            bq_client.query(
                f"DELETE FROM {bq_table(table)} WHERE instance_id = @instance_id",
                job_config=bigquery.QueryJobConfig(query_parameters=[
                    bigquery.ScalarQueryParameter("instance_id", "STRING", instance_id)
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


# --- Clinics ---

@app.get("/clinics/{instance_id}")
def get_clinics(instance_id: str, caller: dict = Depends(verify_token)):
    rows = list(bq_client.query(
        f"SELECT * FROM {bq_table('clinics')} WHERE instance_id = @instance_id",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("instance_id", "STRING", instance_id)
        ])
    ).result())
    return [dict(r) for r in rows]


@app.post("/clinics/")
def add_clinic(clinic: Clinic, caller: dict = Depends(verify_token)):
    errors = bq_client.insert_rows_json(bq_table("clinics"), [clinic.model_dump()])
    if errors:
        return {"status": "error", "errors": errors}
    return {"status": "success"}


@app.delete("/clinics/{clinic_id}")
def delete_clinic(clinic_id: str, caller: dict = Depends(verify_token)):
    try:
        bq_client.query(
            f"DELETE FROM {bq_table('clinics')} WHERE clinic_id = @clinic_id",
            job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("clinic_id", "STRING", clinic_id)
            ])
        ).result()
    except BadRequest as e:
        if "streaming buffer" in str(e):
            return JSONResponse(status_code=409, content={"status": "error", "message": "Record is still in streaming buffer."})
        raise
    return {"status": "success"}


# --- Staff ---

@app.get("/staff/{instance_id}")
def get_staff(instance_id: str, caller: dict = Depends(verify_token)):
    rows = list(bq_client.query(
        f"SELECT * FROM {bq_table('staff')} WHERE instance_id = @instance_id",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("instance_id", "STRING", instance_id)
        ])
    ).result())
    return [dict(r) for r in rows]


@app.post("/staff/")
def add_staff(staff: Staff, caller: dict = Depends(verify_token)):
    errors = bq_client.insert_rows_json(bq_table("staff"), [staff.model_dump()])
    if errors:
        return {"status": "error", "errors": errors}
    return {"status": "success"}


@app.delete("/staff/{instance_id}/{clinic_id}/{name}")
def delete_staff(instance_id: str, clinic_id: str, name: str, caller: dict = Depends(verify_token)):
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


# --- Services ---

@app.get("/services/{instance_id}")
def get_services(instance_id: str, caller: dict = Depends(verify_token)):
    rows = list(bq_client.query(
        f"SELECT * FROM {bq_table('services')} WHERE instance_id = @instance_id",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("instance_id", "STRING", instance_id)
        ])
    ).result())
    return [dict(r) for r in rows]


@app.post("/services/")
def add_service(service: Service, caller: dict = Depends(verify_token)):
    errors = bq_client.insert_rows_json(bq_table("services"), [service.model_dump()])
    if errors:
        return {"status": "error", "errors": errors}
    return {"status": "success"}


@app.delete("/services/{service_id}")
def delete_service(service_id: str, caller: dict = Depends(verify_token)):
    try:
        bq_client.query(
            f"DELETE FROM {bq_table('services')} WHERE service_id = @service_id",
            job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("service_id", "STRING", service_id)
            ])
        ).result()
    except BadRequest as e:
        if "streaming buffer" in str(e):
            return JSONResponse(status_code=409, content={"status": "error", "message": "Record is still in streaming buffer."})
        raise
    return {"status": "success"}


# --- Insurance ---

@app.get("/insurance/{instance_id}")
def get_insurance(instance_id: str, caller: dict = Depends(verify_token)):
    rows = list(bq_client.query(
        f"SELECT * FROM {bq_table('insurance')} WHERE instance_id = @instance_id",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("instance_id", "STRING", instance_id)
        ])
    ).result())
    return [dict(r) for r in rows]


@app.post("/insurance/")
def add_insurance(insurance: Insurance, caller: dict = Depends(verify_token)):
    errors = bq_client.insert_rows_json(bq_table("insurance"), [insurance.model_dump()])
    if errors:
        return {"status": "error", "errors": errors}
    return {"status": "success"}


@app.delete("/insurance/{insurance_id}")
def delete_insurance(insurance_id: str, caller: dict = Depends(verify_token)):
    try:
        bq_client.query(
            f"DELETE FROM {bq_table('insurance')} WHERE insurance_id = @insurance_id",
            job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("insurance_id", "STRING", insurance_id)
            ])
        ).result()
    except BadRequest as e:
        if "streaming buffer" in str(e):
            return JSONResponse(status_code=409, content={"status": "error", "message": "Record is still in streaming buffer."})
        raise
    return {"status": "success"}


# --- Users ---

@app.get("/users/{instance_id}")
def get_users(instance_id: str, caller: dict = Depends(verify_token)):
    rows = list(bq_client.query(
        f"SELECT * FROM {bq_table('users')} WHERE instance_id = @instance_id",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("instance_id", "STRING", instance_id)
        ])
    ).result())
    return [dict(r) for r in rows]


@app.post("/users/")
def add_user(user: User, caller: dict = Depends(verify_token)):
    errors = bq_client.insert_rows_json(bq_table("users"), [user.model_dump()])
    if errors:
        return {"status": "error", "errors": errors}
    return {"status": "success"}


@app.delete("/users/{uid}")
def delete_user(uid: str, caller: dict = Depends(verify_token)):
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


# uids =["gHo5k1SHAZhdGjN7q5OXqMVf7522", "vTKkDhXSrWO6WCboJWf1zS8Y8Xs1", "FC0mXe9S4JduGYvqVzl6z0QqNfz1", "5dmZ6cdWosS46jRVLRba1P8A4th1"]


def reset_user(uid):
    auth.set_custom_user_claims("gHo5k1SHAZhdGjN7q5OXqMVf7522", None)
