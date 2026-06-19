#!/usr/bin/env python3
import os
import socket
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(__file__))
from health_check import check_http_service, check_tcp_port, _is_transient_error


class TestRetryBackoff(unittest.TestCase):
    @patch("health_check.socket.create_connection")
    def test_tcp_success_after_retry(self, mock_connect):
        mock_sock = MagicMock()
        mock_connect.side_effect = [ConnectionRefusedError, mock_sock]
        status, detail, latency, attempts = check_tcp_port("localhost", 8080, 5, retry_count=3, retry_backoff=0.01)
        self.assertEqual(status, "OK")
        self.assertEqual(attempts, 2)

    @patch("health_check.socket.create_connection")
    def test_tcp_exhausted_retries(self, mock_connect):
        mock_connect.side_effect = ConnectionRefusedError("Connection refused")
        status, detail, latency, attempts = check_tcp_port("localhost", 8080, 5, retry_count=3, retry_backoff=0.01)
        self.assertEqual(status, "CRITICAL")
        self.assertEqual(attempts, 3)
        self.assertIn("Connection refused", detail)

    @patch("health_check.time.sleep")
    @patch("health_check.socket.create_connection")
    def test_tcp_no_retry_on_non_transient(self, mock_connect, mock_sleep):
        mock_connect.side_effect = OSError("Permission denied")
        status, detail, latency, attempts = check_tcp_port("localhost", 8080, 5, retry_count=3, retry_backoff=0.01)
        self.assertEqual(status, "CRITICAL")
        self.assertEqual(attempts, 1)
        mock_sleep.assert_not_called()

    def test_is_transient_error(self):
        self.assertTrue(_is_transient_error(socket.timeout()))
        self.assertTrue(_is_transient_error(ConnectionRefusedError()))
        self.assertTrue(_is_transient_error(ConnectionResetError()))
        self.assertFalse(_is_transient_error(ValueError("bad")))


if __name__ == "__main__":
    unittest.main()
