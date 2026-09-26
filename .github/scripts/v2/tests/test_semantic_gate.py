"""Regression tests proving the authoritative shared semantic gate invariants.

Required invariants tested:
1. direct --promote with UNKNOWN semantics is blocked
2. patches/ and metadata remain unchanged on block (fail-closed)
3. the same candidate succeeds after semantic registry/policy approval
4. watcher and pipeline return the same semantic decision for identical input
5. normal already-approved regeneration remains a no-op when bytes are unchanged
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from v2.manifests.patch_manifest import verify_patch_manifest, write_patch_manifest
from v2.pipeline import (
    CandidateValidationError,
    PipelineResult,
    SemanticApprovalError,
    run_pipeline,
)
from v2.semantic.gate import (
    SemanticGateResult,
    evaluate_semantic_gate,
    verify_semantic_gate_for_pipeline,
)
from v2.semantic.model import Confidence, SemanticId, SemanticKind
from v2.semantic.registry import SemanticRegistry, SemanticSpecification, default_registry
from v2.source.baseline import load_authoritative_bundle
from v2.watch.checker import UpstreamWatcher
from v2.watch.model import WatchClassification


class TestSemanticGateInvariants(unittest.TestCase):
    """Test suite proving the 5 required semantic gate invariants across watcher and pipeline."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.tmp_dir.name).resolve()

        # Real root containing fixtures, baselines, and production patches
        self.real_root = Path(__file__).resolve().parents[4]

        # Recreate directory structure
        (self.repo_root / "patches" / "xxksu").mkdir(parents=True, exist_ok=True)
        (self.repo_root / "patches" / "sultan-android14-6.1").mkdir(parents=True, exist_ok=True)
        (self.repo_root / "patches" / "gki-android16-6.12").mkdir(parents=True, exist_ok=True)
        (self.repo_root / "candidate_patches").mkdir(parents=True, exist_ok=True)
        (self.repo_root / ".github" / "fixtures").mkdir(parents=True, exist_ok=True)

        # Copy fixtures
        shutil.copytree(self.real_root / ".github" / "fixtures", self.repo_root / ".github" / "fixtures", dirs_exist_ok=True)

        # Copy baseline records and production patches
        shutil.copy(self.real_root / "patches" / "xxksu" / "BASELINE.json", self.repo_root / "patches" / "xxksu" / "BASELINE.json")
        shutil.copy(self.real_root / "patches" / "sultan-android14-6.1" / "BASELINE.json", self.repo_root / "patches" / "sultan-android14-6.1" / "BASELINE.json")
        shutil.copy(self.real_root / "patches" / "gki-android16-6.12" / "BASELINE.json", self.repo_root / "patches" / "gki-android16-6.12" / "BASELINE.json")
        shutil.copy(self.real_root / "patches" / "manifest.json", self.repo_root / "patches" / "manifest.json")

        shutil.copy(self.real_root / "patches" / "xxksu" / "11_enable_susfs_for_ksu.patch", self.repo_root / "patches" / "xxksu" / "11_enable_susfs_for_ksu.patch")
        shutil.copy(self.real_root / "patches" / "sultan-android14-6.1" / "51_deinlined_susfs_hooks_sultan-android14-6.1.patch", self.repo_root / "patches" / "sultan-android14-6.1" / "51_deinlined_susfs_hooks_sultan-android14-6.1.patch")
        shutil.copy(self.real_root / "patches" / "gki-android16-6.12" / "51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch", self.repo_root / "patches" / "gki-android16-6.12" / "51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch")

        # Setup clean xxKSU target tree from bundle
        self.ksu_tree = self.repo_root / "clean_ksu"
        self.ksu_tree.mkdir(parents=True, exist_ok=True)
        bundle = load_authoritative_bundle("xxksu", self.real_root)
        for f in bundle.files:
            fp = self.ksu_tree / f.path
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(f.content, encoding="utf-8")

        # Setup Sultan Patch 50 input
        self.sultan_p50_path = self.repo_root / ".github" / "fixtures" / "sultan" / "50_add_susfs_in_gki-android14-6.1.patch"
        self.assertTrue(self.sultan_p50_path.is_file())

        # Setup GKI r38 Patch 50 input
        self.r38_p50_path = self.repo_root / ".github" / "fixtures" / "r38" / "50_add_susfs_in_gki-android16-6.12.patch"
        self.assertTrue(self.r38_p50_path.is_file())

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _create_unapproved_sultan_p50(self) -> Path:
        """Create a modified Sultan Patch 50 containing an unapproved new hook symbol."""
        orig_text = self.sultan_p50_path.read_text(encoding="utf-8")
        target_line = "+extern struct static_key_true susfs_is_sdcard_android_data_not_decrypted;"
        self.assertIn(target_line, orig_text)
        corrupted_text = orig_text.replace(target_line, "+extern void susfs_unapproved_custom_hook(void);")
        corrupted_path = self.repo_root / "unapproved_sultan_50.patch"
        corrupted_path.write_text(corrupted_text, encoding="utf-8")
        return corrupted_path

    def test_1_direct_promote_with_unknown_semantics_blocked(self):
        """Invariant 1: Direct --promote with UNKNOWN semantics is strictly blocked."""
        corrupted_input = self._create_unapproved_sultan_p50()

        with self.assertRaises(SemanticApprovalError) as ctx:
            run_pipeline(
                "sultan-android14-6.1-patch51",
                corrupted_input,
                repo_root=self.repo_root,
                promote=True,
                check_only=True,
            )

        err_msg = str(ctx.exception)
        self.assertIn("SEMANTIC_DRIFT", err_msg)
        self.assertIn("UNKNOWN semantic units", err_msg)

    def test_2_patches_and_metadata_remain_unchanged_on_block(self):
        """Invariant 2: When semantic gate blocks, patches/ and metadata remain 100% byte-identical."""
        public_patch = self.repo_root / "patches" / "sultan-android14-6.1" / "51_deinlined_susfs_hooks_sultan-android14-6.1.patch"
        baseline_file = self.repo_root / "patches" / "sultan-android14-6.1" / "BASELINE.json"
        manifest_file = self.repo_root / "patches" / "manifest.json"

        orig_patch_bytes = public_patch.read_bytes()
        orig_baseline_bytes = baseline_file.read_bytes()
        orig_manifest_bytes = manifest_file.read_bytes()

        corrupted_input = self._create_unapproved_sultan_p50()

        with self.assertRaises(SemanticApprovalError):
            run_pipeline(
                "sultan-android14-6.1-patch51",
                corrupted_input,
                repo_root=self.repo_root,
                promote=True,
                check_only=True,
            )

        # Verify fail-closed: public patch, baseline, and manifest must be untouched byte-for-byte
        self.assertEqual(public_patch.read_bytes(), orig_patch_bytes, "Public patch must remain byte-identical on block")
        self.assertEqual(baseline_file.read_bytes(), orig_baseline_bytes, "BASELINE.json must remain byte-identical on block")
        self.assertEqual(manifest_file.read_bytes(), orig_manifest_bytes, "Manifest must remain byte-identical on block")

    def test_3_same_candidate_succeeds_after_semantic_approval(self):
        """Invariant 3: The exact same candidate succeeds after semantic registry/policy approval."""
        corrupted_input = self._create_unapproved_sultan_p50()

        # Step 3A: Proves it fails closed with default registry
        with self.assertRaises(SemanticApprovalError):
            run_pipeline(
                "sultan-android14-6.1-patch51",
                corrupted_input,
                repo_root=self.repo_root,
                promote=True,
                check_only=True,
            )

        # Step 3B: Reconcile semantics by explicitly registering the specification
        custom_registry = default_registry()
        for p in ("fs/exec.c", "fs/namespace.c", "fs/super.c"):
            p_norm = p.replace("/", ".")
            sid = "susfs.unapproved.hook." + p_norm
            custom_registry.add(SemanticSpecification(
                SemanticId(sid),
                SemanticKind.HANDLER_DECLARATION,
                "custom",
                (p,),
                symbols=("susfs_unapproved_custom_hook",),
                source_roles=("declaration",),
                confidence=Confidence.HIGH,
                notes="Reconciled for testing",
            ))

        # Step 3C: Running the exact same input with approved registry passes the semantic gate!
        gate_res = verify_semantic_gate_for_pipeline(
            "sultan-android14-6.1-patch51",
            corrupted_input,
            repo_root=self.repo_root,
            registry=custom_registry,
        )
        self.assertTrue(gate_res.passed, f"Semantic gate must pass after registry reconciliation: {gate_res.details}")
        self.assertEqual(gate_res.classification, WatchClassification.SAFE_REGEN_CANDIDATE)

    def test_4_watcher_and_pipeline_return_same_semantic_decision_for_identical_input(self):
        """Invariant 4: Watcher and pipeline return the same semantic decision for identical input."""
        corrupted_input = self._create_unapproved_sultan_p50()
        corrupted_text = corrupted_input.read_text(encoding="utf-8")

        # 4A: Unapproved input
        # Gate evaluation for watcher:
        gate_res_watcher = evaluate_semantic_gate(
            "sultan-android14-6.1",
            upstream_contents={"50_add_susfs_in_gki-android14-6.1.patch": corrupted_text},
            repo_root=self.repo_root,
        )
        self.assertFalse(gate_res_watcher.passed)
        self.assertEqual(gate_res_watcher.classification, WatchClassification.SEMANTIC_DRIFT)

        # Gate evaluation for pipeline:
        try:
            run_pipeline(
                "sultan-android14-6.1-patch51",
                corrupted_input,
                repo_root=self.repo_root,
                promote=True,
                check_only=True,
            )
            self.fail("Pipeline should have failed with SemanticApprovalError")
        except SemanticApprovalError as exc:
            self.assertIn("SEMANTIC_DRIFT", str(exc))

        # 4B: Approved input (Baseline)
        gate_res_approved_watcher = evaluate_semantic_gate(
            "sultan-android14-6.1",
            upstream_contents={"50_add_susfs_in_gki-android14-6.1.patch": self.sultan_p50_path.read_text(encoding="utf-8")},
            repo_root=self.repo_root,
        )
        self.assertTrue(gate_res_approved_watcher.passed)
        self.assertEqual(gate_res_approved_watcher.classification, WatchClassification.SAFE_REGEN_CANDIDATE)

        gate_res_approved_pipeline = verify_semantic_gate_for_pipeline(
            "sultan-android14-6.1-patch51",
            self.sultan_p50_path,
            repo_root=self.repo_root,
        )
        self.assertTrue(gate_res_approved_pipeline.passed)
        self.assertEqual(gate_res_approved_pipeline.classification, WatchClassification.SAFE_REGEN_CANDIDATE)

        # Decisions match exactly
        self.assertEqual(gate_res_watcher.classification, WatchClassification.SEMANTIC_DRIFT)
        self.assertEqual(gate_res_approved_watcher.classification, gate_res_approved_pipeline.classification)

    def test_5_normal_already_approved_regeneration_is_noop(self):
        """Invariant 5: Normal already-approved regeneration remains a clean no-op when bytes are unchanged."""
        # Run pipeline on clean xxksu tree
        res1 = run_pipeline(
            "xxksu-patch11",
            self.ksu_tree,
            target_tree=self.ksu_tree,
            repo_root=self.repo_root,
            promote=True,
            check_only=True,
        )
        self.assertTrue(res1.validated)

        # Second run with exact same input
        res2 = run_pipeline(
            "xxksu-patch11",
            self.ksu_tree,
            target_tree=self.ksu_tree,
            repo_root=self.repo_root,
            promote=True,
            check_only=True,
        )
        self.assertTrue(res2.is_noop, "Second run with identical inputs must report is_noop=True")
        self.assertFalse(res2.promoted, "Second run must not rewrite file unnecessarily")
        self.assertEqual(res1.candidate_sha256, res2.candidate_sha256)


if __name__ == "__main__":
    unittest.main()
