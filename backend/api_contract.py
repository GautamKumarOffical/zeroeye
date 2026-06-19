"""Backend API contract helpers.

Provides request validation and error response construction based on the
Tent of Trials OpenAPI 3.1.0 specification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class ContractError(Exception):
    """Raised when a request violates the API contract."""

    def __init__(self, code: int, message: str, details: Optional[Dict[str, Any]] = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def to_response(self) -> Dict[str, Any]:
        body: Dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            body["details"] = self.details
        return body


@dataclass
class RequestSpec:
    """Describes the expected shape of an incoming request."""

    required_fields: List[str] = field(default_factory=list)
    optional_fields: List[str] = field(default_factory=list)
    field_types: Dict[str, type] = field(default_factory=dict)
    patterns: Dict[str, str] = field(default_factory=dict)


def validate_payload(payload: Dict[str, Any], spec: RequestSpec) -> None:
    """Validate a request payload against a RequestSpec.

    Raises ContractError on any validation failure.
    """
    for fld in spec.required_fields:
        if fld not in payload:
            raise ContractError(
                code=400,
                message=f"Missing required field: {fld}",
                details={"missing_field": fld},
            )

        for fld, expected in spec.field_types.items():
            if fld in payload and payload[fld] is not None:
                if not isinstance(payload[fld], expected):
                    type_name = expected.__name__ if isinstance(expected, type) else str(expected)
                    raise ContractError(
                        code=400,
                        message=f"Invalid type for field {fld}: expected {type_name}",
                        details={"field": fld, "expected_type": type_name},
                    )

    for fld, pattern in spec.patterns.items():
        if fld in payload and payload[fld] is not None:
            if not re.search(pattern, str(payload[fld])):
                raise ContractError(
                    code=400,
                    message=f"Field {fld} does not match pattern {pattern}",
                    details={"field": fld, "pattern": pattern},
                )


def make_error_response(
    code: int,
    message: str,
    request_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a structured error response matching the API contract."""
    body: Dict[str, Any] = {"code": code, "message": message}
    if request_id:
        body["request_id"] = request_id
    if details:
        body["details"] = details
    return body


def validate_login_credentials(payload: Dict[str, Any]) -> None:
    """Validate a login request payload."""
    spec = RequestSpec(
        required_fields=["email", "password"],
        field_types={"email": str, "password": str},
        patterns={"email": r"^[^@\s]+@[^@\s]+\.[^@\s]+$"},
    )
    validate_payload(payload, spec)


def validate_order_payload(payload: Dict[str, Any]) -> None:
    """Validate an order placement request payload."""
    spec = RequestSpec(
        required_fields=["symbol", "side", "type", "quantity"],
        field_types={
            "symbol": str,
            "side": str,
            "type": str,
            "quantity": (int, float),
        },
        patterns={"symbol": r"^[A-Z0-9]{2,10}/[A-Z0-9]{2,10}$"},
    )
    validate_payload(payload, spec)
    if "side" in payload and payload["side"] not in ("buy", "sell"):
        raise ContractError(
            code=400,
            message="Invalid side: must be 'buy' or 'sell'",
            details={"field": "side", "allowed": ["buy", "sell"]},
        )
    if "type" in payload and payload["type"] not in ("limit", "market", "stop_limit", "stop_market"):
        raise ContractError(
            code=400,
            message="Invalid order type",
            details={"field": "type"},
        )


async def async_validate_login(payload: Dict[str, Any]) -> None:
    """Async wrapper around login validation."""
    validate_login_credentials(payload)


async def async_validate_order(payload: Dict[str, Any]) -> None:
    """Async wrapper around order validation."""
    validate_order_payload(payload)
