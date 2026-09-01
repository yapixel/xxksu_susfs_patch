# xxKSU + SuSFS Phase 1.6 — Dual-Mode Target Manifest

## Status

This is a **design-contract verification task only**.

Do **NOT** implement V2.

Do **NOT** modify:

- existing Python generators
- existing generated patches
- workflows
- fixtures
- kernel source
- xxKSU source
- SuSFS source
- Phase 1 report
- Phase 1.5 report

You may create exactly one new deliverable:

```text
./XXKSU_SUSFS_PHASE1_6_REPORT.md
```

After writing that report, **STOP**.

---

# 1. Read Existing Analysis First

Before doing anything else, read:

```text
./XXKSU_SUSFS_ANALYSIS_REPORT.md
./XXKSU_SUSFS_PHASE1_5_REPORT.md
```

Treat Phase 1.5 as the current semantic/evidence baseline.

Do **NOT** repeat the complete Phase 1 or Phase 1.5 investigation.

Phase 1.6 exists to resolve one specific target-contract issue discovered during human review of Phase 1.5.

---

# 2. Human Decision That Is Now Authoritative

Phase 1.5 ended with an unresolved human decision about whether each target should support:

```text
manual
```

or:

```text
lsm_bl
```

That framing is now superseded.

The authoritative project requirement is:

> Every supported target must support BOTH `manual` and `lsm_bl` as separate valid build profiles.

Therefore the required support matrix is:

| Target | manual | lsm_bl |
|---|---:|---:|
| GKI Android 14 / Linux 6.1 | REQUIRED | REQUIRED |
| GKI Android 16 / Linux 6.12 | REQUIRED | REQUIRED |
| Sultan Android 14 / Linux 6.1 | REQUIRED | REQUIRED |

This produces six required build profiles:

```text
gki-android14-6.1-manual
gki-android14-6.1-lsm_bl

gki-android16-6.12-manual
gki-android16-6.12-lsm_bl

sultan-android14-6.1-manual
sultan-android14-6.1-lsm_bl
```

Do not reinterpret this as choosing one mode per target.

Both modes are required.

---

# 3. Critical Ownership Rule

The phrase:

> exactly one owner per semantic path

applies to an individual **final build profile**, not to the target as a whole.

For example:

```text
GKI 6.1
├── manual
│   └── exec transport owned by scope-min fixture
│
└── lsm_bl
    └── exec transport owned by xxKSU branch-link machinery
```

This is valid.

What is NOT valid is a single final build profile in which the same semantic transport is simultaneously owned by incompatible or duplicate mechanisms.

Example of an invalid composition:

```text
gki-android14-6.1-manual
├── scope-min exec call
└── xxKSU BL exec interception
```

if both mechanisms are active and would produce duplicate ownership.

Phase 1.6 must therefore reason about ownership **per profile**.

---

# 4. Architectural Model to Preserve

Phase 1.5 established the following model.

## 4.1 Manual mode

Manual mode delegates Linux source call sites to fixtures.

Expected ownership:

```text
scope-min-manual-hooks-v2.3.patch
    → exec
    → access
    → stat
    → fstat-return
    → reboot

manual-security-hooks-v2.0.patch
    → security/bprm
    → rename
    → file-permission / init-RC
    → setuid
    → setprocattr
```

xxKSU still owns the actual handlers and runtime functionality.

The fixtures own only the required Linux-side transport/call sites.

---

## 4.2 LSM/BL mode

LSM/BL mode does NOT use the manual fixtures for transport.

Transport is owned by actual xxKSU mechanisms, including where applicable:

```text
LSM hook-list interception
ARM64 branch-link patching
syscall-table fallback/replacement
security-call interception
xxKSU runtime registration
```

Exact mechanisms differ between Linux 6.1 and Linux 6.12.

Do not flatten all of these into the term "hook".

Preserve the terminology established by Phase 1.5.

---

## 4.3 Input path

Input safe-mode behavior is special.

It is not fixture-owned in manual mode.

Actual xxKSU registers its own input handler.

Therefore input may legitimately remain xxKSU-owned in BOTH profiles.

Do not force every semantic path to change owner between manual and lsm_bl.

---

# 5. 51 Must Remain Transport-Neutral

The following Phase 1.5 conclusion remains authoritative:

> 51 must not implicitly choose a KernelSU transport mode.

51 owns SuSFS kernel semantics and target-kernel integration.

51 must not become:

```text
51-manual.patch
```

or:

```text
51-lsm.patch
```

merely because two final build profiles exist.

The intended architecture is:

```text
                    official 50
                        │
                        ▼
             semantic 50 → 51 transform
                        │
                        ▼
              transport-neutral 51
                        │
             ┌──────────┴──────────┐
             ▼                     ▼
          manual                 lsm_bl
             │                     │
      manual fixtures         xxKSU runtime
             │              LSM / BL / syscall
             └──────────┬──────────┘
                        ▼
                 final build profile
```

Phase 1.6 must verify whether the evidence supports this architecture for all six profiles.

If any target requires transport-specific differences inside 51 itself, identify the exact semantic reason and mark it explicitly.

Do not silently create mode-specific 51 policy.

---

# 6. Objective

Produce an authoritative **Dual-Mode Target Manifest** suitable for use as the contract for V2 generator design.

The report must answer:

1. What are the six supported profiles?
2. Which component owns every required semantic path in each profile?
3. Which fixtures are required in manual mode?
4. Which xxKSU mechanisms are required in lsm_bl mode?
5. Which Kconfig settings distinguish the profiles?
6. Which mechanisms must be disabled to avoid duplicate ownership?
7. What must 11 provide?
8. What must 51 provide?
9. What must fixtures provide?
10. What must target adapters provide?
11. What final-source validation is required?
12. What build/config validation is required?
13. Can one transport-neutral 51 safely serve both profiles for every target?

---

# 7. Required Profile Matrix

Create a matrix with one row for every profile:

| Profile | Target | Kernel | Transport Mode | Fixtures | LSM Security Hooks | ARM64 BL | Syscall/Kprobe Requirements | 11 | 51 | Status |
|---|---|---|---|---|---|---|---|---|---|---|

Required rows:

```text
gki-android14-6.1-manual
gki-android14-6.1-lsm_bl
gki-android16-6.12-manual
gki-android16-6.12-lsm_bl
sultan-android14-6.1-manual
sultan-android14-6.1-lsm_bl
```

Use exact evidence for configuration requirements.

Do not guess configuration values.

If a required value cannot be proven, mark:

```text
UNRESOLVED
```

and identify what evidence is missing.

---

# 8. Required Semantic Ownership Matrix

For EACH of the six profiles, account for at least:

```text
exec
access
stat
fstat-return
read / init-RC
reboot / supercall
setuid / zygote handling
input safe mode
SELinux AVC hiding
SELinux setprocattr hiding
SELinux fake status
SELinux context/access hiding
SuSFS stat/mount behavior
uname spoofing
```

Use this table:

| Profile | Semantic Path | Final Owner | Transport Mechanism | Handler/Equivalent | Source of Transport | Duplicate Risk | Validation Required | Confidence |
|---|---|---|---|---|---|---|---|---|

Allowed ownership sources include:

```text
51
11
scope-min fixture
manual-security fixture
xxKSU LSM
xxKSU BL
xxKSU syscall-table path
xxKSU kprobe path
xxKSU runtime registration
target kernel
target adapter
```

Do not use vague ownership such as:

```text
KernelSU
hook
kernel
patch
```

when a more precise mechanism is known.

---

# 9. Manual Profile Contract

For each target, prove the manual profile composition.

Expected model:

```text
target kernel
+ transport-neutral 51
+ xxKSU + 11
+ scope-min-manual-hooks-v2.3.patch
+ manual-security-hooks-v2.0.patch
+ manual-mode configuration
```

Verify whether this exact composition applies to:

```text
GKI 6.1
GKI 6.12
Sultan 6.1
```

Do not assume the fixtures apply identically merely because known-good workflows use them.

Check:

- kernel-version context
- handler ABI
- security API differences
- duplicate transport
- required config
- final caller count

For each semantic path, prove there is exactly one active final transport owner.

---

# 10. LSM/BL Profile Contract

For each target, prove the lsm_bl profile composition.

Expected conceptual model:

```text
target kernel
+ transport-neutral 51
+ xxKSU + 11
+ NO manual transport fixtures
+ CONFIG_KSU_LSM_SECURITY_HOOKS=y
+ required ARM64 BL/runtime configuration
```

Determine the exact required xxKSU configuration from evidence.

In particular inspect/confirm:

```text
CONFIG_KSU_LSM_SECURITY_HOOKS
CONFIG_KSU_HACK_ARM64_BRANCH_LINK
CONFIG_KSU_TAMPER_SYSCALL_TABLE
CONFIG_KSU_KPROBES_KSUD
```

Do not assume all four must be enabled.

Determine which are:

```text
REQUIRED
OPTIONAL
FORBIDDEN
IRRELEVANT
VERSION_DEPENDENT
UNRESOLVED
```

for each lsm_bl profile.

Explain initialization/fallback behavior where syscall-table transport is temporarily or conditionally used by xxKSU.

---

# 11. Duplicate-Transport Analysis

This section is mandatory.

For every semantic path, determine what happens if manual fixtures and LSM/BL transport are accidentally active simultaneously.

Classify:

```text
SAFE_COEXISTENCE
DUPLICATE_CALL
DOUBLE_SIDE_EFFECT
ABI_CONFLICT
ORDER_DEPENDENT
CONFIG_PREVENTED
UNKNOWN
```

Pay special attention to:

```text
exec
access
stat
fstat-return
read
reboot
setuid
SELinux setprocattr
```

Do not merely state that the profiles should be separate.

Explain what V2 validation must detect to prevent invalid mixed compositions.

---

# 12. 11 Responsibility Verification

Phase 1.5 concluded that 11 owns xxKSU-side SuSFS integration, including:

```text
SuSFS initialization
SID helpers
zygote / no-su / umount behavior
ksu_handle_setresuid integration
SuSFS command routing through xxKSU reboot/supercall
xxKSU-specific Kconfig/control integration
```

Verify that this remains valid for BOTH manual and lsm_bl profiles.

Explicitly answer:

> Does the same generated 11 serve all six profiles?

Expected answer must be evidence-based.

If any mode-specific difference is required in 11, identify it.

Do not introduce one without evidence.

---

# 13. 51 Responsibility Verification

Verify that the same semantic 51 policy can serve BOTH transport modes.

51 should retain independent SuSFS kernel functionality such as applicable:

```text
filesystem behavior
namespace behavior
proc behavior
stat/kstat spoofing
mount ID behavior
uname spoofing
maps/kallsyms behavior
target-specific SuSFS kernel adaptations
```

and remove/reroute official-50 transport that belongs to official KernelSU rather than actual xxKSU.

Explicitly answer:

> Does 51 contain any semantic decision that should actually belong to the manual/lsm_bl profile manifest?

If yes, identify it.

---

# 14. Fixture Responsibility Verification

Confirm the precise ownership of:

```text
.github/fixtures/scope-min-manual-hooks-v2.3.patch
.github/fixtures/manual-security-hooks-v2.0.patch
```

For each fixture:

- list semantic paths supplied;
- list supported targets;
- identify version adaptations;
- identify expected xxKSU ABI;
- identify required config assumptions;
- identify any overlap with LSM/BL transport.

The fixtures must not be treated as generic compatibility patches.

They are transport providers for manual profiles.

---

# 15. Target Adapter Responsibility

Define what target adapters may change without changing architecture policy.

Expected adapter responsibilities include:

```text
Linux 6.1 vs 6.12 API differences
VFS API differences
SELinux API differences
hunk anchors/context
6.12 minor-version drift
Sultan vendor-tree adaptations
Sultan-specific SuSFS extensions
```

Adapters must NOT decide:

```text
manual vs lsm_bl
KEEP vs REMOVE based only on patch application success
handler ownership without manifest evidence
```

Clarify how adapters and profile manifests interact.

---

# 16. GKI Current-Workflow Gap Reclassification

Phase 1.5 found a current GKI verification gap because the existing generation workflow applies 11+51 without selecting fixtures or LSM/BL transport.

Reclassify this under the new dual-mode requirement.

The expected conceptual correction is:

```text
Current workflow:
    generates/validates transport-neutral patch material

Required V2 validation:
    validate that material in BOTH final compositions
        ├── manual
        └── lsm_bl
```

Determine whether the current issue is best classified as:

```text
GENERATOR_SEMANTIC_BUG
WORKFLOW_VALIDATION_GAP
TARGET_MANIFEST_GAP
PATCH_CONTENT_BUG
MULTIPLE
```

Provide evidence.

Do not modify the workflow.

---

# 17. SELinux Dual-Mode Verification

Phase 1.5 classified the xxKSU SELinux implementation as replacing the official-50 SELinux architecture, with MEDIUM confidence for exact context/access parity.

Verify ownership separately for:

```text
manual
lsm_bl
```

In particular distinguish:

```text
replacement behavior implementation
```

from:

```text
transport used to reach that implementation
```

For example, manual-security may provide the Linux security call site while lsm_bl may use xxKSU runtime interception.

Do not reclassify SELinux parity as HIGH without new evidence.

Retain UNKNOWN/MEDIUM where appropriate.

---

# 18. Required Validation Contract for V2

Define the validation contract V2 must eventually implement.

At minimum include:

## 18.1 Patch integrity

Generated patch is syntactically valid.

## 18.2 Clean application

11 and 51 apply to the intended clean source revisions.

## 18.3 Semantic accounting

Every relevant official 10/50 semantic block is classified.

No silent loss.

## 18.4 Final-source ownership validation

For each build profile:

```text
exactly one active owner per transport-sensitive semantic path
```

unless coexistence is explicitly proven safe.

## 18.5 Symbol/ABI validation

Required handlers exist.

Removed official-only symbols do not remain referenced.

Examples include:

```text
ksu_handle_execveat_sucompat
ksu_handle_vfs_fstat
ksu_handle_sys_read
ksu_handle_input_handle_event
```

## 18.6 Manual-profile validation

Required fixtures are present.

Automated transport that would conflict with them is disabled or proven inactive.

## 18.7 LSM/BL-profile validation

Manual fixtures are absent.

Required xxKSU LSM/BL/runtime transport is configured and present.

## 18.8 Required SuSFS functionality validation

Pure SuSFS functionality remains after de-inline transformation.

## 18.9 SELinux replacement validation

Official blocks removed from 51 must have explicitly accounted-for xxKSU replacements.

MEDIUM-confidence runtime parity requirements must remain visible.

## 18.10 Build validation

Build every supported final profile with its final configuration.

The intended validation matrix is six builds unless evidence proves a smaller build set provides equivalent coverage.

Do not assume patch application equals integration verification.

---

# 19. Fail-Closed Requirements

Phase 1.6 must preserve the fail-closed design.

Future V2 must fail when:

```text
profile is unknown
transport mode is unknown
required fixture is missing
manual fixture appears in incompatible lsm_bl profile
required xxKSU transport is disabled
two incompatible owners are active
no owner exists
handler symbol is absent
handler ABI is incompatible
official-only handler remains referenced
mixed semantic block cannot be split
target adapter cannot resolve a required semantic block
SELinux replacement cannot be accounted for
required SuSFS behavior disappears
final source cannot prove ownership
build configuration cannot prove transport selection
```

Do not invent a fallback.

Do not silently convert UNKNOWN into KEEP or REMOVE.

---

# 20. Required Final Manifest

The report must propose a machine-readable conceptual manifest.

Do NOT implement a parser yet.

Show the intended data model.

For example:

```yaml
targets:
  gki-android14-6.1:
    patch_51_policy: gki_android14_6_1
    profiles:
      manual:
        fixtures:
          - scope-min-manual-hooks-v2.3
          - manual-security-hooks-v2.0
        transport:
          exec: scope_min
          access: scope_min
          stat: scope_min
          reboot: scope_min
          read: manual_security
          setuid: manual_security
          input: xxksu_runtime

      lsm_bl:
        fixtures: []
        transport:
          exec: xxksu_bl
          access: xxksu_bl
          stat: xxksu_bl
          reboot: xxksu_runtime
          read: xxksu_lsm
          setuid: xxksu_lsm
          input: xxksu_runtime
```

This is only an example structure.

Do not copy values from the example unless evidence confirms them.

The final report must provide evidence-supported manifest entries for all three targets and both profiles.

---

# 21. Required V2 Architecture Consequence

Explain the resulting V2 architecture.

The expected separation is:

```text
upstream 10
    ↓
11 semantic transformer
    ↓
transport-neutral xxKSU integration
```

and:

```text
upstream 50
    ↓
51 semantic transformer
    ↓
transport-neutral SuSFS kernel patch
```

then:

```text
target adapter
    +
profile manifest
    ↓
final composition
    ├── manual
    └── lsm_bl
```

Validation happens against the **final composition**, not merely against 11 or 51 in isolation.

Determine whether the evidence supports this exact separation.

---

# 22. Required Corrections to Phase 1.5

Create a small correction table:

| Phase 1.5 Statement | Status | Phase 1.6 Correction |
|---|---|---|

At minimum address:

```text
"V2 supported modes — UNRESOLVED HUMAN DECISION"
```

and:

```text
"one explicit decision per target"
```

The corrected requirement is:

> Both modes are required for every supported target.

Also clarify:

> Exactly one owner is required per semantic path per final build profile, not per target globally.

Do not rewrite the entire Phase 1.5 report.

This section is an addendum/correction only.

---

# 23. Questions the Final Report Must Answer

The final report must explicitly answer all of these:

1. Are all six profiles supported by existing evidence?
2. Can one 11 serve all six profiles?
3. Can one target-specific 51 serve both modes for that target?
4. Are manual fixtures valid transport providers for all three manual targets?
5. What exact configuration activates lsm_bl for each target?
6. What exact configuration prevents duplicate transport in manual mode?
7. Which semantic paths remain xxKSU-owned in both modes?
8. Are any paths mode-specific inside 11?
9. Are any paths mode-specific inside 51?
10. What is the current GKI workflow actually failing to validate?
11. What must V2 validate after generating 11/51?
12. Are there any remaining blockers to designing V2?
13. Are there any remaining blockers to IMPLEMENTING V2?

Distinguish clearly between:

```text
safe to DESIGN V2
```

and:

```text
safe to IMPLEMENT V2
```

These are not necessarily the same answer.

---

# 24. Evidence Priority

Continue using the evidence hierarchy established by Phase 1.5:

1. Actual target kernel source
2. Actual `backslashxx/KernelSU` source
3. Official `simonpunk/susfs4ksu` 10/50
4. Actual fixture patches
5. Known-good tested 11/51 and their build workflows
6. Current generated 11/51
7. Current Python generator
8. README/documentation

Known-good patches prove tested combinations.

They do not automatically prove architectural optimality.

Current generator behavior is not authoritative merely because it produces the known-good-shaped output.

---

# 25. Evidence Reuse

Do not unnecessarily redownload or re-investigate evidence already proven in Phase 1.5.

Reuse Phase 1.5 evidence where sufficient.

Perform new inspection only where needed to answer the dual-mode manifest questions.

If new evidence contradicts Phase 1.5, document:

```text
NEW EVIDENCE
OLD CONCLUSION
CORRECTED CONCLUSION
```

Do not silently overwrite prior findings.

---

# 26. Required Report Structure

Write exactly:

```text
./XXKSU_SUSFS_PHASE1_6_REPORT.md
```

Use these sections:

1. Executive Decision
2. Phase 1.5 Contract Corrections
3. Six Supported Build Profiles
4. Profile Configuration Matrix
5. Semantic Ownership Matrix
6. GKI Android 14 / Linux 6.1 — Manual
7. GKI Android 14 / Linux 6.1 — LSM/BL
8. GKI Android 16 / Linux 6.12 — Manual
9. GKI Android 16 / Linux 6.12 — LSM/BL
10. Sultan Android 14 / Linux 6.1 — Manual
11. Sultan Android 14 / Linux 6.1 — LSM/BL
12. Duplicate-Transport Analysis
13. 11 Responsibility
14. 51 Responsibility
15. Fixture Responsibility
16. Target Adapter Responsibility
17. SELinux Dual-Mode Ownership
18. Current GKI Workflow Gap Reclassification
19. V2 Validation Contract
20. Fail-Closed Rules
21. Proposed Dual-Mode Target Manifest
22. V2 Architecture Consequences
23. Remaining Unknowns
24. Design-vs-Implementation Readiness
25. Final Recommendation
26. Confidence Report

---

# 27. Final Recommendation Format

End the report with exactly these two decisions:

```text
SAFE TO DESIGN V2: YES / NO
SAFE TO IMPLEMENT V2: YES / NO
```

For each answer, explain the blockers if the answer is NO.

Do not implement anything regardless of the answers.

---

# 28. File Modification Constraint

This task is analysis-only.

The only permitted new/modified file is:

```text
XXKSU_SUSFS_PHASE1_6_REPORT.md
```

Do not modify:

```text
XXKSU_SUSFS_ANALYSIS_REPORT.md
XXKSU_SUSFS_PHASE1_5_REPORT.md
XXKSU_SUSFS_SEMANTIC_ANALYSIS.md
XXKSU_SUSFS_PHASE1_5_TASK.md
README.md
.github/**
patches/**
```

Do not commit.

Do not stage.

Do not regenerate patches.

Do not change workflows.

Do not implement V2.

---

# 29. STOP Condition

After `XXKSU_SUSFS_PHASE1_6_REPORT.md` is complete:

**STOP.**

Do not:

- implement V2;
- edit the existing generators;
- regenerate 11;
- regenerate 51;
- modify fixtures;
- modify workflows;
- fix the current GKI workflow;
- create target manifest source files;
- create tests;
- commit anything.

Wait for human review.