#!/usr/bin/env python3
"""
Configure Blueprint OMS credentials for a clinic.

Thin CLI wrapper around ``POST /clinics/{clinic_id}/pms``. Prompts for the
non-secret Blueprint config (clinic_code, api_url, aws_url) and the four
secrets (api_key, aws_access_key_id, aws_secret_access_key, zip_password),
then forwards them to the hypervisor. The API persists non-secrets to Cloud
SQL ``clinic_blueprint_config`` and writes secrets to Secret Manager under
``clinic_{clinic_id}_blueprint_{key}``.

Auth: mints a Firebase ID token using the admin's email, via the
``firebase-admin-service-account`` credentials in Secret Manager. The admin
must have ``role=super_admin`` or ``admin`` set as a Firebase custom claim
(see cortex/src/app/api/auth/set-claims/route.ts for how those are assigned).

Usage:
    cd cortex-hypervisor
    source venv/bin/activate

    # Interactive: prompts for email + clinic, shows existing config
    python configure_blueprint.py

    # Non-interactive: known clinic
    python configure_blueprint.py --email admin@example.com --clinic-id <uuid>

    # Hit a deployed hypervisor instead of localhost
    API_BASE=https://hypervisor.example.com python configure_blueprint.py

Prerequisites:
    gcloud auth application-default login
    Local hypervisor running on ``API_BASE`` (default http://localhost:8000).
"""
import argparse
import json
import os
import sys
from getpass import getpass

import firebase_admin
import requests
from firebase_admin import auth, credentials

from api.core.secrets import get_secret


# Mirror cortex-hypervisor/api/routers/pms_config.py for validation parity.
_BLUEPRINT_CONFIG_FIELDS = ("clinic_code", "api_url", "aws_url")
_BLUEPRINT_SECRET_KEYS = (
    "api_key", "aws_access_key_id", "aws_secret_access_key", "zip_password",
)


def _init_firebase() -> None:
    if firebase_admin._apps:
        return
    sa_json = json.loads(get_secret("firebase-admin-service-account"))
    firebase_admin.initialize_app(credentials.Certificate(sa_json))


def _mint_id_token(uid: str) -> str:
    """Mint a Firebase ID token by exchanging a custom token via Identity Toolkit."""
    custom_token = auth.create_custom_token(uid).decode("utf-8")
    web_api_key = get_secret("firebase-web-api-key")
    resp = requests.post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key={web_api_key}",
        json={"token": custom_token, "returnSecureToken": True},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["idToken"]


def _prompt(label: str, default: str = "") -> str:
    """Prompt with default — empty input keeps the default."""
    suffix = f" [{default[:40]}{'…' if len(default) > 40 else ''}]" if default else ""
    val = input(f"  {label}{suffix}: ").strip()
    return val if val else default


def _select_clinic(api_base: str, headers: dict, uid: str) -> dict:
    """List the admin's clinics via GET /instance/{uid} and pick one."""
    resp = requests.get(f"{api_base}/instance/{uid}", headers=headers, timeout=15)
    resp.raise_for_status()
    clinics = resp.json().get("clinics") or []
    if not clinics:
        print(f"ERROR: no clinics found for uid {uid}")
        sys.exit(1)

    print("\nClinics:")
    for i, c in enumerate(clinics, 1):
        pms = c.get("pms_type") or "none"
        print(f"  [{i}] {c['clinic_name']:40s}  pms={pms:9s}  {c['clinic_id']}")

    raw = input(f"\nSelect [1-{len(clinics)}]: ").strip()
    try:
        idx = int(raw) - 1
        return clinics[idx]
    except (ValueError, IndexError):
        print("ERROR: invalid selection")
        sys.exit(1)


def _fetch_existing_pms(api_base: str, headers: dict, clinic_id: str) -> dict:
    resp = requests.get(f"{api_base}/clinics/{clinic_id}/pms", headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Configure Blueprint OMS credentials via the hypervisor API",
    )
    parser.add_argument("--email", help="admin email used for Firebase auth")
    parser.add_argument("--clinic-id", help="skip the interactive clinic picker")
    parser.add_argument(
        "--api-base",
        default=os.environ.get("API_BASE", "http://localhost:8000"),
        help="hypervisor base URL (default: $API_BASE or http://localhost:8000)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  Blueprint OMS credential configuration")
    print("=" * 60)
    print(f"  API:  {args.api_base}")

    email = args.email or input("\nAdmin email: ").strip()
    if not email:
        print("ERROR: email is required")
        return 1

    _init_firebase()
    try:
        user = auth.get_user_by_email(email)
    except auth.UserNotFoundError:
        print(f"ERROR: no Firebase user with email {email!r}")
        return 1

    headers = {"Authorization": f"Bearer {_mint_id_token(user.uid)}"}

    if args.clinic_id:
        clinic_id = args.clinic_id
        clinic_label = clinic_id
    else:
        clinic = _select_clinic(args.api_base, headers, user.uid)
        clinic_id = clinic["clinic_id"]
        clinic_label = f"{clinic['clinic_name']} ({clinic_id})"

    try:
        existing = _fetch_existing_pms(args.api_base, headers, clinic_id)
    except requests.HTTPError as e:
        print(f"ERROR: failed to fetch current PMS config: {e}")
        return 1
    existing_config = existing.get("config") or {}

    print(f"\n✓ Selected clinic: {clinic_label}")
    print(f"  current pms_type: {existing.get('pms_type') or 'none'}")
    if existing_config:
        print(f"  existing config:  {existing_config}")
        print(f"  (Enter to keep existing values)")

    print("\n── Non-secret config ──")
    config = {
        field: _prompt(field, existing_config.get(field, ""))
        for field in _BLUEPRINT_CONFIG_FIELDS
    }

    print("\n── Secrets (leave blank to keep current value) ──")
    secrets: dict[str, str] = {}
    for key in _BLUEPRINT_SECRET_KEYS:
        val = getpass(f"  {key}: ").strip()
        if val:
            secrets[key] = val

    # Summary
    print("\n" + "=" * 60)
    print("  Summary")
    print("=" * 60)
    print(f"  Clinic:    {clinic_label}")
    print(f"  pms_type:  blueprint")
    print(f"  Config:")
    for k, v in config.items():
        print(f"    {k}: {v or '(empty)'}")
    if secrets:
        print(f"  Secrets to upsert: {sorted(secrets)}")
    else:
        print(f"  Secrets: (none — keeping existing values)")

    if input("\nProceed? [y/N] ").strip().lower() != "y":
        print("Aborted")
        return 0

    payload: dict = {"pms_type": "blueprint", "config": config}
    if secrets:
        payload["secrets"] = secrets

    resp = requests.post(
        f"{args.api_base}/clinics/{clinic_id}/pms",
        headers=headers,
        json=payload,
        timeout=30,
    )
    if not resp.ok:
        print(f"\nERROR: API returned {resp.status_code}: {resp.text}")
        return 1

    print(f"\n✓ {resp.json()}")
    print("\nDone. Blueprint configuration complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
