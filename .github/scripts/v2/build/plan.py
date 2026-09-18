"""Declarative build planning and command synthesis for V2.10."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import TYPE_CHECKING, Any, Mapping, Optional, Sequence, Tuple, Union

from ..model.provenance import HashDigest, canonical_json
from ..profiles.matrix import (
    CANONICAL_PROFILES,
    ProfileDefinition,
    get_profile_definition,
    list_profile_definitions,
)

if TYPE_CHECKING:
    from ..profiles.composition import ProfileCompositionResult

DEFAULT_REQUIRED_ARTIFACTS: Tuple[str, ...] = ("Image", "vmlinux")
DEFAULT_VALIDATION_GATES: Tuple[str, ...] = (
    "validation.ownership",
    "validation.symbols",
    "validation.abi",
    "validation.config",
    "validation.build",
)


@dataclass(frozen=True)
class BuildToolchainSpec:
    """Declarative specification of kernel compiler toolchain requirements."""

    arch: str = "arm64"
    compiler: str = "clang"
    linker: str = "ld.lld"
    llvm: int = 1
    llvm_ias: int = 1
    cross_compile: str = "aarch64-linux-gnu-"

    def to_dict(self) -> dict[str, Any]:
        return {
            "arch": self.arch,
            "compiler": self.compiler,
            "linker": self.linker,
            "llvm": self.llvm,
            "llvm_ias": self.llvm_ias,
            "cross_compile": self.cross_compile,
        }

    def canonical_json(self) -> str:
        return canonical_json(self.to_dict())


def format_config_fragment(expected_config: Mapping[str, str]) -> str:
    """Format expected configuration dictionary into a deterministic Kconfig fragment."""
    lines = []
    for sym in sorted(expected_config.keys()):
        val = expected_config[sym]
        if val == "y":
            lines.append(f"{sym}=y")
        elif val == "m":
            lines.append(f"{sym}=m")
        elif val == "n":
            lines.append(f"# {sym} is not set")
        else:
            lines.append(f"{sym}={val}")
    return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class BuildPlan:
    """Immutable, deterministic build plan for a single profile target."""

    profile_id: str
    target_id: str
    mode: str
    source_identity: HashDigest
    composition_digest: HashDigest
    source_workspace_path_template: str
    out_dir_template: str
    log_dir_template: str
    result_path_template: str
    base_defconfig_cmd: Tuple[str, ...]
    config_fragment: str
    olddefconfig_cmd: Tuple[str, ...]
    final_build_cmd: Tuple[str, ...]
    required_artifacts: Tuple[str, ...]
    expected_validation_gates: Tuple[str, ...]
    toolchain_requirements: BuildToolchainSpec
    digest: HashDigest

    @property
    def worktree_path_template(self) -> str:
        return self.source_workspace_path_template

    @property
    def o_path_template(self) -> str:
        return self.out_dir_template

    @property
    def log_path_template(self) -> str:
        return self.log_dir_template

    @property
    def toolchain_spec(self) -> BuildToolchainSpec:
        return self.toolchain_requirements

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "xxksu-susfs-build-plan/v1",
            "profile_id": self.profile_id,
            "target_id": self.target_id,
            "mode": self.mode,
            "source_identity": str(self.source_identity),
            "composition_digest": str(self.composition_digest),
            "source_workspace_path_template": self.source_workspace_path_template,
            "out_dir_template": self.out_dir_template,
            "log_dir_template": self.log_dir_template,
            "result_path_template": self.result_path_template,
            "base_defconfig_cmd": list(self.base_defconfig_cmd),
            "config_fragment": self.config_fragment,
            "olddefconfig_cmd": list(self.olddefconfig_cmd),
            "final_build_cmd": list(self.final_build_cmd),
            "required_artifacts": list(self.required_artifacts),
            "expected_validation_gates": list(self.expected_validation_gates),
            "toolchain_requirements": self.toolchain_requirements.to_dict(),
            "digest": str(self.digest),
        }

    def canonical_json(self) -> str:
        return canonical_json(self.to_dict())

    def resolve_source_workspace_path(self, root: Optional[str] = None) -> str:
        rel = self.source_workspace_path_template.format(
            profile_id=self.profile_id, target_id=self.target_id, mode=self.mode
        )
        if root:
            return f"{root.rstrip('/')}/{rel}"
        return rel

    def resolve_out_dir(self, root: Optional[str] = None) -> str:
        rel = self.out_dir_template.format(
            profile_id=self.profile_id, target_id=self.target_id, mode=self.mode
        )
        if root:
            return f"{root.rstrip('/')}/{rel}"
        return rel

    def resolve_log_dir(self, root: Optional[str] = None) -> str:
        rel = self.log_dir_template.format(
            profile_id=self.profile_id, target_id=self.target_id, mode=self.mode
        )
        if root:
            return f"{root.rstrip('/')}/{rel}"
        return rel

    def resolve_result_path(self, root: Optional[str] = None) -> str:
        rel = self.result_path_template.format(
            profile_id=self.profile_id, target_id=self.target_id, mode=self.mode
        )
        if root:
            return f"{root.rstrip('/')}/{rel}"
        return rel

    def resolve_commands(self, root: Optional[str] = None) -> Tuple[Tuple[str, ...], ...]:
        out_dir = self.resolve_out_dir(root)
        resolved_cmds = []
        for cmd in (self.base_defconfig_cmd, self.olddefconfig_cmd, self.final_build_cmd):
            resolved = tuple(
                token.format(
                    profile_id=self.profile_id,
                    target_id=self.target_id,
                    mode=self.mode,
                    out_dir=out_dir,
                )
                if "{" in token
                else token
                for token in cmd
            )
            resolved_cmds.append(resolved)
        return tuple(resolved_cmds)


def _synthesize_defconfig_cmd(target_id: str, out_dir_template: str) -> Tuple[str, ...]:
    defconfig_target = "sultan_defconfig" if target_id.startswith("sultan-") else "gki_defconfig"
    return (
        "make",
        "ARCH=arm64",
        "LLVM=1",
        "LLVM_IAS=1",
        f"O={out_dir_template}",
        defconfig_target,
    )


def _synthesize_olddefconfig_cmd(out_dir_template: str) -> Tuple[str, ...]:
    return (
        "make",
        "ARCH=arm64",
        "LLVM=1",
        "LLVM_IAS=1",
        f"O={out_dir_template}",
        "olddefconfig",
    )


def _synthesize_final_build_cmd(out_dir_template: str) -> Tuple[str, ...]:
    return (
        "make",
        "ARCH=arm64",
        "LLVM=1",
        "LLVM_IAS=1",
        f"O={out_dir_template}",
        "Image",
    )


def create_build_plan_from_definition(
    prof_def: ProfileDefinition,
    *,
    source_identity: Optional[Union[HashDigest, str]] = None,
    composition_digest: Optional[Union[HashDigest, str]] = None,
    source_workspace_path_template: str = "build/worktrees/{profile_id}",
    out_dir_template: str = "build/out/{profile_id}",
    log_dir_template: str = "build/logs/{profile_id}",
    result_path_template: str = "build/results/{profile_id}.json",
    toolchain_requirements: Optional[BuildToolchainSpec] = None,
    required_artifacts: Optional[Sequence[str]] = None,
    expected_validation_gates: Optional[Sequence[str]] = None,
) -> BuildPlan:
    """Construct a deterministic BuildPlan from a canonical ProfileDefinition."""
    profile_id = prof_def.profile_id
    target_id = prof_def.target_id
    mode = prof_def.mode

    if source_identity is None:
        source_id = HashDigest(
            "sha256", hashlib.sha256(f"source-identity:{target_id}".encode("utf-8")).hexdigest()
        )
    elif isinstance(source_identity, str):
        source_id = HashDigest("sha256", source_identity)
    else:
        source_id = source_identity

    if composition_digest is None:
        comp_dig = HashDigest(
            "sha256", hashlib.sha256(f"composition-digest:{profile_id}".encode("utf-8")).hexdigest()
        )
    elif isinstance(composition_digest, str):
        comp_dig = HashDigest("sha256", composition_digest)
    else:
        comp_dig = composition_digest

    tc = toolchain_requirements or BuildToolchainSpec()
    req_artifacts = tuple(required_artifacts) if required_artifacts is not None else DEFAULT_REQUIRED_ARTIFACTS
    val_gates = tuple(expected_validation_gates) if expected_validation_gates is not None else DEFAULT_VALIDATION_GATES

    base_defconfig_cmd = _synthesize_defconfig_cmd(target_id, out_dir_template)
    olddefconfig_cmd = _synthesize_olddefconfig_cmd(out_dir_template)
    final_build_cmd = _synthesize_final_build_cmd(out_dir_template)
    config_fragment = format_config_fragment(prof_def.expected_config)

    payload = {
        "schema": "xxksu-susfs-build-plan/v1",
        "profile_id": profile_id,
        "target_id": target_id,
        "mode": mode,
        "source_identity": str(source_id),
        "composition_digest": str(comp_dig),
        "source_workspace_path_template": source_workspace_path_template,
        "out_dir_template": out_dir_template,
        "log_dir_template": log_dir_template,
        "result_path_template": result_path_template,
        "base_defconfig_cmd": list(base_defconfig_cmd),
        "config_fragment": config_fragment,
        "olddefconfig_cmd": list(olddefconfig_cmd),
        "final_build_cmd": list(final_build_cmd),
        "required_artifacts": list(req_artifacts),
        "expected_validation_gates": list(val_gates),
        "toolchain_requirements": tc.to_dict(),
    }
    digest = HashDigest("sha256", hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest())

    return BuildPlan(
        profile_id=profile_id,
        target_id=target_id,
        mode=mode,
        source_identity=source_id,
        composition_digest=comp_dig,
        source_workspace_path_template=source_workspace_path_template,
        out_dir_template=out_dir_template,
        log_dir_template=log_dir_template,
        result_path_template=result_path_template,
        base_defconfig_cmd=base_defconfig_cmd,
        config_fragment=config_fragment,
        olddefconfig_cmd=olddefconfig_cmd,
        final_build_cmd=final_build_cmd,
        required_artifacts=req_artifacts,
        expected_validation_gates=val_gates,
        toolchain_requirements=tc,
        digest=digest,
    )


def create_build_plan(
    composition: ProfileCompositionResult,
    *,
    source_workspace_path_template: str = "build/worktrees/{profile_id}",
    out_dir_template: str = "build/out/{profile_id}",
    log_dir_template: str = "build/logs/{profile_id}",
    result_path_template: str = "build/results/{profile_id}.json",
    toolchain_requirements: Optional[BuildToolchainSpec] = None,
    required_artifacts: Optional[Sequence[str]] = None,
    expected_validation_gates: Optional[Sequence[str]] = None,
) -> BuildPlan:
    """Construct a deterministic BuildPlan from a ProfileCompositionResult."""
    prof_def = get_profile_definition(composition.profile_id)
    return create_build_plan_from_definition(
        prof_def,
        source_identity=composition.composed_bundle.identity,
        composition_digest=composition.digest,
        source_workspace_path_template=source_workspace_path_template,
        out_dir_template=out_dir_template,
        log_dir_template=log_dir_template,
        result_path_template=result_path_template,
        toolchain_requirements=toolchain_requirements,
        required_artifacts=required_artifacts,
        expected_validation_gates=expected_validation_gates,
    )


def create_all_canonical_plans(
    *,
    source_workspace_path_template: str = "build/worktrees/{profile_id}",
    out_dir_template: str = "build/out/{profile_id}",
    log_dir_template: str = "build/logs/{profile_id}",
    result_path_template: str = "build/results/{profile_id}.json",
    toolchain_requirements: Optional[BuildToolchainSpec] = None,
) -> Tuple[BuildPlan, ...]:
    """Create all six canonical BuildPlan objects in canonical matrix order."""
    return tuple(
        create_build_plan_from_definition(
            prof_def,
            source_workspace_path_template=source_workspace_path_template,
            out_dir_template=out_dir_template,
            log_dir_template=log_dir_template,
            result_path_template=result_path_template,
            toolchain_requirements=toolchain_requirements,
        )
        for prof_def in list_profile_definitions()
    )


def export_ci_matrix(plans: Sequence[BuildPlan]) -> str:
    """Deterministically export CI matrix JSON for GitHub Actions or other CI runners."""
    matrix = {
        "include": [
            {
                "profile_id": p.profile_id,
                "target_id": p.target_id,
                "mode": p.mode,
                "source_workspace": p.source_workspace_path_template,
                "out_dir": p.out_dir_template,
                "log_dir": p.log_dir_template,
                "result_path": p.result_path_template,
                "defconfig_cmd": list(p.base_defconfig_cmd),
                "olddefconfig_cmd": list(p.olddefconfig_cmd),
                "final_build_cmd": list(p.final_build_cmd),
                "required_artifacts": list(p.required_artifacts),
                "expected_validation_gates": list(p.expected_validation_gates),
                "plan_digest": str(p.digest),
            }
            for p in sorted(plans, key=lambda x: x.profile_id)
        ]
    }
    return canonical_json(matrix)


__all__ = [
    "DEFAULT_REQUIRED_ARTIFACTS",
    "DEFAULT_VALIDATION_GATES",
    "BuildToolchainSpec",
    "BuildPlan",
    "format_config_fragment",
    "create_build_plan_from_definition",
    "create_build_plan",
    "create_all_canonical_plans",
    "export_ci_matrix",
]
