# xxKSU + SuSFS V2.3 — Semantic Inventory & Coverage Ledger

## Phase

V2.3 — Semantic Inventory, Semantic Identity, Evidence Mapping & Coverage Ledger

## Status

IMPLEMENTATION AUTHORIZED FOR V2.3 ONLY.

V2.1 and V2.2 have completed their review gates.

This task authorizes implementation of the V2.3 semantic inventory foundation
described by the accepted V2 architecture.

It does NOT authorize V2.4 or any later phase.

After V2.3 is implemented, tested, audited, and documented:

**STOP.**

Do not continue into:

```text
50 → 51 policy
KEEP / REMOVE / SPLIT / REROUTE decisions
mixed-hunk transformation
target adapters
fixture adaptation
10 → 11 transformation
ownership enforcement
source-tree composition
final config validation
kernel builds
regression cutover
```

---

# 1. Read the Project Contract First

Before modifying anything, read these files in this exact order:

```text
./XXKSU_SUSFS_PHASE1_5_REPORT.md
./XXKSU_SUSFS_PHASE1_6_REPORT.md
./XXKSU_SUSFS_V2_DESIGN.md
./XXKSU_SUSFS_V2_1_REPORT.md
./XXKSU_SUSFS_V2_2_REPORT.md
./XXKSU_SUSFS_V2_3_TASK.md
```

Treat:

```text
Phase 1.5
```

as the semantic/evidence baseline.

Treat:

```text
Phase 1.6
```

as the authoritative dual-mode architecture contract.

Treat:

```text
XXKSU_SUSFS_V2_DESIGN.md
```

as the accepted V2 architecture.

Treat:

```text
V2.1
```

as the accepted structural patch-model/parser/emitter foundation.

Treat:

```text
V2.2
```

as the accepted input trust/provenance/cache/manifest foundation.

Treat this task as the authoritative implementation scope for V2.3.

Do not redesign prior accepted architecture during this phase.

If implementation reveals a contradiction in the accepted architecture:

```text
STOP
document it
fail closed
```

Do not silently reinterpret the architecture.

---

# 2. V2.3 Objective

Implement the semantic accounting layer required before transformation policy.

V2.3 must establish:

```text
verified input
    ↓
structural patch/source observations
    ↓
semantic inventory
    ↓
stable semantic identities
    ↓
evidence/fingerprint records
    ↓
coverage/accounting ledger
    ↓
explicit UNKNOWN detection
```

The central invariant is:

```text
Every relevant upstream semantic unit must be identified and accounted for
before any later phase is allowed to decide what to do with it.
```

V2.3 answers:

```text
WHAT semantic units exist?
WHERE are they?
WHAT evidence identifies them?
WHAT architecture-sensitive relationships do they expose?
IS every relevant unit accounted for?
```

V2.3 does NOT answer:

```text
Should this unit be kept?
Should this unit be removed?
Should this unit be rerouted?
Should this hunk be split?
How should 51 be generated?
```

Those are V2.4+ questions.

---

# 3. Fundamental Rule: Inventory Before Policy

V2.3 must remain policy-neutral.

The following transformation actions are forbidden in V2.3:

```text
KEEP
REMOVE
DROP
REROUTE
SPLIT
ADAPT
REPLACE
INSERT
DELETE
```

They may appear in documentation explaining that they belong to later phases,
but must not exist as executable V2.3 transformation decisions.

The inventory may classify facts such as:

```text
pure SuSFS behavior
transport-sensitive
handler definition
Linux-side caller
runtime registration
static-key gating
LSM hook
branch-link site
syscall-table fallback
mixed semantic block
unknown semantic block
```

but it must not decide the future transformation action.

---

# 4. Critical Rule: git apply Is Not Semantic Evidence

Never classify semantic ownership or transformation policy based on:

```text
git apply success
git apply failure
patch context matching
hunk textual applicability
```

Specifically:

```text
git apply failure != DEINLINE
git apply success != KEEP
```

V2.3 must not contain logic that infers semantic meaning from patch applicability.

---

# 5. Critical Rule: Function Names Alone Are Not Enough

Do not classify a semantic unit merely because it contains:

```text
ksu_handle_*
susfs_*
CONFIG_KSU_SUSFS
```

Function-name matching may be one piece of evidence.

It must not be the complete semantic classifier.

The same handler name can occur as:

```text
definition
declaration
Linux-side caller
runtime registration
wrapper
fallback
duplicate transport
test/fixture reference
```

These are semantically different.

---

# 6. Required Terminology

Use the following categories consistently.

## Handler Definition

Implementation of a handler/function.

Example conceptual form:

```c
int ksu_handle_foo(...)
{
    ...
}
```

This is not automatically a caller.

## Linux-Side Call Site

A direct/manual call inserted into Linux kernel source.

Example conceptual form:

```c
ksu_handle_foo(...);
```

inside Linux kernel code.

This is NOT synonymous with a kprobe.

## Runtime Registration

A runtime mechanism that registers or installs a callback/hook.

Examples may include:

```text
input handler registration
LSM registration
runtime hook installation
```

## Static-Key Gating

Architecture where an existing Linux-side call is gated through a static key or
equivalent runtime mechanism.

## LSM / Security Hook

Transport through Linux security-hook infrastructure.

## Kprobe / Kretprobe

Dynamic probe mechanism.

Do not use this term for ordinary source-level calls.

## Syscall-Table Modification

Explicit replacement/modification of syscall table entries.

## ARM64 Branch-Link

Architecture-specific call-site branch-link patching.

## Manual Source Hook

Direct fixture-provided Linux source call site.

## Fixture-Provided Hook

A call or transport mechanism introduced by one of the accepted manual fixtures.

These terms must not be conflated.

---

# 7. Evidence Priority

When semantic evidence conflicts, use this priority:

```text
1. actual target kernel source
2. actual backslashxx/KernelSU source
3. official simonpunk SuSFS 10/50
4. actual project fixtures
5. known-good tested 11/51 + workflows
6. current generated 11/51
7. current Python generators
8. README/docs
```

V2.3 code should not hardcode this as an arbitrary scoring system unless needed.

But inventory/provenance records must be capable of recording:

```text
evidence source
evidence kind
confidence
reason
```

Do not let lower-priority historical artifacts silently override current source
truth.

---

# 8. V2.3 Input Boundary

V2.3 consumes only verified/pinned inputs accepted by the V2.2 trust model.

Where production inputs remain unresolved in V2.2:

```text
do not invent them
do not silently fetch latest
do not fabricate commit/hash provenance
```

For unit tests, use deterministic local fixtures/snapshots.

For production semantic inventory, unresolved required input must remain an
explicit blocker.

V2.3 must preserve V2.2's offline/fail-closed contract.

---

# 9. V2.3 Package Scope

Extend:

```text
.github/scripts/v2/
```

only as needed.

Conceptual additions may include:

```text
.github/scripts/v2/
├── semantic/
│   ├── __init__.py
│   ├── model.py
│   ├── inventory.py
│   ├── fingerprint.py
│   ├── evidence.py
│   └── ledger.py
└── tests/
    └── test_v23_*.py
```

Exact structure may differ.

Prefer small modules with clear responsibilities.

Do not create empty V2.4+ placeholders.

---

# 10. Preserve V2.1 and V2.2

All existing V2.1 and V2.2 behavior must remain intact.

All previous tests must remain green.

Prefer additive V2.3 implementation.

If an existing V2.1/V2.2 file must be modified:

```text
keep the change minimal
document why
prove prior tests still pass
```

Do not redesign accepted APIs casually.

---

# 11. Core Semantic Data Model

Implement only semantic records needed for inventory/accounting.

Expected concepts include:

```text
SemanticUnit
SemanticId
SemanticFingerprint
SemanticKind
SemanticLocation
EvidenceRecord
EvidenceKind
SemanticRelationship
Inventory
LedgerEntry
CoverageLedger
CoverageState
Confidence
```

Exact names may differ.

Do not implement transformation-operation models unless they already exist solely
as neutral accepted design records.

V2.3 must not attach future transformation actions to inventory entries.

---

# 12. SemanticUnit Contract

A `SemanticUnit` represents one independently accountable semantic behavior or
transport element.

It must be finer-grained than:

```text
entire patch
entire file
all code mentioning one handler
```

where those contain multiple independent semantics.

A unit should be large enough to represent a meaningful behavior but small
enough that later phases can account for it independently.

Examples of potential units:

```text
SuSFS uname behavior
SuSFS stat spoofing behavior
SuSFS mount hiding behavior
exec transport caller
access transport caller
stat transport caller
reboot command transport
input safe-mode registration
setuid transport chain
SELinux AVC replacement behavior
SELinux fake-status behavior
```

These examples do not pre-authorize exact IDs.

The implementation must derive the canonical inventory from accepted evidence.

---

# 13. Semantic Identity

Every semantic unit must have a stable machine-readable identity.

A semantic ID must NOT depend solely on:

```text
patch line number
hunk number
absolute filesystem path
temporary directory
commit timestamp
```

Prefer semantic IDs conceptually similar to:

```text
susfs.stat.spoof
transport.exec.linux_call
transport.reboot.dispatch
selinux.avc.replace
```

Exact naming is implementation-defined.

Requirements:

```text
stable
deterministic
human-reviewable
unique within inventory namespace
```

If two distinct behaviors cannot safely share one ID:

```text
split them
```

Do not use a random UUID.

---

# 14. Semantic ID Namespace

Define an explicit namespace/version.

For example:

```text
xxksu-susfs-semantic/v1
```

or equivalent.

Persisted semantic IDs must be versionable.

Unknown future semantic schema versions must fail closed.

Do not silently reinterpret IDs across incompatible schema changes.

---

# 15. Semantic Fingerprint

Semantic identity and textual identity are not the same thing.

Implement a fingerprint representation that can describe evidence such as:

```text
file path
symbol/function context
structural patch location
normalized surrounding statements
required symbols
called symbols
configuration guards
semantic anchor
source kind
```

A fingerprint may contain cryptographic hashes of normalized evidence.

But:

```text
fingerprint != semantic ID
```

The same semantic behavior may move textually between upstream revisions.

The system must be designed so later adapters can update evidence without
renaming the semantic behavior unnecessarily.

---

# 16. Fingerprint Normalization

Fingerprint normalization must be conservative.

Allowed normalization may include:

```text
line-ending normalization
stable relative paths
structural extraction
explicitly documented whitespace normalization where safe
```

Do NOT normalize away:

```text
function names
operators
argument order
control-flow distinctions
preprocessor conditions
return behavior
```

if they can change semantics.

Unknown differences must not be silently treated as equivalent.

---

# 17. Evidence Records

Each semantic unit must be able to carry one or more evidence records.

An evidence record should identify:

```text
source identity
source type
relative path
structural location
symbol/context
fingerprint
evidence priority/category
confidence
notes/reason
```

Evidence must remain traceable back to verified input.

Do not store only prose with no machine-readable location.

---

# 18. Confidence

Use an explicit confidence enum such as:

```text
HIGH
MEDIUM
LOW
UNKNOWN
```

Do not convert confidence into automatic policy.

Example:

```text
MEDIUM evidence
```

must remain MEDIUM.

Do not silently promote it to HIGH because tests pass structurally.

Known unresolved SELinux parity concerns must not be erased.

---

# 19. Semantic Kinds

Define typed semantic categories.

At minimum the model should distinguish categories such as:

```text
SUSFS_BEHAVIOR
HANDLER_DEFINITION
LINUX_CALL_SITE
RUNTIME_REGISTRATION
STATIC_KEY_GATE
LSM_SECURITY_HOOK
KPROBE
SYSCALL_TABLE_HOOK
ARM64_BRANCH_LINK
MANUAL_SOURCE_HOOK
FIXTURE_HOOK
CONFIG_CONTROL
SELINUX_BEHAVIOR
TRANSPORT_WRAPPER
UNKNOWN
```

Exact enum structure may differ.

Avoid an enum so broad that all transport mechanisms collapse into `HOOK`.

---

# 20. Architecture-Sensitive Relationships

The inventory must support relationships between semantic units.

Examples:

```text
DEFINES
CALLS
GATES
REGISTERS
WRAPS
PROVIDES_TRANSPORT_FOR
FALLBACK_FOR
REPLACES_BEHAVIOR_OF
RELATED_TO
```

V2.3 records observed/accepted relationships.

It does NOT enforce exactly-one-owner yet.

---

# 21. Composite BL Representation

Preserve the accepted distinction:

```text
XXKSU_BRANCH_LINK
+
XXKSU_INTERNAL_SYSCALL_FALLBACK
```

belong to the composite selected transport architecture:

```text
XXKSU_BL_COMPOSITE
```

Do not classify the internal syscall-table fallback as evidence that:

```text
CONFIG_KSU_TAMPER_SYSCALL_TABLE=y
```

The canonical lsm_bl profile still declares:

```text
CONFIG_KSU_TAMPER_SYSCALL_TABLE=n
```

V2.3 inventory should be capable of representing both internal mechanisms and
their composite relationship.

---

# 22. Manual Transport Representation

Inventory must distinguish fixture-provided manual transport from xxKSU runtime
transport.

The accepted manual architecture uses:

```text
scope-min-manual-hooks-v2.3.patch
manual-security-hooks-v2.0.patch
```

as transport providers.

Do not classify their direct Linux source calls as:

```text
kprobes
syscall-table hooks
LSM hooks
```

unless the actual mechanism independently proves that category.

---

# 23. Official 50 Inventory

V2.3 must inventory relevant semantics from each official 50 family independently:

```text
Sultan Android 14 / Linux 6.1
GKI Android 14 / Linux 6.1
GKI Android 16 / Linux 6.12
```

Do not assume one 50 inventory can be copied blindly to all three.

Where the same semantic behavior exists in all three:

```text
share semantic identity
retain target/source-specific evidence
```

Where behavior differs:

```text
record the difference explicitly
```

---

# 24. Official 10 Inventory

Inventory the relevant official SuSFS 10 semantics required for future 10→11
generation.

V2.3 must identify:

```text
SuSFS integration behavior
handler-side behavior
configuration/control behavior
transport assumptions exposed by official 10
```

Do not generate 11.

Do not compare old11→new11.

The future source-of-truth relationship remains:

```text
current official 10
+
current actual xxKSU
→
current 11
```

---

# 25. Actual xxKSU Inventory

Inventory actual xxKSU evidence needed to understand the future integration
boundary.

At minimum account for relevant evidence around known architectural concepts such
as:

```text
exec handling
access handling
stat handling
fstat-return handling
reboot handling
setresuid chain
input safe-mode handling
LSM/security hooks
branch-link implementation
internal syscall-table fallback
static keys
SuSFS initialization/control
```

Do not assume official KernelSU symbol names exist in actual xxKSU.

Record actual symbols/ABIs as evidence.

---

# 26. Official-Only Symbol Awareness

V2.3 should be capable of marking evidence for symbols known to belong to
official upstream interfaces but absent from actual xxKSU.

Examples established by prior analysis include concepts around:

```text
ksu_handle_execveat_sucompat
ksu_handle_vfs_fstat
ksu_handle_sys_read
ksu_handle_input_handle_event
```

Do not turn this into V2.8 symbol rejection logic yet.

For V2.3:

```text
inventory and label the evidence
```

only.

---

# 27. ABI Evidence

Semantic inventory must be capable of recording relevant ABI/signature evidence.

Examples include:

```text
argument types
return contract
pointer vs struct filename form
credential object path
handler wrapper relationship
```

Do not implement ABI compatibility enforcement yet.

But do not throw away the evidence needed by V2.8.

---

# 28. Mixed Semantic Blocks

V2.3 must detect and represent a structural block/hunk containing more than one
semantic unit.

For example, a hunk may contain:

```text
pure SuSFS behavior
+
official transport call
```

The inventory must not collapse this into one indivisible semantic label.

Represent:

```text
multiple semantic units
multiple evidence ranges
shared structural container
```

as needed.

Do NOT split/rewrite the hunk in V2.3.

Actual mixed-hunk splitting belongs to V2.4.

---

# 29. Mixed Block Status

A mixed block must be explicitly identifiable as:

```text
MIXED
```

or equivalent factual structural classification.

This is not the same as future:

```text
SPLIT
```

`MIXED` is an observation.

`SPLIT` is a transformation action.

V2.3 may produce the former only.

---

# 30. Semantic Inventory Sources

Inventory may be built from:

```text
V2.1 parsed patch structures
verified source files
verified fixture patches
known-good reference patches
accepted architecture declarations
```

Each observation must retain source/provenance.

Do not merge observations from multiple sources into one anonymous fact.

---

# 31. Source Tree Observation

When actual source is available, semantic inventory should prefer source-tree
truth over historical generated patch text.

Source observation must be deterministic and bounded.

Do not implement a general C compiler/parser unless truly necessary.

A targeted structural scanner is acceptable if:

```text
its grammar is explicit
its limitations are documented
unknown syntax fails closed where required
tests cover boundaries
```

---

# 32. Text/Regex Policy

Regex is allowed for bounded lexical recognition.

Regex must not become the semantic policy engine.

Forbidden pattern:

```python
if "ksu_handle_" in hunk:
    semantic = TRANSPORT
```

Acceptable conceptual pattern:

```text
identify candidate symbol occurrence
+
identify structural context
+
identify source role
+
attach evidence
+
resolve against explicit semantic specification
```

Unknown candidate context must remain UNKNOWN.

---

# 33. Semantic Specification Registry

Implement an explicit, reviewable semantic specification registry if needed.

The registry may define:

```text
semantic ID
expected semantic kind
known source families
expected paths
expected symbols
expected structural anchors
required/optional evidence
relationships
confidence expectations
```

The registry must not contain V2.4 transformation actions.

It must remain data-oriented and human-reviewable.

---

# 34. No Silent Discovery by Keyword

If inventory encounters a candidate relevant block that is not represented by the
semantic specification:

```text
UNKNOWN
```

must be recorded.

Do not silently ignore it.

Examples of candidate relevance may include:

```text
SuSFS config blocks
known SuSFS symbols
known KSU integration symbols
security/SELinux integration
transport-sensitive kernel paths
fixture hook locations
```

The candidate detector must be conservative enough to expose suspicious new
upstream semantics.

---

# 35. UNKNOWN Is Fatal for Complete Inventory

A complete production inventory cannot report PASS while relevant UNKNOWN units
remain.

Required rule:

```text
relevant UNKNOWN count > 0
    =>
inventory completeness FAIL
```

Tests may intentionally create UNKNOWN units.

But production readiness must fail closed.

Do not silently downgrade UNKNOWN to warning.

---

# 36. Coverage Ledger

Implement a deterministic coverage/accounting ledger.

Every relevant discovered semantic unit must receive a ledger entry.

A ledger entry should record:

```text
semantic ID
source identity
source location
semantic kind
evidence records
relationships
confidence
inventory status
accounting state
```

The ledger is not a transformation plan.

---

# 37. Coverage States

Use factual accounting states, not V2.4 actions.

Possible states:

```text
IDENTIFIED
MIXED
UNKNOWN
DUPLICATE_EVIDENCE
UNRESOLVED
```

Exact enum names may differ.

Do NOT use:

```text
KEEP
REMOVE
REROUTE
SPLIT
ADAPT
```

as V2.3 coverage states.

---

# 38. Ledger Completeness

Implement a completeness check.

A complete ledger requires:

```text
all relevant candidate observations accounted for
no relevant UNKNOWN
no duplicate semantic ID collision
no orphan evidence
no invalid source reference
no ambiguous semantic identity
```

A unit may have multiple evidence records.

Multiple evidence records are not automatically duplicate semantics.

---

# 39. Duplicate Semantic Identity

Detect accidental collisions where two incompatible semantic units are assigned
the same semantic ID.

Fail closed if:

```text
same ID
+
incompatible semantic kind/contract
```

Do not merge them automatically.

Legitimate multiple target-specific evidence for the same semantic behavior must
remain supported.

---

# 40. Orphan Evidence

Evidence that cannot be attached to a known semantic unit must not disappear.

Represent it as:

```text
UNKNOWN
```

or explicit unresolved/orphan evidence.

Complete inventory must fail until resolved.

---

# 41. Deterministic Ledger Serialization

Provide deterministic machine serialization of inventory and ledger.

Preferred:

```text
canonical JSON
```

consistent with V2.2 conventions.

Same verified inputs and semantic specification must produce identical semantic
inventory/ledger identity.

Do not include volatile timestamps in deterministic identity.

---

# 42. Semantic Inventory Identity

Provide a deterministic digest/identity for the completed inventory.

It should depend on relevant:

```text
input provenance identity
semantic schema version
semantic specification version
semantic units
evidence fingerprints
relationships
coverage ledger
```

It must not depend on:

```text
absolute path
wall-clock time
temporary directory
iteration order
```

---

# 43. Target-Specific Evidence

The same semantic ID may have different evidence locations across:

```text
gki-android14-6.1
gki-android16-6.12
sultan-android14-6.1
```

Do not encode target/version mechanics into the semantic ID unless the behavior
itself differs.

Example principle:

```text
same behavior
different anchor
=
same semantic ID
different evidence
```

---

# 44. 6.12 Minor Version Drift

Prior analysis established that Linux 6.12.23 vs 6.12.69 can carry the same
semantic payload with context/API/hunk differences.

V2.3 must therefore avoid using exact hunk text as semantic identity.

It may record exact text as evidence/fingerprint.

But semantic identity must remain behavior-oriented.

Do not implement the future 6.12 adapter in this phase.

---

# 45. SELinux Inventory

SELinux behavior requires explicit inventory.

At minimum preserve distinct evidence for known areas such as:

```text
AVC replacement
fake-status behavior
setprocattr/context/access-related behavior
slow_avc_audit integration where applicable
xxKSU selinux_hide replacement behavior
```

Do not collapse all SELinux work into one semantic ID.

---

# 46. SELinux Confidence

Prior analysis has:

```text
AVC replacement parity        HIGH
fake-status parity            HIGH
setprocattr/context/access     MEDIUM
```

or equivalent unresolved confidence.

Do not silently promote MEDIUM to HIGH.

V2.3 ledger must preserve unresolved confidence.

This does not necessarily make inventory incomplete if the semantic unit is
correctly identified.

But it must remain visible as a future release/runtime validation concern.

---

# 47. Reboot Inventory

Inventory reboot behavior carefully.

Distinguish:

```text
handler definition
SuSFS command dispatch
Linux-side caller
syscall replacement/fallback transport
return-value contract
```

Do not treat all reboot-related code as one semantic unit.

Prior analysis found official transport return behavior incompatible with actual
xxKSU in some contexts.

Record that as ABI/behavior evidence.

Do not perform V2.4 rerouting yet.

---

# 48. Exec Inventory

Distinguish at minimum:

```text
actual xxKSU exec handler definition
official Linux-side exec caller
manual fixture exec caller
branch-link exec transport
official-only sucompat path where present
```

Do not assume these are interchangeable.

---

# 49. Access / Stat Inventory

Record the known distinction between:

```text
official 50 handler ABI
actual xxKSU handler ABI
manual fixture caller
BL transport
pure SuSFS stat/access behavior
```

Mixed blocks must remain separable in inventory.

Do not decide future action.

---

# 50. Fstat-Return Inventory

Distinguish official concepts from actual xxKSU equivalents.

Record evidence around actual:

```text
ksu_handle_newfstat_ret
ksu_handle_fstat64_ret
```

where applicable.

Do not invent an actual xxKSU:

```text
ksu_handle_vfs_fstat
```

if it is absent.

---

# 51. Read / Init-RC Inventory

Preserve the important architecture distinction:

```text
official ksu_handle_sys_read-style transport
vs
actual xxKSU ksu_install_rc_hook-style behavior
```

For lsm_bl, remember the accepted architecture:

```text
with BL enabled on 6.1,
read/init-RC is not simply an LSM file_permission hook;
it may use xxKSU BL-managed internal syscall-table fallback.
```

Inventory the actual mechanism.

Do not mislabel it as TAMPER profile mode.

---

# 52. Setuid Inventory

Distinguish:

```text
official direct setuid transport
actual xxKSU setuid/security chain
11-added setresuid integration
manual-security fixture transport
LSM/security transport
```

Do not collapse definition and caller ownership.

Do not generate 11.

---

# 53. Input Safe-Mode Inventory

Distinguish:

```text
official input handler assumptions
actual xxKSU registered input handler
runtime registration
event handling
```

Do not create a fake official handler in inventory to make names line up.

---

# 54. Config Inventory

Inventory relevant configuration semantics separately from runtime transport.

Examples:

```text
CONFIG_KSU
CONFIG_KSU_SUSFS
CONFIG_KSU_LSM_SECURITY_HOOKS
CONFIG_KSU_HACK_ARM64_BRANCH_LINK
CONFIG_KSU_TAMPER_SYSCALL_TABLE
CONFIG_KSU_KPROBES_KSUD
```

V2.2 validates declared profile contract.

V2.3 may associate config controls with semantic mechanisms.

It must not run olddefconfig or validate final `.config`.

---

# 55. Fixture Inventory

Parse and inventory both manual fixtures:

```text
scope-min-manual-hooks-v2.3.patch
manual-security-hooks-v2.0.patch
```

Record the semantic transport units they provide.

Do not apply them.

Do not adapt them.

Do not modify them.

---

# 56. Known-Good References

Known-good 11/51 patches may be used as lower-priority evidence.

They must not become the semantic source of truth when higher-priority current
source evidence disagrees.

Their role in V2.3 is:

```text
behavioral/reference evidence
coverage cross-check
historical known-good comparison
```

not:

```text
copy old patch text
```

---

# 57. Current Generators

The existing:

```text
transform_10_to_11.py
deinline_50_to_51.py
```

may be inspected as historical implementation evidence.

They are lower priority.

Do not copy their unsafe policy into V2.3.

Specifically do not reproduce:

```text
string replace as semantic identity
whole-file security exclusion
drop-all CONFIG_KSU_SUSFS blocks
handler-name-only deletion
heuristic #else surgery
```

---

# 58. Candidate Detection

Implement a bounded candidate-detection layer so new/unexpected relevant upstream
content is not invisible.

Candidate detection may consider:

```text
known paths
known symbols
SuSFS config guards
security/SELinux regions
known transport-sensitive functions
fixture-related call sites
```

But candidate detection and semantic resolution must remain separate.

Conceptually:

```text
candidate discovered
    ↓
semantic resolver
    ├── known -> identified unit
    └── unknown -> UNKNOWN
```

Do not simply ignore unmatched candidates.

---

# 59. Candidate False Positives

Candidate detection may conservatively produce false positives.

That is preferable to silently missing new upstream behavior.

However, provide an explicit mechanism for a specification to declare:

```text
known irrelevant candidate
```

with reviewable reason/evidence if necessary.

Do not hide false positives through arbitrary regex exclusions.

---

# 60. Inventory Diagnostics

When inventory fails, diagnostics should identify:

```text
source
relative path
structural location
candidate text/context summary
candidate fingerprint
reason no semantic unit matched
```

Do not dump entire large source files into errors.

Diagnostics must be useful for updating the semantic specification.

---

# 61. No Transformation Output

V2.3 must not emit:

```text
11_enable_susfs_for_ksu.patch
51_deinlined_*.patch
modified kernel source
modified xxKSU source
adapted fixture
```

The only V2.3 machine outputs should be inventory/accounting artifacts or
in-memory structures needed for tests.

Do not overwrite existing patch artifacts.

---

# 62. No Patch Application

Do not use patch application as part of semantic inventory.

Do not run:

```text
git apply
patch
```

to decide semantic classification.

If a structural test requires parsing a patch, use the V2.1 parser.

---

# 63. No Target Adapter

Do not implement:

```text
6.1 API adaptation
6.12 API adaptation
Sultan adaptation
anchor rewriting
fixture context adaptation
```

V2.3 may record target-specific evidence only.

V2.5 owns target adapters.

---

# 64. No Exactly-One-Owner Enforcement

V2.3 may inventory possible transport providers and relationships.

It must NOT yet claim:

```text
exactly-one-owner source validation PASS
```

V2.8 owns final ownership enforcement.

V2.3 may detect obvious duplicate semantic identity inside its own inventory, but
that is different from final composed-source ownership validation.

---

# 65. No ABI Enforcement

V2.3 records ABI evidence.

V2.8 will enforce symbol/ABI compatibility.

Do not reject an inventory merely because two observed source families expose
different ABI.

Record the difference.

UNKNOWN ABI shape may be fatal if required evidence cannot be parsed/identified.

---

# 66. No Build

Do not run kernel builds as V2.3 acceptance.

Do not run final profile composition.

Do not run final config resolution.

Build validation belongs later.

---

# 67. Required Tests

Add focused V2.3 tests while preserving all V2.1/V2.2 tests.

Required test categories:

```text
semantic model invariants
stable semantic IDs
fingerprint determinism
evidence serialization
relationship serialization
candidate detection
known semantic resolution
UNKNOWN detection
UNKNOWN completeness failure
mixed-block representation
multiple evidence for one semantic ID
semantic ID collision failure
orphan evidence failure
target-specific evidence
tree/path independence
ledger determinism
inventory identity determinism
official-only symbol evidence
ABI evidence preservation
manual-vs-LSM/BL distinction
BL composite distinction
SELinux confidence preservation
fixture inventory
repository patch inventory samples
```

---

# 68. Required Real Evidence Tests

Use bounded real repository evidence where available.

At minimum include real evidence from:

```text
existing 11 patch
existing 51 patch samples that V2.1 can structurally parse
scope-min-manual-hooks-v2.3.patch
manual-security-hooks-v2.0.patch
```

Where verified/pinned source snapshots are available through V2.2 preparation,
use them.

Do not fabricate production evidence merely to make tests pass.

---

# 69. Three 50 Family Coverage

Tests/specification must demonstrate that the inventory architecture can
distinguish evidence for:

```text
sultan-android14-6.1
gki-android14-6.1
gki-android16-6.12
```

If complete verified official-50 material is locally available, inventory it.

If not, use bounded verified test fixtures and explicitly report the production
input limitation.

Do not claim complete production inventory without complete verified input.

---

# 70. Official 10 Coverage

Likewise, inventory architecture must support official 10.

If V2.2 production identity remains unresolved:

```text
report production inventory BLOCKED for that input
```

rather than fetching "latest" implicitly.

Tests may use deterministic local official-10 samples.

---

# 71. Unknown Injection Test

Create at least one synthetic relevant candidate that resembles a new upstream
SuSFS/KSU integration behavior but has no semantic specification.

Expected result:

```text
candidate discovered
semantic resolution UNKNOWN
ledger completeness FAIL
```

This test is mandatory.

It proves the future generator cannot silently ignore new upstream behavior.

---

# 72. Mixed Hunk Test

Create at least one hunk containing:

```text
pure SuSFS semantic behavior
+
transport-sensitive caller
```

Expected V2.3 result:

```text
one structural hunk
multiple semantic observations
MIXED factual status
no transformation performed
```

Do not split the patch text.

---

# 73. Function-Name Ambiguity Test

Create a test where the same handler symbol appears as:

```text
definition
declaration
caller
```

Expected result:

```text
distinct semantic/evidence roles
```

This is mandatory.

It guards against regression to handler-name-only classification.

---

# 74. Transport Terminology Test

Where practical, assert that:

```text
manual direct source call != KPROBE
LSM hook != manual source hook
BL != TAMPER profile selection
internal BL syscall fallback != TAMPER=y
runtime input registration != Linux manual caller
```

This may be expressed through enum/relationship tests.

---

# 75. Determinism Tests

Prove:

```text
same semantic input -> same semantic ID
same evidence -> same fingerprint
same inventory built in different iteration order -> same canonical output
same inventory under different absolute temp roots -> same identity
changed semantic evidence -> changed fingerprint/inventory identity
timestamps do not affect identity
```

---

# 76. Negative Tests

At minimum test:

```text
unknown semantic schema
duplicate incompatible semantic ID
orphan evidence
invalid evidence source reference
invalid relationship target
relevant UNKNOWN
ambiguous semantic resolution
malformed semantic specification
invalid confidence
invalid semantic kind
```

Fail explicitly.

Do not auto-repair malformed semantic records.

---

# 77. Error Model

Extend typed errors only as needed.

Possible V2.3 errors:

```text
SemanticError
UnsupportedSemanticSchema
SemanticSpecificationError
SemanticResolutionError
AmbiguousSemanticMatch
UnknownSemanticUnit
SemanticIdCollision
InvalidEvidence
OrphanEvidence
InvalidRelationship
InventoryIncomplete
LedgerIncomplete
```

Exact names may differ.

Do not introduce V2.4 transformation errors.

---

# 78. Serialization

Use deterministic serialization consistent with V2.2.

If JSON is used:

```text
sorted keys
stable separators
UTF-8
explicit schema
```

Do not serialize arbitrary Python repr.

Machine output should be reviewable.

---

# 79. Optional Inventory Artifact

If useful, V2.3 may emit a deterministic review artifact under:

```text
.github/scripts/v2/**
```

for test/reference purposes.

Do not create large generated production artifacts unless needed.

The authoritative human deliverable remains:

```text
XXKSU_SUSFS_V2_3_REPORT.md
```

---

# 80. Python / Dependencies

Preserve the current Python baseline.

Prefer standard library.

Do not add heavyweight AST/C parsing dependencies unless absolutely necessary.

If a dependency is required:

```text
justify it
pin it
document it
```

A targeted semantic scanner is preferred over a huge dependency if it can remain
strict and fail closed.

---

# 81. Repository Safety

Before implementation run:

```text
git status --short
```

Record it.

Do not clean pre-existing work.

Do not delete V2.1/V2.2 files.

Do not treat untracked project documents as disposable.

After implementation run:

```text
git status --short
```

again.

---

# 82. Allowed Modifications

V2.3 may create/modify only:

```text
.github/scripts/v2/**
XXKSU_SUSFS_V2_3_REPORT.md
```

Do not modify:

```text
.github/scripts/transform_10_to_11.py
.github/scripts/deinline_50_to_51.py
existing generated patches
fixtures
workflows
Phase 1.5 report
Phase 1.6 report
V2 design
V2.1 report/task
V2.2 report/task
```

---

# 83. Git Restrictions

Do NOT run project-mutating Git commands:

```text
git add
git commit
git reset
git checkout
git restore
git clean
git stash
```

Do not change branches/remotes.

Read-only Git commands are allowed.

Temporary test Git repositories remain allowed if isolated outside project state.

---

# 84. Required Commands

At completion run at minimum:

```bash
python3 -m compileall -q .github/scripts/v2
PYTHONPATH=.github/scripts python3 -m unittest discover -s .github/scripts/v2/tests -v
```

Run any focused V2.3 test commands needed.

Record exact commands and results.

All V2.1/V2.2/V2.3 tests must pass.

---

# 85. V2.3 Audit Requirement

Before declaring V2.3 complete, perform a read-only self-audit against this task.

The audit must explicitly search the V2.3 implementation for accidental
transformation policy.

Check for executable policy concepts such as:

```text
KEEP
REMOVE
DROP
REROUTE
SPLIT
ADAPT
```

If present:

```text
explain why
```

and remove them if they implement V2.4 behavior.

Also audit for unsafe semantic shortcuts such as:

```text
handler-name-only classification
whole-file exclusion
git-apply-based classification
silent unmatched-candidate ignore
```

---

# 86. Required V2.3 Report

Create:

```text
./XXKSU_SUSFS_V2_3_REPORT.md
```

Use these exact sections:

```text
1. Executive Result
2. Files Created / Modified
3. V2.1 Regression Status
4. V2.2 Regression Status
5. V2.3 Architecture
6. Semantic Schema
7. SemanticUnit Model
8. Semantic ID Contract
9. Semantic Fingerprint Contract
10. Evidence Model
11. Evidence Priority
12. Confidence Model
13. Semantic Kind Taxonomy
14. Relationship Model
15. Candidate Detection
16. Semantic Resolution
17. Semantic Specification Registry
18. Official 10 Inventory
19. Official 50 Inventory
20. Actual xxKSU Inventory
21. Fixture Inventory
22. Manual Transport Representation
23. LSM / Security Representation
24. ARM64 Branch-Link Representation
25. Internal Syscall Fallback Representation
26. Handler / Caller Distinction
27. ABI Evidence
28. Official-Only Symbol Evidence
29. Mixed Semantic Block Representation
30. SELinux Inventory
31. SELinux Confidence Preservation
32. Reboot Inventory
33. Exec Inventory
34. Access / Stat Inventory
35. Fstat-Return Inventory
36. Read / Init-RC Inventory
37. Setuid Inventory
38. Input Safe-Mode Inventory
39. Config Inventory
40. Coverage Ledger
41. UNKNOWN Handling
42. Completeness Rules
43. Duplicate / Collision Handling
44. Deterministic Inventory Identity
45. Production Input Readiness
46. Test Architecture
47. Real Evidence Test Coverage
48. Unknown Injection Test
49. Mixed-Hunk Test
50. Function-Name Ambiguity Test
51. Transport Terminology Tests
52. Determinism Tests
53. Negative Tests
54. Commands Executed
55. Test Results
56. Git Status Before / After
57. Transformation-Policy Audit
58. Design Deviations
59. Remaining V2.3 Limitations
60. V2.4 Readiness
61. Confidence Report
```

---

# 87. Required Report Questions

The report must explicitly answer:

1. What exact files were created?
2. What exact existing files were modified?
3. Did V2.1 behavior change?
4. Did V2.2 behavior change?
5. Do all prior tests still pass?
6. What is the semantic schema/version?
7. How is a semantic ID constructed?
8. Can line numbers affect semantic identity?
9. Can absolute paths affect semantic identity?
10. How is semantic fingerprinting different from semantic identity?
11. What evidence is preserved?
12. How is evidence tied to V2.2 provenance?
13. How are confidence levels represented?
14. Is MEDIUM SELinux confidence preserved?
15. Which semantic kinds exist?
16. How are handler definitions distinguished from callers?
17. How are manual calls distinguished from kprobes?
18. How are LSM hooks distinguished from manual calls?
19. How is BL distinguished from TAMPER profile mode?
20. How is internal BL syscall fallback represented?
21. How are runtime registrations represented?
22. How are mixed semantic blocks represented?
23. Does V2.3 split mixed hunks?
24. Does V2.3 contain KEEP/REMOVE/REROUTE/SPLIT policy?
25. Does git apply success/failure affect semantic classification?
26. Can a handler name alone classify a unit?
27. How are candidate relevant blocks discovered?
28. What happens when no semantic specification matches?
29. Can relevant UNKNOWN be ignored?
30. What makes the coverage ledger complete?
31. How are duplicate semantic IDs handled?
32. How is orphan evidence handled?
33. Are official 10 semantics represented?
34. Are all three official 50 target families represented?
35. Is actual xxKSU evidence represented?
36. Are both manual fixtures represented?
37. Are official-only symbol differences preserved?
38. Is ABI evidence preserved?
39. Is SELinux behavior split into independently accountable units?
40. Is reboot behavior split into definition/dispatch/transport evidence?
41. Are exec/access/stat/fstat/read/setuid/input mechanisms independently
    represented where required?
42. Is inventory serialization deterministic?
43. Is inventory identity independent of temporary paths?
44. Does changed evidence change the fingerprint?
45. Was an UNKNOWN injection test performed?
46. Was a mixed-hunk test performed?
47. Was same-symbol definition/declaration/caller ambiguity tested?
48. Were transport terminology distinctions tested?
49. Were real repository fixtures used?
50. Which production inputs remain unresolved?
51. Did V2.3 fetch any implicit latest upstream input?
52. Did V2.3 modify source?
53. Did V2.3 apply patches?
54. Did V2.3 generate 11?
55. Did V2.3 generate 51?
56. Did V2.3 implement target adapters?
57. Did V2.3 enforce final exactly-one-owner?
58. Did V2.3 run final config resolution?
59. Did V2.3 run kernel builds?
60. What exact test commands ran?
61. Did all tests pass?
62. Is the semantic inventory foundation sufficiently stable for V2.4?

---

# 88. Acceptance Criteria

V2.3 is complete only if ALL required items are true:

```text
[ ] All V2.1 tests remain green.
[ ] All V2.2 tests remain green.
[ ] Semantic schema/version exists.
[ ] Typed SemanticUnit model exists.
[ ] Stable human-reviewable semantic IDs exist.
[ ] Semantic IDs do not depend on line numbers.
[ ] Semantic IDs do not depend on absolute paths.
[ ] Semantic fingerprints are deterministic.
[ ] Fingerprints preserve meaningful semantic distinctions.
[ ] Evidence records retain verified source identity.
[ ] Evidence priority is representable.
[ ] Confidence is typed.
[ ] MEDIUM evidence remains MEDIUM.
[ ] Handler definition and caller are distinct.
[ ] Linux-side caller and kprobe are distinct.
[ ] Manual hook and LSM hook are distinct.
[ ] BL and TAMPER profile mode are distinct.
[ ] Internal BL syscall fallback is represented correctly.
[ ] Runtime registration is independently representable.
[ ] Candidate detection exists.
[ ] Candidate resolution is separate from detection.
[ ] Unmatched relevant candidates become UNKNOWN.
[ ] Relevant UNKNOWN makes completeness fail.
[ ] Mixed semantic blocks are representable.
[ ] Mixed block does not trigger transformation in V2.3.
[ ] Coverage ledger exists.
[ ] Every relevant discovered unit receives accounting.
[ ] Duplicate incompatible semantic IDs fail closed.
[ ] Orphan evidence fails closed or remains explicit UNKNOWN.
[ ] Ledger serialization is deterministic.
[ ] Inventory identity is deterministic.
[ ] Absolute temp root does not affect inventory identity.
[ ] Changed relevant evidence changes fingerprint/inventory identity.
[ ] Official 10 inventory architecture exists.
[ ] All three official 50 families are distinguishable.
[ ] Actual xxKSU inventory architecture exists.
[ ] Both manual fixtures are represented.
[ ] Official-only symbol evidence is preserved.
[ ] ABI evidence is preserved.
[ ] SELinux semantic units are independently accountable.
[ ] SELinux MEDIUM confidence is preserved.
[ ] Reboot semantic roles are independently accountable.
[ ] Exec semantic roles are independently accountable.
[ ] Access/stat semantic roles are independently accountable.
[ ] Fstat-return semantic roles are independently accountable.
[ ] Read/init-RC semantic roles are independently accountable.
[ ] Setuid semantic roles are independently accountable.
[ ] Input safe-mode semantic roles are independently accountable.
[ ] UNKNOWN injection test passes.
[ ] Mixed-hunk inventory test passes.
[ ] Same-symbol definition/declaration/caller test passes.
[ ] Transport terminology tests pass.
[ ] No git-apply-based semantic policy exists.
[ ] No handler-name-only semantic policy exists.
[ ] No silent unmatched-candidate ignore exists.
[ ] No KEEP/REMOVE/REROUTE/SPLIT transformation policy exists.
[ ] No source mutation exists.
[ ] No patch application exists.
[ ] No 11 generation exists.
[ ] No 51 generation exists.
[ ] No target adapter implementation exists.
[ ] No final ownership enforcement exists.
[ ] No final .config resolution exists.
[ ] No build validation exists.
[ ] Existing generators remain unchanged.
[ ] Existing patches remain unchanged.
[ ] Existing fixtures remain unchanged.
[ ] Existing workflows remain unchanged.
[ ] All V2.1/V2.2/V2.3 tests pass.
[ ] Compile/import checks pass.
[ ] Git status before/after is recorded.
[ ] No unauthorized files were modified.
```

Any required unchecked item means:

```text
V2.3 COMPLETE: NO
```

---

# 89. Important Readiness Distinction

There are two different concepts:

```text
V2.3 implementation complete
```

and:

```text
complete production semantic inventory available
```

They are not automatically the same.

Because some V2.2 production input identities may still be unresolved, V2.3 can
successfully implement and validate the semantic inventory engine while reporting:

```text
production inventory blocked pending verified/pinned source input
```

Do not fake production completeness to obtain a YES.

`SAFE TO BEGIN V2.4` requires that the V2.3 engine itself is sound and that the
semantic policy work can safely begin using verified evidence.

Any production-input blocker must be explicitly carried forward.

---

# 90. Independent Audit Gate

Because V2.3 is the first semantic phase, completion of this task is NOT by itself
sufficient authorization for V2.4.

After the implementation report is written:

```text
STOP
```

A separate read-only audit should review:

```text
semantic IDs
candidate coverage
UNKNOWN behavior
terminology correctness
mixed-block accounting
evidence provenance
absence of transformation policy
```

Only after human review of both implementation and audit may V2.4 be authorized.

---

# 91. Final Status

The V2.3 report must end with exactly:

```text
V2.3 SEMANTIC MODEL COMPLETE: YES / NO
V2.3 INVENTORY ENGINE COMPLETE: YES / NO
V2.3 COVERAGE LEDGER COMPLETE: YES / NO
V2.3 UNKNOWN FAIL-CLOSED COMPLETE: YES / NO
V2.3 TESTS PASS: YES / NO
PRODUCTION SEMANTIC INVENTORY COMPLETE: YES / NO / BLOCKED
SAFE TO BEGIN V2.4: YES / NO
```

`SAFE TO BEGIN V2.4: YES` is readiness for human review only.

It does NOT authorize V2.4.

---

# 92. STOP

After implementation, tests, self-audit, and:

```text
XXKSU_SUSFS_V2_3_REPORT.md
```

are complete:

**STOP.**

Do not stage.

Do not commit.

Do not begin V2.4.