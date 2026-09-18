"""Profile matrix and composition package for V2.9."""

from .composition import ProfileCompositionResult, compose_all_profiles, compose_profile
from .matrix import (
    CANONICAL_PROFILES,
    TARGET_KERNEL_VERSIONS,
    ProfileDefinition,
    get_profile_definition,
    get_profile_manifest,
    list_profile_definitions,
)

__all__ = [
    "ProfileCompositionResult",
    "compose_profile",
    "compose_all_profiles",
    "ProfileDefinition",
    "CANONICAL_PROFILES",
    "TARGET_KERNEL_VERSIONS",
    "get_profile_definition",
    "get_profile_manifest",
    "list_profile_definitions",
]
