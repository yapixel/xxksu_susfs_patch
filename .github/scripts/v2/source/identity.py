"""Explicit immutable identity records for Git-backed inputs."""

from __future__ import annotations

from dataclasses import dataclass

from ..model.provenance import HashDigest


def canonical_repository_url(url: str) -> str:
    """Normalize only an unambiguous trailing slash or .git suffix."""
    if not isinstance(url, str) or not url:
        raise ValueError("repository URL must be non-empty")
    result = url
    while result.endswith("/"):
        result = result[:-1]
    if result.endswith(".git"):
        result = result[:-4]
    return result


@dataclass(frozen=True)
class GitIdentity:
    repository: str
    requested_ref: str | None
    resolved_commit: str
    tree_id: str | None = None
    content_hash: HashDigest | None = None

    def __post_init__(self) -> None:
        if not self.resolved_commit:
            raise ValueError("Git identity requires an immutable commit")
        if self.content_hash is not None:
            object.__setattr__(self, "content_hash", HashDigest.parse(self.content_hash))

    def to_dict(self) -> dict[str, str | None]:
        result: dict[str, str | None] = {"repository": self.repository,
                                         "repository_identity": canonical_repository_url(self.repository),
                                         "requested_ref": self.requested_ref,
                                         "resolved_commit": self.resolved_commit,
                                         "tree_id": self.tree_id}
        result["content_hash"] = str(self.content_hash) if self.content_hash else None
        return result
