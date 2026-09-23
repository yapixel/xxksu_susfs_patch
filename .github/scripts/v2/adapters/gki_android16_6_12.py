"""GKI Android 16 / Linux 6.12 target adapter."""

from __future__ import annotations

from typing import Mapping

from .base import AnchorLocation, AnchorSpec, MissingSemanticAnchor, TargetAdapter


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
            anchor_text="idmap = mnt_idmap(",
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
            anchor_text="return call_int_hook(bprm_check_security, bprm);",
            function="security_bprm_check",
        ),
    }

    _FIXTURE_ANCHORS: Mapping[str, AnchorSpec] = {
        "manual.security.decl": AnchorSpec(
            file_path="security/security.c",
            anchor_text="#include <linux/lsm_hook_defs.h>",
            context_before=(
                "#define LSM_HOOK(RET, DEFAULT, NAME, ...) \\",
                "\tDECLARE_LSM_RET_DEFAULT_##RET(DEFAULT, NAME)",
            ),
        ),
        "manual.security.bprm": AnchorSpec(
            file_path="security/security.c",
            anchor_text="return call_int_hook(bprm_check_security, bprm);",
            function="security_bprm_check",
        ),
        "manual.security.file_permission": AnchorSpec(
            file_path="security/security.c",
            anchor_text="return call_int_hook(file_permission, file, mask);",
            function="security_file_permission",
        ),
        "manual.security.setuid": AnchorSpec(
            file_path="security/security.c",
            anchor_text="return call_int_hook(task_fix_setuid, new, old, flags);",
            function="security_task_fix_setuid",
        ),
        "manual.security.setprocattr": AnchorSpec(
            file_path="security/security.c",
            anchor_text="lsm_for_each_hook(scall, setprocattr) {",
            function="security_setprocattr",
        ),
    }

    _FALLBACK_FIXTURE_ANCHORS: Mapping[str, AnchorSpec] = {
        "manual.security.bprm": AnchorSpec(
            file_path="security/security.c",
            anchor_text="int ret;",
            function="security_bprm_check",
        ),
        "manual.security.file_permission": AnchorSpec(
            file_path="security/security.c",
            anchor_text="ret = call_int_hook(file_permission, 0, file, mask);",
            function="security_file_permission",
        ),
        "manual.security.setuid": AnchorSpec(
            file_path="security/security.c",
            anchor_text="return call_int_hook(task_fix_setuid, 0, new, old, flags);",
            function="security_task_fix_setuid",
        ),
        "manual.security.setprocattr": AnchorSpec(
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

    def get_fixture_anchor_spec(self, fixture_name: str, operation_id: str) -> AnchorSpec | None:
        return self._FIXTURE_ANCHORS.get(operation_id)

    def locate_anchor(
        self,
        source_text: str,
        anchor: str | AnchorSpec,
        *,
        file_path: str | None = None,
        function: str | None = None,
    ) -> AnchorLocation:
        try:
            return super().locate_anchor(source_text, anchor, file_path=file_path, function=function)
        except MissingSemanticAnchor as exc:
            if isinstance(anchor, AnchorSpec):
                if anchor.anchor_text == "#include <linux/lsm_hook_defs.h>" and anchor.context_before:
                    fallback_decl = AnchorSpec(file_path=anchor.file_path, anchor_text=anchor.anchor_text)
                    try:
                        return super().locate_anchor(source_text, fallback_decl, file_path=file_path, function=function)
                    except Exception:
                        pass
                for fb in self._FALLBACK_FIXTURE_ANCHORS.values():
                    if anchor.function and anchor.function == fb.function:
                        try:
                            return super().locate_anchor(source_text, fb, file_path=file_path, function=function)
                        except Exception:
                            continue
            raise exc
