# Test-oracle correction and consolidation

## Correction phase

Starting commit: f83efeb5ca7b9ec3ce34eb17aa2b91975004e453.
Only tests, source-contract/reference fixtures and this report change. Production generators and published patches remain unchanged.

The lifecycle harness executes generated mnt_free_id rather than providing a guarded replacement. It executes native nameidata setup, restoration and nested filename lookup; the generated open/retry and pagemap caller paths remain covered. GKI page-size emulation is exercised separately. The rollup harness uses native iterator wrappers and requires iterator invalidation before lock release. Low-level allocator, page walker and scheduling primitives remain bounded mocks: these tests do not prove full kernel concurrency correctness.

Target contracts come from the authenticated repository source bundles and pinned header excerpts, not a shared fictional API. These preserve Sultan/GKI add_to_pagemap, security_setprocattr, and vfs_tmpfile differences, plus nameidata, VMA/walker, smaps and mount helper signatures. The r38 archive used for header extraction was SHA-256 verified before reading it. Excerpt provenance and complete header hashes are recorded in target-api-contracts.json.

V27 now invokes production overlap validation and physically removes golden access. V28 required declaration absence is rejected by the combined required-symbol gate; the optional ABI validator alone does not promise presence. V29 asserts FAIL/NoOwner and verifies the actual symbol/ABI stages preceding ownership rejection. The reference comparison reads pinned upstream Midori commit bytes from the repository fixture. Dashboard no-change/failure tests compare exact bytes and state.

## Validation

| Phase | Methods | Seconds | Failures/errors/skips |
|---|---:|---:|---|
| Original baseline | 333 | 368.173 | 0 / 0 / 0 |
| Corrected oracles | 335 | 377.142 | 0 / 0 / 0 |

The dashboard byte-comparison and native iterator lock assertions also passed their complete module reruns after final tightening (21 and 9 methods).

## Historical mutation gate

Before consolidation, each mutation below caused a relevant current test assertion or C compile failure, with no unittest errors:
- Sultan two-argument append call.
- Missing nd->name restoration.
- Clone allocation-state re-evaluation.
- Missing generated mount free guard, tested independently for GKI and Sultan.
- Missing smaps hidden-VMA guard.
- Bypassed pagemap caller integration.
- Split generated C character literal, both production targets.

The disposable experiment wraps actual transform outputs (and the actual candidate for the literal mutation), substitutes one defect at a time, runs the unchanged relevant tests, and restores the original callables in a finally block. Mutation site uniqueness is asserted. No mutation framework or mutation hooks were added to production.
