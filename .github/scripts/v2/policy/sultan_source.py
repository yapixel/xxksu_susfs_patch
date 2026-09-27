"""Reviewed Sultan core adaptations, expressed as complete source replacements.

These rules are migrated from the existing SULTAN_EXTRA_CHUNKS policy. They
preserve the accepted postimages; no final Patch 51 supplies their content.
"""
from pathlib import Path
from .lifecycle import replace_once, fix_namespace, fix_task_mmu, fix_remote_memory
from ..source.baseline import load_authoritative_bundle

CORE_REPLACEMENTS = {
    'fs/susfs.c': (
        ('#include <linux/susfs.h>\n#include "fuse/fuse_i.h"\n#include "mount.h"\n\nextern bool susfs_is_current_ksu_domain(void);\nextern void setup_selinux(const char *domain, struct cred *cred);\n',
         '#include <linux/susfs.h>\n#include "fuse/fuse_i.h"\n#include "mount.h"\n#include <uapi/linux/magic.h>\n\nextern bool susfs_is_current_ksu_domain(void);\nextern void setup_selinux(const char *domain, struct cred *cred);\n'),
        ('\tSUSFS_LOGI("CMD_SUSFS_ADD_SUS_PATH_LOOP -> ret: %d\\n", info.err);\n}\n\nstatic void susfs_run_sus_path_loop(void) {\n\tstruct st_susfs_sus_path_list *cursor = NULL;\n\tstruct path path;\n\tstruct inode *inode;\n',
         '\tSUSFS_LOGI("CMD_SUSFS_ADD_SUS_PATH_LOOP -> ret: %d\\n", info.err);\n}\n\nvoid susfs_run_sus_path_loop(void) {\n\tstruct st_susfs_sus_path_list *cursor = NULL;\n\tstruct path path;\n\tstruct inode *inode;\n'),
        ('}\n#endif // #ifdef CONFIG_KSU_SUSFS_SUS_KSTAT\n\n/* spoof_uname */\n#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME\nstatic struct st_susfs_uname my_uname = {0};\n',
         '}\n#endif // #ifdef CONFIG_KSU_SUSFS_SUS_KSTAT\n\n/* try_umount */\n#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT\nstatic DEFINE_SPINLOCK(susfs_spin_lock_try_umount);\nextern void try_umount(const char *mnt, int flags);\nstatic LIST_HEAD(LH_TRY_UMOUNT_PATH);\nvoid susfs_add_try_umount(void __user **user_info) {\n\tstruct st_susfs_try_umount info = {0};\n\tstruct st_susfs_try_umount_list *new_list = NULL;\n\n\tif (copy_from_user(&info, (struct st_susfs_try_umount __user*)*user_info, sizeof(info))) {\n\t\tinfo.err = -EFAULT;\n\t\tgoto out_copy_to_user;\n\t}\n\n\tif (info.mnt_mode == TRY_UMOUNT_DEFAULT) {\n\t\tinfo.mnt_mode = 0;\n\t} else if (info.mnt_mode == TRY_UMOUNT_DETACH) {\n\t\tinfo.mnt_mode = MNT_DETACH;\n\t} else {\n\t\tSUSFS_LOGE("Unsupported mnt_mode: %d\\n", info.mnt_mode);\n\t\tinfo.err = -EINVAL;\n\t\tgoto out_copy_to_user;\n\t}\n\n\tnew_list = kzalloc(sizeof(struct st_susfs_try_umount_list), GFP_KERNEL);\n\tif (!new_list) {\n\t\tinfo.err = -ENOMEM;\n\t\tgoto out_copy_to_user;\n\t}\n\n\tmemcpy(&new_list->info, &info, sizeof(info));\n\n\tINIT_LIST_HEAD(&new_list->list);\n\tspin_lock(&susfs_spin_lock_try_umount);\n\tlist_add_tail(&new_list->list, &LH_TRY_UMOUNT_PATH);\n\tspin_unlock(&susfs_spin_lock_try_umount);\n\tSUSFS_LOGI("target_pathname: \'%s\', umount options: %d, is successfully added to LH_TRY_UMOUNT_PATH\\n", new_list->info.target_pathname, new_list->info.mnt_mode);\n\tinfo.err = 0;\nout_copy_to_user:\n\tif (copy_to_user(&((struct st_susfs_try_umount __user*)*user_info)->err, &info.err, sizeof(info.err))) {\n\t\tinfo.err = -EFAULT;\n\t}\n\tSUSFS_LOGI("CMD_SUSFS_ADD_TRY_UMOUNT -> ret: %d\\n", info.err);\n}\n\nvoid susfs_try_umount(uid_t uid) {\n\tstruct st_susfs_try_umount_list *cursor = NULL;\n\n\t// We should umount in reversed order\n\tlist_for_each_entry_reverse(cursor, &LH_TRY_UMOUNT_PATH, list) {\n\t\tSUSFS_LOGI("umounting \'%s\' for uid: %u\\n", cursor->info.target_pathname, uid);\n\t\ttry_umount(cursor->info.target_pathname, cursor->info.mnt_mode);\n\t}\n}\n#endif // #ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT\n\n/* spoof_uname */\n#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME\nstatic struct st_susfs_uname my_uname = {0};\n'),
        ('\tif (info->err) goto out_copy_to_user;\n\tbuf_ptr = info->enabled_features + copied_size;\n#endif\n#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME\n\tinfo->err = copy_config_to_buf("CONFIG_KSU_SUSFS_SPOOF_UNAME\\n", buf_ptr, &copied_size, SUSFS_ENABLED_FEATURES_SIZE);\n\tif (info->err) goto out_copy_to_user;\n',
         '\tif (info->err) goto out_copy_to_user;\n\tbuf_ptr = info->enabled_features + copied_size;\n#endif\n#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT\n\tinfo->err = copy_config_to_buf("CONFIG_KSU_SUSFS_TRY_UMOUNT\\n", buf_ptr, &copied_size, SUSFS_ENABLED_FEATURES_SIZE);\n\tif (info->err) goto out_copy_to_user;\n\tbuf_ptr = info->enabled_features + copied_size;\n#endif\n#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME\n\tinfo->err = copy_config_to_buf("CONFIG_KSU_SUSFS_SPOOF_UNAME\\n", buf_ptr, &copied_size, SUSFS_ENABLED_FEATURES_SIZE);\n\tif (info->err) goto out_copy_to_user;\n'),
    ),
    'include/linux/susfs.h': (
        ('};\n#endif\n\n/* spoof_uname */\n#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME\nstruct st_susfs_uname {\n',
         '};\n#endif\n\n/* try_umount */\n#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT\nstruct st_susfs_try_umount {\n\tchar                                    target_pathname[SUSFS_MAX_LEN_PATHNAME];\n\tint                                     mnt_mode;\n\tint                                     err;\n};\n\nstruct st_susfs_try_umount_list {\n\tstruct list_head                        list;\n\tstruct st_susfs_try_umount              info;\n};\n#endif\n\n/* spoof_uname */\n#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME\nstruct st_susfs_uname {\n'),
        ('void susfs_update_sus_kstat(void __user **user_info);\n#endif\n\n/* spoof_uname */\n#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME\nvoid susfs_set_uname(void __user **user_info);\n',
         'void susfs_update_sus_kstat(void __user **user_info);\n#endif\n\n/* try_umount */\n#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT\nvoid susfs_add_try_umount(void __user **user_info);\nvoid susfs_try_umount(uid_t uid);\n#endif // #ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT\n\n/* spoof_uname */\n#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME\nvoid susfs_set_uname(void __user **user_info);\n'),
    ),
}

def adapt_core(path, source):
    for before, after in CORE_REPLACEMENTS[path]:
        source = replace_once(source, before, after)
    return source


class SultanPatch51Adapter:
    """Target adapter for Sultan Android 14 / Linux 6.1 Patch 51."""
    target_id = "sultan-android14-6.1"
    patch_id = "sultan-android14-6.1-patch51"
    target_dir = "sultan-android14-6.1"
    source_state_key = "susfs_sultan"
    commit_fixture_relpath = Path(".github/fixtures/sultan/susfs-source-commit.txt")

    def load_preimages(self, root: Path, baseline: dict) -> dict[str, str]:
        bundle = load_authoritative_bundle(self.target_dir, root)
        return {f.path: f.content for f in bundle.files}

    def apply_target_adaptation(self, path: str, source: str) -> str:
        if path == "fs/namespace.c":
            source = fix_namespace(source)
        elif path == "fs/proc/task_mmu.c":
            source = fix_task_mmu(source, gki=False)
        elif path == "mm/memory.c":
            source = fix_remote_memory(source)
        return source

    def extra_postimages(self, root: Path, before: dict[str, str]) -> dict[str, str]:
        extra = {}
        for path in CORE_REPLACEMENTS:
            extra[path] = adapt_core(path, before[path])
        return extra

    def apply_target_name(self, baseline: dict) -> str:
        return self.target_id
