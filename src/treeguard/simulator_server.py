"""Loopback-only HTTP shell around the pure contract simulator."""

from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from treeguard.simulator import (
    MAX_SIMULATOR_REQUEST_BYTES,
    SIMULATOR_CONTRACT_STATUS,
    ContractSimulator,
)


class SimulatorHTTPServer(ThreadingHTTPServer):
    """HTTP server that owns one immutable-development simulator config."""

    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        simulator: ContractSimulator,
    ) -> None:
        self.simulator = simulator
        super().__init__(server_address, SimulatorRequestHandler)


class SimulatorRequestHandler(BaseHTTPRequestHandler):
    """Translate bounded HTTP input into pure simulator requests."""

    server: SimulatorHTTPServer

    def do_GET(self) -> None:
        self._respond(body=b"")

    def do_POST(self) -> None:
        content_length = self.headers.get("Content-Length")
        try:
            length = int(content_length) if content_length is not None else -1
        except ValueError:
            length = -1
        if length < 0:
            self.send_error(411)
            return
        if length > MAX_SIMULATOR_REQUEST_BYTES:
            self.send_error(413)
            return
        body = self.rfile.read(length)
        self._respond(body=body)

    def send_error(
        self,
        code: int,
        message: str | None = None,
        explain: str | None = None,
    ) -> None:
        """Return bounded JSON for parser and unsupported-method failures."""

        error_code = (
            "SIMULATOR_CONTENT_LENGTH_REQUIRED"
            if code == 411
            else (
                "SIMULATOR_REQUEST_TOO_LARGE"
                if code == 413
                else "SIMULATOR_HTTP_PROTOCOL_REJECTED"
            )
        )
        body = json.dumps(
            {
                "schema_version": "provisional-simulator-error.v1",
                "contract_status": SIMULATOR_CONTRACT_STATUS,
                "status": code,
                "message": "Simulator request rejected.",
                "error_code": error_code,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _respond(self, *, body: bytes) -> None:
        response = self.server.simulator.handle(
            method=self.command,
            target=self.path,
            headers={key: value for key, value in self.headers.items()},
            body=body,
        )
        if response.delay_seconds:
            time.sleep(response.delay_seconds)
        self.send_response(response.status_code)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(response.body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(response.body)
        except (BrokenPipeError, ConnectionResetError):
            return

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress request targets and headers from simulator diagnostics."""

        return


def create_simulator_server(
    *,
    port: int,
    simulator: ContractSimulator,
) -> SimulatorHTTPServer:
    if (
        not isinstance(port, int)
        or isinstance(port, bool)
        or port < 0
        or port > 65_535
    ):
        raise ValueError("simulator port is invalid")
    return SimulatorHTTPServer(("127.0.0.1", port), simulator)


__all__ = [
    "SimulatorHTTPServer",
    "SimulatorRequestHandler",
    "create_simulator_server",
]
