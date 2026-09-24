"""Accepted V2 target/profile and patch manifests."""

from .defaults import build_manifest_set, build_manifest_sets

__all__ = [
    "build_manifest_set",
    "build_manifest_sets",
    "MANIFEST_SCHEMA",
    "MANIFEST_RELATIVE_PATH",
    "generate_patch_manifest",
    "write_patch_manifest",
    "verify_patch_manifest",
]


def __getattr__(name: str):
    if name in (
        "generate_patch_manifest",
        "write_patch_manifest",
        "verify_patch_manifest",
        "MANIFEST_SCHEMA",
        "MANIFEST_RELATIVE_PATH",
    ):
        from . import patch_manifest

        return getattr(patch_manifest, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
