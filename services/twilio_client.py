"""
Twilio phone number lifecycle management.

One Twilio number is provisioned per clinic when voice agent is activated.
Outbound calls from the VAPI agent use this number, optionally with the
clinic's primary number verified as the caller ID.

Credentials are read from Secret Manager:
    twilio-account-sid
    twilio-auth-token
"""
from twilio.rest import Client

from services.secrets import get_secret


def _get_client() -> Client:
    return Client(get_secret("twilio-account-sid"), get_secret("twilio-auth-token"))


def buy_phone_number(area_code: str, country_code: str) -> dict:
    """
    Purchase a local Twilio number for the given area code.

    country_code is required (no default) because the wrong country silently
    misroutes calls and triggers a paid Twilio purchase. Callers must pass the
    clinic's country (resolved via services.locale.resolve).

    Returns:
        {"sid": str, "phone_number": str}  — phone_number is in E.164 format
    Raises:
        ValueError if no numbers are available for the area code.
    """
    client = _get_client()
    available = getattr(
        client.available_phone_numbers(country_code), "local"
    ).list(area_code=area_code, limit=1)

    if not available:
        raise ValueError(
            f"No available {country_code} local numbers for area code {area_code}. "
            "Try a nearby area code or a toll-free number."
        )

    purchased = client.incoming_phone_numbers.create(
        phone_number=available[0].phone_number
    )
    return {"sid": purchased.sid, "phone_number": purchased.phone_number}


def release_phone_number(phone_sid: str) -> None:
    """
    Release a Twilio phone number back to the pool.

    Safe to call even if the number was never fully provisioned — Twilio
    returns 404 for unknown SIDs, which is caught and ignored here.
    """
    client = _get_client()
    try:
        client.incoming_phone_numbers(phone_sid).delete()
    except Exception:
        pass  # Already released or never existed


def initiate_caller_id_verification(phone_number: str) -> str:
    """
    Initiate Twilio outbound caller ID verification for a phone number.

    Twilio calls the number and reads a 6-digit code. The clinic staff must
    enter the code to complete verification.

    Returns:
        The validation_code the staff member must enter when Twilio calls.
    """
    client = _get_client()
    validation = client.validation_requests.create(
        phone_number=phone_number,
        friendly_name="Cortex Clinic Caller ID",
    )
    return validation.validation_code
