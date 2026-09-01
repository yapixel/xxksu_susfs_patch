# xxKSU + SuSFS V2.3.2 Corrective Report

## Result

V2.3.2 closes the remaining role-aware matching and production provenance-binding defects without starting V2.4. The semantic inventory remains policy-neutral and UNKNOWN remains fail-closed.

## Files Changed

- `.github/scripts/v2/semantic/registry.py`
- `.github/scripts/v2/semantic/model.py`
- `.github/scripts/v2/semantic/inventory.py`
- `.github/scripts/v2/semantic/ledger.py`
- `.github/scripts/v2/tests/test_v23.py`
- `XXKSU_SUSFS_V2_3_2_REPORT.md`
- live handover/status documents after the successful re-audit

## Finding 1 Root Cause

`SemanticRegistry.match()` correctly checked `candidate.role` when a specification declared `source_roles`, but the registry allowed role-sensitive semantic kinds to omit that constraint. Several handler definitions, Linux call sites, runtime mechanisms, and wrappers could therefore match from path/source family/symbol while carrying an incompatible declaration, definition, or caller role.

## Role Invariant

`ROLE_SENSITIVE_KINDS` now defines semantic kinds that require source-role constraints. `SemanticSpecification.__post_init__()` rejects any specification in that set when `source_roles` is empty. This makes missing role declarations a registry construction error instead of a latent resolver defect.

The invariant covers handler definitions/declarations, Linux and manual call sites, runtime registration, static-key gates, LSM hooks, kprobes, syscall-table hooks, ARM64 branch-link mechanisms, fixture hooks, and transport wrappers.

## Registry Entries Corrected

Explicit roles were added to every previously unconstrained role-sensitive entry:

- `transport.exec.branch_link`
- `official_only.exec.sucompat`
- `transport.access.branch_link`
- `transport.stat.branch_link`
- `official_only.fstat.definition`
- `official_only.read.definition`
- `transport.setuid.lsm`
- `transport.input.official_assumption`
- `transport.input.registration`
- `official_only.input.definition`
- `transport.ksud.kprobe`
- `transport.bl.branch_link`
- `transport.bl.internal_fallback`
- `transport.bl.composite`

The five audit counterexamples now resolve to `UnknownSemanticUnit`; through inventory accounting they become relevant UNKNOWN and fail completeness.

## Finding 4 Root Cause

`CandidateObservation` and `inventory_patch()` defaulted evidence to `SYNTHETIC`, while production ledger completeness rejected only `UNVERIFIED`. A caller could therefore omit trust metadata and obtain complete authoritative-looking inventory from synthetic evidence.

Separately, `EvidenceRecord.validate_against()` accepted the aggregate `Provenance.identity` or any prepared source hash in the provenance set. It did not bind the evidence source family and reference name to one exact `PreparedSource`, allowing cross-source substitution.

## Revised Evidence Lifecycle

1. New observations and patch inventory default to `UNVERIFIED`.
2. Tests/local fixtures must request `SYNTHETIC` explicitly.
3. Production completeness rejects both `UNVERIFIED` and `SYNTHETIC`.
4. Explicit `allow_synthetic=True` is available only for isolated non-production completeness checks and is serialized into ledger identity.
5. `VERIFIED` evidence requires a provenance identity and exact prepared-source name.
6. Inventory admission and final ledger completeness both revalidate verified evidence against V2.2 provenance.
7. The same trust gate covers unit evidence and evidence attached to semantic relationships.

## Exact PreparedSource Binding Contract

A verified evidence record must satisfy all of the following:

- its `provenance_identity` equals the supplied V2.2 `Provenance`/`PreparedInput` identity;
- the provenance contains at least one prepared source;
- `prepared_source_name` selects exactly one `PreparedSource.reference.name`;
- the semantic source family maps to the expected reference name and accepted V2.2 input kind;
- `source_identity` equals that selected source's content or cache identity;
- the aggregate provenance identity is never accepted as source identity;
- a different prepared source from the same provenance set cannot substitute for the selected source.

The binding reuses V2.2 `Provenance`, `PreparedInput`, `PreparedSource`, `InputRef`, content hashes, and cache identities. No parallel acquisition or source-bundle system was introduced.

## Production and Synthetic Completeness

Default production completeness requires verified evidence. `UNVERIFIED` and `SYNTHETIC` evidence are both fatal. Explicit synthetic evidence remains usable for deterministic unit tests, and synthetic completeness requires the explicit `allow_synthetic=True` non-production switch.

A ledger cannot bypass inventory validation by receiving a manually constructed `VERIFIED` record: `CoverageLedger.validate_complete()` validates every verified record again using its supplied V2.2 provenance. It collects evidence from both semantic units and their relationships, so relationship evidence cannot bypass production trust checks.

## Regression Tests Added

Role regressions cover:

- the registry-wide missing-role invariant;
- declaration versus definition for official-only exec, fstat, read, and input handlers;
- declaration versus official input Linux call site;
- definition versus official Linux caller;
- fixture declaration versus fixture caller/hook.

Provenance regressions cover:

- authoritative observations defaulting to `UNVERIFIED`;
- synthetic authoritative evidence failing production completeness;
- explicit non-production synthetic completeness;
- missing prepared-source binding;
- empty provenance;
- aggregate provenance identity rejection;
- exact official-50 `PreparedSource` success;
- wrong source identity;
- kernel-to-official-50 cross-source substitution;
- prepared reference-name/source-family mismatch;
- prepared input-kind mismatch;
- final ledger revalidation of manually added verified evidence;
- unverified, synthetic, and cross-source relationship evidence rejection.

## Test Result

Commands:

```text
python3 -m compileall -q .github/scripts/v2
PYTHONPATH=.github/scripts python3 -m unittest discover -s .github/scripts/v2/tests -v
```

Result:

```text
Ran 53 tests in 0.105s
OK
```

Compileall passed.

## Adversarial Counterexample Result

All five wrong-role examples were rejected with `UnknownSemanticUnit`. Default and synthetic authoritative production evidence were rejected with `InventoryIncomplete`. Aggregate provenance identity, kernel identity as official-50, and cross-source reference substitution were rejected with `InvalidEvidence`. Correct official-50 evidence bound to its exact prepared official-50 source completed successfully.

## Scope Audit

The semantic production package contains no executable `KEEP`, `REMOVE`, `DROP`, `REROUTE`, `SPLIT`, `ADAPT`, `INSERT`, or `DELETE` policy. No patch application, source-tree mutation, 10-to-11 generation, 50-to-51 generation, adapter, ownership enforcement, ABI enforcement, config resolution, source-bundle implementation, or kernel build was added.

Relationship type/endpoint validation, relationship-evidence trust validation, orphan evidence identity, deterministic serialization, candidate separation, mixed factual state, and UNKNOWN fail-closed behavior remain intact.

## Remaining Production Blockers

Complete production semantic inventory remains BLOCKED because immutable prepared official-10, all three official-50, target-kernel, and xxKSU inputs are not all materialized. V2.3.2 enforces trust for those inputs but does not fetch, fabricate, or implement source bundles.

V2.3.2 ROLE-AWARE MATCHING COMPLETE: YES
V2.3.2 PRODUCTION PROVENANCE BINDING COMPLETE: YES
V2.3.2 UNKNOWN FAIL-CLOSED PRESERVED: YES
V2.4 POLICY LEAKAGE: NONE
TESTS PASS: YES
PRODUCTION SEMANTIC INVENTORY: BLOCKED
