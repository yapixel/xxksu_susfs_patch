"""Canonical profile matrix and metadata bindings for V2.9."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Tuple

from ..adapters import TargetAdapter, get_adapter
from ..model.manifest import (
    ADAPTERS,
    KNOWN_PROFILES,
    KNOWN_TARGETS,
    LSM_KCONFIG,
    MANUAL_FIXTURES,
    MANUAL_KCONFIG,
    InvalidFixtureContract,
    InvalidProfileContract,
    ProfileManifest,
    TargetProfileMismatch,
    UnknownProfile,
    UnknownTarget,
)
from ..model.provenance import FixtureRef
from ..validation.ownership import (
    OwnershipClaim,
    make_default_lsm_bl_claims,
    make_default_manual_claims,
)

TARGET_KERNEL_VERSIONS: Mapping[str, str] = {
    "gki-android14-6.1": "6.1",
    "gki-android16-6.12": "6.12",
    "sultan-android14-6.1": "6.1",
}


@dataclass(frozen=True)
class ProfileDefinition:
    """Immutable binding of all required attributes for a canonical profile."""

    profile_id: str
    target_id: str
    kernel_version: str
    adapter_id: str
    mode: str
    shared_patch_11_id: str
    patch_51_id: str
    fixtures: Tuple[str, ...]
    expected_config: Mapping[str, str]
    prerequisites: Mapping[str, Any]
    transport_ownership: Mapping[str, str]
    ordered_patch_set: Tuple[str, ...]

    def get_adapter(self) -> TargetAdapter:
        return get_adapter(self.target_id)

    def get_ownership_claims(self) -> Tuple[OwnershipClaim, ...]:
        if self.mode == "manual":
            return make_default_manual_claims()
        return make_default_lsm_bl_claims()

    def get_manifest(self) -> ProfileManifest:
        if self.mode == "manual":
            fixture_refs = tuple(
                FixtureRef(name, f".github/fixtures/{name}", artifact_path=f".github/fixtures/{name}")
                for name in self.fixtures
            )
        else:
            fixture_refs = ()
        return ProfileManifest(
            schema="xxksu-susfs-profile/v1",
            profile_id=self.profile_id,
            target_id=self.target_id,
            mode=self.mode,
            fixtures=fixture_refs,
            kconfig=self.expected_config,
            prerequisites=self.prerequisites,
            ownership=self.transport_ownership,
            patch_11_id=self.shared_patch_11_id,
            patch_51_id=self.patch_51_id,
            adapter_id=self.adapter_id,
        ).validate()


def _build_profile_definition(target_id: str, mode: str) -> ProfileDefinition:
    if target_id not in KNOWN_TARGETS:
        raise UnknownTarget(f"unknown target: {target_id}")
    if mode not in ("manual", "lsm_bl"):
        raise InvalidProfileContract(f"unknown mode: {mode}")

    profile_id = f"{target_id}-{mode}"
    kernel_version = TARGET_KERNEL_VERSIONS[target_id]
    adapter_id = ADAPTERS[target_id]
    shared_11 = "shared-11"
    patch_51 = f"{target_id.replace('-', '_')}_51"

    if mode == "manual":
        fixtures = MANUAL_FIXTURES
        expected_config = dict(MANUAL_KCONFIG)
        prerequisites = {"arch": "any", "kallsyms": True}
        transport_ownership = {
            "exec": MANUAL_FIXTURES[0],
            "access": MANUAL_FIXTURES[0],
            "stat": MANUAL_FIXTURES[0],
            "fstat-return": MANUAL_FIXTURES[0],
            "reboot": MANUAL_FIXTURES[0],
            "read": MANUAL_FIXTURES[1],
            "setuid": MANUAL_FIXTURES[1],
            "setprocattr": MANUAL_FIXTURES[1],
        }
        ordered_patch_set = (shared_11, patch_51, MANUAL_FIXTURES[0], MANUAL_FIXTURES[1])
    else:
        fixtures = ()
        expected_config = dict(LSM_KCONFIG)
        prerequisites = {"arch": "arm64", "kallsyms": True, "XXKSU_BL_COMPOSITE": "XXKSU_BL_COMPOSITE"}
        transport_ownership = {
            "exec": "XXKSU_BL_COMPOSITE",
            "access": "XXKSU_BL_COMPOSITE",
            "stat": "XXKSU_BL_COMPOSITE",
            "fstat-return": "XXKSU_BL_COMPOSITE",
            "reboot": "XXKSU_BL_COMPOSITE",
            "read": "XXKSU_BL_COMPOSITE",
            "setuid": "XXKSU_LSM",
            "setprocattr": "XXKSU_LSM",
        }
        ordered_patch_set = (shared_11, patch_51)

    return ProfileDefinition(
        profile_id=profile_id,
        target_id=target_id,
        kernel_version=kernel_version,
        adapter_id=adapter_id,
        mode=mode,
        shared_patch_11_id=shared_11,
        patch_51_id=patch_51,
        fixtures=fixtures,
        expected_config=expected_config,
        prerequisites=prerequisites,
        transport_ownership=transport_ownership,
        ordered_patch_set=ordered_patch_set,
    )


CANONICAL_PROFILES: Mapping[str, ProfileDefinition] = {
    f"{target}-{mode}": _build_profile_definition(target, mode)
    for target in KNOWN_TARGETS
    for mode in ("manual", "lsm_bl")
}


def get_profile_definition(profile_id: str) -> ProfileDefinition:
    """Resolve a profile ID to its canonical ProfileDefinition or fail closed."""
    if not isinstance(profile_id, str):
        raise UnknownProfile("profile id must be a string")
    if profile_id not in CANONICAL_PROFILES:
        raise UnknownProfile(f"unknown profile id: '{profile_id}'")
    return CANONICAL_PROFILES[profile_id]


def list_profile_definitions() -> Tuple[ProfileDefinition, ...]:
    """List all six canonical profile definitions in deterministic order."""
    return tuple(CANONICAL_PROFILES.values())


def get_profile_manifest(profile_id: str) -> ProfileManifest:
    """Construct the authoritative ProfileManifest for the given profile ID."""
    prof = get_profile_definition(profile_id)
    return prof.get_manifest()


__all__ = [
    "TARGET_KERNEL_VERSIONS",
    "ProfileDefinition",
    "CANONICAL_PROFILES",
    "get_profile_definition",
    "list_profile_definitions",
    "get_profile_manifest",
]
