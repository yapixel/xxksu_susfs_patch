"""Complete source postimages -> native Git diff. No final-patch input."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from .lifecycle import replace_once, fix_namespace, fix_task_mmu, fix_remote_memory
from .gki_r38 import FILES, _apply_retained
from .sultan_source import adapt_core, CORE_REPLACEMENTS
from ..engine.diff_parser import parse_patch
from ..source.baseline import load_authoritative_bundle

DECLARATIONS = """#ifdef CONFIG_KSU_SUSFS
extern struct static_key_true ksu_is_init_rc_hook_enabled;
extern void ksu_handle_vfs_fstat(int fd, loff_t *kstat_size_ptr);
extern struct static_key_true ksu_su_compat_enabled;
extern bool __ksu_is_allow_uid_for_current(uid_t uid);
extern int ksu_handle_stat(int *dfd, struct filename **filename, int *flags);
#endif // #ifdef CONFIG_KSU_SUSFS
"""
# Exact source ownership rules reviewed against the accepted Patch 50. Mixed
# declarations keep their SuSFS portion; an unknown transport block fails closed.
FSTAT = """#ifdef CONFIG_KSU_SUSFS
	if (static_branch_unlikely(&ksu_is_init_rc_hook_enabled))
		ksu_handle_vfs_fstat(fd, &stat->size);
#endif // #ifdef CONFIG_KSU_SUSFS
"""
STAT = """#ifdef CONFIG_KSU_SUSFS
	if (likely(susfs_is_current_proc_no_su()))
		goto orig_flow;

	if (static_branch_likely(&ksu_su_compat_enabled)) {
		if (unlikely(__ksu_is_allow_uid_for_current(current_uid().val)))
			ksu_handle_stat(&dfd, &filename, &flags);
	}

orig_flow:
#endif
"""
SETRESUID_DECL = """#ifdef CONFIG_KSU_SUSFS
extern int ksu_handle_setresuid(uid_t ruid, uid_t euid, uid_t suid);
#endif
"""
SETRESUID_CALL = """#ifdef CONFIG_KSU_SUSFS
	(void)ksu_handle_setresuid(ruid, euid, suid);
#endif
"""


def remove_transport(path, source, *, gki):
    if path == "fs/stat.c":
        if not gki:  # GKI's existing reviewed source adapter owns this block.
            source = replace_once(source, DECLARATIONS, "")
        source = replace_once(source, FSTAT, "")
        source = replace_once(source, STAT + ("\n" if not gki else ""), "")
    elif path == "kernel/sys.c":
        source = replace_once(source, SETRESUID_DECL, "")
        source = replace_once(source, SETRESUID_CALL + "\n", "")
    return source


def reconstruct_postimages(patch_id, upstream_input, root):
    if patch_id.startswith("gki-"):
        from .gki_r38 import reconstruct_postimages as gki
        return gki(upstream_input, root)
    from ..pipeline import _sultan_source_date
    target = "sultan-android14-6.1"
    baseline = json.loads((root / "patches" / target / "BASELINE.json").read_text())
    state = json.loads((root / ".github/upstream-state.json").read_text())["sources"]["authoritative"]["susfs_sultan"]
    if state["commit"] != baseline["susfs"]["resolved_commit"]:
        raise ValueError("Sultan accepted identities disagree")
    name = baseline["susfs"]["patch_50"]
    paths = [upstream_input] if upstream_input.is_file() else [upstream_input / "kernel_patches" / name, upstream_input / name]
    file = next((p for p in paths if p.is_file() and p.name == name), None)
    if file is None:
        raise ValueError("Upstream SuSFS 50 patch missing")
    raw = file.read_bytes()
    expected = state["tracked_files"]["kernel_patches/" + name].removeprefix("sha256:")
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("unreviewed Sultan Patch 50 content")
    bundle = load_authoritative_bundle(target, root)
    before = {f.path: f.content for f in bundle.files}
    upstream = {f.old_path.removeprefix("a/"): f for f in parse_patch(raw.decode()).files}
    after = {}
    for path in FILES:
        source = remove_transport(path, _apply_retained(before[path], upstream[path]), gki=False)
        if path == "fs/namespace.c":
            source = fix_namespace(source)
        elif path == "fs/proc/task_mmu.c":
            source = fix_task_mmu(source, gki=False)
        elif path == "mm/memory.c":
            source = fix_remote_memory(source)
        after[path] = source
    for path in CORE_REPLACEMENTS:
        after[path] = adapt_core(path, before[path])
    return {p: before[p] for p in after}, after, _sultan_source_date(root), target


GIT_DIFF = ("-c", "core.quotePath=false", "diff", "--no-ext-diff", "--no-textconv",
            "--no-color", "--no-renames", "--full-index")


def generate(patch_id, upstream_input, root, target_tree=None):
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
