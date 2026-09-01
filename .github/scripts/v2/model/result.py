class PatchError(ValueError):
    """Base class for explicit structural patch failures."""

    def __init__(self, message, *, line=None, path=None, hunk=None):
        self.line = line
        self.path = path
        self.hunk = hunk
        details = []
        if line is not None:
            details.append(f"line {line}")
        if path:
            details.append(path)
        if hunk:
            details.append(hunk)
        prefix = f"({' / '.join(details)}) " if details else ""
        super().__init__(prefix + message)


class PatchParseError(PatchError):
    pass


class MalformedFileHeader(PatchParseError):
    pass


class MalformedHunkHeader(PatchParseError):
    pass


class InvalidHunkLine(PatchParseError):
    pass


class HunkCountMismatch(PatchParseError):
    pass


class UnsupportedPatchFormat(PatchParseError):
    pass


class PatchEmitError(PatchError):
    pass
