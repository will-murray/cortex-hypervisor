"""
VAPI server SDK wrapper.

Uses the ``vapi_server_sdk`` package (imports as ``vapi``). Exposes the small
surface the activate / deactivate flows need:

  - ``import_twilio_number``  — register a purchased Twilio number with VAPI
  - ``create_assistant``      — create a VAPI assistant from a config dict
  - ``delete_assistant``      — remove an assistant
  - ``release_phone_number``  — remove a VAPI phone-number record (does NOT
                                release the Twilio number itself; that's
                                ``api.voice_agent.twilio.release_phone_number``)

The VAPI API key is read from Secret Manager once and cached in a module-level
client. Twilio account credentials are also pulled from SM and forwarded to
VAPI when importing a number.
"""
from __future__ import annotations

from functools import lru_cache

from vapi import Vapi

from api.core.secrets import get_secret


@lru_cache(maxsize=1)
def _client() -> Vapi:
    return Vapi(token=get_secret("vapi-api-key"))


def import_twilio_number(twilio_phone_number: str, twilio_phone_sid: str) -> str:
    """
    Register a Twilio number with VAPI so VAPI can route incoming calls to an
    assistant. Returns the VAPI phone-number id (used later when creating /
    updating an assistant or releasing the registration).

    Twilio account credentials come from SM (``twilio-account-sid``,
    ``twilio-auth-token``).
    """
    resp = _client().phone_numbers.create(
        provider="twilio",
        number=twilio_phone_number,
        twilio_account_sid=get_secret("twilio-account-sid"),
        twilio_auth_token=get_secret("twilio-auth-token"),
    )
    # SDK returns a typed object; the id attribute is the VAPI phone-number UUID.
    return resp.id


def create_assistant(config: dict) -> str:
    """
    Create a VAPI assistant from the dict produced by
    ``api.voice_agent.factory.build_agent_config``. Returns the VAPI assistant id.
    """
    resp = _client().assistants.create(**config)
    return resp.id


def update_assistant(assistant_id: str, config: dict) -> None:
    """Replace the assistant's config (system prompt, tools, etc.) in-place."""
    _client().assistants.update(id=assistant_id, **config)


def delete_assistant(assistant_id: str) -> None:
    """Remove a VAPI assistant. Idempotent — no-op if already deleted."""
    try:
        _client().assistants.delete(id=assistant_id)
    except Exception as e:
        # The SDK raises on 404; treat "already gone" as success.
        if "404" not in str(e) and "not found" not in str(e).lower():
            raise


def release_phone_number(phone_number_id: str) -> None:
    """Remove a VAPI phone-number registration. Does NOT release the underlying
    Twilio number — call ``api.voice_agent.twilio.release_phone_number`` for that."""
    try:
        _client().phone_numbers.delete(id=phone_number_id)
    except Exception as e:
        if "404" not in str(e) and "not found" not in str(e).lower():
            raise
