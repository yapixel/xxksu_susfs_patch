"""Compile generated Sultan translation units and link their SuSFS mount helpers.

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
            for susfs, kstat in ((True, True), (True, False), (False, False)):
                with self.subTest(susfs=susfs, kstat=kstat):
                    result = compile_stat(tree, source, metadata["compiler_flags"], susfs=susfs, kstat=kstat)
                    self.assertEqual(result.returncode, 0, result.stderr)

            # Link full generated callers and definitions, not a handwritten model.
            # A relocatable link alone allows undefineds, so enforce this exact
            # historical closure at the real linker boundary with DEFINED assertions.
            candidate = generate_candidate_patch("sultan-android14-6.1-patch51",
                                                 ROOT / ".github/fixtures/sultan", ROOT)
            post = apply_patch_to_bundle(load_authoritative_bundle("sultan-android14-6.1", ROOT),
                                         candidate)
            for name in ("include/linux/susfs.h", "fs/namespace.c", "fs/susfs.c",
                         "fs/statfs.c", "fs/proc/fd.c"):
                path = tree / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(post.get_file(name).content)
            objects = []
            flags = [f for f in metadata["compiler_flags"]
                     if f != "-fsyntax-only" and not f.startswith("-DKBUILD_")
                     and not f.startswith("-D__KBUILD_")]
            for name in ("namespace", "susfs", "statfs", "proc/fd"):
                obj = tree / (name.replace("/", "_") + ".o")
                stem = Path(name).name
                result = subprocess.run([
                    "clang", *flags, "-O2", "-fno-pie", "-fno-stack-protector",
                    "-DCONFIG_KSU_SUSFS", "-DCONFIG_KSU_SUSFS_SUS_MOUNT",
                    "-DCONFIG_KSU_SUSFS_SUS_KSTAT",
                    f'-DKBUILD_MODNAME="{stem}"', f'-DKBUILD_BASENAME="{stem}"',
                    f'-DKBUILD_MODFILE="fs/{name}"', f'-D__KBUILD_MODNAME=kmod_{stem}',
                    "-DKBUILD_IS_MODULE=1", "-c", f"../fs/{name}.c", "-o", str(obj)],
                    cwd=tree / "out", capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                objects.append(str(obj))
            symbols = ("susfs_get_non_sus_mnt_id_from_mnt",
                       "susfs_get_non_sus_vfsmnt_from_vfsmnt")
            script = tree / "mount-closure.lds"
            script.write_text("\n".join(
                f'ASSERT(DEFINED({symbol}), "undefined reference to {symbol}");'
                for symbol in symbols))
            result = subprocess.run(["ld.lld", "-r", "-T", str(script),
                                     "-o", str(tree / "mount-closure.o"), *objects],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
