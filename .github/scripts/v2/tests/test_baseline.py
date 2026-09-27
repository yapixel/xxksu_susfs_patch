"""Unit and verification tests for V2 authoritative baseline records."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from v2.validation.exact_patch import validate_patch_syntax

from v2.model.provenance import HashDigest
from v2.model.result import ValidationStatus
from v2.profiles.matrix import get_profile_definition
from v2.profiles.composition import compose_profile
from v2.source.baseline import BASELINE_SCHEMA, InvalidBaselineContract, UnsupportedBaselineSchema, get_baseline_path, load_authoritative_bundle, load_baseline_record
from v2.source.bundle import SourceBundle
from v2.source.patch_apply import apply_patch_to_bundle
from v2.adapters.xxksu import generate_patch11, apply_patch11_to_bundle
from v2.validation import validate_bundle_integrity
from v2.validation.symbols import validate_symbols

REPO_ROOT = Path(__file__).resolve().parents[4]


class BaselineRecordContractTests(unittest.TestCase):
    """Verify strict validation and fail-closed behavior of BaselineRecord."""

    def setUp(self) -> None:
        self.sultan_path = get_baseline_path("sultan-android14-6.1", REPO_ROOT)
        self.gki_path = get_baseline_path("gki-android16-6.12", REPO_ROOT)
        self.xxksu_path = get_baseline_path("xxksu", REPO_ROOT)

    def test_pinned_baseline_records(self):
        for target, version, commit, susfs in (
            ("sultan-android14-6.1", "6.1", "af5c65b9547a9f33c5f566430d0434aecab5a8b5", "a8324101bca5e5a2dd7d0dc82b1650e10923eec9"),
            ("gki-android16-6.12", "6.12", "c8909f7cf1380810b285cbeee347dd01a8c9ec5c", "b213c54126fb243595ce7876e91d84d6e0861fec"),
            ("xxksu", "main", "bb0be9297da42ff3f63819125314ce0b13935a06", None),
        ):
            with self.subTest(target=target):
                path = get_baseline_path(target, REPO_ROOT)
                self.assertTrue(path.is_file())
                record = load_baseline_record(path)
                self.assertEqual((record.schema, record.target_id, record.kernel_version, record.status),
                                 (BASELINE_SCHEMA, target, version, "VERIFIED"))
                self.assertEqual(record.upstream["resolved_commit"], commit)
                self.assertIsInstance(record.identity, HashDigest)
                if susfs:
                    self.assertEqual(record.susfs["resolved_commit"], susfs)
                    for mode in ("manual", "lsm_bl"):
                        self.assertEqual(record.validation_results[f"{target}-{mode}"], "PASS")
                else:
                    self.assertEqual(record.upstream["tree"], "cc3afab7a762a029c2d8dd7d9e8a4f1358a7df9c")
                    self.assertEqual(record.upstream["archive_sha256"], "e2cd42a7206e8956341089135f67c876f11b7759e5288c8a2ee06cc4ff313075")
                    self.assertEqual(record.patch_10["resolved_commit"], "c8f64e41e3dea2cd44754d7472d3cd0bc0b40784")
                    self.assertEqual(record.patch_11["strict_apply"], "PASS")


    def test_invalid_schema_fails_closed(self) -> None:
        raw = json.loads(self.sultan_path.read_text(encoding="utf-8"))
        raw["schema"] = "invalid/v99"
        with self.assertRaises(UnsupportedBaselineSchema):
            load_baseline_record(raw)

    def test_retired_target_fails_closed(self) -> None:
        raw = json.loads(self.sultan_path.read_text(encoding="utf-8"))
        raw["target_id"] = "gki-android14-6.1"
        with self.assertRaises(InvalidBaselineContract):
            load_baseline_record(raw)

    def test_verified_record_without_archive_sha_fails_closed(self) -> None:
        raw = json.loads(self.sultan_path.read_text(encoding="utf-8"))
        del raw["upstream"]["archive_sha256"]
        with self.assertRaises(InvalidBaselineContract):
            load_baseline_record(raw)

    def test_verified_record_without_bundle_identity_fails_closed(self) -> None:
        raw = json.loads(self.sultan_path.read_text(encoding="utf-8"))
        raw["source_bundle"]["identity"] = None
        with self.assertRaises(InvalidBaselineContract):
            load_baseline_record(raw)

    def test_blocked_record_without_reason_fails_closed(self) -> None:
        raw = json.loads(self.sultan_path.read_text(encoding="utf-8"))
        raw["status"] = "BLOCKED"
        raw["blocker_reason"] = None
        raw["validation_results"] = {
            "sultan-android14-6.1-manual": "BLOCKED",
            "sultan-android14-6.1-lsm_bl": "BLOCKED",
        }
        with self.assertRaises(InvalidBaselineContract):
            load_baseline_record(raw)

    def test_missing_fixture_fails_closed(self) -> None:
        raw = json.loads(self.sultan_path.read_text(encoding="utf-8"))
        raw["fixtures"] = {}
        with self.assertRaises(InvalidBaselineContract):
            load_baseline_record(raw)


class AuthoritativeBundleVerificationTests(unittest.TestCase):
    """Verify loading and quality-gate verification of authoritative bundles."""

    def test_authoritative_bundles(self):
        for target, version, count in (("gki-android16-6.12","6.12",22), ("sultan-android14-6.1","6.1.25",23), ("xxksu","main",13)):
            with self.subTest(target=target):
                bundle = load_authoritative_bundle(target, REPO_ROOT)
                self.assertIsInstance(bundle, SourceBundle)
                self.assertEqual((bundle.target_id, bundle.kernel_version, len(bundle.files)), (target, version, count))

    def test_gki_public_r38_and_retired_internal_patch(self):
        with self.subTest(case='gki_internal_patch_51_retired'):
            retired_patch = REPO_ROOT / "patches" / "gki-android16-6.12" / "51_deinlined_susfs_hooks_gki-android16-6.12.patch"
            self.assertFalse(retired_patch.exists(), "Defective internal patch 51 must remain retired/deleted")
            gki_path = get_baseline_path("gki-android16-6.12", REPO_ROOT)
            record = load_baseline_record(gki_path)
            self.assertIn("retired_internal_patch", record.patch_51)
            self.assertEqual(record.patch_51["retired_internal_patch"], "51_deinlined_susfs_hooks_gki-android16-6.12.patch")
        with self.subTest(case='gki_r38_production_patch_51'):
            patch_path = REPO_ROOT / "patches" / "gki-android16-6.12" / "51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch"
            self.assertTrue(patch_path.is_file(), "r38 production patch must exist")
            patch_text = patch_path.read_text(encoding="utf-8")
            syntax_errors = validate_patch_syntax(patch_text)
            self.assertEqual(syntax_errors, [])
            gki_path = get_baseline_path("gki-android16-6.12", REPO_ROOT)
            record = load_baseline_record(gki_path)
            expected_sha = record.patch_51["patch_sha256"].removeprefix("sha256:")
            actual_sha = hashlib.sha256(patch_path.read_bytes()).hexdigest()
            self.assertEqual(actual_sha, expected_sha)


    def test_xxksu_generated_patch_matches_applied_postimage(self):
        with self.subTest(case='xxksu_patch_11_deterministic_generation'):
            bundle = load_authoritative_bundle("xxksu", REPO_ROOT)
            p1 = generate_patch11(bundle)
            p2 = generate_patch11(bundle)
            self.assertEqual(p1, p2)
            patch_path = REPO_ROOT / "patches" / "xxksu" / "11_enable_susfs_for_ksu.patch"
            disk_text = patch_path.read_text(encoding="utf-8")
            self.assertEqual(p1, disk_text)
        with self.subTest(case='xxksu_patch_11_strict_application_succeeds'):
            bundle = load_authoritative_bundle("xxksu", REPO_ROOT)
            patch_path = REPO_ROOT / "patches" / "xxksu" / "11_enable_susfs_for_ksu.patch"
            patch_text = patch_path.read_text(encoding="utf-8")
            patched = apply_patch_to_bundle(bundle, patch_text)
            self.assertIsInstance(patched, SourceBundle)
            self.assertEqual(len(patched.files), 13)

            adapted = apply_patch11_to_bundle(bundle)
            for f in bundle.files:
                self.assertEqual(patched.get_file(f.path).content, adapted.get_file(f.path).content)
                self.assertEqual(patched.get_file(f.path).content_hash, adapted.get_file(f.path).content_hash)

            integrity_res = validate_bundle_integrity(patched)
            self.assertEqual(integrity_res.status, ValidationStatus.PASS)

            sym_results = validate_symbols(patch=patch_text)
            for res in sym_results:
                self.assertEqual(res.status, ValidationStatus.PASS)


    def test_sultan_profiles_consume_authoritative_patch_11(self) -> None:
        xxksu_bundle = load_authoritative_bundle("xxksu", REPO_ROOT)
        patch_11_path = REPO_ROOT / "patches" / "xxksu" / "11_enable_susfs_for_ksu.patch"
        patch_11_text = patch_11_path.read_text(encoding="utf-8")

        p51_path = REPO_ROOT / "patches" / "sultan-android14-6.1" / "51_deinlined_susfs_hooks_sultan-android14-6.1.patch"
        patch_51_text = p51_path.read_text(encoding="utf-8")

        for profile_id in ("sultan-android14-6.1-manual", "sultan-android14-6.1-lsm_bl"):
            prof_def = get_profile_definition(profile_id)
            target_bundle = load_authoritative_bundle(prof_def.target_id, REPO_ROOT)
            result = compose_profile(
                profile_id=profile_id,
                target_bundle=target_bundle,
                patch_11=patch_11_text,
                patch_51=patch_51_text,
                xxksu_bundle=xxksu_bundle,
                raise_on_failure=True,
            )
            self.assertEqual(result.validation_report.status, ValidationStatus.PASS)


if __name__ == "__main__":
    unittest.main()
