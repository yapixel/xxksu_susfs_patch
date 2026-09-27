"""Regression tests reproducing and guarding against character literal escape corruption in patch generators."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from v2.validation.exact_patch import (
    main,
    parse_patch_tool_output,
    validate_exact_patch_on_tree,
    validate_patch_syntax,
    verify_postimage_integrity,
)


class GeneratorEscapeRegressionTests(unittest.TestCase):
    """Reproduce and guard against the seq_putc(m, '\\n') -> raw newline corruption bug."""

    def test_generated_patch51_literals_both_targets(self):
        from v2.pipeline import generate_candidate_patch
        from test_lifecycle import postimages
        root = Path(__file__).resolve().parents[4]
        for gki, patch_id, folder in (
            (False, "sultan-android14-6.1-patch51", "sultan"),
            (True, "gki-android16-6.12-r38-patch51", "r38"),
        ):
            with self.subTest(target=patch_id):
                candidate = generate_candidate_patch(patch_id, root / ".github/fixtures" / folder, root)
                self.assertEqual(validate_patch_syntax(candidate), [])
                for path, content in postimages(gki).items():
                    self.assertEqual(verify_postimage_integrity(content, path), [])


    def test_validate_patch_syntax_detects_corrupted_seq_putc(self) -> None:
        """Verify that validate_patch_syntax rejects patches with split character literals."""
        corrupted_patch = """diff --git a/fs/proc/task_mmu.c b/fs/proc/task_mmu.c
--- a/fs/proc/task_mmu.c
+++ b/fs/proc/task_mmu.c
@@ -582,2 +582,4 @@ static int show_map(struct seq_file *m, void *v)
 \t\t\t\tseq_pad(m, ' ');
+\t\t\t\tseq_putc(m, '
+');
 \t\t\t\treturn;
"""
        errors = validate_patch_syntax(corrupted_patch)
        self.assertTrue(len(errors) > 0, "Validator must detect split character literal")
        self.assertTrue(any("split/unterminated character literal" in e or "unclosed" in e for e in errors))

    def test_validate_patch_syntax_accepts_clean_patch(self) -> None:
        """Verify that validate_patch_syntax accepts clean seq_putc literals."""
        clean_patch = """diff --git a/fs/proc/task_mmu.c b/fs/proc/task_mmu.c
--- a/fs/proc/task_mmu.c
+++ b/fs/proc/task_mmu.c
@@ -582,2 +582,3 @@ static int show_map(struct seq_file *m, void *v)
 \t\t\t\tseq_pad(m, ' ');
+\t\t\t\tseq_putc(m, '\\n');
 \t\t\t\treturn;
"""
        errors = validate_patch_syntax(clean_patch)
        self.assertEqual(errors, [])

    def test_verify_postimage_integrity_detects_split_literals(self) -> None:
        """Verify postimage scanner flags corrupted lines in resulting source files."""
        corrupted_source = """
static int foo(void) {
\tseq_putc(m, '
');
\treturn 0;
}
"""
        errors = verify_postimage_integrity(corrupted_source, "fs/proc/task_mmu.c")
        self.assertTrue(len(errors) > 0)
        self.assertIn("split character literal", errors[0])

    def test_parse_patch_tool_output_detects_offsets_and_fuzz(self) -> None:
        """Verify detector catches non-zero hunk offsets and fuzz from patch tool output."""
        sample_output = """
patching file fs/proc/base.c
Hunk #1 succeeded at 3986 (offset 10 lines).
patching file fs/proc/task_mmu.c
Hunk #4 succeeded at 497 with fuzz 3 (offset -47 lines).
Hunk #5 succeeded at 1558 (offset -79 lines).
"""
        errors = parse_patch_tool_output(sample_output)
        self.assertEqual(len(errors), 4)
        self.assertTrue(any("Non-zero hunk offset detected" in e for e in errors))
        self.assertTrue(any("Fuzz detected" in e for e in errors))


class ExactPatchApplicationRegressionTests(unittest.TestCase):
    """Verify single-pass authoritative patch application and byte-identical check/dry-run."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tree_dir = Path(self.temp_dir.name)
        self.sub_dir = self.tree_dir / "fs"
        self.sub_dir.mkdir(parents=True, exist_ok=True)
        self.target_file = self.sub_dir / "test.c"
        self.initial_content = (
            "/* header */\n"
            "int original_function(void) {\n"
            "    return 0;\n"
            "}\n"
        )
        self.target_file.write_text(self.initial_content, encoding="utf-8")

        self.patch_content = (
            "diff --git a/fs/test.c b/fs/test.c\n"
            "--- a/fs/test.c\n"
            "+++ b/fs/test.c\n"
            "@@ -1,4 +1,6 @@\n"
            " /* header */\n"
            "+/* added comment */\n"
            " int original_function(void) {\n"
            "+    /* hook */\n"
            "     return 0;\n"
            " }\n"
        )
        self.patch_file = self.tree_dir / "test.patch"
        self.patch_file.write_text(self.patch_content, encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_check_dry_run_leaves_target_tree_byte_identical(self) -> None:
        """any check/dry-run mode leaves the target tree byte-identical."""
        before_bytes = {
            p.relative_to(self.tree_dir): p.read_bytes()
            for p in self.tree_dir.rglob("*")
            if p.is_file() and p != self.patch_file
        }

        # Run validate_exact_patch_on_tree in dry_run mode
        success, errors = validate_exact_patch_on_tree(self.tree_dir, self.patch_file, dry_run=True)
        self.assertTrue(success, f"Dry-run validation should succeed: {errors}")
        self.assertEqual(errors, [])

        after_bytes = {
            p.relative_to(self.tree_dir): p.read_bytes()
            for p in self.tree_dir.rglob("*")
            if p.is_file() and p != self.patch_file
        }
        self.assertEqual(before_bytes, after_bytes, "Target tree must remain 100% byte-identical in dry-run mode")
        self.assertFalse(list(self.tree_dir.glob("**/*.rej")), "No .rej files should exist in dry-run")

        # Test CLI with --check / --dry-run
        ret = main(["--patch", str(self.patch_file), "--target-tree", str(self.tree_dir), "--check"])
        self.assertEqual(ret, 0)
        cli_after_bytes = {
            p.relative_to(self.tree_dir): p.read_bytes()
            for p in self.tree_dir.rglob("*")
            if p.is_file() and p != self.patch_file
        }
        self.assertEqual(before_bytes, cli_after_bytes, "CLI --check must leave tree byte-identical")

    def test_authoritative_application_succeeds_once_without_second_invocation(self) -> None:
        """clean tree -> validation/application succeeds, target postimage is produced exactly once,
        no .rej files, no second patch invocation is required (and a second invocation fails closed)."""
        # Single authoritative application
        success, errors = validate_exact_patch_on_tree(self.tree_dir, self.patch_file, dry_run=False)
        self.assertTrue(success, f"Application should succeed: {errors}")
        self.assertEqual(errors, [])

        # Target postimage produced exactly once
        patched_content = self.target_file.read_text(encoding="utf-8")
        self.assertEqual(patched_content.count("/* added comment */"), 1)
        self.assertEqual(patched_content.count("/* hook */"), 1)
        self.assertIn("return 0;", patched_content)

        # No .rej files exist
        rej_files = list(self.tree_dir.glob("**/*.rej"))
        self.assertEqual(rej_files, [], "No .rej files must exist after application")

        # Prove that running patch again on the already-applied tree would fail closed
        # (reproducing the exact reversed/previously applied failure if a workflow had a duplicate apply)
        second_success, second_errors = validate_exact_patch_on_tree(self.tree_dir, self.patch_file, dry_run=False)
        self.assertFalse(second_success, "Second patch invocation must fail on already-applied tree")
        self.assertTrue(any("Reject files found" in e or "non-zero status" in e for e in second_errors))


if __name__ == "__main__":
    unittest.main()
