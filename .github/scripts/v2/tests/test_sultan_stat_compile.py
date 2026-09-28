"""Check Sultan stat CONFIG combinations against authenticated declarations.

No SuSFS declaration, constant, or native kernel type is mocked here.
The small header closure is captured from the authenticated target via Kbuild.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

from v2.pipeline import generate_candidate_patch
from v2.engine.diff_parser import parse_patch
from v2.engine.emitter import emit_patch
from v2.source.baseline import load_authoritative_bundle
from v2.source.patch_apply import apply_patch_to_bundle

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / ".github/fixtures/sultan/stat-compile"


def generated_stat():
    candidate = generate_candidate_patch("sultan-android14-6.1-patch51",
                                         ROOT / ".github/fixtures/sultan", ROOT)
    patch = parse_patch(candidate)
    patch.files = [f for f in patch.files if f.old_path == "a/fs/stat.c"]
    bundle = load_authoritative_bundle("sultan-android14-6.1", ROOT)
    return apply_patch_to_bundle(bundle, emit_patch(patch)).get_file("fs/stat.c").content


def compile_stat(tree, source, flags, *, susfs=True, kstat=True):
    (tree / "fs/stat.c").write_text(source)
    config = (["-DCONFIG_KSU_SUSFS"] if susfs else [])
    if kstat:
        config.append("-DCONFIG_KSU_SUSFS_SUS_KSTAT")
    return subprocess.run(["clang", *flags, *config, "../fs/stat.c"],
                          cwd=tree / "out", capture_output=True, text=True)


class SultanStatCompileTests(unittest.TestCase):
    def test_generated_stat_translation_unit_with_native_declarations(self):
        metadata = json.loads((FIXTURE / "provenance.json").read_text())
        baseline = json.loads((ROOT / "patches/sultan-android14-6.1/BASELINE.json").read_text())
        self.assertEqual(metadata["target_commit"], baseline["upstream"]["resolved_commit"])
        self.assertEqual(metadata["target_archive_sha256"], baseline["upstream"]["archive_sha256"])
        self.assertEqual(metadata["susfs_commit"], baseline["susfs"]["resolved_commit"])
        archive = FIXTURE / "headers.tar.gz"
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), metadata["archive_sha256"])
        state = json.loads((ROOT / ".github/upstream-state.json").read_text())
        expected_header = state["sources"]["authoritative"]["susfs_sultan"]["tracked_files"][
            "kernel_patches/include/linux/susfs_def.h"].removeprefix("sha256:")
        with tempfile.TemporaryDirectory(prefix="sultan-stat-compile-") as tmp:
            tree = Path(tmp)
            with tarfile.open(archive) as tar:
                for member in tar:
                    self.assertTrue(member.isfile())
                    self.assertFalse(Path(member.name).is_absolute() or ".." in Path(member.name).parts)
                    data = tar.extractfile(member).read()
                    self.assertEqual(hashlib.sha256(data).hexdigest(), metadata["files"][member.name])
                    path = tree / member.name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
            self.assertEqual(hashlib.sha256((tree / "include/linux/susfs_def.h").read_bytes()).hexdigest(),
                             expected_header)
            source = generated_stat()
            for susfs, kstat in ((True, False), (False, False)):
                with self.subTest(susfs=susfs, kstat=kstat):
                    result = compile_stat(tree, source, metadata["compiler_flags"], susfs=susfs, kstat=kstat)
                    self.assertEqual(result.returncode, 0, result.stderr)

            # Real Kbuild + dynamic object closure now own positive build/link
            # dependency evidence and historical mount-helper mutations. Retain
            # these small authenticated-header CONFIG-off checks, which cover a
            # different boundary from the enabled production configuration.
