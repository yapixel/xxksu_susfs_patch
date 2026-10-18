"""Target adapter for GKI Android 16 / 6.12 r38 Patch 51.

Target preimages are clean archive members, not reverse-applied Patch 51 hunks.
An input change needs review before this bounded transformation will accept it.
"""
import copy
import json
from pathlib import Path

from .lifecycle import r38_sources, replace_once, fix_namespace, fix_task_mmu, fix_remote_memory
from .patch51_source import (
    KERNEL_FILES, apply_retained, generate, reconstruct_postimages as shared_reconstruct
)

FILES = KERNEL_FILES
_apply_retained = apply_retained


def _adapt_upstream_retained(path: str, source: str, diff_file) -> str:
    """Target-specific adaptation for upstream Patch 50 hunks on GKI 6.12 r38."""
    if path == "fs/proc/base.c":
        diff_file = copy.deepcopy(diff_file)
        diff_file.hunks[0].lines = [l for l in diff_file.hunks[0].lines if l.text != "#include <linux/dma-buf.h>"]
        diff_file.hunks[0].old_count -= 1
        return _apply_retained(source, diff_file)
    elif path == "fs/proc/task_mmu.c":
        diff_file = copy.deepcopy(diff_file)
        diff_file.hunks = [diff_file.hunks[i] for i in (0, 1, 2, 6, 7)]
        src = _apply_retained(source, diff_file)
        smap_hook = ("#ifdef CONFIG_KSU_SUSFS_SUS_MAP\n"
                     "\tif (vma->vm_file) {\n"
                     "\t\tif (SUSFS_IS_INODE_SUS_MAP(file_inode(vma->vm_file)))\n"
                     "\t\t\treturn 0;\n"
                     "\t}\n"
                     "#endif // #ifdef CONFIG_KSU_SUSFS_SUS_MAP\n\n")
        src = replace_once(src, "\tif (!vma_pages(vma))\n\t\tgoto show_pad;\n",
                           smap_hook + "\tif (!vma_pages(vma))\n\t\tgoto show_pad;\n")
        old_rollup1 = ("\tdo {\n"
                       "\t\tsmap_gather_stats(vma, &mss, 0);\n"
                       "\t\tlast_vma_end = vma->vm_end;\n")
        new_rollup1 = ("\tdo {\n"
                       "#ifdef CONFIG_KSU_SUSFS_SUS_MAP\n"
                       "\t\tif (vma->vm_file && SUSFS_IS_INODE_SUS_MAP(file_inode(vma->vm_file)))\n"
                       "\t\t\tgoto bypass_orig_flow;\n"
                       "#endif // #ifdef CONFIG_KSU_SUSFS_SUS_MAP\n"
                       "\t\tsmap_gather_stats(vma, &mss, 0);\n"
                       "#ifdef CONFIG_KSU_SUSFS_SUS_MAP\n"
                       "bypass_orig_flow:\n"
                       "#endif // #ifdef CONFIG_KSU_SUSFS_SUS_MAP\n"
                       "\t\tlast_vma_end = vma->vm_end;\n")
        src = replace_once(src, old_rollup1, new_rollup1)
        old_rollup2 = ("\t\t\tif (vma->vm_end > last_vma_end) {\n"
                       "\t\t\t\tsmap_gather_stats(vma, &mss, last_vma_end);\n"
                       "\t\t\t\tlast_vma_end = vma->vm_end;\n"
                       "\t\t\t}\n")
        new_rollup2 = ("\t\t\tif (vma->vm_end > last_vma_end) {\n"
                       "#ifdef CONFIG_KSU_SUSFS_SUS_MAP\n"
                       "\t\t\t\tif (!vma->vm_file || !(SUSFS_IS_INODE_SUS_MAP(file_inode(vma->vm_file)))) {\n"
                       "\t\t\t\t\tsmap_gather_stats(vma, &mss, last_vma_end);\n"
                       "\t\t\t\t\tlast_vma_end = vma->vm_end;\n"
                       "\t\t\t\t}\n"
                       "#else\n"
                       "\t\t\t\tsmap_gather_stats(vma, &mss, last_vma_end);\n"
                       "\t\t\t\tlast_vma_end = vma->vm_end;\n"
                       "#endif // #ifdef CONFIG_KSU_SUSFS_SUS_MAP\n"
                       "\t\t\t}\n")
        src = replace_once(src, old_rollup2, new_rollup2)
        return src
    return _apply_retained(source, diff_file)


def _adapt(path: str, source: str) -> str:
    """Target-specific source, API, placement, and lifecycle corrections for GKI 6.12 r38."""
    if path == "fs/namei.c":
        source = replace_once(source,
            "\tstruct filename *fake_filename = NULL;\n\tstruct filename *old_name = nd->name;",
            "\tstruct filename *fake_filename = NULL;")
        start = source.index("static struct file *path_openat(")
        source = source[:start] + replace_once(source[start:],
            "\tint old_dfd = nd->dfd;",
            "\tint old_dfd = nd->dfd;\n\tstruct filename *old_name = nd->name;")
    elif path == "fs/namespace.c":
        source = fix_namespace(source)
        source = replace_once(source, "\tbool is_mnt_ksu_unshared = false;\n\n",
            "\tbool is_mnt_ksu_unshared = false;\n#endif\n\n"
            "#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT\n")
    elif path == "fs/proc/task_mmu.c":
        source = fix_task_mmu(source, gki=True)
        source = replace_once(source,
            "#endif // #ifdef CONFIG_KSU_SUSFS_SUS_MAP\n\t\tdev = inode->i_sb->s_dev;",
            "#endif // #ifdef CONFIG_KSU_SUSFS_SUS_MAP\n\n\t\tdev = inode->i_sb->s_dev;")
    elif path == "fs/super.c":
        block = ("#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT\n"
                 "extern bool susfs_is_current_ksu_domain(void);\n"
                 "extern struct static_key_true susfs_is_sdcard_android_data_not_decrypted;\n"
                 "#endif // #ifdef CONFIG_KSU_SUSFS_SUS_MOUNT\n\n")
        source = replace_once(source, block, "")
        source = replace_once(source, '#include "internal.h"\n\n',
                              '#include "internal.h"\n\n' + block)
    elif path == "mm/memory.c":
        source = fix_remote_memory(source)
    return source


class GkiR38Patch51Adapter:
    """Target adapter for GKI Android 16 / Linux 6.12 r38 Patch 51."""
    target_id = "gki-android16-6.12-r38"
    patch_id = "gki-android16-6.12-r38-patch51"
    target_dir = "gki-android16-6.12"
    source_state_key = "susfs_gki"
    commit_fixture_relpath = Path(".github/fixtures/r38/susfs-source-commit.txt")

    def load_preimages(self, root: Path, baseline: dict) -> dict[str, str]:
        context = json.loads((root / ".github/fixtures/v2/r38-sources.json").read_text())
        target = baseline["metadata"]["compatibility_patches"]["gki-android16-6.12-r38"]
        if any(context[k] != target[k] for k in ("archive_url", "archive_sha256")):
            raise ValueError("r38 archive identities disagree")
        before = r38_sources(root)
        if not set(KERNEL_FILES) <= before.keys():
            raise ValueError("required r38 source context missing")
        return before

    def apply_retained(self, path: str, source: str, diff_file) -> str:
        return _adapt_upstream_retained(path, source, diff_file)

    def apply_target_adaptation(self, path: str, source: str) -> str:
        return _adapt(path, source)

    def extra_postimages(self, root: Path, before: dict[str, str]) -> dict[str, str]:
        return {}

    def apply_target_name(self, baseline: dict) -> str:
        return baseline["metadata"]["compatibility_patches"]["gki-android16-6.12-r38"]["apply_target"]


def reconstruct_postimages(upstream_input: Path, root: Path):
    return shared_reconstruct("gki-android16-6.12-r38-patch51", upstream_input, root)


def reconstruct(upstream_input: Path, root: Path) -> str:
    return generate("gki-android16-6.12-r38-patch51", upstream_input, root)[0]
