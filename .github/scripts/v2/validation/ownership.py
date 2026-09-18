"""Final-source and candidate ownership validation for V2.8."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Mapping, Optional, Sequence, Tuple

from ..model.result import (
    DoubleSideEffect,
    DuplicateOwner,
    IncompatibleOwner,
    NoOwner,
    OfficialSymbolLeakage,
    UndeclaredCoexistence,
    ValidationResult,
    ValidationStatus,
    ZeroOwner,
)
from ..source.bundle import SourceBundle


TRANSPORT_SENSITIVE_PATHS: Tuple[str, ...] = (
    "exec",
    "access",
    "stat",
    "fstat-return",
    "read",
    "reboot",
    "setuid",
    "input",
    "selinux",
)

PATH_ALIASES: Mapping[str, str] = {
    "read/init-rc": "read",
    "init-rc": "read",
    "setuid/zygote": "setuid",
    "zygote": "setuid",
    "fstat_return": "fstat-return",
    "selinux_hide": "selinux",
    "selinux-hide": "selinux",
}


def normalize_path_name(raw_path: str) -> str:
    p = raw_path.lower().strip()
    return PATH_ALIASES.get(p, p)


@dataclass(frozen=True)
class OwnershipClaim:
    """Documented ownership tuple: behavior_owner, transport_owner, implementation_owner."""

    path: str
    behavior_owner: str
    transport_owner: str
    implementation_owner: str
    source_file: Optional[str] = None
    line_number: Optional[int] = None
    caller_symbol: Optional[str] = None
    is_independent_susfs: bool = False
    coexistence_declared: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", normalize_path_name(self.path))
        if not self.path or not self.behavior_owner or not self.transport_owner or not self.implementation_owner:
            raise ValueError("OwnershipClaim requires path, behavior_owner, transport_owner, and implementation_owner")


def make_default_manual_claims() -> Tuple[OwnershipClaim, ...]:
    """Generate the canonical verified claims for a complete manual profile."""
    return (
        OwnershipClaim("exec", "PATCH_11", "FIXTURE_SCOPE_MIN", "fixture", caller_symbol="ksu_handle_execveat", source_file="fs/exec.c"),
        OwnershipClaim("access", "PATCH_11", "FIXTURE_SCOPE_MIN", "fixture", caller_symbol="ksu_handle_faccessat", source_file="fs/open.c"),
        OwnershipClaim("stat", "PATCH_11", "FIXTURE_SCOPE_MIN", "fixture", caller_symbol="ksu_handle_stat", source_file="fs/stat.c"),
        # Independent SuSFS stat spoofing block coexisting in fs/stat.c
        OwnershipClaim(
            "stat", "PATCH_51", "PATCH_51", "target_kernel",
            caller_symbol="susfs_is_sdcard_android_data_not_decrypted",
            source_file="fs/stat.c", is_independent_susfs=True, coexistence_declared=True,
        ),
        OwnershipClaim("fstat-return", "PATCH_11", "FIXTURE_SCOPE_MIN", "fixture", caller_symbol="ksu_handle_newfstat_ret", source_file="fs/stat.c"),
        OwnershipClaim("read", "PATCH_11", "FIXTURE_MANUAL_SECURITY", "fixture", caller_symbol="ksu_file_permission", source_file="security/security.c"),
        OwnershipClaim("reboot", "PATCH_11", "FIXTURE_SCOPE_MIN", "fixture", caller_symbol="ksu_handle_sys_reboot", source_file="kernel/reboot.c"),
        OwnershipClaim("setuid", "PATCH_11", "FIXTURE_MANUAL_SECURITY", "fixture", caller_symbol="ksu_task_fix_setuid", source_file="security/security.c"),
        OwnershipClaim("input", "XXKSU_RUNTIME", "XXKSU_RUNTIME", "xxksu", caller_symbol="input_register_handler", source_file="kernel/feature/vol_detector.c"),
        OwnershipClaim("selinux", "XXKSU_RUNTIME", "FIXTURE_MANUAL_SECURITY", "fixture", caller_symbol="ksu_hide_setprocattr", source_file="security/security.c"),
    )


def make_default_lsm_bl_claims() -> Tuple[OwnershipClaim, ...]:
    """Generate the canonical verified claims for a complete lsm_bl profile."""
    return (
        OwnershipClaim("exec", "PATCH_11", "XXKSU_BL_COMPOSITE", "xxksu", caller_symbol="ksu_handle_execveat"),
        OwnershipClaim("access", "PATCH_11", "XXKSU_BL_COMPOSITE", "xxksu", caller_symbol="ksu_handle_faccessat"),
        OwnershipClaim("stat", "PATCH_11", "XXKSU_BL_COMPOSITE", "xxksu", caller_symbol="ksu_handle_stat"),
        # Independent SuSFS stat spoofing block coexisting in fs/stat.c
        OwnershipClaim(
            "stat", "PATCH_51", "PATCH_51", "target_kernel",
            caller_symbol="susfs_is_sdcard_android_data_not_decrypted",
            source_file="fs/stat.c", is_independent_susfs=True, coexistence_declared=True,
        ),
        OwnershipClaim("fstat-return", "PATCH_11", "XXKSU_BL_COMPOSITE", "xxksu", caller_symbol="ksu_handle_newfstat_ret"),
        OwnershipClaim("read", "PATCH_11", "XXKSU_BL_COMPOSITE", "xxksu", caller_symbol="ksu_handle_sys_read_fd"),
        OwnershipClaim("reboot", "PATCH_11", "XXKSU_BL_COMPOSITE", "xxksu", caller_symbol="ksu_handle_sys_reboot"),
        OwnershipClaim("setuid", "PATCH_11", "XXKSU_LSM", "xxksu", caller_symbol="ksu_task_fix_setuid"),
        OwnershipClaim("input", "XXKSU_RUNTIME", "XXKSU_RUNTIME", "xxksu", caller_symbol="input_register_handler"),
        OwnershipClaim("selinux", "XXKSU_RUNTIME", "XXKSU_LSM", "xxksu", caller_symbol="ksu_hide_setprocattr"),
    )


def validate_ownership(
    mode: str,
    claims: Optional[Sequence[OwnershipClaim]] = None,
    bundle: Optional[SourceBundle] = None,
    required_paths: Sequence[str] = TRANSPORT_SENSITIVE_PATHS,
    raise_on_failure: bool = False,
) -> Tuple[ValidationResult, ...]:
    """Validate that every transport-sensitive path has exactly one valid owner for the active profile mode."""
    if mode not in ("manual", "lsm_bl"):
        raise ValueError(f"unknown mode '{mode}', expected 'manual' or 'lsm_bl'")

    active_claims: list[OwnershipClaim] = []
    if claims is not None:
        active_claims.extend(claims)

    results: list[ValidationResult] = []

    # Map claims by normalized path
    claims_by_path: dict[str, list[OwnershipClaim]] = {}
    for c in active_claims:
        claims_by_path.setdefault(c.path, []).append(c)

    # Validate each required transport path
    for path in required_paths:
        norm_path = normalize_path_name(path)
        all_path_claims = claims_by_path.get(norm_path, [])

        # 1. Coexistence check
        for c in all_path_claims:
            if c.is_independent_susfs and not c.coexistence_declared:
                res = ValidationResult(
                    validator_id="validation.ownership.coexistence",
                    status=ValidationStatus.FAIL,
                    target=norm_path,
                    details=f"Undeclared coexistence detected for independent SuSFS claim on '{norm_path}'",
                    path=c.source_file,
                    line=c.line_number,
                    metadata={"path": norm_path, "error_type": "UndeclaredCoexistence"},
                )
                results.append(res)
                if raise_on_failure:
                    raise UndeclaredCoexistence(res.details)

        # 2. Transport claims (non-independent)
        transport_claims = [c for c in all_path_claims if not c.is_independent_susfs]

        # 3. Check for official input symbol hook rejection
        for tc in transport_claims:
            if tc.caller_symbol == "ksu_handle_input_handle_event":
                res = ValidationResult(
                    validator_id="validation.ownership.official_leak",
                    status=ValidationStatus.FAIL,
                    target=norm_path,
                    details=f"Official-only input handler claimed in path '{norm_path}'",
                    path=tc.source_file,
                    metadata={"path": norm_path, "error_type": "OfficialSymbolLeakage"},
                )
                results.append(res)
                if raise_on_failure:
                    raise OfficialSymbolLeakage(res.details)

        # 4. Zero owner check
        if len(transport_claims) == 0:
            res = ValidationResult(
                validator_id="validation.ownership.cardinality",
                status=ValidationStatus.FAIL,
                target=norm_path,
                details=f"Zero transport owner (NO_OWNER) for path '{norm_path}' in mode '{mode}'",
                metadata={"path": norm_path, "error_type": "NoOwner"},
            )
            results.append(res)
            if raise_on_failure:
                raise NoOwner(res.details)
            continue

        # 5. Duplicate owner check
        if len(transport_claims) > 1:
            owners_list = [c.transport_owner for c in transport_claims]
            res = ValidationResult(
                validator_id="validation.ownership.cardinality",
                status=ValidationStatus.FAIL,
                target=norm_path,
                details=(
                    f"Duplicate transport owners (DOUBLE_SIDE_EFFECT) for path '{norm_path}' "
                    f"in mode '{mode}': {owners_list}"
                ),
                metadata={"path": norm_path, "error_type": "DoubleSideEffect", "owners": owners_list},
            )
            results.append(res)
            if raise_on_failure:
                raise DoubleSideEffect(res.details)
            continue

        # 6. Compatibility check for single transport claim
        tc = transport_claims[0]

        if mode == "manual":
            # Automated transport forbidden in manual mode
            if tc.transport_owner in (
                "XXKSU_BL_COMPOSITE", "XXKSU_BRANCH_LINK", "XXKSU_INTERNAL_SYSCALL_FALLBACK",
                "XXKSU_LSM", "XXKSU_LSM_LIST", "XXKSU_LSM_STATIC",
            ):
                res = ValidationResult(
                    validator_id="validation.ownership.compatibility",
                    status=ValidationStatus.FAIL,
                    target=norm_path,
                    details=(
                        f"Incompatible automated transport owner '{tc.transport_owner}' "
                        f"in manual mode for path '{norm_path}'"
                    ),
                    path=tc.source_file,
                    metadata={"path": norm_path, "error_type": "IncompatibleOwner"},
                )
                results.append(res)
                if raise_on_failure:
                    raise IncompatibleOwner(res.details)
                continue

            # Check valid manual fixture owners
            if norm_path in ("exec", "access", "stat", "fstat-return", "reboot"):
                if tc.transport_owner not in ("FIXTURE_SCOPE_MIN", "scope-min-manual-hooks-v2.3.patch"):
                    res = ValidationResult(
                        validator_id="validation.ownership.compatibility",
                        status=ValidationStatus.FAIL,
                        target=norm_path,
                        details=f"Expected FIXTURE_SCOPE_MIN for path '{norm_path}', got '{tc.transport_owner}'",
                        path=tc.source_file,
                        metadata={"path": norm_path, "error_type": "IncompatibleOwner"},
                    )
                    results.append(res)
                    if raise_on_failure:
                        raise IncompatibleOwner(res.details)
                    continue
            elif norm_path in ("read", "setuid"):
                if tc.transport_owner not in ("FIXTURE_MANUAL_SECURITY", "manual-security-hooks-v2.0.patch"):
                    res = ValidationResult(
                        validator_id="validation.ownership.compatibility",
                        status=ValidationStatus.FAIL,
                        target=norm_path,
                        details=f"Expected FIXTURE_MANUAL_SECURITY for path '{norm_path}', got '{tc.transport_owner}'",
                        path=tc.source_file,
                        metadata={"path": norm_path, "error_type": "IncompatibleOwner"},
                    )
                    results.append(res)
                    if raise_on_failure:
                        raise IncompatibleOwner(res.details)
                    continue
            elif norm_path == "input":
                if tc.transport_owner != "XXKSU_RUNTIME":
                    res = ValidationResult(
                        validator_id="validation.ownership.compatibility",
                        status=ValidationStatus.FAIL,
                        target=norm_path,
                        details=f"Expected XXKSU_RUNTIME for input registration, got '{tc.transport_owner}'",
                        path=tc.source_file,
                        metadata={"path": norm_path, "error_type": "IncompatibleOwner"},
                    )
                    results.append(res)
                    if raise_on_failure:
                        raise IncompatibleOwner(res.details)
                    continue
            elif norm_path == "selinux":
                if tc.transport_owner not in ("FIXTURE_MANUAL_SECURITY", "manual-security-hooks-v2.0.patch", "XXKSU_RUNTIME"):
                    res = ValidationResult(
                        validator_id="validation.ownership.compatibility",
                        status=ValidationStatus.FAIL,
                        target=norm_path,
                        details=f"Incompatible SELinux transport owner '{tc.transport_owner}' in manual mode",
                        path=tc.source_file,
                        metadata={"path": norm_path, "error_type": "IncompatibleOwner"},
                    )
                    results.append(res)
                    if raise_on_failure:
                        raise IncompatibleOwner(res.details)
                    continue

        elif mode == "lsm_bl":
            # Manual fixture callers are strictly forbidden in lsm_bl mode
            if tc.transport_owner in (
                "FIXTURE_SCOPE_MIN", "FIXTURE_MANUAL_SECURITY",
                "scope-min-manual-hooks-v2.3.patch", "manual-security-hooks-v2.0.patch",
            ):
                res = ValidationResult(
                    validator_id="validation.ownership.compatibility",
                    status=ValidationStatus.FAIL,
                    target=norm_path,
                    details=(
                        f"Manual fixture transport '{tc.transport_owner}' is strictly forbidden "
                        f"in lsm_bl mode for path '{norm_path}'"
                    ),
                    path=tc.source_file,
                    metadata={"path": norm_path, "error_type": "IncompatibleOwner"},
                )
                results.append(res)
                if raise_on_failure:
                    raise IncompatibleOwner(res.details)
                continue

            # Check valid lsm_bl owners
            if norm_path in ("exec", "access", "stat", "fstat-return", "read", "reboot"):
                if tc.transport_owner not in ("XXKSU_BL_COMPOSITE", "XXKSU_BRANCH_LINK", "XXKSU_INTERNAL_SYSCALL_FALLBACK"):
                    res = ValidationResult(
                        validator_id="validation.ownership.compatibility",
                        status=ValidationStatus.FAIL,
                        target=norm_path,
                        details=f"Expected XXKSU_BL_COMPOSITE for path '{norm_path}', got '{tc.transport_owner}'",
                        path=tc.source_file,
                        metadata={"path": norm_path, "error_type": "IncompatibleOwner"},
                    )
                    results.append(res)
                    if raise_on_failure:
                        raise IncompatibleOwner(res.details)
                    continue
            elif norm_path == "setuid":
                if tc.transport_owner not in ("XXKSU_LSM", "XXKSU_LSM_LIST", "XXKSU_LSM_STATIC"):
                    res = ValidationResult(
                        validator_id="validation.ownership.compatibility",
                        status=ValidationStatus.FAIL,
                        target=norm_path,
                        details=f"Expected XXKSU_LSM for setuid in lsm_bl mode, got '{tc.transport_owner}'",
                        path=tc.source_file,
                        metadata={"path": norm_path, "error_type": "IncompatibleOwner"},
                    )
                    results.append(res)
                    if raise_on_failure:
                        raise IncompatibleOwner(res.details)
                    continue
            elif norm_path == "input":
                if tc.transport_owner != "XXKSU_RUNTIME":
                    res = ValidationResult(
                        validator_id="validation.ownership.compatibility",
                        status=ValidationStatus.FAIL,
                        target=norm_path,
                        details=f"Expected XXKSU_RUNTIME for input, got '{tc.transport_owner}'",
                        path=tc.source_file,
                        metadata={"path": norm_path, "error_type": "IncompatibleOwner"},
                    )
                    results.append(res)
                    if raise_on_failure:
                        raise IncompatibleOwner(res.details)
                    continue
            elif norm_path == "selinux":
                if tc.transport_owner not in ("XXKSU_LSM", "XXKSU_RUNTIME"):
                    res = ValidationResult(
                        validator_id="validation.ownership.compatibility",
                        status=ValidationStatus.FAIL,
                        target=norm_path,
                        details=f"Incompatible SELinux owner '{tc.transport_owner}' in lsm_bl mode",
                        path=tc.source_file,
                        metadata={"path": norm_path, "error_type": "IncompatibleOwner"},
                    )
                    results.append(res)
                    if raise_on_failure:
                        raise IncompatibleOwner(res.details)
                    continue

        results.append(ValidationResult(
            validator_id="validation.ownership.single_owner",
            status=ValidationStatus.PASS,
            target=norm_path,
            details=f"Path '{norm_path}' has exactly one valid owner '{tc.transport_owner}' for {mode}",
            metadata={"path": norm_path, "owner": tc.transport_owner},
        ))

    return tuple(results)
