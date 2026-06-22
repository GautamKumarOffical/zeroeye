#!/usr/bin/env python3
"""Tests for Terraform resource name validation."""

import csv
import io
import os
import sys
import tempfile
import unittest
import unittest.mock

sys.path.insert(0, os.path.dirname(__file__))

from terraform_import import (
    ResourceToImport,
    TerraformImporter,
    validate_resource_name,
)


class TestValidateResourceName(unittest.TestCase):
    def test_valid_name(self):
        validate_resource_name("aws_instance", "my_instance")

    def test_valid_name_with_numbers(self):
        validate_resource_name("aws_s3_bucket", "bucket_01")

    def test_valid_name_leading_underscore(self):
        validate_resource_name("aws_vpc", "_private")

    def test_empty_name_raises(self):
        with self.assertRaises(ValueError) as ctx:
            validate_resource_name("aws_instance", "")
        self.assertIn("empty", str(ctx.exception))

    def test_hyphenated_name_raises(self):
        with self.assertRaises(ValueError) as ctx:
            validate_resource_name("aws_instance", "my-instance")
        self.assertIn("hyphens", str(ctx.exception))
        self.assertIn("aws_instance", str(ctx.exception))

    def test_invalid_characters_raises(self):
        with self.assertRaises(ValueError):
            validate_resource_name("aws_instance", "my instance")

    def test_name_with_space_raises(self):
        with self.assertRaises(ValueError):
            validate_resource_name("aws_lb", "load balancer")

    def test_type_in_error_message(self):
        with self.assertRaises(ValueError) as ctx:
            validate_resource_name("aws_s3_bucket", "bad-name")
        msg = str(ctx.exception)
        self.assertIn("aws_s3_bucket", msg)
        self.assertIn("bad-name", msg)


class TestImportBatchRejectsHyphens(unittest.TestCase):
    def test_dry_run_rejects_hyphenated(self):
        importer = TerraformImporter.__new__(TerraformImporter)
        importer.state_dir = "."
        importer.terraform_binary = "terraform"
        importer.results = []

        resource = ResourceToImport(
            resource_type="aws_instance",
            resource_name="bad-name",
            resource_id="i-12345",
        )
        with self.assertRaises(ValueError):
            importer.import_batch([resource], dry_run=True)

    def test_generate_script_rejects_hyphens(self):
        importer = TerraformImporter.__new__(TerraformImporter)
        importer.state_dir = "."
        importer.terraform_binary = "terraform"
        importer.results = []

        resource = ResourceToImport(
            resource_type="aws_instance",
            resource_name="bad-name",
            resource_id="i-12345",
        )
        with self.assertRaises(ValueError):
            importer.generate_import_script([resource], output_file="/dev/null")


class TestCSVValidation(unittest.TestCase):
    def test_csv_invalid_name_exits(self):
        csv_content = "type,name,id\naws_instance,my-bad-name,i-12345\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            f.flush()
            csv_path = f.name
        try:
            sys.argv = [
                "terraform_import.py",
                "--csv", csv_path,
            ]
            from terraform_import import main
            ret = main()
            self.assertEqual(ret, 1)
        finally:
            os.unlink(csv_path)

    @unittest.mock.patch("terraform_import.subprocess.run")
    def test_csv_valid_name_passes(self, mock_run):
        mock_run.return_value = unittest.mock.Mock(
            returncode=0, stdout='{"terraform_version":"1.5.0"}', stderr=""
        )
        csv_content = "type,name,id\naws_instance,my_good_instance,i-12345\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            f.flush()
            csv_path = f.name
        try:
            sys.argv = [
                "terraform_import.py",
                "--csv", csv_path,
                "--dry-run",
            ]
            from importlib import reload
            import terraform_import
            reload(terraform_import)
            ret = terraform_import.main()
            self.assertEqual(ret, 0)
        finally:
            os.unlink(csv_path)


if __name__ == "__main__":
    unittest.main()
