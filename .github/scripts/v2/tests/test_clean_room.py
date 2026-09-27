"""Focused checks of the read-only clean-room orchestration boundaries."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from v2.clean_room import authenticated_archive, generation_environment, generate_process, repository_state
from v2.source.baseline import load_authoritative_bundle

ROOT = Path(__file__).resolve().parents[4]


class CleanRoomTests(unittest.TestCase):
    def test_generation_environment_has_no_outputs_and_rejects_checkout_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "generation"
            baselines = {p.parent.name: json.loads(p.read_text())
                         for p in (ROOT / "patches").glob("*/BASELINE.json")}
            generation_environment(ROOT, dest, baselines)
            patches = list(dest.rglob("*.patch"))
            self.assertEqual(len(patches), 2)
            self.assertTrue(all(p.name.startswith("50_") for p in patches))
            self.assertFalse(list((dest / "patches").rglob("*.patch")))
            # Exercise the real generator with all declared inputs allowlisted,
            # final outputs absent and checkout reads blocked.
            source = Path(tmp) / "xxksu"
            for entry in load_authoritative_bundle("xxksu", dest).files:
                path = source / entry.path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(entry.content)
            candidate = generate_process(dest, "xxksu-patch11", source)
            self.assertEqual(candidate, (ROOT / "patches/xxksu/11_enable_susfs_for_ksu.patch").read_bytes())
            # Simulate an accidental fallback in a separate process so the audit
            # hook cannot affect the test runner. It must block before file I/O.
            code = """
import sys, types
from pathlib import Path
from v2.clean_room import generate_child
fake = types.ModuleType('v2.pipeline')
fake.generate_candidate_patch = lambda *args: (Path(sys.argv[1])/'AGENTS.md').read_text()
sys.modules['v2.pipeline'] = fake
generate_child('probe', '.', sys.argv[1])
"""
            proc = subprocess.run([sys.executable, "-c", code, str(ROOT)], cwd=dest,
                                  env={**os.environ, "PYTHONPATH": str(dest / ".github/scripts"),
                                       "PYTHONDONTWRITEBYTECODE": "1"}, capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("generator attempted final-output/checkout read", proc.stderr)

    def test_bad_archive_never_reaches_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "archive"
            archive.write_bytes(b"not the accepted archive")
            with patch("v2.clean_room.subprocess.run") as run:
                with self.assertRaisesRegex(RuntimeError, "archive SHA mismatch"):
                    authenticated_archive({"archive_url": "https://example.invalid/source",
                                           "archive_sha256": "0" * 64},
                                          archive, Path(tmp) / "target")
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0][0], "curl")
            self.assertFalse((Path(tmp) / "target").exists())

    def test_immutability_detects_ignored_untracked_and_staged_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            self.assertEqual(repository_state(root), {"tracked": "CLEAN", "untracked": []})
            (root / ".git/info/exclude").write_text("scratch\n")
            (root / "scratch").write_text("unexpected ignored output")
            self.assertEqual(repository_state(root)["untracked"], ["scratch"])
            (root / "tracked").write_text("unexpected tracked change")
            subprocess.run(["git", "add", "tracked"], cwd=root, check=True)
            self.assertEqual(repository_state(root)["tracked"], "DIRTY")
