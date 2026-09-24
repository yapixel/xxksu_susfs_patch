"""Unit and verification tests for patches/manifest.json."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from v2.manifests.patch_manifest import (
    MANIFEST_RELATIVE_PATH,
    MANIFEST_SCHEMA,
    compute_file_sha256,
    generate_patch_manifest,
    verify_patch_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[4]


class PatchManifestTests(unittest.TestCase):
    """Test suite ensuring patches/manifest.json is valid, complete, and verified."""

    def setUp(self) -> None:
        self.manifest_path = REPO_ROOT / MANIFEST_RELATIVE_PATH
        self.assertTrue(self.manifest_path.is_file(), f"Manifest file missing at {self.manifest_path}")
        self.raw_manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def test_manifest_file_exists_and_valid_json(self) -> None:
        self.assertTrue(self.manifest_path.is_file())
        self.assertIsInstance(self.raw_manifest, dict)

    def test_manifest_schema_and_entries_count(self) -> None:
        self.assertEqual(self.raw_manifest.get("schema"), MANIFEST_SCHEMA)
        patches = self.raw_manifest.get("patches", [])
        self.assertIsInstance(patches, list)
        self.assertEqual(len(patches), 3, "Manifest must contain exactly the 3 verified production patches")

    def test_required_fields_in_each_entry(self) -> None:
        required_fields = ("id", "name", "relative_path", "sha256", "target_lineage", "compatibility_target")
        expected_ids = {"xxksu-patch11", "sultan-android14-6.1-patch51", "gki-android16-6.12-r38-patch51"}
        actual_ids = set()

        for entry in self.raw_manifest["patches"]:
            for field in required_fields:
                self.assertIn(field, entry, f"Missing field '{field}' in entry {entry.get('id')}")
            actual_ids.add(entry["id"])

            # Verify target_lineage has repository and commit
            lineage = entry["target_lineage"]
            self.assertIn("repository", lineage)
            self.assertIn("commit", lineage)

        self.assertEqual(actual_ids, expected_ids)

    def test_every_manifest_path_exists_on_disk(self) -> None:
        for entry in self.raw_manifest["patches"]:
            rel_path = entry["relative_path"]
            abs_path = REPO_ROOT / rel_path
            self.assertTrue(abs_path.is_file(), f"Patch path does not exist on disk: {rel_path}")

    def test_every_manifest_sha256_matches(self) -> None:
        for entry in self.raw_manifest["patches"]:
            rel_path = entry["relative_path"]
            expected_sha = entry["sha256"]
            abs_path = REPO_ROOT / rel_path
            actual_sha = compute_file_sha256(abs_path)
            self.assertEqual(
                actual_sha,
                expected_sha,
                f"SHA-256 mismatch for {rel_path}: expected {expected_sha}, got {actual_sha}",
            )

    def test_manifest_deterministic_match_with_generator(self) -> None:
        expected_manifest = generate_patch_manifest(REPO_ROOT)
        expected_json = json.dumps(expected_manifest, indent=2, sort_keys=True) + "\n"
        on_disk_json = self.manifest_path.read_text(encoding="utf-8")
        self.assertEqual(
            on_disk_json,
            expected_json,
            "patches/manifest.json on disk does not match deterministic generation (manifest is stale)",
        )

    def test_verify_patch_manifest_function_passes(self) -> None:
        valid, errors = verify_patch_manifest(REPO_ROOT)
        self.assertTrue(valid, f"verify_patch_manifest failed with errors: {errors}")
        self.assertEqual(len(errors), 0)

    def test_verify_detects_missing_file_fail_closed(self) -> None:
        orig_is_file = Path.is_file

        def mock_is_file(p):
            if "11_enable_susfs" in str(p):
                return False
            return orig_is_file(p)

        with patch.object(Path, "is_file", autospec=True, side_effect=mock_is_file):
            valid, errors = verify_patch_manifest(REPO_ROOT)
            self.assertFalse(valid)
            self.assertTrue(any("not found on disk" in e or "failed to generate" in e.lower() for e in errors))


if __name__ == "__main__":
    unittest.main()
