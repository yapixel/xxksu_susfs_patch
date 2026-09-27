"""Reconstruct only android16-6.12-2025-09_r38 from accepted Patch 50.

Target excerpts are clean archive members, not reverse-applied Patch 51 hunks.
An input change needs review before this bounded transformation will accept it.
"""
from datetime import datetime, timezone
from email.utils import format_datetime
import hashlib
import json
from pathlib import Path

from ..engine.diff_parser import parse_patch
from ..model.patch import AddedLine, RemovedLine
from .lifecycle import r38_sources, replace_once, fix_namespace, fix_task_mmu, fix_remote_memory

# KSU transport/credential hooks in the other Patch 50 files belong to xxKSU.
FILES = (
    "fs/Makefile", "fs/namei.c", "fs/namespace.c", "fs/notify/fdinfo.c",
    "fs/proc/base.c", "fs/proc/bootconfig.c", "fs/proc/fd.c",
    "fs/proc/task_mmu.c", "fs/proc_namespace.c", "fs/readdir.c",
    "fs/stat.c", "fs/statfs.c", "fs/super.c", "kernel/kallsyms.c",
    "kernel/sys.c", "mm/memory.c",
)


def _apply_retained(source, file):
    """Match complete upstream preimages; no fuzzy or partial-context matching."""
    lines = source.splitlines()
    output, cursor = [], 0
    for hunk in file.hunks:
        before = [line.text for line in hunk.lines if not isinstance(line, AddedLine)]
        after = [line.text for line in hunk.lines if not isinstance(line, RemovedLine)]
        at = hunk.old_start - 1
        if lines[at:at + len(before)] != before:
            matches = [i for i in range(cursor, len(lines) - len(before) + 1)
                       if lines[i:i + len(before)] == before]
            if len(matches) != 1:
                raise ValueError(f"unreviewed r38 context: {file.old_path}:{hunk.old_start}")
            at = matches[0]
        if at < cursor:
            raise ValueError(f"overlapping r38 contexts: {file.old_path}")
        output.extend(lines[cursor:at] + after)
        cursor = at + len(before)
    return "\n".join(output + lines[cursor:]) + "\n"


def _adapt(path, source):
    if path == "fs/stat.c":
        # Mixed upstream hunk: retain SuSFS includes/KSTAT, remove only KSU externs.
        source = replace_once(source,
            "#ifdef CONFIG_KSU_SUSFS\n"
            "extern struct static_key_true ksu_is_init_rc_hook_enabled;\n"
            "extern void ksu_handle_vfs_fstat(int fd, loff_t *kstat_size_ptr);\n"
            "extern struct static_key_true ksu_su_compat_enabled;\n"
            "extern bool __ksu_is_allow_uid_for_current(uid_t uid);\n"
            "extern int ksu_handle_stat(int *dfd, struct filename **filename, int *flags);\n"
            "#endif // #ifdef CONFIG_KSU_SUSFS\n", "")
    elif path == "fs/namespace.c":
        source = fix_namespace(source)
        # Reviewed lookup policy: all paths use the locked traversal/root check.
        for field in ("mnt_id", "mnt_id_unique"):
            source = replace_once(source,
                f"\tif (mnt->mnt_id < DEFAULT_KSU_MNT_ID)\n\t\treturn mnt->{field};\n\n", "")
        source = replace_once(source,
            "\tif (mnt->mnt_id < DEFAULT_KSU_MNT_ID) {\n"
            "\t\tmntget(&mnt->mnt);\n\t\tdget(mnt->mnt.mnt_root);\n"
            "\t\treturn &mnt->mnt;\n\t}\n\n", "")
        # Keep declarations apart from statements, as in the reviewed correction.
        source = replace_once(source, "\tbool is_mnt_ksu_unshared = false;\n\n",
            "\tbool is_mnt_ksu_unshared = false;\n#endif\n\n"
            "#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT\n")
    elif path == "mm/memory.c":
        source = fix_remote_memory(source)
    elif path == "fs/namei.c":
        # Upstream already supplies nested filename_lookup and old_name restore.
        # Only place the saved name alongside the saved dfd; do not replay a fix.
        source = replace_once(source,
            "\tstruct filename *fake_filename = NULL;\n\tstruct filename *old_name = nd->name;",
            "\tstruct filename *fake_filename = NULL;")
        start = source.index("static struct file *path_openat(")
        source = source[:start] + replace_once(source[start:],
            "\tint old_dfd = nd->dfd;",
            "\tint old_dfd = nd->dfd;\n\tstruct filename *old_name = nd->name;")
    elif path == "fs/proc/task_mmu.c":
        source = fix_task_mmu(source, gki=True)
        # Retain the clean target's separation before mapping device accounting.
        source = replace_once(source,
            "#endif // #ifdef CONFIG_KSU_SUSFS_SUS_MAP\n\t\tdev = inode->i_sb->s_dev;",
            "#endif // #ifdef CONFIG_KSU_SUSFS_SUS_MAP\n\n\t\tdev = inode->i_sb->s_dev;")
    elif path == "fs/super.c":
        # File-scope SuSFS declarations belong with the other integration includes.
        block = ("#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT\n"
                 "extern bool susfs_is_current_ksu_domain(void);\n"
                 "extern struct static_key_true susfs_is_sdcard_android_data_not_decrypted;\n"
                 "#endif // #ifdef CONFIG_KSU_SUSFS_SUS_MOUNT\n\n")
        source = replace_once(source, block, "")
        source = replace_once(source, '#include "internal.h"\n\n',
                              '#include "internal.h"\n\n' + block)
    return source


def reconstruct_postimages(upstream_input: Path, root: Path):
    baseline = json.loads((root / "patches/gki-android16-6.12/BASELINE.json").read_text())
    state = json.loads((root / ".github/upstream-state.json").read_text())[
        "sources"]["authoritative"]["susfs_gki"]
    if baseline["susfs"]["resolved_commit"] != state["commit"]:
        raise ValueError("GKI accepted source identities disagree")
    name = baseline["susfs"]["patch_50"]
    paths = [upstream_input] if upstream_input.is_file() else [
        upstream_input / "kernel_patches" / name, upstream_input / name]
    path = next((p for p in paths if p.is_file()), None)
    if path is None or path.name != name:
        raise ValueError("required GKI Patch 50 missing or wrong input name")
    raw = path.read_bytes()
    expected = state["tracked_files"]["kernel_patches/" + name].removeprefix("sha256:")
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("unreviewed GKI Patch 50 content")
    # Accepted Git commit object authenticates its own timestamp, independent of 51.
    commit = (root / ".github/fixtures/r38/susfs-source-commit.txt").read_bytes()
    if hashlib.sha1(b"commit " + str(len(commit)).encode() + b"\0" + commit).hexdigest() != state["commit"]:
        raise ValueError("GKI source commit metadata identity mismatch")
    committer = next(line for line in commit.split(b"\n\n", 1)[0].splitlines()
                     if line.startswith(b"committer "))
    date = format_datetime(datetime.fromtimestamp(int(committer.rsplit(b" ", 2)[1]), timezone.utc))

    context = json.loads((root / ".github/fixtures/v2/r38-sources.json").read_text())
    target = baseline["metadata"]["compatibility_patches"]["gki-android16-6.12-r38"]
    if any(context[key] != target[key] for key in ("archive_url", "archive_sha256")):
        raise ValueError("r38 archive identities disagree")
    before = r38_sources(root)
    if not set(FILES) <= before.keys():
        raise ValueError("required r38 source context missing")
    upstream = {f.old_path.removeprefix("a/"): f for f in parse_patch(raw.decode()).files}
    after = {}
    for path in FILES:
        file = upstream[path]
        # Apply the complete authoritative change first. Ownership is a source
        # decision, never a decision to discard an entire mixed diff hunk.
        from .patch51_source import remove_transport
        source = remove_transport(path, _apply_retained(before[path], file), gki=True)
        after[path] = _adapt(path, source)
    return {p: before[p] for p in after}, after, date, target['apply_target']


def reconstruct(upstream_input: Path, root: Path) -> str:
    from .patch51_source import generate
    return generate("gki-android16-6.12-r38-patch51", upstream_input, root)[0]
