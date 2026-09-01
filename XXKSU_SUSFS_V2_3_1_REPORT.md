# xxKSU + SuSFS V2.3.1 Corrective Report

## Result

V2.3.1 is a narrowly scoped corrective pass for the four findings from the
independent V2.3 audit. It preserves the policy-neutral V2.3 boundary and does
not begin V2.4.

## Files Changed

- `.github/scripts/v2/semantic/model.py`
- `.github/scripts/v2/semantic/registry.py`
- `.github/scripts/v2/semantic/inventory.py`
- `.github/scripts/v2/semantic/ledger.py`
- `.github/scripts/v2/semantic/__init__.py`
- `.github/scripts/v2/__init__.py`
- `.github/scripts/v2/tests/test_v23.py`
- `XXKSU_SUSFS_V2_3_1_REPORT.md`

## Audit Findings and Root Causes

1. Several registry specifications matched path/source/symbol but not source
   role. Fixture `extern` declarations could therefore resolve as caller hooks.
2. `SemanticRelationship` accepted arbitrary values and failed later during
   serialization with `AttributeError`.
3. `CoverageLedger` retained orphan evidence in memory but omitted it from
   canonical serialization and identity.
4. Evidence accepted arbitrary source identity strings without distinguishing
   verified V2.2 provenance from synthetic or unverified observations.

## Implementation Changes

- Added role constraints for caller, definition, fallback, registration, and
  transport specifications; added declaration specifications for access, stat,
  fstat-return, reboot, setuid, bprm, rename, and setprocattr fixture evidence.
  A declaration cannot resolve as a caller.
- Added `EvidenceKind` (`VERIFIED`, `SYNTHETIC`, `UNVERIFIED`) and optional
  provenance identity to `EvidenceRecord`. Verified records require a V2.2
  provenance identity and `validate_against()` checks it against
  `Provenance`/`PreparedInput` identity and prepared source hashes. Complete
  ledgers fail closed on unverified evidence; synthetic test evidence remains
  explicit and permitted.
- Added constructor validation for relationship type, endpoint types, and
  relationship evidence, producing `InvalidRelationship` deterministically.
- Added deterministic `orphan_evidence` serialization. Orphans remain visible
  and identity-bearing while completeness still fails.
- Extended inventory observations and patch inventory entry points to carry
  evidence kind/provenance binding without changing V2.1/V2.2 APIs.

## Tests

Added focused regressions for realistic fixture declarations/callers, invalid
relationship values, orphan serialization and identity, V2.2 provenance
binding, and unverified fail-closed completeness. The complete suite passes 50
tests: 16 V2.1, 16 V2.2, and 18 V2.3/V2.3.1 tests.

## Provenance Binding Design

V2.3.1 reuses V2.2 `Provenance`, `PreparedInput`, and `PreparedSource` records;
it does not duplicate fetching or hashing. A `VERIFIED` evidence record carries
the prepared provenance identity and must reference that provenance identity or
one of its prepared content/cache hashes. `SYNTHETIC` is reserved for
deterministic local tests. `UNVERIFIED` is observable and prevents complete
inventory status.

## Role-Aware Matching Rules

Resolution uses path, source family, symbol, and source role. Role-sensitive
specifications explicitly require `declaration`, `definition`, `caller`, or
`fallback` as appropriate. Same-symbol observations with different roles map to
different semantic kinds/IDs; unsupported role/context remains UNKNOWN rather
than being collapsed.

## Ledger Identity Behavior

Orphan evidence is included in sorted canonical JSON and therefore changes the
ledger and inventory digest. Reordering entries or orphan records does not
change identity. Completeness still rejects orphan evidence, UNKNOWN units, and
unverified evidence.

## Scope Self-Audit

The V2.3.1 diff contains no executable KEEP, REMOVE, DROP, REROUTE, SPLIT,
ADAPT, INSERT, DELETE, or REPLACE transformation policy. `MIXED` remains a
factual observation. No git/patch application, source mutation, patch
generation, target adapter, profile composition, ownership enforcement, ABI
enforcement, config resolution, build logic, or V2.4 code was added.

## Remaining Production Blockers

Complete production inventory remains BLOCKED pending immutable prepared
official-10, all three official-50, kernel, and xxKSU source identities. V2.3.1
does not fetch implicitly or fabricate provenance. ABI and final ownership
enforcement remain later-phase responsibilities.

V2.3.1 REGISTRY ROLE FIX COMPLETE: YES
V2.3.1 RELATIONSHIP VALIDATION COMPLETE: YES
V2.3.1 LEDGER IDENTITY FIX COMPLETE: YES
V2.3.1 PROVENANCE BINDING COMPLETE: YES
UNKNOWN FAIL-CLOSED PRESERVED: YES
V2.4 POLICY LEAKAGE: NONE
TESTS PASS: YES
PRODUCTION SEMANTIC INVENTORY: BLOCKED
SAFE FOR INDEPENDENT RE-AUDIT: YES
