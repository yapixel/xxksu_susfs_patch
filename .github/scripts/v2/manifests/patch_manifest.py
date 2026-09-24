"""Deterministic generator and verifier for patches/manifest.json.

Treats committed patches/ as the public output/API of this repository.
Generates and verifies patches/manifest.json deterministically from authoritative
baseline and state records.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Tuple

from ..source.baseline import get_baseline_path, load_baseline_record

MANIFEST_SCHEMA = "xxksu-susfs-patch-manifest/v1"
MANIFEST_RELATIVE_PATH = "patches/manifest.json"


def get_repo_root(repo_root: Optional[Path] = None) -> Path:
    """Resolve the repository root directory."""
    if repo_root is not None:
        return repo_root.resolve()
    # v2/manifests/patch_manifest.py -> 4 levels up to repo root
    return Path(__file__).resolve().parents[4]


def compute_file_sha256(file_path: Path) -> str:
    """Compute standard 64-character lowercase hex SHA-256 digest of a file."""
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def generate_patch_manifest(repo_root: Optional[Path] = None) -> dict[str, Any]:
    """Generate the patches/manifest.json dictionary deterministically from baseline records."""
    root = get_repo_root(repo_root)

    # 1. Authoritative Shared xxKSU Patch 11
    xxksu_baseline = load_baseline_record(get_baseline_path("xxksu", root))
    p11_rel = xxksu_baseline.patch_11["patch_file"]
    p11_file = root / p11_rel
    if not p11_file.is_file():
        raise FileNotFoundError(f"Missing patch file: {p11_rel}")
    p11_sha = compute_file_sha256(p11_file)
    expected_p11 = xxksu_baseline.patch_11["patch_sha256"].removeprefix("sha256:")
    if p11_sha != expected_p11:
        raise ValueError(f"xxKSU Patch 11 SHA mismatch: expected {expected_p11}, got {p11_sha}")

    p11_entry = {
        "id": "xxksu-patch11",
        "name": "Shared xxKSU Patch 11",
        "relative_path": p11_rel,
        "sha256": p11_sha,
        "type": "ksu",
        "target_lineage": {
            "repository": xxksu_baseline.upstream["repository"],
            "ref": xxksu_baseline.upstream["ref"],
            "commit": xxksu_baseline.upstream["resolved_commit"],
        },
        "susfs_lineage": {
            "repository": xxksu_baseline.patch_10["repository"],
            "ref": xxksu_baseline.patch_10["ref"],
            "commit": xxksu_baseline.patch_10["resolved_commit"],
        },
        "compatibility_target": "backslashxx/KernelSU (xxKSU)",
    }

    # 2. Authoritative Sultan Android 14 / 6.1 Patch 51
    sultan_baseline = load_baseline_record(get_baseline_path("sultan-android14-6.1", root))
    sultan_rel = sultan_baseline.patch_51["patch_file"]
    sultan_file = root / sultan_rel
    if not sultan_file.is_file():
        raise FileNotFoundError(f"Missing patch file: {sultan_rel}")
    sultan_sha = compute_file_sha256(sultan_file)
    expected_sultan = sultan_baseline.patch_51["patch_sha256"].removeprefix("sha256:")
    if sultan_sha != expected_sultan:
        raise ValueError(f"Sultan Patch 51 SHA mismatch: expected {expected_sultan}, got {sultan_sha}")

    sultan_entry = {
        "id": "sultan-android14-6.1-patch51",
        "name": "Sultan Android 14 / 6.1 Patch 51",
        "relative_path": sultan_rel,
        "sha256": sultan_sha,
        "type": "kernel",
        "kernel_version": sultan_baseline.kernel_version,
        "target_lineage": {
            "repository": sultan_baseline.upstream["repository"],
            "ref": sultan_baseline.upstream["ref"],
            "commit": sultan_baseline.upstream["resolved_commit"],
        },
        "susfs_lineage": {
            "repository": sultan_baseline.susfs["repository"],
            "ref": sultan_baseline.susfs["ref"],
            "commit": sultan_baseline.susfs["resolved_commit"],
        },
        "compatibility_target": "Pixel 8 / 8 Pro (Shiba/Husky) Tensynos 16.0.0-sultan (Android 14 6.1)",
    }

    # 3. GKI Android 16 / 6.12 r38 Patch 51
    gki_baseline = load_baseline_record(get_baseline_path("gki-android16-6.12", root))
    compat = gki_baseline.metadata.get("compatibility_patches", {}).get("gki-android16-6.12-r38", {})
    r38_rel = compat.get(
        "patch_file",
        "patches/gki-android16-6.12/51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch",
    )
    r38_file = root / r38_rel
    if not r38_file.is_file():
        raise FileNotFoundError(f"Missing patch file: {r38_rel}")
    r38_sha = compute_file_sha256(r38_file)
    if "patch_sha256" in compat:
        expected_r38 = compat["patch_sha256"].removeprefix("sha256:")
        if r38_sha != expected_r38:
            raise ValueError(f"GKI r38 Patch 51 SHA mismatch: expected {expected_r38}, got {r38_sha}")

    r38_entry = {
        "id": "gki-android16-6.12-r38-patch51",
        "name": "GKI Android 16 / 6.12 r38 Patch 51",
        "relative_path": r38_rel,
        "sha256": r38_sha,
        "type": "kernel",
        "kernel_version": gki_baseline.kernel_version,
        "target_lineage": {
            "repository": gki_baseline.upstream["repository"],
            "ref": gki_baseline.upstream["ref"],
            "commit": gki_baseline.upstream["resolved_commit"],
        },
        "susfs_lineage": {
            "repository": gki_baseline.susfs["repository"],
            "ref": gki_baseline.susfs["ref"],
            "commit": gki_baseline.susfs["resolved_commit"],
        },
        "compatibility_target": compat.get(
            "compatibility_target",
            "android16-6.12-2025-09_r38 (Pixel 9 / GKI 6.12)",
        ),
    }

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "patches": [
            p11_entry,
            sultan_entry,
            r38_entry,
        ],
    }
    return manifest


def format_manifest(manifest: Mapping[str, Any]) -> str:
    """Format manifest as deterministic canonical JSON with trailing newline."""
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


def write_patch_manifest(repo_root: Optional[Path] = None) -> Path:
    """Generate and write patches/manifest.json deterministically."""
    root = get_repo_root(repo_root)
    manifest = generate_patch_manifest(root)
    content = format_manifest(manifest)
    out_path = root / MANIFEST_RELATIVE_PATH
    out_path.write_text(content, encoding="utf-8")
    return out_path


def verify_patch_manifest(repo_root: Optional[Path] = None) -> Tuple[bool, list[str]]:
    """Verify that patches/manifest.json exists, matches generated manifest, and all files match SHA-256."""
    root = get_repo_root(repo_root)
    errors: list[str] = []
    manifest_path = root / MANIFEST_RELATIVE_PATH

    if not manifest_path.is_file():
        errors.append(f"Manifest file missing: {MANIFEST_RELATIVE_PATH}")
        return False, errors

    try:
        on_disk_raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"Invalid JSON in {MANIFEST_RELATIVE_PATH}: {exc}")
        return False, errors

    try:
        expected_manifest = generate_patch_manifest(root)
    except Exception as exc:
        errors.append(f"Failed to generate manifest from baselines: {exc}")
        return False, errors

    # Check on-disk content matches expected deterministic generation
    expected_content = format_manifest(expected_manifest)
    on_disk_content = manifest_path.read_text(encoding="utf-8")
    if on_disk_content != expected_content:
        errors.append("Manifest content on disk does not match deterministic generation (stale manifest)")

    # Check each patch entry
    for entry in on_disk_raw.get("patches", []):
        rel_path = entry.get("relative_path")
        expected_sha = entry.get("sha256")
        if not rel_path:
            errors.append(f"Entry {entry.get('id')} missing relative_path")
            continue
        p = root / rel_path
        if not p.is_file():
            errors.append(f"Patch file not found on disk: {rel_path}")
            continue
        actual_sha = compute_file_sha256(p)
        clean_expected = expected_sha.removeprefix("sha256:") if expected_sha else None
        if actual_sha != clean_expected:
            errors.append(
                f"SHA-256 mismatch for {rel_path}: expected {clean_expected}, got {actual_sha}"
            )

    return len(errors) == 0, errors


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Manage patches/manifest.json")
    parser.add_argument("--check", action="store_true", help="Verify manifest matches baseline records and disk")
    parser.add_argument("--write", action="store_true", help="Write deterministic manifest (default)")
    parser.add_argument("--repo-root", type=Path, default=None, help="Root of repository")
    args = parser.parse_args(argv)

    root = get_repo_root(args.repo_root)

    if args.check:
        valid, errors = verify_patch_manifest(root)
        if not valid:
            print("❌ patches/manifest.json verification failed:")
            for err in errors:
                print(f"  - {err}")
            return 1
        print("✅ patches/manifest.json verified successfully (all paths exist, all SHA-256 match, not stale).")
        return 0
    else:
        out = write_patch_manifest(root)
        print(f"✅ Written deterministic patches manifest to {out}")
        return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
