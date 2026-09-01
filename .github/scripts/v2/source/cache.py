"""Small immutable SHA-256 content-addressed cache."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile

from ..model.provenance import HashDigest
from .hashing import hash_bytes, validate_relative_path


class CacheError(ValueError):
    pass


class CacheObjectMissing(CacheError):
    pass


class CacheCorruption(CacheError):
    pass


@dataclass(frozen=True)
class CacheEntry:
    digest: HashDigest
    path: Path
    size: int


class ContentAddressedCache:
    def __init__(self, root: os.PathLike[str] | str):
        self.root = Path(root).resolve()
        self.objects = self.root / "objects" / "sha256"
        self.objects.mkdir(parents=True, exist_ok=True)

    def _path(self, digest: HashDigest | str) -> Path:
        digest = HashDigest.parse(digest)
        return self.objects / digest.value[:2] / digest.value[2:]

    def put_bytes(self, data: bytes, digest: HashDigest | str | None = None) -> CacheEntry:
        actual = hash_bytes(data)
        expected = HashDigest.parse(digest) if digest is not None else actual
        if expected != actual:
            raise CacheCorruption("content does not match declared digest")
        target = self._path(expected)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            return self._verify(expected)
        fd, temp_name = tempfile.mkstemp(prefix=".tmp-", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            if hash_bytes(Path(temp_name).read_bytes()) != expected:
                raise CacheCorruption("temporary cache object changed")
            os.replace(temp_name, target)
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
        return self._verify(expected)

    def put_file(self, path: os.PathLike[str] | str, digest: HashDigest | str | None = None) -> CacheEntry:
        return self.put_bytes(Path(path).read_bytes(), digest)

    def _verify(self, digest: HashDigest | str) -> CacheEntry:
        expected = HashDigest.parse(digest)
        path = self._path(expected)
        if not path.is_file():
            raise CacheObjectMissing(str(expected))
        data = path.read_bytes()
        if hash_bytes(data) != expected:
            raise CacheCorruption(str(expected))
        return CacheEntry(expected, path, len(data))

    def read_bytes(self, digest: HashDigest | str) -> bytes:
        entry = self._verify(digest)
        return entry.path.read_bytes()

    def has(self, digest: HashDigest | str) -> bool:
        try:
            self._verify(digest)
            return True
        except CacheError:
            return False
