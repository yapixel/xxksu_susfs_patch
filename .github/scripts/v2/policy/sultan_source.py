"""Reviewed Sultan core adaptations.

These rules preserve the accepted postimages; no final Patch 51 supplies their content.
"""
from pathlib import Path
from .lifecycle import fix_namespace, fix_task_mmu, fix_remote_memory
from ..source.baseline import load_authoritative_bundle


class SultanPatch51Adapter:
    """Target adapter for Sultan Android 14 / Linux 6.1 Patch 51."""
    target_id = "sultan-android14-6.1"
    patch_id = "sultan-android14-6.1-patch51"
    target_dir = "sultan-android14-6.1"
    source_state_key = "susfs_sultan"
    commit_fixture_relpath = Path(".github/fixtures/sultan/susfs-source-commit.txt")

    def load_preimages(self, root: Path, baseline: dict) -> dict[str, str]:
        bundle = load_authoritative_bundle(self.target_dir, root)
        return {f.path: f.content for f in bundle.files}

    def apply_target_adaptation(self, path: str, source: str) -> str:
        if path == "fs/namespace.c":
            source = fix_namespace(source)
        elif path == "fs/proc/task_mmu.c":
            source = fix_task_mmu(source, gki=False)
        elif path == "mm/memory.c":
            source = fix_remote_memory(source)
        return source

    def extra_postimages(self, root: Path, before: dict[str, str]) -> dict[str, str]:
        return {}

    def apply_target_name(self, baseline: dict) -> str:
        return self.target_id
