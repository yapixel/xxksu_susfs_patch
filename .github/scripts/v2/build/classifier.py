"""Failure classification for V2.10 build subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any, Mapping, Optional, Union

from ..model.result import (
    AbiLinkageConflict,
    AbiSignatureMismatch,
    AmbiguousAbiMapping,
    BuildFailure,
    DoubleSideEffect,
    DoubleTransport,
    DuplicateOwner,
    FinalConfigMismatch,
    HandlerABIConflict,
    IncompatibleOwner,
    KconfigConflict,
    MissingAbiEvidence,
    MissingPrerequisite,
    MissingRequiredSymbol,
    MissingSymbolEvidence,
    NoOwner,
    OfficialSymbolLeakage,
    PolicyLedgerMismatch,
    SourceBundleIdentityMismatch,
    UndeclaredCoexistence,
    UnexpectedSymbolOwnership,
    ValidationError,
    ZeroOwner,
)


class FailureCategory(str, Enum):
    """Authoritative failure taxonomy per V2 Design Task Section 35."""

    GENERATOR = "generator"
    POLICY = "policy"
    ADAPTER = "adapter"
    PROFILE = "profile"
    UPSTREAM_DRIFT = "upstream_drift"
    TOOLCHAIN_ENVIRONMENT = "toolchain_environment"


@dataclass(frozen=True)
class ClassificationResult:
    """Immutable result of failure classification."""

    category: FailureCategory
    reason: str
    confidence: str  # "HIGH", "MEDIUM", "LOW"
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "reason": self.reason,
            "confidence": self.confidence,
            "details": dict(self.details),
        }


# Known regex patterns for each category
_TOOLCHAIN_PATTERNS = [
    (r"command not found:\s*(make|clang|ld\.lld|gcc|aarch64-[a-z0-9_-]+)", "Toolchain binary not found"),
    (r"/(?:make|clang|ld\.lld|gcc):\s*not found", "Toolchain binary not found"),
    (r"clang:\s*error:\s*unable to execute command", "Compiler process execution failure"),
    (r"clang:\s*error:\s*unsupported option", "Compiler unsupported option"),
    (r"unknown argument:\s*'-target'", "Clang target argument unsupported"),
    (r"unrecognized command line option", "Compiler command line option unsupported"),
    (r"No space left on device", "Disk space exhausted"),
    (r"Cannot allocate memory", "Memory allocation failed"),
    (r"fatal error:\s*out of memory", "Out of memory during build"),
    (r"\bKilled\b", "Process killed (OOM or signal)"),
    (r"Permission denied", "Filesystem permission denied"),
]

_GENERATOR_PATTERNS = [
    (r"malformed patch at line", "Patch generator emitted malformed patch syntax"),
    (r"corrupt patch at line", "Patch generator emitted corrupt hunk"),
    (r"patch unexpectedly ends in middle of line", "Patch generator truncated output"),
    (r"PatchEmitError", "Patch emitter internal exception"),
    (r"PatchParseError", "Diff parser internal exception"),
    (r"fatal:\s*corrupt patch", "Corrupt patch structure emitted"),
]

_ADAPTER_PATTERNS = [
    (r"Hunk #\d+\s+FAILED at \d+", "Target adapter patch anchor rejected"),
    (r"patch does not apply", "Target source divergence from adapter anchors"),
    (r"error:\s*patch failed:", "Unified diff application failed on target tree"),
    (r"Reversed \(or previously applied\) patch", "Target patch sequence conflict"),
    (r"MissingSemanticAnchor", "Target adapter failed to locate required semantic anchor"),
    (r"AmbiguousSemanticMatch", "Target adapter found ambiguous hook sites"),
    (r"FixtureAdaptationFailure", "Manual fixture adaptation failed on target tree"),
]

_POLICY_PATTERNS = [
    (r"OfficialSymbolLeakage", "Policy violation: forbidden official symbol detected"),
    (r"ksu_handle_execveat_sucompat", "Forbidden official symbol leaked"),
    (r"ksu_handle_vfs_fstat\b", "Forbidden official symbol leaked"),
    (r"ksu_handle_sys_read\b", "Forbidden official symbol leaked"),
    (r"ksu_handle_input_handle_event\b", "Forbidden official symbol leaked"),
    (r"ZeroOwner|NoOwner", "Policy violation: missing transport owner"),
    (r"DuplicateOwner|DoubleTransport|DoubleSideEffect", "Policy violation: duplicate transport ownership"),
    (r"HandlerABIConflict|AbiSignatureMismatch|AbiLinkageConflict", "Policy violation: handler ABI mismatch"),
    (r"UnexpectedSymbolOwnership", "Policy violation: symbol owned by unauthorized transport"),
]

_PROFILE_PATTERNS = [
    (r"FinalConfigMismatch", "Profile configuration mismatch with expected truth table"),
    (r"KconfigConflict", "Mutually exclusive Kconfig symbols enabled"),
    (r"MissingPrerequisite", "Profile prerequisites (e.g. ARM64/KALLSYMS) not satisfied"),
    (r"InvalidFixtureContract", "Profile fixture contract violation"),
    (r"TargetProfileMismatch", "Target bundle does not match profile target"),
    (r"UnknownProfile|UnknownTarget", "Unrecognized profile or target specification"),
]

_UPSTREAM_DRIFT_PATTERNS = [
    (r"implicit declaration of function", "Kernel API change: implicit function declaration"),
    (r"has no member named", "Kernel struct layout changed upstream"),
    (r"incompatible type for argument", "Kernel function signature changed upstream"),
    (r"too (?:many|few) arguments to function", "Kernel function arity changed upstream"),
]


def classify_failure(
    error: Union[str, Exception],
    *,
    exit_code: Optional[int] = None,
    error_type: Optional[str] = None,
    is_clean_tree_failure: bool = False,
    file_path: Optional[str] = None,
) -> ClassificationResult:
    """Classify a build or validation failure into its authoritative failure taxonomy.

    Per Section 35:
      A compiler failure must not automatically be classified as generator logic failure.
    """
    text = str(error)
    type_str = error_type or (error.__class__.__name__ if isinstance(error, Exception) else "")

    # 1. Clean tree reproduction: if clean tree fails, cannot be generator or policy
    if is_clean_tree_failure:
        # Check if toolchain error
        for pattern, reason in _TOOLCHAIN_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return ClassificationResult(
                    category=FailureCategory.TOOLCHAIN_ENVIRONMENT,
                    reason=f"Clean tree verification failed: {reason}",
                    confidence="HIGH",
                    details={"text": text, "exit_code": exit_code},
                )
        return ClassificationResult(
            category=FailureCategory.UPSTREAM_DRIFT,
            reason="Clean unpatched tree fails to compile (upstream API drift or break)",
            confidence="HIGH",
            details={"text": text, "exit_code": exit_code},
        )

    # 2. Exit code checks (signal / OOM)
    if exit_code in (137, -9):
        return ClassificationResult(
            category=FailureCategory.TOOLCHAIN_ENVIRONMENT,
            reason="Process terminated by SIGKILL (OOM or runner kill)",
            confidence="HIGH",
            details={"exit_code": exit_code},
        )
    if exit_code == 127:
        return ClassificationResult(
            category=FailureCategory.TOOLCHAIN_ENVIRONMENT,
            reason="Toolchain command not found (exit code 127)",
            confidence="HIGH",
            details={"exit_code": exit_code},
        )

    # 3. Explicit typed errors from model/result
    if isinstance(error, (OfficialSymbolLeakage, UnexpectedSymbolOwnership, HandlerABIConflict, DuplicateOwner, ZeroOwner)):
        return ClassificationResult(
            category=FailureCategory.POLICY,
            reason=f"Typed policy validation error: {type_str}",
            confidence="HIGH",
            details={"error_type": type_str, "text": text},
        )
    if isinstance(error, (FinalConfigMismatch, KconfigConflict, MissingPrerequisite)):
        return ClassificationResult(
            category=FailureCategory.PROFILE,
            reason=f"Typed profile validation error: {type_str}",
            confidence="HIGH",
            details={"error_type": type_str, "text": text},
        )
    if type_str in ("InvalidFixtureContract", "TargetProfileMismatch", "UnknownProfile", "UnknownTarget"):
        return ClassificationResult(
            category=FailureCategory.PROFILE,
            reason=f"Profile contract error: {type_str}",
            confidence="HIGH",
            details={"error_type": type_str, "text": text},
        )
    if type_str in ("PatchEmitError", "PatchParseError", "MalformedFileHeader", "MalformedHunkHeader"):
        return ClassificationResult(
            category=FailureCategory.GENERATOR,
            reason=f"Patch generation error: {type_str}",
            confidence="HIGH",
            details={"error_type": type_str, "text": text},
        )

    # 4. Pattern matching on string content
    for pattern, reason in _TOOLCHAIN_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return ClassificationResult(
                category=FailureCategory.TOOLCHAIN_ENVIRONMENT,
                reason=reason,
                confidence="HIGH",
                details={"pattern": pattern, "text": text},
            )

    for pattern, reason in _POLICY_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return ClassificationResult(
                category=FailureCategory.POLICY,
                reason=reason,
                confidence="HIGH",
                details={"pattern": pattern, "text": text},
            )

    for pattern, reason in _PROFILE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return ClassificationResult(
                category=FailureCategory.PROFILE,
                reason=reason,
                confidence="HIGH",
                details={"pattern": pattern, "text": text},
            )

    for pattern, reason in _ADAPTER_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return ClassificationResult(
                category=FailureCategory.ADAPTER,
                reason=reason,
                confidence="HIGH",
                details={"pattern": pattern, "text": text},
            )

    for pattern, reason in _GENERATOR_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return ClassificationResult(
                category=FailureCategory.GENERATOR,
                reason=reason,
                confidence="HIGH",
                details={"pattern": pattern, "text": text},
            )

    for pattern, reason in _UPSTREAM_DRIFT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return ClassificationResult(
                category=FailureCategory.UPSTREAM_DRIFT,
                reason=reason,
                confidence="MEDIUM",
                details={"pattern": pattern, "text": text},
            )

    # 5. Generic compiler error (e.g. "error: ...")
    # Section 35: A compiler failure must not automatically be classified as generator logic failure.
    if "error:" in text.lower():
        if file_path and ("patch" in file_path or "adapter" in file_path):
            return ClassificationResult(
                category=FailureCategory.ADAPTER,
                reason=f"Compiler failure in adapter target context: {text.splitlines()[0] if text else ''}",
                confidence="MEDIUM",
                details={"text": text},
            )
        return ClassificationResult(
            category=FailureCategory.UPSTREAM_DRIFT,
            reason=f"Compiler failure: {text.splitlines()[0] if text else ''}",
            confidence="MEDIUM",
            details={"text": text},
        )

    # Default fallback
    return ClassificationResult(
        category=FailureCategory.TOOLCHAIN_ENVIRONMENT,
        reason=f"Unclassified environment/execution failure: {text[:100]}",
        confidence="LOW",
        details={"text": text, "exit_code": exit_code},
    )


__all__ = [
    "FailureCategory",
    "ClassificationResult",
    "classify_failure",
]
