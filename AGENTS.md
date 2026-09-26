# Developer & Agent Guidelines (AGENTS.md)

## Canonical Promotion Pipeline (`v2.pipeline`)

Every patch (Patch 11 and Patch 51) must follow this strict unidirectional pipeline:

```
Authoritative Upstream Inputs
  │
  ▼
Shared Authoritative Semantic Gate (`v2.semantic.gate`)
  (Strict Policy: no UNKNOWN semantics, no anchor drift, verified source identity)
  │
  ▼
Deterministic Candidate Generation
  │
  ▼
Candidate Artifact (`candidate_patches/<patch-id>/<patch-filename>`)
  │
  ▼
Exact Validation against Bound Target Source Tree (`exact_patch`)
  (Strict Gate: 0 offsets, 0 fuzz, 0 rejects, valid syntax, deterministic postimage)
  │
  ▼
Deterministic Regeneration Equality Verification
  (Two independent generation passes must yield byte-identical content)
  │
  ▼
Promotion to Stable `patches/` Path
  │
  ▼
Synchronize Metadata, BASELINE records, and `patches/manifest.json`
  │
  ▼
Verify Committed Public Artifact == Validated Candidate (Byte-for-byte)
  │
  ▼
Final Delivery / Write-Back (`origin/main`)
  (Stage only verified diff -> commit -> push -> verify origin/main and raw URL)
```

---

## 12 Hard Repository Invariants

1. **`patches/` is FINAL VERIFIED OUTPUT only:**
   - Published, immutable production artifacts for downstream consumers (e.g. via direct `curl`).
   - `patches/` must **NEVER** be read as the source input to generate or validate a candidate production patch.

2. **Universal Shared Semantic Gate:**
   - Every promotion entry path must pass the exact same semantic approval gate (`v2.semantic.gate`):
     scheduled watcher, GitHub Actions CI, `workflow_dispatch`, direct CLI, and AGY/manual invocations.

3. **Strict Fail-Closed Policy on Semantic Gate:**
   - The semantic gate must immediately fail closed and block promotion upon:
     - `UNKNOWN` / unapproved semantics
     - semantic drift
     - anchor drift
     - invalid source identity
   - Promotion is blocked until the semantic model/policy (`v2/semantic/registry.py`) is explicitly reconciled.

4. **Deterministic Generation:**
   - Candidate generation must produce byte-identical output across independent passes for identical inputs.

5. **Exact Single-Pass Target Validation:**
   - Validation against the bound target source tree requires:
     - **0 offsets**
     - **0 fuzz**
     - **0 rejects**
     - valid deterministic postimage
   - Never validate a patch by applying to the tree and then executing a second `patch -p1` on the same tree.

6. **Immutability on Failed Gates:**
   - If any gate (semantic, generation, or validation) fails, the system must fail closed:
     `patches/`, `BASELINE.json`, `upstream-state.json`, and `patches/manifest.json` must **NEVER** be modified.

7. **Validated Byte-for-Byte Promotion:**
   - Promotion occurs only after all gates pass. The promoted file in `patches/` must be byte-for-byte identical to the validated candidate artifact.

8. **`patches/manifest.json` is the Public Interface:**
   - Schema: `xxksu-susfs-patch-manifest/v1`.
   - Downstream consumers rely on `patches/manifest.json` as the authoritative source of patch metadata, SHA-256 hashes, and apply targets.

9. **Canonical Public Outputs Only:**
   - The repository produces exactly three public patch outputs:
     1. `patches/xxksu/11_enable_susfs_for_ksu.patch` (`xxksu-patch11`)
     2. `patches/sultan-android14-6.1/51_deinlined_susfs_hooks_sultan-android14-6.1.patch` (`sultan-android14-6.1-patch51`)
     3. `patches/gki-android16-6.12/51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch` (`gki-android16-6.12-r38-patch51`, bound to `android16-6.12-2025-09_r38`)
   - Historical commit `c8909f7` is retained solely for internal provenance/baseline records; it is NOT a second public Patch 51.

10. **Downstream Boundaries (No Kernel Compilation):**
    - Kernel compilation, defconfig modifications, compiler toolchains, packaging, and device runtime validation are strictly downstream responsibilities outside this repository's scope.

11. **Midori Sources Are Reference Only:**
    - Downstream trackers in `upstream-state.json` (e.g. `midori_kernelsu_xx_patch`, `midori_gki_patch_50`) are reference-only trackers and can never independently authorize production patch changes.

12. **Patch 11 Mutation Scope Restrictions:**
    - Under current policy, `kernel/feature/kernel_umount.c` and `kernel/downstream/ksu_hostsredirect.h` are NOT Patch 11 mutation targets.
    - Exactly 8 canonical files in `backslashxx/KernelSU` are modified by Patch 11.

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

# 4. Focused Unit & Regression Test Suites
PYTHONPATH=.github/scripts:.github/scripts/v2/tests python3 -m unittest \
  test_delivery test_semantic_gate test_pipeline test_watch test_baseline test_patch_manifest
```
