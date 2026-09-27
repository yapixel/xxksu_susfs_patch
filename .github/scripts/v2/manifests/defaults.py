from __future__ import annotations

import json
import re
from pathlib import Path

from ..model.manifest import (
    ADAPTERS, KNOWN_TARGETS, LSM_KCONFIG, MANUAL_FIXTURES, MANUAL_KCONFIG,
    ManifestSet, ProfileManifest, TargetManifest,
)
from ..model.provenance import FixtureRef, InputRef, PatchRef, RepositoryRef


_TARGET_DATA = {
    "gki-android16-6.12": {
        "kernel": ("https://android.googlesource.com/kernel/common", "android16-6.12"),
    },
    "sultan-android14-6.1": {
        "kernel": ("https://github.com/kerneltoast/android_kernel_google_tensynos", "16.0.0-sultan"),
    },
}

def accepted_sources(repo_root: Path | None = None) -> dict:
    """Read reviewed run identities, not tracking HEADs or historical defaults."""
    from .patch_manifest import get_repo_root
    root = get_repo_root(repo_root)
    sources = json.loads((root / ".github/upstream-state.json").read_text())["sources"]["authoritative"]
    for key, target, field in (("backslashxx_kernelsu", "xxksu", "upstream"),
                               ("susfs_sultan", "sultan-android14-6.1", "susfs"),
                               ("susfs_gki", "gki-android16-6.12", "susfs")):
        baseline = json.loads((root / "patches" / target / "BASELINE.json").read_text())[field]
        source = sources[key]
        if (not re.fullmatch(r"[0-9a-f]{40}", source["commit"])
                or source["commit"] != baseline["resolved_commit"]
                or source["repository"].removesuffix(".git") != baseline["repository"].removesuffix(".git")):
            raise ValueError(f"accepted source identity mismatch: {key}")
    return sources


def _target(target_id: str) -> TargetManifest:
    data = _TARGET_DATA[target_id]
    sources = accepted_sources()
    susfs = sources["susfs_sultan" if target_id.startswith("sultan") else "susfs_gki"]
    xxksu = sources["backslashxx_kernelsu"]
    kernel_url, kernel_ref = data["kernel"]
    susfs_url, susfs_ref = susfs["repository"].removesuffix(".git"), susfs["ref"]
    refs = (
        RepositoryRef("kernel", kernel_url, requested_ref=kernel_ref),
        PatchRef("official-10", "https://gitlab.com/simonpunk/susfs4ksu", requested_ref=susfs_ref),
        PatchRef("official-50", susfs_url, requested_ref=susfs_ref, resolved_commit=susfs["commit"]),
        RepositoryRef("xxksu", xxksu["repository"].removesuffix(".git"), requested_ref=xxksu["ref"], resolved_commit=xxksu["commit"]),
    )
    return TargetManifest("xxksu-susfs-target/v1", target_id, refs, ADAPTERS[target_id],
                          f"{target_id.replace('-', '_')}_51", (f"{target_id}-manual", f"{target_id}-lsm_bl"))


def _profile(target_id: str, mode: str, patch_51_id: str) -> ProfileManifest:
    if mode == "manual":
        fixtures = tuple(FixtureRef(name, f".github/fixtures/{name}", artifact_path=f".github/fixtures/{name}")
                         for name in MANUAL_FIXTURES)
        prerequisites = {"arch": "any", "kallsyms": True}
        ownership = {"exec": MANUAL_FIXTURES[0], "access": MANUAL_FIXTURES[0], "stat": MANUAL_FIXTURES[0],
                     "fstat-return": MANUAL_FIXTURES[0], "reboot": MANUAL_FIXTURES[0],
                     "read": MANUAL_FIXTURES[1], "setuid": MANUAL_FIXTURES[1], "setprocattr": MANUAL_FIXTURES[1]}
        config = dict(MANUAL_KCONFIG)
    else:
        fixtures = ()
        prerequisites = {"arch": "arm64", "kallsyms": True, "XXKSU_BL_COMPOSITE": "XXKSU_BL_COMPOSITE"}
        ownership = {"exec": "XXKSU_BL_COMPOSITE", "access": "XXKSU_BL_COMPOSITE", "stat": "XXKSU_BL_COMPOSITE",
                     "fstat-return": "XXKSU_BL_COMPOSITE", "reboot": "XXKSU_BL_COMPOSITE", "read": "XXKSU_BL_COMPOSITE",
                     "setuid": "XXKSU_LSM", "setprocattr": "XXKSU_LSM"}
        config = dict(LSM_KCONFIG)
    return ProfileManifest("xxksu-susfs-profile/v1", f"{target_id}-{mode}", target_id, mode, fixtures,
                           config, prerequisites, ownership, "shared-11", patch_51_id, ADAPTERS[target_id])


def build_manifest_sets() -> tuple[ManifestSet, ...]:
    targets = [_target(target_id) for target_id in KNOWN_TARGETS]
    return tuple(ManifestSet(target, tuple(_profile(target.target_id, mode, target.patch_51_id)
                              for mode in ("manual", "lsm_bl"))).validate() for target in targets)


def build_manifest_set(target_id: str | None = None):
    """Return one accepted target set, or all three when no target is given."""
    sets = build_manifest_sets()
    if target_id is None:
        return sets
    for manifest_set in sets:
        if manifest_set.target.target_id == target_id:
            return manifest_set
    raise KeyError(target_id)
