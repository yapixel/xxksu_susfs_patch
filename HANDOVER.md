# Stable maintenance handover

Snapshot established 2026-09-27 from origin/main
`eeadeb8b62508ba8fb9e088f6fad8a7e8542383a`, before this documentation-only closeout.
For the subsequent live HEAD use `git rev-parse origin/main`; embedding this file's
own commit ID would be self-referential. Machine records override this dated snapshot.

The repository is in **STABLE MAINTENANCE MODE**: upstream drift reconciliation,
demonstrated correctness defects, target compatibility, and necessary upkeep of
existing automation only. No further architecture/milestone development is planned.
No new abstraction layers, generic frameworks, gates, build systems, or kernel
compilation orchestration without a concrete observed requirement.

## Production snapshot

Purpose: reconstruct, validate, and publish xxKSU/SuSFS patches. Kernel builds and
packaging belong downstream. The public interface is `patches/manifest.json` and
its three stable RAW paths; Actions artifacts are internal only.

- **Shared xxKSU Patch 11**: `patches/xxksu/11_enable_susfs_for_ksu.patch`
  SHA-256: `a0419c3ae48dbf93013cc56e0deb8330649b3089efb3bc711ccc7f6b772b020d`.
- **Sultan Android 14 / 6.1 Patch 51**: `patches/sultan-android14-6.1/51_deinlined_susfs_hooks_sultan-android14-6.1.patch`
  SHA-256: `67cc15066921d8cd0e235e45486b5421c02239b91bc997d911c33d7a5de4fe63`.
- **GKI Android 16 / 6.12 r38 Patch 51**: `patches/gki-android16-6.12/51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch`
  SHA-256: `d299ac9c2585a991c2a10c9b2315da35f927dd89ad2c2d47c689fb51cab0e97f`.

Accepted identities:

- xxKSU: `bb0be9297da42ff3f63819125314ce0b13935a06` (watch ref `master`).
- Simonpunk Sultan: `a8324101bca5e5a2dd7d0dc82b1650e10923eec9` (`sultan-shiba-susfs-minimal`).
- Simonpunk GKI: `b213c54126fb243595ce7876e91d84d6e0861fec` (`gki-android16-6.12`).
- Sultan target: `af5c65b9547a9f33c5f566430d0434aecab5a8b5` (`16.0.0-sultan`).
- GKI target: `android16-6.12-2025-09_r38`; archive SHA-256
  `accf8f9348280116792c9608f420f8d4554da52499119a8536883c5eefd429ff`.
  URL/bindings are in `.github/fixtures/v2/r38-sources.json` and the GKI baseline.
  c8909f7 is internal lineage, not the r38 apply target.
- Patch 11's recorded Patch 10 lineage remains `c8f64e41e3dea2cd44754d7472d3cd0bc0b40784`;
  current SuSFS GKI watch state is separate. Neither supplies Patch 11 generation bytes.

## Contracts and operation

Patch 11 = accepted xxKSU source + reviewed repository adaptation policy.
Simonpunk Patch 10/APIs are semantic lineage/watch input only.
Sultan Patch 51 = accepted Patch 50 + target/core context + target rules + accepted
revision metadata. GKI Patch 51 = accepted Patch 50 + authenticated r38 context +
deinline/adaptation rules + reviewed lifecycle corrections + accepted revision metadata.
Neither Patch 51 reads a previous final patch. Mail Date uses accepted commit time in UTC.

The daily watcher discovers tracking-ref changes and classifies/escalates them;
it may stage candidates but does not publish. Accepted immutable revisions advance
through review/validation, not arbitrary ref movement. Supported changes use the
existing production Actions; sensitive drift fails closed for independent source review.
Both Patch 51 validators must pass before one atomic writer publishes. Patch 11/51
writers serialize. Full-state no-op performs no writes; legitimate metadata-only
advancement remains distinct. Delivery verifies candidate/origin/RAW/manifest equality.

Midori is reference-only: pinned xx.patch and independently reproduced GKI Patch 51
from Midori's own Patch 50/converter. Reviewed implementation differences are retained;
unreviewed sensitive differences block. Reference parity is not kernel correctness.

## Verification evidence and remaining work

[Clean-room run 36296083518](https://github.com/yapixel/xxksu_susfs_patch/actions/runs/36296083518)
passed at `d47e2269e86848711131123f3a9afb80b106fdd0` on a fresh GitHub-hosted runner.
It independently fetched/authenticated inputs, reconstructed all outputs without final
copies, proved two-process determinism and generated/production/manifest equality,
passed exact apply/native lifecycle/API checks, and left the checkout unchanged.
247 tests passed in 134.562s with zero failures/errors/skips: dated evidence, not a
quality metric. Both Midori comparisons were reviewed IMPLEMENTATION_DIFFERENCE.
Clean-room is read-only and never publishes or updates issues.

Latest successful production workflow evidence at closeout: Patch 11 run
36283493358; Patch 51 run 36294761634. No production bytes changed in this closeout.
There are no open agy-required escalations at the initial live check. The watcher
still reports informational Midori GKI reference drift relative to its watch snapshot;
this is separate from the accepted, passing pinned reference comparison. Do not
advance watch acceptance merely to make the dashboard green.

No known production/reconstruction blocker remains. Refresh Issue #5 through its
existing renderer during closeout; thereafter normal scheduled watch and clean-room
checks are the next activity. Meaningful future drift requires focused source review,
not proactive architecture work. See AGENTS.md for execution and mandatory cleanup rules.
