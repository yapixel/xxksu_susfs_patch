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
from ..engine.diff_parser import parse_patch
from ..policy.model import PolicyIncomplete
from ..policy.patch11 import classify_patch11
from ..policy.patch51 import classify_patch51
from ..semantic import SemanticInventory, SemanticKind, inventory_patch
from ..source.baseline import load_authoritative_bundle
from ..source.bundle import SourceBundle, create_source_bundle
from ..source.patch_apply import SourceBundlePatchError, apply_patch_to_bundle
from ..validation.exact_patch import validate_patch_syntax
from .model import SourceResult, WatchClassification, WatchReport

try:
    from deinline_50_to_51 import deinline_patch_content
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from deinline_50_to_51 import deinline_patch_content

logger = logging.getLogger(__name__)


def compute_composite_hash(file_hashes: Mapping[str, str]) -> str:
    """Compute deterministic SHA-256 hash of sorted {path: sha256} mapping."""
    canonical = json.dumps(dict(sorted(file_hashes.items())), sort_keys=True)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def fetch_remote_commit(repo_url: str, ref: str) -> str:
    """Fetch latest remote commit SHA for a git repository and ref."""
    try:
        candidates = []
        if ref:
            candidates.extend([f"refs/heads/{ref}", f"refs/tags/{ref}", ref])
        proc = subprocess.run(
            ["git", "ls-remote", repo_url] + candidates,
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
                ["git", "ls-remote", repo_url, "HEAD"],
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
        raise RuntimeError(f"failed to fetch remote commit from {repo_url} @ {ref}: {exc}") from exc


def fetch_git_files(
    repo_url: str,
    commit: str,
    file_paths: Sequence[str],
) -> dict[str, str]:
    """Fetch specific file contents from git repository at given commit."""
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["git", "init", td], check=True, capture_output=True)
        subprocess.run(["git", "-C", td, "remote", "add", "origin", repo_url], check=True, capture_output=True)
        subprocess.run(["git", "-C", td, "fetch", "--depth=1", "origin", commit], check=True, capture_output=True, timeout=60)

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
    diff_idx = text.find("\ndiff --git ")
    if diff_idx != -1:
        diff_text = text[diff_idx + 1:]
    elif text.startswith("diff --git "):
        diff_text = text
    else:
        diff_idx = text.find("\n--- ")
        if diff_idx != -1:
            diff_text = text[diff_idx + 1:]
        elif text.startswith("--- "):
            diff_text = text
        else:
            diff_text = text

    lines = diff_text.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    if len(lines) >= 2 and lines[-2].strip() == "--":
        lines = lines[:-2]

    filtered = [
        l for l in lines
        if not (l.startswith("index ") and re.match(r"^index [0-9a-f]+\.\.[0-9a-f]+", l))
    ]
    return "\n".join(filtered).strip()


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
                details=f"Upstream commit advanced to {new_commit[:12]}, but all {len(tracked_files)} relevant kernel files are byte-for-byte identical.",
                reproduction_command=repro_cmd,
            )

        # Relevant files changed! Evaluate anchors and semantics.
        adapter = XxksuAdapter()
        drifted_anchors: list[str] = []
        for op in get_patch11_operation_specs():
            if op.file_path in fetched_contents:
                src = fetched_contents[op.file_path]
                try:
                    adapter.locate_anchor(src, op.spec, file_path=op.file_path, function=op.function)
                except (MissingSemanticAnchor, MultipleSemanticAnchors, AnchorConflict) as exc:
                    drifted_anchors.append(f"{op.operation_id} ({op.file_path}): {exc}")

        if drifted_anchors:
            return SourceResult(
                source_id=source_id,
                source_type="authoritative",
                classification=WatchClassification.ANCHOR_DRIFT,
                old_identity=old_commit,
                new_identity=new_commit,
                old_content_hash=old_hash,
                new_content_hash=new_hash,
                affected_files=tuple(affected_files),
                affected_semantics=tuple(drifted_anchors),
                details=f"Semantic anchor drift in {len(drifted_anchors)} operations:\n" + "\n".join(drifted_anchors),
                reproduction_command=repro_cmd,
            )

        # Anchors hold! Try candidate Patch 11 generation and strict application.
        try:
            # Create a source bundle from the fetched files
            entries = []
            for p, content in fetched_contents.items():
                entries.append({"path": p, "content": content})
            temp_bundle = create_source_bundle("xxksu", "main", entries)
            candidate_patch = adapter.generate_patch11(temp_bundle)

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
                details=f"Safe upstream change detected across {len(affected_files)} files. Candidate Patch 11 generated and verified with 0 rejects, 0 fuzz.",
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

        # Authoritative SuSFS files changed! Verify against target adapter anchors
        adapter = get_adapter(target_id)
        bundle = load_authoritative_bundle(target_id, self.repo_root)

        drifted_anchors: list[str] = []
        if bundle is not None:
            for entry in bundle.files:
                if entry.content is None:
                    continue
                # Verify standard anchors
                for anchor_key in ("exec_hook", "access_hook", "stat_hook", "reboot_hook"):
                    try:
                        spec = adapter.get_anchor_spec(anchor_key)
                        if spec.file_path == entry.path:
                            adapter.locate_anchor(entry.content, spec, file_path=entry.path, function=spec.function)
                    except (MissingSemanticAnchor, MultipleSemanticAnchors, AnchorConflict) as exc:
                        drifted_anchors.append(f"{anchor_key} ({entry.path}): {exc}")

        if drifted_anchors:
            return SourceResult(
                source_id=source_id,
                source_type="authoritative",
                classification=WatchClassification.ANCHOR_DRIFT,
                old_identity=old_commit,
                new_identity=new_commit,
                old_content_hash=old_hash,
                new_content_hash=new_hash,
                affected_files=tuple(affected_files),
                affected_semantics=tuple(drifted_anchors),
                details=f"Anchor drift on {target_id}:\n" + "\n".join(drifted_anchors),
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

        # 1. Regenerate candidate Patch 51 from the NEW immutable upstream input
        try:
            candidate_patch_text = deinline_patch_content(fetched_contents[patch50_file], target=target_id)
            syntax_errors = validate_patch_syntax(candidate_patch_text)
            if syntax_errors:
                raise ValueError("Syntax errors in candidate patch: " + "; ".join(syntax_errors))
            parsed_candidate = parse_patch(candidate_patch_text)
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

        # 2. Check for missing newly-required source files in authoritative bundle (e.g. Sultan fs/super.c)
        if bundle is not None:
            bundle_files = {entry.path for entry in bundle.files}
            candidate_files = {
                f.new_path[2:] if (f.new_path and f.new_path.startswith(("a/", "b/"))) else (f.new_path or f.old_path or "")
                for f in parsed_candidate.files
            }
            candidate_files.discard("")
            missing_files = sorted(candidate_files - bundle_files)
            if missing_files:
                return SourceResult(
                    source_id=source_id,
                    source_type="authoritative",
                    classification=WatchClassification.SEMANTIC_DRIFT,
                    old_identity=old_commit,
                    new_identity=new_commit,
                    old_content_hash=old_hash,
                    new_content_hash=new_hash,
                    affected_files=tuple(affected_files),
                    affected_semantics=tuple(f"unbundled_file:{f}" for f in missing_files),
                    details=(
                        f"Upstream SuSFS update requires unbundled kernel files on {target_id}: "
                        f"{', '.join(missing_files)}. Baseline expansion required."
                    ),
                    reproduction_command=repro_cmd,
                )

        # 3. Strict application of candidate patch against authoritative target source
        if bundle is not None:
            try:
                apply_patch_to_bundle(bundle, candidate_patch_text)
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
                    details=f"Candidate Patch 51 failed strict application on {target_id}: {exc}",
                    reproduction_command=repro_cmd,
                )

        # 4. Semantic inventory verification: SAFE_REGEN_CANDIDATE requires zero UNKNOWN semantic changes
        new_unknowns: list[Any] = []
        try:
            old_contents = fetch_git_files(repo_url, old_commit, [patch50_file])
            if patch50_file in old_contents:
                inv_old = inventory_patch(
                    parse_patch(old_contents[patch50_file]),
                    source_identity=old_commit,
                    source_type="official_50",
                )
                inv_new = inventory_patch(
                    parse_patch(fetched_contents[patch50_file]),
                    source_identity=new_commit,
                    source_type="official_50",
                )
                old_digests = {u.evidence[0].fingerprint.digest.value for u in inv_old.units}
                new_unknowns = [
                    u for u in inv_new.units
                    if u.kind == SemanticKind.UNKNOWN and u.evidence[0].fingerprint.digest.value not in old_digests
                ]
        except Exception as exc:
            logger.warning("Failed semantic inventory comparison for %s: %s", source_id, exc)
            return SourceResult(
                source_id=source_id,
                source_type="authoritative",
                classification=WatchClassification.SEMANTIC_DRIFT,
                old_identity=old_commit,
                new_identity=new_commit,
                old_content_hash=old_hash,
                new_content_hash=new_hash,
                affected_files=tuple(affected_files),
                details=f"Semantic inventory verification failed for {source_id}: {exc}",
                reproduction_command=repro_cmd,
            )

        if new_unknowns:
            affected_paths = sorted(set(u.location.path for u in new_unknowns))
            return SourceResult(
                source_id=source_id,
                source_type="authoritative",
                classification=WatchClassification.SEMANTIC_DRIFT,
                old_identity=old_commit,
                new_identity=new_commit,
                old_content_hash=old_hash,
                new_content_hash=new_hash,
                affected_files=tuple(affected_files),
                affected_semantics=tuple(f"unknown:{u.location.path}:{u.location.start_line}" for u in new_unknowns[:20]),
                details=(
                    f"Upstream SuSFS update introduces {len(new_unknowns)} new UNKNOWN semantic units across "
                    f"{len(affected_paths)} files ({', '.join(affected_paths[:5])}). Semantic reconciliation required."
                ),
                reproduction_command=repro_cmd,
            )

        # 5. Check Patch 10 if tracked and changed
        patch10_file = "kernel_patches/KernelSU/10_enable_susfs_for_ksu.patch"
        if patch10_file in affected_files and patch10_file in fetched_contents:
            try:
                old_10 = fetch_git_files(repo_url, old_commit, [patch10_file])
                if patch10_file in old_10:
                    inv_10_old = inventory_patch(
                        parse_patch(old_10[patch10_file]),
                        source_identity=old_commit,
                        source_type="official_10",
                    )
                    inv_10_new = inventory_patch(
                        parse_patch(fetched_contents[patch10_file]),
                        source_identity=new_commit,
                        source_type="official_10",
                    )
                    old_10_digests = {u.evidence[0].fingerprint.digest.value for u in inv_10_old.units}
                    new_unknowns_10 = [
                        u for u in inv_10_new.units
                        if u.kind == SemanticKind.UNKNOWN and u.evidence[0].fingerprint.digest.value not in old_10_digests
                    ]
                    if new_unknowns_10:
                        affected_paths = sorted(set(u.location.path for u in new_unknowns_10))
                        return SourceResult(
                            source_id=source_id,
                            source_type="authoritative",
                            classification=WatchClassification.SEMANTIC_DRIFT,
                            old_identity=old_commit,
                            new_identity=new_commit,
                            old_content_hash=old_hash,
                            new_content_hash=new_hash,
                            affected_files=tuple(affected_files),
                            affected_semantics=tuple(f"unknown:{u.location.path}:{u.location.start_line}" for u in new_unknowns_10[:20]),
                            details=(
                                f"Upstream SuSFS Patch 10 update introduces {len(new_unknowns_10)} new UNKNOWN semantic units across "
                                f"{len(affected_paths)} files ({', '.join(affected_paths[:5])}). Semantic reconciliation required."
                            ),
                            reproduction_command=repro_cmd,
                        )
            except Exception as exc:
                logger.warning("Failed Patch 10 semantic inventory comparison for %s: %s", source_id, exc)

        return SourceResult(
            source_id=source_id,
            source_type="authoritative",
            classification=WatchClassification.SAFE_REGEN_CANDIDATE,
            old_identity=old_commit,
            new_identity=new_commit,
            old_content_hash=old_hash,
            new_content_hash=new_hash,
            affected_files=tuple(affected_files),
            details=f"Safe upstream SuSFS update detected on {target_id}. Candidate Patch 51 generated and verified with 0 rejects, 0 fuzz.",
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
