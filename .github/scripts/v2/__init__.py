"""V2 structural patch infrastructure."""

from .engine.diff_parser import parse_patch
from .engine.emitter import emit_patch
from .model.manifest import load_manifest_set, load_profile_manifest, load_target_manifest
from .model.provenance import HashDigest, InputRef, PreparedInput, Provenance, canonical_json
from .source.cache import ContentAddressedCache
from .source.hashing import hash_bytes, hash_file, hash_tree
from .source.prepare import prepare
from .source.fetch import fetch
from .source.identity import GitIdentity, canonical_repository_url
from .semantic import SemanticInventory, SemanticUnit, SemanticId, SemanticFingerprint, CoverageLedger, EvidenceKind
from .validation import (
    ValidationStatus, ValidationResult, ValidationReport, ValidationError,
    validate_symbols, validate_abi, validate_ownership, validate_all,
    validate_config, parse_kconfig, FinalConfigMismatch, KconfigConflict, MissingPrerequisite,
)
from .profiles import (
    ProfileDefinition, ProfileCompositionResult, compose_profile, compose_all_profiles,
    get_profile_definition, get_profile_manifest, list_profile_definitions,
)
from .build import (
    BuildPlan, BuildToolchainSpec, BuildStatus, BuildResult,
    create_build_plan, create_all_canonical_plans, export_ci_matrix,
    execute_dry_run, execute_all_dry_runs, FailureCategory, classify_failure,
)

__all__ = ["parse_patch", "emit_patch", "load_manifest_set", "load_profile_manifest",
           "load_target_manifest", "HashDigest", "InputRef", "PreparedInput", "Provenance",
           "canonical_json", "ContentAddressedCache", "hash_bytes", "hash_file", "hash_tree",
           "prepare", "fetch", "GitIdentity", "canonical_repository_url", "SemanticInventory",
           "SemanticUnit", "SemanticId", "SemanticFingerprint", "CoverageLedger", "EvidenceKind",
           "ValidationStatus", "ValidationResult", "ValidationReport", "ValidationError",
           "validate_symbols", "validate_abi", "validate_ownership", "validate_all",
           "validate_config", "parse_kconfig", "FinalConfigMismatch", "KconfigConflict",
           "MissingPrerequisite", "ProfileDefinition", "ProfileCompositionResult",
           "compose_profile", "compose_all_profiles", "get_profile_definition",
           "get_profile_manifest", "list_profile_definitions",
           "BuildPlan", "BuildToolchainSpec", "BuildStatus", "BuildResult",
           "create_build_plan", "create_all_canonical_plans", "export_ci_matrix",
           "execute_dry_run", "execute_all_dry_runs", "FailureCategory", "classify_failure"]
