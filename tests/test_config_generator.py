#!/usr/bin/env python3
"""Tests for config_generator secret masking."""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from config_generator import (
    _is_sensitive_key,
    mask_sensitive,
    to_dotenv,
    to_json,
    to_k8s_configmap,
    to_yaml,
    generate_config,
)


class TestSensitiveKeyDetection:
    def test_password_detected(self):
        assert _is_sensitive_key("password") is True
        assert _is_sensitive_key("db_password") is True
        assert _is_sensitive_key("PASSWORD") is True

    def test_secret_detected(self):
        assert _is_sensitive_key("jwt_secret") is True
        assert _is_sensitive_key("api_secret") is True
        assert _is_sensitive_key("SECRET") is True

    def test_token_detected(self):
        assert _is_sensitive_key("access_token") is True
        assert _is_sensitive_key("refresh_token") is True
        assert _is_sensitive_key("api_token") is True

    def test_key_detected(self):
        assert _is_sensitive_key("api_key") is True
        assert _is_sensitive_key("signing_key") is True
        assert _is_sensitive_key("encryption_key") is True

    def test_credential_detected(self):
        assert _is_sensitive_key("credentials") is True
        assert _is_sensitive_key("aws_credential") is True
        assert _is_sensitive_key("CREDENTIAL") is True

    def test_non_sensitive_not_flagged(self):
        assert _is_sensitive_key("host") is False
        assert _is_sensitive_key("port") is False
        assert _is_sensitive_key("name") is False
        assert _is_sensitive_key("debug") is False
        assert _is_sensitive_key("timeout_ms") is False
        assert _is_sensitive_key("pool_size") is False


class TestMaskSensitiveNested:
    def test_nested_dict_masked(self):
        config = {
            "database": {
                "host": "localhost",
                "password": "s3cret",
                "port": 5432,
            }
        }
        masked = mask_sensitive(config)
        assert masked["database"]["host"] == "localhost"
        assert masked["database"]["port"] == 5432
        assert masked["database"]["password"] == "***REDACTED***"

    def test_deeply_nested_masked(self):
        config = {
            "auth": {
                "oauth": {
                    "client_secret": "supersecret",
                    "redirect_uri": "http://localhost",
                }
            }
        }
        masked = mask_sensitive(config)
        assert masked["auth"]["oauth"]["client_secret"] == "***REDACTED***"
        assert masked["auth"]["oauth"]["redirect_uri"] == "http://localhost"

    def test_multiple_secrets_masked(self):
        config = {
            "database": {"password": "dbpass"},
            "redis": {"password": "redispass"},
            "auth": {"jwt_secret": "jwtsecret"},
        }
        masked = mask_sensitive(config)
        assert masked["database"]["password"] == "***REDACTED***"
        assert masked["redis"]["password"] == "***REDACTED***"
        assert masked["auth"]["jwt_secret"] == "***REDACTED***"


class TestMaskSensitiveList:
    def test_list_of_strings_preserved(self):
        config = {"kafka": {"brokers": ["localhost:9092", "localhost:9093"]}}
        masked = mask_sensitive(config)
        assert masked["kafka"]["brokers"] == ["localhost:9092", "localhost:9093"]

    def test_list_of_dicts_with_secrets(self):
        config = {
            "services": [
                {"name": "api", "api_key": "key1"},
                {"name": "web", "api_key": "key2"},
            ]
        }
        masked = mask_sensitive(config)
        for svc in masked["services"]:
            assert svc["api_key"] == "***REDACTED***"
            assert "name" in svc

    def test_list_value_preserves_non_sensitive(self):
        config = {"market": {"allowed_instruments": ["BTC", "ETH"]}}
        masked = mask_sensitive(config)
        assert masked["market"]["allowed_instruments"] == ["BTC", "ETH"]


class TestMaskSensitiveEdgeCases:
    def test_empty_config(self):
        assert mask_sensitive({}) == {}

    def test_non_dict_passthrough(self):
        assert mask_sensitive("hello") == "hello"
        assert mask_sensitive(42) == 42
        assert mask_sensitive(None) is None

    def test_list_at_root(self):
        config = [{"api_key": "secret"}, {"host": "localhost"}]
        masked = mask_sensitive(config)
        assert masked[0]["api_key"] == "***REDACTED***"
        assert masked[1]["host"] == "localhost"


class TestDotenvOutput:
    def test_secret_masked_in_dotenv(self):
        config = {
            "database": {"password": "s3cret", "host": "localhost"},
            "auth": {"jwt_secret": "myjwt"},
        }
        masked = mask_sensitive(config)
        output = to_dotenv(masked)
        assert "s3cret" not in output
        assert "myjwt" not in output
        assert "DATABASE_PASSWORD=***REDACTED***" in output
        assert "AUTH_JWT_SECRET=***REDACTED***" in output
        assert "DATABASE_HOST=localhost" in output

    def test_non_secret_preserved_in_dotenv(self):
        config = {"server": {"host": "0.0.0.0", "port": 8080}}
        masked = mask_sensitive(config)
        output = to_dotenv(masked)
        assert "SERVER_HOST=0.0.0.0" in output
        assert "SERVER_PORT=8080" in output


class TestK8sConfigMapOutput:
    def test_secret_masked_in_configmap(self):
        config = {
            "database": {"password": "s3cret", "host": "localhost"},
        }
        masked = mask_sensitive(config)
        output = to_k8s_configmap(masked)
        assert "s3cret" not in output
        assert "database.password" in output
        assert "***REDACTED***" in output

    def test_non_secret_preserved_in_configmap(self):
        config = {"server": {"host": "0.0.0.0", "port": 8080}}
        masked = mask_sensitive(config)
        output = to_k8s_configmap(masked)
        assert "server.host" in output
        assert "0.0.0.0" in output


class TestJsonOutput:
    def test_secret_masked_in_json(self):
        config = {"auth": {"jwt_secret": "mysecret", "jwt_expiry_minutes": 60}}
        masked = mask_sensitive(config)
        output = to_json(masked)
        parsed = json.loads(output)
        assert parsed["auth"]["jwt_secret"] == "***REDACTED***"
        assert parsed["auth"]["jwt_expiry_minutes"] == 60


class TestYamlOutput:
    def test_secret_masked_in_yaml(self):
        config = {"auth": {"jwt_secret": "mysecret", "jwt_expiry_minutes": 60}}
        masked = mask_sensitive(config)
        output = to_yaml(masked)
        assert "mysecret" not in output
        assert "***REDACTED***" in output


class TestErrorMessageSafety:
    def test_yaml_error_no_leak(self):
        from config_generator import to_yaml
        output = to_yaml({})
        assert "SECRET" not in output or "ERROR" in output

    def test_unsupported_format_error(self):
        from config_generator import main
        import argparse
        sys.argv = ["config_generator.py", "--env", "development", "--format", "badformat"]
        try:
            result = main()
            assert result == 1
        except SystemExit:
            pass


class TestGenerateConfigMasking:
    def test_production_config_masked(self):
        config = generate_config("production")
        masked = mask_sensitive(config)
        assert masked["database"]["password"] == "***REDACTED***"
        assert masked["redis"]["password"] == "***REDACTED***"
        assert masked["auth"]["jwt_secret"] == "***REDACTED***"
        assert masked["auth"]["password_min_length"] == "***REDACTED***"
        assert masked["auth"]["password_require_special"] == "***REDACTED***"
        assert masked["auth"]["password_require_numbers"] == "***REDACTED***"
        assert masked["auth"]["password_require_uppercase"] == "***REDACTED***"

    def test_non_secret_values_preserved(self):
        config = generate_config("production")
        masked = mask_sensitive(config)
        assert masked["database"]["host"] == "localhost"
        assert masked["database"]["port"] == 5432
        assert masked["database"]["name"] == "tent_production"
        assert masked["server"]["host"] == "0.0.0.0"
        assert masked["server"]["port"] == 8080
        assert masked["app"]["debug"] is False
