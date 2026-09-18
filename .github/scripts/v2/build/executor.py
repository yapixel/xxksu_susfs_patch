"""Build orchestration and dry-run execution engine for V2.10."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import os
from typing import Any, Mapping, Optional, Sequence, Tuple

from ..model.provenance import HashDigest, canonical_json
from ..model.result import BuildFailure
from .classifier import FailureCategory
from .plan import BuildPlan


class BuildStatus(str, Enum):
    """Execution status for build operations."""

    PLANNED = "PLANNED"
    DRY_RUN = "DRY_RUN"
    NOT_EXECUTED = "NOT_EXECUTED"
    RUNNING = "RUNNING"
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass(frozen=True)
class BuildResult:
    """Immutable result of a build execution or dry-run planning step."""

    profile_id: str
    plan_digest: HashDigest
    status: BuildStatus
    commands: Tuple[Tuple[str, ...], ...]
    artifacts_expected: Tuple[str, ...]
    artifacts_found: Tuple[str, ...]
    worktree_path: str
    out_dir: str
    log_dir: str
    result_path: str
    failure_category: Optional[FailureCategory] = None
    error_message: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "xxksu-susfs-build-result/v1",
            "profile_id": self.profile_id,
            "plan_digest": str(self.plan_digest),
            "status": self.status.value,
            "commands": [list(c) for c in self.commands],
            "artifacts_expected": list(self.artifacts_expected),
            "artifacts_found": list(self.artifacts_found),
            "worktree_path": self.worktree_path,
            "out_dir": self.out_dir,
            "log_dir": self.log_dir,
            "result_path": self.result_path,
            "failure_category": self.failure_category.value if self.failure_category else None,
            "error_message": self.error_message,
            "metadata": dict(self.metadata),
        }

    def canonical_json(self) -> str:
        return canonical_json(self.to_dict())

    @property
    def digest(self) -> HashDigest:
        return HashDigest("sha256", hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest())


def _check_command_safety(commands: Tuple[Tuple[str, ...], ...]) -> None:
    """Verify that commands contain no network calls or arbitrary shell scripts."""
    banned_network_binaries = {"git", "curl", "wget", "fetch", "ssh", "scp", "rsync", "apt", "apt-get"}
    for cmd in commands:
        if not cmd:
            raise BuildFailure("Empty command detected in build plan")
        binary = cmd[0].lower()
        if binary in banned_network_binaries:
            raise BuildFailure(f"Network / external fetch command forbidden in build plan: {binary}")
        for token in cmd:
            if "curl " in token or "wget " in token or "git clone" in token:
                raise BuildFailure(f"Embedded network command forbidden: {token}")


def _check_path_safety(
    worktree_path: str, out_dir: str, log_dir: str, result_path: str
) -> None:
    """Verify path templates do not mutate or collide with main repository root."""
    forbidden_roots = {"/", "/root", "/home", ".", ""}
    for p, name in [
        (worktree_path, "worktree_path"),
        (out_dir, "out_dir"),
        (log_dir, "log_dir"),
        (result_path, "result_path"),
    ]:
        norm = os.path.normpath(p)
        if norm in forbidden_roots or norm == ".git":
            raise BuildFailure(f"Unsafe path for {name}: '{p}'")


def execute_dry_run(
    plan: BuildPlan,
    *,
    base_dir: Optional[str] = None,
    synthetic_artifacts: bool = False,
    status: BuildStatus = BuildStatus.DRY_RUN,
) -> BuildResult:
    """Execute a dry-run orchestration pass for a BuildPlan.

    CRITICAL: Dry-run result must NEVER be marked as build PASS.
    Local compilation or subprocess execution is strictly forbidden.
    """
    if not isinstance(plan, BuildPlan):
        raise TypeError(f"Expected BuildPlan, got {type(plan)}")

    if status == BuildStatus.PASS:
        raise ValueError("Dry-run result must NEVER be marked as build PASS.")

    if status not in (BuildStatus.DRY_RUN, BuildStatus.PLANNED, BuildStatus.NOT_EXECUTED):
        raise ValueError(f"Invalid dry-run status: {status}")

    worktree_path = plan.resolve_source_workspace_path(base_dir)
    out_dir = plan.resolve_out_dir(base_dir)
    log_dir = plan.resolve_log_dir(base_dir)
    result_path = plan.resolve_result_path(base_dir)

    _check_path_safety(worktree_path, out_dir, log_dir, result_path)

    resolved_commands = plan.resolve_commands(base_dir)
    _check_command_safety(resolved_commands)

    artifacts_found = tuple(plan.required_artifacts) if synthetic_artifacts else ()

    return BuildResult(
        profile_id=plan.profile_id,
        plan_digest=plan.digest,
        status=status,
        commands=resolved_commands,
        artifacts_expected=plan.required_artifacts,
        artifacts_found=artifacts_found,
        worktree_path=worktree_path,
        out_dir=out_dir,
        log_dir=log_dir,
        result_path=result_path,
        failure_category=None,
        error_message=None,
        metadata={
            "dry_run": True,
            "target_id": plan.target_id,
            "mode": plan.mode,
            "validation_gates": list(plan.expected_validation_gates),
            "toolchain": plan.toolchain_requirements.to_dict(),
        },
    )


def execute_build(
    plan: BuildPlan,
    *,
    base_dir: Optional[str] = None,
    allow_real_build: bool = False,
) -> BuildResult:
    """Guarded execution entrypoint. Real compilation is forbidden locally."""
    if not allow_real_build:
        raise BuildFailure(
            "Local compilation is forbidden. Real kernel builds must execute exclusively in CI."
        )
    raise BuildFailure(
        "Local build execution rejected: runner environment is not an authorized CI runner."
    )


def execute_all_dry_runs(
    plans: Sequence[BuildPlan],
    *,
    base_dir: Optional[str] = None,
    status: BuildStatus = BuildStatus.DRY_RUN,
) -> Tuple[BuildResult, ...]:
    """Execute dry-run for all plans and verify complete path isolation."""
    results: list[BuildResult] = []
    seen_worktrees: set[str] = set()
    seen_out_dirs: set[str] = set()
    seen_log_dirs: set[str] = set()
    seen_results: set[str] = set()

    for plan in plans:
        res = execute_dry_run(plan, base_dir=base_dir, status=status)

        if res.worktree_path in seen_worktrees:
            raise BuildFailure(f"Path isolation collision on worktree_path: {res.worktree_path}")
        if res.out_dir in seen_out_dirs:
            raise BuildFailure(f"Path isolation collision on out_dir: {res.out_dir}")
        if res.log_dir in seen_log_dirs:
            raise BuildFailure(f"Path isolation collision on log_dir: {res.log_dir}")
        if res.result_path in seen_results:
            raise BuildFailure(f"Path isolation collision on result_path: {res.result_path}")

        seen_worktrees.add(res.worktree_path)
        seen_out_dirs.add(res.out_dir)
        seen_log_dirs.add(res.log_dir)
        seen_results.add(res.result_path)

        results.append(res)

    return tuple(results)


__all__ = [
    "BuildStatus",
    "BuildResult",
    "execute_dry_run",
    "execute_build",
    "execute_all_dry_runs",
]
