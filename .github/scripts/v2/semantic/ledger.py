"""Deterministic semantic coverage/accounting ledger."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Iterable, Mapping, Optional

from ..model.provenance import canonical_json
from .model import (
    CoverageState, EvidenceKind, EvidenceRecord, InventoryIncomplete, InvalidRelationship,
    LedgerIncomplete, OrphanEvidence, SemanticId, SemanticIdCollision,
    SemanticRelationship, SemanticUnit,
)


@dataclass(frozen=True)
class LedgerEntry:
    unit: SemanticUnit

    @property
    def semantic_id(self) -> SemanticId:
        return self.unit.semantic_id

    def to_dict(self) -> dict[str, Any]:
        return self.unit.to_dict()


class CoverageLedger:
    def __init__(self, *, provenance_identity: str = "", specification_version: str = "v1"):
        self.provenance_identity = provenance_identity
        self.specification_version = specification_version
        self._entries: dict[str, LedgerEntry] = {}
        self._orphan_evidence: list[EvidenceRecord] = []

    def add(self, unit: SemanticUnit) -> LedgerEntry:
        key = str(unit.semantic_id)
        previous = self._entries.get(key)
        if previous is not None:
            old = previous.unit
            if old.kind != unit.kind or old.domain != unit.domain or dict(old.contract) != dict(unit.contract):
                raise SemanticIdCollision(f"incompatible semantic ID: {key}")
            locations = sorted((old.location, unit.location), key=lambda item: canonical_json(item.to_dict()))
            rank = {"UNKNOWN": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
            confidence = min((old.confidence, unit.confidence), key=lambda item: rank[item.value])
            states = {old.state, unit.state}
            state = (CoverageState.UNKNOWN if CoverageState.UNKNOWN in states else
                     CoverageState.UNRESOLVED if CoverageState.UNRESOLVED in states else
                     CoverageState.MIXED if CoverageState.MIXED in states else CoverageState.IDENTIFIED)
            merged = SemanticUnit(old.semantic_id, old.kind, old.domain, locations[0],
                                  tuple(old.evidence) + tuple(item for item in unit.evidence if item not in old.evidence),
                                  tuple(old.relationships) + tuple(item for item in unit.relationships if item not in old.relationships),
                                  confidence, state,
                                  old.contract)
            entry = LedgerEntry(merged)
            self._entries[key] = entry
            return entry
        entry = LedgerEntry(unit)
        self._entries[key] = entry
        return entry

    def add_evidence(self, semantic_id: SemanticId | str, evidence: EvidenceRecord) -> None:
        key = str(semantic_id)
        entry = self._entries.get(key)
        if entry is None:
            self._orphan_evidence.append(evidence)
            raise OrphanEvidence(f"evidence has no semantic unit: {key}")
        unit = entry.unit
        self._entries[key] = LedgerEntry(SemanticUnit(unit.semantic_id, unit.kind, unit.domain, unit.location,
                                                       unit.evidence + (evidence,), unit.relationships, unit.confidence,
                                                       unit.state, unit.contract))

    def add_relationship(self, relationship: SemanticRelationship) -> None:
        if str(relationship.source) not in self._entries or str(relationship.target) not in self._entries:
            raise InvalidRelationship("relationship references an unknown semantic unit")
        source = self._entries[str(relationship.source)].unit
        self._entries[str(relationship.source)] = LedgerEntry(
            SemanticUnit(source.semantic_id, source.kind, source.domain, source.location, source.evidence,
                         source.relationships + (relationship,), source.confidence, source.state, source.contract))

    @property
    def entries(self) -> tuple[LedgerEntry, ...]:
        return tuple(self._entries[key] for key in sorted(self._entries))

    @property
    def unknown_count(self) -> int:
        return sum(entry.unit.state in (CoverageState.UNKNOWN, CoverageState.UNRESOLVED) for entry in self.entries)

    @property
    def orphan_evidence(self) -> tuple[EvidenceRecord, ...]:
        return tuple(self._orphan_evidence)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": "xxksu-susfs-ledger/v1", "provenance_identity": self.provenance_identity,
                "specification_version": self.specification_version,
                "entries": [entry.to_dict() for entry in self.entries],
                "orphan_evidence": sorted((item.to_dict() for item in self._orphan_evidence), key=canonical_json)}

    def canonical_json(self) -> str:
        return canonical_json(self.to_dict())

    @property
    def identity(self):
        from ..model.provenance import HashDigest
        return HashDigest("sha256", hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest())

    def validate_complete(self) -> "CoverageLedger":
        if self.unknown_count:
            raise InventoryIncomplete(f"{self.unknown_count} relevant unknown semantic units")
        if self._orphan_evidence:
            raise LedgerIncomplete("orphan evidence remains")
        if any(item.evidence_kind == EvidenceKind.UNVERIFIED
               for entry in self.entries for item in entry.unit.evidence):
            raise InventoryIncomplete("unverified evidence remains")
        known = set(self._entries)
        for entry in self.entries:
            for relationship in entry.unit.relationships:
                if str(relationship.target) not in known or str(relationship.source) not in known:
                    raise LedgerIncomplete("orphan relationship remains")
        return self


InventoryLedger = CoverageLedger
