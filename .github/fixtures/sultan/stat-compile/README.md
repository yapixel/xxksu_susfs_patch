# Sultan stat.c declaration regression

This is a **target-source test fixture**, never generator input or a final patch.
It contains the real ARM64 include closure for the complete `fs/stat.c`
translation unit: 616 byte-identical target headers, 31 Kbuild-generated headers
and configuration files, and accepted Simonpunk `include/linux/susfs_def.h`.
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
