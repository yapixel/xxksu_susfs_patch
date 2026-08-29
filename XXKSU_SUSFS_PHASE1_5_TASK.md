Continue Task — Phase 1.5 Verification

Resume from the completed Phase 1 analysis.

The Phase 1 report has already been completed and saved.

Do NOT restart Phase 1.

Do NOT implement anything yet.

Do NOT modify:

- current Python generators
- current 11/51 patches
- workflows
- kernel source
- xxKSU source
- SuSFS source
- any existing repository file

This is still an ANALYSIS-ONLY phase.

You MAY create exactly one new file at the end:

"./XXKSU_SUSFS_PHASE1_5_REPORT.md"

Do not create or modify any other file.

---

1. Main Objective

The Phase 1 report exposed important findings, but the exact de-inline boundary is still internally inconsistent.

The goal of Phase 1.5 is to prove exactly:

1. Which Linux kernel call sites must exist for xxKSU.
2. Which Linux kernel call sites must be removed.
3. Which component owns each call site.
4. Which call sites come from official upstream 50.
5. Which call sites come from xxKSU itself.
6. Which call sites come from target-specific fixtures.
7. Which call sites are target-specific.
8. Whether current 51 removes a call site without providing another caller.
9. Whether current 51 removes pure SuSFS behavior by mistake.
10. What the actual semantic meaning of "de-inline" is in this repository.

Do not infer these answers from the current generator.

Prove them from actual source and patch evidence.

---

2. Correct the Hook Terminology First

The Phase 1 report incorrectly blurred several distinct mechanisms.

These must be treated separately:

- manual Linux source call-site hook
- direct "ksu_handle_*()" call
- static-key-gated call site
- LSM/security hook
- kprobe hook
- syscall-table modification
- runtime registration
- fixture-provided manual hook
- handler implementation

A direct call such as:

ksu_handle_execveat(...);

inserted into:

fs/exec.c

is a Linux source call site / manual source hook.

It is NOT automatically:

- a kprobe hook
- a syscall-table hook
- a runtime-registered hook

unless actual source proves that mechanism.

For every path investigated below, clearly separate:

Linux caller
→ gating mechanism if any
→ handler
→ xxKSU implementation
→ SuSFS behavior

Do not use the generic word "hook" when doing so hides important architectural distinctions.

---

3. Resolve the Main Phase 1 Contradiction

Phase 1 currently contains three statements that cannot all be true without qualification.

Claim A

Upstream 50 "ksu_handle_*" call sites duplicate/conflict with xxKSU and therefore must be de-inlined.

Claim B

Many of those same "ksu_handle_*" call sites actually need to remain.

Claim C

51 owns Linux-side "ksu_handle_*" call sites.

Resolve this contradiction.

There must be one consistent ownership model.

Do NOT assume:

ksu_handle_* == REMOVE

and do NOT assume:

ksu_handle_* == KEEP

The decision must be based on actual call-path ownership.

---

4. Official Upstream 50 Sources

Use the following official simonpunk/susfs4ksu patches as the primary upstream 50 references.

These are UPSTREAM SEMANTIC TRUTH for their respective targets.

Sultan / Shiba Android 14 / Linux 6.1

Branch:

sultan-shiba-susfs-minimal

Patch:

https://gitlab.com/simonpunk/susfs4ksu/-/blob/sultan-shiba-susfs-minimal/kernel_patches/50_add_susfs_in_gki-android14-6.1.patch?ref_type=heads

GKI Android 14 / Linux 6.1

Branch:

gki-android14-6.1

Patch:

https://gitlab.com/simonpunk/susfs4ksu/-/raw/gki-android14-6.1/kernel_patches/50_add_susfs_in_gki-android14-6.1.patch?ref_type=heads

GKI Android 16 / Linux 6.12

Branch:

gki-android16-6.12

Patch:

https://gitlab.com/simonpunk/susfs4ksu/-/blob/gki-android16-6.12/kernel_patches/50_add_susfs_in_gki-android16-6.12.patch?ref_type=heads

Do NOT assume these three upstream 50 patches are semantically identical.

Compare them independently.

---

5. Additional Known-Good References

The following patches are known-good, previously tested working references.

Treat them as:

VALIDATED BEHAVIORAL REFERENCES

NOT as upstream ground truth.

They prove that a particular combination was capable of working.

They do NOT automatically prove that every transformation inside them is architecturally optimal or future-proof.

Known-good xxKSU 11

all kernel shared this single 11 patch

https://github.com/yapixel/cheetah_ksu_workflow/blob/main/.github/patches/xxksu/11_enable_susfs_for_ksu.patch

Known-good Sultan Android 14 / Linux 6.1 51

https://github.com/yapixel/cheetah_ksu_workflow/blob/main/.github/patches/xxksu/51_deinlined_susfs_hooks_sultan-android14-6.1.patch

Known-good GKI Android 14 / Linux 6.1 51

https://github.com/yapixel/cheetah_ksu_workflow/blob/main/.github/patches/xxksu/51_deinlined_susfs_hooks_gki-android14-6.1.patch

Known-good GKI Android 16 / Linux 6.12.23 51

https://github.com/yapixel/popsicle_ksu_workflow/blob/popsicle-xxksu/.github/patches/xxksu/51_deinlined_susfs_hooks_gki-android16-6.12.23.patch

Known-good GKI Android 16 / Linux 6.12.69 51

https://github.com/yapixel/popsicle_ksu_workflow/blob/popsicle-xxksu/.github/patches/xxksu/51_deinlined_susfs_hooks_gki-android16-6.12.69.patch

---

6. Evidence Priority

Use evidence in this order:

1. Actual target kernel source
2. Actual backslashxx/KernelSU source
3. Official simonpunk/susfs4ksu 10/50 patches
4. Actual fixture patches
5. Known-good tested 11/51
6. Current generated 11/51
7. Current Python generator
8. README/documentation

Important:

Current generated 11/51 are NOT ground truth.

Current Python generators are NOT ground truth.

Known-good patches are strong behavioral evidence, but NOT upstream semantic truth.

README wording is NOT architectural proof.

If two evidence sources conflict, explicitly document the conflict.

Do not silently choose the implementation used by the current generator.

---

7. Build the Complete Call-Site Ownership Matrix

Investigate at least these handlers:

- "ksu_handle_execveat"
- "ksu_handle_execveat_sucompat"
- "ksu_handle_faccessat"
- "ksu_handle_stat"
- "ksu_handle_vfs_fstat"
- "ksu_handle_sys_read"
- "ksu_handle_sys_reboot"
- "ksu_handle_setresuid"
- "ksu_handle_input_handle_event"

Produce this table:

Handler| Definition Owner| Official 50 Call Site| Clean Target Caller| xxKSU Native Caller| Fixture Caller| GKI 6.1 Final Path| GKI 6.12 Final Path| Sultan 6.1 Final Path| Should 51 Contain It?| Evidence| Confidence

For every handler answer all of the following.

A. Definition

Where is the handler actually defined?

Identify:

- repository
- file
- function
- purpose

B. Clean target

Before applying 50/51:

Does the clean target kernel already contain a caller?

If no, explicitly write:

NO PRE-EXISTING CALL SITE

C. xxKSU ownership

Does xxKSU itself actually provide the Linux-side caller?

Do NOT confuse:

handler definition

with:

call-site ownership

A function existing in xxKSU does not mean Linux will ever invoke it.

Find the caller.

D. Fixture ownership

Determine whether the call site is supplied by:

- "scope-min-manual-hooks-v2.3.patch"
- "manual-security-hooks-v2.0.patch"
- another fixture
- vendor kernel source
- official 50
- generated 51

Identify the exact file and relevant semantic block.

E. Duplicate test

If official 50's call site remains:

Does another path invoke the same handler?

Prove the second path.

If no second caller exists, do NOT classify it as duplicate.

F. Removal test

If official 50's call site is removed:

What exact path still invokes the handler?

If none exists, classify:

FUNCTIONAL GAP

If evidence is insufficient:

UNRESOLVED

---

8. Verify Each Target Independently

Do NOT assume Sultan and GKI use the same mechanism.

Perform independent analysis for:

Target A

GKI Android 14 / Linux 6.1

Target B

GKI Android 16 / Linux 6.12

Also distinguish 6.12.23 vs 6.12.69 where known-good reference differences matter.

Target C

Sultan Android 14 / Linux 6.1

---

9. GKI Call-Path Verification — HIGH PRIORITY

Phase 1 identified possible functional gaps in current GKI 51.

Trace these paths completely.

exec

Linux exec path
→ ?
→ ksu_handle_execveat
→ xxKSU implementation

Also trace:

ksu_handle_execveat_sucompat

if separate.

access

Linux faccessat path
→ ?
→ ksu_handle_faccessat
→ xxKSU

stat

Linux stat path
→ ?
→ ksu_handle_stat
and/or
→ ksu_handle_vfs_fstat
→ xxKSU

read/init RC

Linux read path
→ ?
→ static key if applicable
→ ksu_handle_sys_read
→ xxKSU runtime

reboot/supercall

Linux reboot path
→ ?
→ ksu_handle_sys_reboot
→ xxKSU supercall
→ SuSFS command dispatch

setuid

Possible mechanisms include:

kernel/sys.c
→ ksu_handle_setresuid

or:

security/security.c
→ ksu_task_fix_setuid
→ ksu_handle_setresuid_cred
→ ksu_handle_setresuid

Determine the actual path.

input

Linux input event
→ ?
→ static key if applicable
→ ksu_handle_input_handle_event
→ xxKSU safe-mode behavior

For every unresolved "?", explicitly classify:

UNRESOLVED

If no caller exists:

FUNCTIONAL GAP

Do not invent an implicit xxKSU caller.

---

10. Sultan Call-Path Verification

Perform the same tracing for Sultan Android 14 / Linux 6.1.

Explicitly identify what is supplied by:

- official Sultan 50
- generated 51
- clean Sultan kernel
- "scope-min-manual-hooks-v2.3.patch"
- "manual-security-hooks-v2.0.patch"
- xxKSU
- Sultan-specific compatibility chunks

Determine whether the architecture is:

official 50 caller
→ removed during 50→51
→ restored by fixture
→ final kernel has exactly one caller

If so, prove it for each affected handler.

Do not generalize Sultan behavior to GKI.

---

11. Determine the Exact Meaning of "De-Inline"

After the ownership analysis, define what de-inline actually means in THIS repository.

Answer explicitly:

1. Does de-inline mean removing traditional KSU manual source call sites?
2. Does it mean removing only duplicate call sites?
3. Does it mean replacing direct calls with LSM paths?
4. Does it mean delegating caller ownership to fixture patches?
5. Is de-inline target-specific?
6. Is Sultan fundamentally different from GKI?
7. Are some "ksu_handle_*" calls valid and required?
8. Are static-key-gated calls part of valid xxKSU architecture?
9. Is function name alone ever enough to classify a call site?
10. Which component ultimately owns Linux caller insertion?

Do not derive this definition from the script name.

Derive it from actual working architecture.

---

12. SELinux Exclusion Verification

Current 51 generation excludes some or all of:

- "security/selinux/avc.c"
- "security/selinux/hooks.c"
- "security/selinux/selinuxfs.c"
- "security/selinux/ss/services.c"

Audit every official-50-added semantic block.

For every block classify exactly one of:

PURE_SUSFS_KEEP
DUPLICATE_XXKSU_REMOVE
TARGET_COMPAT_REPLACE
CURRENT_51_BUG
UNKNOWN

Determine whether current 51 loses or reroutes:

- AVC log spoofing
- SELinux hide
- fake SELinux status
- "setprocattr"
- "write_context"
- "write_access"
- 6.12-specific SELinux policy behavior

Do NOT infer breakage only because the original file disappeared.

Search for equivalent implementation elsewhere.

If no equivalent exists, then classify the loss accordingly.

---

13. Focused Mixed-File Audit

Audit these files at semantic-block level:

- "fs/exec.c"
- "fs/open.c"
- "fs/stat.c"
- "kernel/sys.c"
- "fs/read_write.c"
- "kernel/reboot.c"
- "drivers/input/input.c"

For every official 50 semantic addition classify:

KEEP
DEINLINE
REROUTE
TARGET_COMPAT
DUPLICATE
UNKNOWN

Do NOT classify an entire file based on one line.

Do NOT drop an entire hunk merely because it contains:

ksu_handle_*

For every mixed block show:

Official upstream semantic block
├── SuSFS functionality
│     → KEEP / ADAPT
│
├── KSU caller
│     → KEEP / DEINLINE / REROUTE
│
├── static-key gate
│     → KEEP / REMOVE / ADAPT
│
└── target/version context
      → TARGET_COMPAT

---

14. Re-evaluate fs/exec.c

This is one of the most important files.

Do not assume the official 50 implementation is a simple unconditional:

ksu_handle_execveat(...)

Inspect the actual current upstream 50 logic.

Identify all relevant conditions such as:

- static keys
- "ksu_execveat_hook"
- "ksu_su_compat_enabled"
- "susfs_is_boot_completed_triggered"
- "susfs_is_current_proc_umounted"
- SuSFS-specific bypass/guard logic

Separate:

SuSFS semantic behavior

from:

KSU transport/caller behavior

Then compare:

official 50
→ known-good 51
→ current generated 51
→ actual final target kernel path

for every target.

---

15. Re-evaluate fs/open.c

Perform the same semantic separation for:

ksu_handle_faccessat

and any SuSFS-specific logic in the same block.

Determine whether current de-inline removes:

- only the KSU caller
- or also required SuSFS semantics

---

16. Re-evaluate fs/stat.c

Trace both:

ksu_handle_stat

and:

ksu_handle_vfs_fstat

Determine independently whether each must remain, disappear, or be provided elsewhere.

Do not assume both have the same ownership.

---

17. Re-evaluate fs/read_write.c

Determine whether:

ksu_handle_sys_read(...)

is:

- a traditional caller that should be removed
- a valid static-key-gated xxKSU caller
- fixture-owned
- target-specific
- missing after current 51

Trace the complete call path for all targets.

---

18. Re-evaluate kernel/reboot.c

Trace:

ksu_handle_sys_reboot(...)

for all targets.

Remember:

The handler being defined in 11 does NOT mean a caller exists.

Determine:

- official 50 caller
- clean kernel caller
- fixture caller
- final known-good caller
- final current 51 caller

If Sultan gets this via scope-min but GKI does not, state that explicitly.

---

19. Re-evaluate kernel/sys.c / setuid

Trace the actual setuid path for all targets.

Possible designs:

kernel/sys.c
→ ksu_handle_setresuid

or:

security/security.c
→ LSM/manual security hook
→ ksu_task_fix_setuid
→ ksu_handle_setresuid_cred
→ ksu_handle_setresuid

Determine which mechanism each target actually uses.

Then classify removal of the official 50 "kernel/sys.c" caller as:

CORRECT_DEINLINE
DUPLICATE_REMOVAL
TARGET_SPECIFIC_REROUTE
FUNCTIONAL_GAP
UNKNOWN

---

20. Re-evaluate drivers/input/input.c

Phase 1 identified uncertainty around the input path.

Determine:

1. What official 50 expects.
2. What xxKSU expects.
3. What GKI provides.
4. What Sultan provides.
5. What known-good 51 does.
6. What current generated 51 does.
7. Whether safe-mode volume-key detection remains functional.
8. What "ksu_input_hook_key_false" actually does.
9. Whether current stub logic has a real consumer.

Classify current behavior:

CORRECT
TARGET_COMPAT
REDUNDANT
FUNCTIONAL_GAP
UNKNOWN

Provide evidence.

---

21. Known-Good Reference Differential

Add a dedicated section named:

Known-Good Reference Differential

For every disputed semantic path compare:

official upstream 50
        ↓
known-good 51
        ↓
current generated 51
        ↓
actual final target path

At minimum compare:

- "fs/exec.c"
- "fs/open.c"
- "fs/stat.c"
- "fs/read_write.c"
- "kernel/reboot.c"
- "kernel/sys.c"
- "drivers/input/input.c"
- "security/selinux/avc.c"
- "security/selinux/hooks.c"
- "security/selinux/selinuxfs.c"
- "security/selinux/ss/services.c"

For every difference classify:

DEINLINE_POLICY
SUSFS_SEMANTIC_CHANGE
XXKSU_COMPAT
KERNEL_VERSION_COMPAT
VENDOR_COMPAT
PATCH_CONTEXT_ONLY
KNOWN_GOOD_LOCAL_EXTENSION
UNKNOWN

Do not copy known-good patches as templates.

Extract semantic rules from them.

---

22. Compare GKI 6.12.23 vs 6.12.69

The two known-good 6.12 patches provide an important controlled comparison.

Compare:

6.12.23 known-good 51
vs
6.12.69 known-good 51

Identify every meaningful difference.

Classify each difference as:

DEINLINE_POLICY
KERNEL_VERSION_COMPAT
PATCH_CONTEXT_ONLY
UPSTREAM_SUSFS_CHANGE
LOCAL_EXTENSION
UNKNOWN

The goal is to separate:

architecture policy

from:

kernel minor-version adaptation

Do not merge these into one rule.

---

23. Revised 11 / 51 / Fixture Responsibility Boundary

Re-evaluate Phase 1's responsibility model.

Produce four separate ownership domains.

11 owns

Only xxKSU source-side integration responsibilities.

51 owns

Only Linux kernel / SuSFS integration responsibilities that truly belong in generated 51.

Fixtures own

For example:

- scope-min manual call sites
- manual-security-hooks / LSM call sites

Only assign something here if actual fixture source proves it.

Target Adapter owns

Only:

- kernel-version adaptations
- vendor-tree adaptations
- changed anchors/APIs/context
- Sultan-specific compatibility

Architecture transformations must NOT be mixed with target compatibility.

---

24. Produce Three Corrected Architecture Diagrams

Produce one final architecture diagram for each target.

A. GKI Android 14 / Linux 6.1

Show at minimum:

Linux kernel
│
├── exec
│    └── caller
│         └── ksu_handle_execveat
│              └── xxKSU
│
├── faccessat
├── stat
├── read
├── reboot
├── setuid
├── input
│
└── SuSFS kernel functionality

Mark:

OFFICIAL_50
51
XXKSU
FIXTURE
TARGET_KERNEL
MISSING

for each path.

B. GKI Android 16 / Linux 6.12

Same requirement.

If 6.12.23 and 6.12.69 differ semantically, show the difference.

C. Sultan Android 14 / Linux 6.1

Also show:

- scope-min
- manual-security-hooks
- Sultan-specific adaptation

---

25. Corrections to Phase 1

Add a section:

Corrections to Phase 1

Review every major Phase 1 conclusion and mark it as:

CONFIRMED
CORRECTED
REJECTED
UNRESOLVED

At minimum revisit:

- definition of manual/inline hook
- meaning of de-inline
- GKI exec path
- GKI access path
- GKI stat path
- GKI reboot path
- GKI setuid path
- GKI input path
- GKI read path
- Sultan fixture ownership
- SELinux exclusion
- input stub
- 11/51 responsibility boundary
- current generator correctness

Explain every correction.

---

26. Final De-Inline Policy Table

Only after all tracing is complete, produce:

Semantic Path| GKI 6.1| GKI 6.12| Sultan 6.1| Final Owner| 50→51 Action| Evidence| Confidence

Possible actions include:

KEEP
REMOVE_DUPLICATE
REROUTE
SPLIT_MIXED_BLOCK
TARGET_ADAPT
KEEP_PURE_SUSFS
FAIL_UNKNOWN

This table is intended to become the future V2 architecture policy.

It must not be based on regex heuristics.

---

27. Fail-Closed Analysis Rule

If ownership cannot be proven:

Do NOT guess.

Use:

UNKNOWN

or:

UNRESOLVED

and state exactly what evidence is missing.

Examples:

Unable to find caller in clean GKI tree.
Need target kernel commit/source verification.

or:

Known-good patch contains this path, but ownership cannot be proven from xxKSU or fixture source.

Unknown must never silently become:

KEEP

or:

REMOVE

---

28. Confidence Requirements

Use:

HIGH
MEDIUM
LOW

Every MEDIUM or LOW conclusion must state:

1. what evidence exists
2. what evidence is missing
3. what would raise confidence

Do not assign HIGH simply because:

- known-good patch worked
- current generator does it
- README says it
- current 51 contains it

---

29. Final Deliverable

Create exactly one new file:

./XXKSU_SUSFS_PHASE1_5_REPORT.md

It must contain:

1. Corrected hook terminology
2. Official upstream source mapping
3. Known-good reference mapping
4. Complete call-site ownership matrix
5. Exact de-inline definition
6. GKI 6.1 call-path analysis
7. GKI 6.12 call-path analysis
8. Sultan 6.1 call-path analysis
9. SELinux exclusion verification
10. "fs/exec.c" audit
11. "fs/open.c" audit
12. "fs/stat.c" audit
13. "fs/read_write.c" audit
14. "kernel/reboot.c" audit
15. "kernel/sys.c" / setuid audit
16. "drivers/input/input.c" audit
17. Known-Good Reference Differential
18. GKI 6.12.23 vs 6.12.69 differential
19. Revised 11/51/fixture/adapter responsibility boundary
20. Three target architecture diagrams
21. Corrections to Phase 1
22. Final de-inline policy table
23. Unknown / unresolved items
24. Confidence report
25. Recommendation on whether V2 implementation is safe to begin

---

30. STOP CONDITION

After creating:

XXKSU_SUSFS_PHASE1_5_REPORT.md

STOP.

Do NOT:

- implement V2
- modify current generators
- regenerate 11
- regenerate 51
- modify workflows
- fix discovered bugs
- rewrite patches
- create migration code

Wait for human review and approval.