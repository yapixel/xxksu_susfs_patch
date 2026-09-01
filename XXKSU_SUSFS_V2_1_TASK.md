# xxKSU + SuSFS V2.1 — Core Models & Unified Diff Parser/Emitter

## Phase

V2.1 — Core Data Models + Unified Diff Parser/Emitter

## Status

IMPLEMENTATION AUTHORIZED FOR V2.1 ONLY.

This task authorizes implementation of the V2.1 foundation described in:

```text
./XXKSU_SUSFS_V2_DESIGN.md
```

It does NOT authorize V2.2 or any later V2 phase.

After V2.1 is implemented, tested, and documented:

**STOP.**

Do not continue into semantic transformation, manifests, adapters, fixtures, 10→11, 50→51, profile composition, build validation, workflow changes, or cutover work.

---

# 1. Read the Project Contract First

Before modifying anything, read these files in this exact order:

```text
./XXKSU_SUSFS_PHASE1_5_REPORT.md
./XXKSU_SUSFS_PHASE1_6_REPORT.md
./XXKSU_SUSFS_V2_DESIGN.md
./XXKSU_SUSFS_V2_1_TASK.md
```

Use:

```text
Phase 1.5
```

as the semantic/evidence baseline.

Use:

```text
Phase 1.6
```

as the authoritative dual-mode target/profile contract.

Use:

```text
XXKSU_SUSFS_V2_DESIGN.md
```

as the authoritative V2 architecture specification.

Use this task as the authoritative implementation scope for this run.

Do not redesign the architecture during V2.1.

If implementation reveals a contradiction in the design, STOP and document it rather than silently changing the architecture.

---

# 2. V2.1 Objective

Implement the smallest reliable foundation required by later V2 phases:

```text
typed core data models
+
unified diff parser
+
unified diff emitter
+
round-trip tests
+
malformed-input tests
```

V2.1 must establish a trustworthy structural representation of patch files.

It must eliminate dependence on uncontrolled string splitting for future V2 semantic processing.

V2.1 does NOT perform semantic transformation.

---

# 3. Authoritative V2.1 Design Requirements

The V2 design defines the core model as including records such as:

```text
InputRef
TargetRef
Patch
SemanticUnit
Operation
OwnerClaim
ProfileManifest
ValidationResult
Provenance
```

However, V2.1 must implement only the models required now for:

```text
unified diff parsing
unified diff emission
basic structured results/errors
future-compatible type boundaries
```

Do NOT prematurely implement the full semantic/manifest/provenance architecture belonging to later phases.

The design also requires a typed unified-diff representation containing at least:

```text
Patch
FilePatch
Hunk

ContextLine
AddedLine
RemovedLine
NoNewlineMarker

patch/file metadata
```

The parser must retain enough information to reconstruct a valid patch without relying on raw string heuristics.

---

# 4. Scope

V2.1 is limited to the following implementation areas.

## 4.1 Package skeleton

Create the minimum V2 package structure necessary for V2.1.

Expected conceptual structure:

```text
.github/scripts/v2/
├── __init__.py
├── model/
│   ├── __init__.py
│   ├── patch.py
│   └── result.py
├── engine/
│   ├── __init__.py
│   ├── diff_parser.py
│   └── emitter.py
└── tests/
    ├── __init__.py
    └── ...
```

The exact file split may differ if a simpler organization is justified.

Do not create empty placeholder modules for later phases merely to match the final architecture diagram.

Only create files required by V2.1.

---

# 5. Unified Diff Data Model

Implement a typed representation for unified Git patches.

At minimum model:

```text
Patch
FilePatch
Hunk
PatchLine
ContextLine
AddedLine
RemovedLine
NoNewlineMarker
```

The model must preserve the structural information necessary for parsing, validation, and deterministic re-emission.

---

# 6. Patch Model

`Patch` should represent one parsed patch document.

It must be capable of retaining applicable top-level metadata such as:

```text
format-patch/mail headers if present
commit metadata if present
subject if present
free-form pre-diff header lines if present
file patches
trailing metadata if present
```

Do not assume every input is produced by `git format-patch`.

The parser should support ordinary Git unified diff input such as:

```text
diff --git a/foo.c b/foo.c
...
```

as well as format-patch style input where reasonably possible.

Do not implement MIME/email parsing beyond what is necessary for repository patch inputs.

---

# 7. FilePatch Model

A `FilePatch` must retain enough information for:

```text
old path
new path
old mode
new mode
new file mode
deleted file mode
index metadata
rename metadata where present
copy metadata where present
file status
extended Git headers
hunks
```

Do not reduce a file patch to:

```text
filename + list[hunk]
```

because later V2 phases may need creation/deletion/mode/path information.

Unknown but valid Git extended headers should not be silently discarded.

Preserve them structurally or as ordered metadata records.

---

# 8. Hunk Model

A `Hunk` must represent at least:

```text
old_start
old_count
new_start
new_count
section_context
ordered lines
```

Support hunk headers such as:

```text
@@ -10,7 +10,8 @@ function_name
```

and omitted-count forms such as:

```text
@@ -10 +10 @@
@@ -10 +10,2 @@
@@ -10,2 +10 @@
```

The model must distinguish the semantic count value:

```text
omitted count = 1
```

from any raw textual representation if necessary.

---

# 9. Patch Line Model

Do not represent all hunk lines as untyped strings.

At minimum distinguish:

```text
ContextLine
AddedLine
RemovedLine
NoNewlineMarker
```

Each normal hunk line should retain:

```text
text/content
line kind
source position if useful
```

Do not strip meaningful whitespace.

For C/kernel patches, leading tabs and spaces are semantically important.

---

# 10. No-Newline Marker

Correctly support:

```text
\ No newline at end of file
```

This marker is associated with the preceding patch line.

Do not treat it as:

```text
context
addition
removal
```

Do not silently discard it.

Round-trip tests must include it.

---

# 11. Parser Contract

Implement a deterministic parser with an API conceptually similar to:

```python
parse_patch(text: str) -> Patch
```

or an equally clear alternative.

The parser must:

```text
parse supported patch structure completely
preserve relevant metadata
validate hunk headers
validate line prefixes
validate hunk counts
detect malformed structure
fail explicitly
never silently skip malformed hunks
```

No semantic SuSFS/KernelSU interpretation belongs in the parser.

---

# 12. Parser Must Be Structural

The parser may use bounded regex for grammar elements such as:

```text
diff --git
@@ ... @@
index ...
mode headers
--- / +++ headers
```

That is acceptable.

What is forbidden is using arbitrary semantic keyword filtering such as:

```text
if "ksu_handle_" in line:
    ...
```

V2.1 knows nothing about KSU/SuSFS semantic ownership.

Its responsibility is patch syntax and structure only.

---

# 13. Hunk Count Validation

For every hunk, validate:

```text
old_count ==
    ContextLine count
  + RemovedLine count

new_count ==
    ContextLine count
  + AddedLine count
```

`NoNewlineMarker` contributes to neither count.

A mismatch must fail parsing or explicit structural validation.

Do not silently repair malformed input during parsing.

---

# 14. File Boundary Detection

Correctly identify file patch boundaries.

Do not accidentally interpret text inside hunks as new file headers.

For example, an added source line containing text resembling:

```text
diff --git ...
```

must remain an added line when it occurs inside a valid hunk.

Parser state must determine meaning.

---

# 15. Paths

Handle ordinary Git patch paths such as:

```text
a/fs/stat.c
b/fs/stat.c
```

and:

```text
/dev/null
```

for file creation/deletion.

Preserve raw path metadata sufficiently for deterministic emission.

Do not introduce target-specific path rewriting in V2.1.

---

# 16. File Creation and Deletion

Tests must cover:

```text
new file
deleted file
```

including:

```text
new file mode
deleted file mode
--- /dev/null
+++ /dev/null
```

as appropriate.

The parsed model must distinguish creation/deletion from ordinary modification.

---

# 17. Mode Changes

Support and test Git metadata such as:

```text
old mode 100644
new mode 100755
```

including a mode-only change with no hunks if valid.

Do not require every `FilePatch` to contain a hunk.

---

# 18. Rename / Copy Metadata

V2.1 should preserve valid metadata such as:

```text
similarity index
rename from
rename to
copy from
copy to
```

Full semantic rename/copy processing is not required yet.

The requirement for V2.1 is:

```text
parse
preserve
re-emit
```

without silently losing valid metadata.

---

# 19. Binary Patch Boundary

Kernel repositories may contain binary diffs even though the current primary 10/50 use case is textual.

V2.1 does NOT need to semantically decode:

```text
GIT binary patch
```

However, it must make an explicit design choice.

Preferred V2.1 behavior:

```text
recognize binary patch section
preserve it opaquely if safe
or reject it explicitly as unsupported
```

Never accidentally parse binary patch data as text hunks.

Document and test the chosen behavior.

Do not build a binary delta decoder unless necessary.

---

# 20. Combined Diff Boundary

Combined merge diffs such as:

```text
diff --cc
@@@ ...
```

are not required for V2.1 unless current project inputs require them.

Preferred behavior:

```text
detect
raise explicit UnsupportedPatchFormat
```

Do not misparse them as normal unified diffs.

---

# 21. Emitter Contract

Implement a deterministic emitter with an API conceptually similar to:

```python
emit_patch(patch: Patch) -> str
```

or equivalent.

The emitter must produce syntactically valid patch text from the typed model.

It must not depend on the original raw input text for normal hunk emission.

---

# 22. Hunk Header Regeneration

The emitter must regenerate hunk count fields from the typed lines.

It must not blindly trust stale stored count values after model construction or mutation.

This establishes the foundation needed for later semantic transformations.

For example:

```text
old_count =
    context + removed

new_count =
    context + added
```

The emitted hunk header must reflect the actual model.

---

# 23. Deterministic Emission

Given the same typed `Patch` model, emission must be deterministic.

Avoid dependence on:

```text
dict iteration accidents
local Git configuration
locale
timezone
temporary filesystem paths
machine identity
```

Preserve defined input ordering in V2.1 unless the design explicitly requires canonical ordering.

Do not sort hunk lines.

---

# 24. Round-Trip Contract

Primary V2.1 invariant:

```text
parse
  ↓
typed model
  ↓
emit
  ↓
parse
```

must preserve structural equivalence.

Define an explicit structural-equivalence comparison.

Do not require byte equality for every valid input if normalization is intentional.

However:

```text
emit(parse(canonical_input))
```

should be byte-stable for canonical fixtures where practical.

Document any normalization.

---

# 25. Real Repository Fixture Tests

Do not test only synthetic toy patches.

Use representative samples from the repository's existing patch corpus.

Select small, bounded fixtures representing relevant syntax from existing:

```text
10
11
50
51
manual fixture patches
```

where available.

Do NOT modify those source patches.

Tests may read them directly or store small reviewed fixture excerpts under the V2 test directory.

If excerpts are copied, keep them small and document their source.

The goal is parser coverage, not semantic comparison.

---

# 26. Required Synthetic Test Cases

At minimum include tests for:

### Basic modification

```diff
diff --git a/a.c b/a.c
--- a/a.c
+++ b/a.c
@@ -1,2 +1,2 @@
 old context
-old
+new
```

with a structurally valid version of the example.

### Multiple files

One patch containing at least two file diffs.

### Multiple hunks

One file containing multiple hunks.

### Omitted hunk counts

```text
@@ -1 +1 @@
```

### Section context

```text
@@ -10,2 +10,3 @@ some_function(...)
```

### New file

`/dev/null` old side.

### Deleted file

`/dev/null` new side.

### Mode change

Including mode-only if supported.

### Rename metadata

Preservation test.

### No newline marker

Both removal/addition scenarios where useful.

### Empty content edge cases

Valid zero-count hunk forms if Git emits them.

### Source line resembling metadata

An added/context line that contains text resembling:

```text
diff --git
@@
--- 
+++
```

must not confuse parser state.

---

# 27. Required Negative Tests

At minimum reject explicitly:

```text
malformed diff --git header
malformed hunk header
invalid hunk line prefix
old hunk count mismatch
new hunk count mismatch
truncated hunk
unexpected hunk before file header
unsupported combined diff
```

If binary patch is unsupported, include:

```text
binary patch -> explicit unsupported error
```

If binary patch is preserved opaquely, test preservation instead.

No negative test should result in silent partial parsing.

---

# 28. Error Model

Implement only the V2.1 errors required for parser/emitter correctness.

Possible examples:

```text
PatchParseError
MalformedFileHeader
MalformedHunkHeader
InvalidHunkLine
HunkCountMismatch
UnexpectedPatchStructure
UnsupportedPatchFormat
PatchEmitError
```

Exact names may differ.

Errors should carry useful diagnostics such as:

```text
line number
file path if known
hunk if known
short reason
```

Do not implement the entire future V2 semantic error hierarchy yet.

---

# 29. Result Model

If a result wrapper is useful, keep it minimal.

Do not create a complex validation framework in V2.1.

Parser errors should normally be explicit exceptions or typed failures.

Later phases may introduce:

```text
PASS
FAIL
RUNTIME_REQUIRED
...
```

but V2.1 should not implement unused abstractions merely because the final design mentions them.

---

# 30. Python Compatibility

Inspect the repository/workflow environment before choosing the minimum Python version.

Do not unnecessarily introduce dependencies requiring a newer interpreter than the project environment supports.

Prefer Python standard library for V2.1 unless an external dependency provides a clear, necessary advantage.

If adding a dependency is genuinely required:

```text
document why
pin it appropriately
```

Do not add dependencies casually.

---

# 31. Dataclass / Type Design

Prefer clear typed Python structures such as:

```text
dataclasses
Enum
typing
```

where appropriate.

Favor:

```text
immutable or controlled mutation
explicit constructors
clear invariants
```

over large untyped dictionaries.

Do not over-engineer an ORM/schema framework.

---

# 32. Model Invariants

Define invariants explicitly.

Examples:

```text
Hunk start positions are valid integers.
Hunk counts are non-negative.
Normal hunk lines have exactly one valid kind.
NoNewlineMarker cannot appear without a preceding applicable line.
FilePatch paths are structurally valid for its status.
Patch preserves file ordering.
```

Enforce invariants either at construction or validation boundaries.

Tests must exercise them.

---

# 33. Raw Metadata Preservation

Unknown but syntactically valid metadata should not be silently lost.

For metadata not yet semantically modeled, use an explicit representation such as:

```text
ExtendedHeader(kind, raw_value)
```

or:

```text
RawMetadataLine
```

with ordering preserved.

This is preferable to dropping data.

Do not use raw metadata as a substitute for modeling core fields that V2.1 is explicitly required to understand.

---

# 34. Patch Preamble / Trailer

If input contains format-patch material before the first:

```text
diff --git
```

preserve it in a clearly separated patch-level field.

If trailing format-patch metadata exists after the last diff, preserve it where safely distinguishable.

Document any ambiguity and normalization.

Do not attempt a full RFC email parser.

---

# 35. Parser State Machine

Use an explicit parser state or equivalent structured logic.

Conceptual states may include:

```text
PREAMBLE
FILE_HEADER
EXTENDED_HEADERS
HUNK
TRAILER
```

Exact implementation is up to you.

The key requirement is that interpretation depends on structural state.

Avoid a parser built as a loose collection of independent global regex substitutions.

---

# 36. No Semantic Knowledge

V2.1 must NOT contain code referring to semantic project concepts such as:

```text
ksu_handle_execveat
ksu_handle_stat
SuSFS
SELinux ownership
manual
lsm_bl
scope-min
manual-security
GKI
Sultan
```

except in test fixture filenames/comments where unavoidable.

The parser/emitter must remain generic unified-diff infrastructure.

---

# 37. No Source Transformation Yet

Do not implement:

```text
source-tree mutation
semantic operations
semantic coverage ledger
mixed-hunk semantic splitting
target adaptation
fixture adaptation
symbol registry
ABI scanner
ownership validation
config validation
build validation
runtime validation
```

Those belong to later V2 phases.

V2.1 only creates the structural foundation they will consume.

---

# 38. Do Not Implement SemanticUnit Yet Unless Required

The V2 design describes:

```text
SemanticUnit
Operation
OwnerClaim
```

These belong primarily to V2.3+.

Do not implement them in V2.1 merely to make the package look complete.

If a tiny protocol/type placeholder is genuinely required for clean parser interfaces, explain why in the report.

Prefer not to create unused abstractions.

---

# 39. Test Runner

Determine the repository's existing Python test conventions.

If there is no established framework, prefer the smallest reasonable choice.

Using:

```text
unittest
```

is acceptable and avoids a dependency.

Using:

```text
pytest
```

is acceptable only if already available/appropriate or justified.

Do not modify unrelated project dependency configuration merely for convenience.

---

# 40. Required Test Commands

At the end of the task, run the V2.1 test suite.

Also run a basic syntax/import check.

Examples, depending on implementation:

```bash
python -m unittest discover ...
python -m compileall .github/scripts/v2
```

or the repository-equivalent commands.

Record the exact commands and results in the V2.1 report.

Do not claim tests passed unless they were actually executed successfully.

---

# 41. Repository Safety

Before implementation:

```text
inspect git status
```

The repository already may contain untracked analysis/task/report files.

Do NOT delete, overwrite, stage, or commit unrelated untracked files.

Do not treat pre-existing untracked analysis files as cleanup targets.

Only modify/create files explicitly allowed by this task.

At the end:

```text
inspect git status again
```

and report exactly which files V2.1 changed/created.

---

# 42. Allowed Files

V2.1 may create or modify only:

```text
.github/scripts/v2/**
XXKSU_SUSFS_V2_1_REPORT.md
```

and only files under `.github/scripts/v2/` that are necessary for V2.1.

Do not modify:

```text
.github/scripts/transform_10_to_11.py
.github/scripts/deinline_50_to_51.py
```

Do not modify any existing generated patch.

Do not modify any workflow.

Do not modify any manual fixture.

Do not modify:

```text
XXKSU_SUSFS_ANALYSIS_REPORT.md
XXKSU_SUSFS_PHASE1_5_REPORT.md
XXKSU_SUSFS_PHASE1_6_REPORT.md
XXKSU_SUSFS_V2_DESIGN.md
XXKSU_SUSFS_V2_1_TASK.md
```

---

# 43. No Git Mutation Beyond Working Tree

Do NOT:

```text
git add
git commit
git reset
git checkout
git restore
git clean
git stash
```

Do not modify branches or remotes.

Read-only Git commands are allowed.

Examples:

```text
git status
git diff
git log
git show
git ls-files
```

Use Git only for inspection during this phase.

---

# 44. Implementation Quality

V2.1 code must be:

```text
readable
typed where useful
documented at non-obvious boundaries
small
deterministic
testable
fail-closed
```

Avoid:

```text
large god classes
premature plugin frameworks
semantic policy leakage
catch-all exception swallowing
silent malformed-input recovery
unbounded regex heuristics
```

---

# 45. Required V2.1 Report

Create:

```text
./XXKSU_SUSFS_V2_1_REPORT.md
```

The report must describe what was actually implemented.

Use these exact sections:

```text
1. Executive Result
2. Files Created / Modified
3. Core Model Implementation
4. Patch Model
5. FilePatch Model
6. Hunk Model
7. Patch Line Model
8. Parser Architecture
9. Parser State Machine
10. Supported Unified Diff Syntax
11. Unsupported / Explicitly Rejected Syntax
12. Metadata Preservation
13. Hunk Count Validation
14. Emitter Architecture
15. Deterministic Emission
16. Round-Trip Contract
17. Error Model
18. Test Architecture
19. Synthetic Test Coverage
20. Repository Fixture Coverage
21. Negative Test Coverage
22. Commands Executed
23. Test Results
24. Git Status Before / After
25. Design Deviations
26. Remaining V2.1 Limitations
27. V2.2 Readiness
28. Confidence Report
```

---

# 46. Required Report Questions

The report must explicitly answer:

1. What exact files were created?
2. What exact files were modified?
3. What Python version assumptions were made?
4. Does V2.1 add any external dependency?
5. What unified diff syntax is supported?
6. What syntax is intentionally unsupported?
7. How are unknown Git extended headers preserved?
8. How are hunk counts validated?
9. How is `\ No newline at end of file` represented?
10. How are new/deleted files represented?
11. How are mode-only changes represented?
12. How are rename/copy headers handled?
13. How are binary patches handled?
14. How are combined diffs handled?
15. Does parser meaning depend on parser state?
16. Can a source line containing `diff --git` confuse file-boundary detection?
17. Does emitter recompute hunk counts?
18. Is structural parse→emit→parse equivalence tested?
19. Which real repository patches were used as parser fixtures?
20. Were any semantic KSU/SuSFS rules introduced?
21. Were existing generators changed?
22. Were existing patches/workflows/fixtures changed?
23. What exact test commands were run?
24. Did all V2.1 tests pass?
25. Is V2.1 sufficiently stable to begin V2.2?

---

# 47. Acceptance Criteria

V2.1 is complete only if ALL of the following are true:

```text
[ ] Typed Patch/FilePatch/Hunk/line model exists.
[ ] Parser is structural/state-aware.
[ ] Normal Git unified diffs parse correctly.
[ ] Multiple files parse correctly.
[ ] Multiple hunks parse correctly.
[ ] Omitted hunk counts parse correctly.
[ ] Section context is preserved.
[ ] New files are represented correctly.
[ ] Deleted files are represented correctly.
[ ] Mode changes are preserved.
[ ] Rename/copy metadata is preserved or explicitly modeled.
[ ] No-newline markers are preserved.
[ ] Unknown valid extended headers are not silently dropped.
[ ] Hunk old/new counts are validated.
[ ] Malformed hunk structure fails explicitly.
[ ] Unsupported combined diff fails explicitly.
[ ] Binary behavior is explicit and tested.
[ ] Emitter regenerates correct hunk counts.
[ ] Emission is deterministic.
[ ] parse→emit→parse structural equivalence passes.
[ ] Representative real repository patches are tested.
[ ] Negative malformed-patch tests pass.
[ ] No KSU/SuSFS semantic policy exists in parser/emitter.
[ ] Existing generators are unchanged.
[ ] Existing generated patches are unchanged.
[ ] Existing fixtures are unchanged.
[ ] Existing workflows are unchanged.
[ ] Tests were actually executed.
[ ] Test commands/results are recorded.
[ ] Git status was inspected before and after.
[ ] No files outside the allowed scope were modified by this task.
```

Any unchecked required item means:

```text
V2.1 COMPLETE: NO
```

---

# 48. Review Gate

V2.1 completion does NOT authorize V2.2.

After V2.1:

```text
STOP
```

The implementation and report must be reviewed by the human before any V2.2 work.

Do not begin:

```text
provenance/cache
manifest loader
semantic inventory
semantic coverage
50→51 policy
10→11 policy
target adapters
fixture adaptation
profile composition
validation pipeline
```

even if V2.1 finishes early.

---

# 49. Final Status

The report must end with exactly:

```text
V2.1 CORE MODELS COMPLETE: YES / NO
V2.1 DIFF PARSER/EMITTER COMPLETE: YES / NO
V2.1 TESTS PASS: YES / NO
SAFE TO BEGIN V2.2: YES / NO
```

`SAFE TO BEGIN V2.2: YES` means only that V2.1 provides a stable foundation.

It does NOT authorize V2.2.

---

# 50. STOP

After:

```text
.github/scripts/v2/
```

contains only the required V2.1 implementation/tests and:

```text
XXKSU_SUSFS_V2_1_REPORT.md
```

has been written:

**STOP.**

Do not stage.

Do not commit.

Do not start V2.2.