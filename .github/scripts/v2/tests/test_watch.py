"""Focused test suite for Phase 1 upstream watch, classification, and escalation."""

from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from v2.watch.checker import (
    UpstreamWatcher,
    compute_composite_hash,
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


if __name__ == "__main__":
    unittest.main()
