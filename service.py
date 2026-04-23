from pathlib import Path
from typing import Any

from filters import apply_filters, select_detail_candidates
from output import write_results
from scraper import enrich_sections_with_details, scrape_sections
from utils import ConfigError, build_runtime_config, get_live_discrepancy_notes


def run_schedule_search(
    config: dict[str, Any],
    *,
    output_dir: Path,
    subject_override: str | None = None,
) -> dict[str, Any]:
    runtime_config = build_runtime_config(config, subject_override)
    discrepancy_notes = get_live_discrepancy_notes(runtime_config)

    session, sections, subject_messages, warnings, term_label = scrape_sections(
        runtime_config
    )

    candidate_sections = select_detail_candidates(
        sections=sections,
        allowed_modalities=runtime_config["modality"],
        open_only=runtime_config["open_only"],
    )
    preliminary_matches, preliminary_tba = apply_filters(
        sections=candidate_sections,
        allowed_modalities=runtime_config["modality"],
        available_times=runtime_config["available_times"],
        open_only=runtime_config["open_only"],
    )
    detail_sections = dedupe_sections(preliminary_matches + preliminary_tba)
    enrich_sections_with_details(session, detail_sections)

    matched_sections, flagged_tba_sections = apply_filters(
        sections=detail_sections,
        allowed_modalities=runtime_config["modality"],
        available_times=runtime_config["available_times"],
        open_only=runtime_config["open_only"],
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    write_results(matched_sections, flagged_tba_sections, warnings, output_dir)

    return {
        "runtime_config": runtime_config,
        "matched_sections": matched_sections,
        "flagged_tba_sections": flagged_tba_sections,
        "subject_messages": subject_messages,
        "warnings": warnings,
        "term_label": term_label,
        "discrepancy_notes": discrepancy_notes,
        "output_dir": output_dir,
    }


def dedupe_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for section in sections:
        deduped[section["class_number"]] = section
    return list(deduped.values())
