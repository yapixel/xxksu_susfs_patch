"""Strict authoritative baseline records and validation for V2."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple

from ..model.manifest import KNOWN_TARGETS, MANUAL_FIXTURES
from ..model.provenance import HashDigest, canonical_json
from .bundle import SourceBundle, load_source_bundle

BASELINE_SCHEMA = "xxksu-susfs-baseline/v1"


class BaselineError(ValueError):
    """Base error for baseline operations."""
    pass


class UnsupportedBaselineSchema(BaselineError):
    pass


class InvalidBaselineContract(BaselineError):
    pass


class BaselineBlocked(BaselineError):
    pass


@dataclass(frozen=True)
class BaselineRecord:
    """Immutable authoritative baseline record for a supported target."""

    schema: str
    target_id: str
    kernel_version: str
    status: str
    upstream: Mapping[str, Any]
    susfs: Mapping[str, Any] = field(default_factory=dict)
    fixtures: Mapping[str, str] = field(default_factory=dict)
    source_bundle: Mapping[str, Any] = field(default_factory=dict)
    retained_file_hashes: Mapping[str, Any] = field(default_factory=dict)
    patch_51: Mapping[str, Any] = field(default_factory=dict)
    validation_results: Mapping[str, str] = field(default_factory=dict)
    patch_10: Mapping[str, Any] = field(default_factory=dict)
    patch_11: Mapping[str, Any] = field(default_factory=dict)
    policy: Mapping[str, Any] = field(default_factory=dict)
    blocker_reason: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def validate(self) -> "BaselineRecord":
        if self.schema != BASELINE_SCHEMA:
            raise UnsupportedBaselineSchema(f"unsupported baseline schema: {self.schema}")

        if self.target_id == "xxksu":
            if self.status not in ("VERIFIED", "BLOCKED"):
                raise InvalidBaselineContract(f"invalid baseline status: {self.status}")
            if not self.upstream.get("repository") or not self.upstream.get("resolved_commit"):
                raise InvalidBaselineContract("xxksu baseline requires upstream repository and resolved_commit")
            if self.status == "VERIFIED":
                if not self.upstream.get("archive_sha256"):
                    raise InvalidBaselineContract("verified xxksu baseline requires upstream archive_sha256")
                bundle_id = self.source_bundle.get("identity")
                if not bundle_id or not isinstance(bundle_id, str):
                    raise InvalidBaselineContract("verified xxksu baseline requires source_bundle identity")
                if not self.retained_file_hashes:
                    raise InvalidBaselineContract("verified xxksu baseline requires retained_file_hashes")
                if self.patch_11.get("strict_apply") != "PASS":
                    raise InvalidBaselineContract("verified xxksu baseline requires patch_11 strict_apply PASS")
            elif self.status == "BLOCKED":
                if not self.blocker_reason:
                    raise InvalidBaselineContract("blocked xxksu baseline requires blocker_reason")
            return self

        if self.target_id not in KNOWN_TARGETS:
            raise InvalidBaselineContract(f"unknown or retired target: {self.target_id}")
        if self.status not in ("VERIFIED", "BLOCKED"):
            raise InvalidBaselineContract(f"invalid baseline status: {self.status}")

        # Upstream requirements
        if not self.upstream.get("repository") or not self.upstream.get("ref"):
            raise InvalidBaselineContract("upstream repository and ref are required")

        # SuSFS requirements
        if not self.susfs.get("repository") or not self.susfs.get("resolved_commit"):
            raise InvalidBaselineContract("susfs repository and resolved_commit are required")

        # Fixtures requirements
        for fix_name in MANUAL_FIXTURES:
            if fix_name not in self.fixtures:
                raise InvalidBaselineContract(f"missing fixture binding: {fix_name}")

        # Profile validation results
        expected_profiles = (f"{self.target_id}-manual", f"{self.target_id}-lsm_bl")
        for pid in expected_profiles:
            if pid not in self.validation_results:
                raise InvalidBaselineContract(f"missing profile validation result: {pid}")

        if self.status == "VERIFIED":
            if not self.upstream.get("resolved_commit"):
                raise InvalidBaselineContract("verified baseline requires resolved upstream commit")
            if not self.upstream.get("archive_sha256"):
                raise InvalidBaselineContract("verified baseline requires upstream archive SHA-256")
            bundle_id = self.source_bundle.get("identity")
            if not bundle_id or not isinstance(bundle_id, str):
                raise InvalidBaselineContract("verified baseline requires source_bundle identity")
            for pid in expected_profiles:
                if self.validation_results[pid] != "PASS":
                    raise InvalidBaselineContract(f"profile {pid} must PASS for verified baseline")
            if not self.retained_file_hashes:
                raise InvalidBaselineContract("verified baseline requires retained_file_hashes")
            if self.patch_51.get("strict_apply") != "PASS":
                raise InvalidBaselineContract("verified baseline requires strict_apply PASS")
        elif self.status == "BLOCKED":
            if not self.blocker_reason:
                raise InvalidBaselineContract("blocked baseline requires blocker_reason")
            for pid in expected_profiles:
                if self.validation_results[pid] != "BLOCKED":
                    raise InvalidBaselineContract(f"profile {pid} must be BLOCKED for blocked baseline")

        return self

    def identity_payload(self) -> dict[str, Any]:
        payload = {
            "schema": self.schema,
            "target_id": self.target_id,
            "kernel_version": self.kernel_version,
            "status": self.status,
            "upstream": dict(self.upstream),
            "source_bundle": dict(self.source_bundle),
            "retained_file_hashes": dict(sorted(self.retained_file_hashes.items())),
            "blocker_reason": self.blocker_reason,
            "metadata": dict(self.metadata),
        }
        if self.target_id == "xxksu":
            payload["patch_10"] = dict(self.patch_10)
            payload["patch_11"] = dict(self.patch_11)
            payload["policy"] = dict(self.policy)
        else:
            payload["susfs"] = dict(self.susfs)
            payload["fixtures"] = dict(sorted(self.fixtures.items()))
            payload["patch_51"] = dict(self.patch_51)
            payload["validation_results"] = dict(sorted(self.validation_results.items()))
        return payload

    def canonical_json(self) -> str:
        return canonical_json(self.identity_payload())

    @property
    def identity(self) -> HashDigest:
        digest_val = hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()
        return HashDigest("sha256", digest_val)

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self.canonical_json())


def load_baseline_record(data: Any) -> BaselineRecord:
    """Load and strictly validate a BaselineRecord from JSON string, Path, or Mapping."""
    if isinstance(data, (str, Path)):
        if isinstance(data, str) and data.lstrip().startswith("{"):
            raw = json.loads(data)
        else:
            raw = json.loads(Path(data).read_text(encoding="utf-8"))
    elif isinstance(data, Mapping):
        raw = dict(data)
    else:
        raise BaselineError("baseline data must be JSON string, Path, or Mapping")

    record = BaselineRecord(
        schema=raw.get("schema", BASELINE_SCHEMA),
        target_id=raw["target_id"],
        kernel_version=raw["kernel_version"],
        status=raw["status"],
        upstream=raw.get("upstream", {}),
        susfs=raw.get("susfs", {}),
        fixtures=raw.get("fixtures", {}),
        source_bundle=raw.get("source_bundle", {}),
        retained_file_hashes=raw.get("retained_file_hashes", {}),
        patch_51=raw.get("patch_51", {}),
        validation_results=raw.get("validation_results", {}),
        patch_10=raw.get("patch_10", {}),
        patch_11=raw.get("patch_11", {}),
        policy=raw.get("policy", {}),
        blocker_reason=raw.get("blocker_reason"),
        metadata=raw.get("metadata", {}),
    )
    return record.validate()


def get_baseline_path(target_id: str, repo_root: Optional[Path] = None) -> Path:
    """Resolve the canonical filesystem path of a target's BASELINE.json."""
    root = repo_root or Path(__file__).resolve().parents[4]
    return root / "patches" / target_id / "BASELINE.json"


def load_authoritative_bundle(
    target_id: str,
    repo_root: Optional[Path] = None,
) -> Optional[SourceBundle]:
    """Load the authoritative SourceBundle for a target, or return None if blocked."""
    root = repo_root or Path(__file__).resolve().parents[4]
    baseline_path = get_baseline_path(target_id, root)
    if not baseline_path.is_file():
        raise BaselineError(f"no baseline record found for target: {target_id}")

    record = load_baseline_record(baseline_path)
    if record.status != "VERIFIED":
        return None

    artifact_rel = record.source_bundle.get("artifact_path")
    if not artifact_rel:
        raise InvalidBaselineContract(f"verified baseline for {target_id} lacks artifact_path")

    bundle_path = root / artifact_rel
    if not bundle_path.is_file():
        raise BaselineError(f"authoritative bundle artifact not found at {bundle_path}")

    bundle = load_source_bundle(bundle_path)
    expected_identity = record.source_bundle.get("identity")
    if str(bundle.identity) != expected_identity:
        raise InvalidBaselineContract(
            f"bundle identity mismatch: expected {expected_identity}, got {bundle.identity}"
        )
    return bundle


__all__ = [
    "BASELINE_SCHEMA",
    "BaselineError",
    "UnsupportedBaselineSchema",
    "InvalidBaselineContract",
    "BaselineBlocked",
    "BaselineRecord",
    "load_baseline_record",
    "get_baseline_path",
    "load_authoritative_bundle",
]
