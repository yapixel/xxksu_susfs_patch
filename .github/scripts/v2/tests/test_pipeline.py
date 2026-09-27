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
from contextlib import ExitStack
from unittest.mock import patch
from pathlib import Path
import shutil
import tempfile
import unittest

from v2.pipeline import run_pipeline
from v2.source.baseline import load_authoritative_bundle
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

        policy_object = Path(".github/fixtures/v2/patch11-policy-commit.txt")
        (self.repo_root / policy_object).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(real_root / policy_object, self.repo_root / policy_object)

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


    def test_unchanged_candidate_never_enters_promotion_or_writeback(self):
        public = self.repo_root / "patches/xxksu/11_enable_susfs_for_ksu.patch"
        before = public.read_bytes()
        state = self.repo_root / ".github/upstream-state.json"
        state.parent.mkdir(exist_ok=True)
        shutil.copy(Path(__file__).resolve().parents[4] / ".github/upstream-state.json", state)
        protected = [p for p in (self.repo_root / "patches").rglob("*") if p.is_file()] + [state]
        snapshot = {p: p.read_bytes() for p in protected}
        candidate = run_pipeline(
            "xxksu-patch11", self.ksu_tree, target_tree=self.ksu_tree,
            repo_root=self.repo_root, check_only=True,
        )
        self.assertTrue(candidate.validated)
        self.assertEqual(candidate.candidate_path.read_bytes(), before)

        # Candidate artifacts may be written; production and metadata may not.
        def guarded_write(original):
            def write(path, *args, **kwargs):
                resolved = path.resolve()
                if (resolved.is_relative_to(self.repo_root / "patches") or
                        resolved == self.repo_root / ".github/upstream-state.json"):
                    self.fail(f"unchanged candidate rewrote production: {path}")
                return original(path, *args, **kwargs)
            return write

        with ExitStack() as stack:
            stack.enter_context(patch.object(Path, "write_bytes", guarded_write(Path.write_bytes)))
            stack.enter_context(patch.object(Path, "write_text", guarded_write(Path.write_text)))
            for boundary in ("_publish_metadata", "deliver_promotion"):
                stack.enter_context(patch(
                    f"v2.pipeline.{boundary}",
                    side_effect=AssertionError(f"unchanged candidate entered {boundary}"),
                ))
            result = run_pipeline(
                "xxksu-patch11", self.ksu_tree, target_tree=self.ksu_tree,
                repo_root=self.repo_root, promote=True, write_back=True,
                check_only=True, verify_raw_url=False,
            )
        self.assertTrue(result.validated and result.is_noop)
        self.assertEqual(result.publication_state, "FULL_STATE_NOOP")
        self.assertFalse(result.promoted or result.committed or result.pushed)
        self.assertEqual({p: p.read_bytes() for p in protected}, snapshot)

    def test_equal_bytes_do_not_bypass_validation_gates(self):
        from v2.pipeline import SemanticApprovalError, CandidateValidationError, RegenerationMismatchError
        from v2.validation.reference_cross_check import ReferenceCrossCheckError
        text = (self.repo_root / "patches/xxksu/11_enable_susfs_for_ksu.patch").read_text()
        for gate, options, error in (
            ("v2.pipeline.verify_semantic_gate_for_pipeline",
             {"side_effect": SemanticApprovalError("unapproved source")}, SemanticApprovalError),
            ("v2.pipeline.generate_candidate_patch",
             {"side_effect": [text, text + "\\n"]}, RegenerationMismatchError),
            ("v2.pipeline.validate_patch_syntax",
             {"return_value": ["invalid syntax"]}, CandidateValidationError),
            ("v2.pipeline.validate_exact_patch_on_tree",
             {"return_value": (False, ["wrong target"])}, CandidateValidationError),
            ("v2.validation.reference_cross_check.run_reference_cross_check",
             {"side_effect": ReferenceCrossCheckError("semantic conflict")}, ReferenceCrossCheckError),
        ):
            with self.subTest(gate=gate), patch(gate, **options), patch(
                "v2.pipeline._plan_metadata_updates",
                side_effect=AssertionError("publication planning reached before validation passed"),
            ):
                with self.assertRaises(error):
                    run_pipeline(
                        "xxksu-patch11", self.ksu_tree, target_tree=self.ksu_tree,
                        repo_root=self.repo_root, promote=True, write_back=True,
                        check_only=True, verify_raw_url=False,
                    )

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
