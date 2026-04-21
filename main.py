import argparse
import sys
from pathlib import Path

from filters import apply_filters, select_detail_candidates
from output import print_results, write_results
from scraper import enrich_sections_with_details, scrape_sections
from utils import (
    ConfigError,
    build_runtime_config,
    load_config,
    warn_live_discrepancies,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find Hunter College course sections that fit your schedule."
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to the config file. Defaults to config.json.",
    )
    parser.add_argument(
        "--subject",
        help="Override config.json and only search a single subject code.",
    )
    parser.add_argument(
        "--output",
        default=".",
        help="Folder for results.json and results.csv. Defaults to the current directory.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        config = load_config(Path(args.config))
        runtime_config = build_runtime_config(config, args.subject)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    warn_live_discrepancies(runtime_config)

    try:
        session, sections, subject_messages, warnings, term_label = scrape_sections(
            runtime_config
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

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

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_results(matched_sections, flagged_tba_sections, warnings, output_dir)
    print_results(
        matched_sections=matched_sections,
        flagged_tba_sections=flagged_tba_sections,
        subject_messages=subject_messages,
        warnings=warnings,
        requested_subjects=runtime_config["course_codes"],
        term_label=term_label,
    )
    return 0


def dedupe_sections(sections: list[dict]) -> list[dict]:
    deduped: dict[str, dict] = {}
    for section in sections:
        deduped[section["class_number"]] = section
    return list(deduped.values())


if __name__ == "__main__":
    raise SystemExit(main())
