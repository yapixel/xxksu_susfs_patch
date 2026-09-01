import sys
import unittest
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
if str(SCRIPT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT.parent))

from v2.engine.diff_parser import parse_patch
from v2.engine.emitter import emit_patch
from v2.model.patch import AddedLine, Hunk, NoNewlineMarker
from v2.model.result import (
    HunkCountMismatch, InvalidHunkLine, MalformedFileHeader,
    MalformedHunkHeader, PatchError, PatchParseError, UnsupportedPatchFormat,
)


def round_trip(text):
    first = parse_patch(text)
    second = parse_patch(emit_patch(first))
    return first, second


class DiffParserTests(unittest.TestCase):
    def test_basic_multiple_files_and_preamble(self):
        text = (
            "From patch\n"
            "diff --git a/a.c b/a.c\n"
            "index 1111111..2222222 100644\n"
            "--- a/a.c\n+++ b/a.c\n"
            "@@ -1,2 +1,2 @@\n old context\n-old\n+new\n"
            "diff --git a/b.c b/b.c\n"
            "--- a/b.c\n+++ b/b.c\n"
            "@@ -1 +1 @@\n-old\n+new\n"
        )
        parsed = parse_patch(text)
        self.assertEqual(parsed.preamble, ["From patch"])
        self.assertEqual(len(parsed.files), 2)
        self.assertEqual(parsed.files[0].hunks[0].section_context, "")
        self.assertEqual(parsed.files[1].hunks[0].old_count, 1)

    def test_multiple_hunks_and_section_context(self):
        text = (
            "diff --git a/a.c b/a.c\n--- a/a.c\n+++ b/a.c\n"
            "@@ -10,2 +10,3 @@ some_function(...)\n a\n-b\n+b\n+c\n"
            "@@ -30 +31 @@ another\n-x\n+y\n"
        )
        patch = parse_patch(text)
        self.assertEqual(len(patch.files[0].hunks), 2)
        self.assertEqual(patch.files[0].hunks[0].section_context, "some_function(...)")

    def test_new_deleted_mode_rename_copy_and_metadata(self):
        text = (
            "diff --git a/new.txt b/new.txt\nnew file mode 100644\n"
            "--- /dev/null\n+++ b/new.txt\n@@ -0,0 +1 @@\n+new\n"
            "diff --git a/old.txt b/old.txt\ndeleted file mode 100644\n"
            "--- a/old.txt\n+++ /dev/null\n@@ -1 +0,0 @@\n-old\n"
            "diff --git a/a b/b\nsimilarity index 95%\nrename from a\nrename to b\n"
            "diff --git a/c b/d\nsimilarity index 90%\ncopy from c\ncopy to d\n"
            "diff --git a/m a/m\nold mode 100644\nnew mode 100755\n"
        )
        patch = parse_patch(text)
        self.assertEqual(patch.files[0].status.value, "added")
        self.assertEqual(patch.files[1].status.value, "deleted")
        self.assertEqual(patch.files[2].status.value, "renamed")
        self.assertEqual(patch.files[3].status.value, "copied")
        self.assertEqual(patch.files[4].status.value, "mode-only")
        self.assertEqual(parse_patch(emit_patch(patch)).structural_key(), patch.structural_key())

    def test_no_newline_markers(self):
        text = (
            "diff --git a/a b/a\n--- a/a\n+++ b/a\n"
            "@@ -1 +1 @@\n-old\n\\ No newline at end of file\n"
            "+new\n\\ No newline at end of file\n"
        )
        patch = parse_patch(text)
        lines = patch.files[0].hunks[0].lines
        self.assertEqual(sum(type(line).__name__ == "NoNewlineMarker" for line in lines), 2)
        self.assertEqual(parse_patch(emit_patch(patch)).structural_key(), patch.structural_key())

    def test_metadata_like_source_line_is_not_boundary(self):
        text = (
            "diff --git a/a b/a\n--- a/a\n+++ b/a\n@@ -1,3 +1,3 @@\n"
            " diff --git a/not-a-header b/not-a-header\n"
            "-@@ fake\n+--- fake\n"
            " +++ fake\n"
        )
        patch = parse_patch(text)
        self.assertEqual(len(patch.files), 1)
        self.assertEqual(len(patch.files[0].hunks[0].lines), 4)

    def test_binary_patch_is_opaque(self):
        text = (
            "diff --git a/x.bin b/x.bin\n"
            "new file mode 100644\n"
            "GIT binary patch\n"
            "literal 3\nabc\n"
        )
        patch = parse_patch(text)
        self.assertEqual(patch.files[0].status.value, "binary")
        self.assertEqual(parse_patch(emit_patch(patch)).structural_key(), patch.structural_key())

    def test_emitter_recomputes_mutated_hunk_counts(self):
        text = "diff --git a/a b/a\n--- a/a\n+++ b/a\n@@ -1 +1 @@\n-a\n+b\n"
        patch = parse_patch(text)
        hunk = patch.files[0].hunks[0]
        hunk.lines.append(AddedLine("extra"))
        emitted = emit_patch(patch)
        self.assertIn("@@ -1,1 +1,2 @@", emitted)
        reparsed = parse_patch(emitted)
        self.assertEqual(reparsed.files[0].hunks[0].new_count, 2)

    def test_empty_zero_count_hunk(self):
        text = "diff --git a/a b/a\n--- a/a\n+++ b/a\n@@ -1,0 +1,0 @@\n"
        patch = parse_patch(text)
        self.assertEqual(patch.files[0].hunks[0].calculated_counts(), (0, 0))

    def test_unknown_extended_header_is_preserved(self):
        text = "diff --git a/a b/a\nx-vendor-header value\nold mode 100644\nnew mode 100755\n"
        patch = parse_patch(text)
        self.assertEqual(patch.files[0].extended_headers, ["x-vendor-header value"])
        self.assertEqual(parse_patch(emit_patch(patch)).files[0].extended_headers,
                         ["x-vendor-header value"])

    def test_model_invariants(self):
        with self.assertRaises(PatchError):
            Hunk(-1, 0, 0, 0)
        hunk = Hunk(0, 0, 0, 0, lines=[NoNewlineMarker()])
        with self.assertRaises(PatchError):
            hunk.validate()


class DiffParserNegativeTests(unittest.TestCase):
    def assert_error(self, exc, text):
        with self.assertRaises(exc):
            parse_patch(text)

    def test_malformed_headers_and_structure(self):
        self.assert_error(MalformedFileHeader, "diff --git a/only-one\n")
        self.assert_error(MalformedHunkHeader, "diff --git a/a b/a\n--- a/a\n+++ b/a\n@@ bad\n")
        self.assert_error(MalformedFileHeader, "diff --git a/a b/a\n@@ -1 +1 @@\n+a\n")
        self.assert_error(PatchParseError, "@@ -1 +1 @@\n-a\n+b\n")
        self.assert_error(UnsupportedPatchFormat, "diff --cc a/a\n@@@ -1 -1 +1 @@@\n")

    def test_invalid_prefix_and_count_mismatch(self):
        self.assert_error(InvalidHunkLine, "diff --git a/a b/a\n--- a/a\n+++ b/a\n@@ -1 +1 @@\nx\n")
        self.assert_error(HunkCountMismatch, "diff --git a/a b/a\n--- a/a\n+++ b/a\n@@ -1,2 +1,1 @@\n-a\n")

    def test_truncated_and_marker_errors(self):
        self.assert_error(HunkCountMismatch, "diff --git a/a b/a\n--- a/a\n+++ b/a\n@@ -1 +1 @@\n")
        self.assert_error(InvalidHunkLine, "diff --git a/a b/a\n--- a/a\n+++ b/a\n@@ -0,0 +0,0 @@\n\\ No newline at end of file\n")


class RepositoryFixtureTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[4]

    def test_existing_patch_corpus_round_trips(self):
        paths = [
            self.ROOT / "patches" / "xxksu" / "11_enable_susfs_for_ksu.patch",
            self.ROOT / ".github" / "fixtures" / "scope-min-manual-hooks-v2.3.patch",
        ]
        for path in paths:
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                first, second = round_trip(text)
                self.assertEqual(second.structural_key(), first.structural_key())

    def test_real_51_file_patch_sample(self):
        path = self.ROOT / "patches" / "gki-android14-6.1" / "51_deinlined_susfs_hooks_gki-android14-6.1.patch"
        text = path.read_text(encoding="utf-8")
        # The repository patch contains several legacy malformed hunks. Use a
        # complete, structurally valid file patch as the real-corpus sample.
        sample = "diff --git " + text.split("diff --git ", 1)[1].split("diff --git ", 1)[0]
        first, second = round_trip(sample)
        self.assertEqual(second.structural_key(), first.structural_key())

    def test_legacy_malformed_51_fails_closed(self):
        path = self.ROOT / "patches" / "gki-android14-6.1" / "51_deinlined_susfs_hooks_gki-android14-6.1.patch"
        with self.assertRaises(PatchParseError):
            parse_patch(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
