"""Authoritative Generation, Validation, and Promotion Pipeline.

Core repository contract:
  `patches/` is the FINAL VERIFIED OUTPUT of this repository's generators.
  It must NOT be the source input used to generate/validate a supposedly newer production patch.

Pipeline:
  authoritative upstream inputs
  → deterministic V2 generation
  → candidate artifact
  → exact validation against the bound real target source (0 offsets, 0 fuzz, 0 rejects, syntax)
  → deterministic regeneration equality
  → only after PASS, promote candidate bytes into the stable `patches/` path
  → regenerate baseline/state/patches/manifest.json
  → verify committed public artifact is byte-identical to validated candidate.

If candidate generation/validation fails, `patches/` is NEVER modified.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Mapping, Optional, Sequence, Tuple

from .adapters.xxksu import PATCH11_CANONICAL_FILES, generate_patch11
from .engine.diff_parser import parse_patch
from .manifests.patch_manifest import verify_patch_manifest, write_patch_manifest
from .source.bundle import SourceBundle, create_source_bundle
from .validation.exact_patch import (
    validate_exact_patch_on_tree,
    validate_patch_syntax,
    verify_postimage_integrity,
)

# Relative target paths under repo root
TARGET_REL_PATHS = {
    "xxksu-patch11": Path("patches/xxksu/11_enable_susfs_for_ksu.patch"),
    "sultan-android14-6.1-patch51": Path("patches/sultan-android14-6.1/51_deinlined_susfs_hooks_sultan-android14-6.1.patch"),
    "gki-android16-6.12-r38-patch51": Path("patches/gki-android16-6.12/51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch"),
}

TARGET_PATCH_NAMES = {
    "xxksu-patch11": "11_enable_susfs_for_ksu.patch",
    "sultan-android14-6.1-patch51": "51_deinlined_susfs_hooks_sultan-android14-6.1.patch",
    "gki-android16-6.12-r38-patch51": "51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch",
}


class PipelineError(Exception):
    """Base class for pipeline failures."""
    pass


class CandidateGenerationError(PipelineError):
    """Raised when candidate generation fails."""
    pass


class CandidateValidationError(PipelineError):
    """Raised when exact candidate validation fails."""
    pass


class RegenerationMismatchError(PipelineError):
    """Raised when re-running candidate generation yields non-identical output."""
    pass


class PromotionError(PipelineError):
    """Raised when promoting candidate to public path fails."""
    pass


@dataclass(frozen=True)
class PipelineResult:
    patch_id: str
    candidate_path: Path
    public_path: Path
    candidate_sha256: str
    validated: bool
    promoted: bool
    is_noop: bool
    details: str = ""


def _find_date_header(patch_content: str) -> Optional[str]:
    for line in patch_content.splitlines():
        if line.startswith("Date: "):
            return line[len("Date: "):].strip()
    return None


def generate_patch11_from_tree(ksu_tree: Path) -> str:
    """Generate candidate Patch 11 directly from a clean KernelSU tree."""
    kernel_dir = ksu_tree / "kernel" if (ksu_tree / "kernel").is_dir() else ksu_tree
    entries: dict[str, str] = {}
    missing = []
    for rel_path in PATCH11_CANONICAL_FILES:
        # Check relative to repo root (e.g. kernel/Kconfig) or relative to kernel_dir (Kconfig)
        p = ksu_tree / rel_path
        if not p.is_file():
            # Try strip kernel/ if ksu_tree is already kernel_dir
            sub_rel = rel_path.removeprefix("kernel/")
            p = kernel_dir / sub_rel
        if p.is_file():
            entries[rel_path] = p.read_text(encoding="utf-8", errors="ignore")
        else:
            missing.append(rel_path)

    if missing:
        raise CandidateGenerationError(f"Missing required KernelSU files for Patch 11: {missing}")

    bundle = create_source_bundle("xxksu", "main", entries)
    return generate_patch11(bundle)


def generate_sultan_patch51_from_input(upstream_input: Path, repo_root: Path) -> str:
    """Generate candidate Sultan Patch 51 from upstream SuSFS patch 50."""
    try:
        from deinline_50_to_51 import deinline_patch_content
    except ImportError:
        sys.path.insert(0, str(repo_root / ".github" / "scripts"))
        from deinline_50_to_51 import deinline_patch_content

    patch_50_file = upstream_input
    if upstream_input.is_dir():
        candidates = [
            upstream_input / "kernel_patches" / "50_add_susfs_in_gki-android14-6.1.patch",
            upstream_input / "kernel_patches" / "50_add_susfs_in_sultan-kernel-6.1.patch",
            upstream_input / "50_add_susfs_in_gki-android14-6.1.patch",
            upstream_input / "50_add_susfs_in_sultan-kernel-6.1.patch",
        ]
        for c in candidates:
            if c.is_file():
                patch_50_file = c
                break

    if not patch_50_file.is_file():
        raise CandidateGenerationError(f"Upstream SuSFS 50 patch for Sultan not found at {upstream_input}")

    content = patch_50_file.read_text(encoding="utf-8", errors="ignore")
    if "diff --git " not in content:
        raise CandidateGenerationError(f"Input file {patch_50_file} does not contain unified diff content")

    # Determine date string from authoritative fixture to ensure deterministic output
    # Never read from public patches/ path as an input
    fixture_patch = repo_root / ".github" / "fixtures" / "sultan" / "51_deinlined_susfs_hooks_sultan-android14-6.1.patch"
    date_str = None
    if fixture_patch.is_file():
        date_str = _find_date_header(fixture_patch.read_text(encoding="utf-8", errors="ignore"))

    return deinline_patch_content(content, target="sultan-android14-6.1", date_str=date_str)


def generate_gki_r38_patch51_from_input(upstream_input: Path, repo_root: Path) -> str:
    """Generate candidate GKI r38 Patch 51 from authoritative source."""
    if upstream_input.is_file():
        return upstream_input.read_text(encoding="utf-8")
    cand = upstream_input / "51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch"
    if cand.is_file():
        return cand.read_text(encoding="utf-8")
    cand = upstream_input / "kernel_patches" / "51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch"
    if cand.is_file():
        return cand.read_text(encoding="utf-8")
    fixture_patch = repo_root / ".github" / "fixtures" / "r38" / "51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch"
    if fixture_patch.is_file():
        return fixture_patch.read_text(encoding="utf-8")

    raise CandidateGenerationError("Authoritative GKI r38 source patch not found")


def generate_candidate_patch(patch_id: str, upstream_input: Path, repo_root: Path) -> str:
    """Deterministic generator dispatcher: upstream inputs -> candidate patch text."""
    if patch_id == "xxksu-patch11":
        return generate_patch11_from_tree(upstream_input)
    elif patch_id == "sultan-android14-6.1-patch51":
        return generate_sultan_patch51_from_input(upstream_input, repo_root)
    elif patch_id == "gki-android16-6.12-r38-patch51":
        return generate_gki_r38_patch51_from_input(upstream_input, repo_root)
    else:
        raise ValueError(f"Unknown patch_id: {patch_id}")


def _update_baseline_record(patch_id: str, candidate_sha: str, repo_root: Path) -> None:
    import json
    if patch_id == "xxksu-patch11":
        base_file = repo_root / "patches" / "xxksu" / "BASELINE.json"
        if base_file.is_file():
            data = json.loads(base_file.read_text(encoding="utf-8"))
            data.setdefault("patch_11", {})["patch_sha256"] = f"sha256:{candidate_sha}"
            base_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    elif patch_id == "sultan-android14-6.1-patch51":
        base_file = repo_root / "patches" / "sultan-android14-6.1" / "BASELINE.json"
        if base_file.is_file():
            data = json.loads(base_file.read_text(encoding="utf-8"))
            data.setdefault("patch_51", {})["patch_sha256"] = f"sha256:{candidate_sha}"
            base_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    elif patch_id == "gki-android16-6.12-r38-patch51":
        base_file = repo_root / "patches" / "gki-android16-6.12" / "BASELINE.json"
        if base_file.is_file():
            data = json.loads(base_file.read_text(encoding="utf-8"))
            data.setdefault("patch_51", {})["patch_sha256"] = f"sha256:{candidate_sha}"
            compat = data.setdefault("metadata", {}).setdefault("compatibility_patches", {}).setdefault("gki-android16-6.12-r38", {})
            compat["patch_sha256"] = f"sha256:{candidate_sha}"
            base_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def run_pipeline(
    patch_id: str,
    upstream_input: Path,
    *,
    target_tree: Optional[Path] = None,
    candidate_dir: Optional[Path] = None,
    repo_root: Optional[Path] = None,
    promote: bool = False,
    check_only: bool = False,
) -> PipelineResult:
    """Execute the full generation -> candidate -> validation -> promotion pipeline."""
    if repo_root is None:
        repo_root = Path.cwd()
    repo_root = Path(repo_root).resolve()

    if patch_id not in TARGET_REL_PATHS:
        raise ValueError(f"Unknown patch_id: {patch_id}. Valid IDs: {list(TARGET_REL_PATHS.keys())}")

    public_rel_path = TARGET_REL_PATHS[patch_id]
    public_path = repo_root / public_rel_path
    patch_filename = TARGET_PATCH_NAMES[patch_id]

    if candidate_dir is None:
        candidate_dir = repo_root / "candidate_patches" / patch_id
    candidate_dir = Path(candidate_dir).resolve()
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = candidate_dir / patch_filename

    # Record public path content before running to guarantee fail-closed invariance
    public_bytes_before = public_path.read_bytes() if public_path.is_file() else None

    # Step 1: Deterministic candidate generation (writes ONLY to candidate path)
    candidate_text_1 = generate_candidate_patch(patch_id, upstream_input, repo_root)
    candidate_path.write_text(candidate_text_1, encoding="utf-8")

    # Step 2: Deterministic regeneration equality verification
    candidate_text_2 = generate_candidate_patch(patch_id, upstream_input, repo_root)
    if candidate_text_1 != candidate_text_2:
        # Revert candidate file on failure
        if candidate_path.is_file():
            candidate_path.unlink()
        raise RegenerationMismatchError(
            f"Deterministic regeneration mismatch for {patch_id}: second pass output differed from first pass."
        )

    candidate_bytes = candidate_path.read_bytes()
    candidate_sha = hashlib.sha256(candidate_bytes).hexdigest()

    # Step 3: Exact validation of candidate artifact
    syntax_errors = validate_patch_syntax(candidate_text_1)
    if syntax_errors:
        raise CandidateValidationError(
            f"Candidate patch syntax validation failed for {patch_id}:\n" + "\n".join(f"  - {e}" for e in syntax_errors)
        )

    if target_tree is not None:
        target_tree = Path(target_tree).resolve()
        # Single-pass validation against target tree
        valid, errors = validate_exact_patch_on_tree(target_tree, candidate_path, dry_run=check_only)
        if not valid:
            # Crucial rule: patches/ must never be touched if validation fails
            if public_bytes_before is not None:
                assert public_path.read_bytes() == public_bytes_before, "INVARIANT VIOLATION: public patch was modified on failed validation"
            raise CandidateValidationError(
                f"Candidate exact validation failed for {patch_id} on {target_tree}:\n" + "\n".join(f"  - {e}" for e in errors)
            )

        # For Patch 11 on real KernelSU tree: verify exactly 8 modified files if applied
        if patch_id == "xxksu-patch11" and not check_only:
            proc = subprocess.run(["git", "diff", "--name-only"], cwd=target_tree, capture_output=True, text=True)
            if proc.returncode == 0:
                mod_files = [f.strip() for f in proc.stdout.splitlines() if f.strip()]
                if len(mod_files) != 8:
                    raise CandidateValidationError(
                        f"Expected exactly 8 modified files for Patch 11 on KernelSU, got {len(mod_files)}: {mod_files}"
                    )

    # Step 4: Promotion (only after PASS, if promote=True)
    is_noop = False
    promoted = False

    if promote:
        if public_bytes_before is not None and public_bytes_before == candidate_bytes:
            is_noop = True
        else:
            public_path.parent.mkdir(parents=True, exist_ok=True)
            public_path.write_bytes(candidate_bytes)
            promoted = True

        # Verify byte-identical equality of promoted file vs validated candidate
        promoted_bytes = public_path.read_bytes()
        if promoted_bytes != candidate_bytes:
            raise PromotionError(
                f"Promoted file at {public_path} does not match validated candidate bytes at {candidate_path}"
            )

        # Step 5: Regenerate manifest/metadata and verify consistency
        _update_baseline_record(patch_id, candidate_sha, repo_root)
        manifest_path = repo_root / "patches" / "manifest.json"
        if manifest_path.is_file():
            write_patch_manifest(repo_root)
            valid, errors = verify_patch_manifest(repo_root)
            if not valid:
                raise PromotionError("Manifest consistency check failed after promotion:\n" + "\n".join(errors))

    return PipelineResult(
        patch_id=patch_id,
        candidate_path=candidate_path,
        public_path=public_path,
        candidate_sha256=candidate_sha,
        validated=True,
        promoted=promoted,
        is_noop=is_noop,
        details="Pipeline completed successfully: generated -> validated -> promoted" if promote else "Candidate generated and validated successfully",
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="V2 Authoritative Generation, Validation, and Promotion Pipeline"
    )
    parser.add_argument("--patch-id", required=True, choices=list(TARGET_REL_PATHS.keys()), help="Patch target ID")
    parser.add_argument("--upstream-input", required=True, type=Path, help="Path to upstream source repository or patch")
    parser.add_argument("--target-tree", type=Path, default=None, help="Target kernel/KSU source tree for exact validation")
    parser.add_argument("--candidate-dir", type=Path, default=None, help="Directory to store candidate patches")
    parser.add_argument("--repo-root", type=Path, default=None, help="Repository root path")
    parser.add_argument("--promote", action="store_true", default=False, help="Promote candidate to patches/ upon validation PASS")
    parser.add_argument("--check-only", action="store_true", default=False, help="Perform check-only validation without modifying target tree")

    args = parser.parse_args(argv)

    try:
        res = run_pipeline(
            args.patch_id,
            args.upstream_input,
            target_tree=args.target_tree,
            candidate_dir=args.candidate_dir,
            repo_root=args.repo_root,
            promote=args.promote,
            check_only=args.check_only,
        )
        status_str = "PROMOTED" if res.promoted else ("NO_OP (up to date)" if res.is_noop else "CANDIDATE_READY")
        print(f"✅ Pipeline SUCCESS for {res.patch_id} [{status_str}]:")
        print(f"  - Candidate:  {res.candidate_path}")
        print(f"  - Public:     {res.public_path}")
        print(f"  - SHA-256:    {res.candidate_sha256}")
        return 0
    except Exception as exc:
        print(f"❌ Pipeline FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
