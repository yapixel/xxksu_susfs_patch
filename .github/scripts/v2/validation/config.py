"""Final configuration parsing and validation for V2.9."""

from __future__ import annotations

import re
from typing import Any, Mapping, Optional, Union

from ..model.result import (
    FinalConfigMismatch,
    KconfigConflict,
    MissingPrerequisite,
    ValidationResult,
    ValidationStatus,
)


def parse_kconfig(text: str) -> dict[str, str]:
    """Parse standard kernel configuration text into a normalized mapping of symbol -> value.

    Supports:
      CONFIG_FOO=y
      CONFIG_FOO=m
      CONFIG_FOO=n
      # CONFIG_FOO is not set -> n

    Raises:
      KconfigConflict if conflicting duplicate assignments exist.
    """
    config: dict[str, str] = {}
    lines = text.splitlines()
    for line_idx, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        if not line:
            continue

        # Check '# CONFIG_FOO is not set'
        unset_match = re.match(r"^#\s*(CONFIG_[A-Za-z0-9_]+)\s+is not set\b", line)
        if unset_match:
            sym = unset_match.group(1)
            val = "n"
            if sym in config and config[sym] != val:
                raise KconfigConflict(
                    f"conflicting duplicate assignment for {sym} at line {line_idx}: '{config[sym]}' vs '{val}'"
                )
            config[sym] = val
            continue

        # Other comments
        if line.startswith("#"):
            continue

        # Standard assignment 'CONFIG_FOO=val'
        assign_match = re.match(r"^(CONFIG_[A-Za-z0-9_]+)\s*=\s*(.*)$", line)
        if assign_match:
            sym = assign_match.group(1)
            val = assign_match.group(2).strip()
            # Strip surrounding quotes if any
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            if sym in config and config[sym] != val:
                raise KconfigConflict(
                    f"conflicting duplicate assignment for {sym} at line {line_idx}: '{config[sym]}' vs '{val}'"
                )
            config[sym] = val

    return config


def validate_config(
    expected: Mapping[str, str],
    resolved: Union[str, Mapping[str, str]],
    requested: Optional[Mapping[str, str]] = None,
    mode: str = "manual",
    prerequisites: Optional[Mapping[str, Any]] = None,
    raise_on_failure: bool = False,
) -> ValidationResult:
    """Validate resolved kernel configuration against expected profile truth tables."""
    if isinstance(resolved, str):
        try:
            resolved_map = parse_kconfig(resolved)
        except KconfigConflict as exc:
            res = ValidationResult(
                validator_id="validation.config",
                status=ValidationStatus.FAIL,
                target=mode,
                details=f"Kconfig conflict: {exc}",
                metadata={
                    "requested": dict(requested or expected),
                    "resolved": {},
                    "expected": dict(expected),
                    "reason": str(exc),
                    "error_type": "KconfigConflict",
                },
            )
            if raise_on_failure:
                raise
            return res
    elif isinstance(resolved, Mapping):
        resolved_map = {k: str(v).strip("\"'") for k, v in resolved.items()}
    else:
        res = ValidationResult(
            validator_id="validation.config",
            status=ValidationStatus.FAIL,
            target=mode,
            details="resolved configuration must be text or mapping",
            metadata={"error_type": "FinalConfigMismatch"},
        )
        if raise_on_failure:
            raise FinalConfigMismatch(res.details)
        return res

    req_map = dict(requested) if requested is not None else dict(expected)
    exp_map = dict(expected)

    # 1. Check mutual exclusion / general conflicts
    # Branch Link + Tamper Syscall Table is explicitly forbidden
    bl_val = resolved_map.get("CONFIG_KSU_HACK_ARM64_BRANCH_LINK")
    tamper_val = resolved_map.get("CONFIG_KSU_TAMPER_SYSCALL_TABLE")
    if bl_val == "y" and tamper_val == "y":
        reason = "CONFIG_KSU_HACK_ARM64_BRANCH_LINK=y and CONFIG_KSU_TAMPER_SYSCALL_TABLE=y are mutually exclusive"
        res = ValidationResult(
            validator_id="validation.config",
            status=ValidationStatus.FAIL,
            target=mode,
            details=f"Kconfig conflict: {reason}",
            metadata={
                "requested": req_map,
                "resolved": resolved_map,
                "expected": exp_map,
                "reason": reason,
                "error_type": "KconfigConflict",
            },
        )
        if raise_on_failure:
            raise KconfigConflict(res.details)
        return res

    # 2. Check SuSFS requirement across all modes
    susfs_val = resolved_map.get("CONFIG_KSU_SUSFS")
    if susfs_val != "y":
        reason = f"CONFIG_KSU_SUSFS must be 'y', resolved to '{susfs_val}'"
        res = ValidationResult(
            validator_id="validation.config",
            status=ValidationStatus.FAIL,
            target=mode,
            details=f"Final config mismatch: {reason}",
            metadata={
                "requested": req_map,
                "resolved": resolved_map,
                "expected": exp_map,
                "reason": reason,
                "error_type": "FinalConfigMismatch",
            },
        )
        if raise_on_failure:
            raise FinalConfigMismatch(res.details)
        return res

    # 3. Check mode-specific transport truth tables
    if mode == "manual":
        # Any automated transport in manual mode is forbidden
        forbidden_in_manual = [
            ("CONFIG_KSU_LSM_SECURITY_HOOKS", "LSM security hooks"),
            ("CONFIG_KSU_HACK_ARM64_BRANCH_LINK", "ARM64 branch link"),
            ("CONFIG_KSU_TAMPER_SYSCALL_TABLE", "tamper syscall table"),
            ("CONFIG_KSU_KPROBES_KSUD", "kprobes ksud"),
        ]
        for sym, desc in forbidden_in_manual:
            if resolved_map.get(sym) == "y":
                reason = f"manual mode forbids {desc} ({sym}=y)"
                res = ValidationResult(
                    validator_id="validation.config",
                    status=ValidationStatus.FAIL,
                    target=mode,
                    details=f"Final config mismatch: {reason}",
                    metadata={
                        "requested": req_map,
                        "resolved": resolved_map,
                        "expected": exp_map,
                        "reason": reason,
                        "error_type": "FinalConfigMismatch",
                    },
                )
                if raise_on_failure:
                    raise FinalConfigMismatch(res.details)
                return res

    elif mode == "lsm_bl":
        # LSM and BL must be enabled
        if resolved_map.get("CONFIG_KSU_LSM_SECURITY_HOOKS") != "y":
            reason = "lsm_bl mode requires CONFIG_KSU_LSM_SECURITY_HOOKS=y"
            res = ValidationResult(
                validator_id="validation.config",
                status=ValidationStatus.FAIL,
                target=mode,
                details=f"Final config mismatch: {reason}",
                metadata={
                    "requested": req_map,
                    "resolved": resolved_map,
                    "expected": exp_map,
                    "reason": reason,
                    "error_type": "FinalConfigMismatch",
                },
            )
            if raise_on_failure:
                raise FinalConfigMismatch(res.details)
            return res

        if resolved_map.get("CONFIG_KSU_HACK_ARM64_BRANCH_LINK") != "y":
            reason = "lsm_bl mode requires CONFIG_KSU_HACK_ARM64_BRANCH_LINK=y"
            res = ValidationResult(
                validator_id="validation.config",
                status=ValidationStatus.FAIL,
                target=mode,
                details=f"Final config mismatch: {reason}",
                metadata={
                    "requested": req_map,
                    "resolved": resolved_map,
                    "expected": exp_map,
                    "reason": reason,
                    "error_type": "FinalConfigMismatch",
                },
            )
            if raise_on_failure:
                raise FinalConfigMismatch(res.details)
            return res

        # TAMPER and KPROBES_KSUD forbidden
        for sym, desc in [
            ("CONFIG_KSU_TAMPER_SYSCALL_TABLE", "tamper syscall table"),
            ("CONFIG_KSU_KPROBES_KSUD", "kprobes ksud"),
        ]:
            if resolved_map.get(sym) == "y":
                reason = f"lsm_bl mode forbids {desc} ({sym}=y)"
                res = ValidationResult(
                    validator_id="validation.config",
                    status=ValidationStatus.FAIL,
                    target=mode,
                    details=f"Final config mismatch: {reason}",
                    metadata={
                        "requested": req_map,
                        "resolved": resolved_map,
                        "expected": exp_map,
                        "reason": reason,
                        "error_type": "FinalConfigMismatch",
                    },
                )
                if raise_on_failure:
                    raise FinalConfigMismatch(res.details)
                return res

        # Check prerequisites: arch=arm64 and KALLSYMS=y
        prereq = prerequisites or {"arch": "arm64", "kallsyms": True}
        if prereq.get("arch") == "arm64":
            if resolved_map.get("CONFIG_ARM64") != "y":
                reason = "lsm_bl mode requires CONFIG_ARM64=y prerequisite"
                res = ValidationResult(
                    validator_id="validation.config",
                    status=ValidationStatus.FAIL,
                    target=mode,
                    details=f"Prerequisite failure: {reason}",
                    metadata={
                        "requested": req_map,
                        "resolved": resolved_map,
                        "expected": exp_map,
                        "reason": reason,
                        "error_type": "MissingPrerequisite",
                    },
                )
                if raise_on_failure:
                    raise MissingPrerequisite(res.details)
                return res

        if prereq.get("kallsyms") is True:
            if resolved_map.get("CONFIG_KALLSYMS") != "y":
                reason = "lsm_bl mode requires CONFIG_KALLSYMS=y prerequisite"
                res = ValidationResult(
                    validator_id="validation.config",
                    status=ValidationStatus.FAIL,
                    target=mode,
                    details=f"Prerequisite failure: {reason}",
                    metadata={
                        "requested": req_map,
                        "resolved": resolved_map,
                        "expected": exp_map,
                        "reason": reason,
                        "error_type": "MissingPrerequisite",
                    },
                )
                if raise_on_failure:
                    raise MissingPrerequisite(res.details)
                return res

    # 4. Check that all expected symbols match resolved exactly
    for sym, exp_val in exp_map.items():
        res_val = resolved_map.get(sym)
        if res_val is None:
            reason = f"required symbol '{sym}' missing from resolved .config (expected: '{exp_val}')"
            res = ValidationResult(
                validator_id="validation.config",
                status=ValidationStatus.FAIL,
                target=mode,
                details=f"Final config mismatch: {reason}",
                metadata={
                    "requested": req_map,
                    "resolved": resolved_map,
                    "expected": exp_map,
                    "reason": reason,
                    "error_type": "FinalConfigMismatch",
                },
            )
            if raise_on_failure:
                raise FinalConfigMismatch(res.details)
            return res

        if res_val != exp_val:
            reason = f"symbol '{sym}' resolved to '{res_val}', expected '{exp_val}'"
            res = ValidationResult(
                validator_id="validation.config",
                status=ValidationStatus.FAIL,
                target=mode,
                details=f"Final config mismatch: {reason}",
                metadata={
                    "requested": req_map,
                    "resolved": resolved_map,
                    "expected": exp_map,
                    "reason": reason,
                    "error_type": "FinalConfigMismatch",
                },
            )
            if raise_on_failure:
                raise FinalConfigMismatch(res.details)
            return res

    return ValidationResult(
        validator_id="validation.config",
        status=ValidationStatus.PASS,
        target=mode,
        details=f"Final .config matches expected profile truth table ({len(exp_map)} verified symbols)",
        metadata={
            "requested": req_map,
            "resolved": resolved_map,
            "expected": exp_map,
            "mode": mode,
        },
    )


__all__ = [
    "parse_kconfig",
    "validate_config",
]
