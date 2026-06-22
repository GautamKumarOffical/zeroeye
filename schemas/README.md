# JSON Schemas

This directory contains public JSON Schema contracts for exchange-facing data
structures.

## Order Schema

`order.schema.json` describes the market engine `Order` payload using JSON
Schema draft 2020-12. It covers:

- all required order identifiers, lifecycle fields, quantities, prices, and
  timestamps;
- the `side`, `type`, `status`, and `time_in_force` enum values used by the
  market engine;
- optional stop, expiry, iceberg, and display quantity fields;
- valid and invalid example payloads under `schemas/examples/`.

## Validation

Validate the schema and examples with any draft 2020-12 compatible JSON Schema
validator. For example, with Python:

```sh
python3 -m json.tool schemas/order.schema.json >/dev/null
python3 -m json.tool schemas/examples/order.valid.limit.json >/dev/null
python3 -m json.tool schemas/examples/order.valid.iceberg.json >/dev/null
python3 -m json.tool schemas/examples/order.invalid.missing-required.json >/dev/null
python3 -m json.tool schemas/examples/order.invalid.bad-enum.json >/dev/null
```

When the `jsonschema` Python package is installed, this command validates the
example payloads against the schema:

```sh
python3 - <<'PY'
import json
from pathlib import Path
from jsonschema import Draft202012Validator

schema = json.loads(Path("schemas/order.schema.json").read_text())
validator = Draft202012Validator(schema)

for path in sorted(Path("schemas/examples").glob("order.valid.*.json")):
    validator.validate(json.loads(path.read_text()))

for path in sorted(Path("schemas/examples").glob("order.invalid.*.json")):
    errors = list(validator.iter_errors(json.loads(path.read_text())))
    assert errors, f"{path} should be invalid"
PY
```
