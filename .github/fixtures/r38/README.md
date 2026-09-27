# GKI r38 reconstruction provenance

Scope: android16-6.12-2025-09_r38 only. This record maps the accepted output at
1f4434f742478c4ab28b2818e32fd0a606908d18 before implementation. No kernel-content
provenance remained UNKNOWN. This is a reconstruction audit, not a new general
kernel security review.

## Input ownership and dependency direction

Generation reads:
- AUTHORITATIVE_SOURCE: accepted Simonpunk Patch 50, identified by the GKI
  BASELINE and upstream-state tracked-file SHA. Current revision:
  b213c54126fb243595ce7876e91d84d6e0861fec; Patch 50 SHA-256:
  31333a67aef105ce85b43fda29f407cfa4d5585060ed12375da535a4122ea682.
- METADATA: the raw susfs-source-commit.txt Git object. Its Git object ID must
  equal the accepted revision before its committer timestamp supplies Date.
- TARGET_SOURCE: ../v2/r38-sources.json contains unpatched archive members.
  Every member was compared against the downloaded archive, authenticated before
  extraction with SHA-256 accf8f9348280116792c9608f420f8d4554da52499119a8536883c5eefd429ff.
  Archive URL/identity must agree with the r38 compatibility record in BASELINE.
- TRANSFORMATION_RULE: v2/policy/gki_r38.py and bounded namespace/task_mmu
  corrections in v2/policy/lifecycle.py.
- METADATA: GKI BASELINE and .github/upstream-state.json resolve accepted pins.

The three SuSFS core files are authenticated integration/API dependencies,
copied into the real target for validation. Their contents do not contribute
bytes to this 16-file diff; they are not claimed as byte-generator inputs.

The 50_add_susfs_in_gki-android16-6.12.patch fixture is an exact upstream source
copy. The 51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch fixture is
**TEST-ONLY HISTORICAL OUTPUT**, retained for negative lifecycle tests and
historical correction-helper tests. Neither it, the production output, nor
Midori's reference supplies generation content or metadata. The production
entry point rejects a supplied Patch 51 as an unaccepted Patch 50 input.

Old graph:
input file / prebuilt51 search / historical51 fallback
-> correct_patch51 (three files)
-> candidate (other thirteen file diffs replayed).

New graph:
accepted Patch50 + authenticated clean r38 excerpts
-> explicit retained hunks and KSU removal
-> complete-context relocation into r38 source
-> reviewed corrections
-> desired source
-> native diff + established lifecycle diff formatting
-> generated metadata and candidate.

## Hunk provenance matrix

Numbers are old-side hunk starts in the inspected production diff and upstream
Patch 50. Grouped numbers enumerate every production hunk. U=UPSTREAM_PATCH50,
D=DEINLINE_REMOVE, T=TARGET_ADAPTATION, R=REVIEWED_CORRECTION.
Every retained full upstream preimage matches the authenticated target verbatim;
where positions differ, the full-context match is unique. Repeated readdir
contexts match at their unchanged declared positions.

| File / production hunk starts | Purpose / Patch 50 source starts | Deinline action | r38 adaptation / correction | Provenance |
|---|---|---|---|---|
| fs/Makefile 22 | susfs.o / 22 | None | None | U |
| fs/namei.c 40 | SuSFS includes/declarations / 40 | None | None | U |
| fs/namei.c 1601 | lookup_dcache hidden path / 1609 | None | Full-context relocation -8 | U,T |
| fs/namei.c 1618,1627,1635 | lookup_one_qstr_excl retry/fake name / 1626,1635,1643 | None | -8 | U,T |
| fs/namei.c 1657,1665,1688 | lookup_fast RCU/ref-walk hiding / 1665,1673,1696 | None | -8 | U,T |
| fs/namei.c 1709,1723,1736 | __lookup_slow hiding/revalidation / 1717,1731,1744 | None | -8 | U,T |
| fs/namei.c 2050,2361,2552 | walk_component/link_path_walk/lookup_last state / 2058,2369,2560 | None | -8 | U,T |
| fs/namei.c 3506,3652 | lookup_open/open_last_lookups hiding / 3514,3660 | None | -8 | U,T |
| fs/namei.c 3879,3895,3929 | tmpfile/O_PATH/path_openat redirect / 3887,3903,3937 | None | -8; retain upstream nested filename_lookup and old_name restore, declaration ordering only | U,T |
| fs/namei.c 5243,5252,5268 | vfs_readlink redirect spoofing / 5251,5260,5276 | None | -8 | U,T |
| fs/namespace.c 33,73 | declarations/unique-ID counter / 33,82 | None | Full-context relocation | U,T |
| fs/namespace.c 248,256 | mnt_free_id special guard/group-ID allocation / 257,265 | None | Full-context relocation | U,T |
| fs/namespace.c 305 | both special mount allocators / 315 | None | Upstream context at r38 306; fresh diff chooses 305 | U,T |
| fs/namespace.c 801,1203 | lookup/create mount handling / 810,1212 | None | Full-context relocation | U,T |
| fs/namespace.c 1285,1303 | clone allocation and flags / 1294,1313 | None | Retain upstream immutable boolean; clear inherited provenance flag; declaration block separation | U,T,R |
| fs/namespace.c 1342 | clone out_free / no upstream error-path guard | None | Existing fix_namespace guards non-IDA IDs before flags initialize | R |
| fs/namespace.c 1548,3960,5446 | ID lookup/copy namespace/listmount / 1557,3990,5485 | None | Full-context relocation | U,T |
| fs/namespace.c 5852 | three non-sus mount lookup helpers / 5911 | Keep helpers despite generic converter dropping this hunk | Reviewed locked traversal/root validation instead of upstream early returns | U,T,R |
| fs/notify/fdinfo.c 12,22,67,78 | includes/callback context/inotify spoofing / 12,23,73,84 | None | Full-context relocation | U,T |
| fs/proc/base.c 100,1829,1838,2460 | declarations/readlink redirect/map_files hiding / same starts | None | None | U |
| fs/proc/bootconfig.c 12 | bootconfig spoofing / 12 | None | None | U |
| fs/proc/fd.c 15,54 | declarations/seq_show stat and mount spoofing / same starts | None | None | U |
| fs/proc/task_mmu.c 26,452,465 | includes/maps kstat, redirect and hiding / 27,454,467 | None | Context relocation; retain target blank-line separation | U,T |
| fs/proc/task_mmu.c 1213 | shared smap_gather_stats guard / new correction | None | Guard every caller, including lock-reacquire partial gather | R |
| fs/proc/task_mmu.c 1304,1363,1429 | smaps/rollup ordinary and case4 guards / 1329,1388,1454 | None | Full-context relocation | U,T |
| fs/proc/task_mmu.c 2144,2230 | VMA-bounded pagemap helper and caller / 2246,2255 | Replace upstream chunk-start skip | Existing fix_task_mmu removes old VMA local, emits zero entries per hidden page and walks visible spans | U,T,R |
| fs/proc_namespace.c 12,235,301 | declarations/three filtered mount displays/callers / same starts | None | None | U |
| fs/readdir.c 22 | include / 22 | None | None | U |
| fs/readdir.c 175,185,196,228 | old_readdir callback state/filter/caller / same starts | None | None | U |
| fs/readdir.c 252,267,282,321 | getdents callback state/filter/caller / same starts | None | None | U |
| fs/readdir.c 340,354,364,404 | getdents64 callback state/filter/caller / same starts | None | None | U |
| fs/readdir.c 432,443,454,486 | compat old_readdir / same starts | None | None | U |
| fs/readdir.c 504,519,534,572 | compat getdents / same starts | None | None | U |
| fs/stat.c 20 | mixed declarations / 20 | Remove only KSU extern block, retain SuSFS include/KSTAT declarations | Generic whole-hunk exclusion is incorrect here | U,D |
| fs/stat.c 162,250,258 | getattr/statx spoofing / same starts | Remove upstream 227 fstat and 304 stat KSU call hunks | None | U,D |
| fs/statfs.c 9,69,87 | declarations/wrappers/statfs spoofing / same starts | None | None | U |
| fs/super.c 37,1206 | declarations/minor-ID allocation / 37,1191,1206 | None | Move declarations to includes; no behavior change | U,T |
| kernel/kallsyms.c 31,748 | include/symbol hiding / same starts | None | None | U |
| kernel/sys.c 1326 | uname spoofing / 1326 | Remove 678/692 KSU setresuid declarations/call | None | U,D |
| mm/memory.c 79,6837 | include/remote access hook / 79,6829 | None | Full-context relocation +8 | U,T |

Evidence: accepted Patch 50 hunks, authenticated r38 full file preimages, and
existing fix_namespace/fix_task_mmu rules. The locked-helper policy is also
explicit in REVIEWED_LIFECYCLE_DIFFERENCES in reference_cross_check.py. Current
production is used only to compare the independently constructed postimages.

Excluded upstream files are drivers/input/input.c, fs/exec.c, fs/open.c,
fs/read_write.c, kernel/reboot.c and security/selinux/{avc.c,hooks.c,selinuxfs.c,
ss/services.c}. Their additions are Official-KSU input/exec/access/read/reboot/
SELinux integration owned by xxKSU (DEINLINE_REMOVE). No SuSFS-only file from the
16-file set is excluded. The generic converter's extra input.c extern is omitted.

## Why the generic path fails

The strict source applier trusts upstream old_start. namei's first substantive
lookup hunk is at upstream 1609 but r38 1601; full old-side text is identical.
This is target-preimage placement drift, not a filename_lookup API mismatch.
Other files have different nonuniform shifts, enumerated above.

The generic converter additionally drops a mixed SuSFS/KSU stat declaration
hunk and the three namespace helpers; it adds an unwanted KSU input extern.
The bounded r38 path therefore selects accepted Patch 50 hunks explicitly and
matches complete preimages before constructing source. It never fixes offsets
in an emitted patch. Final diffs are generated from real pre/postimages.

## Metadata and migration review

GENERATED_METADATA: From/Subject are repository mail policy; Date is accepted
committer time in UTC; native Git computes index IDs, function headings and
diffstat; the established lifecycle diffs use difflib; trailer is empty.

Old Date: Thu, 24 Sep 2026 10:00:00 +0800.
Canonical Date: Fri, 25 Sep 2026 17:48:27 +0000.

Three old postimage index IDs were stale despite correct hunk content:
- fs/stat.c: f30b435ad1fa -> 8e2cf2b05d23
- fs/statfs.c: 6975513ebc36 -> aa6655c83140
- kernel/sys.c: 811b1afa2310 -> b3e62ed0639a

Those values are calculated Git blob IDs, not transformation constants.
All hunks and all 16 resulting source files are identical to accepted production.
Only Date and those three generated index lines change. No UNKNOWN content or
unreviewed C change is being carried forward.

Old artifact SHA-256:
9422b190e17145ee13cab48311110de5d76b1dc4a1518c9314dff8b16002e326.
Reconstructed artifact SHA-256:
d299ac9c2585a991c2a10c9b2315da35f927dd89ad2c2d47c689fb51cab0e97f.

Publication, if authorized, belongs exclusively to the normal atomic Patch 51
Actions workflow. This reconstructor never writes production.

## Verification ownership

test_provenance removes final outputs before two independent process executions,
then compares full candidate bytes with accepted output. It rejects empty/missing
Patch 50, changed retained and deinlined input, missing/changed r38 context and
tampered source commit metadata. No golden constructs its inputs.
test_lifecycle executes current generated GKI C against native target contracts.
The historical fixture remains only to demonstrate the original failures.
