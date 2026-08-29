# xxKSU + SuSFS 11/51 Patch Semantic Analysis Report

**Phase 1 — Read-only investigation. No files modified.**

---

## 1. Why 11 + 51 Exist

### Core Architectural Reason

Upstream SuSFS patches target **tiann/KernelSU** (traditional KernelSU). That variant implements system call interception via **kprobe-based inline hooks** — it physically patches the syscall table to inject `ksu_handle_*` trampoline functions into `fs/exec.c`, `fs/open.c`, `fs/read_write.c`, `kernel/reboot.c`, `security/selinux/hooks.c`, etc.

**backslashxx/KernelSU (xxKSU)** — also called MidoriSU-XX — is a **fundamentally different architecture**. It does not use kprobe-based syscall table patching. Instead it uses:

- A **static-key guarded trampoline hook system** (`ksu_is_input_hook_enabled`, `ksu_is_init_rc_hook_enabled`, etc.)
- A **setuid-based hook** (`ksu_handle_setresuid`) wired via `security_task_fix_setuid` in the SELinux LSM path (via `manual-security-hooks-v2.0.patch`) or directly from `kernel/sys.c`
- An **execveat-based trampoline** (`ksu_handle_execveat`, `ksu_handle_faccessat`, `ksu_handle_stat`, `ksu_handle_sys_reboot`) registered by the xxKSU runtime rather than by kprobing the syscall table
- **Static keys** (`is_first_zygote`, `is_init_second_stage_not_executed`, `ksu_is_input_hook_enabled`, `ksu_is_init_rc_hook_enabled`) to gate hooks efficiently and with zero overhead when disabled

The consequence:

- **50 → 51**: The kernel-side patches must be rewritten because the "call-site" hook calls in `fs/exec.c`, `fs/read_write.c`, etc. either already exist in xxKSU's hook infrastructure (and would duplicate) or conflict with xxKSU's mechanism. Applying upstream 50 directly on top of xxKSU would create **duplicate or conflicting hooks**.

- **10 → 11**: The KernelSU-side patches must adapt because xxKSU's internal structure (`setuid_hook.c`, `supercall.c`, init sequence, no kprobes, no `ksu_late_loaded`, SID-based zygote detection, different file layout) differs entirely from tiann KernelSU. The upstream 10 patch targets a tiann-style source tree that does not exist in xxKSU.

---

## 2. Upstream 10/50 Architecture

### Upstream 10 — tiann KernelSU Assumptions

The upstream 10 patch (`gki-android14-6.1` branch, `kernel_patches/KernelSU/`) patches **tiann/KernelSU** to integrate SuSFS. Key assumptions:

| Component | Assumption |
|-----------|------------|
| `kernel/Kbuild` | Removes kprobe-based hook objects (`lsm_hook.o`, `syscall_hook_manager.o`, `tp_marker.o`, `symbol_resolver.o`, arch-specific patch_memory.o / syscall_hook.o) — adapts to xxKSU simpler build |
| `kernel/Kconfig` | Removes `KSU_X86_PATCH_SYSCALL_DISPATCHER`; adds `KSU_SUSFS` menu |
| `kernel/core/init.c` | Removes symbol resolver, syscall hook init, lsm hook init; replaces with `susfs_init()`, `ksu_setuid_hook_init()`, `ksu_sucompat_init()` |
| `kernel/feature/kernel_umount.c` | Rewrites `ksu_handle_umount` from `(struct cred*, struct cred*)` to `(uid_t, uid_t)`; removes `is_zygote(old)` credential check; removes `TIF_KSU_UNMOUNTABLE` |
| `kernel/hook/setuid_hook.c` | Full rewrite from simple `ksu_handle_setresuid(old_uid, new_uid)` to SID-based `ksu_handle_setresuid(ruid, euid, suid)` using `susfs_zygote_sid`/`susfs_zygote_next_sid` with dual handlers (`handle_zygote_setresuid`, `handle_zygote_next_setresuid`) |
| `kernel/supercall/supercall.c` | Removes kprobe-based `reboot_kp`; replaces with `ksu_handle_sys_reboot` + `ksu_supercall_reboot_handler` |
| `kernel/supercall/dispatch.c` | Adds SuSFS command dispatch (`SUSFS_MAGIC`); adds `susfs_start_sdcard_monitor_fn()` on boot complete; replaces `ksu_get_task_mark` with `susfs_is_current_proc_no_su()` for `KSU_MARK_GET` |
| `kernel/selinux/selinux.c` | Adds SID helpers + `susfs_set_batch_sid()` |
| `kernel/selinux/rules.c` | Calls `susfs_set_batch_sid()` after policy load |
| `kernel/runtime/ksud*.c` | Replaces kprobe-based hooks with static-key gated call; exports `ksu_handle_vfs_fstat`, `ksu_handle_sys_read` |
| `kernel/feature/sucompat.c` | Rewrites sucompat from PT_REGS-based to filename-struct-based API (`ksu_handle_execveat_sucompat`, `ksu_handle_faccessat`, `ksu_handle_stat`) |
| `kernel/policy/app_profile.c` | Makes `disable_seccomp()` non-static; removes `ksu_late_loaded`; removes `NEED_BACKPORT_COMPAT` logic |

**Critical finding**: Upstream 10 is not a trivial "add SuSFS config" patch. It **restructures tiann/KernelSU's entire hook infrastructure** to the xxKSU pattern (no kprobes, static-key trampolines, SID-based detection). The tiann→xxKSU architectural delta is embedded in upstream 10 itself.

### Upstream 50 — Linux Kernel Assumptions

Upstream 50 adds SuSFS integration throughout the Linux kernel:

| File | Nature of Change |
|------|-----------------|
| `drivers/input/input.c` | Calls `ksu_handle_input_handle_event` under `ksu_is_input_hook_enabled` static key |
| `fs/exec.c` | Calls `ksu_handle_execveat` + `ksu_handle_execveat_sucompat`; adds SuSFS `susfs_is_sdcard_android_data_not_decrypted` guard; `susfs_set_current_proc_no_su()` early exit |
| `fs/open.c` | Calls `ksu_handle_faccessat`; adds `susfs_is_current_proc_no_su()` guards; open_redirect |
| `fs/read_write.c` | Calls `ksu_handle_sys_read` under `ksu_is_init_rc_hook_enabled` static key |
| `fs/stat.c` | Calls `ksu_handle_vfs_fstat` + `ksu_handle_stat`; adds SuSFS kstat spoofing |
| `fs/namei.c` | SuSFS path hiding (open_redirect, sus_path) |
| `fs/namespace.c` | SuSFS mount hiding |
| `fs/proc_namespace.c` | SuSFS mount listing filter |
| `fs/proc/base.c`, `fd.c`, `task_mmu.c` | SuSFS proc hiding |
| `fs/statfs.c`, `readdir.c`, `notify/fdinfo.c` | SuSFS filesystem hiding |
| `fs/proc/bootconfig.c` | SuSFS bootconfig/cmdline spoofing |
| `kernel/reboot.c` | Calls `ksu_handle_sys_reboot` (supercall gate) |
| `kernel/sys.c` | Calls `ksu_handle_setresuid`; adds uname spoofing |
| `kernel/kallsyms.c` | Hides KSU/SuSFS symbols from `/proc/kallsyms` |
| `mm/memory.c` | SuSFS sus_map memory hiding |
| `security/selinux/avc.c` | SuSFS AVC log spoofing |
| `security/selinux/hooks.c` | SuSFS selinux hide (setprocattr hook via LSM) |
| `security/selinux/selinuxfs.c` | SuSFS selinux hide (fake_status, write_context, write_access) |
| `security/selinux/ss/services.c` | (GKI 6.12 only) Additional SuSFS policy changes |

---

## 3. xxKSU Hook Architecture

### xxKSU (backslashxx/KernelSU) — Verified from 11 Patch + Upstream 10

**No kprobes.** xxKSU uses:

```
Linux kernel path
     ↓
security/security.c → ksu_task_fix_setuid() [LSM hook, manual-security-hooks fixture]
     OR
fs/exec.c → ksu_handle_execveat() [manual hook, scope-min fixture OR xxKSU infra]
     OR
drivers/input/input.c → ksu_handle_input_handle_event() [static-key gated]
     ↓
xxKSU kernel/hook/setuid_hook.c → ksu_handle_setresuid_cred()
     ↓
ksu_handle_setresuid() [SID-based zygote detection via susfs_is_sid_equal]
     ↓
SuSFS integration (susfs_set_current_proc_*, ksu_handle_umount, etc.)
```

**Key properties verified from 11 patch**:

1. xxKSU exports `ksu_handle_execveat`, `ksu_handle_faccessat`, `ksu_handle_stat`, `ksu_handle_sys_reboot`, `ksu_handle_setresuid`, `ksu_handle_input_handle_event`, `ksu_handle_sys_read`, `ksu_handle_vfs_fstat` — these are **call targets**, not kprobe handlers.
2. **Call sites in the Linux kernel** (50/51) invoke these via `extern` declarations.
3. xxKSU uses **static keys** (`ksu_is_input_hook_enabled`, `ksu_is_init_rc_hook_enabled`, `is_first_zygote`, `is_init_second_stage_not_executed`) to gate hooks.
4. **Zygote detection** uses SELinux SID comparison (`susfs_is_sid_equal(current_cred(), susfs_zygote_sid)`) — not `is_zygote(old cred)` credential check.
5. **Supercall** routes through `kernel/reboot.c` → `ksu_handle_sys_reboot` → SuSFS CMD dispatch or `ksu_supercall_reboot_handler`. No kprobe on `kernel_reboot`.

**What xxKSU does NOT have** (vs tiann):
- `ksu_late_loaded`
- kprobe-based `reboot_kp`
- kprobe-based `input_event_kp`
- kprobe-based syscall table hooks for read/fstat
- `ksu_syscall_hook_init()`, `ksu_lsm_hook_init()`, `ksu_symbol_resolver_init()`

---

## 4. Inline Hook Inventory

### Traditional KSU Hook Call Sites in Upstream 50

| Hook | Kernel File | Purpose | xxKSU Equivalent | Keep in 51? | Reason |
|------|-------------|---------|------------------|-------------|--------|
| `ksu_handle_execveat` | `fs/exec.c` | Su compat + ksud exec detection | xxKSU exports same function | YES, via scope-min (Sultan) / UNKNOWN (GKI) | Call site needed; method varies by target |
| `ksu_handle_execveat_sucompat` | `fs/exec.c` | Su compatibility redirect | Included in `ksu_handle_execveat` dispatch | YES (bundled) | |
| `ksu_handle_faccessat` | `fs/open.c` | Su access check | xxKSU exports same function | YES, via scope-min (Sultan) / UNKNOWN (GKI) | |
| `ksu_handle_sys_read` | `fs/read_write.c` | Init RC hook (read init.rc) | xxKSU exports same function under `ksu_is_init_rc_hook_enabled` | YES via static key | Direct call in 50 is fine — xxKSU exports this |
| `ksu_handle_vfs_fstat` | `fs/stat.c` | Init RC file size spoof | xxKSU exports same function | YES via static key | |
| `ksu_handle_stat` | `fs/stat.c` | Su stat check (newfstatat) | xxKSU exports same function | CONDITIONAL — under `ksu_su_compat_enabled` guard in 50 | Currently removed in 51 entirely |
| `ksu_handle_sys_reboot` | `kernel/reboot.c` | Supercall gate | xxKSU exports same function | YES, via scope-min (Sultan) / UNKNOWN (GKI) | |
| `ksu_handle_setresuid` | `kernel/sys.c` | Setuid hook (process spawning) | xxKSU exports same function | Wired via LSM (`ksu_task_fix_setuid`) for Sultan; needs explicit call for GKI | |
| `ksu_handle_input_handle_event` | `drivers/input/input.c` | Safe mode volume detection | xxKSU exports same function under `ksu_is_input_hook_enabled` | YES with static key gate | Currently replaced with Sultan stub |

### SELinux Files — No KSU Hooks, Pure SuSFS

| File | Content | Has `ksu_handle_*`? | Exclusion Correct? |
|------|---------|--------------------|--------------------|
| `security/selinux/avc.c` | AVC log spoofing via `susfs_is_avc_log_spoofing_enabled` static key | NO | **INCORRECT** |
| `security/selinux/hooks.c` | LSM `setprocattr` hook for selinux hide | NO | **INCORRECT** |
| `security/selinux/selinuxfs.c` | Fake status page, write_context/write_access intercept | NO | **INCORRECT** |
| `security/selinux/ss/services.c` | (6.12) Policy compute changes | NO | **INCORRECT** |

> [!CAUTION]
> All four SELinux files contain **pure SuSFS functionality** with zero `ksu_handle_*` calls. Their exclusion from 51 silently removes SuSFS AVC log spoofing and selinux hide features entirely.

---

## 5. 10 → 11 Semantic Mapping

| File | Upstream 10 Behavior | 11 Behavior | Classification | Reason |
|------|---------------------|-------------|----------------|--------|
| `kernel/Kbuild` | Removes kprobe objects | Not patched in 11 | `XXKSU_COMPAT` | xxKSU Kbuild already correct |
| `kernel/Kconfig` | Removes `KSU_X86_PATCH_SYSCALL_DISPATCHER`; adds `KSU_SUSFS` menu | Adds same `KSU_SUSFS` menu (different anchor) | `XXKSU_COMPAT` | Different Kconfig structure; anchor `endmenu` vs removed config |
| `kernel/core/init.c` | Major rewrite — removes kprobes, adds `susfs_init()` | Not patched | `XXKSU_COMPAT` | xxKSU entry point is `kernel/ksu.c`, not `kernel/core/init.c` |
| `kernel/ksu.c` | Not in upstream 10 | Adds `#include <linux/susfs.h>` + `susfs_init()` | `XXKSU_COMPAT` | xxKSU init file differs from tiann |
| `kernel/feature/kernel_umount.c` | Changes `ksu_handle_umount` to `(uid_t, uid_t)`; removes `is_zygote(old)` check; removes `TIF_KSU_UNMOUNTABLE`; webview zygote policy | Same changes + `KSU_HAS_PATH_UMOUNT` conditional for `ksu_umount_mnt` + `ksu_is_webview_zygote_umount_enabled()` helper + conditional `try_umount` linkage | `KEEP` + `XXKSU_COMPAT` | Core umount logic kept; compat additions for xxKSU's different `path_umount` API |
| `kernel/hook/setuid_hook.c` | Full SID-based handler rewrite with dual zygote handlers + `ksu_handle_setresuid` | Identical logic wrapped in `#ifdef CONFIG_KSU_SUSFS`; rewrites `ksu_handle_setresuid_cred()` to dispatch to it | `KEEP` + `XXKSU_COMPAT` | Core SID logic identical; xxKSU wrapper/dispatch structure differs |
| `kernel/selinux/rules.c` | Calls `susfs_set_batch_sid()` after policy load | Calls individual `susfs_set_priv_app_sid()` + `susfs_set_init_sid()` + `susfs_set_ksu_sid()` + `susfs_set_zygote_sid()` | `XXKSU_COMPAT` | xxKSU splits batch into individual setters |
| `kernel/selinux/selinux.c` | SID helpers + `susfs_set_batch_sid()` as single entry point | Same helpers + individual setters; functions made fully exported (not inline) | `XXKSU_COMPAT` | API surface difference |
| `kernel/selinux/selinux.h` | Declares `susfs_set_batch_sid()` + domain query functions | Declares individual setters | `XXKSU_COMPAT` | Follows selinux.c API change |
| `kernel/supercall/dispatch.c` | Adds `susfs_start_sdcard_monitor_fn()` on boot complete; `KSU_MARK_GET` returns `susfs_is_current_proc_no_su()` | Same + `objsec.h` include + `susfs_is_boot_completed_triggered` flag; `KSU_MARK_GET` uses `susfs_is_current_proc_umounted()` instead | `KEEP` + `XXKSU_COMPAT` + `UNKNOWN` | Core logic same; `umounted` vs `no_su` semantic difference unverified |
| `kernel/supercall/supercall.c` | Removes kprobe reboot handler; adds `ksu_supercall_reboot_handler`; full SuSFS CMD dispatch in `ksu_handle_sys_reboot` | Identical SuSFS CMD dispatch | `KEEP` | Direct structural match |
| `kernel/downstream/ksu_hostsredirect.h` | Not in upstream 10 | Adds `#ifndef CONFIG_KSU_SUSFS / extern bool ksu_kernel_umount_enabled` guard | `XXKSU_COMPAT` | xxKSU-specific file |
| Various tiann-only files | Various changes (sucompat, ksud, adb_root, app_profile, etc.) | Not present in 11 | `XXKSU_COMPAT` | tiann-only file structure |

### Specific Questions

**1. What upstream 10 behavior remains unchanged in 11?**
`KSU_SUSFS` Kconfig content; `kernel_umount.c` signature change; `setuid_hook.c` SID-based zygote detection logic; full SuSFS CMD dispatch in `supercall.c`; SID initialization after policy load; `susfs_start_sdcard_monitor_fn()` on boot complete.

**2. What behavior is removed?**
Modifications to `kernel/core/init.c`, `kernel/Kbuild`, `kernel/runtime/ksud_integration.c`, `kernel/feature/sucompat.c`, `kernel/feature/adb_root.c`, `kernel/policy/app_profile.c`, `kernel/feature/selinux_hide.c` — all of which exist in tiann but have different paths/structure in xxKSU.

**3. What is rerouted?**
`susfs_init()` call: `core/init.c` → `ksu.c`. SID batch init: `susfs_set_batch_sid()` → individual `susfs_set_*_sid()` calls. `ksu_handle_setresuid_cred()` dispatch: `ksu_handle_umount(new, old)` → `ksu_handle_setresuid(new_uid, new_uid, new_uid)`.

**4. What is xxKSU-specific in 11?**
`ksu_hostsredirect.h` patch; `#ifdef KSU_HAS_PATH_UMOUNT` conditional; `ksu_is_webview_zygote_umount_enabled()` non-static accessor; `manage_mark` using `susfs_is_current_proc_umounted()`.

**5. What exists in 11 because xxKSU source differs from tiann?**
Entire `setuid_hook.c` large block — upstream 10 patches `kernel/hook/setuid_hook.c` which has different function signatures in xxKSU. The `ksu.c` vs `core/init.c` init location. Split `susfs_set_*_sid()` API.

**6. What functionality in 11 compensates for de-inline changes in 51?**
`ksu_handle_setresuid` is defined in 11 (`setuid_hook.c`) and called from `kernel/sys.c` in 51 (or wired via LSM `ksu_task_fix_setuid`). `ksu_handle_sys_reboot` is defined in 11 (`supercall/dispatch.c`) and called from `kernel/reboot.c` in 51. All `ksu_handle_*` trampolines are defined in xxKSU (via 11) and called from the Linux kernel (via 51).

**7. What new behavior exists in 11 not from upstream 10?**
`manage_mark` → `susfs_is_current_proc_umounted()` (upstream uses `susfs_is_current_proc_no_su()`). `susfs_is_boot_completed_triggered` flag.

**8. Is that additional behavior necessary?**
`susfs_is_current_proc_umounted()` vs `susfs_is_current_proc_no_su()` for `KSU_MARK_GET`: **semantic difference** — the upstream uses "no su" flag while 11 uses "umounted" flag. Functional impact unclear without userspace analysis.

**9. Are there hardcoded transformations that may already be stale?**
`susfs_set_*_sid()` individual callers in `rules.c` — if upstream adds new SIDs to `susfs_set_batch_sid()`, the 11 generator silently misses them. The full SuSFS CMD dispatch block in `supercall.c` is hardcoded — new upstream CMDs would be silently missed.

---

## 6. 50 → 51 Semantic Mapping

### GKI Android 14 / Linux 6.1

**Files fully excluded from 51 (present in upstream 50, absent in 51):**

| File | Upstream 50 Content | Exclusion Correct? | Risk |
|------|--------------------|--------------------|------|
| `fs/exec.c` | MIXED: `ksu_handle_execveat` call + SuSFS `susfs_is_sdcard_android_data_not_decrypted` guard + `susfs_set_current_proc_no_su()` early exit | **PARTIAL** — KSU call removed OK, but SuSFS guards also excluded | HIGH — SuSFS exec guards lost |
| `fs/open.c` | MIXED: `ksu_handle_faccessat` call + SuSFS `susfs_is_current_proc_no_su()` guards + open_redirect checks | **PARTIAL** — same issue | HIGH — SuSFS open guards lost |
| `fs/read_write.c` | `ksu_is_init_rc_hook_enabled` gate + `ksu_handle_sys_read` call | **CORRECT** for Sultan (scope-min provides this); **UNCERTAIN** for GKI | MEDIUM |
| `kernel/reboot.c` | `ksu_handle_sys_reboot` call | **CORRECT** for Sultan (scope-min adds it back); **UNCERTAIN** for GKI | MEDIUM |
| `security/selinux/avc.c` | **PURE SuSFS** — AVC log spoofing only, NO `ksu_handle_*` | **INCORRECT** | HIGH — AVC log spoofing broken |
| `security/selinux/hooks.c` | **PURE SuSFS** — selinux hide setprocattr hook | **INCORRECT** | HIGH — selinux hide broken |
| `security/selinux/selinuxfs.c` | **PURE SuSFS** — fake_status + write_context + write_access | **INCORRECT** | HIGH — selinux hide broken |

**Files kept in 51 with analysis:**

| File | 50 Added Lines | 51 Added Lines | Classification | Notes |
|------|--------------|--------------|----------------|-------|
| `drivers/input/input.c` | 10 | 2 | `UNKNOWN/SULTAN_COMPAT` | Real input hook replaced with Sultan stub; safe-mode detection broken |
| `fs/Makefile` | 2 | 2 | `KEEP` | Identical |
| `fs/namei.c` | 233 | 240 | `KEEP` + minor `KERNEL_COMPAT` | 7 extra lines in 51 |
| `fs/namespace.c` | 246 | 247 | `KEEP` + `KERNEL_COMPAT` | `trace/hooks/blk.h` anchor injection for GKI 6.1 |
| `fs/notify/fdinfo.c` | 58 | 58 | `KEEP` | Identical |
| `fs/proc/base.c` | 24 | 24 | `KEEP` | Identical |
| `fs/proc/bootconfig.c` | 13 | 43 | `KEEP` + `SUSFS_EXTENSION` | 30 extra lines — extended bootconfig support |
| `fs/proc/fd.c` | 78 | 82 | `KEEP` + `KERNEL_COMPAT` | 4 extra lines: compile guards for `SUS_MOUNT` and `OPEN_REDIRECT` |
| `fs/proc/task_mmu.c` | 70 | 76 | `KEEP` + minor | 6 extra lines |
| `fs/proc_namespace.c` | 178 | 178 | `KEEP` | Identical |
| `fs/readdir.c` | 111 | 197 | `KEEP` + `SUSFS_EXTENSION` | 86 extra lines — significant extension (origin unclear) |
| `fs/stat.c` | 62 | 33 | `DEINLINE` (correct) | 51 removes `ksu_handle_vfs_fstat`, `ksu_handle_stat`, `ksu_su_compat_enabled` check; keeps kstat spoofing |
| `fs/statfs.c` | 45 | 45 | `KEEP` | Identical |
| `kernel/kallsyms.c` | 31 | 31 | `KEEP` | Identical |
| `kernel/sys.c` | 16 | 10 | `DEINLINE` (correct) | 51 removes `ksu_handle_setresuid` call; keeps uname spoofing |
| `mm/memory.c` | 8 | 8 | `KEEP` | Identical |

**New files in 51 not in upstream 50:**

| File | Source | Classification |
|------|--------|----------------|
| `fs/susfs.c` | `SULTAN_EXTRA_CHUNKS` hardcoded | `SUSFS_EXTENSION` — try_umount implementation |
| `include/linux/susfs.h` | `SULTAN_EXTRA_CHUNKS` hardcoded | `SUSFS_EXTENSION` — try_umount declarations |

### GKI Android 16 / Linux 6.12

Same file exclusions as GKI 6.1, plus `security/selinux/ss/services.c` also excluded (pure SuSFS, no KSU hooks). No scope-min fixture applied for GKI targets — the call sites for `ksu_handle_execveat` etc. are therefore entirely absent in GKI 6.12.

### Sultan Android 14 / Linux 6.1

Same upstream 50 branch as GKI 6.1; same exclusion list. Sultan additionally receives:
- `manual-security-hooks-v2.0.patch` — adds `ksu_task_fix_setuid` + `ksu_hide_setprocattr` + `ksu_bprm_check` etc. to `security/security.c`
- `scope-min-manual-hooks-v2.3.patch` — adds `ksu_handle_execveat` in `fs/exec.c`, `ksu_handle_faccessat` in `fs/open.c`, `ksu_handle_stat` in `fs/stat.c`, `ksu_handle_sys_reboot` in `kernel/reboot.c`

Sultan gets the Sultan extra chunks (`fs/susfs.c` try_umount, `include/linux/susfs.h` try_umount, `drivers/input/input.c` stub).

---

## 7. Mixed Hunk Inventory

### 1. `fs/exec.c` — Critical Mixed Hunk (INCORRECTLY Excluded)

**KEEP** (pure SuSFS):
```c
#include <linux/susfs_def.h>
extern struct static_key_true susfs_is_sdcard_android_data_not_decrypted;
if (likely(susfs_is_current_proc_no_su()))
    goto orig_flow;
if (static_branch_unlikely(&susfs_is_sdcard_android_data_not_decrypted))
    // sdcard decrypt handling
```
**REMOVE** (KSU hook — provided by scope-min or xxKSU infra):
```c
ksu_handle_execveat(&fd, &filename, &argv, &envp, &flags);
ksu_handle_execveat_sucompat(&fd, &filename, &argv, &envp, &flags);
```
**WHY**: The `ksu_handle_execveat` call is provided by scope-min (Sultan) or the xxKSU hook infrastructure. The SuSFS `susfs_is_current_proc_no_su` guards and sdcard decrypt guard are **pure SuSFS** and must remain. Currently the **entire file is excluded**, losing all SuSFS guards.

### 2. `fs/open.c` — Critical Mixed Hunk (INCORRECTLY Excluded)

**KEEP** (pure SuSFS):
```c
#include <linux/susfs_def.h>
if (likely(susfs_is_current_proc_no_su()))
    goto orig_flow;
// open_redirect path checks
// susfs open path guards
```
**REMOVE** (KSU hook):
```c
ksu_handle_faccessat(&dfd, &fname, &mode, NULL);
```
**WHY**: Same pattern. Currently entirely excluded.

### 3. `fs/stat.c` — Correctly Handled Mixed Hunk ✓

**KEEP** (correctly kept in 51):
```c
susfs_sus_kstat_spoof_generic_fillattr(inode, stat);
susfs_get_non_sus_mnt_id_from_mnt(real_mount(path.mnt));
// mnt_id spoofing block
```
**REMOVE** (correctly removed in 51):
```c
ksu_handle_vfs_fstat(fd, &stat.size);
ksu_handle_stat(&dfd, &filename, &flags);
// ksu_su_compat_enabled guard
```
**WHY**: ✓ This is the only mixed hunk handled correctly in the current implementation.

### 4. `kernel/sys.c` — Correctly Handled Mixed Hunk ✓

**KEEP** (correctly kept in 51): uname spoofing, `susfs_spoof_uname`.  
**REMOVE** (correctly removed in 51): `ksu_handle_setresuid` call.  
**WHY**: ✓ Correctly handled.

### 5. `security/selinux/avc.c` — Pure SuSFS, Incorrectly Excluded

**KEEP** (everything — no KSU hooks at all):
```c
susfs_is_avc_log_spoofing_enabled  // static key
susfs_ksu_sid / susfs_priv_app_sid // sid check
// AVC log spoofing logic
```
**REMOVE**: Nothing.  
**WHY**: Excluded by mistake. No `ksu_handle_*` present.

### 6. `security/selinux/hooks.c` — Pure SuSFS LSM Hook, Incorrectly Excluded

**KEEP** (everything):
```c
my_setprocattr() // selinux context spoofer for hide
LSM_HOOK_INIT(setprocattr, my_setprocattr)
fake_state usage
```
**REMOVE**: Nothing.  
**WHY**: Excluded by mistake. Implements selinux hide via LSM.

### 7. `security/selinux/selinuxfs.c` — Pure SuSFS, Incorrectly Excluded

**KEEP** (everything):
```c
my_sel_open_handle_status() // fake SELinux status page for apps
my_write_context()           // hide SELinux context
my_write_access()            // hide SELinux access decisions
```
**REMOVE**: Nothing.  
**WHY**: Excluded by mistake. Core selinux hide functionality.

---

## 8. 11 / 51 Responsibility Boundary

### 11 Responsibilities (xxKSU/KernelSU side)

11 owns:

1. **`KSU_SUSFS` Kconfig menu** — feature toggles for all SuSFS subsystems
2. **`susfs_init()` invocation** — boot-time SuSFS initialization
3. **SID initialization** — `susfs_set_zygote_sid()`, `susfs_set_ksu_sid()`, `susfs_set_init_sid()`, `susfs_set_priv_app_sid()` after SELinux policy load
4. **`ksu_handle_setresuid` implementation** — the full SID-based zygote detection + SuSFS state machine in `setuid_hook.c`
5. **`ksu_handle_sys_reboot` implementation** — SuSFS `CMD_SUSFS_*` dispatch via `SUSFS_MAGIC`
6. **`ksu_handle_umount` export** — accessible to SuSFS zygote handler
7. **`try_umount` export** — non-static for SuSFS `TRY_UMOUNT` feature
8. **`ksu_kernel_umount_enabled` export** — non-static for SuSFS
9. **`disable_seccomp` export** — for SuSFS code path
10. **`ksu_handle_extra_susfs_work` helper** — deferred work scheduling
11. **`ksu_is_webview_zygote_umount_enabled()` accessor** — webview policy
12. **SID equality helpers** — `susfs_is_sid_equal`, `susfs_get_sid_from_name`, etc. in `selinux.c/h`
13. **`susfs_start_sdcard_monitor_fn()` trigger** — on boot_complete
14. **`manage_mark` override** — `KSU_MARK_GET` returns SuSFS proc state

**11 does NOT own**: SuSFS core kernel functionality (fs/, mm/ Linux files), SuSFS feature implementations, the Linux call sites invoking `ksu_handle_*`.

### 51 Responsibilities (Linux kernel side)

51 owns:

1. **`ksu_handle_*` call sites** in Linux kernel files (exec, open, stat, reboot, sys, read_write, input)
2. **SuSFS path hiding** — `fs/namei.c`
3. **SuSFS mount hiding** — `fs/namespace.c`, `fs/proc_namespace.c`
4. **SuSFS proc hiding** — `fs/proc/base.c`, `fd.c`, `task_mmu.c`, `readdir.c`
5. **SuSFS stat spoofing** — `fs/stat.c` (kstat), `fs/statfs.c`
6. **SuSFS bootconfig/cmdline spoof** — `fs/proc/bootconfig.c`
7. **SuSFS memory hiding** — `mm/memory.c`
8. **SuSFS fdinfo filter** — `fs/notify/fdinfo.c`
9. **SuSFS kallsyms hide** — `kernel/kallsyms.c`
10. **SuSFS uname spoof** — `kernel/sys.c` (uname part only)
11. **Kernel build integration** — `fs/Makefile`, `fs/susfs.c`, `include/linux/susfs.h`
12. **SHOULD INCLUDE** (currently excluded): `security/selinux/avc.c`, `security/selinux/hooks.c`, `security/selinux/selinuxfs.c`, SuSFS portions of `fs/exec.c`, `fs/open.c`

---

## 9. Current 11/51 Correctness Audit

### 11 Patch

| Aspect | Assessment |
|--------|-----------|
| `KSU_SUSFS` Kconfig content | ✓ Correct |
| `kernel_umount.c` changes | ✓ Mostly correct; `KSU_HAS_PATH_UMOUNT` conditional is valid xxKSU compat |
| `setuid_hook.c` SuSFS block | ✓ Correct in substance |
| `ksu.c` init call | ✓ Correct — maps to `core/init.c` in upstream 10 |
| `selinux/rules.c` — split SID setters | ⚠️ Differs from upstream (batch vs individual) — works but diverges if upstream adds SIDs |
| `dispatch.c` `manage_mark` | ⚠️ Uses `susfs_is_current_proc_umounted()` vs upstream 10's `susfs_is_current_proc_no_su()` — semantic difference |
| `dispatch.c` `susfs_is_boot_completed_triggered` | ⚠️ Extra flag not in upstream 10 — purpose UNKNOWN |
| `ksu_handle_setresuid_cred` non-SUSFS path | ⚠️ Calls `ksu_handle_umount(old_uid, new_uid)` — may be redundant; confirm compilation |

### 51 Patches

| Aspect | Assessment |
|--------|-----------|
| `fs/exec.c`, `fs/open.c` excluded | ❌ WRONG — SuSFS portions lost |
| `fs/read_write.c`, `kernel/reboot.c` excluded | ✓ Correct for Sultan (scope-min provides); ⚠️ Uncertain for GKI |
| SELinux files excluded | ❌ WRONG — pure SuSFS features removed |
| `drivers/input/input.c` replaced with stub | ⚠️ UNCERTAIN — real safe-mode detection broken |
| `fs/stat.c` mixed hunk | ✓ Correct |
| `kernel/sys.c` mixed hunk | ✓ Correct |
| `fs/namespace.c` GKI 6.1 anchor | ✓ KERNEL_COMPAT correct |
| `SULTAN_EXTRA_CHUNKS` — `fs/susfs.c` | ⚠️ Hardcoded — stale when upstream susfs.c changes |
| `SULTAN_EXTRA_CHUNKS` — `include/linux/susfs.h` | ⚠️ Hardcoded — same risk |
| `fs/readdir.c` 86 extra lines | ⚠️ Origin unclear |
| GKI target missing `ksu_handle_execveat` call site | ❌ Functional gap — no scope-min for GKI |

---

## 10. Current Python Generator Audit

### `transform_10_to_11.py`

**Fundamental problem**: The script accepts `--input` (upstream 10 patch) but **completely ignores it**. It clones xxKSU from GitHub and applies hardcoded string replacements.

**Classification**: **Hardcoded 11 synthesizer**, not a 10→11 transformer.

| Python Rule | Intended Semantic Rule | Correct? | Risk |
|-------------|----------------------|----------|------|
| `--input` arg silently ignored | Should consume upstream 10 | **NO** | Critical — generates same 11 regardless of upstream changes |
| `kconfig_path`: `replace('endmenu', ...)` | Insert SUSFS menu before final `endmenu` | **PARTIAL** | Replaces EVERY `endmenu` occurrence; not anchored to final `endmenu` |
| Exact string replacements, no success check | Should fail if anchor missing | **NO** | Silent failure if xxKSU refactors any anchor string |
| `dispatch.c` manage_mark uses `susfs_is_current_proc_umounted()` | Match upstream `susfs_is_current_proc_no_su()` | **NO** | Semantic difference vs upstream 10 |
| Full SuSFS CMD dispatch hardcoded in `supercall.c` | Should derive from upstream 10 | **STALE RISK** | If upstream adds new CMDs, silently missed |
| Individual `susfs_set_*_sid()` calls in `rules.c` | Should match upstream `susfs_set_batch_sid()` | **PARTIAL** | Diverges if upstream adds new SIDs |
| No provenance tracking | Should record upstream commit | **NO** | Non-reproducible |

### `deinline_50_to_51.py`

| Python Rule | Intended Semantic Rule | Correct? | Risk |
|-------------|----------------------|----------|------|
| `excluded_files` list (7–8 files) | Remove files with KSU inline hooks | **PARTIAL** | Over-excludes: SELinux files have NO KSU hooks |
| `is_ksu_hook` regex: `ksu_handle_\|ksu_is_input_hook\|ksu_is_init_rc_hook` | Detect KSU hook hunks | **PARTIAL** | Correct detection but drops entire hunks even if mixed |
| `is_ksu_hook` secondary: `#ifdef CONFIG_KSU_SUSFS` without `#include`, no `CONFIG_KSU_SUSFS_`, no `obj-$()`, no `susfs_is_sus_su_ready` | Detect "bare" integration hunks | **NO** | Dangerous heuristic — may drop pure SuSFS hunks |
| `SULTAN_EXTRA_CHUNKS['drivers/input/input.c']` stub | Sultan input compat | **UNKNOWN** | Replaces real hook with stub; breaks safe-mode |
| `SULTAN_EXTRA_CHUNKS['fs/susfs.c']`, `['include/linux/susfs.h']` | Add try_umount | **CONDITIONALLY YES** | Hardcoded — stale when upstream changes |
| `fs/namespace.c` `trace/hooks/blk.h` injection | GKI 6.1 kernel compat | **YES** | KERNEL_COMPAT, correct |
| `fs/proc/fd.c` compile guards | Add missing guards | **YES** | Reasonable |
| `fix_hunk_line_counts()` | Recalculate hunk headers | **YES** | Works |
| No semantic validation | Should verify required features present | **NO** | AVC log spoofing silently absent |
| No fail-closed on unknown hunks | Should stop on unknown | **NO** | Unknown hunks silently kept or dropped |
| Static git hashes in `SULTAN_EXTRA_CHUNKS` | Cosmetic only | N/A | Visual inconsistency |

---

## 11. Architecture Policy

### DEINLINE — Remove from 51

Remove a call site from Linux kernel files only if the `ksu_handle_*` function call:
1. Is provided by an alternative mechanism (scope-min fixture, LSM hook, or xxKSU direct hook infra), AND
2. Would be a duplicate if kept

### KEEP — Retain in 51

Keep any line/block that:
1. Calls a `susfs_*` function (SuSFS feature)
2. References a SuSFS static key
3. Contains `#ifdef CONFIG_KSU_SUSFS_*` conditional SuSFS logic
4. Calls `ksu_handle_*` under a static key gate (legitimate call that xxKSU handles)
5. Is in a SELinux file (all SELinux upstream 50 changes are SuSFS functionality)

### MIXED — Split, Never Drop Entire Hunk

When a hunk contains BOTH a `ksu_handle_*` call AND SuSFS functionality:
1. Keep the SuSFS lines
2. Remove only the `ksu_handle_*` call line (and its extern declaration if any)
3. Never drop the entire hunk

### Files Requiring Per-Target Decision

- `fs/exec.c`, `fs/open.c`: Split out `ksu_handle_*` calls; keep SuSFS guards
- `fs/read_write.c`: Keep `ksu_handle_sys_read` call (it IS a legitimate call under static key); or remove if target provides it via scope-min
- `kernel/reboot.c`: Keep `ksu_handle_sys_reboot` call; or remove if provided by scope-min
- `security/selinux/*.c`: ALWAYS KEEP — no KSU hooks present

---

## 12. Version Compatibility Rules

| Type | Description | Target | Current Handling |
|------|-------------|--------|-----------------|
| `KERNEL_COMPAT` | `trace/hooks/blk.h` anchor in `fs/namespace.c` | GKI 6.1 + Sultan | ✓ regex in deinline script |
| `KERNEL_COMPAT` | `struct mnt_idmap *idmap` in stat/getattr | GKI 6.12 | ✓ upstream 50 branch differs |
| `KERNEL_COMPAT` | `security/selinux/ss/services.c` (extra 6.12 file) | GKI 6.12 | ❌ excluded |
| `SULTAN_COMPAT` | Sultan symbol: `ksu_input_hook_key_false` vs `ksu_is_input_hook_enabled` | Sultan 6.1 | ⚠️ stub hack |
| `SULTAN_COMPAT` | `try_umount` in `fs/susfs.c` | Sultan 6.1 | ⚠️ hardcoded chunk |
| `SULTAN_COMPAT` | `susfs_run_sus_path_loop` non-static | Sultan 6.1 | ⚠️ hardcoded |
| `XXKSU_COMPAT` | `ksu_handle_setresuid_cred` dispatch | All | ✓ handled in 11 |
| `XXKSU_COMPAT` | No kprobe supercall | All | ✓ handled in 11 |
| `VERSION_COMPAT` | `ksu_handle_execveat` call site for GKI targets | GKI 6.1, 6.12 | ❌ absent — functional gap |

---

## 13. Unknown / Uncertain Areas

| Area | Uncertainty |
|------|-------------|
| `susfs_is_current_proc_umounted()` vs `no_su` in `manage_mark` | Which is semantically correct? Upstream 10 uses `no_su`; 11 uses `umounted`. |
| `susfs_is_boot_completed_triggered` flag | Purpose? Not in upstream 10; not visibly used in current 11. |
| `drivers/input/input.c` stub | Does Sultan wire `ksu_input_hook_key_false` elsewhere? Is safe-mode detection fully broken? |
| GKI targets missing `ksu_handle_execveat` call site | No scope-min applied for GKI. Where does the execveat hook come from? Is su compat broken on GKI? |
| SELinux file exclusion — intentional? | README says "8 inline system call files stripped" but SELinux files have no inline hooks. Was this intentional (e.g., selinux hide moved elsewhere) or a bug? |
| `fs/readdir.c` 86 extra lines in 51 | Origin — are these from a different SuSFS branch? Backport? |
| `fs/proc/bootconfig.c` 30 extra lines in 51 | Same question. |
| `ksu_handle_setresuid_cred` non-SUSFS path | Does `ksu_handle_umount(old_uid, new_uid)` still compile? The signature was changed. |
| Sultan scope-min applied with `-l` (ignore whitespace) in workflow | Does this mask alignment issues in applied hooks? |

---

## 14. Proposed V2 Generator Architecture

```
UPSTREAM TRUTH (10 or 50, per branch)
         ↓
    PATCH PARSER (structured hunk objects)
         ↓
    HUNK CLASSIFIER
    ┌──────────────────────────────────────┐
    │ KEEP              → pass through     │
    │ DEINLINE          → drop hook call   │
    │ MIXED             → split hunk       │
    │ REROUTE_TO_XXKSU  → verify xxKSU owns│
    │ SUSFS_EXTENSION   → add extra chunk  │
    │ VERSION_ADAPT     → apply adapter    │
    │ UNKNOWN           → FAIL CLOSED      │
    └──────────────────────────────────────┘
         ↓
    MIXED HUNK SPLITTER
    (surgical line-level KSU/SuSFS separation)
         ↓
    TARGET ADAPTER (per kernel version)
         ↓
    SEMANTIC VALIDATOR (6 layers)
    Layer 1: Patch syntax valid
    Layer 2: Clean apply to target tree
    Layer 3: All upstream hunks accounted for
    Layer 4: No forbidden hooks in output
    Layer 5: All required SuSFS features present
    Layer 6: Build/compile check (where practical)
         ↓
    git format-patch → GENERATED 11 or 51
```

### Key Design Principles for V2

1. **Upstream is always the source of truth** — start from current upstream 10/50, never from previous generated patches
2. **Fail closed** — any unclassifiable hunk stops generation with structured diagnostic
3. **Mixed hunk awareness** — never drop an entire hunk because of one `ksu_handle_*` call
4. **Separate architecture policy from version compat** — `policy/` modules are target-agnostic; `adapters/` handle target specifics
5. **Provenance tracking** — record SuSFS commit + xxKSU commit + kernel commit + policy version in every generated patch header

### Proposed Module Structure

```
patch-generator/
├── engine/
│   ├── patch_parser.py          # Parse unified diff → structured hunk objects
│   ├── hunk_classifier.py       # Classify: KEEP/DEINLINE/MIXED/etc.
│   ├── mixed_hunk_splitter.py   # Line-level KSU/SuSFS boundary split
│   ├── hunk_counter.py          # Recalculate @@ line counts
│   └── patch_writer.py          # Emit valid unified diff
│
├── policy/
│   ├── deinline_rules.py        # Which ksu_handle_* calls to remove
│   ├── keep_rules.py            # What susfs_* calls must be retained
│   ├── mixed_rules.py           # Split criteria for mixed hunks
│   ├── required_features.py     # Required SuSFS feature inventory
│   └── forbidden_hooks.py       # Hook patterns that must be absent post-transform
│
├── adapters/
│   ├── base.py                  # Adapter interface
│   ├── gki_android14_6_1.py     # GKI 6.1 (trace/hooks/blk.h, fd.c guards)
│   ├── gki_android16_6_12.py    # GKI 6.12 (mnt_idmap, ss/services.c)
│   ├── sultan_android14_6_1.py  # Sultan (try_umount, input, fixtures)
│   └── xxksu.py                 # xxKSU source adapter for 11 generation
│
├── validators/
│   ├── semantic_coverage.py     # Every upstream hunk has known outcome
│   ├── feature_presence.py      # All required SuSFS features present in output
│   ├── hook_absence.py          # No forbidden inline hooks remain
│   └── patch_integrity.py       # Syntactically valid patch
│
├── generators/
│   ├── generate_11.py           # 10 → 11 (reads upstream 10, applies xxKSU adapter)
│   └── generate_51.py           # 50 → 51 per target
│
└── tests/
    ├── fixtures/                # Golden snapshots per target
    ├── test_classifier.py       # Hunk classification unit tests
    ├── test_splitter.py         # Mixed hunk splitting tests
    └── test_integration.py      # Full pipeline regression tests
```

---

## 15. Migration Plan

### Phase 1 — Baseline Capture (Now)
1. Record current 11 and 51 patches as **golden snapshots** with full provenance (SuSFS commit, xxKSU commit, kernel commit)
2. Audit which SuSFS features are currently functional vs. broken (especially SELinux hide, AVC log spoofing — currently excluded)
3. Confirm Sultan fixture interaction (verify scope-min provides missing call sites)
4. Document GKI functional gap (execveat call site absent for GKI targets)

### Phase 2 — Build V2 Core
1. Implement hunk parser with full test coverage
2. Write policy rules validated against upstream 50 → 51 golden pairs
3. Implement mixed hunk splitter (key new capability vs. current implementation)
4. Build per-target adapters

### Phase 3 — Parallel Verification
1. Run V2 on same inputs → compare to golden snapshots
2. Document every intentional difference from golden (including bug fixes — SELinux, exec.c, open.c)
3. Get explicit approval for each behavioral change

### Phase 4 — Canary Deployment
1. Enable V2 for Sultan in CI (has most complete fixture set)
2. Perform actual kernel build to verify compilation
3. Verify SELinux hide, AVC log spoofing, safe-mode detection at runtime

### Phase 5 — Full Migration
1. Enable V2 for all targets
2. Archive old generators with deprecation
3. Enforce provenance headers in all generated patches

---

## 16. Confidence Report

| Area | Confidence | Evidence | Remaining Questions |
|------|------------|----------|---------------------|
| 11 semantic understanding | **HIGH** | Upstream 10 (3034 lines) fully read; 11 (780 lines) fully read; direct line-by-line comparison; key semantic differences identified | Minor: `susfs_is_current_proc_umounted` vs `no_su` intent in `manage_mark` |
| 51 semantic understanding | **MEDIUM** | Upstream 50 for all 3 targets read; 51 patches (all 3) analyzed; file exclusion list verified; key file comparisons done via Python analysis | Need to verify: where does GKI get execveat call site? Confirm SELinux exclusion was unintentional |
| de-inline boundary | **HIGH** | Clear from analysis: SELinux files wrongly excluded (0 `ksu_handle_*`); exec.c/open.c wrongly excluded (mixed); stat.c/sys.c correctly handled | Confirm: intent behind SELinux exclusion |
| xxKSU hook ownership | **HIGH** | xxKSU hook architecture traced through 11 patch, upstream 10, fixture patches, supercall structure | Confirm: GKI execveat wiring mechanism |
| SuSFS feature preservation | **LOW** | Confirmed: AVC log spoofing, selinux hide, setprocattr hook, exec.c/open.c SuSFS guards all absent from current 51 | Need build + runtime verification of impact |
| Current generator correctness | **HIGH** | `transform_10_to_11.py` confirmed as hardcoded synthesizer with no upstream 10 consumption; `deinline_50_to_51.py` confirmed over-excludes SELinux files and has mixed-hunk blindness | Full anchor fragility inventory needed |
| proposed V2 model | **MEDIUM** | Architecture is well-grounded in analysis findings; module boundaries are clear | Policy rules need validation against all upstream 50 branches (not just GKI 6.1); adapter complexity for Sultan fixtures to be worked out |

---

**End of Phase 1 Analysis.**  
**No repository files were modified.**  
**Awaiting approval before proceeding to any implementation.**
