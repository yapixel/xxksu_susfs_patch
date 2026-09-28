"""Unit and verification tests for patches/manifest.json."""

from __future__ import annotations

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
        self.manifest_text = self.manifest_path.read_text(encoding="utf-8")
        self.raw_manifest = json.loads(self.manifest_text)

    def test_manifest_integrity_and_canonical_bytes(self):
        with self.subTest(case='manifest_file_exists_and_valid_json'):
            self.assertIsInstance(self.raw_manifest, dict)
        with self.subTest(case='manifest_schema_and_entries_count'):
            self.assertEqual(self.raw_manifest.get("schema"), MANIFEST_SCHEMA)
            patches = self.raw_manifest.get("patches", [])
            self.assertIsInstance(patches, list)
            self.assertEqual(len(patches), 3, "Manifest must contain exactly the 3 verified production patches")
        with self.subTest(case='required_fields_in_each_entry'):
            required_fields = (
                "id",
                "name",
                "relative_path",
                "sha256",
                "target_lineage",
                "compatibility_target",
                "apply_target",
                "patch_apply_target",
            )
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
        with self.subTest(case='manifest_paths_and_hashes'):
            for entry in self.raw_manifest["patches"]:
                abs_path = REPO_ROOT / entry["relative_path"]
                self.assertTrue(abs_path.is_file(), f"Patch path does not exist on disk: {abs_path}")
                self.assertEqual(compute_file_sha256(abs_path), entry["sha256"], str(abs_path))
        with self.subTest(case='manifest_deterministic_match_with_generator'):
            expected_manifest = generate_patch_manifest(REPO_ROOT)
            expected_json = json.dumps(expected_manifest, indent=2, sort_keys=True) + "\n"
            on_disk_json = self.manifest_text
            self.assertEqual(
                on_disk_json,
                expected_json,
                "patches/manifest.json on disk does not match deterministic generation (manifest is stale)",
            )
        with self.subTest(case='verify_patch_manifest_function_passes'):
            valid, errors = verify_patch_manifest(REPO_ROOT)
            self.assertTrue(valid, f"verify_patch_manifest failed with errors: {errors}")
            self.assertEqual(len(errors), 0)


    def test_gki_r38_manifest_entry_unambiguous(self) -> None:
        r38_entry = next(e for e in self.raw_manifest["patches"] if e["id"] == "gki-android16-6.12-r38-patch51")
        self.assertEqual(r38_entry["apply_target"], "android16-6.12-2025-09_r38")
        self.assertEqual(r38_entry["patch_apply_target"], "android16-6.12-2025-09_r38")
        self.assertEqual(r38_entry["target_lineage"]["commit"], "c8909f7cf1380810b285cbeee347dd01a8c9ec5c")
        self.assertEqual(r38_entry["target_lineage"]["ref"], "android16-6.12")
        self.assertIn("internal", r38_entry["target_lineage"].get("description", "").lower())
        self.assertIn("provenance_lineage", r38_entry)
        self.assertEqual(r38_entry["provenance_lineage"]["commit"], "c8909f7cf1380810b285cbeee347dd01a8c9ec5c")


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
