"""Offline manifest preparation and provenance assembly."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from ..model.manifest import ManifestSet, ProfileManifest, TargetManifest
from ..model.provenance import HashDigest, InputRef, PreparedInput, PreparedSource, Provenance, canonical_json
from .cache import CacheError, CacheObjectMissing, ContentAddressedCache
from .hashing import hash_file, validate_relative_path


class OfflineInputMissing(CacheError):
    pass


class UnresolvedSourceIdentity(CacheError):
    pass


def _manifest_hash(target: TargetManifest, profile: Optional[ProfileManifest]) -> HashDigest:
    value = {"target": target.to_dict(), "profile": profile.to_dict() if profile else None}
    import hashlib
    return HashDigest("sha256", hashlib.sha256(canonical_json(value).encode()).hexdigest())


def _refs(target: TargetManifest, profile: Optional[ProfileManifest]) -> Iterable[InputRef]:
    yield from target.inputs
    if profile:
        yield from profile.fixtures


def prepare(target: TargetManifest | ManifestSet, cache: ContentAddressedCache,
            profile: ProfileManifest | str | None = None, *, offline: bool = True,
            repository_root: Path | str | None = None) -> PreparedInput:
    if isinstance(target, ManifestSet):
        manifest_set = target.validate()
        profile_obj = next((item for item in manifest_set.profiles if item.profile_id == profile), None) if isinstance(profile, str) else profile
        if profile_obj is None and profile is not None:
            raise OfflineInputMissing("profile is not part of manifest set")
        if profile_obj is not None:
            profile_obj.validate(manifest_set.target)
        target_obj = manifest_set.target
    else:
        target_obj = target.validate()
        profile_obj = profile
        if profile_obj is not None:
            profile_obj.validate(target_obj)
    if not offline:
        raise ValueError("prepare is offline-only; call fetch explicitly before prepare")
    sources: list[PreparedSource] = []
    seen: set[str] = set()
    for ref in _refs(target_obj, profile_obj):
        if ref.name in seen:
            raise ValueError(f"duplicate input name: {ref.name}")
        seen.add(ref.name)
        digest = ref.content_hash
        if digest is None:
            raise UnresolvedSourceIdentity(f"{ref.name} has no immutable content hash")
        try:
            entry = cache._verify(digest)
        except CacheObjectMissing as exc:
            if repository_root is not None and ref.artifact_path:
                rel = validate_relative_path(ref.artifact_path)
                path = Path(repository_root).resolve() / rel
                if path.is_file() and hash_file(path) == digest:
                    entry = cache.put_file(path, digest)
                else:
                    raise OfflineInputMissing(ref.name) from exc
            else:
                raise OfflineInputMissing(ref.name) from exc
        except CacheError:
            raise
        sources.append(PreparedSource(ref, entry.digest, entry.digest))
    sources_tuple = tuple(sources)
    provenance = Provenance("xxksu-susfs-provenance/v1", target_obj.target_id,
                            profile_obj.profile_id if profile_obj else None,
                            _manifest_hash(target_obj, profile_obj), sources_tuple)
    return PreparedInput(target_obj.target_id, profile_obj.profile_id if profile_obj else None,
                         sources_tuple, provenance)
