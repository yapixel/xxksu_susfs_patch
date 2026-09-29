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
import copy
from datetime import datetime, timezone
from email.utils import format_datetime
from dataclasses import dataclass
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Mapping, Optional, Sequence, Tuple

from .adapters.xxksu import PATCH11_CANONICAL_FILES, generate_patch11
from .engine.diff_parser import parse_patch
from .manifests.patch_manifest import verify_patch_manifest, generate_patch_manifest, format_manifest
from .semantic.gate import verify_semantic_gate_for_pipeline
from .semantic.registry import SemanticRegistry
from .source.bundle import SourceBundle, create_source_bundle
from .validation.exact_patch import (
    validate_exact_patch_on_tree,
    validate_patch_syntax,
    verify_postimage_integrity,
    substantive_patch_text,
)

logger = logging.getLogger(__name__)

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


class SemanticApprovalError(PipelineError):
    """Raised when upstream candidate fails semantic inventory or policy approval."""
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


class DeliveryError(PipelineError):
    """Raised when git delivery, commit, or push fails."""
    pass


class DeliveryVerificationError(PipelineError):
    """Raised when verifying delivered remote artifact fails."""
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
    committed: bool = False
    pushed: bool = False
    commit_sha: Optional[str] = None
    details: str = ""
    publication_state: str = "VALIDATION_ONLY"


def _sultan_source_date(repo_root: Path) -> str:
    """UTC mail date from the accepted SuSFS Git object, never an output patch."""
    baseline = json.loads((repo_root / "patches/sultan-android14-6.1/BASELINE.json").read_text())
    commit = baseline["susfs"]["resolved_commit"]
    raw = (repo_root / ".github/fixtures/sultan/susfs-source-commit.txt").read_bytes()
    identity = hashlib.sha1(b"commit " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if identity != commit:
        raise CandidateGenerationError("Sultan source commit metadata identity mismatch")
    headers = raw.split(b"\n\n", 1)[0].splitlines()
    committer = next(line for line in headers if line.startswith(b"committer "))
    timestamp = int(committer.rsplit(b" ", 2)[1])
    return format_datetime(datetime.fromtimestamp(timestamp, timezone.utc))


def generate_patch11_from_tree(ksu_tree: Path, repo_root: Optional[Path] = None) -> str:
    """Generate from xxKSU and reviewed repository policy; Patch 10 is watched lineage."""
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
    return generate_patch11(bundle, repo_root)


def generate_sultan_patch51_from_input(upstream_input: Path, repo_root: Path) -> str:
    """Generate candidate Sultan Patch 51 from upstream SuSFS patch 50."""
    from .policy.patch51_source import generate
    try:
        return generate("sultan-android14-6.1-patch51", upstream_input, repo_root)[0]
    except (ValueError, KeyError, OSError) as exc:
        raise CandidateGenerationError(str(exc)) from exc


def generate_gki_r38_patch51_from_input(upstream_input: Path, repo_root: Path) -> str:
    """Reconstruct from accepted Patch 50 and authenticated r38 preimages."""
    from .policy.patch51_source import generate
    try:
        return generate("gki-android16-6.12-r38-patch51", upstream_input, repo_root)[0]
    except (ValueError, KeyError, OSError) as exc:
        raise CandidateGenerationError(str(exc)) from exc


def generate_candidate_patch(patch_id: str, upstream_input: Path, repo_root: Path) -> str:
    """Deterministic generator dispatcher: upstream inputs -> candidate patch text."""
    if patch_id == "xxksu-patch11":
        return generate_patch11_from_tree(upstream_input, repo_root)
    elif patch_id == "sultan-android14-6.1-patch51":
        return generate_sultan_patch51_from_input(upstream_input, repo_root)
    elif patch_id == "gki-android16-6.12-r38-patch51":
        return generate_gki_r38_patch51_from_input(upstream_input, repo_root)
    else:
        raise ValueError(f"Unknown patch_id: {patch_id}")


def _extract_git_commit(upstream_input: Path) -> Optional[str]:
    """Extract 40-hex git commit SHA from a directory if it is a git repo."""
    git_dir = upstream_input / ".git"
    if not git_dir.exists():
        return None
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=upstream_input, capture_output=True, text=True)
    if proc.returncode == 0:
        c = proc.stdout.strip()
        if len(c) == 40 and all(ch in "0123456789abcdefABCDEF" for ch in c):
            return c.lower()
    return None


def _plan_metadata_updates(
    candidate_shas: Mapping[str, str], upstream_commits: Mapping[str, str],
    repo_root: Path,
) -> dict[Path, bytes]:
    """Read-only plan for the existing baseline/provenance synchronization fields.

    Commits are supplied only after the caller's validation gates. Equality of
    patch bytes does not imply equality of accepted source provenance.
    """
    updates = {}
    for patch_id, candidate_sha in candidate_shas.items():
        path = TARGET_REL_PATHS[patch_id].parent / "BASELINE.json"
        full_path = repo_root / path
        if not full_path.is_file():
            continue
        before = json.loads(full_path.read_bytes())
        data = copy.deepcopy(before)
        key = "patch_11" if patch_id == "xxksu-patch11" else "patch_51"
        data.setdefault(key, {})["patch_sha256"] = f"sha256:{candidate_sha}"
        if patch_id == "gki-android16-6.12-r38-patch51":
            compat = data.setdefault("metadata", {}).setdefault("compatibility_patches", {}).setdefault("gki-android16-6.12-r38", {})
            compat["patch_sha256"] = f"sha256:{candidate_sha}"
        commit = upstream_commits.get(patch_id)
        if commit:
            lineage = "upstream" if patch_id == "xxksu-patch11" else "susfs"
            data.setdefault(lineage, {})["resolved_commit"] = commit
        if data != before:
            updates[path] = (json.dumps(data, indent=2) + "\n").encode()

    state_path = Path(".github/upstream-state.json")
    if upstream_commits and (repo_root / state_path).is_file():
        before = json.loads((repo_root / state_path).read_bytes())
        data = copy.deepcopy(before)
        authoritative = data.get("sources", {}).get("authoritative", {})
        source_keys = {
            "xxksu-patch11": "backslashxx_kernelsu",
            "sultan-android14-6.1-patch51": "susfs_sultan",
            "gki-android16-6.12-r38-patch51": "susfs_gki",
        }
        for patch_id in candidate_shas:
            commit = upstream_commits.get(patch_id)
            key = source_keys[patch_id]
            if commit and key in authoritative:
                authoritative[key]["commit"] = commit
        if data != before:
            updates[state_path] = (json.dumps(data, indent=2) + "\n").encode()
    return updates


def _manifest_is_current(repo_root: Path) -> bool:
    return (not (repo_root / "patches/manifest.json").is_file()
            or verify_patch_manifest(repo_root)[0])


def _publish_metadata(updates: Mapping[Path, bytes], repo_root: Path) -> None:
    """Apply only planned metadata changes, then synchronize shared manifest once."""
    for path, content in updates.items():
        (repo_root / path).write_bytes(content)
    manifest = repo_root / "patches/manifest.json"
    if manifest.is_file():
        expected = format_manifest(generate_patch_manifest(repo_root)).encode()
        if manifest.read_bytes() != expected:
            manifest.write_bytes(expected)
        valid, errors = verify_patch_manifest(repo_root)
        if not valid:
            raise PromotionError("Manifest consistency check failed:\n" + "\n".join(errors))


def _resolve_repo_slug(repo_root: Path, git_remote: str) -> Optional[str]:
    """Resolve GitHub owner/repo slug from GITHUB_REPOSITORY or git remote URL."""
    slug = os.environ.get("GITHUB_REPOSITORY")
    if slug:
        return slug
    proc = subprocess.run(["git", "remote", "get-url", git_remote], cwd=repo_root, capture_output=True, text=True)
    if proc.returncode == 0:
        m = re.search(r"github\.com[:/]([^/]+/[^/\.]+)", proc.stdout.strip())
        if m:
            return m.group(1).removesuffix(".git")
    return None


def _verify_raw_github_url(repo_slug: str, commit_or_ref: str, rel_path: Path, expected_sha: str) -> None:
    """Verify that raw.githubusercontent.com serves the exact expected candidate SHA."""
    import urllib.request
    import urllib.error
    import time

    raw_url = f"https://raw.githubusercontent.com/{repo_slug}/{commit_or_ref}/{rel_path}"
    last_err = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(
                raw_url,
                headers={"User-Agent": "xxksu-pipeline/1.0", "Cache-Control": "no-cache"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
            actual_sha = hashlib.sha256(data).hexdigest()
            if actual_sha != expected_sha:
                raise DeliveryVerificationError(
                    f"Raw URL {raw_url} SHA-256 mismatch: expected {expected_sha}, got {actual_sha}"
                )
            return
        except urllib.error.URLError as exc:
            last_err = exc
            time.sleep(1.5)
        except Exception as exc:
            raise DeliveryVerificationError(f"Failed verifying raw URL {raw_url}: {exc}")

    # If all attempts failed with URLError (e.g. offline / firewall)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        raise DeliveryVerificationError(f"Failed reaching raw URL {raw_url}: {last_err}")


def _verify_existing_delivery(
    patch_id: str,
    candidate_sha: str,
    candidate_bytes: bytes,
    repo_root: Path,
    git_remote: str,
    git_branch: str,
) -> None:
    """Verify existing tracking branch and raw URL serve expected candidate bytes."""
    remotes_proc = subprocess.run(["git", "remote"], cwd=repo_root, capture_output=True, text=True)
    if git_remote in remotes_proc.stdout.split():
        show_proc = subprocess.run(
            ["git", "show", f"{git_remote}/{git_branch}:{TARGET_REL_PATHS[patch_id]}"],
            cwd=repo_root,
            capture_output=True,
        )
        if show_proc.returncode == 0 and show_proc.stdout != candidate_bytes:
            raise DeliveryVerificationError(
                f"Byte mismatch on existing {git_remote}/{git_branch}:{TARGET_REL_PATHS[patch_id]} vs candidate"
            )
        repo_slug = _resolve_repo_slug(repo_root, git_remote)
        if repo_slug:
            _verify_raw_github_url(repo_slug, git_branch, TARGET_REL_PATHS[patch_id], candidate_sha)


def deliver_promotion(
    patch_id: str,
    candidate_path: Path,
    candidate_bytes: bytes,
    candidate_sha: str,
    repo_root: Path,
    *,
    git_remote: str = "origin",
    git_branch: str = "main",
    verify_raw_url: bool = True,
    updated_upstream_state: bool = False,
) -> Tuple[bool, bool, Optional[str]]:
    """Commit and push verified pipeline changes to git, and verify remote delivery.

    Returns (committed: bool, pushed: bool, commit_sha: Optional[str]).
    If no diff is present on allowed paths, returns (False, False, None).
    """
    allowed_paths = [
        TARGET_REL_PATHS[patch_id],
        Path("patches/manifest.json"),
    ]
    if patch_id == "xxksu-patch11":
        allowed_paths.append(Path("patches/xxksu/BASELINE.json"))
    elif patch_id == "sultan-android14-6.1-patch51":
        allowed_paths.append(Path("patches/sultan-android14-6.1/BASELINE.json"))
    elif patch_id == "gki-android16-6.12-r38-patch51":
        allowed_paths.append(Path("patches/gki-android16-6.12/BASELINE.json"))

    if updated_upstream_state and (repo_root / ".github" / "upstream-state.json").is_file():
        allowed_paths.append(Path(".github/upstream-state.json"))

    git_dir = repo_root / ".git"
    if not git_dir.exists():
        return False, False, None

    # Stage ONLY modified files among allowed paths (never commit unrelated or reference files)
    staged_any = False
    for rel_path in allowed_paths:
        full_path = repo_root / rel_path
        if not full_path.is_file():
            continue
        status_proc = subprocess.run(
            ["git", "status", "--porcelain", "--", str(rel_path)],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if status_proc.returncode == 0 and status_proc.stdout.strip():
            add_proc = subprocess.run(
                ["git", "add", "--", str(rel_path)],
                cwd=repo_root,
                capture_output=True,
                text=True,
            )
            if add_proc.returncode != 0:
                raise DeliveryError(f"Failed to git add {rel_path}: {add_proc.stderr}")
            staged_any = True

    diff_proc = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=repo_root,
    )
    if diff_proc.returncode == 0:
        # No diff on allowed paths; exit successfully without commit
        if verify_raw_url:
            _verify_existing_delivery(patch_id, candidate_sha, candidate_bytes, repo_root, git_remote, git_branch)
        return False, False, None

    # Configure git author if not already set
    name_proc = subprocess.run(["git", "config", "user.name"], cwd=repo_root, capture_output=True, text=True)
    if not name_proc.stdout.strip():
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], cwd=repo_root, check=True)
    email_proc = subprocess.run(["git", "config", "user.email"], cwd=repo_root, capture_output=True, text=True)
    if not email_proc.stdout.strip():
        subprocess.run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], cwd=repo_root, check=True)

    commit_msg = (
        f"auto(pipeline): deliver verified {patch_id} production patch [skip ci]\n\n"
        f"Candidate SHA-256: {candidate_sha}\n"
        f"Target relative path: {TARGET_REL_PATHS[patch_id]}\n"
    )
    commit_proc = subprocess.run(
        ["git", "commit", "-m", commit_msg],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if commit_proc.returncode != 0:
        raise DeliveryError(f"git commit failed:\n{commit_proc.stderr}\n{commit_proc.stdout}")

    commit_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    # Push to remote (standard push, no force-push)
    remotes_proc = subprocess.run(["git", "remote"], cwd=repo_root, capture_output=True, text=True)
    remotes = remotes_proc.stdout.split()
    pushed = False
    if git_remote in remotes:
        # Pull --rebase first to absorb any concurrent non-conflicting commits cleanly
        pull_proc = subprocess.run(
            ["git", "pull", "--rebase", git_remote, git_branch],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if pull_proc.returncode != 0:
            subprocess.run(["git", "rebase", "--abort"], cwd=repo_root, capture_output=True)
            raise DeliveryError(f"git pull --rebase failed:\n{pull_proc.stderr}")

        commit_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        push_proc = subprocess.run(
            ["git", "push", git_remote, f"HEAD:{git_branch}"],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if push_proc.returncode != 0:
            raise DeliveryError(f"git push failed:\n{push_proc.stderr}\n{push_proc.stdout}")
        pushed = True

        # Ensure local remote tracking ref is up to date with remote
        subprocess.run(["git", "fetch", git_remote, git_branch], cwd=repo_root, capture_output=True)

        # Verify origin/main contains exact validated candidate bytes
        show_proc = subprocess.run(
            ["git", "show", f"{git_remote}/{git_branch}:{TARGET_REL_PATHS[patch_id]}"],
            cwd=repo_root,
            capture_output=True,
            check=True,
        )
        if show_proc.stdout != candidate_bytes:
            raise DeliveryVerificationError(
                f"Byte mismatch on {git_remote}/{git_branch}:{TARGET_REL_PATHS[patch_id]} "
                f"({len(show_proc.stdout)} bytes) vs candidate ({len(candidate_bytes)} bytes)"
            )

        # Verify public raw patch SHA-256 equals promoted candidate SHA-256
        if verify_raw_url:
            repo_slug = _resolve_repo_slug(repo_root, git_remote)
            if repo_slug:
                _verify_raw_github_url(repo_slug, commit_sha, TARGET_REL_PATHS[patch_id], candidate_sha)

    return True, pushed, commit_sha


def deliver_multi_candidates(
    candidate_targets: Mapping[str, Path],
    *,
    repo_root: Optional[Path] = None,
    write_back: bool = False,
    git_remote: str = "origin",
    git_branch: str = "main",
    verify_raw_url: bool = True,
    upstream_commits: Optional[Mapping[str, str]] = None,
) -> Tuple[bool, bool, Optional[str], dict[str, str]]:
    """Atomically promote and deliver multiple validated candidates to git.

    Returns (state_changed: bool, pushed: bool, commit_sha: Optional[str], candidate_shas: dict[str, str]).
    state_changed includes metadata-only promotion; all supplied candidates must
    already have passed the upstream validation jobs.
    """
    if repo_root is None:
        repo_root = Path.cwd()
    repo_root = Path(repo_root).resolve()

    for patch_id, cand_path in candidate_targets.items():
        if patch_id not in TARGET_REL_PATHS:
            raise ValueError(f"Unknown patch_id: {patch_id}. Valid IDs: {list(TARGET_REL_PATHS.keys())}")
        if not cand_path.is_file():
            raise FileNotFoundError(f"Candidate file not found for {patch_id}: {cand_path}")

    # Validate syntax and compute SHA for all candidates
    candidate_data: dict[str, tuple[Path, bytes, str]] = {}
    candidate_shas: dict[str, str] = {}
    for patch_id, cand_path in candidate_targets.items():
        text = cand_path.read_text(encoding="utf-8")
        syntax_errors = validate_patch_syntax(text)
        if syntax_errors:
            raise CandidateValidationError(
                f"Candidate patch syntax validation failed for {patch_id}:\n" + "\n".join(f"  - {e}" for e in syntax_errors)
            )
        cand_bytes = cand_path.read_bytes()
        cand_sha = hashlib.sha256(cand_bytes).hexdigest()
        candidate_data[patch_id] = (cand_path, cand_bytes, cand_sha)
        candidate_shas[patch_id] = cand_sha


    # Compare candidates against existing public files
    changed_targets: dict[str, tuple[Path, bytes, str]] = {}
    for patch_id, (cand_path, cand_bytes, cand_sha) in candidate_data.items():
        public_path = repo_root / TARGET_REL_PATHS[patch_id]
        public_bytes = public_path.read_bytes() if public_path.is_file() else None
        if public_bytes != cand_bytes:
            changed_targets[patch_id] = (cand_path, cand_bytes, cand_sha)

    metadata_updates = _plan_metadata_updates(candidate_shas, upstream_commits or {}, repo_root)
    if not changed_targets and not metadata_updates and _manifest_is_current(repo_root):
        # FULL_STATE_NOOP: validation is complete; no publication work is needed.
        if write_back and verify_raw_url:
            for patch_id, (cand_path, cand_bytes, cand_sha) in candidate_data.items():
                _verify_existing_delivery(patch_id, cand_sha, cand_bytes, repo_root, git_remote, git_branch)
        return False, False, None, candidate_shas

    # Promote changed candidates into patches/
    for patch_id, (cand_path, cand_bytes, cand_sha) in changed_targets.items():
        public_path = repo_root / TARGET_REL_PATHS[patch_id]
        public_path.parent.mkdir(parents=True, exist_ok=True)
        public_path.write_bytes(cand_bytes)
        if public_path.read_bytes() != cand_bytes:
            raise PromotionError(f"Promoted file at {public_path} does not match candidate bytes")

    _publish_metadata(metadata_updates, repo_root)

    if not write_back:
        return True, False, None, candidate_shas

    # Write-back to git
    git_dir = repo_root / ".git"
    if not git_dir.exists():
        return True, False, None, candidate_shas

    allowed_paths = [Path("patches/manifest.json"), *metadata_updates]
    allowed_paths.extend(TARGET_REL_PATHS[patch_id] for patch_id in changed_targets)

    for rel_path in allowed_paths:
        full_path = repo_root / rel_path
        if not full_path.is_file():
            continue
        status_proc = subprocess.run(
            ["git", "status", "--porcelain", "--", str(rel_path)],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if status_proc.returncode == 0 and status_proc.stdout.strip():
            add_proc = subprocess.run(
                ["git", "add", "--", str(rel_path)],
                cwd=repo_root,
                capture_output=True,
                text=True,
            )
            if add_proc.returncode != 0:
                raise DeliveryError(f"Failed to git add {rel_path}: {add_proc.stderr}")

    diff_proc = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo_root)
    if diff_proc.returncode == 0:
        if verify_raw_url:
            for patch_id, (cand_path, cand_bytes, cand_sha) in candidate_data.items():
                _verify_existing_delivery(patch_id, cand_sha, cand_bytes, repo_root, git_remote, git_branch)
        return True, False, None, candidate_shas

    # Configure author
    name_proc = subprocess.run(["git", "config", "user.name"], cwd=repo_root, capture_output=True, text=True)
    if not name_proc.stdout.strip():
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], cwd=repo_root, check=True)
    email_proc = subprocess.run(["git", "config", "user.email"], cwd=repo_root, capture_output=True, text=True)
    if not email_proc.stdout.strip():
        subprocess.run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], cwd=repo_root, check=True)

    summary_lines = "\n".join(f"- {pid}: {csha}" for pid, csha in candidate_shas.items())
    commit_msg = (
        "auto(pipeline): deliver verified 51 patch production outputs [skip ci]\n\n"
        f"Validated candidates:\n{summary_lines}\n"
    )

    commit_proc = subprocess.run(
        ["git", "commit", "-m", commit_msg],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if commit_proc.returncode != 0:
        raise DeliveryError(f"git commit failed:\n{commit_proc.stderr}\n{commit_proc.stdout}")

    commit_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    remotes_proc = subprocess.run(["git", "remote"], cwd=repo_root, capture_output=True, text=True)
    remotes = remotes_proc.stdout.split()
    pushed = False
    if git_remote in remotes:
        pull_proc = subprocess.run(
            ["git", "pull", "--rebase", git_remote, git_branch],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if pull_proc.returncode != 0:
            subprocess.run(["git", "rebase", "--abort"], cwd=repo_root, capture_output=True)
            raise DeliveryError(f"git pull --rebase failed:\n{pull_proc.stderr}")

        commit_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        push_proc = subprocess.run(
            ["git", "push", git_remote, f"HEAD:{git_branch}"],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if push_proc.returncode != 0:
            raise DeliveryError(f"git push failed:\n{push_proc.stderr}\n{push_proc.stdout}")
        pushed = True

        subprocess.run(["git", "fetch", git_remote, git_branch], cwd=repo_root, capture_output=True)

        # Verify all candidates match on origin/main
        for patch_id, (_, cand_bytes, _) in candidate_data.items():
            show_proc = subprocess.run(
                ["git", "show", f"{git_remote}/{git_branch}:{TARGET_REL_PATHS[patch_id]}"],
                cwd=repo_root,
                capture_output=True,
                check=True,
            )
            if show_proc.stdout != cand_bytes:
                raise DeliveryVerificationError(
                    f"Byte mismatch on {git_remote}/{git_branch}:{TARGET_REL_PATHS[patch_id]} vs candidate"
                )

        if verify_raw_url:
            repo_slug = _resolve_repo_slug(repo_root, git_remote)
            if repo_slug:
                for patch_id, (_, _, cand_sha) in candidate_data.items():
                    _verify_raw_github_url(repo_slug, commit_sha, TARGET_REL_PATHS[patch_id], cand_sha)

    return True, pushed, commit_sha, candidate_shas


def run_pipeline(
    patch_id: str,
    upstream_input: Path,
    *,
    target_tree: Optional[Path] = None,
    candidate_dir: Optional[Path] = None,
    repo_root: Optional[Path] = None,
    promote: bool = False,
    check_only: bool = False,
    registry: Optional[SemanticRegistry] = None,
    write_back: bool = False,
    git_remote: str = "origin",
    git_branch: str = "main",
    verify_raw_url: bool = True,
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
    else:
        candidate_dir = Path(candidate_dir).resolve()
        if candidate_dir.name != patch_id:
            candidate_dir = candidate_dir / patch_id
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = candidate_dir / patch_filename

    # Record public path content before running to guarantee fail-closed invariance
    public_bytes_before = public_path.read_bytes() if public_path.is_file() else None

    # Step 0: Shared semantic inventory and policy validation gate
    # Any unapproved semantic drift or anchor drift immediately fails closed
    gate_result = verify_semantic_gate_for_pipeline(
        patch_id,
        upstream_input,
        repo_root=repo_root,
        registry=registry,
    )
    if not gate_result.passed:
        # Crucial fail-closed invariance: verify public patch was not modified
        if public_bytes_before is not None:
            assert public_path.read_bytes() == public_bytes_before, "INVARIANT VIOLATION: public patch was modified on blocked semantic gate"
        raise SemanticApprovalError(
            f"Semantic gate evaluation failed for {patch_id} ({gate_result.classification.value}):\n"
            f"{gate_result.details}"
        )

    # Step 1: Deterministic candidate generation (writes ONLY to candidate path)
    postimages = None
    if patch_id.endswith("patch51") and target_tree is not None:
        from .policy.patch51_source import generate
        candidate_text_1, postimages = generate(patch_id, upstream_input, repo_root, target_tree)
    else:
        candidate_text_1 = generate_candidate_patch(patch_id, upstream_input, repo_root)
    candidate_path.write_text(candidate_text_1, encoding="utf-8")

    # Step 2: Deterministic regeneration equality verification
    if postimages is not None:
        candidate_text_2, reproduced = generate(patch_id, upstream_input, repo_root, target_tree)
        if reproduced != postimages:
            raise RegenerationMismatchError("independent source reconstruction differs")
    else:
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
        if postimages is not None:
            # An archive target nested below the checkout must not inherit the
            # parent repository's path prefix (git apply would skip every file).
            if not (target_tree / ".git").exists():
                subprocess.run(["git", "init", "-q", str(target_tree)], check=True)
            subprocess.run(["git", "apply", "--check", str(candidate_path)], cwd=target_tree, check=True)
        # Single-pass validation against target tree
        valid, errors = validate_exact_patch_on_tree(target_tree, candidate_path, dry_run=check_only)
        if not valid:
            # Crucial rule: patches/ must never be touched if validation fails
            if public_bytes_before is not None:
                assert public_path.read_bytes() == public_bytes_before, "INVARIANT VIOLATION: public patch was modified on failed validation"
            raise CandidateValidationError(
                f"Candidate exact validation failed for {patch_id} on {target_tree}:\n" + "\n".join(f"  - {e}" for e in errors)
            )

        if postimages is not None and not check_only:
            for path, hashes in postimages.items():
                hashes["applied"] = hashlib.sha256((target_tree / path).read_bytes()).hexdigest()
                if hashes["applied"] != hashes["postimage"]:
                    raise CandidateValidationError(f"postimage round-trip mismatch: {path}")
            (candidate_dir / "postimages.json").write_text(json.dumps(postimages, indent=2))

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
    committed = False
    pushed = False
    commit_sha = None

    publication_state = "VALIDATION_ONLY"
    if promote:
        upstream_commit = _extract_git_commit(upstream_input)
        metadata_updates = _plan_metadata_updates(
            {patch_id: candidate_sha},
            {patch_id: upstream_commit} if upstream_commit else {}, repo_root,
        )
        patch_changed = public_bytes_before != candidate_bytes
        old_substantive = (substantive_patch_text(public_bytes_before.decode("utf-8"))
                           if public_bytes_before is not None else None)
        new_substantive = substantive_patch_text(candidate_text_1)
        substantive_changed = old_substantive != new_substantive
        if not patch_changed and not metadata_updates and _manifest_is_current(repo_root):
            if write_back and verify_raw_url:
                _verify_existing_delivery(patch_id, candidate_sha, candidate_bytes,
                                          repo_root, git_remote, git_branch)
            return PipelineResult(
                patch_id=patch_id, candidate_path=candidate_path, public_path=public_path,
                candidate_sha256=candidate_sha, validated=True, promoted=False,
                is_noop=True, publication_state="FULL_STATE_NOOP",
                details="Validated candidate and authoritative metadata already current",
            )
        publication_state = "PATCH_PROMOTION" if substantive_changed else "METADATA_ONLY_PROMOTION"
        if patch_changed:
            public_path.parent.mkdir(parents=True, exist_ok=True)
            public_path.write_bytes(candidate_bytes)
            promoted = True

        # Verify byte-identical equality of promoted file vs validated candidate
        promoted_bytes = public_path.read_bytes()
        if promoted_bytes != candidate_bytes:
            raise PromotionError(
                f"Promoted file at {public_path} does not match validated candidate bytes at {candidate_path}"
            )

        _publish_metadata(metadata_updates, repo_root)
        updated_upstream_state = Path(".github/upstream-state.json") in metadata_updates

        # Step 6: Delivery / Write-Back (origin/main)
        if write_back:
            committed, pushed, commit_sha = deliver_promotion(
                patch_id=patch_id,
                candidate_path=candidate_path,
                candidate_bytes=candidate_bytes,
                candidate_sha=candidate_sha,
                repo_root=repo_root,
                git_remote=git_remote,
                git_branch=git_branch,
                verify_raw_url=verify_raw_url,
                updated_upstream_state=updated_upstream_state,
            )

    return PipelineResult(
        patch_id=patch_id,
        candidate_path=candidate_path,
        public_path=public_path,
        candidate_sha256=candidate_sha,
        validated=True,
        promoted=promoted,
        is_noop=is_noop,
        publication_state=publication_state,
        committed=committed,
        pushed=pushed,
        commit_sha=commit_sha,
        details=(
            "Pipeline delivered verified changes to git"
            if committed
            else (f"Pipeline completed successfully: {publication_state}" if promote else "Candidate generated and validated successfully")
        ),
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="V2 Authoritative Generation, Validation, and Promotion Pipeline"
    )
    parser.add_argument("--patch-id", required=False, choices=list(TARGET_REL_PATHS.keys()), help="Patch target ID")
    parser.add_argument("--upstream-input", required=False, type=Path, help="Path to upstream source repository or patch")
    parser.add_argument("--target-tree", type=Path, default=None, help="Target kernel/KSU source tree for exact validation")
    parser.add_argument("--candidate-dir", type=Path, default=None, help="Directory to store candidate patches")
    parser.add_argument("--repo-root", type=Path, default=None, help="Repository root path")
    parser.add_argument("--promote", action="store_true", default=False, help="Promote candidate to patches/ upon validation PASS")
    parser.add_argument("--check-only", action="store_true", default=False, help="Perform check-only validation without modifying target tree")
    parser.add_argument("--write-back", action="store_true", default=False, help="Commit and push verified promoted changes to git origin/main")
    parser.add_argument("--no-verify-raw", action="store_true", default=False, help="Skip raw.githubusercontent.com network verification (for offline tests)")
    parser.add_argument("--deliver-candidates", action="store_true", default=False, help="Atomically deliver multiple validated candidates")
    parser.add_argument("--candidate-target", action="append", default=[], help="Target candidate in format patch_id:candidate_file_path")

    args = parser.parse_args(argv)

    try:
        if args.deliver_candidates:
            if not args.candidate_target:
                raise ValueError("--deliver-candidates requires at least one --candidate-target <patch_id>:<file_path>")
            targets = {}
            for item in args.candidate_target:
                if ":" not in item:
                    raise ValueError(f"Invalid --candidate-target format (expected patch_id:path): {item}")
                pid, path_str = item.split(":", 1)
                targets[pid.strip()] = Path(path_str.strip()).resolve()

            promoted, pushed, commit_sha, candidate_shas = deliver_multi_candidates(
                targets,
                repo_root=args.repo_root,
                write_back=args.write_back,
                verify_raw_url=not args.no_verify_raw,
            )
            status_str = "DELIVERED" if pushed else ("PROMOTED" if promoted else "NO_OP (up to date)")
            print(f"✅ Multi-candidate delivery SUCCESS [{status_str}]:")
            for pid, csha in candidate_shas.items():
                print(f"  - {pid}: {csha}")
            if commit_sha:
                print(f"  - Commit: {commit_sha}")
                print(f"  - Pushed: {pushed}")
            return 0

        if not args.patch_id or not args.upstream_input:
            parser.error("--patch-id and --upstream-input are required when not using --deliver-candidates")

        promote = args.promote or args.write_back
        res = run_pipeline(
            args.patch_id,
            args.upstream_input,
            target_tree=args.target_tree,
            candidate_dir=args.candidate_dir,
            repo_root=args.repo_root,
            promote=promote,
            check_only=args.check_only,
            write_back=args.write_back,
            verify_raw_url=not args.no_verify_raw,
        )
        status_str = (
            "DELIVERED"
            if res.pushed
            else ("COMMITTED" if res.committed else ("PROMOTED" if res.promoted else ("NO_OP (up to date)" if res.is_noop else (res.publication_state if promote else "CANDIDATE_READY"))))
        )
        print(f"✅ Pipeline SUCCESS for {res.patch_id} [{status_str}]:")
        print(f"  - Candidate:  {res.candidate_path}")
        print(f"  - Public:     {res.public_path}")
        print(f"  - SHA-256:    {res.candidate_sha256}")
        if res.committed:
            print(f"  - Commit:     {res.commit_sha}")
            print(f"  - Pushed:     {res.pushed}")
        return 0
    except Exception as exc:
        print(f"❌ Pipeline FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
