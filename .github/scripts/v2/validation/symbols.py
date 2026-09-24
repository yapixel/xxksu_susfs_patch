"""Official-only symbol leakage and required symbol presence validation for V2.8."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Optional, Sequence, Tuple, Union

from ..model.patch import AddedLine, ContextLine, Patch
from ..model.result import (
    MissingRequiredSymbol,
    MissingSymbolEvidence,
    OfficialSymbolLeakage,
    UnexpectedSymbolOwnership,
    ValidationResult,
    ValidationStatus,
)
from ..source.bundle import SourceBundle


BANNED_OFFICIAL_SYMBOLS: Tuple[str, ...] = (
    "ksu_handle_execveat_sucompat",
    "ksu_handle_vfs_fstat",
    "ksu_handle_sys_read",
    "ksu_handle_input_handle_event",
)


@dataclass(frozen=True)
class SymbolContract:
    symbol: str
    is_banned: bool = False
    is_required: bool = False
    expected_owner: Optional[str] = None
    expected_paths: Tuple[str, ...] = ()
    actual_equivalent: Optional[str] = None
    description: str = ""
    bundle_target: Optional[str] = None
    strict_paths: bool = False


DEFAULT_SYMBOL_CONTRACTS: Tuple[SymbolContract, ...] = (
    # 4 Hard-banned official-only symbols
    SymbolContract(
        symbol="ksu_handle_execveat_sucompat",
        is_banned=True,
        expected_owner="official_only",
        actual_equivalent="ksu_handle_execveat",
        description="Official-10 sucompat handler (forbidden in xxKSU)",
    ),
    SymbolContract(
        symbol="ksu_handle_vfs_fstat",
        is_banned=True,
        expected_owner="official_only",
        actual_equivalent="ksu_handle_newfstat_ret",
        description="Official-10 vfs_fstat handler (forbidden in xxKSU)",
    ),
    SymbolContract(
        symbol="ksu_handle_sys_read",
        is_banned=True,
        expected_owner="official_only",
        actual_equivalent="ksu_handle_sys_read_fd",
        description="Official-10 sys_read handler (forbidden in xxKSU)",
    ),
    SymbolContract(
        symbol="ksu_handle_input_handle_event",
        is_banned=True,
        expected_owner="official_only",
        actual_equivalent="input_register_handler",
        description="Official-10 input handler (forbidden in xxKSU)",
    ),
    # 4 Required xxKSU replacement symbols
    SymbolContract(
        symbol="ksu_handle_execveat",
        is_required=True,
        expected_paths=("kernel/feature/sucompat.c",),
        bundle_target="xxksu",
        description="xxKSU execveat handler",
    ),
    SymbolContract(
        symbol="ksu_handle_newfstat_ret",
        is_required=True,
        expected_paths=("kernel/runtime/ksud.c",),
        bundle_target="xxksu",
        description="xxKSU fstat return handler",
    ),
    SymbolContract(
        symbol="ksu_handle_sys_read_fd",
        is_required=True,
        expected_paths=("kernel/hook/syscall_table_hook_arm64.c",),
        bundle_target="xxksu",
        description="xxKSU read fallback handler",
    ),
    SymbolContract(
        symbol="input_register_handler",
        is_required=True,
        expected_paths=("kernel/runtime/ksud.c", "kernel/feature/vol_detector.c"),
        bundle_target="xxksu",
        description="xxKSU volume detector input registration",
    ),
    # 6 Required SuSFS integration symbols
    SymbolContract(
        symbol="susfs_init",
        is_required=True,
        expected_paths=("kernel/ksu.c",),
        bundle_target="xxksu",
        description="SuSFS core initialization hook in ksu.c",
    ),
    SymbolContract(
        symbol="susfs_cmd_dispatch",
        is_required=True,
        expected_paths=("kernel/supercall/dispatch.c", "kernel/supercall/supercall.c"),
        bundle_target="xxksu",
        description="SuSFS supercall command dispatch",
    ),
    SymbolContract(
        symbol="susfs_auto_reboot",
        is_required=True,
        expected_paths=("kernel/supercall/dispatch.c", "kernel/supercall/supercall.c"),
        bundle_target="xxksu",
        description="SuSFS auto reboot helper",
    ),
    SymbolContract(
        symbol="handle_zygote_setresuid",
        is_required=True,
        expected_paths=("kernel/hook/setuid_hook.c",),
        bundle_target="xxksu",
        description="SuSFS zygote credentials and SID handling",
    ),
    SymbolContract(
        symbol="ksu_is_webview_zygote_umount_enabled",
        is_required=True,
        expected_paths=("kernel/feature/kernel_umount.c", "kernel/downstream/ksu_hostsredirect.h"),
        bundle_target="xxksu",
        description="SuSFS webview zygote umount helper",
    ),
    SymbolContract(
        symbol="susfs_set_sid",
        is_required=True,
        expected_paths=("kernel/selinux/rules.c", "kernel/selinux/selinux.c"),
        bundle_target="xxksu",
        description="SuSFS SELinux SID management helper",
    ),
)


def _scan_patch_for_banned_symbols(
    patch: Union[str, Patch],
    banned_symbols: Sequence[str],
    raise_on_failure: bool,
) -> list[ValidationResult]:
    results: list[ValidationResult] = []
    banned_regexes = {sym: re.compile(r"\b" + re.escape(sym) + r"\b") for sym in banned_symbols}

    if isinstance(patch, Patch):
        for fp in patch.files:
            target_path = fp.new_path[2:] if fp.new_path.startswith("b/") else fp.new_path
            for hunk in fp.hunks:
                line_no = hunk.new_start
                for line in hunk.lines:
                    if isinstance(line, AddedLine):
                        for sym, regex in banned_regexes.items():
                            if regex.search(line.text):
                                res = ValidationResult(
                                    validator_id="validation.symbols.leakage",
                                    status=ValidationStatus.FAIL,
                                    target=sym,
                                    details=f"Official-only symbol '{sym}' leaked in patch for {target_path}:{line_no}",
                                    path=target_path,
                                    line=line_no,
                                    context=line.text,
                                    metadata={"symbol": sym, "error_type": "OfficialSymbolLeakage"},
                                )
                                results.append(res)
                                if raise_on_failure:
                                    raise OfficialSymbolLeakage(res.details)
                        line_no += 1
                    elif isinstance(line, ContextLine):
                        line_no += 1
        return results

    # patch is a raw unified diff string
    lines = patch.splitlines()
    current_file = "unknown"
    for line_idx, raw_line in enumerate(lines, 1):
        if raw_line.startswith("+++ b/"):
            current_file = raw_line[6:].strip()
            continue
        elif raw_line.startswith("+++ "):
            current_file = raw_line[4:].strip()
            continue
        elif raw_line.startswith("diff --git"):
            parts = raw_line.split()
            if len(parts) >= 4 and parts[3].startswith("b/"):
                current_file = parts[3][2:].strip()
            continue

        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            added_content = raw_line[1:]
            for sym, regex in banned_regexes.items():
                if regex.search(added_content):
                    res = ValidationResult(
                        validator_id="validation.symbols.leakage",
                        status=ValidationStatus.FAIL,
                        target=sym,
                        details=f"Official-only symbol '{sym}' leaked in patch for {current_file}:{line_idx}",
                        path=current_file,
                        line=line_idx,
                        context=added_content.strip(),
                        metadata={"symbol": sym, "error_type": "OfficialSymbolLeakage"},
                    )
                    results.append(res)
                    if raise_on_failure:
                        raise OfficialSymbolLeakage(res.details)

    return results


def _scan_bundle_for_banned_symbols(
    bundle: SourceBundle,
    banned_symbols: Sequence[str],
    raise_on_failure: bool,
) -> list[ValidationResult]:
    results: list[ValidationResult] = []
    banned_regexes = {sym: re.compile(r"\b" + re.escape(sym) + r"\b") for sym in banned_symbols}

    for file_entry in bundle.files:
        lines = file_entry.content.splitlines()
        for line_idx, line in enumerate(lines, 1):
            for sym, regex in banned_regexes.items():
                if regex.search(line):
                    res = ValidationResult(
                        validator_id="validation.symbols.leakage",
                        status=ValidationStatus.FAIL,
                        target=sym,
                        details=f"Official-only symbol '{sym}' leaked in source {file_entry.path}:{line_idx}",
                        path=file_entry.path,
                        line=line_idx,
                        context=line.strip(),
                        metadata={"symbol": sym, "error_type": "OfficialSymbolLeakage"},
                    )
                    results.append(res)
                    if raise_on_failure:
                        raise OfficialSymbolLeakage(res.details)

    return results


def _verify_required_symbols(
    bundle: SourceBundle,
    contracts: Sequence[SymbolContract],
    raise_on_failure: bool,
) -> list[ValidationResult]:
    results: list[ValidationResult] = []

    for contract in contracts:
        if not contract.is_required:
            continue
        if contract.bundle_target and contract.bundle_target != bundle.target_id:
            continue

        pattern = re.compile(r"\b" + re.escape(contract.symbol) + r"\b")
        found = False
        found_path: Optional[str] = None
        found_line: Optional[int] = None
        found_context: Optional[str] = None

        search_paths = contract.expected_paths if contract.expected_paths else tuple(f.path for f in bundle.files)
        for p in search_paths:
            if bundle.has_file(p):
                file_entry = bundle.get_file(p)
                lines = file_entry.content.splitlines()
                for l_idx, l_text in enumerate(lines, 1):
                    if pattern.search(l_text):
                        found = True
                        found_path = p
                        found_line = l_idx
                        found_context = l_text.strip()
                        break
            if found:
                break

        if not found:
            res = ValidationResult(
                validator_id="validation.symbols.presence",
                status=ValidationStatus.FAIL,
                target=contract.symbol,
                details=(
                    f"Required symbol '{contract.symbol}' missing from bundle '{bundle.target_id}' "
                    f"(searched {search_paths})"
                ),
                path=contract.expected_paths[0] if contract.expected_paths else None,
                metadata={"symbol": contract.symbol, "error_type": "MissingRequiredSymbol"},
            )
            results.append(res)
            if raise_on_failure:
                raise MissingRequiredSymbol(res.details)
        else:
            results.append(ValidationResult(
                validator_id="validation.symbols.presence",
                status=ValidationStatus.PASS,
                target=contract.symbol,
                details=f"Required symbol '{contract.symbol}' present in {found_path}:{found_line}",
                path=found_path,
                line=found_line,
                context=found_context,
                metadata={"symbol": contract.symbol},
            ))

    return results


def validate_symbols(
    *,
    bundle: Optional[SourceBundle] = None,
    patch: Optional[Union[str, Patch]] = None,
    contracts: Sequence[SymbolContract] = DEFAULT_SYMBOL_CONTRACTS,
    allow_synthetic: bool = False,
    evidence_kind: Optional[str] = None,
    raise_on_failure: bool = False,
) -> Tuple[ValidationResult, ...]:
    """Validate that candidate patch and source bundle have 0 official leaks and all required symbols."""
    results: list[ValidationResult] = []

    if not allow_synthetic and evidence_kind in ("SYNTHETIC", "UNVERIFIED"):
        res = ValidationResult(
            validator_id="validation.symbols.evidence",
            status=ValidationStatus.FAIL,
            target="symbol_evidence",
            details=f"Synthetic or unverified symbol evidence '{evidence_kind}' rejected in production",
            metadata={"error_type": "MissingSymbolEvidence"},
        )
        results.append(res)
        if raise_on_failure:
            raise MissingSymbolEvidence(res.details)

    banned = tuple(c.symbol for c in contracts if c.is_banned)
    if not banned:
        banned = BANNED_OFFICIAL_SYMBOLS

    # 1. Scan patch diff if provided
    if patch is not None:
        patch_results = _scan_patch_for_banned_symbols(patch, banned, raise_on_failure)
        results.extend(patch_results)
        if not patch_results:
            results.append(ValidationResult(
                validator_id="validation.symbols.leakage",
                status=ValidationStatus.PASS,
                target="patch",
                details="Zero official-only symbols detected in patch additions",
            ))

    # 2. Scan source bundle if provided
    if bundle is not None:
        bundle_leakage = _scan_bundle_for_banned_symbols(bundle, banned, raise_on_failure)
        results.extend(bundle_leakage)
        if not bundle_leakage:
            results.append(ValidationResult(
                validator_id="validation.symbols.leakage",
                status=ValidationStatus.PASS,
                target=f"bundle:{bundle.target_id}",
                details=f"Zero official-only symbols detected in source bundle '{bundle.target_id}'",
            ))

        # Check required symbols
        presence_results = _verify_required_symbols(bundle, contracts, raise_on_failure)
        results.extend(presence_results)

    return tuple(results)
