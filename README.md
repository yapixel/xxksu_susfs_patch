<div align="center">

# xxksu_susfs_patch

**Deterministic SuSFS integration patches for xxKSU.**

Reviewed Patch 11 / Patch 51 generation for xxKSU, Sultan 6.1, and Android 16 GKI 6.12.

[![Patch 11](https://github.com/yapixel/xxksu_susfs_patch/actions/workflows/generate-11-ksu-patch.yml/badge.svg?branch=main)](https://github.com/yapixel/xxksu_susfs_patch/actions/workflows/generate-11-ksu-patch.yml)
[![Patch 51](https://github.com/yapixel/xxksu_susfs_patch/actions/workflows/generate-51-kernel-patches.yml/badge.svg?branch=main)](https://github.com/yapixel/xxksu_susfs_patch/actions/workflows/generate-51-kernel-patches.yml)
[![Clean Room](https://github.com/yapixel/xxksu_susfs_patch/actions/workflows/clean-room.yml/badge.svg?branch=main)](https://github.com/yapixel/xxksu_susfs_patch/actions/workflows/clean-room.yml)
[![Upstream Watch](https://github.com/yapixel/xxksu_susfs_patch/actions/workflows/upstream-watch.yml/badge.svg?branch=main)](https://github.com/yapixel/xxksu_susfs_patch/actions/workflows/upstream-watch.yml)

</div>

---

## Production Patches

| Target | Kernel | Artifact | Status |
| :--- | :--- | :--- | :--- |
| **xxKSU** | — | [Patch 11](patches/xxksu/11_enable_susfs_for_ksu.patch) · [Raw](https://raw.githubusercontent.com/yapixel/xxksu_susfs_patch/main/patches/xxksu/11_enable_susfs_for_ksu.patch) | Verified |
| **Sultan** (Pixel 8 / 8 Pro) | Android 14 / Linux 6.1 | [Patch 51](patches/sultan-android14-6.1/51_deinlined_susfs_hooks_sultan-android14-6.1.patch) · [Raw](https://raw.githubusercontent.com/yapixel/xxksu_susfs_patch/main/patches/sultan-android14-6.1/51_deinlined_susfs_hooks_sultan-android14-6.1.patch) | Verified |
| **GKI** (Pixel 9) | Android 16 / Linux 6.12 r38 | [Patch 51](patches/gki-android16-6.12/51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch) · [Raw](https://raw.githubusercontent.com/yapixel/xxksu_susfs_patch/main/patches/gki-android16-6.12/51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch) | Verified |

Complete artifact checksums, source identities, and compatibility targets are maintained in [patches/manifest.json](patches/manifest.json).

## Why this project exists

Upstream SuSFS patches are designed around upstream KernelSU integration. However, xxKSU already owns several runtime responsibilities natively, including umount, try-umount, task-mark, and hosts redirection.

This project produces reviewed, de-inlined integration patches that retain SuSFS behavior while avoiding obsolete or duplicated KernelSU transport hooks.

## How it works

```text
Simonpunk SuSFS Patch 50
        +
Authenticated target source
        ↓
Reviewed source reconstruction
        ↓
Native Git diff
        ↓
Patch 51
        ↓
Kbuild + symbol closure
        ↓
Clean-room verification
```

Patch 11 follows a dedicated path: accepted xxKSU source + reviewed Patch 11 policy → Patch 11.

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

## Real-device validation

Observed validation on hardware:

| Target | Observed validation |
| :--- | :--- |
| **Sultan 6.1** | ✓ Full kernel build<br>✓ Boot<br>✓ xxKSU root<br>✓ Basic SuSFS functionality |
| **GKI 6.12 r38** | ✓ Full kernel build<br>✓ Boot<br>✓ xxKSU root<br>✓ Basic SuSFS functionality |

*Note: Observed validation reflects verified maintainer builds and hardware boots, not exhaustive runtime certification.*

## Design principles

- **Authoritative postimages**: Source postimages are authoritative; Python does not handcraft final kernel hunks.
- **Native diff generation**: Native Git in authenticated target kernel trees generates production Patch 51 diffs.
- **Fail-closed decomposition**: Mixed SuSFS/KSU ownership is explicitly decomposed or fails closed.
- **Isolated publication**: GitHub Actions is the sole production publisher.

## Usage

Select the appropriate patch for your component:

- **Patch 11** → Apply to accepted / compatible [backslashxx/KernelSU](https://github.com/backslashxx/KernelSU) source.
- **Sultan Patch 51** → Apply to Sultan Android 14 / Linux 6.1 kernel source (Pixel 8 / 8 Pro Tensynos `16.0.0-sultan`).
- **GKI Patch 51** → Apply to Android 16 / Linux 6.12 r38 common kernel source (Pixel 9 / GKI 6.12).

Check [patches/manifest.json](patches/manifest.json) or each target's `BASELINE.json` for companion SuSFS core files and patch checksums.

## Upstreams

- [backslashxx/KernelSU](https://github.com/backslashxx/KernelSU) — Upstream xxKSU implementation.
- [simonpunk/susfs4ksu](https://gitlab.com/simonpunk/susfs4ksu) — Upstream SuSFS source and patches.

Tracking refs discover upstream changes; each generation resolves to immutable reviewed revisions.

Live status and drift tracking: [Status & upstream tracking → Issue #5](https://github.com/yapixel/xxksu_susfs_patch/issues/5).

## Maintenance & Documentation

- [HANDOVER.md](HANDOVER.md) — Current maintenance baseline and operational history.
- [AGENTS.md](AGENTS.md) — Contributor contracts and automation invariants.
- [patches/manifest.json](patches/manifest.json) — Production artifact index, digests, and metadata.
- [Status Issue #5](https://github.com/yapixel/xxksu_susfs_patch/issues/5) — Live upstream watch status and sync dashboard.

*Reference checks: Independent Midori artifacts are tracked purely as comparison references and are never used as production generation inputs.*
