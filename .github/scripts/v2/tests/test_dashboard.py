"""Comprehensive test suite for Upstream Watch permanent GitHub Issue dashboard."""

from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from v2.manifests.patch_manifest import verify_patch_manifest
from v2.watch.dashboard import (
    DASHBOARD_LABEL,
    DASHBOARD_TITLE,
    MAX_BODY_BYTES,
    MAX_DISPLAYED_ESCALATIONS,
    MAX_RECENT_EVENTS,
    OverallStatus,
    calculate_overall_status,
    combine_recent_events,
    extract_transition_events,
    load_manifest_patches,
    parse_dashboard_events,
    render_dashboard_body,
    sync_dashboard_issue,
    trim_body_if_needed,
)
from v2.watch.model import SourceResult, WatchClassification, WatchReport

REPO_ROOT = Path(__file__).resolve().parents[4]


def make_clean_report(timestamp: str = "2026-09-24T22:00:00Z") -> WatchReport:
    """Create a baseline all-NO_CHANGE report across all 5 tracked sources."""
    results = (
        SourceResult(
            source_id="backslashxx_kernelsu",
            source_type="authoritative",
            classification=WatchClassification.NO_CHANGE,
            old_identity="bb0be9297da42ff3f63819125314ce0b13935a06",
            new_identity="bb0be9297da42ff3f63819125314ce0b13935a06",
            old_content_hash="sha256:4e00b0314139",
            new_content_hash="sha256:4e00b0314139",
        ),
        SourceResult(
            source_id="susfs_sultan",
            source_type="authoritative",
            classification=WatchClassification.NO_CHANGE,
            old_identity="c254cf2dcdffcfb466b7ac6706f705a339adeaa0",
            new_identity="c254cf2dcdffcfb466b7ac6706f705a339adeaa0",
            old_content_hash="sha256:db2b7a373398",
            new_content_hash="sha256:db2b7a373398",
        ),
        SourceResult(
            source_id="susfs_gki",
            source_type="authoritative",
            classification=WatchClassification.NO_CHANGE,
            old_identity="2528bdb0e2e76d26b9b174a8314ac115c9f00b3c",
            new_identity="2528bdb0e2e76d26b9b174a8314ac115c9f00b3c",
            old_content_hash="sha256:016434f1d970",
            new_content_hash="sha256:016434f1d970",
        ),
        SourceResult(
            source_id="midori_kernelsu_xx_patch",
            source_type="reference",
            classification=WatchClassification.NO_CHANGE,
            old_identity="bc1b8e371d80fb8dbed5ac10096e39f9cf864d56",
            new_identity="719d466e7228a0f9f3819125314ce0b13935a06",
            old_content_hash="sha256:6d0a6b64ffcc",
            new_content_hash="sha256:6d0a6b64ffcc",
        ),
        SourceResult(
            source_id="midori_gki_patch_50",
            source_type="reference",
            classification=WatchClassification.NO_CHANGE,
            old_identity="https://raw.githubusercontent.com/.../50.patch",
            new_identity="https://raw.githubusercontent.com/.../50.patch",
            old_content_hash="sha256:4bb0e351558c",
            new_content_hash="sha256:4bb0e351558c",
        ),
    )
    return WatchReport(results=results, timestamp=timestamp)


class DashboardTests(unittest.TestCase):
    """Test all 17 required dashboard behaviors."""

    # 1. dashboard creation when none exists
    @patch("v2.watch.dashboard.find_dashboard_issues", return_value=[])
    @patch("v2.watch.dashboard.create_dashboard_issue", return_value="https://github.com/yapixel/xxksu_susfs_patch/issues/100")
    @patch("v2.watch.dashboard.ensure_label_exists")
    @patch("v2.watch.dashboard.fetch_open_escalations", return_value=[])
    def test_01_dashboard_creation_when_none_exists(self, mock_esc, mock_lbl, mock_create, mock_find):
        report = make_clean_report()
        url, created = sync_dashboard_issue(report=report, repo="yapixel/xxksu_susfs_patch", repo_root=REPO_ROOT)
        self.assertTrue(created)
        self.assertEqual(url, "https://github.com/yapixel/xxksu_susfs_patch/issues/100")
        mock_create.assert_called_once()
        call_body = mock_create.call_args[0][1]
        self.assertIn("# 📡 Upstream Watch Status", call_body)
        self.assertIn("🟢 HEALTHY", call_body)

    # 2. update-in-place when exactly one exists
    @patch("v2.watch.dashboard.find_dashboard_issues")
    @patch("v2.watch.dashboard.update_dashboard_issue", return_value="https://github.com/yapixel/xxksu_susfs_patch/issues/42")
    @patch("v2.watch.dashboard.create_dashboard_issue")
    @patch("v2.watch.dashboard.fetch_open_escalations", return_value=[])
    def test_02_update_in_place_when_exactly_one_exists(self, mock_esc, mock_create, mock_update, mock_find):
        mock_find.return_value = [{"number": 42, "title": DASHBOARD_TITLE, "url": "https://github.com/yapixel/xxksu_susfs_patch/issues/42", "body": "old body"}]
        report = make_clean_report()
        url, created = sync_dashboard_issue(report=report, repo="yapixel/xxksu_susfs_patch", repo_root=REPO_ROOT)
        self.assertFalse(created)
        self.assertEqual(url, "https://github.com/yapixel/xxksu_susfs_patch/issues/42")
        mock_update.assert_called_once()
        self.assertEqual(mock_update.call_args[0][1], 42)
        mock_create.assert_not_called()

    # 3. duplicate dashboard detection
    @patch("v2.watch.dashboard.find_dashboard_issues")
    def test_03_duplicate_dashboard_detection(self, mock_find):
        mock_find.return_value = [
            {"number": 10, "title": DASHBOARD_TITLE, "body": ""},
            {"number": 20, "title": DASHBOARD_TITLE, "body": ""},
        ]
        report = make_clean_report()
        with self.assertRaises(RuntimeError) as ctx:
            sync_dashboard_issue(report=report, repo="yapixel/xxksu_susfs_patch", repo_root=REPO_ROOT)
        self.assertIn("Duplicate dashboard condition", str(ctx.exception))

    # 4. all-authoritative-NO_CHANGE → HEALTHY
    def test_04_all_authoritative_no_change_is_healthy(self):
        report = make_clean_report()
        status = calculate_overall_status(report, open_escalations=())
        self.assertEqual(status, OverallStatus.HEALTHY)
        body = render_dashboard_body(report=report, repo_root=REPO_ROOT)
        self.assertIn("**Overall Status:** 🟢 HEALTHY", body)

    # 5. SAFE_REGEN_CANDIDATE → UPDATE AVAILABLE
    def test_05_safe_regen_candidate_is_update_available(self):
        cand_res = SourceResult(
            source_id="backslashxx_kernelsu",
            source_type="authoritative",
            classification=WatchClassification.SAFE_REGEN_CANDIDATE,
            old_identity="bb0be9297da4",
            new_identity="112233445566",
            old_content_hash="h1",
            new_content_hash="h2",
            candidate_patch="diff ...",
            candidate_patch_name="11_enable_susfs_for_ksu.patch",
        )
        report = WatchReport(results=(cand_res,), timestamp="2026-09-24T22:00:00Z")
        status = calculate_overall_status(report, open_escalations=())
        self.assertEqual(status, OverallStatus.UPDATE_AVAILABLE)
        body = render_dashboard_body(report=report, repo_root=REPO_ROOT)
        self.assertIn("**Overall Status:** 🔵 UPDATE AVAILABLE", body)

    # 6. reference-only real drift → REVIEW REQUIRED
    def test_06_reference_only_real_drift_is_review_required(self):
        clean = make_clean_report()
        ref_drift_res = SourceResult(
            source_id="midori_kernelsu_xx_patch",
            source_type="reference",
            classification=WatchClassification.REFERENCE_DRIFT,
            old_identity="bc1b8e371d80",
            new_identity="719d466e7228",
            old_content_hash="h_old",
            new_content_hash="h_new",
        )
        # Authoritative are NO_CHANGE, reference has drift
        results = tuple(r for r in clean.results if r.source_id != "midori_kernelsu_xx_patch") + (ref_drift_res,)
        report = WatchReport(results=results, timestamp="2026-09-24T22:00:00Z")
        status = calculate_overall_status(report, open_escalations=())
        self.assertEqual(status, OverallStatus.REVIEW_REQUIRED)
        body = render_dashboard_body(report=report, repo_root=REPO_ROOT)
        self.assertIn("**Overall Status:** 🟠 REVIEW REQUIRED", body)

    # 7. authoritative drift → ACTION REQUIRED
    def test_07_authoritative_drift_is_action_required(self):
        drift_classes = [
            WatchClassification.ANCHOR_DRIFT,
            WatchClassification.SEMANTIC_DRIFT,
            WatchClassification.SOURCE_IDENTITY_ERROR,
        ]
        for cls in drift_classes:
            drift_res = SourceResult(
                source_id="backslashxx_kernelsu",
                source_type="authoritative",
                classification=cls,
                old_identity="bb0be9297da4",
                new_identity="deadbeef1234",
                old_content_hash="h1",
                new_content_hash="h2",
            )
            report = WatchReport(results=(drift_res,), timestamp="2026-09-24T22:00:00Z")
            status = calculate_overall_status(report, open_escalations=())
            self.assertEqual(status, OverallStatus.ACTION_REQUIRED, f"Failed for {cls}")

        # Also when an open authoritative escalation exists
        clean_report = make_clean_report()
        esc = [{"number": 4, "source_id": "backslashxx_kernelsu", "classification": "ANCHOR_DRIFT"}]
        status = calculate_overall_status(clean_report, open_escalations=esc)
        self.assertEqual(status, OverallStatus.ACTION_REQUIRED)

    # 8. authoritative status precedence over reference status
    def test_08_authoritative_status_precedence_over_reference_status(self):
        # Case A: Authoritative SAFE_REGEN_CANDIDATE + Reference REFERENCE_DRIFT -> UPDATE_AVAILABLE
        r_auth = SourceResult(
            source_id="backslashxx_kernelsu",
            source_type="authoritative",
            classification=WatchClassification.SAFE_REGEN_CANDIDATE,
            old_identity="id1",
            new_identity="id2",
            old_content_hash="h1",
            new_content_hash="h2",
        )
        r_ref = SourceResult(
            source_id="midori_kernelsu_xx_patch",
            source_type="reference",
            classification=WatchClassification.REFERENCE_DRIFT,
            old_identity="id3",
            new_identity="id4",
            old_content_hash="h3",
            new_content_hash="h4",
        )
        report_a = WatchReport(results=(r_auth, r_ref), timestamp="2026-09-24T22:00:00Z")
        self.assertEqual(calculate_overall_status(report_a), OverallStatus.UPDATE_AVAILABLE)

        # Case B: Authoritative ANCHOR_DRIFT + Reference REFERENCE_DRIFT -> ACTION_REQUIRED
        r_auth_drift = SourceResult(
            source_id="backslashxx_kernelsu",
            source_type="authoritative",
            classification=WatchClassification.ANCHOR_DRIFT,
            old_identity="id1",
            new_identity="id2",
            old_content_hash="h1",
            new_content_hash="h2",
        )
        report_b = WatchReport(results=(r_auth_drift, r_ref), timestamp="2026-09-24T22:00:00Z")
        self.assertEqual(calculate_overall_status(report_b), OverallStatus.ACTION_REQUIRED)

        # Case C: Reference drift alone MUST NEVER trigger ACTION_REQUIRED
        report_c = WatchReport(results=(r_ref,), timestamp="2026-09-24T22:00:00Z")
        self.assertNotEqual(calculate_overall_status(report_c), OverallStatus.ACTION_REQUIRED)
        self.assertEqual(calculate_overall_status(report_c), OverallStatus.REVIEW_REQUIRED)

    # 9. production patches loaded from manifest.json
    def test_09_production_patches_loaded_from_manifest(self):
        manifest_patches = load_manifest_patches(REPO_ROOT)
        self.assertEqual(len(manifest_patches), 3)
        ids = {p["id"] for p in manifest_patches}
        self.assertEqual(ids, {"xxksu-patch11", "sultan-android14-6.1-patch51", "gki-android16-6.12-r38-patch51"})

        report = make_clean_report()
        body = render_dashboard_body(report=report, repo_root=REPO_ROOT)
        for p in manifest_patches:
            self.assertIn(f"`{p['id']}`", body)
            self.assertIn(f"`{p['relative_path']}`", body)
            self.assertIn(f"`{p['sha256'][:12]}`", body)

    # 10. maximum 5 displayed escalations
    def test_10_maximum_5_displayed_escalations(self):
        report = make_clean_report()
        escalations = [
            {"number": 101 + i, "url": f"https://github.com/issues/{101+i}", "source_id": "test_src", "classification": "DRIFT"}
            for i in range(8)
        ]
        body = render_dashboard_body(report=report, repo_root=REPO_ROOT, open_escalations=escalations)
        self.assertIn("#101", body)
        self.assertIn("#105", body)
        self.assertNotIn("#106", body)
        self.assertIn("+ 3 additional open escalations", body)

    # 11. maximum 10 Recent Events
    def test_11_maximum_10_recent_events(self):
        events = [
            {"timestamp": f"2026-09-0{i%9 + 1}", "source_id": f"src_{i}", "text": f"Event {i}"}
            for i in range(16)
        ]
        combined = combine_recent_events([], events, max_events=MAX_RECENT_EVENTS)
        self.assertEqual(len(combined), MAX_RECENT_EVENTS)

        report = make_clean_report()
        body = render_dashboard_body(report=report, repo_root=REPO_ROOT, recent_events=combined)
        for i in range(10):
            self.assertIn(f"Event {i}", body)
        self.assertNotIn("Event 10", body)

    # 12. routine NO_CHANGE does not grow Recent Events
    def test_12_routine_no_change_does_not_grow_recent_events(self):
        report = make_clean_report()
        transitions = extract_transition_events(report, "2026-09-24")
        self.assertEqual(transitions, [], "NO_CHANGE report must produce zero transition events")

        seed_events = [
            {"timestamp": "2026-09-24", "source_id": "backslashxx_kernelsu", "text": "Resolved #4"},
            {"timestamp": "2026-09-23", "source_id": "susfs_sultan", "text": "Resolved #3"},
        ]
        combined = combine_recent_events(seed_events, transitions)
        self.assertEqual(combined, seed_events)

    # 13. repeated watcher runs do not cause unbounded body growth
    def test_13_repeated_watcher_runs_do_not_cause_unbounded_body_growth(self):
        report = make_clean_report(timestamp="2026-09-24T22:00:00Z")
        events = [
            {"timestamp": "2026-09-24", "source_id": "backslashxx_kernelsu", "text": "Resolved #4"},
        ]
        body1 = render_dashboard_body(report=report, repo_root=REPO_ROOT, recent_events=events, revision="84743b5", branch="main")
        len1 = len(body1.encode("utf-8"))

        current_events = events
        for _ in range(15):
            transitions = extract_transition_events(report, "2026-09-24")
            current_events = combine_recent_events(current_events, transitions)
            body_n = render_dashboard_body(report=report, repo_root=REPO_ROOT, recent_events=current_events, revision="84743b5", branch="main")
            len_n = len(body_n.encode("utf-8"))
            self.assertEqual(len1, len_n)

    # 14. commit/rebase-only Midori change with identical normalized content remains NO_CHANGE
    def test_14_commit_rebase_only_midori_with_identical_normalized_content_remains_no_change(self):
        clean = make_clean_report()
        # Midori has different git commit but normalized sha is unchanged -> NO_CHANGE
        midori_res = next(r for r in clean.results if r.source_id == "midori_kernelsu_xx_patch")
        self.assertEqual(midori_res.classification, WatchClassification.NO_CHANGE)
        self.assertNotEqual(midori_res.old_identity, midori_res.new_identity)

        status = calculate_overall_status(clean)
        self.assertEqual(status, OverallStatus.HEALTHY)

        body = render_dashboard_body(report=clean, repo_root=REPO_ROOT)
        self.assertIn("| `Midori xx.patch` | Reference Only | 🟢 `NO_CHANGE` | `cc36da9e333c` (commit: `bc1b8e37`) | — (commit: `719d466e`) | — |", body)
        self.assertIn("| `Midori GKI 50 Patch` | Reference Only | 🟢 `NO_CHANGE` | `1fa63a063144` | — | — |", body)
        self.assertIn("| `xxKSU` | Authoritative | 🟢 `NO_CHANGE` | `bb0be9297da4` | — | — |", body)

    # 15. rendered body stays below 30 KiB
    def test_15_rendered_body_stays_below_30_kib(self):
        report = make_clean_report()
        body = render_dashboard_body(report=report, repo_root=REPO_ROOT)
        size = len(body.encode("utf-8"))
        self.assertLessEqual(size, MAX_BODY_BYTES)

        # Test trimming with excessive text
        huge_events = [
            {"timestamp": "2026-09-24", "source_id": "test", "text": "x" * 5000}
            for _ in range(10)
        ]
        initial_body = render_dashboard_body(
            report=report,
            repo_root=REPO_ROOT,
            recent_events=huge_events,
        )
        self.assertGreater(len(initial_body.encode("utf-8")), MAX_BODY_BYTES)

        trimmed = trim_body_if_needed(
            body=initial_body,
            recent_events=huge_events,
            open_escalations=[],
            report=report,
            repo_root=REPO_ROOT,
        )
        trimmed_size = len(trimmed.encode("utf-8"))
        self.assertLessEqual(trimmed_size, MAX_BODY_BYTES)
        # Protected content must remain present
        self.assertIn("# 📡 Upstream Watch Status", trimmed)
        self.assertIn("## Upstream Sources", trimmed)
        self.assertIn("## Production Patches", trimmed)

    # 16. deterministic rendering for identical state
    def test_16_deterministic_rendering_for_identical_state(self):
        report = make_clean_report(timestamp="2026-09-24T22:00:00Z")
        events = [
            {"timestamp": "2026-09-24", "source_id": "src", "text": "Transition 1"},
        ]
        body1 = render_dashboard_body(report=report, repo_root=REPO_ROOT, recent_events=events, revision="84743b5", branch="main")
        body2 = render_dashboard_body(report=report, repo_root=REPO_ROOT, recent_events=events, revision="84743b5", branch="main")
        self.assertEqual(body1, body2)

    # 17. dashboard failure does not modify production state
    def test_17_dashboard_failure_does_not_modify_production_state(self):
        # 1. Verify manifest passes before
        ok_before, errs_before = verify_patch_manifest(REPO_ROOT)
        self.assertTrue(ok_before, f"Manifest verification failed before test: {errs_before}")

        # 2. Simulate dashboard exception
        report = make_clean_report()
        with patch("v2.watch.dashboard.find_dashboard_issues", side_effect=RuntimeError("Simulated gh failure")):
            with self.assertRaises(RuntimeError):
                sync_dashboard_issue(report=report, repo="yapixel/xxksu_susfs_patch", repo_root=REPO_ROOT)

        # 3. Verify manifest and production patches are still 100% untouched and passing
        ok_after, errs_after = verify_patch_manifest(REPO_ROOT)
        self.assertTrue(ok_after, f"Manifest verification failed after simulated error: {errs_after}")

    # 18. transient SOURCE_IDENTITY_ERROR never persisted to Recent Events
    def test_18_transient_source_identity_error_never_persisted_to_recent_events(self):
        err_res = SourceResult(
            source_id="susfs_sultan",
            source_type="authoritative",
            classification=WatchClassification.SOURCE_IDENTITY_ERROR,
            old_identity="c254cf2dcdff",
            new_identity="UNKNOWN",
            old_content_hash="h_old",
            new_content_hash="UNKNOWN",
            details="Command git ls-remote timed out after 30 seconds",
        )
        report = WatchReport(results=(err_res,), timestamp="2026-09-24T22:00:00Z")
        # 1. extract_transition_events must ignore transient SOURCE_IDENTITY_ERROR
        events = extract_transition_events(report, "2026-09-24")
        self.assertEqual(events, [], "Transient SOURCE_IDENTITY_ERROR must not produce a persistent Recent Event")

        # 2. combine_recent_events must strip any existing spurious SOURCE_IDENTITY_ERROR event
        spurious_events = [
            {"timestamp": "2026-09-24", "source_id": "susfs_sultan", "text": "Drift detected: SOURCE_IDENTITY_ERROR (old: `c254cf2d`, new: `UNKNOWN`)"},
            {"timestamp": "2026-09-24", "source_id": "backslashxx_kernelsu", "text": "Promoted authoritative bb0be929 pin and regenerated Patch 11 (resolved Issue #4)"},
        ]
        combined = combine_recent_events(spurious_events, [])
        texts = [e["text"] for e in combined]
        self.assertFalse(any("SOURCE_IDENTITY_ERROR" in t for t in texts))
        self.assertTrue(any("resolved Issue #4" in t for t in texts))

    # 19. reference patch primary identity is normalized content
    def test_19_reference_patch_primary_identity_is_normalized_content(self):
        report = make_clean_report()
        body = render_dashboard_body(report=report, repo_root=REPO_ROOT)
        # Check Midori xx.patch row: normalized content cc36da9e333c is primary, commit bc1b8e37 is metadata
        self.assertIn("`cc36da9e333c` (commit: `bc1b8e37`)", body)
        # Check Midori GKI 50 patch row: normalized content 1fa63a063144 is primary
        self.assertIn("`1fa63a063144`", body)
        # Check Authoritative rows remain commit-identity based
        self.assertIn("`bb0be9297da4`", body)
        self.assertIn("`c254cf2dcdff`", body)
        self.assertIn("`2528bdb0e2e7`", body)


if __name__ == "__main__":
    unittest.main()
