"""Focused unit and regression tests for deterministic hunk-offset normalization."""

import unittest
from pathlib import Path

from v2.engine.diff_parser import parse_patch
from v2.engine.emitter import emit_patch
from v2.engine.normalizer import (
    AmbiguousContextError,
    ContextMismatchError,
    HunkOrderError,
    OffsetVerificationError,
    SourceMissingError,
    normalize_patch_offsets,
)
from v2.model.patch import AddedLine, ContextLine, FilePatch, Hunk, Patch, RemovedLine
from v2.source.bundle import create_source_bundle
from v2.source.patch_apply import apply_patch_to_bundle


class TestNormalizer(unittest.TestCase):
    def test_single_hunk_offset_normalization(self):
        source = (
            "line 1\n"
            "line 2\n"
            "line 3\n"
            "target context 1\n"
            "target context 2\n"
            "line 6\n"
        )
        # Patch declared at line 10 (offset -6 drift)
        patch_text = (
            "diff --git a/test.c b/test.c\n"
            "--- a/test.c\n"
            "+++ b/test.c\n"
            "@@ -10,2 +10,3 @@\n"
            " target context 1\n"
            "+inserted line\n"
            " target context 2\n"
        )
        result = normalize_patch_offsets(patch_text, {"test.c": source})
        self.assertEqual(len(result.report.records), 1)
        rec = result.report.records[0]
        self.assertEqual(rec.old_start_before, 10)
        self.assertEqual(rec.old_start_after, 4)
        self.assertEqual(rec.new_start_after, 4)
        self.assertEqual(rec.offset, -6)
        self.assertIn("@@ -4,2 +4,3 @@", result.to_text())
        expected_postimage = (
            "line 1\n"
            "line 2\n"
            "line 3\n"
            "target context 1\n"
            "inserted line\n"
            "target context 2\n"
            "line 6\n"
        )
        self.assertEqual(result.postimages["test.c"], expected_postimage)

    def test_multi_hunk_cumulative_delta(self):
        source = (
            "fn1_ctx1\n"
            "fn1_ctx2\n"
            "between 1\n"
            "between 2\n"
            "fn2_ctx1\n"
            "fn2_ctx2\n"
        )
        # Hunk 1 at line 1 adds 2 lines (new_count - old_count = +2)
        # Hunk 2 declared at line 5 (in source at line 5, postimage line 5 + 2 = 7)
        patch_text = (
            "diff --git a/test.c b/test.c\n"
            "--- a/test.c\n"
            "+++ b/test.c\n"
            "@@ -1,2 +1,4 @@\n"
            " fn1_ctx1\n"
            "+add1\n"
            "+add2\n"
            " fn1_ctx2\n"
            "@@ -20,2 +22,3 @@\n"
            " fn2_ctx1\n"
            "+add3\n"
            " fn2_ctx2\n"
        )
        result = normalize_patch_offsets(patch_text, {"test.c": source})
        self.assertEqual(len(result.report.records), 2)
        h1 = result.report.records[0]
        h2 = result.report.records[1]
        self.assertEqual((h1.old_start_after, h1.new_start_after), (1, 1))
        self.assertEqual((h2.old_start_after, h2.new_start_after), (5, 7))
        self.assertIn("@@ -1,2 +1,4 @@", result.to_text())
        self.assertIn("@@ -5,2 +7,3 @@", result.to_text())

    def test_section_context_disambiguation(self):
        # Two identical bodies under different function headers
        source = (
            "void func_a(void) {\n"
            "    int a = 1;\n"
            "    int b = 2;\n"
            "}\n"
            "\n"
            "void func_b(void) {\n"
            "    int a = 1;\n"
            "    int b = 2;\n"
            "}\n"
        )
        # Patch targets func_b specifically
        patch_text = (
            "diff --git a/test.c b/test.c\n"
            "--- a/test.c\n"
            "+++ b/test.c\n"
            "@@ -50,2 +50,3 @@ void func_b(void)\n"
            "     int a = 1;\n"
            "+    int injected = 99;\n"
            "     int b = 2;\n"
        )
        result = normalize_patch_offsets(patch_text, {"test.c": source})
        rec = result.report.records[0]
        self.assertEqual(rec.old_start_after, 7)
        self.assertIn("void func_b(void)", rec.section_context)
        self.assertIn("int injected = 99;", result.postimages["test.c"].split("void func_b(void)")[1])
        self.assertNotIn("int injected = 99;", result.postimages["test.c"].split("void func_b(void)")[0])

    def test_ambiguous_context_fails_closed(self):
        # Two identical functions with no distinguishing section context
        source = (
            "int a = 1;\n"
            "int b = 2;\n"
            "int a = 1;\n"
            "int b = 2;\n"
        )
        patch_text = (
            "diff --git a/test.c b/test.c\n"
            "--- a/test.c\n"
            "+++ b/test.c\n"
            "@@ -10,2 +10,3 @@\n"
            " int a = 1;\n"
            "+int injected = 99;\n"
            " int b = 2;\n"
        )
        with self.assertRaises(AmbiguousContextError):
            normalize_patch_offsets(patch_text, {"test.c": source})

    def test_context_mismatch_fails_closed(self):
        source = "line 1\nline 2\n"
        patch_text = (
            "diff --git a/test.c b/test.c\n"
            "--- a/test.c\n"
            "+++ b/test.c\n"
            "@@ -1,2 +1,3 @@\n"
            " nonexistent context\n"
            "+added\n"
            " line 2\n"
        )
        with self.assertRaises(ContextMismatchError):
            normalize_patch_offsets(patch_text, {"test.c": source})

    def test_missing_source_fails_closed(self):
        patch_text = (
            "diff --git a/missing.c b/missing.c\n"
            "--- a/missing.c\n"
            "+++ b/missing.c\n"
            "@@ -1,1 +1,2 @@\n"
            " ctx\n"
            "+added\n"
        )
        with self.assertRaises(SourceMissingError):
            normalize_patch_offsets(patch_text, {"other.c": "ctx\n"})

    def test_r38_manual_fixture_normalization_and_bundle_reapply(self):
        r38_dir = Path("/home/codex/.gemini/antigravity-cli/brain/d3167f18-714c-4639-9a70-e941c706fe60/scratch/r38_files")
        if not r38_dir.exists():
            self.skipTest("r38 scratch files not available")

        target_sources = {
            "fs/exec.c": (r38_dir / "fs/exec.c").read_text(encoding="utf-8"),
            "fs/open.c": (r38_dir / "fs/open.c").read_text(encoding="utf-8"),
            "fs/stat.c": (r38_dir / "fs/stat.c").read_text(encoding="utf-8"),
            "kernel/reboot.c": (r38_dir / "kernel/reboot.c").read_text(encoding="utf-8"),
            "security/security.c": (r38_dir / "security/security.c").read_text(encoding="utf-8"),
        }

        # 1. The normalized r38 fixture on disk has 0 drift and applies directly at offset 0
        patch_scope_text = Path(".github/fixtures/r38/scope-min-manual-hooks-v2.3.patch").read_text(encoding="utf-8")
        res_scope = normalize_patch_offsets(patch_scope_text, target_sources)
        self.assertFalse(res_scope.report.has_drift)
        self.assertEqual(res_scope.report.total_hunks, 7)
        self.assertEqual(res_scope.report.drifted_hunks, 0)

        # Verify bundle application with normalized patch succeeds directly
        bundle_files = {k: v for k, v in target_sources.items() if k != "security/security.c"}
        bundle = create_source_bundle("gki-android16-6.12", "6.12", bundle_files)
        applied_bundle = apply_patch_to_bundle(bundle, patch_scope_text)
        for entry in applied_bundle.files:
            self.assertEqual(entry.content, res_scope.postimages[entry.path])

        # 2. Test intentional drift on r38: shift line numbers back to original unnormalized values
        drifted_patch = parse_patch(patch_scope_text)
        for fp in drifted_patch.files:
            p = fp.old_path or fp.new_path
            if "exec.c" in p:
                fp.hunks[0].old_start = 1940
                fp.hunks[0].new_start = 1940
            elif "stat.c" in p:
                fp.hunks[0].old_start = 502
                fp.hunks[0].new_start = 502
                fp.hunks[1].old_start = 517
                fp.hunks[1].new_start = 522
                fp.hunks[2].old_start = 649
                fp.hunks[2].new_start = 662
                fp.hunks[3].old_start = 658
                fp.hunks[3].new_start = 679
        res_drifted = normalize_patch_offsets(drifted_patch, target_sources)
        self.assertTrue(res_drifted.report.has_drift)
        self.assertEqual(res_drifted.report.drifted_hunks, 5)  # 1 in exec.c, 4 in stat.c
        self.assertEqual(res_drifted.to_text(), patch_scope_text)

        # 3. Normalize manual-security-hooks-v2.0.patch (already offset 0)
        patch_sec_text = Path(".github/fixtures/r38/manual-security-hooks-v2.0.patch").read_text(encoding="utf-8")
        res_sec = normalize_patch_offsets(patch_sec_text, target_sources)
        self.assertFalse(res_sec.report.has_drift)
        self.assertEqual(res_sec.report.total_hunks, 6)
        self.assertEqual(res_sec.report.drifted_hunks, 0)


if __name__ == "__main__":
    unittest.main()
