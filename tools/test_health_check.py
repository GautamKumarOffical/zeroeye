#!/usr/bin/env python3
"""Tests for health_check retry, backoff, and circuit breaker logic."""

import time
import unittest
from unittest.mock import MagicMock, patch

import health_check


class TestCircuitBreaker(unittest.TestCase):
    """CircuitBreaker unit tests."""

    def test_starts_closed(self):
        cb = health_check.CircuitBreaker(threshold=3)
        self.assertEqual(cb.state, "closed")
        self.assertTrue(cb.allow_request())

    def test_opens_after_threshold_failures(self):
        cb = health_check.CircuitBreaker(threshold=2)
        cb.record_failure()
        self.assertEqual(cb.state, "closed")
        cb.record_failure()
        self.assertEqual(cb.state, "open")
        self.assertFalse(cb.allow_request())

    def test_resets_on_success(self):
        cb = health_check.CircuitBreaker(threshold=2)
        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.state, "open")
        cb.record_success()
        self.assertEqual(cb.state, "closed")
        self.assertTrue(cb.allow_request())

    def test_half_open_after_cooldown(self):
        cb = health_check.CircuitBreaker(threshold=2, cooldown=0.1)
        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.state, "open")
        time.sleep(0.15)
        self.assertEqual(cb.state, "half-open")
        self.assertTrue(cb.allow_request())

    def test_failure_count_resets_on_success(self):
        cb = health_check.CircuitBreaker(threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        self.assertEqual(cb.state, "closed")


class TestCheckHttpServiceRetry(unittest.TestCase):
    """check_http_service retry behavior."""

    @patch("health_check.time.sleep")
    @patch("http.client.HTTPConnection")
    def test_retries_on_exception_then_succeeds(self, mock_conn_cls, mock_sleep):
        mock_conn = MagicMock()
        mock_conn_cls.return_value = mock_conn
        mock_conn.getresponse.side_effect = [
            Exception("connection reset"),
            MagicMock(status=200, read=MagicMock(return_value=b"ok")),
        ]

        result, detail, code = health_check.check_http_service(
            "localhost", 8080, "/health", 5,
            max_retries=2, backoff_factor=1.0, base_delay=0.01,
        )
        self.assertEqual(result, "OK")
        self.assertEqual(code, 200)
        mock_sleep.assert_called_once()

    @patch("health_check.time.sleep")
    @patch("http.client.HTTPConnection")
    def test_returns_critical_after_all_retries_fail(self, mock_conn_cls, mock_sleep):
        mock_conn = MagicMock()
        mock_conn_cls.return_value = mock_conn
        mock_conn.getresponse.side_effect = Exception("nope")

        result, detail, code = health_check.check_http_service(
            "localhost", 8080, "/health", 5,
            max_retries=1, backoff_factor=1.0, base_delay=0.01,
        )
        self.assertEqual(result, "CRITICAL")

    @patch("health_check.time.sleep")
    @patch("http.client.HTTPConnection")
    def test_circuit_breaker_skips_when_open(self, mock_conn_cls, mock_sleep):
        cb = health_check.CircuitBreaker(threshold=1, cooldown=999)
        cb.record_failure()  # opens the circuit

        result, detail, code = health_check.check_http_service(
            "localhost", 8080, "/health", 5,
            max_retries=2, circuit_breaker=cb,
        )
        self.assertEqual(result, "CRITICAL")
        self.assertIn("Circuit breaker open", detail)
        mock_conn_cls.assert_not_called()


class TestCheckTcpPortRetry(unittest.TestCase):
    """check_tcp_port retry behavior."""

    @patch("health_check.time.sleep")
    @patch("health_check.socket.create_connection")
    def test_retries_on_timeout_then_succeeds(self, mock_connect, mock_sleep):
        import socket as sock_mod
        mock_connect.side_effect = [
            sock_mod.timeout("timed out"),
            MagicMock(),
        ]

        result, detail, latency = health_check.check_tcp_port(
            "localhost", 5432, 5,
            max_retries=2, backoff_factor=1.0, base_delay=0.01,
        )
        self.assertEqual(result, "OK")
        self.assertIn("Connected", detail)

    @patch("health_check.time.sleep")
    @patch("health_check.socket.create_connection")
    def test_returns_critical_after_all_retries(self, mock_connect, mock_sleep):
        import socket as sock_mod
        mock_connect.side_effect = sock_mod.timeout("timed out")

        result, detail, latency = health_check.check_tcp_port(
            "localhost", 5432, 5,
            max_retries=1, backoff_factor=1.0, base_delay=0.01,
        )
        self.assertEqual(result, "CRITICAL")
        self.assertIn("timeout", detail)


class TestBackoffCalculation(unittest.TestCase):
    """Verify exponential backoff delay calculation."""

    def test_backoff_delay_formula(self):
        base_delay = 0.5
        factor = 2.0
        self.assertAlmostEqual(base_delay * (factor ** 0), 0.5)
        self.assertAlmostEqual(base_delay * (factor ** 1), 1.0)
        self.assertAlmostEqual(base_delay * (factor ** 2), 2.0)

    @patch("health_check.time.sleep")
    def test_sleep_called_with_correct_delay(self, mock_sleep):
        health_check._sleep_with_backoff(1, 0.5, 2.0)
        mock_sleep.assert_called_once_with(1.0)


class TestSummaryStats(unittest.TestCase):
    """Health check summary aggregation."""

    def test_summary_in_results(self):
        results = health_check.run_health_checks(
            max_retries=0, backoff_factor=1.0, circuit_threshold=1,
        )
        self.assertIn("summary", results)
        summary = results["summary"]
        self.assertIn("total_checks", summary)
        self.assertIn("ok", summary)
        self.assertIn("warning", summary)
        self.assertIn("critical", summary)
        self.assertEqual(
            summary["total_checks"],
            summary["ok"] + summary["warning"] + summary["critical"],
        )


if __name__ == "__main__":
    unittest.main()
