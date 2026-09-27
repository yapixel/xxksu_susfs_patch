"""Target adapter for GKI Android 16 / 6.12 r38 Patch 51.

Target preimages are clean archive members, not reverse-applied Patch 51 hunks.
An input change needs review before this bounded transformation will accept it.
"""
import json
from pathlib import Path

from .lifecycle import r38_sources, replace_once, fix_namespace, fix_task_mmu, fix_remote_memory
from .patch51_source import (
    KERNEL_FILES, apply_retained, generate, reconstruct_postimages as shared_reconstruct
)

FILES = KERNEL_FILES
_apply_retained = apply_retained


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
        for field in ("mnt_id", "mnt_id_unique"):
            source = replace_once(source,
                f"\tif (mnt->mnt_id < DEFAULT_KSU_MNT_ID)\n\t\treturn mnt->{field};\n\n", "")
        source = replace_once(source,
            "\tif (mnt->mnt_id < DEFAULT_KSU_MNT_ID) {\n"
            "\t\tmntget(&mnt->mnt);\n\t\tdget(mnt->mnt.mnt_root);\n"
            "\t\treturn &mnt->mnt;\n\t}\n\n", "")
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
