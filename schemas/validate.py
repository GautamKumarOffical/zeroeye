#!/usr/bin/env python3
"""Validate example Order payloads against the JSON Schema."""
import json
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    print("Installing jsonschema...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "jsonschema", "-q"])
    import jsonschema

SCHEMA_PATH = Path(__file__).resolve().parent / "order.schema.json"
EXAMPLES_DIR = Path(__file__).resolve().parent / "examples"

def main():
    schema = json.loads(SCHEMA_PATH.read_text())

    valid_files = sorted(EXAMPLES_DIR.glob("valid-*.json"))
    invalid_files = sorted(EXAMPLES_DIR.glob("invalid-*.json"))

    errors = []

    for f in valid_files:
        payload = json.loads(f.read_text())
        try:
            jsonschema.validate(payload, schema)
            print(f"  PASS  {f.name} validates correctly")
        except jsonschema.ValidationError as e:
            print(f"  FAIL  {f.name} should be valid but failed: {e.message}")
            errors.append(f.name)

    for f in invalid_files:
        payload = json.loads(f.read_text())
        try:
            jsonschema.validate(payload, schema)
            print(f"  FAIL  {f.name} should be invalid but passed validation")
            errors.append(f.name)
        except jsonschema.ValidationError:
            print(f"  PASS  {f.name} correctly rejected")

    print()
    if errors:
        print(f"FAILED: {', '.join(errors)}")
        sys.exit(1)
    else:
        print("All validation checks passed.")
        sys.exit(0)

if __name__ == "__main__":
    main()
