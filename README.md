# xxKSU SuSFS Patches

Deterministic patch generation, strict source tree application verification (0 rejects, 0 fuzz), and automated upstream maintenance for **xxKSU (`backslashxx/KernelSU`) + SuSFS (De-inlined Hooks)**.

This repository produces and maintains downstream-ready production patches:
- **Patch 11**: Adapts SuSFS to `backslashxx/KernelSU` (`patches/xxksu/11_enable_susfs_for_ksu.patch`).
- **Patch 51**: De-inlined SuSFS kernel hooks for supported kernel trees (`patches/sultan-android14-6.1/` and `patches/gki-android16-6.12/`).

Live upstream status: **[📡 Upstream Watch Status (Issue #5)](https://github.com/yapixel/xxksu_susfs_patch/issues/5)**

---

## 🎯 Production Patches & Targets

The authoritative public interface is defined by [`patches/manifest.json`](patches/manifest.json).

| Patch ID | Relative Path | Target Tree & Lineage | Strict Apply Verification |
| :--- | :--- | :--- | :--- |
| `xxksu-patch11` | [`patches/xxksu/11_enable_susfs_for_ksu.patch`](patches/xxksu/11_enable_susfs_for_ksu.patch) | `backslashxx/KernelSU` (`master`) | PASS (0 rejects, 0 fuzz across 10 preimages) |
| `sultan-android14-6.1-patch51` | [`patches/sultan-android14-6.1/51_deinlined_susfs_hooks_sultan-android14-6.1.patch`](patches/sultan-android14-6.1/51_deinlined_susfs_hooks_sultan-android14-6.1.patch) | Pixel 8 / 8 Pro Tensynos `16.0.0-sultan` (Linux 6.1) | PASS (0 rejects, 0 fuzz on Sultan 6.1 tree) |
| `gki-android16-6.12-r38-patch51` | [`patches/gki-android16-6.12/51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch`](patches/gki-android16-6.12/51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch) | Pixel 9 / GKI `android16-6.12-2025-09_r38` (Linux 6.12) | PASS (0 rejects, 0 fuzz on r38 common tree) |

*Note: Legacy GKI Android 14 / Linux 6.1 targets have been retired.*

---

## 🚀 Quick Start: Applying Patches Downstream

### 1. Apply Patch 11 to KernelSU

Within your `KernelSU` repository tree:

```bash
# Verify clean application first (dry-run)
curl -fsSL https://raw.githubusercontent.com/yapixel/xxksu_susfs_patch/main/patches/xxksu/11_enable_susfs_for_ksu.patch | git apply -v --check

# Apply Patch 11
curl -fsSL https://raw.githubusercontent.com/yapixel/xxksu_susfs_patch/main/patches/xxksu/11_enable_susfs_for_ksu.patch | git apply -v
```

### 2. Apply Patch 51 to Kernel Tree

**For Sultan Android 14 / 6.1 (`android_kernel_google_tensynos` @ `16.0.0-sultan`):**

```bash
# Check dry-run
curl -fsSL https://raw.githubusercontent.com/yapixel/xxksu_susfs_patch/main/patches/sultan-android14-6.1/51_deinlined_susfs_hooks_sultan-android14-6.1.patch | git apply -v --check

# Apply Patch 51
curl -fsSL https://raw.githubusercontent.com/yapixel/xxksu_susfs_patch/main/patches/sultan-android14-6.1/51_deinlined_susfs_hooks_sultan-android14-6.1.patch | git apply -v
```

**For GKI Android 16 / 6.12 (`common` @ `android16-6.12-2025-09_r38`):**

```bash
# Check dry-run
curl -fsSL https://raw.githubusercontent.com/yapixel/xxksu_susfs_patch/main/patches/gki-android16-6.12/51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch | git apply -v --check

# Apply Patch 51
curl -fsSL https://raw.githubusercontent.com/yapixel/xxksu_susfs_patch/main/patches/gki-android16-6.12/51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch | git apply -v
```

---

## 📋 Public Manifest (`patches/manifest.json`)

The machine-readable contract [`patches/manifest.json`](patches/manifest.json) specifies public outputs, apply targets, compatibility descriptions, and SHA-256 digests. Downstream tooling can query it directly:

```bash
curl -fsSL https://raw.githubusercontent.com/yapixel/xxksu_susfs_patch/main/patches/manifest.json | jq '.patches[] | {id, relative_path, sha256, apply_target}'
```

CI workflows verify that `patches/manifest.json` matches committed patch bytes exactly:
```bash
PYTHONPATH=.github/scripts python3 -m v2.manifests.patch_manifest --check
```

---

## 🛰️ Upstream Watcher & Auto-Maintenance

Automated monitoring runs daily via [`.github/workflows/upstream-watch.yml`](.github/workflows/upstream-watch.yml) to track upstream changes and maintain patch stability.

### Tracked Upstreams

1. **Authoritative Sources** (govern production baselines and drift escalation):
   - `backslashxx/KernelSU` (`master` branch)
   - `simonpunk/susfs4ksu` (`sultan-shiba-susfs-minimal` and `gki-android16-6.12` branches)
2. **Reference Sources** (monitored for comparison; never modify production patches):
   - `midori01/KernelSU` (`xx.patch`)
   - `midori01/gki_ksu_workflow` (`50_add_susfs_in_gki-android16-6.12.38.patch`)

### Classification Model

- 🟢 `NO_CHANGE`: Upstream content matches verified baseline.
- 🔵 `SAFE_REGEN_CANDIDATE`: Upstream advanced cleanly; deterministic regeneration produces a verified patch applying with 0 rejects / 0 fuzz across all preimages. Candidate patch is saved as an Actions artifact.
- 🔴 `ANCHOR_DRIFT`: Anchor line shifted or missing in upstream commit; fail-closed.
- 🔴 `SEMANTIC_DRIFT`: Upstream introduced semantic changes requiring policy adaptation; fail-closed.
- 🟠 `REFERENCE_DRIFT`: Reference-only patch content changed; non-blocking informational review.
- 🔴 `SOURCE_IDENTITY_ERROR`: Remote query failure; fail-closed.

### Escalation & Fail-Closed Safety

- **Fail-Closed Principle**: Zero fuzzy hunks or rejects (`.rej`) are ever tolerated. Production patches are never updated without explicit verification.
- **`agy-required` Escalation**: Whenever an authoritative drift occurs, a structured GitHub Issue labeled `agy-required` is created or updated with reproduction commands and diagnostics.
- **Permanent Status Dashboard**: Current status is published to the persistent Issue [📡 Upstream Watch Status (#5)](https://github.com/yapixel/xxksu_susfs_patch/issues/5), updated in place each run without noisy comments.

---

## 📁 Repository Layout

```text
xxksu_susfs_patch/
├── .github/
│   ├── fixtures/v2/v29-baselines/     # Authoritative SourceBundle fixtures
│   ├── scripts/v2/                    # V2 engine, policy, adapters, and watcher
│   │   ├── adapters/                  # Tree adapters (xxKSU, Sultan, GKI)
│   │   ├── engine/                    # Deterministic diff parser and emitter
│   │   ├── manifests/                 # Manifest generator & consistency verifier
│   │   ├── model/                     # Unified diff AST and provenance models
│   │   ├── policy/                    # Semantic architecture policies
│   │   ├── semantic/                  # Semantic inventory & evidence ledger
│   │   ├── watch/                     # Upstream watcher, dashboard, and escalation
│   │   └── tests/                     # Focused unit and regression test suites
│   ├── workflows/                     # GitHub Actions CI workflows
│   └── upstream-state.json            # Tracked upstream commit & content hashes
├── candidate_patches/                 # Staging directory for generated candidates
├── patches/                           # 🎯 Public production patches and baselines
│   ├── manifest.json                  # Public downstream contract (schema v1)
│   ├── xxksu/                         # Shared xxKSU Patch 11 + BASELINE.json
│   ├── sultan-android14-6.1/          # Sultan 6.1 Patch 51 + BASELINE.json
│   └── gki-android16-6.12/            # GKI 6.12 r38 Patch 51 + BASELINE.json
├── HANDOVER.md                        # Active developer handover document
└── README.md                          # Downstream patch catalog & documentation
```

---

## 🛠️ Local Development & Validation

Run local test suites and consistency checks without downloading external kernel trees:

```bash
# 1. Verify manifest consistency
PYTHONPATH=.github/scripts python3 -m v2.manifests.patch_manifest --check

# 2. Run unit and watcher regression tests
PYTHONPATH=.github/scripts python3 -m unittest \
  v2.tests.test_dashboard \
  v2.tests.test_watch \
  v2.tests.test_patch_manifest

# 3. Run upstream watch check (dry-run mode)
PYTHONPATH=.github/scripts python3 -m v2.watch.cli --dry-run

# 4. Regenerate production patches deterministically
PYTHONPATH=.github/scripts python3 -m v2.adapters.xxksu.generator
PYTHONPATH=.github/scripts python3 -m v2.adapters.kernel.generator
```

---

## ⚠️ Scope Boundary

This repository is strictly scoped to:
- Deterministic Patch 11/51 generation and adaptation
- Semantic AST transformations and de-inlining
- Strict source tree application verification (0 rejects, 0 fuzz)
- Upstream change monitoring and drift escalation

**Out of scope:**
- Kernel compilation, defconfig management, toolchain provisioning, or boot image packaging. Kernel builds belong downstream.
