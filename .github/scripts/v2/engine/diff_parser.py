import re
from typing import Optional, Tuple

from ..model.patch import (
    AddedLine, ContextLine, FilePatch, FileStatus, Hunk, NoNewlineMarker, Patch,
    RemovedLine,
)
from ..model.result import (
    InvalidHunkLine, MalformedFileHeader, MalformedHunkHeader,
    PatchParseError, UnsupportedPatchFormat,
)

DIFF_RE = re.compile(r"^diff --git (\S+) (\S+)$")
HUNK_RE = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: ?(.*))?$"
)


def _content(raw: str) -> str:
    return raw.rstrip("\r\n")


def _path_header(text: str) -> str:
    value = text[4:]
    return value.split("\t", 1)[0]


def _parse_diff_header(line: str, line_no: int) -> Tuple[str, str]:
    match = DIFF_RE.match(line)
    if not match:
        raise MalformedFileHeader("malformed diff --git header", line=line_no)
    return match.group(1), match.group(2)


def _start_file(line: str, line_no: int) -> FilePatch:
    old_path, new_path = _parse_diff_header(line, line_no)
    return FilePatch(line, old_path=old_path[2:] if old_path.startswith("a/") else old_path,
                     new_path=new_path[2:] if new_path.startswith("b/") else new_path)


def _parse_hunk_header(line: str, line_no: int) -> Hunk:
    if line.startswith("@@@"):  # combined diff marker
        raise UnsupportedPatchFormat("combined diff hunk is unsupported", line=line_no)
    match = HUNK_RE.match(line)
    if not match:
        raise MalformedHunkHeader("malformed hunk header", line=line_no)
    old_count = int(match.group(2) or 1)
    new_count = int(match.group(4) or 1)
    return Hunk(
        old_start=int(match.group(1)), old_count=old_count,
        new_start=int(match.group(3)), new_count=new_count,
        section_context=match.group(5) or "",
        old_count_omitted=match.group(2) is None,
        new_count_omitted=match.group(4) is None,
        source_line=line_no,
    )


def _set_header(file_patch: FilePatch, line: str, line_no: int):
    if line.startswith("old mode "):
        file_patch.old_mode = line[9:]
    elif line.startswith("new mode "):
        file_patch.new_mode = line[9:]
    elif line.startswith("new file mode "):
        file_patch.new_file_mode = line[len("new file mode "):]
    elif line.startswith("deleted file mode "):
        file_patch.deleted_file_mode = line[len("deleted file mode "):]
    elif line.startswith("index "):
        file_patch.index_line = line
    elif line.startswith("similarity index "):
        file_patch.similarity_index = line[17:]
    elif line.startswith("rename from "):
        file_patch.rename_from = line[12:]
    elif line.startswith("rename to "):
        file_patch.rename_to = line[10:]
    elif line.startswith("copy from "):
        file_patch.copy_from = line[10:]
    elif line.startswith("copy to "):
        file_patch.copy_to = line[8:]
    else:
        file_patch.extended_headers.append(line)


def parse_patch(text: str) -> Patch:
    if not isinstance(text, str):
        raise TypeError("patch input must be str")
    lines = text.splitlines(keepends=True)
    patch = Patch()
    current: Optional[FilePatch] = None
    current_hunk: Optional[Hunk] = None
    state = "PREAMBLE"
    binary = False

    def finish_hunk(line_no):
        nonlocal current_hunk
        if current_hunk is not None:
            try:
                current_hunk.validate()
            except PatchParseError:
                raise
            except Exception as exc:
                raise PatchParseError(str(exc), line=line_no) from exc
            current.hunks.append(current_hunk)
            current_hunk = None

    def finish_file(line_no):
        nonlocal current, binary
        finish_hunk(line_no)
        if current is not None:
            current.validate()
            patch.files.append(current)
        current = None
        binary = False

    for line_no, raw in enumerate(lines, 1):
        line = _content(raw)
        is_combined = line.startswith("diff --cc ") or line.startswith("diff --combined ")
        if is_combined:
            raise UnsupportedPatchFormat("combined diff is unsupported", line=line_no)

        if state != "HUNK" and line.startswith("diff --git"):
            if current is not None:
                finish_file(line_no)
            current = _start_file(line, line_no)
            state = "FILE_HEADER"
            continue

        if state == "PREAMBLE":
            if line.startswith("@@"):
                raise PatchParseError("hunk before file header", line=line_no)
            patch.preamble.append(line)
            continue

        if current is None:
            raise PatchParseError("unexpected patch structure", line=line_no)

        if binary:
            if line == "GIT binary patch":
                current.binary_lines.append(line)
            else:
                current.binary_lines.append(line)
            continue

        if state in ("FILE_HEADER", "TRAILER"):
            if line == "GIT binary patch":
                finish_hunk(line_no)
                current.binary_lines = []
                current.status = FileStatus.BINARY
                current.binary_lines.append(line)
                binary = True
                state = "BINARY"
            elif line.startswith("Binary files "):
                current.binary_lines = [line]
                current.status = FileStatus.BINARY
                binary = True
                state = "BINARY"
            elif line.startswith("--- "):
                current.old_header = line
                current.old_path = _path_header(line)
            elif line.startswith("+++ "):
                current.new_header = line
                current.new_path = _path_header(line)
            elif line.startswith("@@"):
                if current.old_header is None or current.new_header is None:
                    raise MalformedFileHeader("hunk before complete file headers", line=line_no)
                current_hunk = _parse_hunk_header(line, line_no)
                state = "HUNK"
            elif state == "TRAILER":
                current.trailing_lines.append(line)
            else:
                _set_header(current, line, line_no)
            continue

        if state == "HUNK":
            if line == "\\ No newline at end of file":
                if current_hunk is None or not current_hunk.lines:
                    raise InvalidHunkLine("no-newline marker without preceding line", line=line_no)
                current_hunk.lines.append(NoNewlineMarker(source_line=line_no))
            elif (line.startswith("-- ") or line == "") and current_hunk.calculated_counts() == (current_hunk.old_count, current_hunk.new_count):
                finish_hunk(line_no)
                state = "TRAILER"
                current.trailing_lines.append(line)
            elif line.startswith((" ", "+", "-")):
                if line.startswith("+"):
                    current_hunk.lines.append(AddedLine(line[1:], line_no))
                elif line.startswith("-"):
                    current_hunk.lines.append(RemovedLine(line[1:], line_no))
                else:
                    current_hunk.lines.append(ContextLine(line[1:], line_no))
            elif line.startswith("@@"):
                finish_hunk(line_no)
                current_hunk = _parse_hunk_header(line, line_no)
            elif line.startswith("diff --git"):
                finish_file(line_no)
                current = _start_file(line, line_no)
                state = "FILE_HEADER"
            else:
                raise InvalidHunkLine("invalid hunk line prefix", line=line_no)
            continue

    if current is not None:
        finish_file(len(lines) + 1)
        if patch.files[-1].trailing_lines:
            patch.trailer.extend(patch.files[-1].trailing_lines)
            patch.files[-1].trailing_lines.clear()
    elif state == "HUNK":
        raise PatchParseError("truncated hunk")
    return patch.validate()
