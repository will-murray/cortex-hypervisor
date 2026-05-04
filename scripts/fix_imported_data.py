"""
One-shot data cleanup after the BQ → Cloud SQL import.

Two issues bled across from the legacy BQ data and need fixing in Cloud SQL:

  1. Every clinic has time_zone='America/Vancouver' — not the real local tz.
     Set per-clinic from the address.
  2. Calgary Ear Center has country='US' but is in Calgary, AB → 'CA'.

Idempotent: re-running with the same values is a no-op (the data already
matches what we'd write).

Usage:
    cd cortex-hypervisor
    CLOUD_SQL_IAM_USER=<your-email-or-sa> python -m scripts.fix_imported_data [--dry-run]
"""
import argparse
import logging
import sys

from sqlalchemy import select

from services.db import session_scope
from services.models import Clinic


logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("fix_imported_data")


# Keyed by clinic_name (unique, human-readable). Tuple is (country, time_zone).
FIXES: dict[str, tuple[str, str]] = {
    "Audiology Clinic of Northern Alberta": ("CA", "America/Edmonton"),
    "Calgary Ear Center":                   ("CA", "America/Edmonton"),
    "Earl for Life":                        ("CA", "America/Winnipeg"),
    "Greenville":                           ("US", "America/New_York"),
    "Labyrinth Audiology":                  ("US", "America/New_York"),
    "Princeton":                            ("US", "America/New_York"),
    "Sarasota":                             ("US", "America/New_York"),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Print intended changes without writing")
    args = parser.parse_args()

    changed, unchanged, missing = 0, 0, 0

    with session_scope() as db:
        for clinic_name, (country, time_zone) in FIXES.items():
            clinic = db.scalar(select(Clinic).where(Clinic.clinic_name == clinic_name))
            if clinic is None:
                log.warning("✗ clinic not found: %s", clinic_name)
                missing += 1
                continue

            location = clinic.location
            country_now = clinic.country
            tz_now = location.time_zone if location else None

            updates = []
            if country_now != country:
                updates.append(f"country: {country_now!r} → {country!r}")
            if tz_now != time_zone:
                updates.append(f"time_zone: {tz_now!r} → {time_zone!r}")

            if not updates:
                log.info("· %s — already correct", clinic_name)
                unchanged += 1
                continue

            log.info("→ %s\n    %s", clinic_name, "\n    ".join(updates))
            if not args.dry_run:
                clinic.country = country
                if location is not None:
                    location.time_zone = time_zone
            changed += 1

        if args.dry_run:
            db.rollback()
            log.info("\n(dry run — no changes committed)")

    log.info("\nSummary: changed=%d  unchanged=%d  missing=%d",
             changed, unchanged, missing)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
