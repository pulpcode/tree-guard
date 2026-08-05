#!/usr/bin/env python3
"""Run one non-semantic H2 CPU smoke without loading experiment data."""

from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from pathlib import Path

from treeguard.local_embedding_provider import (
    LocalBgeH2EmbeddingProvider,
    LocalEmbeddingProviderError,
)
from treeguard.retrieval_hybrid_h2 import EMBEDDING_DIMENSIONS


SMOKE_VERSION = "treeguard.h2-local-runtime-smoke.v1"
FROZEN_BATCH_SIZE = 16
SMOKE_TEXT = "甲乙丙丁戊己庚辛壬癸" * 32


def run_smoke(snapshot_dir: Path) -> dict[str, object]:
    started = time.perf_counter()
    provider = LocalBgeH2EmbeddingProvider.from_local_snapshot(
        snapshot_dir,
        batch_size=FROZEN_BATCH_SIZE,
    )
    loaded = time.perf_counter()
    texts = tuple(SMOKE_TEXT for _ in range(FROZEN_BATCH_SIZE))
    first = provider.embed_document_batch(texts)
    second = provider.embed_document_batch(texts)
    finished = time.perf_counter()
    deterministic = first == second
    if not deterministic:
        raise LocalEmbeddingProviderError("H2_LOCAL_SMOKE_NONDETERMINISTIC")
    peak_rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if sys.platform != "darwin":
        peak_rss *= 1_024
    return {
        "report_version": SMOKE_VERSION,
        "status": "PASS",
        "batch_size": FROZEN_BATCH_SIZE,
        "dimensions": EMBEDDING_DIMENSIONS,
        "device": "cpu",
        "dtype": "float32",
        "deterministic_replay": True,
        "inference_call_count": provider.inference_call_count,
        "load_milliseconds": int((loaded - started) * 1_000),
        "two_batch_milliseconds": int((finished - loaded) * 1_000),
        "peak_rss_bytes": peak_rss,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = run_smoke(args.snapshot_dir)
    except LocalEmbeddingProviderError as error:
        report = {
            "report_version": SMOKE_VERSION,
            "status": "ERROR",
            "error_code": error.code,
        }
        print(json.dumps(report, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
