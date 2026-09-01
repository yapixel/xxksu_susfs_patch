# xxKSU + SuSFS V2.1 Implementation Report

## 1. Executive Result

V2.1 implements the generic structural foundation only: typed patch models, a
state-aware unified diff parser, a deterministic emitter, and 16 focused tests.
No semantic transformation, target/profile logic, fixture adaptation, or later
V2 phase was implemented.

## 2. Files Created / Modified

Created:

- `.github/scripts/v2/__init__.py`
- `.github/scripts/v2/model/__init__.py`
- `.github/scripts/v2/model/patch.py`
- `.github/scripts/v2/model/result.py`
- `.github/scripts/v2/engine/__init__.py`
- `.github/scripts/v2/engine/diff_parser.py`
- `.github/scripts/v2/engine/emitter.py`
- `.github/scripts/v2/tests/__init__.py`
- `.github/scripts/v2/tests/test_diff.py`
- `XXKSU_SUSFS_V2_1_REPORT.md`

Modified existing files: none. Existing generators, patches, fixtures, workflows,
and prior reports/tasks were left untouched.

## 3. Core Model Implementation

The model uses Python `dataclasses` and `Enum` with no external dependency.
`Patch`, `FilePatch`, `Hunk`, and typed line classes retain structural data and
validate at parser/file boundaries. Future semantic records were intentionally
not added.

## 4. Patch Model

`Patch` stores ordered preamble lines, `FilePatch` records, and trailing format-
patch metadata. `structural_key()` compares normalized structural content while
ignoring source line numbers and hunk count spelling.

## 5. FilePatch Model

`FilePatch` retains raw `diff --git` text, old/new paths, status, mode fields,
index, similarity, rename/copy metadata, unknown extended headers, `---`/`+++`
headers, hunks, opaque binary lines, and inter-file trailing lines. It infers
modified/added/deleted/renamed/copied/mode-only/binary status without discarding
metadata.

## 6. Hunk Model

`Hunk` stores integer starts/counts, section context, ordered typed lines, and
whether counts were omitted in the input. Counts are validated against line
kinds; emission always recalculates them.

## 7. Patch Line Model

`ContextLine`, `AddedLine`, and `RemovedLine` retain content exactly after the
single diff prefix, including meaningful whitespace and optional source line
number. `NoNewlineMarker` is a distinct typed line and is not counted.

## 8. Parser Architecture

`parse_patch(text)` uses bounded grammar regexes only for `diff --git` and hunk
headers. It parses line-by-line into typed objects, validates headers and counts,
and never performs project-specific keyword filtering.

## 9. Parser State Machine

The explicit states are `PREAMBLE`, `FILE_HEADER`, `HUNK`, `TRAILER`, and
`BINARY`. A `diff --git` boundary is recognized only outside `HUNK`; therefore
source text inside a hunk cannot create a file boundary. Completed-hunk separators
are retained at their file position, while final trailer lines are promoted to
`Patch.trailer`.

## 10. Supported Unified Diff Syntax

Supported syntax includes ordinary Git diffs, format-patch preambles/trailers,
multiple files/hunks, omitted hunk counts, section context, `/dev/null` create/
delete paths, mode-only changes, index/mode headers, rename/copy metadata, unknown
extended headers, no-newline markers, `GIT binary patch`, and `Binary files ...
differ` opaque sections.

## 11. Unsupported / Explicitly Rejected Syntax

Combined `diff --cc`/`diff --combined` formats, malformed file/hunk headers,
invalid hunk prefixes, incomplete file headers, count mismatches, unexpected
pre-file hunks, and misplaced no-newline markers raise typed errors. Binary
payloads are not decoded; they are preserved opaquely.

## 12. Metadata Preservation

Known Git fields are modeled explicitly. Unknown valid extended headers remain in
ordered `extended_headers`. Raw diff/file headers, preamble, inter-file
separators, and final trailer lines are retained, so metadata is not silently
lost.

## 13. Hunk Count Validation

`Hunk.validate()` checks `old_count = context + removed` and
`new_count = context + added`; markers contribute zero. Parsing fails with
`HunkCountMismatch`, including source line when available. The emitter validates
line invariants with stale-count tolerance and writes recalculated counts.

## 14. Emitter Architecture

`emit_patch(patch)` emits typed preamble, file metadata, headers, opaque binary
content, hunks, in-file separators, and final trailer. Hunk lines are emitted from
their class prefix, never from original raw hunk text.

## 15. Deterministic Emission

Emission preserves model ordering, uses fixed newline output (`\n`), does not sort
hunk lines, and has no dependence on locale, Git configuration, timestamps, or
filesystem paths. Hunk headers are normalized to explicit counts.

## 16. Round-Trip Contract

Tests enforce `parse(emit(parse(text))).structural_key()` equality for synthetic
patches and repository fixtures. Canonical 11 and manual fixture inputs also
emit byte-for-byte identically. Count omission spelling is intentionally
normalized; semantic counts and all content remain equivalent.

## 17. Error Model

`PatchError` carries optional line/path/hunk context. V2.1 defines
`PatchParseError`, `MalformedFileHeader`, `MalformedHunkHeader`,
`InvalidHunkLine`, `HunkCountMismatch`, `UnsupportedPatchFormat`, and
`PatchEmitError`. The future semantic error hierarchy is not implemented.

## 18. Test Architecture

The standard-library `unittest` suite is in `.github/scripts/v2/tests/test_diff.py`.
It combines synthetic positive/negative cases, model invariant checks, and real
repository patch samples. No test dependency or project configuration was added.

## 19. Synthetic Test Coverage

Covered cases include basic edits, multiple files, multiple hunks, omitted counts,
section context, new/deleted files, mode-only changes, rename/copy metadata,
unknown headers, both no-newline scenarios, zero-count hunks, binary sections,
inter-file ordering, metadata-like source lines, and emitter count recomputation
after model mutation.

## 20. Repository Fixture Coverage

The suite round-trips the complete existing `patches/xxksu/11_enable_susfs_for_ksu.patch`
and `.github/fixtures/scope-min-manual-hooks-v2.3.patch`. It parses and round-trips
a complete valid file patch sampled from the existing GKI 6.1 51 patch. The full
legacy GKI 6.1 51 artifact is also tested as an explicit fail-closed malformed
input because it contains unprefixed/count-inconsistent legacy hunks.

## 21. Negative Test Coverage

Tests explicitly reject malformed `diff --git`, malformed hunk headers, incomplete
file headers, invalid prefixes, old/new count mismatches, truncated hunks,
misplaced no-newline markers, unexpected pre-file hunks, and combined diffs.
Binary input is tested for opaque preservation rather than decoding.

## 22. Commands Executed

From WSL Debian (Python 3.11.2):

```text
python3 -m compileall -q .github/scripts/v2
PYTHONPATH=.github/scripts python3 -m unittest discover -s .github/scripts/v2/tests -v
PYTHONPATH=.github/scripts python3 -c "import v2; print(v2.parse_patch(\"\").structural_key())"
```

The compile/import command was run alongside the final test command; the separate
byte-stability check also compared the complete 11 and manual fixture outputs.

## 23. Test Results

All 16 tests passed. `compileall` completed successfully. The import smoke check
returned `((), (), ())`. Complete 11 and manual fixture emission was byte-stable.

## 24. Git Status Before / After

Before implementation, the worktree already contained unrelated modified files
and untracked Phase/design documents. No cleanup commands, staging, commits,
reset, checkout, restore, or stash operations were used. After implementation,
the only files added by this task are the nine V2.1 package/test files and this
report; pre-existing worktree entries remain unchanged.

## 25. Design Deviations

No architecture deviation was introduced. The emitter normalizes omitted hunk
count spelling to explicit counts, which is allowed by the V2.1 round-trip
contract. Inter-file trailing lines were modeled explicitly to preserve ordering.

## 26. Remaining V2.1 Limitations

Binary deltas remain opaque, quoted paths with complex Git escaping are not
decoded, and there is no full email/MIME parser. These are deliberate V2.1
boundaries. Semantic units, source-tree mutation, adapters, manifests, ABI
contracts, and profile validation remain for later phases.

## 27. V2.2 Readiness

The structural foundation is stable enough to begin V2.2 after human review:
typed parsing/emission, strict malformed-input behavior, metadata preservation,
and round-trip tests are in place. This status does not authorize V2.2 in this
run.

## 28. Confidence Report

| Area | Confidence | Evidence |
|---|---|---|
| typed patch/file/hunk/line model | HIGH | model invariant and round-trip tests |
| state-aware parser | HIGH | boundary, malformed, and real-patch tests |
| hunk count validation | HIGH | positive, mutation, and mismatch tests |
| metadata preservation | HIGH | mode/rename/copy/unknown-header tests |
| no-newline handling | HIGH | removal/addition marker round trip |
| binary boundary | HIGH (opaque) | both binary marker forms tested |
| combined diff rejection | HIGH | explicit negative test |
| real corpus compatibility | HIGH for valid inputs | complete 11/fixture plus valid 51 sample |
| legacy malformed patch behavior | HIGH (fail closed) | explicit full-51 rejection test |
| future semantic readiness | MEDIUM | structural API is ready; later phases unimplemented |

V2.1 CORE MODELS COMPLETE: YES
V2.1 DIFF PARSER/EMITTER COMPLETE: YES
V2.1 TESTS PASS: YES
SAFE TO BEGIN V2.2: YES
