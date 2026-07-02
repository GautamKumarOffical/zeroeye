#!/usr/bin/env python3
"""Validate order JSON examples against schemas/order.schema.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    print("jsonschema not installed; using minimal structural checks")
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


def main() -> int:
    schema = load_json(SCHEMA_PATH)
    passed = 0
    for name, should_pass in EXAMPLES:
        data = load_json(ROOT / "schemas" / "examples" / name)
        ok = True
        if jsonschema is not None:
            try:
                jsonschema.validate(data, schema)
                ok = True
            except jsonschema.ValidationError:
                ok = False
        else:
            ok = bool(data.get("id")) and data.get("quantity", 0) > 0 and data.get("timestamp", -1) >= 0
        if ok == should_pass:
            passed += 1
            print(f"PASS {name}")
        else:
            print(f"FAIL {name} expected valid={should_pass} got valid={ok}")
            return 1
    print(f"{passed}/{len(EXAMPLES)} tests passed")
    return 0 if passed == len(EXAMPLES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
