#!/usr/bin/env python3
"""
Validation script to prove deterministic output of the data generator.

Runs the data generator with the same seed multiple times and verifies
that the output is byte-for-byte identical across runs.
"""

import hashlib
import os
import subprocess
import sys
import tempfile
import shutil


def run_generator(seed, output_dir):
    """Run the data generator with a specific seed and return hashes of output files."""
    result = subprocess.run(
        [sys.executable, "tools/data_generator.py",
         "--seed", str(seed),
         "--output-dir", output_dir,
         "--users", "10",
         "--orders", "20",
         "--trades", "30",
         "--ticks", "50",
         "--candles", "20"],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"Generator failed with seed {seed}:")
        print(result.stderr)
        return None

    hashes = {}
    for root, dirs, files in os.walk(output_dir):
        for fname in sorted(files):
            fpath = os.path.join(root, fname)
            with open(fpath, 'rb') as f:
                h = hashlib.sha256(f.read()).hexdigest()
            hashes[fname] = h
    return hashes


def main():
    test_seeds = [42, 12345, 999999]
    results = {}

    print("Deterministic Data Generator Validation")
    print("=" * 50)

    for seed in test_seeds:
        print(f"\nTesting seed {seed}...")

        run1_dir = tempfile.mkdtemp(prefix=f"dg_seed{seed}_run1_")
        run2_dir = tempfile.mkdtemp(prefix=f"dg_seed{seed}_run2_")

        try:
            hashes1 = run_generator(seed, run1_dir)
            hashes2 = run_generator(seed, run2_dir)

            if hashes1 is None or hashes2 is None:
                print(f"  FAILED: Generator error")
                results[seed] = False
                continue

            if hashes1.keys() != hashes2.keys():
                print(f"  FAILED: Different files produced")
                results[seed] = False
                continue

            all_match = all(hashes1[k] == hashes2[k] for k in hashes1)
            if all_match:
                print(f"  PASS: All {len(hashes1)} files are byte-for-byte identical")
                results[seed] = True
            else:
                mismatches = [k for k in hashes1 if hashes1[k] != hashes2[k]]
                print(f"  FAILED: {len(mismatches)} files differ: {mismatches}")
                results[seed] = False
        finally:
            shutil.rmtree(run1_dir, ignore_errors=True)
            shutil.rmtree(run2_dir, ignore_errors=True)

    # Test that different seeds produce different output
    print("\nVerifying different seeds produce different output...")
    dir_a = tempfile.mkdtemp(prefix="dg_seed_a_")
    dir_b = tempfile.mkdtemp(prefix="dg_seed_b_")
    try:
        hashes_a = run_generator(42, dir_a)
        hashes_b = run_generator(999999, dir_b)

        if hashes_a and hashes_b:
            diffs = [k for k in hashes_a if hashes_a.get(k) != hashes_b.get(k)]
            if len(diffs) == len(hashes_a):
                print(f"  PASS: Different seeds produce completely different output")
            else:
                print(f"  WARNING: {len(diffs)}/{len(hashes_a)} files differ")
    finally:
        shutil.rmtree(dir_a, ignore_errors=True)
        shutil.rmtree(dir_b, ignore_errors=True)

    print("\n" + "=" * 50)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"Results: {passed}/{total} seeds produced deterministic output")

    if passed == total:
        print("All tests PASSED")
        return 0
    else:
        print("Some tests FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
