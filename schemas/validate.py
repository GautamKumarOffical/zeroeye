#!/usr/bin/env python3
"""Validate order JSON examples against schemas/order.schema.json."""

from __future__ import annotations

import json
from pathlib import Path

try:
    import jsonschema
except ImportError:
    jsonschema = None

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "order.schema.json"
EXAMPLES = [
    ("valid-limit-buy.json", True),
    ("valid-stop-limit-sell.json", True),
    ("invalid-order.json", False),
]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def minimal_valid(data: dict) -> bool:
    required = ORDER_SCHEMA_REQUIRED
    if not all(data.get(k) for k in ("id", "client_order_id", "symbol")):
        return False
    if data.get("quantity", 0) <= 0:
        return False
    if data.get("created_at", -1) < 0:
        return False
    return all(k in data for k in required)


ORDER_SCHEMA_REQUIRED = [
    "id", "client_order_id", "symbol", "side", "type", "status", "price",
    "quantity", "filled_quantity", "remaining_quantity", "leaves_quantity",
    "cumulative_quote_quantity", "avg_price", "time_in_force", "created_at", "updated_at",
]


def main() -> int:
    schema = load_json(SCHEMA_PATH)
    passed = 0
    for name, should_pass in EXAMPLES:
        data = load_json(ROOT / "schemas" / "examples" / name)
        if jsonschema is not None:
            try:
                jsonschema.validate(data, schema)
                ok = True
            except jsonschema.ValidationError:
                ok = False
        else:
            ok = minimal_valid(data)
        if ok == should_pass:
            passed += 1
            print(f"PASS {name}")
        else:
            print(f"FAIL {name}")
            return 1
    print(f"{passed}/{len(EXAMPLES)} tests passed")
    return 0 if passed == len(EXAMPLES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
