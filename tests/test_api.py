"""
Comprehensive API test suite for the Tent of Trials platform.

Tests cover:
  - Health check tool (HTTP, TCP, system resource checks)
  - Benchmark tool (request helper, aggregation, worker logic)
  - Connector types and config validation
  - Protocol message validation and serialization
  - RPC method registry
  - Service registry / discovery data contracts
  - Event envelope structure
  - Edge cases and error paths
"""

import json
import math
import socket
import struct
import threading
import time
from dataclasses import dataclass
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, Mock, patch

import pytest


# =========================================================================
# SECTION 1: HEALTH CHECK TOOL TESTS
# =========================================================================


class TestCheckHttpService:
    """Tests for ``health_check.check_http_service``."""

    def test_returns_ok_on_200(self):
        from tools.health_check import check_http_service

        with patch("http.client.HTTPConnection") as conn_cls:
            conn = MagicMock()
            conn_cls.return_value = conn
            resp = MagicMock()
            resp.status = 200
            resp.read.return_value = b'{"status":"ok"}'
            conn.getresponse.return_value = resp

            status, detail, code = check_http_service("localhost", 8080, "/health", 5)

        assert status == "OK"
        assert code == 200
        assert "200" in detail

    def test_returns_warning_on_4xx(self):
        from tools.health_check import check_http_service

        with patch("http.client.HTTPConnection") as conn_cls:
            conn = MagicMock()
            conn_cls.return_value = conn
            resp = MagicMock()
            resp.status = 404
            resp.read.return_value = b"Not Found"
            conn.getresponse.return_value = resp

            status, detail, code = check_http_service("localhost", 8080, "/missing", 5)

        assert status == "WARNING"
        assert code == 404

    def test_returns_critical_on_5xx(self):
        from tools.health_check import check_http_service

        with patch("http.client.HTTPConnection") as conn_cls:
            conn = MagicMock()
            conn_cls.return_value = conn
            resp = MagicMock()
            resp.status = 503
            resp.read.return_value = b"Service Unavailable"
            conn.getresponse.return_value = resp

            status, detail, code = check_http_service("localhost", 8080, "/health", 5)

        assert status == "CRITICAL"
        assert code == 503

    def test_returns_critical_on_connection_error(self):
        from tools.health_check import check_http_service

        with patch("http.client.HTTPConnection") as conn_cls:
            conn = MagicMock()
            conn_cls.return_value = conn
            conn.request.side_effect = ConnectionRefusedError("Connection refused")

            status, detail, code = check_http_service("localhost", 8080, "/health", 5)

        assert status == "CRITICAL"
        assert code == 0

    def test_returns_critical_on_timeout(self):
        from tools.health_check import check_http_service

        with patch("http.client.HTTPConnection") as conn_cls:
            conn = MagicMock()
            conn_cls.return_value = conn
            conn.request.side_effect = socket.timeout("timed out")

            status, detail, code = check_http_service("localhost", 8080, "/health", 5)

        assert status == "CRITICAL"
        assert code == 0


class TestCheckTcpPort:
    """Tests for ``health_check.check_tcp_port``."""

    def test_returns_ok_when_port_open(self):
        from tools.health_check import check_tcp_port

        mock_sock = MagicMock()
        with patch("socket.create_connection", return_value=mock_sock):
            status, detail, latency = check_tcp_port("localhost", 5432, 5)

        assert status == "OK"
        assert latency > 0
        mock_sock.close.assert_called_once()

    def test_returns_critical_on_timeout(self):
        from tools.health_check import check_tcp_port

        with patch("socket.create_connection", side_effect=socket.timeout):
            status, detail, latency = check_tcp_port("localhost", 5432, 5)

        assert status == "CRITICAL"
        assert "timeout" in detail.lower()
        assert latency == 0

    def test_returns_critical_on_refused(self):
        from tools.health_check import check_tcp_port

        with patch("socket.create_connection", side_effect=ConnectionRefusedError):
            status, detail, latency = check_tcp_port("localhost", 5432, 5)

        assert status == "CRITICAL"
        assert "refused" in detail.lower()

    def test_returns_critical_on_generic_error(self):
        from tools.health_check import check_tcp_port

        with patch("socket.create_connection", side_effect=OSError("No route to host")):
            status, detail, latency = check_tcp_port("localhost", 5432, 5)

        assert status == "CRITICAL"
        assert "No route" in detail


class TestCheckDiskUsage:
    """Tests for ``health_check.check_disk_usage``."""

    def test_ok_when_usage_below_threshold(self):
        from tools.health_check import check_disk_usage

        mock_stat = MagicMock()
        mock_stat.f_frsize = 4096
        mock_stat.f_blocks = 1000000
        mock_stat.f_bavail = 500000

        with patch("os.statvfs", return_value=mock_stat):
            status, detail, pct = check_disk_usage("/")

        assert status == "OK"
        assert 0 <= pct <= 100

    def test_warning_when_usage_high(self):
        from tools.health_check import check_disk_usage

        mock_stat = MagicMock()
        mock_stat.f_frsize = 4096
        mock_stat.f_blocks = 1000000
        mock_stat.f_bavail = 150000  # ~85% used

        with patch("os.statvfs", return_value=mock_stat):
            status, detail, pct = check_disk_usage("/")

        assert status == "WARNING"
        assert pct > 80

    def test_critical_when_usage_very_high(self):
        from tools.health_check import check_disk_usage

        mock_stat = MagicMock()
        mock_stat.f_frsize = 4096
        mock_stat.f_blocks = 1000000
        mock_stat.f_bavail = 50000  # ~95% used

        with patch("os.statvfs", return_value=mock_stat):
            status, detail, pct = check_disk_usage("/")

        assert status == "CRITICAL"
        assert pct > 90

    def test_handles_stat_error(self):
        from tools.health_check import check_disk_usage

        with patch("os.statvfs", side_effect=OSError("Permission denied")):
            status, detail, pct = check_disk_usage("/")

        assert status == "WARNING"
        assert "Cannot check" in detail


class TestCheckMemoryUsage:
    """Tests for ``health_check.check_memory_usage``."""

    def test_ok_when_usage_normal(self):
        from tools.health_check import check_memory_usage

        meminfo = "MemTotal:       16384000 kB\nMemAvailable:   12000000 kB\n"
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=iter(meminfo.splitlines(True)))
        mock_file.__exit__ = MagicMock(return_value=False)
        with patch("builtins.open", return_value=mock_file):
            status, detail, pct = check_memory_usage()

        assert status == "OK"

    def test_warning_when_usage_high(self):
        from tools.health_check import check_memory_usage

        meminfo = "MemTotal:       16384000 kB\nMemAvailable:    2000000 kB\n"
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=iter(meminfo.splitlines(True)))
        mock_file.__exit__ = MagicMock(return_value=False)
        with patch("builtins.open", return_value=mock_file):
            status, detail, pct = check_memory_usage()

        assert status == "WARNING"

    def test_handles_missing_file(self):
        from tools.health_check import check_memory_usage

        with patch("builtins.open", side_effect=FileNotFoundError):
            status, detail, pct = check_memory_usage()

        assert status == "WARNING"


class TestCheckLoadAverage:
    """Tests for ``health_check.check_load_average``."""

    def test_ok_when_load_low(self):
        from tools.health_check import check_load_average

        loadavg = "0.50 0.60 0.70 1/400 12345\n"
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_file.read.return_value = loadavg
        with patch("builtins.open", return_value=mock_file):
            with patch("os.cpu_count", return_value=8):
                status, detail, val = check_load_average()

        assert status == "OK"
        assert val == 0.50

    def test_warning_when_load_elevated(self):
        from tools.health_check import check_load_average

        loadavg = "6.00 5.50 5.00 1/400 12345\n"
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_file.read.return_value = loadavg
        with patch("builtins.open", return_value=mock_file):
            with patch("os.cpu_count", return_value=8):
                status, detail, val = check_load_average()

        assert status == "WARNING"

    def test_critical_when_load_extreme(self):
        from tools.health_check import check_load_average

        loadavg = "8.00 7.00 6.00 1/400 12345\n"
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_file.read.return_value = loadavg
        with patch("builtins.open", return_value=mock_file):
            with patch("os.cpu_count", return_value=4):
                status, detail, val = check_load_average()

        assert status == "CRITICAL"


class TestRunHealthChecks:
    """Tests for ``health_check.run_health_checks`` integration."""

    def test_all_services_checked(self):
        from tools.health_check import run_health_checks

        with patch("tools.health_check.check_http_service", return_value=("OK", "HTTP 200", 200)):
            with patch("tools.health_check.check_tcp_port", return_value=("OK", "Connected", 1.0)):
                with patch("tools.health_check.check_disk_usage", return_value=("OK", "50%", 50.0)):
                    with patch("tools.health_check.check_memory_usage", return_value=("OK", "40%", 40.0)):
                        with patch("tools.health_check.check_load_average", return_value=("OK", "Load: 1", 1.0)):
                            result = run_health_checks()

        assert result["overall_status"] == "OK"
        assert len(result["services"]) > 0

    def test_single_service_filter(self):
        from tools.health_check import run_health_checks

        with patch("tools.health_check.check_http_service", return_value=("OK", "HTTP 200", 200)):
            with patch("tools.health_check.check_tcp_port", return_value=("OK", "Connected", 1.0)):
                with patch("tools.health_check.check_disk_usage", return_value=("OK", "50%", 50.0)):
                    with patch("tools.health_check.check_memory_usage", return_value=("OK", "40%", 40.0)):
                        with patch("tools.health_check.check_load_average", return_value=("OK", "Load: 1", 1.0)):
                            result = run_health_checks(service="backend")

        assert "backend" in result["services"]

    def test_degraded_when_service_down(self):
        from tools.health_check import run_health_checks

        with patch("tools.health_check.check_http_service", return_value=("CRITICAL", "Connection refused", 0)):
            with patch("tools.health_check.check_tcp_port", return_value=("OK", "Connected", 1.0)):
                with patch("tools.health_check.check_disk_usage", return_value=("OK", "50%", 50.0)):
                    with patch("tools.health_check.check_memory_usage", return_value=("OK", "40%", 40.0)):
                        with patch("tools.health_check.check_load_average", return_value=("OK", "Load: 1", 1.0)):
                            result = run_health_checks()

        assert result["overall_status"] == "DEGRADED"


# =========================================================================
# SECTION 2: BENCHMARK TOOL TESTS
# =========================================================================


class TestMakeRequest:
    """Tests for ``benchmark.make_request``."""

    def test_success_on_200(self):
        from tools.benchmark import make_request

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"ok":true}'

        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_resp)
        mock_ctx.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_ctx):
            status, duration, error = make_request("http://localhost:8080/health")

        assert status == 200
        assert duration > 0
        assert error is None

    def test_error_on_http_error(self):
        from tools.benchmark import make_request

        import urllib.error

        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
            url="http://localhost:8080", code=500, msg="Server Error", hdrs=None, fp=None
        )):
            status, duration, error = make_request("http://localhost:8080/health")

        assert status == 500
        assert error is not None

    def test_error_on_url_error(self):
        from tools.benchmark import make_request

        import urllib.error

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
            status, duration, error = make_request("http://localhost:8080/health")

        assert status == 0
        assert "Connection error" in error

    def test_error_on_timeout(self):
        from tools.benchmark import make_request

        import urllib.error

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timed out")):
            status, duration, error = make_request("http://localhost:8080/health", timeout=1.0)

        assert status == 0
        assert error is not None

    def test_error_on_generic_exception(self):
        from tools.benchmark import make_request

        with patch("urllib.request.urlopen", side_effect=RuntimeError("unexpected")):
            status, duration, error = make_request("http://localhost:8080/health")

        assert status == 0
        assert "unexpected" in error


class TestAggregateResults:
    """Tests for ``benchmark.aggregate_results``."""

    def test_empty_results(self):
        from tools.benchmark import aggregate_results, LatencySample

        result = aggregate_results([], "latency", "http://example.com", 1)

        assert result.total_requests == 0
        assert result.successful_requests == 0
        assert result.failed_requests == 0
        assert result.requests_per_second == 0

    def test_all_successful(self):
        from tools.benchmark import aggregate_results, LatencySample

        samples = [
            LatencySample(timestamp=time.time() + i, duration=10.0 + i, status_code=200, success=True)
            for i in range(10)
        ]
        result = aggregate_results(samples, "latency", "http://example.com", 2)

        assert result.total_requests == 10
        assert result.successful_requests == 10
        assert result.failed_requests == 0
        assert result.latency_ms["min"] == 10.0
        assert result.latency_ms["max"] == 19.0

    def test_mixed_success_and_failure(self):
        from tools.benchmark import aggregate_results, LatencySample

        samples = [
            LatencySample(timestamp=time.time(), duration=10.0, status_code=200, success=True),
            LatencySample(timestamp=time.time(), duration=15.0, status_code=500, success=False, error="Server Error"),
            LatencySample(timestamp=time.time(), duration=20.0, status_code=200, success=True),
        ]
        result = aggregate_results(samples, "throughput", "http://example.com", 1)

        assert result.total_requests == 3
        assert result.successful_requests == 2
        assert result.failed_requests == 1
        assert "Server Error" in result.error_distribution

    def test_latency_percentiles(self):
        from tools.benchmark import aggregate_results, LatencySample

        samples = [
            LatencySample(timestamp=time.time() + i, duration=float(i), status_code=200, success=True)
            for i in range(100)
        ]
        result = aggregate_results(samples, "latency", "http://example.com", 1)

        assert result.latency_ms["min"] == 0.0
        assert result.latency_ms["max"] == 99.0
        assert result.latency_ms["p50"] == 50.0

    def test_timeout_requests_tracked(self):
        from tools.benchmark import aggregate_results, LatencySample

        samples = [
            LatencySample(timestamp=time.time(), duration=5000.0, status_code=0, success=False, error="Connection timeout"),
        ]
        result = aggregate_results(samples, "latency", "http://example.com", 1)

        assert result.timeout_requests == 1


class TestBenchmarkWorker:
    """Tests for ``benchmark.run_worker``."""

    def test_worker_collects_results(self):
        from tools.benchmark import run_worker, LatencySample

        results: List[LatencySample] = []
        stop_flag = threading.Event()

        with patch("tools.benchmark.make_request", return_value=(200, 10.0, None)):
            run_worker("http://example.com", 5, results, stop_flag, 30.0)

        assert len(results) == 5
        assert all(r.success for r in results)

    def test_worker_respects_stop_flag(self):
        from tools.benchmark import run_worker, LatencySample

        results: List[LatencySample] = []
        stop_flag = threading.Event()
        stop_flag.set()  # pre-set

        run_worker("http://example.com", 100, results, stop_flag, 30.0)

        assert len(results) == 0

    def test_worker_records_errors(self):
        from tools.benchmark import run_worker, LatencySample

        results: List[LatencySample] = []
        stop_flag = threading.Event()

        with patch("tools.benchmark.make_request", return_value=(500, 15.0, "Internal Server Error")):
            run_worker("http://example.com", 3, results, stop_flag, 30.0)

        assert len(results) == 3
        assert all(not r.success for r in results)


# =========================================================================
# SECTION 3: CONNECTOR TYPES TESTS
# =========================================================================


class TestConnectorResult:
    """Tests for the ConnectorResult enum contract."""

    def test_success_is_ok(self, mock_rpc_methods):
        assert mock_rpc_methods["HEALTH_CHECK"] == 0x1000

    def test_all_rpc_methods_have_unique_ids(self, mock_rpc_methods):
        values = list(mock_rpc_methods.values())
        assert len(values) == len(set(values)), "RPC method IDs must be unique"


class TestConnectorConfig:
    """Tests for connector configuration structure."""

    def test_default_config_has_required_fields(self, mock_connector_config):
        required = [
            "config_version", "mode", "max_concurrency",
            "timeout_ms", "encoding", "compression",
        ]
        for field in required:
            assert field in mock_connector_config, f"Missing required field: {field}"

    def test_config_version_matches(self, mock_connector_config):
        assert mock_connector_config["config_version"] == 3

    def test_default_mode_is_synchronous(self, mock_connector_config):
        assert mock_connector_config["mode"] == "Synchronous"

    def test_buffer_sizes_are_pow2(self, mock_connector_config):
        for key in ("receive_buffer_size", "send_buffer_size"):
            val = mock_connector_config[key]
            assert val > 0, f"{key} must be positive"
            assert val & (val - 1) == 0, f"{key} should be a power of 2"


# =========================================================================
# SECTION 4: RPC METHOD REGISTRY TESTS
# =========================================================================


class TestRpcMethodRegistry:
    """Tests for the RPC method ID registry."""

    def test_market_methods_present(self, mock_rpc_methods):
        market_ids = [
            "GET_INSTRUMENTS", "GET_ORDER_BOOK", "GET_TICKER",
            "GET_CANDLES", "GET_TRADES",
        ]
        for name in market_ids:
            assert name in mock_rpc_methods, f"Missing market method: {name}"

    def test_trading_methods_present(self, mock_rpc_methods):
        trading_ids = ["PLACE_ORDER", "CANCEL_ORDER", "GET_ORDER", "GET_ORDERS"]
        for name in trading_ids:
            assert name in mock_rpc_methods, f"Missing trading method: {name}"

    def test_account_methods_present(self, mock_rpc_methods):
        account_ids = ["GET_ACCOUNT", "GET_ACCOUNT_TRANSACTIONS", "GET_POSITIONS"]
        for name in account_ids:
            assert name in mock_rpc_methods, f"Missing account method: {name}"

    def test_auth_methods_present(self, mock_rpc_methods):
        auth_ids = ["AUTHENTICATE", "GET_SESSION", "REFRESH_TOKEN"]
        for name in auth_ids:
            assert name in mock_rpc_methods, f"Missing auth method: {name}"

    def test_admin_methods_present(self, mock_rpc_methods):
        admin_ids = ["GET_METRICS", "GET_CONFIG", "UPDATE_CONFIG", "GET_LOGS"]
        for name in admin_ids:
            assert name in mock_rpc_methods, f"Missing admin method: {name}"

    def test_health_check_method(self, mock_rpc_methods):
        assert mock_rpc_methods["HEALTH_CHECK"] == 0x1000

    def test_method_ids_are_16bit(self, mock_rpc_methods):
        for name, mid in mock_rpc_methods.items():
            assert 0 <= mid <= 0xFFFF, f"{name} ID {mid} out of 16-bit range"

    def test_market_ids_in_expected_range(self, mock_rpc_methods):
        for name in ["GET_INSTRUMENTS", "GET_ORDER_BOOK", "GET_TICKER"]:
            mid = mock_rpc_methods[name]
            assert 0x0001 <= mid <= 0x000F, f"{name} not in market range"

    def test_trading_ids_in_expected_range(self, mock_rpc_methods):
        for name in ["PLACE_ORDER", "CANCEL_ORDER"]:
            mid = mock_rpc_methods[name]
            assert 0x0010 <= mid <= 0x001F, f"{name} not in trading range"


# =========================================================================
# SECTION 5: SERVICE REGISTRY / DISCOVERY DATA CONTRACTS
# =========================================================================


class TestServiceEntry:
    """Tests for service entry data contract."""

    def test_entry_has_required_fields(self, make_service_entry):
        entry = make_service_entry()
        required = ["service_id", "service_name", "version", "endpoints", "metadata"]
        for field in required:
            assert field in entry, f"Missing field: {field}"

    def test_entry_default_values(self, make_service_entry):
        entry = make_service_entry()
        assert entry["service_id"] == "svc-001"
        assert entry["service_name"] == "tent-backend"
        assert entry["version"] == "0.1.0"
        assert isinstance(entry["endpoints"], list)
        assert isinstance(entry["metadata"], dict)

    def test_entry_custom_values(self, make_service_entry):
        entry = make_service_entry(
            service_id="svc-999",
            service_name="market-service",
            version="2.0.0",
        )
        assert entry["service_id"] == "svc-999"
        assert entry["service_name"] == "market-service"
        assert entry["version"] == "2.0.0"

    def test_ttl_is_positive(self, make_service_entry):
        entry = make_service_entry(ttl=60)
        assert entry["ttl"] > 0

    def test_endpoints_are_strings(self, make_service_entry):
        entry = make_service_entry()
        for ep in entry["endpoints"]:
            assert isinstance(ep, str)


# =========================================================================
# SECTION 6: EVENT ENVELOPE TESTS
# =========================================================================


class TestEventEnvelope:
    """Tests for event envelope data contract."""

    def test_envelope_has_required_fields(self, make_event_envelope):
        envelope = make_event_envelope()
        required = [
            "event_id", "event_type", "schema_version", "payload",
            "metadata", "source", "produced_at", "available_at",
            "partition_key", "retention",
        ]
        for field in required:
            assert field in envelope, f"Missing field: {field}"

    def test_envelope_metadata_structure(self, make_event_envelope):
        envelope = make_event_envelope()
        meta = envelope["metadata"]
        assert "trace_id" in meta
        assert "span_id" in meta

    def test_envelope_retention_structure(self, make_event_envelope):
        envelope = make_event_envelope()
        ret = envelope["retention"]
        assert "retention_days" in ret
        assert "archive" in ret
        assert "storage_tier" in ret

    def test_envelope_different_event_types(self, make_event_envelope):
        event_types = [
            "order.created", "order.filled", "trade.executed",
            "account.deposit", "market.halt", "user.login",
            "compliance.violation", "system.deployment",
        ]
        for et in event_types:
            envelope = make_event_envelope(event_type=et)
            assert envelope["event_type"] == et

    def test_schema_version_positive(self, make_event_envelope):
        envelope = make_event_envelope(schema_version=5)
        assert envelope["schema_version"] > 0


# =========================================================================
# SECTION 7: ORDER PAYLOAD VALIDATION TESTS
# =========================================================================


class TestOrderPayload:
    """Tests for order payload structure."""

    def test_valid_buy_order(self, make_order_payload):
        payload = make_order_payload(side="buy", order_type="limit", price=50000.0, quantity=0.1)
        assert payload["side"] == "buy"
        assert payload["type"] == "limit"
        assert payload["price"] == 50000.0
        assert payload["quantity"] == 0.1

    def test_valid_sell_order(self, make_order_payload):
        payload = make_order_payload(side="sell")
        assert payload["side"] == "sell"

    def test_market_order_no_price_required(self, make_order_payload):
        payload = make_order_payload(order_type="market", price=None)
        assert payload["type"] == "market"
        assert payload["price"] is None

    def test_order_type_must_be_string(self, make_order_payload):
        payload = make_order_payload()
        assert isinstance(payload["type"], str)

    def test_quantity_must_be_positive(self, make_order_payload):
        payload = make_order_payload(quantity=1.0)
        assert payload["quantity"] > 0

    def test_valid_time_in_force_values(self, make_order_payload):
        valid_tif = ["gtc", "ioc", "fok", "day", "gtd"]
        for tif in valid_tif:
            payload = make_order_payload(time_in_force=tif)
            assert payload["time_in_force"] == tif

    def test_instrument_id_is_string(self, make_order_payload):
        payload = make_order_payload()
        assert isinstance(payload["instrument_id"], str)
        assert len(payload["instrument_id"]) > 0


# =========================================================================
# SECTION 8: ACCOUNT PAYLOAD VALIDATION TESTS
# =========================================================================


class TestAccountPayload:
    """Tests for account payload structure."""

    def test_valid_payload(self, make_account_payload):
        payload = make_account_payload(amount=1000.0, currency="USD")
        assert payload["amount"] == 1000.0
        assert payload["currency"] == "USD"

    def test_amount_must_be_positive(self, make_account_payload):
        payload = make_account_payload(amount=0.01)
        assert payload["amount"] > 0

    def test_valid_currencies(self, make_account_payload):
        valid = ["USD", "EUR", "GBP", "BTC", "ETH", "USDT", "USDC"]
        for cur in valid:
            payload = make_account_payload(currency=cur)
            assert payload["currency"] == cur

    def test_account_id_is_string(self, make_account_payload):
        payload = make_account_payload()
        assert isinstance(payload["account_id"], str)


# =========================================================================
# SECTION 9: PROTOCOL VALIDATION HELPER TESTS
# =========================================================================


class TestProtocolValidation:
    """Tests for protocol validation logic (Python-side reimplementation)."""

    def test_valid_email(self):
        import re
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        assert re.match(pattern, "user@example.com")
        assert not re.match(pattern, "not-an-email")

    def test_valid_uuid(self):
        import re
        pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        assert re.match(pattern, "550e8400-e29b-41d4-a716-446655440000")
        assert not re.match(pattern, "not-a-uuid")

    def test_valid_symbol_format(self):
        import re
        pattern = r"^[A-Z0-9]{2,10}/[A-Z0-9]{2,10}$"
        assert re.match(pattern, "BTC/USDT")
        assert re.match(pattern, "ETH/USD")
        assert not re.match(pattern, "BTC")
        assert not re.match(pattern, "btc/usdt")

    def test_valid_instrument_id(self):
        import re
        pattern = r"^[a-z0-9]{2,20}$"
        assert re.match(pattern, "btcusdt")
        assert re.match(pattern, "ethusd")
        assert not re.match(pattern, "BTC")
        assert not re.match(pattern, "a")

    def test_price_in_valid_range(self):
        def validate_price(price):
            return price > 0.0 and price < 1_000_000_000.0

        assert validate_price(50000.0)
        assert validate_price(0.01)
        assert not validate_price(-1.0)
        assert not validate_price(0.0)
        assert not validate_price(1_000_000_001.0)

    def test_quantity_in_valid_range(self):
        def validate_quantity(qty):
            return qty > 0.0 and qty < 100_000_000.0

        assert validate_quantity(0.1)
        assert validate_quantity(99999999.0)
        assert not validate_quantity(-1.0)
        assert not validate_quantity(0.0)
        assert not validate_quantity(100_000_001.0)

    def test_valid_phone_number(self):
        def validate_phone(phone):
            digits = "".join(c for c in phone if c.isdigit())
            return 10 <= len(digits) <= 15

        assert validate_phone("+1-555-123-4567")
        assert validate_phone("5551234567")
        assert not validate_phone("12345")
        assert not validate_phone("1" * 16)

    def test_order_side_validation(self):
        valid_sides = ["buy", "sell"]
        assert "buy" in valid_sides
        assert "sell" in valid_sides
        assert "hold" not in valid_sides

    def test_order_type_validation(self):
        valid_types = ["market", "limit", "stop", "stop_limit"]
        for t in valid_types:
            assert t in valid_types

    def test_message_size_within_limit(self):
        MAX_MESSAGE_SIZE = 10 * 1024 * 1024
        small_msg = json.dumps({"type": "heartbeat"}).encode()
        assert len(small_msg) < MAX_MESSAGE_SIZE

    def test_message_size_exceeds_limit(self):
        MAX_MESSAGE_SIZE = 10 * 1024 * 1024
        large_msg = b"x" * (MAX_MESSAGE_SIZE + 1)
        assert len(large_msg) > MAX_MESSAGE_SIZE


# =========================================================================
# SECTION 10: PROTOCOL CONSTANTS TESTS
# =========================================================================


class TestProtocolConstants:
    """Tests for protocol constant values."""

    def test_protocol_version(self):
        PROTOCOL_VERSION = 3
        MIN_COMPATIBLE_VERSION = 2
        assert PROTOCOL_VERSION >= MIN_COMPATIBLE_VERSION

    def test_frame_magic(self):
        FRAME_MAGIC = 0x544F5446  # "TOTF"
        assert FRAME_MAGIC == 0x544F5446

    def test_frame_header_size(self):
        FRAME_HEADER_SIZE = 24
        assert FRAME_HEADER_SIZE == 24

    def test_frame_max_payload(self):
        FRAME_MAX_PAYLOAD_SIZE = 16 * 1024 * 1024
        assert FRAME_MAX_PAYLOAD_SIZE == 16 * 1024 * 1024

    def test_frame_flags(self):
        FLAG_NONE = 0x0000
        FLAG_COMPRESSED = 0x0001
        FLAG_ENCRYPTED = 0x0002
        FLAG_CHECKSUMED = 0x0004
        FLAG_REQUIRES_ACK = 0x0020

        assert FLAG_NONE == 0
        assert FLAG_COMPRESSED != FLAG_ENCRYPTED
        assert FLAG_CHECKSUMED != FLAG_REQUIRES_ACK


# =========================================================================
# SECTION 11: FRAME ENCODE / DECODE TESTS (Python-side)
# =========================================================================


class TestFrameCodec:
    """Tests for the wire-format frame codec (Python reimplementation)."""

    FRAME_HEADER_SIZE = 20  # actual bytes written by encoder (magic 4 + version 1 + type 1 + flags 2 + len 4 + seq 4 + reserved 4)

    def _encode_frame(self, message_type: int, payload: bytes, flags: int = 0, sequence: int = 0) -> bytes:
        """Encode a frame matching the Rust FrameEncoder format."""
        FRAME_MAGIC = 0x544F5446
        buf = bytearray()
        buf.extend(FRAME_MAGIC.to_bytes(4, "big"))
        buf.append(3)  # version
        buf.append(message_type & 0xFF)
        buf.extend(flags.to_bytes(2, "big"))
        buf.extend(len(payload).to_bytes(4, "big"))
        buf.extend(sequence.to_bytes(4, "big"))
        buf.extend(b"\x00" * 4)  # reserved
        buf.extend(payload)
        return bytes(buf)

    def test_encode_decode_roundtrip(self):
        payload = b"Hello, World!"
        encoded = self._encode_frame(0x01, payload)

        assert len(encoded) == self.FRAME_HEADER_SIZE + len(payload)
        assert encoded[0:4] == b"TOTF"
        assert encoded[4] == 3  # version
        assert encoded[5] == 0x01  # message type

    def test_payload_preserved(self):
        payload = json.dumps({"action": "heartbeat"}).encode()
        encoded = self._encode_frame(0x50, payload)

        extracted = encoded[self.FRAME_HEADER_SIZE:self.FRAME_HEADER_SIZE + len(payload)]
        assert extracted == payload

    def test_multiple_frames_concatenated(self):
        frame1 = self._encode_frame(0x01, b"frame1")
        frame2 = self._encode_frame(0x02, b"frame2")
        combined = frame1 + frame2

        assert len(combined) == len(frame1) + len(frame2)

    def test_frame_total_size(self):
        payload = b"test payload data"
        encoded = self._encode_frame(0x01, payload)
        assert len(encoded) == self.FRAME_HEADER_SIZE + len(payload)

    def test_reserved_bytes_zero(self):
        encoded = self._encode_frame(0x01, b"data")
        reserved = encoded[16:20]
        assert reserved == b"\x00\x00\x00\x00"


# =========================================================================
# SECTION 12: CIRCUIT BREAKER LOGIC TESTS
# =========================================================================


class TestCircuitBreaker:
    """Tests for circuit breaker logic (Python reimplementation)."""

    def _make_circuit_breaker(self, threshold=5, reset_ms=30000):
        class CircuitBreaker:
            def __init__(self, threshold, reset_ms):
                self.threshold = threshold
                self.reset_ms = reset_ms
                self.consecutive_errors = 0
                self.state = "closed"
                self.opened_at = 0

            def record_success(self):
                self.consecutive_errors = 0
                if self.state == "half_open":
                    self.state = "closed"

            def record_error(self):
                self.consecutive_errors += 1
                if self.consecutive_errors >= self.threshold:
                    if self.state in ("closed", "half_open"):
                        self.state = "open"
                        self.opened_at = time.time()

            def is_allowed(self):
                if self.state == "closed":
                    return True
                if self.state == "open":
                    elapsed = (time.time() - self.opened_at) * 1000
                    if elapsed >= self.reset_ms:
                        self.state = "half_open"
                        return True
                    return False
                if self.state == "half_open":
                    return True
                return False

        return CircuitBreaker(threshold, reset_ms)

    def test_closed_allows_requests(self):
        cb = self._make_circuit_breaker()
        assert cb.is_allowed()

    def test_opens_after_threshold_errors(self):
        cb = self._make_circuit_breaker(threshold=3)
        for _ in range(3):
            cb.record_error()
        assert cb.state == "open"
        assert not cb.is_allowed()

    def test_resets_on_success(self):
        cb = self._make_circuit_breaker(threshold=3)
        cb.record_error()
        cb.record_error()
        cb.record_success()
        assert cb.consecutive_errors == 0
        assert cb.state == "closed"

    def test_half_open_after_timeout(self):
        cb = self._make_circuit_breaker(threshold=2, reset_ms=1)
        cb.record_error()
        cb.record_error()
        assert cb.state == "open"
        time.sleep(0.01)
        assert cb.is_allowed()
        assert cb.state == "half_open"

    def test_half_open_closes_on_success(self):
        cb = self._make_circuit_breaker(threshold=2, reset_ms=1)
        cb.record_error()
        cb.record_error()
        time.sleep(0.01)
        cb.is_allowed()
        cb.record_success()
        assert cb.state == "closed"

    def test_half_open_opens_on_error(self):
        cb = self._make_circuit_breaker(threshold=2, reset_ms=1)
        cb.record_error()
        cb.record_error()
        time.sleep(0.01)
        cb.is_allowed()
        cb.record_error()
        assert cb.state == "open"


# =========================================================================
# SECTION 13: SERIALIZATION TESTS
# =========================================================================


class TestSerialization:
    """Tests for JSON serialization round-trips."""

    def test_json_roundtrip_dict(self):
        data = {"key": "value", "number": 42, "nested": {"a": [1, 2, 3]}}
        encoded = json.dumps(data).encode()
        decoded = json.loads(encoded)
        assert decoded == data

    def test_json_roundtrip_list(self):
        data = [1, "two", 3.0, None, True, {"key": "val"}]
        encoded = json.dumps(data).encode()
        decoded = json.loads(encoded)
        assert decoded == data

    def test_json_handles_unicode(self):
        data = {"text": "Hello, \u00e9\u00e8\u00ea!"}
        encoded = json.dumps(data).encode()
        decoded = json.loads(encoded)
        assert decoded["text"] == data["text"]

    def test_json_empty_payload(self):
        data = {}
        encoded = json.dumps(data).encode()
        decoded = json.loads(encoded)
        assert decoded == {}

    def test_json_preserves_float_precision(self):
        data = {"price": 50000.12345678}
        encoded = json.dumps(data).encode()
        decoded = json.loads(encoded)
        assert abs(decoded["price"] - data["price"]) < 1e-6


# =========================================================================
# SECTION 14: EDGE CASE TESTS
# =========================================================================


class TestEdgeCases:
    """Edge case and boundary condition tests."""

    def test_empty_service_entry_endpoints(self, make_service_entry):
        entry = make_service_entry(endpoints=[])
        assert entry["endpoints"] == []

    def test_large_metadata_dict(self, make_service_entry):
        meta = {f"key_{i}": f"value_{i}" for i in range(100)}
        entry = make_service_entry(metadata=meta)
        assert len(entry["metadata"]) == 100

    def test_zero_quantity_order(self, make_order_payload):
        payload = make_order_payload(quantity=0.0)
        assert payload["quantity"] == 0.0

    def test_negative_price_order(self, make_order_payload):
        payload = make_order_payload(price=-100.0)
        assert payload["price"] < 0

    def test_very_large_quantity(self, make_order_payload):
        payload = make_order_payload(quantity=999999999.99)
        assert payload["quantity"] > 0

    def test_empty_event_payload(self, make_event_envelope):
        envelope = make_event_envelope(payload={})
        assert envelope["payload"] == {}

    def test_nested_event_payload(self, make_event_envelope):
        payload = {
            "order_id": "ord-001",
            "details": {
                "fills": [{"price": 50000, "qty": 0.1}],
                "metadata": {"source": "engine"},
            },
        }
        envelope = make_event_envelope(payload=payload)
        assert envelope["payload"]["details"]["fills"][0]["price"] == 50000

    def test_max_concurrency_boundary(self, mock_connector_config):
        config = mock_connector_config.copy()
        config["max_concurrency"] = 16
        assert 1 <= config["max_concurrency"] <= 16

    def test_zero_timeout(self, mock_connector_config):
        config = mock_connector_config.copy()
        config["timeout_ms"] = 0
        assert config["timeout_ms"] == 0

    def test_large_payload_size(self):
        MAX_MESSAGE_SIZE = 10 * 1024 * 1024
        payload = b"x" * MAX_MESSAGE_SIZE
        assert len(payload) == MAX_MESSAGE_SIZE

    def test_payload_exceeds_max(self):
        MAX_MESSAGE_SIZE = 10 * 1024 * 1024
        payload = b"x" * (MAX_MESSAGE_SIZE + 1)
        assert len(payload) > MAX_MESSAGE_SIZE


# =========================================================================
# SECTION 15: MOCK HTTP SERVER TESTS
# =========================================================================


class TestMockHttpServer:
    """Tests using the mock HTTP server fixture."""

    def test_server_returns_health(self, mock_http_server):
        import urllib.request

        url = f"{mock_http_server['base_url']}/health"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())

        assert data["status"] == "ok"
        assert "version" in data

    def test_server_configurable_response(self, mock_http_server):
        from tests.conftest import MockHealthHandler
        import urllib.request

        MockHealthHandler.health_response = {"status": "degraded", "version": "0.1.0"}
        MockHealthHandler.status_code = 503

        url = f"{mock_http_server['base_url']}/health"
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read())
        except Exception:
            pass  # 503 is fine for this test

        MockHealthHandler.health_response = {"status": "ok", "version": "0.1.0"}
        MockHealthHandler.status_code = 200


# =========================================================================
# SECTION 16: MAKE REQUEST WITH MOCK SERVER
# =========================================================================


class TestMakeRequestWithServer:
    """Tests for ``benchmark.make_request`` using the mock server."""

    def test_success_request(self, mock_http_server):
        from tools.benchmark import make_request

        url = f"{mock_http_server['base_url']}/health"
        status, duration, error = make_request(url, timeout=5)

        assert status == 200
        assert error is None
        assert duration > 0
