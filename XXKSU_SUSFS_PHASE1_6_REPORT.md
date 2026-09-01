# xxKSU + SuSFS Phase 1.6 — Dual-Mode Target Manifest

**Scope:** design-contract verification only. No V2 implementation, generator, patch, fixture, workflow, kernel, xxKSU, or SuSFS source was modified.

**Baseline:** `XXKSU_SUSFS_PHASE1_5_REPORT.md`. Evidence identifiers E1–E6 below retain the Phase 1.5 meanings: actual target kernels, pinned actual xxKSU, official 10/50, fixtures, known-good builds/workflows, and current repository material, in that priority order.

## 1. Executive Decision

All six required profiles are architecturally supported by existing evidence. The authoritative contract is no longer “choose one mode per target”; every target has a `manual` profile and an `lsm_bl` profile. Ownership is exclusive per final profile, not across both profiles of a target.

The evidence supports this separation:

```text
one shared 11
+ one transport-neutral, target-specific 51
+ one target adapter
+ one explicit profile manifest
    ├── manual: both manual fixtures; automated LSM/BL/syscall/kprobe transport off
    └── lsm_bl: no manual fixtures; LSM and ARM64 BL on; BL-managed syscall fallback
```

The canonical built-in profile settings are:

| Mode | `KSU_LSM_SECURITY_HOOKS` | `KSU_HACK_ARM64_BRANCH_LINK` | `KSU_TAMPER_SYSCALL_TABLE` | `KSU_KPROBES_KSUD` |
|---|---:|---:|---:|---:|
| `manual` | `n` | `n` | `n` | `n` |
| `lsm_bl` | `y` | `y` | `n` | `n` |

These are explicit contract values, not defaults to be assumed. `KSU_TAMPER_SYSCALL_TABLE=n` does **not** mean the `lsm_bl` profile has no syscall-table activity: actual xxKSU includes `syscall_table_hook_arm64.c` internally when BL is enabled and uses it as a managed bootstrap/fallback. `KSU_KPROBES_KSUD` is inactive in source whenever BL is enabled; the canonical profile still pins it to `n` to keep configuration unambiguous.

No evidence requires mode-specific policy in 11 or 51. Final-source and final-configuration validation must occur after composition, for all six profiles.

## 2. Phase 1.5 Contract Corrections

| Phase 1.5 Statement | Status | Phase 1.6 Correction |
|---|---|---|
| “V2 supported modes — UNRESOLVED HUMAN DECISION” | `SUPERSEDED` | Both `manual` and `lsm_bl` are required for every supported target. |
| “one explicit decision per target” | `SUPERSEDED` | Each target must declare two profiles, not select one target-wide mode. |
| Exactly one owner per semantic path | `CLARIFIED` | Exactly one owner is required per semantic path per final build profile. Different profiles may use different owners. |
| Target adapter selects the target transport manifest | `CORRECTED` | The profile manifest selects transport. The adapter implements version/vendor mechanics and validates that selection; it must not decide the mode. |
| 6.1 LSM read/init-RC is owned by the LSM-list file-permission slot | `CONFIG-QUALIFIED` | That is true only when both syscall-table tamper and BL are disabled. Required `lsm_bl` has BL enabled, so read/init-RC uses BL's internally included syscall-table fallback. |

Required contradiction record:

```text
NEW EVIDENCE
Pinned xxKSU lsm_hooks_list.c installs file_permission only when neither
KSU_TAMPER_SYSCALL_TABLE nor KSU_HACK_ARM64_BRANCH_LINK is enabled. Pinned
ksu.c includes syscall_table_hook_arm64.c as the BL fallback, and BL init
installs reboot/read/fstat plus sucompat syscall replacements before attempting
call-site patches.

OLD CONCLUSION
The Phase 1.5 6.1 diagram labeled the lsm_bl read path as LSM-list
file-permission interception.

CORRECTED CONCLUSION
For the required 6.1 lsm_bl profile, read/init-RC is owned by the xxKSU
BL-managed syscall-table fallback. Setuid and setprocattr remain LSM-list owned.
```

This is a configuration-specific refinement, not a change to the transport-neutral 51 policy.

## 3. Six Supported Build Profiles

| Profile | Target | Kernel | Required result |
|---|---|---|---|
| `gki-android14-6.1-manual` | GKI Android 14 | Linux 6.1 | Both fixtures plus manual xxKSU ABI; automated transport disabled |
| `gki-android14-6.1-lsm_bl` | GKI Android 14 | Linux 6.1 | No fixtures; 6.1 LSM-list plus ARM64 BL/internal syscall fallback |
| `gki-android16-6.12-manual` | GKI Android 16 | Linux 6.12 | Both fixtures plus manual xxKSU ABI; automated transport disabled |
| `gki-android16-6.12-lsm_bl` | GKI Android 16 | Linux 6.12 | No fixtures; 6.12 static security-call BL plus sucompat BL/internal syscall fallback |
| `sultan-android14-6.1-manual` | Sultan Android 14 | Linux 6.1 | Both fixtures plus manual xxKSU ABI; Sultan adapter |
| `sultan-android14-6.1-lsm_bl` | Sultan Android 14 | Linux 6.1 | No fixtures; 6.1 LSM-list plus ARM64 BL/internal syscall fallback; Sultan adapter |

Existing evidence supports all six at the architecture/known-good-build level: the clean target inspection proves no pre-existing KSU/SuSFS caller, fixture source proves the manual ABI, actual xxKSU proves runtime transport, and the pinned cheetah/popsicle workflows contain manual and LSM build jobs. This does not substitute for V2's required six final builds.

## 4. Profile Configuration Matrix

| Profile | Target | Kernel | Transport Mode | Fixtures | LSM Security Hooks | ARM64 BL | Syscall/Kprobe Requirements | 11 | 51 | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| `gki-android14-6.1-manual` | GKI A14 | 6.1 | manual source/security calls | both | `n` required | `n` required | `TAMPER=n`; `KPROBES_KSUD=n` | shared | GKI 6.1 policy | `SUPPORTED; BUILD_REQUIRED` |
| `gki-android14-6.1-lsm_bl` | GKI A14 | 6.1 | LSM-list + BL/SCT | none | `y` required | `y` required | internal SCT required via BL; `TAMPER=n`; canonical `KPROBES_KSUD=n` | shared | same GKI 6.1 policy | `SUPPORTED; BUILD_REQUIRED` |
| `gki-android16-6.12-manual` | GKI A16 | 6.12 | manual source/security calls | both | `n` required | `n` required | `TAMPER=n`; `KPROBES_KSUD=n` | shared | GKI 6.12 policy | `SUPPORTED; BUILD_REQUIRED` |
| `gki-android16-6.12-lsm_bl` | GKI A16 | 6.12 | static security BL + sucompat BL/SCT | none | `y` required | `y` required | internal SCT required via BL; `TAMPER=n`; canonical `KPROBES_KSUD=n` | shared | same GKI 6.12 policy | `SUPPORTED; BUILD_REQUIRED` |
| `sultan-android14-6.1-manual` | Sultan A14 | 6.1 | manual source/security calls | both | `n` required | `n` required | `TAMPER=n`; `KPROBES_KSUD=n` | shared | Sultan 6.1 policy | `SUPPORTED; BUILD_REQUIRED` |
| `sultan-android14-6.1-lsm_bl` | Sultan A14 | 6.1 | LSM-list + BL/SCT | none | `y` required | `y` required | internal SCT required via BL; `TAMPER=n`; canonical `KPROBES_KSUD=n` | shared | same Sultan 6.1 policy | `SUPPORTED; BUILD_REQUIRED` |

All six also require built-in `CONFIG_KSU=y`, `CONFIG_KSU_SUSFS=y`, and the target's required SuSFS feature settings. `lsm_bl` additionally depends on `ARM64=y` and `KALLSYMS=y`, as enforced by xxKSU Kconfig/source. Out-of-tree module heuristics are outside this manifest; these profiles are evidenced built-in kernel profiles.

Exact four-option classification for every `lsm_bl` row:

| Option | Classification | Evidence-based reason |
|---|---|---|
| `CONFIG_KSU_LSM_SECURITY_HOOKS=y` | `REQUIRED` | Selects 6.1 `lsm_hooks_list.c` or 6.12 `lsm_hooks_static.c`. |
| `CONFIG_KSU_HACK_ARM64_BRANCH_LINK=y` | `REQUIRED` | Supplies exec/access/stat and includes the managed syscall fallback. |
| `CONFIG_KSU_TAMPER_SYSCALL_TABLE=n` | `FORBIDDEN` as an independent mode | Kconfig makes BL depend on `!KSU_TAMPER_SYSCALL_TABLE`; setting it to `y` prevents the required BL selection. |
| `CONFIG_KSU_KPROBES_KSUD=n` | `IRRELEVANT_TO_ACTIVE_PATH`, canonical `n` | xxKSU includes/initializes kprobe KSUD only if neither tamper nor BL is enabled. Pinning `n` avoids a misleading unused selection. |

For every manual row, all four values are `REQUIRED` as shown: `LSM=n` selects the global manual ABI; the other three are required `n` to prevent a hybrid or duplicate transport.

## 5. Semantic Ownership Matrix

The duplicate column describes a valid profile. Section 12 analyzes invalid mixed compositions.

### `gki-android14-6.1-manual`

| Profile | Semantic Path | Final Owner | Transport Mechanism | Handler/Equivalent | Source of Transport | Duplicate Risk | Validation Required | Confidence |
|---|---|---|---|---|---|---|---|---|
| GKI6.1 manual | exec | scope-min fixture | direct Linux source call | `ksu_handle_execveat` | `fs/exec.c` fixture | none if BL/SCT off | one call; ABI match | HIGH |
| GKI6.1 manual | access | scope-min fixture | direct Linux source call | `ksu_handle_faccessat` user-pointer ABI | `fs/open.c` fixture | none if BL/SCT off | one call; ABI match | HIGH |
| GKI6.1 manual | stat | scope-min fixture | direct syscall-source call | `ksu_handle_stat` user-pointer ABI | `fs/stat.c` fixture | none if BL/SCT off | one call plus pure 51 blocks | HIGH |
| GKI6.1 manual | fstat-return | scope-min fixture | direct return call | `ksu_handle_newfstat_ret` / `ksu_handle_fstat64_ret` | `fs/stat.c` fixture | none if probes off | one return handler | HIGH |
| GKI6.1 manual | read / init-RC | manual-security fixture | `security_file_permission` source call | `ksu_file_permission` → `ksu_install_rc_hook` | `security/security.c` fixture | none if SCT/LSM off | global symbol and one caller | HIGH |
| GKI6.1 manual | reboot / supercall | scope-min fixture + 11 | side-effect call then original syscall | `ksu_handle_sys_reboot` with 11 SuSFS dispatch | `kernel/reboot.c` fixture | none if probes/SCT off | caller contract and count | HIGH |
| GKI6.1 manual | setuid / zygote | manual-security fixture + 11 | security source call | `ksu_task_fix_setuid` → cred path → `ksu_handle_setresuid` | fixture + xxKSU manual ABI | none if LSM off | symbol, flags, one call | HIGH |
| GKI6.1 manual | input safe mode | xxKSU runtime registration | input handler registration | `vol_detector_handler` / `vol_detector_event` | xxKSU runtime | safe single owner | registration present; no official call | HIGH |
| GKI6.1 manual | SELinux AVC hiding | xxKSU runtime | slow-AVC call-site replacement | SID substitution equivalent | xxKSU selinux-hide/slow-AVC | no fixture overlap | replacement accounted | HIGH |
| GKI6.1 manual | SELinux setprocattr hiding | manual-security fixture + xxKSU | security source call to replacement | `ksu_hide_setprocattr` → inline hide | manual-security fixture | none if LSM off | global manual ABI; runtime parity | MEDIUM |
| GKI6.1 manual | SELinux fake status | xxKSU runtime registration | status fops/open replacement | fake status page | xxKSU selinux-hide | no fixture overlap | replacement present | HIGH |
| GKI6.1 manual | SELinux context/access hiding | xxKSU runtime registration | transaction fops replacement | context/access normalization | xxKSU selinux-hide | no fixture overlap | side-by-side runtime probe | MEDIUM |
| GKI6.1 manual | SuSFS stat/mount behavior | 51 | kernel semantic blocks | kstat/mount-ID/path/namespace behavior | target-specific 51 | transport-neutral | required feature inventory | HIGH |
| GKI6.1 manual | uname spoofing | 51 | `kernel/sys.c` semantic block | `susfs_spoof_uname` | target-specific 51 | transport-neutral | block and config present | HIGH |

### `gki-android14-6.1-lsm_bl`

| Profile | Semantic Path | Final Owner | Transport Mechanism | Handler/Equivalent | Source of Transport | Duplicate Risk | Validation Required | Confidence |
|---|---|---|---|---|---|---|---|---|
| GKI6.1 lsm_bl | exec | xxKSU BL | ARM64 caller patch with managed SCT fallback | BL exec wrapper → `ksu_handle_execveat` | xxKSU branch-link runtime | none without fixture | BL/SCT owner proven | HIGH |
| GKI6.1 lsm_bl | access | xxKSU BL | ARM64 caller patch with managed SCT fallback | `ksu_do_faccessat` / handler | xxKSU branch-link runtime | none without fixture | patch result or fallback active | HIGH |
| GKI6.1 lsm_bl | stat | xxKSU BL | ARM64 caller patch with managed SCT fallback | vfs stat wrapper / actual handler | xxKSU branch-link runtime | none without fixture | patch result or fallback active | HIGH |
| GKI6.1 lsm_bl | fstat-return | xxKSU syscall-table path | BL-managed early-boot replacement | actual return handlers | internal BL fallback | managed handoff | wrapper present; restore conditions | HIGH |
| GKI6.1 lsm_bl | read / init-RC | xxKSU syscall-table path | BL-managed early-boot read replacement | `ksu_handle_sys_read_fd` → install RC | internal BL fallback | managed handoff | correct conditional path | HIGH |
| GKI6.1 lsm_bl | reboot / supercall | xxKSU syscall-table path + 11 | syscall wrapper calls handler then original | `ksu_handle_sys_reboot` with 11 dispatch | internal BL fallback | none without fixture | wrapper and handler ABI | HIGH |
| GKI6.1 lsm_bl | setuid / zygote | xxKSU LSM | 6.1 LSM-list slot replacement | cred path → 11 setresuid handler | `lsm_hooks_list.c` | none without fixture | slot and original chaining | HIGH |
| GKI6.1 lsm_bl | input safe mode | xxKSU runtime registration | input handler registration | volume detector | xxKSU runtime | safe single owner | registration present | HIGH |
| GKI6.1 lsm_bl | SELinux AVC hiding | xxKSU runtime | slow-AVC replacement | SID substitution | xxKSU selinux-hide/slow-AVC | no fixture overlap | replacement accounted | HIGH |
| GKI6.1 lsm_bl | SELinux setprocattr hiding | xxKSU LSM | 6.1 LSM-list slot replacement | `ksu_setprocattr` → inline hide | `lsm_hooks_list.c` | none without fixture | slot/original chain; runtime parity | MEDIUM |
| GKI6.1 lsm_bl | SELinux fake status | xxKSU runtime registration | status fops/open replacement | fake status page | xxKSU selinux-hide | none | replacement present | HIGH |
| GKI6.1 lsm_bl | SELinux context/access hiding | xxKSU runtime registration | transaction fops replacement | context/access normalization | xxKSU selinux-hide | none | side-by-side runtime probe | MEDIUM |
| GKI6.1 lsm_bl | SuSFS stat/mount behavior | 51 | kernel semantic blocks | target SuSFS behavior | same GKI6.1 51 | transport-neutral | feature inventory | HIGH |
| GKI6.1 lsm_bl | uname spoofing | 51 | kernel semantic block | `susfs_spoof_uname` | same GKI6.1 51 | transport-neutral | block/config present | HIGH |

### `gki-android16-6.12-manual`

| Profile | Semantic Path | Final Owner | Transport Mechanism | Handler/Equivalent | Source of Transport | Duplicate Risk | Validation Required | Confidence |
|---|---|---|---|---|---|---|---|---|
| GKI6.12 manual | exec | scope-min fixture | direct source call | `ksu_handle_execveat` | fixture + 6.12 context adapter | none if automated paths off | strict adapted call/ABI | HIGH |
| GKI6.12 manual | access | scope-min fixture | direct source call | user-pointer faccessat handler | fixture + adapter | none | strict adapted call/ABI | HIGH |
| GKI6.12 manual | stat | scope-min fixture | direct source call | actual stat handler | fixture + 6.12 VFS adapter | none | one call plus 51 unique-ID blocks | HIGH |
| GKI6.12 manual | fstat-return | scope-min fixture | direct return call | actual fstat return handlers | fixture + adapter | none if probes off | one return path | HIGH |
| GKI6.12 manual | read / init-RC | manual-security fixture | security source call | manual `ksu_file_permission` | fixture + security API adapter | none | global ABI and one caller | HIGH |
| GKI6.12 manual | reboot / supercall | scope-min fixture + 11 | side-effect call then original | actual reboot handler | fixture + adapter | none | return contract/count | HIGH |
| GKI6.12 manual | setuid / zygote | manual-security fixture + 11 | security source call | manual fix-setuid → 11 | fixture + adapter | none | global ABI and one caller | HIGH |
| GKI6.12 manual | input safe mode | xxKSU runtime registration | input registration | volume detector | xxKSU runtime | safe | registration/no official symbol | HIGH |
| GKI6.12 manual | SELinux AVC hiding | xxKSU runtime | slow-AVC replacement | SID substitution | xxKSU | none | replacement accounted | HIGH |
| GKI6.12 manual | SELinux setprocattr hiding | manual-security fixture + xxKSU | adapted security source call | manual hide handler | fixture + 6.12 signature adapter | none | adapted caller and parity | MEDIUM |
| GKI6.12 manual | SELinux fake status | xxKSU runtime registration | fops/open replacement | fake status page | xxKSU | none | replacement present | HIGH |
| GKI6.12 manual | SELinux context/access hiding | xxKSU runtime registration | transaction fops replacement | lightweight replacement | xxKSU | none | runtime comparison | MEDIUM |
| GKI6.12 manual | SuSFS stat/mount behavior | 51 | 6.12 kernel semantic blocks | idmap/unique-ID/stat/mount behavior | GKI6.12 51 + adapter | neutral | feature inventory | HIGH |
| GKI6.12 manual | uname spoofing | 51 | kernel semantic block | `susfs_spoof_uname` | GKI6.12 51 | neutral | block/config present | HIGH |

### `gki-android16-6.12-lsm_bl`

| Profile | Semantic Path | Final Owner | Transport Mechanism | Handler/Equivalent | Source of Transport | Duplicate Risk | Validation Required | Confidence |
|---|---|---|---|---|---|---|---|---|
| GKI6.12 lsm_bl | exec | xxKSU BL | ARM64 call patch + SCT fallback | exec wrapper/handler | branch-link runtime | none without fixture | patch or fallback | HIGH |
| GKI6.12 lsm_bl | access | xxKSU BL | ARM64 call patch + SCT fallback | access wrapper/handler | branch-link runtime | none | patch or fallback | HIGH |
| GKI6.12 lsm_bl | stat | xxKSU BL | ARM64 call patch + SCT fallback | stat wrapper/handler | branch-link runtime | none | patch or fallback | HIGH |
| GKI6.12 lsm_bl | fstat-return | xxKSU syscall-table path | BL-managed early-boot replacement | actual return handlers | internal BL fallback | managed handoff | wrapper/restore conditions | HIGH |
| GKI6.12 lsm_bl | read / init-RC | xxKSU syscall-table path | BL-managed early-boot read replacement | read-fd handler/install RC | internal BL fallback | managed handoff | correct conditional path | HIGH |
| GKI6.12 lsm_bl | reboot / supercall | xxKSU syscall-table path + 11 | wrapper then original | actual reboot handler + dispatch | internal BL fallback | none | ABI/caller count | HIGH |
| GKI6.12 lsm_bl | setuid / zygote | xxKSU LSM | 6.12 ARM64 security-call patch | static wrapper → cred path → 11 | `lsm_hooks_static.c` | none | patch result and original call | HIGH |
| GKI6.12 lsm_bl | input safe mode | xxKSU runtime registration | input registration | volume detector | xxKSU runtime | safe | registration | HIGH |
| GKI6.12 lsm_bl | SELinux AVC hiding | xxKSU runtime | slow-AVC replacement | SID substitution | xxKSU | none | replacement accounted | HIGH |
| GKI6.12 lsm_bl | SELinux setprocattr hiding | xxKSU LSM | 6.12 ARM64 security-call patch | static setprocattr wrapper | `lsm_hooks_static.c` | none | patch result/runtime parity | MEDIUM |
| GKI6.12 lsm_bl | SELinux fake status | xxKSU runtime registration | fops/open replacement | fake status page | xxKSU | none | replacement present | HIGH |
| GKI6.12 lsm_bl | SELinux context/access hiding | xxKSU runtime registration | transaction fops replacement | lightweight replacement | xxKSU | none | runtime comparison | MEDIUM |
| GKI6.12 lsm_bl | SuSFS stat/mount behavior | 51 | 6.12 kernel semantic blocks | idmap/unique-ID/stat/mount behavior | same GKI6.12 51 | neutral | feature inventory | HIGH |
| GKI6.12 lsm_bl | uname spoofing | 51 | kernel semantic block | uname spoof | same GKI6.12 51 | neutral | block/config | HIGH |

### `sultan-android14-6.1-manual`

| Profile | Semantic Path | Final Owner | Transport Mechanism | Handler/Equivalent | Source of Transport | Duplicate Risk | Validation Required | Confidence |
|---|---|---|---|---|---|---|---|---|
| Sultan6.1 manual | exec | scope-min fixture | direct source call | exec handler | fixture + Sultan anchors | none | one adapted call | HIGH |
| Sultan6.1 manual | access | scope-min fixture | direct source call | access handler | fixture + Sultan anchors | none | one adapted call | HIGH |
| Sultan6.1 manual | stat | scope-min fixture | direct source call | stat handler | fixture + Sultan anchors | none | call plus pure 51 behavior | HIGH |
| Sultan6.1 manual | fstat-return | scope-min fixture | return call | actual return handlers | fixture + Sultan anchors | none | one return path | HIGH |
| Sultan6.1 manual | read / init-RC | manual-security fixture | security source call | manual file-permission path | fixture + Sultan anchors | none | global ABI/call count | HIGH |
| Sultan6.1 manual | reboot / supercall | scope-min fixture + 11 | side-effect call then original | reboot handler + SuSFS dispatch | fixture + Sultan anchors | none | contract/count | HIGH |
| Sultan6.1 manual | setuid / zygote | manual-security fixture + 11 | security source call | manual fix-setuid → 11 | fixture + Sultan anchors | none | ABI/count | HIGH |
| Sultan6.1 manual | input safe mode | xxKSU runtime registration | input registration | volume detector | xxKSU runtime | safe | registration; remove redundant extern | HIGH |
| Sultan6.1 manual | SELinux AVC hiding | xxKSU runtime | slow-AVC replacement | SID substitution | xxKSU | none | replacement | HIGH |
| Sultan6.1 manual | SELinux setprocattr hiding | manual-security fixture + xxKSU | security source call | manual hide handler | fixture | none | ABI/runtime parity | MEDIUM |
| Sultan6.1 manual | SELinux fake status | xxKSU runtime registration | fops/open replacement | fake status page | xxKSU | none | replacement | HIGH |
| Sultan6.1 manual | SELinux context/access hiding | xxKSU runtime registration | transaction replacement | lightweight equivalent | xxKSU | none | runtime comparison | MEDIUM |
| Sultan6.1 manual | SuSFS stat/mount behavior | 51 | kernel/vendor semantic blocks | SuSFS behavior + Sultan extensions | Sultan51 + adapter | neutral | feature/extension inventory | HIGH |
| Sultan6.1 manual | uname spoofing | 51 | kernel semantic block | uname spoof | Sultan51 | neutral | block/config | HIGH |

### `sultan-android14-6.1-lsm_bl`

| Profile | Semantic Path | Final Owner | Transport Mechanism | Handler/Equivalent | Source of Transport | Duplicate Risk | Validation Required | Confidence |
|---|---|---|---|---|---|---|---|---|
| Sultan6.1 lsm_bl | exec | xxKSU BL | ARM64 call patch + SCT fallback | exec wrapper/handler | branch-link runtime | none without fixture | patch or fallback | HIGH |
| Sultan6.1 lsm_bl | access | xxKSU BL | ARM64 call patch + SCT fallback | access wrapper/handler | branch-link runtime | none | patch or fallback | HIGH |
| Sultan6.1 lsm_bl | stat | xxKSU BL | ARM64 call patch + SCT fallback | stat wrapper/handler | branch-link runtime | none | patch or fallback | HIGH |
| Sultan6.1 lsm_bl | fstat-return | xxKSU syscall-table path | BL-managed early-boot replacement | actual return handlers | internal BL fallback | managed | wrapper/restore | HIGH |
| Sultan6.1 lsm_bl | read / init-RC | xxKSU syscall-table path | BL-managed early-boot read replacement | read-fd/install RC | internal BL fallback | managed | correct conditional | HIGH |
| Sultan6.1 lsm_bl | reboot / supercall | xxKSU syscall-table path + 11 | wrapper then original | reboot handler + dispatch | internal BL fallback | none | ABI/count | HIGH |
| Sultan6.1 lsm_bl | setuid / zygote | xxKSU LSM | 6.1 LSM-list slot replacement | cred path → 11 | `lsm_hooks_list.c` | none | slot/original chain | HIGH |
| Sultan6.1 lsm_bl | input safe mode | xxKSU runtime registration | input registration | volume detector | xxKSU runtime | safe | registration | HIGH |
| Sultan6.1 lsm_bl | SELinux AVC hiding | xxKSU runtime | slow-AVC replacement | SID substitution | xxKSU | none | replacement | HIGH |
| Sultan6.1 lsm_bl | SELinux setprocattr hiding | xxKSU LSM | 6.1 LSM-list slot replacement | setprocattr wrapper | `lsm_hooks_list.c` | none | slot/runtime parity | MEDIUM |
| Sultan6.1 lsm_bl | SELinux fake status | xxKSU runtime registration | fops/open replacement | fake status page | xxKSU | none | replacement | HIGH |
| Sultan6.1 lsm_bl | SELinux context/access hiding | xxKSU runtime registration | transaction replacement | lightweight equivalent | xxKSU | none | runtime comparison | MEDIUM |
| Sultan6.1 lsm_bl | SuSFS stat/mount behavior | 51 | kernel/vendor semantic blocks | SuSFS + Sultan extensions | same Sultan51 + adapter | neutral | feature/extension inventory | HIGH |
| Sultan6.1 lsm_bl | uname spoofing | 51 | kernel semantic block | uname spoof | same Sultan51 | neutral | block/config | HIGH |

## 6. GKI Android 14 / Linux 6.1 — Manual

Composition is exactly: clean GKI 6.1 target + transport-neutral GKI6.1 51 + xxKSU + shared 11 + both manual fixtures + the explicit all-`n` transport configuration. Phase 1.5 inspected the target functions and the pinned cheetah workflow builds this mode.

`LSM_SECURITY_HOOKS=n` is essential because it selects `lsm_hooks_manual.c`, which exports the global functions referenced by manual-security. BL, independent syscall tamper, and kprobe KSUD must be `n`; otherwise scope-min calls duplicate automated paths or its guarded reboot/fstat calls disappear into a hybrid profile. Final validation must count calls after all patches, not infer success from fixture exit status.

## 7. GKI Android 14 / Linux 6.1 — LSM/BL

Composition is clean target + the same GKI6.1 51 + xxKSU + the same 11 + no manual fixtures. `LSM_SECURITY_HOOKS=y` selects LSM-list interception for setuid, rename, bprm where enabled, and setprocattr. `HACK_ARM64_BRANCH_LINK=y` supplies exec/access/stat and its internal syscall fallback supplies reboot/read/fstat-return. The independent tamper mode is forbidden; kprobe KSUD is inactive and canonically `n`.

BL's syscall-table bootstrap and later call-site patching are one composite xxKSU owner with a managed fallback, not two project-level owners. V2 must nevertheless validate the required source/config prerequisites and treat an unaccounted patch/fallback failure as a failed profile.

## 8. GKI Android 16 / Linux 6.12 — Manual

The same manual architecture applies. The pinned popsicle workflow applies both fixture versions and builds manual 6.12.23/.69 profiles; Phase 1.5 found identical de-inline payload policy across those minors. Linux 6.12 security/VFS signatures and anchors require an adapter. In particular, the existing known-good manual-security application uses fuzz for changed security context; V2 must replace tolerance with exact adapted hunks and final caller/ABI checks.

No mode-specific 51 block is required. The GKI6.12 51 keeps idmap, unique mount ID, stat, namespace, proc, and other SuSFS semantics in both modes.

## 9. GKI Android 16 / Linux 6.12 — LSM/BL

The same GKI6.12 51 and 11 are used without fixtures. `LSM_SECURITY_HOOKS=y` selects `lsm_hooks_static.c`; this uses ARM64 call-site patching for setuid, rename, bprm, and setprocattr. BL mode supplies exec/access/stat plus the internally included syscall fallback for reboot/read/fstat-return. This is version-specific mechanism, not mode-specific 51 policy.

The target must be ARM64 with kallsyms. Every runtime patch result or retained fallback must be observable in validation; merely compiling the wrapper functions is not ownership proof.

## 10. Sultan Android 14 / Linux 6.1 — Manual

Composition matches GKI6.1 manual but uses the Sultan adapter and Sultan51. Known-good Sultan manual builds use both fixtures. Sultan-specific `try_umount`, exported loop helpers, vendor anchors, bootconfig/FUSE adaptations, and related extensions remain adapter/51 responsibilities and do not alter transport ownership.

The current repository workflow's `|| true` fixture application is not acceptable evidence in V2. V2 must require exact application and final callers; the known-good final combination supports the architecture, while the current workflow only weakly verifies it.

## 11. Sultan Android 14 / Linux 6.1 — LSM/BL

Composition uses the same Sultan51 and shared 11, no manual fixtures, the 6.1 LSM-list path, and BL's composite BL/syscall system. Sultan vendor changes do not justify a distinct transport policy. The same explicit config and validation rules as GKI6.1 lsm_bl apply.

## 12. Duplicate-Transport Analysis

An owner is a component responsible for a semantic path. BL plus its internally managed fallback is one owner with multiple mechanisms. The invalid case is adding manual providers or an independent automated mode to that owner.

| Semantic Path | Manual + required lsm_bl accidentally combined | Classification | Required V2 prevention |
|---|---|---|---|
| exec | BL/SCT wrapper invokes the handler, then the original source path reaches the fixture call and invokes it again | `DUPLICATE_CALL`, `DOUBLE_SIDE_EFFECT` | forbid scope-min when BL/tamper active; count final/static and runtime owners |
| access | automated wrapper and fixture both call the user-pointer handler | `DUPLICATE_CALL`, `DOUBLE_SIDE_EFFECT` | same; validate ABI and one owner |
| stat | automated wrapper and fixture both alter/inspect the stat path; pure 51 spoofing is separate and valid | `DUPLICATE_CALL`, `ORDER_DEPENDENT` | distinguish transport call from 51 behavior; forbid mixed transport |
| fstat-return | BL bootstrap/SCT return wrapper plus fixture return call can invoke the equivalent twice until restoration | `DOUBLE_SIDE_EFFECT`, `ORDER_DEPENDENT` | require manual automated bits `n`; validate restore path in lsm_bl |
| read / init-RC | BL/SCT read wrapper overlaps manual-security file-permission transport; with `LSM=y`, the fixture also expects global manual symbols not provided by list/static mode | `DOUBLE_SIDE_EFFECT`, `ABI_CONFLICT` | fixture absence in lsm_bl; LSM must be `n` in manual; symbol/link check |
| reboot / supercall | syscall wrapper calls the handler then original reboot enters the fixture call and calls it again | `DOUBLE_SIDE_EFFECT` | forbid BL/tamper/probe in manual and scope-min in lsm_bl |
| setuid / zygote | manual-security expects global `ksu_task_fix_setuid`; LSM mode compiles private/static interception instead; an artificially resolved mix would also run both source and LSM transports | `ABI_CONFLICT`; otherwise `DOUBLE_SIDE_EFFECT` | config/fixture compatibility check plus one final call chain |
| input safe mode | fixtures do not provide input transport; xxKSU registers one handler in both profiles | `SAFE_COEXISTENCE` | prove one registration and absence of official-only input symbols |
| SELinux AVC hiding | neither fixture duplicates the slow-AVC replacement | `SAFE_COEXISTENCE` | account for the one xxKSU replacement |
| SELinux setprocattr | manual-security expects global manual ABI while LSM modes compile private/static wrapper; adapted coexistence would invoke hide logic twice | `ABI_CONFLICT`; otherwise `DOUBLE_SIDE_EFFECT` | fixture/config compatibility and symbol check |
| SELinux fake status | one xxKSU fops replacement in either profile | `SAFE_COEXISTENCE` | one initialization path |
| SELinux context/access | one xxKSU transaction replacement in either profile | `SAFE_COEXISTENCE` | one initialization path; parity test |
| SuSFS stat/mount behavior | 51 semantics coexist with either transport by design | `SAFE_COEXISTENCE` | prove semantic block present, do not count it as KSU transport |
| uname spoofing | 51 semantics coexist with either transport | `SAFE_COEXISTENCE` | block/config presence |

Additional invalid configurations:

- `BL=y` plus `TAMPER=y` is `CONFIG_PREVENTED` by Kconfig and must be rejected rather than normalized.
- `manual` plus `KPROBES_KSUD=y` is a hybrid: scope-min compiles out reboot/fstat-return while probes own them. It is not the required manual profile and must be rejected.
- `manual` plus `TAMPER=y` is a hybrid/duplicate: manual file-permission read is compiled inactive while exec/access/stat/reboot overlap syscall-table paths.
- A final source containing official-only symbols is `ABI_CONFLICT`, not a fallback opportunity.

## 13. 11 Responsibility

11 remains responsible in all six profiles for:

- SuSFS initialization and Kconfig/control integration;
- SID helpers and SID initialization;
- zygote/no-su/umount behavior and `ksu_handle_setresuid` integration;
- SuSFS command dispatch inside actual xxKSU `ksu_handle_sys_reboot`;
- xxKSU-specific command, boot-complete, and control plumbing.

The same generated 11 serves all six profiles. Evidence: current/known-good 11 contains no `LSM_SECURITY_HOOKS`, BL, tamper, kprobe, or fixture selection; actual xxKSU's own Kconfig-controlled unity build selects manual/list/static transport around the handler behavior extended by 11. There is no evidenced mode-specific change required inside 11.

## 14. 51 Responsibility

One target-specific 51 serves both profiles for each target. It owns independent SuSFS filesystem, namespace, proc, stat/kstat, mount-ID, uname, maps, kallsyms, bootconfig, and target/vendor behavior. GKI6.12 keeps its 6.12 APIs and unique-ID semantics; Sultan keeps its vendor extensions.

51 must remove/reroute official-50 transport coupled to official 10, while preserving independently owned SuSFS blocks. It must neither add manual calls nor enable LSM/BL.

No current 51 semantic decision belongs in the mode manifest. The only mode-related-looking content, `ksu_input_hook_key_false`, is a redundant declaration with no consumer and is not valid transport policy; V2 should classify/remove it under semantic accounting, not use it to choose a profile.

## 15. Fixture Responsibility

| Fixture | Semantic paths supplied | Supported targets | Version adaptations | Expected xxKSU ABI | Config assumptions | LSM/BL overlap |
|---|---|---|---|---|---|---|
| `scope-min-manual-hooks-v2.3.patch` | exec, access, stat, native/compat fstat-return, reboot | all three manual targets | exact target anchors for 6.1/6.12/vendor drift; 6.12 VFS context; compat syscall presence | actual single exec handler; user-pointer access/stat; actual fstat-return handlers; side-effect reboot contract | `KSU=y`; BL/tamper/kprobe KSUD all `n` | direct duplicate/hybrid risk for exec/access/stat/fstat/reboot |
| `manual-security-hooks-v2.0.patch` | bprm, rename, file-permission/init-RC, setuid, setprocattr | all three manual targets | 6.1 vs 6.12 security signatures/anchors, including setprocattr/rename context; Sultan anchors | global functions from `lsm_hooks_manual.c`: `ksu_bprm_check`, `ksu_inode_rename`, `ksu_file_permission`, `ksu_task_fix_setuid`, `ksu_hide_setprocattr` | `KSU=y`, `LSM_SECURITY_HOOKS=n`, tamper `n` for file-permission behavior | ABI/link conflict with list/static LSM mode; double transport if force-combined |

The fixtures are manual transport providers, not generic compatibility patches. Known-good builds support their semantics on all three targets, but V2 must express version adaptation explicitly and reject fuzz-only/tolerated application as final proof.

## 16. Target Adapter Responsibility

Adapters may change only mechanics:

- Linux 6.1 versus 6.12 VFS and SELinux signatures;
- hunk anchors and context;
- 6.12 minor drift without policy drift;
- Sultan vendor-tree anchors and Sultan-specific SuSFS extensions;
- exact fixture adaptation while preserving its declared ABI/semantics;
- exact final-source probes appropriate to each target.

Adapters must not choose manual versus lsm_bl, classify by patch-application success, invent a handler owner, or silently turn unknown blocks into KEEP/REMOVE. The profile manifest chooses the mode and required components; the adapter maps those requirements to a target revision and must fail if it cannot do so exactly.

## 17. SELinux Dual-Mode Ownership

Replacement behavior and transport are separate:

| Domain | Replacement implementation (both modes) | Manual transport | lsm_bl transport | Confidence |
|---|---|---|---|---|
| AVC hiding | xxKSU slow-AVC SID substitution | xxKSU runtime call-site replacement | same | HIGH |
| setprocattr hiding | xxKSU selinux-hide inline behavior | manual-security `security_setprocattr` call to global manual handler | 6.1 LSM-list or 6.12 static ARM64 security-call patch | MEDIUM |
| fake status | xxKSU fake page and status fops/open replacement | xxKSU runtime initialization | same | HIGH |
| context/access hiding | xxKSU transaction fops replacement and normalization | xxKSU runtime initialization | same | MEDIUM |

The removed official-50 backup-policy architecture is replaced, not duplicated in 51. Exact context/access and setprocattr parity remains MEDIUM because no new side-by-side runtime evidence was produced. Phase 1.6 does not promote it to HIGH.

## 18. Current GKI Workflow Gap Reclassification

Classification: `MULTIPLE = TARGET_MANIFEST_GAP + WORKFLOW_VALIDATION_GAP`.

The current workflow generates and clean-applies transport-neutral 11/51 material but does not compose or build either GKI manual profile or GKI lsm_bl profile. It therefore fails to validate:

- fixture presence and manual all-`n` transport configuration;
- fixture absence and LSM/BL configuration;
- final owner/caller counts and handler ABI;
- final `.config` after Kconfig resolution;
- any final GKI build, much less both modes.

This specific gap is not evidence of a `PATCH_CONTENT_BUG`: known-good final compositions use the same disputed-path 51 policy. The current generator still has the independent semantic/fail-open defects documented in Phase 1.5, but those are not the reason the workflow validates neither GKI profile.

## 19. V2 Validation Contract

V2 must implement the smallest complete fail-closed pipeline:

1. **Patch integrity:** parse and emit syntactically valid unified/format patches.
2. **Clean application:** apply 11 and the target 51 to pinned clean xxKSU/target revisions with zero rejects; apply the profile's fixtures/adaptations exactly.
3. **Semantic accounting:** classify every relevant official 10/50 semantic block; reject silent loss and unsplit mixed blocks.
4. **Final-source ownership:** after full composition, prove exactly one owner for each transport-sensitive path, except explicitly safe coexistence; account for BL's managed fallback as one composite owner.
5. **Symbol/ABI validation:** prove required actual handlers and signatures; reject references to `ksu_handle_execveat_sucompat`, `ksu_handle_vfs_fstat`, `ksu_handle_sys_read`, and `ksu_handle_input_handle_event`.
6. **Manual validation:** require both fixtures, `LSM=n`, `BL=n`, `TAMPER=n`, `KPROBES_KSUD=n`, global manual handler symbols, and exact final caller counts.
7. **lsm_bl validation:** forbid both fixtures; require `LSM=y`, `BL=y`, `TAMPER=n`, canonical `KPROBES_KSUD=n`, ARM64/kallsyms prerequisites, and list/static/BL/internal-SCT source presence.
8. **SuSFS feature validation:** verify all pure 51 filesystem, namespace, proc, stat/mount, uname, maps, kallsyms, bootconfig, and target extension behaviors remain.
9. **SELinux replacement validation:** explicitly map every removed official domain to xxKSU; preserve MEDIUM runtime-parity requirements.
10. **Build/config validation:** run olddefconfig or equivalent, inspect the resulting `.config`, and build all six profiles. No smaller set is evidenced equivalent because 6.1/6.12 transport differs and Sultan has vendor adaptations.

Patch application is not integration verification. A profile passes only after its final tree, final config, symbols, and build pass together.

## 20. Fail-Closed Rules

Future V2 must fail when any of the following occurs:

- unknown target, profile, or transport mode;
- missing required fixture or fixture present in lsm_bl;
- any required Kconfig value cannot be proven in final `.config`;
- manual global ABI is absent or automated transport appears in manual;
- required LSM/list/static/BL/internal-SCT source is absent;
- two incompatible owners, no owner, or an unclassified temporal fallback exists;
- handler is absent or ABI-incompatible;
- an official-only symbol remains referenced;
- mixed semantic block cannot be split;
- adapter cannot resolve a required block or exact anchor;
- SELinux replacement cannot be accounted for;
- required SuSFS behavior disappears;
- final source/caller counts cannot prove ownership;
- any of the six final builds fails.

There is no fallback from UNKNOWN to KEEP/REMOVE, no conversion from one profile to the other, and no tolerated fixture failure.

## 21. Proposed Dual-Mode Target Manifest

This is a conceptual data contract, not parser/source implementation. Repetition is deliberately limited through explicit shared profile policy; every required target/profile entry remains named.

```yaml
schema: xxksu-susfs-dual-mode/v1
xxksu_ref: 0b138d6a9cfe4dc163aa05c21b1e6a14ff868230

profile_policies:
  manual:
    fixtures: [scope-min-manual-hooks-v2.3, manual-security-hooks-v2.0]
    config:
      KSU: y
      KSU_LSM_SECURITY_HOOKS: n
      KSU_HACK_ARM64_BRANCH_LINK: n
      KSU_TAMPER_SYSCALL_TABLE: n
      KSU_KPROBES_KSUD: n
    forbid: [xxksu_lsm_list, xxksu_lsm_static, xxksu_bl, independent_syscall_tamper, kprobe_ksud]
    transport:
      exec: scope_min
      access: scope_min
      stat: scope_min
      fstat_return: scope_min
      read_init_rc: manual_security
      reboot_supercall: scope_min
      setuid_zygote: manual_security
      input_safe_mode: xxksu_input_registration
      selinux_avc: xxksu_slow_avc
      selinux_setprocattr: manual_security_to_xxksu_selinux_hide
      selinux_fake_status: xxksu_selinux_hide_runtime
      selinux_context_access: xxksu_selinux_hide_runtime

  lsm_bl_6_1:
    fixtures: []
    config:
      KSU: y
      KSU_LSM_SECURITY_HOOKS: y
      KSU_HACK_ARM64_BRANCH_LINK: y
      KSU_TAMPER_SYSCALL_TABLE: n
      KSU_KPROBES_KSUD: n
    require_kernel: [ARM64, KALLSYMS]
    transport:
      exec: xxksu_bl_with_internal_sct_fallback
      access: xxksu_bl_with_internal_sct_fallback
      stat: xxksu_bl_with_internal_sct_fallback
      fstat_return: xxksu_internal_sct_fallback
      read_init_rc: xxksu_internal_sct_fallback
      reboot_supercall: xxksu_internal_sct_fallback
      setuid_zygote: xxksu_lsm_list
      input_safe_mode: xxksu_input_registration
      selinux_avc: xxksu_slow_avc
      selinux_setprocattr: xxksu_lsm_list
      selinux_fake_status: xxksu_selinux_hide_runtime
      selinux_context_access: xxksu_selinux_hide_runtime

  lsm_bl_6_12:
    fixtures: []
    config:
      KSU: y
      KSU_LSM_SECURITY_HOOKS: y
      KSU_HACK_ARM64_BRANCH_LINK: y
      KSU_TAMPER_SYSCALL_TABLE: n
      KSU_KPROBES_KSUD: n
    require_kernel: [ARM64, KALLSYMS]
    transport:
      exec: xxksu_bl_with_internal_sct_fallback
      access: xxksu_bl_with_internal_sct_fallback
      stat: xxksu_bl_with_internal_sct_fallback
      fstat_return: xxksu_internal_sct_fallback
      read_init_rc: xxksu_internal_sct_fallback
      reboot_supercall: xxksu_internal_sct_fallback
      setuid_zygote: xxksu_lsm_static_arm64
      input_safe_mode: xxksu_input_registration
      selinux_avc: xxksu_slow_avc
      selinux_setprocattr: xxksu_lsm_static_arm64
      selinux_fake_status: xxksu_selinux_hide_runtime
      selinux_context_access: xxksu_selinux_hide_runtime

targets:
  gki-android14-6.1:
    kernel: {android: 14, linux: "6.1", arch: arm64}
    patch_11: shared_xxksu_11
    patch_51_policy: gki_android14_6_1
    adapter: gki_android14_6_1
    profiles:
      manual: {policy: manual, id: gki-android14-6.1-manual}
      lsm_bl: {policy: lsm_bl_6_1, id: gki-android14-6.1-lsm_bl}

  gki-android16-6.12:
    kernel: {android: 16, linux: "6.12", arch: arm64}
    patch_11: shared_xxksu_11
    patch_51_policy: gki_android16_6_12
    adapter: gki_android16_6_12
    profiles:
      manual: {policy: manual, id: gki-android16-6.12-manual}
      lsm_bl: {policy: lsm_bl_6_12, id: gki-android16-6.12-lsm_bl}

  sultan-android14-6.1:
    kernel: {android: 14, linux: "6.1", arch: arm64, vendor: sultan}
    patch_11: shared_xxksu_11
    patch_51_policy: sultan_android14_6_1
    adapter: sultan_android14_6_1
    profiles:
      manual: {policy: manual, id: sultan-android14-6.1-manual}
      lsm_bl: {policy: lsm_bl_6_1, id: sultan-android14-6.1-lsm_bl}

validation:
  require_exact_profile: true
  require_final_source_owner_count: true
  require_final_config: true
  require_symbol_abi_check: true
  require_semantic_accounting: true
  required_builds:
    - gki-android14-6.1-manual
    - gki-android14-6.1-lsm_bl
    - gki-android16-6.12-manual
    - gki-android16-6.12-lsm_bl
    - sultan-android14-6.1-manual
    - sultan-android14-6.1-lsm_bl
```

## 22. V2 Architecture Consequences

The evidence supports the requested separation exactly:

```text
official 10 → 11 semantic transformer → transport-neutral xxKSU integration
official 50 → 51 semantic transformer → transport-neutral SuSFS kernel patch

target adapter + profile manifest
                ↓
       final composition
       ├── manual
       └── lsm_bl
                ↓
final-source + final-config + build validation
```

The simplest sufficient V2 design is therefore not two 51 generators. It is one semantic 51 policy per target family, one shared 11 policy, three mechanical adapters, and two version-aware profile policies (`manual`, `lsm_bl_6_1`, `lsm_bl_6_12`). Sultan reuses the 6.1 profile policy and adds only its adapter.

## 23. Remaining Unknowns

1. Exact SELinux setprocattr/context/access behavioral parity remains MEDIUM. Needed evidence: side-by-side runtime probes against official 50 behavior.
2. Feature-by-feature runtime logs for the designated known-good builds remain unavailable. Needed evidence: exec/access/stat/init-RC/reboot/input/SuSFS/SELinux traces.
3. Release-archive Git commit provenance remains unresolved even though Phase 1.5 inspected actual archive contents. Needed evidence: embedded source provenance.
4. BL patching is intentionally best-effort at runtime. The source proves managed syscall fallback ownership, but production validation still needs observable success/fallback state so a silent loss cannot pass.
5. Existing 6.12 manual fixture application relies on context tolerance. V2 needs exact adapter hunks and strict final-source proof.

None changes KEEP/REMOVE policy. Items 1–4 are validation/release risks; item 5 is an implementation precondition for a fail-closed adapter.

## 24. Design-vs-Implementation Readiness

Explicit answers to the required questions:

1. **Are all six profiles supported by existing evidence?** Yes, architecturally and by designated known-good build workflows; V2 must reproduce six strict builds.
2. **Can one 11 serve all six?** Yes. No mode-conditioned 11 policy is evidenced.
3. **Can one target-specific 51 serve both modes?** Yes for each of the three targets.
4. **Are the manual fixtures valid providers for all three manual targets?** Yes semantically/ABI-wise and in known-good builds; V2 must make 6.12/vendor context adaptation strict.
5. **What exact configuration activates lsm_bl?** Built-in KSU with `LSM_SECURITY_HOOKS=y`, `HACK_ARM64_BRANCH_LINK=y`, `TAMPER_SYSCALL_TABLE=n`, canonical `KPROBES_KSUD=n`, on ARM64 with kallsyms.
6. **What exact configuration prevents duplicate manual transport?** `LSM_SECURITY_HOOKS=n`, `HACK_ARM64_BRANCH_LINK=n`, `TAMPER_SYSCALL_TABLE=n`, `KPROBES_KSUD=n`, with both fixtures present.
7. **Which paths remain xxKSU-owned in both modes?** Handler implementations, input registration, AVC replacement, fake status, context/access replacement, and the runtime behind setuid/reboot; their Linux-side transport may differ.
8. **Any mode-specific paths inside 11?** No.
9. **Any mode-specific paths inside 51?** No.
10. **What does the current GKI workflow fail to validate?** Both complete final compositions, their exact configs, owner counts, ABIs, and builds.
11. **What must V2 validate after 11/51 generation?** Full composition, semantic accounting, exact owners, symbols/ABIs, final config, SuSFS/SELinux coverage, and six builds.
12. **Remaining blockers to designing V2?** None at the architecture-contract level.
13. **Remaining blockers to implementing V2?** Human acceptance of this manifest, strict target-adapted fixture rules (especially 6.12), and a concrete way to make BL success/fallback plus final configs observable and fail-closed. These must be resolved before coding is authorized; SELinux runtime parity can remain an explicit release gate rather than alter generator policy.

Thus the design boundary is stable, but immediate implementation is not yet approved or fail-closed enough to start from this report without human review.

## 25. Final Recommendation

Adopt this six-profile manifest as the V2 design contract. Preserve one shared 11 and one 51 per target, keep transport selection exclusively in the profile manifest, and require explicit values for all four transport Kconfig options. Treat BL and its internally included syscall fallback as one composite xxKSU owner, while rejecting manual/automated mixtures.

Do not implement V2 until human review accepts the manifest and the three implementation blockers in Section 24 have concrete validation rules. Do not split 51 by mode.

## 26. Confidence Report

| Area | Confidence | Basis | Remaining evidence |
|---|---|---|---|
| Six-profile architectural support | HIGH | Phase 1.5 target/source evidence plus pinned manual/LSM workflows | V2 six-build run |
| Exact manual Kconfig contract | HIGH | manual ABI selection, fixture guards, defaults, known-good configs | final `.config` artifacts |
| Exact lsm_bl Kconfig contract | HIGH | pinned Kconfig/ksu.c/list/static/BL/SCT source | final `.config` and runtime state |
| One shared 11 | HIGH | 11 payload and xxKSU config-controlled transport selection | V2 application/build |
| One target 51 for both modes | HIGH | known-good/current 51 policy and ownership separation | V2 composition/build |
| Fixture semantic ABI across targets | HIGH | fixture source, target inspection, known-good builds | strict 6.12/vendor adapter proof |
| Duplicate analysis | HIGH | direct source call chains and compile-time guards | optional runtime trace |
| BL/internal syscall handoff | HIGH for ownership, MEDIUM for runtime observability | pinned xxKSU source | explicit success/fallback telemetry validation |
| SELinux AVC/fake-status replacement | HIGH | actual xxKSU replacement | runtime confirmation optional |
| SELinux setprocattr/context/access parity | MEDIUM | actual lightweight replacement and known-good builds | side-by-side runtime tests |
| Current GKI gap classification | HIGH | workflow contains no GKI profile composition/build | none |
| Safe design readiness | HIGH | human mode decision plus complete ownership/config contract | human acceptance |
| Safe implementation readiness now | MEDIUM/NO | design is stable, but strict adapter/runtime/config validation details await approval | close Section 24 blockers |

SAFE TO DESIGN V2: YES
SAFE TO IMPLEMENT V2: NO
