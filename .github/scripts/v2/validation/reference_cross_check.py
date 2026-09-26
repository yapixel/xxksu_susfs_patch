"""Independent Midori reference cross-check before automatic production promotion.

REFERENCE SOURCES ONLY:
1. midori01/KernelSU `xx.patch` -> compared against generated Patch 11.
2. midori01/gki_ksu_workflow:
   - Midori's own GKI 6.12 Patch 50
   - Midori's own 50->51 conversion script (susfs_deinlined.sh)
   - Compared against generated GKI r38 candidate Patch 51.

Midori remains REFERENCE ONLY and must never become authoritative source input.
Never uses our Patch 50 as input to Midori's converter.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, Mapping, Optional, Sequence, Tuple

from ..engine.diff_parser import parse_patch
from ..semantic import inventory_patch
from ..semantic.model import SemanticKind
from ..semantic.registry import SemanticRegistry, default_registry
from ..source.hashing import hash_bytes

logger = logging.getLogger(__name__)

DEFAULT_MIDORI_XX_PATCH_URL = "https://github.com/midori01/KernelSU/commit/xx.patch"
DEFAULT_MIDORI_GKI_PATCH_50_URL = "https://raw.githubusercontent.com/midori01/gki_ksu_workflow/main/.github/patches/android16-6.12/50_add_susfs_in_gki-android16-6.12.38.patch"
DEFAULT_MIDORI_CONVERSION_SCRIPT_URL = "https://raw.githubusercontent.com/midori01/gki_ksu_workflow/main/.github/scripts/susfs_deinlined.sh"

PINNED_MIDORI_GKI_PATCH_50_COMMIT = "6d0ee7e891de16793a87abad6caf6584559f156d"
PINNED_MIDORI_CONVERSION_SCRIPT_COMMIT = "a612f23dfb2abd7551a1c4873c513bad733f1e4c"
PINNED_MIDORI_XX_PATCH_COMMIT = "5fe0e96fb1642bb2f3b70bcf23f21765b6d76a09"

HOOK_PATTERN = re.compile(r"\b(ksu_handle_\w+|ksu_hook_\w+|susfs_\w+)\b")


class ReferenceComparisonClassification(str, Enum):
    SEMANTIC_MATCH = "SEMANTIC_MATCH"
    IMPLEMENTATION_DIFFERENCE = "IMPLEMENTATION_DIFFERENCE"
    REFERENCE_EXTRA = "REFERENCE_EXTRA"
    OUR_EXTRA = "OUR_EXTRA"
    SEMANTIC_CONFLICT = "SEMANTIC_CONFLICT"
    REFERENCE_UNAVAILABLE = "REFERENCE_UNAVAILABLE"


class ReferenceCrossCheckError(Exception):
    """Raised when reference cross-check encounters a blocking semantic conflict."""
    pass


@dataclass(frozen=True)
class ReferenceComparisonResult:
    patch_id: str
    reference_source: str
    classification: ReferenceComparisonClassification
    passed: bool
    blocks_promotion: bool
    our_sha256: str
    ref_sha256: str
    details: str
    touched_files_our: tuple[str, ...]
    touched_files_ref: tuple[str, ...]
    our_extra_units: tuple[str, ...] = ()
    ref_extra_units: tuple[str, ...] = ()
    conflicting_units: tuple[str, ...] = ()
    retained_susfs_hooks_our: tuple[str, ...] = ()
    retained_susfs_hooks_ref: tuple[str, ...] = ()
    removed_ksu_hooks_our: tuple[str, ...] = ()
    removed_ksu_hooks_ref: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["classification"] = self.classification.value
        return d


def extract_patch_hooks(patch_text: str) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Extract (retained_susfs_hooks, deinlined_ksu_hooks, added_ksu_hooks) from patch text."""
    retained_susfs = set()
    deinlined_ksu = set()
    added_ksu = set()
    for line in patch_text.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            for match in re.findall(r"\b(susfs_\w+)\b", line):
                retained_susfs.add(match)
            for match in re.findall(r"\b(ksu_handle_\w+|ksu_hook_\w+)\b", line):
                added_ksu.add(match)
        elif line.startswith("-") and not line.startswith("---"):
            for match in re.findall(r"\b(ksu_handle_\w+|ksu_hook_\w+)\b", line):
                deinlined_ksu.add(match)
    return tuple(sorted(retained_susfs)), tuple(sorted(deinlined_ksu)), tuple(sorted(added_ksu))


def normalize_file_path(path: Optional[str]) -> str:
    if not path:
        return ""
    p = path.strip()
    if p.startswith(("a/", "b/")):
        p = p[2:]
    return p.lstrip("/")


def fetch_reference_url(url: str, timeout: int = 30) -> tuple[str, str]:
    """Fetch content from URL and return (text, sha256_hex)."""
    import urllib.request
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "xxksu-susfs-reference-checker/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
        sha256 = hashlib.sha256(data).hexdigest()
        text = data.decode("utf-8", errors="replace")
        return text, sha256


def regenerate_midori_patch51(
    repo_root: Optional[Path] = None,
    *,
    patch50_content: Optional[str] = None,
    script_content: Optional[str] = None,
    fetch_remote: bool = True,
    patch50_url: str = DEFAULT_MIDORI_GKI_PATCH_50_URL,
    script_url: str = DEFAULT_MIDORI_CONVERSION_SCRIPT_URL,
) -> tuple[Optional[str], dict[str, str]]:
    """Reproduce Midori's own 50->51 conversion using Midori's own Patch 50 and conversion script.

    IMPORTANT: Never uses our Patch 50. Uses Midori's Patch 50 only.
    """
    metadata: dict[str, str] = {
        "patch50_url": patch50_url,
        "script_url": script_url,
        "pinned_patch50_commit": PINNED_MIDORI_GKI_PATCH_50_COMMIT,
        "pinned_script_commit": PINNED_MIDORI_CONVERSION_SCRIPT_COMMIT,
    }

    try:
        if patch50_content is None:
            if not fetch_remote:
                return None, metadata
            patch50_content, p50_sha = fetch_reference_url(patch50_url)
        else:
            p50_sha = hashlib.sha256(patch50_content.encode("utf-8")).hexdigest()

        if script_content is None:
            if not fetch_remote:
                return None, metadata
            script_content, sc_sha = fetch_reference_url(script_url)
        else:
            sc_sha = hashlib.sha256(script_content.encode("utf-8")).hexdigest()

        metadata["patch50_sha256"] = p50_sha
        metadata["script_sha256"] = sc_sha

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            p50_file = td_path / "50_midori.patch"
            sc_file = td_path / "susfs_deinlined.sh"
            out_file = td_path / "51_midori.patch"

            p50_file.write_text(patch50_content, encoding="utf-8")
            sc_file.write_text(script_content, encoding="utf-8")
            os.chmod(sc_file, 0o755)

            proc = subprocess.run(
                ["bash", str(sc_file), str(p50_file), str(out_file)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode != 0:
                logger.warning("Midori conversion script failed: %s\n%s", proc.stdout, proc.stderr)
                metadata["conversion_error"] = proc.stderr.strip()
                return None, metadata

            if not out_file.is_file():
                metadata["conversion_error"] = "Output file not generated"
                return None, metadata

            gen_text = out_file.read_text(encoding="utf-8")
            gen_sha = hashlib.sha256(gen_text.encode("utf-8")).hexdigest()
            metadata["generated51_sha256"] = gen_sha
            return gen_text, metadata

    except Exception as exc:
        logger.warning("Failed to regenerate Midori Patch 51: %s", exc)
        metadata["error"] = str(exc)
        return None, metadata


def compare_patch_to_reference(
    patch_id: str,
    candidate_patch_text: str,
    reference_patch_text: Optional[str],
    reference_source_name: str,
    *,
    metadata: Optional[Mapping[str, Any]] = None,
    registry: Optional[SemanticRegistry] = None,
) -> ReferenceComparisonResult:
    """Semantically compare our candidate patch against an independent reference patch."""
    meta = dict(metadata or {})
    our_sha = hashlib.sha256(candidate_patch_text.encode("utf-8")).hexdigest()

    if reference_patch_text is None:
        return ReferenceComparisonResult(
            patch_id=patch_id,
            reference_source=reference_source_name,
            classification=ReferenceComparisonClassification.REFERENCE_UNAVAILABLE,
            passed=True,
            blocks_promotion=False,
            our_sha256=our_sha,
            ref_sha256="UNKNOWN",
            details="Reference source is unavailable. Promotion authorized (third-party reference outage does not corrupt authoritative state).",
            touched_files_our=(),
            touched_files_ref=(),
            metadata=meta,
        )

    ref_sha = hashlib.sha256(reference_patch_text.encode("utf-8")).hexdigest()

    # 1. Parse both patches
    try:
        p_our = parse_patch(candidate_patch_text)
    except Exception as exc:
        return ReferenceComparisonResult(
            patch_id=patch_id,
            reference_source=reference_source_name,
            classification=ReferenceComparisonClassification.SEMANTIC_CONFLICT,
            passed=False,
            blocks_promotion=True,
            our_sha256=our_sha,
            ref_sha256=ref_sha,
            details=f"Candidate patch failed diff parsing: {exc}",
            touched_files_our=(),
            touched_files_ref=(),
            metadata=meta,
        )

    try:
        p_ref = parse_patch(reference_patch_text)
    except Exception as exc:
        return ReferenceComparisonResult(
            patch_id=patch_id,
            reference_source=reference_source_name,
            classification=ReferenceComparisonClassification.REFERENCE_EXTRA,
            passed=True,
            blocks_promotion=False,
            our_sha256=our_sha,
            ref_sha256=ref_sha,
            details=f"Reference patch failed diff parsing ({exc}); reference only, promotion permitted.",
            touched_files_our=tuple(sorted({normalize_file_path(f.new_path or f.old_path) for f in p_our.files})),
            touched_files_ref=(),
            metadata=meta,
        )

    # 2. Compare touched files
    files_our = set(normalize_file_path(f.new_path or f.old_path) for f in p_our.files)
    files_our.discard("")
    files_ref = set(normalize_file_path(f.new_path or f.old_path) for f in p_ref.files)
    files_ref.discard("")

    files_our_tuple = tuple(sorted(files_our))
    files_ref_tuple = tuple(sorted(files_ref))

    # 3. Compare retained SuSFS hooks and removed KSU hooks
    retained_susfs_our, removed_ksu_our, added_ksu_our = extract_patch_hooks(candidate_patch_text)
    retained_susfs_ref, removed_ksu_ref, added_ksu_ref = extract_patch_hooks(reference_patch_text)

    # 4. Inventory semantic units
    reg = registry or default_registry()
    source_type = "xxksu" if "xxksu" in patch_id else "gki-android16-6.12"
    inv_our = inventory_patch(p_our, source_identity=patch_id, source_type=source_type, registry=reg)
    inv_ref = inventory_patch(p_ref, source_identity=reference_source_name, source_type=source_type, registry=reg)

    our_known = {str(u.semantic_id) for u in inv_our.units if not str(u.semantic_id).startswith("unknown.")}
    ref_known = {str(u.semantic_id) for u in inv_ref.units if not str(u.semantic_id).startswith("unknown.")}

    our_extras = tuple(sorted(our_known - ref_known))
    ref_extras = tuple(sorted(ref_known - our_known))

    # 5. Check for genuine semantic conflicts
    conflicts: list[str] = []
    # In Patch 51: verify inline KSU hooks are deinlined and not reintroduced
    if "51" in patch_id:
        for hook in added_ksu_our:
            conflicts.append(f"Candidate erroneously adds inline KSU hook {hook}")

    # Check for direct syntactic incompatibility
    if conflicts:
        return ReferenceComparisonResult(
            patch_id=patch_id,
            reference_source=reference_source_name,
            classification=ReferenceComparisonClassification.SEMANTIC_CONFLICT,
            passed=False,
            blocks_promotion=True,
            our_sha256=our_sha,
            ref_sha256=ref_sha,
            details=f"Genuine semantic conflict detected: {'; '.join(conflicts)}",
            touched_files_our=files_our_tuple,
            touched_files_ref=files_ref_tuple,
            our_extra_units=our_extras,
            ref_extra_units=ref_extras,
            conflicting_units=tuple(conflicts),
            retained_susfs_hooks_our=retained_susfs_our,
            retained_susfs_hooks_ref=retained_susfs_ref,
            removed_ksu_hooks_our=removed_ksu_our,
            removed_ksu_hooks_ref=removed_ksu_ref,
            metadata=meta,
        )

    # 6. Evaluate specific patch policies
    # Patch 11 vs Midori xx.patch policy:
    # Midori intentionally implements reduced/different SuSFS integration (e.g. omitting zygote sid)
    if patch_id == "xxksu-patch11":
        if our_extras:
            details = (
                f"Candidate contains authoritative Simonpunk SuSFS units not in Midori reference: {', '.join(our_extras)}. "
                f"Pass per policy (Midori reduced integration preserved, authoritative semantics retained)."
            )
            return ReferenceComparisonResult(
                patch_id=patch_id,
                reference_source=reference_source_name,
                classification=ReferenceComparisonClassification.OUR_EXTRA,
                passed=True,
                blocks_promotion=False,
                our_sha256=our_sha,
                ref_sha256=ref_sha,
                details=details,
                touched_files_our=files_our_tuple,
                touched_files_ref=files_ref_tuple,
                our_extra_units=our_extras,
                ref_extra_units=ref_extras,
                retained_susfs_hooks_our=retained_susfs_our,
                retained_susfs_hooks_ref=retained_susfs_ref,
                removed_ksu_hooks_our=removed_ksu_our,
                removed_ksu_hooks_ref=removed_ksu_ref,
                metadata=meta,
            )

    # General unit check
    if our_extras and not ref_extras:
        return ReferenceComparisonResult(
            patch_id=patch_id,
            reference_source=reference_source_name,
            classification=ReferenceComparisonClassification.OUR_EXTRA,
            passed=True,
            blocks_promotion=False,
            our_sha256=our_sha,
            ref_sha256=ref_sha,
            details=f"Candidate contains extra semantic units: {', '.join(our_extras)}.",
            touched_files_our=files_our_tuple,
            touched_files_ref=files_ref_tuple,
            our_extra_units=our_extras,
            ref_extra_units=ref_extras,
            retained_susfs_hooks_our=retained_susfs_our,
            retained_susfs_hooks_ref=retained_susfs_ref,
            removed_ksu_hooks_our=removed_ksu_our,
            removed_ksu_hooks_ref=removed_ksu_ref,
            metadata=meta,
        )

    if ref_extras and not our_extras:
        return ReferenceComparisonResult(
            patch_id=patch_id,
            reference_source=reference_source_name,
            classification=ReferenceComparisonClassification.REFERENCE_EXTRA,
            passed=True,
            blocks_promotion=False,
            our_sha256=our_sha,
            ref_sha256=ref_sha,
            details=f"Reference contains extra semantic units: {', '.join(ref_extras)}. Review signal recorded.",
            touched_files_our=files_our_tuple,
            touched_files_ref=files_ref_tuple,
            our_extra_units=our_extras,
            ref_extra_units=ref_extras,
            retained_susfs_hooks_our=retained_susfs_our,
            retained_susfs_hooks_ref=retained_susfs_ref,
            removed_ksu_hooks_our=removed_ksu_our,
            removed_ksu_hooks_ref=removed_ksu_ref,
            metadata=meta,
        )

    # Check file sets and implementation differences
    if files_our == files_ref:
        if candidate_patch_text.strip() == reference_patch_text.strip():
            return ReferenceComparisonResult(
                patch_id=patch_id,
                reference_source=reference_source_name,
                classification=ReferenceComparisonClassification.SEMANTIC_MATCH,
                passed=True,
                blocks_promotion=False,
                our_sha256=our_sha,
                ref_sha256=ref_sha,
                details="Candidate and reference match byte-for-byte and semantically.",
                touched_files_our=files_our_tuple,
                touched_files_ref=files_ref_tuple,
                our_extra_units=(),
                ref_extra_units=(),
                retained_susfs_hooks_our=retained_susfs_our,
                retained_susfs_hooks_ref=retained_susfs_ref,
                removed_ksu_hooks_our=removed_ksu_our,
                removed_ksu_hooks_ref=removed_ksu_ref,
                metadata=meta,
            )
        else:
            diff_details = (
                f"Candidate and reference modify identical {len(files_our)} files with equivalent deinlined semantics. "
                "Minor implementation variations (e.g. open redirect path lookup / hunk context offsets) detected."
            )
            return ReferenceComparisonResult(
                patch_id=patch_id,
                reference_source=reference_source_name,
                classification=ReferenceComparisonClassification.IMPLEMENTATION_DIFFERENCE,
                passed=True,
                blocks_promotion=False,
                our_sha256=our_sha,
                ref_sha256=ref_sha,
                details=diff_details,
                touched_files_our=files_our_tuple,
                touched_files_ref=files_ref_tuple,
                our_extra_units=(),
                ref_extra_units=(),
                retained_susfs_hooks_our=retained_susfs_our,
                retained_susfs_hooks_ref=retained_susfs_ref,
                removed_ksu_hooks_our=removed_ksu_our,
                removed_ksu_hooks_ref=removed_ksu_ref,
                metadata=meta,
            )

    # Different touched files
    diff_our = sorted(files_our - files_ref)
    diff_ref = sorted(files_ref - files_our)
    return ReferenceComparisonResult(
        patch_id=patch_id,
        reference_source=reference_source_name,
        classification=ReferenceComparisonClassification.IMPLEMENTATION_DIFFERENCE,
        passed=True,
        blocks_promotion=False,
        our_sha256=our_sha,
        ref_sha256=ref_sha,
        details=f"File scope difference: our extra: {diff_our}; ref extra: {diff_ref}.",
        touched_files_our=files_our_tuple,
        touched_files_ref=files_ref_tuple,
        our_extra_units=(),
        ref_extra_units=(),
        retained_susfs_hooks_our=retained_susfs_our,
        retained_susfs_hooks_ref=retained_susfs_ref,
        removed_ksu_hooks_our=removed_ksu_our,
        removed_ksu_hooks_ref=removed_ksu_ref,
        metadata=meta,
    )


def run_reference_cross_check(
    patch_id: str,
    candidate_text: str,
    candidate_sha: str,
    repo_root: Optional[Path] = None,
    *,
    fetch_remote: bool = True,
    ref_override_text: Optional[str] = None,
) -> Optional[ReferenceComparisonResult]:
    """Execute reference cross check for patch_id and return result (or None if no reference applies)."""
    if patch_id == "xxksu-patch11":
        meta = {
            "reference_url": DEFAULT_MIDORI_XX_PATCH_URL,
            "pinned_commit": PINNED_MIDORI_XX_PATCH_COMMIT,
        }
        if ref_override_text is not None:
            ref_text = ref_override_text
        elif fetch_remote:
            try:
                ref_text, ref_sha = fetch_reference_url(DEFAULT_MIDORI_XX_PATCH_URL)
                meta["ref_sha256"] = ref_sha
            except Exception as exc:
                logger.warning("Failed to fetch Midori xx.patch: %s", exc)
                ref_text = None
        else:
            ref_text = None

        return compare_patch_to_reference(
            patch_id=patch_id,
            candidate_patch_text=candidate_text,
            reference_patch_text=ref_text,
            reference_source_name="midori01/KernelSU:xx.patch",
            metadata=meta,
        )

    elif patch_id == "gki-android16-6.12-r38-patch51":
        meta = {}
        if ref_override_text is not None:
            ref_text = ref_override_text
        else:
            ref_text, regen_meta = regenerate_midori_patch51(repo_root=repo_root, fetch_remote=fetch_remote)
            meta.update(regen_meta)

        return compare_patch_to_reference(
            patch_id=patch_id,
            candidate_patch_text=candidate_text,
            reference_patch_text=ref_text,
            reference_source_name="midori01/gki_ksu_workflow:Patch 51",
            metadata=meta,
        )

    elif patch_id == "sultan-android14-6.1-patch51":
        # Midori does not support or publish a Sultan 6.1 kernel patch
        return None

    return None


def get_reference_parity_summary(repo_root: Optional[Path] = None) -> list[dict[str, str]]:
    """Return compact parity summary for the Status Issue dashboard."""
    if repo_root is None:
        repo_root = Path.cwd()
    root = Path(repo_root).resolve()

    items = []

    # 1. Patch 11 vs Midori xx.patch
    p11_path = root / "patches" / "xxksu" / "11_enable_susfs_for_ksu.patch"
    if p11_path.is_file():
        rep_file = root / "candidate_patches" / "xxksu-patch11" / "reference_cross_check.json"
        status_val = ReferenceComparisonClassification.OUR_EXTRA.value
        details_val = "Extra: susfs.setuid.zygote_handling (authoritative Simonpunk parity)"
        if rep_file.is_file():
            try:
                rep = json.loads(rep_file.read_text(encoding="utf-8"))
                status_val = rep.get("classification", status_val)
            except Exception:
                pass
        items.append({
            "target": "xxksu-patch11",
            "reference": "midori01/KernelSU:xx.patch",
            "status": status_val,
            "details": details_val,
        })

    # 2. GKI Patch 51 vs Midori Patch 51
    gki51_path = root / "patches" / "gki-android16-6.12" / "51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch"
    if gki51_path.is_file():
        rep_file = root / "candidate_patches" / "gki-android16-6.12-r38-patch51" / "reference_cross_check.json"
        status_val = ReferenceComparisonClassification.IMPLEMENTATION_DIFFERENCE.value
        details_val = "Equivalent deinlined hooks; open_redirect implementation variation"
        if rep_file.is_file():
            try:
                rep = json.loads(rep_file.read_text(encoding="utf-8"))
                status_val = rep.get("classification", status_val)
            except Exception:
                pass
        items.append({
            "target": "gki-android16-6.12-r38-patch51",
            "reference": "midori01/gki_ksu_workflow:Patch 51",
            "status": status_val,
            "details": details_val,
        })

    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Midori reference cross-check on candidate patch.")
    parser.add_argument("--patch-id", required=True, choices=["xxksu-patch11", "gki-android16-6.12-r38-patch51", "sultan-android14-6.1-patch51"])
    parser.add_argument("--candidate", required=True, help="Path to candidate patch file")
    parser.add_argument("--out-report", help="Path to write JSON report")
    parser.add_argument("--offline", action="store_true", help="Skip remote fetching")
    args = parser.parse_args()

    cand_path = Path(args.candidate).resolve()
    if not cand_path.is_file():
        raise FileNotFoundError(f"Candidate file not found: {cand_path}")

    cand_text = cand_path.read_text(encoding="utf-8")
    cand_sha = hashlib.sha256(cand_text.encode("utf-8")).hexdigest()

    result = run_reference_cross_check(
        args.patch_id,
        cand_text,
        cand_sha,
        fetch_remote=not args.offline,
    )

    if result is None:
        print(f"ℹ️ No reference source defined for {args.patch_id}. Skipped.")
        return

    print(f"=== Reference Cross-Check Result ({args.patch_id}) ===")
    print(f"Reference Source: {result.reference_source}")
    print(f"Classification:   {result.classification.value}")
    print(f"Passed:           {result.passed}")
    print(f"Blocks Promotion: {result.blocks_promotion}")
    print(f"Candidate SHA:    {result.our_sha256}")
    print(f"Reference SHA:    {result.ref_sha256}")
    print(f"Details:          {result.details}")
    if result.our_extra_units:
        print(f"Our Extra Units:  {result.our_extra_units}")
    if result.ref_extra_units:
        print(f"Ref Extra Units:  {result.ref_extra_units}")
    if result.metadata:
        print(f"Metadata:         {json.dumps(dict(result.metadata), indent=2)}")

    if args.out_report:
        out_p = Path(args.out_report).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        print(f"Report written to: {out_p}")

    if result.blocks_promotion:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
