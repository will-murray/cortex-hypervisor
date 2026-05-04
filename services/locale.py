"""
Clinic locale resolution — single source of truth for everything that depends
on where a clinic operates.

A clinic's `country` (ISO-3166 alpha-2) and `timezone` (IANA, e.g.
"America/Edmonton") drive:
  - Twilio: country code for `buy_phone_number`
  - VAPI transcriber: a Deepgram nova-2 language tag (see allowlist below)
  - VAPI assistant prompt: locale block (today's date in clinic-local time,
    timezone, country) prepended to the system prompt

Language is currently always English; voice ID is not country-specific
(Emma works for all English variants) so it is set in the assistant config
builders, not here.
"""
import datetime
from zoneinfo import ZoneInfo


# Country → Deepgram nova-2 language tag (English-speaking markets).
# nova-2 supports `en, en-US, en-AU, en-GB, en-NZ, en-IN` — note the absence
# of `en-CA`. Countries without a region-specific tag fall back to generic
# `en`. Multi-language clinics can override by adding their own row; for now
# we assume English. (`fr-CA` is supported by nova-2 if we want French
# Canadian clinics later.)
_TRANSCRIBER_LANGUAGE_BY_COUNTRY: dict[str, str] = {
    "US": "en-US",
    "GB": "en-GB",
    "AU": "en-AU",
    "NZ": "en-NZ",
    "IN": "en-IN",
    # Canada has no en-CA in nova-2; generic `en` is the closest match and
    # transcribes North American English well in practice.
    "CA": "en",
}
_TRANSCRIBER_LANGUAGE_DEFAULT = "en"


def resolve(clinic: dict) -> dict:
    """
    Returns the locale config derived from a clinic row.

    Args:
        clinic: must contain `country` (ISO-3166 alpha-2) and `timezone` (IANA).

    Returns:
        {
          "country_code": "CA",
          "transcriber_language": "en",
          "timezone": "America/Edmonton",
          "today_local": "2026-04-27",
          "prompt_block": "## Locale\\n- Country: CA\\n- Timezone: ...\\n- Today: ...",
        }
    """
    country = (clinic.get("country") or "").upper()
    timezone = clinic.get("timezone") or ""
    if not country:
        raise ValueError(f"Clinic missing country: {clinic.get('clinic_id')}")
    if not timezone:
        raise ValueError(f"Clinic missing timezone: {clinic.get('clinic_id')}")

    today_local = datetime.datetime.now(ZoneInfo(timezone)).strftime("%Y-%m-%d")
    transcriber_language = _TRANSCRIBER_LANGUAGE_BY_COUNTRY.get(
        country, _TRANSCRIBER_LANGUAGE_DEFAULT
    )

    prompt_block = (
        "## Locale\n"
        f"- Country: {country}\n"
        f"- Timezone: {timezone}\n"
        f"- Today's date (clinic local): {today_local}\n"
        "Always reason about days, hours, and appointment times in the clinic's local timezone."
    )

    return {
        "country_code": country,
        "transcriber_language": transcriber_language,
        "timezone": timezone,
        "today_local": today_local,
        "prompt_block": prompt_block,
    }
