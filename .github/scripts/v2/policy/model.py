"""Typed, deterministic semantic policy decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
from typing import Any, Iterable, Optional, Tuple

from ..model.provenance import HashDigest, canonical_json
from ..semantic import SemanticId


POLICY_SCHEMA = "xxksu-susfs-policy/v1"


class PolicyError(ValueError):
    pass


class PolicyIncomplete(PolicyError):
    pass


class PolicyAction(str, Enum):
    KEEP = "KEEP"
    REMOVE = "REMOVE"
    REROUTE = "REROUTE"
    SPLIT = "SPLIT"
    ADAPT = "ADAPT"
    UNKNOWN = "UNKNOWN"


class OwnerKind(str, Enum):
    PATCH_51 = "PATCH_51"
    PROFILE_MANIFEST = "PROFILE_MANIFEST"
    XXKSU_RUNTIME = "XXKSU_RUNTIME"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class PolicyOccurrence:
    semantic_id: SemanticId
    evidence_fingerprint: str
    container_id: str
    path: str
    start_line: Optional[int]
    end_line: Optional[int]  # half-open

    def __post_init__(self) -> None:
        if not self.evidence_fingerprint or not self.container_id or not self.path:
            raise PolicyError("policy occurrence requires evidence, container, and path")
        if (self.start_line is None) != (self.end_line is None):
            raise PolicyError("policy occurrence span must be fully bounded or absent")
        if self.start_line is not None and (self.start_line < 1 or self.end_line <= self.start_line):
            raise PolicyError("invalid half-open policy occurrence span")

    def to_dict(self) -> dict[str, Any]:
        return {"semantic_id": str(self.semantic_id), "evidence_fingerprint": self.evidence_fingerprint,
                "container_id": self.container_id, "path": self.path,
                "span": {"start_line": self.start_line, "end_line": self.end_line}}

    @property
    def identity(self) -> str:
        return hashlib.sha256(canonical_json(self.to_dict()).encode()).hexdigest()


@dataclass(frozen=True)
class PolicyDecision:
    occurrence: PolicyOccurrence
    action: PolicyAction
    owner: OwnerKind
    rationale: str
    preserves: Tuple[PolicyOccurrence, ...] = field(default_factory=tuple)
    replacement_sources: Tuple[SemanticId, ...] = field(default_factory=tuple)
    replacement_evidence: Tuple[str, ...] = field(default_factory=tuple)
    replacement_relation: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.rationale:
            raise PolicyError("decision requires rationale")
        if self.action == PolicyAction.UNKNOWN and self.owner != OwnerKind.UNRESOLVED:
            raise PolicyError("UNKNOWN decisions must remain unresolved")
        if self.action != PolicyAction.UNKNOWN and self.owner == OwnerKind.UNRESOLVED:
            raise PolicyError("resolved decisions require a typed owner")
        if self.action in (PolicyAction.SPLIT, PolicyAction.ADAPT):
            raise PolicyError("SPLIT is derived for mixed containers; ADAPT belongs to V2.5")
        if self.action in (PolicyAction.REMOVE, PolicyAction.REROUTE) and not self.replacement_sources:
            raise PolicyError("destructive policy requires an explicit replacement source")
        if self.replacement_sources and (not self.replacement_relation or not self.replacement_evidence):
            raise PolicyError("replacement sources require relationship evidence")
        if self.replacement_relation and not self.replacement_sources:
            raise PolicyError("replacement relationship requires a source")
        if self.replacement_evidence and not self.replacement_sources:
            raise PolicyError("replacement evidence requires a source")
        if any(not isinstance(item, PolicyOccurrence) for item in self.preserves):
            raise PolicyError("preservation claims must bind to exact occurrences")

    @property
    def semantic_id(self) -> SemanticId:
        return self.occurrence.semantic_id

    def to_dict(self) -> dict[str, Any]:
        return {"occurrence": self.occurrence.to_dict(), "action": self.action.value,
                "owner": self.owner.value, "rationale": self.rationale,
                "preserves": [item.to_dict() for item in sorted(self.preserves, key=lambda item: item.identity)],
                "replacement_sources": sorted(str(item) for item in self.replacement_sources),
                "replacement_evidence": sorted(self.replacement_evidence),
                "replacement_relation": self.replacement_relation}


@dataclass(frozen=True)
class MixedMember:
    occurrence: PolicyOccurrence
    action: PolicyAction

    def to_dict(self) -> dict[str, Any]:
        return {"occurrence": self.occurrence.to_dict(), "action": self.action.value}


@dataclass(frozen=True)
class MixedBlockDecision:
    container_id: str
    action: PolicyAction
    members: Tuple[MixedMember, ...]
    rationale: str

    def __post_init__(self) -> None:
        if not self.container_id or not self.members or not self.rationale:
            raise PolicyError("mixed block decision is incomplete")
        if self.action not in (PolicyAction.KEEP, PolicyAction.REMOVE, PolicyAction.REROUTE,
                               PolicyAction.SPLIT, PolicyAction.UNKNOWN):
            raise PolicyError("invalid mixed block action")

    def to_dict(self) -> dict[str, Any]:
        return {"container_id": self.container_id, "action": self.action.value,
                "members": [item.to_dict() for item in sorted(self.members,
                                                               key=lambda item: item.occurrence.identity)],
                "rationale": self.rationale}


class PolicyCoverageLedger:
    def __init__(self, inventory_identity: str):
        if not inventory_identity:
            raise PolicyError("policy ledger requires semantic inventory identity")
        self.inventory_identity = inventory_identity
        self._decisions: dict[str, PolicyDecision] = {}
        self._mixed: dict[str, MixedBlockDecision] = {}

    def add(self, decision: PolicyDecision) -> None:
        key = decision.occurrence.identity
        previous = self._decisions.get(key)
        if previous is not None and previous != decision:
            raise PolicyError(f"conflicting policy decision: {key}")
        self._decisions[key] = decision

    def add_mixed(self, decision: MixedBlockDecision) -> None:
        previous = self._mixed.get(decision.container_id)
        if previous is not None and previous != decision:
            raise PolicyError(f"conflicting mixed block decision: {decision.container_id}")
        self._mixed[decision.container_id] = decision

    @property
    def decisions(self) -> tuple[PolicyDecision, ...]:
        return tuple(self._decisions[key] for key in sorted(self._decisions))

    @property
    def mixed_blocks(self) -> tuple[MixedBlockDecision, ...]:
        return tuple(self._mixed[key] for key in sorted(self._mixed))

    def validate_complete(self, relevant_occurrences: Iterable[PolicyOccurrence],
                          required_mixed_occurrences: Iterable[PolicyOccurrence] = ()) -> "PolicyCoverageLedger":
        occurrences = tuple(relevant_occurrences)
        expected = {item.identity for item in occurrences}
        expected_by_id = {item.identity: item for item in occurrences}
        if not expected:
            raise PolicyIncomplete("no official 50 semantic occurrences were supplied")
        if set(self._decisions) != expected:
            missing = sorted(expected - set(self._decisions))
            extra = sorted(set(self._decisions) - expected)
            raise PolicyIncomplete(f"policy coverage mismatch; missing={missing}, extra={extra}")
        for key, decision in self._decisions.items():
            if decision.occurrence != expected_by_id[key]:
                raise PolicyIncomplete("decision occurrence does not match its covered evidence")
            for preserved in decision.preserves:
                if preserved.identity not in expected:
                    raise PolicyIncomplete("preservation references an unaccounted occurrence")
        required_mixed = tuple(required_mixed_occurrences)
        required_by_container: dict[str, set[str]] = {}
        for occurrence in required_mixed:
            required_by_container.setdefault(occurrence.container_id, set()).add(occurrence.identity)
        actual_by_container: dict[str, set[str]] = {}
        for block in self.mixed_blocks:
            actual = {member.occurrence.identity for member in block.members}
            if block.container_id in actual_by_container:
                raise PolicyIncomplete("duplicate mixed container accounting")
            actual_by_container[block.container_id] = actual
            expected_members = required_by_container.get(block.container_id)
            if expected_members != actual:
                raise PolicyIncomplete("mixed block member coverage mismatch")
            member_actions = {member.action for member in block.members}
            expected_action = next(iter(member_actions)) if len(member_actions) == 1 else PolicyAction.SPLIT
            if block.action != expected_action:
                raise PolicyIncomplete("mixed block action does not match member dispositions")
            for member in block.members:
                decision = self._decisions.get(member.occurrence.identity)
                if decision is None or decision.action != member.action:
                    raise PolicyIncomplete("mixed member action does not match policy decision")
        if set(actual_by_container) != set(required_by_container):
            raise PolicyIncomplete("mixed container accounting mismatch")
        preserve_claims: dict[str, int] = {}
        for decision in self.decisions:
            preserved = {item.identity for item in decision.preserves}
            for occurrence_id in preserved:
                preserve_claims[occurrence_id] = preserve_claims.get(occurrence_id, 0) + 1
            local_expected = required_by_container.get(decision.occurrence.container_id)
            if local_expected is not None and not preserved.issubset(local_expected):
                raise PolicyIncomplete("preservation crosses a mixed-container boundary")
        if any(count > 1 for count in preserve_claims.values()):
            raise PolicyIncomplete("one preserved occurrence cannot cover multiple transport occurrences")
        for decision in self.decisions:
            if decision.action in (PolicyAction.REMOVE, PolicyAction.REROUTE):
                if not decision.replacement_sources or not decision.replacement_relation:
                    raise PolicyIncomplete("destructive decision lacks replacement proof")
        if any(item.action == PolicyAction.UNKNOWN for item in self.decisions):
            raise PolicyIncomplete("UNKNOWN semantic decisions remain")
        if any(item.action == PolicyAction.UNKNOWN for item in self.mixed_blocks):
            raise PolicyIncomplete("unsafe or ambiguous mixed blocks remain")
        return self

    def to_dict(self) -> dict[str, Any]:
        return {"schema": POLICY_SCHEMA, "inventory_identity": self.inventory_identity,
                "decisions": [item.to_dict() for item in self.decisions],
                "mixed_blocks": [item.to_dict() for item in self.mixed_blocks]}

    def canonical_json(self) -> str:
        return canonical_json(self.to_dict())

    @property
    def identity(self) -> HashDigest:
        return HashDigest("sha256", hashlib.sha256(self.canonical_json().encode()).hexdigest())
