# xxKSU SuSFS Patches

Deterministic SuSFS integration patches for backslashxx/KernelSU and two supported
kernel targets. This repository reconstructs, validates, and publishes patches;
kernel compilation, defconfig, packaging, boot testing, and device validation belong downstream.

[Live status](https://github.com/yapixel/xxksu_susfs_patch/issues/5) ·
[Clean-room verification](https://github.com/yapixel/xxksu_susfs_patch/actions/workflows/clean-room.yml)

## Production interface

The stable public interface is [patches/manifest.json](patches/manifest.json),
with paths, accepted identities, target descriptions, and SHA-256 digests.
Production means committed files under `patches/` on `origin/main`.
Actions artifacts are internal transport/debug material, never downstream releases.

| Artifact | Supported target | Stable RAW download |
| --- | --- | --- |
| Shared xxKSU Patch 11 | backslashxx/KernelSU (xxKSU) | [Patch](https://raw.githubusercontent.com/yapixel/xxksu_susfs_patch/main/patches/xxksu/11_enable_susfs_for_ksu.patch) |
| Sultan Android 14 / 6.1 Patch 51 | Pixel 8 / 8 Pro (Shiba/Husky) Tensynos 16.0.0-sultan (Android 14 6.1) | [Patch](https://raw.githubusercontent.com/yapixel/xxksu_susfs_patch/main/patches/sultan-android14-6.1/51_deinlined_susfs_hooks_sultan-android14-6.1.patch) |
| GKI Android 16 / 6.12 r38 Patch 51 | android16-6.12-2025-09_r38 (Pixel 9 / GKI 6.12) | [Patch](https://raw.githubusercontent.com/yapixel/xxksu_susfs_patch/main/patches/gki-android16-6.12/51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch) |

Download the manifest and selected patch, verify its SHA-256, and apply against the
bound source revision. Moving RAW URLs can change during publication; retry if
manifest and patch disagree, or fetch both at one repository commit for repeatability.
Install the accepted SuSFS core files with the kernel integration; Patch 51 is not
a complete kernel source distribution. Consult each target's `BASELINE.json`.

```sh
curl -fsSL https://raw.githubusercontent.com/yapixel/xxksu_susfs_patch/main/patches/manifest.json -o manifest.json
# After downloading and verifying the selected patch in the target tree:
git apply --check selected.patch
git apply selected.patch
```

## Generation and maintenance

- **Patch 11:** accepted xxKSU source + reviewed repository adaptation policy.
  Simonpunk Patch 10 / SuSFS APIs are semantic lineage and watch inputs, not runtime
  byte-generation inputs. Patch 11 owns eight files and preserves native xxKSU
  try-umount and task-mark behavior.
- **Sultan Patch 51:** accepted Simonpunk Sultan Patch 50 + accepted target/core
  context + explicit transformation rules + deterministic accepted-revision metadata.
- **GKI r38 Patch 51:** accepted Simonpunk GKI Patch 50 + authenticated clean r38
  context + deinline/target rules + reviewed lifecycle corrections + deterministic
  accepted-revision metadata. Neither Patch 51 consumes a previous final patch.

The daily [watcher](.github/workflows/upstream-watch.yml) discovers changes on
xxKSU `master`, SuSFS `sultan-shiba-susfs-minimal`, and SuSFS `gki-android16-6.12`.
Tracking refs discover new revisions; accepted revisions identify reproducible,
reviewed generations and advance only after acceptance. No change needs no action.
The watcher classifies drift and can prepare candidates; it does not publish.
Supported changes proceed through validation and the production Actions workflows.
Semantic, anchor, target-API, or lifecycle drift fails closed for independent
source review before policy reconciliation and publication.

```text
Tracking ref → watcher → review/acceptance boundary → authoritative inputs
→ semantic/source gate → deterministic target-specific reconstruction
→ exact target validation → reference review → production Actions → patches/ + manifest
```

[Patch 11 publication](.github/workflows/generate-11-ksu-patch.yml) and
[Patch 51 publication](.github/workflows/generate-51-kernel-patches.yml) serialize
writes; both Patch 51 targets must validate before one atomic publication.
Midori is an independent reference/difference signal, never generation authority,
production source, or a kernel-correctness oracle.

## Verification and scope

[Clean-Room Reproducibility Verification](.github/workflows/clean-room.yml) runs
manually and weekly on a fresh GitHub-hosted Ubuntu runner with `contents: read`.
It fetches/authenticates declared inputs, reconstructs with final outputs absent,
checks two-process determinism and generated = production = manifest, applies
exactly, runs target-native contracts/historical regressions and the consolidated
suite, compares authenticated Midori references, and checks repository immutability.
It never promotes, commits, pushes, or updates issues, and uses no developer scratch state.

Successful evidence: [run 36296083518](https://github.com/yapixel/xxksu_susfs_patch/actions/runs/36296083518)
at `d47e2269e86848711131123f3a9afb80b106fdd0` (2026-09-27).

Tests cover generator/pipeline invariants, target-native APIs, historical defects,
structural ownership, and publication integrity. These checks prove their covered
contracts and reproducibility, not arbitrary future kernel lifetime, concurrency,
or all semantic behavior. Meaningful semantic drift still requires source review.

The architecture is in **STABLE MAINTENANCE MODE**. See [AGENTS.md](AGENTS.md)
for contributor rules and [HANDOVER.md](HANDOVER.md) for the closeout snapshot.
