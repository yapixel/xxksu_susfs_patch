"""Build orchestration subsystem for V2.10."""

from __future__ import annotations

from .classifier import ClassificationResult, FailureCategory, classify_failure
from .executor import BuildResult, BuildStatus, execute_all_dry_runs, execute_build, execute_dry_run
from .plan import (
    DEFAULT_REQUIRED_ARTIFACTS,
    DEFAULT_VALIDATION_GATES,
    BuildPlan,
    BuildToolchainSpec,
    create_all_canonical_plans,
    create_build_plan,
    create_build_plan_from_definition,
    export_ci_matrix,
    format_config_fragment,
)

__all__ = [
    # Plan
    "DEFAULT_REQUIRED_ARTIFACTS",
    "DEFAULT_VALIDATION_GATES",
    "BuildToolchainSpec",
    "BuildPlan",
    "format_config_fragment",
    "create_build_plan_from_definition",
    "create_build_plan",
    "create_all_canonical_plans",
    "export_ci_matrix",
    # Execution
    "BuildStatus",
    "BuildResult",
    "execute_dry_run",
    "execute_build",
    "execute_all_dry_runs",
    # Classifier
    "FailureCategory",
    "ClassificationResult",
    "classify_failure",
]
