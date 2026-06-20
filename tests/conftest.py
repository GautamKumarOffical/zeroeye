"""
Shared fixtures and mocks for the Tent of Trials API test suite.

Provides test clients, mock data factories, and reusable fixtures
for testing the Python tools and API interactions.
"""

import json
import socket
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict, Generator
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# MOCK HTTP SERVER
# ---------------------------------------------------------------------------

class MockHealthHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler that returns configurable health responses."""

    health_response: Dict[str, Any] = {
        "status": "ok",
        "version": "0.1.0",
        "uptime_seconds": 12345,
        "services": {
            "registry": "healthy",
            "discovery": "healthy",
            "messaging": "healthy",
        },
    }
    status_code = 200

    def do_GET(self):
        body = json.dumps(self.health_response).encode()
        self.send_response(self.status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # silence request logs during tests


@pytest.fixture()
def mock_http_server() -> Generator[Dict[str, Any], None, None]:
    """Start a temporary HTTP server and yield its base URL.

    The server responds to every GET with a JSON health payload.
    Configure ``MockHealthHandler.health_response`` and
    ``MockHealthHandler.status_code`` before each request to alter
    the behaviour.
    """
    server = HTTPServer(("127.0.0.1", 0), MockHealthHandler)
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield {
            "host": host,
            "port": port,
            "base_url": f"http://{host}:{port}",
        }
    finally:
        server.shutdown()
        thread.join(timeout=5)


# ---------------------------------------------------------------------------
# SERVICE CONFIGURATION FIXTURES
# ---------------------------------------------------------------------------

@pytest.fixture()
def service_configs() -> Dict[str, Dict[str, Any]]:
    """Return the canonical service endpoint definitions."""
    return {
        "backend": {"host": "localhost", "port": 8080, "path": "/health", "timeout": 5},
        "market": {"host": "localhost", "port": 8081, "path": "/health", "timeout": 5},
        "frailbox": {"host": "localhost", "port": 8082, "path": "/health", "timeout": 10},
        "frontend": {"host": "localhost", "port": 3000, "path": "/", "timeout": 5},
    }


@pytest.fixture()
def infrastructure_configs() -> Dict[str, Dict[str, Any]]:
    """Return infrastructure endpoint definitions."""
    return {
        "postgresql": {"host": "localhost", "port": 5432, "timeout": 5},
        "redis": {"host": "localhost", "port": 6379, "timeout": 5},
        "kafka": {"host": "localhost", "port": 9092, "timeout": 5},
    }


# ---------------------------------------------------------------------------
# MOCK DATA FACTORIES
# ---------------------------------------------------------------------------

@pytest.fixture()
def make_health_result():
    """Factory fixture that builds a health-check result dict."""
    def _make(
        status: str = "OK",
        detail: str = "All systems operational",
        code: int = 200,
        endpoint: str = "http://localhost:8080/health",
    ) -> Dict[str, Any]:
        return {
            "status": status,
            "detail": detail,
            "code": code,
            "endpoint": endpoint,
        }
    return _make


@pytest.fixture()
def make_latency_sample():
    """Factory fixture that builds a latency sample dict."""
    def _make(
        timestamp: float | None = None,
        duration: float = 45.0,
        status_code: int = 200,
        success: bool = True,
        error: str | None = None,
    ) -> Dict[str, Any]:
        return {
            "timestamp": timestamp or time.time(),
            "duration": duration,
            "status_code": status_code,
            "success": success,
            "error": error,
        }
    return _make


@pytest.fixture()
def make_order_payload():
    """Factory fixture that builds a valid order payload."""
    def _make(
        account_id: str = "acc-001",
        instrument_id: str = "btcusdt",
        side: str = "buy",
        order_type: str = "limit",
        price: float = 50000.0,
        quantity: float = 0.1,
        time_in_force: str = "gtc",
    ) -> Dict[str, Any]:
        return {
            "account_id": account_id,
            "instrument_id": instrument_id,
            "side": side,
            "type": order_type,
            "price": price,
            "quantity": quantity,
            "time_in_force": time_in_force,
        }
    return _make


@pytest.fixture()
def make_account_payload():
    """Factory fixture that builds a valid account payload."""
    def _make(
        account_id: str = "acc-001",
        amount: float = 1000.0,
        currency: str = "USD",
    ) -> Dict[str, Any]:
        return {
            "account_id": account_id,
            "amount": amount,
            "currency": currency,
        }
    return _make


@pytest.fixture()
def make_service_entry():
    """Factory fixture that builds a service entry dict matching the Rust struct."""
    def _make(
        service_id: str = "svc-001",
        service_name: str = "tent-backend",
        version: str = "0.1.0",
        endpoints: list[str] | None = None,
        metadata: Dict[str, str] | None = None,
        registered_at: int = 0,
        ttl: int = 30,
    ) -> Dict[str, Any]:
        return {
            "service_id": service_id,
            "service_name": service_name,
            "version": version,
            "endpoints": endpoints if endpoints is not None else ["http://localhost:8080"],
            "metadata": metadata if metadata is not None else {"runtime": "rust", "protocol": "grpc"},
            "registered_at": registered_at or int(time.time()),
            "ttl": ttl,
        }
    return _make


@pytest.fixture()
def make_event_envelope():
    """Factory fixture that builds an event envelope matching the Rust EventEnvelope."""
    def _make(
        event_type: str = "order.created",
        schema_version: int = 1,
        payload: Dict[str, Any] | None = None,
        source: str = "order-service",
        partition_key: str = "order-001",
    ) -> Dict[str, Any]:
        return {
            "event_id": "550e8400-e29b-41d4-a716-446655440000",
            "event_type": event_type,
            "schema_version": schema_version,
            "payload": payload or {},
            "metadata": {
                "trace_id": "trace-001",
                "span_id": "span-001",
                "correlation_id": None,
                "user_id": None,
                "organization_id": None,
                "request_id": None,
                "client_ip": None,
                "user_agent": None,
                "custom": {},
            },
            "source": source,
            "produced_at": "2025-01-01T00:00:00Z",
            "available_at": "2025-01-01T00:00:00Z",
            "partition_key": partition_key,
            "retention": {
                "retention_days": 90,
                "archive": False,
                "storage_tier": "Hot",
            },
        }
    return _make


# ---------------------------------------------------------------------------
# MOCK NETWORKING
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_tcp_port():
    """Context manager that mocks ``socket.create_connection``.

    Usage::

        with mock_tcp_port(open=True):
            status, detail, latency = check_tcp_port("localhost", 5432, 5)
            assert status == "OK"
    """
    class _MockPort:
        def __init__(self):
            self.open = True
            self.connect_called = False

        def __enter__(self):
            self._patch = patch("socket.create_connection", side_effect=self._connect)
            self._patch.start()
            return self

        def __exit__(self, *args):
            self._patch.stop()

        def _connect(self, address, timeout=5):
            self.connect_called = True
            if self.open:
                sock = MagicMock()
                sock.__enter__ = MagicMock(return_value=sock)
                sock.__exit__ = MagicMock(return_value=False)
                return sock
            raise ConnectionRefusedError

    return _MockPort


@pytest.fixture()
def mock_http_response():
    """Factory that returns a mock ``http.client.HTTPConnection``.

    Usage::

        with mock_http_response(status=200, body='{"status":"ok"}'):
            result = check_http_service("localhost", 8080, "/health", 5)
    """
    class _MockHTTP:
        def __init__(self):
            self.status = 200
            self.body = '{"status": "ok"}'
            self._patch = None

        def __enter__(self):
            self._patch = patch("http.client.HTTPConnection")
            conn_cls = self._patch.start()
            conn = MagicMock()
            conn_cls.return_value = conn

            resp = MagicMock()
            resp.status = self.status
            resp.read.return_value = self.body.encode()
            conn.getresponse.return_value = resp

            return self

        def __exit__(self, *args):
            if self._patch:
                self._patch.stop()

    factory = _MockHTTP()
    return factory


# ---------------------------------------------------------------------------
# CONNECTOR / BRIDGE FIXTURES
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_connector_config():
    """Return a dict that mirrors the Rust ConnectorConfig defaults."""
    return {
        "config_version": 3,
        "mode": "Synchronous",
        "features": 0,
        "max_concurrency": 1,
        "timeout_ms": 5000,
        "retry_count": 0,
        "retry_backoff_ms": 1000,
        "receive_buffer_size": 65536,
        "send_buffer_size": 65536,
        "max_message_size": 1048576,
        "encoding": "Binary",
        "compression": "None",
        "compression_level": -1,
        "default_priority": "Normal",
        "enable_checksum": False,
        "enable_encryption": False,
        "enable_audit": False,
    }


@pytest.fixture()
def mock_rpc_methods():
    """Return the RPC method ID map extracted from the Rust source."""
    return {
        "GET_INSTRUMENTS": 0x0001,
        "GET_ORDER_BOOK": 0x0002,
        "GET_TICKER": 0x0003,
        "GET_CANDLES": 0x0004,
        "GET_TRADES": 0x0005,
        "PLACE_ORDER": 0x0010,
        "CANCEL_ORDER": 0x0011,
        "GET_ORDER": 0x0012,
        "GET_ORDERS": 0x0013,
        "GET_POSITIONS": 0x0020,
        "GET_POSITION": 0x0021,
        "GET_ACCOUNT": 0x0030,
        "GET_ACCOUNT_TRANSACTIONS": 0x0031,
        "GET_MARKET_STATUS": 0x0040,
        "GET_NEWS": 0x0041,
        "GET_PORTFOLIO_SUMMARY": 0x0050,
        "GET_PERFORMANCE": 0x0051,
        "AUTHENTICATE": 0x0100,
        "GET_SESSION": 0x0101,
        "REFRESH_TOKEN": 0x0102,
        "GET_USER": 0x0110,
        "UPDATE_USER": 0x0111,
        "GET_PREFERENCES": 0x0120,
        "UPDATE_PREFERENCES": 0x0121,
        "HEALTH_CHECK": 0x1000,
        "GET_METRICS": 0x1001,
        "GET_CONFIG": 0x1002,
        "UPDATE_CONFIG": 0x1003,
        "GET_LOGS": 0x1004,
    }


# ---------------------------------------------------------------------------
# BENCHMARK FIXTURES
# ---------------------------------------------------------------------------

@pytest.fixture()
def benchmark_url(mock_http_server: Dict[str, Any]) -> str:
    """Return a full URL pointing at the mock HTTP server."""
    return f"{mock_http_server['base_url']}/health"
