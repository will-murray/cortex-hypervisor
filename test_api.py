import requests
import uuid
import firebase_admin
from firebase_admin import credentials, auth
from dotenv import load_dotenv
import os

load_dotenv()
FIREBASE_WEB_API_KEY = os.getenv("FIREBASE_WEB_API_KEY")#"***REDACTED***"

_fb_app = None

def _get_fb_app():
    global _fb_app
    if _fb_app is None:
        cred = credentials.Certificate("secrets/cortex-2b256-firebase-adminsdk-fbsvc-b1e848b7fc.json")
        _fb_app = firebase_admin.initialize_app(cred, name="test")
    return _fb_app


def get_id_token(uid: str) -> str:
    """Mint a Firebase ID token for the given UID (test use only)."""
    app = _get_fb_app()
    custom_token = auth.create_custom_token(uid, app=app).decode("utf-8")
    resp = requests.post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key={FIREBASE_WEB_API_KEY}",
        json={"token": custom_token, "returnSecureToken": True},
    )
    resp.raise_for_status()
    return resp.json()["idToken"]


def auth_headers(uid: str) -> dict:
    return {"Authorization": f"Bearer {get_id_token(uid)}"}


wills_uid = "gHo5k1SHAZhdGjN7q5OXqMVf7522"


def provision_data(uid):
    instance_id = str(uuid.uuid4())
    return {
    "instance": {
        "instance_name": "John Pork's Hearing Wonderland",
        "invoca_id": "...",
        "google_ads_id": "...",
        "primary_contact_name": "Dr. John Pork",
        "primary_contact_uid": f"{uid}",
        "instance_id": f"{instance_id}"
    },
    "clinics": [
        {
        "clinic_name": "Test clinic 1",
        "address": "1450 Lonsdale Ave, North Vancouver, BC",
        "place_id": "ChIJN0northvan001",
        "about_us": "A multidisciplinary clinic offering physiotherapy, chiropractic, and sports medicine.",
        "hours_monday": "08:00-18:00",
        "hours_tuesday": "08:00-18:00",
        "hours_wednesday": "08:00-18:00",
        "hours_thursday": "08:00-18:00",
        "hours_friday": "08:00-17:00",
        "hours_saturday": "10:00-14:00",
        "hours_sunday": "Closed",
        "clinic_id": "clinic_cypress_nv_001",
        "instance_id": f"{instance_id}",
        "phone": "(604) 555-0101",
        "parking_info": "Free parking available at the rear of the building.",
        "accessibility_info": "Wheelchair accessible entrance on the north side.",
        "timezone": "America/Vancouver",
        "booking_system": "Acuity Scheduling",
        "transfer_number": "(604) 555-0102"
        },
        {
        "clinic_name": "Test clinic 2",
        "address": "4100 Kingsway, Burnaby, BC",
        "place_id": "ChIJBurnabyKingsway002",
        "about_us": "Integrated care with a focus on rehabilitation and preventative medicine.",
        "hours_monday": "09:00-17:00",
        "hours_tuesday": "09:00-17:00",
        "hours_wednesday": "09:00-17:00",
        "hours_thursday": "09:00-17:00",
        "hours_friday": "09:00-16:00",
        "hours_saturday": "Closed",
        "hours_sunday": "Closed",
        "clinic_id": "clinic_cypress_bby_002",
        "instance_id": f"{instance_id}",
        "phone": "(604) 555-0201",
        "parking_info": "Street parking available on Kingsway.",
        "accessibility_info": "Elevator access available. Wheelchair accessible.",
        "timezone": "America/Vancouver",
        "booking_system": "Acuity Scheduling",
        "transfer_number": "(604) 555-0202"
        }
    ],
    "staff": [
        {
        "name": "Dr. Lucas Chen",
        "title": "Chiropractor",
        "credentials": "DC",
        "clinic_id": "clinic_cypress_nv_001",
        "bio": "Specializes in spinal health, sports injuries, and long-term mobility optimization.",
        "years_experience": "7",
        "instance_id": f"{instance_id}"
        },
        {
        "name": "Sarah Mitchell",
        "title": "Physiotherapist",
        "credentials": "MPT",
        "clinic_id": "clinic_cypress_nv_001",
        "bio": "Focuses on post-operative rehab and athletic performance recovery.",
        "years_experience": "5",
        "instance_id": f"{instance_id}"
        },
        {
        "name": "Dr. Priya Nair",
        "title": "Sports Medicine Physician",
        "credentials": "MD, CCFP(SEM)",
        "clinic_id": "clinic_cypress_bby_002",
        "bio": "Experienced in musculoskeletal medicine and ultrasound-guided procedures.",
        "years_experience": "12",
        "instance_id": f"{instance_id}"
        }
    ],
    "services": [
        {
        "service_id": "svc_001",
        "service_name": "Comprehensive Hearing Evaluation",
        "description": "Full diagnostic hearing assessment for adults.",
        "duration_minutes": "60",
        "cost": "75.00",
        "insurance_covered": "Alberta Blue Cross, most employer benefits",
        "clinic_id": "clinic_cypress_nv_001",
        "instance_id": f"{instance_id}"
        }
    ],
    "insurance": [
        {
        "insurance_id": "ins_001",
        "plan_name": "Alberta Blue Cross",
        "provider_org": "Alberta Blue Cross",
        "notes": "Covers hearing evaluation in full under most plans.",
        "clinic_id": "clinic_cypress_nv_001",
        "instance_id": f"{instance_id}"
        },
        {
        "insurance_id": "ins_002",
        "plan_name": "AADL",
        "provider_org": "Alberta Aids to Daily Living",
        "notes": "Covers hearing aids and assistive devices.",
        "clinic_id": "clinic_cypress_nv_001",
        "instance_id": f"{instance_id}"
        }
    ]
    }


def test(uid):
    url = "http://localhost:8000/provision_account/"
    D = provision_data(uid)
    response = requests.post(url, headers=auth_headers(uid), json={
        "uid": uid,
        "instance": D["instance"],
        "staff": D["staff"],
        "clinics": D["clinics"],
        "services": D["services"],
        "insurance": D["insurance"]
    })
    print(response.status_code)
    print(response.json())
    return D["instance"]["instance_id"]


def test_delete(uid):
    response = requests.delete(
        f"http://localhost:8000/instance/{uid}",
        headers=auth_headers(uid)
    )
    print(response.status_code)
    print(response.json())



# test(real_uid)
# instance_id = test(real_uid)
test_delete(wills_uid)