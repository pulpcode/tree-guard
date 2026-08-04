#!/usr/bin/env python3
"""Replay and preflight the M5 candidate staging dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fire_m5_data_common import M5DataError, preflight_dataset, write_json_new


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = preflight_dataset(args.dataset_dir)
        if args.output is not None:
            write_json_new(args.output, report)
    except (M5DataError, OSError) as exc:
        code = exc.code if isinstance(exc, M5DataError) else "M5_FILE_IO_FAILED"
        print(json.dumps({"status": "FAIL", "error_code": code}, sort_keys=True))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
