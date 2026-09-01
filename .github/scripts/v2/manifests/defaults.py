from __future__ import annotations

from ..model.manifest import (
    ADAPTERS, KNOWN_TARGETS, LSM_KCONFIG, MANUAL_FIXTURES, MANUAL_KCONFIG,
    ManifestSet, ProfileManifest, TargetManifest,
)
from ..model.provenance import FixtureRef, InputRef, PatchRef, RepositoryRef


_TARGET_DATA = {
    "gki-android14-6.1": {
        "kernel": ("https://android.googlesource.com/kernel/common", "android14-6.1"),
        "susfs50": ("https://gitlab.com/simonpunk/susfs4ksu", "gki-android14-6.1"),
        "susfs50_commit": "598370fe434a7825bfe0f41d3029d102e3cfaec4",
    },
    "gki-android16-6.12": {
        "kernel": ("https://android.googlesource.com/kernel/common", "android16-6.12"),
        "susfs50": ("https://gitlab.com/simonpunk/susfs4ksu", "gki-android16-6.12"),
        "susfs50_commit": "698aa6a4ddca6fa5359871daf13f93583fb8282a",
    },
    "sultan-android14-6.1": {
        "kernel": ("https://github.com/kerneltoast/android_kernel_google_tensynos", "16.0.0-sultan"),
        "susfs50": ("https://gitlab.com/simonpunk/susfs4ksu", "sultan-shiba-susfs-minimal"),
        "susfs50_commit": "7fd1da8e0cc8d1b572c97c5fe4a27d0ec6e3e2f1",
    },
}

_XXKSU_COMMIT = "0b138d6a9cfe4dc163aa05c21b1e6a14ff868230"


def _target(target_id: str) -> TargetManifest:
    data = _TARGET_DATA[target_id]
    kernel_url, kernel_ref = data["kernel"]
    susfs_url, susfs_ref = data["susfs50"]
    refs = (
        RepositoryRef("kernel", kernel_url, requested_ref=kernel_ref),
        PatchRef("official-10", "https://gitlab.com/simonpunk/susfs4ksu", requested_ref=susfs_ref),
        PatchRef("official-50", susfs_url, requested_ref=susfs_ref, resolved_commit=data["susfs50_commit"]),
        RepositoryRef("xxksu", "https://github.com/backslashxx/KernelSU", requested_ref="master", resolved_commit=_XXKSU_COMMIT),
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
