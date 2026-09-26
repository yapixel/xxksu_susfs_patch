# Developer & Agent Guidelines (AGENTS.md)

## Canonical Promotion Pipeline (`v2.pipeline`)

Every production patch follows this strict unidirectional pipeline:

```
Authoritative Upstream Inputs
  │
  ▼
Shared Authoritative Semantic Gate (`v2.semantic.gate`)
  (Strict Fail-Closed: no UNKNOWN semantics, no anchor drift, verified source identity)
  │
  ▼
Deterministic Candidate Generation
  (Pass 1 & Pass 2 equality verification)
  │
  ▼
Candidate Artifact (`candidate_patches/<patch-id>/<patch-filename>`)
  │
  ▼
Exact Target Validation against Bound Target Source Tree (`exact_patch`)
  (Strict Gate: 0 offsets, 0 fuzz, 0 rejects, valid syntax, deterministic postimage)
  │
  ▼
Independent Midori Reference Cross-Check (`reference_cross_check`)
  (Reference-only cross-check; blocks only on SEMANTIC_CONFLICT; never modifies production)
  │
  ▼
Single-Writer Promotion Gate
  (Write-back authorized only after all gates pass; no-op if candidate matches production)
  │
  ▼
origin/main:patches/ (Tracked Stable Path)
  │
  ▼
Synchronize Metadata, BASELINE records, and `patches/manifest.json`
  │
  ▼
Public Delivery Verification
  (Candidate SHA == Committed origin/main SHA == RAW URL SHA == manifest.json SHA)
```

---

## 15 Hard Repository Invariants

### 1. Product / Publication Contract
- This repository automatically generates, validates, and maintains production patches.
- `origin/main:patches/` is the **ONLY** public production distribution channel.
- Downstream users consume patches via stable `raw.githubusercontent.com` URLs (e.g. via direct `curl`).
- A successful update is **NOT complete** until the verified bytes are committed and pushed to `origin/main` and the public raw URL serves the exact same SHA-256 as the validated candidate and manifest.
- Runner-local files or temporary candidate files are not publication.
- `patches/` must **NEVER** be read as generator input.

### 2. Actions Artifact Distinction
- GitHub Actions workflow artifacts are strictly diagnostic and ephemeral; they are **NEVER** public production outputs.
- Artifacts MAY be used only as ephemeral intra-workflow transport (`retention-days: 1`) between read-only validation jobs and the single promotion job.
- Downstream users must never be instructed or directed to download Actions artifacts.

### 3. Authoritative Pipeline
Promotion entry paths must follow the authoritative sequence:
`authoritative upstream` → `shared semantic gate` → `deterministic candidate generation` → `exact target validation` → `Midori reference cross-check` → `single-writer promotion` → `origin/main:patches/` → `manifest/baseline/state synchronization` → `RAW URL SHA verification`.

### 4. Shared Authoritative Semantic Gate
- Every promotion entry path (scheduled watcher, GitHub Actions CI, `workflow_dispatch`, CLI, AGY/manual invocations) uses the identical `v2.semantic.gate`.
- Strict fail-closed policy: `UNKNOWN` unapproved semantics, semantic drift, anchor drift, or invalid source identity immediately fail closed and block promotion until the semantic model/policy (`v2/semantic/registry.py`) is explicitly reconciled.

### 5. Exact Single-Pass Target Validation
- Production-bound candidates require:
  - **0 offsets**
  - **0 fuzz**
  - **0 rejects**
  - Valid deterministic postimage / syntax
  - Deterministic regeneration (byte-identical content across two independent generation passes)
- Validation must be single-pass against clean target trees: never validate by applying to a tree and then running a second `patch -p1` on the same tree.

### 6. Patch 51 Atomic Publication Topology
- Multi-kernel Patch 51 execution splits validation and promotion:
  ```
  validate_sultan (contents: read) ────────┐
                                           ├── promote_and_deliver (contents: write)
  validate_gki_r38 (contents: read) ───────┘
  ```
- `validate_sultan` and `validate_gki_r38` run in parallel with read-only permissions (`contents: read`). They must never commit or push.
- Exactly one promotion/delivery job (`promote_and_deliver`) holds `contents: write`.
- Promotion executes strictly after **BOTH** validation jobs succeed (`needs: [validate_sultan, validate_gki_r38]`).
- If either validation fails, promotion does not execute (zero partial publication).
- Changed Patch 51 outputs, BASELINEs, upstream state, and `patches/manifest.json` are committed and pushed in exactly one serialized repository write transaction.

### 7. Patch 11 / Patch 51 Writer Serialization
- Patch 11 and Patch 51 production workflows share the repository-wide `concurrency: group: "production-promotion"`.
- They can never execute concurrent write-backs to `origin/main`.

### 8. Promotion Byte & SHA Equality Requirement
For every updated public patch:
```
candidate SHA-256
  == committed origin/main patch SHA-256
  == raw.githubusercontent.com SHA-256
  == patches/manifest.json SHA-256
```
If any of these hashes differ, publication is **FAILED** even if GitHub Actions marks the run green.

### 9. Canonical Public Outputs Only
The repository produces exactly three public production patches:
1. `patches/xxksu/11_enable_susfs_for_ksu.patch` (`xxksu-patch11`)
2. `patches/sultan-android14-6.1/51_deinlined_susfs_hooks_sultan-android14-6.1.patch` (`sultan-android14-6.1-patch51`)
3. `patches/gki-android16-6.12/51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch` (`gki-android16-6.12-r38-patch51`, bound to `android16-6.12-2025-09_r38`)
*(Historical commit `c8909f7` is retained solely for internal provenance/baseline records; it is NOT a second public Patch 51).*

### 10. Midori Reference Cross-Check
Midori sources are **REFERENCE ONLY** and never authoritative inputs:
- **Patch 11:** Compare candidate against `midori01/KernelSU:xx.patch`.
- **GKI Patch 51:** Fetch Midori's own Patch 50 and Midori's own `susfs_deinlined.sh` conversion script from `midori01/gki_ksu_workflow`, independently generate Midori's Patch 51, and semantically cross-check against our candidate.
- **Rules:**
  - Never feed our Patch 50 into Midori's converter.
  - Never modify authoritative production code/patches merely to match Midori.
  - Comparison classifications: `SEMANTIC_MATCH`, `IMPLEMENTATION_DIFFERENCE`, `OUR_EXTRA`, `REFERENCE_EXTRA`, `SEMANTIC_CONFLICT`, `REFERENCE_UNAVAILABLE`.
  - Only genuine semantic conflicts (`SEMANTIC_CONFLICT`) block promotion for review. Reference differences never authorize production changes.
  - Third-party reference outages (`REFERENCE_UNAVAILABLE`) do not corrupt or block authoritative releases.

### 11. Current Known Reference Differences
- **Patch 11 vs Midori:** Reports `OUR_EXTRA` because our authoritative Simonpunk SuSFS integration retains setuid/zygote handling (`susfs.setuid.zygote_handling`), whereas Midori intentionally implements reduced integration.
- **GKI r38 Patch 51 vs Midori Patch 51:** Reports `IMPLEMENTATION_DIFFERENCE` with equivalent deinlining semantics across identical 16 kernel files (open redirect path lookup variation in `fs/namei.c`).
These are documented reference observations, not reasons to modify production.

### 12. Patch 11 Mutation Scope Restrictions
- Under current policy, Patch 11 modifies exactly the canonical 8 files in `backslashxx/KernelSU`:
  1. `kernel/Kconfig`
  2. `kernel/hook/setuid_hook.c`
  3. `kernel/ksu.c`
  4. `kernel/selinux/rules.c`
  5. `kernel/selinux/selinux.c`
  6. `kernel/selinux/selinux.h`
  7. `kernel/supercall/dispatch.c`
  8. `kernel/supercall/supercall.c`
- `kernel/feature/kernel_umount.c` and `kernel/downstream/ksu_hostsredirect.h` are **NOT** Patch 11 mutation targets.

### 13. Repository Scope & Downstream Boundaries
This repository owns:
- Upstream monitoring and change detection
- Patch candidate generation
- Shared semantic validation
- Exact source target application validation (0 offsets, 0 fuzz, 0 rejects)
- Verified automated publication to `origin/main:patches/`

This repository does **NOT** own:
- Kernel compilation or build verification
- Defconfig policy or modifications
- Compiler toolchains or environments
- Kernel packaging (AnyKernel3, boot image generation)
- Device runtime testing or booting

### 14. Watcher & AGY Escalation Policy
- Normal upstream updates detected by the watcher pass through the shared semantic gate.
- If upstream introduces unapproved semantic drift, anchor drift, or unknown semantics, the system fails closed:
  - No candidate is promoted.
  - Production patches, baselines, and manifest remain untouched.
  - The watcher creates/uses a dedicated `[AGY-REQUIRED]` GitHub issue for explicit developer/AGY semantic review and model reconciliation.

### 15. Status Dashboard Contract
- The permanent upstream-status Issue (#5) is a bounded current-state dashboard (`render_dashboard_body`).
- It is updated in-place via issue edit, not as an append-only log.
- It provides a human-readable operational overview (authoritative pins, reference parity, escalations) and does not replace machine-readable truth (`patches/manifest.json`, `BASELINE.json`, `.github/upstream-state.json`).

---

## Operational Verification Commands

```bash
# 1. Authoritative Promotion Pipeline (CLI)
PYTHONPATH=.github/scripts python3 -m v2.pipeline \
  --patch-id <xxksu-patch11 | sultan-android14-6.1-patch51 | gki-android16-6.12-r38-patch51> \
  --upstream-input <path-to-source-or-patch> \
  --target-tree <path-to-clean-target-tree> \
  --promote \
  --write-back

# 2. Check Manifest Consistency
PYTHONPATH=.github/scripts python3 -m v2.manifests.patch_manifest --check

# 3. Run Upstream Watcher
PYTHONPATH=.github/scripts python3 -m v2.watch.cli

# 4. Run Independent Midori Reference Cross-Check (CLI)
PYTHONPATH=.github/scripts python3 -m v2.validation.reference_cross_check \
  --patch-id <xxksu-patch11 | gki-android16-6.12-r38-patch51> \
  --candidate <path-to-candidate-patch>

# 5. Focused Unit & Regression Test Suites
PYTHONPATH=.github/scripts:.github/scripts/v2/tests python3 -m unittest \
  test_delivery test_semantic_gate test_pipeline test_watch test_baseline test_patch_manifest test_reference_cross_check
```
