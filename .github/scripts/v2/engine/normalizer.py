"""Deterministic hunk-offset normalization for generated and adapted patches."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Mapping, Sequence, Tuple

from ..model.patch import AddedLine, ContextLine, FilePatch, Hunk, Patch, RemovedLine
from ..model.result import PatchError
from .diff_parser import parse_patch
from .emitter import emit_patch


class NormalizationError(PatchError):
    """Base class for patch normalization failures."""


class ContextMismatchError(NormalizationError):
    """Preimage context was not found in target source."""


class AmbiguousContextError(NormalizationError):
    """Preimage context matched multiple locations and could not be uniquely disambiguated."""


class SourceMissingError(NormalizationError):
    """Target source file required for patch normalization is missing."""


class HunkOrderError(NormalizationError):
    """Normalized hunk positions violate monotonic order."""


class OffsetVerificationError(NormalizationError):
    """Reapplication of normalized patch at offset 0 failed verification."""


@dataclass(frozen=True)
class HunkNormalizationRecord:
    file_path: str
    hunk_index: int
    old_start_before: int
    old_count_before: int
    old_start_after: int
    old_count_after: int
    new_start_before: int
    new_count_before: int
    new_start_after: int
    new_count_after: int
    offset: int
    section_context: str

    @property
    def header_before(self) -> str:
        ctx = f" {self.section_context}" if self.section_context else ""
        return f"@@ -{self.old_start_before},{self.old_count_before} +{self.new_start_before},{self.new_count_before} @@{ctx}"

    @property
    def header_after(self) -> str:
        ctx = f" {self.section_context}" if self.section_context else ""
        return f"@@ -{self.old_start_after},{self.old_count_after} +{self.new_start_after},{self.new_count_after} @@{ctx}"

    @property
    def has_drift(self) -> bool:
        return (
            self.old_start_before != self.old_start_after
            or self.new_start_before != self.new_start_after
        )


@dataclass(frozen=True)
class NormalizationReport:
    records: Tuple[HunkNormalizationRecord, ...]

    @property
    def total_hunks(self) -> int:
        return len(self.records)

    @property
    def drifted_hunks(self) -> int:
        return sum(1 for r in self.records if r.has_drift)

    @property
    def has_drift(self) -> bool:
        return self.drifted_hunks > 0

    def format_table(self) -> str:
        lines = []
        for r in self.records:
            status = f"offset {r.offset:+d}" if r.offset != 0 else "offset 0"
            lines.append(
                f"{r.file_path} Hunk #{r.hunk_index} ({status}):\n"
                f"  Before: {r.header_before}\n"
                f"  After:  {r.header_after}"
            )
        return "\n".join(lines)


@dataclass
class NormalizedPatchResult:
    patch: Patch
    report: NormalizationReport
    postimages: dict[str, str]

    def to_text(self) -> str:
        return emit_patch(self.patch)


def _clean_path(path: str | None) -> str | None:
    if path is None or path == "/dev/null":
        return None
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path


def _resolve_source(
    path: str | None, target_sources: Mapping[str, str]
) -> tuple[str, str]:
    cleaned = _clean_path(path)
    if cleaned is not None and cleaned in target_sources:
        return cleaned, target_sources[cleaned]
    if path is not None and path in target_sources:
        return path, target_sources[path]
    raise SourceMissingError(f"Target source not provided for path: {path}")


def _extract_preimage(hunk: Hunk) -> list[str]:
    return [
        line.text.rstrip("\r\n")
        for line in hunk.lines
        if isinstance(line, (ContextLine, RemovedLine))
    ]


def _match_section_context(
    lines: Sequence[str], candidate_idx: int, min_idx: int, section_context: str
) -> bool:
    if not section_context:
        return True
    ctx = section_context.strip()
    search_start = max(min_idx, candidate_idx - 100)
    for j in range(candidate_idx - 1, search_start - 1, -1):
        line = lines[j].strip()
        if ctx == line or line.startswith(ctx) or ctx in line:
            return True
        # If we hit an earlier function definition boundary that is not this context, stop scanning
        if line.endswith("{") and not (ctx in line):
            break
    return False


def normalize_patch_offsets(
    patch_or_text: Patch | str,
    target_sources: Mapping[str, str],
    *,
    verify_postimage: bool = True,
) -> NormalizedPatchResult:
    """Deterministically normalize hunk line offsets against bound target sources.

    Fails closed if context cannot be uniquely identified or if post-normalization
    offset-0 reapplication does not match the pre-normalization postimage.
    """
    if isinstance(patch_or_text, str):
        patch = parse_patch(patch_or_text)
    elif isinstance(patch_or_text, Patch):
        patch = copy.deepcopy(patch_or_text)
    else:
        raise TypeError("patch_or_text must be Patch or str")

    records: list[HunkNormalizationRecord] = []
    postimages: dict[str, str] = {}

    for file_patch in patch.files:
        if file_patch.binary_lines is not None or not file_patch.hunks:
            continue

        raw_path = file_patch.new_path or file_patch.old_path
        clean_path, source_text = _resolve_source(raw_path, target_sources)
        source_lines = [
            line.rstrip("\r\n")
            for line in source_text.splitlines(keepends=True)
        ]

        # First pass: find consensus offset across hunks with unique matches
        unique_offsets: set[int] = set()
        for hunk in file_patch.hunks:
            preimage = _extract_preimage(hunk)
            if not preimage:
                continue
            plen = len(preimage)
            cands = [
                i
                for i in range(len(source_lines) - plen + 1)
                if source_lines[i : i + plen] == preimage
            ]
            if len(cands) == 1:
                unique_offsets.add(cands[0] - (hunk.old_start - 1))
        consensus_offset = next(iter(unique_offsets)) if len(unique_offsets) == 1 else None

        # Second pass: sequential match and recomputation
        cursor = 0
        cumulative_delta = 0
        established_offset: int | None = None
        matched_indices: list[int] = []

        for hunk_idx, hunk in enumerate(file_patch.hunks, 1):
            preimage = _extract_preimage(hunk)
            plen = len(preimage)

            if plen == 0:
                # Pure insertion without context lines
                match_idx = hunk.old_start - 1
                if match_idx < cursor:
                    raise HunkOrderError(
                        f"Zero-preimage hunk in {clean_path} falls before cursor {cursor}",
                        path=clean_path,
                        hunk=f"#{hunk_idx}",
                    )
                cands = [match_idx]
            else:
                cands = [
                    i
                    for i in range(cursor, len(source_lines) - plen + 1)
                    if source_lines[i : i + plen] == preimage
                ]

            if not cands:
                raise ContextMismatchError(
                    f"Context mismatch in {clean_path} (Hunk #{hunk_idx}): preimage not found after line {cursor + 1}",
                    path=clean_path,
                    hunk=f"#{hunk_idx}",
                )

            if len(cands) > 1:
                # 1. Filter by section context if present
                if hunk.section_context:
                    sec_filtered = [
                        c
                        for c in cands
                        if _match_section_context(source_lines, c, cursor, hunk.section_context)
                    ]
                    if len(sec_filtered) == 1:
                        cands = sec_filtered
                    elif len(sec_filtered) > 1:
                        cands = sec_filtered

                # 2. Filter by established / consensus offset
                if len(cands) > 1:
                    target_offset = (
                        established_offset
                        if established_offset is not None
                        else consensus_offset
                    )
                    if target_offset is not None:
                        off_filtered = [
                            c
                            for c in cands
                            if (c - (hunk.old_start - 1)) == target_offset
                        ]
                        if len(off_filtered) == 1:
                            cands = off_filtered

            if len(cands) != 1:
                raise AmbiguousContextError(
                    f"Ambiguous context in {clean_path} (Hunk #{hunk_idx}): {len(cands)} matching locations found "
                    f"at lines {[c + 1 for c in cands]}; cannot uniquely disambiguate",
                    path=clean_path,
                    hunk=f"#{hunk_idx}",
                )

            match_idx = cands[0]
            matched_indices.append(match_idx)
            offset = match_idx - (hunk.old_start - 1)
            established_offset = offset

            new_old_start = match_idx + 1
            new_new_start = new_old_start + cumulative_delta

            records.append(
                HunkNormalizationRecord(
                    file_path=clean_path,
                    hunk_index=hunk_idx,
                    old_start_before=hunk.old_start,
                    old_count_before=hunk.old_count,
                    old_start_after=new_old_start,
                    old_count_after=hunk.old_count,
                    new_start_before=hunk.new_start,
                    new_count_before=hunk.new_count,
                    new_start_after=new_new_start,
                    new_count_after=hunk.new_count,
                    offset=offset,
                    section_context=hunk.section_context,
                )
            )

            hunk.old_start = new_old_start
            hunk.new_start = new_new_start

            cursor = match_idx + plen
            cumulative_delta += hunk.new_count - hunk.old_count

        # Build expected postimage from matched positions
        expected_output: list[str] = []
        cur = 0
        for hunk, m_idx in zip(file_patch.hunks, matched_indices):
            expected_output.extend(source_lines[cur:m_idx])
            cur = m_idx
            for line in hunk.lines:
                if isinstance(line, ContextLine):
                    expected_output.append(source_lines[cur])
                    cur += 1
                elif isinstance(line, RemovedLine):
                    cur += 1
                elif isinstance(line, AddedLine):
                    expected_output.append(line.text)
        expected_output.extend(source_lines[cur:])
        expected_postimage = "\n".join(expected_output)
        if source_text.endswith("\n"):
            expected_postimage += "\n"

        if verify_postimage:
            # Reapply normalized patch strictly at offset 0 (start == hunk.old_start - 1)
            reapplied_output: list[str] = []
            reapply_cur = 0
            for hunk_idx, hunk in enumerate(file_patch.hunks, 1):
                start = hunk.old_start - 1
                if start < reapply_cur or start > len(source_lines):
                    raise OffsetVerificationError(
                        f"Normalized hunk #{hunk_idx} start line {hunk.old_start} out of range in {clean_path}",
                        path=clean_path,
                        hunk=f"#{hunk_idx}",
                    )
                reapplied_output.extend(source_lines[reapply_cur:start])
                reapply_cur = start
                for line in hunk.lines:
                    if isinstance(line, ContextLine):
                        if (
                            reapply_cur >= len(source_lines)
                            or source_lines[reapply_cur] != line.text
                        ):
                            raise OffsetVerificationError(
                                f"Offset 0 context mismatch in {clean_path} at line {reapply_cur + 1}",
                                path=clean_path,
                                hunk=f"#{hunk_idx}",
                            )
                        reapplied_output.append(source_lines[reapply_cur])
                        reapply_cur += 1
                    elif isinstance(line, RemovedLine):
                        if (
                            reapply_cur >= len(source_lines)
                            or source_lines[reapply_cur] != line.text
                        ):
                            raise OffsetVerificationError(
                                f"Offset 0 removal mismatch in {clean_path} at line {reapply_cur + 1}",
                                path=clean_path,
                                hunk=f"#{hunk_idx}",
                            )
                        reapply_cur += 1
                    elif isinstance(line, AddedLine):
                        reapplied_output.append(line.text)
            reapplied_output.extend(source_lines[reapply_cur:])
            actual_postimage = "\n".join(reapplied_output)
            if source_text.endswith("\n"):
                actual_postimage += "\n"

            if actual_postimage != expected_postimage:
                raise OffsetVerificationError(
                    f"Postimage mismatch between pre-normalization and post-normalization for {clean_path}",
                    path=clean_path,
                )

        postimages[clean_path] = expected_postimage

    return NormalizedPatchResult(
        patch=patch,
        report=NormalizationReport(records=tuple(records)),
        postimages=postimages,
    )


__all__ = [
    "AmbiguousContextError",
    "ContextMismatchError",
    "HunkNormalizationRecord",
    "HunkOrderError",
    "NormalizationError",
    "NormalizationReport",
    "NormalizedPatchResult",
    "OffsetVerificationError",
    "SourceMissingError",
    "normalize_patch_offsets",
]
