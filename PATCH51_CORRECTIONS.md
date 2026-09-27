# Patch 51 lifecycle corrections and publication evidence

## Scope and source identities

The independent audit was treated as a defect report. Work started from fetched `origin/main` `b798977a692d05e398bf94c8ac2cd3225b7bf5a9`; accepted source identities were unchanged. Patch 11 is unchanged (`a0419c3ae48dbf93013cc56e0deb8330649b3089efb3bc711ccc7f6b772b020d`).

| Source | Exact identity |
|---|---|
| xxKSU | `bb0be9297da42ff3f63819125314ce0b13935a06` |
| Sultan SuSFS | `a8324101bca5e5a2dd7d0dc82b1650e10923eec9` |
| GKI SuSFS | `b213c54126fb243595ce7876e91d84d6e0861fec` |
| Sultan kernel | `af5c65b9547a9f33c5f566430d0434aecab5a8b5` |
| GKI kernel apply target | `android16-6.12-2025-09_r38` |
| Actual r38 archive SHA-256 | `accf8f9348280116792c9608f420f8d4554da52499119a8536883c5eefd429ff` |
| Midori workflow/converter/Patch 50 | `54b1647db92ead90acf263e0dd48836163b40da5` |
| Midori KernelSU xx | `d09d7a875dce2a97c64c7e6bf336a76e03ce883b` |

The r38 archive was re-downloaded from the authoritative release asset before pinning; its hash is not copied from the audit. The historical c8909f7 archive hash remains historical metadata, not the production apply-target authentication value.

## Findings and minimum corrections

### P0 nameidata lifetime — CONFIRMED + FIXED

The old production r38 postimage installed `fake_filename` using `set_nameidata(nd, old_dfd, fake_filename, NULL)` in all three redirect paths, then called `putname(fake_filename)` without restoring `nd->name`. Exact r38 `do_filp_open` reuses that same stack nameidata after `-ECHILD` and `-ESTALE`, so retry can dereference freed filename storage. A patch applying exactly did not detect this.

`policy/lifecycle.py:fix_namei` now uses local `filename_lookup` in tmpfile/O_PATH, retaining the original `dfd` and lookup flags (including `LOOKUP_DIRECTORY` for tmpfile). That kernel helper owns a nested nameidata and its own RCU/revalidation retries; caller still owns and releases the filename. Original path is released once; failed replacement lookup releases the filename once and returns without using an uninitialized replacement path. Successful replacement is released through the unchanged existing exit path.

Normal `path_openat` saves/restores `old_name` before releasing fake storage. `terminate_walk` precedes restoration/release; retries begin with the original live name. Root-preset redirects remain excluded, so a supplied root is not accidentally replaced with process-root lookup. Nonredirect lookup is unchanged. Ordinary dfd/root, namespace, lookup flags and symlink handling remain delegated to existing kernel lookup APIs. Pinned Simonpunk b213c54 and current Midori already use these ownership patterns; the old r38 fixture had retained the defective variant.

Executable regression extracts the actual generated functions, drives both retries in `do_filp_open`, checks live-name access, exercises tmpfile/O_PATH with redirect/root-preset combinations and lookup/open errors, and checks single release. The same harness fails on the old production postimage.

### P0 clone_mnt allocation provenance — CONFIRMED + FIXED

Old r38 `clone_mnt` selected `susfs_alloc_unshare_ksu_vfsmnt` (copies old ID without IDA allocation), then re-read the asynchronous sdcard static key before marking the no-IDA flag. A key transition could therefore send a copied ID to `ida_free`. Pinned Simonpunk and Midori retain allocation provenance in `is_mnt_ksu_unshared`; our old r38 fixture did not.

`fix_namespace` records the decision once at allocation and never re-evaluates it for accounting. Two related control paths were also proven in both target postimages: `mnt_alloc_group_id` can jump to `out_free` before flags are assigned, and a normal IDA-allocated clone can inherit its parent's no-IDA bit. The correction guards early free with the same local provenance and clears the inherited bit before applying the new allocation's bit. No mount references or linking operations change.

The compiled actual allocator/flag/error slices cover all combinations of static-key transition, caller domain, copy mode, inherited flag, and group-allocation failure. Non-IDA IDs are never freed; IDA IDs are freed once. Sultan already had the local boolean but required the inherited-bit and early-error corrections too. Midori retains those two related defects.

### P1 pagemap VMA boundaries, both targets — CONFIRMED + FIXED

Both old production postimages, pinned official inputs, and reproduced Midori test only `vma_lookup(mm, start_vaddr)` for an entire `PAGEMAP_WALK_SIZE` range. A hidden VMA later in that range can leak; skipping a chunk whose first VMA is hidden also hides later visible VMAs and shortens output.

The new `susfs_pagemap_walk` runs under the existing mmap read lock. It bounds each iteration at the next VMA start/end, delegates visible/hole ranges to the original walker, and appends a zero pagemap entry per hidden base page. Zero is the existing unmapped-hole representation: no hidden PFN/flags leak, no dropped entries, no hidden-span truncation oracle. Original buffer limits/return codes, copy length and position accounting remain in place; GKI's page-size collapse receives the same number of entries and hidden subpages contribute zero flags.

Compiled tests enumerate all 256 visible/hidden arrangements across eight VMA boundaries and every nonempty subrange, including the five requested cases, holes and end-of-buffer behavior. This is bounded API-mock execution, not a live-kernel test or proof of timing indistinguishability.

### P1 GKI smaps_rollup reacquire — CONFIRMED + FIXED

The original normal loop and case-4 path guard hidden VMAs, but the case-1/2 `smap_gather_stats(vma, &mss, 0)` after mmap-lock reacquire does not. The shared `smap_gather_stats` now returns before any shmem swap accounting or page walk for a hidden VMA. All call sites—including partial-VMA (`last_vma_end`) and reacquire paths—converge on this guard. Caller progress/last_vma_end handling and visible statistics are unchanged.

Compiled actual gather code tests normal, partial/reacquired and exhausted ranges with ordinary/shmem mappings, hidden and visible. A second harness executes the actual rollup loop and its lock-contention branches for cases 1–4, checking visible totals and lock state. The original gather fails both harnesses. Pinned official GKI and Midori retain the inherited missing guard.

### P2 r38 archive authentication — CONFIRMED + FIXED

The workflow's unauthenticated `curl | tar` is replaced with download-to-file, pinned SHA-256 verification, then extraction. A regression executes those exact commands with a corrupt download and proves extraction is never reached. Sultan checkout also now fetches its exact pinned commit and fails closed, instead of ignoring a failed checkout of a shallow moving branch.

### P2 lifecycle reference approval and identity — CONFIRMED + FIXED

The previous matching-files/symbols heuristic permitted dangerous changes. Sensitive file differences now block as `REVIEW_REQUIRED` unless both exact file-diff hashes match the explicitly reviewed pair in `reference_cross_check.py`. Tests mutate name restoration, mount free condition and pagemap progression without changing helper symbols and confirm blocking. The original defective production candidate is blocked too.

Reference URLs now contain actual commit IDs, with expected byte SHA checks before conversion. Override inputs are labeled `OVERRIDE`, not falsely pinned. Reference outages remain `REFERENCE_UNAVAILABLE`, never semantic success or production authority. This bounded policy is not a C semantic analyzer; non-sensitive-file heuristics remain diagnostic and do not replace authoritative validation.

### P2 clean-clone normalizer test — CONFIRMED + FIXED

The hardcoded external scratch path and silent skip are removed. The authenticated repository fixture supplies clean sources; the test explicitly applies Patch 51 to stat.c first, matching the actual manual-fixture order. The old scratch state had silently embedded those 67 inserted lines.

### P3 consistency — CONFIRMED + FIXED

The Sultan-only input declaration has no remaining consumer after input hook deinlining. Its extra generator chunk is removed, with a negative regression. No production patch was hand-edited. The retired `gki-android14-6.1` target stays retired; current handover documents two targets/four profiles. Current provenance separates actual r38 input from historical c8909f7 lineage. Historical implementation reports are not rewritten.

## Midori reproduction and remaining differences

Executed Midori's own pinned shell converter under WSL Debian, using only its own Patch 50:

- Patch 50 SHA: `862a60184970b821fa69a188b5fa70cb37c1b82d1d59e08b9a3b5daf67208ce1`.
- Converter SHA: `1e402acaaac7c611319aa2a112f92fdeabce4fafcb6e39204c13b8d18546e54b`.
- Reproduced Patch 51 SHA: `8fc7905d5c8d804191a4d3c29f75409ea69924fa18f0eda038f7b45f102d7fd6`.

Of 16 GKI postimages, 12 are byte-identical (including proc/base.c and statfs.c). All remaining differences:

- namei.c: declaration order only after the ownership fix.
- namespace.c: our early-error/inherited-flag fixes; our existing non-sus mount lookup takes the lock rather than Midori's early-return optimization. Both retain the same parent walk and returned references for normal mounts; no optimization was copied merely for parity.
- task_mmu.c: one blank line plus intentional pagemap and shared-gather fixes.
- super.c: placement of two extern declarations only.

Reference normalization was used only to compare postimages, not to authorize or loosen exact candidate application. No byte-parity requirement was introduced. Midori has no Sultan reference.

## Validation and delivery

Local semantic gate, double generation equality, syntax checks and exact target application passed for both candidates (zero offsets/fuzz/rejects). Repeated exact bundle application verified identical per-file postimage hashes (16 GKI files; Sultan bundle 23 retained files). Focused C regressions pass. No full kernel compilation was claimed.

Final clean-checkout test result, real Actions run/delivery commit, four-way SHA evidence and Status Issue refresh will be recorded here after publication. Until then publication acceptance is pending.
