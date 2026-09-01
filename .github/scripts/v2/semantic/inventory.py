"""Conservative candidate detection and semantic resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Iterable, Mapping, Optional, Tuple

from ..model.patch import Patch
from ..model.provenance import canonical_json
from .ledger import CoverageLedger
from .model import (
    AmbiguousSemanticMatch, Confidence, CoverageState, EvidenceKind, EvidenceRecord,
    SemanticFingerprint, SemanticId, SemanticKind, SemanticLocation, SemanticResolutionError,
    SemanticUnit, UnknownSemanticUnit,
)
from .registry import SemanticRegistry, SemanticSpecification, default_registry


@dataclass(frozen=True)
class CandidateObservation:
    source_identity: str
    source_type: str
    path: str
    text: str
    function: Optional[str] = None
    source_kind: str = "source"
    symbols: Tuple[str, ...] = field(default_factory=tuple)
    structural_anchor: Optional[str] = None
    container_id: Optional[str] = None
    mixed: bool = False
    start_line: Optional[int] = None
    abi: Mapping[str, Any] = field(default_factory=dict)
    role: str = "observation"
    evidence_kind: EvidenceKind = EvidenceKind.UNVERIFIED
    provenance_identity: Optional[str] = None
    prepared_source_name: Optional[str] = None


def _symbols(text: str) -> tuple[str, ...]:
    return tuple(sorted(set(re.findall(r"(?:ksu|susfs|security|input|branch_link|syscall_table)[A-Za-z0-9_]*", text))))


def _role(text: str, symbol: str) -> str:
    if re.search(rf"\bextern\b[^;]*\b{re.escape(symbol)}\s*\(", text):
        return "declaration"
    if symbol and re.search(rf"^[^;]*\b{re.escape(symbol)}\s*\([^;]*\)\s*\{{?\s*$", text.strip()):
        return "definition"
    return "caller"


def _priority(source_kind: str) -> int:
    if source_kind == "target_kernel":
        return 1
    if source_kind == "xxksu":
        return 2
    if source_kind in {"official_10", "official_50"}:
        return 3
    if source_kind.startswith("fixture_"):
        return 4
    if source_kind.startswith("known_good"):
        return 5
    if source_kind.startswith("generated"):
        return 6
    if source_kind == "generator":
        return 7
    return 8


class CandidateDetector:
    def __init__(self, registry: Optional[SemanticRegistry] = None):
        self.registry = registry or default_registry()

    def detect(self, observations: Iterable[CandidateObservation]) -> tuple[CandidateObservation, ...]:
        result = []
        known_paths = {path for spec in self.registry for path in spec.paths}
        for observation in observations:
            symbols = observation.symbols or _symbols(observation.text)
            relevant = observation.path in known_paths or bool(symbols) or "CONFIG_KSU_SUSFS" in observation.text
            if relevant:
                result.append(CandidateObservation(observation.source_identity, observation.source_type, observation.path,
                                                   observation.text, observation.function, observation.source_kind, symbols,
                                                   observation.structural_anchor, observation.container_id, observation.mixed,
                                                   observation.start_line, observation.abi, observation.role,
                                                   observation.evidence_kind, observation.provenance_identity,
                                                   observation.prepared_source_name))
        return tuple(result)


class SemanticResolver:
    def __init__(self, registry: Optional[SemanticRegistry] = None):
        self.registry = registry or default_registry()

    def resolve(self, candidate: CandidateObservation) -> SemanticUnit:
        matches = self.registry.match(candidate)
        if len(matches) > 1:
            raise AmbiguousSemanticMatch(f"{candidate.path}: {len(matches)} specifications match")
        if not matches:
            raise UnknownSemanticUnit(f"unmatched candidate at {candidate.path}")
        spec = matches[0]
        fingerprint = SemanticFingerprint(candidate.path, candidate.function, candidate.structural_anchor,
                                          tuple(candidate.text.replace("\r", "").splitlines()), (), candidate.symbols, (),
                                          candidate.source_kind, candidate.role)
        evidence = EvidenceRecord(candidate.source_identity, candidate.source_type,
                                  SemanticLocation(candidate.path, candidate.function, candidate.start_line, candidate.start_line, candidate.structural_anchor),
                                  fingerprint, _priority(candidate.source_kind), spec.confidence, spec.notes,
                                  {"container_id": candidate.container_id, "abi": dict(candidate.abi)},
                                  candidate.evidence_kind, candidate.provenance_identity,
                                  candidate.prepared_source_name)
        state = CoverageState.MIXED if candidate.mixed else CoverageState.IDENTIFIED
        return SemanticUnit(spec.semantic_id, spec.kind, spec.domain,
                            SemanticLocation(candidate.path, candidate.function, candidate.start_line, candidate.start_line, candidate.structural_anchor),
                            (evidence,), (), spec.confidence, state, {})


class SemanticInventory:
    def __init__(self, *, provenance_identity: str = "", provenance: Any = None,
                 specification_version: str = "v1", registry: Optional[SemanticRegistry] = None,
                 allow_synthetic: bool = False):
        self.registry = registry or default_registry()
        self.ledger = CoverageLedger(provenance_identity=provenance_identity,
                                     specification_version=specification_version,
                                     allow_synthetic=allow_synthetic,
                                     provenance=provenance)
        self.provenance = provenance
        self.candidates: list[CandidateObservation] = []

    def add_candidate(self, candidate: CandidateObservation) -> Optional[SemanticUnit]:
        self.candidates.append(candidate)
        try:
            unit = SemanticResolver(self.registry).resolve(candidate)
        except SemanticResolutionError as exc:
            fingerprint = SemanticFingerprint(candidate.path, candidate.function, candidate.structural_anchor,
                                              tuple(candidate.text.replace("\r", "").splitlines()), (), candidate.symbols, (),
                                              candidate.source_kind, candidate.role)
            unknown_id = SemanticId("unknown." + fingerprint.digest.value[:16])
            unit = SemanticUnit(unknown_id, SemanticKind.UNKNOWN, "unknown",
                                SemanticLocation(candidate.path, candidate.function, candidate.start_line, candidate.start_line, candidate.structural_anchor),
                                (EvidenceRecord(candidate.source_identity, candidate.source_type,
                                                SemanticLocation(candidate.path, candidate.function, candidate.start_line, candidate.start_line, candidate.structural_anchor),
                                                fingerprint, _priority(candidate.source_kind), Confidence.UNKNOWN, str(exc),
                                                {"container_id": candidate.container_id, "abi": dict(candidate.abi)},
                                                candidate.evidence_kind, candidate.provenance_identity,
                                                candidate.prepared_source_name),),
                                (), Confidence.UNKNOWN, CoverageState.UNKNOWN)
        for evidence in unit.evidence:
            evidence.validate_against(self.provenance)
        self.ledger.add(unit)
        return unit

    def add_relationship(self, relationship):
        self.ledger.add_relationship(relationship)

    def detect_and_resolve(self, observations: Iterable[CandidateObservation]) -> "SemanticInventory":
        for candidate in CandidateDetector(self.registry).detect(observations):
            self.add_candidate(candidate)
        return self

    @property
    def units(self) -> tuple[SemanticUnit, ...]:
        return tuple(entry.unit for entry in self.ledger.entries)

    def validate_complete(self) -> "SemanticInventory":
        self.ledger.validate_complete()
        return self

    def to_dict(self) -> dict:
        return {"schema": "xxksu-susfs-inventory/v1", "registry": self.registry.to_dict(),
                "ledger": self.ledger.to_dict()}

    def canonical_json(self) -> str:
        return canonical_json(self.to_dict())

    @property
    def identity(self):
        from ..model.provenance import HashDigest
        import hashlib
        return HashDigest("sha256", hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest())


def inventory_from_observations(observations: Iterable[CandidateObservation], *, provenance_identity: str = "",
                                provenance: Any = None, registry=None,
                                allow_synthetic: bool = False) -> SemanticInventory:
    return SemanticInventory(provenance_identity=provenance_identity, provenance=provenance,
                             registry=registry, allow_synthetic=allow_synthetic).detect_and_resolve(observations)


def inventory_patch(patch: Patch, *, source_identity: str, source_type: str,
                    evidence_kind: EvidenceKind = EvidenceKind.UNVERIFIED,
                    provenance_identity: Optional[str] = None,
                    prepared_source_name: Optional[str] = None, provenance: Any = None,
                    registry=None, allow_synthetic: bool = False) -> SemanticInventory:
    observations = []
    for file_patch in patch.files:
        path = file_patch.new_path or file_patch.old_path or "unknown"
        if path.startswith(("a/", "b/")):
            path = path[2:]
        for index, hunk in enumerate(file_patch.hunks):
            text = "\n".join(line.text for line in hunk.lines)
            symbols = _symbols(text)
            found = False
            for line in hunk.lines:
                for symbol in _symbols(line.text):
                    found = True
                    observations.append(CandidateObservation(source_identity, source_type, path, line.text,
                                                             hunk.section_context or None, source_type, (symbol,),
                                                             f"hunk-{index}", f"{path}:{index}", len(symbols) > 1,
                                                             line.source_line, {}, _role(line.text, symbol),
                                                             evidence_kind, provenance_identity,
                                                             prepared_source_name))
            if not found:
                observations.append(CandidateObservation(source_identity, source_type, path, text,
                                                         hunk.section_context or None, source_type, (),
                                                         f"hunk-{index}", f"{path}:{index}", False, hunk.source_line,
                                                         {}, "observation", evidence_kind, provenance_identity,
                                                         prepared_source_name))
    return inventory_from_observations(observations, provenance_identity=provenance_identity or "",
                                       provenance=provenance, registry=registry,
                                       allow_synthetic=allow_synthetic)
