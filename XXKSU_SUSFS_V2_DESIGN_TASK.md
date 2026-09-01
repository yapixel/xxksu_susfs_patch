# xxKSU + SuSFS V2 Generator — Architecture & Implementation Specification Task

## Phase

Phase 2 — V2 Generator Architecture Design

## Status

DESIGN ONLY.

This task does NOT authorize implementation.

Do NOT modify the existing generators, patches, workflows, fixtures, kernel sources, xxKSU sources, or SuSFS sources.

You may create exactly one new deliverable:

```text
./XXKSU_SUSFS_V2_DESIGN.md
```

After completing that document:

**STOP.**

Do not implement V2.

---

# 1. Read the Existing Analysis First

Before doing anything else, read:

```text
./XXKSU_SUSFS_ANALYSIS_REPORT.md
./XXKSU_SUSFS_PHASE1_5_REPORT.md
./XXKSU_SUSFS_PHASE1_6_REPORT.md
```

Phase 1.6 is the authoritative architecture/target contract.

Phase 1.5 remains authoritative for semantic ownership evidence unless Phase 1.6 explicitly corrects it.

Do not repeat Phase 1, Phase 1.5, or Phase 1.6.

This task converts the accepted semantic architecture into an implementable V2 generator design.

---

# 2. Authoritative Project Contract

The following architecture is fixed unless direct source evidence proves an internal contradiction.

## 2.1 Supported targets

V2 must support:

```text
GKI Android 14 / Linux 6.1
GKI Android 16 / Linux 6.12
Sultan Android 14 / Linux 6.1
```

---

## 2.2 Supported build profiles

Every target must support BOTH:

```text
manual
lsm_bl
```

Required final validation profiles:

```text
gki-android14-6.1-manual
gki-android14-6.1-lsm_bl

gki-android16-6.12-manual
gki-android16-6.12-lsm_bl

sultan-android14-6.1-manual
sultan-android14-6.1-lsm_bl
```

Do not design a one-mode-per-target system.

---

## 2.3 Manual profile contract

Canonical manual transport configuration:

```text
CONFIG_KSU_LSM_SECURITY_HOOKS=n
CONFIG_KSU_HACK_ARM64_BRANCH_LINK=n
CONFIG_KSU_TAMPER_SYSCALL_TABLE=n
CONFIG_KSU_KPROBES_KSUD=n
```

Manual profiles require both transport fixtures:

```text
scope-min-manual-hooks-v2.3.patch
manual-security-hooks-v2.0.patch
```

The fixtures provide Linux-side transport.

They do not own the xxKSU handler implementations.

---

## 2.4 LSM/BL profile contract

Canonical lsm_bl configuration:

```text
CONFIG_KSU_LSM_SECURITY_HOOKS=y
CONFIG_KSU_HACK_ARM64_BRANCH_LINK=y
CONFIG_KSU_TAMPER_SYSCALL_TABLE=n
CONFIG_KSU_KPROBES_KSUD=n
```

Manual fixtures must NOT be applied.

Transport is provided by actual xxKSU mechanisms.

Depending on kernel version these include:

```text
LSM hook-list interception
ARM64 static security-call patching
ARM64 branch-link patching
BL-managed syscall-table fallback
runtime subsystem registration
```

Important:

```text
CONFIG_KSU_TAMPER_SYSCALL_TABLE=n
```

does NOT mean that no syscall-table mechanism exists.

BL internally owns a managed syscall-table bootstrap/fallback.

Model BL + its internal fallback as one composite xxKSU transport owner.

---

# 3. Fixed Architectural Boundary

The intended V2 architecture is:

```text
official upstream 10
        │
        ▼
11 semantic transformer
        │
        ▼
shared transport-neutral xxKSU/SuSFS integration
```

and:

```text
official upstream 50
        │
        ▼
51 semantic transformer
        │
        ▼
target-specific transport-neutral SuSFS kernel patch
```

followed by:

```text
target adapter
      +
profile manifest
      │
      ▼
final composition
├── manual
└── lsm_bl
      │
      ▼
final-source validation
final-config validation
build validation
```

The V2 design must preserve this separation.

---

# 4. 11 Responsibility

11 owns xxKSU-side SuSFS integration.

This includes the already-proven domains:

```text
SuSFS initialization
xxKSU-specific Kconfig/control integration
SID helpers and initialization
zygote/no-su/umount behavior
ksu_handle_setresuid integration
SuSFS command dispatch through actual xxKSU reboot/supercall
boot-complete/control plumbing
```

11 does NOT own Linux source caller insertion.

The same generated 11 must serve all six profiles unless new direct evidence proves otherwise.

Do not introduce manual-specific or lsm_bl-specific 11 variants.

---

# 5. 51 Responsibility

51 owns transport-neutral target-kernel SuSFS semantics.

Examples include applicable:

```text
filesystem behavior
namespace behavior
proc behavior
stat/kstat spoofing
mount ID behavior
unique mount ID behavior
uname spoofing
maps behavior
kallsyms behavior
bootconfig behavior
target/vendor SuSFS extensions
```

51 removes or reroutes official-50 KernelSU transport that is:

```text
ABI-incompatible with actual xxKSU
owned by official 10 rather than actual xxKSU
duplicated by the selected final transport
replaced by actual xxKSU behavior
```

51 must NOT:

```text
choose manual mode
choose lsm_bl mode
insert manual fixtures
enable BL
enable LSM
enable syscall-table tamper
guess transport ownership
```

One target-specific 51 must serve both profiles for that target.

---

# 6. Fixtures

Treat:

```text
scope-min-manual-hooks-v2.3.patch
manual-security-hooks-v2.0.patch
```

as first-class manual transport providers.

Do not treat them as generic compatibility patches.

Their semantics must be represented explicitly in the design.

V2 must support exact target adaptation of fixture semantics.

Fuzz-only fixture application is not acceptable final validation.

---

# 7. Target Adapters

Target adapters own mechanical differences, not architecture policy.

Adapters may handle:

```text
Linux 6.1 vs 6.12 APIs
VFS signature differences
SELinux signature differences
hunk anchors
context drift
6.12 minor-version drift
Sultan vendor-tree differences
Sultan-specific SuSFS extensions
exact fixture adaptation
target-specific validation probes
```

Adapters must NOT decide:

```text
KEEP vs REMOVE based on git apply success
manual vs lsm_bl
handler ownership
unknown semantic blocks
```

---

# 8. Core Design Objective

Design a V2 generator that derives current 11/51 from current upstream truth.

The fundamental generation model is:

```text
current official 10
+ current actual xxKSU
+ semantic policy
+ xxKSU adapter
        ↓
current 11
```

and:

```text
current official 50
+ current target kernel
+ semantic policy
+ target adapter
        ↓
current 51
```

Never evolve:

```text
old 11 → new 11
old 51 → new 51
```

Existing generated patches may be used as regression references, not as transformation inputs.

---

# 9. Upstream Truth

V2 must begin from actual upstream inputs.

For 11:

```text
official current 10
actual current xxKSU source
```

For 51:

```text
official current target-specific 50
actual target kernel source
```

The design must define how provenance is captured:

```text
upstream repository
branch
commit
patch hash
target kernel identity
xxKSU commit
generator version
policy version
adapter version
profile manifest version
```

Same provenance inputs must produce deterministic output.

---

# 10. Semantic Transformation Model

V2 must NOT primarily operate as:

```text
string replacement
keyword filtering
whole-file exclusion
regex => delete
git apply success => KEEP
git apply failure => REMOVE
```

The design must represent semantic units explicitly.

Propose a concrete internal model.

At minimum each semantic unit should be able to represent:

```text
semantic ID
source patch
target file
upstream hunk
semantic domain
ownership class
required behavior
transport sensitivity
expected symbols
expected call sites
target adapter
profile relevance
confidence/evidence
transformation action
validation requirements
```

Example conceptual object:

```yaml
id: susfs.stat.vfs_statx.ksu_transport
source: official_50
file: fs/stat.c
domain: stat
class: KSU_TRANSPORT
transport_sensitive: true

upstream:
  handler: ksu_handle_stat
  abi: official_ksu

policy:
  action: REROUTE
  final_owner: profile_manifest

preserve:
  - susfs_kstat_spoof
  - susfs_mount_id_spoof

validation:
  forbid_symbols:
    - official_only_handler
  require_final_owner: true
```

This is illustrative.

Design the actual schema rather than blindly copying the example.

---

# 11. Semantic Action Vocabulary

Define a small explicit action vocabulary.

At minimum evaluate:

```text
KEEP
REMOVE
REROUTE
SPLIT
ADAPT
REPLACE
REQUIRE_EXTERNAL_OWNER
UNKNOWN
```

If better names are justified, propose them.

Every action must have precise semantics.

For example:

```text
KEEP
```

must mean the upstream semantic behavior remains owned by the generated patch.

It must NOT simply mean “retain these text lines.”

Similarly:

```text
REMOVE
```

must mean behavior is intentionally absent or replaced elsewhere, with ownership proof.

Do not allow ambiguous action meanings.

---

# 12. Ownership Model

Design ownership as a first-class concept.

At minimum support owners such as:

```text
PATCH_11
PATCH_51

FIXTURE_SCOPE_MIN
FIXTURE_MANUAL_SECURITY

XXKSU_LSM_LIST
XXKSU_LSM_STATIC
XXKSU_BRANCH_LINK
XXKSU_INTERNAL_SYSCALL_FALLBACK
XXKSU_RUNTIME_INPUT
XXKSU_SELINUX_HIDE

TARGET_KERNEL
TARGET_ADAPTER
PROFILE_MANIFEST
```

If BL and internal syscall fallback are represented separately internally, the design must still support grouping them as one composite final owner where appropriate.

Define:

```text
behavior owner
transport owner
implementation owner
```

if those distinctions improve correctness.

Avoid reducing all ownership to a single vague field if that loses necessary semantics.

---

# 13. Mixed-Hunk Handling

This is a mandatory V2 design requirement.

A hunk may contain:

```text
pure SuSFS behavior
+
official KernelSU transport
+
version compatibility
```

V2 must safely split such hunks.

Example:

```text
fs/stat.c
```

may contain:

```text
SuSFS kstat behavior      → KEEP
official KSU caller       → REROUTE
mount-ID behavior         → KEEP
6.12 API adaptation       → ADAPT
```

The design must explain how the transformer reconstructs a valid output patch without deleting the whole hunk.

Never use:

```text
if "ksu_handle_" in hunk:
    drop_hunk()
```

or equivalent logic.

---

# 14. Semantic Matching Strategy

Design how V2 identifies semantic blocks.

Evaluate a layered strategy such as:

```text
1. unified-diff structural parser
2. file/function context
3. symbol/call-site matching
4. bounded structural patterns
5. source-side verification
6. target adapter
7. fail if ambiguous
```

Do not call something AST-based unless it actually uses a parser capable of producing a language syntax tree.

If the design proposes:

```text
tree-sitter
clang AST
Coccinelle
custom structural matcher
```

justify exactly where it is needed.

Avoid unnecessary complexity.

The objective is deterministic semantic correctness, not using a sophisticated parser for its own sake.

---

# 15. Unified Diff Engine

Specify a proper unified-diff data model.

At minimum support:

```text
Patch
FilePatch
Hunk
ContextLine
AddedLine
RemovedLine
Metadata
```

The engine must preserve or correctly regenerate:

```text
file paths
new/deleted file state
file modes where applicable
hunk boundaries
old/new line counts
context
newline markers
patch metadata
```

Do not use uncontrolled string splitting as the primary patch representation.

Define how semantic transformations produce new hunks.

---

# 16. 10 → 11 Design

Current `transform_10_to_11.py` is not a real 10→11 transformer.

V2 must consume official 10 as a real semantic input.

Design the complete 10→11 pipeline.

Expected conceptual flow:

```text
fetch/read official 10
        ↓
parse unified diff
        ↓
build semantic inventory
        ↓
classify official-KSU integration
        ↓
map to actual xxKSU architecture
        ↓
apply xxKSU semantic transformations
        ↓
apply xxKSU compatibility adapter
        ↓
construct candidate source tree
        ↓
semantic validation
        ↓
emit deterministic 11
```

Explain how V2 ensures upstream changes in 10 are not silently lost.

Every relevant upstream semantic block must be:

```text
accounted for
transformed
explicitly replaced
or rejected as UNKNOWN
```

---

# 17. 50 → 51 Design

Design the complete 50→51 pipeline.

Expected conceptual flow:

```text
fetch/read official target 50
        ↓
parse unified diff
        ↓
semantic inventory
        ↓
classify:
    pure SuSFS
    official KernelSU transport
    mixed
    target/version compatibility
        ↓
split mixed blocks
        ↓
remove/reroute official transport
        ↓
preserve SuSFS semantics
        ↓
apply target adapter
        ↓
construct candidate target tree
        ↓
semantic validation
        ↓
emit deterministic 51
```

The design must explicitly eliminate current whole-file exclusion behavior.

---

# 18. Official-Only Symbol Detection

V2 must explicitly know about interfaces belonging to official 10 that actual xxKSU does not provide.

Examples established by Phase 1.5/1.6 include:

```text
ksu_handle_execveat_sucompat
ksu_handle_vfs_fstat
ksu_handle_sys_read
ksu_handle_input_handle_event
```

Do not hardcode these merely as strings in arbitrary filtering code.

Design a symbol/ABI contract registry.

The registry should support:

```text
symbol
expected owner
availability
ABI/signature
official-KSU-only status
actual xxKSU equivalent
allowed final profiles
validation rule
```

Final composed source must not contain unresolved references to incompatible official-only interfaces.

---

# 19. Handler ABI Validation

Name equality is insufficient.

V2 must validate ABI/signature compatibility where relevant.

Examples:

```text
faccessat
stat
reboot
manual-security functions
```

The design must explain how it verifies:

```text
function declaration
function definition
argument count
important argument types
return contract
visibility/static/global requirements
```

This does not necessarily require a complete C compiler front end.

Propose the smallest reliable implementation.

---

# 20. Profile Manifest Design

Turn the Phase 1.6 conceptual manifest into an implementation-ready schema.

The design must specify:

```text
schema version
target ID
kernel family/version
architecture
11 policy
51 policy
adapter
profile IDs
fixture requirements
Kconfig requirements
forbidden config
transport ownership
required symbols
forbidden symbols
validation probes
build requirements
```

Required profiles remain:

```text
manual
lsm_bl
```

The schema must make invalid hybrid configurations representable as errors, not silently normalize them.

---

# 21. Target Manifest vs Profile Manifest

Define these separately if useful.

For example:

```text
TargetManifest
    target source
    upstream 50
    kernel version
    adapter
    51 policy
    target validation

ProfileManifest
    manual / lsm_bl
    fixtures
    Kconfig
    transport ownership
    profile validation
```

Avoid duplicating common data across all six profiles if inheritance/composition can remain explicit and deterministic.

Do not introduce inheritance so complex that effective configuration becomes difficult to audit.

---

# 22. Adapter Interface

Specify a stable adapter interface.

For example, an adapter may need operations similar to:

```text
identify_target()
map_file_path()
locate_semantic_anchor()
adapt_semantic_block()
adapt_fixture()
validate_target_prerequisite()
validate_final_source()
```

Do not require these exact names.

Define:

- inputs;
- outputs;
- failure modes;
- whether adapter changes semantics or only mechanics;
- how the engine proves an adapter did not silently change architecture policy.

Adapter failures must be fatal unless the semantic unit is explicitly optional.

---

# 23. Exact Fixture Adaptation

Phase 1.6 identified 6.12 manual fixture fuzz/tolerance as an implementation blocker.

Design a strict solution.

V2 must NOT rely on:

```text
patch --fuzz
git apply --reject + manual hope
|| true
```

Design fixture adaptation as semantic transformation.

Conceptual model:

```text
fixture semantic specification
        +
target adapter
        ↓
exact target-specific fixture patch
```

or another justified architecture.

The design must specify how to validate:

```text
correct target function
correct insertion point
correct ABI
exact caller count
no duplicate transport
```

This requirement applies to all manual profiles, not only 6.12.

---

# 24. BL Runtime Validation Problem

Phase 1.6 identified BL runtime observability as an implementation blocker.

Design how V2 should handle it.

Distinguish:

```text
generation-time validation
build-time validation
boot/runtime validation
release validation
```

Do not pretend generation-time source inspection can prove runtime text patch success.

Define what can be proven statically:

```text
required config
required symbols
required target functions
BL patch descriptors/anchors
fallback implementation
initialization path
```

Then define what requires runtime evidence.

If runtime observability requires a future instrumentation mechanism, specify the contract without implementing it.

The generator must not report runtime verification when only static/build validation occurred.

---

# 25. SELinux Validation Model

Preserve Phase 1.6 confidence levels.

Current evidence supports:

```text
AVC replacement                HIGH
fake status replacement        HIGH
setprocattr parity              MEDIUM
context/access parity           MEDIUM
```

Design validation accordingly.

Do not make exact backup-policy parity a generation-time assumption.

Separate:

```text
replacement ownership validation
```

from:

```text
behavioral parity validation
```

The latter may be a runtime/release gate.

---

# 26. Semantic Coverage Ledger

V2 must maintain a machine-checkable semantic coverage ledger.

For every relevant upstream semantic unit record:

```text
source semantic ID
source location
classification
action
final owner
adapter used
output location if applicable
validation status
evidence/provenance
```

Generation must fail if a required upstream semantic unit is unaccounted for.

The design must specify how newly appearing upstream hunks/blocks are detected.

An upstream change must not silently disappear merely because existing pattern rules no longer match.

---

# 27. Unknown-Upstream Detection

This is critical for automatic future updates.

Design how V2 distinguishes:

```text
known semantic change with changed context
```

from:

```text
new unknown upstream behavior
```

The safe default is:

```text
UNKNOWN → FAIL
```

not:

```text
UNKNOWN → copy
```

and not:

```text
UNKNOWN → delete
```

Describe how the failure report helps a human add a new semantic policy or adapter rule.

---

# 28. Reject Analysis

Raw patch application/reject information is useful diagnostic evidence but not semantic policy.

Design reject handling as:

```text
apply upstream patch to clean source
        ↓
collect rejects
        ↓
map reject to semantic unit
        ↓
target adapter attempts version adaptation
        ↓
validate semantic equivalence
        ↓
resolved or FAIL
```

Never define:

```text
reject = de-inline
```

and never define:

```text
applied cleanly = keep
```

---

# 29. Source-Tree-Based Transformation

Evaluate whether V2 should produce patches by:

```text
A. rewriting patch text directly
```

or:

```text
B. constructing a candidate source tree and generating the final diff
```

Strongly evaluate approach B.

For example:

```text
clean source
    ↓
apply accepted semantic operations
    ↓
validate resulting source
    ↓
git diff / format-patch
```

Explain advantages/disadvantages.

The final design should prefer semantic source correctness over preserving upstream hunk formatting.

---

# 30. Deterministic Output

Define deterministic generation requirements.

Given identical:

```text
official patch commit/hash
xxKSU commit
kernel commit/archive identity
policy version
adapter version
manifest version
generator version
```

V2 must generate semantically and byte-stably reproducible patch output where practical.

Specify handling of:

```text
commit dates
author metadata
subject
blob IDs
line offsets
temporary paths
locale
Git configuration
```

If byte-identical output cannot reasonably be guaranteed for a field, define normalization.

---

# 31. Validation Pipeline

Design validation as explicit stages.

At minimum:

## Stage 1 — Input provenance

Verify expected repositories/revisions/hashes.

## Stage 2 — Patch parsing

Official 10/50 parse successfully.

## Stage 3 — Semantic coverage

Every relevant semantic unit accounted for.

## Stage 4 — Transformation

Generate candidate 11/51.

## Stage 5 — Patch integrity

Generated patch structurally valid.

## Stage 6 — Clean application

Generated patch applies to intended clean source.

## Stage 7 — Static semantic validation

Required SuSFS behavior exists.

Forbidden official transport does not remain.

## Stage 8 — Profile composition

Compose all six profiles.

## Stage 9 — Ownership validation

Exactly one owner per transport-sensitive semantic path per profile.

## Stage 10 — Symbol/ABI validation

Required symbols exist and incompatible official-only symbols do not.

## Stage 11 — Final config validation

Resolve Kconfig and inspect actual `.config`.

## Stage 12 — Build validation

Build all six profiles.

## Stage 13 — Runtime/release gates

Track tests that cannot be proven statically.

Define exact failure semantics for every stage.

---

# 32. Validation Result Model

Do not use a single boolean.

Design structured validation results.

For example:

```text
PASS
FAIL
NOT_APPLICABLE
RUNTIME_REQUIRED
UNRESOLVED
```

A final generator success must not hide:

```text
RUNTIME_REQUIRED
```

release gates.

Distinguish:

```text
generation success
static integration success
build success
runtime validation status
release readiness
```

---

# 33. Final-Source Ownership Validator

Design how the validator proves final ownership.

It should reason over the final composed tree, not only generated patch text.

Examples:

Manual exec:

```text
required:
    exactly one fixture call

forbidden:
    official 50 exec transport
    active BL transport
```

LSM/BL exec:

```text
required:
    xxKSU BL transport prerequisites

forbidden:
    manual fixture call
    official 50 transport
```

Input:

```text
required:
    xxKSU input registration

forbidden:
    official-only input handler reference
```

Define comparable rules for every transport-sensitive semantic path.

---

# 34. Final Config Validator

The requested config fragment is not proof.

V2 must inspect the resolved final `.config`.

Design exact checks for manual:

```text
CONFIG_KSU=y
CONFIG_KSU_SUSFS=y
CONFIG_KSU_LSM_SECURITY_HOOKS=n
CONFIG_KSU_HACK_ARM64_BRANCH_LINK=n
CONFIG_KSU_TAMPER_SYSCALL_TABLE=n
CONFIG_KSU_KPROBES_KSUD=n
```

and lsm_bl:

```text
CONFIG_KSU=y
CONFIG_KSU_SUSFS=y
CONFIG_KSU_LSM_SECURITY_HOOKS=y
CONFIG_KSU_HACK_ARM64_BRANCH_LINK=y
CONFIG_KSU_TAMPER_SYSCALL_TABLE=n
CONFIG_KSU_KPROBES_KSUD=n
```

plus target-required SuSFS options and ARM64/KALLSYMS prerequisites where applicable.

Design failure reporting that shows:

```text
requested
resolved
expected
reason
```

---

# 35. Build Validation Design

All six profiles must eventually build.

Design:

```text
build matrix
source preparation
profile composition
config generation
build invocation
artifact/log capture
failure classification
```

Do not implement workflow YAML yet.

Specify which failures belong to:

```text
generator
policy
adapter
profile
upstream drift
toolchain/environment
```

A compiler failure must not automatically be classified as generator logic failure.

---

# 36. Test Architecture

Design a comprehensive test hierarchy.

At minimum:

```text
tests/unit/
tests/fixtures/
tests/golden/
tests/integration/
tests/regression/
tests/semantic/
```

or a justified equivalent.

Required categories:

### Parser tests

Unified diff parsing and emission.

### Semantic classifier tests

Known blocks map to expected semantic IDs/actions.

### Mixed-hunk tests

Pure SuSFS content survives while transport is rerouted.

### Adapter tests

6.1, 6.12, Sultan adaptations.

### Fixture adaptation tests

Manual call sites generated exactly.

### Ownership tests

Detect zero owner and duplicate owner.

### ABI tests

Detect incompatible handler signatures.

### Config tests

Reject invalid hybrid profiles.

### Golden tests

Known-good patches may be used as behavioral regression references.

Golden equality must NOT replace semantic validation.

### Upstream drift tests

Unknown semantic blocks must fail closed.

---

# 37. Known-Good Patch Role

Known-good patches are validated behavioral references.

They may be used for:

```text
regression comparison
semantic differential analysis
expected behavior inventory
migration confidence
```

They must NOT become:

```text
hardcoded output templates
patch fragments blindly copied into V2
authoritative upstream truth
```

A difference from known-good is not automatically a failure if the new result is semantically correct and evidence-supported.

The design must specify how differences are reviewed.

---

# 38. Current Generator Migration

Audit the reusable and non-reusable pieces of:

```text
.github/scripts/transform_10_to_11.py
.github/scripts/deinline_50_to_51.py
```

Do not implement changes.

Classify existing components as:

```text
REUSE
REFACTOR
REPLACE
DELETE
REFERENCE_ONLY
```

At minimum address:

```text
repository/source setup
unified diff parsing
hunk handling
string replacement logic
whole-file exclusions
keyword filtering
Sultan extra chunks
target-specific substitutions
hunk count recalculation
git apply checks
format-patch generation
CLI
logging
error handling
```

Explain migration rather than proposing a flag day rewrite without justification.

---

# 39. Proposed Package Structure

Produce a concrete proposed package/module structure.

For example:

```text
.github/scripts/v2/
├── cli.py
├── model/
│   ├── patch.py
│   ├── semantic.py
│   ├── manifest.py
│   └── result.py
├── engine/
│   ├── diff_parser.py
│   ├── source_tree.py
│   ├── transformer.py
│   ├── coverage.py
│   └── emitter.py
├── policy/
│   ├── patch11.py
│   ├── patch51.py
│   ├── symbols.py
│   └── ownership.py
├── adapters/
│   ├── xxksu.py
│   ├── gki_android14_6_1.py
│   ├── gki_android16_6_12.py
│   └── sultan_android14_6_1.py
├── profiles/
│   ├── manual.py
│   ├── lsm_bl_6_1.py
│   └── lsm_bl_6_12.py
├── validation/
│   ├── semantic.py
│   ├── ownership.py
│   ├── symbols.py
│   ├── config.py
│   ├── build.py
│   └── runtime_contract.py
└── tests/
```

This is illustrative.

Propose the smallest clean architecture that satisfies the requirements.

Avoid unnecessary framework-style abstraction.

---

# 40. CLI Design

Specify a future CLI without implementing it.

Examples of desired capabilities:

```text
generate 11
generate 51
validate patch
validate target
validate profile
validate all profiles
explain semantic unit
show provenance
```

Propose actual command syntax.

The CLI should make dangerous ambiguity impossible.

For example, generating target 51 should not require choosing manual or lsm_bl if 51 is truly transport-neutral.

---

# 41. Explainability

A semantic generator must explain its decisions.

Design commands/reports such as:

```text
why was this hunk removed?
who owns exec in gki-6.12-lsm_bl?
which upstream blocks changed?
why did generation fail?
which adapter handled this block?
```

Every transformed semantic unit should be traceable.

Design a human-readable generation report.

---

# 42. Error Model

Design typed/focused errors.

Examples:

```text
UnknownSemanticBlock
AmbiguousSemanticMatch
MissingSemanticAnchor
MultipleSemanticAnchors
UnsupportedTarget
UnsupportedProfile
MissingTransportOwner
DuplicateTransportOwner
HandlerSymbolMissing
HandlerABIConflict
ForbiddenOfficialSymbol
FixtureAdaptationFailure
FinalConfigMismatch
BuildFailure
RuntimeValidationRequired
UpstreamProvenanceMismatch
```

Do not require these exact class names.

Explain which errors are fatal for:

```text
generation
static validation
build validation
release readiness
```

---

# 43. Security / Safety of Transformation

The generator changes kernel source.

Design defensive constraints:

```text
never modify outside the temporary worktree
never mutate upstream checkout
verify repository identity before patching
verify clean worktree
pin revisions
avoid shell injection from manifest values
avoid arbitrary command execution from manifest
record every external command
fail on unexpected modified files
```

Do not over-engineer sandboxing, but explicitly design safe source mutation boundaries.

---

# 44. Temporary Worktree Model

Design how V2 uses temporary Git worktrees/clones.

Prefer a model where:

```text
immutable source cache
        ↓
temporary clean worktree
        ↓
semantic transformation
        ↓
validation
        ↓
diff emission
        ↓
discard worktree
```

Define cleanup behavior on failure.

Do not let generation mutate the user's actual kernel or xxKSU checkout.

---

# 45. Network / Offline Boundary

Separate:

```text
source acquisition
```

from:

```text
semantic generation
```

The semantic engine should ideally operate on pinned local inputs.

Design whether V2 supports:

```text
fetch
prepare
generate
validate
```

as separate stages.

This improves reproducibility and testability.

---

# 46. Provenance Manifest

Design an output provenance file/report.

It should record enough information to reproduce the patch.

At minimum:

```text
generator version
policy schema version
official upstream repository
official upstream branch
official upstream commit
official patch hash
xxKSU repository/commit
target kernel identity
target adapter
profile manifest version
fixture hashes
generation timestamp if non-semantic
output patch hash
validation results
```

Do not embed volatile timestamps into patch semantics if that breaks deterministic output.

---

# 47. Generated Patch Metadata

Specify deterministic patch metadata.

Define:

```text
subject
author
commit message
ordering
file ordering
hunk ordering
newline policy
```

Avoid inheriting uncontrolled local Git identity/config.

Generated patches should clearly state they are generated artifacts and identify provenance without introducing nondeterminism.

---

# 48. Migration Compatibility

Existing external workflows may expect current filenames:

```text
11_enable_susfs_for_ksu.patch
51_deinlined_susfs_hooks_sultan-android14-6.1.patch
51_deinlined_susfs_hooks_gki-android14-6.1.patch
51_deinlined_susfs_hooks_gki-android16-6.12.patch
```

The V2 design should preserve these output contracts unless there is a compelling reason not to.

Do not redesign filenames casually.

Manual/lsm_bl profiles do NOT imply separate 51 filenames.

---

# 49. V2 Implementation Phases

Produce a staged implementation plan.

Do NOT implement it.

Prefer small reviewable phases.

For example:

```text
V2.1 — core data models + diff parser
V2.2 — provenance + manifest loader
V2.3 — semantic coverage framework
V2.4 — 50→51 semantic policy
V2.5 — target adapters
V2.6 — strict manual fixture adaptation
V2.7 — 10→11 semantic policy
V2.8 — ownership/symbol/ABI validators
V2.9 — profile composition/config validator
V2.10 — six-profile build validation
V2.11 — regression/golden comparison
V2.12 — shadow-mode comparison with current generator
V2.13 — cutover
```

Determine the actual safest dependency order.

Each implementation phase must have:

```text
scope
files/modules
acceptance criteria
tests
STOP/review gate
```

---

# 50. Shadow-Mode Migration

Design a period where:

```text
current generator
        +
V2 generator
```

both run against the same pinned inputs.

Compare:

```text
semantic coverage
patch output
known-good references
final source
six-profile builds
```

Do not automatically replace the current generator merely because V2 runs once successfully.

Define cutover criteria.

---

# 51. Cutover Criteria

Specify when V2 is allowed to replace the current generators.

At minimum consider requiring:

```text
all relevant upstream semantic units accounted for
no UNKNOWN
all generated patches clean-apply
all six profile ownership validations pass
all six final configs pass
all six builds pass
known-good semantic differential reviewed
no forbidden official-only symbols
strict fixture adaptation
deterministic regeneration
human approval
```

Runtime/release gates such as SELinux parity and BL observability must be explicitly classified rather than hidden.

---

# 52. Current Generator Retirement

Design how old generators are retired.

Do not delete them during initial V2 implementation.

Possible lifecycle:

```text
ACTIVE
    ↓
SHADOWED
    ↓
LEGACY
    ↓
REMOVED
```

Define what evidence is required at each transition.

---

# 53. Implementation Blockers

Phase 1.6 identified three immediate blockers before coding authorization:

## Blocker A — strict fixture adaptation

Especially Linux 6.12 manual mode.

Need a concrete exact adaptation strategy.

## Blocker B — BL success/fallback observability

Need a concrete validation contract separating static/build/runtime proof.

## Blocker C — final `.config` validation

Need exact resolved-config checks.

The V2 design report must provide concrete engineering solutions for all three.

If any blocker remains too vague to implement safely, mark:

```text
IMPLEMENTATION BLOCKED
```

Do not pretend design completion resolves it.

---

# 54. Runtime Gates That May Remain

Not every runtime concern necessarily blocks generator implementation.

Evaluate separately:

```text
SELinux setprocattr parity
SELinux context/access parity
BL runtime patch success
SuSFS command behavior
safe-mode input behavior
zygote/umount behavior
```

Classify each as:

```text
IMPLEMENTATION_BLOCKER
PRE_CUTOVER_GATE
RELEASE_GATE
OPTIONAL_RUNTIME_CONFIRMATION
```

Justify each classification.

---

# 55. Required Decision Tables

The report must include at least these tables.

## A. Component responsibility

```text
Component | Owns | Must Not Own | Inputs | Outputs
```

## B. Semantic action vocabulary

```text
Action | Meaning | Required Evidence | Failure Condition
```

## C. Ownership types

```text
Owner | Behavior | Transport | Profiles | Validation
```

## D. Adapter responsibilities

```text
Adapter | Mechanical Differences | Semantic Policy Allowed? | Validation
```

## E. Validation stages

```text
Stage | Input | Check | Output | Fatal Conditions
```

## F. Current-generator migration

```text
Current Mechanism | REUSE/REFACTOR/REPLACE/DELETE/REFERENCE_ONLY | V2 Replacement | Reason
```

## G. Runtime gates

```text
Concern | Static Proof | Build Proof | Runtime Proof | Gate Classification
```

## H. Implementation phases

```text
Phase | Scope | Dependencies | Acceptance Criteria | Review Gate
```

---

# 56. Required Architecture Diagrams

Include diagrams for:

## Generation architecture

```text
upstream → semantic inventory → policy → adapter → source tree → patch
```

## Composition architecture

```text
11 + 51 + target + profile → final tree
```

## Validation architecture

```text
semantic → source → ownership → ABI → config → build → runtime gate
```

## Manual ownership

Show fixture transport.

## LSM/BL ownership

Show xxKSU runtime transport and internal syscall fallback.

---

# 57. Required Questions

The report must explicitly answer:

1. What is the smallest correct V2 architecture?
2. Should transformations operate primarily on patch text or source trees?
3. How are semantic blocks represented?
4. How are mixed hunks safely split?
5. How does V2 detect new upstream behavior?
6. How does V2 prove no upstream semantic unit was silently lost?
7. How does V2 validate handler ABI rather than just symbol names?
8. How does V2 distinguish architecture policy from version adaptation?
9. How are manual fixtures adapted without fuzz?
10. How are manual and lsm_bl profiles represented without duplicating 51?
11. How does V2 detect invalid hybrid transport?
12. How does V2 validate final resolved `.config`?
13. What BL properties can be proven statically?
14. What BL properties require runtime validation?
15. What SELinux properties remain runtime gates?
16. How is deterministic generation achieved?
17. Which current-generator components are reusable?
18. What is the safest migration sequence?
19. What are the cutover criteria?
20. Is the design now sufficiently concrete to authorize V2 implementation?

---

# 58. Required Report Structure

Write exactly:

```text
./XXKSU_SUSFS_V2_DESIGN.md
```

Use these sections:

1. Executive Architecture Decision
2. Accepted Phase 1.6 Contract
3. Design Principles
4. Component Responsibility Model
5. Repository / Package Structure
6. Core Data Model
7. Unified Diff Model
8. Semantic Unit Model
9. Semantic Action Vocabulary
10. Ownership Model
11. Upstream Input & Provenance Model
12. 10→11 Transformation Pipeline
13. 50→51 Transformation Pipeline
14. Mixed-Hunk Strategy
15. Semantic Matching Strategy
16. Source-Tree Transformation Model
17. Symbol & ABI Contract Registry
18. Target Manifest Schema
19. Profile Manifest Schema
20. Adapter Interface
21. GKI 6.1 Adapter
22. GKI 6.12 Adapter
23. Sultan 6.1 Adapter
24. Strict Manual Fixture Adaptation
25. Manual Profile Composition
26. LSM/BL Profile Composition
27. Duplicate / Hybrid Transport Prevention
28. Semantic Coverage Ledger
29. Unknown-Upstream Handling
30. Reject Analysis
31. Final-Source Ownership Validation
32. Final Config Validation
33. Build Validation
34. BL Static / Runtime Validation Contract
35. SELinux Validation Contract
36. Validation Result & Error Model
37. Deterministic Output
38. Temporary Worktree / Source Safety
39. Network / Offline Boundary
40. CLI Design
41. Explainability & Generation Reports
42. Test Architecture
43. Known-Good Regression Strategy
44. Current Generator Migration Audit
45. Shadow-Mode Migration
46. Cutover Criteria
47. Current Generator Retirement
48. V2 Implementation Phases
49. Runtime / Release Gates
50. Remaining Unknowns
51. Implementation Blocker Resolution
52. Final Implementation Readiness
53. Confidence Report

---

# 59. Final Implementation Readiness

The report must end with exactly:

```text
V2 ARCHITECTURE COMPLETE: YES / NO
IMPLEMENTATION BLOCKERS RESOLVED: YES / NO
SAFE TO IMPLEMENT V2: YES / NO
```

Explain each answer immediately before those final lines.

`SAFE TO IMPLEMENT V2: YES` is allowed only if the design gives concrete fail-closed solutions for:

```text
strict fixture adaptation
BL static/runtime observability boundary
final resolved .config validation
```

Runtime release tests that cannot reasonably be executed by the generator may remain later gates, but they must be explicitly modeled.

---

# 60. Evidence Discipline

Use the existing evidence hierarchy:

1. actual target kernel source
2. actual backslashxx/KernelSU source
3. official simonpunk/susfs4ksu 10/50
4. actual fixtures
5. known-good tested build workflows and 11/51
6. current generated 11/51
7. current Python generators
8. documentation

Do not weaken an existing HIGH-confidence conclusion without contrary evidence.

Do not promote MEDIUM-confidence SELinux parity to HIGH without new runtime evidence.

If the design requires a fact not established by existing evidence, mark it explicitly.

---

# 61. No Implementation

This task does NOT authorize:

```text
creating .github/scripts/v2/
editing transform_10_to_11.py
editing deinline_50_to_51.py
changing fixtures
changing generated patches
changing workflows
creating manifest source files
creating tests
regenerating 11
regenerating 51
running a cutover
committing changes
staging changes
```

Design may describe all of those.

It may not perform them.

---

# 62. File Modification Constraint

The only permitted new/modified file is:

```text
XXKSU_SUSFS_V2_DESIGN.md
```

Do not modify any existing file.

Do not stage.

Do not commit.

---

# 63. STOP Condition

After writing:

```text
XXKSU_SUSFS_V2_DESIGN.md
```

STOP.

Wait for human review before implementation.