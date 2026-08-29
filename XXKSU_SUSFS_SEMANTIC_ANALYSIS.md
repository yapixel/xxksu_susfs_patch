xxKSU + SuSFS 11/51 Patch Semantic Analysis & Generator Redesign

0. Mission

This repository maintains xxKSU-compatible SuSFS patches:

- "11_enable_susfs_for_ksu.patch"
- "51_add_susfs_in_kernel*.patch"

These are derived conceptually from upstream SuSFS patches:

- "10_enable_susfs_for_ksu.patch"
- "50_add_susfs_in_kernel*.patch"

The current repository also contains Python scripts intended to generate or transform these patches.

Before modifying any generator, workflow, or patch, first determine:

«Why does xxKSU require 11 + 51 instead of directly using upstream 10 + 50?»

The primary objective is NOT to make patches apply.

The primary objective is to recover and verify the architecture and semantic transformation rules behind:

10 + 50
   ↓
11 + 51

Only after this model is understood and verified may the generator implementation be redesigned.

---

1. Critical Rule: Analysis First

During the first phase:

DO NOT modify any file.

Do not modify:

- Python scripts
- workflows
- patches
- source code
- README
- configuration

The first phase is read-only investigation.

Inspect the actual repository contents and upstream sources.

Do not rely only on README descriptions.

---

2. Sources of Truth

The following should be treated as primary evidence:

Upstream SuSFS

Inspect the actual current upstream:

- "10_enable_susfs_for_ksu.patch"
- relevant "50_add_susfs_in_kernel*.patch"
- SuSFS source
- relevant branches

xxKSU

Inspect the actual xxKSU source and determine its hook architecture.

Specifically determine:

- which KernelSU hooks already exist;
- which execution paths xxKSU owns;
- whether xxKSU uses traditional manual/inline hooks;
- which traditional KernelSU hooks are unnecessary or conflicting;
- how SuSFS is expected to reach xxKSU/kernel functionality.

Target kernels

Inspect the actual kernel trees corresponding to each supported 51 patch.

Examples may include:

- GKI Android 14 / Linux 6.1
- Android 15 targets
- Android 16 / Linux 6.12
- Sultan-derived targets
- any other target currently supported by this repository

Do not assume all kernel targets require identical transformations.

---

3. Current 11/51 Are NOT Automatically Ground Truth

The current:

- "11_enable_susfs_for_ksu.patch"
- "51_add_susfs_in_kernel*.patch"

must be treated as implementations that require auditing.

Do NOT assume:

current 11 == correct
current 51 == correct

The investigation is allowed to conclude:

Current 11 contains unnecessary or stale logic.

or:

Current 51 incorrectly removed legitimate SuSFS functionality.

The goal is NOT to reproduce the current patches byte-for-byte.

The goal is to determine the correct semantic result.

---

4. Understand Why De-Inline Exists

Determine precisely why xxKSU requires de-inline behavior.

Investigate whether upstream SuSFS 10 + 50 assumes a traditional KernelSU architecture such as:

Linux syscall / VFS path
        ↓
fs/exec.c
fs/open.c
fs/read_write.c
kernel/reboot.c
SELinux paths
etc.
        ↓
ksu_handle_*
        ↓
KernelSU
        ↓
SuSFS

Then determine how xxKSU differs.

Answer:

1. Which traditional KernelSU inline/manual hooks are already replaced by xxKSU architecture?
2. Which upstream 50 modifications would duplicate xxKSU behavior?
3. Which modifications would conflict with xxKSU?
4. Which SuSFS kernel functionality is independent of KernelSU inline hooks and therefore MUST remain?
5. Which responsibilities move from 50 to 11?
6. Which responsibilities disappear completely because xxKSU already provides them?

The final analysis must clearly explain:

«What exactly does "de-inline" mean in this repository?»

---

5. Architecture Transformation vs Version Adaptation

These MUST be treated as two different concepts.

5.1 Architecture Transformation

This is intentional transformation required because xxKSU architecture differs from traditional KernelSU.

Examples:

DEINLINE
REROUTE_TO_XXKSU
REMOVE_DUPLICATE_HOOK
USE_XXKSU_EXISTING_PATH

A patch hunk may apply perfectly and STILL need to be removed because it represents an unwanted traditional KernelSU inline hook.

Therefore:

git apply success != KEEP

5.2 Version Adaptation

This exists because source context changed.

Examples:

- xxKSU changed a function;
- Linux 6.1 differs from Linux 6.12;
- Sultan tree differs from GKI;
- SuSFS upstream changed context;
- symbol names changed;
- source moved.

This should be classified as:

XXKSU_COMPAT
KERNEL_COMPAT
VERSION_COMPAT
SULTAN_COMPAT

Therefore:

git apply failure != DEINLINE

This distinction is fundamental.

---

6. Analyze 10 → 11

Compare the current upstream 10 patch against the current 11 patch.

Perform a semantic comparison.

Do NOT only run textual diff.

For every meaningful changed block classify it as one of:

KEEP
DEINLINE
REROUTE_TO_XXKSU
XXKSU_COMPAT
VERSION_COMPAT
SUSFS_EXTENSION
UNKNOWN

Produce a table:

File| Upstream 10 Behavior| 11 Behavior| Classification| Reason

Answer specifically:

1. What upstream 10 behavior remains unchanged?
2. What behavior is removed?
3. What behavior is rerouted?
4. What is xxKSU-specific?
5. What exists only because current xxKSU source differs from upstream KernelSU?
6. What functionality in 11 compensates for de-inline changes in 51?
7. What new behavior exists in current 11 that does not originate from upstream 10?
8. Is that additional behavior actually necessary?
9. Are there hardcoded transformations that may already be stale?

Any transformation that cannot be confidently explained must be:

UNKNOWN

Do not invent explanations.

---

7. Analyze 50 → 51

Perform the same semantic comparison for every supported kernel target.

Compare:

upstream 50

against:

current 51

Classify changes as:

KEEP
DEINLINE
KERNEL_COMPAT
VERSION_COMPAT
SULTAN_COMPAT
SUSFS_EXTENSION
MIXED
UNKNOWN

Produce:

File| Hunk| 50 Behavior| 51 Behavior| Classification| Reason

---

8. Build an Inline Hook Inventory

Create a complete inventory of traditional KernelSU hooks found in upstream 50.

Look for, but do not limit analysis to:

ksu_handle_*
ksu_is_input_hook
ksu_is_init_rc_hook

Inspect paths including but not limited to:

fs/exec.c
fs/open.c
fs/read_write.c
fs/stat.c
fs/statfs.c
kernel/reboot.c
drivers/input/*
security/selinux/*

For every hook record:

Hook| Kernel File| Original Purpose| xxKSU Equivalent| Keep in 51?| Reason

Do not assume every "ksu_*" reference should be removed.

Determine ownership semantically.

---

9. Mixed Hunk Handling

This is extremely important.

A single upstream hunk may contain both:

SuSFS kernel functionality
+
traditional KernelSU inline hook transport

Example conceptually:

+ susfs_do_something();

+ if (ksu_hook_enabled)
+     ksu_handle_something();

+ susfs_other_feature();

The correct 51 may need:

+ susfs_do_something();

+ susfs_other_feature();

Therefore:

DO NOT delete an entire hunk merely because it contains "ksu_handle_*".

Every mixed hunk must be identified.

For each mixed hunk explain:

KEEP:
<lines / behavior>

REMOVE:
<lines / behavior>

WHY:
<architectural reason>

---

10. Determine the 11 / 51 Responsibility Boundary

After semantic analysis, explicitly define the responsibility of each patch.

10.1 11 Responsibilities

Determine whether 11 owns:

- xxKSU-side SuSFS integration;
- command routing;
- supercall routing;
- hook routing;
- initialization;
- feature control;
- KSU-side APIs;
- replacements for traditional KernelSU integration assumptions.

Do not simply state:

11 patches KernelSU.

Describe actual behavior.

10.2 51 Responsibilities

Determine which functionality belongs to the Linux kernel side.

Identify:

- SuSFS core kernel functionality;
- filesystem behavior;
- mount behavior;
- stat behavior;
- namespace behavior;
- proc behavior;
- SELinux-related SuSFS functionality;
- any other legitimate kernel-side SuSFS behavior.

Then separately identify:

traditional KernelSU inline transport

that should NOT exist in 51.

---

11. Produce the Actual Architecture Diagram

After investigation, produce the real call/control architecture.

For example, if supported by evidence:

Userspace
    ↓
xxKSU
    ↓
11 integration
    ↓
SuSFS command/control interface
    ↓
Linux kernel + 51
    ↓
SuSFS functionality

Also show the architecture that MUST NOT occur:

                     Linux path
                         ↓
             ┌───────────┴───────────┐
             ↓                       ↓
        xxKSU hook             traditional
                               KSU inline hook
             ↓                       ↓
             └───────────┬───────────┘
                         ↓
                       SuSFS

Verify the diagram against actual source.

Do not assume this example is correct merely because it appears in this task description.

---

12. Audit Current Python Generators

Only after completing the semantic analysis above, audit the existing Python.

Inspect all relevant scripts, especially:

transform_10_to_11.py
deinline_50_to_51.py

and any helper scripts they use.

Produce:

Python Rule| Intended Semantic Rule| Correct?| Risk

Use:

YES
PARTIAL
NO
UNKNOWN

---

13. Audit transform_10_to_11.py

Determine whether the generator actually consumes the current upstream 10 patch.

If it does not, explicitly document this.

Identify:

- hardcoded reconstruction;
- exact string replacement;
- silent replacement failure;
- missing anchor validation;
- stale copied SuSFS logic;
- duplicated upstream implementation;
- assumptions about xxKSU source;
- assumptions about SuSFS source.

Determine whether the current generator is actually:

10 → 11 transformer

or effectively:

hardcoded 11 synthesizer

---

14. Audit deinline_50_to_51.py

Inspect specifically:

- whole-file exclusion;
- whole-hunk exclusion;
- keyword-based filtering;
- "ksu_handle_*" filtering;
- "SULTAN_EXTRA_CHUNKS";
- hardcoded unified-diff blocks;
- static index hashes;
- copied SuSFS source;
- branch-specific assumptions.

Determine whether legitimate SuSFS functionality can be accidentally removed.

Especially search for cases where:

one KSU inline hook

causes:

an entire mixed hunk

to disappear.

Also determine whether hardcoded chunks can reintroduce stale upstream SuSFS implementation.

---

15. Correct Use of Raw Apply

The redesigned system MAY use:

git apply --check
git apply --reject
patch

and ".rej" files.

However raw apply is for detecting source compatibility problems.

It must NOT define architecture policy.

Correct interpretation:

apply failure
    ↓
possible VERSION/CONTEXT incompatibility

NOT:

apply failure
    ↓
must DEINLINE

Likewise:

apply success

does NOT automatically mean:

KEEP

because an unwanted traditional inline hook may apply perfectly.

---

16. Proposed Generator Model

After the investigation, design a V2 generator around:

UPSTREAM TRUTH
        ↓
ARCHITECTURE POLICY
        ↓
SEMANTIC TRANSFORMATION
        ↓
TARGET VERSION ADAPTATION
        ↓
VALIDATION
        ↓
GENERATED PATCH

---

17. Upstream Must Remain the Source of Truth

Every generation must begin from the current upstream patch.

Correct:

current 10
+
current xxKSU
+
architecture policy
+
compatibility adapters
=
current 11

Correct:

current 50
+
current target kernel
+
architecture policy
+
compatibility adapters
=
current 51

Incorrect:

old 11
→ modify
→ new 11

Incorrect:

old 51
→ modify
→ new 51

Incorrect:

hardcoded Python implementation
→ reconstruct upstream behavior from memory

---

18. Suggested Transformation Layers

Evaluate an architecture similar to:

patch-generator/
├── engine/
│   ├── unified_diff.py
│   ├── apply.py
│   ├── reject_analysis.py
│   ├── semantic_validation.py
│   └── output.py
│
├── policy/
│   ├── deinline_policy.py
│   ├── xxksu_routing.py
│   └── required_susfs_features.py
│
├── adapters/
│   ├── xxksu.py
│   ├── android14_6_1.py
│   ├── android15_*.py
│   ├── android16_6_12.py
│   └── sultan.py
│
└── tests/

This is only a proposed structure.

Change it if investigation reveals a better design.

Architecture policy and version adapters MUST remain logically separate.

---

19. Fail-Closed Requirement

The future generator must fail closed.

Generation MUST stop when:

- an unknown upstream hunk appears in a transformation-sensitive region;
- an expected semantic anchor disappears;
- an anchor matches more times than expected;
- a mixed hunk cannot be safely separated;
- an unknown KernelSU hook appears;
- an upstream behavior cannot be classified;
- a compatibility adapter cannot resolve a reject;
- semantic validation fails;
- required SuSFS functionality disappears.

Never silently continue.

Forbidden patterns include:

silent skip
silent replace failure
keyword → drop whole hunk
unknown → assume KEEP
unknown → assume DELETE

Unknown behavior should produce a structured diagnostic and stop generation.

---

20. Semantic Coverage Validation

Every relevant upstream modification should have an accounting trail.

Conceptually:

Upstream changes
      ↓
┌──────────────────────────┐
│ KEEP                     │
│ DEINLINE                 │
│ REROUTE                  │
│ VERSION ADAPT            │
│ TARGET-SPECIFIC ADAPT    │
└──────────────────────────┘
      ↓
100% accounted for

There should be no silent loss.

If:

upstream relevant hunks = N

then every one of those N hunks must have a known outcome.

---

21. Forbidden Inline Hook Validation

After generating 11 + 51 and applying them to clean target trees, inspect the resulting source.

Verify that traditional KernelSU inline/manual hooks that should have been removed are actually absent.

Do not only inspect patch text.

Inspect final source state.

Produce a list of:

expected absent hooks
expected present hooks
xxKSU-owned hooks
SuSFS-owned functionality

and validate them.

---

22. Required SuSFS Functionality Validation

The opposite check is equally important.

De-inline must NOT accidentally remove SuSFS functionality.

Build a required feature inventory from upstream.

Verify that final 11 + 51 still provides the intended SuSFS behavior.

The generator must detect:

inline hook successfully removed
BUT
associated legitimate SuSFS functionality accidentally removed

as a failure.

---

23. Build Validation

"git apply" success is insufficient.

Design validation layers:

Layer 1 — Patch Integrity

Generated patch is syntactically valid.

Layer 2 — Clean Application

Generated 11/51 apply to intended clean trees.

Layer 3 — Semantic Coverage

All relevant upstream changes are accounted for.

Layer 4 — Forbidden Hook Scan

Unwanted traditional inline hooks are absent.

Layer 5 — Required Feature Scan

Required SuSFS functionality remains.

Layer 6 — Build/Compile

Where practical, compile relevant kernel/KSU targets or at minimum compile affected components/configurations.

Do not report:

Integration verified

when only patch application was tested.

---

24. Reproducibility

The generator should be deterministic.

Given:

same upstream commit
same xxKSU commit
same kernel commit
same architecture policy
same adapter version

the generated patch should be identical.

Record provenance such as:

SuSFS commit
xxKSU commit
kernel commit
source patch identity
generator version
policy version

---

25. First Deliverable

DO NOT IMPLEMENT V2 YET.

The first deliverable is an analysis report containing exactly these major sections:

1. Why 11 + 51 Exist

Explain the architecture reason.

2. Upstream 10/50 Architecture

Explain what assumptions upstream patches make about KernelSU.

3. xxKSU Hook Architecture

Explain how xxKSU differs.

4. Inline Hook Inventory

List every relevant traditional KSU inline/manual hook.

5. 10 → 11 Semantic Mapping

Detailed mapping.

6. 50 → 51 Semantic Mapping

Detailed mapping for every supported target.

7. Mixed Hunk Inventory

List all mixed SuSFS + KSU hook hunks.

8. 11 / 51 Responsibility Boundary

Define exactly what belongs in each patch.

9. Current 11/51 Correctness Audit

Identify questionable current transformations.

10. Current Python Generator Audit

Identify correct, fragile, incorrect and stale logic.

11. Architecture Policy

Extract the actual de-inline rules independent of kernel versions.

12. Version Compatibility Rules

Separate target-specific compatibility from architecture policy.

13. Unknown / Uncertain Areas

Do not hide uncertainty.

14. Proposed V2 Generator Architecture

Design only.

No implementation yet.

15. Migration Plan

Explain how to replace the current generator safely without breaking known-good targets.

---

26. Confidence Report

At the end provide:

Area| Confidence| Evidence| Remaining Questions
11 semantic understanding| HIGH/MEDIUM/LOW| ...| ...
51 semantic understanding| HIGH/MEDIUM/LOW| ...| ...
de-inline boundary| HIGH/MEDIUM/LOW| ...| ...
xxKSU hook ownership| HIGH/MEDIUM/LOW| ...| ...
SuSFS feature preservation| HIGH/MEDIUM/LOW| ...| ...
current generator correctness| HIGH/MEDIUM/LOW| ...| ...
proposed V2 model| HIGH/MEDIUM/LOW| ...| ...

Every MEDIUM or LOW result must state what evidence is still needed.

---

27. Final Rules

Do not optimize for reproducing current patch output.

Optimize for preserving correct behavior.

Do not assume current Python defines the intended architecture.

Do not assume current 11/51 are correct.

Do not infer de-inline decisions from patch failures.

Do not infer KEEP decisions from patch success.

Do not remove whole files merely because they historically contained KernelSU hooks.

Do not remove whole hunks merely because they contain "ksu_handle_*".

Do not silently ignore upstream changes.

Do not rewrite upstream SuSFS functionality manually unless there is a proven architectural reason.

Always distinguish:

ARCHITECTURE TRANSFORMATION

from:

VERSION ADAPTATION

The fundamental model to verify is:

          upstream SuSFS
           10       50
            │       │
            ▼       ▼
      architecture policy
       │             │
       ▼             ▼
 xxKSU routing     de-inline
       │             │
       ▼             ▼
 compatibility    kernel compatibility
       │             │
       ▼             ▼
      11            51
       └──────┬──────┘
              ▼
       validated xxKSU
          + SuSFS

The first task is to prove or correct this model from actual source and patch evidence.

STOP after producing the first analysis report.

Do not modify code until the semantic model has been reviewed and explicitly approved.