"""GKI Android 16 / Linux 6.12 target adapter."""

from __future__ import annotations

from typing import Mapping

from .base import AnchorSpec, TargetAdapter


class GKIAndroid16_6_12Adapter(TargetAdapter):
    target_id = "gki-android16-6.12"
    adapter_id = "gki_android16_6_12"
    supported_kernel_families = ("6.12",)

    _KNOWN_ANCHORS: Mapping[str, AnchorSpec] = {
        "namespace_include": AnchorSpec(
            file_path="fs/namespace.c",
            anchor_text='#include "internal.h"',
        ),
        "stat_idmap": AnchorSpec(
            file_path="fs/stat.c",
            anchor_text="idmap = mnt_idmap(path.mnt);",
            function="vfs_statx",
        ),
        "stat_hook": AnchorSpec(
            file_path="fs/stat.c",
            anchor_text="error = vfs_fstatat(dfd, filename, &stat, flag);",
            function="newfstatat",
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
        "reboot_hook": AnchorSpec(
            file_path="kernel/reboot.c",
            anchor_text="if (!ns_capable(pid_ns->user_ns, CAP_SYS_BOOT))",
            function="reboot",
        ),
        "security_bprm": AnchorSpec(
            file_path="security/security.c",
            anchor_text="int ret;",
            function="security_bprm_check",
        ),
    }

    def get_anchor_spec(self, key: str) -> AnchorSpec:
        try:
            return self._KNOWN_ANCHORS[key]
        except KeyError:
            raise KeyError(f"unknown anchor key {key!r} for adapter {self.adapter_id}")
