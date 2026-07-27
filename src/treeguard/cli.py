"""Aggregate-only conformance CLI for local, offline validation."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from treeguard.adapter import TreeFormatError, load_tree_export


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="treeguard")
    parser.add_argument("tree_file", help="path to a tree export JSON")
    parser.add_argument(
        "--allow-curl-transcript",
        action="store_true",
        help="explicitly accept one curl command line followed by a JSON response",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = load_tree_export(
            args.tree_file,
            allow_curl_transcript=args.allow_curl_transcript,
        )
    except TreeFormatError:
        report = {
            "report_version": "treeguard-conformance.v1",
            "valid": False,
            "severity_counts": {"ERROR": 1, "WARNING": 0},
            "issue_code_counts": {"TREE_FORMAT_ERROR": 1},
        }
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 2

    print(json.dumps(result.conformance_report(), ensure_ascii=False, sort_keys=True))
    return 0 if result.is_valid else 2
