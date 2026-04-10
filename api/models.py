from typing import List, Literal, Optional
from pydantic import BaseModel, field_validator


def _require_non_empty(v: str, field_name: str) -> str:
    if not v or not v.strip():
        raise ValueError(f"{field_name} is required and cannot be empty")
    return v.strip()


def _reject_empty_string(v: Optional[str]) -> Optional[str]:
    if v is not None and not v.strip():
        raise ValueError("Field cannot be an empty string")
    return v.strip() if v is not None else v


# --- Create Models ---

class InstanceCreate(BaseModel):
    instance_name: str
    primary_contact_name: str
    primary_contact_email: str

    @field_validator("instance_name")
    @classmethod
    def validate_instance_name(cls, v):
        return _require_non_empty(v, "instance_name")

    @field_validator("primary_contact_name")
    @classmethod
    def validate_primary_contact_name(cls, v):
        return _require_non_empty(v, "primary_contact_name")

    @field_validator("primary_contact_email")
    @classmethod
    def validate_primary_contact_email(cls, v):
        return _require_non_empty(v, "primary_contact_email")


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

    @field_validator("clinic_name")
    @classmethod
    def validate_clinic_name(cls, v):
        return _require_non_empty(v, "clinic_name")

    @field_validator("address")
    @classmethod
    def validate_address(cls, v):
        return _require_non_empty(v, "address")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        return _require_non_empty(v, "phone")


# --- Update Models (all fields optional, immutable fields excluded) ---

class InstanceUpdate(BaseModel):
    primary_contact_name: Optional[str] = None
    primary_contact_email: Optional[str] = None
    google_ads_customer_id: Optional[str] = None
    invoca_profile_id: Optional[str] = None

    @field_validator("primary_contact_name", "primary_contact_email", "google_ads_customer_id", "invoca_profile_id")
    @classmethod
    def validate_fields(cls, v):
        return _reject_empty_string(v)


class ClinicUpdate(BaseModel):
    address: Optional[str] = None
    place_id: Optional[str] = None
    about_us: Optional[str] = None
    hours_monday: Optional[str] = None
    hours_tuesday: Optional[str] = None
    hours_wednesday: Optional[str] = None
    hours_thursday: Optional[str] = None
    hours_friday: Optional[str] = None
    hours_saturday: Optional[str] = None
    hours_sunday: Optional[str] = None
    phone: Optional[str] = None
    parking_info: Optional[str] = None
    accessibility_info: Optional[str] = None
    timezone: Optional[str] = None
    booking_system: Optional[str] = None
    transfer_number: Optional[str] = None
    google_ads_campaign_id: Optional[str] = None
    invoca_campaign_id: Optional[str] = None
    gbp_location_id: Optional[str] = None

    @field_validator("address", "phone", "google_ads_campaign_id", "invoca_campaign_id",
                     "place_id", "about_us", "timezone", "booking_system", "transfer_number",
                     "hours_monday", "hours_tuesday", "hours_wednesday", "hours_thursday",
                     "hours_friday", "hours_saturday", "hours_sunday",
                     "parking_info", "accessibility_info", "gbp_location_id")
    @classmethod
    def validate_fields(cls, v):
        return _reject_empty_string(v)


class StaffUpdate(BaseModel):
    title: Optional[str] = None
    credentials: Optional[str] = None
    bio: Optional[str] = None
    years_experience: Optional[str] = None

    @field_validator("title", "credentials", "bio", "years_experience")
    @classmethod
    def validate_fields(cls, v):
        return _reject_empty_string(v)


class ServiceUpdate(BaseModel):
    service_name: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[str] = None
    cost: Optional[str] = None
    insurance_covered: Optional[str] = None

    @field_validator("service_name", "description", "duration_minutes", "cost", "insurance_covered")
    @classmethod
    def validate_fields(cls, v):
        return _reject_empty_string(v)

    @field_validator("service_name")
    @classmethod
    def validate_service_name(cls, v):
        if v is not None:
            return _require_non_empty(v, "service_name")
        return v


class InsuranceUpdate(BaseModel):
    plan_name: Optional[str] = None
    provider_org: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("plan_name", "provider_org", "notes")
    @classmethod
    def validate_fields(cls, v):
        return _reject_empty_string(v)


# --- Storage Models ---

class Instance(BaseModel):
    instance_name: str
    primary_contact_name: str
    primary_contact_email: str
    primary_contact_uid: str
    instance_id: str
    google_ads_customer_id: Optional[str] = None
    invoca_profile_id: Optional[str] = None


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
    google_ads_campaign_id: Optional[str] = None
    invoca_campaign_id: Optional[str] = None
    gbp_location_id: Optional[str] = None
    # Voice agent — managed by /clinics/{clinic_id}/voice_agent/* routes
    voice_agent_status: str = "inactive"  # inactive | provisioning | active | error
    twilio_phone_number: Optional[str] = None
    twilio_phone_sid: Optional[str] = None
    twilio_verified_caller_id: bool = False
    vapi_assistant_id: Optional[str] = None
    vapi_phone_number_id: Optional[str] = None
    # PMS — managed by /clinics/{clinic_id}/pms routes (api_key excluded — write-only)
    pms_type: str = "none"  # none | blueprint
    blueprint_server: Optional[str] = None
    blueprint_clinic_slug: Optional[str] = None
    blueprint_location_id: Optional[int] = None
    blueprint_user_id: Optional[int] = None


class Service(BaseModel):
    service_id: str
    service_name: str
    description: str
    duration_minutes: str
    cost: str
    insurance_covered: str
    clinic_id: str
    instance_id: str

    @field_validator("service_name")
    @classmethod
    def validate_service_name(cls, v):
        return _require_non_empty(v, "service_name")


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

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        return _require_non_empty(v, "name")


class User(BaseModel):
    uid: str
    name: str
    instance_id: str


class AppointmentType(BaseModel):
    appointment_type_id: str
    appointment_name: str
    duration: Optional[str] = None
    price: Optional[str] = None
    description: Optional[str] = None
    clinic_id: str
    clinic_name: str
    instance_id: str

    @field_validator("appointment_name")
    @classmethod
    def validate_appointment_name(cls, v):
        return _require_non_empty(v, "appointment_name")


class AppointmentTypeUpdate(BaseModel):
    appointment_name: Optional[str] = None
    duration: Optional[str] = None
    price: Optional[str] = None
    description: Optional[str] = None

    @field_validator("appointment_name", "duration", "price", "description")
    @classmethod
    def validate_fields(cls, v):
        return _reject_empty_string(v)

    @field_validator("appointment_name")
    @classmethod
    def validate_appointment_name(cls, v):
        if v is not None:
            return _require_non_empty(v, "appointment_name")
        return v


class ProvisionRequest(BaseModel):
    uid: str
    instance: InstanceCreate
    staff: List[Staff]
    clinics: List[ClinicCreate]
    services: Optional[List[Service]] = []
    insurance: Optional[List[Insurance]] = []


# --- Phase 2: Review Snapshots ---

class ReviewSnapshot(BaseModel):
    instance_id: str
    clinic_id: str
    snapshot_date: str   # YYYY-MM-DD
    review_count: int
    avg_rating: float

    @field_validator("instance_id", "clinic_id", "snapshot_date")
    @classmethod
    def validate_required(cls, v, info):
        return _require_non_empty(v, info.field_name)


# --- Phase 3: Blueprint / EMR Integration ---

class PatientCreate(BaseModel):
    patient_id: str       # Blueprint patient ID
    instance_id: str
    clinic_id: str
    first_seen_date: Optional[str] = None   # YYYY-MM-DD
    status: Optional[str] = None            # active | lapsed | tested-not-sold | deceased
    source: Optional[str] = None            # physician-referral | walk-in | ad | database | unknown
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    phone: Optional[str] = None

    @field_validator("patient_id", "instance_id", "clinic_id")
    @classmethod
    def validate_required(cls, v):
        return _require_non_empty(v, "field")


class AppointmentCreate(BaseModel):
    appointment_id: str
    patient_id: str
    instance_id: str
    clinic_id: str
    scheduled_at: Optional[str] = None      # ISO datetime string
    appointment_type: Optional[str] = None  # hearing-test | fitting | follow-up | repair | other
    outcome: Optional[str] = None           # attended | no-show | cancelled | rescheduled
    provider: Optional[str] = None
    referral_source: Optional[str] = None   # physician name or source label

    @field_validator("appointment_id", "patient_id", "instance_id", "clinic_id")
    @classmethod
    def validate_required(cls, v):
        return _require_non_empty(v, "field")


class InvoiceCreate(BaseModel):
    invoice_id: str
    patient_id: str
    instance_id: str
    clinic_id: str
    invoice_date: Optional[str] = None      # YYYY-MM-DD
    amount: Optional[float] = None
    product_category: Optional[str] = None  # hearing-aid | accessory | service | other
    hearing_aid_tier: Optional[str] = None  # economy | mid | premium | ultra-premium

    @field_validator("invoice_id", "patient_id", "instance_id", "clinic_id")
    @classmethod
    def validate_required(cls, v):
        return _require_non_empty(v, "field")


class PhysicianReferralCreate(BaseModel):
    referral_id: str
    patient_id: str
    instance_id: str
    clinic_id: str
    referring_physician: Optional[str] = None
    practice_name: Optional[str] = None
    referral_date: Optional[str] = None     # YYYY-MM-DD
    converted: Optional[bool] = None        # Did the referral result in a sale?

    @field_validator("referral_id", "patient_id", "instance_id", "clinic_id")
    @classmethod
    def validate_required(cls, v):
        return _require_non_empty(v, "field")


# --- Campaigns (multi-campaign per clinic) ---

class ClinicCampaignCreate(BaseModel):
    campaign_type: Literal["google_ads", "invoca"]
    external_campaign_id: str
    campaign_name: Optional[str] = None

    @field_validator("external_campaign_id")
    @classmethod
    def validate_external_id(cls, v):
        return _require_non_empty(v, "external_campaign_id")


class ClinicCampaign(BaseModel):
    id: str
    clinic_id: str
    instance_id: str
    campaign_type: str
    external_campaign_id: str
    campaign_name: Optional[str] = None


# --- PMS Config ---

class PmsConfigSet(BaseModel):
    """
    Sets the PMS configuration for a clinic. blueprint_api_key is write-only
    and is never returned in GET responses.
    """
    pms_type: Literal["none", "blueprint"]
    blueprint_server: Optional[str] = None       # e.g. "wp2.bp-solutions.net:8443"
    blueprint_clinic_slug: Optional[str] = None  # [CLINIC] path segment in Blueprint URLs
    blueprint_api_key: Optional[str] = None      # stored in BQ, never returned
    blueprint_location_id: Optional[int] = None  # numeric location ID
    blueprint_user_id: Optional[int] = None      # service account user for API writes
