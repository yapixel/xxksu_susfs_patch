from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

from .result import HunkCountMismatch, PatchError


class FileStatus(str, Enum):
    MODIFIED = "modified"
    ADDED = "added"
    DELETED = "deleted"
    RENAMED = "renamed"
    COPIED = "copied"
    MODE_ONLY = "mode-only"
    BINARY = "binary"


@dataclass
class PatchLine:
    text: str
    source_line: Optional[int] = None

    @property
    def prefix(self) -> str:
        raise NotImplementedError

    @property
    def kind(self) -> str:
        return type(self).__name__


@dataclass
class ContextLine(PatchLine):
    @property
    def prefix(self) -> str:
        return " "


@dataclass
class AddedLine(PatchLine):
    @property
    def prefix(self) -> str:
        return "+"


@dataclass
class RemovedLine(PatchLine):
    @property
    def prefix(self) -> str:
        return "-"


@dataclass
class NoNewlineMarker(PatchLine):
    text: str = "\\ No newline at end of file"

    def __post_init__(self):
        if self.text != "\\ No newline at end of file":
            raise PatchError("invalid no-newline marker text")

    @property
    def prefix(self) -> str:
        return ""


@dataclass
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    section_context: str = ""
    lines: List[PatchLine] = field(default_factory=list)
    old_count_omitted: bool = False
    new_count_omitted: bool = False
    source_line: Optional[int] = None

    def __post_init__(self):
        if min(self.old_start, self.new_start) < 0:
            raise PatchError("hunk start positions must be non-negative")
        if min(self.old_count, self.new_count) < 0:
            raise PatchError("hunk counts must be non-negative")
        # Count validation happens when a complete hunk is parsed or attached
        # to a FilePatch; parser construction necessarily starts with no lines.

    def calculated_counts(self) -> Tuple[int, int]:
        old_count = sum(isinstance(line, (ContextLine, RemovedLine)) for line in self.lines)
        new_count = sum(isinstance(line, (ContextLine, AddedLine)) for line in self.lines)
        return old_count, new_count

    def validate(self, *, check_counts=True):
        previous = None
        for line in self.lines:
            if isinstance(line, NoNewlineMarker):
                if previous is None or isinstance(previous, NoNewlineMarker):
                    raise PatchError("no-newline marker must follow a normal hunk line")
            elif not isinstance(line, (ContextLine, AddedLine, RemovedLine)):
                raise PatchError("unknown hunk line type")
            previous = line
        old_count, new_count = self.calculated_counts()
        if check_counts and (self.old_count, self.new_count) != (old_count, new_count):
            raise HunkCountMismatch(
                f"hunk declares {self.old_count}/{self.new_count}, "
                f"contains {old_count}/{new_count} lines",
                line=self.source_line,
            )

    def emitted_counts(self) -> Tuple[int, int]:
        return self.calculated_counts()


@dataclass
class FilePatch:
    diff_header: str
    old_path: Optional[str] = None
    new_path: Optional[str] = None
    status: FileStatus = FileStatus.MODIFIED
    old_mode: Optional[str] = None
    new_mode: Optional[str] = None
    new_file_mode: Optional[str] = None
    deleted_file_mode: Optional[str] = None
    index_line: Optional[str] = None
    similarity_index: Optional[str] = None
    rename_from: Optional[str] = None
    rename_to: Optional[str] = None
    copy_from: Optional[str] = None
    copy_to: Optional[str] = None
    extended_headers: List[str] = field(default_factory=list)
    old_header: Optional[str] = None
    new_header: Optional[str] = None
    hunks: List[Hunk] = field(default_factory=list)
    binary_lines: Optional[List[str]] = None
    trailing_lines: List[str] = field(default_factory=list)

    def infer_status(self):
        if self.binary_lines is not None:
            self.status = FileStatus.BINARY
        elif self.rename_from is not None or self.rename_to is not None:
            self.status = FileStatus.RENAMED
        elif self.copy_from is not None or self.copy_to is not None:
            self.status = FileStatus.COPIED
        elif self.old_path == "/dev/null" or self.new_file_mode is not None:
            self.status = FileStatus.ADDED
        elif self.new_path == "/dev/null" or self.deleted_file_mode is not None:
            self.status = FileStatus.DELETED
        elif not self.hunks and (self.old_mode or self.new_mode):
            self.status = FileStatus.MODE_ONLY

    def validate(self, *, check_counts=True):
        self.infer_status()
        for hunk in self.hunks:
            hunk.validate(check_counts=check_counts)
        if self.hunks and (self.old_header is None or self.new_header is None):
            raise PatchError("textual hunks require --- and +++ file headers", path=self.new_path or self.old_path)


@dataclass
class Patch:
    preamble: List[str] = field(default_factory=list)
    files: List[FilePatch] = field(default_factory=list)
    trailer: List[str] = field(default_factory=list)

    def validate(self, *, check_counts=True):
        for file_patch in self.files:
            file_patch.validate(check_counts=check_counts)
        return self

    def structural_key(self):
        def line_key(line):
            return (type(line).__name__, line.text)

        def hunk_key(hunk):
            old_count, new_count = hunk.calculated_counts()
            return (hunk.old_start, old_count, hunk.new_start, new_count,
                    hunk.section_context, tuple(line_key(line) for line in hunk.lines))

        def file_key(file_patch):
            return (
                file_patch.diff_header, file_patch.old_path, file_patch.new_path,
                file_patch.status.value, file_patch.old_mode, file_patch.new_mode,
                file_patch.new_file_mode, file_patch.deleted_file_mode,
                file_patch.index_line, file_patch.similarity_index,
                file_patch.rename_from, file_patch.rename_to,
                file_patch.copy_from, file_patch.copy_to,
                tuple(file_patch.extended_headers), file_patch.old_header,
                file_patch.new_header, tuple(hunk_key(h) for h in file_patch.hunks),
                tuple(file_patch.binary_lines) if file_patch.binary_lines is not None else None,
                tuple(file_patch.trailing_lines),
            )

        return (tuple(self.preamble), tuple(file_key(f) for f in self.files), tuple(self.trailer))

    def to_text(self) -> str:
        from ..engine.emitter import emit_patch
        return emit_patch(self)
