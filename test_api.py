"""
Manual integration test helpers for the hypervisor API.

Not a pytest file — provides Firebase auth helpers so you can hit the running
API with a real bearer token. Build your own request payloads inline; the old
provision_data fixture was tied to the pre-Cloud-SQL schema and was removed.

Usage:
    python -i test_api.py
    >>> headers = auth_headers("<some-firebase-uid>")
    >>> requests.get("http://localhost:8000/instance/<uid>", headers=headers)
"""
import json

import firebase_admin
import requests
from firebase_admin import auth, credentials

from services.secrets import get_secret


FIREBASE_WEB_API_KEY = get_secret("firebase-web-api-key")
_fb_app = None


def _get_fb_app():
    global _fb_app
    if _fb_app is None:
        cred = credentials.Certificate(json.loads(get_secret("firebase-admin-service-account")))
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
