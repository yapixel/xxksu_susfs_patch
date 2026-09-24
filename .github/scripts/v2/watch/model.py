"""Data models and classifications for upstream watch and auto-maintenance."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional, Tuple


class WatchClassification(str, Enum):
    """Authoritative outcome classification for an upstream watch evaluation."""
    NO_CHANGE = "NO_CHANGE"
    IRRELEVANT_CHANGE = "IRRELEVANT_CHANGE"
    SAFE_REGEN_CANDIDATE = "SAFE_REGEN_CANDIDATE"
    SEMANTIC_DRIFT = "SEMANTIC_DRIFT"
    ANCHOR_DRIFT = "ANCHOR_DRIFT"
    REFERENCE_DRIFT = "REFERENCE_DRIFT"
    SOURCE_IDENTITY_ERROR = "SOURCE_IDENTITY_ERROR"


@dataclass(frozen=True)
class SourceResult:
    """Evaluation result for a single tracked upstream source."""
    source_id: str
    source_type: str  # "authoritative" | "reference"
    classification: WatchClassification
    old_identity: str
    new_identity: str
    old_content_hash: str
    new_content_hash: str
    affected_files: Tuple[str, ...] = ()
    affected_semantics: Tuple[str, ...] = ()
    details: str = ""
    candidate_patch: Optional[str] = None
    candidate_patch_name: Optional[str] = None
    reproduction_command: str = ""

    def requires_escalation(self) -> bool:
        """True if this result represents a failure requiring human/AGY intervention."""
        return self.classification in (
            WatchClassification.SEMANTIC_DRIFT,
            WatchClassification.ANCHOR_DRIFT,
            WatchClassification.SOURCE_IDENTITY_ERROR,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "classification": self.classification.value,
            "old_identity": self.old_identity,
            "new_identity": self.new_identity,
            "old_content_hash": self.old_content_hash,
            "new_content_hash": self.new_content_hash,
            "affected_files": list(self.affected_files),
            "affected_semantics": list(self.affected_semantics),
            "details": self.details,
            "has_candidate_patch": bool(self.candidate_patch),
            "candidate_patch_name": self.candidate_patch_name,
            "reproduction_command": self.reproduction_command,
        }


@dataclass(frozen=True)
class WatchReport:
    """Aggregate report across all tracked sources."""
    results: Tuple[SourceResult, ...]
    timestamp: str
    escalations: Tuple[Mapping[str, str], ...] = ()

    @property
    def has_failures(self) -> bool:
        return any(r.requires_escalation() for r in self.results)

    @property
    def has_candidates(self) -> bool:
        return any(r.classification == WatchClassification.SAFE_REGEN_CANDIDATE for r in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "results": [r.to_dict() for r in self.results],
            "escalations": list(self.escalations),
            "summary": {
                c.value: sum(1 for r in self.results if r.classification == c)
                for c in WatchClassification
            },
        }


__all__ = [
    "WatchClassification",
    "SourceResult",
    "WatchReport",
]
