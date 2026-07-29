"""CLI for the provisional loopback contract simulator."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from treeguard.repository_client import (
    ProvisionalRepositoryClient,
    RepositoryClientConfig,
    RepositoryClientError,
)
from treeguard.simulator import (
    MAX_SIMULATOR_NODES,
    MIN_SIMULATOR_NODES,
    SIMULATOR_CATEGORY_ID,
    SIMULATOR_MODEL_SCENARIOS,
    SIMULATOR_RESOURCE_ID,
    ContractSimulator,
    SimulatorValidationError,
)
from treeguard.simulator_server import create_simulator_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="treeguard-contract-simulator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser(
        "serve",
        help="serve provisional repository and OpenAI contracts on loopback",
    )
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument(
        "--node-count",
        type=int,
        default=50,
        help=(
            f"fictional tree size ({MIN_SIMULATOR_NODES}-"
            f"{MAX_SIMULATOR_NODES})"
        ),
    )
    serve.add_argument(
        "--model-scenario",
        choices=sorted(SIMULATOR_MODEL_SCENARIOS),
        default="ready",
    )
    serve.add_argument("--delay-seconds", type=float, default=1.0)

    verify = subparsers.add_parser(
        "verify-repository",
        help="verify the four provisional read-only repository operations",
    )
    verify.add_argument("--base-url", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "serve":
        try:
            simulator = ContractSimulator(
                node_count=args.node_count,
                model_scenario=args.model_scenario,
                delay_seconds=args.delay_seconds,
            )
            server = create_simulator_server(
                port=args.port,
                simulator=simulator,
            )
        except (OSError, SimulatorValidationError, TypeError, ValueError):
            _print_error("SIMULATOR_START_REJECTED")
            return 2
        port = server.server_address[1]
        print(
            json.dumps(
                {
                    "report_version": "contract-simulator-server.v1",
                    "valid": True,
                    "status": "SERVING",
                    "contract_status": (
                        "PROVISIONAL_SIMULATOR_CONTRACT"
                    ),
                    "loopback_only": True,
                    "port": port,
                    "node_count": args.node_count,
                    "model_scenario": args.model_scenario,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            flush=True,
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0

    try:
        client = ProvisionalRepositoryClient(
            RepositoryClientConfig(base_url=args.base_url)
        )
        categories = client.list_categories()
        resources = client.list_resources(SIMULATOR_CATEGORY_ID)
        versions = client.list_versions(SIMULATOR_RESOURCE_ID)
        trees = [
            client.fetch_tree(
                SIMULATOR_RESOURCE_ID,
                version=item.version,
            )
            for item in versions
        ]
    except RepositoryClientError as exc:
        _print_error(exc.code)
        return 2
    print(
        json.dumps(
            {
                "report_version": "repository-simulator-check.v1",
                "valid": True,
                "status": "VERIFIED",
                "contract_status": "PROVISIONAL_SIMULATOR_CONTRACT",
                "category_count": len(categories),
                "resource_count": len(resources),
                "version_count": len(versions),
                "snapshot_count": len(trees),
                "node_count": sum(
                    len(result.tree.nodes)
                    for result in trees
                    if result.tree is not None
                ),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _print_error(code: str) -> None:
    print(
        json.dumps(
            {
                "report_version": "contract-simulator-error.v1",
                "valid": False,
                "status": "REJECTED",
                "error_code": code,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
