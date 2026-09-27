"""Shared Patch 51 generation engine: authoritative Simonpunk Patch 50 -> complete source postimages -> native Git diff."""
from datetime import datetime, timezone
from email.utils import format_datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Protocol

from .lifecycle import replace_once
from ..engine.diff_parser import parse_patch
from ..model.patch import AddedLine, RemovedLine

# Shared kernel files modified across all target families
KERNEL_FILES = (
    "fs/Makefile", "fs/namei.c", "fs/namespace.c", "fs/notify/fdinfo.c",
    "fs/proc/base.c", "fs/proc/bootconfig.c", "fs/proc/fd.c",
    "fs/proc/task_mmu.c", "fs/proc_namespace.c", "fs/readdir.c",
    "fs/stat.c", "fs/statfs.c", "fs/super.c", "kernel/kallsyms.c",
    "kernel/sys.c", "mm/memory.c",
)
FILES = KERNEL_FILES

# Obsolete KSU transport definitions to decompose in mixed-ownership files
DECLARATIONS = """#ifdef CONFIG_KSU_SUSFS
extern struct static_key_true ksu_is_init_rc_hook_enabled;
extern void ksu_handle_vfs_fstat(int fd, loff_t *kstat_size_ptr);
extern struct static_key_true ksu_su_compat_enabled;
extern bool __ksu_is_allow_uid_for_current(uid_t uid);
extern int ksu_handle_stat(int *dfd, struct filename **filename, int *flags);
#endif // #ifdef CONFIG_KSU_SUSFS
"""

FSTAT = """#ifdef CONFIG_KSU_SUSFS
\tif (static_branch_unlikely(&ksu_is_init_rc_hook_enabled))
\t\tksu_handle_vfs_fstat(fd, &stat->size);
#endif // #ifdef CONFIG_KSU_SUSFS
"""

STAT = """#ifdef CONFIG_KSU_SUSFS
\tif (likely(susfs_is_current_proc_no_su()))
\t\tgoto orig_flow;

\tif (static_branch_likely(&ksu_su_compat_enabled)) {
\t\tif (unlikely(__ksu_is_allow_uid_for_current(current_uid().val)))
\t\t\tksu_handle_stat(&dfd, &filename, &flags);
\t}

orig_flow:
#endif
"""

SETRESUID_DECL = """#ifdef CONFIG_KSU_SUSFS
extern int ksu_handle_setresuid(uid_t ruid, uid_t euid, uid_t suid);
#endif
"""

SETRESUID_CALL = """#ifdef CONFIG_KSU_SUSFS
\t(void)ksu_handle_setresuid(ruid, euid, suid);
#endif
"""

# Reviewed Simonpunk Patch 50 file ownership classification
REMOVE_FILES = frozenset({
    "drivers/input/input.c",
    "fs/exec.c",
    "fs/open.c",
    "fs/read_write.c",
    "kernel/reboot.c",
    "security/selinux/avc.c",
    "security/selinux/hooks.c",
    "security/selinux/selinuxfs.c",
    "security/selinux/ss/services.c",
})

MIXED_FILES = frozenset({
    "fs/stat.c",
    "kernel/sys.c",
})

KEEP_FILES = frozenset(KERNEL_FILES) - MIXED_FILES


def apply_retained(source: str, file) -> str:
    """Apply Patch 50 hunks cleanly to target source; no fuzz or offsets."""
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
                raise ValueError(f"unreviewed target context: {file.old_path}:{hunk.old_start}")
            at = matches[0]
        if at < cursor:
            raise ValueError(f"overlapping target contexts: {file.old_path}")
        output.extend(lines[cursor:at] + after)
        cursor = at + len(before)
    return "\n".join(output + lines[cursor:]) + "\n"


_apply_retained = apply_retained


def decompose_mixed_ownership(path: str, source: str) -> str:
    """Explicitly decompose mixed SuSFS + obsolete-KSU content at source level.
    Fails closed if any transport block is missing or unexpected.
    """
    if path == "fs/stat.c":
        source = replace_once(source, DECLARATIONS, "")
        if FSTAT in source:
            source = replace_once(source, FSTAT, "")
        if (STAT + "\n") in source:
            source = replace_once(source, STAT + "\n", "")
        elif STAT in source:
            source = replace_once(source, STAT, "")
    elif path == "kernel/sys.c":
        source = replace_once(source, SETRESUID_DECL, "")
        source = replace_once(source, SETRESUID_CALL + "\n", "")
    else:
        raise ValueError(f"unsupported mixed-ownership path: {path}")
    return source


def remove_transport(path: str, source: str, *, gki: bool = False) -> str:
    """Compatibility wrapper for mixed-ownership transport decomposition."""
    return decompose_mixed_ownership(path, source)


def source_commit_date(commit_bytes: bytes, expected_commit: str) -> str:
    """Authenticate raw git commit object and derive RFC 2822 UTC timestamp."""
    git_sha1 = hashlib.sha1(b"commit " + str(len(commit_bytes)).encode() + b"\0" + commit_bytes).hexdigest()
    if git_sha1 != expected_commit:
        raise ValueError("source commit metadata identity mismatch")
    header = commit_bytes.split(b"\n\n", 1)[0]
    committer = next((line for line in header.splitlines() if line.startswith(b"committer ")), None)
    if not committer:
        raise ValueError("committer line missing from commit object")
    timestamp = int(committer.split()[-2])
    return format_datetime(datetime.fromtimestamp(timestamp, tz=timezone.utc))


class Patch51TargetAdapter(Protocol):
    target_id: str
    patch_id: str
    target_dir: str
    source_state_key: str
    commit_fixture_relpath: Path

    def load_preimages(self, root: Path, baseline: dict) -> dict[str, str]: ...
    def apply_target_adaptation(self, path: str, source: str) -> str: ...
    def extra_postimages(self, root: Path, before: dict[str, str]) -> dict[str, str]: ...
    def apply_target_name(self, baseline: dict) -> str: ...


def get_adapter(patch_id: str) -> Patch51TargetAdapter:
    if patch_id == "sultan-android14-6.1-patch51":
        from .sultan_source import SultanPatch51Adapter
        return SultanPatch51Adapter()
    elif patch_id == "gki-android16-6.12-r38-patch51":
        from .gki_r38 import GkiR38Patch51Adapter
        return GkiR38Patch51Adapter()
    raise ValueError(f"unsupported Patch 51 target: {patch_id}")


def reconstruct_postimages(patch_id: str, upstream_input: Path, root: Path):
    """Shared Patch 51 generation engine: orchestrates preimages, Patch 50
    interpretation, shared ownership decisions, target adaptation, and postimages.
    """
    adapter = get_adapter(patch_id)

    baseline_path = root / "patches" / adapter.target_dir / "BASELINE.json"
    baseline = json.loads(baseline_path.read_text())
    state = json.loads((root / ".github/upstream-state.json").read_text())[
        "sources"]["authoritative"][adapter.source_state_key]

    if state["commit"] != baseline["susfs"]["resolved_commit"]:
        raise ValueError(f"{adapter.target_id} accepted identities disagree")

    patch_50_name = baseline["susfs"]["patch_50"]
    candidate_paths = [upstream_input] if upstream_input.is_file() else [
        upstream_input / "kernel_patches" / patch_50_name,
        upstream_input / patch_50_name,
    ]
    patch_50_file = next((p for p in candidate_paths if p.is_file() and p.name == patch_50_name), None)
    if patch_50_file is None:
        raise ValueError(f"Upstream SuSFS 50 patch missing: {patch_50_name}")

    raw_patch_50 = patch_50_file.read_bytes()
    expected_patch_sha = state["tracked_files"]["kernel_patches/" + patch_50_name].removeprefix("sha256:")
    if hashlib.sha256(raw_patch_50).hexdigest() != expected_patch_sha:
        raise ValueError(f"unreviewed {adapter.target_id} Patch 50 content")

    commit_bytes = (root / adapter.commit_fixture_relpath).read_bytes()
    date = source_commit_date(commit_bytes, state["commit"])

    before = adapter.load_preimages(root, baseline)

    parsed_patch = parse_patch(raw_patch_50.decode())
    upstream = {f.old_path.removeprefix("a/"): f for f in parsed_patch.files}

    # Shared ownership classification and fail-closed validation of Patch 50 files
    all_reviewed = REMOVE_FILES | MIXED_FILES | KEEP_FILES
    unreviewed = set(upstream.keys()) - all_reviewed
    if unreviewed:
        raise ValueError(f"unreviewed files in Patch 50: {sorted(unreviewed)}")

    after = {}
    for path in KERNEL_FILES:
        diff_file = upstream[path]
        retained_source = apply_retained(before[path], diff_file)

        # Decompose mixed-ownership files at source level
        if path in MIXED_FILES:
            retained_source = decompose_mixed_ownership(path, retained_source)

        # Target-specific adjustments
        after[path] = adapter.apply_target_adaptation(path, retained_source)

    # Extra target postimages (e.g. Sultan core replacements)
    after.update(adapter.extra_postimages(root, before))

    return {p: before[p] for p in after}, after, date, adapter.apply_target_name(baseline)


GIT_DIFF = ("-c", "core.quotePath=false", "diff", "--no-ext-diff", "--no-textconv",
            "--no-color", "--no-renames", "--full-index")


def generate(patch_id: str, upstream_input: Path, root: Path, target_tree=None):
    """Production supplies the authenticated full target; local unit checks may
    use authenticated complete-file source snapshots. Neither reads Patch 51.
    Each call creates its own generation tree, index and source reconstruction.
    """
    before, after, date, target = reconstruct_postimages(patch_id, upstream_input, root)
    env = {**os.environ, "LC_ALL": "C", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
    with tempfile.TemporaryDirectory(prefix="patch51-git-") as tmp:
        tree = Path(tmp) / "tree"
        if target_tree is not None:
            shutil.copytree(target_tree, tree, symlinks=True,
                            ignore=shutil.ignore_patterns(".git", "out"))
            for path, content in before.items():
                if (tree / path).read_bytes() != content.encode():
                    raise ValueError(f"target preimage mismatch: {path}")
        else:
            tree.mkdir()
            for path, content in before.items():
                dest = tree / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(content.encode())
        def git(*args):
            return subprocess.check_output(["git", *args], cwd=tree, env=env)
        git("init", "-q")
        (tree / ".git/info/attributes").write_text("*.c diff=cpp\n")
        git("add", "--", *sorted(before))
        for path, content in after.items():
            (tree / path).write_bytes(content.encode())
        body = git(*GIT_DIFF, "--", *sorted(before))
        stat = git(*GIT_DIFF, "--stat=80", "--", *sorted(before))
        evidence = {p: {"preimage": hashlib.sha256(before[p].encode()).hexdigest(),
                        "postimage": hashlib.sha256(after[p].encode()).hexdigest()}
                    for p in sorted(after)}
    header = ("From: yapixel <yapixel@users.noreply.github.com>\n"
              f"Date: {date}\nSubject: [PATCH] SUSFS de-inlined hooks for {target}\n\n---\n")
    return (header.encode() + stat + b"\n" + body).decode(), evidence
