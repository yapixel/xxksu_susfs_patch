"""Unit and verification tests for V2 authoritative baseline records."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from v2.model.manifest import KNOWN_TARGETS, MANUAL_FIXTURES
from v2.model.provenance import HashDigest
from v2.model.result import ValidationStatus
from v2.profiles.matrix import KNOWN_PROFILES, get_profile_definition
from v2.profiles.composition import compose_profile
from v2.source.baseline import (
    BASELINE_SCHEMA,
    BaselineRecord,
    InvalidBaselineContract,
    UnsupportedBaselineSchema,
    get_baseline_path,
    load_authoritative_bundle,
    load_baseline_record,
)
from v2.source.bundle import SourceBundle
from v2.source.hashing import hash_file
from v2.source.patch_apply import apply_patch_to_bundle
from v2.adapters.xxksu import generate_patch11, apply_patch11_to_bundle
from v2.validation import validate_all, validate_bundle_integrity
from v2.validation.symbols import validate_symbols

REPO_ROOT = Path(__file__).resolve().parents[4]


class BaselineRecordContractTests(unittest.TestCase):
    """Verify strict validation and fail-closed behavior of BaselineRecord."""

    def setUp(self) -> None:
        self.sultan_path = get_baseline_path("sultan-android14-6.1", REPO_ROOT)
        self.gki_path = get_baseline_path("gki-android16-6.12", REPO_ROOT)
        self.xxksu_path = get_baseline_path("xxksu", REPO_ROOT)

    def test_all_baseline_files_exist(self) -> None:
        self.assertTrue(self.sultan_path.is_file(), f"missing {self.sultan_path}")
        self.assertTrue(self.gki_path.is_file(), f"missing {self.gki_path}")
        self.assertTrue(self.xxksu_path.is_file(), f"missing {self.xxksu_path}")

    def test_sultan_baseline_record_validates(self) -> None:
        record = load_baseline_record(self.sultan_path)
        self.assertEqual(record.schema, BASELINE_SCHEMA)
        self.assertEqual(record.target_id, "sultan-android14-6.1")
        self.assertEqual(record.kernel_version, "6.1")
        self.assertEqual(record.status, "VERIFIED")
        self.assertEqual(record.upstream["resolved_commit"], "af5c65b9547a9f33c5f566430d0434aecab5a8b5")
        self.assertEqual(record.susfs["resolved_commit"], "7fd1da8e0cc8d1b572c97c5fe4a27d0ec6e3e2f1")
        self.assertEqual(record.validation_results["sultan-android14-6.1-manual"], "PASS")
        self.assertEqual(record.validation_results["sultan-android14-6.1-lsm_bl"], "PASS")
        self.assertIsInstance(record.identity, HashDigest)

    def test_gki_baseline_record_validates(self) -> None:
        record = load_baseline_record(self.gki_path)
        self.assertEqual(record.schema, BASELINE_SCHEMA)
        self.assertEqual(record.target_id, "gki-android16-6.12")
        self.assertEqual(record.kernel_version, "6.12")
        self.assertEqual(record.status, "VERIFIED")
        self.assertEqual(record.upstream["resolved_commit"], "c8909f7cf1380810b285cbeee347dd01a8c9ec5c")
        self.assertEqual(record.susfs["resolved_commit"], "c8f64e41e3dea2cd44754d7472d3cd0bc0b40784")
        self.assertEqual(record.validation_results["gki-android16-6.12-manual"], "PASS")
        self.assertEqual(record.validation_results["gki-android16-6.12-lsm_bl"], "PASS")
        self.assertIsInstance(record.identity, HashDigest)

    def test_xxksu_baseline_record_validates(self) -> None:
        record = load_baseline_record(self.xxksu_path)
        self.assertEqual(record.schema, BASELINE_SCHEMA)
        self.assertEqual(record.target_id, "xxksu")
        self.assertEqual(record.kernel_version, "main")
        self.assertEqual(record.status, "VERIFIED")
        self.assertEqual(record.upstream["resolved_commit"], "0b138d6a9cfe4dc163aa05c21b1e6a14ff868230")
        self.assertEqual(record.upstream["tree"], "026a4682a51e6d3d707704ef3a1dc1f478138de6")
        self.assertEqual(record.upstream["archive_sha256"], "84978d24638b47bd282c2e496255acb364d91ee0474db46d02767b890143a05d")
        self.assertEqual(record.patch_10["resolved_commit"], "c8f64e41e3dea2cd44754d7472d3cd0bc0b40784")
        self.assertEqual(record.patch_11["strict_apply"], "PASS")
        self.assertIsInstance(record.identity, HashDigest)

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

    def test_gki_authoritative_bundle_loads(self) -> None:
        bundle = load_authoritative_bundle("gki-android16-6.12", REPO_ROOT)
        self.assertIsNotNone(bundle)
        self.assertIsInstance(bundle, SourceBundle)
        self.assertEqual(bundle.target_id, "gki-android16-6.12")
        self.assertEqual(bundle.kernel_version, "6.12")
        self.assertEqual(len(bundle.files), 22)

    def test_gki_patch_51_strict_application_succeeds(self) -> None:
        bundle = load_authoritative_bundle("gki-android16-6.12", REPO_ROOT)
        patch_path = REPO_ROOT / "patches" / "gki-android16-6.12" / "51_deinlined_susfs_hooks_gki-android16-6.12.patch"
        patch_text = patch_path.read_text(encoding="utf-8")
        patched = apply_patch_to_bundle(bundle, patch_text)
        self.assertIsInstance(patched, SourceBundle)
        self.assertEqual(len(patched.files), 22)

    def test_gki_both_profiles_validate_positive(self) -> None:
        bundle = load_authoritative_bundle("gki-android16-6.12", REPO_ROOT)
        patch_path = REPO_ROOT / "patches" / "gki-android16-6.12" / "51_deinlined_susfs_hooks_gki-android16-6.12.patch"
        patch_text = patch_path.read_text(encoding="utf-8")
        patched = apply_patch_to_bundle(bundle, patch_text)

        # 1. Manual profile
        prof_manual = get_profile_definition("gki-android16-6.12-manual")
        adapter = prof_manual.get_adapter()
        plan = adapter.adapt_fixtures(patched, prof_manual.fixtures)
        composed_manual = plan.apply_to_bundle(patched)
        report_manual = validate_all(
            bundle=composed_manual,
            mode="manual",
            claims=prof_manual.get_ownership_claims(),
            raise_on_failure=True,
        )
        self.assertEqual(report_manual.status, ValidationStatus.PASS)

        # 2. LSM_BL profile
        prof_lsm = get_profile_definition("gki-android16-6.12-lsm_bl")
        report_lsm = validate_all(
            bundle=patched,
            mode="lsm_bl",
            claims=prof_lsm.get_ownership_claims(),
            raise_on_failure=True,
        )
        self.assertEqual(report_lsm.status, ValidationStatus.PASS)


    def test_sultan_authoritative_bundle_loads(self) -> None:
        bundle = load_authoritative_bundle("sultan-android14-6.1", REPO_ROOT)
        self.assertIsNotNone(bundle)
        self.assertIsInstance(bundle, SourceBundle)
        self.assertEqual(bundle.target_id, "sultan-android14-6.1")
        self.assertEqual(bundle.kernel_version, "6.1.25")
        self.assertEqual(len(bundle.files), 22)

    def test_sultan_patch_51_strict_application_succeeds(self) -> None:
        bundle = load_authoritative_bundle("sultan-android14-6.1", REPO_ROOT)
        patch_path = REPO_ROOT / "patches" / "sultan-android14-6.1" / "51_deinlined_susfs_hooks_sultan-android14-6.1.patch"
        patch_text = patch_path.read_text(encoding="utf-8")
        patched = apply_patch_to_bundle(bundle, patch_text)
        self.assertIsInstance(patched, SourceBundle)
        self.assertEqual(len(patched.files), 22)

    def test_sultan_both_profiles_validate_positive(self) -> None:
        bundle = load_authoritative_bundle("sultan-android14-6.1", REPO_ROOT)
        patch_path = REPO_ROOT / "patches" / "sultan-android14-6.1" / "51_deinlined_susfs_hooks_sultan-android14-6.1.patch"
        patch_text = patch_path.read_text(encoding="utf-8")
        patched = apply_patch_to_bundle(bundle, patch_text)

        # 1. Manual profile
        prof_manual = get_profile_definition("sultan-android14-6.1-manual")
        adapter = prof_manual.get_adapter()
        plan = adapter.adapt_fixtures(patched, prof_manual.fixtures)
        composed_manual = plan.apply_to_bundle(patched)
        report_manual = validate_all(
            bundle=composed_manual,
            mode="manual",
            claims=prof_manual.get_ownership_claims(),
            raise_on_failure=True,
        )
        self.assertEqual(report_manual.status, ValidationStatus.PASS)

        # 2. LSM_BL profile
        prof_lsm = get_profile_definition("sultan-android14-6.1-lsm_bl")
        report_lsm = validate_all(
            bundle=patched,
            mode="lsm_bl",
            claims=prof_lsm.get_ownership_claims(),
            raise_on_failure=True,
        )
        self.assertEqual(report_lsm.status, ValidationStatus.PASS)

    def test_xxksu_authoritative_bundle_loads(self) -> None:
        bundle = load_authoritative_bundle("xxksu", REPO_ROOT)
        self.assertIsNotNone(bundle)
        self.assertIsInstance(bundle, SourceBundle)
        self.assertEqual(bundle.target_id, "xxksu")
        self.assertEqual(bundle.kernel_version, "main")
        self.assertEqual(len(bundle.files), 13)

    def test_xxksu_patch_11_deterministic_generation(self) -> None:
        bundle = load_authoritative_bundle("xxksu", REPO_ROOT)
        p1 = generate_patch11(bundle)
        p2 = generate_patch11(bundle)
        self.assertEqual(p1, p2)
        patch_path = REPO_ROOT / "patches" / "xxksu" / "11_enable_susfs_for_ksu.patch"
        disk_text = patch_path.read_text(encoding="utf-8")
        self.assertEqual(p1, disk_text)

    def test_xxksu_patch_11_strict_application_succeeds(self) -> None:
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

    def test_all_four_profiles_consume_authoritative_patch_11(self) -> None:
        xxksu_bundle = load_authoritative_bundle("xxksu", REPO_ROOT)
        patch_11_path = REPO_ROOT / "patches" / "xxksu" / "11_enable_susfs_for_ksu.patch"
        patch_11_text = patch_11_path.read_text(encoding="utf-8")

        p51_map = {
            "sultan-android14-6.1": REPO_ROOT / "patches" / "sultan-android14-6.1" / "51_deinlined_susfs_hooks_sultan-android14-6.1.patch",
            "gki-android16-6.12": REPO_ROOT / "patches" / "gki-android16-6.12" / "51_deinlined_susfs_hooks_gki-android16-6.12.patch",
        }

        for profile_id in sorted(KNOWN_PROFILES):
            prof_def = get_profile_definition(profile_id)
            target_bundle = load_authoritative_bundle(prof_def.target_id, REPO_ROOT)
            patch_51_text = p51_map[prof_def.target_id].read_text(encoding="utf-8")
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
