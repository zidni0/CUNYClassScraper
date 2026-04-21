import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def write_results(
    matched_sections: list[dict[str, Any]],
    flagged_tba_sections: list[dict[str, Any]],
    warnings: list[str],
    output_dir: Path,
) -> None:
    exported_sections = build_export_sections(matched_sections, flagged_tba_sections)
    write_json(exported_sections, output_dir / "results.json")
    write_csv(exported_sections, output_dir / "results.csv")
    write_warnings(warnings, output_dir / "warnings.log")


def write_json(sections: list[dict[str, Any]], path: Path) -> None:
    payload = [serialize_section(section) for section in sections]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_warnings(warnings: list[str], path: Path) -> None:
    if warnings:
        path.write_text("\n".join(warnings) + "\n", encoding="utf-8")
    else:
        path.write_text("", encoding="utf-8")


def write_csv(sections: list[dict[str, Any]], path: Path) -> None:
    fieldnames = [
        "course",
        "section",
        "class_number",
        "instructor",
        "days",
        "time",
        "modality",
        "room",
        "status",
        "credits",
        "result_category",
        "time_filter_status",
        "warnings",
    ]

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for section in sections:
            writer.writerow(
                {
                    "course": section.get("course", ""),
                    "section": section.get("section", ""),
                    "class_number": section.get("class_number", ""),
                    "instructor": first_non_tba_instructor(section),
                    "days": flattened_days(section),
                    "time": flattened_time(section),
                    "modality": section.get("modality_raw", ""),
                    "room": first_non_tba_room(section),
                    "status": section.get("status", ""),
                    "credits": section.get("credits", ""),
                    "result_category": section.get("result_category", ""),
                    "time_filter_status": section.get("time_filter_status", ""),
                    "warnings": " | ".join(section.get("warnings", [])),
                }
            )


def print_results(
    matched_sections: list[dict[str, Any]],
    flagged_tba_sections: list[dict[str, Any]],
    subject_messages: list[str],
    warnings: list[str],
    requested_subjects: list[str],
    term_label: str,
) -> None:
    grouped = defaultdict(list)
    for section in matched_sections:
        grouped[section.get("course", "").split(" ", 1)[0]].append(section)

    if not matched_sections:
        print(f"No matching sections found for {term_label}.")
    else:
        for subject in requested_subjects:
            subject_key = subject_display_group(subject, grouped)
            subject_sections = grouped.get(subject_key, [])
            if not subject_sections:
                continue

            print("============================")
            print(f"{subject_key} - {len(subject_sections)} sections found")
            print("============================")
            print()

            for index, section in enumerate(subject_sections, start=1):
                print(
                    f"[{index}] {section['course']} - {section['course_title']}  |  Section: {section['section']}"
                )
                print(f"    Class #: {section['class_number']}")
                print(f"    Time: {format_time_line(section)}")
                print(f"    Modality: {section['modality_raw']}")
                print(f"    Instructor: {first_non_tba_instructor(section)}")
                room = first_non_tba_room(section)
                if room:
                    print(f"    Room: {room}")
                print(f"    Status: {section['status']}")
                if section.get("credits") is not None:
                    print(f"    Credits: {section['credits']}")
                print()

    if flagged_tba_sections:
        print("============================")
        print("TBA / Needs Review")
        print("============================")
        print()
        for section in flagged_tba_sections:
            print(
                f"{section['course']} | Section {section['section']} | Class # {section['class_number']} | "
                f"Modality: {section['modality_raw']} | Time: TBA"
            )
        print()

    for message in subject_messages:
        print(f"Warning: {message}")
    for warning in warnings:
        print(f"Warning: {warning}")


def build_export_sections(
    matched_sections: list[dict[str, Any]],
    flagged_tba_sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    exported_sections: list[dict[str, Any]] = []
    for section in matched_sections:
        section["result_category"] = "matched"
        exported_sections.append(section)
    for section in flagged_tba_sections:
        section["result_category"] = "tba_review"
        exported_sections.append(section)
    exported_sections.sort(key=sort_key)
    return exported_sections


def sort_key(section: dict[str, Any]) -> tuple[str, str, str]:
    return (
        section.get("course", ""),
        section.get("section", ""),
        section.get("class_number", ""),
    )


def subject_display_group(subject: str, grouped: dict[str, list[dict[str, Any]]]) -> str:
    if subject in grouped:
        return subject
    if subject == "CMSC" and "CSCI" in grouped:
        return "CSCI"
    return subject


def format_time_line(section: dict[str, Any]) -> str:
    parsed_patterns = section.get("parsed_meeting_patterns") or []
    if not parsed_patterns:
        return section.get("days_time", "TBA")
    if any(pattern.get("is_tba") for pattern in parsed_patterns):
        return "TBA"
    return " | ".join(
        f"{pattern['days_raw']} {pattern['time']}" for pattern in parsed_patterns
    )


def flattened_days(section: dict[str, Any]) -> str:
    parsed_patterns = section.get("parsed_meeting_patterns") or []
    if not parsed_patterns:
        return ""
    if any(pattern.get("is_tba") for pattern in parsed_patterns):
        return "TBA"
    return " | ".join(pattern["days_raw"] for pattern in parsed_patterns)


def flattened_time(section: dict[str, Any]) -> str:
    parsed_patterns = section.get("parsed_meeting_patterns") or []
    if not parsed_patterns:
        return section.get("days_time", "")
    if any(pattern.get("is_tba") for pattern in parsed_patterns):
        return "TBA"
    return " | ".join(pattern["time"] for pattern in parsed_patterns)


def first_non_tba_instructor(section: dict[str, Any]) -> str:
    patterns = section.get("meeting_patterns") or []
    for pattern in patterns:
        instructor = pattern.get("instructor", "").strip()
        if instructor and instructor.upper() != "TBA":
            return instructor
    return section.get("instructor", "TBA")


def first_non_tba_room(section: dict[str, Any]) -> str:
    patterns = section.get("meeting_patterns") or []
    for pattern in patterns:
        room = pattern.get("room", "").strip()
        if room and room.upper() != "TBA":
            return room
    return section.get("room", "")


def serialize_section(section: dict[str, Any]) -> dict[str, Any]:
    payload = dict(section)
    return payload
