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
from .gki_android16_6_12 import GKIAndroid16_6_12Adapter
from .sultan_android14_6_1 import SultanAndroid14_6_1Adapter
from .fixtures import (
    FIXED_FIXTURES,
    ADAPTATION_PLAN_SCHEMA,
    Placement,
    AdaptationOperation,
    FixtureAdaptationPlan,
    FixtureAdaptationError,
    IncompatibleFixtureTarget,
    DuplicateAdaptationOperation,
    MissingFixtureSource,
    AmbiguousFixtureMatch,
    FixtureContractViolation,
    adapt_fixture_for_adapter,
    adapt_fixtures_for_adapter,
)
from .xxksu import (
    XxksuAdapter,
    build_xxksu_adaptation_plan,
    apply_patch11_to_bundle,
    generate_patch11,
    get_xxksu_adapter,
)


_ADAPTER_REGISTRY: Mapping[str, Type[TargetAdapter]] = {
    "gki-android16-6.12": GKIAndroid16_6_12Adapter,
    "sultan-android14-6.1": SultanAndroid14_6_1Adapter,
    "xxksu": XxksuAdapter,
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
    "GKIAndroid16_6_12Adapter",
    "SultanAndroid14_6_1Adapter",
    "get_adapter",
    "FIXED_FIXTURES",
    "ADAPTATION_PLAN_SCHEMA",
    "Placement",
    "AdaptationOperation",
    "FixtureAdaptationPlan",
    "FixtureAdaptationError",
    "IncompatibleFixtureTarget",
    "DuplicateAdaptationOperation",
    "MissingFixtureSource",
    "AmbiguousFixtureMatch",
    "FixtureContractViolation",
    "adapt_fixture_for_adapter",
    "adapt_fixtures_for_adapter",
    "XxksuAdapter",
    "build_xxksu_adaptation_plan",
    "apply_patch11_to_bundle",
    "generate_patch11",
    "get_xxksu_adapter",
]
