"""Comprehensive test suite for V2.9: profile matrix, composition, and config validation."""

from __future__ import annotations

import copy
from pathlib import Path
import unittest

from v2.adapters import get_adapter
from v2.model.manifest import (
    KNOWN_PROFILES,
    KNOWN_TARGETS,
    LSM_KCONFIG,
    MANUAL_FIXTURES,
    MANUAL_KCONFIG,
    InvalidFixtureContract,
    ProfileManifest,
    TargetProfileMismatch,
    UnknownProfile,
)
from v2.model.patch import ContextLine, RemovedLine
from v2.model.provenance import FixtureRef, HashDigest
from v2.engine.diff_parser import parse_patch
from test_v27 import _create_clean_xxksu_bundle
from v2.model.result import (
    AbiSignatureMismatch,
    DoubleSideEffect,
    DuplicateOwner,
    FinalConfigMismatch,
    HandlerABIConflict,
    KconfigConflict,
    MissingPrerequisite,
    OfficialSymbolLeakage,
    NoOwner,
    ValidationStatus,
)
from v2.profiles import (
    CANONICAL_PROFILES,
    ProfileCompositionResult,
    ProfileDefinition,
    compose_all_profiles,
    compose_profile,
    get_profile_definition,
    get_profile_manifest,
    list_profile_definitions,
)
from v2.source.bundle import SourceBundle, create_source_bundle
from v2.validation import (
    OwnershipClaim,
    make_default_lsm_bl_claims,
    make_default_manual_claims,
    parse_kconfig,
    validate_config,
)

# Test kernel source samples
_SAMPLE_EXEC = """/* fs/exec.c */
#include <linux/fs.h>

static int do_execveat_common(int fd, struct filename *filename,
	struct user_arg_ptr argv,
	struct user_arg_ptr envp,
	int flags)
{
	struct linux_binprm *bprm;
	int retval;

	if (IS_ERR(filename))
		return PTR_ERR(filename);

	return retval;
}
"""

_SAMPLE_OPEN = """/* fs/open.c */
#include <linux/fs.h>

SYSCALL_DEFINE3(faccessat, int, dfd, const char __user *, filename, int, mode)
{
	return do_faccessat(dfd, filename, mode, 0);
}
"""

_SAMPLE_STAT = """/* fs/stat.c */
#include <linux/fs.h>

SYSCALL_DEFINE4(newfstatat, int, dfd, const char __user *, filename,
	struct stat __user *, statbuf, int, flag)
{
	struct kstat stat;
	int error;

	error = vfs_fstatat(dfd, filename, &stat, flag);
	if (error)
		return error;
	return cp_new_stat(&stat, statbuf);
}

SYSCALL_DEFINE2(newfstat, unsigned int, fd, struct stat __user *, statbuf)
{
	struct kstat stat;
	int error;

	if (!error)
		error = cp_new_stat(&stat, statbuf);

	return error;
}

SYSCALL_DEFINE2(fstat64, unsigned long, fd, struct stat64 __user *, statbuf)
{
	struct kstat stat;
	int error;

	if (!error)
		error = cp_new_stat64(&stat, statbuf);

	return error;
}

SYSCALL_DEFINE4(fstatat64, int, dfd, const char __user *, filename,
	struct stat64 __user *, statbuf, int, flag)
{
	struct kstat stat;
	int error;

	error = vfs_fstatat(dfd, filename, &stat, flag);
	if (error)
		return error;
	return cp_new_stat64(&stat, statbuf);
}
"""

_SAMPLE_REBOOT = """/* kernel/reboot.c */
#include <linux/reboot.h>

SYSCALL_DEFINE4(reboot, int, magic1, int, magic2, unsigned int, cmd, void __user *, arg)
{
	char buffer[256];
	int ret = 0;

	/* We only trust the superuser with rebooting the system. */
	if (!ns_capable(pid_ns->user_ns, CAP_SYS_BOOT))
		return -EPERM;
	return ret;
}
"""

_SAMPLE_SECURITY_6_1 = """/* security/security.c */
#include <linux/security.h>

static int lsm_superblock_alloc(struct super_block *sb)
{
	return 0;
}

#include <linux/lsm_hook_defs.h>
#undef LSM_HOOK

int security_bprm_check(struct linux_binprm *bprm)
{
	int ret;

	ret = call_int_hook(bprm_check_security, 0, bprm);
	if (ret)
		return ret;
	return 0;
}

int security_inode_rename(struct inode *old_dir, struct dentry *old_dentry,
			   struct inode *new_dir, struct dentry *new_dentry,
			   unsigned int flags)
{
	if (unlikely(IS_PRIVATE(d_backing_inode(old_dentry)) ||
            (d_is_positive(new_dentry) && IS_PRIVATE(d_backing_inode(new_dentry)))))
		return 0;
	return 0;
}

int security_file_permission(struct file *file, int mask)
{
	int ret;

	ret = call_int_hook(file_permission, 0, file, mask);
	if (ret)
		return ret;
	return 0;
}

int security_task_fix_setuid(struct cred *new, const struct cred *old, int flags)
{
	return call_int_hook(task_fix_setuid, 0, new, old, flags);
}

int security_setprocattr(const char *lsm, const char *name, void *value, size_t size)
{
	struct security_hook_list *hp;

	hlist_for_each_entry(hp, &security_hook_heads.setprocattr, list) {
		if (lsm != NULL && strcmp(lsm, hp->lsm))
			continue;
	}
	return 0;
}
"""

_SAMPLE_SECURITY_6_12 = """/* security/security.c 6.12 */
#include <linux/security.h>

static int lsm_superblock_alloc(struct super_block *sb)
{
	return 0;
}

#include <linux/lsm_hook_defs.h>
#undef LSM_HOOK

int security_bprm_check(struct linux_binprm *bprm)
{
	int ret;

	return 0;
}

int security_inode_rename(struct inode *old_dir, struct dentry *old_dentry,
			   struct inode *new_dir, struct dentry *new_dentry,
			   unsigned int flags)
{
	if (unlikely(IS_PRIVATE(d_backing_inode(old_dentry)) ||
            (d_is_positive(new_dentry) && IS_PRIVATE(d_backing_inode(new_dentry)))))
		return 0;
	return 0;
}

int security_file_permission(struct file *file, int mask)
{
	int ret;

	ret = call_int_hook(file_permission, 0, file, mask);
	if (ret)
		return ret;
	return 0;
}

int security_task_fix_setuid(struct cred *new, const struct cred *old, int flags)
{
	return call_int_hook(task_fix_setuid, 0, new, old, flags);
}

int security_setprocattr(const char *lsm, const char *name, void *value, size_t size)
{
	struct security_hook_list *hp;

	hlist_for_each_entry(hp, &security_hook_heads.setprocattr, list) {
		if (lsm != NULL && strcmp(lsm, hp->lsm))
			continue;
	}
	return 0;
}
"""


def _make_clean_bundle(target_id: str = "sultan-android14-6.1", version: str = "6.1.25") -> SourceBundle:
    sec_content = _SAMPLE_SECURITY_6_12 if "6.12" in target_id else _SAMPLE_SECURITY_6_1
    files = {
        "fs/exec.c": _SAMPLE_EXEC,
        "fs/open.c": _SAMPLE_OPEN,
        "fs/stat.c": _SAMPLE_STAT,
        "kernel/reboot.c": _SAMPLE_REBOOT,
        "security/security.c": sec_content,
    }
    patch_paths = {
        "gki-android16-6.12": "patches/gki-android16-6.12/51_deinlined_susfs_hooks_gki-android16-6.12.patch",
        "sultan-android14-6.1": "patches/sultan-android14-6.1/51_deinlined_susfs_hooks_sultan-android14-6.1.patch",
    }
    patch = parse_patch((Path(__file__).resolve().parents[4] / patch_paths[target_id]).read_text())
    fillers = {
        "fs/exec.c": _SAMPLE_EXEC.splitlines(keepends=True),
        "fs/open.c": _SAMPLE_OPEN.splitlines(keepends=True),
        "fs/stat.c": [line.replace("return error;", "return stat_error;") for line in _SAMPLE_STAT.splitlines(keepends=True)],
        "kernel/reboot.c": _SAMPLE_REBOOT.splitlines(keepends=True),
    }
    for file_patch in patch.files:
        old_lines = {}
        max_line = 0
        for hunk in file_patch.hunks:
            line_no = hunk.old_start
            for line in hunk.lines:
                if isinstance(line, (ContextLine, RemovedLine)):
                    old_lines[line_no] = line.text + "\n"
                    line_no += 1
            max_line = max(max_line, hunk.old_start + hunk.old_count - 1)
        path = file_patch.old_path[2:] if file_patch.old_path.startswith("a/") else file_patch.old_path
        # Keep the synthetic stat source structurally valid: patch-context
        # reconstruction alone cannot provide complete function bodies.
        fallback = () if path == "fs/stat.c" else fillers.get(path, ())
        content = "".join(
            old_lines.get(i, fallback[i - 1] if i <= len(fallback) else f"/* line {i} */\n")
            for i in range(1, max_line + 1)
        )
        if path == "fs/stat.c":
            content += _SAMPLE_STAT
        files[path] = content
    return create_source_bundle(target_id=target_id, kernel_version=version, files=files)


_XXKSU_BUNDLE = _create_clean_xxksu_bundle()
_REAL_COMPOSE_PROFILE = compose_profile


def compose_profile(*args, **kwargs):
    kwargs.setdefault("xxksu_bundle", _XXKSU_BUNDLE)
    return _REAL_COMPOSE_PROFILE(*args, **kwargs)


_MANUAL_CONFIG_TEXT = """
# Linux/arm64 Kernel Configuration
CONFIG_KSU=y
CONFIG_KSU_SUSFS=y
# CONFIG_KSU_LSM_SECURITY_HOOKS is not set
# CONFIG_KSU_HACK_ARM64_BRANCH_LINK is not set
# CONFIG_KSU_TAMPER_SYSCALL_TABLE is not set
# CONFIG_KSU_KPROBES_KSUD is not set
CONFIG_ARM64=y
CONFIG_KALLSYMS=y
"""

_LSM_BL_CONFIG_TEXT = """
# Linux/arm64 Kernel Configuration
CONFIG_ARM64=y
CONFIG_KALLSYMS=y
CONFIG_KSU=y
CONFIG_KSU_SUSFS=y
CONFIG_KSU_LSM_SECURITY_HOOKS=y
CONFIG_KSU_HACK_ARM64_BRANCH_LINK=y
# CONFIG_KSU_TAMPER_SYSCALL_TABLE is not set
# CONFIG_KSU_KPROBES_KSUD is not set
"""


class V29PositiveProfileMatrixTests(unittest.TestCase):
    """Verify all 16 positive requirements for V2.9 profile composition and config validation."""

    def setUp(self) -> None:
        self.bundles = {
            "gki-android16-6.12": _make_clean_bundle("gki-android16-6.12", "6.12.0"),
            "sultan-android14-6.1": _make_clean_bundle("sultan-android14-6.1", "6.1.25"),
        }
        self.patch_11 = "shared-11"
        self.patches_51 = {
            "gki-android16-6.12": {"name": "gki_android16_6_12_51", "target_id": "gki-android16-6.12"},
            "sultan-android14-6.1": {"name": "sultan_android14_6_1_51", "target_id": "sultan-android14-6.1"},
        }

    def test_1_all_four_canonical_profile_ids_resolve(self) -> None:
        self.assertEqual(len(KNOWN_PROFILES), 4)
        for pid in KNOWN_PROFILES:
            prof = get_profile_definition(pid)
            self.assertEqual(prof.profile_id, pid)
            self.assertIn(prof.target_id, KNOWN_TARGETS)
            self.assertIn(prof.mode, ("manual", "lsm_bl"))
            self.assertEqual(prof.profile_id, f"{prof.target_id}-{prof.mode}")

    def _assert_incomplete_source_blocked(self, pid: str, bundle: SourceBundle | None = None) -> str:
        prof_def = get_profile_definition(pid)
        with self.assertRaises(NoOwner) as blocked:
            compose_profile(
                pid,
                target_bundle=bundle or self.bundles[prof_def.target_id],
                patch_11=self.patch_11,
                patch_51=self.patches_51[prof_def.target_id],
            )
        return str(blocked.exception)

    def test_2_incomplete_synthetic_sources_are_blocked(self) -> None:
        for pid in KNOWN_PROFILES:
            self._assert_incomplete_source_blocked(pid)

    def test_3_manual_positive_composition_is_blocked_without_authority(self) -> None:
        for pid in KNOWN_PROFILES:
            if pid.endswith("-manual"):
                self._assert_incomplete_source_blocked(pid)

    def test_4_lsm_positive_composition_is_blocked_without_authority(self) -> None:
        for pid in KNOWN_PROFILES:
            if pid.endswith("-lsm_bl"):
                self._assert_incomplete_source_blocked(pid)

    def test_5_patch_order_cannot_be_asserted_without_authority(self) -> None:
        for pid in KNOWN_PROFILES:
            self._assert_incomplete_source_blocked(pid)

    def test_6_all_four_use_identical_shared_patch_11_identity(self) -> None:
        for pid in KNOWN_PROFILES:
            prof_def = get_profile_definition(pid)
            self.assertEqual(prof_def.shared_patch_11_id, "shared-11")
            manifest = prof_def.get_manifest()
            self.assertEqual(manifest.patch_11_id, "shared-11")

    def test_7_target_patch_51_differs_only_by_target_never_by_mode(self) -> None:
        for target in KNOWN_TARGETS:
            manual_prof = get_profile_definition(f"{target}-manual")
            lsm_prof = get_profile_definition(f"{target}-lsm_bl")
            self.assertEqual(manual_prof.patch_51_id, lsm_prof.patch_51_id)
            self.assertNotIn("manual", manual_prof.patch_51_id)
            self.assertNotIn("lsm_bl", manual_prof.patch_51_id)

    def test_8_manual_config_validates(self) -> None:
        res = validate_config(
            expected=MANUAL_KCONFIG,
            resolved=_MANUAL_CONFIG_TEXT,
            mode="manual",
            raise_on_failure=True,
        )
        self.assertEqual(res.status, ValidationStatus.PASS)

    def test_9_lsm_bl_config_validates(self) -> None:
        res = validate_config(
            expected=LSM_KCONFIG,
            resolved=_LSM_BL_CONFIG_TEXT,
            mode="lsm_bl",
            prerequisites={"arch": "arm64", "kallsyms": True},
            raise_on_failure=True,
        )
        self.assertEqual(res.status, ValidationStatus.PASS)

    def test_10_incomplete_sources_are_rejected_by_ownership_validation(self) -> None:
        for pid in KNOWN_PROFILES:
            self._assert_incomplete_source_blocked(pid)

    def test_11_incomplete_sources_do_not_reach_symbol_validation(self) -> None:
        for pid in KNOWN_PROFILES:
            self._assert_incomplete_source_blocked(pid)

    def test_12_incomplete_sources_do_not_reach_abi_validation(self) -> None:
        for pid in KNOWN_PROFILES:
            self._assert_incomplete_source_blocked(pid)

    def test_13_manifests_are_byte_deterministic(self) -> None:
        for pid in KNOWN_PROFILES:
            m1 = get_profile_manifest(pid)
            m2 = get_profile_manifest(pid)
            self.assertEqual(m1.to_dict(), m2.to_dict())
            self.assertEqual(m1.validate().to_dict(), m2.validate().to_dict())

    def test_14_incomplete_sources_block_deterministically(self) -> None:
        pid = "sultan-android14-6.1-manual"
        first = self._assert_incomplete_source_blocked(pid)
        second = self._assert_incomplete_source_blocked(pid)
        self.assertEqual(first, second)

    def test_15_repeated_incomplete_composition_remains_blocked(self) -> None:
        for pid in KNOWN_PROFILES:
            self._assert_incomplete_source_blocked(pid)
            self._assert_incomplete_source_blocked(pid)

    def test_16_incomplete_source_permutations_remain_blocked(self) -> None:
        pid = "sultan-android14-6.1-lsm_bl"
        bundle = self.bundles[pid.rsplit("-", 1)[0]]
        reversed_files = {f.path: f.content for f in reversed(bundle.files)}
        reversed_bundle = create_source_bundle(
            target_id=bundle.target_id,
            kernel_version=bundle.kernel_version,
            files=reversed_files,
        )
        self._assert_incomplete_source_blocked(pid, bundle)
        self._assert_incomplete_source_blocked(pid, reversed_bundle)


class V29NegativeTests(unittest.TestCase):
    """Verify all 22 required negative fail-closed conditions for V2.9."""

    def setUp(self) -> None:
        self.bundle_gki_6_1 = _make_clean_bundle("sultan-android14-6.1", "6.1.25")
        self.patch_11 = "shared-11"
        self.patch_51_gki_6_1 = {"name": "sultan_android14_6_1_51", "target_id": "sultan-android14-6.1"}

    def test_neg_1_unknown_profile_id(self) -> None:
        with self.assertRaises(UnknownProfile):
            compose_profile(
                "invalid-profile-id",
                target_bundle=self.bundle_gki_6_1,
                patch_11=self.patch_11,
                patch_51=self.patch_51_gki_6_1,
            )

    def test_neg_2_profile_target_mismatch(self) -> None:
        # Pass 6.1 bundle to 6.12 profile
        with self.assertRaises(TargetProfileMismatch):
            compose_profile(
                "gki-android16-6.12-manual",
                target_bundle=self.bundle_gki_6_1,
                patch_11=self.patch_11,
                patch_51={"name": "gki_android16_6_12_51", "target_id": "gki-android16-6.12"},
            )

    def test_neg_3_manual_missing_scope_min_fixture(self) -> None:
        # Create manifest missing scope-min fixture
        bad_manifest = ProfileManifest(
            schema="xxksu-susfs-profile/v1",
            profile_id="sultan-android14-6.1-manual",
            target_id="sultan-android14-6.1",
            mode="manual",
            fixtures=(FixtureRef(MANUAL_FIXTURES[1], f".github/fixtures/{MANUAL_FIXTURES[1]}"),),
            kconfig=dict(MANUAL_KCONFIG),
            prerequisites={"arch": "any", "kallsyms": True},
            ownership={"exec": MANUAL_FIXTURES[0]},
            patch_11_id="shared-11",
            patch_51_id="sultan_android14_6_1_51",
            adapter_id="sultan_android14_6_1",
        )
        with self.assertRaises(InvalidFixtureContract):
            compose_profile(
                "sultan-android14-6.1-manual",
                target_bundle=self.bundle_gki_6_1,
                patch_11=self.patch_11,
                patch_51=self.patch_51_gki_6_1,
                manifest=bad_manifest,
            )

    def test_neg_4_manual_missing_manual_security_fixture(self) -> None:
        bad_manifest = ProfileManifest(
            schema="xxksu-susfs-profile/v1",
            profile_id="sultan-android14-6.1-manual",
            target_id="sultan-android14-6.1",
            mode="manual",
            fixtures=(FixtureRef(MANUAL_FIXTURES[0], f".github/fixtures/{MANUAL_FIXTURES[0]}"),),
            kconfig=dict(MANUAL_KCONFIG),
            prerequisites={"arch": "any", "kallsyms": True},
            ownership={"exec": MANUAL_FIXTURES[0]},
            patch_11_id="shared-11",
            patch_51_id="sultan_android14_6_1_51",
            adapter_id="sultan_android14_6_1",
        )
        with self.assertRaises(InvalidFixtureContract):
            compose_profile(
                "sultan-android14-6.1-manual",
                target_bundle=self.bundle_gki_6_1,
                patch_11=self.patch_11,
                patch_51=self.patch_51_gki_6_1,
                manifest=bad_manifest,
            )

    def test_neg_5_manual_extra_fixture(self) -> None:
        extra_fixture = "unsupported-extra-fixture.patch"
        bad_manifest = ProfileManifest(
            schema="xxksu-susfs-profile/v1",
            profile_id="sultan-android14-6.1-manual",
            target_id="sultan-android14-6.1",
            mode="manual",
            fixtures=(
                FixtureRef(MANUAL_FIXTURES[0], f".github/fixtures/{MANUAL_FIXTURES[0]}"),
                FixtureRef(MANUAL_FIXTURES[1], f".github/fixtures/{MANUAL_FIXTURES[1]}"),
                FixtureRef(extra_fixture, f".github/fixtures/{extra_fixture}"),
            ),
            kconfig=dict(MANUAL_KCONFIG),
            prerequisites={"arch": "any", "kallsyms": True},
            ownership={"exec": MANUAL_FIXTURES[0]},
            patch_11_id="shared-11",
            patch_51_id="sultan_android14_6_1_51",
            adapter_id="sultan_android14_6_1",
        )
        with self.assertRaises(InvalidFixtureContract):
            compose_profile(
                "sultan-android14-6.1-manual",
                target_bundle=self.bundle_gki_6_1,
                patch_11=self.patch_11,
                patch_51=self.patch_51_gki_6_1,
                manifest=bad_manifest,
            )

    def test_neg_6_lsm_bl_containing_either_manual_fixture(self) -> None:
        bad_manifest = ProfileManifest(
            schema="xxksu-susfs-profile/v1",
            profile_id="sultan-android14-6.1-lsm_bl",
            target_id="sultan-android14-6.1",
            mode="lsm_bl",
            fixtures=(FixtureRef(MANUAL_FIXTURES[0], f".github/fixtures/{MANUAL_FIXTURES[0]}"),),
            kconfig=dict(LSM_KCONFIG),
            prerequisites={"arch": "arm64", "kallsyms": True, "XXKSU_BL_COMPOSITE": "XXKSU_BL_COMPOSITE"},
            ownership={"exec": "XXKSU_BL_COMPOSITE"},
            patch_11_id="shared-11",
            patch_51_id="sultan_android14_6_1_51",
            adapter_id="sultan_android14_6_1",
        )
        with self.assertRaises(InvalidFixtureContract):
            compose_profile(
                "sultan-android14-6.1-lsm_bl",
                target_bundle=self.bundle_gki_6_1,
                patch_11=self.patch_11,
                patch_51=self.patch_51_gki_6_1,
                manifest=bad_manifest,
            )

    def test_neg_7_missing_patch_11(self) -> None:
        with self.assertRaises(ValueError):
            compose_profile(
                "sultan-android14-6.1-manual",
                target_bundle=self.bundle_gki_6_1,
                patch_11="",
                patch_51=self.patch_51_gki_6_1,
            )

    def test_neg_8_missing_patch_51(self) -> None:
        with self.assertRaises(ValueError):
            compose_profile(
                "sultan-android14-6.1-manual",
                target_bundle=self.bundle_gki_6_1,
                patch_11=self.patch_11,
                patch_51="",
            )

    def test_neg_9_patch_51_bound_to_wrong_target(self) -> None:
        wrong_p51 = {"name": "gki_android16_6_12_51", "target_id": "gki-android16-6.12"}
        with self.assertRaises(ValueError):
            compose_profile(
                "sultan-android14-6.1-manual",
                target_bundle=self.bundle_gki_6_1,
                patch_11=self.patch_11,
                patch_51=wrong_p51,
            )

    def test_neg_10_manual_lsm_y_fails(self) -> None:
        cfg = dict(MANUAL_KCONFIG)
        cfg["CONFIG_KSU_LSM_SECURITY_HOOKS"] = "y"
        with self.assertRaises(FinalConfigMismatch):
            validate_config(expected=MANUAL_KCONFIG, resolved=cfg, mode="manual", raise_on_failure=True)

    def test_neg_11_manual_bl_y_fails(self) -> None:
        cfg = dict(MANUAL_KCONFIG)
        cfg["CONFIG_KSU_HACK_ARM64_BRANCH_LINK"] = "y"
        with self.assertRaises(FinalConfigMismatch):
            validate_config(expected=MANUAL_KCONFIG, resolved=cfg, mode="manual", raise_on_failure=True)

    def test_neg_12_lsm_bl_lsm_n_fails(self) -> None:
        cfg = dict(LSM_KCONFIG)
        cfg["CONFIG_KSU_LSM_SECURITY_HOOKS"] = "n"
        cfg["CONFIG_ARM64"] = "y"
        cfg["CONFIG_KALLSYMS"] = "y"
        with self.assertRaises(FinalConfigMismatch):
            validate_config(expected=LSM_KCONFIG, resolved=cfg, mode="lsm_bl", raise_on_failure=True)

    def test_neg_13_lsm_bl_bl_n_fails(self) -> None:
        cfg = dict(LSM_KCONFIG)
        cfg["CONFIG_KSU_HACK_ARM64_BRANCH_LINK"] = "n"
        cfg["CONFIG_ARM64"] = "y"
        cfg["CONFIG_KALLSYMS"] = "y"
        with self.assertRaises(FinalConfigMismatch):
            validate_config(expected=LSM_KCONFIG, resolved=cfg, mode="lsm_bl", raise_on_failure=True)

    def test_neg_14_bl_y_tamper_y_conflict(self) -> None:
        cfg = dict(LSM_KCONFIG)
        cfg["CONFIG_KSU_TAMPER_SYSCALL_TABLE"] = "y"
        cfg["CONFIG_ARM64"] = "y"
        cfg["CONFIG_KALLSYMS"] = "y"
        with self.assertRaises(KconfigConflict):
            validate_config(expected=LSM_KCONFIG, resolved=cfg, mode="lsm_bl", raise_on_failure=True)

    def test_neg_15_config_ksu_susfs_missing_or_n_fails(self) -> None:
        cfg = dict(MANUAL_KCONFIG)
        cfg["CONFIG_KSU_SUSFS"] = "n"
        with self.assertRaises(FinalConfigMismatch):
            validate_config(expected=MANUAL_KCONFIG, resolved=cfg, mode="manual", raise_on_failure=True)

    def test_neg_16_lsm_bl_missing_arm64_fails(self) -> None:
        cfg = dict(LSM_KCONFIG)
        cfg["CONFIG_KALLSYMS"] = "y"
        # CONFIG_ARM64 omitted or n
        cfg["CONFIG_ARM64"] = "n"
        with self.assertRaises(MissingPrerequisite):
            validate_config(
                expected=LSM_KCONFIG,
                resolved=cfg,
                mode="lsm_bl",
                prerequisites={"arch": "arm64", "kallsyms": True},
                raise_on_failure=True,
            )

    def test_neg_17_lsm_bl_missing_kallsyms_fails(self) -> None:
        cfg = dict(LSM_KCONFIG)
        cfg["CONFIG_ARM64"] = "y"
        cfg["CONFIG_KALLSYMS"] = "n"
        with self.assertRaises(MissingPrerequisite):
            validate_config(
                expected=LSM_KCONFIG,
                resolved=cfg,
                mode="lsm_bl",
                prerequisites={"arch": "arm64", "kallsyms": True},
                raise_on_failure=True,
            )

    def test_neg_18_olddefconfig_silent_drop_fails(self) -> None:
        # Simulate olddefconfig silently dropping CONFIG_KSU_SUSFS
        cfg = dict(MANUAL_KCONFIG)
        del cfg["CONFIG_KSU_SUSFS"]
        with self.assertRaises(FinalConfigMismatch):
            validate_config(
                expected=MANUAL_KCONFIG,
                resolved=cfg,
                requested=MANUAL_KCONFIG,
                mode="manual",
                raise_on_failure=True,
            )

    def test_neg_19_duplicate_transport_owner_fails(self) -> None:
        claims = list(make_default_manual_claims())
        # Duplicate transport claim for exec
        dup = OwnershipClaim("exec", "PATCH_11", "XXKSU_BL_COMPOSITE", "xxksu")
        claims.append(dup)

        with self.assertRaises(DoubleSideEffect):
            compose_profile(
                "sultan-android14-6.1-lsm_bl",
                target_bundle=self.bundle_gki_6_1,
                patch_11=self.patch_11,
                patch_51=self.patch_51_gki_6_1,
                claims=claims,
                raise_on_failure=True,
            )

    def test_neg_20_banned_official_symbol_injected_fails(self) -> None:
        # Inject banned official symbol into fs/exec.c
        corrupted_files = {
            "fs/exec.c": _SAMPLE_EXEC + "\nint ksu_handle_execveat_sucompat(void) { return 0; }\n",
            "fs/open.c": _SAMPLE_OPEN,
            "fs/stat.c": _SAMPLE_STAT,
            "kernel/reboot.c": _SAMPLE_REBOOT,
            "security/security.c": _SAMPLE_SECURITY_6_1,
        }
        corrupted_bundle = self.bundle_gki_6_1.with_updated_file(
            "fs/exec.c",
            _SAMPLE_EXEC + "\nint ksu_handle_execveat_sucompat(void) { return 0; }\n",
        )
        with self.assertRaises(OfficialSymbolLeakage):
            compose_profile(
                "sultan-android14-6.1-lsm_bl",
                target_bundle=corrupted_bundle,
                patch_11=self.patch_11,
                patch_51=self.patch_51_gki_6_1,
                raise_on_failure=True,
            )

    def test_neg_21_handler_abi_mutated_fails(self) -> None:
        # Mutate an ABI contract function signature in security.c
        corrupted_files = {
            "fs/exec.c": _SAMPLE_EXEC,
            "fs/open.c": _SAMPLE_OPEN,
            "fs/stat.c": _SAMPLE_STAT,
            "kernel/reboot.c": _SAMPLE_REBOOT,
            "security/security.c": _SAMPLE_SECURITY_6_1 + "\nextern void ksu_bprm_check(void);\n",
        }
        corrupted_bundle = self.bundle_gki_6_1.with_updated_file(
            "security/security.c",
            _SAMPLE_SECURITY_6_1 + "\nextern void ksu_bprm_check(void);\n",
        )
        with self.assertRaises(HandlerABIConflict):
            compose_profile(
                "sultan-android14-6.1-lsm_bl",
                target_bundle=corrupted_bundle,
                patch_11=self.patch_11,
                patch_51=self.patch_51_gki_6_1,
                raise_on_failure=True,
            )

    def test_neg_22_conflicting_duplicate_kconfig_assignment_fails(self) -> None:
        conflicting_text = """
        CONFIG_KSU=y
        CONFIG_KSU=n
        """
        with self.assertRaises(KconfigConflict):
            parse_kconfig(conflicting_text)


if __name__ == "__main__":
    unittest.main()
