"""Comprehensive test suite for V2.10: build planning, orchestration, and dry-run execution."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from v2.build import (
    BuildPlan,
    BuildResult,
    BuildStatus,
    BuildToolchainSpec,
    ClassificationResult,
    FailureCategory,
    classify_failure,
    create_all_canonical_plans,
    create_build_plan,
    create_build_plan_from_definition,
    execute_all_dry_runs,
    execute_build,
    execute_dry_run,
    export_ci_matrix,
    format_config_fragment,
)
from v2.validation import (
    validate_build_plan,
    validate_build_result,
    validate_plan_isolation,
)
from v2.model.manifest import KNOWN_PROFILES
from v2.model.provenance import HashDigest
from v2.model.result import (
    AbiSignatureMismatch,
    BuildFailure,
    DoubleTransport,
    FinalConfigMismatch,
    KconfigConflict,
    MissingPrerequisite,
    OfficialSymbolLeakage,
    UnexpectedSymbolOwnership,
    ValidationError,
    ValidationStatus,
    ZeroOwner,
)
from v2.profiles.matrix import get_profile_definition, list_profile_definitions


class TestV210SixBuildPlans(unittest.TestCase):
    """Verify that all six canonical BuildPlan objects are generated deterministically."""

    def test_canonical_matrix_six_plans(self):
        plans = create_all_canonical_plans()
        self.assertEqual(len(plans), 6)

        expected_profiles = (
            "gki-android14-6.1-manual",
            "gki-android14-6.1-lsm_bl",
            "gki-android16-6.12-manual",
            "gki-android16-6.12-lsm_bl",
            "sultan-android14-6.1-manual",
            "sultan-android14-6.1-lsm_bl",
        )
        plan_profiles = tuple(p.profile_id for p in plans)
        self.assertEqual(plan_profiles, expected_profiles)

    def test_plan_fields_completeness(self):
        plans = create_all_canonical_plans()
        for p in plans:
            self.assertIn(p.profile_id, KNOWN_PROFILES)
            self.assertTrue(p.target_id)
            self.assertIn(p.mode, ("manual", "lsm_bl"))
            self.assertTrue(isinstance(p.source_identity, HashDigest))
            self.assertTrue(isinstance(p.composition_digest, HashDigest))
            self.assertTrue(isinstance(p.digest, HashDigest))
            self.assertTrue(p.source_workspace_path_template)
            self.assertTrue(p.out_dir_template)
            self.assertTrue(p.log_dir_template)
            self.assertTrue(p.result_path_template)
            self.assertTrue(p.base_defconfig_cmd)
            self.assertTrue(p.config_fragment)
            self.assertTrue(p.olddefconfig_cmd)
            self.assertTrue(p.final_build_cmd)
            self.assertTrue(p.required_artifacts)
            self.assertTrue(p.expected_validation_gates)
            self.assertTrue(isinstance(p.toolchain_requirements, BuildToolchainSpec))

    def test_unknown_profile_rejected(self):
        with self.assertRaises(Exception):
            get_profile_definition("unknown-profile-6.1-manual")


class TestV210DefconfigAndFlags(unittest.TestCase):
    """Verify target-specific defconfigs and mandatory toolchain flags."""

    def test_gki_vs_sultan_defconfig(self):
        plans = {p.profile_id: p for p in create_all_canonical_plans()}

        # GKI profiles must use gki_defconfig
        gki_profiles = [
            "gki-android14-6.1-manual",
            "gki-android14-6.1-lsm_bl",
            "gki-android16-6.12-manual",
            "gki-android16-6.12-lsm_bl",
        ]
        for pid in gki_profiles:
            plan = plans[pid]
            self.assertIn("gki_defconfig", plan.base_defconfig_cmd)
            self.assertNotIn("sultan_defconfig", plan.base_defconfig_cmd)

        # Sultan profiles must use sultan_defconfig
        sultan_profiles = [
            "sultan-android14-6.1-manual",
            "sultan-android14-6.1-lsm_bl",
        ]
        for pid in sultan_profiles:
            plan = plans[pid]
            self.assertIn("sultan_defconfig", plan.base_defconfig_cmd)
            self.assertNotIn("gki_defconfig", plan.base_defconfig_cmd)

    def test_mandatory_flags_in_all_commands(self):
        plans = create_all_canonical_plans()
        for p in plans:
            for cmd in (p.base_defconfig_cmd, p.olddefconfig_cmd, p.final_build_cmd):
                cmd_str = " ".join(cmd)
                self.assertIn("ARCH=arm64", cmd_str)
                self.assertIn("LLVM=1", cmd_str)
                self.assertIn("LLVM_IAS=1", cmd_str)
                self.assertIn("O=", cmd_str)

    def test_command_targets(self):
        plans = create_all_canonical_plans()
        for p in plans:
            self.assertEqual(p.base_defconfig_cmd[0], "make")
            self.assertEqual(p.olddefconfig_cmd[0], "make")
            self.assertIn("olddefconfig", p.olddefconfig_cmd)
            self.assertEqual(p.final_build_cmd[0], "make")
            self.assertIn("Image", p.final_build_cmd)


class TestV210PathIsolation(unittest.TestCase):
    """Verify mutual path isolation across all six profiles."""

    def test_disjoint_paths(self):
        plans = create_all_canonical_plans()
        worktrees = set()
        out_dirs = set()
        log_dirs = set()
        result_paths = set()

        for p in plans:
            w = p.resolve_source_workspace_path()
            o = p.resolve_out_dir()
            l = p.resolve_log_dir()
            r = p.resolve_result_path()

            self.assertNotIn(w, worktrees, f"Collision on worktree: {w}")
            self.assertNotIn(o, out_dirs, f"Collision on out_dir: {o}")
            self.assertNotIn(l, log_dirs, f"Collision on log_dir: {l}")
            self.assertNotIn(r, result_paths, f"Collision on result_path: {r}")

            worktrees.add(w)
            out_dirs.add(o)
            log_dirs.add(l)
            result_paths.add(r)

        self.assertEqual(len(worktrees), 6)
        self.assertEqual(len(out_dirs), 6)
        self.assertEqual(len(log_dirs), 6)
        self.assertEqual(len(result_paths), 6)

    def test_path_isolation_validator(self):
        plans = create_all_canonical_plans()
        res = validate_plan_isolation(plans)
        self.assertEqual(res.status, ValidationStatus.PASS)

    def test_path_isolation_collision_detected(self):
        plans = list(create_all_canonical_plans())
        # Duplicate the first plan
        plans.append(plans[0])
        res = validate_plan_isolation(plans)
        self.assertEqual(res.status, ValidationStatus.FAIL)
        with self.assertRaises(BuildFailure):
            validate_plan_isolation(plans, raise_on_failure=True)

    def test_no_mutation_of_main_checkout(self):
        plans = create_all_canonical_plans()
        for p in plans:
            w = p.resolve_source_workspace_path()
            o = p.resolve_out_dir()
            # Paths must not equal or contain dangerous roots
            for path_str in (w, o, p.resolve_log_dir(), p.resolve_result_path()):
                norm = os.path.normpath(path_str)
                self.assertNotIn(norm, (".", "/", "", ".git"))
                self.assertFalse(norm.startswith("/etc"))
                self.assertFalse(norm.startswith("/root"))


class TestV210Determinism(unittest.TestCase):
    """Verify deterministic JSON serialization, digests, and CI matrix export."""

    def test_deterministic_plan_json_and_digest(self):
        plans_a = create_all_canonical_plans()
        plans_b = create_all_canonical_plans()

        for a, b in zip(plans_a, plans_b):
            self.assertEqual(a.to_dict(), b.to_dict())
            self.assertEqual(a.canonical_json(), b.canonical_json())
            self.assertEqual(a.digest, b.digest)

    def test_deterministic_toolchain_spec(self):
        t1 = BuildToolchainSpec()
        t2 = BuildToolchainSpec()
        self.assertEqual(t1.to_dict(), t2.to_dict())
        self.assertEqual(t1.canonical_json(), t2.canonical_json())

    def test_ci_matrix_serialization_determinism(self):
        plans = create_all_canonical_plans()
        matrix1 = export_ci_matrix(plans)
        matrix2 = export_ci_matrix(plans)
        self.assertEqual(matrix1, matrix2)

        data = json.loads(matrix1)
        self.assertIn("include", data)
        self.assertEqual(len(data["include"]), 6)
        # Verify ordering is deterministic by profile_id
        profile_ids = [item["profile_id"] for item in data["include"]]
        self.assertEqual(profile_ids, sorted(profile_ids))


class TestV210ArtifactsAndConfigFragment(unittest.TestCase):
    """Verify required artifacts and Kconfig fragments."""

    def test_expected_artifacts(self):
        plans = create_all_canonical_plans()
        for p in plans:
            self.assertIn("Image", p.required_artifacts)
            self.assertIn("vmlinux", p.required_artifacts)

    def test_config_fragment_content(self):
        plans = {p.profile_id: p for p in create_all_canonical_plans()}

        for p in plans.values():
            self.assertIn("CONFIG_KSU=y", p.config_fragment)
            self.assertIn("CONFIG_KSU_SUSFS=y", p.config_fragment)

        # Manual profiles: no LSM / BL
        manual_plan = plans["gki-android14-6.1-manual"]
        self.assertIn("# CONFIG_KSU_LSM_SECURITY_HOOKS is not set", manual_plan.config_fragment)
        self.assertIn("# CONFIG_KSU_HACK_ARM64_BRANCH_LINK is not set", manual_plan.config_fragment)

        # LSM_BL profiles: LSM / BL enabled
        lsm_plan = plans["gki-android14-6.1-lsm_bl"]
        self.assertIn("CONFIG_KSU_LSM_SECURITY_HOOKS=y", lsm_plan.config_fragment)
        self.assertIn("CONFIG_KSU_HACK_ARM64_BRANCH_LINK=y", lsm_plan.config_fragment)

    def test_format_config_fragment_sorting(self):
        cfg = {"CONFIG_B": "y", "CONFIG_A": "n", "CONFIG_C": "m"}
        frag = format_config_fragment(cfg)
        lines = frag.strip().splitlines()
        self.assertEqual(lines, ["# CONFIG_A is not set", "CONFIG_B=y", "CONFIG_C=m"])


class TestV210CommandSafetyAndOrdering(unittest.TestCase):
    """Verify absence of network commands and correct phase ordering."""

    def test_no_network_commands_present(self):
        plans = create_all_canonical_plans()
        banned = {"git", "curl", "wget", "ssh", "scp", "rsync", "apt", "fetch"}
        for p in plans:
            for cmd in (p.base_defconfig_cmd, p.olddefconfig_cmd, p.final_build_cmd):
                for token in cmd:
                    for b in banned:
                        self.assertNotEqual(token.lower(), b)
                        self.assertNotIn(f"{b} ", token.lower())

    def test_command_ordering(self):
        plan = create_all_canonical_plans()[0]
        cmds = plan.resolve_commands()
        self.assertEqual(len(cmds), 3)
        # Phase 1: defconfig
        self.assertTrue("defconfig" in cmds[0][-1])
        # Phase 2: olddefconfig
        self.assertTrue("olddefconfig" in cmds[1][-1])
        # Phase 3: Image
        self.assertTrue("Image" in cmds[2][-1])


class TestV210DryRunAndExecutionGuards(unittest.TestCase):
    """Verify dry-run execution, status invariants, and local build execution guard."""

    def test_dry_run_all_six_profiles(self):
        plans = create_all_canonical_plans()
        results = execute_all_dry_runs(plans)
        self.assertEqual(len(results), 6)

        for res in results:
            self.assertTrue(isinstance(res, BuildResult))
            # Critical requirement: dry-run status is NOT PASS
            self.assertNotEqual(res.status, BuildStatus.PASS)
            self.assertEqual(res.status, BuildStatus.DRY_RUN)
            self.assertEqual(len(res.commands), 3)
            self.assertEqual(res.artifacts_expected, ("Image", "vmlinux"))
            self.assertEqual(res.artifacts_found, ())
            self.assertIsNone(res.failure_category)
            self.assertIsNone(res.error_message)

    def test_dry_run_cannot_be_marked_pass(self):
        plan = create_all_canonical_plans()[0]
        with self.assertRaises(ValueError):
            execute_dry_run(plan, status=BuildStatus.PASS)

    def test_execute_build_strictly_guarded(self):
        plan = create_all_canonical_plans()[0]
        # Without explicit authorization, must fail closed
        with self.assertRaises(BuildFailure):
            execute_build(plan, allow_real_build=False)

        # Even with allow_real_build=True, local runner is not authorized CI runner
        with self.assertRaises(BuildFailure):
            execute_build(plan, allow_real_build=True)

    def test_build_result_schema_and_digest(self):
        plan = create_all_canonical_plans()[0]
        res = execute_dry_run(plan)
        d = res.to_dict()
        self.assertEqual(d["schema"], "xxksu-susfs-build-result/v1")
        self.assertEqual(d["status"], "DRY_RUN")
        self.assertEqual(d["profile_id"], plan.profile_id)
        self.assertTrue(isinstance(res.digest, HashDigest))
        self.assertEqual(res.canonical_json(), json.dumps(d, sort_keys=True, separators=(",", ":")))


class TestV210FailureClassification(unittest.TestCase):
    """Verify authoritative taxonomy failure classification per Section 35."""

    def test_toolchain_environment_failures(self):
        cases = [
            ("make: command not found", FailureCategory.TOOLCHAIN_ENVIRONMENT),
            ("clang: error: unable to execute command", FailureCategory.TOOLCHAIN_ENVIRONMENT),
            ("No space left on device", FailureCategory.TOOLCHAIN_ENVIRONMENT),
            ("fatal error: out of memory", FailureCategory.TOOLCHAIN_ENVIRONMENT),
        ]
        for msg, expected in cases:
            res = classify_failure(msg)
            self.assertEqual(res.category, expected, f"Failed for '{msg}'")

    def test_exit_code_signal_failures(self):
        res = classify_failure("Process killed", exit_code=137)
        self.assertEqual(res.category, FailureCategory.TOOLCHAIN_ENVIRONMENT)

        res_127 = classify_failure("command missing", exit_code=127)
        self.assertEqual(res_127.category, FailureCategory.TOOLCHAIN_ENVIRONMENT)

    def test_generator_failures(self):
        cases = [
            ("malformed patch at line 42", FailureCategory.GENERATOR),
            ("corrupt patch at line 10", FailureCategory.GENERATOR),
            ("patch unexpectedly ends in middle of line", FailureCategory.GENERATOR),
        ]
        for msg, expected in cases:
            res = classify_failure(msg)
            self.assertEqual(res.category, expected, f"Failed for '{msg}'")

    def test_adapter_failures(self):
        cases = [
            ("Hunk #2 FAILED at 150", FailureCategory.ADAPTER),
            ("patch does not apply", FailureCategory.ADAPTER),
            ("error: patch failed: fs/exec.c:100", FailureCategory.ADAPTER),
        ]
        for msg, expected in cases:
            res = classify_failure(msg)
            self.assertEqual(res.category, expected, f"Failed for '{msg}'")

    def test_policy_failures(self):
        # Typed policy errors
        self.assertEqual(
            classify_failure(OfficialSymbolLeakage("forbidden symbol leaked")).category,
            FailureCategory.POLICY,
        )
        self.assertEqual(
            classify_failure(DoubleTransport("double transport")).category,
            FailureCategory.POLICY,
        )
        self.assertEqual(
            classify_failure(ZeroOwner("zero owner")).category,
            FailureCategory.POLICY,
        )
        self.assertEqual(
            classify_failure(AbiSignatureMismatch("abi mismatch")).category,
            FailureCategory.POLICY,
        )

        # String patterns
        self.assertEqual(
            classify_failure("Leaked symbol: ksu_handle_execveat_sucompat").category,
            FailureCategory.POLICY,
        )

    def test_profile_failures(self):
        self.assertEqual(
            classify_failure(FinalConfigMismatch("config mismatch")).category,
            FailureCategory.PROFILE,
        )
        self.assertEqual(
            classify_failure(KconfigConflict("kconfig conflict")).category,
            FailureCategory.PROFILE,
        )
        self.assertEqual(
            classify_failure(MissingPrerequisite("prerequisite missing")).category,
            FailureCategory.PROFILE,
        )

    def test_clean_tree_probe_failures(self):
        # Section 35: compiler failure must not automatically be blamed on generator
        res = classify_failure(
            "error: implicit declaration of function 'foo'",
            is_clean_tree_failure=True,
        )
        self.assertEqual(res.category, FailureCategory.UPSTREAM_DRIFT)

    def test_compiler_failure_not_automatically_generator(self):
        res = classify_failure("error: incompatible type for argument 2 of 'bar'")
        # Must not be generator!
        self.assertNotEqual(res.category, FailureCategory.GENERATOR)
        self.assertEqual(res.category, FailureCategory.UPSTREAM_DRIFT)


class TestV210BuildValidators(unittest.TestCase):
    """Verify build plan and result validators."""

    def test_validate_all_six_build_plans(self):
        for plan in create_all_canonical_plans():
            res = validate_build_plan(plan)
            self.assertEqual(res.status, ValidationStatus.PASS)
            self.assertEqual(res.validator_id, "validation.build.plan")

    def test_validate_build_plan_failure_cases(self):
        plan = create_all_canonical_plans()[0]
        # Mutate to missing defconfig
        bad_plan = BuildPlan(
            profile_id=plan.profile_id,
            target_id=plan.target_id,
            mode=plan.mode,
            source_identity=plan.source_identity,
            composition_digest=plan.composition_digest,
            source_workspace_path_template=plan.source_workspace_path_template,
            out_dir_template=plan.out_dir_template,
            log_dir_template=plan.log_dir_template,
            result_path_template=plan.result_path_template,
            base_defconfig_cmd=("make", "ARCH=arm64", "LLVM=1", "LLVM_IAS=1", "O=out", "wrong_defconfig"),
            config_fragment=plan.config_fragment,
            olddefconfig_cmd=plan.olddefconfig_cmd,
            final_build_cmd=plan.final_build_cmd,
            required_artifacts=plan.required_artifacts,
            expected_validation_gates=plan.expected_validation_gates,
            toolchain_requirements=plan.toolchain_requirements,
            digest=plan.digest,
        )
        res = validate_build_plan(bad_plan)
        self.assertEqual(res.status, ValidationStatus.FAIL)

    def test_validate_dry_run_result_not_pass(self):
        plan = create_all_canonical_plans()[0]
        res = execute_dry_run(plan)
        val_res = validate_build_result(res)
        # Unexecuted / dry-run must NOT report PASS
        self.assertNotEqual(val_res.status, ValidationStatus.PASS)
        self.assertEqual(val_res.status, ValidationStatus.NOT_APPLICABLE)

    def test_validate_failed_build_result(self):
        plan = create_all_canonical_plans()[0]
        failed_res = BuildResult(
            profile_id=plan.profile_id,
            plan_digest=plan.digest,
            status=BuildStatus.FAIL,
            commands=plan.resolve_commands(),
            artifacts_expected=plan.required_artifacts,
            artifacts_found=(),
            worktree_path=plan.resolve_source_workspace_path(),
            out_dir=plan.resolve_out_dir(),
            log_dir=plan.resolve_log_dir(),
            result_path=plan.resolve_result_path(),
            failure_category=FailureCategory.ADAPTER,
            error_message="Hunk failed at 120",
        )
        val_res = validate_build_result(failed_res)
        self.assertEqual(val_res.status, ValidationStatus.FAIL)
        with self.assertRaises(BuildFailure):
            validate_build_result(failed_res, raise_on_failure=True)


class TestV210ZeroBuildBinariesExecuted(unittest.TestCase):
    """Verify that under no circumstances are compiler or build tools invoked locally."""

    @patch("subprocess.run")
    @patch("subprocess.Popen")
    @patch("subprocess.call")
    @patch("os.system")
    def test_zero_build_tool_invocations(self, mock_system, mock_call, mock_popen, mock_run):
        # Execute the entire suite of build planning, dry runs, matrix exports, validations
        plans = create_all_canonical_plans()
        self.assertEqual(len(plans), 6)

        results = execute_all_dry_runs(plans)
        self.assertEqual(len(results), 6)

        ci_matrix = export_ci_matrix(plans)
        self.assertTrue(ci_matrix)

        for p in plans:
            validate_build_plan(p)

        validate_plan_isolation(plans)

        for r in results:
            validate_build_result(r)

        # None of subprocess or os.system must have been called
        mock_run.assert_not_called()
        mock_popen.assert_not_called()
        mock_call.assert_not_called()
        mock_system.assert_not_called()


if __name__ == "__main__":
    unittest.main()
