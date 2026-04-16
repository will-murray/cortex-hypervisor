"""
Blueprint OMS integration test script.

Auto-mints a Firebase super_admin ID token (no manual paste), auto-loads clinic
credentials from blueprint_creds/creds.csv, tests the Blueprint API directly
and via the hypervisor proxy, and optionally downloads the S3 data feed for
local inspection.

The data-feed subcommand writes decrypted PHI to local disk — delete when done
and DO NOT commit. PHI ingest into BigQuery is deferred until the GCP HIPAA
BAA is signed (see CLAUDE.md Phase 2 plan).

Requires (from .env):
    FIREBASE_ADMIN_SERVICE_ACCOUNT   # Admin SDK JSON
    FIREBASE_WEB_API_KEY             # Web API key (for signInWithCustomToken)
    VAPI_WEBHOOK_SECRET              # Only needed for `proxy` subcommand

Run the hypervisor first (for config/clinic-config/proxy subcommands):
    uvicorn api:app --reload

Usage:
    python test_blueprint.py config          # Save PMS config to hypervisor
    python test_blueprint.py clinic-config   # Fetch event types / providers / locations
    python test_blueprint.py direct          # Direct Blueprint API tests
    python test_blueprint.py proxy           # Via hypervisor proxy (needs VAPI_WEBHOOK_SECRET)
    python test_blueprint.py data-feed       # Download + unzip S3 feed locally
    python test_blueprint.py all             # direct + proxy

Options (all subcommands):
    --clinic "Audiology Clinic of Northern Alberta"   # pick row from creds.csv
    --hypervisor-url http://localhost:8000
    --phone +17801234567                               # for CTI trigger
    --appt-type-id 42                                  # for availability/appointment
    --feed-dir ./feed_extracted                        # data-feed output dir
    --yes                                              # skip interactive confirms
"""
import argparse
import csv
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

HERE = Path(__file__).resolve().parent

# Secret Manager for credentials (falls back to .env during transition)
try:
    from services.secrets import get_secret
    _USE_SM = True
except Exception:
    _USE_SM = False

CREDS_CSV = HERE / "blueprint_creds" / "creds.csv"

# ─── OUTPUT HELPERS ───────────────────────────────────────────────────────────

def section(title: str):
    print(f"\n{'─'*60}\n  {title}\n{'─'*60}")


def ok(label: str, data=None):
    print(f"  ✓  {label}")
    if data is not None:
        dumped = json.dumps(data, indent=2, default=str) if isinstance(data, (dict, list)) else str(data)
        print("     " + dumped[:800].replace("\n", "\n     "))


def fail(label: str, detail: str = ""):
    print(f"  ✗  {label}")
    if detail:
        print(f"     {detail[:500]}")


def _is_connect_refused(exc: Exception) -> bool:
    """True if the exception is a 'connection refused' (hypervisor not running)."""
    if isinstance(exc, httpx.ConnectError):
        return True
    msg = str(exc).lower()
    return "connection refused" in msg or "errno 111" in msg


def hypervisor_hint(url: str):
    print(f"     (is the hypervisor running? try: `uvicorn api:app --reload` — expecting {url})")


def skip(label: str):
    print(f"  –  SKIP: {label}")


# ─── FIREBASE TOKEN MINTING ───────────────────────────────────────────────────

_cached_id_token: str | None = None


def get_admin_id_token() -> str:
    """
    Mint a Firebase ID token with role=super_admin using the admin SDK, then
    exchange it for an ID token via the Identity Toolkit REST API.

    super_admin short-circuits require_read/write_access in deps.py, so the
    minted UID does not need to exist in BigQuery.
    """
    global _cached_id_token
    if _cached_id_token:
        return _cached_id_token

    try:
        import firebase_admin
        from firebase_admin import auth, credentials
    except ImportError:
        print("ERROR: firebase_admin not installed (should be in requirements.txt)")
        sys.exit(1)

    if _USE_SM:
        admin_json = get_secret("firebase-admin-service-account")
        web_key = get_secret("firebase-web-api-key")
    else:
        admin_json = os.environ.get("FIREBASE_ADMIN_SERVICE_ACCOUNT")
        web_key = os.environ.get("FIREBASE_WEB_API_KEY")

    if not admin_json or not web_key:
        print("ERROR: Firebase credentials not found in Secret Manager or environment")
        sys.exit(1)

    if not firebase_admin._apps:
        cred = credentials.Certificate(json.loads(admin_json) if isinstance(admin_json, str) and admin_json.startswith("{") else admin_json)
        firebase_admin.initialize_app(cred)

    custom_token = auth.create_custom_token(
        "test-blueprint-script",
        developer_claims={"role": "super_admin"},
    ).decode("utf-8")

    resp = httpx.post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken",
        params={"key": web_key},
        json={"token": custom_token, "returnSecureToken": True},
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"ERROR: signInWithCustomToken failed: {resp.status_code} {resp.text[:300]}")
        sys.exit(1)
    _cached_id_token = resp.json()["idToken"]
    return _cached_id_token


# ─── CREDS LOADER ─────────────────────────────────────────────────────────────

def _parse_blueprint_url(api_url: str) -> tuple[str, str]:
    """
    Parse a Blueprint API URL into (server, slug).

    Example input:  https://ca-alb1.aws.bp-solutions.net:8443/ca_mst1/AB/acn/?rest/hello
    Example output: ("ca-alb1.aws.bp-solutions.net:8443", "ca_mst1/AB/acn")

    The query-string portion (?rest/...) and any trailing /rest/... in the path
    are stripped — those are endpoint paths, not part of the slug.
    """
    cleaned = api_url.replace("\u200b", "").strip()
    parsed = urlparse(cleaned)
    if not parsed.netloc:
        raise ValueError(f"Could not parse server from URL: {api_url!r}")
    server = parsed.netloc
    path = parsed.path.strip("/")
    # If the path ends in /rest (typos like /rest/hello), strip that marker
    for marker in ("/rest/", "/rest"):
        idx = path.lower().find(marker)
        if idx >= 0:
            path = path[:idx]
            break
    slug = path.strip("/")
    if not slug:
        raise ValueError(f"Could not parse slug from URL: {api_url!r}")
    return server, slug


def load_clinic_creds(clinic_name: str | None = None) -> dict:
    """
    Load a clinic row from blueprint_creds/creds.csv.

    If clinic_name is None and the CSV has exactly one row, return that row.
    Otherwise require an exact match on "Clinic Name".
    """
    if not CREDS_CSV.exists():
        print(f"ERROR: {CREDS_CSV} not found")
        sys.exit(1)

    with CREDS_CSV.open(newline="") as f:
        # Strip trailing colons in headers (e.g. "AWS Secret Access Key:")
        reader = csv.DictReader(f)
        rows = [{(k or "").strip().rstrip(":"): (v or "").strip() for k, v in row.items()} for row in reader]

    if not rows:
        print(f"ERROR: {CREDS_CSV} has no data rows")
        sys.exit(1)

    if clinic_name is None:
        if len(rows) == 1:
            row = rows[0]
        else:
            names = [r.get("Clinic Name", "?") for r in rows]
            print(f"ERROR: multiple clinics in CSV, pass --clinic. Options: {names}")
            sys.exit(1)
    else:
        matches = [r for r in rows if r.get("Clinic Name") == clinic_name]
        if not matches:
            names = [r.get("Clinic Name", "?") for r in rows]
            print(f"ERROR: clinic {clinic_name!r} not found. Available: {names}")
            sys.exit(1)
        row = matches[0]

    required = [
        "Clinic Name", "Clinic ID", "Clinic Code",
        "API URL", "API KEY",
        "AWS URL", "AWS Access Key ID", "AWS Secret Access Key",
        "Default region", "ZIP password",
    ]
    missing = [col for col in required if not row.get(col)]
    if missing:
        print(f"ERROR: CSV row missing columns: {missing}")
        sys.exit(1)

    server, slug = _parse_blueprint_url(row["API URL"])

    return {
        "clinic_name":        row["Clinic Name"],
        "clinic_id":          row["Clinic ID"],
        "clinic_code":        row["Clinic Code"],
        "blueprint_server":   server,
        "blueprint_slug":     slug,
        "blueprint_api_key":  row["API KEY"],
        "aws_s3_uri":         row["AWS URL"],
        "aws_access_key_id":  row["AWS Access Key ID"],
        "aws_secret_key":     row["AWS Secret Access Key"],
        "aws_region":         row["Default region"],
        "zip_password":       row["ZIP password"],
    }


def blueprint_base(creds: dict) -> str:
    return f"https://{creds['blueprint_server']}/{creds['blueprint_slug']}/rest"


# ─── SUBCOMMAND: config ───────────────────────────────────────────────────────

def cmd_config(args, creds: dict):
    """
    POST Blueprint PMS config to hypervisor. location_id/user_id must be known
    (run `clinic-config` first to discover them).
    """
    if not args.location_id or not args.user_id:
        print("ERROR: pass --location-id and --user-id (run `clinic-config` first to discover)")
        sys.exit(1)

    payload = {
        "pms_type": "blueprint",
        "blueprint_server":       creds["blueprint_server"],
        "blueprint_clinic_slug":  creds["blueprint_slug"],
        "blueprint_api_key":      creds["blueprint_api_key"],
        "blueprint_location_id":  args.location_id,
        "blueprint_user_id":      args.user_id,
    }

    section(f"Set PMS config — {creds['clinic_name']} ({creds['clinic_id']})")
    print(f"  server:      {creds['blueprint_server']}")
    print(f"  slug:        {creds['blueprint_slug']}")
    print(f"  location_id: {args.location_id}")
    print(f"  user_id:     {args.user_id}")
    if not args.yes and input("\nProceed? [y/N] ").strip().lower() != "y":
        print("Aborted"); return

    token = get_admin_id_token()
    try:
        resp = httpx.post(
            f"{args.hypervisor_url}/clinics/{creds['clinic_id']}/pms",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
        if resp.status_code == 200:
            ok("PMS config saved", resp.json())
        else:
            fail(f"HTTP {resp.status_code}", resp.text[:400])
    except Exception as e:
        fail("Request failed", str(e))
        if _is_connect_refused(e):
            hypervisor_hint(args.hypervisor_url)


# ─── SUBCOMMAND: clinic-config ────────────────────────────────────────────────

def fetch_clinic_config_direct(creds: dict):
    section("Blueprint clinicConfiguration (direct)")
    try:
        resp = httpx.get(
            f"{blueprint_base(creds)}/clinicConfiguration/",
            params={"apiKey": creds["blueprint_api_key"]},
            timeout=15,
        )
        if resp.status_code != 200:
            fail(f"HTTP {resp.status_code}", resp.text[:300])
            return

        data = resp.json()
        appt_types = data.get("appointmentTypes", [])
        providers  = data.get("providers", [])
        locations  = data.get("locations", [])

        ok(f"Appointment Types ({len(appt_types)} found):")
        for t in appt_types:
            print(f"       id={t['id']}  name={t['name']!r}  duration={t.get('duration')}min")
        ok(f"Providers ({len(providers)} found):")
        for p in providers:
            name = p.get("displayName") or f"{p.get('firstName','')} {p.get('lastName','')}".strip()
            print(f"       id={p['id']}  name={name!r}  locations={p.get('locations')}")
        ok(f"Locations ({len(locations)} found):")
        for loc in locations:
            print(f"       id={loc['id']}  name={loc['name']!r}  tz={loc.get('timeZone')}")
        print("\n  → Pass one of these location/user ids to `config --location-id ... --user-id ...`")
    except Exception as e:
        fail("Request failed", str(e))


def fetch_clinic_config_proxy(args, creds: dict):
    section("Hypervisor clinic-config endpoint")
    try:
        token = get_admin_id_token()
        resp = httpx.get(
            f"{args.hypervisor_url}/blueprint/{creds['clinic_id']}/clinic-config",
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
        if resp.status_code == 200:
            ok("clinic-config response", resp.json())
        else:
            fail(f"HTTP {resp.status_code}", resp.text[:400])
    except Exception as e:
        fail("Request failed", str(e))
        if _is_connect_refused(e):
            hypervisor_hint(args.hypervisor_url)


def cmd_clinic_config(args, creds: dict):
    fetch_clinic_config_direct(creds)
    fetch_clinic_config_proxy(args, creds)


# ─── SUBCOMMAND: direct ───────────────────────────────────────────────────────

def cmd_direct(args, creds: dict):
    section("Direct — CTI trigger (client/show)")
    if not args.phone:
        skip("pass --phone to test CTI trigger")
    else:
        phone_digits = "".join(c for c in args.phone if c.isdigit())
        try:
            resp = httpx.get(
                f"{blueprint_base(creds)}/client/show",
                params={
                    "apiKey":   creds["blueprint_api_key"],
                    "event":    "ringing",
                    "user":     str(args.user_id or 1),
                    "callerid": phone_digits,
                },
                timeout=10,
            )
            if resp.status_code == 200:
                ok(f"HTTP {resp.status_code} (body: {repr(resp.text[:50]) or '<empty — correct>'})")
                print("     Blueprint opened the patient file in their UI (empty body is expected)")
            else:
                fail(f"HTTP {resp.status_code}", resp.text[:300])
        except Exception as e:
            fail("Request failed", str(e))

    section("Direct — Availability")
    if not args.appt_type_id:
        skip("pass --appt-type-id (run `clinic-config` first)")
    else:
        today = date.today()
        start_ts = int(datetime(today.year, today.month, today.day, tzinfo=timezone.utc).timestamp())
        end_dt   = today + timedelta(days=7)
        end_ts   = int(datetime(end_dt.year, end_dt.month, end_dt.day, tzinfo=timezone.utc).timestamp())
        try:
            params = {
                "apiKey":                  creds["blueprint_api_key"],
                "startTime":               start_ts,
                "endTime":                 end_ts,
                "eventTypeId":             args.appt_type_id,
                "bookingTimeSlotInterval": "30",
                "minimumAdvanceBookingTime": "60",
            }
            if args.location_id:
                params["locations"] = args.location_id
            resp = httpx.get(f"{blueprint_base(creds)}/availability/", params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                count = len(data) if isinstance(data, list) else "?"
                ok(f"{count} day(s) in response", data[:2] if isinstance(data, list) else data)
            else:
                fail(f"HTTP {resp.status_code}", resp.text[:300])
        except Exception as e:
            fail("Request failed", str(e))


# ─── SUBCOMMAND: proxy ────────────────────────────────────────────────────────

def cmd_proxy(args, creds: dict):
    vapi_secret = os.environ.get("VAPI_WEBHOOK_SECRET")
    if not vapi_secret:
        print("ERROR: VAPI_WEBHOOK_SECRET must be set in .env for proxy subcommand")
        sys.exit(1)

    headers = {"X-Vapi-Secret": vapi_secret, "Content-Type": "application/json"}

    section(f"Proxy — CTI trigger (clinic: {creds['clinic_id']})")
    if not args.phone:
        skip("pass --phone")
    else:
        try:
            resp = httpx.post(
                f"{args.hypervisor_url}/blueprint/{creds['clinic_id']}/patient/lookup",
                headers=headers,
                json={"caller_phone": args.phone},
                timeout=15,
            )
            if resp.status_code == 200:
                ok("Response", resp.json())
                print("     Expected: {\"triggered\": true}")
            else:
                fail(f"HTTP {resp.status_code}", resp.text[:400])
        except Exception as e:
            fail("Request failed", str(e))
            if _is_connect_refused(e):
                hypervisor_hint(args.hypervisor_url)

    section(f"Proxy — Availability (clinic: {creds['clinic_id']})")
    if not args.appt_type_id:
        skip("pass --appt-type-id (run `clinic-config` first)")
    else:
        today = date.today()
        body = {
            "event_type_id": args.appt_type_id,
            "start_date":    today.isoformat(),
            "end_date":      (today + timedelta(days=7)).isoformat(),
        }
        try:
            resp = httpx.post(
                f"{args.hypervisor_url}/blueprint/{creds['clinic_id']}/availability",
                headers=headers, json=body, timeout=20,
            )
            if resp.status_code == 200:
                data = resp.json()
                count = len(data) if isinstance(data, list) else "?"
                ok(f"{count} day(s) in response", data[:2] if isinstance(data, list) else data)
            else:
                fail(f"HTTP {resp.status_code}", resp.text[:400])
        except Exception as e:
            fail("Request failed", str(e))
            if _is_connect_refused(e):
                hypervisor_hint(args.hypervisor_url)


# ─── SUBCOMMAND: data-feed ────────────────────────────────────────────────────

def _parse_s3_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://"):
        raise ValueError(f"Not an s3:// URI: {uri}")
    path = uri[len("s3://"):]
    bucket, _, key = path.partition("/")
    if not bucket or not key:
        raise ValueError(f"Malformed s3 URI (expected s3://bucket/key): {uri}")
    return bucket, key


def cmd_data_feed(args, creds: dict):
    """
    Download Blueprint's data feed ZIP from S3, unzip with password, list contents.

    PHI HANDLING: decrypted contents are written to --feed-dir (default
    ./feed_extracted). This directory is .gitignored implicitly since it is
    not under version control, but you MUST delete it when finished. No
    contents are uploaded anywhere — this subcommand only downloads and unzips.
    """
    try:
        import boto3
        from botocore.exceptions import ClientError
        import pyzipper
    except ImportError as e:
        print(f"ERROR: missing dependency ({e}). Run: pip install -r requirements.txt")
        sys.exit(1)

    bucket, key = _parse_s3_uri(creds["aws_s3_uri"])
    feed_dir = Path(args.feed_dir).resolve()

    section(f"Data feed — {creds['clinic_name']}")
    print(f"  source:  s3://{bucket}/{key}")
    print(f"  region:  {creds['aws_region']}")
    print(f"  target:  {feed_dir}")
    print("\n  ⚠  This downloads PHI. Decrypted files remain on local disk until you delete them.")
    if not args.yes and input("\nProceed? [y/N] ").strip().lower() != "y":
        print("Aborted"); return

    feed_dir.mkdir(parents=True, exist_ok=True)
    zip_path = feed_dir / "StandardDataFeed.zip"

    # Download from S3
    print("\n  Downloading from S3…")
    try:
        s3 = boto3.client(
            "s3",
            aws_access_key_id=creds["aws_access_key_id"],
            aws_secret_access_key=creds["aws_secret_key"],
            region_name=creds["aws_region"],
        )
        s3.download_file(bucket, key, str(zip_path))
        size_mb = zip_path.stat().st_size / (1024 * 1024)
        ok(f"Downloaded {size_mb:.2f} MB → {zip_path.name}")
    except ClientError as e:
        fail("S3 download failed", str(e)); return
    except Exception as e:
        fail("S3 download failed", str(e)); return

    # Unzip with password (AES-encrypted)
    print("\n  Decrypting ZIP…")
    try:
        with pyzipper.AESZipFile(str(zip_path)) as zf:
            zf.setpassword(creds["zip_password"].encode("utf-8"))
            names = zf.namelist()
            zf.extractall(path=str(feed_dir))
        ok(f"Extracted {len(names)} entries")
    except RuntimeError as e:
        # pyzipper raises RuntimeError("Bad password") on wrong password
        fail("Decryption failed", str(e)); return
    except Exception as e:
        fail("Unzip failed", f"{type(e).__name__}: {e}"); return

    # Summarise contents
    section("Feed contents")
    extracted = sorted(p for p in feed_dir.rglob("*") if p.is_file() and p.name != zip_path.name)
    for p in extracted:
        rel = p.relative_to(feed_dir)
        size_kb = p.stat().st_size / 1024
        print(f"  {size_kb:>8.1f} KB  {rel}")

    print(f"\n  Total: {len(extracted)} files, {sum(p.stat().st_size for p in extracted) / (1024*1024):.2f} MB")
    print(f"\n  When finished, delete PHI with: rm -rf {feed_dir}")


# ─── ARG PARSING ──────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Blueprint OMS integration tests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("command",
                   choices=["config", "clinic-config", "direct", "proxy", "data-feed", "all"])
    p.add_argument("--clinic", default=None,
                   help="Clinic Name in creds.csv (optional if CSV has one row)")
    p.add_argument("--hypervisor-url", default="http://localhost:8000")
    p.add_argument("--phone", default=None, help="E.g. +17801234567 for CTI trigger tests")
    p.add_argument("--appt-type-id", type=int, default=None,
                   help="Blueprint event_type_id — from clinic-config output")
    p.add_argument("--location-id", type=int, default=None,
                   help="Blueprint location id — from clinic-config output")
    p.add_argument("--user-id", type=int, default=None,
                   help="Blueprint service-account user id")
    p.add_argument("--feed-dir", default="./feed_extracted",
                   help="Where data-feed extracts to (PHI — delete when done)")
    p.add_argument("--yes", "-y", action="store_true",
                   help="Skip interactive confirmations")
    return p


def main():
    args = build_parser().parse_args()
    creds = load_clinic_creds(args.clinic)

    section(f"Loaded creds for: {creds['clinic_name']} ({creds['clinic_id']})")
    print(f"  server:  {creds['blueprint_server']}")
    print(f"  slug:    {creds['blueprint_slug']}")
    print(f"  S3 URI:  {creds['aws_s3_uri']}")

    if args.command == "config":
        cmd_config(args, creds)
    elif args.command == "clinic-config":
        cmd_clinic_config(args, creds)
    elif args.command == "direct":
        cmd_direct(args, creds)
    elif args.command == "proxy":
        cmd_proxy(args, creds)
    elif args.command == "data-feed":
        cmd_data_feed(args, creds)
    elif args.command == "all":
        cmd_direct(args, creds)
        cmd_proxy(args, creds)

    print()


if __name__ == "__main__":
    main()
