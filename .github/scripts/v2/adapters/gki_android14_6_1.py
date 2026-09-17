"""GKI Android 14 / Linux 6.1 target adapter."""

from __future__ import annotations

from typing import Mapping

from .base import AnchorSpec, TargetAdapter


class GKIAndroid14_6_1Adapter(TargetAdapter):
    target_id = "gki-android14-6.1"
    adapter_id = "gki_android14_6_1"
    supported_kernel_families = ("6.1",)

    _KNOWN_ANCHORS: Mapping[str, AnchorSpec] = {
        "namespace_include": AnchorSpec(
            file_path="fs/namespace.c",
            anchor_text='#include "internal.h"\n#include <trace/hooks/blk.h>',
        ),
        "exec_hook": AnchorSpec(
            file_path="fs/exec.c",
            anchor_text="if (IS_ERR(filename))",
            function="do_execveat_common",
        ),
        "access_hook": AnchorSpec(
            file_path="fs/open.c",
            anchor_text="return do_faccessat(dfd, filename, mode, 0);",
            function="faccessat",
        ),
        "stat_hook": AnchorSpec(
            file_path="fs/stat.c",
            anchor_text="error = vfs_fstatat(dfd, filename, &stat, flag);",
            function="newfstatat",
        ),
        "reboot_hook": AnchorSpec(
            file_path="kernel/reboot.c",
            anchor_text="if (!ns_capable(pid_ns->user_ns, CAP_SYS_BOOT))",
            function="reboot",
        ),
        "security_bprm": AnchorSpec(
            file_path="security/security.c",
            anchor_text="ret = call_int_hook(bprm_check_security, 0, bprm);",
            function="security_bprm_check",
        ),
        "security_rename": AnchorSpec(
            file_path="security/security.c",
            anchor_text="if (unlikely(IS_PRIVATE(d_backing_inode(old_dentry))",
            function="security_inode_rename",
        ),
        "security_file_perm": AnchorSpec(
            file_path="security/security.c",
            anchor_text="ret = call_int_hook(file_permission, 0, file, mask);",
            function="security_file_permission",
        ),
        "security_setuid": AnchorSpec(
            file_path="security/security.c",
            anchor_text="return call_int_hook(task_fix_setuid, 0, new, old, flags);",
            function="security_task_fix_setuid",
        ),
        "security_setprocattr": AnchorSpec(
            file_path="security/security.c",
            anchor_text="hlist_for_each_entry(hp, &security_hook_heads.setprocattr, list) {",
            function="security_setprocattr",
        ),
    }

    def get_anchor_spec(self, key: str) -> AnchorSpec:
        try:
            return self._KNOWN_ANCHORS[key]
        except KeyError:
            raise KeyError(f"unknown anchor key {key!r} for adapter {self.adapter_id}")
