<div align="center">

# xxksu_susfs_patch

**Deterministic SuSFS generation, adaptation, and validation for xxKSU.**

A source-driven system that publishes reviewed Patch 11 / Patch 51 artifacts for xxKSU, Sultan 6.1, and Android 16 GKI 6.12.

[![Patch 11](https://github.com/yapixel/xxksu_susfs_patch/actions/workflows/generate-11-ksu-patch.yml/badge.svg?branch=main)](https://github.com/yapixel/xxksu_susfs_patch/actions/workflows/generate-11-ksu-patch.yml)
[![Patch 51](https://github.com/yapixel/xxksu_susfs_patch/actions/workflows/generate-51-kernel-patches.yml/badge.svg?branch=main)](https://github.com/yapixel/xxksu_susfs_patch/actions/workflows/generate-51-kernel-patches.yml)
[![Clean Room](https://github.com/yapixel/xxksu_susfs_patch/actions/workflows/clean-room.yml/badge.svg?branch=main)](https://github.com/yapixel/xxksu_susfs_patch/actions/workflows/clean-room.yml)
[![Upstream Watch](https://github.com/yapixel/xxksu_susfs_patch/actions/workflows/upstream-watch.yml/badge.svg?branch=main)](https://github.com/yapixel/xxksu_susfs_patch/actions/workflows/upstream-watch.yml)

</div>

---

## Current Status

- **Generation:** deterministic shared Patch 11; target-specific Sultan 6.1 and GKI 6.12 r38 Patch 51 reconstruction.
- **Verification:** fresh-runner clean-room, ownership/symbol/ABI/config checks, and real Kbuild object compilation with SuSFS symbol closure.
- **Profiles:** four current composition profiles: two kernel targets × MANUAL / LSM + Branch-Link. Six-profile build orchestration is not implemented in the current manifests.
- **CI acceptance:** full-kernel build/runtime acceptance across the complete profile matrix remains pending; the existing production gates are bounded object/closure checks.

## Production Patches

| Target | Kernel | Artifact | Status |
| :--- | :--- | :--- | :--- |
| **xxKSU** | — | [Patch 11](patches/xxksu/11_enable_susfs_for_ksu.patch) · [Raw](https://raw.githubusercontent.com/yapixel/xxksu_susfs_patch/main/patches/xxksu/11_enable_susfs_for_ksu.patch) | Verified |
| **Sultan** (see target note below) | Android 14 / Linux 6.1 | [Patch 51](patches/sultan-android14-6.1/51_deinlined_susfs_hooks_sultan-android14-6.1.patch) · [Raw](https://raw.githubusercontent.com/yapixel/xxksu_susfs_patch/main/patches/sultan-android14-6.1/51_deinlined_susfs_hooks_sultan-android14-6.1.patch) | Verified |
| **GKI** | Android 16 / Linux 6.12 r38 | [Patch 51](patches/gki-android16-6.12/51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch) · [Raw](https://raw.githubusercontent.com/yapixel/xxksu_susfs_patch/main/patches/gki-android16-6.12/51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch) | Verified |

Complete artifact checksums, source identities, and compatibility targets are maintained in [patches/manifest.json](patches/manifest.json).

**Sultan target note:** the maintainer confirms that `sultan-shiba-susfs-minimal`
supports Pixel 7 Pro (gs201/Cheetah), alongside the existing Pixel 8 / 8 Pro
(Shiba/Husky) target description. The accepted Tensynos `16.0.0-sultan` source
identity is unchanged. Device-specific runtime evidence is listed below; this is
not a blanket compatibility claim for all gs201 devices.

## Why this project exists

Upstream SuSFS patches are designed around upstream KernelSU integration. However, xxKSU already owns several runtime responsibilities natively, including umount, try-umount, task-mark, and hosts redirection.

This project produces reviewed, de-inlined integration patches that retain SuSFS behavior while avoiding obsolete or duplicated KernelSU transport hooks.

## How it works

```text
Official Patch 10 / SuSFS APIs → semantic policy (lineage/reference)
Accepted xxKSU source + reviewed policy → shared Patch 11
Accepted Patch 50 + authenticated target/core → source adaptation → native Git → Patch 51
Patch 11 + Patch 51 + profile fixtures → profile composition → static validation
  → configured Kbuild object/symbol-closure gates → Actions publication
  → downstream full build and runtime validation
```

Official Patch 10 is not a runtime byte-generation input. Profile composition and
static validation do not imply full-matrix kernel build or runtime acceptance.

## Verification

| Gate | Status |
| :--- | :---: |
| Source authentication | ✓ |
| Deterministic reconstruction | ✓ |
| Native Git generation | ✓ |
| Independent clean-tree apply | ✓ |
| Real Kbuild objects | ✓ |
| SuSFS symbol closure | ✓ |
| Clean-room reproduction | ✓ |

Python tests provide supporting regression coverage; build confidence comes from real target source and Kbuild validation. (Full `vmlinux` link is not run on every generation).

## Runtime Validation

Maintainer-reported observations, not exhaustive runtime certification:

| Reported environment | Runtime results |
| :--- | :--- |
| **Android 16 / Linux 6.12** | LSM + Branch-Link; SuSFS v2.3.0. Runtime healthy with warnings; no observed Oops/BUG/panic or duplicate transport symptoms. |
| **Pixel 7 Pro / Sultan Android 14 / Linux 6.1** | MANUAL HOOKS; KernelSU 3.3.0-52; SuSFS v2.3.0. Manual `sys_newfstatat`, `sys_faccessat`, and `do_execveat_common` paths verified; Sultan `ADD_TRY_UMOUNT`, WebView zygote, and open redirect paths verified. Runtime healthy with warnings. |

Full kernel build, boot, xxKSU root, and basic SuSFS operation were also reported
for both target families. Warnings remain part of these observations, not a clean
runtime certification. Reported `ADD_TRY_UMOUNT` behavior does not change the repository's
native xxKSU ownership policy or restore retired legacy glue.

## Design principles

- **Authoritative postimages**: Source postimages are authoritative; Python does not handcraft final kernel hunks.
- **Native diff generation**: Native Git in authenticated target kernel trees generates production Patch 51 diffs.
- **Fail-closed decomposition**: Mixed SuSFS/KSU ownership is explicitly decomposed or fails closed.
- **Isolated publication**: GitHub Actions is the sole production publisher.

## Usage

Select the appropriate patch for your component:

- **Patch 11** → Apply to accepted / compatible [backslashxx/KernelSU](https://github.com/backslashxx/KernelSU) source.
- **Sultan Patch 51** → Apply to Sultan Android 14 / Linux 6.1 kernel source (accepted Tensynos `16.0.0-sultan` lineage; see the Sultan target note).
- **GKI Patch 51** → Apply to Android 16 / Linux 6.12 r38 common kernel source (GKI 6.12).

Check [patches/manifest.json](patches/manifest.json) or each target's `BASELINE.json` for companion SuSFS core files and patch checksums.

## Upstream Watch

**[Issue #5 — authoritative live upstream-status dashboard](https://github.com/yapixel/xxksu_susfs_patch/issues/5)**

README documents stable architecture and support. Issue #5 tracks KernelSU and
Simonpunk SuSFS drift, production Patch 11 / Patch 51 hashes,
validation events, and open escalations.

- [backslashxx/KernelSU](https://github.com/backslashxx/KernelSU) — upstream xxKSU.
- [simonpunk/susfs4ksu](https://gitlab.com/simonpunk/susfs4ksu) — upstream SuSFS.

Tracking refs discover changes; each generation uses immutable accepted revisions.
Sensitive drift fails closed for source review before acceptance and publication.

## Maintenance & Documentation

- [HANDOVER.md](HANDOVER.md) — Dated handoff snapshot; current machine-readable state takes precedence.
- [AGENTS.md](AGENTS.md) — Contributor contracts and automation invariants.
- [patches/manifest.json](patches/manifest.json) — Production artifact index, digests, and metadata.
- [Status Issue #5](https://github.com/yapixel/xxksu_susfs_patch/issues/5) — Live upstream watch status and sync dashboard.

<details>
<summary>V2 evolution</summary>

V2 established explicit source/provenance records, target adaptation, profile
composition, and semantic validation. Production Patch 51 now uses complete source
postimages, native Git diffs, independent round trips, real Kbuild objects, and
symbol closure. Clean-room verifies reproduction independently. Further changes
follow stable maintenance policy; historical milestones are not current support claims.

</details>
