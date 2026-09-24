"""Deterministic xxKSU target adapter and shared patch 11 generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Sequence, Tuple

from ..engine.emitter import emit_patch
from ..model.patch import AddedLine, ContextLine, FilePatch, Hunk, Patch, RemovedLine
from ..source.bundle import MissingBundleFile, SourceBundle
from .base import (
    AdapterError,
    AnchorConflict,
    AnchorLocation,
    AnchorSpec,
    MissingSemanticAnchor,
    MultipleSemanticAnchors,
    TargetAdapter,
    UnsupportedTarget,
)
from .fixtures import (
    AdaptationOperation,
    DuplicateAdaptationOperation,
    FixtureAdaptationPlan,
    FixtureContractViolation,
    IncompatibleFixtureTarget,
    Placement,
)

FIXTURE_PATCH11 = "11_enable_susfs_for_ksu.patch"

PATCH11_CANONICAL_FILES: Tuple[str, ...] = (
    "kernel/Kconfig",
    "kernel/downstream/ksu_hostsredirect.h",
    "kernel/feature/kernel_umount.c",
    "kernel/hook/setuid_hook.c",
    "kernel/ksu.c",
    "kernel/selinux/rules.c",
    "kernel/selinux/selinux.c",
    "kernel/selinux/selinux.h",
    "kernel/supercall/dispatch.c",
    "kernel/supercall/supercall.c",
)

PATCH11_FILE_INDEXES: Mapping[str, str] = {
    "kernel/Kconfig": "index 18b97b7..36e28e2 100644",
    "kernel/downstream/ksu_hostsredirect.h": "index 07e7ca9..c5a5ef8 100644",
    "kernel/feature/kernel_umount.c": "index 3d6eb6f..001b1f0 100644",
    "kernel/hook/setuid_hook.c": "index 9257980..c0cdcad 100644",
    "kernel/ksu.c": "index ff786d1..7441a22 100644",
    "kernel/selinux/rules.c": "index 12a7a17..9f7743f 100644",
    "kernel/selinux/selinux.c": "index 04e5ffe..e3bd796 100644",
    "kernel/selinux/selinux.h": "index cbeac55..42bdf73 100644",
    "kernel/supercall/dispatch.c": "index b1cf6b5..05e5fa9 100644",
    "kernel/supercall/supercall.c": "index 8c20793..f8a4276 100644",
}

PATCH11_PREAMBLE: Tuple[str, ...] = (
    "From 37eee69d83424bba4b2ae3d3dd38cbbbb1ef9824 Mon Sep 17 00:00:00 2001",
    "From: yapixel <yapixel@users.noreply.github.com>",
    "Date: Thu, 27 Aug 2026 14:43:32 +0000",
    "Subject: [PATCH] Enable SUSFS for backslashxx KernelSU",
    "",
    "---",
    " kernel/Kconfig                        |  98 +++++++++++++++",
    " kernel/downstream/ksu_hostsredirect.h |   4 +",
    " kernel/feature/kernel_umount.c        |  54 +++++---",
    " kernel/hook/setuid_hook.c             | 169 +++++++++++++++++++++++---",
    " kernel/ksu.c                          |   8 ++",
    " kernel/selinux/rules.c                |   7 ++",
    " kernel/selinux/selinux.c              | 103 ++++++++++++++++",
    " kernel/selinux/selinux.h              |  14 +++",
    " kernel/supercall/dispatch.c           |  24 ++++",
    " kernel/supercall/supercall.c          |  99 +++++++++++++++",
    " 10 files changed, 545 insertions(+), 35 deletions(-)",
    "",
)

PATCH11_TRAILER: Tuple[str, ...] = (
    "-- ",
    "2.55.0",
    "",
)


@dataclass(frozen=True)
class XxksuOperationSpec:
    operation_id: str
    file_path: str
    spec: AnchorSpec
    placement: Placement
    payload: str
    function: Optional[str] = None
    section_context: str = ""
    context_before_count: int = 3
    context_after_count: int = 3
    context_before_offset: int = 3
    diff_body: Optional[Tuple[Tuple[str, str], ...]] = None

    def get_diff_body(self) -> Tuple[Tuple[str, str], ...]:
        if self.diff_body is not None:
            return self.diff_body
        if self.placement in (Placement.BEFORE, Placement.AFTER):
            return tuple(("+", line) for line in self.payload.splitlines())
        if not self.payload:
            return tuple(("-", line) for line in self.spec.anchor_text.splitlines())
        anchor_lines = self.spec.anchor_text.splitlines()
        payload_lines = self.payload.splitlines()
        lines = []
        for l in anchor_lines:
            lines.append(("-", l))
        for l in payload_lines:
            lines.append(("+", l))
        return tuple(lines)

def get_patch11_operation_specs() -> Tuple[XxksuOperationSpec, ...]:
    """Return the 20 self-contained operation specifications matching patch 11 intent."""
    return (
        XxksuOperationSpec(
            operation_id='xxksu.kernel_Kconfig.hunk_0',
            file_path='kernel/Kconfig',
            spec=AnchorSpec('kernel/Kconfig', 'endmenu\n', context_before=('depends on KSU', 'default y'), context_after=()),
            placement=Placement.BEFORE,
            payload='menu "KernelSU - SUSFS"\nconfig KSU_SUSFS\n    bool "KernelSU addon - SUSFS"\n    depends on KSU\n    depends on THREAD_INFO_IN_TASK\n    default y\n    help\n        Patch and Enable SUSFS to kernel with KernelSU.\n\nconfig KSU_SUSFS_SUS_PATH\n    bool "Enable to hide suspicious path (NOT recommended)"\n    depends on KSU_SUSFS\n    default y\n    help\n        - Allow hiding the user-defined path and all its sub-paths from various system calls.\n        - Includes temp fix for the leaks of app path in /sdcard/Android/data directory.\n        - Effective only on zygote spawned user app process.\n        - Use with cautious as it may cause performance loss and will be vulnerable to side channel attacks,\n          just disable this feature if it doesn\'t work for you or you don\'t need it at all.\n\nconfig KSU_SUSFS_SUS_MOUNT\n    bool "Enable to hide suspicious mounts"\n    depends on KSU_SUSFS\n    default y\n    help\n        - Allow hiding the user-defined mount paths from /proc/self/[mounts|mountinfo|mountstat].\n        - Effective on all processes for hiding mount entries.\n        - mnt_id and mnt_group_id of the sus mount will be assigned to a much bigger number to solve the ssue of id not being contiguous.\n\nconfig KSU_SUSFS_SUS_KSTAT\n    bool "Enable to spoof suspicious kstat"\n    depends on KSU_SUSFS\n    default y\n    help\n        - Allow spoofing the kstat of user-defined file/directory.\n        - Effective only on zygote spawned user app process.\n\nconfig KSU_SUSFS_TRY_UMOUNT\n\tbool "Enable to use ksu\'s try_umount"\n\tdepends on KSU_SUSFS\n\tdefault n\n\thelp\n\t\t- Allow using try_umount to umount other user-defined mount paths prior to ksu\'s default umount paths.\n\t\t- Effective only on zygote spawned umounted user app process.\n\nconfig KSU_SUSFS_SPOOF_UNAME\n    bool "Enable to spoof uname"\n    depends on KSU_SUSFS\n    default y\n    help\n        - Allow spoofing the string returned by uname syscall to user-defined string.\n        - Effective on all processes.\n\nconfig KSU_SUSFS_ENABLE_LOG\n    bool "Enable logging susfs log to kernel"\n    depends on KSU_SUSFS\n    default y\n    help\n        - Allow logging susfs log to kernel, uncheck it to completely disable all susfs log.\n\nconfig KSU_SUSFS_HIDE_KSU_SUSFS_SYMBOLS\n    bool "Enable to automatically hide ksu and susfs symbols from /proc/kallsyms"\n    depends on KSU_SUSFS\n    default y\n    help\n        - Automatically hide ksu and susfs symbols from \'/proc/kallsyms\'.\n        - Effective on all processes.\n\nconfig KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG\n    bool "Enable to spoof /proc/bootconfig (gki) or /proc/cmdline (non-gki)"\n    depends on KSU_SUSFS\n    default y\n    help\n        - Spoof the output of /proc/bootconfig (gki) or /proc/cmdline (non-gki) with a user-defined file.\n        - Effective on all processes.\n\nconfig KSU_SUSFS_OPEN_REDIRECT\n    bool "Enable to redirect a path to be opened with another path (experimental)"\n    depends on KSU_SUSFS\n    default y\n    help\n        - Allow redirecting a target path to be opened with another user-defined path.\n        - Effective only on processes with uid < 2000.\n        - Please be reminded that process with open access to the target and redirected path can be detected.\n\nconfig KSU_SUSFS_SUS_MAP\n    bool "Enable to hide some mmapped real file from different proc maps interfaces"\n    depends on KSU_SUSFS\n    default y\n    help\n        - Allow hiding mmapped real file from /proc/<pid>/[maps|smaps|smaps_rollup|map_files|mem|pagemap]\n        - It does NOT support hiding for anon memory.\n        - It does NOT hide any inline hooks or plt hooks cause by the injected library itself.\n        - It may not be able to evade detections by apps that implement a good injection detection.\n        - Effective only on zygote spawned umounted user app process.\n\nendmenu\n\n',
            section_context='config KSU_HEURISTIC_IN_TREE_BUILD',
            context_before_count=3,
            context_after_count=1,
            context_before_offset=3,
            diff_body=(('+', 'menu "KernelSU - SUSFS"'), ('+', 'config KSU_SUSFS'), ('+', '    bool "KernelSU addon - SUSFS"'), ('+', '    depends on KSU'), ('+', '    depends on THREAD_INFO_IN_TASK'), ('+', '    default y'), ('+', '    help'), ('+', '        Patch and Enable SUSFS to kernel with KernelSU.'), ('+', ''), ('+', 'config KSU_SUSFS_SUS_PATH'), ('+', '    bool "Enable to hide suspicious path (NOT recommended)"'), ('+', '    depends on KSU_SUSFS'), ('+', '    default y'), ('+', '    help'), ('+', '        - Allow hiding the user-defined path and all its sub-paths from various system calls.'), ('+', '        - Includes temp fix for the leaks of app path in /sdcard/Android/data directory.'), ('+', '        - Effective only on zygote spawned user app process.'), ('+', '        - Use with cautious as it may cause performance loss and will be vulnerable to side channel attacks,'), ('+', "          just disable this feature if it doesn't work for you or you don't need it at all."), ('+', ''), ('+', 'config KSU_SUSFS_SUS_MOUNT'), ('+', '    bool "Enable to hide suspicious mounts"'), ('+', '    depends on KSU_SUSFS'), ('+', '    default y'), ('+', '    help'), ('+', '        - Allow hiding the user-defined mount paths from /proc/self/[mounts|mountinfo|mountstat].'), ('+', '        - Effective on all processes for hiding mount entries.'), ('+', '        - mnt_id and mnt_group_id of the sus mount will be assigned to a much bigger number to solve the ssue of id not being contiguous.'), ('+', ''), ('+', 'config KSU_SUSFS_SUS_KSTAT'), ('+', '    bool "Enable to spoof suspicious kstat"'), ('+', '    depends on KSU_SUSFS'), ('+', '    default y'), ('+', '    help'), ('+', '        - Allow spoofing the kstat of user-defined file/directory.'), ('+', '        - Effective only on zygote spawned user app process.'), ('+', ''), ('+', 'config KSU_SUSFS_TRY_UMOUNT'), ('+', '\tbool "Enable to use ksu\'s try_umount"'), ('+', '\tdepends on KSU_SUSFS'), ('+', '\tdefault n'), ('+', '\thelp'), ('+', "\t\t- Allow using try_umount to umount other user-defined mount paths prior to ksu's default umount paths."), ('+', '\t\t- Effective only on zygote spawned umounted user app process.'), ('+', ''), ('+', 'config KSU_SUSFS_SPOOF_UNAME'), ('+', '    bool "Enable to spoof uname"'), ('+', '    depends on KSU_SUSFS'), ('+', '    default y'), ('+', '    help'), ('+', '        - Allow spoofing the string returned by uname syscall to user-defined string.'), ('+', '        - Effective on all processes.'), ('+', ''), ('+', 'config KSU_SUSFS_ENABLE_LOG'), ('+', '    bool "Enable logging susfs log to kernel"'), ('+', '    depends on KSU_SUSFS'), ('+', '    default y'), ('+', '    help'), ('+', '        - Allow logging susfs log to kernel, uncheck it to completely disable all susfs log.'), ('+', ''), ('+', 'config KSU_SUSFS_HIDE_KSU_SUSFS_SYMBOLS'), ('+', '    bool "Enable to automatically hide ksu and susfs symbols from /proc/kallsyms"'), ('+', '    depends on KSU_SUSFS'), ('+', '    default y'), ('+', '    help'), ('+', "        - Automatically hide ksu and susfs symbols from '/proc/kallsyms'."), ('+', '        - Effective on all processes.'), ('+', ''), ('+', 'config KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG'), ('+', '    bool "Enable to spoof /proc/bootconfig (gki) or /proc/cmdline (non-gki)"'), ('+', '    depends on KSU_SUSFS'), ('+', '    default y'), ('+', '    help'), ('+', '        - Spoof the output of /proc/bootconfig (gki) or /proc/cmdline (non-gki) with a user-defined file.'), ('+', '        - Effective on all processes.'), ('+', ''), ('+', 'config KSU_SUSFS_OPEN_REDIRECT'), ('+', '    bool "Enable to redirect a path to be opened with another path (experimental)"'), ('+', '    depends on KSU_SUSFS'), ('+', '    default y'), ('+', '    help'), ('+', '        - Allow redirecting a target path to be opened with another user-defined path.'), ('+', '        - Effective only on processes with uid < 2000.'), ('+', '        - Please be reminded that process with open access to the target and redirected path can be detected.'), ('+', ''), ('+', 'config KSU_SUSFS_SUS_MAP'), ('+', '    bool "Enable to hide some mmapped real file from different proc maps interfaces"'), ('+', '    depends on KSU_SUSFS'), ('+', '    default y'), ('+', '    help'), ('+', '        - Allow hiding mmapped real file from /proc/<pid>/[maps|smaps|smaps_rollup|map_files|mem|pagemap]'), ('+', '        - It does NOT support hiding for anon memory.'), ('+', '        - It does NOT hide any inline hooks or plt hooks cause by the injected library itself.'), ('+', '        - It may not be able to evade detections by apps that implement a good injection detection.'), ('+', '        - Effective only on zygote spawned umounted user app process.'), ('+', ''), ('+', 'endmenu'), ('+', '')),
        ),
        XxksuOperationSpec(
            operation_id='xxksu.kernel_downstream_ksu_hostsredirect_h.hunk_0',
            file_path='kernel/downstream/ksu_hostsredirect.h',
            spec=AnchorSpec('kernel/downstream/ksu_hostsredirect.h', 'static bool ksu_kernel_umount_enabled __read_mostly;\n', context_before=('#ifndef __KSU_H_HOSTSREDIRECT', '#define __KSU_H_HOSTSREDIRECT'), context_after=()),
            placement=Placement.REPLACE,
            payload='#ifndef CONFIG_KSU_SUSFS\nstatic bool ksu_kernel_umount_enabled __read_mostly;\n#else\nextern bool ksu_kernel_umount_enabled;\n#endif\n',
            section_context='',
            context_before_count=3,
            context_after_count=3,
            context_before_offset=3,
            diff_body=(('+', '#ifndef CONFIG_KSU_SUSFS'), (' ', 'static bool ksu_kernel_umount_enabled __read_mostly;'), ('+', '#else'), ('+', 'extern bool ksu_kernel_umount_enabled;'), ('+', '#endif')),
        ),
        XxksuOperationSpec(
            operation_id='xxksu.kernel_feature_kernel_umount_c.hunk_0',
            file_path='kernel/feature/kernel_umount.c',
            spec=AnchorSpec('kernel/feature/kernel_umount.c', 'static bool ksu_kernel_umount_enabled __read_mostly = true;\nbool ksu_webview_zygote_umount_enabled __read_mostly = true;\n', context_before=(), context_after=('static int kernel_umount_feature_get(u64 *value)',)),
            placement=Placement.REPLACE,
            payload='#ifndef CONFIG_KSU_SUSFS\nstatic bool ksu_kernel_umount_enabled __read_mostly = true;\n#else\nbool ksu_kernel_umount_enabled = true;\n#endif // #ifndef CONFIG_KSU_SUSFS\nbool ksu_webview_zygote_umount_enabled = true;\n\nbool ksu_is_webview_zygote_umount_enabled(void)\n{\n\treturn READ_ONCE(ksu_webview_zygote_umount_enabled);\n}\n',
            section_context='',
            context_before_count=0,
            context_after_count=3,
            context_before_offset=0,
            diff_body=(('+', '#ifndef CONFIG_KSU_SUSFS'), (' ', 'static bool ksu_kernel_umount_enabled __read_mostly = true;'), ('-', 'bool ksu_webview_zygote_umount_enabled __read_mostly = true;'), ('+', '#else'), ('+', 'bool ksu_kernel_umount_enabled = true;'), ('+', '#endif // #ifndef CONFIG_KSU_SUSFS'), ('+', 'bool ksu_webview_zygote_umount_enabled = true;'), ('+', ''), ('+', 'bool ksu_is_webview_zygote_umount_enabled(void)'), ('+', '{'), ('+', '\treturn READ_ONCE(ksu_webview_zygote_umount_enabled);'), ('+', '}')),
        ),
        XxksuOperationSpec(
            operation_id='xxksu.kernel_feature_kernel_umount_c.hunk_1',
            file_path='kernel/feature/kernel_umount.c',
            spec=AnchorSpec('kernel/feature/kernel_umount.c', 'static inline void ksu_umount_mnt(const char *mnt, struct path *path, int flags)\n{\n\tint err = path_umount(path, flags);\n\tif (err)\n\t\tpr_info("umount %s failed: %d\\n", mnt, err);\n}\n\nstatic inline void try_umount(const char *mnt, int flags)\n', context_before=('extern int path_umount(struct path *path, int flags);',), context_after=()),
            placement=Placement.REPLACE,
            payload='#ifndef KSU_HAS_PATH_UMOUNT\nstatic inline void ksu_umount_mnt(const char *mnt, struct path *path, int flags)\n{\n\tint err = path_umount(path, flags);\n\tif (err)\n\t\tpr_info("umount %s failed: %d\\n", mnt, err);\n}\n#else\nstatic inline void ksu_umount_mnt(struct path *path, int flags)\n{\n\tint err = path_umount(path, flags);\n\tif (err)\n\t\tpr_info("umount failed: %d\\n", err);\n}\n#endif\n\n#if !defined(CONFIG_KSU_SUSFS) || !defined(CONFIG_KSU_SUSFS_TRY_UMOUNT)\nstatic void try_umount(const char *mnt, int flags)\n#else\nvoid try_umount(const char *mnt, int flags)\n#endif\n',
            section_context='static const struct ksu_feature_handler webview_zygote_umount_handler = {',
            context_before_count=3,
            context_after_count=3,
            context_before_offset=3,
            diff_body=(('+', '#ifndef KSU_HAS_PATH_UMOUNT'), (' ', 'static inline void ksu_umount_mnt(const char *mnt, struct path *path, int flags)'), (' ', '{'), (' ', '\tint err = path_umount(path, flags);'), (' ', '\tif (err)'), (' ', '\t\tpr_info("umount %s failed: %d\\n", mnt, err);'), (' ', '}'), ('+', '#else'), ('+', 'static inline void ksu_umount_mnt(struct path *path, int flags)'), ('+', '{'), ('+', '\tint err = path_umount(path, flags);'), ('+', '\tif (err)'), ('+', '\t\tpr_info("umount failed: %d\\n", err);'), ('+', '}'), ('+', '#endif'), (' ', ''), ('-', 'static inline void try_umount(const char *mnt, int flags)'), ('+', '#if !defined(CONFIG_KSU_SUSFS) || !defined(CONFIG_KSU_SUSFS_TRY_UMOUNT)'), ('+', 'static void try_umount(const char *mnt, int flags)'), ('+', '#else'), ('+', 'void try_umount(const char *mnt, int flags)'), ('+', '#endif')),
        ),
        XxksuOperationSpec(
            operation_id='xxksu.kernel_feature_kernel_umount_c.hunk_2',
            file_path='kernel/feature/kernel_umount.c',
            spec=AnchorSpec('kernel/feature/kernel_umount.c', '\tksu_umount_mnt(mnt, &path, flags);\n}\n\nstatic inline int ksu_handle_umount(struct cred *new, const struct cred *old)\n{\n\tuid_t new_uid = ksu_get_uid_t(new->uid);\n\tuid_t old_uid = ksu_get_uid_t(old->uid);\n', context_before=('\t\treturn;', '\t}'), context_after=()),
            placement=Placement.REPLACE,
            payload='#ifndef KSU_HAS_PATH_UMOUNT\n\tksu_umount_mnt(mnt, &path, flags);\n#else\n\tksu_umount_mnt(&path, flags);\n#endif\n\tpath_put(&path);\n}\n\n#ifdef CONFIG_KSU_SUSFS\nint ksu_handle_umount(uid_t old_uid, uid_t new_uid)\n#else\nstatic inline int ksu_handle_umount(uid_t old_uid, uid_t new_uid)\n#endif\n{',
            section_context='static inline void try_umount(const char *mnt, int flags)',
            context_before_count=3,
            context_after_count=3,
            context_before_offset=3,
            diff_body=(('+', '#ifndef KSU_HAS_PATH_UMOUNT'), (' ', '\tksu_umount_mnt(mnt, &path, flags);'), ('+', '#else'), ('+', '\tksu_umount_mnt(&path, flags);'), ('+', '#endif'), ('+', '\tpath_put(&path);'), (' ', '}'), (' ', ''), ('-', 'static inline int ksu_handle_umount(struct cred *new, const struct cred *old)'), ('+', '#ifdef CONFIG_KSU_SUSFS'), ('+', 'int ksu_handle_umount(uid_t old_uid, uid_t new_uid)'), ('+', '#else'), ('+', 'static inline int ksu_handle_umount(uid_t old_uid, uid_t new_uid)'), ('+', '#endif'), (' ', '{'), ('-', '\tuid_t new_uid = ksu_get_uid_t(new->uid);'), ('-', '\tuid_t old_uid = ksu_get_uid_t(old->uid);'), ('-', '')),
        ),
        XxksuOperationSpec(
            operation_id='xxksu.kernel_feature_kernel_umount_c.hunk_3',
            file_path='kernel/feature/kernel_umount.c',
            spec=AnchorSpec('kernel/feature/kernel_umount.c', '\t// There are 6 scenarios:\n', context_before=('\tif (!ksu_module_mounted)', '\t\treturn 0;'), context_after=()),
            placement=Placement.BEFORE,
            payload='\t// Handle webview zygote umount policy\n\tif (new_uid == WEBVIEW_ZYGOTE_UID && !ksu_is_webview_zygote_umount_enabled())\n\t\treturn 0;\n\n',
            section_context='static inline int ksu_handle_umount(struct cred *new, const struct cred *old)',
            context_before_count=3,
            context_after_count=3,
            context_before_offset=3,
            diff_body=(('+', '\t// Handle webview zygote umount policy'), ('+', '\tif (new_uid == WEBVIEW_ZYGOTE_UID && !ksu_is_webview_zygote_umount_enabled())'), ('+', '\t\treturn 0;'), ('+', '')),
        ),
        XxksuOperationSpec(
            operation_id='xxksu.kernel_feature_kernel_umount_c.hunk_4',
            file_path='kernel/feature/kernel_umount.c',
            spec=AnchorSpec(
                'kernel/feature/kernel_umount.c',
                '\t// check old process\'s selinux context, if it is not zygote, ignore it!\n\t// because some su apps may setuid to untrusted_app but they are in global mount namespace\n\t// when we umount for such process, that is a disaster!\n\t// also handle case 4 and 5\n\tbool is_zygote_child = is_zygote(old);\n\tif (!is_zygote_child) {\n\t\tpr_info("handle umount ignore non zygote child: %d\\n", current->pid);\n\t\treturn 0;\n\t}\n\n',
                context_before=('if (!ksu_uid_should_umount(new_uid) && !is_isolated_process(new_uid))', 'return 0;'),
                context_after=('#ifdef CONFIG_KSU_HOSTSREDIRECT', '\tset_thread_flag(TIF_KSU_UNMOUNTABLE);', '#endif'),
            ),
            placement=Placement.REPLACE,
            payload='',
            section_context='static inline int ksu_handle_umount(struct cred *new, const struct cred *old)',
            context_before_count=3,
            context_after_count=3,
            context_before_offset=3,
            diff_body=(
                ('-', "\t// check old process's selinux context, if it is not zygote, ignore it!"),
                ('-', '\t// because some su apps may setuid to untrusted_app but they are in global mount namespace'),
                ('-', '\t// when we umount for such process, that is a disaster!'),
                ('-', '\t// also handle case 4 and 5'),
                ('-', '\tbool is_zygote_child = is_zygote(old);'),
                ('-', '\tif (!is_zygote_child) {'),
                ('-', '\t\tpr_info("handle umount ignore non zygote child: %d\\n", current->pid);'),
                ('-', '\t\treturn 0;'),
                ('-', '\t}'),
                ('-', ''),
            ),
        ),
        XxksuOperationSpec(
            operation_id='xxksu.kernel_hook_setuid_hook_c.hunk_0',
            file_path='kernel/hook/setuid_hook.c',
            spec=AnchorSpec('kernel/hook/setuid_hook.c', 'static __always_inline void ksu_handle_setresuid_cred(struct cred *new, const struct cred *old)\n', context_before=(), context_after=('{', 'if (!new || !old)')),
            placement=Placement.REPLACE,
            payload='#ifdef CONFIG_KSU_SUSFS\n#include <linux/susfs_def.h>\n#include "selinux/selinux.h"\n#endif\n\n#ifdef CONFIG_KSU_SUSFS\nextern u32 susfs_zygote_sid;\nextern u32 susfs_zygote_next_sid;\nextern void disable_seccomp(void);\nextern struct work_struct susfs_extra_works;\nextern bool ksu_is_webview_zygote_umount_enabled(void);\n#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT\nextern void susfs_try_umount(uid_t uid);\n#endif\n\nstatic inline void ksu_handle_extra_susfs_work(void)\n{\n\tif (work_pending(&susfs_extra_works))\n\t\treturn;\n\n\tschedule_work(&susfs_extra_works);\n}\n\nstatic int handle_zygote_setresuid(uid_t ruid) {\n\t// Check if spawned process is isolated service first, and force to do umount if so\n\tif (is_isolated_process(ruid)) {\n\t\tsusfs_set_current_proc_no_su();\n\t\tsusfs_set_current_proc_umounted();\n\t\tgoto do_umount;\n\t}\n\n\t// Check if webview zygote should be umounted\n\tif (unlikely(ruid == WEBVIEW_ZYGOTE_UID)) {\n\t\tif (ksu_is_webview_zygote_umount_enabled()) {\n\t\t\tsusfs_set_current_proc_no_su();\n\t\t\tsusfs_set_current_proc_umounted();\n\t\t\tgoto do_umount;\n\t\t}\n\t\tsusfs_set_current_proc_no_su();\n\t\treturn 0;\n\t}\n\n\t// Normal app that needs umount\n\tif (likely(is_appuid(ruid) && ksu_uid_should_umount(ruid))) {\n\t\tsusfs_set_current_proc_no_su();\n\t\tsusfs_set_current_proc_umounted();\n\t\tgoto do_umount;\n\t}\n\n\t// Root allowed apps\n\tif (ksu_is_allow_uid_for_current(ruid)) {\n\t\tdisable_seccomp();\n\t\treturn 0;\n\t}\n\n\tsusfs_set_current_proc_no_su();\n\treturn 0;\n\ndo_umount:\n\t{\n#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT\n\t\tsusfs_try_umount(ruid);\n#endif\n\t\tksu_handle_umount(current_uid().val, ruid);\n\t\tksu_handle_extra_susfs_work();\n\t}\n\n\treturn 0;\n}\n\nstatic int handle_zygote_next_setresuid(uid_t ruid) {\n\t// zygote_next: do NOT umount, just set flags\n\tif (is_isolated_process(ruid)) {\n\t\tsusfs_set_current_proc_no_su();\n\t\tsusfs_set_current_proc_umounted();\n\t\tsusfs_set_current_proc_umounted_for_zygote_next();\n\t\tgoto do_susfs_work;\n\t}\n\n\tif (unlikely(ruid == WEBVIEW_ZYGOTE_UID)) {\n\t\tif (ksu_is_webview_zygote_umount_enabled()) {\n\t\t\tsusfs_set_current_proc_no_su();\n\t\t\tsusfs_set_current_proc_umounted();\n\t\t\tsusfs_set_current_proc_umounted_for_zygote_next();\n\t\t\tgoto do_susfs_work;\n\t\t}\n\t\tsusfs_set_current_proc_no_su();\n\t\treturn 0;\n\t}\n\n\tif (likely(is_appuid(ruid) && ksu_uid_should_umount(ruid))) {\n\t\tsusfs_set_current_proc_no_su();\n\t\tsusfs_set_current_proc_umounted();\n\t\tsusfs_set_current_proc_umounted_for_zygote_next();\n\t\tgoto do_susfs_work;\n\t}\n\n\tif (ksu_is_allow_uid_for_current(ruid)) {\n\t\tdisable_seccomp();\n\t\treturn 0;\n\t}\n\n\tsusfs_set_current_proc_no_su();\n\treturn 0;\n\ndo_susfs_work:\n\t{\n#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT\n\t\tsusfs_try_umount(ruid);\n#endif\n\t\tksu_handle_extra_susfs_work();\n\t}\n\n\treturn 0;\n}\n\nint ksu_handle_setresuid(uid_t ruid, uid_t euid, uid_t suid)\n{\n\tuid_t cur_uid = current_uid().val;\n\n\tif (cur_uid != 0)\n\t\treturn 0;\n\n\tif (susfs_is_sid_equal(current_cred(), susfs_zygote_sid))\n\t\treturn handle_zygote_setresuid(ruid);\n\n\tif (susfs_is_sid_equal(current_cred(), susfs_zygote_next_sid))\n\t\treturn handle_zygote_next_setresuid(ruid);\n\n\treturn 0;\n}\n#endif // #ifdef CONFIG_KSU_SUSFS\n\nvoid ksu_handle_setresuid_cred(struct cred *new, const struct cred *old)\n',
            section_context='',
            context_before_count=0,
            context_after_count=3,
            context_before_offset=0,
            diff_body=(('-', 'static __always_inline void ksu_handle_setresuid_cred(struct cred *new, const struct cred *old)'), ('+', '#ifdef CONFIG_KSU_SUSFS'), ('+', '#include <linux/susfs_def.h>'), ('+', '#include "selinux/selinux.h"'), ('+', '#endif'), ('+', ''), ('+', '#ifdef CONFIG_KSU_SUSFS'), ('+', 'extern u32 susfs_zygote_sid;'), ('+', 'extern u32 susfs_zygote_next_sid;'), ('+', 'extern void disable_seccomp(void);'), ('+', 'extern struct work_struct susfs_extra_works;'), ('+', 'extern bool ksu_is_webview_zygote_umount_enabled(void);'), ('+', '#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT'), ('+', 'extern void susfs_try_umount(uid_t uid);'), ('+', '#endif'), ('+', ''), ('+', 'static inline void ksu_handle_extra_susfs_work(void)'), ('+', '{'), ('+', '\tif (work_pending(&susfs_extra_works))'), ('+', '\t\treturn;'), ('+', ''), ('+', '\tschedule_work(&susfs_extra_works);'), ('+', '}'), ('+', ''), ('+', 'static int handle_zygote_setresuid(uid_t ruid) {'), ('+', '\t// Check if spawned process is isolated service first, and force to do umount if so'), ('+', '\tif (is_isolated_process(ruid)) {'), ('+', '\t\tsusfs_set_current_proc_no_su();'), ('+', '\t\tsusfs_set_current_proc_umounted();'), ('+', '\t\tgoto do_umount;'), ('+', '\t}'), ('+', ''), ('+', '\t// Check if webview zygote should be umounted'), ('+', '\tif (unlikely(ruid == WEBVIEW_ZYGOTE_UID)) {'), ('+', '\t\tif (ksu_is_webview_zygote_umount_enabled()) {'), ('+', '\t\t\tsusfs_set_current_proc_no_su();'), ('+', '\t\t\tsusfs_set_current_proc_umounted();'), ('+', '\t\t\tgoto do_umount;'), ('+', '\t\t}'), ('+', '\t\tsusfs_set_current_proc_no_su();'), ('+', '\t\treturn 0;'), ('+', '\t}'), ('+', ''), ('+', '\t// Normal app that needs umount'), ('+', '\tif (likely(is_appuid(ruid) && ksu_uid_should_umount(ruid))) {'), ('+', '\t\tsusfs_set_current_proc_no_su();'), ('+', '\t\tsusfs_set_current_proc_umounted();'), ('+', '\t\tgoto do_umount;'), ('+', '\t}'), ('+', ''), ('+', '\t// Root allowed apps'), ('+', '\tif (ksu_is_allow_uid_for_current(ruid)) {'), ('+', '\t\tdisable_seccomp();'), ('+', '\t\treturn 0;'), ('+', '\t}'), ('+', ''), ('+', '\tsusfs_set_current_proc_no_su();'), ('+', '\treturn 0;'), ('+', ''), ('+', 'do_umount:'), ('+', '\t{'), ('+', '#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT'), ('+', '\t\tsusfs_try_umount(ruid);'), ('+', '#endif'), ('+', '\t\tksu_handle_umount(current_uid().val, ruid);'), ('+', '\t\tksu_handle_extra_susfs_work();'), ('+', '\t}'), ('+', ''), ('+', '\treturn 0;'), ('+', '}'), ('+', ''), ('+', 'static int handle_zygote_next_setresuid(uid_t ruid) {'), ('+', '\t// zygote_next: do NOT umount, just set flags'), ('+', '\tif (is_isolated_process(ruid)) {'), ('+', '\t\tsusfs_set_current_proc_no_su();'), ('+', '\t\tsusfs_set_current_proc_umounted();'), ('+', '\t\tsusfs_set_current_proc_umounted_for_zygote_next();'), ('+', '\t\tgoto do_susfs_work;'), ('+', '\t}'), ('+', ''), ('+', '\tif (unlikely(ruid == WEBVIEW_ZYGOTE_UID)) {'), ('+', '\t\tif (ksu_is_webview_zygote_umount_enabled()) {'), ('+', '\t\t\tsusfs_set_current_proc_no_su();'), ('+', '\t\t\tsusfs_set_current_proc_umounted();'), ('+', '\t\t\tsusfs_set_current_proc_umounted_for_zygote_next();'), ('+', '\t\t\tgoto do_susfs_work;'), ('+', '\t\t}'), ('+', '\t\tsusfs_set_current_proc_no_su();'), ('+', '\t\treturn 0;'), ('+', '\t}'), ('+', ''), ('+', '\tif (likely(is_appuid(ruid) && ksu_uid_should_umount(ruid))) {'), ('+', '\t\tsusfs_set_current_proc_no_su();'), ('+', '\t\tsusfs_set_current_proc_umounted();'), ('+', '\t\tsusfs_set_current_proc_umounted_for_zygote_next();'), ('+', '\t\tgoto do_susfs_work;'), ('+', '\t}'), ('+', ''), ('+', '\tif (ksu_is_allow_uid_for_current(ruid)) {'), ('+', '\t\tdisable_seccomp();'), ('+', '\t\treturn 0;'), ('+', '\t}'), ('+', ''), ('+', '\tsusfs_set_current_proc_no_su();'), ('+', '\treturn 0;'), ('+', ''), ('+', 'do_susfs_work:'), ('+', '\t{'), ('+', '#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT'), ('+', '\t\tsusfs_try_umount(ruid);'), ('+', '#endif'), ('+', '\t\tksu_handle_extra_susfs_work();'), ('+', '\t}'), ('+', ''), ('+', '\treturn 0;'), ('+', '}'), ('+', ''), ('+', 'int ksu_handle_setresuid(uid_t ruid, uid_t euid, uid_t suid)'), ('+', '{'), ('+', '\tuid_t cur_uid = current_uid().val;'), ('+', ''), ('+', '\tif (cur_uid != 0)'), ('+', '\t\treturn 0;'), ('+', ''), ('+', '\tif (susfs_is_sid_equal(current_cred(), susfs_zygote_sid))'), ('+', '\t\treturn handle_zygote_setresuid(ruid);'), ('+', ''), ('+', '\tif (susfs_is_sid_equal(current_cred(), susfs_zygote_next_sid))'), ('+', '\t\treturn handle_zygote_next_setresuid(ruid);'), ('+', ''), ('+', '\treturn 0;'), ('+', '}'), ('+', '#endif // #ifdef CONFIG_KSU_SUSFS'), ('+', ''), ('+', 'void ksu_handle_setresuid_cred(struct cred *new, const struct cred *old)')),
        ),
        XxksuOperationSpec(
            operation_id='xxksu.kernel_hook_setuid_hook_c.hunk_1',
            file_path='kernel/hook/setuid_hook.c',
            spec=AnchorSpec('kernel/hook/setuid_hook.c', '\t// we dont have those new fancy things upstream has\n\t// lets just do the original thing where we disable seccomp\n\tif (unlikely(is_uid_manager(new_uid)))\n\t\tgoto install_ksu_fd;\n\n\tif (ksu_is_allow_uid_for_current(new_uid))\n\t\tgoto kill_seccomp;\n\n\t// Handle kernel umount\n\tksu_handle_umount(new, old);\n\treturn;\n\ninstall_ksu_fd:\n\tpr_info("install fd for manager: %d\\n", new_uid);\n\tksu_install_fd();\n\nkill_seccomp:\n\tdisable_seccomp();\n\tset_thread_flag(TIF_KSU_MANAGED); // sucompat fast-path\n\treturn;\n', context_before=('pr_info("handle_setresuid from %d to %d\\n", old_uid, new_uid);',), context_after=()),
            placement=Placement.REPLACE,
            payload='#ifdef CONFIG_KSU_SUSFS\n\tif (unlikely(is_uid_manager(new_uid))) {\n\t\tdisable_seccomp();\n\t\tset_thread_flag(TIF_KSU_MANAGED); // sucompat fast-path\n\t\tpr_info("install fd for manager: %d\\n", new_uid);\n\t\tksu_install_fd();\n\t\treturn;\n\t}\n\n\tif (ksu_is_allow_uid_for_current(new_uid)) {\n\t\tdisable_seccomp();\n\t\treturn;\n\t}\n\n\tksu_handle_setresuid(new_uid, new_uid, new_uid);\n#else\n\tksu_handle_umount(old_uid, new_uid);\n#endif\n',
            section_context='static __always_inline void ksu_handle_setresuid_cred(struct cred *new, const st',
            context_before_count=3,
            context_after_count=1,
            context_before_offset=3,
            diff_body=(('-', '\t// we dont have those new fancy things upstream has'), ('-', '\t// lets just do the original thing where we disable seccomp'), ('-', '\tif (unlikely(is_uid_manager(new_uid)))'), ('-', '\t\tgoto install_ksu_fd;'), ('-', ''), ('-', '\tif (ksu_is_allow_uid_for_current(new_uid))'), ('-', '\t\tgoto kill_seccomp;'), ('-', ''), ('-', '\t// Handle kernel umount'), ('-', '\tksu_handle_umount(new, old);'), ('-', '\treturn;'), ('+', '#ifdef CONFIG_KSU_SUSFS'), ('+', '\tif (unlikely(is_uid_manager(new_uid))) {'), ('+', '\t\tdisable_seccomp();'), ('+', '\t\tset_thread_flag(TIF_KSU_MANAGED); // sucompat fast-path'), ('+', '\t\tpr_info("install fd for manager: %d\\n", new_uid);'), ('+', '\t\tksu_install_fd();'), ('+', '\t\treturn;'), ('+', '\t}'), (' ', ''), ('-', 'install_ksu_fd:'), ('-', '\tpr_info("install fd for manager: %d\\n", new_uid);'), ('-', '\tksu_install_fd();'), ('+', '\tif (ksu_is_allow_uid_for_current(new_uid)) {'), ('+', '\t\tdisable_seccomp();'), ('+', '\t\treturn;'), ('+', '\t}'), (' ', ''), ('-', 'kill_seccomp:'), ('-', '\tdisable_seccomp();'), ('-', '\tset_thread_flag(TIF_KSU_MANAGED); // sucompat fast-path'), ('-', '\treturn;'), ('+', '\tksu_handle_setresuid(new_uid, new_uid, new_uid);'), ('+', '#else'), ('+', '\tksu_handle_umount(old_uid, new_uid);'), ('+', '#endif')),
        ),
        XxksuOperationSpec(
            operation_id='xxksu.kernel_ksu_c.hunk_0',
            file_path='kernel/ksu.c',
            spec=AnchorSpec('kernel/ksu.c', '// track backports and other quirks here\n', context_before=('#include "hook/kp_ksud.c"', '#endif'), context_after=()),
            placement=Placement.BEFORE,
            payload='#ifdef CONFIG_KSU_SUSFS\n#include <linux/susfs.h>\n#endif // #ifdef CONFIG_KSU_SUSFS\n\n',
            section_context='',
            context_before_count=3,
            context_after_count=3,
            context_before_offset=3,
            diff_body=(('+', '#ifdef CONFIG_KSU_SUSFS'), ('+', '#include <linux/susfs.h>'), ('+', '#endif // #ifdef CONFIG_KSU_SUSFS'), ('+', '')),
        ),
        XxksuOperationSpec(
            operation_id='xxksu.kernel_ksu_c.hunk_1',
            file_path='kernel/ksu.c',
            spec=AnchorSpec('kernel/ksu.c', '\tksu_ksud_init();\n', context_before=('\tksu_throne_tracker_init();',), context_after=()),
            placement=Placement.BEFORE,
            payload='#ifdef CONFIG_KSU_SUSFS\n    susfs_init();\n#endif // #ifdef CONFIG_KSU_SUSFS\n\n',
            section_context='static int __init kernelsu_init(void)',
            context_before_count=3,
            context_after_count=3,
            context_before_offset=3,
            diff_body=(('+', '#ifdef CONFIG_KSU_SUSFS'), ('+', '    susfs_init();'), ('+', '#endif // #ifdef CONFIG_KSU_SUSFS'), ('+', '')),
        ),
        XxksuOperationSpec(
            operation_id='xxksu.kernel_selinux_rules_c.hunk_0',
            file_path='kernel/selinux/rules.c',
            spec=AnchorSpec('kernel/selinux/rules.c', '\tsmp_mb();\n\treset_avc_cache();\n#endif\n', context_before=(), context_after=('}', '#define KSU_SEPOLICY_MAX_BATCH_SIZE (8U * 1024U * 1024U)')),
            placement=Placement.AFTER,
            payload='\n#ifdef CONFIG_KSU_SUSFS\n\tsusfs_set_priv_app_sid();\n\tsusfs_set_init_sid();\n\tsusfs_set_ksu_sid();\n\tsusfs_set_zygote_sid();\n#endif\n',
            section_context='out_flush:',
            context_before_count=3,
            context_after_count=3,
            context_before_offset=0,
            diff_body=(('+', ''), ('+', '#ifdef CONFIG_KSU_SUSFS'), ('+', '\tsusfs_set_priv_app_sid();'), ('+', '\tsusfs_set_init_sid();'), ('+', '\tsusfs_set_ksu_sid();'), ('+', '\tsusfs_set_zygote_sid();'), ('+', '#endif')),
        ),
        XxksuOperationSpec(
            operation_id='xxksu.kernel_selinux_selinux_c.hunk_0',
            file_path='kernel/selinux/selinux.c',
            spec=AnchorSpec('kernel/selinux/selinux.c', 'commit_creds(cred);\n}\n', context_before=(), context_after=()),
            placement=Placement.AFTER,
            payload='\n#ifdef CONFIG_KSU_SUSFS\n#define KERNEL_INIT_DOMAIN "u:r:init:s0"\n#define KERNEL_ZYGOTE_DOMAIN "u:r:zygote:s0"\n#define KERNEL_ZYGOTE_NEXT_DOMAIN "u:r:zygote_next:s0"\n#define KERNEL_PRIV_APP_DOMAIN "u:r:priv_app:s0:c512,c768"\n\nu32 susfs_ksu_sid = 0;\nu32 susfs_init_sid = 0;\nu32 susfs_zygote_sid = 0;\nu32 susfs_zygote_next_sid = 0;\nu32 susfs_priv_app_sid = 0;\n\nstatic inline void susfs_set_sid(const char *secctx_name, u32 *out_sid)\n{\n    int err;\n    \n    if (!secctx_name || !out_sid) {\n        pr_err("secctx_name || out_sid is NULL\\n");\n        return;\n    }\n\n    err = security_secctx_to_secid(secctx_name, strlen(secctx_name),\n                       out_sid);\n    if (err) {\n        pr_err("failed setting sid for \'%s\', err: %d\\n", secctx_name, err);\n        return;\n    }\n    pr_info("sid \'%u\' is set for secctx_name \'%s\'\\n", *out_sid, secctx_name);\n}\n\nbool susfs_is_sid_equal(const struct cred *cred, u32 sid2) {\n#if LINUX_VERSION_CODE < KERNEL_VERSION(6, 18, 0)\n    const struct task_security_struct *tsec = selinux_cred(cred);\n#else\n    const struct cred_security_struct *tsec = selinux_cred(cred);\n#endif\n\n    if (!tsec) {\n        return false;\n    }\n    return tsec->sid == sid2;\n}\n\nu32 susfs_get_sid_from_name(const char *secctx_name)\n{\n    u32 out_sid = 0;\n    int err;\n    \n    if (!secctx_name) {\n        pr_err("secctx_name is NULL\\n");\n        return 0;\n    }\n    err = security_secctx_to_secid(secctx_name, strlen(secctx_name),\n                       &out_sid);\n    if (err) {\n        pr_err("failed getting sid from secctx_name: %s, err: %d\\n", secctx_name, err);\n        return 0;\n    }\n    return out_sid;\n}\n\nu32 susfs_get_current_sid(void) {\n    return current_sid();\n}\n\nvoid susfs_set_zygote_sid(void)\n{\n    susfs_set_sid(KERNEL_ZYGOTE_DOMAIN, &susfs_zygote_sid);\n    susfs_set_sid(KERNEL_ZYGOTE_NEXT_DOMAIN, &susfs_zygote_next_sid);\n}\n\nbool susfs_is_current_zygote_domain(void) {\n    return unlikely(current_sid() == susfs_zygote_sid);\n}\n\nvoid susfs_set_ksu_sid(void)\n{\n    susfs_set_sid(KERNEL_SU_CONTEXT, &susfs_ksu_sid);\n}\n\nbool susfs_is_current_zygote_next_domain(void) {\n    return unlikely(current_sid() == susfs_zygote_next_sid);\n}\n\nbool susfs_is_current_ksu_domain(void) {\n    return unlikely(current_sid() == susfs_ksu_sid);\n}\n\nvoid susfs_set_init_sid(void)\n{\n    susfs_set_sid(KERNEL_INIT_DOMAIN, &susfs_init_sid);\n}\n\nbool susfs_is_current_init_domain(void) {\n    return unlikely(current_sid() == susfs_init_sid);\n}\n\nvoid susfs_set_priv_app_sid(void)\n{\n    susfs_set_sid(KERNEL_PRIV_APP_DOMAIN, &susfs_priv_app_sid);\n}\n#endif // #ifdef CONFIG_KSU_SUSFS\n',
            section_context='void escape_to_root_for_adb_root(void)',
            context_before_count=3,
            context_after_count=0,
            context_before_offset=1,
            diff_body=(('+', ''), ('+', '#ifdef CONFIG_KSU_SUSFS'), ('+', '#define KERNEL_INIT_DOMAIN "u:r:init:s0"'), ('+', '#define KERNEL_ZYGOTE_DOMAIN "u:r:zygote:s0"'), ('+', '#define KERNEL_ZYGOTE_NEXT_DOMAIN "u:r:zygote_next:s0"'), ('+', '#define KERNEL_PRIV_APP_DOMAIN "u:r:priv_app:s0:c512,c768"'), ('+', ''), ('+', 'u32 susfs_ksu_sid = 0;'), ('+', 'u32 susfs_init_sid = 0;'), ('+', 'u32 susfs_zygote_sid = 0;'), ('+', 'u32 susfs_zygote_next_sid = 0;'), ('+', 'u32 susfs_priv_app_sid = 0;'), ('+', ''), ('+', 'static inline void susfs_set_sid(const char *secctx_name, u32 *out_sid)'), ('+', '{'), ('+', '    int err;'), ('+', '    '), ('+', '    if (!secctx_name || !out_sid) {'), ('+', '        pr_err("secctx_name || out_sid is NULL\\n");'), ('+', '        return;'), ('+', '    }'), ('+', ''), ('+', '    err = security_secctx_to_secid(secctx_name, strlen(secctx_name),'), ('+', '                       out_sid);'), ('+', '    if (err) {'), ('+', '        pr_err("failed setting sid for \'%s\', err: %d\\n", secctx_name, err);'), ('+', '        return;'), ('+', '    }'), ('+', '    pr_info("sid \'%u\' is set for secctx_name \'%s\'\\n", *out_sid, secctx_name);'), ('+', '}'), ('+', ''), ('+', 'bool susfs_is_sid_equal(const struct cred *cred, u32 sid2) {'), ('+', '#if LINUX_VERSION_CODE < KERNEL_VERSION(6, 18, 0)'), ('+', '    const struct task_security_struct *tsec = selinux_cred(cred);'), ('+', '#else'), ('+', '    const struct cred_security_struct *tsec = selinux_cred(cred);'), ('+', '#endif'), ('+', ''), ('+', '    if (!tsec) {'), ('+', '        return false;'), ('+', '    }'), ('+', '    return tsec->sid == sid2;'), ('+', '}'), ('+', ''), ('+', 'u32 susfs_get_sid_from_name(const char *secctx_name)'), ('+', '{'), ('+', '    u32 out_sid = 0;'), ('+', '    int err;'), ('+', '    '), ('+', '    if (!secctx_name) {'), ('+', '        pr_err("secctx_name is NULL\\n");'), ('+', '        return 0;'), ('+', '    }'), ('+', '    err = security_secctx_to_secid(secctx_name, strlen(secctx_name),'), ('+', '                       &out_sid);'), ('+', '    if (err) {'), ('+', '        pr_err("failed getting sid from secctx_name: %s, err: %d\\n", secctx_name, err);'), ('+', '        return 0;'), ('+', '    }'), ('+', '    return out_sid;'), ('+', '}'), ('+', ''), ('+', 'u32 susfs_get_current_sid(void) {'), ('+', '    return current_sid();'), ('+', '}'), ('+', ''), ('+', 'void susfs_set_zygote_sid(void)'), ('+', '{'), ('+', '    susfs_set_sid(KERNEL_ZYGOTE_DOMAIN, &susfs_zygote_sid);'), ('+', '    susfs_set_sid(KERNEL_ZYGOTE_NEXT_DOMAIN, &susfs_zygote_next_sid);'), ('+', '}'), ('+', ''), ('+', 'bool susfs_is_current_zygote_domain(void) {'), ('+', '    return unlikely(current_sid() == susfs_zygote_sid);'), ('+', '}'), ('+', ''), ('+', 'void susfs_set_ksu_sid(void)'), ('+', '{'), ('+', '    susfs_set_sid(KERNEL_SU_CONTEXT, &susfs_ksu_sid);'), ('+', '}'), ('+', ''), ('+', 'bool susfs_is_current_zygote_next_domain(void) {'), ('+', '    return unlikely(current_sid() == susfs_zygote_next_sid);'), ('+', '}'), ('+', ''), ('+', 'bool susfs_is_current_ksu_domain(void) {'), ('+', '    return unlikely(current_sid() == susfs_ksu_sid);'), ('+', '}'), ('+', ''), ('+', 'void susfs_set_init_sid(void)'), ('+', '{'), ('+', '    susfs_set_sid(KERNEL_INIT_DOMAIN, &susfs_init_sid);'), ('+', '}'), ('+', ''), ('+', 'bool susfs_is_current_init_domain(void) {'), ('+', '    return unlikely(current_sid() == susfs_init_sid);'), ('+', '}'), ('+', ''), ('+', 'void susfs_set_priv_app_sid(void)'), ('+', '{'), ('+', '    susfs_set_sid(KERNEL_PRIV_APP_DOMAIN, &susfs_priv_app_sid);'), ('+', '}'), ('+', '#endif // #ifdef CONFIG_KSU_SUSFS')),
        ),
        XxksuOperationSpec(
            operation_id='xxksu.kernel_selinux_selinux_h.hunk_0',
            file_path='kernel/selinux/selinux.h',
            spec=AnchorSpec('kernel/selinux/selinux.h', 'void setup_selinux(const char *, struct cred *);\n', context_before=('#define INIT_CONTEXT "u:r:init:s0"',), context_after=()),
            placement=Placement.BEFORE,
            payload='#ifdef CONFIG_KSU_SUSFS\nbool susfs_is_sid_equal(const struct cred *cred, u32 sid2);\nu32 susfs_get_sid_from_name(const char *secctx_name);\nu32 susfs_get_current_sid(void);\nvoid susfs_set_zygote_sid(void);\nbool susfs_is_current_zygote_domain(void);\nbool susfs_is_current_zygote_next_domain(void);\nvoid susfs_set_ksu_sid(void);\nbool susfs_is_current_ksu_domain(void);\nvoid susfs_set_init_sid(void);\nbool susfs_is_current_init_domain(void);\nvoid susfs_set_priv_app_sid(void);\n#endif // #ifdef CONFIG_KSU_SUSFS\n\n',
            section_context='',
            context_before_count=3,
            context_after_count=3,
            context_before_offset=3,
            diff_body=(('+', '#ifdef CONFIG_KSU_SUSFS'), ('+', 'bool susfs_is_sid_equal(const struct cred *cred, u32 sid2);'), ('+', 'u32 susfs_get_sid_from_name(const char *secctx_name);'), ('+', 'u32 susfs_get_current_sid(void);'), ('+', 'void susfs_set_zygote_sid(void);'), ('+', 'bool susfs_is_current_zygote_domain(void);'), ('+', 'bool susfs_is_current_zygote_next_domain(void);'), ('+', 'void susfs_set_ksu_sid(void);'), ('+', 'bool susfs_is_current_ksu_domain(void);'), ('+', 'void susfs_set_init_sid(void);'), ('+', 'bool susfs_is_current_init_domain(void);'), ('+', 'void susfs_set_priv_app_sid(void);'), ('+', '#endif // #ifdef CONFIG_KSU_SUSFS'), ('+', '')),
        ),
        XxksuOperationSpec(
            operation_id='xxksu.kernel_supercall_dispatch_c.hunk_0',
            file_path='kernel/supercall/dispatch.c',
            spec=AnchorSpec('kernel/supercall/dispatch.c', 'static int do_grant_root(void __user *arg)\n', context_before=(), context_after=('{', 'int ret;')),
            placement=Placement.BEFORE,
            payload='#ifdef CONFIG_KSU_SUSFS\n#include <linux/namei.h>\n#include <linux/susfs.h>\n#include "objsec.h"\n#endif // #ifdef CONFIG_KSU_SUSFS\n\n#ifdef CONFIG_KSU_SUSFS\nbool susfs_is_boot_completed_triggered __read_mostly = false;\n#endif // #ifdef CONFIG_KSU_SUSFS\n\n',
            section_context='',
            context_before_count=0,
            context_after_count=3,
            context_before_offset=0,
            diff_body=(('+', '#ifdef CONFIG_KSU_SUSFS'), ('+', '#include <linux/namei.h>'), ('+', '#include <linux/susfs.h>'), ('+', '#include "objsec.h"'), ('+', '#endif // #ifdef CONFIG_KSU_SUSFS'), ('+', ''), ('+', '#ifdef CONFIG_KSU_SUSFS'), ('+', 'bool susfs_is_boot_completed_triggered __read_mostly = false;'), ('+', '#endif // #ifdef CONFIG_KSU_SUSFS'), ('+', '')),
        ),
        XxksuOperationSpec(
            operation_id='xxksu.kernel_supercall_dispatch_c.hunk_1',
            file_path='kernel/supercall/dispatch.c',
            spec=AnchorSpec('kernel/supercall/dispatch.c', '\t\t\ton_boot_completed();\n', context_before=('boot_complete_lock = true;', 'pr_info("boot_complete triggered\\n");'), context_after=()),
            placement=Placement.AFTER,
            payload='#ifdef CONFIG_KSU_SUSFS\n        \tsusfs_start_sdcard_monitor_fn();\n#endif // #ifdef CONFIG_KSU_SUSFS\n',
            section_context='static int do_report_event(void __user *arg)',
            context_before_count=3,
            context_after_count=3,
            context_before_offset=2,
            diff_body=(('+', '#ifdef CONFIG_KSU_SUSFS'), ('+', '        \tsusfs_start_sdcard_monitor_fn();'), ('+', '#endif // #ifdef CONFIG_KSU_SUSFS')),
        ),
        XxksuOperationSpec(
            operation_id='xxksu.kernel_supercall_dispatch_c.hunk_2',
            file_path='kernel/supercall/dispatch.c',
            spec=AnchorSpec('kernel/supercall/dispatch.c', '\t\tcase KSU_MARK_GET: {\n', context_before=('switch (cmd.operation) {',), context_after=()),
            placement=Placement.AFTER,
            payload='#ifndef CONFIG_KSU_SUSFS\n',
            section_context='static int do_manage_mark(void __user *arg)',
            context_before_count=3,
            context_after_count=3,
            context_before_offset=2,
            diff_body=(('+', '#ifndef CONFIG_KSU_SUSFS'),),
        ),
        XxksuOperationSpec(
            operation_id='xxksu.kernel_supercall_dispatch_c.hunk_3',
            file_path='kernel/supercall/dispatch.c',
            spec=AnchorSpec('kernel/supercall/dispatch.c', '\t\t\tcmd.result = (u32)ret;\n\t\t\tbreak;\n', context_before=(), context_after=('\t\t}', '#if 0 // TODO: revisit this sometime')),
            placement=Placement.AFTER,
            payload='#else\nif (susfs_is_current_proc_umounted()) {\n            ret = 0; // SYSCALL_TRACEPOINT is NOT flagged\n        } else {\n            ret = 1; // SYSCALL_TRACEPOINT is flagged\n        }\n        pr_info("manage_mark: ret for pid %d: %d\\n", cmd.pid, ret);\n        cmd.result = (u32)ret;\n        break;\n#endif // #ifndef CONFIG_KSU_SUSFS\n',
            section_context='static int do_manage_mark(void __user *arg)',
            context_before_count=3,
            context_after_count=3,
            context_before_offset=1,
            diff_body=(('+', '#else'), ('+', 'if (susfs_is_current_proc_umounted()) {'), ('+', '            ret = 0; // SYSCALL_TRACEPOINT is NOT flagged'), ('+', '        } else {'), ('+', '            ret = 1; // SYSCALL_TRACEPOINT is flagged'), ('+', '        }'), ('+', '        pr_info("manage_mark: ret for pid %d: %d\\n", cmd.pid, ret);'), ('+', '        cmd.result = (u32)ret;'), ('+', '        break;'), ('+', '#endif // #ifndef CONFIG_KSU_SUSFS')),
        ),
        XxksuOperationSpec(
            operation_id='xxksu.kernel_supercall_supercall_c.hunk_0',
            file_path='kernel/supercall/supercall.c',
            spec=AnchorSpec('kernel/supercall/supercall.c', 'static int anon_ksu_release(struct inode *inode, struct file *filp)\n', context_before=(), context_after=('{', 'pr_info("ksu fd released\\n");')),
            placement=Placement.BEFORE,
            payload='#ifdef CONFIG_KSU_SUSFS\n#include <linux/namei.h>\n#include <linux/susfs.h>\n#include "objsec.h"\n#endif // #ifdef CONFIG_KSU_SUSFS\n\n',
            section_context='',
            context_before_count=0,
            context_after_count=3,
            context_before_offset=0,
            diff_body=(('+', '#ifdef CONFIG_KSU_SUSFS'), ('+', '#include <linux/namei.h>'), ('+', '#include <linux/susfs.h>'), ('+', '#include "objsec.h"'), ('+', '#endif // #ifdef CONFIG_KSU_SUSFS'), ('+', '')),
        ),
        XxksuOperationSpec(
            operation_id='xxksu.kernel_supercall_supercall_c.hunk_1',
            file_path='kernel/supercall/supercall.c',
            spec=AnchorSpec('kernel/supercall/supercall.c', '\tif (magic1 != KSU_INSTALL_MAGIC1)\n\t\treturn 0;\n', context_before=('{',), context_after=()),
            placement=Placement.AFTER,
            payload='#ifdef CONFIG_KSU_DEBUG\n\tpr_info("sys_reboot: intercepted call! magic: 0x%x id: %d\\n", magic1,\n\t\tmagic2);\n#endif\n\n#ifdef CONFIG_KSU_SUSFS\n    // If magic2 is susfs and current process is root\n    if (magic2 == SUSFS_MAGIC && current_uid().val == 0) {\n#ifdef CONFIG_KSU_SUSFS_SUS_PATH\n        if (cmd == CMD_SUSFS_ADD_SUS_PATH) {\n            susfs_add_sus_path(arg);\n            return 0;\n        }\n        if (cmd == CMD_SUSFS_ADD_SUS_PATH_LOOP) {\n            susfs_add_sus_path_loop(arg);\n            return 0;\n        }\n#endif //#ifdef CONFIG_KSU_SUSFS_SUS_PATH\n#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT\n        if (cmd == CMD_SUSFS_HIDE_SUS_MNTS_FOR_NON_SU_PROCS) {\n            susfs_set_hide_sus_mnts_for_non_su_procs(arg);\n            return 0;\n        }\n#endif //#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT\n#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT\n        if (cmd == CMD_SUSFS_ADD_SUS_KSTAT) {\n            susfs_add_sus_kstat(arg);\n            return 0;\n        }\n        if (cmd == CMD_SUSFS_UPDATE_SUS_KSTAT) {\n            susfs_update_sus_kstat(arg);\n            return 0;\n        }\n        if (cmd == CMD_SUSFS_ADD_SUS_KSTAT_STATICALLY) {\n            susfs_add_sus_kstat(arg);\n            return 0;\n        }\n#endif //#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT\n#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT\n        if (cmd == CMD_SUSFS_ADD_TRY_UMOUNT) {\n            susfs_add_try_umount(arg);\n            return 0;\n        }\n#endif //#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT\n#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME\n        if (cmd == CMD_SUSFS_SET_UNAME) {\n            susfs_set_uname(arg);\n            return 0;\n        }\n#endif //#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME\n#ifdef CONFIG_KSU_SUSFS_ENABLE_LOG\n        if (cmd == CMD_SUSFS_ENABLE_LOG) {\n            susfs_enable_log(arg);\n            return 0;\n        }\n#endif //#ifdef CONFIG_KSU_SUSFS_ENABLE_LOG\n#ifdef CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG\n        if (cmd == CMD_SUSFS_SET_CMDLINE_OR_BOOTCONFIG) {\n            susfs_set_cmdline_or_bootconfig(arg);\n            return 0;\n        }\n#endif //#ifdef CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG\n#ifdef CONFIG_KSU_SUSFS_OPEN_REDIRECT\n        if (cmd == CMD_SUSFS_ADD_OPEN_REDIRECT) {\n            susfs_add_open_redirect(arg);\n            return 0;\n        }\n#endif //#ifdef CONFIG_KSU_SUSFS_OPEN_REDIRECT\n#ifdef CONFIG_KSU_SUSFS_SUS_MAP\n        if (cmd == CMD_SUSFS_ADD_SUS_MAP) {\n            susfs_add_sus_map(arg);\n            return 0;\n        }\n#endif // #ifdef CONFIG_KSU_SUSFS_SUS_MAP\n        if (cmd == CMD_SUSFS_ENABLE_AVC_LOG_SPOOFING) {\n            susfs_set_avc_log_spoofing(arg);\n            return 0;\n        }\n        if (cmd == CMD_SUSFS_SHOW_ENABLED_FEATURES) {\n            susfs_get_enabled_features(arg);\n            return 0;\n        }\n        if (cmd == CMD_SUSFS_SHOW_VARIANT) {\n            susfs_show_variant(arg);\n            return 0;\n        }\n        if (cmd == CMD_SUSFS_SHOW_VERSION) {\n            susfs_show_version(arg);\n            return 0;\n        }\n        return 0;\n    }\n#endif // #ifdef CONFIG_KSU_SUSFS\n',
            section_context='int ksu_handle_sys_reboot(int magic1, int magic2, unsigned int cmd, void __user',
            context_before_count=3,
            context_after_count=3,
            context_before_offset=1,
            diff_body=(('+', '#ifdef CONFIG_KSU_DEBUG'), ('+', '\tpr_info("sys_reboot: intercepted call! magic: 0x%x id: %d\\n", magic1,'), ('+', '\t\tmagic2);'), ('+', '#endif'), ('+', ''), ('+', '#ifdef CONFIG_KSU_SUSFS'), ('+', '    // If magic2 is susfs and current process is root'), ('+', '    if (magic2 == SUSFS_MAGIC && current_uid().val == 0) {'), ('+', '#ifdef CONFIG_KSU_SUSFS_SUS_PATH'), ('+', '        if (cmd == CMD_SUSFS_ADD_SUS_PATH) {'), ('+', '            susfs_add_sus_path(arg);'), ('+', '            return 0;'), ('+', '        }'), ('+', '        if (cmd == CMD_SUSFS_ADD_SUS_PATH_LOOP) {'), ('+', '            susfs_add_sus_path_loop(arg);'), ('+', '            return 0;'), ('+', '        }'), ('+', '#endif //#ifdef CONFIG_KSU_SUSFS_SUS_PATH'), ('+', '#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT'), ('+', '        if (cmd == CMD_SUSFS_HIDE_SUS_MNTS_FOR_NON_SU_PROCS) {'), ('+', '            susfs_set_hide_sus_mnts_for_non_su_procs(arg);'), ('+', '            return 0;'), ('+', '        }'), ('+', '#endif //#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT'), ('+', '#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT'), ('+', '        if (cmd == CMD_SUSFS_ADD_SUS_KSTAT) {'), ('+', '            susfs_add_sus_kstat(arg);'), ('+', '            return 0;'), ('+', '        }'), ('+', '        if (cmd == CMD_SUSFS_UPDATE_SUS_KSTAT) {'), ('+', '            susfs_update_sus_kstat(arg);'), ('+', '            return 0;'), ('+', '        }'), ('+', '        if (cmd == CMD_SUSFS_ADD_SUS_KSTAT_STATICALLY) {'), ('+', '            susfs_add_sus_kstat(arg);'), ('+', '            return 0;'), ('+', '        }'), ('+', '#endif //#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT'), ('+', '#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT'), ('+', '        if (cmd == CMD_SUSFS_ADD_TRY_UMOUNT) {'), ('+', '            susfs_add_try_umount(arg);'), ('+', '            return 0;'), ('+', '        }'), ('+', '#endif //#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT'), ('+', '#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME'), ('+', '        if (cmd == CMD_SUSFS_SET_UNAME) {'), ('+', '            susfs_set_uname(arg);'), ('+', '            return 0;'), ('+', '        }'), ('+', '#endif //#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME'), ('+', '#ifdef CONFIG_KSU_SUSFS_ENABLE_LOG'), ('+', '        if (cmd == CMD_SUSFS_ENABLE_LOG) {'), ('+', '            susfs_enable_log(arg);'), ('+', '            return 0;'), ('+', '        }'), ('+', '#endif //#ifdef CONFIG_KSU_SUSFS_ENABLE_LOG'), ('+', '#ifdef CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG'), ('+', '        if (cmd == CMD_SUSFS_SET_CMDLINE_OR_BOOTCONFIG) {'), ('+', '            susfs_set_cmdline_or_bootconfig(arg);'), ('+', '            return 0;'), ('+', '        }'), ('+', '#endif //#ifdef CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG'), ('+', '#ifdef CONFIG_KSU_SUSFS_OPEN_REDIRECT'), ('+', '        if (cmd == CMD_SUSFS_ADD_OPEN_REDIRECT) {'), ('+', '            susfs_add_open_redirect(arg);'), ('+', '            return 0;'), ('+', '        }'), ('+', '#endif //#ifdef CONFIG_KSU_SUSFS_OPEN_REDIRECT'), ('+', '#ifdef CONFIG_KSU_SUSFS_SUS_MAP'), ('+', '        if (cmd == CMD_SUSFS_ADD_SUS_MAP) {'), ('+', '            susfs_add_sus_map(arg);'), ('+', '            return 0;'), ('+', '        }'), ('+', '#endif // #ifdef CONFIG_KSU_SUSFS_SUS_MAP'), ('+', '        if (cmd == CMD_SUSFS_ENABLE_AVC_LOG_SPOOFING) {'), ('+', '            susfs_set_avc_log_spoofing(arg);'), ('+', '            return 0;'), ('+', '        }'), ('+', '        if (cmd == CMD_SUSFS_SHOW_ENABLED_FEATURES) {'), ('+', '            susfs_get_enabled_features(arg);'), ('+', '            return 0;'), ('+', '        }'), ('+', '        if (cmd == CMD_SUSFS_SHOW_VARIANT) {'), ('+', '            susfs_show_variant(arg);'), ('+', '            return 0;'), ('+', '        }'), ('+', '        if (cmd == CMD_SUSFS_SHOW_VERSION) {'), ('+', '            susfs_show_version(arg);'), ('+', '            return 0;'), ('+', '        }'), ('+', '        return 0;'), ('+', '    }'), ('+', '#endif // #ifdef CONFIG_KSU_SUSFS')),
        ),
    )


_SPECS_BY_ID: Mapping[str, XxksuOperationSpec] = {
    s.operation_id: s for s in get_patch11_operation_specs()
}


class XxksuAdapter(TargetAdapter):
    """Target adapter for xxKSU source bundles."""

    def __init__(self) -> None:
        super().__init__()
        self.target_id = "xxksu"
        self.adapter_id = "xxksu"
        self.supported_kernel_families = ("common", "android")

    def build_adaptation_plan(self, bundle: SourceBundle) -> FixtureAdaptationPlan:
        """Resolve all 20 anchor locations against clean xxKSU files and construct adaptation plan."""
        if bundle.target_id != "xxksu":
            raise IncompatibleFixtureTarget(
                f"bundle target {bundle.target_id} is incompatible with xxksu adapter"
            )

        specs = get_patch11_operation_specs()
        operations: list[AdaptationOperation] = []
        by_file: dict[str, list[AdaptationOperation]] = {}

        for op_spec in specs:
            file_entry = bundle.get_file(op_spec.file_path)
            if file_entry.content is None:
                raise MissingBundleFile(f"file content for {op_spec.file_path} not present in bundle")

            loc = self.locate_anchor(file_entry.content, op_spec.spec)
            op = AdaptationOperation(
                operation_id=op_spec.operation_id,
                fixture_name=FIXTURE_PATCH11,
                file_path=op_spec.file_path,
                anchor_location=loc,
                placement=op_spec.placement,
                payload=op_spec.payload,
                target_id="xxksu",
                function=op_spec.function,
            )
            operations.append(op)
            by_file.setdefault(op_spec.file_path, []).append(op)

        # Validate that operations within each file do not overlap or conflict
        for file_path, file_ops in by_file.items():
            sorted_ops = sorted(
                file_ops,
                key=lambda o: (o.anchor_location.start_offset or 0, o.anchor_location.end_offset or 0),
            )
            for i in range(len(sorted_ops) - 1):
                cur = sorted_ops[i]
                nxt = sorted_ops[i + 1]
                cur_end = cur.anchor_location.end_offset or 0
                nxt_start = nxt.anchor_location.start_offset or 0
                if cur_end > nxt_start:
                    raise AnchorConflict(
                        f"overlapping mutation spans in {file_path}: "
                        f"{cur.operation_id} [{cur.anchor_location.start_offset}:{cur_end}] and "
                        f"{nxt.operation_id} [{nxt_start}:{nxt.anchor_location.end_offset}]"
                    )

        return FixtureAdaptationPlan(
            target_id="xxksu",
            bundle_identity=str(bundle.identity),
            operations=tuple(operations),
            metadata={"fixture": FIXTURE_PATCH11, "operation_count": len(operations)},
        )

    def apply_to_bundle(self, bundle: SourceBundle) -> SourceBundle:
        """Apply patch 11 adaptations to clean xxKSU source bundle."""
        plan = self.build_adaptation_plan(bundle)
        return plan.apply_to_bundle(bundle)

    def generate_patch11(self, bundle: SourceBundle) -> str:
        """Validate clean xxKSU bundle against all anchors and emit deterministic patch 11."""
        plan = self.build_adaptation_plan(bundle)
        by_file: dict[str, list[AdaptationOperation]] = {}
        for op in plan.operations:
            by_file.setdefault(op.file_path, []).append(op)

        file_patches: list[FilePatch] = []
        for file_path in PATCH11_CANONICAL_FILES:
            file_ops = by_file.get(file_path, [])
            if not file_ops:
                continue
            file_entry = bundle.get_file(file_path)
            clean_lines = [l.rstrip('\r\n') for l in file_entry.content.splitlines(keepends=True)]
            sorted_ops = sorted(
                file_ops,
                key=lambda o: (o.anchor_location.start_offset or 0, o.anchor_location.end_offset or 0),
            )

            hunks: list[Hunk] = []
            line_shift = 0
            for op in sorted_ops:
                spec = _SPECS_BY_ID[op.operation_id]
                loc = op.anchor_location

                ctx_before = spec.context_before_count
                ctx_after = spec.context_after_count
                body = spec.get_diff_body()

                old_start = max(1, loc.line_number - spec.context_before_offset)
                new_start = old_start + line_shift

                old_body_cnt = sum(1 for p, t in body if p in ("-", " "))
                old_count = ctx_before + old_body_cnt + ctx_after

                lines = []
                for i in range(old_start - 1, old_start - 1 + ctx_before):
                    lines.append(ContextLine(clean_lines[i]))
                for p, t in body:
                    if p == "+":
                        lines.append(AddedLine(t))
                    elif p == "-":
                        lines.append(RemovedLine(t))
                    elif p == " ":
                        lines.append(ContextLine(t))
                for i in range(old_start - 1 + old_count - ctx_after, old_start - 1 + old_count):
                    lines.append(ContextLine(clean_lines[i]))

                emitted_old = sum(isinstance(l, (ContextLine, RemovedLine)) for l in lines)
                emitted_new = sum(isinstance(l, (ContextLine, AddedLine)) for l in lines)
                hunk = Hunk(old_start, emitted_old, new_start, emitted_new, spec.section_context, lines)
                hunks.append(hunk)
                line_shift += (emitted_new - emitted_old)

            fp = FilePatch(
                diff_header=f"diff --git a/{file_path} b/{file_path}",
                old_path=f"a/{file_path}",
                new_path=f"b/{file_path}",
                index_line=PATCH11_FILE_INDEXES[file_path],
                old_header=f"--- a/{file_path}",
                new_header=f"+++ b/{file_path}",
                hunks=hunks,
            )
            file_patches.append(fp)

        patch = Patch(
            preamble=list(PATCH11_PREAMBLE),
            files=file_patches,
            trailer=list(PATCH11_TRAILER),
        )
        return emit_patch(patch)


def get_xxksu_adapter() -> XxksuAdapter:
    return XxksuAdapter()


def build_xxksu_adaptation_plan(bundle: SourceBundle) -> FixtureAdaptationPlan:
    adapter = XxksuAdapter()
    return adapter.build_adaptation_plan(bundle)


def apply_patch11_to_bundle(bundle: SourceBundle) -> SourceBundle:
    adapter = XxksuAdapter()
    return adapter.apply_to_bundle(bundle)


def generate_patch11(bundle: SourceBundle) -> str:
    adapter = XxksuAdapter()
    return adapter.generate_patch11(bundle)
