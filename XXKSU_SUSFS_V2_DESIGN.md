# xxKSU + SuSFS V2 Generator Design

Design-only deliverable. This document turns the Phase 1.5 evidence baseline and
the authoritative Phase 1.6 dual-mode contract into an implementation design.
No implementation is included here.

## 1. Executive Architecture Decision

V2 is a deterministic, fail-closed semantic transformer. It starts from current
official 10/50 inputs, actual pinned xxKSU and clean target kernels, builds a
semantic inventory, applies architecture policy, applies a mechanical adapter,
constructs a candidate source tree, validates that tree, and emits a patch.

There is one shared 11 for all profiles and one transport-neutral, target-specific
51 for each target. A profile manifest owns transport selection. Every target has
both `manual` and `lsm_bl` profiles, for six final build profiles total. Ownership
uniqueness is evaluated per semantic path per final profile.

```text
official 10 + xxKSU + 11 policy + xxKSU adapter -> shared 11
official 50 + clean target + 51 policy + target adapter -> target 51
shared 11 + target 51 + target + profile manifest -> final profile tree
final tree -> source/ABI/config/build/runtime validation -> artifacts
```

## 2. Accepted Phase 1.6 Contract

Supported targets are GKI Android 14/Linux 6.1, GKI Android 16/Linux 6.12,
and Sultan Android 14/Linux 6.1. Each target requires:

```text
<target>-manual
<target>-lsm_bl
```

The six required IDs are `gki-android14-6.1-manual`,
`gki-android14-6.1-lsm_bl`, `gki-android16-6.12-manual`,
`gki-android16-6.12-lsm_bl`, `sultan-android14-6.1-manual`, and
`sultan-android14-6.1-lsm_bl`.

Manual requires both `scope-min-manual-hooks-v2.3.patch` and
`manual-security-hooks-v2.0.patch`, with `LSM_SECURITY_HOOKS=n`,
`HACK_ARM64_BRANCH_LINK=n`, `TAMPER_SYSCALL_TABLE=n`, and
`KPROBES_KSUD=n`. LSM/BL forbids both fixtures and requires
`LSM_SECURITY_HOOKS=y`, `HACK_ARM64_BRANCH_LINK=y`,
`TAMPER_SYSCALL_TABLE=n`, and canonical `KPROBES_KSUD=n`. BL and its internally
managed syscall-table bootstrap/fallback are one composite xxKSU transport
owner. `KSU=y`, `KSU_SUSFS=y`, ARM64, and KALLSYMS prerequisites are checked in
the resolved final configuration.

The same 11 serves all six profiles. One target-specific 51 serves both modes
for each target. Neither 11 nor 51 selects transport or inserts fixtures.

## 3. Design Principles

1. Upstream truth is always an input; generated patches are regression references only.
2. Semantic units, not keywords or whole files, are the policy boundary.
3. Unknown, ambiguous, missing, duplicate, and unowned behavior fails closed.
4. Mixed hunks are split at semantic line/block boundaries; pure SuSFS behavior is never lost with transport.
5. Architecture policy is independent of target/version mechanics.
6. Patch application is evidence, not semantic classification.
7. Final-source validation follows complete composition, not isolated patch text.
8. Every profile is explicit; no effective-value guessing or hybrid normalization.
9. Deterministic inputs produce deterministic output and provenance.
10. Runtime claims are reported only when runtime evidence exists.

## 4. Component Responsibility Model

| Component | Owns | Must Not Own | Inputs | Outputs |
|---|---|---|---|---|
| 11 policy/transformer | xxKSU-side SuSFS integration and compatibility mapping | Linux caller insertion or mode selection | official 10, xxKSU tree, policy | shared 11 patch, ledger |
| 51 policy/transformer | transport-neutral target SuSFS semantics and official transport rerouting | fixtures, LSM/BL enablement, guessed ownership | official 50, clean target, policy | target 51 patch, ledger |
| Profile manifest | mode, fixtures, Kconfig, owners, gates | changing 11/51 semantics | target manifest, profile policy | explicit profile composition |
| Target adapter | anchors, APIs, vendor and minor drift, exact fixture adaptation | KEEP/REMOVE decisions or mode selection | target identity, semantic unit | adapted operations and probes |
| Fixture provider | manual Linux/security call sites | xxKSU handler implementation | fixture spec, adapter | exact manual fixture patch |
| Source-tree engine | isolated composition and mutation | changing immutable inputs | clean worktree, operations | candidate tree |
| Validators | integrity, coverage, ownership, ABI, config, build status | silently repairing failures | candidate tree and evidence | typed results |
| Provenance/reporting | reproducibility and explainability | volatile semantic content | all inputs/results | manifest and human report |

## 5. Repository / Package Structure

```text
.github/scripts/v2/
  cli.py
  model/{patch.py,semantic.py,manifest.py,result.py,provenance.py}
  engine/{diff_parser.py,source_tree.py,transformer.py,coverage.py,emitter.py}
  policy/{patch11.py,patch51.py,symbols.py,ownership.py,actions.py}
  adapters/{base.py,xxksu.py,gki_android14_6_1.py,gki_android16_6_12.py,sultan_android14_6_1.py}
  profiles/{common.py,manual.py,lsm_bl_6_1.py,lsm_bl_6_12.py,targets.py}
  validation/{semantic.py,source.py,ownership.py,abi.py,config.py,build.py,runtime.py}
  tests/{unit,fixtures,golden,integration,regression,semantic}
```

The package is intentionally small and uses a typed internal model rather than
a framework. Policy modules contain decisions; adapters contain mechanics.

## 6. Core Data Model

Core immutable records are `InputRef`, `TargetRef`, `Patch`, `SemanticUnit`,
`Operation`, `OwnerClaim`, `ProfileManifest`, `ValidationResult`, and
`Provenance`. Every record has a stable ID and schema version. Operations are
pure descriptions until applied to a temporary source tree.

```yaml
Operation:
  id: stable-operation-id
  unit_id: susfs.stat.vfs_statx.ksu_transport
  action: REROUTE
  target_file: fs/stat.c
  source_span: {function: vfs_statx, old_lines: [..]}
  replacement: {kind: remove_official_transport}
  owner_claim: {behavior: PATCH_51, transport: PROFILE_MANIFEST}
  adapter: gki_android16_6_12
  evidence: [E2, E3, E4]
```

## 7. Unified Diff Model

The parser produces `Patch(metadata, files)`, `FilePatch(old_path, new_path,
old_mode, new_mode, status, hunks)`, and `Hunk(old_start, old_count, new_start,
new_count, lines, section_context)`. Lines are tagged `ContextLine`,
`AddedLine`, `RemovedLine`, or `NoNewlineMarker`, each retaining text and source
line numbers. Metadata preserves headers, index/mode lines, rename/create/delete
state, and newline markers.

The emitter recalculates counts from typed lines, preserves file ordering from a
canonical path sort, and emits standard unified/format-patch syntax. Semantic
operations create a new patch by diffing validated trees, so hunk boundaries and
offsets are regenerated rather than hand-maintained.

## 8. Semantic Unit Model

Each unit is a bounded behavior, not a line pattern:

```yaml
SemanticUnit:
  id: susfs.stat.vfs_statx.ksu_transport
  source: official_50
  location: {file: fs/stat.c, function: vfs_statx}
  domain: stat
  class: KSU_TRANSPORT
  required_behavior: compatible stat interception
  transport_sensitive: true
  upstream_contract: {symbols: [ksu_handle_stat], abi: official_ksu}
  expected_call_sites: [fs/stat.c:vfs_statx]
  policy: {action: REROUTE, final_owner: PROFILE_MANIFEST}
  preserve_units: [susfs.stat.kstat, susfs.stat.mount_id]
  adapter: target_adapter
  profiles: [all]
  confidence: HIGH
  evidence: [E1, E2, E3, E4, E5]
  validation: {forbid: [official_only_symbols], require_owner: true}
```

Units are discovered from patch structure and source context, then matched to
policy IDs. A unit may produce multiple operations when a hunk contains several
independent behaviors.

## 9. Semantic Action Vocabulary

| Action | Meaning | Required Evidence | Failure Condition |
|---|---|---|---|
| KEEP | Generated patch owns and preserves the behavior | source match and required-feature proof | behavior absent or changed unexpectedly |
| REMOVE | Behavior is intentionally absent because a named replacement/owner is proven | owner and replacement evidence | no replacement or owner proof |
| REROUTE | Official implementation/transport is removed or redirected to selected owner | compatible final owner and ABI proof | profile has no owner |
| SPLIT | One mixed unit is decomposed into independently classified operations | bounded semantic boundaries | unsplittable overlap |
| ADAPT | Mechanics change while behavior and ownership remain invariant | adapter equivalence checks | adapter changes policy or cannot locate anchor |
| REPLACE | A named implementation is substituted by an equivalent xxKSU/target behavior | replacement mapping and confidence | replacement missing or unsupported |
| REQUIRE_EXTERNAL_OWNER | Output intentionally relies on a fixture/runtime/target component | manifest claim and final-source proof | component absent or duplicated |
| UNKNOWN | Classification is not established | diagnostic only | always fatal for required units |

## 10. Ownership Model

Ownership is a tuple `(behavior_owner, transport_owner, implementation_owner)`.
The validator enforces one transport owner per semantic path per final profile;
safe coexistence is declared explicitly for independent behavior such as 51
stat spoofing plus a fixture stat caller.

| Owner | Behavior | Transport | Profiles | Validation |
|---|---|---|---|---|
| PATCH_11 | xxKSU/SuSFS implementation integration | N/A | all | 11 symbols and source checks |
| PATCH_51 | kernel SuSFS semantics | N/A | all | feature inventory |
| FIXTURE_SCOPE_MIN | exec/access/stat/fstat/reboot calls | direct source | manual | exact adapted call counts |
| FIXTURE_MANUAL_SECURITY | security, read, setuid, setprocattr calls | security source | manual | ABI and call counts |
| XXKSU_LSM_LIST | 6.1 LSM slots | LSM list | 6.1 lsm_bl | slot/original chaining |
| XXKSU_LSM_STATIC | 6.12 security call patches | ARM64 BL | 6.12 lsm_bl | descriptor and target checks |
| XXKSU_BRANCH_LINK | exec/access/stat wrappers | ARM64 BL | lsm_bl | descriptors/fallback |
| XXKSU_INTERNAL_SYSCALL_FALLBACK | early read/fstat/reboot and BL handoff | managed SCT | lsm_bl | one composite BL claim |
| XXKSU_RUNTIME_INPUT | safe-mode input | registered handler | all | registration and no official symbol |
| XXKSU_SELINUX_HIDE | AVC/status/context replacement | runtime/LSM/manual call | all | replacement mapping; parity gate |
| TARGET_KERNEL | existing security/VFS behavior | native target call | all | clean-source anchor |
| TARGET_ADAPTER | target mechanics | adaptation layer | target | equivalence proof |
| PROFILE_MANIFEST | selected mode/owner declaration | composition | one profile | exact schema/config |

For lsm_bl, `XXKSU_BRANCH_LINK` and `XXKSU_INTERNAL_SYSCALL_FALLBACK` are
reported internally but grouped as `XXKSU_BL_COMPOSITE` for uniqueness.

## 11. Upstream Input & Provenance Model

`fetch` records repository URL, branch, commit, and cryptographic object/patch
hash. Kernel archives record release identity, archive hash, extracted tree hash,
architecture, and any published commit metadata. Provenance also records
xxKSU commit, generator/policy/adapter/manifest schema versions, fixture hashes,
and output hash. The timestamp is kept only in a sidecar report and never in
semantic patch content.

Inputs are content-addressed and verified before use. A provenance mismatch is
fatal; no unpinned network state is accepted by `generate`.

## 12. 10→11 Transformation Pipeline

```text
read pinned official 10 and xxKSU tree
 -> parse diff and source inventory
 -> classify every official KernelSU unit
 -> map definitions/ABIs to actual xxKSU
 -> apply semantic operations through xxKSU adapter
 -> build candidate xxKSU tree
 -> validate coverage, symbols, ABI and initialization
 -> emit shared 11 and provenance
```

The inventory includes unchanged-but-relevant interfaces discovered from 10 and
actual xxKSU. New 10 hunks not matched to a policy ID become `UNKNOWN` and stop
generation. No operation reads the prior generated 11.

## 13. 50→51 Transformation Pipeline

```text
read pinned target-specific official 50 and clean target
 -> parse and inventory semantic blocks
 -> classify pure SuSFS, transport, mixed, and version units
 -> split mixed blocks
 -> reroute/remove official transport only with owner claims
 -> keep/replace pure SuSFS behavior
 -> apply target adapter mechanics
 -> validate candidate source and coverage
 -> emit one transport-neutral 51 for the target
```

Whole-file exclusions and keyword filtering are prohibited. `fs/stat.c` is the
reference mixed case: retain kstat/mount-ID behavior, reroute official stat and
fstat transport, and adapt 6.12 APIs independently.

## 14. Mixed-Hunk Strategy

The splitter first maps added/removed lines to function and semantic spans using
context and symbol references. It creates a dependency graph for declarations,
guards, calls, and pure SuSFS statements. Connected components with different
actions are separated only at compilable statement/block boundaries. Each
component is transformed and the candidate source is diffed again, allowing Git
to form valid new hunks.

If a boundary cannot be proven without changing behavior, the unit is
`UNKNOWN`/`AmbiguousSemanticMatch` and generation stops. A hunk containing
`ksu_handle_*` is never dropped as a unit.

## 15. Semantic Matching Strategy

Matching is layered and deterministic:

1. Parse unified diff structurally.
2. Resolve file/function context against the clean source.
3. Match declared symbols, call signatures, guards, and nearby statements.
4. Use bounded structural matchers for known C idioms (not unrestricted regex).
5. Verify the proposed span in the source tree and compare pre/post semantics.
6. Ask the target adapter to resolve only mechanical context/API differences.
7. Fail on zero, multiple, or contradictory matches.

No AST dependency is required initially. A small tokenizer/function-span parser
is sufficient for bounded C statements; a real parser may be added only for a
demonstrated ambiguity class, with its version pinned.

## 16. Source-Tree Transformation Model

V2 prefers approach B: apply accepted semantic operations to an immutable clone
of a clean source tree, validate it, then generate the final diff. Direct patch
text rewriting remains only an input/output format concern.

Source-tree transformation gives compilable context, exact caller counts, and
correct offsets/modes/newline handling. It costs temporary storage and requires
careful operation ordering; those costs are controlled by isolated worktrees and
typed operations. The final patch is `git diff --binary`/format-patch from the
validated tree, never a concatenation of hand-edited hunks.

## 17. Symbol & ABI Contract Registry

The registry is structured data, not ad hoc string filters:

```yaml
symbol: ksu_handle_vfs_fstat
status: official_ksu_only
official_owner: official_10
actual_xxksu: absent
signature: void (int fd, size_t *size)
return_contract: side_effect_only
allowed_profiles: []
equivalent: [ksu_handle_newfstat_ret, ksu_handle_fstat64_ret]
rule: forbid_final_reference
```

It includes `ksu_handle_execveat_sucompat`, `ksu_handle_vfs_fstat`,
`ksu_handle_sys_read`, and `ksu_handle_input_handle_event`, plus all actual
xxKSU handlers and manual-security globals. Registry entries include parameter
types, return behavior, visibility, owner, profile allowance, and equivalent
path. A final-source scan resolves declarations and references and rejects any
official-only unresolved interface.

ABI validation extracts function declarations/definitions with a C signature
scanner, normalizes typedefs and qualifiers, checks argument count and important
types, visibility (`static` versus global), and return/side-effect contract.
For difficult signatures, a tiny compile probe against the candidate headers is
required. Name-only matches are never sufficient.

## 18. Target Manifest Schema

```yaml
schema: xxksu-susfs-target/v1
target_id: gki-android14-6.1
kernel: {family: android-gki, android: 14, linux: 6.1, arch: arm64}
kernel_source: {repo: ..., ref: ..., tree_hash: ...}
official_50: {repo: ..., branch: ..., commit: ..., patch_sha256: ...}
patch_11_policy: shared_xxksu_11
patch_51_policy: gki_android14_6_1
adapter: gki_android14_6_1
profiles: [gki-android14-6.1-manual, gki-android14-6.1-lsm_bl]
required_susfs: [KSU_SUSFS]
target_probes: [clean_required_paths, vfs_api, arm64_kallsyms]
```

Target manifests contain no mode choice. Unknown target IDs or mismatched kernel
identity are fatal.

## 19. Profile Manifest Schema

```yaml
schema: xxksu-susfs-profile/v1
profile_id: gki-android14-6.1-manual
target_id: gki-android14-6.1
mode: manual
patch_11: shared_xxksu_11
patch_51: target_manifest.patch_51_policy
fixtures:
  required: [scope-min-manual-hooks-v2.3, manual-security-hooks-v2.0]
  forbidden: []
config:
  required: {KSU: y, KSU_SUSFS: y, KSU_LSM_SECURITY_HOOKS: n, KSU_HACK_ARM64_BRANCH_LINK: n, KSU_TAMPER_SYSCALL_TABLE: n, KSU_KPROBES_KSUD: n}
transport_owners: {exec: FIXTURE_SCOPE_MIN, read_init_rc: FIXTURE_MANUAL_SECURITY}
forbidden_symbols: [official_only_registry]
validation: {owner_counts: exact, build: required}
```

The `lsm_bl` profile uses the same shape with no fixtures, all four canonical
values, ARM64/KALLSYMS prerequisites, and explicit owners for BL composite,
LSM-list/static, input registration, and SELinux replacement. The loader expands
only named common policy records; it prints the effective manifest and rejects
conflicts instead of normalizing hybrids.

## 20. Adapter Interface

An adapter receives a pinned target identity, clean source index, semantic unit,
and requested operation. It returns an exact source span/operation plus an
evidence record. Required methods are `identify`, `locate_anchor`,
`adapt_unit`, `adapt_fixture`, `validate_prerequisite`, and
`validate_final_source`.

Adapters may alter signatures, context, offsets, and vendor mechanics only when
the unit's semantic contract remains unchanged. They cannot select mode, owner,
or action. Missing/multiple anchors, unsupported APIs, or failed equivalence
checks are fatal unless the unit is explicitly optional.

| Adapter | Mechanical Differences | Semantic Policy Allowed? | Validation |
|---|---|---|---|
| xxKSU | source layout, symbol visibility, handler signatures | No | actual definitions, exports, init path |
| GKI 6.1 | 6.1 VFS/security anchors and LSM-list slots | No | exact anchors, ABI probes, BL descriptors |
| GKI 6.12 | idmap/unique-ID and static security-call context | No | exact context, API probes, minor-version fingerprint |
| Sultan 6.1 | vendor anchors and try-umount extensions | No | vendor source probes and extension inventory |
| Fixture adapter | target-specific insertion context | No | one exact insertion, caller count, no fuzz |

## 21. GKI 6.1 Adapter

Resolves Android 14/GKI 6.1 VFS and security anchors, ARM64 branch-link
descriptors, 6.1 LSM-list slots, and exact fixture call sites. It verifies clean
required paths have no pre-existing KSU/SuSFS callers, validates `security_*`
signatures, and checks BL fallback source/initialization descriptors.

## 22. GKI 6.12 Adapter

Resolves Android 16/Linux 6.12 `mnt_idmap`, unique mount-ID, VFS and SELinux
signature/context changes, including minor-version drift. It requires exact
fixture operations generated against the selected tree and rejects fuzz/tolerated
application. 6.12 policy wrappers that belong only to official backup-policy
transport are classified as replaced by xxKSU, not copied.

## 23. Sultan 6.1 Adapter

Reuses the 6.1 architecture policy while resolving Sultan vendor paths and
Sultan-specific SuSFS extensions such as try-umount and path adaptations. It
does not alter manual versus lsm_bl ownership. Vendor anchors and required
features are source-verified before emission.

## 24. Strict Manual Fixture Adaptation

Fixtures are semantic specifications with declared operations: scope-min owns
exec/access/stat/fstat-return/reboot; manual-security owns bprm/rename/file
permission/setuid/setprocattr. The adapter applies each operation to a function
identity and exact anchor selected from the target source, producing a
target-specific patch operation. Context tolerance and fuzz are disabled.

Validation requires: exactly the declared target function; one insertion per
semantic call site; actual xxKSU ABI match; expected global symbol visibility;
expected caller count; no BL/LSM/SCT/kprobe transport in the resolved config;
and no duplicate official call. A fixture failure is fatal, including when Git
could otherwise apply it with fuzz.

## 25. Manual Profile Composition

```text
clean target + shared 11 + target 51
 -> exact scope-min fixture
 -> exact manual-security fixture
 -> config all transport options n
 -> source/owner/ABI/config validation
 -> build
```

The final owners are fixtures for exec/access/stat/fstat/reboot/read/setuid and
setprocattr; xxKSU runtime owns input, AVC, fake status, and context/access
replacement; 51 owns pure SuSFS behavior. Both fixtures are mandatory for all
three manual targets.

## 26. LSM/BL Profile Composition

```text
clean target + shared 11 + target 51
 -> no fixtures
 -> LSM=y, BL=y, TAMPER=n, KPROBES_KSUD=n
 -> validate LSM list/static + BL descriptors + internal SCT fallback
 -> source/owner/ABI/config validation
 -> build, then runtime observability gate
```

6.1 setuid/setprocattr use LSM-list interception; 6.12 uses static security-call
ARM64 patching. Exec/access/stat use branch-link with the managed fallback. Read,
fstat-return, and reboot use the BL composite's internal syscall fallback.
Input and the remaining SELinux replacements are xxKSU runtime-owned. Fixtures
are forbidden, not merely ignored.

## 27. Duplicate / Hybrid Transport Prevention

The profile loader validates a complete truth table before composition. Manual
rejects any `y` for LSM, BL, tamper, or KSUD probes and rejects missing fixtures.
lsm_bl rejects any fixture and requires the exact four config values plus
ARM64/KALLSYMS. `BL=y` with `TAMPER=y` is rejected as Kconfig-invalid. Any
second owner claim, absent owner, official-only symbol, or active unselected
transport is fatal. There is no fallback from UNKNOWN and no conversion between
profiles.

## 28. Semantic Coverage Ledger

The ledger is a versioned JSON/YAML artifact keyed by source semantic ID and
source patch location. Each row records classification, action, owner tuple,
adapter, output location, validation status, evidence, and input hashes.

Generation requires every required unit to end in `ACCOUNTED`, `REPLACED`, or
`REROUTED` with proof. A changed context is matched by structural identity; a
new file/function/symbol or changed semantic fingerprint creates an unclassified
unit and fails. The ledger is emitted beside the patch and summarized in the
human report.

## 29. Unknown-Upstream Handling

Known units use stable semantic IDs plus normalized fingerprints of file,
function, symbols, and bounded statement shape. Context/line-offset changes can
be accepted only after adapter resolution and fingerprint verification. New
symbols, domains, or unmatched hunks become `UnknownSemanticBlock` with a
minimal diff excerpt, candidate function, nearest known units, and suggested
policy/adapter location. The run stops until a reviewed rule is added.

## 30. Reject Analysis

Rejects are collected with file, hunk, source span, and command provenance. The
engine maps each reject to a semantic unit, asks the adapter for a bounded exact
anchor, and revalidates semantic equivalence. A resolved reject is reported as
adaptation evidence; an unresolved reject is fatal. Clean application never
implies KEEP, and a reject never implies de-inline.

## 31. Final-Source Ownership Validation

Validation scans the fully composed tree and resolved runtime source/config
selection. For every path (exec, access, stat, fstat-return, read/init-RC,
reboot, setuid, input, SELinux domains), it counts active callers/registrations
and compares them to the profile owner set. Manual requires exactly one fixture
caller where specified and no active automated transport. lsm_bl requires the
xxKSU LSM/BL composite and no fixture caller. Input requires runtime registration
and forbids the official input symbol. Independent 51 SuSFS blocks are checked
for required presence and are allowed to coexist with transport owners.

```text
semantic coverage -> source integrity -> ownership -> ABI/symbols
                  -> resolved .config -> build -> runtime/release gates
```

| Stage | Input | Check | Output | Fatal Conditions |
|---|---|---|---|---|
| provenance | refs, hashes | identity and pin verification | verified inputs | mismatch or missing pin |
| parse | official 10/50 | typed diff parse | Patch model | malformed diff |
| semantic | Patch model, source | every unit classified | coverage ledger | UNKNOWN/unaccounted unit |
| transform | operations, clean tree | apply bounded operations | candidate tree | anchor/conflict failure |
| patch integrity | candidate tree | valid deterministic diff | generated patch | invalid hunk/metadata |
| clean apply | generated patch, clean tree | zero rejects | applied tree | reject or unexpected file |
| source/feature | applied tree | SuSFS and replacements present | static result | missing/forbidden behavior |
| ownership | final composed tree | exactly one owner/profile | owner ledger | zero or duplicate owner |
| ABI/symbol | final tree | signatures and official-only bans | ABI result | missing/conflicting symbol |
| config | resolved `.config` | requested equals expected | config result | mismatch or unmet dependency |
| build | profile tree/config | compile and link | artifacts/logs | profile build failure |
| runtime/release | test kernel and probes | BL/SELinux/feature behavior | gate result | required gate fails |

## 32. Final Config Validation

After target configuration and `olddefconfig` (or equivalent), V2 parses the
actual `.config`, including tristate normalization and selected dependencies.
For each option it records requested, resolved, expected, source fragment, and
reason. It requires:

```text
manual: KSU=y, KSU_SUSFS=y, LSM=n, BL=n, TAMPER=n, KPROBES_KSUD=n
lsm_bl: KSU=y, KSU_SUSFS=y, LSM=y, BL=y, TAMPER=n, KPROBES_KSUD=n
```

It additionally requires target SuSFS options and ARM64/KALLSYMS for lsm_bl,
and verifies that Kconfig did not silently disable a requested symbol. Any
requested/resolved mismatch is `FinalConfigMismatch` and prevents build status
from becoming PASS.

## 33. Build Validation

The build matrix contains all six named profiles. For each, V2 prepares an
isolated tree, composes patches/fixtures, resolves config, runs the pinned build
command, and captures logs, toolchain identity, artifacts, and hashes. Failures
are typed: generator/policy/adapter/profile/upstream-drift versus
toolchain/environment. Compiler failure is not automatically blamed on policy;
the classifier uses reproducibility and clean-tree probes. Every profile must
build before cutover.

## 34. BL Static / Runtime Validation Contract

Generation/static proof checks ARM64/KALLSYMS, exact BL descriptors and target
functions, required LSM/static source, internal SCT source inclusion, fallback
implementation, initialization path, and resolved config. Build proof checks
that all descriptors and fallback code compile and that no fixture transport is
linked.

Runtime proof is separate: a future test kernel must expose a structured BL
status containing descriptor success/failure, fallback activation, and restore
state for exec/access/stat/read/fstat/reboot. Without that telemetry the result
is `RUNTIME_REQUIRED`, never runtime PASS. Runtime failure is a pre-cutover gate
for lsm_bl release; static/build generation may still be reported independently.

## 35. SELinux Validation Contract

Static ownership validation maps AVC spoofing, fake status, setprocattr, and
context/access domains to xxKSU replacements in both modes. AVC and fake-status
replacement presence are HIGH-confidence static checks. Setprocattr and
context/access behavioral parity remain MEDIUM and require side-by-side runtime
probes before release; generation does not claim exact official backup-policy
parity. Missing replacement accounting is fatal; a parity mismatch is a release
gate according to the confidence policy.

## 36. Validation Result & Error Model

Results are structured, not boolean: `PASS`, `FAIL`, `NOT_APPLICABLE`,
`RUNTIME_REQUIRED`, and `UNRESOLVED`, with stage, evidence, diagnostics, and
provenance. Generation/static errors are fatal for output. Build errors are
fatal for that profile and cutover. Runtime-required results block release but
do not masquerade as generation failure.

Typed errors include `UnknownSemanticBlock`, `AmbiguousSemanticMatch`,
`MissingSemanticAnchor`, `MultipleSemanticAnchors`, `UnsupportedTarget`,
`UnsupportedProfile`, `MissingTransportOwner`, `DuplicateTransportOwner`,
`HandlerSymbolMissing`, `HandlerABIConflict`, `ForbiddenOfficialSymbol`,
`FixtureAdaptationFailure`, `FinalConfigMismatch`, `BuildFailure`,
`RuntimeValidationRequired`, and `UpstreamProvenanceMismatch`.

## 37. Deterministic Output

Canonicalize locale, timezone, path separators, file ordering, hunk ordering,
newline policy, and Git configuration. Use a fixed subject, author identity,
commit message template, and normalized zero timestamp for generated metadata;
put real timestamps only in sidecar reports. Blob IDs and line offsets are
derived from the canonical tree. Temporary paths never enter patches. Identical
input hashes, versions, and manifest produce byte-stable output where Git permits.

## 38. Temporary Worktree / Source Safety

Source acquisition populates an immutable, content-addressed cache. Generation
creates a temporary clean worktree, verifies repository identity, revision, and
clean status, applies operations, validates unexpected modifications, emits the
diff, and removes the worktree on success or failure. Manifest values are
validated enums/paths; no shell fragments or arbitrary commands are accepted.
Every external command is logged with sanitized arguments. User checkouts are
never mutated.

## 39. Network / Offline Boundary

Commands are staged: `fetch` obtains and hashes sources; `prepare` verifies and
indexes local inputs; `generate` is offline-only; `validate` consumes prepared
trees; `build` runs the matrix. `--offline` refuses missing cache entries.
Network acquisition cannot occur implicitly during semantic generation.

## 40. CLI Design

```text
v2 fetch --target TARGET --ref REF
v2 prepare --target TARGET --offline
v2 generate 11 --input prepared-id
v2 generate 51 --target TARGET
v2 validate patch PATCH --target TARGET
v2 validate profile PROFILE
v2 validate all-profiles
v2 explain unit SEMANTIC_ID --profile PROFILE
v2 provenance PATCH_OR_REPORT
```

`generate 51` accepts a target, never a mode; profile composition is a separate
explicit command. `validate profile` requires one of the six exact IDs, making
ambiguous hybrids impossible.

## 41. Explainability & Generation Reports

Each run emits a machine ledger and human report listing inputs, decisions,
owners, adapter actions, preserved/replaced blocks, validation stages, and
errors. `explain unit` answers why a hunk was kept, split, rerouted, or removed,
which evidence and adapter were used, and who owns the final path. Reports
include before/after source spans and profile-specific owner/config reasoning.

## 42. Test Architecture

`tests/unit` covers diff/model/ABI primitives; `tests/fixtures` covers exact
fixture adaptation per target; `tests/golden` stores reviewed semantic snapshots;
`tests/integration` composes patches; `tests/regression` compares known-good
behavior; `tests/semantic` exercises coverage, unknown drift, mixed splitting,
ownership, and required-feature inventories. Parser, adapter, config, build
matrix, and invalid-hybrid tests are mandatory. Golden equality is informative,
never the semantic oracle.

## 43. Known-Good Regression Strategy

Known-good 11/51 patches and cheetah/popsicle workflows are behavioral references.
V2 compares semantic ledgers, final-source inventories, owner counts, and build
results. Text differences are reviewed through a semantic differential report;
they are not automatically failures. References are never used as output
templates or upstream truth.

## 44. Current Generator Migration Audit

| Current Mechanism | Classification | V2 Replacement | Reason |
|---|---|---|---|
| repository/source setup | REFACTOR | pinned fetch/prepare/cache | current 11 ignores input and lacks provenance |
| unified diff parsing | REPLACE | typed diff parser | current string handling loses structure |
| hunk handling/count recalculation | REUSE then REFACTOR | tree diff/emitter plus count tests | useful concept, safer implementation |
| string replacements | DELETE | semantic operations | silent anchor failure is unsafe |
| whole-file exclusions | DELETE | per-unit policy | loses mixed/pure behavior |
| keyword filtering | DELETE | symbol/ABI registry | names do not establish ownership |
| Sultan extra chunks | REFACTOR | Sultan adapter semantic units | preserve extension with provenance |
| target substitutions | REFACTOR | adapter interface | separate mechanics from policy |
| git apply checks | REFACTOR | diagnostic application stage | apply status is not classification |
| format-patch generation | REUSE | deterministic emitter | retain contract, normalize metadata |
| CLI | REFACTOR | explicit staged CLI | prevent mode ambiguity |
| logging/error handling | REPLACE | typed results and reports | fail closed and explain |

Migration is incremental: keep old scripts unchanged, introduce V2 in shadow
mode, then retire only after cutover evidence.

## 45. Shadow-Mode Migration

For identical pinned inputs, run current and V2 generators side by side. Compare
coverage ledgers, patches, final trees, known-good semantic inventories, all six
owner/config validations, and builds. Every difference receives a reviewed
classification: intentional semantic fix, target adaptation, metadata/context,
or regression. A single successful V2 run is insufficient for cutover.

## 46. Cutover Criteria

Cutover requires no UNKNOWN units, clean application, exact fixture adaptation,
no forbidden official-only symbols, all six owner validations, all six resolved
configs, all six builds, deterministic regeneration, reviewed known-good
differentials, and human approval. BL runtime observability and MEDIUM-confidence
SELinux parity are explicitly tracked as pre-cutover/release gates, not hidden by
static PASS.

## 47. Current Generator Retirement

Lifecycle is `ACTIVE -> SHADOWED -> LEGACY -> REMOVED`. Shadowed requires two
complete comparison cycles; Legacy requires cutover criteria and documented
rollback; removal requires a subsequent release retaining archived source and
provenance. No old generator is deleted during initial V2 work.

## 48. V2 Implementation Phases

| Phase | Scope | Dependencies | Acceptance Criteria | Review Gate |
|---|---|---|---|---|
| V2.1 | models, diff parser/emitter | none | round-trip parser tests | parser review |
| V2.2 | provenance/cache/manifest loader | V2.1 | pinned offline preparation | manifest review |
| V2.3 | semantic inventory/ledger | V2.1-2 | all baseline units accounted | policy review |
| V2.4 | 50->51 policy/mixed splitter | V2.3 | stat mixed golden passes | semantic review |
| V2.5 | target adapters | V2.4 | 6.1/6.12/Sultan anchors exact | adapter review |
| V2.6 | strict fixtures | V2.5 | six manual compositions source-pass | fixture review |
| V2.7 | 10->11 policy | V2.3 | shared 11 regenerated from 10 | 11 review |
| V2.8 | ownership/symbol/ABI validation | V2.6-7 | invalid owners/ABIs fail | validator review |
| V2.9 | profile composition/config | V2.8 | six resolved configs exact | profile review |
| V2.10 | build matrix | V2.9 | six builds pass | build review |
| V2.11 | regression/golden | V2.10 | reviewed differentials | regression review |
| V2.12 | shadow mode | V2.11 | repeated parity evidence | migration review |
| V2.13 | cutover tooling only | V2.12 | criteria and approval recorded | explicit human gate |

Each phase stops on its review gate; later phases cannot normalize earlier
UNKNOWN or unresolved errors.

## 49. Runtime / Release Gates

| Concern | Static Proof | Build Proof | Runtime Proof | Gate Classification |
|---|---|---|---|---|
| SELinux setprocattr parity | replacement/owner | compiles | side-by-side behavior | PRE_CUTOVER_GATE |
| SELinux context/access parity | replacement/owner | compiles | transaction probes | RELEASE_GATE |
| BL patch success/fallback | descriptors/config | code links | telemetry/status | PRE_CUTOVER_GATE |
| SuSFS commands | 11 dispatch/symbols | compiles | command behavior | RELEASE_GATE |
| safe-mode input | registration source | compiles | key sequence | OPTIONAL_RUNTIME_CONFIRMATION |
| zygote/umount | SID/handler chain | compiles | policy behavior | RELEASE_GATE |

Runtime-required results remain visible even when generation/static/build pass.

## 50. Remaining Unknowns

Existing evidence leaves exact SELinux context/access parity at MEDIUM, BL
runtime success unobservable without future telemetry, and release-archive Git
commit provenance incomplete. These do not alter KEEP/REMOVE policy. They are
explicit runtime/release evidence requirements. Any new upstream semantic unit,
unverified adapter anchor, or ABI ambiguity is an implementation-time UNKNOWN
and must fail closed.

## 51. Implementation Blocker Resolution

Blocker A is resolved by semantic fixture specifications plus per-target exact
anchor operations, no fuzz, strict ABI and caller-count validation, and fatal
adaptation errors.

Blocker B is resolved by separating static descriptor/fallback checks and build
link checks from a runtime telemetry contract. V2 reports `RUNTIME_REQUIRED`
until a test kernel supplies BL success/fallback/restore evidence.

Blocker C is resolved by running target configuration resolution, parsing the
actual final `.config`, checking every requested/resolved/expected value and
dependency prerequisite, and making mismatch fatal.

## 52. Final Implementation Readiness

The architecture is complete: all targets have both required profiles, 11 and
51 are shared at the mandated boundaries, semantic transformations are
source-tree based and fail closed, and the three Phase 1.6 blockers have concrete
engineering contracts. Implementation remains a separate future action and is
not performed by this design-only run; the final status below describes whether
the design is sufficiently specified to begin that reviewed implementation.

## 53. Confidence Report

| Area | Confidence | Basis | Remaining Evidence |
|---|---|---|---|
| six-profile architecture | HIGH | Phase 1.6 contract and known-good workflows | six V2 builds |
| shared 11 | HIGH | no mode-specific 11 evidence | regeneration/build |
| one 51 per target | HIGH | transport-neutral policy and ownership split | six compositions |
| manual fixture ABI | HIGH | fixture source and tested workflows | strict adapter tests |
| lsm_bl composite ownership | HIGH | pinned xxKSU Kconfig/source | runtime telemetry |
| pure SuSFS preservation | HIGH | Phase 1.5/1.6 semantic inventory | feature tests |
| SELinux AVC/fake status replacement | HIGH | actual xxKSU implementation | runtime confirmation |
| SELinux parity | MEDIUM | replacement intent/build evidence | side-by-side probes |
| deterministic generation | HIGH (design) | canonical inputs/emitter rules | repeated runs |
| implementation readiness | HIGH (design) | blockers have fail-closed contracts | human review |

The design is sufficiently concrete for a reviewed implementation phase. This
document itself does not authorize or perform that implementation.

V2 ARCHITECTURE COMPLETE: YES
IMPLEMENTATION BLOCKERS RESOLVED: YES
SAFE TO IMPLEMENT V2: YES
