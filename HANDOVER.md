# xxKSU + SuSFS V2 Handover

## Repository Purpose

Legacy scripts generate xxKSU/SuSFS patches (11 and target 51 artifacts). The V2 package is a deterministic, evidence-driven foundation for parsing, trusted inputs, semantic inventory, and later validation; it does not replace the legacy generators yet.

## Current Status

- V2.1: COMPLETE: typed patch models, unified-diff parser/emitter, 16 tests.
- V2.2: COMPLETE: provenance, hashing, cache, fetch/prepare boundary, manifests, 16 tests.
- V2.3: COMPLETE as a policy-neutral semantic engine; 15 tests added.
- V2.3.1: corrective implementation COMPLETE, but independent re-audit FAILED on provenance binding.
- V2.4: NOT STARTED and not authorized.
- Current complete V2 suite: 50 tests PASS.

The next gate is to resolve the provenance trust defect and pass an independent read-only V2.3/V2.3.1 re-audit. Do not authorize V2.4 before that gate.

## Non-Negotiable Architecture

```text
official 10 + actual xxKSU evidence -> one shared 11
official 50 + exact target/kernel-version evidence -> one target-specific transport-neutral 51
```

Never model old11 -> new11 or old51 -> new51. All three targets support both `manual` and `lsm_bl`; the same target-specific 51 serves both modes, and the same shared 11 serves every profile. Transport selection belongs to the profile manifest. Ownership uniqueness is per semantic path per final profile. `UNKNOWN` fails closed. `git apply` success/failure is not semantic evidence. Function names alone are not semantic classification. `MIXED` is an observation, not automatic `SPLIT` policy.

Keep distinct: handler definition; Linux-side call site; runtime registration; static-key gating; LSM/security hook; kprobe/kretprobe; syscall-table hook; ARM64 branch-link; manual source hook; fixture-provided hook. `BL=y` may use xxKSU-managed internal syscall-table fallback while `CONFIG_KSU_TAMPER_SYSCALL_TABLE=n`.

## Six Required Profiles

- `gki-android14-6.1-manual`
- `gki-android14-6.1-lsm_bl`
- `gki-android16-6.12-manual`
- `gki-android16-6.12-lsm_bl`
- `sultan-android14-6.1-manual`
- `sultan-android14-6.1-lsm_bl`

All require `CONFIG_KSU=y` and `CONFIG_KSU_SUSFS=y`. Manual uses both fixtures and disables automated transport: `CONFIG_KSU_LSM_SECURITY_HOOKS=n`, `CONFIG_KSU_HACK_ARM64_BRANCH_LINK=n`, `CONFIG_KSU_TAMPER_SYSCALL_TABLE=n`, `CONFIG_KSU_KPROBES_KSUD=n`. `lsm_bl` uses no fixtures and requires ARM64, KALLSYMS, LSM and BL: `CONFIG_KSU_LSM_SECURITY_HOOKS=y`, `CONFIG_KSU_HACK_ARM64_BRANCH_LINK=y`, `CONFIG_KSU_TAMPER_SYSCALL_TABLE=n`, `CONFIG_KSU_KPROBES_KSUD=n`, with BL composite ownership and its internal syscall fallback.

## Evidence Priority

Priority is target kernel (1), actual xxKSU (2), official 10/50 (3), fixtures (4), known-good references/workflows (5), generated artifacts (6), generators (7), documentation/other observations (8). Established identities include xxKSU `0b138d6a9cfe4dc163aa05c21b1e6a14ff868230`; official-50 Sultan `7fd1da8e0cc8d1b572c97c5fe4a27d0ec6e3e2f1`, GKI 6.1 `598370fe434a7825bfe0f41d3029d102e3cfaec4`, GKI 6.12 `698aa6a4ddca6fa5359871daf13f93583fb8282a`; and known-good workflows `eecfddfa8f036a51575804195938cd97a9fa04fc` and `7a1f69c70889b309dd96cf1a46d4555d394c5783`. Do not invent unresolved identities.

## Completed Implementation

V2.1: `.github/scripts/v2/model/patch.py`, `engine/diff_parser.py`, and `engine/emitter.py` provide typed lines, state-aware boundaries, hunk validation, metadata preservation, opaque binary handling, and deterministic emission. Report: `XXKSU_SUSFS_V2_1_REPORT.md`; limitation: no semantic transformation or source mutation.

V2.2: `model/provenance.py`, `model/manifest.py`, `source/{hashing,identity,cache,fetch,prepare}.py`, and `manifests/defaults.py` provide SHA-256 identities, atomic content-addressed cache, explicit fetch/offline preparation, and strict six-profile validation. Report: `XXKSU_SUSFS_V2_2_REPORT.md`; limitation: authoritative sources are not fully prepared.

V2.3: `semantic/{model,registry,inventory,ledger}.py` provide stable IDs separate from fingerprints, traceable evidence/relationships, role-aware candidate detection/resolution, explicit mechanism taxonomy, deterministic accounting, and fatal relevant UNKNOWN. Report: `XXKSU_SUSFS_V2_3_REPORT.md`; no transformation, ABI, ownership, or complete production inventory.

V2.3.1: role-aware registry matching, relationship validation, orphan evidence serialization/identity, and explicit V2.2 evidence-kind/provenance references. Report: `XXKSU_SUSFS_V2_3_1_REPORT.md`; implementation tests pass, but trust validation remains defective as described below.

## V2.3.1 Audit History

The first independent audit found four defects: missing source-role constraints; missing `SemanticRelationship` validation; orphan evidence omitted from serialized ledger identity; and evidence identities not bound to V2.2 provenance. V2.3.1 addressed those findings. The successful post-V2.3.1 independent re-audit remains pending; the latest independent re-audit still FAILED because `CandidateObservation` defaults to `SYNTHETIC`, so an observation labeled `official_50` with an arbitrary source label can resolve without verified V2.2 provenance. No historical report is rewritten.

## Production Inventory Status

**BLOCKED.** Authoritative official-10, all three official-50, kernel, and xxKSU inputs are not all materialized as immutable prepared sources. The engine may be complete while production inventory remains blocked; missing provenance must not be guessed or fabricated.

## Agreed Source Bundle Direction - NOT IMPLEMENTED

Future design may use `target + kernel_version + authoritative minimal source bundle`, with explicit supported versions, fail-closed unknown versions, exact file identity/hash checks, and no full archive download for normal static generation. Bundles describe input identity only, never transformation policy. Keep target, kernel_version, and profile independent. No source-bundle code exists.

## 11 / 51 / Fixture Responsibilities

Official-10 plus actual xxKSU evidence feeds shared 11. Official-50 plus target/kernel-version evidence feeds target-specific neutral 51. Manual validates 51 with both fixtures and manual config; lsm_bl validates 51 with xxKSU LSM/BL and lsm_bl config. Fixtures are evidence and constraints, never templates for a manual-specific 51.

## Kernel Build Boundary

Full kernel compilation is not a responsibility of this repository. Separate GitHub Actions perform build validation. V2 focuses on deterministic generation, semantic validation, ownership/ABI/static validation, applicability, and reproducible artifacts/metadata. Historical reports remain unchanged.

## Future Autopilot Direction

The agreed direction is continuous phased development with machine gates, critical audits for V2.3/V2.4/V2.7/V2.8, routine defect repair, stops for authoritative input or unresolved architecture/semantics/ABI/ownership/external requirements, and never automatic push. No autopilot controller is implemented here.

## Next Required Action

Resolve the provenance trust defect, rerun the independent read-only V2.3/V2.3.1 audit, and only after PASS consider authorizing V2.4.

## Files Pi Must Read First

1. `HANDOVER.md`
2. `XXKSU_SUSFS_PHASE1_5_REPORT.md`
3. `XXKSU_SUSFS_PHASE1_6_REPORT.md`
4. `XXKSU_SUSFS_V2_DESIGN.md`
5. `XXKSU_SUSFS_V2_1_REPORT.md`
6. `XXKSU_SUSFS_V2_2_REPORT.md`
7. `XXKSU_SUSFS_V2_3_TASK.md`
8. `XXKSU_SUSFS_V2_3_REPORT.md`
9. `XXKSU_SUSFS_V2_3_1_REPORT.md`
10. `.github/scripts/v2/**` and all V2 tests

## Forbidden Shortcuts

Do not weaken the parser for malformed legacy patches; classify semantics using `git apply`, function names alone, or ignored UNKNOWN; create profile-specific 51 or target/profile-specific 11; use fixtures as 51 templates; guess unsupported kernel versions; fabricate authoritative source; accept fuzz/three-way/reject output as release validation; or start V2.4 before the gate passes. Do not stage or push without authorization.
