"""Typed, deterministic V2.2 input and provenance records."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Mapping, Optional, Tuple


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class HashDigest:
    algorithm: str
    value: str

    def __post_init__(self) -> None:
        if self.algorithm != "sha256" or len(self.value) != 64:
            raise ValueError("only sha256 digests are supported")
        int(self.value, 16)

    @classmethod
    def parse(cls, value: str | "HashDigest") -> "HashDigest":
        if isinstance(value, cls):
            return value
        if not isinstance(value, str) or not value.startswith("sha256:"):
            raise ValueError("digest must use sha256:<hex> form")
        return cls("sha256", value[7:])

    def __str__(self) -> str:
        return f"{self.algorithm}:{self.value}"


@dataclass(frozen=True)
class InputRef:
    name: str
    kind: str
    source: str
    requested_ref: Optional[str] = None
    resolved_commit: Optional[str] = None
    tree_id: Optional[str] = None
    content_hash: Optional[HashDigest] = None
    artifact_path: Optional[str] = None
    original_source: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.name or not self.kind or not self.source:
            raise ValueError("input references require name, kind, and source")
        if self.content_hash is not None:
            object.__setattr__(self, "content_hash", HashDigest.parse(self.content_hash))
        if self.resolved_commit is None and self.kind in {"git", "repository", "tree"}:
            # A fetch may resolve this later; offline preparation cannot.
            return

    @property
    def immutable(self) -> bool:
        return bool(self.content_hash or self.resolved_commit or self.tree_id)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"name": self.name, "kind": self.kind, "source": self.source}
        for key in ("requested_ref", "resolved_commit", "tree_id", "artifact_path", "original_source"):
            value = getattr(self, key)
            if value is not None:
                result[key] = value
        if self.content_hash is not None:
            result["content_hash"] = str(self.content_hash)
        return result


class RepositoryRef(InputRef):
    def __init__(self, name: str, source: str, **kwargs: Any) -> None:
        super().__init__(name, "git", source, **kwargs)


class PatchRef(InputRef):
    def __init__(self, name: str, source: str, **kwargs: Any) -> None:
        super().__init__(name, "patch", source, **kwargs)


class FixtureRef(InputRef):
    def __init__(self, name: str, source: str, **kwargs: Any) -> None:
        super().__init__(name, "fixture", source, **kwargs)


@dataclass(frozen=True)
class PreparedSource:
    reference: InputRef
    cache_object: HashDigest
    content_hash: HashDigest

    def to_dict(self) -> dict[str, Any]:
        return {"reference": self.reference.to_dict(), "cache_object": str(self.cache_object),
                "content_hash": str(self.content_hash)}


@dataclass(frozen=True)
class Provenance:
    schema: str
    target_id: str
    profile_id: Optional[str]
    manifest_hash: HashDigest
    inputs: Tuple[PreparedSource, ...] = field(default_factory=tuple)
    preparation_version: str = "v2.2"

    def identity_payload(self) -> dict[str, Any]:
        return {"schema": self.schema, "target_id": self.target_id,
                "profile_id": self.profile_id, "manifest_hash": str(self.manifest_hash),
                "inputs": [item.to_dict() for item in self.inputs],
                "preparation_version": self.preparation_version}

    @property
    def identity(self) -> HashDigest:
        return HashDigest.parse(_digest(canonical_json(self.identity_payload())))

    def to_dict(self) -> dict[str, Any]:
        result = self.identity_payload()
        result["identity"] = str(self.identity)
        return result


@dataclass(frozen=True)
class PreparedInput:
    target_id: str
    profile_id: Optional[str]
    sources: Tuple[PreparedSource, ...]
    provenance: Provenance

    def to_dict(self) -> dict[str, Any]:
        return {"target_id": self.target_id, "profile_id": self.profile_id,
                "sources": [source.to_dict() for source in self.sources],
                "provenance": self.provenance.to_dict()}

    def to_json(self) -> str:
        return canonical_json(self.to_dict())
