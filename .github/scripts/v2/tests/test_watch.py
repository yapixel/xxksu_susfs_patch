"""Focused test suite for Phase 1 upstream watch, classification, and escalation."""

from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from v2.watch.checker import (
    UpstreamWatcher,
    compute_composite_hash,
    fetch_remote_commit,
)
from v2.watch.escalation import (
    format_issue_body,
    format_issue_title,
)
from v2.watch.model import (
    SourceResult,
    WatchClassification,
    WatchReport,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
STATE_FILE = REPO_ROOT / ".github" / "upstream-state.json"


class WatchModelTests(unittest.TestCase):
    def test_all_classifications_present(self):
        expected = {
            "NO_CHANGE",
            "IRRELEVANT_CHANGE",
            "SAFE_REGEN_CANDIDATE",
            "SEMANTIC_DRIFT",
            "ANCHOR_DRIFT",
            "REFERENCE_DRIFT",
            "SOURCE_IDENTITY_ERROR",
        }
        actual = {c.value for c in WatchClassification}
        self.assertEqual(actual, expected)

    def test_escalation_predicate(self):
        failing = [
            WatchClassification.SEMANTIC_DRIFT,
            WatchClassification.ANCHOR_DRIFT,
            WatchClassification.SOURCE_IDENTITY_ERROR,
        ]
        non_failing = [
            WatchClassification.NO_CHANGE,
            WatchClassification.IRRELEVANT_CHANGE,
            WatchClassification.SAFE_REGEN_CANDIDATE,
            WatchClassification.REFERENCE_DRIFT,
        ]

        for c in failing:
            res = SourceResult(
                source_id="test",
                source_type="authoritative",
                classification=c,
                old_identity="1",
                new_identity="2",
                old_content_hash="h1",
                new_content_hash="h2",
            )
            self.assertTrue(res.requires_escalation(), f"Expected escalation for {c}")

        for c in non_failing:
            res = SourceResult(
                source_id="test",
                source_type="authoritative",
                classification=c,
                old_identity="1",
                new_identity="2",
                old_content_hash="h1",
                new_content_hash="h2",
            )
            self.assertFalse(res.requires_escalation(), f"Expected no escalation for {c}")

    def test_composite_hash_deterministic(self):
        map1 = {"b.c": "sha256:222", "a.c": "sha256:111"}
        map2 = {"a.c": "sha256:111", "b.c": "sha256:222"}
        self.assertEqual(compute_composite_hash(map1), compute_composite_hash(map2))


class WatchStateTests(unittest.TestCase):
    def test_upstream_state_file_valid(self):
        self.assertTrue(STATE_FILE.is_file(), "upstream-state.json must exist")
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        self.assertEqual(data.get("schema"), "xxksu-susfs-upstream-state/v1")
        sources = data.get("sources", {})

        auth = sources.get("authoritative", {})
        self.assertIn("backslashxx_kernelsu", auth)
        self.assertIn("susfs_sultan", auth)
        self.assertIn("susfs_gki", auth)

        ref = sources.get("reference", {})
        self.assertIn("midori_kernelsu_xx_patch", ref)
        self.assertIn("midori_gki_patch_50", ref)

    @patch("subprocess.run")
    def test_fetch_remote_commit_resolves_exact_ref(self, mock_run):
        # When git ls-remote returns multiple refs including HEAD, exact ref must match
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = (
            "30e66dc3a5c65954de865afd8f44682866887544\tHEAD\n"
            "c254cf2dcdffcfb466b7ac6706f705a339adeaa0\trefs/heads/sultan-shiba-susfs-minimal\n"
        )
        mock_run.return_value = mock_proc

        commit = fetch_remote_commit("https://gitlab.com/simonpunk/susfs4ksu.git", "sultan-shiba-susfs-minimal")
        self.assertEqual(commit, "c254cf2dcdffcfb466b7ac6706f705a339adeaa0")
        # Ensure HEAD was not in candidates passed to git ls-remote
        args = mock_run.call_args[0][0]
        self.assertNotIn("HEAD", args)


class WatchClassificationTests(unittest.TestCase):
    def setUp(self):
        self.watcher = UpstreamWatcher(repo_root=REPO_ROOT, state_path=STATE_FILE)

    def test_dry_run_all_no_change(self):
        report = self.watcher.run_all(fetch_remote=False)
        self.assertEqual(len(report.results), 5)
        for r in report.results:
            self.assertEqual(r.classification, WatchClassification.NO_CHANGE)
        self.assertFalse(report.has_failures)

    @patch("v2.watch.checker.fetch_remote_commit")
    def test_upstream_commit_unchanged_yields_no_change(self, mock_commit):
        mock_commit.return_value = "0b138d6a9cfe4dc163aa05c21b1e6a14ff868230"
        info = {
            "repository": "https://github.com/backslashxx/KernelSU.git",
            "ref": "master",
            "commit": "0b138d6a9cfe4dc163aa05c21b1e6a14ff868230",
            "relevant_content_hash": "sha256:ebb3ae93",
            "tracked_files": {},
        }
        res = self.watcher.check_backslashxx_kernelsu(info, fetch_remote=True)
        self.assertEqual(res.classification, WatchClassification.NO_CHANGE)

    @patch("v2.watch.checker.fetch_remote_commit")
    @patch("v2.watch.checker.fetch_git_files")
    def test_irrelevant_change_when_tracked_files_identical(self, mock_files, mock_commit):
        mock_commit.return_value = "ffffffffffffffffffffffffffffffffffffffff"
        mock_files.return_value = {
            "kernel/Kconfig": "content_kconfig",
        }
        info = {
            "repository": "https://github.com/backslashxx/KernelSU.git",
            "ref": "master",
            "commit": "0b138d6a9cfe4dc163aa05c21b1e6a14ff868230",
            "tracked_files": {
                "kernel/Kconfig": f"sha256:{__import__('hashlib').sha256(b'content_kconfig').hexdigest()}",
            },
        }
        info["relevant_content_hash"] = compute_composite_hash(info["tracked_files"])

        res = self.watcher.check_backslashxx_kernelsu(info, fetch_remote=True)
        self.assertEqual(res.classification, WatchClassification.IRRELEVANT_CHANGE)
        self.assertEqual(res.new_identity, "ffffffffffffffffffffffffffffffffffffffff")

    @patch("v2.watch.checker.fetch_remote_commit")
    @patch("v2.watch.checker.fetch_git_files")
    def test_anchor_drift_detected_when_anchor_missing(self, mock_files, mock_commit):
        mock_commit.return_value = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        # Content with corrupted / missing anchor
        mock_files.return_value = {
            "kernel/Kconfig": "totally corrupted without ksu config entries",
        }
        info = {
            "repository": "https://github.com/backslashxx/KernelSU.git",
            "ref": "master",
            "commit": "0b138d6a9cfe4dc163aa05c21b1e6a14ff868230",
            "relevant_content_hash": "sha256:old_hash",
            "tracked_files": {
                "kernel/Kconfig": "sha256:different_hash",
            },
        }
        res = self.watcher.check_backslashxx_kernelsu(info, fetch_remote=True)
        self.assertEqual(res.classification, WatchClassification.ANCHOR_DRIFT)
        self.assertTrue(res.requires_escalation())
        self.assertIn("kernel/Kconfig", res.affected_files)

    @patch("v2.watch.checker.fetch_url_content")
    def test_reference_drift_when_reference_changes(self, mock_url):
        mock_url.return_value = ("new reference patch content", "sha256:new_ref_hash_1234")
        info = {
            "url": "https://github.com/midori01/KernelSU/commit/xx.patch",
            "sha256": "sha256:old_ref_hash_0000",
            "commit_or_ref": "bc1b8e371d80",
        }
        res = self.watcher.check_reference_source("midori_kernelsu_xx_patch", info, fetch_remote=True)
        self.assertEqual(res.classification, WatchClassification.REFERENCE_DRIFT)
        self.assertEqual(res.source_type, "reference")
        # Reference drift must NOT trigger escalation or candidate patch
        self.assertFalse(res.requires_escalation())
        self.assertIsNone(res.candidate_patch)

    @patch("v2.watch.checker.fetch_remote_commit")
    def test_source_identity_error_on_network_failure(self, mock_commit):
        mock_commit.side_effect = RuntimeError("Connection timed out")
        info = {
            "repository": "https://github.com/backslashxx/KernelSU.git",
            "ref": "master",
            "commit": "0b138d6a9cfe4dc163aa05c21b1e6a14ff868230",
            "relevant_content_hash": "sha256:hash",
            "tracked_files": {},
        }
        res = self.watcher.check_backslashxx_kernelsu(info, fetch_remote=True)
        self.assertEqual(res.classification, WatchClassification.SOURCE_IDENTITY_ERROR)
        self.assertTrue(res.requires_escalation())
        self.assertIn("Connection timed out", res.details)


class WatchEscalationTests(unittest.TestCase):
    def test_issue_formatting(self):
        result = SourceResult(
            source_id="test_source",
            source_type="authoritative",
            classification=WatchClassification.SEMANTIC_DRIFT,
            old_identity="old_commit_123",
            new_identity="new_commit_456",
            old_content_hash="sha256:old_hash",
            new_content_hash="sha256:new_hash",
            affected_files=("fs/exec.c", "kernel/ksu.c"),
            affected_semantics=("susfs.exec.hook",),
            details="Context line mismatch in hunk #3",
            reproduction_command="PYTHONPATH=.github/scripts python3 -m v2.watch.cli --source test_source",
        )

        title = format_issue_title(result)
        self.assertIn("[AGY-REQUIRED]", title)
        self.assertIn("test_source", title)
        self.assertIn("SEMANTIC_DRIFT", title)

        body = format_issue_body(result)
        self.assertIn("old_commit_123", body)
        self.assertIn("new_commit_456", body)
        self.assertIn("fs/exec.c", body)
        self.assertIn("susfs.exec.hook", body)
        self.assertIn("Context line mismatch", body)
        self.assertIn("PYTHONPATH=.github/scripts python3 -m v2.watch.cli", body)


class SuSFSWatcherRegressionTests(unittest.TestCase):
    def setUp(self):
        self.watcher = UpstreamWatcher(repo_root=REPO_ROOT, state_path=STATE_FILE)

    def test_deinline_target_isolation(self):
        from deinline_50_to_51 import deinline_patch_content

        sample_patch = """diff --git a/fs/statfs.c b/fs/statfs.c
--- a/fs/statfs.c
+++ b/fs/statfs.c
@@ -10,1 +10,2 @@
 int foo;
+int bar;
"""
        gki_cand = deinline_patch_content(sample_patch, target="gki-android16-6.12")
        self.assertIn("drivers/input/input.c", gki_cand)
        self.assertIn("354", gki_cand)
        self.assertNotIn("387", gki_cand)
        self.assertNotIn("diff --git a/fs/susfs.c", gki_cand)
        self.assertNotIn("diff --git a/include/linux/susfs.h", gki_cand)

        sultan_cand = deinline_patch_content(sample_patch, target="sultan-android14-6.1")
        self.assertIn("drivers/input/input.c", sultan_cand)
        self.assertIn("387", sultan_cand)
        self.assertIn("diff --git a/fs/susfs.c", sultan_cand)
        self.assertIn("diff --git a/include/linux/susfs.h", sultan_cand)

    @patch("v2.watch.checker.fetch_remote_commit")
    @patch("v2.watch.checker.fetch_git_files")
    def test_susfs_drift_detected_on_unbundled_file(self, mock_files, mock_commit):
        mock_commit.return_value = "new_sultan_commit_c254cf2d"
        new_patch = """diff --git a/fs/super.c b/fs/super.c
--- a/fs/super.c
+++ b/fs/super.c
@@ -10,1 +10,2 @@
 int a;
+int b;
"""
        mock_files.return_value = {
            "kernel_patches/50_add_susfs_in_gki-android14-6.1.patch": new_patch,
        }
        info = {
            "repository": "https://gitlab.com/simonpunk/susfs4ksu.git",
            "ref": "sultan-shiba-susfs-minimal",
            "commit": "old_commit_7fd1da8e",
            "relevant_content_hash": "sha256:old_hash",
            "tracked_files": {
                "kernel_patches/50_add_susfs_in_gki-android14-6.1.patch": "sha256:different",
            },
        }
        res = self.watcher.check_susfs_authoritative("susfs_sultan", "sultan-android14-6.1", info, fetch_remote=True)
        self.assertEqual(res.classification, WatchClassification.SEMANTIC_DRIFT)
        self.assertTrue(res.requires_escalation())
        self.assertIn("unbundled kernel files", res.details)
        self.assertIn("fs/super.c", res.details)
        self.assertIn("Baseline expansion required", res.details)

    @patch("v2.watch.checker.fetch_remote_commit")
    @patch("v2.watch.checker.fetch_git_files")
    def test_susfs_drift_when_candidate_fails_strict_apply(self, mock_files, mock_commit):
        mock_commit.return_value = "new_gki_commit_2528bdb0"
        # Context mismatch on existing bundled file
        new_patch = """diff --git a/fs/stat.c b/fs/stat.c
--- a/fs/stat.c
+++ b/fs/stat.c
@@ -9999,1 +9999,2 @@
 completely_nonexistent_context_line();
+int injected_var;
"""
        mock_files.return_value = {
            "kernel_patches/50_add_susfs_in_gki-android16-6.12.patch": new_patch,
        }
        info = {
            "repository": "https://gitlab.com/simonpunk/susfs4ksu.git",
            "ref": "gki-android16-6.12",
            "commit": "old_commit_c8f64e41",
            "relevant_content_hash": "sha256:old_hash",
            "tracked_files": {
                "kernel_patches/50_add_susfs_in_gki-android16-6.12.patch": "sha256:different",
            },
        }
        res = self.watcher.check_susfs_authoritative("susfs_gki", "gki-android16-6.12", info, fetch_remote=True)
        self.assertEqual(res.classification, WatchClassification.SEMANTIC_DRIFT)
        self.assertTrue(res.requires_escalation())
        self.assertIn("failed strict application", res.details)

    @patch("v2.watch.checker.fetch_remote_commit")
    @patch("v2.watch.checker.fetch_git_files")
    @patch("v2.watch.checker.apply_patch_to_bundle")
    def test_susfs_drift_detected_on_unknown_semantic_unit(self, mock_apply, mock_files, mock_commit):
        mock_commit.return_value = "new_gki_commit_2528bdb0"
        mock_apply.return_value = None

        old_patch = """diff --git a/fs/statfs.c b/fs/statfs.c
--- a/fs/statfs.c
+++ b/fs/statfs.c
@@ -10,1 +10,2 @@
 int flags;
+int old_flags;
"""
        new_patch = """diff --git a/fs/statfs.c b/fs/statfs.c
--- a/fs/statfs.c
+++ b/fs/statfs.c
@@ -10,1 +10,3 @@
 int flags;
+int old_flags;
+int totally_new_unmodeled_susfs_hook(void);
"""
        def mock_fetch(repo_url, commit, paths):
            if commit == "old_commit_c8f64e41":
                return {"kernel_patches/50_add_susfs_in_gki-android16-6.12.patch": old_patch}
            return {"kernel_patches/50_add_susfs_in_gki-android16-6.12.patch": new_patch}

        mock_files.side_effect = mock_fetch

        info = {
            "repository": "https://gitlab.com/simonpunk/susfs4ksu.git",
            "ref": "gki-android16-6.12",
            "commit": "old_commit_c8f64e41",
            "relevant_content_hash": "sha256:old_hash",
            "tracked_files": {
                "kernel_patches/50_add_susfs_in_gki-android16-6.12.patch": "sha256:different",
            },
        }
        res = self.watcher.check_susfs_authoritative("susfs_gki", "gki-android16-6.12", info, fetch_remote=True)
        self.assertEqual(res.classification, WatchClassification.SEMANTIC_DRIFT)
        self.assertTrue(res.requires_escalation())
        self.assertIn("UNKNOWN semantic units", res.details)


if __name__ == "__main__":
    unittest.main()
