"""Policy-neutral semantic records for V2.3."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional, Tuple

from ..model.provenance import HashDigest, canonical_json
from ..source.hashing import validate_relative_path


SEMANTIC_SCHEMA = "xxksu-susfs-semantic/v1"


class SemanticError(ValueError):
    pass


class UnsupportedSemanticSchema(SemanticError):
    pass


class SemanticSpecificationError(SemanticError):
    pass


class SemanticResolutionError(SemanticError):
    pass


class AmbiguousSemanticMatch(SemanticResolutionError):
    pass


class UnknownSemanticUnit(SemanticResolutionError):
    pass


class SemanticIdCollision(SemanticError):
    pass


class InvalidEvidence(SemanticError):
    pass


class OrphanEvidence(SemanticError):
    pass


class InvalidRelationship(SemanticError):
    pass


class InventoryIncomplete(SemanticError):
    pass


class LedgerIncomplete(SemanticError):
    pass


class Confidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class EvidenceKind(str, Enum):
    """How an observation is tied to an input trust boundary."""

    VERIFIED = "VERIFIED"
    SYNTHETIC = "SYNTHETIC"
    UNVERIFIED = "UNVERIFIED"


class SemanticKind(str, Enum):
    SUSFS_BEHAVIOR = "SUSFS_BEHAVIOR"
    HANDLER_DEFINITION = "HANDLER_DEFINITION"
    HANDLER_DECLARATION = "HANDLER_DECLARATION"
    LINUX_CALL_SITE = "LINUX_CALL_SITE"
    RUNTIME_REGISTRATION = "RUNTIME_REGISTRATION"
    STATIC_KEY_GATE = "STATIC_KEY_GATE"
    LSM_SECURITY_HOOK = "LSM_SECURITY_HOOK"
    KPROBE = "KPROBE"
    SYSCALL_TABLE_HOOK = "SYSCALL_TABLE_HOOK"
    ARM64_BRANCH_LINK = "ARM64_BRANCH_LINK"
    MANUAL_SOURCE_HOOK = "MANUAL_SOURCE_HOOK"
    FIXTURE_HOOK = "FIXTURE_HOOK"
    CONFIG_CONTROL = "CONFIG_CONTROL"
    SELINUX_BEHAVIOR = "SELINUX_BEHAVIOR"
    TRANSPORT_WRAPPER = "TRANSPORT_WRAPPER"
    UNKNOWN = "UNKNOWN"


class RelationshipType(str, Enum):
    DEFINES = "DEFINES"
    CALLS = "CALLS"
    GATES = "GATES"
    REGISTERS = "REGISTERS"
    WRAPS = "WRAPS"
    PROVIDES_TRANSPORT_FOR = "PROVIDES_TRANSPORT_FOR"
    FALLBACK_FOR = "FALLBACK_FOR"
    REPLACES_BEHAVIOR_OF = "REPLACES_BEHAVIOR_OF"
    RELATED_TO = "RELATED_TO"


class CoverageState(str, Enum):
    IDENTIFIED = "IDENTIFIED"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"
    DUPLICATE_EVIDENCE = "DUPLICATE_EVIDENCE"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class SemanticId:
    value: str
    schema: str = SEMANTIC_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != SEMANTIC_SCHEMA:
            raise UnsupportedSemanticSchema(self.schema)
        if not self.value or any(part in self.value for part in ("/", "\\", "\n")):
            raise SemanticError("semantic ID must be a stable dotted identifier")

    def __str__(self) -> str:
        return self.value

    def to_dict(self) -> dict[str, str]:
        return {"schema": self.schema, "id": self.value}


def semantic_id(domain: str, name: str) -> SemanticId:
    if not domain or not name or any(char in domain + name for char in "/\\"):
        raise SemanticError("invalid semantic ID components")
    return SemanticId(f"{domain}.{name}")


@dataclass(frozen=True)
class SemanticLocation:
    path: str
    function: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    anchor: Optional[str] = None

    def __post_init__(self) -> None:
        try:
            normalized = validate_relative_path(self.path)
        except ValueError as exc:
            raise SemanticError(str(exc)) from exc
        object.__setattr__(self, "path", normalized)
        if self.start_line is not None and self.start_line < 1:
            raise SemanticError("location line must be positive")
        if self.end_line is not None and self.start_line is not None and self.end_line < self.start_line:
            raise SemanticError("location range is inverted")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"path": self.path}
        for key in ("function", "start_line", "end_line", "anchor"):
            value = getattr(self, key)
            if value is not None:
                result[key] = value
        return result


@dataclass(frozen=True)
class SemanticFingerprint:
    path: str
    function: Optional[str] = None
    structural_anchor: Optional[str] = None
    normalized_statements: Tuple[str, ...] = field(default_factory=tuple)
    required_symbols: Tuple[str, ...] = field(default_factory=tuple)
    called_symbols: Tuple[str, ...] = field(default_factory=tuple)
    configuration_guards: Tuple[str, ...] = field(default_factory=tuple)
    source_kind: str = "source"
    source_role: str = "observation"

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "path", validate_relative_path(self.path))
        except ValueError as exc:
            raise SemanticError(str(exc)) from exc
        for name in ("normalized_statements", "required_symbols", "called_symbols", "configuration_guards"):
            values = tuple(str(item).replace("\r\n", "\n").replace("\r", "\n") for item in getattr(self, name))
            object.__setattr__(self, name, values)

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "function": self.function, "structural_anchor": self.structural_anchor,
                "normalized_statements": list(self.normalized_statements), "required_symbols": list(self.required_symbols),
                "called_symbols": list(self.called_symbols), "configuration_guards": list(self.configuration_guards),
                "source_kind": self.source_kind, "source_role": self.source_role}

    @property
    def digest(self) -> HashDigest:
        import hashlib
        return HashDigest("sha256", hashlib.sha256(canonical_json(self.to_dict()).encode("utf-8")).hexdigest())


@dataclass(frozen=True)
class EvidenceRecord:
    source_identity: str
    source_type: str
    location: SemanticLocation
    fingerprint: SemanticFingerprint
    priority: int
    confidence: Confidence
    notes: str = ""
    attributes: Mapping[str, Any] = field(default_factory=dict)
    evidence_kind: EvidenceKind = EvidenceKind.UNVERIFIED
    provenance_identity: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.source_identity or not 1 <= self.priority <= 8:
            raise InvalidEvidence("evidence requires source identity and positive priority")
        if self.location.path != self.fingerprint.path:
            raise InvalidEvidence("location and fingerprint paths differ")
        if not isinstance(self.confidence, Confidence):
            try:
                object.__setattr__(self, "confidence", Confidence(self.confidence))
            except ValueError as exc:
                raise InvalidEvidence("invalid confidence") from exc
        if not isinstance(self.evidence_kind, EvidenceKind):
            try:
                object.__setattr__(self, "evidence_kind", EvidenceKind(self.evidence_kind))
            except ValueError as exc:
                raise InvalidEvidence("invalid evidence kind") from exc
        if self.evidence_kind == EvidenceKind.VERIFIED and not self.provenance_identity:
            raise InvalidEvidence("verified evidence requires V2.2 provenance identity")

    def validate_against(self, provenance: Any) -> None:
        """Bind verified evidence to a V2.2 Provenance or PreparedInput."""
        if self.evidence_kind != EvidenceKind.VERIFIED:
            return
        candidate = getattr(provenance, "provenance", provenance)
        expected_identity = str(getattr(candidate, "identity", ""))
        if not expected_identity or self.provenance_identity != expected_identity:
            raise InvalidEvidence("evidence provenance identity mismatch")
        source_ids = {expected_identity}
        for prepared in getattr(candidate, "inputs", ()):
            source_ids.add(str(getattr(prepared, "content_hash", "")))
            source_ids.add(str(getattr(prepared, "cache_object", "")))
        if self.source_identity not in source_ids:
            raise InvalidEvidence("evidence source is not present in prepared provenance")

    def to_dict(self) -> dict[str, Any]:
        return {"source_identity": self.source_identity, "source_type": self.source_type,
                "location": self.location.to_dict(), "fingerprint": self.fingerprint.to_dict(),
                "fingerprint_digest": str(self.fingerprint.digest), "priority": self.priority,
                "confidence": self.confidence.value, "notes": self.notes, "attributes": dict(self.attributes),
                "evidence_kind": self.evidence_kind.value,
                "provenance_identity": self.provenance_identity}


@dataclass(frozen=True)
class SemanticRelationship:
    relation: RelationshipType
    source: SemanticId
    target: SemanticId
    evidence: Tuple[EvidenceRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.relation, RelationshipType):
            try:
                object.__setattr__(self, "relation", RelationshipType(self.relation))
            except (TypeError, ValueError) as exc:
                raise InvalidRelationship("invalid relationship type") from exc
        if not isinstance(self.source, SemanticId) or not isinstance(self.target, SemanticId):
            raise InvalidRelationship("relationship endpoints must be SemanticId values")
        if any(not isinstance(item, EvidenceRecord) for item in self.evidence):
            raise InvalidRelationship("relationship evidence must be EvidenceRecord values")

    def to_dict(self) -> dict[str, Any]:
        return {"relation": self.relation.value, "source": str(self.source), "target": str(self.target),
                "evidence": sorted((item.to_dict() for item in self.evidence), key=canonical_json)}


@dataclass(frozen=True)
class SemanticUnit:
    semantic_id: SemanticId
    kind: SemanticKind
    domain: str
    location: SemanticLocation
    evidence: Tuple[EvidenceRecord, ...] = field(default_factory=tuple)
    relationships: Tuple[SemanticRelationship, ...] = field(default_factory=tuple)
    confidence: Confidence = Confidence.UNKNOWN
    state: CoverageState = CoverageState.IDENTIFIED
    contract: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.domain or not isinstance(self.kind, SemanticKind):
            raise SemanticError("semantic unit requires domain and kind")
        if self.state == CoverageState.UNKNOWN and self.kind != SemanticKind.UNKNOWN:
            raise SemanticError("unknown state requires unknown kind")
        if not isinstance(self.confidence, Confidence):
            try:
                object.__setattr__(self, "confidence", Confidence(self.confidence))
            except ValueError as exc:
                raise SemanticError("invalid confidence") from exc

    def to_dict(self) -> dict[str, Any]:
        return {"schema": self.semantic_id.schema, "semantic_id": str(self.semantic_id), "kind": self.kind.value,
                "domain": self.domain, "location": self.location.to_dict(),
                "evidence": sorted((item.to_dict() for item in self.evidence), key=canonical_json),
                "relationships": sorted((item.to_dict() for item in self.relationships), key=canonical_json),
                "confidence": self.confidence.value, "state": self.state.value, "contract": dict(self.contract)}
