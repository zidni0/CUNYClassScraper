import threading
import webbrowser
from collections import defaultdict
from pathlib import Path
from typing import Any

from flask import Flask, abort, render_template, request, send_from_directory

from output import first_non_tba_instructor, first_non_tba_room
from service import run_schedule_search
from utils import ConfigError, DAY_NAMES, load_config


APP_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = APP_ROOT / "config.json"
UI_OUTPUT_DIR = APP_ROOT / "ui_output" / "latest"
DOWNLOADABLE_FILES = {"results.json", "results.csv", "warnings.log"}
MODALITY_OPTIONS = [
    ("online", "Online"),
    ("in-person", "In Person"),
    ("hybrid-synchronous", "Hybrid Synchronous"),
    ("hybrid-asynchronous", "Hybrid Asynchronous"),
    ("online-synchronous", "Online Synchronous"),
    ("online-asynchronous", "Online Asynchronous"),
]

app = Flask(__name__)


@app.context_processor
def template_helpers():
    return {
        "format_section_time": format_section_time,
        "display_room": first_non_tba_room,
        "display_instructor": first_non_tba_instructor,
    }


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        form_data = config_to_form_data(load_config(DEFAULT_CONFIG_PATH))
        return render_template(
            "index.html",
            form_data=form_data,
            modality_options=MODALITY_OPTIONS,
            day_names=DAY_NAMES,
            results=None,
            error_message=None,
        )

    form_data = request.form.to_dict(flat=True)
    form_data["modality"] = request.form.getlist("modality")

    try:
        config = form_to_config(request.form)
        result = run_schedule_search(config, output_dir=UI_OUTPUT_DIR)
    except (ConfigError, RuntimeError) as exc:
        return render_template(
            "index.html",
            form_data=normalize_form_data(form_data),
            modality_options=MODALITY_OPTIONS,
            day_names=DAY_NAMES,
            results=None,
            error_message=str(exc),
        )

    grouped_matches = group_sections(result["matched_sections"])
    grouped_tba = group_sections(result["flagged_tba_sections"])

    return render_template(
        "index.html",
        form_data=config_to_form_data(config),
        modality_options=MODALITY_OPTIONS,
        day_names=DAY_NAMES,
        results={
            "term_label": result["term_label"],
            "grouped_matches": grouped_matches,
            "grouped_tba": grouped_tba,
            "matched_count": len(result["matched_sections"]),
            "tba_count": len(result["flagged_tba_sections"]),
            "subject_messages": result["subject_messages"],
            "warnings": result["warnings"],
            "notes": result["discrepancy_notes"],
        },
        error_message=None,
    )


@app.route("/downloads/<path:filename>")
def download(filename: str):
    if filename not in DOWNLOADABLE_FILES:
        abort(404)
    return send_from_directory(UI_OUTPUT_DIR, filename, as_attachment=False)


def config_to_form_data(config: dict[str, Any]) -> dict[str, Any]:
    available_times = config.get("available_times", {})
    return {
        "term": config.get("term", ""),
        "course_codes": ", ".join(config.get("course_codes", [])),
        "modality": list(config.get("modality", [])),
        "open_only": bool(config.get("open_only", False)),
        "available_times": {
            day: ", ".join(available_times.get(day, [])) for day in DAY_NAMES
        },
    }


def normalize_form_data(form_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "term": form_data.get("term", ""),
        "course_codes": form_data.get("course_codes", ""),
        "modality": form_data.get("modality", []) or [],
        "open_only": form_data.get("open_only") == "on",
        "available_times": {
            day: form_data.get(f"time_{day.lower()}", "") for day in DAY_NAMES
        },
    }


def form_to_config(form: Any) -> dict[str, Any]:
    course_codes = [
        item.strip().upper()
        for item in form.get("course_codes", "").split(",")
        if item.strip()
    ]
    modality = [item.strip() for item in form.getlist("modality") if item.strip()]
    available_times = {
        day: parse_day_ranges(form.get(f"time_{day.lower()}", ""))
        for day in DAY_NAMES
    }

    return {
        "institution": "HUN01",
        "term": form.get("term", "").strip(),
        "course_codes": course_codes,
        "modality": modality,
        "available_times": available_times,
        "open_only": form.get("open_only") == "on",
    }


def parse_day_ranges(raw_value: str) -> list[str]:
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def group_sections(sections: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for section in sections:
        subject = section.get("course", "").split(" ", 1)[0]
        grouped[subject].append(section)

    ordered_groups: list[tuple[str, list[dict[str, Any]]]] = []
    for subject in sorted(grouped):
        ordered_groups.append((subject, grouped[subject]))
    return ordered_groups


def format_section_time(section: dict[str, Any]) -> str:
    parsed_patterns = section.get("parsed_meeting_patterns") or []
    if not parsed_patterns:
        return section.get("days_time", "TBA")
    if any(pattern.get("is_tba") for pattern in parsed_patterns):
        return "TBA / manual review"
    return " | ".join(
        f"{pattern['days_raw']} {pattern['time']}" for pattern in parsed_patterns
    )


def open_browser() -> None:
    webbrowser.open("http://127.0.0.1:5000")


if __name__ == "__main__":
    UI_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    threading.Timer(1.0, open_browser).start()
    app.run(host="127.0.0.1", port=5000, debug=False)
