from ..model.patch import AddedLine, ContextLine, NoNewlineMarker, RemovedLine
from ..model.result import PatchEmitError


def _line(value: str) -> str:
    return value if value.endswith("\n") else value + "\n"


def _hunk_header(hunk) -> str:
    old_count, new_count = hunk.emitted_counts()
    old = f"{hunk.old_start},{old_count}"
    new = f"{hunk.new_start},{new_count}"
    suffix = f" {hunk.section_context}" if hunk.section_context else ""
    return f"@@ -{old} +{new} @@{suffix}\n"


def emit_patch(patch) -> str:
    if not hasattr(patch, "files"):
        raise PatchEmitError("expected Patch instance")
    # Emission recomputes hunk counts, so stale declared counts after a model
    # mutation are not an emission error. Line and marker invariants still run.
    patch.validate(check_counts=False)
    output = []
    output.extend(_line(line) for line in patch.preamble)
    for file_patch in patch.files:
        output.append(_line(file_patch.diff_header))
        if file_patch.old_mode:
            output.append(_line(f"old mode {file_patch.old_mode}"))
        if file_patch.new_mode:
            output.append(_line(f"new mode {file_patch.new_mode}"))
        if file_patch.new_file_mode:
            output.append(_line(f"new file mode {file_patch.new_file_mode}"))
        if file_patch.deleted_file_mode:
            output.append(_line(f"deleted file mode {file_patch.deleted_file_mode}"))
        if file_patch.index_line:
            output.append(_line(file_patch.index_line))
        if file_patch.similarity_index:
            output.append(_line(f"similarity index {file_patch.similarity_index}"))
        if file_patch.rename_from is not None:
            output.append(_line(f"rename from {file_patch.rename_from}"))
        if file_patch.rename_to is not None:
            output.append(_line(f"rename to {file_patch.rename_to}"))
        if file_patch.copy_from is not None:
            output.append(_line(f"copy from {file_patch.copy_from}"))
        if file_patch.copy_to is not None:
            output.append(_line(f"copy to {file_patch.copy_to}"))
        output.extend(_line(line) for line in file_patch.extended_headers)
        if file_patch.old_header is not None:
            output.append(_line(file_patch.old_header))
        if file_patch.new_header is not None:
            output.append(_line(file_patch.new_header))
        if file_patch.binary_lines is not None:
            output.extend(_line(line) for line in file_patch.binary_lines)
        for hunk in file_patch.hunks:
            output.append(_hunk_header(hunk))
            for line in hunk.lines:
                if isinstance(line, NoNewlineMarker):
                    output.append(_line(line.text))
                elif isinstance(line, (ContextLine, AddedLine, RemovedLine)):
                    output.append(_line(line.prefix + line.text))
                else:
                    raise PatchEmitError(f"unknown hunk line type: {type(line).__name__}")
        output.extend(_line(line) for line in file_patch.trailing_lines)
    output.extend(_line(line) for line in patch.trailer)
    return "".join(output)
