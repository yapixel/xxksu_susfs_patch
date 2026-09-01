"""Explicit acquisition boundary; preparation never calls this module."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Any

from ..model.provenance import HashDigest, InputRef
from .cache import ContentAddressedCache, CacheEntry


class FetchError(ValueError):
    pass


def fetch(reference: InputRef, cache: ContentAddressedCache,
          acquire: Callable[[InputRef], bytes] | None = None) -> CacheEntry:
    try:
        if acquire is None:
            if reference.source.startswith("file://"):
                data = Path(reference.source[7:]).read_bytes()
            else:
                path = Path(reference.source)
                if not path.is_file():
                    raise FetchError("an explicit acquisition callback is required for non-file sources")
                data = path.read_bytes()
        else:
            data = acquire(reference)
        if not isinstance(data, bytes):
            raise FetchError("acquisition callback must return bytes")
        return cache.put_bytes(data, reference.content_hash)
    except (OSError, TypeError, ValueError) as exc:
        raise FetchError(str(exc)) from exc
