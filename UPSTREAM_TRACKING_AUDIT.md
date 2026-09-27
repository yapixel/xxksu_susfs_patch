# Upstream tracking audit — 2026-09-27

Audited origin/main: `66e0ccce83ba46b49cb92c93ec55829c5af7abd1`.
Result: illegal duplicated production pins found and removed; no accepted input or
production artifact advanced by this task.

## Live discovery

| Upstream | Tracking ref | Remote HEAD | Accepted revision | Status |
|---|---|---|---|---|
| backslashxx/KernelSU | master | ae81a610ef8c481b9a73e48a962f8eee910b619e | bb0be9297da42ff3f63819125314ce0b13935a06 | UNREVIEWED_DRIFT |
| simonpunk/susfs4ksu | sultan-shiba-susfs-minimal | a8324101bca5e5a2dd7d0dc82b1650e10923eec9 | a8324101bca5e5a2dd7d0dc82b1650e10923eec9 | NO_CHANGE |
| simonpunk/susfs4ksu | gki-android16-6.12 | b213c54126fb243595ce7876e91d84d6e0861fec | b213c54126fb243595ce7876e91d84d6e0861fec | NO_CHANGE |

Resolved with live `git ls-remote`; GitHub API also confirmed xxKSU default branch
`master`. The three state `ref` fields are TRACKING_CONFIGURATION. Each SHA returned
by `fetch_remote_commit` is RUN_RESOLVED_REVISION. No upstream drift was accepted.

## Actual path and correction

`watch/checker.py:fetch_remote_commit` resolves the configured ref once, then
`check_backslashxx_kernelsu` / `check_susfs_authoritative` fetch tracked files at that
exact discovered SHA. Changed identities stay visible even when relevant bytes are
unchanged (`IRRELEVANT_CHANGE`); relevant changes enter the semantic gate and source
checks. The watcher stages/reports candidates and escalations; it never approves
or publishes. In particular, its preliminary Patch 51 conversion is not a substitute
for the target-specific production reconstruction.

Approval is the existing review boundary: synchronize the accepted state and
BASELINE, tracked content hashes, reviewed source snapshots and authenticated raw
commit metadata as required. GKI's accepted Patch 50 hash check and both targets'
raw-commit checks intentionally reject an incoherent/unreviewed update. These are
reviewed data, not production Python SHA constants. After approval, the production
workflows fetch those accepted exact commits and run the existing generation,
semantic, exact-target and publication gates. Patch 11 also retains the explicit
exact-candidate-SHA dispatch path through its validation gates.

Previously both workflow defaults/env/fetch commands and manifest defaults repeated
historical upstream SHAs. Updating acceptance records did not update those fetches.
They now read the shared accepted records, check state/BASELINE agreement, reject
moving-ref overrides, and freeze repository checkout to the triggering SHA across
all validator/writer jobs. No independently moving branch fetch occurs mid-run.
Baseline tests now compare acceptance records instead of requiring historical SHAs;
provenance tests no longer require a historical accepted-revision Date.

Clean-room still intentionally reconstructs accepted exact commits and authenticates
tracked bytes. The fixed Sultan kernel commit and r38 archive remain target bindings,
not the mutable xxKSU/Simonpunk discovery policy. No generator or semantic policy was
changed. Publication was not dispatched for this audit.

## SHA occurrence classification at audited HEAD

The table groups repeated occurrences with the same role. Source fixtures may contain
Git tree/parent IDs as well as commits; those are authenticated reproduction data.
64-character SHA-256 content digests are not commit pins. Historical prose/header
IDs never control fetching. TEST_FIXTURE_IDENTITY means controlled test data; the
live-baseline assertions that actually blocked accepted advancement are separately
marked illegal. All reproduction/reference/history entries were retained.

| Source / used by | SHA | Classification | Can block upstream advancement? | Correct at audited HEAD? |
|---|---|---|---|---|
| `PATCH51_CORRECTIONS.md` | `0a41be581964a7dee9ca6163a64ebea663133876` | HISTORICAL_PROVENANCE | No | Correct for this role |
| `.github/scripts/v2/tests/test_watch.py` | `0b138d6a9cfe4dc163aa05c21b1e6a14ff868230` | TEST_FIXTURE_IDENTITY | No | Correct for this role |
| `.github/fixtures/r38/susfs-source-commit.txt` | `0cd1a0a44dc02abad16e6acf202a0007dc6b6b6d` | REPRODUCIBILITY_RECORD | No; review/authentication may require coherent data updates | Correct for this role |
| `.github/fixtures/r38/README.md` | `1f4434f742478c4ab28b2818e32fd0a606908d18` | HISTORICAL_PROVENANCE | No | Correct for this role |
| `patches/gki-android16-6.12/PROVENANCE.md` | `2528bdb0e2e76d26b9b174a8314ac115c9f00b3c` | HISTORICAL_PROVENANCE | No | Correct for this role |
| `.github/scripts/v2/tests/test_dashboard.py` | `2528bdb0e2e76d26b9b174a8314ac115c9f00b3c` | TEST_FIXTURE_IDENTITY | No | Correct for this role |
| `.codex/TEST_ORACLE_REPORT.md` | `2d4ee0302b6106d25f91471fbbdf83bdc5cf7f6e` | HISTORICAL_PROVENANCE | No | Correct for this role |
| `.github/scripts/v2/tests/test_watch.py` | `30e66dc3a5c65954de865afd8f44682866887544` | TEST_FIXTURE_IDENTITY | No | Correct for this role |
| `.github/scripts/v2/adapters/xxksu.py`<br>`patches/xxksu/11_enable_susfs_for_ksu.patch` | `37eee69d83424bba4b2ae3d3dd38cbbbb1ef9824` | HISTORICAL_PROVENANCE | No | Correct for this role |
| `.github/fixtures/sultan/susfs-source-commit.txt` | `3cdb78f89752b3123c3efd8d72bc4a491c1b3684` | REPRODUCIBILITY_RECORD | No; review/authentication may require coherent data updates | Correct for this role |
| `patches/gki-android16-6.12/PROVENANCE.md` | `4ce1cd677e86aed8188e040fcd2971a95b1cd5f4` | HISTORICAL_PROVENANCE | No | Correct for this role |
| `.github/fixtures/v2/v29-baselines/gki-android16-6.12.json`<br>`patches/gki-android16-6.12/BASELINE.json` | `4ce1cd677e86aed8188e040fcd2971a95b1cd5f4` | REPRODUCIBILITY_RECORD | No; review/authentication may require coherent data updates | Correct for this role |
| `PATCH51_CORRECTIONS.md` | `54b1647db92ead90acf263e0dd48836163b40da5` | HISTORICAL_PROVENANCE | No | Correct for this role |
| `.github/scripts/v2/validation/reference_cross_check.py` | `54b1647db92ead90acf263e0dd48836163b40da5` | REFERENCE_ONLY | No | Correct for this role |
| `.github/fixtures/v2/v29-baselines/xxksu.json` | `54e45c169dbce43cf46d00eb1521b655b6e4f9e9` | REPRODUCIBILITY_RECORD | No; review/authentication may require coherent data updates | Correct for this role |
| `.github/fixtures/sultan/susfs-source-commit.txt` | `5ed27d85ecf66d6ce484f3a1a3392f7e04fd96d5` | REPRODUCIBILITY_RECORD | No; review/authentication may require coherent data updates | Correct for this role |
| `.github/fixtures/v2/v29-baselines/xxksu.json` | `61197364367c9e404c7da6900658f1b16c42d0da` | REPRODUCIBILITY_RECORD | No; review/authentication may require coherent data updates | Correct for this role |
| `patches/gki-android16-6.12/PROVENANCE.md` | `698aa6a4ddca6fa5359871daf13f93583fb8282a` | HISTORICAL_PROVENANCE | No | Correct for this role |
| `PATCH51_CORRECTIONS.md` | `6c3c9f669a2c9ccb2a21a0be54256cf5f735c862` | HISTORICAL_PROVENANCE | No | Correct for this role |
| `.github/scripts/v2/tests/test_watch.py` | `719d466e7228825f0515a0545f5c708c94a80ac5` | TEST_FIXTURE_IDENTITY | No | Correct for this role |
| `patches/gki-android16-6.12/PROVENANCE.md` | `939d95f4932f532004653d52ab0ab47e62cdb013` | HISTORICAL_PROVENANCE | No | Correct for this role |
| `.github/upstream-state.json` | `a8324101bca5e5a2dd7d0dc82b1650e10923eec9` | ACCEPTED_REVISION | No | Correct for this role |
| `HANDOVER.md`<br>`PATCH51_CORRECTIONS.md` | `a8324101bca5e5a2dd7d0dc82b1650e10923eec9` | HISTORICAL_PROVENANCE | No | Correct for this role |
| `.github/scripts/v2/manifests/defaults.py`<br>`.github/scripts/v2/tests/test_baseline.py`<br>`.github/workflows/generate-51-kernel-patches.yml` | `a8324101bca5e5a2dd7d0dc82b1650e10923eec9` | ILLEGAL_PERMANENT_PIN | Yes, stale literal | Incorrect; corrected |
| `.github/fixtures/v2/v29-baselines/sultan-android14-6.1.json`<br>`patches/manifest.json`<br>`patches/sultan-android14-6.1/BASELINE.json` | `a8324101bca5e5a2dd7d0dc82b1650e10923eec9` | REPRODUCIBILITY_RECORD | No; review/authentication may require coherent data updates | Correct for this role |
| `.github/scripts/v2/tests/test_watch.py` | `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa` | TEST_FIXTURE_IDENTITY | No | Correct for this role |
| `HANDOVER.md`<br>`PATCH51_CORRECTIONS.md` | `af5c65b9547a9f33c5f566430d0434aecab5a8b5` | HISTORICAL_PROVENANCE | No | Correct for this role |
| `.github/fixtures/v2/target-api-contracts.json`<br>`.github/fixtures/v2/v29-baselines/sultan-android14-6.1.json`<br>`.github/workflows/generate-51-kernel-patches.yml`<br>`patches/manifest.json`<br>`patches/sultan-android14-6.1/BASELINE.json` | `af5c65b9547a9f33c5f566430d0434aecab5a8b5` | REPRODUCIBILITY_RECORD | No; review/authentication may require coherent data updates | Correct for this role |
| `.github/scripts/v2/tests/test_baseline.py` | `af5c65b9547a9f33c5f566430d0434aecab5a8b5` | TEST_FIXTURE_IDENTITY | No | Correct for this role |
| `.github/upstream-state.json` | `b213c54126fb243595ce7876e91d84d6e0861fec` | ACCEPTED_REVISION | No | Correct for this role |
| `.github/fixtures/r38/README.md`<br>`HANDOVER.md`<br>`PATCH51_CORRECTIONS.md`<br>`patches/gki-android16-6.12/PROVENANCE.md` | `b213c54126fb243595ce7876e91d84d6e0861fec` | HISTORICAL_PROVENANCE | No | Correct for this role |
| `.github/scripts/v2/manifests/defaults.py`<br>`.github/scripts/v2/tests/test_baseline.py`<br>`.github/workflows/generate-51-kernel-patches.yml` | `b213c54126fb243595ce7876e91d84d6e0861fec` | ILLEGAL_PERMANENT_PIN | Yes, stale literal | Incorrect; corrected |
| `.github/fixtures/v2/v29-baselines/gki-android16-6.12.json`<br>`patches/gki-android16-6.12/BASELINE.json`<br>`patches/manifest.json` | `b213c54126fb243595ce7876e91d84d6e0861fec` | REPRODUCIBILITY_RECORD | No; review/authentication may require coherent data updates | Correct for this role |
| `PATCH51_CORRECTIONS.md` | `b798977a692d05e398bf94c8ac2cd3225b7bf5a9` | HISTORICAL_PROVENANCE | No | Correct for this role |
| `.github/upstream-state.json` | `bb0be9297da42ff3f63819125314ce0b13935a06` | ACCEPTED_REVISION | No | Correct for this role |
| `HANDOVER.md`<br>`PATCH51_CORRECTIONS.md` | `bb0be9297da42ff3f63819125314ce0b13935a06` | HISTORICAL_PROVENANCE | No | Correct for this role |
| `.github/scripts/v2/manifests/defaults.py`<br>`.github/scripts/v2/tests/test_baseline.py`<br>`.github/workflows/generate-11-ksu-patch.yml`<br>`.github/workflows/generate-51-kernel-patches.yml` | `bb0be9297da42ff3f63819125314ce0b13935a06` | ILLEGAL_PERMANENT_PIN | Yes, stale literal | Incorrect; corrected |
| `patches/manifest.json`<br>`patches/xxksu/BASELINE.json` | `bb0be9297da42ff3f63819125314ce0b13935a06` | REPRODUCIBILITY_RECORD | No; review/authentication may require coherent data updates | Correct for this role |
| `.github/scripts/v2/tests/test_dashboard.py` | `bb0be9297da42ff3f63819125314ce0b13935a06` | TEST_FIXTURE_IDENTITY | No | Correct for this role |
| `PATCH51_CORRECTIONS.md` | `bb72cfe5e197e8f3342d4bbc2902d26dbb949b4c` | HISTORICAL_PROVENANCE | No | Correct for this role |
| `.github/upstream-state.json` | `bc1b8e371d80fb8dbed5ac10096e39f9cf864d56` | REFERENCE_ONLY | No | Correct for this role |
| `.github/scripts/v2/tests/test_dashboard.py`<br>`.github/scripts/v2/tests/test_watch.py` | `bc1b8e371d80fb8dbed5ac10096e39f9cf864d56` | TEST_FIXTURE_IDENTITY | No | Correct for this role |
| `.github/scripts/v2/tests/test_dashboard.py`<br>`.github/scripts/v2/tests/test_watch.py` | `c254cf2dcdffcfb466b7ac6706f705a339adeaa0` | TEST_FIXTURE_IDENTITY | No | Correct for this role |
| `patches/gki-android16-6.12/PROVENANCE.md` | `c51858f1cdc556939c2ee1bd21669c71c169d84e` | HISTORICAL_PROVENANCE | No | Correct for this role |
| `patches/gki-android16-6.12/PROVENANCE.md` | `c8909f7cf1380810b285cbeee347dd01a8c9ec5c` | HISTORICAL_PROVENANCE | No | Correct for this role |
| `.github/fixtures/v2/v29-baselines/gki-android16-6.12.json`<br>`patches/gki-android16-6.12/BASELINE.json`<br>`patches/manifest.json` | `c8909f7cf1380810b285cbeee347dd01a8c9ec5c` | REPRODUCIBILITY_RECORD | No; review/authentication may require coherent data updates | Correct for this role |
| `.github/scripts/v2/tests/test_baseline.py`<br>`.github/scripts/v2/tests/test_patch_manifest.py` | `c8909f7cf1380810b285cbeee347dd01a8c9ec5c` | TEST_FIXTURE_IDENTITY | No | Correct for this role |
| `HANDOVER.md` | `c8f64e41e3dea2cd44754d7472d3cd0bc0b40784` | HISTORICAL_PROVENANCE | No | Correct for this role |
| `patches/manifest.json`<br>`patches/xxksu/BASELINE.json` | `c8f64e41e3dea2cd44754d7472d3cd0bc0b40784` | REPRODUCIBILITY_RECORD | No; review/authentication may require coherent data updates | Correct for this role |
| `.github/scripts/v2/tests/test_baseline.py` | `c8f64e41e3dea2cd44754d7472d3cd0bc0b40784` | TEST_FIXTURE_IDENTITY | No | Correct for this role |
| `.github/scripts/v2/tests/test_baseline.py` | `cc3afab7a762a029c2d8dd7d9e8a4f1358a7df9c` | ILLEGAL_PERMANENT_PIN | Yes, stale literal | Incorrect; corrected |
| `patches/xxksu/BASELINE.json` | `cc3afab7a762a029c2d8dd7d9e8a4f1358a7df9c` | REPRODUCIBILITY_RECORD | No; review/authentication may require coherent data updates | Correct for this role |
| `PATCH51_CORRECTIONS.md` | `d09d7a875dce2a97c64c7e6bf336a76e03ce883b` | HISTORICAL_PROVENANCE | No | Correct for this role |
| `.github/fixtures/midori/xx-reference.json`<br>`.github/fixtures/midori/xx-reference.patch`<br>`.github/scripts/v2/validation/reference_cross_check.py` | `d09d7a875dce2a97c64c7e6bf336a76e03ce883b` | REFERENCE_ONLY | No | Correct for this role |
| `.github/scripts/v2/tests/test_reference_cross_check.py` | `d09d7a875dce2a97c64c7e6bf336a76e03ce883b` | TEST_FIXTURE_IDENTITY | No | Correct for this role |
| `HANDOVER.md`<br>`README.md` | `d47e2269e86848711131123f3a9afb80b106fdd0` | HISTORICAL_PROVENANCE | No | Correct for this role |
| `PATCH51_CORRECTIONS.md` | `da8c2d00995cfcafb82a583b602e1e3949026744` | HISTORICAL_PROVENANCE | No | Correct for this role |
| `.github/fixtures/r38/susfs-source-commit.txt` | `ebbc112e84d21e31ab2aca9aee8aa972ee92ec72` | REPRODUCIBILITY_RECORD | No; review/authentication may require coherent data updates | Correct for this role |
| `HANDOVER.md` | `eeadeb8b62508ba8fb9e088f6fad8a7e8542383a` | HISTORICAL_PROVENANCE | No | Correct for this role |
| `.codex/TEST_ORACLE_REPORT.md` | `f83efeb5ca7b9ec3ce34eb17aa2b91975004e453` | HISTORICAL_PROVENANCE | No | Correct for this role |
| `.github/scripts/v2/tests/test_watch.py` | `ffffffffffffffffffffffffffffffffffffffff` | TEST_FIXTURE_IDENTITY | No | Correct for this role |

## Regression evidence

One added provenance regression covers all three sources: A→B discovery with only
network-boundary mocks, identity reporting, coherent simulated acceptance of B,
real byte generation, execution of the actual workflow freezing shell, rejection
of moving-ref overrides, and rejection of inconsistent acceptance records.
It does not accept the live xxKSU drift or replace semantic review.

Validation: complete discovery 249 tests / 76.983s / zero failures, errors or skips;
final focused provenance/baseline/watcher checks 33 tests / 6.482s / zero failures,
errors or skips. YAML structure, every workflow shell block (`bash -n`), manifest
consistency and diff whitespace checks passed. Production patches, manifest,
accepted state, baseline records, generators and clean-room behavior are unchanged.
