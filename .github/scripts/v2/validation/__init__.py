"""Unified validation facade for V2.8 static quality gates."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping, Optional, Sequence, Tuple, Union

from ..model.patch import Patch
from ..model.provenance import HashDigest, canonical_json
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
    ValidationReport,
    ValidationResult,
    ValidationStatus,
    ZeroOwner,
)
from ..policy.model import OwnerKind, PolicyAction, PolicyCoverageLedger
from ..source.bundle import CorruptedSourceBundle, SourceBundle
from .abi import (
    DEFAULT_ABI_CONTRACTS,
    AbiContract,
    AbiSignature,
    normalize_c_type,
    parse_c_signatures,
    validate_abi,
    validate_signature_against_contract,
)
from .config import parse_kconfig, validate_config
from .ownership import (
    PATH_ALIASES,
    TRANSPORT_SENSITIVE_PATHS,
    OwnershipClaim,
    make_default_lsm_bl_claims,
    make_default_manual_claims,
    normalize_path_name,
    validate_ownership,
)
from .symbols import (
    BANNED_OFFICIAL_SYMBOLS,
    DEFAULT_SYMBOL_CONTRACTS,
    SymbolContract,
    validate_symbols,
)


def validate_bundle_integrity(
    bundle: SourceBundle,
    raise_on_failure: bool = False,
) -> ValidationResult:
    """Validate that the SourceBundle satisfies internal schema, file hashes, and identity."""
    try:
        if not isinstance(bundle, SourceBundle):
            raise SourceBundleIdentityMismatch("object is not a SourceBundle")
        if bundle.schema != "xxksu-susfs-source-bundle/v1":
            raise SourceBundleIdentityMismatch(f"unsupported bundle schema: {bundle.schema}")
        for f in bundle.files:
            if f.content is not None:
                content_bytes = f.content.encode("utf-8")
                if len(content_bytes) != f.size:
                    raise CorruptedSourceBundle(f"size mismatch for {f.path}")
                actual_hash = HashDigest("sha256", hashlib.sha256(content_bytes).hexdigest())
                if actual_hash != f.content_hash:
                    raise CorruptedSourceBundle(f"hash mismatch for {f.path}")
        expected_identity = hashlib.sha256(bundle.canonical_json().encode("utf-8")).hexdigest()
        if bundle.identity.value != expected_identity:
            raise SourceBundleIdentityMismatch("bundle identity does not match canonical manifest")
        return ValidationResult(
            validator_id="validation.integrity.bundle",
            status=ValidationStatus.PASS,
            target=bundle.target_id,
            details=f"SourceBundle '{bundle.target_id}' integrity verified ({len(bundle.files)} files)",
            metadata={"bundle_identity": str(bundle.identity)},
        )
    except Exception as exc:
        res = ValidationResult(
            validator_id="validation.integrity.bundle",
            status=ValidationStatus.FAIL,
            target=getattr(bundle, "target_id", "unknown"),
            details=f"SourceBundle integrity failure: {exc}",
            metadata={"error_type": "SourceBundleIdentityMismatch"},
        )
        if raise_on_failure:
            if isinstance(exc, (SourceBundleIdentityMismatch, CorruptedSourceBundle)):
                raise
            raise SourceBundleIdentityMismatch(res.details) from exc
        return res


def validate_ledger_integrity(
    ledger: PolicyCoverageLedger,
    expected_inventory_identity: Optional[str] = None,
    raise_on_failure: bool = False,
) -> ValidationResult:
    """Validate that the PolicyCoverageLedger contains complete resolved decisions without UNKNOWN."""
    try:
        if not hasattr(ledger, "decisions") or not hasattr(ledger, "inventory_identity"):
            raise PolicyLedgerMismatch("object is not a valid PolicyCoverageLedger")
        if not ledger.decisions:
            raise PolicyLedgerMismatch("policy coverage ledger has zero decisions")
        if expected_inventory_identity and ledger.inventory_identity != expected_inventory_identity:
            raise PolicyLedgerMismatch(
                f"ledger inventory identity mismatch: expected {expected_inventory_identity}, got {ledger.inventory_identity}"
            )
        for d in ledger.decisions:
            if d.action == PolicyAction.UNKNOWN or d.owner == OwnerKind.UNRESOLVED:
                raise PolicyLedgerMismatch(f"ledger contains UNKNOWN disposition: {d.semantic_id}")
        for b in ledger.mixed_blocks:
            if b.action == PolicyAction.UNKNOWN:
                raise PolicyLedgerMismatch(f"ledger contains UNKNOWN mixed block: {b.container_id}")
        return ValidationResult(
            validator_id="validation.integrity.ledger",
            status=ValidationStatus.PASS,
            target=ledger.inventory_identity,
            details=f"PolicyCoverageLedger verified ({len(ledger.decisions)} decisions, 0 UNKNOWN)",
            metadata={"inventory_identity": ledger.inventory_identity},
        )
    except Exception as exc:
        res = ValidationResult(
            validator_id="validation.integrity.ledger",
            status=ValidationStatus.FAIL,
            target=getattr(ledger, "inventory_identity", "unknown"),
            details=f"PolicyCoverageLedger mismatch: {exc}",
            metadata={"error_type": "PolicyLedgerMismatch"},
        )
        if raise_on_failure:
            raise PolicyLedgerMismatch(res.details) from exc
        return res


def validate_all(
    *,
    bundle: Optional[SourceBundle] = None,
    patch: Optional[Union[str, Patch]] = None,
    ledger: Optional[PolicyCoverageLedger] = None,
    config: Optional[Union[str, Mapping[str, str]]] = None,
    expected_config: Optional[Mapping[str, str]] = None,
    mode: str = "manual",
    claims: Optional[Sequence[OwnershipClaim]] = None,
    contracts_symbols: Sequence[SymbolContract] = DEFAULT_SYMBOL_CONTRACTS,
    contracts_abi: Sequence[AbiContract] = DEFAULT_ABI_CONTRACTS,
    expected_inventory_identity: Optional[str] = None,
    allow_synthetic: bool = False,
    runtime_probes_required: bool = False,
    raise_on_failure: bool = False,
) -> ValidationReport:
    """Execute all static validators deterministically and produce an aggregate ValidationReport."""
    results: list[ValidationResult] = []

    # 1. Bundle integrity check
    if bundle is not None:
        bundle_res = validate_bundle_integrity(bundle, raise_on_failure=raise_on_failure)
        results.append(bundle_res)

    # 2. Ledger integrity check
    if ledger is not None:
        ledger_res = validate_ledger_integrity(
            ledger,
            expected_inventory_identity=expected_inventory_identity,
            raise_on_failure=raise_on_failure,
        )
        results.append(ledger_res)

    # 3. Symbol validation
    symbol_results = validate_symbols(
        bundle=bundle,
        patch=patch,
        contracts=contracts_symbols,
        allow_synthetic=allow_synthetic,
        raise_on_failure=raise_on_failure,
    )
    results.extend(symbol_results)

    # 4. ABI validation
    abi_results = validate_abi(
        bundle=bundle,
        contracts=contracts_abi,
        allow_synthetic=allow_synthetic,
        raise_on_failure=raise_on_failure,
    )
    results.extend(abi_results)

    # 5. Ownership validation
    if claims is not None:
        ownership_results = validate_ownership(
            mode=mode,
            claims=claims,
            bundle=bundle,
            raise_on_failure=raise_on_failure,
        )
        results.extend(ownership_results)

    # 6. Final config validation
    if config is not None and expected_config is not None:
        config_res = validate_config(
            expected=expected_config,
            resolved=config,
            mode=mode,
            raise_on_failure=raise_on_failure,
        )
        results.append(config_res)

    # 7. Runtime required gate tracking (classified, not silently passed)
    if runtime_probes_required:
        results.append(ValidationResult(
            validator_id="validation.runtime.probe",
            status=ValidationStatus.RUNTIME_REQUIRED,
            target="runtime_observability_gate",
            details="Runtime kernel probes required before final release gate clearance",
        ))

    # Deterministic sort order
    sorted_results = tuple(sorted(
        results,
        key=lambda r: (r.validator_id, r.target, r.path or "", r.line or 0, r.status.value),
    ))

    report = ValidationReport(results=sorted_results, metadata={"mode": mode})

    if raise_on_failure and report.status == ValidationStatus.FAIL:
        report.raise_for_status()

    return report


__all__ = [
    # Facade functions
    "validate_symbols",
    "validate_abi",
    "validate_ownership",
    "validate_bundle_integrity",
    "validate_ledger_integrity",
    "validate_config",
    "parse_kconfig",
    "validate_all",
    "validate_signature_against_contract",
    # Result models
    "ValidationStatus",
    "ValidationResult",
    "ValidationReport",
    "ValidationError",
    # Exceptions
    "OfficialSymbolLeakage",
    "MissingRequiredSymbol",
    "UnexpectedSymbolOwnership",
    "MissingSymbolEvidence",
    "HandlerABIConflict",
    "AbiSignatureMismatch",
    "AbiLinkageConflict",
    "MissingAbiEvidence",
    "AmbiguousAbiMapping",
    "ZeroOwner",
    "NoOwner",
    "DuplicateOwner",
    "DoubleTransport",
    "DoubleSideEffect",
    "IncompatibleOwner",
    "UndeclaredCoexistence",
    "SourceBundleIdentityMismatch",
    "PolicyLedgerMismatch",
    "FinalConfigMismatch",
    "KconfigConflict",
    "MissingPrerequisite",
    "BuildFailure",
    # Contracts & specifications
    "SymbolContract",
    "BANNED_OFFICIAL_SYMBOLS",
    "DEFAULT_SYMBOL_CONTRACTS",
    "AbiContract",
    "AbiSignature",
    "DEFAULT_ABI_CONTRACTS",
    "normalize_c_type",
    "parse_c_signatures",
    "OwnershipClaim",
    "TRANSPORT_SENSITIVE_PATHS",
    "PATH_ALIASES",
    "normalize_path_name",
    "make_default_manual_claims",
    "make_default_lsm_bl_claims",
]
