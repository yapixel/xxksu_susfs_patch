"""Destructive provenance checks; expected outputs never construct source inputs."""
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from v2.pipeline import CandidateGenerationError, TARGET_REL_PATHS, generate_candidate_patch
from v2.source.baseline import load_authoritative_bundle
from v2.watch.checker import UpstreamWatcher, compute_composite_hash
from v2.watch.model import WatchClassification

ROOT = Path(__file__).resolve().parents[4]
SULTAN = "sultan-android14-6.1-patch51"


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="provenance-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        # Keep code, metadata and source snapshots, never final patch copies.
        shutil.copytree(ROOT / ".github", self.root / ".github",
                        ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "patches", self.root / "patches")
        for path in self.root.rglob("*.patch"):
            if path.name.startswith(("11_", "51_")) or "reference" in path.name:
                path.unlink()
        self.ksu = self.root / "xxksu"
        for entry in load_authoritative_bundle("xxksu", ROOT).files:
            path = self.ksu / entry.path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(entry.content)
        self.sultan = self.root / ".github/fixtures/sultan"

    def fresh(self, patch_id, source):
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
               "PYTHONPATH": str(self.root / ".github/scripts"), "TZ": "Pacific/Honolulu"}
        code = ("import sys; from pathlib import Path; "
                "from v2.pipeline import generate_candidate_patch; "
                "sys.stdout.write(generate_candidate_patch(sys.argv[1], Path(sys.argv[2]), Path.cwd()))")
        return subprocess.run([sys.executable, "-c", code, patch_id, str(source)],
                              cwd=self.root, env=env, capture_output=True, check=True).stdout

    def test_patch11_reconstructs_without_outputs_or_patch10_and_requires_xxksu(self):
        expected = (ROOT / TARGET_REL_PATHS["xxksu-patch11"]).read_bytes()
        self.assertFalse(list(self.root.rglob("*10_enable_susfs*")))
        self.assertEqual(self.fresh("xxksu-patch11", self.ksu), expected)
        source = self.ksu / "kernel/Kconfig"
        original = source.read_text()
        source.unlink()
        with self.assertRaises(CandidateGenerationError):
            generate_candidate_patch("xxksu-patch11", self.ksu, self.root)
        source.write_text(original.replace("endmenu", "missing_semantic_anchor", 1))
        with self.assertRaises(ValueError):
            generate_candidate_patch("xxksu-patch11", self.ksu, self.root)

    def test_sultan_without_outputs_is_deterministic_and_inputs_are_required(self):
        # Approved metadata-only migration; body/golden is checked only as output.
        expected = re.sub(rb"(?m)^Date:.*$", b"Date: Fri, 25 Sep 2026 17:26:49 +0000",
                          (ROOT / TARGET_REL_PATHS[SULTAN]).read_bytes())
        self.assertEqual(self.fresh(SULTAN, self.sultan), expected)
        self.assertEqual(self.fresh(SULTAN, self.sultan), expected)
        source = self.sultan / "50_add_susfs_in_gki-android14-6.1.patch"
        # The standalone converter must not reuse an existing output Date either.
        output = self.root / "legacy.patch"
        output.write_text("Date: Wed, 01 Jan 2020 00:00:00 +0000\\n")
        subprocess.run([sys.executable, str(self.root / ".github/scripts/deinline_50_to_51.py"),
                        "--input", str(source), "--output", str(output),
                        "--target", "sultan-android14-6.1"], cwd=self.root,
                       env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                       check=True, capture_output=True)
        self.assertIn("Date: Fri, 25 Sep 2026 17:26:49 +0000", output.read_text())
        original = source.read_text()
        source.unlink()
        with self.assertRaises(CandidateGenerationError):
            generate_candidate_patch(SULTAN, self.sultan, self.root)
        changed = original.replace("obj-$(CONFIG_KSU_SUSFS) += susfs.o",
                                   "obj-$(CONFIG_KSU_SUSFS) += provenance_probe.o", 1)
        self.assertNotEqual(changed, original)
        source.write_text(changed)
        self.assertNotEqual(generate_candidate_patch(SULTAN, self.sultan, self.root).encode(), expected)
        source.write_text(original)
        context = self.root / ".github/fixtures/v2/v29-baselines/sultan-android14-6.1.json"
        saved = context.read_bytes()
        context.unlink()
        with self.assertRaises(FileNotFoundError):
            generate_candidate_patch(SULTAN, self.sultan, self.root)
        data = json.loads(saved)
        for entry in data["files"]:
            if entry["path"] == "fs/namespace.c":
                entry["content"] = entry["content"].replace("static struct mount *clone_mnt(",
                                                          "static struct mount *changed_clone(", 1)
        context.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            generate_candidate_patch(SULTAN, self.sultan, self.root)
        context.write_bytes(saved)
        metadata = self.sultan / "susfs-source-commit.txt"
        metadata.write_bytes(metadata.read_bytes() + b"tampered")
        with self.assertRaisesRegex(CandidateGenerationError, "metadata identity mismatch"):
            generate_candidate_patch(SULTAN, self.sultan, self.root)

    def test_patch10_lineage_drift_reaches_real_watch_semantic_review(self):
        info = json.loads((ROOT / ".github/upstream-state.json").read_text())[
            "sources"]["authoritative"]["susfs_gki"]
        p50 = "kernel_patches/50_add_susfs_in_gki-android16-6.12.patch"
        p10 = "kernel_patches/KernelSU/10_enable_susfs_for_ksu.patch"
        self.assertIn(p10, info["tracked_files"])
        old = {p50: (ROOT / ".github/fixtures/r38" / Path(p50).name).read_text(),
               p10: "diff --git a/kernel/ksu.c b/kernel/ksu.c\n--- a/kernel/ksu.c\n"
                    "+++ b/kernel/ksu.c\n@@ -1 +1,2 @@\n void init(void) {\n+\tsusfs_init();\n"}
        new = {**old, p10: old[p10].replace("susfs_init();", "unreviewed_lineage_call();")}
        info["tracked_files"] = {p: "sha256:" + hashlib.sha256(v.encode()).hexdigest()
                                 for p, v in old.items()}
        info["relevant_content_hash"] = compute_composite_hash(info["tracked_files"])
        def fetch(url, commit, paths):
            values = old if commit == info["commit"] else new
            return {p: values[p] for p in paths}
        with patch("v2.watch.checker.fetch_remote_commit", return_value="f" * 40), \
             patch("v2.watch.checker.fetch_git_files", side_effect=fetch) as fetched:
            result = UpstreamWatcher(repo_root=ROOT, state_path=ROOT / ".github/upstream-state.json").check_susfs_authoritative(
                "susfs_gki", "gki-android16-6.12", info)
        self.assertTrue(any(p10 in call.args[2] for call in fetched.call_args_list))
        self.assertEqual(result.classification, WatchClassification.SEMANTIC_DRIFT)
        self.assertIn(p10, result.affected_files)
        self.assertIn("Patch 10", result.details)


    def test_gki_reconstructs_without_final_outputs_and_requires_authoritative_inputs(self):
        from v2.engine.diff_parser import parse_patch
        from v2.policy.gki_r38 import FILES
        patch_id = "gki-android16-6.12-r38-patch51"
        source = self.root / ".github/fixtures/r38/50_add_susfs_in_gki-android16-6.12.patch"
        # setUp removed production, historical 51 and Midori reference outputs.
        self.assertFalse(list(self.root.rglob("51_*.patch")))
        first = self.fresh(patch_id, source.parent)
        second = self.fresh(patch_id, source.parent)
        self.assertEqual(first, second)
        self.assertEqual({f.old_path[2:] for f in parse_patch(first.decode()).files}, set(FILES))
        # Golden is read only AFTER independent generation; it supplies no input.
        expected = (ROOT / TARGET_REL_PATHS[patch_id]).read_bytes()
        self.assertEqual(first, expected)
        self.assertIn(b"Date: Fri, 25 Sep 2026 17:48:27 +0000", first)
        empty = self.root / "empty"
        empty.mkdir()
        with self.assertRaisesRegex(CandidateGenerationError, "Patch 50 missing"):
            generate_candidate_patch(patch_id, empty, self.root)
        saved = source.read_bytes()
        source.unlink()
        with self.assertRaisesRegex(CandidateGenerationError, "Patch 50 missing"):
            generate_candidate_patch(patch_id, source.parent, self.root)
        for old, new in (
            (b"obj-$(CONFIG_KSU_SUSFS) += susfs.o", b"obj-$(CONFIG_KSU_SUSFS) += wrong.o"),
            (b"ksu_handle_setresuid", b"changed_credential_hook"),
        ):
            with self.subTest(input_mutation=old):
                changed = saved.replace(old, new)
                self.assertNotEqual(changed, saved)
                source.write_bytes(changed)
                with self.assertRaisesRegex(CandidateGenerationError, "unreviewed GKI Patch 50"):
                    generate_candidate_patch(patch_id, source.parent, self.root)
        source.write_bytes(saved)
        context = self.root / ".github/fixtures/v2/r38-sources.json"
        saved_context = context.read_bytes()
        context.unlink()
        with self.assertRaises(CandidateGenerationError):
            generate_candidate_patch(patch_id, source.parent, self.root)
        data = json.loads(saved_context)
        del data["files"]["fs/notify/fdinfo.c"]
        context.write_text(json.dumps(data))
        with self.assertRaisesRegex(CandidateGenerationError, "source context missing"):
            generate_candidate_patch(patch_id, source.parent, self.root)
        for field, anchor in (("fs/namei.c", "lookup_dcache"),
                              ("fs/notify/fdinfo.c", "show_fdinfo")):
            data = json.loads(saved_context)
            original = data["files"][field]["content"]
            data["files"][field]["content"] = original.replace(anchor, "unreviewed_anchor", 1)
            self.assertNotEqual(data["files"][field]["content"], original)
            context.write_text(json.dumps(data))
            with self.assertRaisesRegex(CandidateGenerationError, "r38 source hash mismatch"):
                generate_candidate_patch(patch_id, source.parent, self.root)
        context.write_bytes(saved_context)
        metadata = source.parent / "susfs-source-commit.txt"
        metadata.write_bytes(metadata.read_bytes() + b"tampered")
        with self.assertRaisesRegex(CandidateGenerationError, "metadata identity mismatch"):
            generate_candidate_patch(patch_id, source.parent, self.root)
