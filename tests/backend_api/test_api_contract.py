"""Tests for backend API contract edge cases.

Covers malformed payloads, async wrappers, and error response shape
validation without requiring network services or optional pytest plugins.
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

import pytest
from api_contract import (
    ContractError,
    RequestSpec,
    async_validate_login,
    async_validate_order,
    make_error_response,
    validate_login_credentials,
    validate_order_payload,
    validate_payload,
)


class TestValidatePayloadMissingFields:
    def test_missing_single_required_field(self):
        spec = RequestSpec(required_fields=["email", "password"])
        with pytest.raises(ContractError) as exc_info:
            validate_payload({"email": "a@b.com"}, spec)
        assert exc_info.value.code == 400
        assert "password" in exc_info.value.message
        assert exc_info.value.details["missing_field"] == "password"

    def test_missing_all_required_fields(self):
        spec = RequestSpec(required_fields=["email", "password"])
        with pytest.raises(ContractError) as exc_info:
            validate_payload({}, spec)
        assert exc_info.value.code == 400

    def test_optional_field_not_required(self):
        spec = RequestSpec(
            required_fields=["email"],
            optional_fields=["remember_me"],
        )
        validate_payload({"email": "a@b.com"}, spec)


class TestValidatePayloadTypeErrors:
    def test_wrong_type_for_string_field(self):
        spec = RequestSpec(
            required_fields=["name"],
            field_types={"name": str},
        )
        with pytest.raises(ContractError) as exc_info:
            validate_payload({"name": 12345}, spec)
        assert exc_info.value.code == 400
        assert "Invalid type" in exc_info.value.message

    def test_wrong_type_for_numeric_field(self):
        spec = RequestSpec(
            required_fields=["quantity"],
            field_types={"quantity": (int, float)},
        )
        with pytest.raises(ContractError) as exc_info:
            validate_payload({"quantity": "not-a-number"}, spec)
        assert exc_info.value.code == 400

    def test_none_value_skips_type_check(self):
        spec = RequestSpec(
            required_fields=["optional_thing"],
            field_types={"optional_thing": str},
        )
        validate_payload({"optional_thing": None}, spec)


class TestValidatePayloadPatternErrors:
    def test_pattern_mismatch(self):
        spec = RequestSpec(
            required_fields=["email"],
            patterns={"email": r"^[^@\s]+@[^@\s]+\.[^@\s]+$"},
        )
        with pytest.raises(ContractError) as exc_info:
            validate_payload({"email": "not-an-email"}, spec)
        assert exc_info.value.code == 400
        assert "pattern" in exc_info.value.details

    def test_pattern_match_success(self):
        spec = RequestSpec(
            required_fields=["email"],
            patterns={"email": r"^[^@\s]+@[^@\s]+\.[^@\s]+$"},
        )
        validate_payload({"email": "user@example.com"}, spec)


class TestLoginCredentialValidation:
    def test_missing_email(self):
        with pytest.raises(ContractError) as exc_info:
            validate_login_credentials({"password": "hunter2"})
        assert exc_info.value.code == 400
        assert "email" in exc_info.value.message

    def test_missing_password(self):
        with pytest.raises(ContractError) as exc_info:
            validate_login_credentials({"email": "a@b.com"})
        assert exc_info.value.code == 400
        assert "password" in exc_info.value.message

    def test_missing_both(self):
        with pytest.raises(ContractError):
            validate_login_credentials({})

    def test_invalid_email_format(self):
        with pytest.raises(ContractError) as exc_info:
            validate_login_credentials({"email": "bad", "password": "x"})
        assert exc_info.value.code == 400

    def test_valid_credentials(self):
        validate_login_credentials({"email": "user@example.com", "password": "hunter2"})


class TestOrderPayloadValidation:
    def test_missing_symbol(self):
        with pytest.raises(ContractError) as exc_info:
            validate_order_payload({"side": "buy", "type": "limit", "quantity": 1})
        assert exc_info.value.code == 400
        assert "symbol" in exc_info.value.message

    def test_invalid_symbol_format(self):
        with pytest.raises(ContractError) as exc_info:
            validate_order_payload({
                "symbol": "INVALID",
                "side": "buy",
                "type": "limit",
                "quantity": 1,
            })
        assert exc_info.value.code == 400

    def test_invalid_side_value(self):
        with pytest.raises(ContractError) as exc_info:
            validate_order_payload({
                "symbol": "BTC/USD",
                "side": "hold",
                "type": "limit",
                "quantity": 1,
            })
        assert exc_info.value.code == 400
        assert "side" in exc_info.value.message

    def test_invalid_type_value(self):
        with pytest.raises(ContractError) as exc_info:
            validate_order_payload({
                "symbol": "BTC/USD",
                "side": "buy",
                "type": "weird_type",
                "quantity": 1,
            })
        assert exc_info.value.code == 400
        assert "order type" in exc_info.value.message.lower()

    def test_quantity_not_numeric(self):
        with pytest.raises(ContractError) as exc_info:
            validate_order_payload({
                "symbol": "BTC/USD",
                "side": "buy",
                "type": "limit",
                "quantity": "lots",
            })
        assert exc_info.value.code == 400

    def test_valid_order(self):
        validate_order_payload({
            "symbol": "BTC/USD",
            "side": "buy",
            "type": "limit",
            "quantity": 1.5,
        })


class TestErrorResponseShape:
    def test_error_response_has_code_and_message(self):
        resp = make_error_response(401, "Unauthorized")
        assert resp["code"] == 401
        assert resp["message"] == "Unauthorized"
        assert "request_id" not in resp

    def test_error_response_with_request_id(self):
        resp = make_error_response(404, "Not found", request_id="req-abc")
        assert resp["request_id"] == "req-abc"

    def test_error_response_with_details(self):
        resp = make_error_response(422, "Invalid", details={"field": "email"})
        assert resp["details"]["field"] == "email"

    def test_contract_error_to_response(self):
        err = ContractError(400, "Bad request", details={"reason": "missing foo"})
        resp = err.to_response()
        assert resp["code"] == 400
        assert resp["message"] == "Bad request"
        assert resp["details"]["reason"] == "missing foo"


class TestAsyncHelpers:
    def _run(self, coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def test_async_validate_login_valid(self):
        self._run(async_validate_login({"email": "a@b.com", "password": "pass"}))

    def test_async_validate_login_missing_field(self):
        with pytest.raises(ContractError):
            self._run(async_validate_login({"password": "pass"}))

    def test_async_validate_order_valid(self):
        self._run(async_validate_order({
            "symbol": "ETH/BTC",
            "side": "sell",
            "type": "market",
            "quantity": 10,
        }))

    def test_async_validate_order_bad_side(self):
        with pytest.raises(ContractError):
            self._run(async_validate_order({
                "symbol": "ETH/BTC",
                "side": "hold",
                "type": "market",
                "quantity": 10,
            }))

    def test_async_validate_order_missing_symbol(self):
        with pytest.raises(ContractError):
            self._run(async_validate_order({
                "side": "buy",
                "type": "limit",
                "quantity": 1,
            }))
