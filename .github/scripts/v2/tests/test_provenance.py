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

    def assert_production_postimages(self, patch_id, candidate):
        expected = (ROOT / TARGET_REL_PATHS[patch_id]).read_bytes()
        if patch_id == "xxksu-patch11":
            self.assertEqual(candidate, expected)
            return
        from v2.source.patch_apply import apply_patch_to_bundle
        from v2.source.bundle import create_source_bundle
        from v2.policy.lifecycle import r38_sources
        bundle = (create_source_bundle("gki-android16-6.12", "6.12", r38_sources(ROOT))
                  if patch_id.startswith("gki") else load_authoritative_bundle("sultan-android14-6.1", ROOT))
        def images(text):
            return {f.path: f.content for f in apply_patch_to_bundle(bundle, text.decode()).files}
        self.assertEqual(images(candidate), images(expected))
        self.assertEqual(candidate.split(b"---\n", 1)[0], expected.split(b"---\n", 1)[0])

    def test_patch11_reconstructs_without_outputs_or_patch10_and_requires_xxksu(self):
        expected = (ROOT / TARGET_REL_PATHS["xxksu-patch11"]).read_bytes()
        self.assertFalse(list(self.root.rglob("*10_enable_susfs*")))
        first = self.fresh("xxksu-patch11", self.ksu)
        self.assertEqual(first, self.fresh("xxksu-patch11", self.ksu))
        self.assertEqual(first, expected)
        source = self.ksu / "kernel/Kconfig"
        original = source.read_text()
        source.unlink()
        with self.assertRaises(CandidateGenerationError):
            generate_candidate_patch("xxksu-patch11", self.ksu, self.root)
        source.write_text(original.replace("endmenu", "missing_semantic_anchor", 1))
        with self.assertRaises(ValueError):
            generate_candidate_patch("xxksu-patch11", self.ksu, self.root)

    def test_patch11_policy_date_and_diff_identity_are_independent(self):
        from v2.adapters.xxksu import patch11_envelope_id
        first = self.fresh("xxksu-patch11", self.ksu)
        baseline = self.root / "patches/xxksu/BASELINE.json"
        data = json.loads(baseline.read_text())
        policy = data["policy"]["reviewed_revision"]
        metadata = self.root / policy["commit_object"]
        original = metadata.read_bytes()
        # A controlled, authenticated test commit: same policy tree, later
        # committer timestamp. Git calculates its identity, not a mock loader.
        changed = re.sub(rb"(committer .* )([0-9]+)( [+-][0-9]{4})",
                         lambda m: m[1] + str(int(m[2]) + 86400).encode() + m[3], original, count=1)
        self.assertNotEqual(changed, original)
        policy["resolved_commit"] = subprocess.check_output(
            ["git", "hash-object", "-t", "commit", "--stdin"], input=changed).decode().strip()
        metadata.write_bytes(changed)
        baseline.write_text(json.dumps(data))
        second = self.fresh("xxksu-patch11", self.ksu)
        self.assertEqual(first.splitlines()[0], second.splitlines()[0])
        self.assertNotEqual(first.splitlines()[2], second.splitlines()[2])
        self.assertEqual(first.split(b"diff --git", 1)[1], second.split(b"diff --git", 1)[1])

        # Real transformation mutation, using the actual adapter and ID function.
        from dataclasses import replace
        from v2.adapters.xxksu import generate_patch11, _SPECS_BY_ID
        bundle = load_authoritative_bundle("xxksu", ROOT)
        spec = next(v for v in _SPECS_BY_ID.values() if "susfs_init();" in v.payload)
        unmodified = generate_patch11(bundle, self.root)
        modified_spec = replace(spec, diff_body=tuple(
            (prefix, text.replace("susfs_init();", "susfs_init_reviewed_probe();"))
            for prefix, text in spec.get_diff_body()))
        with patch.dict(_SPECS_BY_ID, {spec.operation_id: modified_spec}):
            modified = generate_patch11(bundle, self.root)
        def diff(text):
            return text[text.index("diff --git "):text.rindex("-- \n")].encode()
        self.assertNotEqual(diff(unmodified), diff(modified))
        self.assertNotEqual(patch11_envelope_id(diff(unmodified)), patch11_envelope_id(diff(modified)))
        self.assertNotEqual(unmodified.splitlines()[0], modified.splitlines()[0])
        self.assertEqual(unmodified.splitlines()[2], modified.splitlines()[2])

    def test_patch11_policy_provenance_fails_closed(self):
        baseline = self.root / "patches/xxksu/BASELINE.json"
        data = json.loads(baseline.read_text())
        record = data["policy"]["reviewed_revision"]
        metadata = self.root / record["commit_object"]
        saved = metadata.read_bytes()
        metadata.unlink()
        with self.assertRaises(subprocess.CalledProcessError):
            self.fresh("xxksu-patch11", self.ksu)
        metadata.write_bytes(saved + b"tampered")
        with self.assertRaises(subprocess.CalledProcessError):
            self.fresh("xxksu-patch11", self.ksu)
        metadata.write_bytes(saved)
        record["resolved_commit"] = "0" * 40
        baseline.write_text(json.dumps(data))
        with self.assertRaises(subprocess.CalledProcessError):
            self.fresh("xxksu-patch11", self.ksu)
        del data["policy"]["reviewed_revision"]
        baseline.write_text(json.dumps(data))
        with self.assertRaises(subprocess.CalledProcessError):
            self.fresh("xxksu-patch11", self.ksu)

    def test_sultan_without_outputs_is_deterministic_and_inputs_are_required(self):
        # Production is a final assertion only, never a generation input.
        expected = (ROOT / TARGET_REL_PATHS[SULTAN]).read_bytes()
        first = self.fresh(SULTAN, self.sultan)
        self.assertEqual(first, self.fresh(SULTAN, self.sultan))
        self.assert_production_postimages(SULTAN, first)
        source = self.sultan / "50_add_susfs_in_gki-android14-6.1.patch"
        # The standalone converter must not reuse an existing output Date either.
        output = self.root / "legacy.patch"
        output.write_text("Date: Wed, 01 Jan 2020 00:00:00 +0000\\n")
        subprocess.run([sys.executable, str(self.root / ".github/scripts/deinline_50_to_51.py"),
                        "--input", str(source), "--output", str(output),
                        "--target", "sultan-android14-6.1"], cwd=self.root,
                       env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                       check=True, capture_output=True)
        self.assertIn(re.search(rb"(?m)^Date:.*$", expected).group().decode(), output.read_text())
        original = source.read_text()
        source.unlink()
        with self.assertRaises(CandidateGenerationError):
            generate_candidate_patch(SULTAN, self.sultan, self.root)
        changed = original.replace("obj-$(CONFIG_KSU_SUSFS) += susfs.o",
                                   "obj-$(CONFIG_KSU_SUSFS) += provenance_probe.o", 1)
        self.assertNotEqual(changed, original)
        source.write_text(changed)
        with self.assertRaisesRegex(CandidateGenerationError, r"unreviewed .*Patch 50"):
            generate_candidate_patch(SULTAN, self.sultan, self.root)
        source.write_text(original)
        context = self.root / ".github/fixtures/v2/v29-baselines/sultan-android14-6.1.json"
        saved = context.read_bytes()
        context.unlink()
        with self.assertRaises(CandidateGenerationError):
            generate_candidate_patch(SULTAN, self.sultan, self.root)
        data = json.loads(saved)
        for entry in data["files"]:
            if entry["path"] == "fs/namespace.c":
                entry["content"] = entry["content"].replace("static struct mount *clone_mnt(",
                                                          "static struct mount *changed_clone(", 1)
        context.write_text(json.dumps(data))
        with self.assertRaises(CandidateGenerationError):
            generate_candidate_patch(SULTAN, self.sultan, self.root)
        context.write_bytes(saved)
        metadata = self.sultan / "susfs-source-commit.txt"
        metadata.write_bytes(metadata.read_bytes() + b"tampered")
        with self.assertRaisesRegex(CandidateGenerationError, "metadata identity mismatch"):
            generate_candidate_patch(SULTAN, self.sultan, self.root)

    def test_patch51_bytes_do_not_depend_on_midori_removal_or_poison(self):
        references = [p for p in (self.root / ".github/fixtures").rglob("*")
                      if p.is_file() and any(word in str(p).lower() for word in ("midori", "reference"))]
        for p in references:
            p.unlink()
        state_path = self.root / ".github/upstream-state.json"
        state = json.loads(state_path.read_text())
        state["sources"].pop("reference", None)
        state_path.write_text(json.dumps(state))
        inputs = ((SULTAN, self.sultan),
                  ("gki-android16-6.12-r38-patch51", self.root / ".github/fixtures/r38"))
        removed = {pid: self.fresh(pid, source) for pid, source in inputs}
        for p in references:
            p.write_text("MIDORI_POISON_MUST_NOT_ENTER_GENERATION\n")
        state["sources"]["reference"] = {"poison": "NOT_AN_INPUT"}
        state_path.write_text(json.dumps(state))
        for pid, source in inputs:
            self.assertEqual(self.fresh(pid, source), removed[pid])
            self.assert_production_postimages(pid, removed[pid])

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
        self.assert_production_postimages(patch_id, first)
        empty = self.root / "empty"
        empty.mkdir()
        with self.assertRaisesRegex(CandidateGenerationError, "Upstream SuSFS 50 patch missing"):
            generate_candidate_patch(patch_id, empty, self.root)
        saved = source.read_bytes()
        source.unlink()
        with self.assertRaisesRegex(CandidateGenerationError, "Upstream SuSFS 50 patch missing"):
            generate_candidate_patch(patch_id, source.parent, self.root)
        for old, new in (
            (b"obj-$(CONFIG_KSU_SUSFS) += susfs.o", b"obj-$(CONFIG_KSU_SUSFS) += wrong.o"),
            (b"ksu_handle_setresuid", b"changed_credential_hook"),
        ):
            with self.subTest(input_mutation=old):
                changed = saved.replace(old, new)
                self.assertNotEqual(changed, saved)
                source.write_bytes(changed)
                with self.assertRaisesRegex(CandidateGenerationError, r"unreviewed .*Patch 50"):
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

    def test_tracking_drift_and_reviewed_revision_advancement(self):
        from v2.manifests.defaults import accepted_sources
        state_path = self.root / ".github/upstream-state.json"
        state = json.loads(state_path.read_text())
        cases = (("backslashxx_kernelsu", "xxksu", "upstream", "xxksu-patch11", self.ksu),
                 ("susfs_sultan", "sultan-android14-6.1", "susfs", SULTAN, self.sultan),
                 ("susfs_gki", "gki-android16-6.12", "susfs", "gki-android16-6.12-r38-patch51",
                  self.root / ".github/fixtures/r38"))
        for key, target, field, patch_id, source in cases:
            with self.subTest(source=key):
                info = state["sources"]["authoritative"][key]
                old = info["commit"]
                if target == "xxksu":
                    new = "f" * 40
                    tracked = "kernel/Kconfig"
                    old_text = (self.ksu / tracked).read_text()
                    changed = old_text.replace("endmenu", "unreviewed_anchor", 1)
                else:
                    metadata = source / "susfs-source-commit.txt"
                    raw = metadata.read_bytes() + b"\nSimulated reviewed revision\n"
                    new = hashlib.sha1(b"commit " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
                    tracked = next(p for p in info["tracked_files"] if "/50_" in p)
                    old_text = (source / Path(tracked).name).read_text()
                    changed = old_text.replace("susfs.o", "unreviewed.o", 1)
                self.assertNotEqual(changed, old_text)
                watcher = UpstreamWatcher(self.root, state_path)
                def fetch(url, revision, paths):
                    return {tracked: old_text if revision == old else changed}
                with patch("v2.watch.checker.fetch_remote_commit", return_value=new) as resolve, \
                     patch("v2.watch.checker.fetch_git_files", side_effect=fetch) as files:
                    result = (watcher.check_backslashxx_kernelsu(info) if target == "xxksu" else
                              watcher.check_susfs_authoritative(key, target, info))
                resolve.assert_called_once_with(info["repository"], info["ref"])
                self.assertEqual((result.old_identity, result.new_identity), (old, new))
                self.assertNotEqual(result.classification, WatchClassification.NO_CHANGE)
                self.assertTrue(any(call.args[1] == new for call in files.call_args_list))
                # Simulated human approval of a new revision with identical source:
                # synchronize identity records and authenticated commit metadata only.
                info["commit"] = new
                state_path.write_text(json.dumps(state))
                baseline = self.root / "patches" / target / "BASELINE.json"
                data = json.loads(baseline.read_text())
                data[field]["resolved_commit"] = new
                with self.assertRaisesRegex(ValueError, "accepted source identity mismatch"):
                    accepted_sources(self.root)
                baseline.write_text(json.dumps(data))
                if target != "xxksu":
                    metadata.write_bytes(raw)
                self.assertEqual(accepted_sources(self.root)[key]["commit"], new)
                self.assert_production_postimages(patch_id, self.fresh(patch_id, source))

        # Execute the actual workflow identity-freezing shell, not a test resolver.
        for name in ("generate-11-ksu-patch.yml", "generate-51-kernel-patches.yml"):
            workflow = (ROOT / ".github/workflows" / name).read_text()
            self.assertNotIn("ref: main", workflow)
            self.assertNotRegex(workflow, r"bb0be929|a8324101|b213c541")
            blocks = re.findall(r"name: Freeze accepted upstream identities.*?        run: \|\n(.*?)(?=\n      - name:)", workflow, re.S)
            self.assertEqual(len(blocks), 1 if "11-" in name else 2)
            for block in blocks:
                script = "\n".join(line[10:] for line in block.splitlines())
                output = self.root / "run-identities"
                env = {**os.environ, "GITHUB_ENV": str(output), "KSU_OVERRIDE": "",
                       "RUNNER_TEMP": os.environ.get("RUNNER_TEMP", tempfile.gettempdir()),
                       "PYTHONDONTWRITEBYTECODE": "1"}
                subprocess.run(["bash", "-c", script], cwd=self.root, env=env, check=True)
                self.assertIn("KSU_COMMIT=" + state["sources"]["authoritative"]["backslashxx_kernelsu"]["commit"], output.read_text())
                self.assertIn("SULTAN_SUSFS_COMMIT=" + state["sources"]["authoritative"]["susfs_sultan"]["commit"], output.read_text())
                self.assertIn("GKI_SUSFS_COMMIT=" + state["sources"]["authoritative"]["susfs_gki"]["commit"], output.read_text())
                env["KSU_OVERRIDE"] = "master"
                self.assertNotEqual(subprocess.run(["bash", "-c", script], cwd=self.root,
                                    env=env, capture_output=True).returncode, 0)
