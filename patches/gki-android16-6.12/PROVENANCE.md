# GKI Android 16 / 6.12 patch-51 provenance

## Status: historical evidence only

`51_deinlined_susfs_hooks_gki-android16-6.12.patch` was added by commit
`939d95f4932f532004653d52ab0ab47e62cdb013`. Its generation workflow named:

- kernel archive: `https://github.com/yapixel/gki-build-assets/releases/download/android16-6.12-2025-06_r58/common-android16-6.12-2025-06_r58.tar.gz`
- SuSFS branch: `gki-android16-6.12`

Neither input was recorded with an immutable content identity. The archive currently
served at that URL does not match the patch preimage (for example,
`drivers/input/input.c` expects Git blob prefix `78be582b5766`). Therefore the
current `2025-06_r58` archive must not be accepted as the historical authoritative
bundle, and the stored patch is not sufficient provenance for production
validation.

A new production baseline must be generated from newly pinned inputs and bind, at
minimum:

- release/ref identity;
- archive/content SHA-256;
- source-bundle identity;
- hashes of every retained source file;
- pinned SuSFS commit;
- fixture identity.

Until those records exist and strict patch application succeeds, GKI 6.12
baseline validation remains blocked. Do not reconstruct the missing historical
baseline from patch context.
