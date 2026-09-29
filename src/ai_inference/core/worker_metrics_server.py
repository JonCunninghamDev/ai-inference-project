"""Private-only HTTP export for worker Prometheus metrics."""
from __future__ import annotations

import ipaddress
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from ai_inference.core.metrics import PROMETHEUS_CONTENT_TYPE, MetricsCollector


def validate_private_bind_host(host: str) -> str:
    """Require an explicit loopback or private IP literal.

    Hostnames, wildcard addresses, unspecified addresses, multicast, and public
    addresses are rejected to keep the worker metrics listener private by
    construction.
    """
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError(
            "worker metrics bind host must be an explicit loopback or private IP literal"
        ) from exc

    if address.is_unspecified or address.is_multicast:
        raise ValueError("worker metrics bind host cannot be wildcard or multicast")
    if not (address.is_loopback or address.is_private):
        raise ValueError("worker metrics bind host must be loopback or private")

    return host


class WorkerMetricsServer:
    """Serve one MetricsCollector at /metrics on a private bind address."""

    def __init__(
        self,
        metrics: MetricsCollector,
        *,
        host: str = "127.0.0.1",
        port: int = 9101,
    ) -> None:
        self.metrics = metrics
        self.host = validate_private_bind_host(host)
        if not (0 <= port <= 65535):
            raise ValueError("worker metrics port must be between 0 and 65535")
        self.port = port
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def bound_host(self) -> str:
        if self._server is None:
            return self.host
        return str(self._server.server_address[0])

    @property
    def bound_port(self) -> int:
        if self._server is None:
            return self.port
        return int(self._server.server_address[1])

    @property
    def running(self) -> bool:
        return self._server is not None and self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return

        metrics = self.metrics

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path != "/metrics":
                    self.send_response(HTTPStatus.NOT_FOUND)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return

                payload = metrics.render_prometheus().encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", PROMETHEUS_CONTENT_TYPE)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format: str, *args: object) -> None:
                del format, args

        server = ThreadingHTTPServer((self.host, self.port), Handler)
        server.daemon_threads = True
        self._server = server
        self._thread = threading.Thread(
            target=server.serve_forever,
            name="worker-metrics-server",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        server = self._server
        thread = self._thread
        if server is None:
            return

        server.shutdown()
        server.server_close()
        if thread is not None:
            thread.join(timeout=5)

        self._server = None
        self._thread = None
