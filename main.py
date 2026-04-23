import argparse
import sys
from pathlib import Path

from output import print_results
from service import run_schedule_search
from utils import (
    ConfigError,
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
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    try:
        result = run_schedule_search(
            config,
            output_dir=Path(args.output),
            subject_override=args.subject,
        )
    except (RuntimeError, ConfigError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    warn_live_discrepancies(result["runtime_config"])
    print_results(
        matched_sections=result["matched_sections"],
        flagged_tba_sections=result["flagged_tba_sections"],
        subject_messages=result["subject_messages"],
        warnings=result["warnings"],
        requested_subjects=result["runtime_config"]["course_codes"],
        term_label=result["term_label"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
