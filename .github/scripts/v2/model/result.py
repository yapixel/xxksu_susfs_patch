class PatchError(ValueError):
    """Base class for explicit structural patch failures."""

    def __init__(self, message, *, line=None, path=None, hunk=None):
        self.line = line
        self.path = path
        self.hunk = hunk
        details = []
        if line is not None:
            details.append(f"line {line}")
        if path:
            details.append(path)
        if hunk:
            details.append(hunk)
        prefix = f"({' / '.join(details)}) " if details else ""
        super().__init__(prefix + message)


class PatchParseError(PatchError):
    pass


class MalformedFileHeader(PatchParseError):
    pass


class MalformedHunkHeader(PatchParseError):
    pass


class InvalidHunkLine(PatchParseError):
    pass


class HunkCountMismatch(PatchParseError):
    pass


class UnsupportedPatchFormat(PatchParseError):
    pass


class PatchEmitError(PatchError):
    pass


from dataclasses import dataclass, field
from enum import Enum
import hashlib
from typing import Any, Mapping, Optional, Tuple

from .provenance import HashDigest, canonical_json


class ValidationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    RUNTIME_REQUIRED = "RUNTIME_REQUIRED"
    UNRESOLVED = "UNRESOLVED"


class ValidationError(ValueError):
    """Base class for V2.8 validation quality gate failures."""
    pass


class OfficialSymbolLeakage(ValidationError):
    pass


class MissingRequiredSymbol(ValidationError):
    pass


class UnexpectedSymbolOwnership(ValidationError):
    pass


class MissingSymbolEvidence(ValidationError):
    pass


class HandlerABIConflict(ValidationError):
    pass


class AbiSignatureMismatch(HandlerABIConflict):
    pass


class AbiLinkageConflict(HandlerABIConflict):
    pass


class MissingAbiEvidence(HandlerABIConflict):
    pass


class AmbiguousAbiMapping(HandlerABIConflict):
    pass


class ZeroOwner(ValidationError):
    pass


class NoOwner(ZeroOwner):
    pass


class DuplicateOwner(ValidationError):
    pass


class DoubleTransport(DuplicateOwner):
    pass


class DoubleSideEffect(DuplicateOwner):
    pass


class IncompatibleOwner(ValidationError):
    pass


class UndeclaredCoexistence(ValidationError):
    pass


class SourceBundleIdentityMismatch(ValidationError):
    pass


class PolicyLedgerMismatch(ValidationError):
    pass


class FinalConfigMismatch(ValidationError):
    """Raised when resolved .config diverges from expected profile configuration."""
    pass


class KconfigConflict(FinalConfigMismatch):
    """Raised when conflicting or mutually exclusive Kconfig options are detected."""
    pass


class MissingPrerequisite(ValidationError):
    """Raised when architectural or kernel prerequisites (e.g. arm64, KALLSYMS) are unmet."""
    pass


@dataclass(frozen=True)
class ValidationResult:
    validator_id: str
    status: ValidationStatus
    target: str
    details: str
    path: Optional[str] = None
    line: Optional[int] = None
    context: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "validator_id": self.validator_id,
            "status": self.status.value,
            "target": self.target,
            "details": self.details,
            "path": self.path,
            "line": self.line,
            "context": self.context,
            "metadata": dict(self.metadata),
        }

    def canonical_json(self) -> str:
        return canonical_json(self.to_dict())

    @property
    def identity(self) -> HashDigest:
        return HashDigest("sha256", hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest())


@dataclass(frozen=True)
class ValidationReport:
    results: Tuple[ValidationResult, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> ValidationStatus:
        if any(r.status == ValidationStatus.FAIL for r in self.results):
            return ValidationStatus.FAIL
        if any(r.status == ValidationStatus.RUNTIME_REQUIRED for r in self.results):
            return ValidationStatus.RUNTIME_REQUIRED
        if any(r.status == ValidationStatus.UNRESOLVED for r in self.results):
            return ValidationStatus.UNRESOLVED
        if any(r.status == ValidationStatus.PASS for r in self.results):
            return ValidationStatus.PASS
        return ValidationStatus.NOT_APPLICABLE

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "results": [r.to_dict() for r in self.results],
            "metadata": dict(self.metadata),
        }

    def canonical_json(self) -> str:
        return canonical_json(self.to_dict())

    @property
    def digest(self) -> HashDigest:
        return HashDigest("sha256", hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest())

    def raise_for_status(self) -> None:
        for r in self.results:
            if r.status == ValidationStatus.FAIL:
                err_type_name = r.metadata.get("error_type")
                if err_type_name and err_type_name in globals():
                    err_cls = globals()[err_type_name]
                    raise err_cls(r.details)
                raise ValidationError(r.details)
