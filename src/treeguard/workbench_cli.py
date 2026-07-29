"""CLI entry point for the loopback-only TreeGuard workbench API."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

import uvicorn


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="treeguard-workbench")
    parser.add_argument("--port", type=int, default=8000)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.port < 1 or args.port > 65_535:
        parser = build_parser()
        parser.error("--port must be between 1 and 65535")
    uvicorn.run(
        "treeguard.web:app",
        host="127.0.0.1",
        port=args.port,
        access_log=False,
    )
    return 0


__all__ = ["build_parser", "main"]
