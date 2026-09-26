"""Unit and regression tests proving the required automation pipeline architecture.

Core repository contract:
`patches/` is the FINAL VERIFIED OUTPUT of this repository's generators.
It must NOT be the source input used to generate/validate a supposedly newer production patch.

Required pipeline properties tested:
1. generator output is the candidate
2. failed candidate never changes patches/
3. successful candidate is promoted to patches/
4. promoted file == validated candidate byte-for-byte
5. manifest SHA == promoted file
6. rerunning identical inputs is a no-op
7. validation does not mutate/apply the same tree twice
"""

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
    generate_patch11_from_tree,
    run_pipeline,
)
from v2.source.baseline import get_baseline_path, load_authoritative_bundle, load_baseline_record
from v2.validation.exact_patch import validate_exact_patch_on_tree


class TestPipelineArchitecture(unittest.TestCase):
    """Test suite proving the 7 core contract invariants of the pipeline."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.tmp_dir.name).resolve()

        # Create mock repository structure
        (self.repo_root / "patches" / "xxksu").mkdir(parents=True, exist_ok=True)
        (self.repo_root / "patches" / "sultan-android14-6.1").mkdir(parents=True, exist_ok=True)
        (self.repo_root / "patches" / "gki-android16-6.12").mkdir(parents=True, exist_ok=True)
        (self.repo_root / "candidate_patches").mkdir(parents=True, exist_ok=True)

        # Copy baseline fixtures and records to mock repo root
        real_root = Path(__file__).resolve().parents[4]
        shutil.copy(real_root / "patches" / "xxksu" / "BASELINE.json", self.repo_root / "patches" / "xxksu" / "BASELINE.json")
        shutil.copy(real_root / "patches" / "sultan-android14-6.1" / "BASELINE.json", self.repo_root / "patches" / "sultan-android14-6.1" / "BASELINE.json")
        shutil.copy(real_root / "patches" / "gki-android16-6.12" / "BASELINE.json", self.repo_root / "patches" / "gki-android16-6.12" / "BASELINE.json")
        shutil.copy(real_root / "patches" / "manifest.json", self.repo_root / "patches" / "manifest.json")

        # Copy existing public patches so manifest check initially passes
        shutil.copy(real_root / "patches" / "xxksu" / "11_enable_susfs_for_ksu.patch", self.repo_root / "patches" / "xxksu" / "11_enable_susfs_for_ksu.patch")
        shutil.copy(real_root / "patches" / "sultan-android14-6.1" / "51_deinlined_susfs_hooks_sultan-android14-6.1.patch", self.repo_root / "patches" / "sultan-android14-6.1" / "51_deinlined_susfs_hooks_sultan-android14-6.1.patch")
        shutil.copy(real_root / "patches" / "gki-android16-6.12" / "51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch", self.repo_root / "patches" / "gki-android16-6.12" / "51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch")

        # Setup clean xxKSU target tree from bundle
        self.ksu_tree = self.repo_root / "clean_ksu"
        self.ksu_tree.mkdir(parents=True, exist_ok=True)
        bundle = load_authoritative_bundle("xxksu", real_root)
        for f in bundle.files:
            fp = self.ksu_tree / f.path
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(f.content, encoding="utf-8")

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_1_generator_output_is_the_candidate(self):
        """Invariant 1: Generator outputs to candidate path, leaving public patches/ untouched."""
        cand_dir = self.repo_root / "candidate_patches" / "xxksu-patch11"
        res = run_pipeline(
            "xxksu-patch11",
            self.ksu_tree,
            target_tree=self.ksu_tree,
            candidate_dir=cand_dir,
            repo_root=self.repo_root,
            promote=False,
            check_only=True,
        )

        candidate_file = cand_dir / "11_enable_susfs_for_ksu.patch"
        self.assertTrue(candidate_file.is_file(), "Candidate artifact must be created")
        self.assertEqual(res.candidate_path, candidate_file)
        self.assertFalse(res.promoted, "Candidate must NOT be promoted when promote=False")

        # Candidate content must be valid unified diff
        cand_text = candidate_file.read_text(encoding="utf-8")
        self.assertIn("diff --git a/kernel/ksu.c b/kernel/ksu.c", cand_text)

    def test_2_failed_candidate_never_changes_patches(self):
        """Invariant 2: When candidate validation fails, public patches/ is strictly untouched."""
        public_file = self.repo_root / "patches" / "xxksu" / "11_enable_susfs_for_ksu.patch"
        orig_bytes = public_file.read_bytes()
        orig_sha = hashlib.sha256(orig_bytes).hexdigest()

        # Create a separate target tree that has corrupted context causing patch rejection
        target_tree = self.repo_root / "corrupted_target"
        shutil.copytree(self.ksu_tree, target_tree)
        (target_tree / "kernel" / "ksu.c").write_text("corrupted target context\n", encoding="utf-8")

        with self.assertRaises(CandidateValidationError):
            run_pipeline(
                "xxksu-patch11",
                self.ksu_tree,  # clean upstream input produces candidate
                target_tree=target_tree,  # validation against corrupted target fails
                repo_root=self.repo_root,
                promote=True,  # Even with promote=True, failure aborts before promotion
            )

        # Public patch must remain completely identical
        self.assertEqual(public_file.read_bytes(), orig_bytes)
        self.assertEqual(hashlib.sha256(public_file.read_bytes()).hexdigest(), orig_sha)

    def test_3_successful_candidate_promoted_to_patches(self):
        """Invariant 3: A candidate passing exact validation is promoted to public patches/."""
        public_file = self.repo_root / "patches" / "xxksu" / "11_enable_susfs_for_ksu.patch"
        # Overwrite with placeholder to prove promotion overwrites it
        public_file.write_text("old placeholder patch\n", encoding="utf-8")

        res = run_pipeline(
            "xxksu-patch11",
            self.ksu_tree,
            target_tree=self.ksu_tree,
            repo_root=self.repo_root,
            promote=True,
            check_only=True,
        )

        self.assertTrue(res.promoted, "Pipeline must report promoted=True")
        self.assertNotEqual(public_file.read_text(encoding="utf-8"), "old placeholder patch\n")
        self.assertEqual(public_file.read_bytes(), res.candidate_path.read_bytes())

    def test_4_promoted_file_equals_validated_candidate_byte_for_byte(self):
        """Invariant 4: Promoted public file is byte-for-byte identical to validated candidate."""
        res = run_pipeline(
            "xxksu-patch11",
            self.ksu_tree,
            target_tree=self.ksu_tree,
            repo_root=self.repo_root,
            promote=True,
            check_only=True,
        )

        candidate_bytes = res.candidate_path.read_bytes()
        promoted_bytes = res.public_path.read_bytes()
        self.assertEqual(promoted_bytes, candidate_bytes, "Promoted bytes must match candidate bytes exactly")
        self.assertEqual(
            hashlib.sha256(promoted_bytes).hexdigest(),
            hashlib.sha256(candidate_bytes).hexdigest(),
        )

    def test_5_manifest_sha_equals_promoted_file(self):
        """Invariant 5: Manifest SHA-256 matches promoted file SHA-256."""
        res = run_pipeline(
            "xxksu-patch11",
            self.ksu_tree,
            target_tree=self.ksu_tree,
            repo_root=self.repo_root,
            promote=True,
            check_only=True,
        )

        manifest_file = self.repo_root / "patches" / "manifest.json"
        manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
        entry = next(p for p in manifest_data["patches"] if p["id"] == "xxksu-patch11")

        promoted_sha = hashlib.sha256(res.public_path.read_bytes()).hexdigest()
        self.assertEqual(entry["sha256"], promoted_sha, "Manifest SHA must match promoted file SHA")

        # Full manifest consistency check must pass
        valid, errors = verify_patch_manifest(self.repo_root)
        self.assertTrue(valid, f"Manifest verification failed: {errors}")

    def test_6_rerunning_identical_inputs_is_noop(self):
        """Invariant 6: Rerunning full pipeline with identical inputs is a clean no-op."""
        # First run: promotes candidate
        res1 = run_pipeline(
            "xxksu-patch11",
            self.ksu_tree,
            target_tree=self.ksu_tree,
            repo_root=self.repo_root,
            promote=True,
            check_only=True,
        )

        # Second run: identical inputs
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

    def test_7_validation_does_not_mutate_tree_twice(self):
        """Invariant 7: Validation check-only leaves tree untouched; application operates once."""
        # 7A: Check-only mode leaves target tree 100% byte-identical
        tree_hashes_before = {}
        for p in self.ksu_tree.rglob("*"):
            if p.is_file():
                tree_hashes_before[p.relative_to(self.ksu_tree)] = hashlib.sha256(p.read_bytes()).hexdigest()

        res = run_pipeline(
            "xxksu-patch11",
            self.ksu_tree,
            target_tree=self.ksu_tree,
            repo_root=self.repo_root,
            check_only=True,
        )
        self.assertTrue(res.validated)

        tree_hashes_after = {}
        for p in self.ksu_tree.rglob("*"):
            if p.is_file():
                tree_hashes_after[p.relative_to(self.ksu_tree)] = hashlib.sha256(p.read_bytes()).hexdigest()

        self.assertEqual(tree_hashes_before, tree_hashes_after, "Check-only mode must not mutate tree")

        # 7B: Authoritative single-pass apply operates cleanly once
        cand_file = res.candidate_path
        valid1, errors1 = validate_exact_patch_on_tree(self.ksu_tree, cand_file, dry_run=False)
        self.assertTrue(valid1, f"First application must succeed: {errors1}")

        # Attempting second application to already-patched tree must fail closed (not double-applied)
        valid2, errors2 = validate_exact_patch_on_tree(self.ksu_tree, cand_file, dry_run=False)
        self.assertFalse(valid2, "Second application to already-patched tree must fail closed")


if __name__ == "__main__":
    unittest.main()
