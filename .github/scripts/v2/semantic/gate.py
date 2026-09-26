"""Authoritative shared semantic gate for upstream watcher and promotion pipeline.

Enforces the core semantic contract:
authoritative upstream input
→ semantic inventory / policy validation
→ no UNKNOWN or unapproved semantic drift
→ deterministic generation
→ exact target validation
→ promotion

If semantic approval fails:
- pipeline fails closed
- public patches/ remains byte-identical
- BASELINE/state/manifest remain unchanged
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Optional, Sequence, Tuple

from ..adapters import get_adapter
from ..adapters.base import AnchorConflict, MissingSemanticAnchor, MultipleSemanticAnchors
from ..adapters.xxksu import PATCH11_CANONICAL_FILES, XxksuAdapter, get_patch11_operation_specs
from ..engine.diff_parser import parse_patch
from ..source.baseline import load_authoritative_bundle
from .inventory import inventory_patch
from .model import SemanticKind, SemanticUnit
from .registry import SemanticRegistry, default_registry

if TYPE_CHECKING:
    from ..watch.model import WatchClassification


@dataclass(frozen=True)
class SemanticGateResult:
    """Outcome of the shared semantic inventory and policy validation gate."""
    passed: bool
    classification: WatchClassification
    details: str
    affected_files: Tuple[str, ...] = ()
    affected_semantics: Tuple[str, ...] = ()
    unknown_units: Tuple[SemanticUnit, ...] = ()
    drifted_anchors: Tuple[str, ...] = ()


def _normalize_target_id(identifier: str) -> str:
    ident = identifier.lower()
    if "xxksu" in ident or "kernelsu" in ident:
        return "xxksu"
    elif "sultan" in ident:
        return "sultan-android14-6.1"
    elif "6.12" in ident or "gki" in ident or "r38" in ident:
        return "gki-android16-6.12"
    return identifier


def _find_patch_key(contents: Mapping[str, str], target_id: str) -> Optional[str]:
    target_cands = []
    if "6.12" in target_id or "r38" in target_id or "gki" in target_id:
        target_cands = (
            "kernel_patches/50_add_susfs_in_gki-android16-6.12.patch",
            "50_add_susfs_in_gki-android16-6.12.patch",
            "kernel_patches/51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch",
            "51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch",
        )
    elif "sultan" in target_id or "6.1" in target_id:
        target_cands = (
            "kernel_patches/50_add_susfs_in_sultan-kernel-6.1.patch",
            "kernel_patches/50_add_susfs_in_gki-android14-6.1.patch",
            "50_add_susfs_in_sultan-kernel-6.1.patch",
            "50_add_susfs_in_gki-android14-6.1.patch",
            "kernel_patches/51_deinlined_susfs_hooks_sultan-android14-6.1.patch",
            "51_deinlined_susfs_hooks_sultan-android14-6.1.patch",
        )
    for c in target_cands:
        if c in contents:
            return c
    for c in (
        "kernel_patches/50_add_susfs_in_gki-android14-6.1.patch",
        "kernel_patches/50_add_susfs_in_gki-android16-6.12.patch",
        "kernel_patches/50_add_susfs_in_sultan-kernel-6.1.patch",
        "50_add_susfs_in_gki-android14-6.1.patch",
        "50_add_susfs_in_gki-android16-6.12.patch",
        "50_add_susfs_in_sultan-kernel-6.1.patch",
    ):
        if c in contents:
            return c
    for k in contents:
        if ("50_add_susfs" in k or "51_deinlined" in k) and k.endswith(".patch"):
            return k
    for k in contents:
        if k.endswith(".patch") and "10_enable_susfs" not in k:
            return k
    return None


def evaluate_semantic_gate(
    target_or_patch_id: str,
    *,
    upstream_contents: Mapping[str, str],
    baseline_contents: Optional[Mapping[str, str]] = None,
    repo_root: Optional[Path] = None,
    registry: Optional[SemanticRegistry] = None,
    source_identity: str = "upstream",
    baseline_identity: str = "baseline",
) -> SemanticGateResult:
    """Evaluate upstream contents against authoritative semantic specifications and anchors.

    Shared by both UpstreamWatcher and v2.pipeline.
    """
    from ..watch.model import WatchClassification

    if repo_root is None:
        repo_root = Path.cwd()
    repo_root = Path(repo_root).resolve()

    if registry is None:
        registry = default_registry()

    target_id = _normalize_target_id(target_or_patch_id)

    # 1. Semantic Evaluation for xxKSU (Patch 11)
    if target_id == "xxksu":
        adapter = XxksuAdapter()
        drifted_anchors: list[str] = []
        for op in get_patch11_operation_specs():
            # Check canonical relative path (e.g. kernel/ksu.c) or stripped path (ksu.c)
            src = upstream_contents.get(op.file_path)
            if src is None and op.file_path.startswith("kernel/"):
                src = upstream_contents.get(op.file_path.removeprefix("kernel/"))
            if src is not None:
                try:
                    adapter.locate_anchor(src, op.spec, file_path=op.file_path, function=op.function)
                except (MissingSemanticAnchor, MultipleSemanticAnchors, AnchorConflict) as exc:
                    drifted_anchors.append(f"{op.operation_id} ({op.file_path}): {exc}")

        if drifted_anchors:
            return SemanticGateResult(
                passed=False,
                classification=WatchClassification.ANCHOR_DRIFT,
                details=f"Semantic anchor drift in {len(drifted_anchors)} operations:\n" + "\n".join(drifted_anchors),
                drifted_anchors=tuple(drifted_anchors),
                affected_semantics=tuple(drifted_anchors),
            )

        # Check Patch 10 if present
        patch10_key = None
        for k in upstream_contents:
            if "10_enable_susfs_for_ksu" in k and k.endswith(".patch"):
                patch10_key = k
                break

        if patch10_key in upstream_contents:
            try:
                inv_10_new = inventory_patch(
                    parse_patch(upstream_contents[patch10_key]),
                    source_identity=source_identity,
                    source_type="official_10",
                    registry=registry,
                )
                old_10_text = baseline_contents.get(patch10_key) if baseline_contents else None
                old_10_digests: set[str] = set()
                if old_10_text:
                    inv_10_old = inventory_patch(
                        parse_patch(old_10_text),
                        source_identity=baseline_identity,
                        source_type="official_10",
                        registry=registry,
                    )
                    old_10_digests = {u.evidence[0].fingerprint.digest.value for u in inv_10_old.units}

                new_unknowns_10 = [
                    u for u in inv_10_new.units
                    if u.kind == SemanticKind.UNKNOWN and u.evidence[0].fingerprint.digest.value not in old_10_digests
                ]
                if new_unknowns_10:
                    affected_paths = sorted(set(u.location.path for u in new_unknowns_10))
                    return SemanticGateResult(
                        passed=False,
                        classification=WatchClassification.SEMANTIC_DRIFT,
                        details=(
                            f"Upstream KernelSU Patch 10 update introduces {len(new_unknowns_10)} new UNKNOWN semantic units "
                            f"across {len(affected_paths)} files ({', '.join(affected_paths[:5])}). Semantic reconciliation required."
                        ),
                        unknown_units=tuple(new_unknowns_10),
                        affected_semantics=tuple(f"unknown:{u.location.path}:{u.location.start_line}" for u in new_unknowns_10[:20]),
                    )
            except Exception as exc:
                return SemanticGateResult(
                    passed=False,
                    classification=WatchClassification.SEMANTIC_DRIFT,
                    details=f"Semantic inventory verification failed for KernelSU Patch 10: {exc}",
                )

        return SemanticGateResult(
            passed=True,
            classification=WatchClassification.SAFE_REGEN_CANDIDATE,
            details="Semantic gate passed: all xxKSU operation anchors verified cleanly.",
        )

    # 2. Semantic Evaluation for SuSFS (Sultan and GKI Patch 51)
    # 2A. Check target adapter anchor hooks if bundle is available
    bundle = load_authoritative_bundle(target_id, repo_root)
    drifted_anchors = []
    if bundle is not None:
        adapter = get_adapter(target_id)
        for entry in bundle.files:
            if entry.content is None:
                continue
            for anchor_key in ("exec_hook", "access_hook", "stat_hook", "reboot_hook"):
                try:
                    spec = adapter.get_anchor_spec(anchor_key)
                    if spec.file_path == entry.path:
                        adapter.locate_anchor(entry.content, spec, file_path=entry.path, function=spec.function)
                except (MissingSemanticAnchor, MultipleSemanticAnchors, AnchorConflict) as exc:
                    drifted_anchors.append(f"{anchor_key} ({entry.path}): {exc}")

    if drifted_anchors:
        return SemanticGateResult(
            passed=False,
            classification=WatchClassification.ANCHOR_DRIFT,
            details=f"Anchor drift on {target_id}:\n" + "\n".join(drifted_anchors),
            drifted_anchors=tuple(drifted_anchors),
            affected_semantics=tuple(drifted_anchors),
        )

    # 2B. Check Patch 50 / Patch 51 Semantic Inventory
    patch_key = _find_patch_key(upstream_contents, target_id)
    if patch_key is None:
        return SemanticGateResult(
            passed=False,
            classification=WatchClassification.SEMANTIC_DRIFT,
            details=f"No patch file found in upstream contents for {target_id}.",
        )

    patch_text = upstream_contents[patch_key]
    try:
        parsed_patch = parse_patch(patch_text)
        inv_new = inventory_patch(
            parsed_patch,
            source_identity=source_identity,
            source_type="official_50",
            registry=registry,
        )

        # Locate baseline patch text
        old_text = baseline_contents.get(patch_key) if baseline_contents else None
        if not old_text:
            # Check authoritative fixture
            is_51 = "51_deinlined" in patch_key
            fixture_dir = "sultan" if "sultan" in target_id else "r38"
            if is_51:
                fix_candidates = [
                    repo_root / ".github" / "fixtures" / fixture_dir / "51_deinlined_susfs_hooks_sultan-android14-6.1.patch",
                    repo_root / ".github" / "fixtures" / fixture_dir / "51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch",
                ]
            else:
                fix_candidates = [
                    repo_root / ".github" / "fixtures" / fixture_dir / "50_add_susfs_in_gki-android14-6.1.patch",
                    repo_root / ".github" / "fixtures" / fixture_dir / "50_add_susfs_in_gki-android16-6.12.patch",
                ]
            for fc in fix_candidates:
                if fc.is_file():
                    old_text = fc.read_text(encoding="utf-8")
                    break

        old_digests: set[str] = set()
        if old_text:
            inv_old = inventory_patch(
                parse_patch(old_text),
                source_identity=baseline_identity,
                source_type="official_50",
                registry=registry,
            )
            old_digests = {u.evidence[0].fingerprint.digest.value for u in inv_old.units}

        new_unknowns = [
            u for u in inv_new.units
            if u.kind == SemanticKind.UNKNOWN and u.evidence[0].fingerprint.digest.value not in old_digests
        ]

        if new_unknowns:
            affected_paths = sorted(set(u.location.path for u in new_unknowns))
            return SemanticGateResult(
                passed=False,
                classification=WatchClassification.SEMANTIC_DRIFT,
                details=(
                    f"Upstream SuSFS update introduces {len(new_unknowns)} new UNKNOWN semantic units across "
                    f"{len(affected_paths)} files ({', '.join(affected_paths[:5])}). Semantic reconciliation required."
                ),
                unknown_units=tuple(new_unknowns),
                affected_semantics=tuple(f"unknown:{u.location.path}:{u.location.start_line}" for u in new_unknowns[:20]),
            )

    except Exception as exc:
        return SemanticGateResult(
            passed=False,
            classification=WatchClassification.SEMANTIC_DRIFT,
            details=f"Semantic inventory verification failed for {target_id}: {exc}",
        )

    # 2C. Check Patch 10 in SuSFS tree if present
    patch10_key = None
    for k in upstream_contents:
        if "10_enable_susfs_for_ksu" in k and k.endswith(".patch"):
            patch10_key = k
            break

    # 2C. Check Patch 10 in SuSFS tree if present and baseline comparison is requested
    patch10_key = None
    for k in upstream_contents:
        if "10_enable_susfs_for_ksu" in k and k.endswith(".patch"):
            patch10_key = k
            break

    if patch10_key in upstream_contents and baseline_contents and patch10_key in baseline_contents:
        try:
            inv_10_new = inventory_patch(
                parse_patch(upstream_contents[patch10_key]),
                source_identity=source_identity,
                source_type="official_10",
                registry=registry,
            )
            old_10_text = baseline_contents.get(patch10_key)
            old_10_digests: set[str] = set()
            if old_10_text:
                inv_10_old = inventory_patch(
                    parse_patch(old_10_text),
                    source_identity=baseline_identity,
                    source_type="official_10",
                    registry=registry,
                )
                old_10_digests = {u.evidence[0].fingerprint.digest.value for u in inv_10_old.units}

            new_unknowns_10 = [
                u for u in inv_10_new.units
                if u.kind == SemanticKind.UNKNOWN and u.evidence[0].fingerprint.digest.value not in old_10_digests
            ]
            if new_unknowns_10:
                affected_paths = sorted(set(u.location.path for u in new_unknowns_10))
                return SemanticGateResult(
                    passed=False,
                    classification=WatchClassification.SEMANTIC_DRIFT,
                    details=(
                        f"Upstream SuSFS Patch 10 update introduces {len(new_unknowns_10)} new UNKNOWN semantic units across "
                        f"{len(affected_paths)} files ({', '.join(affected_paths[:5])}). Semantic reconciliation required."
                    ),
                    unknown_units=tuple(new_unknowns_10),
                    affected_semantics=tuple(f"unknown:{u.location.path}:{u.location.start_line}" for u in new_unknowns_10[:20]),
                )
        except Exception as exc:
            return SemanticGateResult(
                passed=False,
                classification=WatchClassification.SEMANTIC_DRIFT,
                details=f"Semantic inventory verification failed for SuSFS Patch 10: {exc}",
            )

    return SemanticGateResult(
        passed=True,
        classification=WatchClassification.SAFE_REGEN_CANDIDATE,
        details=f"Semantic gate passed: zero unapproved UNKNOWN semantic units on {target_id}.",
    )


def verify_semantic_gate_for_pipeline(
    patch_id: str,
    upstream_input: Path,
    *,
    repo_root: Optional[Path] = None,
    registry: Optional[SemanticRegistry] = None,
) -> SemanticGateResult:
    """Convenience entrypoint for v2.pipeline to evaluate semantic approval before candidate generation."""
    upstream_input = Path(upstream_input).resolve()
    upstream_contents: dict[str, str] = {}

    target_id = _normalize_target_id(patch_id)

    if target_id == "xxksu":
        kernel_dir = upstream_input / "kernel" if (upstream_input / "kernel").is_dir() else upstream_input
        for rel_path in PATCH11_CANONICAL_FILES:
            p = upstream_input / rel_path
            if not p.is_file():
                sub_rel = rel_path.removeprefix("kernel/")
                p = kernel_dir / sub_rel
            if p.is_file():
                upstream_contents[rel_path] = p.read_text(encoding="utf-8", errors="ignore")
    else:
        # SuSFS targets: find Patch 50 / 51 in upstream input
        if upstream_input.is_file():
            upstream_contents[upstream_input.name] = upstream_input.read_text(encoding="utf-8", errors="ignore")
        elif upstream_input.is_dir():
            target_cands = []
            if "6.12" in target_id or "r38" in target_id or "gki" in target_id:
                target_cands = (
                    "kernel_patches/50_add_susfs_in_gki-android16-6.12.patch",
                    "50_add_susfs_in_gki-android16-6.12.patch",
                    "kernel_patches/51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch",
                    "51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch",
                )
            elif "sultan" in target_id or "6.1" in target_id:
                target_cands = (
                    "kernel_patches/50_add_susfs_in_sultan-kernel-6.1.patch",
                    "kernel_patches/50_add_susfs_in_gki-android14-6.1.patch",
                    "50_add_susfs_in_sultan-kernel-6.1.patch",
                    "50_add_susfs_in_gki-android14-6.1.patch",
                    "kernel_patches/51_deinlined_susfs_hooks_sultan-android14-6.1.patch",
                    "51_deinlined_susfs_hooks_sultan-android14-6.1.patch",
                )
            for cand_rel in target_cands:
                p = upstream_input / cand_rel
                if p.is_file():
                    upstream_contents[cand_rel] = p.read_text(encoding="utf-8", errors="ignore")
                    break

    return evaluate_semantic_gate(
        patch_id,
        upstream_contents=upstream_contents,
        repo_root=repo_root,
        registry=registry,
        source_identity=upstream_input.name,
    )
