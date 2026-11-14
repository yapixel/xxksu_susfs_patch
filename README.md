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
| **Sultan** | Android 14 / Linux 6.1 | [Patch 51](patches/sultan-android14-6.1/51_deinlined_susfs_hooks_sultan-android14-6.1.patch) · [Raw](https://raw.githubusercontent.com/yapixel/xxksu_susfs_patch/main/patches/sultan-android14-6.1/51_deinlined_susfs_hooks_sultan-android14-6.1.patch) | Verified |
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

### Kernel Configuration (Kconfig)

When compiling your kernel with xxKSU and SuSFS (e.g. in automated kernel workflows such as `wuji_ksu_workflow` or `cheetah_ksu_workflow`), ensure the required and recommended Kconfig options are enabled in your kernel `defconfig` / `.config`:

#### Core Options
- `CONFIG_KSU=y` — Enables KernelSU core.
- `CONFIG_KSU_SUSFS=y` — Enables SuSFS support in KernelSU and kernel hooks.

#### Feature Options (Recommended)
- `CONFIG_KSU_SUSFS_PRIORITY_UID_FILTER=y` — **(Latest)** Enables parsing and filtering of priority UIDs (range 10000–19999 for non-root apps) across kernel syscall hooks and the SuSFS supercall handler (`CMD_SUSFS_SET_PRIORITY_UID_FILTER 0x60030`). Enabled by default (`default y`) in Kconfig; if your workflow explicitly appends config fragments or uses a custom defconfig, ensure this option is present.
- `CONFIG_KSU_SUSFS_SUS_PATH=y` — Enables hiding suspicious paths and sub-paths from system calls.
- `CONFIG_KSU_SUSFS_SUS_MOUNT=y` — Enables hiding suspicious mounts from `/proc/self/[mounts|mountinfo|mountstat]`.
- `CONFIG_KSU_SUSFS_SUS_KSTAT=y` — Enables spoofing suspicious kstat for specified files/directories.
- `CONFIG_KSU_SUSFS_SUS_MAP=y` — Enables hiding mmapped files from `/proc/<pid>/[maps|smaps|smaps_rollup|pagemap]`.
- `CONFIG_KSU_SUSFS_SPOOF_UNAME=y` — Enables spoofing uname strings.
- `CONFIG_KSU_SUSFS_ENABLE_LOG=y` — Enables SuSFS logging to kernel dmesg (disable in production if silent operation is desired).
- `CONFIG_KSU_SUSFS_HIDE_KSU_SUSFS_SYMBOLS=y` — Automatically hides ksu and susfs symbols from `/proc/kallsyms`.
- `CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG=y` — Enables spoofing `/proc/bootconfig` (GKI) or `/proc/cmdline` (non-GKI).
- `CONFIG_KSU_SUSFS_OPEN_REDIRECT=y` — Enables redirecting opened paths to alternative target paths.

> [!IMPORTANT]
> **Parity Requirement:** xxKSU (Patch 11) and the kernel hooks (Patch 51 / `fs/susfs.c`) must be built with matching SuSFS configuration. Specifically, `CONFIG_KSU_SUSFS_PRIORITY_UID_FILTER` should be enabled on both sides to ensure priority UID filtering functions properly.

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
