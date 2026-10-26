"""Authoritative upstream change detection, anchor/semantic verification, and classification."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from typing import Any, Mapping, Optional, Sequence, Tuple
import urllib.request

from ..adapters import get_adapter
from ..adapters.base import AnchorConflict, MissingSemanticAnchor, MultipleSemanticAnchors
from ..adapters.xxksu import (
    PATCH11_CANONICAL_FILES,
    XxksuAdapter,
    generate_patch11,
    get_patch11_operation_specs,
)
from ..policy.model import PolicyIncomplete
from ..policy.patch11 import classify_patch11
from ..policy.patch51 import classify_patch51
from ..semantic import SemanticInventory, SemanticKind, inventory_patch
from ..semantic.gate import evaluate_semantic_gate
from ..source.bundle import SourceBundle, create_source_bundle
from ..source.patch_apply import SourceBundlePatchError, apply_patch_to_bundle
from ..validation.exact_patch import substantive_patch_text
from .model import SourceResult, WatchClassification, WatchReport

logger = logging.getLogger(__name__)


def compute_composite_hash(file_hashes: Mapping[str, str]) -> str:
    """Compute deterministic SHA-256 hash of sorted {path: sha256} mapping."""
    canonical = json.dumps(dict(sorted(file_hashes.items())), sort_keys=True)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def fetch_remote_commit(repo_url: str, ref: str, retries: int = 3) -> str:
    """Fetch latest remote commit SHA for a git repository and ref."""
    last_exc = None
    candidates = []
    if ref:
        candidates.extend([f"refs/heads/{ref}", f"refs/tags/{ref}", ref])
    for attempt in range(retries):
        try:
            # Use protocol.version=0 to avoid GitLab/Gitaly protocol v2 overload errors
            proc = subprocess.run(
                ["git", "-c", "protocol.version=0", "ls-remote", repo_url] + candidates,
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            lines = [line.strip() for line in proc.stdout.strip().splitlines() if line.strip()]
            for line in lines:
                parts = line.split()
                if len(parts) >= 2:
                    commit = parts[0]
                    target_ref = parts[1]
                    if target_ref in (f"refs/heads/{ref}", f"refs/tags/{ref}", ref):
                        return commit

            # If ref is main/master/HEAD or empty, fallback to querying HEAD
            if ref in ("main", "master", "HEAD", ""):
                proc_head = subprocess.run(
                    ["git", "-c", "protocol.version=0", "ls-remote", repo_url, "HEAD"],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=30,
                )
                head_lines = [l.strip() for l in proc_head.stdout.strip().splitlines() if l.strip()]
                if head_lines:
                    return head_lines[0].split()[0]

            raise ValueError(f"no remote commit found for {repo_url} @ {ref}")
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"failed to fetch remote commit from {repo_url} @ {ref}: {last_exc}") from last_exc


def fetch_git_files(
    repo_url: str,
    commit: str,
    file_paths: Sequence[str],
    retries: int = 3,
) -> dict[str, str]:
    """Fetch specific file contents from git repository at given commit."""
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["git", "init", td], check=True, capture_output=True)
        subprocess.run(["git", "-C", td, "remote", "add", "origin", repo_url], check=True, capture_output=True)
        for attempt in range(retries):
            try:
                subprocess.run(["git", "-C", td, "fetch", "--depth=1", "origin", commit], check=True, capture_output=True, timeout=60)
                break
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                if attempt == retries - 1:
                    raise
                time.sleep(2 ** attempt)

        results: dict[str, str] = {}
        missing_files: list[str] = []
        for p in file_paths:
            proc = subprocess.run(["git", "-C", td, "show", f"FETCH_HEAD:{p}"], capture_output=True)
            if proc.returncode == 0:
                results[p] = proc.stdout.decode("utf-8", errors="replace")
            else:
                missing_files.append(p)
                logger.warning("File %s not found in %s @ %s", p, repo_url, commit)
        if missing_files:
            raise FileNotFoundError(f"Missing required tracked files at {commit}: {', '.join(missing_files)}")
        return results


def fetch_git_checkout(repo_url: str, commit: str, dest: Path) -> Path:
    """Shallow detached checkout of one exact commit."""
    from ..clean_room import fetch_git
    return fetch_git({"repository": repo_url, "commit": commit}, dest)


def fetch_url_content(url: str, timeout: int = 30) -> tuple[str, str]:
    """Fetch text content from URL and return (content, sha256_hash)."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "xxksu-susfs-upstream-watch/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
        text = data.decode("utf-8", errors="replace")
        sha = hashlib.sha256(data).hexdigest()
        return text, f"sha256:{sha}"


def normalize_reference_patch(text: str) -> str:
    """Normalize reference patch by stripping commit metadata headers, footers, and index hashes."""
    return substantive_patch_text(text)


def compute_normalized_patch_hash(text: str) -> str:
    """Compute sha256: hash of normalized reference patch content."""
    normalized = normalize_reference_patch(text)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


class UpstreamWatcher:
    """Evaluates tracked authoritative and reference upstream sources."""

    def __init__(self, repo_root: Path, state_path: Path):
        self.repo_root = repo_root
        self.state_path = state_path

    def load_state(self) -> dict[str, Any]:
        if not self.state_path.is_file():
            raise FileNotFoundError(f"State file not found: {self.state_path}")
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def check_backslashxx_kernelsu(
        self,
        info: Mapping[str, Any],
        fetch_remote: bool = True,
    ) -> SourceResult:
        source_id = "backslashxx_kernelsu"
        repro_cmd = f"PYTHONPATH=.github/scripts python3 -m v2.watch.cli --source {source_id}"
        old_commit = info.get("commit", "")
        old_hash = info.get("relevant_content_hash", "")
        tracked_files = info.get("tracked_files", {})
        repo_url = info.get("repository", "https://github.com/backslashxx/KernelSU.git")
        ref = info.get("ref", "master")

        if not fetch_remote:
            return SourceResult(
                source_id=source_id,
                source_type="authoritative",
                classification=WatchClassification.NO_CHANGE,
                old_identity=old_commit,
                new_identity=old_commit,
                old_content_hash=old_hash,
                new_content_hash=old_hash,
                details="Dry run: remote fetch skipped.",
                reproduction_command=repro_cmd,
            )

        try:
            new_commit = fetch_remote_commit(repo_url, ref)
        except Exception as exc:
            return SourceResult(
                source_id=source_id,
                source_type="authoritative",
                classification=WatchClassification.SOURCE_IDENTITY_ERROR,
                old_identity=old_commit,
                new_identity="UNKNOWN",
                old_content_hash=old_hash,
                new_content_hash="UNKNOWN",
                details=f"Failed to query remote commit: {exc}",
                reproduction_command=repro_cmd,
            )

        if new_commit == old_commit:
            return SourceResult(
                source_id=source_id,
                source_type="authoritative",
                classification=WatchClassification.NO_CHANGE,
                old_identity=old_commit,
                new_identity=new_commit,
                old_content_hash=old_hash,
                new_content_hash=old_hash,
                details=f"Upstream commit unchanged ({new_commit[:12]}).",
                reproduction_command=repro_cmd,
            )

        # Commit has changed. Fetch tracked files at new commit.
        try:
            fetched_contents = fetch_git_files(repo_url, new_commit, list(tracked_files.keys()))
        except Exception as exc:
            return SourceResult(
                source_id=source_id,
                source_type="authoritative",
                classification=WatchClassification.SOURCE_IDENTITY_ERROR,
                old_identity=old_commit,
                new_identity=new_commit,
                old_content_hash=old_hash,
                new_content_hash="UNKNOWN",
                details=f"Failed to fetch upstream files at {new_commit}: {exc}",
                reproduction_command=repro_cmd,
            )

        new_file_hashes: dict[str, str] = {}
        affected_files: list[str] = []
        for path, content in fetched_contents.items():
            file_sha = f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"
            new_file_hashes[path] = file_sha
            if path in tracked_files and file_sha != tracked_files[path]:
                affected_files.append(path)

        new_hash = compute_composite_hash(new_file_hashes)

        # Check if any relevant files changed
        if not affected_files and new_hash == old_hash:
            return SourceResult(
                source_id=source_id,
                source_type="authoritative",
                classification=WatchClassification.IRRELEVANT_CHANGE,
                old_identity=old_commit,
                new_identity=new_commit,
                old_content_hash=old_hash,
                new_content_hash=new_hash,
                details=f"Upstream commit advanced to {new_commit[:12]}, but all {len(tracked_files)} tracked source/dependency files are byte-for-byte identical (not a whole-tree comparison).",
                reproduction_command=repro_cmd,
            )

        # Relevant files changed! Evaluate anchors and semantics via authoritative shared gate.
        gate_res = evaluate_semantic_gate(
            "xxksu",
            upstream_contents=fetched_contents,
            repo_root=self.repo_root,
            source_identity=new_commit,
            baseline_identity=old_commit,
        )
        if not gate_res.passed:
            return SourceResult(
                source_id=source_id,
                source_type="authoritative",
                classification=gate_res.classification,
                old_identity=old_commit,
                new_identity=new_commit,
                old_content_hash=old_hash,
                new_content_hash=new_hash,
                affected_files=tuple(affected_files),
                affected_semantics=gate_res.affected_semantics,
                details=gate_res.details,
                reproduction_command=repro_cmd,
            )

        # Anchors hold! Try candidate Patch 11 generation and strict application.
        try:
            # Create a source bundle from the fetched files
            temp_bundle = create_source_bundle("xxksu", "main", fetched_contents)
            candidate_patch = generate_patch11(temp_bundle)

            # Strictly apply to verify 0 rejects, 0 fuzz
            apply_patch_to_bundle(temp_bundle, candidate_patch)

            return SourceResult(
                source_id=source_id,
                source_type="authoritative",
                classification=WatchClassification.SAFE_REGEN_CANDIDATE,
                old_identity=old_commit,
                new_identity=new_commit,
                old_content_hash=old_hash,
                new_content_hash=new_hash,
                affected_files=tuple(affected_files),
                details=(f"Source change detected across {len(affected_files)} tracked files. "
                         "Candidate Patch 11 generated and verified with exact application; "
                         "this is not approval of dependency semantics. "
                         + ("Dependency source review required: " + ", ".join(
                             p for p in affected_files if p not in PATCH11_CANONICAL_FILES)
                            if any(p not in PATCH11_CANONICAL_FILES for p in affected_files) else "")),
                candidate_patch=candidate_patch,
                candidate_patch_name="11_enable_susfs_for_ksu.patch",
                reproduction_command=repro_cmd,
            )
        except Exception as exc:
            return SourceResult(
                source_id=source_id,
                source_type="authoritative",
                classification=WatchClassification.SEMANTIC_DRIFT,
                old_identity=old_commit,
                new_identity=new_commit,
                old_content_hash=old_hash,
                new_content_hash=new_hash,
                affected_files=tuple(affected_files),
                details=f"Candidate patch generation/application failed: {exc}",
                reproduction_command=repro_cmd,
            )

    def check_susfs_authoritative(
        self,
        source_id: str,
        target_id: str,
        info: Mapping[str, Any],
        fetch_remote: bool = True,
    ) -> SourceResult:
        repro_cmd = f"PYTHONPATH=.github/scripts python3 -m v2.watch.cli --source {source_id}"
        old_commit = info.get("commit", "")
        old_hash = info.get("relevant_content_hash", "")
        tracked_files = info.get("tracked_files", {})
        repo_url = info.get("repository", "https://gitlab.com/simonpunk/susfs4ksu.git")
        ref = info.get("ref", "")

        if not fetch_remote:
            return SourceResult(
                source_id=source_id,
                source_type="authoritative",
                classification=WatchClassification.NO_CHANGE,
                old_identity=old_commit,
                new_identity=old_commit,
                old_content_hash=old_hash,
                new_content_hash=old_hash,
                details="Dry run: remote fetch skipped.",
                reproduction_command=repro_cmd,
            )

        try:
            new_commit = fetch_remote_commit(repo_url, ref)
        except Exception as exc:
            return SourceResult(
                source_id=source_id,
                source_type="authoritative",
                classification=WatchClassification.SOURCE_IDENTITY_ERROR,
                old_identity=old_commit,
                new_identity="UNKNOWN",
                old_content_hash=old_hash,
                new_content_hash="UNKNOWN",
                details=f"Failed to query remote commit for {ref}: {exc}",
                reproduction_command=repro_cmd,
            )

        if new_commit == old_commit:
            return SourceResult(
                source_id=source_id,
                source_type="authoritative",
                classification=WatchClassification.NO_CHANGE,
                old_identity=old_commit,
                new_identity=new_commit,
                old_content_hash=old_hash,
                new_content_hash=old_hash,
                details=f"Upstream SuSFS commit unchanged ({new_commit[:12]}).",
                reproduction_command=repro_cmd,
            )

        # Commit changed, fetch tracked files
        try:
            fetched_contents = fetch_git_files(repo_url, new_commit, list(tracked_files.keys()))
        except Exception as exc:
            return SourceResult(
                source_id=source_id,
                source_type="authoritative",
                classification=WatchClassification.SOURCE_IDENTITY_ERROR,
                old_identity=old_commit,
                new_identity=new_commit,
                old_content_hash=old_hash,
                new_content_hash="UNKNOWN",
                details=f"Failed to fetch SuSFS files at {new_commit}: {exc}",
                reproduction_command=repro_cmd,
            )

        new_file_hashes: dict[str, str] = {}
        affected_files: list[str] = []
        for path, content in fetched_contents.items():
            file_sha = f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"
            new_file_hashes[path] = file_sha
            if path in tracked_files and file_sha != tracked_files[path]:
                affected_files.append(path)

        new_hash = compute_composite_hash(new_file_hashes)

        if not affected_files and new_hash == old_hash:
            return SourceResult(
                source_id=source_id,
                source_type="authoritative",
                classification=WatchClassification.IRRELEVANT_CHANGE,
                old_identity=old_commit,
                new_identity=new_commit,
                old_content_hash=old_hash,
                new_content_hash=new_hash,
                details=f"Upstream SuSFS commit advanced to {new_commit[:12]}, but all {len(tracked_files)} tracked files are identical.",
                reproduction_command=repro_cmd,
            )

        # Locate candidate Patch 51 filename from target baseline
        baseline_path = self.repo_root / "patches" / target_id / "BASELINE.json"
        patch_file = (
            "51_deinlined_susfs_hooks_sultan-android14-6.1.patch"
            if "sultan" in target_id
            else "51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch"
        )
        if baseline_path.is_file():
            try:
                base_data = json.loads(baseline_path.read_text(encoding="utf-8"))
                pf = base_data.get("patch_51", {}).get("patch_file")
                if pf:
                    patch_file = Path(pf).name
            except Exception:
                pass

        # Locate upstream 50 patch in fetched contents
        patch50_file = None
        for p in fetched_contents:
            if ("50_add_susfs" in p or "50_" in p) and p.endswith(".patch"):
                patch50_file = p
                break

        if not patch50_file:
            return SourceResult(
                source_id=source_id,
                source_type="authoritative",
                classification=WatchClassification.SEMANTIC_DRIFT,
                old_identity=old_commit,
                new_identity=new_commit,
                old_content_hash=old_hash,
                new_content_hash=new_hash,
                affected_files=tuple(affected_files),
                details=f"No upstream 50 patch found in fetched contents for {target_id}.",
                reproduction_command=repro_cmd,
            )

        # Fetch baseline files from old commit if available
        old_contents: dict[str, str] = {}
        patch10_file = "kernel_patches/KernelSU/10_enable_susfs_for_ksu.patch"
        fetch_keys = [k for k in (patch50_file, patch10_file) if k]
        try:
            old_contents = fetch_git_files(repo_url, old_commit, fetch_keys)
        except Exception as exc:
            logger.warning("Failed to fetch baseline files for semantic comparison: %s", exc)

        # Authoritative shared semantic gate: evaluate anchors, Patch 50, and Patch 10
        gate_res = evaluate_semantic_gate(
            target_id,
            upstream_contents=fetched_contents,
            baseline_contents=old_contents,
            repo_root=self.repo_root,
            source_identity=new_commit,
            baseline_identity=old_commit,
        )
        if not gate_res.passed:
            return SourceResult(
                source_id=source_id,
                source_type="authoritative",
                classification=gate_res.classification,
                old_identity=old_commit,
                new_identity=new_commit,
                old_content_hash=old_hash,
                new_content_hash=new_hash,
                affected_files=tuple(affected_files),
                affected_semantics=gate_res.affected_semantics,
                details=gate_res.details,
                reproduction_command=repro_cmd,
            )

        # Production generator on the discovered checkout: exact reviewed preimages,
        # fail-closed ownership, authenticated commit Date.
        try:
            from ..policy.patch51_source import generate
            patch_id = ("sultan-android14-6.1-patch51" if "sultan" in target_id
                        else "gki-android16-6.12-r38-patch51")
            with tempfile.TemporaryDirectory(prefix="susfs-watch-") as td:
                checkout = fetch_git_checkout(repo_url, new_commit, Path(td) / "susfs")
                candidate_patch_text = generate(patch_id, checkout, self.repo_root, advance=True)[0]
        except Exception as exc:
            return SourceResult(
                source_id=source_id,
                source_type="authoritative",
                classification=WatchClassification.SEMANTIC_DRIFT,
                old_identity=old_commit,
                new_identity=new_commit,
                old_content_hash=old_hash,
                new_content_hash=new_hash,
                affected_files=tuple(affected_files),
                details=f"Candidate Patch 51 generation failed on {target_id}: {exc}",
                reproduction_command=repro_cmd,
            )

        return SourceResult(
            source_id=source_id,
            source_type="authoritative",
            classification=WatchClassification.SAFE_REGEN_CANDIDATE,
            old_identity=old_commit,
            new_identity=new_commit,
            old_content_hash=old_hash,
            new_content_hash=new_hash,
            affected_files=tuple(affected_files),
            details=" ".join((f"Safe upstream SuSFS update detected on {target_id}. Candidate Patch 51 generated and verified with 0 rejects, 0 fuzz.",
                              *gate_res.advisories)),
            candidate_patch=candidate_patch_text,
            candidate_patch_name=patch_file,
            reproduction_command=repro_cmd,
        )

    def check_reference_source(
        self,
        source_id: str,
        info: Mapping[str, Any],
        fetch_remote: bool = True,
    ) -> SourceResult:
        repro_cmd = f"PYTHONPATH=.github/scripts python3 -m v2.watch.cli --source {source_id}"
        old_hash = info.get("sha256", "")
        old_norm_hash = info.get("normalized_sha256", "")
        old_identity = info.get("commit_or_ref", old_hash[:16])
        url = info.get("url", "")

        if not fetch_remote:
            return SourceResult(
                source_id=source_id,
                source_type="reference",
                classification=WatchClassification.NO_CHANGE,
                old_identity=old_identity,
                new_identity=old_identity,
                old_content_hash=old_hash,
                new_content_hash=old_hash,
                details="Dry run: remote fetch skipped.",
                reproduction_command=repro_cmd,
            )

        try:
            text, new_hash = fetch_url_content(url)
        except Exception as exc:
            return SourceResult(
                source_id=source_id,
                source_type="reference",
                classification=WatchClassification.SOURCE_IDENTITY_ERROR,
                old_identity=old_identity,
                new_identity="UNKNOWN",
                old_content_hash=old_hash,
                new_content_hash="UNKNOWN",
                details=f"Failed to fetch reference URL {url}: {exc}",
                reproduction_command=repro_cmd,
            )

        new_norm_hash = compute_normalized_patch_hash(text)
        commit_match = re.search(r"^From\s+([0-9a-f]{40})\b", text, re.MULTILINE)
        new_identity = commit_match.group(1) if commit_match else new_hash[:16]

        if new_hash == old_hash:
            return SourceResult(
                source_id=source_id,
                source_type="reference",
                classification=WatchClassification.NO_CHANGE,
                old_identity=old_identity,
                new_identity=old_identity,
                old_content_hash=old_hash,
                new_content_hash=new_hash,
                details=f"Reference content unchanged ({new_hash[:16]}).",
                reproduction_command=repro_cmd,
            )

        target_norm_hash = old_norm_hash or old_hash
        if new_norm_hash == target_norm_hash:
            return SourceResult(
                source_id=source_id,
                source_type="reference",
                classification=WatchClassification.NO_CHANGE,
                old_identity=old_identity,
                new_identity=new_identity,
                old_content_hash=old_hash,
                new_content_hash=new_hash,
                details=(
                    f"Reference commit identity changed ({old_identity[:12]} -> {new_identity[:12]}), "
                    f"but normalized patch content is unchanged ({new_norm_hash[:16]})."
                ),
                reproduction_command=repro_cmd,
            )

        # Reference patch content changed!
        return SourceResult(
            source_id=source_id,
            source_type="reference",
            classification=WatchClassification.REFERENCE_DRIFT,
            old_identity=old_identity,
            new_identity=new_identity,
            old_content_hash=old_hash,
            new_content_hash=new_hash,
            details=f"Reference patch content changed (new sha256: {new_hash[:16]}, normalized: {new_norm_hash[:16]}). Reference only; never modifies production patches.",
            reproduction_command=repro_cmd,
        )

    def run_all(self, fetch_remote: bool = True, source_filter: Optional[str] = None) -> WatchReport:
        import datetime
        state = self.load_state()
        sources = state.get("sources", {})
        auth_sources = sources.get("authoritative", {})
        ref_sources = sources.get("reference", {})

        results: list[SourceResult] = []

        # 1. backslashxx_kernelsu
        if "backslashxx_kernelsu" in auth_sources and (not source_filter or source_filter == "backslashxx_kernelsu"):
            results.append(self.check_backslashxx_kernelsu(auth_sources["backslashxx_kernelsu"], fetch_remote=fetch_remote))

        # 2. susfs_sultan
        if "susfs_sultan" in auth_sources and (not source_filter or source_filter == "susfs_sultan"):
            results.append(self.check_susfs_authoritative("susfs_sultan", "sultan-android14-6.1", auth_sources["susfs_sultan"], fetch_remote=fetch_remote))

        # 3. susfs_gki
        if "susfs_gki" in auth_sources and (not source_filter or source_filter == "susfs_gki"):
            results.append(self.check_susfs_authoritative("susfs_gki", "gki-android16-6.12", auth_sources["susfs_gki"], fetch_remote=fetch_remote))

        # 4 & 5. Reference sources
        for ref_id, ref_info in ref_sources.items():
            if not source_filter or source_filter == ref_id:
                results.append(self.check_reference_source(ref_id, ref_info, fetch_remote=fetch_remote))

        return WatchReport(
            results=tuple(results),
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )


__all__ = [
    "compute_composite_hash",
    "compute_normalized_patch_hash",
    "fetch_remote_commit",
    "fetch_git_files",
    "fetch_url_content",
    "normalize_reference_patch",
    "UpstreamWatcher",
]
