#!/usr/bin/env python3
"""Create a non-authoritative Codex Silver precheck artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fire_m5_data_common import (
    M5DataError,
    build_codex_silver_review,
    write_json_new,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        review = build_codex_silver_review(args.dataset_dir)
        write_json_new(args.output, review)
    except (M5DataError, OSError) as exc:
        code = exc.code if isinstance(exc, M5DataError) else "M5_FILE_IO_FAILED"
        print(json.dumps({"status": "FAIL", "error_code": code}, sort_keys=True))
        return 2
    print(
        json.dumps(
            {
                "status": "PASS",
                "quality_tier": review["quality_tier"],
                "reviewed_candidate_count": review["reviewed_candidate_count"],
                "blocking_finding_count": review["blocking_finding_count"],
                "execution_eligible": review["execution_eligible"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
