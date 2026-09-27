"""Regression tests proving the final delivery and write-back step of the pipeline.

Invariants tested:
1. failed candidate -> no commit/push
2. unchanged candidate -> no commit
3. changed + fully verified candidate -> one promotion commit
4. committed patches/ bytes == validated candidate byte-for-byte
5. manifest SHA == committed public patch
6. rerun after promotion -> clean no-op
7. reference-only Midori changes never trigger write-back
8. unrelated files are never committed
"""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from contextlib import ExitStack
import v2.pipeline as pipeline

from v2.manifests.patch_manifest import verify_patch_manifest
from v2.pipeline import (
    CandidateValidationError,
    PipelineResult,
    deliver_multi_candidates,
    run_pipeline,
)
from v2.source.baseline import load_authoritative_bundle


class TestPipelineDelivery(unittest.TestCase):
    """Test suite proving delivery, commit, push, and no-op invariants."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.tmp_dir.name).resolve()
        self.remote_dir = tempfile.TemporaryDirectory()
        self.remote_path = Path(self.remote_dir.name).resolve()

        # Initialize bare origin remote
        subprocess.run(["git", "init", "--bare", str(self.remote_path)], check=True, capture_output=True)

        # Initialize local git repo
        subprocess.run(["git", "init", "-b", "main", str(self.repo_root)], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test Delivery Bot"], cwd=self.repo_root, check=True)
        subprocess.run(["git", "config", "user.email", "test-delivery@example.com"], cwd=self.repo_root, check=True)
        subprocess.run(["git", "remote", "add", "origin", str(self.remote_path)], cwd=self.repo_root, check=True)

        # Create mock repository structure
        (self.repo_root / "patches" / "xxksu").mkdir(parents=True, exist_ok=True)
        (self.repo_root / "patches" / "sultan-android14-6.1").mkdir(parents=True, exist_ok=True)
        (self.repo_root / "patches" / "gki-android16-6.12").mkdir(parents=True, exist_ok=True)
        (self.repo_root / "candidate_patches").mkdir(parents=True, exist_ok=True)
        (self.repo_root / ".github").mkdir(parents=True, exist_ok=True)

        # Copy baseline fixtures, manifest, and upstream state
        real_root = Path(__file__).resolve().parents[4]
        shutil.copytree(real_root / ".github" / "fixtures", self.repo_root / ".github" / "fixtures")
        shutil.copy(real_root / "patches" / "xxksu" / "BASELINE.json", self.repo_root / "patches" / "xxksu" / "BASELINE.json")
        shutil.copy(real_root / "patches" / "sultan-android14-6.1" / "BASELINE.json", self.repo_root / "patches" / "sultan-android14-6.1" / "BASELINE.json")
        shutil.copy(real_root / "patches" / "gki-android16-6.12" / "BASELINE.json", self.repo_root / "patches" / "gki-android16-6.12" / "BASELINE.json")
        shutil.copy(real_root / "patches" / "manifest.json", self.repo_root / "patches" / "manifest.json")
        shutil.copy(real_root / ".github" / "upstream-state.json", self.repo_root / ".github" / "upstream-state.json")

        # Copy existing public patches
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

        # Initial commit and push to origin main
        subprocess.run(["git", "add", "-A"], cwd=self.repo_root, check=True)
        subprocess.run(["git", "commit", "-m", "base: initial repository state"], cwd=self.repo_root, check=True)
        subprocess.run(["git", "push", "-u", "origin", "main"], cwd=self.repo_root, check=True)
        self.initial_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.repo_root, capture_output=True, text=True, check=True).stdout.strip()

    def tearDown(self):
        self.tmp_dir.cleanup()
        self.remote_dir.cleanup()

    def test_1_failed_candidate_no_commit_or_push(self):
        """Invariant 1: When candidate validation fails, no commit or push occurs."""
        protected = list((self.repo_root / "patches").rglob("*")) + [self.repo_root / ".github/upstream-state.json"]
        before = {p: p.read_bytes() for p in protected if p.is_file()}
        target_tree = self.repo_root / "corrupted_target"
        shutil.copytree(self.ksu_tree, target_tree)
        (target_tree / "kernel" / "ksu.c").write_text("corrupted target context\n", encoding="utf-8")

        with self.assertRaises(CandidateValidationError):
            run_pipeline(
                "xxksu-patch11",
                self.ksu_tree,
                target_tree=target_tree,
                repo_root=self.repo_root,
                promote=True,
                write_back=True,
                verify_raw_url=False,
            )

        head_after = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.repo_root, capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(head_after, self.initial_commit, "HEAD must not move on candidate validation failure")

        remote_head = subprocess.run(["git", "rev-parse", "main"], cwd=self.remote_path, capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(remote_head, self.initial_commit, "Remote main must not move on candidate validation failure")
        self.assertEqual({p: p.read_bytes() for p in before}, before)

    def test_delivery_bytes_manifest_and_noop(self):
        res = run_pipeline(
            "xxksu-patch11",
            self.ksu_tree,
            target_tree=self.ksu_tree,
            repo_root=self.repo_root,
            promote=True,
            check_only=True,
            write_back=True,
            verify_raw_url=False,
        )

        self.assertTrue(res.is_noop, "Pipeline must report is_noop=True")
        self.assertFalse(res.committed, "Pipeline must not commit unchanged candidate")
        self.assertFalse(res.pushed, "Pipeline must not push when unchanged")

        head_after = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.repo_root, capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(head_after, self.initial_commit, "HEAD must remain at initial commit")

        public_patch = self.repo_root / "patches" / "xxksu" / "11_enable_susfs_for_ksu.patch"
        public_patch.write_text("old placeholder patch\n", encoding="utf-8")
        subprocess.run(["git", "add", str(public_patch)], cwd=self.repo_root, check=True)
        subprocess.run(["git", "commit", "-m", "mock: simulate older public patch"], cwd=self.repo_root, check=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=self.repo_root, check=True)
        base_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.repo_root, capture_output=True, text=True, check=True).stdout.strip()

        res = run_pipeline(
            "xxksu-patch11",
            self.ksu_tree,
            target_tree=self.ksu_tree,
            repo_root=self.repo_root,
            promote=True,
            check_only=True,
            write_back=True,
            verify_raw_url=False,
        )

        self.assertTrue(res.promoted, "Candidate must be promoted")
        self.assertEqual(res.publication_state, "PATCH_PROMOTION")
        self.assertTrue(res.committed, "Candidate change must be committed")
        self.assertTrue(res.pushed, "Candidate change must be pushed")

        head_after = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.repo_root, capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(head_after, res.commit_sha)

        # Verify exactly 1 commit on top of base_commit
        parent_commit = subprocess.run(["git", "rev-parse", "HEAD~1"], cwd=self.repo_root, capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(parent_commit, base_commit, "Exactly one commit must be added on top of base")

        # Verify commit message
        log_msg = subprocess.run(["git", "log", "-1", "--pretty=%B"], cwd=self.repo_root, capture_output=True, text=True, check=True).stdout
        self.assertIn("auto(pipeline): deliver verified xxksu-patch11 production patch", log_msg)
        self.assertIn(res.candidate_sha256, log_msg)

        candidate_bytes = res.candidate_path.read_bytes()

        # Check local committed file
        local_bytes = public_patch.read_bytes()
        self.assertEqual(local_bytes, candidate_bytes)

        # Check origin/main via git show
        show_proc = subprocess.run(
            ["git", "show", "origin/main:patches/xxksu/11_enable_susfs_for_ksu.patch"],
            cwd=self.repo_root,
            capture_output=True,
            check=True,
        )
        self.assertEqual(show_proc.stdout, candidate_bytes, "origin/main must contain exact validated candidate bytes")

        manifest_file = self.repo_root / "patches" / "manifest.json"
        manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
        entry = next(p for p in manifest_data["patches"] if p["id"] == "xxksu-patch11")
        self.assertEqual(entry["sha256"], res.candidate_sha256)

        valid, errors = verify_patch_manifest(self.repo_root)
        self.assertTrue(valid, f"Manifest verification failed: {errors}")

        head_after_first = res.commit_sha
        # Second: rerun with identical inputs
        res2 = run_pipeline(
            "xxksu-patch11",
            self.ksu_tree,
            target_tree=self.ksu_tree,
            repo_root=self.repo_root,
            promote=True,
            check_only=True,
            write_back=True,
            verify_raw_url=False,
        )
        self.assertTrue(res2.is_noop, "Rerun must report is_noop=True")
        self.assertFalse(res2.committed, "Rerun must not commit")
        self.assertFalse(res2.pushed, "Rerun must not push")

        head_after_second = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.repo_root, capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(head_after_second, head_after_first, "HEAD must not move on clean no-op rerun")


    def test_7_reference_only_midori_does_not_trigger_write_back(self):
        """Invariant 7: Reference-only tracker modifications do not trigger production write-back."""
        # Simulate modified reference tracker in upstream-state.json
        state_file = self.repo_root / ".github" / "upstream-state.json"
        state_data = json.loads(state_file.read_text(encoding="utf-8"))
        state_data["sources"]["reference"]["midori_gki_patch_50"]["sha256"] = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
        state_file.write_text(json.dumps(state_data, indent=2) + "\n", encoding="utf-8")

        res = run_pipeline(
            "xxksu-patch11",
            self.ksu_tree,
            target_tree=self.ksu_tree,
            repo_root=self.repo_root,
            promote=True,
            check_only=True,
            write_back=True,
            verify_raw_url=False,
        )

        self.assertTrue(res.is_noop, "Authoritative pipeline must remain no-op despite reference tracker drift")
        self.assertFalse(res.committed, "Reference tracker change must not trigger commit")

        head_after = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.repo_root, capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(head_after, self.initial_commit, "HEAD must remain unchanged")

    def test_8_unrelated_files_are_not_committed(self):
        """Invariant 8: Unrelated files in workspace are never staged or committed."""
        # Create unrelated dirty file and untracked file
        unrelated_untracked = self.repo_root / "unrelated_scratch.txt"
        unrelated_untracked.write_text("should never be committed\n", encoding="utf-8")

        # Overwrite with placeholder to trigger promotion commit
        public_patch = self.repo_root / "patches" / "xxksu" / "11_enable_susfs_for_ksu.patch"
        public_patch.write_text("old placeholder patch\n", encoding="utf-8")
        subprocess.run(["git", "add", str(public_patch)], cwd=self.repo_root, check=True)
        subprocess.run(["git", "commit", "-m", "mock: simulate older public patch"], cwd=self.repo_root, check=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=self.repo_root, check=True)

        res = run_pipeline(
            "xxksu-patch11",
            self.ksu_tree,
            target_tree=self.ksu_tree,
            repo_root=self.repo_root,
            promote=True,
            check_only=True,
            write_back=True,
            verify_raw_url=False,
        )

        self.assertTrue(res.committed)

        # Inspect files in the promotion commit
        show_files = subprocess.run(
            ["git", "show", "--name-only", "--pretty=format:", "HEAD"],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        committed_files = [f.strip() for f in show_files if f.strip()]

        self.assertNotIn("unrelated_scratch.txt", committed_files)
        for f in committed_files:
            self.assertTrue(
                f.startswith("patches/") or f == ".github/upstream-state.json",
                f"Unexpected file committed: {f}",
            )

    def test_patch51_target_delivery(self):
        real_root = Path(__file__).resolve().parents[4]
        for target, patch_id, source, output in (
            ("sultan-android14-6.1", "sultan-android14-6.1-patch51",
             ".github/fixtures/sultan/50_add_susfs_in_gki-android14-6.1.patch",
             "51_deinlined_susfs_hooks_sultan-android14-6.1.patch"),
            ("gki-android16-6.12", "gki-android16-6.12-r38-patch51",
             ".github/fixtures/r38/51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch",
             "51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch"),
        ):
            with self.subTest(target=target):
                public_patch = self.repo_root / "patches" / target / output
                public_patch.write_text("old patch placeholder\n", encoding="utf-8")
                subprocess.run(["git", "add", str(public_patch)], cwd=self.repo_root, check=True)
                subprocess.run(["git", "commit", "-m", "mock: older target patch"], cwd=self.repo_root, check=True)
                subprocess.run(["git", "push", "origin", "main"], cwd=self.repo_root, check=True)
                res = run_pipeline(patch_id, real_root / source, target_tree=None, repo_root=self.repo_root,
                                   promote=True, check_only=True, write_back=True, verify_raw_url=False)
                self.assertTrue(res.promoted and res.committed and res.pushed)
                self.assertEqual(public_patch.read_bytes(), res.candidate_path.read_bytes())
                committed = subprocess.run(["git", "show", f"origin/main:patches/{target}/{output}"],
                                           cwd=self.repo_root, capture_output=True, check=True).stdout
                self.assertEqual(committed, res.candidate_path.read_bytes())
                valid, errors = verify_patch_manifest(self.repo_root)
                self.assertTrue(valid, errors)
                rerun = run_pipeline(patch_id, real_root / source, target_tree=None, repo_root=self.repo_root,
                                     promote=True, check_only=True, write_back=True, verify_raw_url=False)
                self.assertTrue(rerun.is_noop)
                self.assertFalse(rerun.committed or rerun.pushed)


    def test_11_multi_candidate_both_changed_single_commit(self):
        """Invariant: Both Sultan and GKI candidates changing produces exactly ONE delivery commit."""
        real_root = Path(__file__).resolve().parents[4]
        sultan_patch = self.repo_root / "patches" / "sultan-android14-6.1" / "51_deinlined_susfs_hooks_sultan-android14-6.1.patch"
        gki_patch = self.repo_root / "patches" / "gki-android16-6.12" / "51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch"

        sultan_patch.write_text("old sultan patch placeholder\n", encoding="utf-8")
        gki_patch.write_text("old gki patch placeholder\n", encoding="utf-8")
        subprocess.run(["git", "add", str(sultan_patch), str(gki_patch)], cwd=self.repo_root, check=True)
        subprocess.run(["git", "commit", "-m", "mock: simulate older sultan and gki patches"], cwd=self.repo_root, check=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=self.repo_root, check=True)

        head_before = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.repo_root, capture_output=True, text=True, check=True).stdout.strip()

        cand_sultan = real_root / ".github" / "fixtures" / "sultan" / "51_deinlined_susfs_hooks_sultan-android14-6.1.patch"
        cand_gki = real_root / ".github" / "fixtures" / "r38" / "51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch"

        with patch("v2.pipeline._publish_metadata", wraps=pipeline._publish_metadata) as metadata:
            promoted, pushed, commit_sha, shas = deliver_multi_candidates(
                {
                    "sultan-android14-6.1-patch51": cand_sultan,
                    "gki-android16-6.12-r38-patch51": cand_gki,
                },
                repo_root=self.repo_root,
                write_back=True,
                verify_raw_url=False,
            )
        metadata.assert_called_once()

        self.assertTrue(promoted, "Both targets should be promoted")
        self.assertTrue(pushed, "Changes should be pushed")
        self.assertIsNotNone(commit_sha)

        # Verify exactly ONE new commit was created on main
        rev_count = subprocess.run(
            ["git", "rev-list", "--count", f"{head_before}..HEAD"],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        self.assertEqual(rev_count, "1", f"Expected exactly 1 delivery commit, got {rev_count}")

        # Check commit message
        log_msg = subprocess.run(["git", "log", "-1", "--pretty=%B"], cwd=self.repo_root, capture_output=True, text=True, check=True).stdout
        self.assertIn("auto(pipeline): deliver verified 51 patch production outputs", log_msg)
        self.assertIn(shas["sultan-android14-6.1-patch51"], log_msg)
        self.assertIn(shas["gki-android16-6.12-r38-patch51"], log_msg)

        # Byte equality on origin/main
        self.assertEqual(sultan_patch.read_bytes(), cand_sultan.read_bytes())
        self.assertEqual(gki_patch.read_bytes(), cand_gki.read_bytes())

        show_sultan = subprocess.run(
            ["git", "show", "origin/main:patches/sultan-android14-6.1/51_deinlined_susfs_hooks_sultan-android14-6.1.patch"],
            cwd=self.repo_root,
            capture_output=True,
            check=True,
        ).stdout
        self.assertEqual(show_sultan, cand_sultan.read_bytes())

        show_gki = subprocess.run(
            ["git", "show", "origin/main:patches/gki-android16-6.12/51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch"],
            cwd=self.repo_root,
            capture_output=True,
            check=True,
        ).stdout
        self.assertEqual(show_gki, cand_gki.read_bytes())

        # Manifest consistency
        valid, errors = verify_patch_manifest(self.repo_root)
        self.assertTrue(valid, f"Manifest invalid after multi-delivery: {errors}")

    def test_12_multi_candidate_one_changed_one_unchanged(self):
        real_root = Path(__file__).resolve().parents[4]
        candidates = {pid: real_root / rel for pid, rel in pipeline.TARGET_REL_PATHS.items()
                      if pid != "xxksu-patch11"}
        for index, changed_id in enumerate(candidates):
            with self.subTest(changed=changed_id):
                changed_rel = pipeline.TARGET_REL_PATHS[changed_id]
                changed_path = self.repo_root / changed_rel
                changed_path.write_text("old patch placeholder\n")
                subprocess.run(["git", "add", str(changed_path)], cwd=self.repo_root, check=True)
                subprocess.run(["git", "commit", "-m", "mock: old single target"], cwd=self.repo_root, check=True)
                subprocess.run(["git", "push", "origin", "main"], cwd=self.repo_root, check=True)
                head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo_root, text=True).strip()
                unchanged_id = next(pid for pid in candidates if pid != changed_id)
                unchanged = pipeline.TARGET_REL_PATHS[unchanged_id]
                protected = {self.repo_root / unchanged, self.repo_root / unchanged.parent / "BASELINE.json"}
                snapshot = {p: p.read_bytes() for p in protected}

                def guard(original):
                    def write(path, *args, **kwargs):
                        self.assertNotIn(path.resolve(), protected)
                        return original(path, *args, **kwargs)
                    return write

                with patch.object(Path, "write_bytes", guard(Path.write_bytes)), \
                     patch.object(Path, "write_text", guard(Path.write_text)), \
                     patch("v2.pipeline._publish_metadata", wraps=pipeline._publish_metadata) as metadata:
                    promoted, pushed, commit, _ = deliver_multi_candidates(
                        candidates, repo_root=self.repo_root, write_back=True, verify_raw_url=False,
                        upstream_commits={changed_id: str(index + 1) * 40},
                    )
                self.assertTrue(promoted and pushed)
                metadata.assert_called_once()
                self.assertEqual(subprocess.check_output(["git", "rev-parse", "HEAD^"], cwd=self.repo_root, text=True).strip(), head)
                self.assertEqual(subprocess.check_output(["git", "rev-parse", "origin/main"], cwd=self.repo_root, text=True).strip(), commit)
                changed = set(subprocess.check_output(["git", "diff", "--name-only", head, "HEAD"], cwd=self.repo_root, text=True).splitlines())
                self.assertEqual(changed, {str(changed_rel), str(changed_rel.parent / "BASELINE.json"),
                                           "patches/manifest.json", ".github/upstream-state.json"})
                self.assertEqual({p: p.read_bytes() for p in protected}, snapshot)
                for pid, candidate in candidates.items():
                    self.assertEqual((self.repo_root / pipeline.TARGET_REL_PATHS[pid]).read_bytes(), candidate.read_bytes())
                self.assertTrue(verify_patch_manifest(self.repo_root)[0])

    def test_13_multi_candidate_both_unchanged_noop(self):
        """Invariant: When both candidates are already up to date, clean NO_OP with 0 commits."""
        real_root = Path(__file__).resolve().parents[4]
        cand_sultan = real_root / "patches/sultan-android14-6.1/51_deinlined_susfs_hooks_sultan-android14-6.1.patch"
        cand_gki = real_root / "patches/gki-android16-6.12/51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch"

        protected = [p for p in (self.repo_root / "patches").rglob("*") if p.is_file()]
        protected.append(self.repo_root / ".github/upstream-state.json")
        before = {p: p.read_bytes() for p in protected}
        with patch("v2.pipeline._publish_metadata", side_effect=AssertionError("no-op entered metadata publication")), \
             patch.object(Path, "write_bytes", side_effect=AssertionError("no-op wrote bytes")), \
             patch.object(Path, "write_text", side_effect=AssertionError("no-op wrote text")), \
             patch("v2.pipeline.subprocess.run", side_effect=AssertionError("no-op entered Git delivery")):
            promoted, pushed, commit_sha, _ = deliver_multi_candidates(
                {
                    "sultan-android14-6.1-patch51": cand_sultan,
                    "gki-android16-6.12-r38-patch51": cand_gki,
                },
                repo_root=self.repo_root,
                write_back=True,
                verify_raw_url=False,
            )
        self.assertEqual({p: p.read_bytes() for p in protected}, before)
        self.assertFalse(promoted)
        self.assertFalse(pushed)
        self.assertIsNone(commit_sha)
        self.assertEqual(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo_root,
                                                text=True).strip(), self.initial_commit)
        self.assertEqual(subprocess.check_output(["git", "rev-parse", "origin/main"], cwd=self.repo_root,
                                                text=True).strip(), self.initial_commit)

    def test_metadata_only_promotion_then_full_noop(self):
        real_root = Path(__file__).resolve().parents[4]
        candidates = {pid: real_root / rel for pid, rel in pipeline.TARGET_REL_PATHS.items()
                      if pid != "xxksu-patch11"}
        # Real source tree commit, with unchanged accepted source contents.
        for command in (
            ["git", "init", str(self.ksu_tree)],
            ["git", "config", "user.name", "Source Fixture"],
            ["git", "config", "user.email", "source@example.com"],
            ["git", "add", "."],
            ["git", "commit", "-m", "accepted source fixture"],
        ):
            subprocess.run(command, cwd=self.ksu_tree, check=True, capture_output=True)
        source_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.ksu_tree, text=True).strip()
        for mode in ("single", "multi"):
            with self.subTest(mode=mode):
                head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo_root, text=True).strip()
                public = [self.repo_root / rel for rel in pipeline.TARGET_REL_PATHS.values()]
                before = {p: p.read_bytes() for p in public}
                baseline = "patches/xxksu/BASELINE.json" if mode == "single" else "patches/sultan-android14-6.1/BASELINE.json"
                commits = {"sultan-android14-6.1-patch51": "a" * 40}

                def guard(original):
                    def write(path, *args, **kwargs):
                        self.assertNotIn(path.resolve(), before, "metadata-only promotion rewrote a patch")
                        return original(path, *args, **kwargs)
                    return write

                def publish():
                    if mode == "single":
                        result = run_pipeline(
                            "xxksu-patch11", self.ksu_tree, target_tree=self.ksu_tree,
                            repo_root=self.repo_root, promote=True, check_only=True,
                            write_back=True, verify_raw_url=False,
                        )
                        return result
                    return deliver_multi_candidates(candidates, repo_root=self.repo_root,
                        upstream_commits=commits, write_back=True, verify_raw_url=False)

                with patch.object(Path, "write_bytes", guard(Path.write_bytes)), \
                     patch.object(Path, "write_text", guard(Path.write_text)), \
                     patch("v2.pipeline._publish_metadata", wraps=pipeline._publish_metadata) as metadata:
                    result = publish()
                metadata.assert_called_once()
                if mode == "single":
                    self.assertEqual(result.publication_state, "METADATA_ONLY_PROMOTION")
                    self.assertFalse(result.promoted or result.is_noop)
                    self.assertTrue(result.committed and result.pushed)
                else:
                    self.assertTrue(result[0] and result[1])
                self.assertEqual(subprocess.check_output(["git", "rev-parse", "HEAD^"], cwd=self.repo_root, text=True).strip(), head)
                changed = set(subprocess.check_output(["git", "diff", "--name-only", head, "HEAD"], cwd=self.repo_root, text=True).splitlines())
                self.assertEqual(changed, {baseline, "patches/manifest.json", ".github/upstream-state.json"})
                data = json.loads((self.repo_root / baseline).read_text())
                self.assertEqual(data["upstream" if mode == "single" else "susfs"]["resolved_commit"],
                                 source_commit if mode == "single" else "a" * 40)
                self.assertEqual({p: p.read_bytes() for p in public}, before)
                self.assertTrue(verify_patch_manifest(self.repo_root)[0])
                current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo_root)
                with patch("v2.pipeline._publish_metadata", side_effect=AssertionError("repeated metadata promotion")), \
                     patch("v2.pipeline.deliver_promotion", side_effect=AssertionError("no-op delivery")):
                    result = publish()
                if mode == "single":
                    self.assertEqual(result.publication_state, "FULL_STATE_NOOP")
                else:
                    self.assertEqual(result[:3], (False, False, None))
                self.assertEqual(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo_root), current)

    def test_14_validation_run_is_read_only(self):
        """Invariant: Validation-only run produces candidate without touching patches/ or metadata."""
        real_root = Path(__file__).resolve().parents[4]
        public_patch = self.repo_root / "patches" / "sultan-android14-6.1" / "51_deinlined_susfs_hooks_sultan-android14-6.1.patch"
        orig_bytes = public_patch.read_bytes()
        orig_manifest = (self.repo_root / "patches" / "manifest.json").read_bytes()

        cand_dir = self.repo_root / "test_candidate_dir"
        res = run_pipeline(
            "sultan-android14-6.1-patch51",
            real_root / ".github" / "fixtures" / "sultan" / "50_add_susfs_in_gki-android14-6.1.patch",
            target_tree=None,
            candidate_dir=cand_dir,
            repo_root=self.repo_root,
            promote=False,
            check_only=True,
            write_back=False,
            verify_raw_url=False,
        )

        self.assertTrue(res.validated)
        self.assertFalse(res.promoted)
        self.assertFalse(res.committed)
        self.assertFalse(res.pushed)
        self.assertTrue(res.candidate_path.is_file())

        # Public files completely unmodified
        self.assertEqual(public_patch.read_bytes(), orig_bytes)
        self.assertEqual((self.repo_root / "patches" / "manifest.json").read_bytes(), orig_manifest)


if __name__ == "__main__":
    unittest.main()
