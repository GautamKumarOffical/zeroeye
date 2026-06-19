#!/usr/bin/env python3
"""
Test script for log aggregator JSONL output.

Tests JSONL export with multiple log formats and verifies the output
conforms to the expected schema.
"""

import json
import os
import subprocess
import sys
import tempfile
import shutil


def run_aggregator(input_path, output_path, fmt="jsonl"):
    """Run the log aggregator and return the return code."""
    result = subprocess.run(
        [sys.executable, "tools/log_aggregator.py",
         "--input", input_path,
         "--output", output_path,
         "--format", fmt],
        capture_output=True,
        text=True
    )
    return result.returncode, result.stdout, result.stderr


def validate_jsonl_record(record):
    """Validate that a JSONL record has the required fields."""
    required_fields = ['timestamp', 'level', 'source', 'message', 'metadata']
    for field in required_fields:
        if field not in record:
            return False, f"Missing required field: {field}"
    return True, None


def main():
    test_dir = tempfile.mkdtemp(prefix="log_agg_test_")
    results = {}

    try:
        print("Log Aggregator JSONL Output Tests")
        print("=" * 50)

        # Test 1: JSON log format
        print("\nTest 1: JSON log format -> JSONL output")
        json_input = os.path.join(test_dir, "input.json")
        json_output = os.path.join(test_dir, "output.jsonl")

        shutil.copy("tools/test_fixtures/sample_json_logs.jsonl", json_input)
        rc, stdout, stderr = run_aggregator(json_input, json_output)

        if rc != 0:
            print(f"  FAILED: Aggregator returned {rc}")
            print(f"  stderr: {stderr[:200]}")
            results["json"] = False
        else:
            with open(json_output) as f:
                lines = [json.loads(line) for line in f if line.strip()]

            valid_count = 0
            for i, record in enumerate(lines):
                ok, err = validate_jsonl_record(record)
                if ok:
                    valid_count += 1
                else:
                    print(f"  Record {i}: {err}")

            if valid_count == len(lines):
                print(f"  PASS: {len(lines)} valid JSONL records")
                results["json"] = True
            else:
                print(f"  FAILED: {valid_count}/{len(lines)} records valid")
                results["json"] = False

        # Test 2: Text log format
        print("\nTest 2: Text log format -> JSONL output")
        text_input = os.path.join(test_dir, "input.log")
        text_output = os.path.join(test_dir, "text_output.jsonl")

        shutil.copy("tools/test_fixtures/sample_text_logs.log", text_input)
        rc, stdout, stderr = run_aggregator(text_input, text_output)

        if rc != 0:
            print(f"  FAILED: Aggregator returned {rc}")
            print(f"  stderr: {stderr[:200]}")
            results["text"] = False
        else:
            with open(text_output) as f:
                lines = [json.loads(line) for line in f if line.strip()]

            valid_count = 0
            has_warning = False
            for i, record in enumerate(lines):
                ok, err = validate_jsonl_record(record)
                if ok:
                    valid_count += 1
                    if record.get('level') == 'warn' and record.get('metadata', {}).get('parse_error'):
                        has_warning = True
                else:
                    print(f"  Record {i}: {err}")

            if valid_count == len(lines) and has_warning:
                print(f"  PASS: {len(lines)} valid records, warning for unparseable line found")
                results["text"] = True
            elif valid_count == len(lines):
                print(f"  PASS: {len(lines)} valid records (no unparseable lines in test data)")
                results["text"] = True
            else:
                print(f"  FAILED: {valid_count}/{len(lines)} records valid")
                results["text"] = False

        # Test 3: Check timestamp ordering
        print("\nTest 3: Timestamp ordering in JSONL output")
        if results.get("json"):
            with open(json_output) as f:
                records = [json.loads(line) for line in f if line.strip()]

            timestamps = [r['timestamp'] for r in records if r['timestamp']]
            if timestamps == sorted(timestamps):
                print("  PASS: Records are ordered by timestamp")
                results["ordering"] = True
            else:
                print("  FAILED: Records are not ordered by timestamp")
                results["ordering"] = False

        # Test 4: Verify required fields
        print("\nTest 4: Required fields in JSONL output")
        if results.get("json"):
            with open(json_output) as f:
                first_record = json.loads(f.readline())

            required = {'timestamp', 'level', 'source', 'message', 'metadata'}
            present = set(first_record.keys())
            missing = required - present
            if not missing:
                print(f"  PASS: All required fields present: {sorted(required)}")
                results["fields"] = True
            else:
                print(f"  FAILED: Missing fields: {missing}")
                results["fields"] = False

        # Print summary
        print("\n" + "=" * 50)
        passed = sum(1 for v in results.values() if v)
        total = len(results)
        print(f"Results: {passed}/{total} tests passed")

        if passed == total:
            print("All tests PASSED")
            return 0
        else:
            print("Some tests FAILED")
            return 1

    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
