import json
import re
import sys
from pathlib import Path
from typing import Any


DAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

INSTITUTION_CODE_TO_NAME = {
    "BAR01": "Baruch College",
    "BMC01": "Borough of Manhattan CC",
    "BCC01": "Bronx CC",
    "BKL01": "Brooklyn College",
    "CTY01": "City College",
    "CSI01": "College of Staten Island",
    "GRD01": "Graduate Center",
    "NCC01": "Guttman CC",
    "HOS01": "Hostos CC",
    "HTR01": "Hunter College",
    "JJC01": "John Jay College",
    "KCC01": "Kingsborough CC",
    "LAG01": "LaGuardia CC",
    "LEH01": "Lehman College",
    "MHC01": "Macaulay Honors College",
    "MEC01": "Medgar Evers College",
    "NYT01": "NYC College of Technology",
    "QNS01": "Queens College",
    "QCC01": "Queensborough CC",
    "SOJ01": "School of Journalism",
    "SLU01": "School of Labor&Urban Studies",
    "LAW01": "School of Law",
    "MED01": "School of Medicine",
    "SPS01": "School of Professional Studies",
    "SPH01": "School of Public Health",
    "YRK01": "York College",
}

INSTITUTION_ALIASES = {
    "HUN01": "HTR01",
    "HUNTER": "HTR01",
    "HUNTER COLLEGE": "HTR01",
}

SUBJECT_ALIASES = {
    "CSCI": "CMSC",
}

ALLOWED_MODALITIES = {
    "online",
    "online-asynchronous",
    "online-synchronous",
    "online-mix",
    "in-person",
    "hybrid-synchronous",
    "hybrid-asynchronous",
    "hyflex",
    "hyfield",
}


class ConfigError(Exception):
    pass


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")

    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc

    required_keys = {
        "institution",
        "term",
        "course_codes",
        "modality",
        "available_times",
        "open_only",
    }
    missing = required_keys - set(config)
    if missing:
        raise ConfigError(f"Missing config keys: {', '.join(sorted(missing))}")

    return config


def build_runtime_config(config: dict[str, Any], subject_override: str | None) -> dict[str, Any]:
    institution_code = canonicalize_institution_code(config["institution"])
    institution_name = institution_name_for_code(institution_code)

    course_codes = config["course_codes"]
    if not isinstance(course_codes, list) or not course_codes:
        raise ConfigError("course_codes must be a non-empty list of subject codes.")

    if subject_override:
        course_codes = [subject_override]

    normalized_course_codes = []
    for code in course_codes:
        if not isinstance(code, str) or not code.strip():
            raise ConfigError("Each course code must be a non-empty string.")
        normalized_course_codes.append(code.strip().upper())

    modality = config["modality"]
    if not isinstance(modality, list) or not modality:
        raise ConfigError("modality must be a non-empty list.")

    normalized_modalities = []
    for item in modality:
        if not isinstance(item, str):
            raise ConfigError("Each modality entry must be a string.")
        value = item.strip().lower()
        if value not in ALLOWED_MODALITIES:
            raise ConfigError(
                "Unsupported modality "
                f"'{item}'. Allowed values include: {', '.join(sorted(ALLOWED_MODALITIES))}"
            )
        normalized_modalities.append(value)

    available_times = validate_available_times(config["available_times"])

    open_only = config["open_only"]
    if not isinstance(open_only, bool):
        raise ConfigError("open_only must be true or false.")

    term = config["term"]
    if not isinstance(term, str) or not term.strip():
        raise ConfigError("term must be a non-empty string.")

    return {
        "institution_code": institution_code,
        "institution_name": institution_name,
        "term": term.strip(),
        "course_codes": normalized_course_codes,
        "modality": normalized_modalities,
        "available_times": available_times,
        "open_only": open_only,
        "input_institution": str(config["institution"]).strip(),
    }


def validate_available_times(available_times: Any) -> dict[str, list[str]]:
    if not isinstance(available_times, dict):
        raise ConfigError("available_times must be an object keyed by weekday.")

    normalized: dict[str, list[str]] = {}
    for day in DAY_NAMES:
        value = available_times.get(day, [])
        if not isinstance(value, list):
            raise ConfigError(f"available_times.{day} must be a list of ranges.")
        normalized_ranges = []
        for time_range in value:
            if not isinstance(time_range, str) or not is_valid_24_hour_range(time_range):
                raise ConfigError(
                    f"Invalid time range '{time_range}' for {day}. Use HH:MM-HH:MM in 24-hour time."
                )
            normalized_ranges.append(time_range)
        normalized[day] = normalized_ranges
    return normalized


def canonicalize_institution_code(value: str) -> str:
    raw = value.strip()
    upper = raw.upper()

    if upper in INSTITUTION_CODE_TO_NAME:
        return upper
    if upper in INSTITUTION_ALIASES:
        return INSTITUTION_ALIASES[upper]

    for code, name in INSTITUTION_CODE_TO_NAME.items():
        if name.upper() == upper:
            return code

    raise ConfigError(f"Unsupported institution '{value}'.")


def institution_name_for_code(code: str) -> str:
    try:
        return INSTITUTION_CODE_TO_NAME[code]
    except KeyError as exc:
        raise ConfigError(f"Unsupported institution code '{code}'.") from exc


def resolve_search_subject(subject_code: str, subject_options: dict[str, str]) -> tuple[str, str]:
    normalized = subject_code.strip().upper()
    if normalized in subject_options:
        return normalized, subject_options[normalized]

    alias = SUBJECT_ALIASES.get(normalized)
    if alias and alias in subject_options:
        return alias, subject_options[alias]

    raise ConfigError(
        f"Subject '{subject_code}' is not available for the selected institution/term."
    )


def is_valid_24_hour_range(value: str) -> bool:
    match = re.fullmatch(r"(\d{2}):(\d{2})-(\d{2}):(\d{2})", value)
    if not match:
        return False
    start_hour, start_minute, end_hour, end_minute = map(int, match.groups())
    if not (
        0 <= start_hour <= 23
        and 0 <= end_hour <= 23
        and 0 <= start_minute <= 59
        and 0 <= end_minute <= 59
    ):
        return False
    return (start_hour, start_minute) < (end_hour, end_minute)


def clean_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def slugify_term(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def requested_term_matches(option_text: str, requested_term: str) -> bool:
    option_slug = slugify_term(option_text)
    requested_slug = slugify_term(requested_term)
    if option_slug == requested_slug:
        return True

    year_match = re.search(r"(20\d{2})", requested_slug)
    if not year_match:
        return False

    year = year_match.group(1)
    season = None
    for candidate in ("spring", "summer", "fall", "winter"):
        if candidate in requested_slug:
            season = candidate
            break

    return bool(season and year in option_slug and season in option_slug)


def warn_live_discrepancies(runtime_config: dict[str, Any]) -> None:
    if runtime_config["input_institution"].strip().upper() == "HUN01":
        print(
            "Note: the PRD uses Hunter institution code HUN01, but the live CUNY site currently uses HTR01. "
            "This tool is using HTR01.",
            file=sys.stderr,
        )

    if "CSCI" in runtime_config["course_codes"]:
        print(
            "Note: the PRD example uses CSCI, but the live Hunter search dropdown uses CMSC for the search step. "
            "This tool will automatically search CMSC and still report the returned CSCI course codes.",
            file=sys.stderr,
        )
