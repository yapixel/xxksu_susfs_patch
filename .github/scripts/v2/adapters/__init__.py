"""Target adapters package."""

from __future__ import annotations

from typing import Mapping, Type

from .base import (
    AdapterError,
    AmbiguousSemanticMatch,
    AnchorConflict,
    AnchorLocation,
    AnchorSpec,
    MissingSemanticAnchor,
    MultipleSemanticAnchors,
    TargetAdapter,
    UnsupportedKernelVersion,
    UnsupportedTarget,
    find_function_span,
)
from .gki_android14_6_1 import GKIAndroid14_6_1Adapter
from .gki_android16_6_12 import GKIAndroid16_6_12Adapter
from .sultan_android14_6_1 import SultanAndroid14_6_1Adapter


_ADAPTER_REGISTRY: Mapping[str, Type[TargetAdapter]] = {
    "gki-android14-6.1": GKIAndroid14_6_1Adapter,
    "gki-android16-6.12": GKIAndroid16_6_12Adapter,
    "sultan-android14-6.1": SultanAndroid14_6_1Adapter,
}


def get_adapter(target_id: str) -> TargetAdapter:
    cls = _ADAPTER_REGISTRY.get(target_id)
    if cls is None:
        raise UnsupportedTarget(f"unknown or unsupported target: {target_id}")
    return cls()


__all__ = [
    "AdapterError",
    "AmbiguousSemanticMatch",
    "AnchorConflict",
    "AnchorLocation",
    "AnchorSpec",
    "MissingSemanticAnchor",
    "MultipleSemanticAnchors",
    "TargetAdapter",
    "UnsupportedKernelVersion",
    "UnsupportedTarget",
    "find_function_span",
    "GKIAndroid14_6_1Adapter",
    "GKIAndroid16_6_12Adapter",
    "SultanAndroid14_6_1Adapter",
    "get_adapter",
]
