# GKI Android 16 / Linux 6.12 Provenance

## 1. Authoritative Production Lineage (c8909f7)

**Status:** `VERIFIED`

This lineage represents the authoritative, reproducible production baseline for `gki-android16-6.12`.

### Upstream Kernel
- **Repository:** `https://android.googlesource.com/kernel/common`
- **Ref:** `android16-6.12`
- **Commit:** `c8909f7cf1380810b285cbeee347dd01a8c9ec5c`
- **Tree:** `4ce1cd677e86aed8188e040fcd2971a95b1cd5f4`
- **Archive URL:** `https://android.googlesource.com/kernel/common/+archive/c8909f7cf1380810b285cbeee347dd01a8c9ec5c.tar.gz`
- **Archive SHA-256:** `a06d5a7505fe5437ee7fcec0b07e62fb725c689579bbc4d4ec51d68060971e97`

### SuSFS Lineage
- **Repository:** `https://gitlab.com/simonpunk/susfs4ksu`
- **Branch:** `gki-android16-6.12`
- **Commit:** `c8f64e41e3dea2cd44754d7472d3cd0bc0b40784`
- **Upstream Patch:** `kernel_patches/50_add_susfs_in_gki-android16-6.12.patch`

### Authoritative Source Bundle
- **Artifact:** `.github/fixtures/v2/v29-baselines/gki-android16-6.12.json`
- **Schema:** `xxksu-susfs-source-bundle/v1`
- **Files:** 22 retained files (20 kernel source + 2 SuSFS source)
- **Identity:** `sha256:b29c4eff277bdd0ea2422f96ac90f7fe931ca3f390c2fcc3f4ac55f90bad7cb9`

### Deinlined Target Patch 51
- **File:** `patches/gki-android16-6.12/51_deinlined_susfs_hooks_gki-android16-6.12.patch`
- **SHA-256:** `sha256:563a7650efb2e44bcb6b8da95076f79098d00c94511ed25bf70952e7af5bc2f6`
- **Strict Patch Application:** `PASS` (zero rejects, exact preimages, zero fuzz)

### Fixture Bindings
- `manual-security-hooks-v2.0.patch`: `sha256:183f5bc323ad9e8b4b3dc874b7b52761c94187656a51d3d7cb5832d908370934`
- `scope-min-manual-hooks-v2.3.patch`: `sha256:2168daaed174a4e64dc133bca7c39c49a75bb9e2fcc62df726e1b66604368c72`

### Validation Status
- `gki-android16-6.12-manual`: `ValidationStatus.PASS`
- `gki-android16-6.12-lsm_bl`: `ValidationStatus.PASS`

---

## 2. Historical r58 Lineage (Permanently Non-Authoritative)

**Status:** `PERMANENTLY NON-AUTHORITATIVE / HISTORICAL EVIDENCE ONLY`

The original historical `51_deinlined_susfs_hooks_gki-android16-6.12.patch` was committed under commit `939d95f4932f532004653d52ab0ab47e62cdb013`. Its documented workflow named:
- Kernel archive: `https://github.com/yapixel/gki-build-assets/releases/download/android16-6.12-2025-06_r58/common-android16-6.12-2025-06_r58.tar.gz`
- SuSFS commit: `698aa6a4ddca6fa5359871daf13f93583fb8282a`

Neither input had immutable content verification at commit time. The archive currently served at that URL exhibited preimage divergence against the patch (e.g. `drivers/input/input.c` preimage prefix `78be582b5766` vs actual archive blob `c51858f1cdc556939c2ee1bd21669c71c169d84e`). Reconstructing the baseline from patch context is strictly forbidden under V2 architectural rules.

Therefore, the r58 lineage remains permanently non-authoritative and retained solely as historical evidence.
