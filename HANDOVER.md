# xxKSU + SuSFS production handover

## Current implementation

This repository generates shared xxKSU Patch 11 and transport-neutral kernel Patch 51 artifacts. The old V2.3-only checkpoint description is historical: source bundles, semantic policy, adapters, validation, the watcher, and the production pipeline now exist under `.github/scripts/v2/`. Do not restart the phase plan from this document.

Production authority is `patches/manifest.json`, active `BASELINE.json` files, `.github/upstream-state.json`, and workflow pins. Public delivery is `origin/main:patches/`, not Actions artifacts. Patch 51 is generated and validated by parallel read-only workers; only the single delivery job publishes both candidates atomically.

Read `AGENTS.md`, this file, `PATCH51_CORRECTIONS.md`, the machine records, `v2/pipeline.py`, `v2/policy/lifecycle.py`, and their tests before changing production.

## Active targets and profiles

`gki-android14-6.1` was retired by commit `6352a68`; do not restore it to satisfy historical six-profile documents. There are **two targets and four profiles**:

- `sultan-android14-6.1-manual`
- `sultan-android14-6.1-lsm_bl`
- `gki-android16-6.12-manual`
- `gki-android16-6.12-lsm_bl`

One shared 11 serves all four. Each target has one 51 for both modes. Transport selection belongs to profiles, not 11/51. Manual uses both fixtures with automated transport disabled. LSM/BL uses no manual fixtures and keeps `CONFIG_KSU_TAMPER_SYSCALL_TABLE=n`; BL's internally managed syscall fallback is a distinct mechanism.

## Accepted identities

- xxKSU: `bb0be9297da42ff3f63819125314ce0b13935a06`.
- Sultan SuSFS: `a8324101bca5e5a2dd7d0dc82b1650e10923eec9`.
- GKI SuSFS: `b213c54126fb243595ce7876e91d84d6e0861fec`.
- Sultan kernel: `af5c65b9547a9f33c5f566430d0434aecab5a8b5`.
- GKI production apply target: `android16-6.12-2025-09_r38`; archive URL and authenticated SHA-256 are in `.github/fixtures/v2/r38-sources.json` and GKI baseline compatibility metadata. The c8909f7 source bundle is historical lineage, not this archive.
- Exact current production patch hashes: `patches/manifest.json`. Avoid duplicating changing hashes in this handover.

## Correctness and evidence boundaries

Target kernel control flow and pinned SuSFS/xxKSU sources govern corrections. An independent audit is a defect report, not authority. Relevant UNKNOWN fails closed. Function names and `git apply` success are not semantic evidence. Ownership is per semantic path per final profile.

Keep handler definition, Linux call site, runtime registration, LSM, kprobe, syscall-table hook, ARM64 BL, manual hook and fixture hook distinct. Do not assume copying more official-KSU code is safer than retaining native xxKSU ownership. Patch 11 remains unchanged by the Patch 51 correction work.

`policy/lifecycle.py` applies bounded source corrections against exact kernel preimages, then emits candidate diffs. It never reads production patches as generation inputs. `tests/test_lifecycle.py` executes corrected C with bounded API mocks. This is not a full kernel build or runtime proof. Separate build workflows own kernel compilation.

Midori is reference-only. Inputs are commit-pinned and hashed. Unreviewed differences in namei, namespace or task_mmu block promotion. Exact reviewed pairs document intentional corrections; they are not wildcard equivalence. `REFERENCE_UNAVAILABLE` is not `SEMANTIC_MATCH` and cannot authorize changes.

## Validation and next maintenance gate

Run complete discovery from a clean checkout:

```sh
PYTHONPATH=.github/scripts GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=commit.gpgsign GIT_CONFIG_VALUE_0=false GIT_CONFIG_KEY_1=tag.gpgsign GIT_CONFIG_VALUE_1=false python3 -m unittest discover -s .github/scripts/v2/tests -p 'test_*.py'
```

GCC is required for lifecycle regressions; absence is a failure, not a silent skip. The r38 manual-hook normalizer test reconstructs its post-Patch-51 stat.c from repository-controlled sources, without an external scratch directory.

New upstream/baseline identities require revalidation. Required publication evidence is candidate SHA = origin/main bytes = RAW bytes = manifest SHA, plus the delivery commit and refreshed Status Issue #5. See `PATCH51_CORRECTIONS.md` for exact results and limitations. Never publish generated patches manually, weaken exact validation, or let a reference comparison select production policy.
