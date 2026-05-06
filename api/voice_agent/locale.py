"""
Clinic locale resolution.

A clinic's `country` (ISO-3166 alpha-2, on Clinic) and `time_zone` (IANA, on
ClinicLocationDetails) drive: VAPI transcriber language, the locale block
prepended to the system prompt, and "today's local date" for the agent.
"""
import datetime
from zoneinfo import ZoneInfo

from api.core.orm import Clinic


# Country → Deepgram nova-2 language tag (English-speaking markets).
# nova-2 supports `en, en-US, en-AU, en-GB, en-NZ, en-IN` — note the absence
# of `en-CA`. Countries without a region-specific tag fall back to generic `en`.
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


def resolve(clinic: Clinic) -> dict:
    """
    Returns the locale config derived from a Clinic ORM (with its
    ClinicLocationDetails relationship loaded).

    Returns:
        {country_code, transcriber_language, timezone, today_local, prompt_block}
    """
    country = (clinic.country or "").upper()
    location = clinic.location
    timezone = (location.time_zone if location else None) or ""

    if not country:
        raise ValueError(f"Clinic {clinic.clinic_id} missing country")
    if not timezone:
        raise ValueError(f"Clinic {clinic.clinic_id} missing time_zone")

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
