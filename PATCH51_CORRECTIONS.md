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

`fix_namespace` records the decision once at allocation and never re-evaluates it for accounting. A related accounting defect exists in both target postimages: a normal IDA-allocated clone can inherit its parent's no-IDA bit. The correction clears that inherited bit before applying the new allocation's bit. Early `out_free` is also guarded with the same provenance because it precedes flag initialization. This last guard is defensive allocator-contract coverage: current `copy_mnt_ns` does not request `CL_MAKE_SHARED`, so the artificial combined-flags failure test is not claimed as a separately reproduced production failure. No mount references or linking operations change.

The compiled actual allocator/flag/error slices cover combinations of static-key transition, caller domain, copy mode, inherited flag, and group-allocation failure. Non-IDA IDs are never freed; IDA IDs are freed once. Sultan already had the local boolean but required inherited-bit clearing too; both targets use the same defensive early-error guard. Midori retains the inherited-bit accounting defect.

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

## Follow-up: production mail diffstat — CONFIRMED + FIXED

The first lifecycle publication's summary-only header refresh omitted the per-file list in both GKI and Sultan Patch 51. The generator now feeds the **final emitted diff body**, after every lifecycle transformation, to native `git apply --stat` in canonical `LC_ALL=C`, with color disabled and stable pathname quoting. It embeds all resulting per-file counts/bars and the aggregate summary. No filename/count list is hardcoded; renderer failure aborts generation. This command reports statistics only and does not apply the patch.

`tests/test_mail_diffstat.py` independently compares final AST counts with Git `--numstat`, verifies the diffstat path set equals the actual file set, checks every per-file count and aggregate insertion/deletion count, checks the native bar rendering, and verifies identical repeated generation (including locale variation). A synthetic added file plus a changed existing hunk verifies automatic updates. Patch 11 was audited: all eight per-file counts and its 367-insertion/1-deletion summary match its diff, so it remains unchanged.

The formatting follow-up changes only Patch 51 mail preambles; hunk bodies and corrected C postimages remain unchanged. It is republished through the same parallel validation/single-writer Actions path, not by editing production files.

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

Initial correctness publication: [36283493548](https://github.com/yapixel/xxksu_susfs_patch/actions/runs/36283493548), SUCCESS, delivery `da8c2d00995cfcafb82a583b602e1e3949026744`. Final publication including complete diffstats: [36284535551](https://github.com/yapixel/xxksu_susfs_patch/actions/runs/36284535551), SUCCESS. Both independent read-only validation jobs passed before the one promotion/delivery job ran. GKI logs verify the authenticated archive before extraction. The final single-writer delivery commit is `bb72cfe5e197e8f3342d4bbc2902d26dbb949b4c` (`auto(pipeline): deliver verified 51 patch production outputs [skip ci]`), changing only both Patch 51 outputs, their two baseline records and the manifest. Patch 11 remained byte-identical. Independently comparing both deliveries confirmed identical diff bodies; only mail preambles changed.

Downloaded Actions artifacts were compared byte-for-byte with local generated candidates, `git show origin/main:<path>`, independently fetched `raw.githubusercontent.com` responses, and the matching manifest entries:

| Patch | SHA-256, identical in all four publication locations |
|---|---|
| Sultan Patch 51 | `be73180680fb545bc38939adc900a85c00cd7ec834323c3700dfe034ebb627d0` |
| GKI r38 Patch 51 | `9422b190e17145ee13cab48311110de5d76b1dc4a1518c9314dff8b16002e326` |

Pinned Midori reproduction in Actions has SHA `8fc7905d5c8d804191a4d3c29f75409ea69924fa18f0eda038f7b45f102d7fd6`; the exact reviewed-pair cross-check passed. No corrected code was reverted for parity.

Final status refresh run [36284739196](https://github.com/yapixel/xxksu_susfs_patch/actions/runs/36284739196) succeeded. Permanent [Status Issue #5](https://github.com/yapixel/xxksu_susfs_patch/issues/5) was updated at `2026-09-27T01:11:03Z` and independently read back: production rows show `be73180680fb` and `9422b190e171`, plus the explicit reviewed lifecycle-difference explanation. Its overall status remains REVIEW REQUIRED because the separate moving-reference watcher reports informational Midori Patch-50 drift against an older watch baseline; that is not the pinned comparison or an authoritative-source failure. Escalation was disabled for this refresh; no new issue was requested or created.

Final post-publication clean-checkout test result at `bb72cfe5e197e8f3342d4bbc2902d26dbb949b4c`: **Ran 331 tests in 363.333s — OK; zero skips**. Source/test revisions also passed full clean discovery (327 tests, then 328 tests, and 331 tests in 362.886s) and all focused regressions. The first run against published outputs exposed one test-setup failure in `test_13_multi_candidate_both_unchanged_noop`: historical generator fixtures were assumed to equal current production bytes. The related one-changed test had the same assumption. Both now use the actual initial delivery bytes; no-op still requires no commit/push, and added assertions verify unchanged GKI bytes and local/remote HEAD. Both focused tests pass. No production logic was weakened or changed for this failure.

Signing: interactive GPG access blocked; commits used the user-authorized `--no-gpg-sign` fallback. No Git identity/signing configuration or history was rewritten. Unsigned local commit hashes are recorded in the intentionally ignored local `.codex/HANDOFF.md` ledger. Final evidence-only documentation follows the delivery commit and does not alter production bytes.

Reproduction command (WSL Debian, clean detached checkout of the final delivery):

```sh
PYTHONPATH=.github/scripts \
GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=commit.gpgsign GIT_CONFIG_VALUE_0=false \
GIT_CONFIG_KEY_1=tag.gpgsign GIT_CONFIG_VALUE_1=false \
python3 -m unittest discover -s .github/scripts/v2/tests -p 'test_*.py' -v
```

The environment-only Git settings allow disposable test repositories to commit without interactive signing; they do not modify repository/global configuration. Production diffstats were also independently checked directly on all three published patches, not merely generated fixtures.


## Remote-memory SUS_MAP correction (2026-09-27)

Provenance: **UPSTREAM_INHERITED_DEFECT + REVIEWED_LOCAL_CORRECTION**.
Audited main: 6c3c9f669a2c9ccb2a21a0be54256cf5f735c862. Accepted Simonpunk
Sultan a8324101bca5e5a2dd7d0dc82b1650e10923eec9 and GKI
b213c54126fb243595ce7876e91d84d6e0861fec both insert the guard before GUP.
Real Sultan af5c65b9547a9f33c5f566430d0434aecab5a8b5 sources and the authenticated
r38 archive (accf8f9348280116792c9608f420f8d4554da52499119a8536883c5eefd429ff)
confirm the postimages independently of repository source fixtures.

In GKI, __access_remote_vm initializes vma=NULL each iteration; the inherited
check can never hide anything. Sultan initially looks up/expands the VMA before
the loop, but the inherited check subsequently tests the previous GUP's VMA.
A request crossing visible into hidden memory can therefore transfer hidden bytes;
even proc mem's PAGE_SIZE request can cross a boundary when its address is unaligned.
This is not a deinlining error. Authenticated Midori 54b1647db92ead90acf263e0dd48836163b40da5
Patch 50 plus its own converter retains the GKI NULL-VMA check. Current Midori main
0a41be581964a7dee9ca6163a64ebea663133876 was checked independently: both inputs
and the reproduced output match the pinned reference bytes.

The correction adds one vma_lookup(mm, addr) immediately before the existing
SUS_MAP test on every iteration, under the already-held mmap read lock. GKI's
get_user_page_vma_remote calls its six-argument get_user_pages_remote with locked=NULL;
Sultan uses the seven-argument API with vmas=&vma and locked=NULL. Neither permits
fault retry to drop the lock here. No reference has been acquired when hiding
breaks the loop. Native successful-page cleanup remains unchanged (Sultan
kunmap/put_page; GKI unmap_and_put_page). A naive post-GUP break would leak a reference;
it also allows hidden write faults before rejection, so it is not used.

Upstream's Kconfig promises hiding real file mappings from mem, excludes anonymous
memory, and the existing break establishes stop semantics. We preserve the native
inaccessible-region convention: return transferred prefix bytes; a hidden start
returns zero internally, becoming -EIO in proc mem_rw with unchanged position.
Visible-to-hidden returns only the visible prefix; hidden-to-visible does not skip
hidden memory. Writes obey the same boundary and do not dirty hidden pages. This
is deliberately different from pagemap's fixed-entry-count zero representation.
Maps/smaps/rollup/map_files continue omitting hidden mappings as already reviewed.
Other callers of access_remote_vm/access_process_vm share this correction; direct
GUP users (for example process_vm_readv/writev) are outside this specific call path.

Anonymous/visible access, FOLL_WRITE/FOLL_FORCE, unmapped errors, and native stack
expansion are retained. expand_stack may drop/reacquire mmap_lock; successful
initial expansion reaches the new lookup, and GKI's later expansion continues back
to it. Failure returns with the lock already dropped, as before. No VMA pointer
is reused across that transition. Sultan retains its native initial-only expansion
behavior. IO/PFNMAP fallback is rejected before GUP for a hidden VMA; visible
vm_ops->access dispatch and native return handling are unchanged.

The target-native remote-memory regression executes the real generated function,
access_remote_vm wrapper, and proc mem_rw. It covers read/write, partial/unaligned
boundaries, anonymous mappings, holes, expansion/reacquisition, IO fallback,
configuration-disabled cases, and page reference/lock balance. Native GUP declarations
and the GKI wrapper come from authenticated target header excerpts. These bounded
regressions do not claim full kernel runtime proof.

Patch 11 SID note (read-only): native xxKSU is_sid_match uses a context fallback
when cached SID is zero. Added susfs_* values are populated after apply_kernelsu_rules
but direct equality helpers lack that fallback; a pre-initialization or failed
context conversion can yield a false negative. Classify as LOW robustness concern,
not proof of a failure under normal successful policy initialization. No Patch 11
change is part of this correction; no universal policy-reload correctness claim is made.


## Source-postimage migration (2026-09-27)

Migration freezes the production postimages at repository
`b1e15279d00f2ec52795ccf1667a696d34c6e484`: Sultan 18 files and GKI 16 files.
The user reports Sultan full kernel build PASS; GKI full build, ROM boot, xxKSU
root and basic SuSFS runtime PASS. No new boot/runtime claim is inferred.

`policy/patch51_source.py` applies complete authoritative Patch 50 changes to
authenticated source, then removes exact reviewed KSU-only source blocks.
Sultan core replacements come from the existing reviewed repository core policy,
not Midori or a final Patch 51. Existing lifecycle corrections remain unchanged.
GKI retains its source adapter; hunk-coordinate exclusions and Python final-hunk
re-emission are retired from production. The old converter remains historical.

Native Git commands use `git -c core.quotePath=false diff --no-ext-diff
--no-textconv --no-color --no-renames --full-index` and the same command with
`--stat=80`. Git owns hunk ranges/context/indexes/statistics. Mail Date/attribution
policy is unchanged. Canonicalization updates reviewed reference **format**
fingerprints only, after proving all kernel postimages identical; classifications
and reference payloads/policy remain unchanged. Midori is not imported/read by
source reconstruction: it is compared only after candidate generation.

The normal build boundary is `validation/patch51_kbuild.py`: ARM64 target
`gki_defconfig`, accepted xxKSU with unchanged Patch 11, LLVM 14, and actual Kbuild
commands. Final-diff C paths seed object selection; Kbuild determines object names.
Potential providers are discovered from configured source/unity builds, but only
global definitions in real compiled objects satisfy closure. A native relocatable
aggregate catches duplicate definitions; unresolved SuSFS symbols fail closed.
This is **not** a vmlinux link. Missing header and both historical mount-helper
mutations run against actual Kbuild objects and must be rejected before restoration.

Test consolidation: the old manually invoked four-object/two-symbol linker check
in `test_sultan_stat_compile` is replaced by this configured Kbuild/dynamic closure
and historical mutations. The authenticated-header CONFIG-disabled checks remain:
the enabled production configuration does not supersede those negative boundaries.
Manual diffstat column-width equality is removed; native Git identity/round trip
and independent file/count accounting retain its useful invariant. Unique parser,
transformation, lifecycle, provenance and publication/no-op protections remain.
