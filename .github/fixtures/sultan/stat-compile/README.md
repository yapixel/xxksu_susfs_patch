# Sultan declaration and mount-helper link regression

This is a **target-source test fixture**, never generator input or a final patch.
It contains the real ARM64 include closure for complete `fs/stat.c`,
`fs/namespace.c`, `fs/susfs.c`, `fs/statfs.c`, and `fs/proc/fd.c` translation units.
All source headers match the authenticated target or accepted SuSFS input; output
headers/configuration are captured Kbuild results.
`provenance.json` records source identities, archive/per-file hashes, compiler
flags, and the capture command. No SuSFS symbols or kernel types are invented.

## Capture and scope

1. Download the Sultan archive identified by the active BASELINE and authenticate
   its SHA-256 **before** extraction.
2. Copy `susfs_def.h` from the accepted Simonpunk revision. Its SHA must match
   upstream-state. The other SuSFS core files are needed for full patch application.
3. Use the existing Clang 14 toolchain and `make ARCH=arm64 LLVM=-14 defconfig`.
   Compile `fs/stat.o` with the Kbuild command recorded in provenance. This enables
   both `CONFIG_KSU_SUSFS` and `CONFIG_KSU_SUSFS_SUS_KSTAT` through KCFLAGS.
4. Replay `out/fs/.stat.o.cmd` with `-M` instead of `-c -o ...` to collect its
   dependency closure. Copy those files plus `out/.config`, excluding `fs/stat.c`.
   Preserve relative source/output paths; verify source headers against the
   authenticated archive. Store sorted regular files with zero tar metadata and
   gzip mtime=0. Keep only preprocessing/type options for the syntax-only oracle.

The test reconstructs and applies the real generator's stat diff to the accepted
native source, then compiles the **entire generated stat.c** against these headers
using Clang's ARM64 target. It checks SUSFS+KSTAT enabled, SUSFS alone, and both off.
No compiler availability skip is allowed. This checks declarations and C types,
not linkage, runtime semantics, or the user's complete device configuration.
Future accepted target/header changes require recapturing this explicit fixture.

## Confirmed defect and correction

The converter's whole-hunk `ksu_handle_` exclusion discarded a mixed `fs/stat.c`
header hunk. It retained KSTAT call sites while removing `susfs_def.h` and the two
local externs already provided by accepted Patch 50. The correction removes only
the exact KSU transport-declaration block and retains upstream SuSFS dependencies.
It adds eight lines; KSTAT runtime code is unchanged. GKI already splits this hunk.

The prior literal scanner checked quoting; provenance tests checked deterministic
reconstruction/golden equality; lifecycle tests compiled selected functions with
bounded API mocks. None compiled `fs/stat.c` with its real include context. They
could all pass while this declaration surface was missing.

Local Kbuild reproduced the production errors and compiled the corrected ARM64
`fs/stat.o`. Removing the generated include, either local extern, the real header's
UID helper, or either STATX macro fails the new compile oracle; restoration passes.
Full device kernel build/boot remains pending user rebuild.

## Confirmed full-link omission

The separate `CONFIG_KSU_SUSFS`-only hunk heuristic discarded the final Sultan
`fs/namespace.c` hunk containing `susfs_get_non_sus_mnt_id_from_mnt` and
`susfs_get_non_sus_vfsmnt_from_vfsmnt`. This is a FUNCTION_DEFINITION_OMISSION
caused by ownership misclassification: **this hunk contains no inline KSU
transport**. Calls/externs in other hunks and accepted `fs/susfs.c` survived.
The converter now preserves Sultan namespace base-SUSFS hunks while retaining
its explicit KSU transport filter. Both bodies come directly from Patch 50,
including their native mount hash lock, parent walk and reference accounting.

The existing compile test additionally compiles the four complete generated
mount/core/caller translation units to ARM64 objects with SUSFS, SUS_MOUNT and
SUS_KSTAT enabled. It links them with LLD and `ASSERT(DEFINED(...))` for both
reported missing helpers. Plain `ld -r` alone would permit undefined symbols;
the assertions make these omissions fatal. No implementations are supplied by
the test. Definitions must come from generated namespace.c. This also rejects
duplicate definitions. Native kernel/xxKSU dependencies outside this bounded
aggregate are deliberately not stubbed or claimed resolved.

Capture the expanded header closure by replaying all four Kbuild commands with
`-M`, as for stat.c. Do not store patched .c files or patched susfs.h in this
fixture: the regression obtains those from actual reconstruction. The recorded
`link_capture_command` builds actual target objects. The test's portable Clang
flags retain the target preprocessing/type context and compile at O2.

Local real Kbuild objects reproduce both undefined symbols with the old
production namespace.c and satisfy the same LLD assertions after restoration.
Removing either body, leaving externs only, or restoring the old hunk filter
must fail the regression. Restoring generated definitions passes. A successful
aggregate link is not a full vmlinux layout/boot result: the user's GOT/PLT and
ID-map diagnostics require the user's full build rerun, not linker-script edits.

The prior 253-test clean-room and native stat.o check covered reconstruction and
translation-unit declarations; neither required link-time definitions. An extern
is enough to compile a call, so all could pass despite missing namespace bodies.
This extends the existing authoritative oracle across that specific boundary.

### Bounded external SuSFS closure (accepted Sultan)

The added extern/caller inventory in all 18 patched files resolves as follows:

- `fs/susfs.c`: `susfs_fake_qstr_name`, `susfs_get_data_path`,
  `susfs_is_inode_sus_path` (SUS_PATH); `susfs_is_inode_sus_kstat` and
  `susfs_sus_kstat_spoof_{generic_fillattr,inotify_fdinfo,proc_fd_seq_show,show_map_vma,vfs_statfs}`
  (SUS_KSTAT); `susfs_open_redirect_spoof_{do_proc_readlink,do_sys_openat,show_map_vma_srcu,vfs_readlink}`
  and `susfs_srcu_open_redirect` (OPEN_REDIRECT);
  `susfs_is_hide_sus_mnts_for_non_su_procs_enabled` (SUS_MOUNT);
  `susfs_is_fake_cmdline_or_bootconfig_buffer_set` and
  `susfs_spoof_cmdline_or_bootconfig` (SPOOF_CMDLINE_OR_BOOTCONFIG);
  `susfs_is_uname_spoof_buffer_set` and `susfs_spoof_uname` (SPOOF_UNAME);
  `susfs_is_sdcard_android_data_not_decrypted` (base SUSFS).
- Generated `fs/namespace.c`: the two restored mount helpers (base SUSFS).
- Native xxKSU plus Patch 11: `susfs_is_current_ksu_domain`; core's existing
  `setup_selinux`/`ksu_cred` dependencies remain xxKSU-owned.
- Accepted `susfs_def.h`: current-app/proc helpers and `susfs_starts_with` are
  static inline, not missing external definitions.
- Generated `fs/statfs.c`: core's `statfs_by_dentry_wrapper` and
  `calculate_f_flags_wrapper` resolve locally in the aggregate.
- Allocation, pagemap, mount-show and statfs helpers are static in their own
  translation units. No additional unresolved added SuSFS external was found.

GKI already retains its namespace definitions through explicit reconstruction;
its reviewed locked-lookup bodies differ from Sultan's native early-return
bodies. No GKI code or Patch 11 is changed by this correction.
