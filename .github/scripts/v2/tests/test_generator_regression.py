"""Regression tests reproducing and guarding against character literal escape corruption in patch generators."""

from __future__ import annotations

from pathlib import Path
import re
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

    def test_reproduce_re_sub_template_corrupts_escaped_newline_literal(self) -> None:
        """Demonstrate that re.sub string replacement unescapes '\\n' into raw line breaks."""
        # A hunk containing C code with character literal '\n'
        c_line = "\t\t\t\tseq_putc(m, '\\n');"
        self.assertIn(r"\n", c_line)
        self.assertNotIn("\n", c_line)

        # Naive string template substitution in re.sub
        template = f"+#ifdef TEST\n{c_line}\n+#endif"
        corrupted = re.sub(r"ANCHOR", template, "ANCHOR")

        # The '\\n' in the replacement string template is converted to a raw 0x0A newline:
        # seq_putc(m, '
        # ');
        self.assertIn("seq_putc(m, '\n", corrupted)
        self.assertNotIn(r"\n", corrupted)

    def test_safe_replacement_preserves_character_literal(self) -> None:
        """Verify that str.replace and lambda replacements preserve '\\n' verbatim."""
        c_line = "\t\t\t\tseq_putc(m, '\\n');"
        template = f"+#ifdef TEST\n{c_line}\n+#endif"

        # 1. str.replace
        safe1 = "ANCHOR".replace("ANCHOR", template)
        self.assertIn(r"seq_putc(m, '\n');", safe1)
        self.assertNotIn("seq_putc(m, '\n", safe1)

        # 2. lambda in re.sub
        safe2 = re.sub(r"ANCHOR", lambda m: template, "ANCHOR")
        self.assertIn(r"seq_putc(m, '\n');", safe2)
        self.assertNotIn("seq_putc(m, '\n", safe2)

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
