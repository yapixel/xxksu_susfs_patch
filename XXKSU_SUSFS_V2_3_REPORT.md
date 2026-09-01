# xxKSU + SuSFS V2.3 Implementation Report

## 1. Executive Result

V2.3 implements a deterministic, policy-neutral semantic inventory foundation:
typed semantic records, stable IDs and fingerprints, traceable evidence and
relationships, a reviewable specification registry, conservative candidate
detection/resolution, a coverage ledger, and fatal relevant-UNKNOWN handling.
It performs no patch transformation, source mutation, composition, build, or
V2.4 work.

## 2. Files Created / Modified

Created:

- `.github/scripts/v2/semantic/__init__.py`
- `.github/scripts/v2/semantic/model.py`
- `.github/scripts/v2/semantic/registry.py`
- `.github/scripts/v2/semantic/inventory.py`
- `.github/scripts/v2/semantic/ledger.py`
- `.github/scripts/v2/tests/test_v23.py`
- `XXKSU_SUSFS_V2_3_REPORT.md`

Modified:

- `.github/scripts/v2/__init__.py` — additive public exports for V2.3 types.

No generator, patch, fixture, workflow, prior report, or prior task was modified.

## 3. V2.1 Regression Status

V2.1 parser/emitter/model behavior did not change. All 16 V2.1 tests pass.

## 4. V2.2 Regression Status

V2.2 provenance/cache/fetch/prepare/manifest behavior did not change. All 16
V2.2 tests pass.

## 5. V2.3 Architecture

The flow is verified observation → bounded candidate detection → registry-based
resolution → typed semantic unit/evidence → deterministic ledger → completeness
check. Detection and resolution are separate, and the ledger records facts only.

## 6. Semantic Schema

Persisted semantic IDs use `xxksu-susfs-semantic/v1`; inventory and ledger
serialization use `xxksu-susfs-inventory/v1` and
`xxksu-susfs-ledger/v1`. Unknown semantic schema versions fail closed.

## 7. SemanticUnit Model

`SemanticUnit` contains a typed ID, kind, domain, relative location, evidence,
relationships, confidence, factual coverage state, and neutral contract data.
It contains no future transformation action.

## 8. Semantic ID Contract

IDs are stable, dotted, human-reviewable behavior/role names such as
`transport.exec.definition` and `selinux.fake_status`. Construction excludes
line/hunk numbers, absolute roots, timestamps, and random UUIDs. Line numbers
and absolute paths therefore cannot affect semantic identity.

## 9. Semantic Fingerprint Contract

Fingerprints identify textual/structural evidence, not behavior identity. They
hash canonical JSON containing relative path, function/anchor, exact normalized
statements, required/called symbols, guards, source kind, and source role.
Meaningful operators, argument order, names, control flow, and guards are not
normalized away. Changed evidence changes the fingerprint without necessarily
renaming the semantic behavior.

## 10. Evidence Model

`EvidenceRecord` retains verified source identity, source type, relative and
structural location, fingerprint/digest, priority, typed confidence, notes, and
machine-readable attributes such as ABI and structural-container identity.
The source identity accepts the V2.2 prepared/provenance identity supplied by
the caller; it is never derived from a temporary path.

## 11. Evidence Priority

Recorded priority follows the accepted order: target kernel 1, actual xxKSU 2,
official 10/50 3, fixtures 4, known-good references 5, current generated
artifacts 6, generators 7, and documentation/other observations 8. Priority is
traceability metadata, not an automatic policy score.

## 12. Confidence Model

Confidence is the enum `HIGH`, `MEDIUM`, `LOW`, or `UNKNOWN`. It never selects a
future action. When compatible evidence is merged, the conservative lower
confidence remains visible.

## 13. Semantic Kind Taxonomy

The typed taxonomy distinguishes SuSFS behavior, handler definition,
declaration, Linux call site, runtime registration, static-key gate, LSM/security
hook, kprobe, syscall-table hook, ARM64 branch-link, manual source hook, fixture
hook, config control, SELinux behavior, transport wrapper, and UNKNOWN.

## 14. Relationship Model

Relationships are typed as `DEFINES`, `CALLS`, `GATES`, `REGISTERS`, `WRAPS`,
`PROVIDES_TRANSPORT_FOR`, `FALLBACK_FOR`, `REPLACES_BEHAVIOR_OF`, and
`RELATED_TO`. Both endpoints must exist in the ledger. V2.3 records these
relationships but does not enforce final ownership.

## 15. Candidate Detection

The detector conservatively exposes observations on registered paths, with
recognized KSU/SuSFS/security/input/BL/syscall symbols, or with relevant config
guards. Bounded symbol recognition only creates candidates; it never determines
semantic meaning by itself.

## 16. Semantic Resolution

Resolution requires a matching combination of relative path, source family,
source role, expected function when declared, and expected symbol. Zero matches
become UNKNOWN; multiple matches become an ambiguous UNKNOWN in inventory or a
typed `AmbiguousSemanticMatch` when the resolver is invoked directly.

## 17. Semantic Specification Registry

The data-oriented registry contains 50 reviewed factual specifications covering
official-10 integration/config concepts, official-50 transport observations,
actual xxKSU mechanisms, fixture providers, official-only interfaces, BL
composite parts, and independent SELinux domains. It contains no V2.4 action.

## 18. Official 10 Inventory

The registry represents SuSFS initialization/control, actual and official-only
handler-side concepts, and exposed transport assumptions. The existing generated
11 is exercised as lower-priority bounded repository evidence. A complete
production official-10 inventory remains blocked because its immutable prepared
content identity is unresolved in V2.2; no latest source was fetched.

## 19. Official 50 Inventory

The model supports separate evidence identities for Sultan 6.1, GKI 6.1, and
GKI 6.12 while sharing behavior-oriented semantic IDs. Target/version locations
remain evidence. A bounded structurally valid real 51 corpus sample is exercised;
complete production inventories of all three official 50 inputs remain blocked
pending verified complete prepared inputs.

## 20. Actual xxKSU Inventory

Specifications independently represent exec/access/stat handlers and wrappers,
actual fstat-return functions, reboot, setresuid, input registration, LSM,
branch-link, internal syscall fallback, kprobes, config controls, initialization,
and SELinux-hide behavior. Actual names/roles are not inferred from official
KernelSU interfaces. Complete source-tree inventory awaits a pinned prepared
xxKSU tree.

## 21. Fixture Inventory

Both real fixtures are exercised without modification or application.
Scope-min evidence covers exec/access/stat/fstat-return/reboot; manual-security
evidence covers bprm/rename/read/setuid/setprocattr. Its historical malformed
unified-diff context is retained as bounded raw evidence in the test rather than
interpreting parser failure semantically.

## 22. Manual Transport Representation

Fixture calls use `MANUAL_SOURCE_HOOK` or declaration evidence and retain their
fixture source identity. They are not labeled kprobes, syscall-table hooks, or
LSM hooks.

## 23. LSM / Security Representation

LSM-list/static mechanisms use `LSM_SECURITY_HOOK`; manual security calls use
`MANUAL_SOURCE_HOOK`. They remain distinct even when both relate to the same
setuid or setprocattr behavior.

## 24. ARM64 Branch-Link Representation

ARM64 call-site patching is `ARM64_BRANCH_LINK`, with distinct per-path evidence
and a separate composite wrapper identity. It is not represented as independent
TAMPER profile selection.

## 25. Internal Syscall Fallback Representation

The internal fallback is `SYSCALL_TABLE_HOOK` evidence related with
`FALLBACK_FOR` to branch-link and `RELATED_TO` the `transport.bl.composite`
unit. This preserves both internal mechanisms while leaving the canonical
profile declaration `TAMPER=n` untouched.

## 26. Handler / Caller Distinction

Source role is part of matching and fingerprinting. The mandatory same-symbol
test produces distinct handler definition, declaration, and Linux caller units;
a function name alone cannot classify any of them.

## 27. ABI Evidence

Evidence attributes preserve parsed/declared return type, argument types,
pointer/struct shape, and other ABI facts supplied by a scanner or verified
source observation. V2.3 records these facts but performs no ABI enforcement.

## 28. Official-Only Symbol Evidence

Separate registry entries label `ksu_handle_execveat_sucompat`,
`ksu_handle_vfs_fstat`, `ksu_handle_sys_read`, and
`ksu_handle_input_handle_event` as official-interface evidence with the accepted
notes about actual xxKSU differences. No absent xxKSU function is invented.

## 29. Mixed Semantic Block Representation

Multiple observations can share one `container_id` and each receive `MIXED`
factual state. The mixed-hunk test keeps one structural container with identified
pure-SuSFS and transport observations. V2.3 does not rewrite or split its text.

## 30. SELinux Inventory

AVC/slow-audit replacement, fake status, setprocattr, and context/access are
independent semantic IDs. Manual/LSM transport observations remain separate
from replacement behavior.

## 31. SELinux Confidence Preservation

AVC and fake-status entries remain HIGH. Setprocattr and context/access entries
remain MEDIUM exactly as established by Phase 1.5/1.6; passing structural tests
does not promote them.

## 32. Reboot Inventory

The registry separates actual handler definition, official Linux caller, manual
fixture caller, internal syscall fallback, command/ABI notes, and future
relationships. The incompatible return-contract evidence is recordable without
making a transformation decision.

## 33. Exec Inventory

Actual definition, official Linux caller, fixture declaration/caller,
official-only sucompat definition, and branch-link transport have independent
IDs/kinds/evidence.

## 34. Access / Stat Inventory

Official callers, actual/manual ABI observations, fixture callers, BL transport,
and pure SuSFS stat/mount-ID behavior are independently representable. Mixed
stat evidence is not collapsed to one handler-name unit.

## 35. Fstat-Return Inventory

Actual `ksu_handle_newfstat_ret`/`ksu_handle_fstat64_ret`, manual fixture calls,
internal fallback, and official-only `ksu_handle_vfs_fstat` have separate
specifications. Absence is not repaired by inventing a symbol.

## 36. Read / Init-RC Inventory

Official `ksu_handle_sys_read`, manual `ksu_file_permission`, actual install-RC
behavior, and BL-managed `ksu_handle_sys_read_fd` fallback are distinct. The
fallback is not mislabeled as independent TAMPER mode.

## 37. Setuid Inventory

Actual definition/cred chain, official direct transport, manual-security call,
and 6.1/6.12 LSM mechanisms remain independently accountable. No 11 is
generated.

## 38. Input Safe-Mode Inventory

Official input-handler assumptions are distinct from actual xxKSU
`input_register_handler`/volume-event runtime registration. Runtime registration
is not a Linux manual caller.

## 39. Config Inventory

Independent config-control specifications cover KSU/SuSFS, LSM security hooks,
ARM64 branch-link, independent syscall tamper, and KSUD kprobes. V2.3 associates
configuration evidence only; it runs no config resolution.

## 40. Coverage Ledger

Every detected relevant candidate receives a deterministic `LedgerEntry`.
Entries retain unit/evidence/relationships/confidence and one of the factual
states `IDENTIFIED`, `MIXED`, `UNKNOWN`, `DUPLICATE_EVIDENCE`, or `UNRESOLVED`.
Canonical JSON sorts semantic IDs, evidence, and relationships.

## 41. UNKNOWN Handling

An unmatched or ambiguous relevant candidate receives a stable
`unknown.<fingerprint-prefix>` ID, UNKNOWN kind/confidence/state, traceable
evidence, and diagnostic reason. It is never silently ignored or converted to a
future action.

## 42. Completeness Rules

Completeness requires zero relevant UNKNOWN/UNRESOLVED entries, zero semantic-ID
contract collisions, zero orphan evidence, and valid relationship endpoints.
Any relevant UNKNOWN raises `InventoryIncomplete`.

## 43. Duplicate / Collision Handling

Compatible target-specific evidence for one behavior ID is merged and preserved.
The same ID with incompatible kind, domain, or contract raises
`SemanticIdCollision`; no automatic merge or repair occurs. Orphan evidence
raises `OrphanEvidence` and keeps the ledger incomplete.

## 44. Deterministic Inventory Identity

Inventory identity is SHA-256 over canonical JSON containing semantic schemas,
specification version/registry, caller-supplied provenance identity, units,
fingerprints, relationships, and ledger states. Absolute roots, iteration order,
wall-clock time, and temporary directories are absent. Changed relevant evidence
changes both fingerprint and inventory identity.

## 45. Production Input Readiness

The engine is complete, but complete production inventory is BLOCKED. V2.2
deliberately leaves exact immutable kernel and official-10 content identities
unresolved and does not provide all three complete prepared official-50 inputs or
a materialized prepared xxKSU tree. V2.3 did not fetch or fabricate them.

## 46. Test Architecture

The standard-library suite adds 15 V2.3 tests to the existing 32. It covers
model invariants, schemas, detection/resolution, errors, registry coverage,
real corpus observations, determinism, relationships, and terminology without
network, patch application, or source mutation.

## 47. Real Evidence Test Coverage

Tests use the existing 11 patch, both real manual fixtures, and a complete
structurally valid file-patch sample from the existing GKI 6.1 51 corpus. The
three official-50 target families are represented as separate evidence source
identities while sharing semantic identity.

## 48. Unknown Injection Test

A synthetic new `ksu_handle_future_feature` candidate is detected, resolves to
UNKNOWN, enters the ledger, and makes completeness raise
`InventoryIncomplete`.

## 49. Mixed-Hunk Test

One synthetic stat container includes pure SuSFS and transport-sensitive
observations. Both are independently identified with factual `MIXED` state;
the input text is not transformed.

## 50. Function-Name Ambiguity Test

The same `ksu_handle_execveat` spelling is tested as a definition, declaration,
and caller. Path, source family, and source role resolve three distinct kinds,
proving name-only classification is absent.

## 51. Transport Terminology Tests

Tests prove manual call, kprobe, LSM hook, ARM64 BL, syscall-table fallback, and
runtime registration are distinct enum values. BL/fallback/composite
relationships serialize independently.

## 52. Determinism Tests

Tests prove stable IDs/fingerprints; insertion-order-independent ledger output;
temporary-root independence; multiple target evidence preservation; changed
evidence changing identity; and no timestamp contribution.

## 53. Negative Tests

Negative coverage includes unknown schema, invalid semantic kind/confidence,
malformed specification, incompatible ID collision, orphan evidence, invalid
relationship target, unmatched relevant candidate, ambiguous resolution, unsafe
path, and UNKNOWN completeness failure. Invalid records are not repaired.

## 54. Commands Executed

Executed from WSL Debian:

```text
python3 -m compileall -q .github/scripts/v2
PYTHONPATH=.github/scripts python3 -m unittest discover -s .github/scripts/v2/tests -v
PYTHONPATH=.github/scripts python3 -c "import v2; import v2.semantic as s; print(v2.parse_patch(\"\").structural_key(), len(tuple(s.default_registry())))"
grep -RInE "...transformation vocabulary..." .github/scripts/v2/semantic .github/scripts/v2/tests/test_v23.py
grep -RInEi "...unsafe shortcuts..." .github/scripts/v2/semantic .github/scripts/v2/tests/test_v23.py
```

## 55. Test Results

All 47 tests passed: 16 V2.1, 16 V2.2, and 15 V2.3. Compile/import checks
passed. The smoke check returned `((), (), ()) 50`.

## 56. Git Status Before / After

Before V2.3, the worktree contained the pre-existing untracked V2 package and
Phase/V2 documents. After V2.3, those remain plus the semantic package, V2.3
tests, V2.3 task supplied by the user, and this report. No staging, commit,
reset, clean, checkout, restore, stash, branch, or remote operation occurred.

## 57. Transformation-Policy Audit

The required read-only audit searched V2.3 implementation/tests for executable
future action vocabulary, patch-application classification, whole-file and
handler-name-only shortcuts, external commands/build/config resolution, and
source mutation. It found none. `MIXED` appears only as a factual coverage
state; no executable future transformation action exists. `REPLACES_BEHAVIOR_OF`
is only an observational relationship type, not a decision.

## 58. Design Deviations

No accepted architecture changed. A small bounded line/symbol/source-role scanner
was sufficient; no C AST dependency was added. Complete production registry
population is intentionally not claimed without V2.2-prepared sources. The
historical manual-security malformed diff is observed only in a bounded test;
parser failure never supplies semantic meaning.

## 59. Remaining V2.3 Limitations

The scanner is intentionally lexical and bounded, not a general C parser.
Complete official 10/50 and actual xxKSU production evidence must be prepared
and inventoried before production completeness. MEDIUM SELinux parity remains a
future runtime/release concern. V2.3 does not enforce ABI or exactly-one-owner.

## 60. V2.4 Readiness

The semantic model, registry boundary, candidate accounting, and fail-closed
UNKNOWN behavior are stable enough for independent human audit and possible
V2.4 authorization. Production-input blockers remain explicit and must not be
normalized during future policy work. This report does not authorize V2.4.

## 61. Confidence Report

| Area | Confidence | Evidence |
|---|---|---|
| semantic models/IDs | HIGH | invariant/schema/determinism tests |
| fingerprints/evidence | HIGH | changed-evidence and serialization tests |
| candidate UNKNOWN boundary | HIGH | injection and ambiguity tests |
| mixed-block accounting | HIGH | shared-container multi-unit test |
| mechanism terminology | HIGH | distinct-kind and BL relationship tests |
| real local evidence handling | HIGH for bounded inputs | 11, fixtures, valid 51 sample |
| complete production inventory | BLOCKED | unresolved/unprepared authoritative inputs |
| SELinux behavioral parity | MEDIUM | preserved accepted confidence |
| transformation policy | NOT IMPLEMENTED | mandatory audit clean |

V2.3 SEMANTIC MODEL COMPLETE: YES
V2.3 INVENTORY ENGINE COMPLETE: YES
V2.3 COVERAGE LEDGER COMPLETE: YES
V2.3 UNKNOWN FAIL-CLOSED COMPLETE: YES
V2.3 TESTS PASS: YES
PRODUCTION SEMANTIC INVENTORY COMPLETE: BLOCKED
SAFE TO BEGIN V2.4: YES
