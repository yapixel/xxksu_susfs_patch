"""Deterministic source-bundle identity and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Tuple

from ..model.manifest import KNOWN_TARGETS
from ..model.provenance import HashDigest, canonical_json
from .hashing import validate_relative_path


SOURCE_BUNDLE_SCHEMA = "xxksu-susfs-source-bundle/v1"


class SourceBundleError(ValueError):
    """Base error for source-bundle operations."""
    pass


class UnsupportedBundleSchema(SourceBundleError):
    pass


class UnsupportedTarget(SourceBundleError):
    pass


class UnsupportedKernelVersion(SourceBundleError):
    pass


class CorruptedSourceBundle(SourceBundleError):
    pass


class MissingBundleFile(SourceBundleError):
    pass


class DuplicateBundleFile(SourceBundleError):
    pass


def _validate_target_version(target_id: str, kernel_version: str) -> None:
    if target_id not in KNOWN_TARGETS:
        raise UnsupportedTarget(f"unknown or unsupported target: {target_id}")
    if not kernel_version or not isinstance(kernel_version, str):
        raise UnsupportedKernelVersion("kernel version must be a non-empty string")

    if target_id == "gki-android14-6.1":
        if not (kernel_version == "6.1" or kernel_version.startswith("6.1.") or kernel_version.startswith("6.1-")):
            raise UnsupportedKernelVersion(f"kernel version {kernel_version} incompatible with {target_id}")
    elif target_id == "gki-android16-6.12":
        if not (kernel_version == "6.12" or kernel_version.startswith("6.12.") or kernel_version.startswith("6.12-")):
            raise UnsupportedKernelVersion(f"kernel version {kernel_version} incompatible with {target_id}")
    elif target_id == "sultan-android14-6.1":
        if not (kernel_version == "6.1" or kernel_version.startswith("6.1.") or kernel_version.startswith("6.1-")):
            raise UnsupportedKernelVersion(f"kernel version {kernel_version} incompatible with {target_id}")


@dataclass(frozen=True)
class SourceBundleFile:
    path: str
    content_hash: HashDigest
    size: int
    content: Optional[str] = None

    def __post_init__(self) -> None:
        norm_path = validate_relative_path(self.path)
        if norm_path != self.path:
            object.__setattr__(self, "path", norm_path)
        if not isinstance(self.content_hash, HashDigest):
            object.__setattr__(self, "content_hash", HashDigest.parse(self.content_hash))
        if self.size < 0:
            raise SourceBundleError("file size cannot be negative")
        if self.content is not None:
            content_bytes = self.content.encode("utf-8")
            actual_size = len(content_bytes)
            if actual_size != self.size:
                raise CorruptedSourceBundle(
                    f"size mismatch for {self.path}: declared {self.size}, actual {actual_size}"
                )
            actual_hash = HashDigest("sha256", hashlib.sha256(content_bytes).hexdigest())
            if actual_hash != self.content_hash:
                raise CorruptedSourceBundle(
                    f"hash mismatch for {self.path}: declared {self.content_hash}, actual {actual_hash}"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "content_hash": str(self.content_hash),
            "size": self.size,
        }


@dataclass(frozen=True)
class SourceBundle:
    target_id: str
    kernel_version: str
    files: Tuple[SourceBundleFile, ...]
    schema: str = SOURCE_BUNDLE_SCHEMA
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema != SOURCE_BUNDLE_SCHEMA:
            raise UnsupportedBundleSchema(f"unsupported bundle schema: {self.schema}")
        _validate_target_version(self.target_id, self.kernel_version)
        seen: set[str] = set()
        for f in self.files:
            if not isinstance(f, SourceBundleFile):
                raise SourceBundleError(f"invalid file entry: {f}")
            if f.path in seen:
                raise DuplicateBundleFile(f"duplicate file in bundle: {f.path}")
            seen.add(f.path)
        sorted_files = tuple(sorted(self.files, key=lambda item: item.path))
        if sorted_files != self.files:
            object.__setattr__(self, "files", sorted_files)

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "target_id": self.target_id,
            "kernel_version": self.kernel_version,
            "files": [f.to_dict() for f in self.files],
            "metadata": dict(self.metadata),
        }

    def canonical_json(self) -> str:
        return canonical_json(self.identity_payload())

    @property
    def identity(self) -> HashDigest:
        return HashDigest("sha256", hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest())

    @property
    def file_paths(self) -> Tuple[str, ...]:
        return tuple(f.path for f in self.files)

    def has_file(self, path: str) -> bool:
        norm = validate_relative_path(path)
        return any(f.path == norm for f in self.files)

    def get_file(self, path: str) -> SourceBundleFile:
        norm = validate_relative_path(path)
        for f in self.files:
            if f.path == norm:
                return f
        raise MissingBundleFile(f"file not found in bundle: {path}")

    def verify_file(self, path: str, content: str | bytes) -> bool:
        entry = self.get_file(path)
        raw_bytes = content.encode("utf-8") if isinstance(content, str) else content
        actual_hash = HashDigest("sha256", hashlib.sha256(raw_bytes).hexdigest())
        if actual_hash != entry.content_hash:
            raise CorruptedSourceBundle(
                f"content hash mismatch for {path}: expected {entry.content_hash}, got {actual_hash}"
            )
        if len(raw_bytes) != entry.size:
            raise CorruptedSourceBundle(
                f"size mismatch for {path}: expected {entry.size}, got {len(raw_bytes)}"
            )
        return True

    def with_file_content(self, path: str, content: str) -> "SourceBundle":
        norm = validate_relative_path(path)
        new_files = []
        found = False
        for f in self.files:
            if f.path == norm:
                new_files.append(SourceBundleFile(f.path, f.content_hash, f.size, content=content))
                found = True
            else:
                new_files.append(f)
        if not found:
            raise MissingBundleFile(f"file not found in bundle: {path}")
        return SourceBundle(
            target_id=self.target_id,
            kernel_version=self.kernel_version,
            files=tuple(new_files),
            schema=self.schema,
            metadata=self.metadata,
        )


def create_source_bundle(
    target_id: str,
    kernel_version: str,
    files: Mapping[str, str] | Iterable[SourceBundleFile],
    metadata: Optional[Mapping[str, Any]] = None,
) -> SourceBundle:
    if isinstance(files, Mapping):
        file_objs = []
        for path, content in files.items():
            content_bytes = content.encode("utf-8")
            digest = HashDigest("sha256", hashlib.sha256(content_bytes).hexdigest())
            file_objs.append(SourceBundleFile(path, digest, len(content_bytes), content=content))
        file_tuple = tuple(file_objs)
    else:
        file_tuple = tuple(files)
    return SourceBundle(
        target_id=target_id,
        kernel_version=kernel_version,
        files=file_tuple,
        metadata=metadata or {},
    )


def load_source_bundle(data: Any) -> SourceBundle:
    if isinstance(data, (str, Path)):
        if isinstance(data, str) and data.lstrip().startswith("{"):
            raw = json.loads(data)
        else:
            raw = json.loads(Path(data).read_text(encoding="utf-8"))
    elif isinstance(data, Mapping):
        raw = data
    else:
        raise SourceBundleError("source bundle data must be JSON string, Path, or Mapping")

    schema = raw.get("schema", SOURCE_BUNDLE_SCHEMA)
    target_id = raw.get("target_id")
    kernel_version = raw.get("kernel_version")
    if not target_id or not kernel_version:
        raise SourceBundleError("source bundle requires target_id and kernel_version")

    file_list = []
    for item in raw.get("files", []):
        file_list.append(
            SourceBundleFile(
                path=item["path"],
                content_hash=HashDigest.parse(item["content_hash"]),
                size=item["size"],
                content=item.get("content"),
            )
        )
    return SourceBundle(
        target_id=target_id,
        kernel_version=kernel_version,
        files=tuple(file_list),
        schema=schema,
        metadata=raw.get("metadata", {}),
    )
