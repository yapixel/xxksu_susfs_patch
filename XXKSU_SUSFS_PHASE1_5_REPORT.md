# xxKSU + SuSFS Phase 1.5 Verification Report

**Scope:** analysis only. No generator, patch, workflow, kernel, xxKSU, or SuSFS source was modified.

**Evidence cutoff:** 2026-08-29 (Asia/Singapore). Remote branch heads and repositories are identified below so later movement can be detected.

## Executive conclusion

Phase 1's contradiction is resolved by separating a handler definition from the mechanism that reaches it.

The validated architecture has two transport modes:

1. **Manual mode:** target fixtures insert Linux source call sites. `scope-min-manual-hooks-v2.3.patch` owns exec, access, stat, fstat-return, and reboot call sites; `manual-security-hooks-v2.0.patch` owns security call sites that reach setuid and init-RC behavior.
2. **LSM/BL mode:** xxKSU owns runtime transport. On Linux 6.1 it hijacks existing LSM hook-list entries; on Linux 6.12 it patches ARM64 call sites to existing security functions. With `CONFIG_KSU_HACK_ARM64_BRANCH_LINK=y`, xxKSU also patches exec/access/stat call sites and temporarily uses syscall-table replacements for reboot/read/fstat-return. Its input safe-mode path is an independently registered input handler.

The official 50 call sites target the interfaces created by official 10 for a different KernelSU source tree. Several are ABI-incompatible with actual xxKSU; several expected handlers/static keys do not exist in xxKSU at all; and the official reboot return contract is incompatible with xxKSU's reboot handler. Therefore the correct transformation is not “remove every `ksu_handle_*`” and not “keep every `ksu_handle_*`.” It is:

> Remove or split official-50 KernelSU transport only after a target manifest proves one compatible manual-fixture or xxKSU-runtime owner for the final path. Keep independent SuSFS behavior. Fail if no owner is selected and proven.

The known-good GKI workflows do prove alternate callers: their manual variants apply both fixtures, and their LSM variants explicitly enable xxKSU branch-link/LSM transport. The current repository's GKI generation workflow does neither and performs no build. Thus current GKI 51 output alone has a **FUNCTIONAL GAP under default built-in xxKSU configuration** for exec/access/stat/reboot, while the known-good final GKI build combinations do not. This is a workflow/target-contract gap, not proof that the known-good 51 de-inline policy is wrong.

The Phase 1 assertion that excluding all four SELinux files necessarily loses pure SuSFS behavior is also corrected. Actual xxKSU already implements the same architectural domains—AVC SID spoofing, `setprocattr` hiding, fake status, and context/access transaction hiding—through `kernel/feature/selinux_hide.c`, its LSM transport, and `slow_avc_audit` call-site patching. The implementation is intentionally lighter than official 50's backup-policy model, so parity is MEDIUM confidence, but disappearance of the original SELinux files is not by itself a functional gap.

V2 implementation is **not safe to begin yet**. The de-inline rule is now sufficiently clear, but this repository still lacks an authoritative target manifest selecting manual versus LSM/BL transport for each GKI output and validating the resulting final source/configuration.

---

## 1. Corrected hook terminology

| Term | Exact meaning in this report | Evidence/example |
|---|---|---|
| Linux source call site / manual source hook | A direct call inserted into ordinary Linux source. | Fixture `fs/exec.c` calls `ksu_handle_execveat`; fixture `kernel/reboot.c` calls `ksu_handle_sys_reboot`. |
| Direct `ksu_handle_*()` call | A C call. It says nothing by itself about how the caller was installed. | Official 50, a fixture, a syscall wrapper, or an ARM64 branch-link wrapper may all make such a call. |
| Static-key-gated call site | A source call preceded by a jump-label/static-key test. | Official 50 input/read/fstat calls use `ksu_is_*` keys created by official 10. |
| LSM/security path | A path through an existing `security_*` function and LSM hook. | `security_task_fix_setuid` → xxKSU `ksu_task_fix_setuid` → `ksu_handle_setresuid_cred`. |
| Kprobe/kretprobe path | Runtime registration of a probe on a symbol. | xxKSU optional `kp_ksud.c` registers reboot and fstat probes when `CONFIG_KSU_KPROBES_KSUD=y`. |
| Syscall-table modification | Runtime replacement of a syscall-table entry. | xxKSU optional `syscall_table_hook_arm64.c`. |
| ARM64 branch-link patch | Runtime replacement of a `b`/`bl` call instruction in kernel text. | xxKSU `branch_link_hook_arm64.c` and 6.12 `lsm_hooks_static.c`. |
| Runtime registration | Registering a kernel subsystem consumer without editing its event call site. | xxKSU safe mode calls `input_register_handler(&vol_detector_handler)`. |
| Fixture-provided manual hook | A manual source call supplied by a repository fixture rather than by 51. | `scope-min-manual-hooks-v2.3.patch`, `manual-security-hooks-v2.0.patch`. |
| Handler implementation | The called function and behavior; not proof of a caller. | `ksu_handle_sys_reboot` in xxKSU `kernel/supercall/supercall.c`. |

The Phase 1 phrase “kprobe-based inline hooks physically patch the syscall table to inject calls into `fs/*.c`” is rejected. Those are three different mechanisms: kprobe registration, syscall-table replacement, and source call-site insertion.

---

## 2. Evidence ledger and priority

### E1 — actual target kernel sources

| Target | Identity inspected | Result for required clean paths |
|---|---|---|
| Sultan Android 14 / 6.1 | `kerneltoast/android_kernel_google_tensynos`, branch `16.0.0-sultan`, commit `af5c65b9547a9f33c5f566430d0434aecab5a8b5` | Raw source inspection of all required paths found no `ksu_` or `susfs_` references. |
| GKI Android 14 / 6.1 | Release asset `kernel-pantah-15260412.tar.xz` (1,533,017,308 bytes) | The actual archive was streamed without extraction; all required `common/ack` paths contained no `ksu_` or `susfs_` references. |
| GKI Android 16 / 6.12 | Release asset `common-android16-6.12-2025-06_r58.tar.gz` (254,113,656 bytes) | The actual archive was streamed without extraction; all required paths contained no `ksu_` or `susfs_` references. |

For every investigated handler, every clean target therefore has **NO PRE-EXISTING CALL SITE**.

### E2 — actual xxKSU source

`backslashxx/KernelSU` master was `0b138d6a9cfe4dc163aa05c21b1e6a14ff868230` at the evidence cutoff.

Primary files:

- [`kernel/Kconfig`](https://github.com/backslashxx/KernelSU/blob/0b138d6a9cfe4dc163aa05c21b1e6a14ff868230/kernel/Kconfig)
- [`kernel/ksu.c`](https://github.com/backslashxx/KernelSU/blob/0b138d6a9cfe4dc163aa05c21b1e6a14ff868230/kernel/ksu.c)
- [`kernel/feature/sucompat.c`](https://github.com/backslashxx/KernelSU/blob/0b138d6a9cfe4dc163aa05c21b1e6a14ff868230/kernel/feature/sucompat.c)
- [`kernel/runtime/ksud.c`](https://github.com/backslashxx/KernelSU/blob/0b138d6a9cfe4dc163aa05c21b1e6a14ff868230/kernel/runtime/ksud.c)
- [`kernel/hook/setuid_hook.c`](https://github.com/backslashxx/KernelSU/blob/0b138d6a9cfe4dc163aa05c21b1e6a14ff868230/kernel/hook/setuid_hook.c)
- [`kernel/hook/lsm_hooks_list.c`](https://github.com/backslashxx/KernelSU/blob/0b138d6a9cfe4dc163aa05c21b1e6a14ff868230/kernel/hook/lsm_hooks_list.c)
- [`kernel/hook/lsm_hooks_static.c`](https://github.com/backslashxx/KernelSU/blob/0b138d6a9cfe4dc163aa05c21b1e6a14ff868230/kernel/hook/lsm_hooks_static.c)
- [`kernel/hook/lsm_hooks_manual.c`](https://github.com/backslashxx/KernelSU/blob/0b138d6a9cfe4dc163aa05c21b1e6a14ff868230/kernel/hook/lsm_hooks_manual.c)
- [`kernel/hook/branch_link_hook_arm64.c`](https://github.com/backslashxx/KernelSU/blob/0b138d6a9cfe4dc163aa05c21b1e6a14ff868230/kernel/hook/branch_link_hook_arm64.c)
- [`kernel/hook/syscall_table_hook_arm64.c`](https://github.com/backslashxx/KernelSU/blob/0b138d6a9cfe4dc163aa05c21b1e6a14ff868230/kernel/hook/syscall_table_hook_arm64.c)
- [`kernel/hook/kp_ksud.c`](https://github.com/backslashxx/KernelSU/blob/0b138d6a9cfe4dc163aa05c21b1e6a14ff868230/kernel/hook/kp_ksud.c)
- [`kernel/feature/selinux_hide.c`](https://github.com/backslashxx/KernelSU/blob/0b138d6a9cfe4dc163aa05c21b1e6a14ff868230/kernel/feature/selinux_hide.c)
- [`kernel/downstream/slow_avc_audit_defs.h`](https://github.com/backslashxx/KernelSU/blob/0b138d6a9cfe4dc163aa05c21b1e6a14ff868230/kernel/downstream/slow_avc_audit_defs.h)

### E3 — official simonpunk sources

| Target | Branch head | Official 50 |
|---|---|---|
| Sultan 6.1 | `7fd1da8e0cc8d1b572c97c5fe4a27d0ec6e3e2f1` | [Sultan 50](https://gitlab.com/simonpunk/susfs4ksu/-/raw/sultan-shiba-susfs-minimal/kernel_patches/50_add_susfs_in_gki-android14-6.1.patch) |
| GKI 6.1 | `598370fe434a7825bfe0f41d3029d102e3cfaec4` | [GKI 6.1 50](https://gitlab.com/simonpunk/susfs4ksu/-/raw/gki-android14-6.1/kernel_patches/50_add_susfs_in_gki-android14-6.1.patch) |
| GKI 6.12 | `698aa6a4ddca6fa5359871daf13f93583fb8282a` | [GKI 6.12 50](https://gitlab.com/simonpunk/susfs4ksu/-/raw/gki-android16-6.12/kernel_patches/50_add_susfs_in_gki-android16-6.12.patch) |

Official 10 was also inspected for its handler interfaces: [GKI 6.1 10](https://gitlab.com/simonpunk/susfs4ksu/-/raw/gki-android14-6.1/kernel_patches/KernelSU/10_enable_susfs_for_ksu.patch) and [GKI 6.12 10](https://gitlab.com/simonpunk/susfs4ksu/-/raw/gki-android16-6.12/kernel_patches/KernelSU/10_enable_susfs_for_ksu.patch).

The official 50 patches are not semantically identical. The 6.12 patch uses `mnt_idmap`, `mnt_id_unique`, `backup_sepolicy`, policy-specific helper wrappers in `security/selinux/ss/services.c`, and changed VFS/SELinux APIs. The Sultan 6.1 patch also contains vendor/target additions absent from generic GKI 6.1, including verified-boot bootconfig filtering/spoofing and additional FUSE/path adaptations. Their disputed KernelSU transport blocks have the same official-10 ownership model but different target anchors.

### E4 — fixtures

- [`scope-min-manual-hooks-v2.3.patch`](.github/fixtures/scope-min-manual-hooks-v2.3.patch): `fs/exec.c`, `fs/open.c`, `fs/stat.c`, and `kernel/reboot.c`.
- [`manual-security-hooks-v2.0.patch`](.github/fixtures/manual-security-hooks-v2.0.patch): `security_bprm_check`, `security_inode_rename`, `security_file_permission`, `security_task_fix_setuid`, and `security_setprocattr` call sites.

### E5 — known-good references

`yapixel/cheetah_ksu_workflow@eecfddfa8f036a51575804195938cd97a9fa04fc` and `yapixel/popsicle_ksu_workflow@7a1f69c70889b309dd96cf1a46d4555d394c5783` were inspected.

The decisive evidence is not only the patch text. Their build workflows show:

- manual GKI/Sultan jobs apply both fixtures and set `CONFIG_KSU_LSM_SECURITY_HOOKS=n`;
- LSM jobs set `CONFIG_KSU_LSM_SECURITY_HOOKS=y` and `CONFIG_KSU_HACK_ARM64_BRANCH_LINK=y`;
- both 6.12.23 and 6.12.69 known-good manual jobs apply the fixtures before 51;
- all known-good 51s exclude the disputed official transport and SELinux files.

### E6 — current repository implementation

Current generated 51s have the same disputed-path disposition as known-good 51: `fs/exec.c`, `fs/open.c`, `fs/read_write.c`, `kernel/reboot.c`, and all four SELinux files are absent; `fs/stat.c` retains only SuSFS kstat/mount behavior; `kernel/sys.c` retains uname spoofing but no setuid caller; and `drivers/input/input.c` only declares `ksu_input_hook_key_false`.

Unlike the known-good build workflows, [the current generation workflow](.github/workflows/generate-51-kernel-patches.yml) applies the two fixtures only for Sultan, does not select GKI manual or LSM/BL mode, and does not build. Its “integration verified” message is patch application only.

---

## 3. Known-good reference mapping

| Reference | What it proves | What it does not prove |
|---|---|---|
| Shared known-good 11 | The xxKSU SuSFS source integration compiled/worked in the tested combinations; it adds `ksu_handle_setresuid` and extends `ksu_handle_sys_reboot`. | It does not define `ksu_handle_execveat_sucompat`, `ksu_handle_vfs_fstat`, `ksu_handle_sys_read`, or `ksu_handle_input_handle_event`. |
| GKI/Sultan 6.1 known-good 51 | The reduced SuSFS kernel patch can work when paired with a selected transport mode. | It does not prove 51 alone supplies callers. |
| GKI 6.12.23/.69 known-good 51 | The same de-inline policy works across those minor versions with adapted context. | It does not prove feature-by-feature parity of the lightweight xxKSU SELinux replacement. |
| Known-good manual workflows | Fixtures supply final source call sites. | They do not validate the fixture-free current GKI generation workflow. |
| Known-good LSM workflows | Explicit BL/LSM configuration supplies runtime transport. | They do not make branch-link a default xxKSU behavior for built-in kernels. |

---

## 4. Complete call-site ownership matrix

“Official 50 call site” below means the direct/static-key source call created by 50. “xxKSU native caller” means a caller or equivalent behavior in actual xxKSU, not merely a definition.

| Handler | Definition owner | Official 50 call site | Clean target caller | xxKSU native caller | Fixture caller | GKI 6.1 final path | GKI 6.12 final path | Sultan 6.1 final path | Should 51 contain it? | Evidence | Confidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `ksu_handle_execveat` | Actual xxKSU `kernel/feature/sucompat.c`; kernel-filename sucompat | `fs/exec.c`, gated by official-10 keys and SuSFS state | **NO PRE-EXISTING CALL SITE** | BL wrapper `ksu_do_execveat_common` when BL mode is enabled | `scope-min` `fs/exec.c` | manual: fixture; LSM: BL wrapper; current repo GKI: **FUNCTIONAL GAP** unless consumer supplies mode | same | manual: fixture; LSM: BL wrapper | No generic call in 51; require selected owner | E1–E6 | HIGH |
| `ksu_handle_execveat_sucompat` | Official-10 KernelSU `feature/sucompat.c`; **absent from actual xxKSU and 11** | `fs/exec.c` alternate branch | **NO PRE-EXISTING CALL SITE** | None | None | Replaced by actual xxKSU single `ksu_handle_execveat` path | same | same | No; incompatible official interface | E2, E3, known-good 11 search | HIGH |
| `ksu_handle_faccessat` | Actual xxKSU `kernel/feature/sucompat.c`; user-pointer ABI | `fs/open.c` uses official-10 `struct filename **` ABI | **NO PRE-EXISTING CALL SITE** | BL `ksu_vfs_faccessat` wrapper or syscall-table wrapper | `scope-min` `fs/open.c` uses actual xxKSU ABI | manual: fixture; LSM: BL; current repo GKI: **FUNCTIONAL GAP** absent selected mode | same | manual fixture / LSM BL | No; official ABI must be replaced | E1–E6 | HIGH |
| `ksu_handle_stat` | Actual xxKSU `kernel/feature/sucompat.c`; user-pointer ABI | `fs/stat.c` `vfs_statx` uses official-10 `struct filename **` ABI | **NO PRE-EXISTING CALL SITE** | BL `ksu_vfs_fstatat` or syscall-table wrapper | `scope-min` newfstatat/fstatat64 | manual fixture / LSM BL; current repo GKI gap absent selected mode | same | manual fixture / LSM BL | No handler call in 51; keep separate SuSFS stat blocks | E1–E6 | HIGH |
| `ksu_handle_vfs_fstat` | Official-10 `kernel/runtime/ksud.c`; **absent from actual xxKSU and 11** | static-key call in `vfs_fstat` | **NO PRE-EXISTING CALL SITE** | Equivalent actual functions `ksu_handle_newfstat_ret`/`ksu_handle_fstat64_ret`, reached by syscall-table, kretprobe, or fixture return call | `scope-min` newfstat/fstat64 return calls | equivalent return path | equivalent return path | equivalent return path | No; reroute to actual xxKSU return ABI | E2–E5 | HIGH |
| `ksu_handle_sys_read` | Official-10 `kernel/runtime/ksud.c`; **absent from actual xxKSU and 11** | static-key call in `ksys_read` | **NO PRE-EXISTING CALL SITE** | Equivalent `ksu_install_rc_hook`: 6.1 LSM `file_permission`, 6.12 BL-patched read/security call, or syscall-table `ksu_handle_sys_read_fd` | `manual-security` `security_file_permission` → `ksu_file_permission` | manual-security or native LSM/BL | manual-security or native LSM/BL | same | No; reroute to actual xxKSU path | E1–E5 | HIGH |
| `ksu_handle_sys_reboot` | Actual xxKSU `kernel/supercall/supercall.c`; 11 adds SuSFS dispatch | `kernel/reboot.c` with official-10 handled/original return contract | **NO PRE-EXISTING CALL SITE** | syscall-table wrapper, BL fallback, or optional kprobe | `scope-min` direct call then original syscall flow | manual fixture / LSM BL+syscall table; current repo GKI gap absent selected mode | same | manual fixture / LSM BL | No official block; replace with compatible transport | E1–E6 | HIGH |
| `ksu_handle_setresuid` | Added by 11 in actual xxKSU `kernel/hook/setuid_hook.c`; SuSFS zygote flags/umount | direct `kernel/sys.c` call | **NO PRE-EXISTING CALL SITE** | `ksu_task_fix_setuid` → `ksu_handle_setresuid_cred` → `ksu_handle_setresuid` | `manual-security` inserts `security_task_fix_setuid` call | manual-security / 6.1 LSM slot hijack | manual-security / 6.12 ARM64 security-call patch | same | No direct call when LSM/manual path is selected; it would duplicate | E1–E5, current 11 | HIGH |
| `ksu_handle_input_handle_event` | Official-10 `kernel/runtime/ksud.c`; **absent from actual xxKSU and 11** | static-key call in `drivers/input/input.c` | **NO PRE-EXISTING CALL SITE** | No such handler. Equivalent `vol_detector_handler` is registered with input core and `vol_detector_event` counts keys. | None | xxKSU input handler | xxKSU input handler | xxKSU input handler | No; remove official block and remove redundant declaration | E1–E6 | HIGH |

### Duplicate and removal tests

- A retained official 50 call is a duplicate only when a second final caller is proven. The known-good manual and LSM builds prove such alternatives. The current GKI generation workflow does not.
- Removing official `execveat_sucompat`, `vfs_fstat`, `sys_read`, and input calls is not a gap because actual xxKSU lacks those exact interfaces and proves equivalent paths.
- Removing official exec/access/stat/reboot without selecting fixtures or BL/syscall transport is a **FUNCTIONAL GAP**. This is the current repository's GKI validation state.
- Sultan current validation applies both fixtures, so its manual final tree has exactly one compatible caller after official 50 transport is removed.

---

## 5. Exact meaning of “de-inline” in this repository

1. It does **not** mean removing all traditional manual source calls. Valid manual builds require fixture-owned direct calls.
2. It means removing official-50 transport that is duplicate, ABI-incompatible, or owned by another selected component.
3. It does not universally replace direct calls with LSM paths. Exec/access/stat/reboot use fixtures in manual mode and BL/syscall transport in LSM mode; setuid/read use security paths.
4. It delegates caller ownership to fixtures in manual mode and to xxKSU runtime mechanisms in LSM/BL mode.
5. It is target- and configuration-specific because kernel APIs and chosen transport differ.
6. Sultan is not fundamentally different in architecture, but its vendor tree and current workflow make fixture/adapter ownership explicit.
7. Some `ksu_handle_*` calls are valid and required—for example fixture calls and xxKSU wrappers.
8. Static-key-gated calls can be valid architecture, but the official keys/handlers belong to official 10 and are not automatically compatible with actual xxKSU.
9. Function name alone is never enough to classify a call site.
10. The target manifest ultimately owns the decision. It must select exactly one of: manual fixture source calls, xxKSU LSM/BL/syscall transport, or a separately proven target-native mechanism. 51 must not guess.

---

## 6. GKI Android 14 / Linux 6.1 call-path analysis

### Clean target

The actual Pantah archive has no pre-existing KSU/SuSFS caller in any required file.

### Validated manual path

```text
exec:    fs/exec.c [FIXTURE scope-min]
           → ksu_handle_execveat [XXKSU sucompat]

access:  fs/open.c [FIXTURE scope-min]
           → ksu_handle_faccessat [XXKSU sucompat]

stat:    fs/stat.c newfstatat [FIXTURE scope-min]
           → ksu_handle_stat [XXKSU sucompat]
         newfstat return [FIXTURE scope-min]
           → ksu_handle_newfstat_ret [XXKSU init-RC size]

read:    security/security.c security_file_permission [FIXTURE manual-security]
           → ksu_file_permission [XXKSU]
           → static branch ksud_vfs_read_key
           → ksu_install_rc_hook [XXKSU runtime]

reboot:  kernel/reboot.c [FIXTURE scope-min]
           → ksu_handle_sys_reboot [XXKSU + 11]
           → SuSFS command dispatch / xxKSU supercall

setuid:  kernel/sys.c → security_task_fix_setuid [TARGET_KERNEL]
           → ksu_task_fix_setuid [FIXTURE manual-security]
           → ksu_handle_setresuid_cred [XXKSU]
           → ksu_handle_setresuid [11]

input:   input core [TARGET_KERNEL]
           → registered vol_detector_handler [XXKSU runtime]
           → vol_detector_event → safe_mode_flag
```

### Validated LSM/BL path

- `CONFIG_KSU_LSM_SECURITY_HOOKS=y` selects `lsm_hooks_list.c` on 6.1. It replaces existing LSM hook-list function pointers for setuid and file permission.
- `CONFIG_KSU_HACK_ARM64_BRANCH_LINK=y` patches exec/access/stat call sites to xxKSU wrappers. Its initialization uses syscall-table replacements for reboot/read/fstat-return until early-boot read/stat work is complete.
- Input still uses xxKSU runtime registration.

### Current repository path

Current GKI generation applies 11+51 but no fixture and no mode-selecting config. With built-in defaults (`KSU_HACK_ARM64_BRANCH_LINK=n`, `KSU_TAMPER_SYSCALL_TABLE=n`, `KSU_KPROBES_KSUD=n`), setuid/read can use the default 6.1 LSM path, but exec/access/stat/reboot have no proven transport. Classification: **FUNCTIONAL GAP in the current verification composition**.

---

## 7. GKI Android 16 / Linux 6.12 call-path analysis

The actual r58 archive has no pre-existing KSU/SuSFS caller in any required file.

Manual mode is the same ownership model as 6.1: `scope-min` supplies exec/access/stat/fstat-return/reboot, `manual-security` supplies setuid/read/security calls, and xxKSU registers its input handler.

LSM mode differs internally:

```text
setuid syscall [TARGET_KERNEL]
  → existing security_task_fix_setuid call
  → ARM64 BL call-site patched by xxKSU lsm_hooks_static.c
  → ksu_task_fix_setuid
  → ksu_handle_setresuid_cred
  → ksu_handle_setresuid [11]

read syscall [TARGET_KERNEL]
  → xxKSU BL-patched vfs_read/security_file_permission
  → ksu_install_rc_hook

exec/access/stat [TARGET_KERNEL]
  → xxKSU branch-link wrappers
  → actual xxKSU handlers

reboot/fstat-return/read early boot
  → xxKSU syscall-table wrappers/fallback

input event [TARGET_KERNEL]
  → xxKSU registered input handler
```

The 6.12 official calls to `ksu_handle_execveat_sucompat`, `ksu_handle_vfs_fstat`, `ksu_handle_sys_read`, and `ksu_handle_input_handle_event` cannot be retained because the actual xxKSU symbols do not exist. The current repository's GKI validation again selects neither manual fixtures nor BL mode, so its final transport is unproven and has the same qualified gap as GKI 6.1.

---

## 8. Sultan Android 14 / Linux 6.1 call-path analysis

The clean Sultan commit contains no pre-existing KSU/SuSFS caller in the required paths.

The current repository workflow applies 51, 11, then both fixtures for Sultan. Its manual architecture is therefore:

```text
official Sultan 50 transport
  → removed during 50→51 [51]
  → compatible exec/access/stat/reboot restored [scope-min fixture]
  → setuid/read/security calls restored [manual-security fixture]
  → handlers/equivalent behavior in xxKSU [XXKSU + 11]
```

For each affected manual path there is exactly one compatible caller after transformation. The official and fixture calls are not present simultaneously.

The known-good Sultan LSM build does not apply manual fixtures; it selects the same 6.1 LSM-list and ARM64 BL/syscall mechanisms as known-good GKI LSM. Sultan-specific 51 chunks (`try_umount`, exported `susfs_run_sus_path_loop`, headers) are target extensions/adaptations, not de-inline policy. The `ksu_input_hook_key_false` declaration is not an adaptation with a consumer; it is redundant.

---

## 9. SELinux exclusion verification

Actual xxKSU initializes `ksu_selinux_hide_init()` unconditionally. It provides a self-contained replacement which its own source describes as lighter than the official “fullblown” backup-policy approach.

| Official-50 file/block | Official behavior | Equivalent elsewhere | Classification | Confidence |
|---|---|---|---|---|
| `security/selinux/avc.c` declarations + audit branch | Spoof KSU target SID/context as priv_app in AVC output | xxKSU `slow_avc_audit` wrappers replace `tsid==cached_su_sid` with `priv_app_sid` before the original audit | `DUPLICATE_XXKSU_REMOVE` | HIGH |
| `security/selinux/hooks.c` fake-state declarations | Support backup/fake policy setprocattr | xxKSU owns its state and context-destruction logic | `TARGET_COMPAT_REPLACE` | MEDIUM |
| `security/selinux/hooks.c::my_setprocattr` + LSM slot | Validate hidden context against fake policy | xxKSU `ksu_hide_setprocattr_inline`, reached through manual security, 6.1 LSM-list, or 6.12 call patch | `TARGET_COMPAT_REPLACE` | MEDIUM |
| `security/selinux/selinuxfs.c` fake-status declarations/open replacement | Present fake enforcing/status page to apps | xxKSU creates `ksu_fake_status_page` and rewrites the status file's `fops->open` | `TARGET_COMPAT_REPLACE` | HIGH |
| `selinuxfs.c::my_write_context` | Resolve contexts against backup policy | xxKSU rewrites the transaction write path and destroys KSU contexts | `TARGET_COMPAT_REPLACE` | MEDIUM |
| `selinuxfs.c` access/context handler table | Route access/context writes to fake-policy handlers | xxKSU rewrites the common transaction write file operation | `TARGET_COMPAT_REPLACE` | MEDIUM |
| `selinuxfs.c::my_write_access` | Compute AV from backup policy | xxKSU hides KSU context queries and normalizes returned sequence; not bit-for-bit identical | `TARGET_COMPAT_REPLACE` | MEDIUM |
| `security/selinux/ss/services.c` two wrappers (6.12) | Expose internal policy helpers used by official backup-policy implementation | Not needed by xxKSU's self-contained replacement | `TARGET_COMPAT_REPLACE` | HIGH |

No source proves a second independent implementation of official 50's exact backup-policy model, so exact parity for `write_context`/`write_access` is not HIGH confidence. Evidence present: actual xxKSU replacement code and successful known-good builds. Evidence missing: targeted runtime tests comparing outputs for the same hidden contexts. Confidence would rise with those tests.

Conclusion: current 51 does not silently drop these domains, but its whole-file exclusion is still an unsafe implementation technique because it cannot prove the replacement. V2 must encode and validate the replacement explicitly.

---

## 10. `fs/exec.c` semantic-block audit

```text
Official upstream semantic block
├── SuSFS process/decryption gates
│     → REROUTE: they select between official-10 handlers and are coupled to that ABI
├── KSU caller
│     → DEINLINE/REPLACE: actual xxKSU has one compatible handler, not both official handlers
├── static-key gate (`ksu_su_compat_enabled`)
│     → REMOVE/ADAPT: official key belongs to official 10; actual xxKSU uses `ksud_sucompat_key`
└── target/version context
      → TARGET_COMPAT: 6.1/6.12 function anchors differ
```

Official 50 is not an unconditional call. It first skips processes marked no-su, then tests `ksu_su_compat_enabled`, then selects `ksu_handle_execveat` while Android data is not decrypted or `ksu_handle_execveat_sucompat` otherwise. Actual xxKSU lacks the second handler and official key. Its single handler applies its own seccomp/allowlist/TIF gate. Known-good/current 51 remove the whole block; manual fixtures add one compatible call and LSM builds use BL. Classification: `REROUTE`, not name-based removal.

---

## 11. `fs/open.c` semantic-block audit

```text
Official upstream semantic block
├── `getname_flags`/`struct filename` conversion
│     → REROUTE: required by official-10 ABI, not actual xxKSU ABI
├── no-su/allow-UID checks
│     → REROUTE to actual xxKSU `is_su_allowed`
├── `ksu_handle_faccessat`
│     → DEINLINE official ABI; fixture/BL owns final caller
└── 6.1 vs 6.12 getname API
      → TARGET_COMPAT
```

There is no independent open-redirect or filesystem-hiding behavior in this official `fs/open.c` block; open redirect lives in other retained SuSFS paths. Current removal does not delete a separate pure SuSFS block.

---

## 12. `fs/stat.c` semantic-block audit

`fs/stat.c` contains independently owned blocks and must be split:

| Block | Action | Reason |
|---|---|---|
| SuSFS includes and kstat/mount helper declarations | `KEEP` | Pure SuSFS kernel behavior. |
| `generic_fillattr` spoof | `KEEP_PURE_SUSFS` | Independent of KSU transport. |
| `vfs_getattr_nosec` spoof | `KEEP_PURE_SUSFS` | Independent. |
| official `vfs_fstat` → `ksu_handle_vfs_fstat` | `REROUTE` | Handler absent from xxKSU; actual fstat-return mechanism exists. |
| official `vfs_statx` → `ksu_handle_stat` | `REROUTE` | Official ABI differs; fixture/BL owns final caller. |
| mount ID and 6.12 unique-ID spoof | `KEEP_PURE_SUSFS` + `TARGET_ADAPT` | Required SuSFS behavior; 6.12 API differs. |

Current and known-good 51 correctly keep the pure blocks and remove the incompatible KSU blocks.

---

## 13. `fs/read_write.c` audit

Official 50 expects `ksu_is_init_rc_hook_enabled` and exported `ksu_handle_sys_read(unsigned int)`, both created by official 10. Actual xxKSU has neither. It has `ksud_vfs_read_key`, `ksu_install_rc_hook`, and a private `ksu_handle_sys_read_fd` for probe/syscall-table paths.

Classification by final mode:

- manual: `REROUTE` to fixture `security_file_permission` → xxKSU `ksu_file_permission`;
- 6.1 LSM: `REROUTE` to LSM-list file-permission interception;
- 6.12 LSM: `REROUTE` to BL-patched read/security path;
- BL/syscall mode: `REROUTE` to syscall-table read wrapper.

It is not a valid actual-xxKSU static-key call as written, and removal is not a gap when one of those paths is selected.

---

## 14. `kernel/reboot.c` audit

Official 50 assumes a handler return value tells the syscall whether to continue original reboot flow. Actual xxKSU's `ksu_handle_sys_reboot` returns zero for non-KSU input and handled operations. Retaining the official block would therefore suppress normal reboot flow; it is not merely redundant.

Compatible paths call the handler for its side effects and then continue the original syscall: the scope-min fixture and xxKSU syscall-table/probe wrappers do exactly that. 11 extends the handler with SuSFS command dispatch. Classification: `REROUTE`/`XXKSU_COMPAT`; **FUNCTIONAL GAP** if official block is removed without fixture or native runtime transport.

---

## 15. `kernel/sys.c` / setuid audit

```text
manual:
kernel/sys.c __sys_setresuid
  → security_task_fix_setuid [TARGET_KERNEL]
  → ksu_task_fix_setuid [FIXTURE manual-security]
  → ksu_handle_setresuid_cred [XXKSU]
  → ksu_handle_setresuid [11]

6.1 LSM:
security_task_fix_setuid
  → existing LSM-list entry replaced by xxKSU
  → same cred/handler chain

6.12 LSM:
__sys_setresuid call to security_task_fix_setuid
  → ARM64 call patched to xxKSU wrapper
  → same cred/handler chain
```

The official direct `kernel/sys.c` call would duplicate those selected paths. Its removal is `DUPLICATE_REMOVAL` for validated manual/LSM builds. The separate uname spoof block is pure SuSFS and is retained by current 51.

---

## 16. `drivers/input/input.c` audit

Official 50 expects official-10 symbols `ksu_is_input_hook_enabled` and `ksu_handle_input_handle_event`. Actual xxKSU defines neither. Instead:

1. `ksu_ksud_init` calls `vol_detector_init`.
2. `vol_detector_init` calls `input_register_handler`.
3. `vol_detector_event` counts volume-up/down presses and sets `safe_mode_flag` at three presses.
4. `ksu_is_safe_mode` consumes the flag and unregisters the input handler.

`ksu_input_hook_key_false` in known-good/current 51 is only an `extern` declaration. No actual xxKSU definition or kernel consumer was found; because it is never referenced, it creates no link requirement and no behavior.

Classification:

- removal of official input call: `CORRECT` / `DUPLICATE_XXKSU_REMOVE` at the behavior level;
- safe-mode volume-key detection: remains functional through runtime registration;
- `ksu_input_hook_key_false` declaration: `REDUNDANT` known-good local extension;
- Phase 1 “safe mode broken” conclusion: rejected.

---

## 17. Known-Good Reference Differential

| Path | Official upstream 50 | Known-good 51 | Current generated 51 | Actual final target path | Classification |
|---|---|---|---|---|---|
| `fs/exec.c` | Official-key-gated dual official-10 handler block | absent | absent | fixture single handler or xxKSU BL | `DEINLINE_POLICY`, `XXKSU_COMPAT` |
| `fs/open.c` | official `struct filename` ABI call | absent | absent | fixture user-pointer ABI or xxKSU BL | `XXKSU_COMPAT` |
| `fs/stat.c` | mixed pure SuSFS + official handlers | pure SuSFS retained; handlers removed | same | fixture/BL + retained SuSFS | `SPLIT_MIXED_BLOCK`, `DEINLINE_POLICY` |
| `fs/read_write.c` | official static-key read handler | absent | absent | manual-security/LSM/syscall wrapper | `REROUTE`, `XXKSU_COMPAT` |
| `kernel/reboot.c` | incompatible return-contract caller | absent | absent | scope-min or xxKSU wrapper | `REROUTE`, `XXKSU_COMPAT` |
| `kernel/sys.c` | direct setuid + uname | setuid removed; uname kept | same | LSM/manual setuid chain + 51 uname | `DUPLICATE_REMOVAL`, `KEEP_PURE_SUSFS` |
| `drivers/input/input.c` | official static-key handler | redundant extern only | same | xxKSU input-handler registration | `KNOWN_GOOD_LOCAL_EXTENSION` (redundant), `REROUTE` |
| `security/selinux/avc.c` | direct official AVC spoof | absent | absent | xxKSU slow-AVC call patch | `XXKSU_COMPAT` |
| `security/selinux/hooks.c` | full backup-policy setprocattr | absent | absent | xxKSU LSM/manual lightweight replacement | `XXKSU_COMPAT` |
| `security/selinux/selinuxfs.c` | fake status/context/access handlers | absent | absent | xxKSU fops/transaction-write replacement | `XXKSU_COMPAT` |
| `security/selinux/ss/services.c` | 6.12 backup-policy wrappers | absent | absent | not needed by xxKSU replacement | `KERNEL_VERSION_COMPAT`, `XXKSU_COMPAT` |

There is no disputed-path policy difference between known-good and current generated 51. The material difference is composition: known-good workflows select a transport; current GKI generation does not.

---

## 18. GKI 6.12.23 vs 6.12.69 differential

The two known-good patches each contain 1,285 changed payload lines. Comparing only added/deleted payload lines produces **zero differences**. There are 62 differing line positions in the full patches, consisting of:

- subject/base identity;
- Git blob index IDs;
- hunk offsets;
- surrounding context changes such as `linux/dma-buf.h`, `vma_pages` → `vma_data_pages`, changed namespace/listmount signatures, and shifted SELinux/VFS lines.

| Difference class | Result |
|---|---|
| `DEINLINE_POLICY` | No difference. |
| `KERNEL_VERSION_COMPAT` | Hunk positions, APIs, and context only. |
| `PATCH_CONTEXT_ONLY` | Blob IDs and context lines. |
| `UPSTREAM_SUSFS_CHANGE` | None in changed payload. |
| `LOCAL_EXTENSION` | None differing. |
| `UNKNOWN` | None found. |

Policy must therefore remain shared; minor-version adapters must account for context/API drift without creating a second architecture rule.

---

## 19. Revised 11 / 51 / fixture / adapter responsibility boundary

### 11 owns

- xxKSU source-side SuSFS initialization, SID helpers, zygote/no-su/umount behavior;
- `ksu_handle_setresuid` and the cred-to-handler chain;
- SuSFS command routing inside the existing xxKSU reboot handler;
- xxKSU-specific Kconfig and command/control integration.

11 does not own Linux source caller insertion.

### 51 owns

- target Linux SuSFS filesystem, namespace, proc, stat, uname, map, kallsyms, and related kernel behavior;
- only integration blocks whose final owner is truly Linux/SuSFS and not replaced by xxKSU;
- explicit semantic accounting for official 50 blocks.

51 must not implicitly choose a KernelSU transport mode.

### Fixtures own

- `scope-min`: manual exec/access/stat/fstat-return/reboot source call sites;
- `manual-security`: manual bprm/rename/file-permission/setuid/setprocattr security call sites.

This assignment is proven by fixture source and known-good workflow application.

### Target adapter owns

- 6.1 versus 6.12 VFS/SELinux APIs and anchors;
- 6.12 minor-version context drift;
- Sultan vendor-tree anchors and extensions such as try-umount support;
- selecting and validating the target transport manifest (manual fixtures or LSM/BL config).

Architecture transformation must remain independent from these adaptations.

---

## 20. Corrected target architecture diagrams

### A. GKI Android 14 / Linux 6.1

```text
Linux 6.1 target [TARGET_KERNEL; clean has no KSU callers]
│
├── exec ───── manual [FIXTURE scope-min] ─────┐
│              LSM [XXKSU BL] ────────────────┤→ ksu_handle_execveat [XXKSU]
├── faccessat ─ manual [FIXTURE scope-min] ────┤
│              LSM [XXKSU BL] ────────────────┘
├── stat ───── manual [FIXTURE scope-min]
│              LSM [XXKSU BL/syscall fallback] → actual stat handlers
├── read ───── manual [FIXTURE manual-security]
│              LSM [XXKSU LSM-list] → ksu_install_rc_hook
├── reboot ─── manual [FIXTURE scope-min]
│              LSM [XXKSU syscall fallback] → ksu_handle_sys_reboot [11]
├── setuid ─── security_task_fix_setuid
│              → [FIXTURE manual-security OR XXKSU LSM-list]
│              → ksu_handle_setresuid [11]
├── input ──── registered input handler [XXKSU]
└── SuSFS kernel functionality [51]

Current repository GKI verification: transport selection MISSING for exec/access/stat/reboot.
```

### B. GKI Android 16 / Linux 6.12

```text
Linux 6.12 target [TARGET_KERNEL; clean has no KSU callers]
│
├── exec/access/stat
│    ├── manual [FIXTURE scope-min]
│    └── LSM [XXKSU ARM64 BL + syscall fallback]
├── read
│    ├── manual [FIXTURE manual-security]
│    └── LSM [XXKSU ARM64 read/security call patch]
├── reboot
│    ├── manual [FIXTURE scope-min]
│    └── LSM [XXKSU syscall fallback]
├── setuid
│    ├── manual [FIXTURE manual-security]
│    └── LSM [XXKSU ARM64 security call patch]
├── input [XXKSU registered handler]
└── SuSFS kernel functionality [51 + 6.12 adapter]

6.12.23 vs 6.12.69: same architecture/payload; context adapter differs.
Current repository GKI verification: transport selection MISSING.
```

### C. Sultan Android 14 / Linux 6.1

```text
Sultan target [TARGET_KERNEL; clean has no KSU callers]
│
├── manual mode
│    ├── exec/access/stat/reboot [FIXTURE scope-min]
│    ├── read/setuid/security [FIXTURE manual-security]
│    └── xxKSU handlers/equivalents [XXKSU + 11]
├── LSM mode
│    ├── exec/access/stat/reboot [XXKSU BL/syscall]
│    └── read/setuid/security [XXKSU 6.1 LSM-list]
├── input [XXKSU registered handler]
├── SuSFS kernel behavior [51]
└── Sultan anchors/try-umount/vendor changes [TARGET ADAPTER]
```

---

## 21. Corrections to Phase 1

| Phase 1 conclusion | Status | Correction/evidence |
|---|---|---|
| Manual/inline calls were kprobes/syscall-table hooks | `REJECTED` | Direct source calls, kprobes, syscall-table replacements, BL patches, and runtime registration are distinct. |
| De-inline means remove traditional KSU calls | `CORRECTED` | It means replace incompatible/duplicate official transport only after proving final ownership. |
| GKI exec path is missing | `CORRECTED` | Missing in current repository GKI verification composition; present in known-good manual fixture and LSM BL builds. |
| GKI access path is missing | `CORRECTED` | Same qualification. |
| GKI stat path is missing | `CORRECTED` | SuSFS stat behavior is retained; KSU stat/fstat is supplied by fixture/BL in known-good builds, missing from current unselected composition. |
| GKI reboot path is missing | `CORRECTED` | Known-good fixture/syscall transport exists; current GKI verification selects neither. |
| GKI setuid needs direct `kernel/sys.c` | `REJECTED` | Manual-security or native LSM routes through `ksu_handle_setresuid_cred`. |
| GKI input safe mode is broken | `REJECTED` | Actual xxKSU registers an input handler and counts keys independently. |
| GKI read path is uncertain/missing | `CORRECTED` | Manual-security and native LSM/read patch paths are proven. Exact official handler is absent by design. |
| Sultan fixture owns manual callers | `CONFIRMED` | Proven by fixture semantic blocks and manual workflow. LSM Sultan does not need them. |
| SELinux exclusions lose pure SuSFS behavior | `CORRECTED` | xxKSU replaces all four architectural domains; exact backup-policy parity remains MEDIUM. |
| Input stub is required Sultan compatibility | `REJECTED` | It is an unused extern with no definition/consumer. |
| 11/51 boundary puts Linux KSU callers in 51 | `REJECTED` | Fixtures or xxKSU runtime own transport; 51 owns SuSFS kernel integration. |
| Current generator is incorrect | `CONFIRMED`, reason refined | It uses whole-file/keyword filtering and cannot prove replacement ownership. Some exclusions are semantically correct, but the method and GKI validation are not fail-closed. |

---

## 22. Final de-inline policy table

| Semantic path | GKI 6.1 | GKI 6.12 | Sultan 6.1 | Final owner | 50→51 action | Evidence | Confidence |
|---|---|---|---|---|---|---|---|
| Exec transport | fixture or xxKSU BL | fixture or xxKSU BL | fixture or xxKSU BL | target manifest | `REROUTE`; `FAIL_UNKNOWN` if none selected | E1–E6 | HIGH |
| Exec SuSFS/official-key gates | incompatible with actual xxKSU | same | same | xxKSU sucompat policy | `REROUTE` | E2/E3 | HIGH |
| Access transport | fixture or BL | fixture or BL | fixture or BL | target manifest | `REROUTE`; `FAIL_UNKNOWN` if absent | E1–E6 | HIGH |
| Stat sucompat | fixture or BL | fixture or BL | fixture or BL | target manifest | `REROUTE` | E1–E6 | HIGH |
| Stat/fstat init-RC | fixture return call or xxKSU runtime | same | same | fixture/xxKSU | `REROUTE` | E2/E4/E5 | HIGH |
| Pure SuSFS kstat/mount ID | keep | keep + unique ID adapt | keep | 51 | `KEEP_PURE_SUSFS`, `TARGET_ADAPT` | official/current diffs | HIGH |
| Read/init-RC | manual-security or LSM/runtime | manual-security or LSM/runtime | same | fixture/xxKSU | `REROUTE` | E2/E4/E5 | HIGH |
| Reboot/supercall | fixture or xxKSU wrapper | fixture or xxKSU wrapper | fixture or xxKSU wrapper | target manifest + 11 handler | `REROUTE`; `FAIL_UNKNOWN` if absent | E2–E6 | HIGH |
| Setuid | manual-security or LSM | manual-security or LSM | same | fixture/xxKSU + 11 | `REMOVE_DUPLICATE` | E2/E4/E5 | HIGH |
| Input safe mode | xxKSU registration | xxKSU registration | xxKSU registration | xxKSU | `REMOVE_DUPLICATE`; delete stub | E2 | HIGH |
| Uname spoof | keep | keep | keep | 51 | `KEEP_PURE_SUSFS` | E3/E6 | HIGH |
| AVC spoof | xxKSU replacement | xxKSU replacement | xxKSU replacement | xxKSU | `REMOVE_DUPLICATE` | E2/E3 | HIGH |
| SELinux setprocattr | xxKSU replacement | xxKSU replacement | xxKSU replacement | xxKSU/manual-security | `REROUTE` | E2/E4 | MEDIUM |
| Fake SELinux status | xxKSU replacement | xxKSU replacement | xxKSU replacement | xxKSU | `REROUTE` | E2 | HIGH |
| SELinux context/access | xxKSU lightweight replacement | same | same | xxKSU | `REROUTE`; runtime parity test required | E2/E3/E5 | MEDIUM |
| 6.12 policy wrappers | N/A | unused after replacement | N/A | adapter | `TARGET_ADAPT`/remove with official path | E2/E3 | HIGH |

This is semantic policy, not a regex policy. A generator must match named semantic blocks and prove the selected final owner.

---

## 23. Unknown / unresolved items

1. **Current GKI target contract — UNRESOLVED.** Evidence: current workflow produces/applies 11+51. Missing: an explicit manual or LSM/BL configuration and final-source/build validation. Required evidence: a target manifest and built `.config` for each current GKI output.
2. **Exact SELinux backup-policy parity — UNKNOWN.** Evidence: xxKSU source implements every domain and known-good builds work. Missing: feature-level output tests for fake `setprocattr`, `write_context`, and `write_access`. Required evidence: side-by-side runtime probes against official 50 and xxKSU replacement.
3. **Known-good runtime coverage — UNRESOLVED.** The user designates the references as tested working, but no feature-by-feature test logs were supplied. Required evidence: logs for exec/access/stat/init-RC/reboot/SuSFS commands/input/SELinux.
4. **Release-archive Git commit provenance — UNRESOLVED.** The actual archive contents were inspected, but the releases do not publish a kernel commit in their metadata. Required evidence: a provenance manifest embedded in each asset.
5. **V2 supported modes — UNRESOLVED HUMAN DECISION.** It is unknown whether V2 must emit manual, LSM/BL, or both variants per target. This choice changes final ownership and validation, not 51's pure SuSFS policy.

No unknown above was silently converted into KEEP or REMOVE.

---

## 24. Confidence report

| Area | Confidence | Evidence | Missing evidence / what raises confidence |
|---|---|---|---|
| Clean target caller inventory | HIGH | Actual Sultan commit and both actual release archives scanned | None for required paths. |
| Handler definitions/ABIs | HIGH | Actual xxKSU and official 10 source | None. |
| Manual fixture ownership | HIGH | Fixture source and known-good workflow order/config | None. |
| LSM/BL/syscall ownership | HIGH | Actual xxKSU source and known-good config injection | Runtime traces would validate execution but not change ownership. |
| GKI current composition gap | HIGH | Current workflow lacks fixtures/config/build; current 51 lacks calls | A target manifest could resolve the gap. |
| Sultan final ownership | HIGH | Current/known-good workflow applies fixtures for manual mode | None. |
| Input safe-mode behavior | HIGH | Actual registered input-handler implementation | A keypress runtime test would be operational confirmation. |
| SELinux AVC/fake-status replacement | HIGH | Direct equivalent xxKSU implementations | Runtime output test optional. |
| SELinux context/access parity | MEDIUM | Intentional xxKSU replacement and known-good builds | Missing side-by-side semantic runtime tests; those would raise confidence. |
| 6.12.23 vs .69 policy identity | HIGH | Zero changed-payload differences | None. |
| Exact de-inline definition | HIGH | Convergent target, xxKSU, official, fixture, and known-good evidence | None. |
| Current generator correctness | HIGH (unsafe) | Whole-file exclusions, keyword policy, no owner/config validation | A V2 design does not change this finding; replacement implementation is needed after approval. |

---

## 25. Recommendation: is V2 safe to begin?

**NO — not yet.** The architectural policy is now proven, but implementation must wait for human review and one explicit decision per target:

- `manual`: apply and validate both fixtures; disable automated LSM transport as intended; or
- `lsm_bl`: enable and validate xxKSU LSM + ARM64 branch-link/syscall fallback; do not apply manual fixtures.

Before V2 begins, the approved target manifest must also require:

1. final-source call-path validation (not patch-text validation);
2. exactly one owner per semantic path;
3. handler ABI/symbol validation;
4. required SuSFS semantic coverage, including explicit xxKSU SELinux replacement accounting;
5. build validation with the final `.config`;
6. failure when a caller owner, mixed block, or replacement cannot be proven.

Until that contract exists, generating another 51 would risk reproducing the current GKI ambiguity. Per the Phase 1.5 STOP condition, no V2 implementation, patch regeneration, workflow change, or bug fix follows this report.
