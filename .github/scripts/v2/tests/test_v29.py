"""Comprehensive test suite for V2.9: profile matrix, composition, and config validation."""

from __future__ import annotations

import copy
from pathlib import Path
import unittest
from test_lifecycle import target_sources
from unittest.mock import patch

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
from v2.source.baseline import load_authoritative_bundle
from v2.source.bundle import SourceBundle, create_source_bundle

REPO_ROOT = Path(__file__).resolve().parents[4]
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

_SAMPLE_SECURITY_6_1 = target_sources(False)["security/security.c"]

_SAMPLE_SECURITY_6_12 = target_sources(True)["security/security.c"]


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
        "gki-android16-6.12": "patches/gki-android16-6.12/51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch",
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
        files[path] = sec_content if path == "security/security.c" else content
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
    """Profile identity, configuration, and exact missing-owner rejection."""

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

    def test_profile_identity_matrix(self):
        with self.subTest(case='1_all_four_canonical_profile_ids_resolve'):
            self.assertEqual(len(KNOWN_PROFILES), 4)
            for pid in KNOWN_PROFILES:
                prof = get_profile_definition(pid)
                self.assertEqual(prof.profile_id, pid)
                self.assertIn(prof.target_id, KNOWN_TARGETS)
                self.assertIn(prof.mode, ("manual", "lsm_bl"))
                self.assertEqual(prof.profile_id, f"{prof.target_id}-{prof.mode}")
        with self.subTest(case='6_all_four_use_identical_shared_patch_11_identity'):
            for pid in KNOWN_PROFILES:
                prof_def = get_profile_definition(pid)
                self.assertEqual(prof_def.shared_patch_11_id, "shared-11")
                manifest = prof_def.get_manifest()
                self.assertEqual(manifest.patch_11_id, "shared-11")
        with self.subTest(case='7_target_patch_51_differs_only_by_target_never_by_mode'):
            for target in KNOWN_TARGETS:
                manual_prof = get_profile_definition(f"{target}-manual")
                lsm_prof = get_profile_definition(f"{target}-lsm_bl")
                self.assertEqual(manual_prof.patch_51_id, lsm_prof.patch_51_id)
                self.assertNotIn("manual", manual_prof.patch_51_id)
                self.assertNotIn("lsm_bl", manual_prof.patch_51_id)
        with self.subTest(case='13_manifests_are_byte_deterministic'):
            for pid in KNOWN_PROFILES:
                m1 = get_profile_manifest(pid)
                m2 = get_profile_manifest(pid)
                self.assertEqual(m1.to_dict(), m2.to_dict())
                self.assertEqual(m1.validate().to_dict(), m2.validate().to_dict())

    def _assert_incomplete_source_blocked(self, pid: str, bundle: SourceBundle | None = None) -> str:
        prof_def = get_profile_definition(pid)
        target_bundle = bundle or self.bundles[prof_def.target_id]

        # Composition is not the publication authentication gate. Exercise its
        # actual missing-owner rejection, including the returned report state.
        kwargs = dict(target_bundle=target_bundle, patch_11=self.patch_11,
                      patch_51=self.patches_51[prof_def.target_id], claims=())
        from v2.validation import validate_symbols, validate_abi
        with patch("v2.validation.validate_symbols", wraps=validate_symbols) as symbols, \
             patch("v2.validation.validate_abi", wraps=validate_abi) as abi:
            res = compose_profile(pid, **kwargs, raise_on_failure=False)
        self.assertEqual(res.validation_report.status, ValidationStatus.FAIL)
        failures = [r for r in res.validation_report.results if r.status == ValidationStatus.FAIL]
        self.assertTrue(failures)
        self.assertTrue(all(r.validator_id.startswith("validation.ownership") for r in failures))
        self.assertTrue(any(r.metadata.get("error_type") == "NoOwner" for r in failures))
        self.assertTrue(symbols.called)
        self.assertTrue(abi.called)
        with self.assertRaises(NoOwner):
            compose_profile(pid, **kwargs, raise_on_failure=True)
        return str(res.digest)

    def test_2_incomplete_synthetic_sources_are_blocked(self) -> None:
        for pid in KNOWN_PROFILES:
            self._assert_incomplete_source_blocked(pid)


    def test_valid_config_modes(self):
        with self.subTest(case='8_manual_config_validates'):
            res = validate_config(
                expected=MANUAL_KCONFIG,
                resolved=_MANUAL_CONFIG_TEXT,
                mode="manual",
                raise_on_failure=True,
            )
            self.assertEqual(res.status, ValidationStatus.PASS)
        with self.subTest(case='9_lsm_bl_config_validates'):
            res = validate_config(
                expected=LSM_KCONFIG,
                resolved=_LSM_BL_CONFIG_TEXT,
                mode="lsm_bl",
                prerequisites={"arch": "arm64", "kallsyms": True},
                raise_on_failure=True,
            )
            self.assertEqual(res.status, ValidationStatus.PASS)


class V29NegativeTests(unittest.TestCase):
    """Fail-closed profile, fixture, configuration, and validation cases."""

    def setUp(self) -> None:
        self.bundle_sultan = _make_clean_bundle("sultan-android14-6.1", "6.1.25")
        self.patch_11 = "shared-11"
        self.patch_51_sultan = {"name": "sultan_android14_6_1_51", "target_id": "sultan-android14-6.1"}

    def test_neg_1_unknown_profile_id(self) -> None:
        with self.assertRaises(UnknownProfile):
            compose_profile(
                "invalid-profile-id",
                target_bundle=self.bundle_sultan,
                patch_11=self.patch_11,
                patch_51=self.patch_51_sultan,
            )

    def test_neg_2_profile_target_mismatch(self) -> None:
        # Pass 6.1 bundle to 6.12 profile
        with self.assertRaises(TargetProfileMismatch):
            compose_profile(
                "gki-android16-6.12-manual",
                target_bundle=self.bundle_sultan,
                patch_11=self.patch_11,
                patch_51={"name": "gki_android16_6_12_51", "target_id": "gki-android16-6.12"},
            )

    def test_invalid_fixture_sets(self):
        with self.subTest(case='neg_3_manual_missing_scope_min_fixture'):
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
                    target_bundle=self.bundle_sultan,
                    patch_11=self.patch_11,
                    patch_51=self.patch_51_sultan,
                    manifest=bad_manifest,
                )
        with self.subTest(case='neg_4_manual_missing_manual_security_fixture'):
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
                    target_bundle=self.bundle_sultan,
                    patch_11=self.patch_11,
                    patch_51=self.patch_51_sultan,
                    manifest=bad_manifest,
                )
        with self.subTest(case='neg_5_manual_extra_fixture'):
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
                    target_bundle=self.bundle_sultan,
                    patch_11=self.patch_11,
                    patch_51=self.patch_51_sultan,
                    manifest=bad_manifest,
                )
        with self.subTest(case='neg_6_lsm_bl_containing_either_manual_fixture'):
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
                    target_bundle=self.bundle_sultan,
                    patch_11=self.patch_11,
                    patch_51=self.patch_51_sultan,
                    manifest=bad_manifest,
                )


    def test_missing_patch_inputs(self):
        with self.subTest(case='neg_7_missing_patch_11'):
            with self.assertRaises(ValueError):
                compose_profile(
                    "sultan-android14-6.1-manual",
                    target_bundle=self.bundle_sultan,
                    patch_11="",
                    patch_51=self.patch_51_sultan,
                )
        with self.subTest(case='neg_8_missing_patch_51'):
            with self.assertRaises(ValueError):
                compose_profile(
                    "sultan-android14-6.1-manual",
                    target_bundle=self.bundle_sultan,
                    patch_11=self.patch_11,
                    patch_51="",
                )


    def test_neg_9_patch_51_bound_to_wrong_target(self) -> None:
        wrong_p51 = {"name": "gki_android16_6_12_51", "target_id": "gki-android16-6.12"}
        with self.assertRaises(ValueError):
            compose_profile(
                "sultan-android14-6.1-manual",
                target_bundle=self.bundle_sultan,
                patch_11=self.patch_11,
                patch_51=wrong_p51,
            )

    def test_wrong_mode_config(self):
        with self.subTest(case='neg_10_manual_lsm_y_fails'):
            cfg = dict(MANUAL_KCONFIG)
            cfg["CONFIG_KSU_LSM_SECURITY_HOOKS"] = "y"
            with self.assertRaises(FinalConfigMismatch):
                validate_config(expected=MANUAL_KCONFIG, resolved=cfg, mode="manual", raise_on_failure=True)
        with self.subTest(case='neg_11_manual_bl_y_fails'):
            cfg = dict(MANUAL_KCONFIG)
            cfg["CONFIG_KSU_HACK_ARM64_BRANCH_LINK"] = "y"
            with self.assertRaises(FinalConfigMismatch):
                validate_config(expected=MANUAL_KCONFIG, resolved=cfg, mode="manual", raise_on_failure=True)
        with self.subTest(case='neg_12_lsm_bl_lsm_n_fails'):
            cfg = dict(LSM_KCONFIG)
            cfg["CONFIG_KSU_LSM_SECURITY_HOOKS"] = "n"
            cfg["CONFIG_ARM64"] = "y"
            cfg["CONFIG_KALLSYMS"] = "y"
            with self.assertRaises(FinalConfigMismatch):
                validate_config(expected=LSM_KCONFIG, resolved=cfg, mode="lsm_bl", raise_on_failure=True)
        with self.subTest(case='neg_13_lsm_bl_bl_n_fails'):
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

    def test_missing_lsm_prerequisites(self):
        with self.subTest(case='neg_16_lsm_bl_missing_arm64_fails'):
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
        with self.subTest(case='neg_17_lsm_bl_missing_kallsyms_fails'):
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

    def test_composition_validation_failures(self):
        with self.subTest(case='neg_19_duplicate_transport_owner_fails'):
            claims = list(make_default_manual_claims())
            # Duplicate transport claim for exec
            dup = OwnershipClaim("exec", "PATCH_11", "XXKSU_BL_COMPOSITE", "xxksu")
            claims.append(dup)

            with self.assertRaises(DoubleSideEffect):
                compose_profile(
                    "sultan-android14-6.1-lsm_bl",
                    target_bundle=self.bundle_sultan,
                    patch_11=self.patch_11,
                    patch_51=self.patch_51_sultan,
                    claims=claims,
                    raise_on_failure=True,
                )
        with self.subTest(case='neg_20_banned_official_symbol_injected_fails'):
            corrupted_bundle = self.bundle_sultan.with_updated_file(
                "fs/exec.c",
                _SAMPLE_EXEC + "\nint ksu_handle_execveat_sucompat(void) { return 0; }\n",
            )
            with self.assertRaises(OfficialSymbolLeakage):
                compose_profile(
                    "sultan-android14-6.1-lsm_bl",
                    target_bundle=corrupted_bundle,
                    patch_11=self.patch_11,
                    patch_51=self.patch_51_sultan,
                    raise_on_failure=True,
                )
        with self.subTest(case='neg_21_handler_abi_mutated_fails'):
            corrupted_bundle = self.bundle_sultan.with_updated_file(
                "security/security.c",
                _SAMPLE_SECURITY_6_1 + "\nextern void ksu_bprm_check(void);\n",
            )
            with self.assertRaises(HandlerABIConflict):
                compose_profile(
                    "sultan-android14-6.1-lsm_bl",
                    target_bundle=corrupted_bundle,
                    patch_11=self.patch_11,
                    patch_51=self.patch_51_sultan,
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
