"""Strict validator for exact patch application and syntax integrity.

Enforces:
- Zero fuzz (fuzz = 0)
- Zero rejects (rejects = 0)
- Zero hunk offsets (offset = 0 on exact target)
- Zero malformed C syntax (e.g. split character literals like seq_putc(m, '\n'))
- Deterministic postimage verification
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Mapping, Optional, Sequence, Tuple

from ..engine.diff_parser import parse_patch
from ..model.patch import AddedLine, ContextLine, Hunk, Patch, RemovedLine
from ..source.bundle import SourceBundle
from ..source.patch_apply import SourceBundlePatchError, apply_patch_to_bundle


class PatchValidationError(ValueError):
    """Raised when a patch violates strict exact application or syntax invariants."""
    pass


# Pattern matching lines ending in an unclosed single quote (e.g. seq_putc(m, ')
# or character literal split across lines.
_SPLIT_CHAR_LITERAL_PAT = re.compile(
    r"""(?:seq_putc|seq_pad)\s*\([^,]+,\s*'(\\[^']*)?\s*$""",
    re.MULTILINE,
)


def validate_patch_syntax(patch_input: Patch | str) -> list[str]:
    """Validate that patch hunks do not contain malformed C syntax or split literals.

    Detects unescaped raw newlines inside character constants, such as:
        seq_putc(m, '
        ');
    or any added line ending in an unterminated single-quote character literal.
    """
    errors: list[str] = []

    if isinstance(patch_input, str):
        # Scan raw lines first so split literals are caught even if hunk counts are broken
        for line_idx, line in enumerate(patch_input.splitlines(), 1):
            if line.startswith("+") and not line.startswith("+++"):
                content = line[1:]
                if _SPLIT_CHAR_LITERAL_PAT.search(content):
                    errors.append(
                        f"line #{line_idx}: split/unterminated character literal: {content.strip()!r}"
                    )
                elif re.search(r"seq_putc\s*\([^,]+,\s*'\s*$", content):
                    errors.append(
                        f"line #{line_idx}: unterminated character literal quote: {content.strip()!r}"
                    )

        try:
            patch = parse_patch(patch_input)
        except Exception as exc:
            if not errors:
                errors.append(f"Malformed patch structure: {exc}")
            return errors
    else:
        patch = patch_input

    for file_patch in patch.files:
        path = file_patch.new_path or file_patch.old_path or "unknown"
        # Syntax check applies strictly to C source and header files
        if not path.endswith((".c", ".h")):
            continue

        for hunk_idx, hunk in enumerate(file_patch.hunks, 1):
            for line_idx, line in enumerate(hunk.lines, 1):
                if isinstance(line, AddedLine):
                    text = line.text
                    # Check for split seq_putc / seq_pad calls
                    if _SPLIT_CHAR_LITERAL_PAT.search(text):
                        errors.append(
                            f"{path} hunk #{hunk_idx} line #{line_idx}: split/unterminated character literal: {text.strip()!r}"
                        )
                        continue

                    # Strip comments before checking character constants
                    code_only = re.sub(r"//.*$", "", text)
                    # Detect lines ending with open single quote (e.g. `+    seq_putc(m, '`)
                    if re.search(r"'\s*$", code_only) and not re.search(r"'(\\?.)'\s*$", code_only):
                        errors.append(
                            f"{path} hunk #{hunk_idx} line #{line_idx}: line ends with unclosed character quote: {text.strip()!r}"
                        )
                        continue

                    # In C code outside comments, character constants have matching pairs of single quotes
                    single_quotes = re.findall(r"(?<!\\)'", code_only)
                    if len(single_quotes) % 2 != 0:
                        errors.append(
                            f"{path} hunk #{hunk_idx} line #{line_idx}: unmatched single quote in C code: {text.strip()!r}"
                        )

    return errors


def parse_patch_tool_output(output: str) -> list[str]:
    """Parse output from GNU patch and detect non-zero offsets, fuzz, or failures.

    GNU patch outputs:
        Hunk #1 succeeded at 454 (offset -79 lines).
        Hunk #4 succeeded at 497 with fuzz 3 (offset -47 lines).
        Hunk #1 FAILED at 100.
    """
    errors: list[str] = []
    for line in output.splitlines():
        line_clean = line.strip()
        if not line_clean:
            continue
        if re.search(r"\(offset\s+[-+]?\d+\s+lines?\)", line_clean):
            errors.append(f"Non-zero hunk offset detected: {line_clean}")
        if re.search(r"with\s+fuzz\s+\d+", line_clean):
            errors.append(f"Fuzz detected: {line_clean}")
        if re.search(r"\bFAILED\b", line_clean):
            errors.append(f"Hunk failure detected: {line_clean}")
    return errors



def verify_postimage_integrity(content: str, file_path: str = "unknown") -> list[str]:
    """Verify that a patched source file does not contain malformed split character literals."""
    errors: list[str] = []
    lines = content.splitlines()
    for idx, line in enumerate(lines, 1):
        if _SPLIT_CHAR_LITERAL_PAT.search(line):
            errors.append(f"{file_path}:{idx}: split character literal in source: {line.strip()!r}")
        elif re.search(r"seq_putc\s*\([^,]+,\s*'\s*$", line):
            errors.append(f"{file_path}:{idx}: unterminated seq_putc literal: {line.strip()!r}")
    return errors


def validate_exact_bundle_application(
    bundle: SourceBundle,
    patch_text: str,
    *,
    expected_postimage_hashes: Optional[Mapping[str, str]] = None,
) -> SourceBundle:
    """Strictly apply patch to bundle at offset 0, fuzz 0, and verify postimages.

    Fails closed on:
    - Syntax defects in hunks (split literals / unescaped newlines)
    - Context mismatch (offsets != 0 or context drift)
    - Removal mismatch
    - Postimage syntax defects or hash mismatches
    """
    syntax_errors = validate_patch_syntax(patch_text)
    if syntax_errors:
        raise PatchValidationError("Patch syntax validation failed:\n" + "\n".join(f"  - {e}" for e in syntax_errors))

    # apply_patch_to_bundle enforces exact context at declared hunk coordinates (offset 0, fuzz 0)
    try:
        patched_bundle = apply_patch_to_bundle(bundle, patch_text)
    except Exception as exc:
        raise PatchValidationError(f"Exact patch application failed at offset 0 / fuzz 0: {exc}") from exc

    # Verify postimages
    for f in patched_bundle.files:
        if f.content is not None:
            post_errors = verify_postimage_integrity(f.content, f.path)
            if post_errors:
                raise PatchValidationError("Postimage integrity failure:\n" + "\n".join(f"  - {e}" for e in post_errors))

    if expected_postimage_hashes:
        for file_path, expected_sha in expected_postimage_hashes.items():
            entry = patched_bundle.get_file(file_path)
            if entry is None:
                raise PatchValidationError(f"Expected postimage file missing: {file_path}")
            clean_expected = expected_sha.removeprefix("sha256:")
            if entry.content_hash.value != clean_expected:
                raise PatchValidationError(
                    f"Postimage hash mismatch for {file_path}: expected {clean_expected}, got {entry.content_hash.value}"
                )

    return patched_bundle


def validate_exact_patch_on_tree(
    tree_dir: Path,
    patch_path: Path,
    *,
    dry_run: bool = True,
) -> Tuple[bool, list[str]]:
    """Validate patch application against a real kernel tree with 0 fuzz, 0 offsets, and 0 rejects."""
    errors: list[str] = []

    if not tree_dir.is_dir():
        return False, [f"Target tree directory not found: {tree_dir}"]
    if not patch_path.is_file():
        return False, [f"Patch file not found: {patch_path}"]

    # 1. Validate patch syntax
    patch_text = patch_path.read_text(encoding="utf-8")
    syntax_errors = validate_patch_syntax(patch_text)
    if syntax_errors:
        errors.extend(syntax_errors)
        return False, errors

    # 2. Run patch tool with --fuzz=0
    cmd = ["patch", "-p1", "--fuzz=0"]
    if dry_run:
        cmd.append("--dry-run")

    try:
        proc = subprocess.run(
            cmd,
            input=patch_text,
            text=True,
            capture_output=True,
            cwd=tree_dir,
        )
    except Exception as exc:
        return False, [f"Failed to execute patch tool: {exc}"]

    # Check tool output for offsets or fuzz
    tool_output = proc.stdout + "\n" + proc.stderr
    tool_errors = parse_patch_tool_output(tool_output)
    if tool_errors:
        errors.extend(tool_errors)

    if proc.returncode != 0:
        errors.append(f"patch command exited with non-zero status {proc.returncode}")

    # Check for any .rej files
    rej_files = list(tree_dir.glob("**/*.rej"))
    if rej_files:
        errors.append(f"Reject files found: {', '.join(str(p) for p in rej_files)}")

    # 3. Postimage syntax verification on patched files
    if not dry_run and proc.returncode == 0 and not errors:
        parsed = parse_patch(patch_text)
        for fp in parsed.files:
            rel = fp.new_path or fp.old_path
            if rel and rel.startswith(("a/", "b/")):
                rel = rel[2:]
            if rel and rel != "/dev/null":
                fpath = tree_dir / rel
                if fpath.is_file():
                    content = fpath.read_text(encoding="utf-8", errors="ignore")
                    post_errs = verify_postimage_integrity(content, rel)
                    if post_errs:
                        errors.extend(post_errs)

    return len(errors) == 0, errors


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Strict patch validator and authoritative applicator (0 fuzz, 0 offset, 0 rejects)"
    )
    parser.add_argument("--patch", required=True, type=Path, help="Path to patch file")
    parser.add_argument("--target-tree", type=Path, default=None, help="Path to target kernel tree")
    parser.add_argument(
        "--check",
        "--dry-run",
        dest="check_only",
        action="store_true",
        default=False,
        help="Check-only mode: validate patch application without modifying target tree",
    )
    args = parser.parse_args(argv)

    if args.target_tree:
        valid, errors = validate_exact_patch_on_tree(args.target_tree, args.patch, dry_run=args.check_only)
        if not valid:
            mode_str = "check" if args.check_only else "application"
            print(f"❌ Strict patch {mode_str} FAILED:")
            for err in errors:
                print(f"  - {err}")
            return 1
        if args.check_only:
            print("✅ Strict patch check PASSED: 0 fuzz, 0 offsets, 0 rejects, valid syntax (tree unmodified).")
        else:
            print("✅ Strict patch application SUCCEEDED: applied cleanly with 0 fuzz, 0 offsets, 0 rejects, valid syntax.")
        return 0
    else:
        # Syntax check only
        patch_text = args.patch.read_text(encoding="utf-8")
        errors = validate_patch_syntax(patch_text)
        if errors:
            print("❌ Patch syntax validation FAILED:")
            for err in errors:
                print(f"  - {err}")
            return 1
        print("✅ Patch syntax validation PASSED: 0 syntax defects.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
