# Code Review Report for yapixel/xxksu_susfs_patch

- Review target: `github.com/yapixel/xxksu_susfs_patch` @ `fa0f719` (2026-09-29)
- Review date: 2026-10-02
- Comparison baselines (all verified individually after actual retrieval, not from memory):
  - xxKSU: `backslashxx/KernelSU` author-pinned `f263bdb9`, and current master `5da23982`
  - SuSFS: `simonpunk/susfs4ksu` `gki-android16-6.12` @ `b213c541`, `sultan-shiba-susfs-minimal` @ `a8324101`, and the lineage `c8f64e41` claimed by Patch 11
  - Upstream Patch 10: `kernel_patches/KernelSU/10_enable_susfs_for_ksu.patch` @ `b213c541`
  - Kernel source: Google `android16-6.12-2025-09_r38` (commit `98d5b9e071f1`), `kerneltoast/android_kernel_google_tensynos` @ `af5c65b9`
- Methodology: Constructed two trees: "clean source + upstream Patch 50" and "clean source + this repository's Patch 51", classifying each diff hunk one by one; read Patch 11 section by section against upstream Patch 10 and xxKSU source code; Python tests actually executed (macOS). **Kernel was not built; no physical device testing was performed**; items marked "inferred from code reading only" have not been verified via execution.

> Severity: **High** = May cause incorrect behavior / build failure / leaks; **Medium** = Logical inconsistency or foreseeable maintenance risk; **Low** = Redundancy, style, descriptive text; **Info** = Observation, not necessarily requiring changes.
> "Author-documented intentional designs" and "Bugs" are listed separately; "inherited from upstream" indicates the issue comes verbatim from simonpunk's Patch 50 / kernel, not introduced by this repository, but will be shipped with this repository's artifacts.

## Summary: recommended priorities

| # | Severity | Item | Source | Section |
|---|---|---|---|---|
| 1 | High | The pinned xxKSU `f263bdb9` has become unreachable due to upstream force-push; Patch 11, Patch 51 Kbuild gate, and clean-room all rely on fetching it by SHA, and will break together once GC'd | This repo | 2.1, 5.1 |
| 2 | Medium | GKI Patch 51 removed upstream's lockless early return `mnt_id < DEFAULT_KSU_MNT_ID`; on every `statfs()`, apps write-lock global `mount_lock`; retained in Sultan version, making the two targets inconsistent | This repo | 4.1 |
| 3 | Medium | Sultan Patch 51 rewrote SuSFS core, reviving upstream's retired `TRY_UMOUNT` code (dead code, link failure, unlocked traversal), and changed `susfs_run_sus_path_loop` to global | This repo | 3.1 |
| 4 | Medium | Patch 11 outer condition `\|\| new_uid == WEBVIEW_ZYGOTE_UID` causes non-zygote processes to be marked "umounted" while not actually umounted | This repo | 1.1 |
| 5 | Medium | open-redirect calls `getname_kernel()` (`GFP_KERNEL`) during RCU-walk, present in both targets | Inherited from upstream | 3.2, 4.2 |
| 6 | Medium | "GKI 6.12 = Pixel 9" does not match Google's official table (Pixel 9 is `android14-6.1`) | This repo | 4.5 |
| 7 | Medium | Watcher does not check reachability, exits 0 on drift, Patch 10 comparison is silently skipped when baseline is missing, `ksu_commit` override only updates commit field, Patch 11 template lacks semantic check against upstream Patch 10 | This repo | 5.2–5.5 |
| 8 | Medium | auto-clean deletes all failed runs and retains only 5 successful runs; 6 evidence runs cited in docs all 404 when spot-checked | This repo | 5.5 |
| 9 | Low | Kconfig help text outdated, dead variables, `KSU=y` dependency, `d_path` error checking, documentation out of sync with removed gates, various stale hashes | Mixed | 1.x, 2.x, 3.4, 4.4 |

**Overall Assessment**: The removal of KSU transport in Patch 51 and the author's 5 lifecycle fixes (`clone_mnt`, pagemap, smaps_rollup, remote-memory) were confirmed line-by-line to be correct, and they fix genuine defects present in upstream, worthy of upstreaming back to simonpunk. Both Patch 51 patches apply with 0 fuzz to verified clean source trees. The main issues are concentrated in three areas: first, a few changes added by this repository that are inconsistent with upstream (Items 2–4 in the table above); second, lack of protection in provenance/automation against "upstream history rewrites" (Items 1 and 7 in the table above); third, outdated documentation and metadata.

---

## 0. Items Verified as "Correct / No Issue" (Conclusion first to avoid duplicate investigation)

| Item | Result |
|---|---|
| sha256 of the three production patches vs `patches/manifest.json` | Consistent |
| Patch 11 applied to pinned `f263bdb9` | `git apply --check` passed |
| Patch 11 applied to xxKSU current master `5da23982` | Passed (files modified upstream do not touch Patch 11 hunks) |
| 13 files in `v29-baselines/xxksu.json` vs upstream `f263bdb9` | Byte-for-byte consistent |
| Content hashes in `v29-baselines/*.json` vs each `BASELINE.json`'s `retained_file_hashes` | All consistent |
| KSU-side symbols needed by SuSFS core `fs/susfs.c` (`susfs_is_current_ksu_domain`, `setup_selinux`, `ksu_cred`) | xxKSU + Patch 11 both have non-static global definitions with matching types |
| `susfs_ksu_sid`, `susfs_priv_app_sid` referenced by Patch 50 | Defined in Patch 11 |
| Patch 11 splitting upstream's single `susfs_set_batch_sid()` into 5 functions | Core side (Patch 50 / `susfs.c`) does not reference `susfs_set_batch_sid`, will **not** cause link failure |
| Handler signatures in `susfs.h` `void (void __user **)` vs xxKSU `ksu_handle_sys_reboot(..., void __user **arg)` | Consistent; passing `arg` directly is correct |
| Patch 11 setresuid logic vs upstream Patch 10 (`handle_zygote_setresuid` / `handle_zygote_next_setresuid`) | For zygote / zygote_next child processes: isolated -> umount, manager / authorized -> do not mark, rest -> `NO_SU`, semantically equivalent to upstream (manager / authorized do an early `goto` in xxKSU native flow); **webview zygote handling and outer uid bypass excepted, see 1.1 / 1.7** |
| Unknown / deprecated SUSFS commands swallowed with `return 0` | Userspace `ksu_susfs` initializes `info.err = ERR_CMD_NOT_SUPPORTED` beforehand, so it still correctly reports "not supported"; not an issue |

---

## 1. Patch 11 (`patches/xxksu/11_enable_susfs_for_ksu.patch`)

### 1.1 [Medium] `WEBVIEW_ZYGOTE_UID` outer condition is overly broad
- Location: `11_enable_susfs_for_ksu.patch:160`
  ```c
  if (susfs_is_current_zygote_domain() || new_uid == WEBVIEW_ZYGOTE_UID) {
      handle_zygote_setresuid(new, old, new_uid, false);
  ```
- Problem: webview_zygote is itself forked from zygote; when `setresuid(1053)` occurs, current is still in the `zygote` domain, so `susfs_is_current_zygote_domain()` is already true. Therefore, `|| new_uid == WEBVIEW_ZYGOTE_UID` is **redundant** for the normal path; its only newly introduced effect is allowing **non-zygote root processes** that call `setresuid(1053)` to also enter `handle_zygote_setresuid()`.
- Failure scenario: Any root (non-zygote) process calls `setresuid(1053, ...)` ->
  1. `susfs_set_current_proc_no_su()` is unconditionally set;
  2. If `ksu_uid_should_umount(1053)` is true, `TIF_PROC_UMOUNTED` is set and `susfs_extra_works` is scheduled;
  3. However, xxKSU native `ksu_handle_umount()` will refuse to umount because `is_zygote(old)` is false (`kernel_umount.c:105`),
  resulting in **the flag claiming "umounted" while actual umount did not happen**; SuSFS core's hiding decisions based on `TIF_PROC_UMOUNTED` become inconsistent with the actual mount state.
- Upstream comparison: `b213c541`'s `ksu_handle_setresuid()` only checks `susfs_zygote_sid` / `susfs_zygote_next_sid`, without this uid bypass.
- Recommendation: Change the outer condition back to only checking domains:
  ```c
  if (susfs_is_current_zygote_domain())
      handle_zygote_setresuid(new, old, new_uid, false);
  else if (susfs_is_current_zygote_next_domain())
      handle_zygote_setresuid(new, old, new_uid, true);
  ```
  The umount requirement for webview zygote is already handled inside `should_umount` by `new_uid == WEBVIEW_ZYGOTE_UID`; no outer bypass is needed.

### 1.2 [Low] `susfs_is_boot_completed_triggered` is a dead variable
- Location: `11_enable_susfs_for_ksu.patch:362-364`; source hardcoded in `.github/scripts/v2/adapters/xxksu.py:251`
- Upstream replaced this long ago with `susfs_is_sdcard_android_data_decrypted` (SuSFS historical commit `b917aac`, etc.); `b213c541`'s `fs/susfs.c`, `susfs.h`, Patch 50, and Patch 10 **contain zero references** to it; Patch 11 defines it but never sets it to `true`, and nobody reads it.
- Impact: Adds an unused global symbol (which also appears in kallsyms if not covered by `HIDE_KSU_SUSFS_SYMBOLS`), contradicting the claim of "using Patch 10 as semantic lineage".
- Recommendation: Delete this definition and the corresponding payload in the adapter.

### 1.3 [Low] Kconfig help text is from an older SuSFS version and does not match the pinned lineage
- Location: `11_enable_susfs_for_ksu.patch:34-111`
- Comparison with `b213c541` Patch 10 Kconfig (listing only those with substantive differences):

| Option | Patch 11 wording | Upstream `b213c541` wording |
|---|---|---|
| `SUS_PATH` | "(NOT recommended)", "temp fix for the leaks of app path in /sdcard/Android/data", "Effective only on zygote spawned user app process" | No "NOT recommended"; suggests using `add_sus_path_loop` for frequently changing paths; effective only on zygote/zygote_next child processes with `TIF_PROC_UMOUNTED` |
| `SUS_MOUNT` | "Effective on all processes", "mnt_id ... assigned to a much bigger number" | Only assigns fake ids to mounts of ksu processes before /sdcard decryption; effective only on processes with `TIF_PROC_UMOUNTED` |
| `SUS_KSTAT` | "Effective only on zygote spawned user app process" | "Effective on all processes with (uid % 100000) >= 10000" |
| `OPEN_REDIRECT` | "(experimental)", "uid < 2000" | Not experimental; both paths must exist beforehand; SELinux permissions must be handled manually; "pre-defined uid scheme" |
| `SUS_MAP` | "zygote spawned umounted user app process" | Additionally requires `(uid % 100000) >= 10000` |

- Impact: Descriptive text only, does not affect compilation, but may mislead users regarding the effective scope of features (especially `SUS_KSTAT` / `SUS_MOUNT` where the effective targets are inverted).
- Recommendation: Sync help text from the pinned Patch 10; or add a check in the adapter verifying that "help text matches Patch 10".

### 1.4 [Low] `KSU_SUSFS` does not restrict `KSU=y`
- Location: `11_enable_susfs_for_ksu.patch:26-29`; in xxKSU `kernel/Kconfig:3-4`, `config KSU` is `tristate`, and xxKSU master recently had "restore LKM support" (`89701bc8`).
- Failure scenario: `CONFIG_KSU=m` + `CONFIG_KSU_SUSFS=y` (Kconfig allows bool depending on m to be y) -> symbols referenced by the core side (Patch 51, `fs/susfs.c`) such as `susfs_is_current_ksu_domain`, `susfs_ksu_sid`, `ksu_cred` are defined in a module -> vmlinux link failure; conversely, the module also cannot access non-`EXPORT_SYMBOL` `susfs_*` symbols.
- Upstream also lacks this check, but xxKSU explicitly supports LKM, making it easier to hit than upstream.
- Recommendation: `depends on KSU=y`.

### 1.5 [Low] SID cache duplicated and lacks fallback
- Location: `11_enable_susfs_for_ksu.patch:230-234, 295-319`
- xxKSU already has `cached_zygote_sid` / `cached_su_sid` / `cached_init_sid` and `is_sid_match()` (`selinux.c:165`), which fall back to string comparison when the cache is 0; Patch 11 introduces a separate set of `susfs_*_sid`, which directly compare `current_sid() == 0` when the cache is 0, evaluating to false permanently.
- Additionally, upstream declares these five variables as `__read_mostly`, which Patch 11 lacks (read on every setresuid in the hot path).
- The author already assessed this as a LOW robustness concern in `PATCH51_CORRECTIONS.md`; here it is only added that `susfs_set_zygote_sid()` etc. can directly reuse xxKSU's cache sources to avoid desynchronization between the two sets of SIDs during policy reloads.

### 1.6 [Low] Duplicate logs, redundant includes, and mixed whitespace
- `11_enable_susfs_for_ksu.patch:400-403`: The added `#ifdef CONFIG_KSU_DEBUG pr_info("sys_reboot: intercepted call! ...")` will duplicate xxKSU's original unconditional `pr_info("sys_reboot: magic: ...")` for **non-SUSFS** calls; SUSFS calls, on the other hand, are not logged by the native log due to early `return 0` (this part is good). Recommended to remove the added block.
- `11_enable_susfs_for_ksu.patch:356-360, 387-391`: xxKSU is a unity build (`ksu.c` sequentially `#include`s each `.c`); `objsec.h` is already included in `ksu.c:25`; in `dispatch.c` / `supercall.c`, re-including `objsec.h` and `<linux/namei.h>` is redundant (include guards prevent errors).
- `11_enable_susfs_for_ksu.patch:374`: `        	susfs_start_sdcard_monitor_fn();` mixes "8 spaces + tab"; `:191` `susfs_init();` uses 4 spaces, inconsistent with surrounding tab indentation (`checkpatch` will complain).

### 1.7 [Intentional design, not a bug] WebView zygote will be umounted
- `11_enable_susfs_for_ksu.patch:136`: `should_umount` includes `new_uid == WEBVIEW_ZYGOTE_UID`.
- Upstream SuSFS explicitly "does not umount webview zygote" (`b1dceb4`: `// we should not umount for webview zygote`; current `b213c541` only checks `is_appuid(ruid)`).
- Patch 11 retains the case 4 behavior of xxKSU native `kernel_umount.c`, and the runtime table in README also claims the WebView zygote path has been verified. This is an intentional retention of documented xxKSU native semantics and is **not classified as a bug**; note only that because TIF flags are inherited across fork, all webview isolated renderers will also carry `TIF_PROC_UMOUNTED`, behaving differently from what upstream SuSFS users expect; recommending stating this explicitly in README.

---

## 2. Provenance / Metadata Consistency

### 2.1 [Medium, consequence in 5.1 High] Pinned xxKSU commit `f263bdb9` is no longer on any upstream branch
- `backslashxx/KernelSU` master was rewritten on 2026-10-01 (new head `5da23982`, `19937348 "KernelSU v3.3.0+"` replaced `f263bdb9`). `git branch -r --contains f263bdb9` is empty; currently it can only be retrieved by "fetching directly by SHA".
- `AGENTS.md` explains that xxKSU force-pushes are normal and ancestry is not an acceptance prerequisite, so this is not a policy violation; however, the risks are:
  - Unreachable objects may be garbage-collected by GitHub, at which point `BASELINE.json`'s `archive_url` (codeload by SHA) and clean-room will become unreproducible;
  - Tracked files modified between `f263bdb9 → 5da23982`: `kernel/Kconfig` (`KSU_KPROBES_KSUD` became deprecated), `kernel/feature/kernel_umount.c`, `kernel/kernel_compat.h`, `kernel/kernel_includes.h`, `kernel/ksu.c`. I have confirmed these changes do not affect Patch 11 hunks (Patch 11 still applies cleanly), so the new head can be accepted as soon as possible.
- Recommendation: Save the verified xxKSU tarball as a release asset (as is already done for GKI r38), rather than relying on upstream retaining unreachable objects.

### 2.2 [Low] Patch 11's Patch 10 lineage is inconsistent with watch state
- `patches/xxksu/BASELINE.json` / `manifest.json`: `c8f64e41` (Patch 10 sha `757d0991…`)
- `.github/upstream-state.json` `susfs_gki`: `b213c541` (Patch 10 sha `590e1bc9…`)
- I compared differences between the two Patch 10 versions; they only involve index lines, riscv Kbuild, and `PT_REGS_SYSCALL_PARM1` due to upstream KernelSU catching up, **with no semantic impact on the parts mirrored by Patch 11**. However, the two records contradict each other; recommended to advance lineage to `b213c541` for consistency.

### 2.3 [Low] Gate described in documentation has been removed, but documentation still portrays it as "currently active"
- `b6a2383` (2026-09-28) removed `validation/reference_cross_check.py`, its tests, and workflow steps.
- However, `PATCH51_CORRECTIONS.md:60` ("Sensitive file differences now block as REVIEW_REQUIRED unless ... reference_cross_check.py"), `:110`, and `UPSTREAM_TRACKING_AUDIT.md:75, 115-116` still describe this gate as an active safeguard.
- Readers may assume sensitive file differences are still protected by dual-hash review when it no longer exists. Recommended adding a note stating "removed in b6a2383" in these sections.

### 2.4 [Low] Hashes in `HANDOVER.md` / `PATCH51_CORRECTIONS.md` are all stale
- `HANDOVER.md` lists Patch 11 `a0419c3a…`, Sultan `67cc1506…`, GKI `d299ac9c…`, xxKSU `bb0be929…`, which are **all different** from current manifest (`c3f40703…`, `63a34d45…`, `f722add0…`, `f263bdb9`).
- `HANDOVER.md` states "Machine records override this dated snapshot", so it is not strictly wrong, but README lists it as the first item under maintenance docs, making it prone to misuse. Recommended adding dates and "Outdated" notice directly to the title, or changing it to reference manifest only.

### 2.5 [Info] Metadata advanced via manual commit
- `b15144a` ("reconcile upstream xxKSU drift at f263bdb9") directly modified `manifest.json`, `BASELINE.json`, and `upstream-state.json` manually, whereas `AGENTS.md:137-146` states `manifest.json` is a public interface and publication only goes through Actions (with a `METADATA_ONLY_PROMOTION` path). Patch bytes did not change, so practical risk is low, but inconsistent with custom procedures; meanwhile `v29-baselines/xxksu.json`'s `metadata` is empty without `identity`, yet `BASELINE.json` recorded `source_bundle.identity`.

---

## 3. Sultan Patch 51 (`patches/sultan-android14-6.1/51_deinlined_susfs_hooks_sultan-android14-6.1.patch`)

### 3.0 Verification Results Summary
- `kerneltoast/android_kernel_google_tensynos` `16.0.0-sultan` head remains `af5c65b9` (GitHub compare: identical); patched files have not changed.
- The 21 Sultan fixture files in the repository are byte-for-byte identical to the original files retrieved from GitHub; `fs/susfs.c`, `susfs.h` match the upstream `a8324101` core.
- Both upstream Patch 50 and this repository's Patch 51 apply to clean trees with 0 offset / 0 fuzz / 0 reject; all 18 index blob hashes of Patch 51 match.
- Core files and Patch 10 between `sultan-shiba-susfs-minimal` and `gki-android14-6.1` are completely identical; difference lies only in 6 Sultan-specific adjustments in Patch 50, all of which are retained in Patch 51.
- 15 files differ between A (clean tree + Patch 50) and B (clean tree + Patch 51):
  - The 8 files touched only by Patch 50 (`drivers/input/input.c`, `fs/exec.c`, `fs/open.c`, `fs/read_write.c`, `kernel/reboot.c`, 3 selinux files) all belong to "KSU transport / selinux_hide natively handled by xxKSU"; removal is justified.
  - `calculate_f_flags_wrapper` / `statfs_by_dentry_wrapper` are defined in `fs/statfs.c`; signatures and config guards are byte-for-byte identical to Patch 50.
  - `susfs_is_current_proc_no_su()` in Patch 50 was only used to block 3 sucompat transports, deleted in Patch 51 along with the hooks; Patch 11 still sets `NO_SU`, but there are no readers left (xxKSU achieves equivalent effect via seccomp + `TIF_KSU_MANAGED`), harmless.
  - The author's 3 fixes for Sultan (`clone_mnt` inheritance flag clearing + `out_free` guard, pagemap per-VMA walker, remote-memory per-iteration `vma_lookup`) were confirmed correct line-by-line against source code.

### 3.1 [Medium] Patch 51 rewrites SuSFS core, reviving upstream's retired `TRY_UMOUNT` code (introduced by this repository)
- Location: `51_…sultan….patch:2232-2233` (`susfs_run_sus_path_loop` changed from `static` to global), `:2241-2296` (entire `CONFIG_KSU_SUSFS_TRY_UMOUNT` block), `:2312-2349` (corresponding struct and declarations in `susfs.h`); source is `.github/scripts/v2/policy/sultan_source.py:10-27`'s `CORE_REPLACEMENTS` (hardcoded string replacement).
- Problems:
  1. `CONFIG_KSU_SUSFS_TRY_UMOUNT` **does not exist** in Patch 11 Kconfig or upstream `a8324101`; the entire block is dead code;
  2. If manually enabled, `extern void try_umount(const char *, int)` corresponds to `static inline` `try_umount()` in xxKSU (`kernel_umount.c`), failing to link; furthermore, `susfs_try_umount()`, while traversing `LH_TRY_UMOUNT_PATH`, **does not hold** `susfs_spin_lock_try_umount`, causing races with concurrent `susfs_add_try_umount()`;
  3. `susfs_run_sus_path_loop` was made non-static, but has no external callers anywhere in the repository;
  4. Contradicts the statement in README claiming "not restoring retired legacy glue";
  5. Couples Sultan Patch 51 to requiring users to first supply `a8324101`-identical `susfs.c` / `susfs.h`; as soon as SuSFS core updates, Patch 51 fails to apply (GKI Patch 51 does not have this coupling).
- Contradiction with README: README Runtime Validation table states "Sultan `ADD_TRY_UMOUNT` … paths verified". However, under the current patch combination, `CONFIG_KSU_SUSFS_TRY_UMOUNT` does not exist, and Patch 11 has no `CMD_SUSFS_ADD_TRY_UMOUNT` handler (`susfs_def.h` marks it as `/* deprecated */`); `ksu_susfs add_try_umount` simply returns `ERR_CMD_NOT_SUPPORTED`. **Author is requested to clarify whether the "verified" ADD_TRY_UMOUNT in README refers to xxKSU's native try-umount (`ksud`'s umount list) or the SuSFS command; if the latter, it cannot pass with current artifacts**, and README wording should be corrected.
- Recommendation: In `CORE_REPLACEMENTS`, delete the two replacement sets for TRY_UMOUNT and `susfs_run_sus_path_loop`; the include of `<uapi/linux/magic.h>` is also unnecessary (core files already compile). Make Sultan Patch 51 leave SuSFS core files untouched, just like GKI.

### 3.2 [Medium, inherited from upstream] open-redirect performs sleepable allocation during RCU-walk
- Location: `51_…sultan….patch:403-421` (`path_openat`), corresponding to upstream Patch 50 same section; GKI version has the same structure (see Section 4).
- Problem: The initial `do_filp_open()` runs with `LOOKUP_RCU`, and `path_init()` has already invoked `rcu_read_lock()`; when the `link_path_walk` / `open_last_lookups` loop finishes, nd may still be in RCU mode (`complete_walk()` is only done in `do_open()`). At this point, calling `susfs_open_redirect_spoof_do_sys_openat()`, in which `getname_kernel()` allocates with `GFP_KERNEL` (sleepable), before `terminate_walk()` releases RCU.
- Failure scenario: Performing a regular `open()` on a file configured with open-redirect sleeps within an RCU read-side critical section: with `CONFIG_DEBUG_ATOMIC_SLEEP` / `PROVE_RCU` enabled, a splat will be triggered; under non-preemptible RCU configurations, this is a genuine RCU violation that may cause the grace period to end prematurely.
- Recommendation: Before calling spoof, if `nd->flags & LOOKUP_RCU`, call `try_to_unlazy(nd)` first; if it fails, return `-ECHILD` to allow `do_filp_open` to retry with ref-walk; or defer `getname_kernel()` until after `terminate_walk()`. This is an upstream issue; recommended to report to simonpunk simultaneously.

### 3.3 [Low, inherited from upstream, behavior change] Sultan native `id.gms.unstable` uname spoofing unconditionally removed
- Location: `51_…sultan….patch:2405-2443` (`kernel/sys.c` `newuname`), upstream Patch 50 `:2501` also deletes it.
- Problem: Deletion is not wrapped inside `#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME`; if users do not use `ksu_susfs set_uname`, DroidGuard (`id.gms.unstable`) sees Sultan's real release string, making it more identifiable than the native kernel.
- Recommendation: Retain native check, only overriding with SuSFS spoof when the buffer has been configured; or remind users in README that uname must be configured.

### 3.4 [Low, inherited from upstream] `d_path()` error checked with `NULL`
- Location: `51_…sultan….patch:919-920` (`fs/notify/fdinfo.c`), `:1136-1137` (`fs/proc/fd.c`)
- `d_path()` returns `ERR_PTR(-ENAMETOOLONG)` etc. on failure, **never NULL**; `if (!dpath)` fails to catch errors, and subsequent `kern_path(dpath, …)` dereferences an error pointer, causing an oops. Triggering requires extremely long paths; low probability, but a definite bug.
- Recommendation: `if (IS_ERR(dpath)) goto out_kfree;`

### 3.5 [Low, inherited from upstream] Others
- `51_…sultan….patch:911`: The SUS_MOUNT branch in inotify fdinfo checks inotify fd's own anonymous file `file->f_path.mnt` (anon inode mount, `mnt_id` is always small); condition never holds, making this branch dead code.
- `51_…sultan….patch:815-824`: The fallback in `susfs_get_non_sus_vfsmnt_from_vfsmnt()`, while holding `mount_lock`, calls `mntput`, and returns a vfsmnt without holding a reference; subsequent `mntput` by the caller underflows refcount by one; virtually unreachable in practice.
- `fanotify_fdinfo` remains a 2-parameter signature while `show_fdinfo` expects 3 parameters: currently Sultan does not enable `CONFIG_FANOTIFY`, so it is not triggered; if enabled, build will fail due to `-Werror=incompatible-pointer-types`.

### 3.6 [Info, inherited from upstream, applies to both targets] Patch 11 sets `TIF_PROC_UMOUNTED` before umounting, causing native umount to actually skip KSU mounts
- `51_…sultan….patch:813-826`, GKI `51_…r38.patch:682` onwards (identical `__lookup_mnt` hook on both sides): For processes carrying `TIF_PROC_UMOUNTED`, path traversal skips mounts with `mnt_id >= DEFAULT_KSU_MNT_ID`.
- Patch 11 `handle_zygote_setresuid()` calls `susfs_set_current_proc_umounted()` before `ksu_handle_umount()` (same order as upstream `b213c541`); when xxKSU's `try_umount()` uses `kern_path()` to look up mountpoints, it cannot see these mounts, and skips them directly thinking they "have already been umounted" because `path.dentry != path.mnt->mnt_root`.
- Result: For mounts created by KSU before /sdcard decryption, hiding in reality relies solely on the lookup hook without actual umounting (upstream comments also explicitly state "with this hack, we do not even need to umount"). Inferred from code reading, not verified on real devices; if genuine umount is desired, flag setting can be moved after `ksu_handle_umount()` (older upstream `b1dceb4` used this order).

### 3.7 [Intentional design, residual issue] AVC log spoofing switch silently ineffective on Sultan
- Patch 51 removed SuSFS hooks in 3 selinux files (delegating to xxKSU native selinux_hide), but Patch 11 still handles `CMD_SUSFS_ENABLE_AVC_LOG_SPOOFING`; the static key it toggles has no consumers left. Users issuing the command receive a success response with no actual effect. Recommended that Patch 11 reports unsupported for this command, or note this in README.

---

## 4. GKI Patch 51 (`patches/gki-android16-6.12/51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch`)

### 4.0 Verification Results Summary
- Google tag `android16-6.12-2025-09_r38` exists (tag object `1b0462bd` -> commit `98d5b9e071f1`). The 20 source files in repository `r38-sources.json` are **byte-for-byte identical** to Google's commit, with correct embedded sha256. Therefore, the content of the author-mirrored tarball is trustworthy, though the verification chain does not connect directly to Google (see 5.6).
- `c8909f7` is a subsequent branch point rather than r38; manifest already notes it is only provenance lineage, separate from the actual apply target, which is accurately described.
- Upstream Patch 50 (`b213c541`) applied to r38: 24 of 25 files have only line number offsets; the sole reject is hunk 1 of `security/selinux/hooks.c` (context contains ANDROID KMI comments not present in r38), belonging to the KSU side, which Patch 51 does not retain anyway.
- This repository's Patch 51 applied to r38: 16 files, 0 offset / 0 fuzz / 0 reject, all index blob hashes match.
- A total of 45 hunks differ between A and B, with no unexplainable SuSFS logic changes found; removals of KSU transport hooks (input, exec, open, read, stat, reboot, setresuid, SELinux hide) are all justified.
- The author's 5 fixes (`clone_mnt` inheritance flag clearing, `out_free` guard, `smap_gather_stats` guard, `susfs_pagemap_walk`, `__access_remote_vm` adding `vma_lookup`) were confirmed correct item by item, fixing genuine upstream defects; **recommended to upstream back to simonpunk**.
- `calculate_f_flags_wrapper` / `statfs_by_dentry_wrapper` definitions are byte-for-byte identical to Patch 50; all 3 read sites of `NO_SU` were removed along with sucompat; KSU-side symbols required by Patch 51 include only `susfs_is_current_ksu_domain()`, which Patch 11 provides with matching type; CONFIG guards match.

### 4.1 [Medium] GKI version removed upstream's lockless early return, taking global `mount_lock` every time on hot path; retained in Sultan version
- Location: `51_…r38.patch:836-876` (in `fs/namespace.c`, the three `susfs_get_non_sus_*` helpers, entire file contains no `if (mnt->mnt_id < DEFAULT_KSU_MNT_ID)`); cf. upstream `b213c541` Patch 50 `:906`, `:921`, `:935`, and this repository's Sultan Patch 51 `:795`, `:809` (Sultan 6.1 lacks `mnt_id_unique`, has only two helpers, both retaining early return).
- Problem: All three helpers in the GKI version **invoke `lock_mount_hash()` immediately** (`write_seqlock(&mount_lock)`), even when the passed-in mount is not a KSU mount at all. One caller is `vfs_statfs()` (`51_…r38.patch:2046-2064`), traversed whenever `susfs_is_current_proc_umounted()`. xxKSU defaults to `default_non_root_profile.umount_modules = true` (`kernel/policy/allowlist.c:27`), so almost all regular apps carry this flag; consequently, every app `statfs()` write-locks global `mount_lock`, while simultaneously invalidating and causing retries for ongoing RCU path lookups across the entire system.
- Result: Output is completely identical to upstream (`mnt_id` does not change once allocated; lockless read is safe), **incurring only a performance cost**, and creating behavioral inconsistency between GKI and Sultan targets.
- `PATCH51_CORRECTIONS.md:91` frames this as "not adopting Midori's early-return optimization", but this code was actually in **upstream Patch 50 itself**, which is an inaccurate claim.
- Recommendation: Restore upstream's early return (`susfs_get_non_sus_vfsmnt_from_vfsmnt` must do `mntget` + `dget` on early return as upstream does), aligning GKI with Sultan.

### 4.2 [Medium, inherited from upstream] open-redirect performs sleepable allocation during RCU-walk
- Location: `51_…r38.patch:404` (`susfs_open_redirect_spoof_do_sys_openat()`, containing `getname_kernel()` / `GFP_KERNEL`) executed before `:407` `terminate_walk(nd)`.
- Same as Sultan 3.2, with identical fix.

### 4.3 [Low, inherited from upstream, inferred from code reading only] `SUS_PATH` leaves inconsistent dcache state or creates `..5.u.S` entities on create/unlink operations
- Location: `51_…r38.patch:63-114` (`lookup_dcache` / `lookup_one_qstr_excl`), equivalent to upstream Patch 50 `:142-193`; Sultan `51_…sultan….patch:100-116` similar.
- Scenarios:
  1. After `lookup_dcache()` hides a cached sus dentry and returns `NULL`, `lookup_one_qstr_excl()` allocates a dentry of the same name via `d_alloc()` and calls `->lookup`. For non-directory inodes, `d_splice_alias()` does not merge aliases, potentially leaving two positive dentries with the same name under the same parent directory in dcache.
  2. It then retries using `susfs_fake_qstr_name` (`..5.u.S`), returning a negative dentry. For `unlink`/`rmdir`, this yields the expected `-ENOENT`, but for `mkdir`/`O_CREAT`, it **actually creates an entry named `..5.u.S` on disk**. This constitutes filesystem pollution and can also be used to probe whether a path is hidden.
- Recommended to report upstream; this repository can consider returning errors like `-EEXIST` / `-EPERM` instead of renaming on create paths.

### 4.4 [Low, inherited from upstream] Others
- `51_…r38.patch:1140-1146` (`fs/proc/fd.c`) and `:969-975` (`fs/notify/fdinfo.c`): `d_path()` checked with `if (!dpath)`, same as 3.4.
- `51_…r38.patch:901-933`: When `CONFIG_FANOTIFY=y`, `fanotify_fdinfo` callback signature mismatches; clang >= 16 will fail compilation or trigger CFI trap; disabled in GKI default defconfig.
- fdinfo SUS_MOUNT block is dead code (same as 3.5). `susfs_get_non_sus_vfsmnt_from_vfsmnt` fallback calls `mntput` under lock and returns unreferenced pointer (same as 3.5, practically unreachable).
- In `avc.c`, `susfs_is_avc_log_spoofing_enabled` is SuSFS's own feature (`susfs.c:1195`), but was removed along with KSU transport, causing AVC spoofing switch to become silently ineffective (same as 3.7, affecting both targets).

### 4.5 [Medium] Device label "GKI android16-6.12 r38 = Pixel 9" contradicts official Google data
- Location: `README.md` Production Patches table, `patches/manifest.json` `compatibility_target`, `BASELINE.json` `metadata.compatibility_patches`
- Google's official "Build Pixel kernels" page (https://source.android.com/docs/setup/build/building-pixel-kernels ) lists: Pixel 9 / 9 Pro / 9 Pro XL (caimito), 9 Pro Fold (comet), 9a (tegu) all use **`android14-6.1`**; Pixel 6–8 likewise use 6.1 (so Sultan's "Pixel 7 Pro / 8 runs 6.1" is correct).
- The repository's own `.github/runtime-validation.json:8` also states `"device": "Not specified"` for GKI 6.12 (whereas Sultan explicitly states Pixel 7 Pro (cheetah)).
- Recommendation: Unless the author has indeed verified on a Pixel 9 6.12 community port kernel (if so, specify the source), remove "Pixel 9" wording to prevent users from applying 6.12 patches to stock 6.1 kernels on Pixel 9.

---

## 5. Automation Toolchain and CI (`.github/scripts/v2`, `.github/workflows`)

Testing: Executed full discovery on macOS / Python 3.12; of 252 tests, 11 failed + 1 error, all attributable to environment (glibc `loff_t`, `RUNNER_TEMP`, Apple `patch` automatically reverse-applying and returning 0 on already applied patches); after environment fixes, 2 remained, similarly due to Apple `patch` behavior. **Not run on Linux**, but found no test failures caused by genuine logic errors in the code.

### 5.1 [High] Three verification paths rely on SHA to fetch orphaned `f263bdb9`
- `generate-11-ksu-patch.yml:79` (`git fetch --depth=1 origin "$TARGET_COMMIT"`, Patch 11 generation), `validation/patch51_kbuild.py:110-112` (reads xxKSU identity from `upstream-state.json` then calls `fetch_git()`; **Patch 51** Kbuild gate also builds xxKSU + Patch 11), `clean_room.py:32-44` (`fetch_git()` with commit `fetch --depth=1`) and `:186`.
- Once GitHub reclaims this unreachable commit, all three paths (Patch 11, Patch 51, clean-room) will fail **simultaneously**, and error messages will only show fetch failures, making it difficult to associate with upstream force-push.
- Recommendation: See 2.1; save verified tarball as a release asset, or accept the new head as soon as possible.

### 5.2 [Medium] Watcher does not check ancestry / reachability
- `watch/checker.py:53-90` only uses `git ls-remote` to retrieve head; `:260-271` directly declares `IRRELEVANT_CHANGE` when tracked file hashes are unchanged, and dashboard shows HEALTHY.
- Offline simulation with master `5da23982`: result `SAFE_REGEN_CANDIDATE`, no issue opened, CLI exits 0.
- `AGENTS.md:113-115` explicitly notes xxKSU force-pushes are normal and ancestry is not an acceptance prerequisite, which is an intentional design; however, the consequence in 5.1 (accepted commit becoming unreachable) is **nowhere detected or warned**.
- Recommendation: At least add an informational check verifying "whether accepted commit is still reachable from tracking ref", flagging on the dashboard and prompting archiving when unreachable.

### 5.3 [Medium] Patch 11 is a hardcoded template with no mechanism verifying semantic consistency with upstream Patch 10
- `adapters/xxksu.py:132-294` hardcodes all hunks as string constants; `policy/patch11.py` is only invoked in tests, and production gate only checks if anchors can be found.
- Actual divergences have occurred: 6 Kconfig symbol prompts/help differ (modified upstream in `c023d8e`, `41e748a`), `susfs_is_boot_completed_triggered` (removed upstream in `b917aac`), upstream changed to `susfs_set_batch_sid()`. (Upstream returns `-EINVAL` on unknown SUSFS cmd, template returns `0`, but all callers in xxKSU `syscall_table_hook_arm64.c:53,137,217,274`, `kp_ksud.c:99` discard the return value, **no practical impact**.)
- The good news is symbols used by the template still exist upstream, so this is **not a compilation error**. However, the claim that "Patch 10 is semantic lineage" currently lacks programmatic guarantee.
- Recommendation: At least perform structured comparisons on Patch 10 Kconfig blocks and `ksu_handle_sys_reboot` cmd lists, failing closed to require manual review when upstream changes.

### 5.4 [Medium] Manual `ksu_commit` override only updates commit field; other provenance fields not synchronized
- `pipeline.py:204-250` `_plan_metadata_updates()` only writes `resolved_commit` / `commit`, without updating `tracked_files`, `relevant_content_hash`, `tree`, `archive_sha256`, `archive_url`, `retained_file_hashes`.
- Failure scenario: `workflow_dispatch` with `ksu_commit` (`generate-11-ksu-patch.yml:6,49`) advances -> `BASELINE.json` commit is new, while hash and archive remain old -> `accepted_sources()` and manifest checks still pass -> watcher compares against new commit subsequently, continuously reporting `NO_CHANGE`; only weekly clean-room detects inconsistency.
- Recommendation: When advancing commit, recalculate and write all provenance fields together, or verify archive / tree / tracked hash match new commit prior to promotion.

### 5.5 [Medium] Other toolchain issues
- **M1 Drift check silently skipped**: `watch/checker.py:469-476` logs `logger.warning` when Patch 10/50 for old commit cannot be fetched, then condition in `semantic/gate.py:318` `patch10_key in upstream_contents and baseline_contents and …` skips Patch 10 comparison when baseline is missing; subagent testing showed adding a new upstream call to Patch 10 still resulted in `passed=True`. Should fail closed. (In the same file `:305-316`, the loop looking up `patch10_key` is written twice, a copy-paste remnant.)
- **M2 Exit code 0 even when drift detected**: `watch/cli.py:117` returns 1 only when dashboard sync fails or manifest validation fails; drift requiring escalation does not affect exit code, and in `escalation.py`, `escalate_issue()`, upon `gh` failure, catches with `except … return None`, while `cli.py:74-76` does nothing with `None`. As a result, scheduled workflows show green, issues fail to open, and maintainers receive no notice.
- **M3 Evidence automatically purged**: `auto-clean-actions.yml:29-46` retains only the latest 5 successful runs for each workflow and deletes **all** failed and cancelled runs (`gh run delete … || true`). 6 runs cited as evidence in `HANDOVER.md` and `PATCH51_CORRECTIONS.md` (`36283493548`, `36284535551`, `36284739196`, `36296083518`, `36283493358`, `36294761634`) all returned **404** when queried via GitHub API (repo API returned 200; entire repo currently has only 32 runs remaining). Additionally, Upstream Watch run `36981486449` on 2026-10-02 concluded with success, matching M2's description: xxKSU upstream rewritten, yet scheduled run stayed green. Recommended retaining by day count, or at least not deleting runs cited by documentation, and saving critical evidence as artifacts/releases.
- **M4 `[skip ci]` and trigger paths**: Push trigger paths do not include `adapters/xxksu.py`, `engine/`, `source/`, `semantic/`, `upstream-state.json`, `BASELINE.json`; commits modifying code such as `899c010`, `2767ca6` used `[skip ci]`, violating `AGENTS.md:32` (`[skip ci]` restricted to doc-only). Normal validation occurred after current HEAD, but procedural gaps exist.
- **M5 Watcher candidate validation does not represent production**: Patch 11 apply validation applies back to the same source (circular); Patch 51 uses old `.github/scripts/deinline_50_to_51.py` (`checker.py:504`), not production generator (`policy/patch51_source.py`), so watcher declaring "safe to regenerate" does not guarantee production will pass.

### 5.6 [Low / Info]
- `validation/exact_patch.py` calls `patch` without `--forward` or `LC_ALL=C`; when fixing, do not use `--batch` (which automatically reverse-applies).
- `upstream-watch.yml:57-66`, `generate-51-kernel-patches.yml:119,235` interpolate `workflow_dispatch` inputs directly into shell; low risk as only users with write permission can trigger, but recommended passing via `env:`.
- Actions pins tags rather than commit SHAs; some protective assertions implemented via `assert` (removed by `python -O`).
- r38 source code only compared against author's own mirrored tarball hash (`yapixel/gki-build-assets`), without checking Google's official source.
- `patches/xxksu/BASELINE.json` records Patch 11 `size: 16772`, while actual file is **15458** bytes (same in git content), an old version remnant.
- In each `BASELINE.json`, `"status": "VERIFIED"` and `validation_results: PASS` are written strings, not recomputed dynamically.
- `pull_request_target` is not used; the only secret used is `GITHUB_TOKEN`, which is not printed.
- The description of "four profiles" matches code; no documentation claims six are implemented.

---

## Appendix

- [appendix_gki_findings.md](appendix_gki_findings.md): GKI Patch 51 hunk-by-hunk classification table, application logs, reproduction commands
- [appendix_sultan_findings.md](appendix_sultan_findings.md): Sultan Patch 51 hunk-by-hunk classification table, application logs, reproduction commands
- [appendix_tooling_findings.md](appendix_tooling_findings.md): Python toolchain / CI review details and test execution logs

> Appendices are subagent raw reports (English). The main report only includes items that have been re-verified; details in the appendices not cited by the main report have not been independently verified; please confirm before use.
