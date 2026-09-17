"""Base target adapter interface and strict anchor mechanics."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Optional, Tuple

from ..model.manifest import KNOWN_TARGETS
from ..source.bundle import MissingBundleFile, SourceBundle, UnsupportedKernelVersion as BundleUnsupportedKernelVersion, UnsupportedTarget as BundleUnsupportedTarget


class AdapterError(ValueError):
    """Base error for target adapter operations."""
    pass


class UnsupportedTarget(AdapterError):
    pass


class UnsupportedKernelVersion(AdapterError):
    pass


class MissingSemanticAnchor(AdapterError):
    pass


class MultipleSemanticAnchors(AdapterError):
    pass


class AmbiguousSemanticMatch(MultipleSemanticAnchors):
    pass


class AnchorConflict(AdapterError):
    pass


@dataclass(frozen=True)
class AnchorLocation:
    file_path: str
    line_number: int
    line_count: int
    matched_text: str
    function: Optional[str] = None
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "line_number": self.line_number,
            "line_count": self.line_count,
            "matched_text": self.matched_text,
            "function": self.function,
        }


@dataclass(frozen=True)
class AnchorSpec:
    file_path: str
    anchor_text: str
    function: Optional[str] = None
    expected_matches: int = 1
    context_before: Tuple[str, ...] = ()
    context_after: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.file_path or not self.anchor_text:
            raise AdapterError("AnchorSpec requires file_path and anchor_text")
        if self.expected_matches < 1:
            raise AdapterError("expected_matches must be at least 1")


def find_function_span(source_text: str, function: str) -> tuple[int, int]:
    """Locate the exact character span (open_brace, close_brace) for a C function definition."""
    if not function or not isinstance(function, str):
        raise AdapterError("function name must be a non-empty string")

    # Patterns for C function headers
    header_patterns = [
        re.compile(r'SYSCALL_DEFINE\d\s*\(\s*' + re.escape(function) + r'\b[^)]*\)', re.MULTILINE),
        re.compile(r'(?:^|\n)[ \t]*(?:(?:static|inline|extern|__init|asmlinkage|unsigned|long|int|void|bool|struct\s+[a-zA-Z0-9_]+|\*)\s+)+' + re.escape(function) + r'\s*\([^;]*?\)', re.MULTILINE),
        re.compile(r'(?:^|\n)[^\n;]*?\b' + re.escape(function) + r'\s*\([^;]*?\)', re.MULTILINE),
    ]

    match_start = -1
    search_from = 0
    open_brace_idx = -1

    for pattern in header_patterns:
        for m in pattern.finditer(source_text):
            # Look ahead for opening brace, skipping whitespace and attributes
            tail = source_text[m.end():]
            brace_match = re.match(r'^[ \t\n]*(?:__[a-zA-Z0-9_()]+[ \t\n]*)*\{', tail)
            if brace_match:
                open_brace_idx = m.end() + brace_match.end() - 1
                match_start = m.start()
                break
        if open_brace_idx != -1:
            break

    if open_brace_idx == -1:
        raise MissingSemanticAnchor(f"function definition for {function!r} not found")

    idx = open_brace_idx
    depth = 0
    in_string = False
    in_char = False
    in_line_comment = False
    in_block_comment = False
    text_len = len(source_text)

    while idx < text_len:
        c = source_text[idx]
        if in_line_comment:
            if c == '\n':
                in_line_comment = False
        elif in_block_comment:
            if c == '*' and idx + 1 < text_len and source_text[idx + 1] == '/':
                in_block_comment = False
                idx += 1
        elif in_string:
            if c == '\\':
                idx += 1
            elif c == '"':
                in_string = False
        elif in_char:
            if c == '\\':
                idx += 1
            elif c == "'":
                in_char = False
        else:
            if c == '/' and idx + 1 < text_len:
                if source_text[idx + 1] == '/':
                    in_line_comment = True
                    idx += 1
                elif source_text[idx + 1] == '*':
                    in_block_comment = True
                    idx += 1
            elif c == '"':
                in_string = True
            elif c == "'":
                in_char = True
            elif c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return (open_brace_idx, idx + 1)
        idx += 1

    raise MissingSemanticAnchor(f"function boundary for {function!r} did not balance braces")


def _check_context(source_text: str, match_offset: int, match_len: int,
                   context_before: Tuple[str, ...], context_after: Tuple[str, ...]) -> bool:
    if context_before:
        before_text = source_text[:match_offset]
        lines_before = [l.strip() for l in before_text.splitlines() if l.strip()]
        needed_before = [c.strip() for c in context_before if c.strip()]
        if len(lines_before) < len(needed_before):
            return False
        if lines_before[-len(needed_before):] != needed_before:
            return False

    if context_after:
        after_text = source_text[match_offset + match_len:]
        lines_after = [l.strip() for l in after_text.splitlines() if l.strip()]
        needed_after = [c.strip() for c in context_after if c.strip()]
        if len(lines_after) < len(needed_after):
            return False
        if lines_after[:len(needed_after)] != needed_after:
            return False

    return True


class TargetAdapter:
    target_id: str
    adapter_id: str
    supported_kernel_families: Tuple[str, ...] = ()

    def identify(self) -> dict[str, str]:
        return {
            "target_id": self.target_id,
            "adapter_id": self.adapter_id,
        }

    def validate_kernel_version(self, kernel_version: str) -> None:
        if not kernel_version or not isinstance(kernel_version, str):
            raise UnsupportedKernelVersion("kernel version must be a non-empty string")
        for family in self.supported_kernel_families:
            if kernel_version == family or kernel_version.startswith(family + ".") or kernel_version.startswith(family + "-"):
                return
        raise UnsupportedKernelVersion(
            f"kernel version {kernel_version} not supported by adapter {self.adapter_id} "
            f"(supported: {self.supported_kernel_families})"
        )

    def locate_anchor(
        self,
        source_text: str,
        anchor: str | AnchorSpec,
        *,
        file_path: Optional[str] = None,
        function: Optional[str] = None,
    ) -> AnchorLocation:
        if not isinstance(source_text, str):
            raise AdapterError("source_text must be a string")

        if isinstance(anchor, AnchorSpec):
            spec = anchor
            eff_path = spec.file_path
            eff_func = spec.function
            anchor_text = spec.anchor_text
        else:
            if not isinstance(anchor, str):
                raise AdapterError("anchor must be an AnchorSpec or string")
            eff_path = file_path or "unknown"
            eff_func = function
            spec = AnchorSpec(file_path=eff_path, anchor_text=anchor, function=eff_func)
            anchor_text = anchor

        search_base_offset = 0
        search_text = source_text

        if eff_func:
            func_start, func_end = find_function_span(source_text, eff_func)
            search_base_offset = func_start
            search_text = source_text[func_start:func_end]

        # Find occurrences
        occurrences: list[int] = []
        pos = 0
        while True:
            idx = search_text.find(anchor_text, pos)
            if idx == -1:
                break
            occurrences.append(idx)
            pos = idx + len(anchor_text)

        # Context filtering if requested
        if spec.context_before or spec.context_after:
            filtered = []
            for occ in occurrences:
                global_offset = search_base_offset + occ
                if _check_context(source_text, global_offset, len(anchor_text),
                                  spec.context_before, spec.context_after):
                    filtered.append(occ)
            occurrences = filtered

        location_desc = f"{eff_path}:{eff_func}" if eff_func else eff_path

        if len(occurrences) == 0:
            raise MissingSemanticAnchor(f"anchor not found in {location_desc}: {anchor_text!r}")

        if len(occurrences) > spec.expected_matches:
            raise MultipleSemanticAnchors(
                f"ambiguous anchor in {location_desc}: expected {spec.expected_matches} match, "
                f"found {len(occurrences)} occurrences of {anchor_text!r}"
            )

        match_offset = search_base_offset + occurrences[0]
        line_number = source_text[:match_offset].count('\n') + 1
        line_count = anchor_text.count('\n') + 1

        return AnchorLocation(
            file_path=eff_path,
            line_number=line_number,
            line_count=line_count,
            matched_text=anchor_text,
            function=eff_func,
            start_offset=match_offset,
            end_offset=match_offset + len(anchor_text),
        )

    def locate_anchor_in_bundle(
        self,
        bundle: SourceBundle,
        anchor: str | AnchorSpec,
        *,
        file_path: Optional[str] = None,
        function: Optional[str] = None,
    ) -> AnchorLocation:
        self.validate_source_bundle(bundle)
        target_path = anchor.file_path if isinstance(anchor, AnchorSpec) else file_path
        if not target_path:
            raise AdapterError("file_path must be specified when locating anchor in bundle")

        file_entry = bundle.get_file(target_path)
        if file_entry.content is None:
            raise MissingBundleFile(f"file content for {target_path} not loaded in bundle")

        return self.locate_anchor(
            file_entry.content,
            anchor,
            file_path=target_path,
            function=anchor.function if isinstance(anchor, AnchorSpec) else function,
        )

    def validate_source_bundle(self, bundle: SourceBundle) -> None:
        if bundle.target_id != self.target_id:
            raise UnsupportedTarget(
                f"bundle target {bundle.target_id} does not match adapter target {self.target_id}"
            )
        try:
            self.validate_kernel_version(bundle.kernel_version)
        except BundleUnsupportedKernelVersion as exc:
            raise UnsupportedKernelVersion(str(exc)) from exc

    def get_anchor_spec(self, key: str) -> AnchorSpec:
        raise KeyError(f"unknown anchor key: {key}")

    def get_fixture_anchor_spec(self, fixture_name: str, operation_id: str) -> Optional[AnchorSpec]:
        return None

    def adapt_fixture(self, bundle: SourceBundle, fixture_name: str) -> Any:
        from .fixtures import adapt_fixture_for_adapter
        return adapt_fixture_for_adapter(self, bundle, fixture_name)

    def adapt_fixtures(self, bundle: SourceBundle, fixture_names: Any = None) -> Any:
        from .fixtures import FIXED_FIXTURES, adapt_fixtures_for_adapter
        fnames = FIXED_FIXTURES if fixture_names is None else fixture_names
        return adapt_fixtures_for_adapter(self, bundle, fnames)
