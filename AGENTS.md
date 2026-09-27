# Contributor and Agent Contract

## Stable maintenance

The repository is in **STABLE MAINTENANCE MODE**. Future work normally consists of
upstream drift reconciliation, demonstrated correctness defects, target compatibility,
and necessary maintenance of existing automation. Do not proactively add milestone
subsystems, abstraction layers, semantic frameworks, gates, generic validators,
build systems, or kernel compilation orchestration. Require a concrete observed
failure and prefer the smallest correction supported by evidence.

Machine-readable authority is `patches/manifest.json`, active `BASELINE.json`
records, `.github/upstream-state.json`, and accepted workflow/input bindings.
Read these before editing. Do not turn historical prose or a passing test count
into correctness evidence. Keep README downstream-facing and HANDOVER a dated snapshot.

## Environment, commits, and cleanup

- On Windows Codex hosts use local WSL for repository work, audits, Git, and tests.
  Do not rely on VPS, AGY/Pi, or developer scratch state.
- Keep the actual working repository persistent. Put all disposable clones,
  archives, extracted kernels, candidates, comparisons, and temporary caches under
  one explicitly tracked task-owned `/tmp/<project>-<task>-<unique>/` root.
- Before completion permanently remove only that root, verify it is absent, and
  report remaining task-created clones/trees/archives. Never clean unrelated data,
  shared caches, or system files. Report cleanup failures without killing unrelated processes.
- Verify working-tree status before and after work. Read-only audits leave it unchanged.
- Follow the user's signing instruction. Otherwise interactive development commits
  use GPG key `56BBBCE870EF17D9`; unattended passphrase-blocked commits may use
  `--no-gpg-sign`, recording hashes in `.codex/HANDOFF.md`. Never change GPG configuration
  or rewrite commits solely to sign them later.
- Documentation-only closeouts may use `[skip ci]`; do not dispatch production
  publication or expensive reconstruction merely for prose changes.

## Input roles and generation

- **Generation input — Patch 11:** accepted xxKSU source + reviewed repository
  policy (`v2.adapters.xxksu.get_patch11_operation_specs`) → Patch 11.
- **Semantic lineage / watch input:** Simonpunk Patch 10 and SuSFS APIs inform
  Patch 11 review. Patch 10 is watched, but is not a runtime byte-generation input.
- **Generation input — Sultan:** accepted Simonpunk Sultan Patch 50 + accepted
  Sultan target/core context + explicit deinline/correction rules + deterministic
  accepted-revision metadata → Sultan Patch 51.
- **Generation input — GKI r38:** accepted Simonpunk GKI Patch 50 + authenticated
  clean r38 source/context + explicit deinline/target adaptations + reviewed
  lifecycle corrections + deterministic accepted-revision metadata → GKI Patch 51.
- Both Patch 51 mail Dates derive from the accepted Simonpunk commit's committer
  timestamp in UTC; authenticate the retained raw commit object. Never use a final
  patch, wall clock, filesystem mtime, or local timezone as metadata input.
- **Target source:** authenticated source bundles/excerpts supply preimages and APIs.
  They must agree with the bound real target. Authenticate the r38 archive file's
  declared SHA before extraction. The historical c8909f7 bundle is lineage, not
  the actual r38 apply target.
- **Production output:** exactly the three artifacts in `patches/manifest.json`.
  Final patches under `patches/` or elsewhere never supply generation bytes/metadata.
  Baseline metadata under `patches/` may identify inputs.
- **Test golden:** historical/final outputs may support final assertions or negative
  regressions, never construct generation inputs. Output-hidden reconstruction and
  required-input rejection must remain possible.
- **Reference input:** authenticated Midori artifacts are comparison-only.

Preserve target-native API differences; never replace Sultan/GKI contracts with a
fake common mock. Preserve reviewed nameidata retry ownership, mount-ID allocation
and free provenance, pagemap VMA/caller behavior, smaps lock-reacquire guards, and C
literal integrity. A source/API change needs focused source review.

Patch 11 modifies exactly: `kernel/Kconfig`, `kernel/hook/setuid_hook.c`,
`kernel/ksu.c`, `kernel/selinux/rules.c`, `kernel/selinux/selinux.c`,
`kernel/selinux/selinux.h`, `kernel/supercall/dispatch.c`, and
`kernel/supercall/supercall.c`. Do not modify `kernel/feature/kernel_umount.c` or
`kernel/downstream/ksu_hostsredirect.h`; native try-umount/task-mark ownership remains.

## Watch, acceptance, and publication

**Tracking ref** is the mutable remote branch used for discovery. **Discovered
revision** is its resolved immutable SHA. **Accepted revision** is the reviewed
SHA authorized for production. Workflows read accepted state, never duplicated
historical SHA defaults; one checkout/immutable identity is used throughout a run.
After review, advance coherent BASELINE/state records, tracked hashes/source bundles
and authenticated commit metadata where required; do not bypass their checks.
A changed ref is discovered even when semantic drift remains unaccepted.

Tracking refs discover upstream state; accepted revisions are immutable identities
for individual reviewed generations, not permanent historical pins. Discovered
revision != accepted revision triggers classification/review; accepted revisions
advance after supported change validation or justified semantic reconciliation.

No relevant change → no action. Supported/mechanical change → reconstruct and
validate → production Actions publication. Semantic/anchor/target-API/lifecycle
uncertainty → fail closed → escalation and independent source review → smallest
justified policy correction → revalidation → production Actions publication.
The watcher classifies changes and stages candidates; it does not itself publish.

Production uses the existing shared semantic/source gate before deterministic
reconstruction, exact target validation, reference review, and publication.
Require zero offsets/fuzz/rejects and valid deterministic postimages. Apply once
per clean target; never validate by reapplying to an already patched tree.

Production publication belongs exclusively to the existing update Actions workflows.
Patch 11 and Patch 51 share `production-promotion` writer serialization. Patch 51
has two read-only validators and one writer dependent on both; publish changed
patches and required shared baseline/state/manifest metadata atomically.

After required validation, FULL_STATE_NOOP means no publication/metadata/delivery
activity. A legitimate authoritative provenance advancement with identical patch
bytes is METADATA_ONLY_PROMOTION; changed bytes are PATCH_PROMOTION. Do not suppress
legitimate metadata advancement or skip safety validation through byte equality.

Publication requires candidate SHA = origin/main bytes = stable RAW bytes = manifest.
`origin/main:patches/` is the public interface; Actions artifacts are transport/debug
only. Never manually publish local candidates.

## References, tests, and clean-room

Midori is a reference/difference signal, not an authority or correctness oracle.
Compare Patch 11 with pinned Midori xx.patch; reproduce GKI reference from Midori's
own authenticated Patch 50 and converter. Never feed our inputs to that converter.
`SEMANTIC_CONFLICT` and unreviewed lifecycle-sensitive `REVIEW_REQUIRED` differences
block promotion. Explicitly reviewed pairs may be `IMPLEMENTATION_DIFFERENCE`.
`REFERENCE_UNAVAILABLE` is never `SEMANTIC_MATCH`; production policy tolerates reference
outages, while complete clean-room acceptance requires available reference evidence.

Tests cover generator/pipeline invariants, native APIs, historical regressions,
ownership, and publication integrity. They do not prove arbitrary kernel lifetime,
concurrency, or complete semantics; meaningful drift requires targeted source review.
Kernel compilation, toolchain/defconfig management, packaging, and device testing
remain downstream responsibilities.

GitHub Actions `clean-room.yml` is the authoritative fresh-environment reproducibility
check: fresh Ubuntu, `contents: read`, independent input authentication, outputs
unavailable to generation, two-process determinism, exact application, native
contracts/lifecycle regressions, consolidated tests, reference comparison, and
checkout immutability. It is read-only: no promotion, commits, pushes, or issue
updates. Its concurrency is separate from publication. Local WSL checks do not
substitute for a successful real Actions run.

Issue #5 is the compact current-state dashboard. Update only through the existing
watcher/renderer, preserving bounded events; machine-readable records remain truth.
Use supported extra events for verified operational evidence, never fabricate results.

Useful local checks (Python 3.11; GCC required by C regressions):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.github/scripts python3 -m v2.manifests.patch_manifest --check
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.github/scripts:.github/scripts/v2/tests python3 -m unittest discover -s .github/scripts/v2/tests
```

Run tests in a disposable checkout: existing dashboard tests may write diagnostics.
For prose changes use manifest, path/link, diff, and status checks; add no tests solely
for documentation.
