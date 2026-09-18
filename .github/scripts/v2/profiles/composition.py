"""Deterministic profile composition engine for V2.9."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping, Optional, Sequence, Tuple, Union

from ..model.manifest import (
    InvalidFixtureContract,
    ProfileManifest,
    TargetProfileMismatch,
    UnknownProfile,
)
from ..model.provenance import HashDigest, canonical_json
from ..model.result import (
    SourceBundleIdentityMismatch,
    ValidationError,
    ValidationReport,
    ValidationResult,
    ValidationStatus,
)
from ..source.bundle import SourceBundle
from ..validation import (
    OwnershipClaim,
    validate_all,
    validate_bundle_integrity,
    validate_config,
    validate_symbols,
)
from .matrix import ProfileDefinition, get_profile_definition, get_profile_manifest, list_profile_definitions


@dataclass(frozen=True)
class ProfileCompositionResult:
    """Immutable result of profile composition, quality gates, and config validation."""

    profile_id: str
    target_id: str
    mode: str
    ordered_patch_set: Tuple[str, ...]
    fixtures: Tuple[str, ...]
    composed_bundle: SourceBundle
    expected_config: Mapping[str, str]
    config_result: Optional[ValidationResult]
    validation_report: ValidationReport
    manifest: ProfileManifest
    digest: HashDigest

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "xxksu-susfs-profile-composition/v1",
            "profile_id": self.profile_id,
            "target_id": self.target_id,
            "mode": self.mode,
            "ordered_patch_set": list(self.ordered_patch_set),
            "fixtures": list(self.fixtures),
            "composed_bundle_identity": str(self.composed_bundle.identity),
            "manifest": self.manifest.to_dict(),
            "expected_config": dict(sorted(self.expected_config.items())),
            "validation_report_digest": str(self.validation_report.digest),
            "config_status": self.config_result.status.value if self.config_result else "NOT_SUPPLIED",
            "digest": str(self.digest),
        }

    def canonical_json(self) -> str:
        return canonical_json(self.to_dict())


def compose_profile(
    profile_id: str,
    *,
    target_bundle: SourceBundle,
    patch_11: Union[str, Any],
    patch_51: Union[str, Any],
    resolved_config: Optional[Union[str, Mapping[str, str]]] = None,
    requested_config: Optional[Mapping[str, str]] = None,
    manifest: Optional[ProfileManifest] = None,
    claims: Optional[Sequence[OwnershipClaim]] = None,
    raise_on_failure: bool = True,
) -> ProfileCompositionResult:
    """Deterministically compose a profile candidate and validate all V2.8/V2.9 quality gates."""
    # 1. Profile existence & definition
    prof_def = get_profile_definition(profile_id)
    target_id = prof_def.target_id
    mode = prof_def.mode

    # 2. Validate clean target SourceBundle
    if not isinstance(target_bundle, SourceBundle):
        raise SourceBundleIdentityMismatch("target_bundle must be a SourceBundle")
    if target_bundle.target_id != target_id:
        raise TargetProfileMismatch(
            f"bundle target '{target_bundle.target_id}' does not match profile target '{target_id}'"
        )
    validate_bundle_integrity(target_bundle, raise_on_failure=True)

    # 3. Validate profile manifest
    if manifest is None:
        eff_manifest = get_profile_manifest(profile_id)
    else:
        eff_manifest = manifest.validate()
        if eff_manifest.profile_id != profile_id:
            raise TargetProfileMismatch(
                f"manifest profile_id '{eff_manifest.profile_id}' does not match '{profile_id}'"
            )
        if eff_manifest.target_id != target_id:
            raise TargetProfileMismatch(
                f"manifest target_id '{eff_manifest.target_id}' does not match '{target_id}'"
            )

    # 4. Validate patch 11 identity
    if not patch_11:
        raise ValueError("missing shared patch 11")
    p11_name = getattr(patch_11, "name", None) or (
        patch_11.get("name") if isinstance(patch_11, dict) else None
    ) or str(patch_11)
    if "manual" in str(p11_name) or "lsm" in str(p11_name):
        raise ValueError(f"patch 11 must be transport-neutral across all profiles: {p11_name}")
    if isinstance(patch_11, str) and ("\n" in patch_11 or patch_11.startswith("---") or patch_11.startswith("From ")):
        validate_symbols(patch=patch_11, raise_on_failure=True)

    # 5. Validate patch 51 target binding & transport neutrality
    if not patch_51:
        raise ValueError("missing target patch 51")
    p51_target = getattr(patch_51, "target_id", None) or (
        patch_51.get("target_id") if isinstance(patch_51, dict) else None
    )
    if p51_target and p51_target != target_id:
        raise ValueError(f"patch 51 target '{p51_target}' does not match profile target '{target_id}'")

    p51_id = getattr(patch_51, "name", None) or getattr(patch_51, "patch_51_id", None) or (
        patch_51.get("name") if isinstance(patch_51, dict) else (
            patch_51.get("patch_51_id") if isinstance(patch_51, dict) else None
        )
    ) or str(patch_51)
    if "manual" in str(p51_id) or "lsm_bl" in str(p51_id):
        raise ValueError(f"patch 51 must be transport-neutral, got: {p51_id}")

    # 6. Enforce fixture contract
    manifest_fixtures = tuple(ref.name.rsplit("/", 1)[-1] for ref in eff_manifest.fixtures)
    if mode == "manual":
        if set(manifest_fixtures) != set(prof_def.fixtures):
            raise InvalidFixtureContract(
                f"manual profiles require both manual fixtures: expected {prof_def.fixtures}, got {manifest_fixtures}"
            )
        if len(manifest_fixtures) != 2:
            raise InvalidFixtureContract(f"manual profiles require exactly 2 fixtures, got {len(manifest_fixtures)}")
    elif mode == "lsm_bl":
        if manifest_fixtures:
            raise InvalidFixtureContract(
                f"lsm_bl profiles strictly forbid manual fixtures, got {len(manifest_fixtures)}"
            )

    # 7. Adapt fixtures using V2.6 when mode == manual
    if mode == "manual":
        adapter = prof_def.get_adapter()
        plan = adapter.adapt_fixtures(target_bundle, prof_def.fixtures)
        composed_bundle = plan.apply_to_bundle(target_bundle)
    else:
        composed_bundle = target_bundle

    # 8. Post-composition quality gates: run V2.8 validators
    ownership_claims = claims if claims is not None else prof_def.get_ownership_claims()
    v28_report = validate_all(
        bundle=composed_bundle,
        mode=mode,
        claims=ownership_claims,
        raise_on_failure=raise_on_failure,
    )

    # 9. Final config validation if supplied
    config_result: Optional[ValidationResult] = None
    if resolved_config is not None:
        config_result = validate_config(
            expected=prof_def.expected_config,
            resolved=resolved_config,
            requested=requested_config,
            mode=mode,
            prerequisites=prof_def.prerequisites,
            raise_on_failure=raise_on_failure,
        )

    # 10. Canonical digest
    payload = {
        "schema": "xxksu-susfs-profile-composition/v1",
        "profile_id": profile_id,
        "target_id": target_id,
        "mode": mode,
        "ordered_patch_set": list(prof_def.ordered_patch_set),
        "fixtures": list(prof_def.fixtures),
        "composed_bundle_identity": str(composed_bundle.identity),
        "manifest": eff_manifest.to_dict(),
        "expected_config": dict(sorted(prof_def.expected_config.items())),
        "validation_report_digest": str(v28_report.digest),
        "config_status": config_result.status.value if config_result else "NOT_SUPPLIED",
    }
    digest = HashDigest("sha256", hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest())

    return ProfileCompositionResult(
        profile_id=profile_id,
        target_id=target_id,
        mode=mode,
        ordered_patch_set=prof_def.ordered_patch_set,
        fixtures=prof_def.fixtures,
        composed_bundle=composed_bundle,
        expected_config=prof_def.expected_config,
        config_result=config_result,
        validation_report=v28_report,
        manifest=eff_manifest,
        digest=digest,
    )


def compose_all_profiles(
    target_bundles: Mapping[str, SourceBundle],
    patch_11: Union[str, Any],
    target_patches_51: Mapping[str, Any],
    resolved_configs: Optional[Mapping[str, Union[str, Mapping[str, str]]]] = None,
    raise_on_failure: bool = True,
) -> Tuple[ProfileCompositionResult, ...]:
    """Compose all six canonical profiles in canonical order."""
    results: list[ProfileCompositionResult] = []
    for prof_def in list_profile_definitions():
        target_id = prof_def.target_id
        if target_id not in target_bundles:
            raise KeyError(f"target bundle missing for {target_id}")
        if target_id not in target_patches_51:
            raise KeyError(f"patch 51 missing for {target_id}")

        cfg = resolved_configs.get(prof_def.profile_id) if resolved_configs else None
        res = compose_profile(
            prof_def.profile_id,
            target_bundle=target_bundles[target_id],
            patch_11=patch_11,
            patch_51=target_patches_51[target_id],
            resolved_config=cfg,
            raise_on_failure=raise_on_failure,
        )
        results.append(res)
    return tuple(results)


__all__ = [
    "ProfileCompositionResult",
    "compose_profile",
    "compose_all_profiles",
]
