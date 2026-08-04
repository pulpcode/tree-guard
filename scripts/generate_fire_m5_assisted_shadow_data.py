#!/usr/bin/env python3
"""Generate the independent clean-room M5 candidate staging dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fire_m5_data_common import M5DataError, write_dataset


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        manifest = write_dataset(args.output_dir)
    except M5DataError as exc:
        print(json.dumps({"status": "FAIL", "error_code": exc.code}, sort_keys=True))
        return 2
    print(
        json.dumps(
            {
                "status": "PASS",
                "dataset_ref": manifest["dataset_ref"],
                "node_count": manifest["node_count"],
                "candidate_count": manifest["candidate_count"],
                "model_called": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
