# Sultan fixture roles

- 50_add_susfs_in_gki-android14-6.1.patch: accepted authoritative Patch 50 snapshot.
- susfs-source-commit.txt: raw accepted Simonpunk Git commit object. The generator
  verifies its Git object ID against BASELINE.json and uses its committer epoch
  for the UTC mail Date. This is source provenance, not output metadata replay.
- 51_deinlined_susfs_hooks_sultan-android14-6.1.patch: historical output retained
  for lifecycle correction regressions. Production generation must not read it.
