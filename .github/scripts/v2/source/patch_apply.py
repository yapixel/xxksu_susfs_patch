"""Strict application of textual unified patches to SourceBundle objects."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from ..engine.diff_parser import parse_patch
from ..model.patch import AddedLine, ContextLine, RemovedLine
from ..source.bundle import SourceBundle, create_source_bundle


class SourceBundlePatchError(ValueError):
    """A patch could not be applied exactly to a source bundle."""


def _path(value: str | None) -> str | None:
    if value is None or value == "/dev/null":
        return None
    if value.startswith("a/") or value.startswith("b/"):
        return value[2:]
    return value


def apply_patch_to_bundle(bundle: SourceBundle, patch_text: str) -> SourceBundle:
    """Apply a textual patch with exact context and fail closed on any mismatch."""
    if not isinstance(bundle, SourceBundle):
        raise TypeError("bundle must be a SourceBundle")
    if not isinstance(patch_text, str) or not patch_text:
        raise SourceBundlePatchError("patch content is required")

    patch = parse_patch(patch_text)
    files: dict[str, str] = {}
    for entry in bundle.files:
        if entry.content is None:
            raise SourceBundlePatchError(f"bundle file has no content: {entry.path}")
        files[entry.path] = entry.content

    for file_patch in patch.files:
        if file_patch.binary_lines is not None:
            raise SourceBundlePatchError("binary patches are unsupported")
        old_path = _path(file_patch.old_path)
        new_path = _path(file_patch.new_path)
        if old_path is None and new_path is None:
            raise SourceBundlePatchError("patch file has no path")
        if old_path is not None and old_path not in files:
            raise SourceBundlePatchError(f"patch baseline file missing: {old_path}")
        if old_path is None:
            source = ""
        else:
            source = files[old_path]

        lines = source.splitlines(keepends=True)
        output: list[str] = []
        original_cursor = 0
        for hunk in file_patch.hunks:
            # Hunk coordinates are always relative to the original file.  Build
            # the result from that immutable sequence; output-side insertions
            # must never shift later old_start positions.
            start = 0 if hunk.old_start == 0 else hunk.old_start - 1
            if start < original_cursor or start > len(lines):
                raise SourceBundlePatchError(f"hunk position out of range for {old_path or new_path}")
            output.extend(lines[original_cursor:start])
            original_cursor = start
            for line in hunk.lines:
                if isinstance(line, ContextLine):
                    if original_cursor >= len(lines) or lines[original_cursor].rstrip("\r\n") != line.text:
                        raise SourceBundlePatchError(f"context mismatch in {old_path or new_path}")
                    output.append(lines[original_cursor])
                    original_cursor += 1
                elif isinstance(line, RemovedLine):
                    if original_cursor >= len(lines) or lines[original_cursor].rstrip("\r\n") != line.text:
                        raise SourceBundlePatchError(f"removal mismatch in {old_path or new_path}")
                    original_cursor += 1
                elif isinstance(line, AddedLine):
                    output.append(line.text + "\n")
                else:
                    raise SourceBundlePatchError(f"unsupported hunk line in {old_path or new_path}")
        output.extend(lines[original_cursor:])
        result = "".join(output)

        if old_path is not None:
            del files[old_path]
        if new_path is not None:
            if new_path in files and new_path != old_path:
                raise SourceBundlePatchError(f"patch destination already exists: {new_path}")
            files[new_path] = result

    return create_source_bundle(
        bundle.target_id,
        bundle.kernel_version,
        files,
        metadata={**bundle.metadata, "applied_patch": True},
    )


def load_patch_text(value: object, paths: Mapping[str, str]) -> str:
    """Resolve an approved patch identifier or explicit patch/path."""
    if isinstance(value, str) and ("\n" in value or value.startswith(("From ", "diff --git", "--- "))):
        return value
    if isinstance(value, Mapping):
        identifier = value.get("name") or value.get("patch_51_id")
        if isinstance(identifier, str) and identifier in paths:
            value = identifier
        else:
            for key in ("content", "patch", "path", "artifact_path", "source"):
                candidate = value.get(key)
                if isinstance(candidate, str):
                    value = candidate
                    break
    if not isinstance(value, str):
        raise SourceBundlePatchError("patch must be text, path, or approved identifier")
    path = paths.get(value, value)
    patch_path = Path(path)
    if not patch_path.is_file():
        raise SourceBundlePatchError(f"patch artifact not found: {value}")
    return patch_path.read_text(encoding="utf-8")


__all__ = ["SourceBundlePatchError", "apply_patch_to_bundle", "load_patch_text"]
