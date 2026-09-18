"""Build plan and result validation for V2.10."""

from __future__ import annotations

from typing import Optional, Sequence

from ..build.executor import BuildResult, BuildStatus
from ..build.plan import BuildPlan
from ..model.manifest import KNOWN_PROFILES
from ..model.result import BuildFailure, ValidationResult, ValidationStatus


def validate_build_plan(
    plan: BuildPlan,
    *,
    raise_on_failure: bool = False,
) -> ValidationResult:
    """Validate that a BuildPlan satisfies all V2.10 contracts."""
    if not isinstance(plan, BuildPlan):
        res = ValidationResult(
            validator_id="validation.build.plan",
            status=ValidationStatus.FAIL,
            target="unknown",
            details=f"Expected BuildPlan, got {type(plan)}",
            metadata={"error_type": "BuildFailure"},
        )
        if raise_on_failure:
            raise BuildFailure(res.details)
        return res

    # 1. Profile membership
    if plan.profile_id not in KNOWN_PROFILES:
        res = ValidationResult(
            validator_id="validation.build.plan",
            status=ValidationStatus.FAIL,
            target=plan.profile_id,
            details=f"Unknown profile_id in build plan: '{plan.profile_id}'",
            metadata={"error_type": "BuildFailure"},
        )
        if raise_on_failure:
            raise BuildFailure(res.details)
        return res

    # 2. Defconfig target matching
    expected_defconfig = "sultan_defconfig" if plan.target_id.startswith("sultan-") else "gki_defconfig"
    if not any(expected_defconfig in token for token in plan.base_defconfig_cmd):
        res = ValidationResult(
            validator_id="validation.build.plan",
            status=ValidationStatus.FAIL,
            target=plan.profile_id,
            details=f"Defconfig command missing expected target '{expected_defconfig}': {plan.base_defconfig_cmd}",
            metadata={"error_type": "BuildFailure"},
        )
        if raise_on_failure:
            raise BuildFailure(res.details)
        return res

    # 3. Required make flags in all make commands
    for cmd_name, cmd in [
        ("base_defconfig_cmd", plan.base_defconfig_cmd),
        ("olddefconfig_cmd", plan.olddefconfig_cmd),
        ("final_build_cmd", plan.final_build_cmd),
    ]:
        cmd_str = " ".join(cmd)
        for req_flag in ("ARCH=arm64", "LLVM=1", "LLVM_IAS=1", "O="):
            if req_flag not in cmd_str:
                res = ValidationResult(
                    validator_id="validation.build.plan",
                    status=ValidationStatus.FAIL,
                    target=plan.profile_id,
                    details=f"Command '{cmd_name}' missing required flag '{req_flag}': {cmd}",
                    metadata={"error_type": "BuildFailure"},
                )
                if raise_on_failure:
                    raise BuildFailure(res.details)
                return res

    # 4. Olddefconfig target
    if "olddefconfig" not in plan.olddefconfig_cmd:
        res = ValidationResult(
            validator_id="validation.build.plan",
            status=ValidationStatus.FAIL,
            target=plan.profile_id,
            details=f"olddefconfig command does not specify olddefconfig: {plan.olddefconfig_cmd}",
            metadata={"error_type": "BuildFailure"},
        )
        if raise_on_failure:
            raise BuildFailure(res.details)
        return res

    # 5. Final build target
    if "Image" not in plan.final_build_cmd:
        res = ValidationResult(
            validator_id="validation.build.plan",
            status=ValidationStatus.FAIL,
            target=plan.profile_id,
            details=f"final_build_cmd does not specify Image target: {plan.final_build_cmd}",
            metadata={"error_type": "BuildFailure"},
        )
        if raise_on_failure:
            raise BuildFailure(res.details)
        return res

    # 6. Required artifacts
    for art in ("Image", "vmlinux"):
        if art not in plan.required_artifacts and not any(art in a for a in plan.required_artifacts):
            res = ValidationResult(
                validator_id="validation.build.plan",
                status=ValidationStatus.FAIL,
                target=plan.profile_id,
                details=f"required_artifacts missing essential artifact '{art}': {plan.required_artifacts}",
                metadata={"error_type": "BuildFailure"},
            )
            if raise_on_failure:
                raise BuildFailure(res.details)
            return res

    # 7. Config fragment sanity
    if "CONFIG_KSU=y" not in plan.config_fragment or "CONFIG_KSU_SUSFS=y" not in plan.config_fragment:
        res = ValidationResult(
            validator_id="validation.build.plan",
            status=ValidationStatus.FAIL,
            target=plan.profile_id,
            details="config_fragment missing CONFIG_KSU=y or CONFIG_KSU_SUSFS=y",
            metadata={"error_type": "BuildFailure"},
        )
        if raise_on_failure:
            raise BuildFailure(res.details)
        return res

    # 8. Path isolation sanity (non-empty, non-root)
    for p_name, p_val in [
        ("source_workspace", plan.source_workspace_path_template),
        ("out_dir", plan.out_dir_template),
        ("log_dir", plan.log_dir_template),
        ("result_path", plan.result_path_template),
    ]:
        if not p_val or p_val.strip() in ("/", ".", ""):
            res = ValidationResult(
                validator_id="validation.build.plan",
                status=ValidationStatus.FAIL,
                target=plan.profile_id,
                details=f"Unsafe or empty template for {p_name}: '{p_val}'",
                metadata={"error_type": "BuildFailure"},
            )
            if raise_on_failure:
                raise BuildFailure(res.details)
            return res

    return ValidationResult(
        validator_id="validation.build.plan",
        status=ValidationStatus.PASS,
        target=plan.profile_id,
        details=f"Build plan for {plan.profile_id} validated successfully ({plan.target_id}, {plan.mode})",
        metadata={
            "plan_digest": str(plan.digest),
            "expected_defconfig": expected_defconfig,
            "toolchain": plan.toolchain_requirements.to_dict(),
        },
    )


def validate_plan_isolation(
    plans: Sequence[BuildPlan],
    *,
    raise_on_failure: bool = False,
) -> ValidationResult:
    """Validate that a set of BuildPlans are mutually disjoint across all workspaces and output paths."""
    seen_profiles: set[str] = set()
    seen_worktrees: set[str] = set()
    seen_out_dirs: set[str] = set()
    seen_log_dirs: set[str] = set()
    seen_result_paths: set[str] = set()

    for p in plans:
        if p.profile_id in seen_profiles:
            res = ValidationResult(
                validator_id="validation.build.isolation",
                status=ValidationStatus.FAIL,
                target=p.profile_id,
                details=f"Duplicate profile in plan set: '{p.profile_id}'",
                metadata={"error_type": "BuildFailure"},
            )
            if raise_on_failure:
                raise BuildFailure(res.details)
            return res
        seen_profiles.add(p.profile_id)

        w = p.resolve_source_workspace_path()
        o = p.resolve_out_dir()
        l = p.resolve_log_dir()
        r = p.resolve_result_path()

        if w in seen_worktrees:
            res = ValidationResult(
                validator_id="validation.build.isolation",
                status=ValidationStatus.FAIL,
                target=p.profile_id,
                details=f"Source workspace path collision: '{w}'",
                metadata={"error_type": "BuildFailure"},
            )
            if raise_on_failure:
                raise BuildFailure(res.details)
            return res
        seen_worktrees.add(w)

        if o in seen_out_dirs:
            res = ValidationResult(
                validator_id="validation.build.isolation",
                status=ValidationStatus.FAIL,
                target=p.profile_id,
                details=f"Output directory path collision: '{o}'",
                metadata={"error_type": "BuildFailure"},
            )
            if raise_on_failure:
                raise BuildFailure(res.details)
            return res
        seen_out_dirs.add(o)

        if l in seen_log_dirs:
            res = ValidationResult(
                validator_id="validation.build.isolation",
                status=ValidationStatus.FAIL,
                target=p.profile_id,
                details=f"Log directory path collision: '{l}'",
                metadata={"error_type": "BuildFailure"},
            )
            if raise_on_failure:
                raise BuildFailure(res.details)
            return res
        seen_log_dirs.add(l)

        if r in seen_result_paths:
            res = ValidationResult(
                validator_id="validation.build.isolation",
                status=ValidationStatus.FAIL,
                target=p.profile_id,
                details=f"Result path collision: '{r}'",
                metadata={"error_type": "BuildFailure"},
            )
            if raise_on_failure:
                raise BuildFailure(res.details)
            return res
        seen_result_paths.add(r)

    return ValidationResult(
        validator_id="validation.build.isolation",
        status=ValidationStatus.PASS,
        target=f"{len(plans)}_plans",
        details=f"Full path isolation verified across {len(plans)} plans",
        metadata={"plan_count": len(plans)},
    )


def validate_build_result(
    result: BuildResult,
    *,
    raise_on_failure: bool = False,
) -> ValidationResult:
    """Validate a BuildResult.

    CRITICAL: Dry-run and unexecuted builds are NEVER reported as PASS.
    """
    if not isinstance(result, BuildResult):
        res = ValidationResult(
            validator_id="validation.build.result",
            status=ValidationStatus.FAIL,
            target="unknown",
            details=f"Expected BuildResult, got {type(result)}",
            metadata={"error_type": "BuildFailure"},
        )
        if raise_on_failure:
            raise BuildFailure(res.details)
        return res

    if result.status == BuildStatus.PASS:
        # Verify required artifacts were found
        for art in result.artifacts_expected:
            if art not in result.artifacts_found and not any(art in a for a in result.artifacts_found):
                res = ValidationResult(
                    validator_id="validation.build.result",
                    status=ValidationStatus.FAIL,
                    target=result.profile_id,
                    details=f"Build marked PASS but required artifact '{art}' not found in {result.artifacts_found}",
                    metadata={"error_type": "BuildFailure"},
                )
                if raise_on_failure:
                    raise BuildFailure(res.details)
                return res

        return ValidationResult(
            validator_id="validation.build.result",
            status=ValidationStatus.PASS,
            target=result.profile_id,
            details=f"Build passed with all {len(result.artifacts_found)} artifacts verified",
            metadata={"status": "PASS", "artifacts": list(result.artifacts_found)},
        )

    if result.status in (BuildStatus.DRY_RUN, BuildStatus.PLANNED, BuildStatus.NOT_EXECUTED):
        return ValidationResult(
            validator_id="validation.build.result",
            status=ValidationStatus.NOT_APPLICABLE,
            target=result.profile_id,
            details=f"Build pending real CI execution (current local status: {result.status.value})",
            metadata={"status": result.status.value, "dry_run": True},
        )

    # BuildStatus.FAIL
    cat_str = result.failure_category.value if result.failure_category else "unclassified"
    res = ValidationResult(
        validator_id="validation.build.result",
        status=ValidationStatus.FAIL,
        target=result.profile_id,
        details=f"Build execution failed ({cat_str}): {result.error_message or 'unknown error'}",
        metadata={"status": "FAIL", "failure_category": cat_str, "error_type": "BuildFailure"},
    )
    if raise_on_failure:
        raise BuildFailure(res.details)
    return res


__all__ = [
    "validate_build_plan",
    "validate_plan_isolation",
    "validate_build_result",
]
