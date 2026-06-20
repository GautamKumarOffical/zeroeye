#!/usr/bin/env python3
"""Tests for data manifest generation and verification."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

GENERATOR = os.path.join(os.path.dirname(__file__), "data_generator.py")


class TestManifestGeneration(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _run_generator(self, extra_args):
        cmd = [sys.executable, GENERATOR, "--output-dir", self.tmpdir] + extra_args
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_manifest_created_with_checksums(self):
        manifest_path = os.path.join(self.tmpdir, "manifest.json")
        self._run_generator(["--seed", "42", "--manifest", manifest_path])
        self.assertTrue(os.path.exists(manifest_path))

        with open(manifest_path) as f:
            m = json.load(f)

        self.assertEqual(m["schema_version"], 1)
        self.assertEqual(m["seed"], 42)
        self.assertIn("files", m)
        self.assertIn("users.json", m["files"])
        self.assertIn("sha256", m["files"]["users.json"])
        self.assertEqual(len(m["files"]["users.json"]["sha256"]), 64)

    def test_manifest_deterministic(self):
        m1_path = os.path.join(self.tmpdir, "m1.json")
        m2_path = os.path.join(self.tmpdir, "m2.json")
        self._run_generator(["--seed", "42", "--manifest", m1_path])
        self._run_generator(["--seed", "42", "--manifest", m2_path])

        with open(m1_path) as f1, open(m2_path) as f2:
            m1 = json.load(f1)
            m2 = json.load(f2)

        for key in m1["files"]:
            self.assertEqual(m1["files"][key]["sha256"], m2["files"][key]["sha256"])

    def test_verify_manifest_passes(self):
        manifest_path = os.path.join(self.tmpdir, "manifest.json")
        self._run_generator(["--seed", "42", "--manifest", manifest_path])
        result = subprocess.run(
            [sys.executable, GENERATOR, "--verify-manifest", manifest_path],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("passed", result.stdout.lower())

    def test_verify_manifest_fails_on_corrupted_file(self):
        manifest_path = os.path.join(self.tmpdir, "manifest.json")
        self._run_generator(["--seed", "42", "--manifest", manifest_path])

        users_path = os.path.join(self.tmpdir, "users.json")
        with open(users_path, "w") as f:
            f.write("corrupted")

        result = subprocess.run(
            [sys.executable, GENERATOR, "--verify-manifest", manifest_path],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAILED", result.stdout)

    def test_verify_manifest_fails_on_missing_file(self):
        manifest_path = os.path.join(self.tmpdir, "manifest.json")
        self._run_generator(["--seed", "42", "--manifest", manifest_path])

        os.remove(os.path.join(self.tmpdir, "users.json"))

        result = subprocess.run(
            [sys.executable, GENERATOR, "--verify-manifest", manifest_path],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Missing file", result.stdout)

    def test_manifest_records_counts(self):
        manifest_path = os.path.join(self.tmpdir, "manifest.json")
        self._run_generator(["--seed", "42", "--manifest", manifest_path])
        with open(manifest_path) as f:
            m = json.load(f)
        self.assertEqual(m["files"]["users.json"]["record_count"], 50)
        self.assertEqual(m["files"]["orders.json"]["record_count"], 200)
        self.assertEqual(m["files"]["trades.json"]["record_count"], 500)


if __name__ == "__main__":
    unittest.main()
