"""Strict target/profile manifest models and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Tuple

from .provenance import HashDigest, InputRef, canonical_json


class ManifestError(ValueError):
    pass


class UnsupportedManifestSchema(ManifestError):
    pass


class UnknownTarget(ManifestError):
    pass


class UnknownProfile(ManifestError):
    pass


class TargetProfileMismatch(ManifestError):
    pass


class InvalidProfileContract(ManifestError):
    pass


class InvalidFixtureContract(InvalidProfileContract):
    pass


class InvalidConfigContract(InvalidProfileContract):
    pass


KNOWN_TARGETS = ("gki-android14-6.1", "gki-android16-6.12", "sultan-android14-6.1")
KNOWN_PROFILES = tuple(f"{target}-{mode}" for target in KNOWN_TARGETS for mode in ("manual", "lsm_bl"))
TARGET_SCHEMAS = {"xxksu-susfs-target/v1"}
PROFILE_SCHEMAS = {"xxksu-susfs-profile/v1"}
MANUAL_FIXTURES = ("scope-min-manual-hooks-v2.3.patch", "manual-security-hooks-v2.0.patch")
MANUAL_KCONFIG = {"CONFIG_KSU": "y", "CONFIG_KSU_SUSFS": "y", "CONFIG_KSU_LSM_SECURITY_HOOKS": "n",
                  "CONFIG_KSU_HACK_ARM64_BRANCH_LINK": "n", "CONFIG_KSU_TAMPER_SYSCALL_TABLE": "n",
                  "CONFIG_KSU_KPROBES_KSUD": "n"}
LSM_KCONFIG = {"CONFIG_KSU": "y", "CONFIG_KSU_SUSFS": "y", "CONFIG_KSU_LSM_SECURITY_HOOKS": "y",
               "CONFIG_KSU_HACK_ARM64_BRANCH_LINK": "y", "CONFIG_KSU_TAMPER_SYSCALL_TABLE": "n",
               "CONFIG_KSU_KPROBES_KSUD": "n"}
ADAPTERS = {"gki-android14-6.1": "gki_android14_6_1", "gki-android16-6.12": "gki_android16_6_12",
            "sultan-android14-6.1": "sultan_android14_6_1"}


def _ref(value: Any) -> InputRef:
    if isinstance(value, InputRef):
        return value
    if not isinstance(value, dict):
        raise ManifestError("input reference must be an object")
    allowed = {"name", "kind", "source", "requested_ref", "resolved_commit", "tree_id", "content_hash",
               "artifact_path", "original_source"}
    if set(value) - allowed:
        raise ManifestError("unknown input reference field")
    try:
        ref = InputRef(**value)
        if ref.kind not in {"git", "repository", "tree", "patch", "fixture", "archive", "local"}:
            raise ManifestError("unknown input reference kind")
        return ref
    except (TypeError, ValueError) as exc:
        raise ManifestError(str(exc)) from exc


@dataclass(frozen=True)
class TargetManifest:
    schema: str
    target_id: str
    inputs: Tuple[InputRef, ...]
    adapter_id: str
    patch_51_id: str
    profiles: Tuple[str, ...]
    shared_11_id: str = "shared-11"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def validate(self) -> "TargetManifest":
        if self.schema not in TARGET_SCHEMAS:
            raise UnsupportedManifestSchema(self.schema)
        if self.target_id not in KNOWN_TARGETS:
            raise UnknownTarget(self.target_id)
        if self.adapter_id != ADAPTERS[self.target_id]:
            raise ManifestError("adapter does not belong to target")
        expected = tuple(f"{self.target_id}-{mode}" for mode in ("manual", "lsm_bl"))
        if tuple(self.profiles) != expected:
            raise ManifestError("target must declare both profiles in canonical order")
        if not self.patch_51_id or "manual" in self.patch_51_id or "lsm_bl" in self.patch_51_id:
            raise ManifestError("target 51 must be one transport-neutral policy")
        if not self.shared_11_id or "manual" in self.shared_11_id or "lsm" in self.shared_11_id:
            raise ManifestError("11 must be shared across profiles")
        if len({ref.name for ref in self.inputs}) != len(self.inputs):
            raise ManifestError("duplicate target input names")
        return self

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {"schema": self.schema, "target_id": self.target_id,
                "inputs": [ref.to_dict() for ref in self.inputs], "adapter_id": self.adapter_id,
                "patch_51_id": self.patch_51_id, "profiles": list(self.profiles),
                "shared_11_id": self.shared_11_id, "metadata": dict(self.metadata)}


@dataclass(frozen=True)
class ProfileManifest:
    schema: str
    profile_id: str
    target_id: str
    mode: str
    fixtures: Tuple[InputRef, ...]
    kconfig: Mapping[str, str]
    prerequisites: Mapping[str, Any]
    ownership: Mapping[str, str]
    patch_11_id: str = "shared-11"
    patch_51_id: Optional[str] = None
    adapter_id: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def validate(self, target: Optional[TargetManifest] = None) -> "ProfileManifest":
        if self.schema not in PROFILE_SCHEMAS:
            raise UnsupportedManifestSchema(self.schema)
        if self.target_id not in KNOWN_TARGETS:
            raise UnknownTarget(self.target_id)
        if self.profile_id not in KNOWN_PROFILES:
            raise UnknownProfile(self.profile_id)
        if self.profile_id != f"{self.target_id}-{self.mode}":
            raise TargetProfileMismatch(self.profile_id)
        if self.mode not in ("manual", "lsm_bl"):
            raise InvalidProfileContract("unknown mode")
        if not self.patch_51_id:
            raise InvalidProfileContract("profile requires a target-specific 51 policy")
        expected = MANUAL_KCONFIG if self.mode == "manual" else LSM_KCONFIG
        if dict(self.kconfig) != expected:
            raise InvalidConfigContract("Kconfig does not exactly match profile mode")
        fixture_names = tuple(ref.name.rsplit("/", 1)[-1] for ref in self.fixtures)
        if self.mode == "manual":
            if set(fixture_names) != set(MANUAL_FIXTURES):
                raise InvalidFixtureContract("manual profiles require both manual fixtures")
            if self.prerequisites.get("arch") not in (None, "any"):
                raise InvalidConfigContract("manual architecture prerequisite is invalid")
        else:
            if self.fixtures:
                raise InvalidFixtureContract("lsm_bl profiles forbid manual fixtures")
            if self.prerequisites.get("arch") != "arm64" or self.prerequisites.get("kallsyms") is not True:
                raise InvalidConfigContract("lsm_bl requires arm64 and KALLSYMS")
            if self.prerequisites.get("XXKSU_BL_COMPOSITE") != "XXKSU_BL_COMPOSITE":
                raise InvalidProfileContract("lsm_bl requires composite BL ownership")
        if self.patch_11_id != "shared-11" or "manual" in self.patch_11_id or "lsm" in self.patch_11_id:
            raise ManifestError("profile must use shared 11")
        if target is not None:
            target.validate()
            if target.target_id != self.target_id or self.profile_id not in target.profiles:
                raise TargetProfileMismatch(self.profile_id)
            if self.adapter_id not in (None, target.adapter_id):
                raise ManifestError("adapter does not belong to target")
            if self.patch_51_id != target.patch_51_id:
                raise ManifestError("profile must reference target transport-neutral 51")
        if not self.ownership or any(not isinstance(key, str) or not isinstance(value, str)
                                     for key, value in self.ownership.items()):
            raise InvalidProfileContract("ownership declarations must be a non-empty string map")
        if len(self.ownership) != len(set(self.ownership)):
            raise InvalidProfileContract("duplicate ownership declaration")
        valid_paths = {"exec", "access", "stat", "fstat-return", "reboot", "read", "setuid", "setprocattr"}
        if set(self.ownership) - valid_paths:
            raise InvalidProfileContract("unknown ownership path")
        allowed_owners = set(MANUAL_FIXTURES) if self.mode == "manual" else {"XXKSU_BL_COMPOSITE", "XXKSU_LSM"}
        if set(self.ownership.values()) - allowed_owners:
            raise InvalidProfileContract("ownership owner conflicts with profile mode")
        return self

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {"schema": self.schema, "profile_id": self.profile_id, "target_id": self.target_id,
                "mode": self.mode, "fixtures": [ref.to_dict() for ref in self.fixtures],
                "kconfig": dict(self.kconfig), "prerequisites": dict(self.prerequisites),
                "ownership": dict(self.ownership), "patch_11_id": self.patch_11_id,
                "patch_51_id": self.patch_51_id, "adapter_id": self.adapter_id,
                "metadata": dict(self.metadata)}


@dataclass(frozen=True)
class ManifestSet:
    target: TargetManifest
    profiles: Tuple[ProfileManifest, ...]

    def validate(self) -> "ManifestSet":
        self.target.validate()
        for profile in self.profiles:
            profile.validate(self.target)
        if tuple(profile.profile_id for profile in self.profiles) != self.target.profiles:
            raise ManifestError("target/profile set does not match")
        if len({profile.patch_51_id for profile in self.profiles}) != 1:
            raise ManifestError("51 is not transport-neutral")
        return self

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {"target": self.target.to_dict(), "profiles": [profile.to_dict() for profile in self.profiles]}

    def canonical_json(self) -> str:
        return canonical_json(self.to_dict())


def _load_json(data: Any) -> Mapping[str, Any]:
    import json
    from pathlib import Path
    if isinstance(data, (str, Path)):
        if isinstance(data, str) and data.lstrip().startswith("{"):
            return json.loads(data)
        return json.loads(Path(data).read_text(encoding="utf-8"))
    if isinstance(data, Mapping):
        return data
    raise ManifestError("manifest must be JSON text, path, or object")


def _reject_unknown(raw: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = set(raw) - allowed
    if unknown:
        raise ManifestError("unknown manifest field: " + sorted(unknown)[0])


def load_manifest_set(data: Any) -> ManifestSet:
    raw = _load_json(data)
    if "target" in raw:
        _reject_unknown(raw, {"target", "profiles"})
    target_raw = raw.get("target") if "target" in raw else raw
    if not isinstance(target_raw, Mapping):
        raise ManifestError("target manifest missing")
    try:
        _reject_unknown(target_raw, {"schema", "target_id", "inputs", "adapter_id", "patch_51_id", "profiles", "shared_11_id", "metadata"})
        target = TargetManifest(schema=target_raw["schema"], target_id=target_raw["target_id"],
                                inputs=tuple(_ref(item) for item in target_raw.get("inputs", [])),
                                adapter_id=target_raw["adapter_id"], patch_51_id=target_raw["patch_51_id"],
                                profiles=tuple(target_raw["profiles"]), shared_11_id=target_raw.get("shared_11_id", "shared-11"),
                                metadata=target_raw.get("metadata", {}))
        profiles = []
        for item in raw.get("profiles", []):
            _reject_unknown(item, {"schema", "profile_id", "target_id", "mode", "fixtures", "kconfig",
                                   "prerequisites", "ownership", "patch_11_id", "patch_51_id", "adapter_id", "metadata"})
            profiles.append(ProfileManifest(schema=item["schema"], profile_id=item["profile_id"],
                                            target_id=item["target_id"], mode=item["mode"],
                                            fixtures=tuple(_ref(ref) for ref in item.get("fixtures", [])),
                                            kconfig=item["kconfig"], prerequisites=item.get("prerequisites", {}),
                                            ownership=item.get("ownership", {}), patch_11_id=item.get("patch_11_id", "shared-11"),
                                            patch_51_id=item.get("patch_51_id"), adapter_id=item.get("adapter_id"),
                                            metadata=item.get("metadata", {})))
    except (KeyError, TypeError, ValueError) as exc:
        raise ManifestError(f"missing or invalid manifest field: {exc}") from exc
    return ManifestSet(target, profiles).validate()


def load_target_manifest(data: Any) -> TargetManifest:
    raw = _load_json(data)
    if "target" in raw:
        raw = raw["target"]
    try:
        _reject_unknown(raw, {"schema", "target_id", "inputs", "adapter_id", "patch_51_id", "profiles", "shared_11_id", "metadata"})
        target = TargetManifest(schema=raw["schema"], target_id=raw["target_id"],
                                inputs=tuple(_ref(item) for item in raw.get("inputs", [])),
                                adapter_id=raw["adapter_id"], patch_51_id=raw["patch_51_id"],
                                profiles=tuple(raw["profiles"]), shared_11_id=raw.get("shared_11_id", "shared-11"),
                                metadata=raw.get("metadata", {}))
    except (KeyError, TypeError, ValueError) as exc:
        raise ManifestError(str(exc)) from exc
    return target.validate()


def load_profile_manifest(data: Any, target: Optional[TargetManifest] = None) -> ProfileManifest:
    raw = _load_json(data)
    if "profile" in raw:
        raw = raw["profile"]
    try:
        _reject_unknown(raw, {"schema", "profile_id", "target_id", "mode", "fixtures", "kconfig", "prerequisites", "ownership", "patch_11_id", "patch_51_id", "adapter_id", "metadata"})
        profile = ProfileManifest(schema=raw["schema"], profile_id=raw["profile_id"], target_id=raw["target_id"],
                                  mode=raw["mode"], fixtures=tuple(_ref(item) for item in raw.get("fixtures", [])),
                                  kconfig=raw["kconfig"], prerequisites=raw.get("prerequisites", {}),
                                  ownership=raw.get("ownership", {}), patch_11_id=raw.get("patch_11_id", "shared-11"),
                                  patch_51_id=raw.get("patch_51_id"), adapter_id=raw.get("adapter_id"),
                                  metadata=raw.get("metadata", {}))
    except (KeyError, TypeError, ValueError) as exc:
        raise ManifestError(str(exc)) from exc
    return profile.validate(target)
