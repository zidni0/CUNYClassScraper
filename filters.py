import re
from typing import Any


DAY_CODE_TO_NAME = {
    "Mo": "Monday",
    "Tu": "Tuesday",
    "We": "Wednesday",
    "Th": "Thursday",
    "Fr": "Friday",
    "Sa": "Saturday",
    "Su": "Sunday",
}

DAY_CODES_IN_ORDER = ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")

MODALITY_MAP = {
    "In Person": "in-person",
    "Hybrid Synchronous": "hybrid-synchronous",
    "Hybrid Asynchronous": "hybrid-asynchronous",
    "Online Asynchronous": "online-asynchronous",
    "Asynchronous Online": "online-asynchronous",
    "Online Synchronous": "online-synchronous",
    "Online Mix": "online-mix",
    "Online": "online-asynchronous",
    "HyFlex": "hyflex",
    "HyField": "hyfield",
}

OPEN_STATUSES = {"open"}
EXCLUDED_OPEN_ONLY_STATUSES = {"closed", "wait list", "waitlist"}


def apply_filters(
    sections: list[dict[str, Any]],
    allowed_modalities: list[str],
    available_times: dict[str, list[str]],
    open_only: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    matched_sections: list[dict[str, Any]] = []
    flagged_tba_sections: list[dict[str, Any]] = []

    for section in sections:
        normalized_modality = normalize_modality(section.get("modality_raw", ""))
        section["modality"] = normalized_modality

        if not modality_allowed(normalized_modality, allowed_modalities):
            continue

        if open_only and not status_allowed(section.get("status", "")):
            continue

        time_result = evaluate_time_fit(section, available_times)
        section["time_filter_status"] = time_result

        if time_result == "match":
            matched_sections.append(section)
        elif time_result == "tba":
            flagged_tba_sections.append(section)

    matched_sections.sort(key=sort_key)
    flagged_tba_sections.sort(key=sort_key)
    return matched_sections, flagged_tba_sections


def select_detail_candidates(
    sections: list[dict[str, Any]],
    allowed_modalities: list[str],
    open_only: bool,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for section in sections:
        normalized_modality = normalize_modality(section.get("modality_raw", ""))
        section["modality"] = normalized_modality
        if not modality_allowed(normalized_modality, allowed_modalities):
            continue
        if open_only and not status_allowed(section.get("status", "")):
            continue
        candidates.append(section)
    return candidates


def sort_key(section: dict[str, Any]) -> tuple[str, str, str]:
    return (
        section.get("course", ""),
        section.get("section", ""),
        section.get("class_number", ""),
    )


def normalize_modality(raw_value: str) -> str:
    text = " ".join(raw_value.replace("-", " ").split()).title()
    return MODALITY_MAP.get(text, raw_value.strip().lower())


def modality_allowed(section_modality: str, allowed_modalities: list[str]) -> bool:
    if section_modality in allowed_modalities:
        return True
    if section_modality.startswith("online-") and "online" in allowed_modalities:
        return True
    return False


def status_allowed(status: str) -> bool:
    normalized = status.strip().lower()
    if normalized in OPEN_STATUSES:
        return True
    return normalized not in EXCLUDED_OPEN_ONLY_STATUSES


def evaluate_time_fit(
    section: dict[str, Any], available_times: dict[str, list[str]]
) -> str:
    meeting_patterns = section.get("meeting_patterns") or []
    if not meeting_patterns:
        meeting_patterns = [
            {
                "days_time": section.get("days_time", "TBA"),
            }
        ]

    parsed_patterns = [parse_days_time(pattern.get("days_time", "")) for pattern in meeting_patterns]
    section["parsed_meeting_patterns"] = parsed_patterns

    if all(pattern["is_tba"] for pattern in parsed_patterns):
        if section.get("modality") == "online-asynchronous":
            return "match"
        return "tba"

    for pattern in parsed_patterns:
        if pattern["is_tba"]:
            return "tba"

        for day in pattern["days"]:
            allowed_ranges = available_times.get(day, [])
            if not allowed_ranges:
                return "no-match"
            if not fits_any_window(
                pattern["start_minutes"],
                pattern["end_minutes"],
                allowed_ranges,
            ):
                return "no-match"

    return "match"


def fits_any_window(
    start_minutes: int | None,
    end_minutes: int | None,
    allowed_ranges: list[str],
) -> bool:
    if start_minutes is None or end_minutes is None:
        return False

    for time_range in allowed_ranges:
        range_start, range_end = parse_24_hour_range(time_range)
        if range_start <= start_minutes and end_minutes <= range_end:
            return True
    return False


def parse_24_hour_range(value: str) -> tuple[int, int]:
    start_text, end_text = value.split("-", 1)
    return parse_24_hour_time(start_text), parse_24_hour_time(end_text)


def parse_24_hour_time(value: str) -> int:
    hours_text, minutes_text = value.split(":", 1)
    return int(hours_text) * 60 + int(minutes_text)


def parse_days_time(value: str) -> dict[str, Any]:
    cleaned = " ".join(value.split())
    if not cleaned or cleaned.upper() == "TBA":
        return {
            "raw": cleaned or "TBA",
            "days": [],
            "days_raw": "TBA",
            "time": "TBA",
            "start_minutes": None,
            "end_minutes": None,
            "is_tba": True,
        }

    match = re.match(
        r"^(?P<days>[A-Za-z]+)\s+(?P<start>\d{1,2}:\d{2}[AP]M)\s*-\s*(?P<end>\d{1,2}:\d{2}[AP]M)$",
        cleaned,
        re.IGNORECASE,
    )
    if not match:
        return {
            "raw": cleaned,
            "days": [],
            "days_raw": cleaned,
            "time": "TBA",
            "start_minutes": None,
            "end_minutes": None,
            "is_tba": True,
        }

    days_raw = match.group("days")
    start_text = match.group("start").upper()
    end_text = match.group("end").upper()
    return {
        "raw": cleaned,
        "days": split_day_codes(days_raw),
        "days_raw": days_raw,
        "time": f"{start_text} - {end_text}",
        "start_minutes": parse_meridiem_time(start_text),
        "end_minutes": parse_meridiem_time(end_text),
        "is_tba": False,
    }


def split_day_codes(days_raw: str) -> list[str]:
    days: list[str] = []
    remaining = days_raw

    while remaining:
        matched = False
        for code in DAY_CODES_IN_ORDER:
            if remaining.startswith(code):
                days.append(DAY_CODE_TO_NAME[code])
                remaining = remaining[len(code) :]
                matched = True
                break
        if not matched:
            return []
    return days


def parse_meridiem_time(value: str) -> int:
    match = re.fullmatch(r"(\d{1,2}):(\d{2})(AM|PM)", value)
    if not match:
        raise ValueError(f"Invalid time: {value}")

    hours = int(match.group(1))
    minutes = int(match.group(2))
    meridiem = match.group(3)

    if hours == 12:
        hours = 0
    if meridiem == "PM":
        hours += 12
    return hours * 60 + minutes
