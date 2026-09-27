"""Source transformation / native Git boundaries, not kernel build claims."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from v2.policy.patch51_source import generate, reconstruct_postimages, remove_transport, GIT_DIFF, DECLARATIONS
from v2.source.bundle import create_source_bundle
from v2.source.patch_apply import apply_patch_to_bundle
from v2.pipeline import TARGET_REL_PATHS
from v2.validation.patch51_kbuild import kbuild_objects, affected_sources

ROOT = Path(__file__).resolve().parents[4]


class Patch51SourceTests(unittest.TestCase):
    def test_native_git_and_independent_round_trip_preserve_migration_baseline(self):
        for folder, pid in (("sultan", "sultan-android14-6.1-patch51"),
                            ("r38", "gki-android16-6.12-r38-patch51")):
            with self.subTest(target=pid), tempfile.TemporaryDirectory() as tmp:
                source = ROOT / ".github/fixtures" / folder
                before, after, *_ = reconstruct_postimages(pid, source, ROOT)
                # Golden is only a final migration assertion, never a transform input.
                old = apply_patch_to_bundle(create_source_bundle("gki-android16-6.12" if folder == "r38" else "sultan-android14-6.1", "6.12" if folder == "r38" else "6.1", before),
                                            (ROOT / TARGET_REL_PATHS[pid]).read_text())
                self.assertEqual(after, {f.path: f.content for f in old.files})
                tree = Path(tmp)
                for path, text in before.items():
                    dest = tree / path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(text)
                with patch("v2.engine.emitter.emit_patch", side_effect=AssertionError("manual emitter")), \
                     patch("difflib.unified_diff", side_effect=AssertionError("manual hunks")):
                    candidate, evidence = generate(pid, source, ROOT, tree)
                subprocess.run(["git", "init", "-q"], cwd=tree, check=True)
                (tree / ".git/info/attributes").write_text("*.c diff=cpp\n")
                subprocess.run(["git", "add", "."], cwd=tree, check=True)
                subprocess.run(["git", "apply", "--check", "-"], input=candidate, text=True, cwd=tree, check=True)
                subprocess.run(["git", "apply", "-"], input=candidate, text=True, cwd=tree, check=True)
                for path, text in after.items():
                    self.assertEqual((tree / path).read_bytes(), text.encode())
                    self.assertEqual(evidence[path]["postimage"], hashlib.sha256(text.encode()).hexdigest())
                native = subprocess.check_output(["git", *GIT_DIFF], cwd=tree)
                self.assertEqual(candidate[candidate.index("diff --git "):].encode(), native)
                with self.assertRaisesRegex(ValueError, "target preimage mismatch"):
                    generate(pid, source, ROOT, tree)  # B must not inherit A's dirty files.

    def test_mixed_source_ownership_is_explicit_and_fail_closed(self):
        source = ROOT / ".github/fixtures/sultan"
        _, images, *_ = reconstruct_postimages("sultan-android14-6.1-patch51", source, ROOT)
        stat = images["fs/stat.c"]
        self.assertIn("susfs_is_inode_sus_kstat", stat)
        self.assertIn("susfs_get_non_sus_mnt_id_from_mnt", images["fs/namespace.c"])
        self.assertNotIn("ksu_handle_stat", stat)
        with self.assertRaises(ValueError):
            remove_transport("fs/stat.c", DECLARATIONS.replace("ksu_handle_stat", "unknown_transport"), gki=False)

    def test_kbuild_maps_composite_conditional_commands_without_filename_guess(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "fs").mkdir()
            (root / "fs/different-source-name.c").write_text("/* mapping only */\n")
            plan = "clang -c -o fs/selected-member.o ../fs/different-source-name.c ; fixdep x\n"
            self.assertEqual(kbuild_objects(plan, root, root / "out"),
                             {"fs/different-source-name.c": "fs/selected-member.o"})

    def test_archive_below_checkout_does_not_hide_git_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            checkout, scratch = root / "checkout", root / "scratch"
            checkout.mkdir(); scratch.mkdir()
            subprocess.run(["git", "init", "-q", str(checkout)], check=True)
            nested = checkout / "kernel_tree"
            nested.mkdir()
            candidate = checkout / "candidate.patch"
            candidate.write_text("diff --git a/fs/stat.c b/fs/stat.c\n--- a/fs/stat.c\n+++ b/fs/stat.c\n@@ -1 +1 @@\n-old\n+new\n")
            self.assertEqual(subprocess.check_output(["git", "apply", "--numstat", str(candidate)], cwd=nested), b"")
            self.assertEqual(affected_sources(candidate, scratch), {"fs/stat.c"})
