# xxKSU + SuSFS V2.2 — Provenance, Content-Addressed Cache & Manifest Loader

## Phase

V2.2 — Provenance + Source Preparation + Content-Addressed Cache + Manifest Loader

## Status

IMPLEMENTATION AUTHORIZED FOR V2.2 ONLY.

V2.1 has completed its review gate.

This task authorizes implementation of the V2.2 foundation described in:

```text
./XXKSU_SUSFS_V2_DESIGN.md
```

It does NOT authorize V2.3 or any later V2 phase.

After V2.2 is implemented, tested, and documented:

**STOP.**

Do not continue into semantic inventory, semantic classification, coverage ledgers,
10→11 transformation, 50→51 transformation, target adapters, fixture adaptation,
profile composition, build validation, runtime validation, workflow migration, or
cutover work.

---

# 1. Read the Project Contract First

Before modifying anything, read these files in this exact order:

```text
./XXKSU_SUSFS_PHASE1_5_REPORT.md
./XXKSU_SUSFS_PHASE1_6_REPORT.md
./XXKSU_SUSFS_V2_DESIGN.md
./XXKSU_SUSFS_V2_1_REPORT.md
./XXKSU_SUSFS_V2_2_TASK.md
```

Treat:

```text
Phase 1.5
```

as the semantic/evidence baseline.

Treat:

```text
Phase 1.6
```

as the authoritative dual-mode target/profile contract.

Treat:

```text
XXKSU_SUSFS_V2_DESIGN.md
```

as the accepted V2 architecture.

Treat:

```text
XXKSU_SUSFS_V2_1_REPORT.md
```

as the accepted implementation baseline for the existing V2 package.

Treat this task as the authoritative implementation scope for this run.

Do not redesign the accepted architecture during V2.2.

If implementation reveals a contradiction in the accepted design, STOP and
document the contradiction instead of silently changing architecture.

---

# 2. V2.2 Objective

Implement the trustworthy-input layer required before semantic processing.

V2.2 must establish:

```text
typed input references
+
typed target/profile manifests
+
strict manifest loading and validation
+
source identity verification
+
content hashing
+
content-addressed local cache
+
network/offline separation
+
prepared-input records
+
provenance records
+
deterministic serialization
+
tests
```

The central invariant is:

```text
semantic generation must never operate on implicit,
unverified, or silently moving upstream state.
```

V2.2 prepares and verifies inputs.

V2.2 does NOT interpret patch semantics.

---

# 3. V2.2 Architecture Boundary

The accepted pipeline is conceptually:

```text
NETWORK SIDE

fetch
  ↓
verify identity
  ↓
hash immutable input
  ↓
content-addressed cache

---------------- TRUST BOUNDARY ----------------

OFFLINE SIDE

prepare
  ↓
load target/profile manifest
  ↓
resolve only cached pinned inputs
  ↓
verify hashes/identity
  ↓
PreparedInput / Provenance
  ↓
future V2.3 semantic inventory
```

V2.2 ends before the final arrow.

No V2.3 semantic inventory is authorized.

---

# 4. Important Terminology

Use these terms consistently.

## Fetch

Network-capable acquisition of an explicitly declared source/ref.

Fetch may populate the cache.

Fetch must not perform semantic transformation.

## Cache

Local content-addressed storage containing immutable fetched/prepared inputs.

Cache identity must derive from content and/or verified immutable source identity,
not from a mutable branch name alone.

## Prepare

Offline verification and resolution of already available cached inputs into a
typed prepared-input record.

Prepare must not silently fetch missing data.

## Manifest

Declarative project contract describing supported target/profile identity,
expected inputs, configuration requirements, and ownership declarations.

In V2.2 manifests are validated data only.

They do not cause source transformation.

## Provenance

A deterministic record explaining exactly which verified inputs, revisions,
hashes, manifest schema versions, and preparation rules identify a prepared run.

---

# 5. Required V2.2 Package Scope

Extend the existing:

```text
.github/scripts/v2/
```

package only as necessary for V2.2.

Expected conceptual additions may include:

```text
.github/scripts/v2/
├── model/
│   ├── manifest.py
│   └── provenance.py
├── source/
│   ├── cache.py
│   ├── fetch.py
│   ├── prepare.py
│   ├── hashing.py
│   └── identity.py
├── profiles/
│   └── ...
├── manifests/
│   └── ...
└── tests/
    └── ...
```

Exact organization may differ if a simpler structure is better.

Do not create empty future-phase modules.

Do not create semantic-policy modules in V2.2.

---

# 6. Reuse V2.1 Correctly

Do not rewrite or destabilize the accepted V2.1 parser/emitter.

V2.2 may import V2.1 types/utilities where appropriate.

Changes to existing V2.1 files are allowed ONLY when strictly necessary for
V2.2 integration and must:

```text
preserve V2.1 behavior
preserve all V2.1 tests
be explicitly documented in the V2.2 report
```

Prefer additive V2.2 modules over unnecessary V2.1 refactoring.

All V2.1 tests must remain green.

---

# 7. Core V2.2 Data Models

Implement only the data models required for V2.2.

Expected concepts include:

```text
InputRef
RepositoryRef
PatchRef
TargetRef
ProfileManifest
TargetManifest
PreparedInput
PreparedSource
Provenance
HashDigest
CacheEntry
```

Exact class names may differ.

Use typed structures rather than arbitrary nested dictionaries after manifest
loading.

Do not implement:

```text
SemanticUnit
semantic Operation
semantic OwnerClaim engine
coverage ledger
```

Those belong to later phases.

---

# 8. InputRef Contract

An input reference must distinguish what is being referenced.

Examples:

```text
Git repository/tree
patch file
fixture
kernel archive/tree
local immutable test source
```

An input reference should contain only fields meaningful to its type.

Where applicable, record:

```text
source URL/repository identity
declared branch
immutable commit/ref
object/tree identity
content hash
expected artifact path
schema/type
```

Mutable branch names may be recorded for provenance, but they must not be the
only immutable identity used by offline preparation.

---

# 9. Hash Contract

Use a deterministic cryptographic hash.

Preferred:

```text
SHA-256
```

unless the existing repository has a stronger established convention.

The hash representation must be explicit, for example:

```text
sha256:<lowercase hex>
```

or a typed equivalent.

Do not rely on:

```text
mtime
inode
filesystem path
archive filename
branch name
```

as content identity.

Tests must verify changed content produces changed identity.

---

# 10. Git Identity Contract

For Git-backed sources, provenance should distinguish:

```text
repository URL
requested ref/branch
resolved immutable commit
tree/object identity where useful
content/prepared-tree hash
```

A mutable branch name alone is insufficient.

Preparation must be able to prove that the cached source corresponds to the
declared immutable revision.

Do not infer correctness from directory names.

---

# 11. Repository URL Canonicalization

Define a conservative repository identity policy.

Equivalent spellings may be normalized only when equivalence is safely known.

Do not aggressively rewrite arbitrary URLs.

At minimum:

```text
strip clearly irrelevant trailing syntax where safe
preserve repository host/path identity
record the original declared source
record normalized identity separately if normalization occurs
```

Do not allow URL normalization to silently make two uncertain repositories equal.

---

# 12. Content-Addressed Cache

Implement a local cache abstraction.

The cache must not depend on the user's active working tree.

Conceptual layout may resemble:

```text
<cache-root>/
  objects/
    sha256/
      ab/
        abcdef...
  metadata/
    ...
```

Exact layout is implementation-defined.

Requirements:

```text
content-addressed
immutable once committed
atomic population
verified on read
safe against partial writes
no mutation of user checkout
```

Do not use the repository working tree itself as the cache.

---

# 13. Cache Root

The cache root must be explicit/configurable.

Tests must use temporary directories.

Do not write tests into the user's real home cache.

Do not hardcode:

```text
/home/ezhang
```

or any user-specific path.

A reasonable default may be designed, but tests and core APIs must allow an
explicit cache root.

---

# 14. Atomic Cache Population

Cache writes must avoid exposing partially populated objects.

Preferred pattern:

```text
write temporary object
verify/hash
fsync where appropriate
atomic rename into final object identity
```

Do not overwrite an existing object with different content.

If an object already exists:

```text
verify it
reuse it
```

If existing cached content does not match its declared identity:

```text
FAIL CLOSED
```

---

# 15. Cache Integrity Verification

Reading a cache object must not blindly trust its filename.

At appropriate verification boundaries:

```text
recompute content hash
compare to object identity
```

Corruption must produce an explicit typed failure.

Do not silently delete and redownload during an offline operation.

---

# 16. Directory / Tree Identity

V2 eventually consumes source trees, not only single files.

Define a deterministic tree hashing contract.

The tree hash must account for at least:

```text
relative path
file type where relevant
file content
executable/mode information where semantically relevant
symlink target if symlinks are supported
```

It must not depend on:

```text
absolute path
mtime
directory enumeration accident
temporary root
```

Traversal ordering must be deterministic.

Document exactly what is included/excluded.

---

# 17. Git Metadata and Tree Hashing

Be explicit about whether:

```text
.git/
```

is excluded from prepared source-tree content hashing.

Preferred design:

```text
Git commit/tree identity is provenance metadata.
Prepared source content hash represents the materialized source tree.
.git metadata is excluded from source-content hashing.
```

If another approach is used, justify it.

---

# 18. Symlink Policy

Define and test symlink handling.

At minimum:

```text
do not silently follow arbitrary symlinks outside the source root
hash the link target or reject unsupported links explicitly
prevent cache traversal outside the intended root
```

Security and deterministic identity matter here.

---

# 19. File Mode Policy

Define which mode bits affect deterministic tree identity.

At minimum executable-vs-non-executable distinction should be considered for Git
source equivalence.

Do not allow unrelated host permission noise to make hashes unstable.

Document the exact normalization.

---

# 20. Network Boundary

Network access must be explicit.

A network-capable operation may conceptually be:

```text
fetch
```

An offline operation may conceptually be:

```text
prepare
```

Core requirement:

```text
prepare MUST NOT perform implicit network access.
```

If a required cache object is missing:

```text
OfflineInputMissing
```

or equivalent must be raised.

Do not silently invoke Git/network from prepare.

---

# 21. Fetch Contract

Implement only enough fetch infrastructure to establish V2.2's acquisition
boundary.

Fetch must:

```text
receive explicit source/ref information
resolve immutable identity
obtain content
verify expected identity/hash where declared
populate cache
return a typed acquisition/provenance result
```

Fetch must NOT:

```text
run semantic classification
generate 11
generate 51
apply fixtures
compose profiles
build kernels
```

---

# 22. External Command Safety

If Git or another external executable is invoked:

```text
use argument arrays
do not construct shell command strings
do not use shell=True
validate inputs
capture stdout/stderr
check exit status
provide typed diagnostics
```

Do not allow manifest fields to become arbitrary shell fragments.

Tests should mock/substitute network-facing execution where practical.

Do not require live network access for the ordinary V2.2 test suite.

---

# 23. Offline Preparation Contract

Implement an offline preparation API conceptually similar to:

```python
prepare(target_manifest, cache, offline=True) -> PreparedInput
```

or an equally clear design.

Preparation must:

```text
validate manifest
resolve declared immutable cache objects
verify object integrity
verify expected source identities
verify expected hashes
construct deterministic PreparedInput
construct Provenance
```

It must not:

```text
classify semantic hunks
parse KSU/SuSFS behavior
apply patches
modify source trees
choose semantic KEEP/REMOVE policy
```

---

# 24. PreparedInput Contract

A prepared input record should identify everything later semantic stages require
without requiring network discovery.

For example:

```text
target identity
official 10 reference
official 50 reference
actual xxKSU reference
target kernel reference
fixture references where declared
resolved immutable identities
content/tree hashes
manifest schema versions
cache object identities
```

Do not include semantic transformation results.

PreparedInput should be serializable deterministically.

---

# 25. Provenance Contract

Implement provenance as structured data.

At minimum include applicable:

```text
schema version
target ID
profile ID if preparing a profile
repository/source identity
declared branch/ref
resolved commit
Git tree/object identity
content hash
prepared tree hash
official patch hash
fixture hashes
manifest hashes
V2 preparation/schema version
```

Do not include volatile timestamps in deterministic identity.

If operational timestamps are useful, place them only in a non-identity report
field or sidecar.

---

# 26. Deterministic Serialization

Manifest-derived and provenance-derived machine output must serialize
deterministically.

Preferred:

```text
JSON with explicit key ordering/canonical separators
```

or another documented canonical format.

Tests must prove that identical logical inputs serialize identically.

Do not rely on Python object repr as a persistent format.

---

# 27. Manifest Architecture

Implement two distinct manifest concepts:

```text
TargetManifest
ProfileManifest
```

Do not merge them into one ambiguous object.

Target manifests identify:

```text
what target this is
which upstream/input identities belong to it
which target adapter ID will eventually apply
which 51 policy ID will eventually apply
which profiles are supported
```

Profile manifests identify:

```text
which target
which mode
fixture requirements
configuration contract
declared transport ownership
validation prerequisites
```

V2.2 validates these declarations.

V2.2 does not execute them.

---

# 28. Target Manifest Contract

Support exactly the three accepted target IDs:

```text
gki-android14-6.1
gki-android16-6.12
sultan-android14-6.1
```

Each target manifest must declare both profiles:

```text
<target>-manual
<target>-lsm_bl
```

Unknown target IDs must fail closed.

Target manifests must not choose one transport mode globally.

---

# 29. Six Profile Contract

Support exactly these six final profile IDs:

```text
gki-android14-6.1-manual
gki-android14-6.1-lsm_bl

gki-android16-6.12-manual
gki-android16-6.12-lsm_bl

sultan-android14-6.1-manual
sultan-android14-6.1-lsm_bl
```

Unknown profile IDs must fail closed.

Do not infer a profile from partial strings.

Do not normalize an invalid hybrid into a valid profile.

---

# 30. Canonical Manual Profile Contract

All three manual profiles require:

```text
CONFIG_KSU=y
CONFIG_KSU_SUSFS=y

CONFIG_KSU_LSM_SECURITY_HOOKS=n
CONFIG_KSU_HACK_ARM64_BRANCH_LINK=n
CONFIG_KSU_TAMPER_SYSCALL_TABLE=n
CONFIG_KSU_KPROBES_KSUD=n
```

Manual also requires both fixture providers:

```text
scope-min-manual-hooks-v2.3.patch
manual-security-hooks-v2.0.patch
```

The manifest loader must reject a manual profile that:

```text
omits either fixture
enables automated transport
declares contradictory ownership
uses the wrong target
```

V2.2 only validates this contract.

It does not apply fixtures.

---

# 31. Canonical LSM/BL Profile Contract

All three lsm_bl profiles require:

```text
CONFIG_KSU=y
CONFIG_KSU_SUSFS=y

CONFIG_KSU_LSM_SECURITY_HOOKS=y
CONFIG_KSU_HACK_ARM64_BRANCH_LINK=y
CONFIG_KSU_TAMPER_SYSCALL_TABLE=n
CONFIG_KSU_KPROBES_KSUD=n
```

LSM/BL profiles require:

```text
ARM64
KALLSYMS
```

and forbid both manual fixtures.

The manifest loader must reject:

```text
fixture presence
LSM=n
BL=n
TAMPER=y
KPROBES_KSUD=y
wrong target/profile relationship
contradictory transport declarations
```

Important:

```text
TAMPER_SYSCALL_TABLE=n
```

does NOT mean the BL implementation has no internally managed syscall-table
bootstrap/fallback.

Do not encode that false assumption in manifest validation.

---

# 32. BL Composite Ownership Representation

The manifest data model must be able to represent that:

```text
XXKSU_BRANCH_LINK
+
XXKSU_INTERNAL_SYSCALL_FALLBACK
```

form one composite selected transport owner for ownership uniqueness purposes:

```text
XXKSU_BL_COMPOSITE
```

Do not flatten this into:

```text
TAMPER_SYSCALL_TABLE=y
```

and do not model the internal fallback as an independently selected profile
transport.

V2.2 only records/validates this declaration.

Actual source ownership validation belongs to later phases.

---

# 33. Manual Ownership Declarations

The manifest schema must be able to declare manual ownership such as:

```text
exec
access
stat
fstat-return
reboot
```

through the scope-min fixture provider, and security/read/setuid/setprocattr
transport through the manual-security fixture provider as defined by the accepted
architecture.

Do not inspect source to prove those claims in V2.2.

That belongs to later ownership validation.

V2.2 validates only schema/contract consistency.

---

# 34. Shared 11 Contract

Manifest validation must encode:

```text
one shared 11 policy
```

for all six profiles.

A profile must not be allowed to select a mode-specific 11.

Reject concepts such as:

```text
11-manual
11-lsm
11-gki
```

unless the accepted architecture is explicitly revised in a future human-reviewed
phase.

---

# 35. Transport-Neutral 51 Contract

Each target has one target-specific 51 policy.

The same target 51 must be referenced by both:

```text
manual
lsm_bl
```

profiles for that target.

Reject manifests that attempt to define:

```text
51-manual
51-lsm_bl
```

or otherwise select 51 by transport mode.

V2.2 must enforce this architectural invariant.

---

# 36. Adapter Contract at V2.2

Target manifests may declare an adapter ID such as:

```text
gki_android14_6_1
gki_android16_6_12
sultan_android14_6_1
```

V2.2 may validate that the ID belongs to the target.

V2.2 must NOT implement the adapter behavior.

No:

```text
anchor resolution
API adaptation
fixture insertion
semantic equivalence
```

belongs in V2.2.

---

# 37. Manifest Schema Versioning

Every persisted manifest must have an explicit schema ID/version.

For example:

```text
xxksu-susfs-target/v1
xxksu-susfs-profile/v1
```

Unknown schema versions must fail closed.

Do not silently accept future schema versions.

Do not silently discard unknown required fields.

Define and document policy for unknown optional fields if any.

Strict schemas are preferred.

---

# 38. Manifest Parsing

Prefer a representation that does not require a new external dependency unless
there is a strong reason.

If JSON is sufficient, JSON is acceptable.

If YAML is selected:

```text
justify dependency/availability
use safe loading
pin dependency if introduced
```

Do not implement a custom general YAML parser.

Do not use unsafe object deserialization.

---

# 39. Manifest Validation

Validation must include:

```text
schema version
required fields
field types
known target IDs
known profile IDs
target/profile relationship
mode enum
fixture requirements
fixture prohibitions
canonical Kconfig contract
shared 11 invariant
transport-neutral target 51 invariant
adapter/target relationship
ownership declaration shape
duplicate/conflicting declarations
unknown enum values
```

Validation failure must be typed and explicit.

Do not "fix" invalid manifests automatically.

---

# 40. Manifest Effective View

Provide a deterministic way to display/serialize the effective validated manifest.

The loader may expand named common policy records if the design uses them, but:

```text
effective output must be explicit
conflicts must fail
no hybrid normalization
```

A reviewer should be able to inspect exactly what V2 believes the profile means.

---

# 41. Source Manifest vs Test Manifest

Production manifests should describe accepted architecture.

Tests may construct intentionally invalid manifests.

Do not weaken production validation to make negative tests convenient.

Keep invalid examples inside test fixtures/temp data.

---

# 42. Actual Upstream References

Use the accepted project evidence to populate manifest source identities where
they are already established.

Do not invent missing immutable information.

If an input's exact immutable identity is not currently established:

```text
represent it explicitly as unresolved for fetch/preparation
```

or fail the production preparation path with a typed error.

Do NOT fabricate:

```text
commit hashes
tree hashes
archive provenance
patch hashes
```

The manifest schema must support resolving and then recording them.

---

# 43. Official SuSFS Source Contract

The target manifests must be capable of distinguishing the official 50 source
appropriate to each target family:

```text
Sultan Android 14 / Linux 6.1
GKI Android 14 / Linux 6.1
GKI Android 16 / Linux 6.12
```

Do not collapse these into one generic "latest 50".

Branch/ref identity must remain explicit.

---

# 44. xxKSU Source Contract

The manifest/provenance model must support an explicitly pinned actual xxKSU
source revision.

Do not treat:

```text
backslashxx/KernelSU latest
```

as a reproducible input.

Branch information may be recorded, but preparation must resolve an immutable
revision.

---

# 45. Fixture Provenance

The two manual fixtures are project inputs and must be hashable/provenance-aware:

```text
scope-min-manual-hooks-v2.3.patch
manual-security-hooks-v2.0.patch
```

Manual profile preparation should be able to identify their exact content hashes.

LSM/BL preparation must reject their inclusion as selected fixtures.

Do not apply them in V2.2.

---

# 46. Local Fixture Resolution

Fixture lookup must be deterministic and repository-relative or manifest-explicit.

Do not search arbitrary directories by filename.

Do not use:

```text
find /
```

or home-directory scans.

Missing declared fixture:

```text
FAIL CLOSED
```

---

# 47. Path Safety

All cache and manifest-derived relative paths must be validated.

Reject unsafe traversal such as:

```text
../
```

where it could escape an intended root.

Do not trust archive paths blindly.

If archive extraction is implemented, protect against:

```text
path traversal
absolute-path entries
unsafe symlink extraction
```

If archive extraction is not necessary for V2.2, do not implement it prematurely.

---

# 48. Cache/Manifest Separation

A manifest describes expected identity.

The cache stores content.

Do not make cache contents authoritative merely because an object exists.

Preparation must compare:

```text
manifest expectation
vs
cached verified identity
```

and fail on mismatch.

---

# 49. No Implicit "Latest"

The following behavior is forbidden:

```text
manifest says branch X
prepare asks network what X points to today
```

Preparation must use already resolved immutable identity.

Only explicit fetch may resolve a mutable branch/ref.

The resolved identity must then become part of the prepared provenance.

---

# 50. Test Architecture

Add focused V2.2 tests while preserving all V2.1 tests.

Tests should cover:

```text
hashing
tree hashing
cache write/read
cache corruption
atomic behavior where practical
offline missing input
manifest parsing
manifest validation
six valid profiles
invalid hybrid profiles
shared 11 invariant
target-specific transport-neutral 51 invariant
fixture requirements
fixture prohibitions
config contracts
target/profile mismatch
unknown schema
unknown target
unknown profile
deterministic serialization
prepared input reproducibility
path safety
symlink behavior
```

Do not require network access for the normal test suite.

---

# 51. Six Valid Profile Tests

There must be explicit successful validation coverage for all six:

```text
gki-android14-6.1-manual
gki-android14-6.1-lsm_bl

gki-android16-6.12-manual
gki-android16-6.12-lsm_bl

sultan-android14-6.1-manual
sultan-android14-6.1-lsm_bl
```

Do not test one profile and assume the others are equivalent.

---

# 52. Invalid Hybrid Tests

At minimum reject cases such as:

```text
manual + LSM=y
manual + BL=y
manual + missing scope-min fixture
manual + missing manual-security fixture

lsm_bl + fixture present
lsm_bl + LSM=n
lsm_bl + BL=n
lsm_bl + TAMPER=y
lsm_bl + KPROBES_KSUD=y

profile target != target manifest
unknown target
unknown profile
mode-specific 11
mode-specific 51
wrong target adapter
```

---

# 53. Cache Negative Tests

At minimum test:

```text
missing cache object
corrupted cache object
hash mismatch
unsafe cache-relative path
attempt to reuse wrong content under an identity
```

If practical, test interrupted/temporary cache population behavior.

No corruption case may silently become PASS.

---

# 54. Offline Guarantee Test

Add a test demonstrating that offline preparation cannot invoke network acquisition.

This can be established through dependency injection/mock/fake acquisition layer.

The test should fail if prepare attempts to call fetch/network resolution.

This is an important V2.2 acceptance gate.

---

# 55. Determinism Tests

At minimum demonstrate:

```text
same file content -> same hash
changed file content -> different hash
same source tree at different absolute paths -> same tree hash
different executable bit where tracked -> different tree hash
same logical manifest -> same canonical serialization
same prepared inputs -> same deterministic provenance identity
```

Volatile timestamps must not alter deterministic identity.

---

# 56. Existing Corpus / Repository Tests

Use actual repository fixture files where useful to verify hashing and preparation
behavior.

Do not modify them.

At minimum, where present, exercise content hashing of:

```text
scope-min-manual-hooks-v2.3.patch
manual-security-hooks-v2.0.patch
```

and verify their identities are stable during the test run.

Do not hardcode a hash without first deriving and documenting why it is trusted.

---

# 57. Error Model

Extend the typed error model only as needed.

Expected V2.2 concepts may include:

```text
ManifestError
UnsupportedManifestSchema
UnknownTarget
UnknownProfile
TargetProfileMismatch
InvalidProfileContract
InvalidFixtureContract
InvalidConfigContract

SourceIdentityError
UnresolvedSourceIdentity
SourceHashMismatch

CacheError
CacheObjectMissing
CacheCorruption

OfflineInputMissing
UnsafePath

FetchError
ExternalCommandError
```

Exact names may differ.

Errors should provide actionable context without leaking arbitrary command output
into structured identities.

Do not implement future semantic errors.

---

# 58. No Semantic Knowledge in Source Infrastructure

Cache/hashing/fetch/prepare infrastructure must remain generic.

It must not contain logic such as:

```text
if "ksu_handle_" ...
if file == "fs/stat.c" ...
if SuSFS block ...
```

Architecture-specific profile contract validation belongs in manifest validation,
not in generic cache/hash utilities.

---

# 59. No Source Mutation

V2.2 must not modify prepared upstream source content.

Preparation is verification/indexing only.

Do not:

```text
apply patch
edit kernel source
edit xxKSU source
insert fixture
generate 11
generate 51
```

Prepared source objects are immutable inputs to future phases.

---

# 60. No Build or Config Resolution

V2.2 may validate the declared Kconfig contract in manifests.

It must not run:

```text
olddefconfig
make
kernel build
actual final .config resolution
```

Those belong to later phases.

Do not confuse:

```text
manifest contract validation
```

with:

```text
final resolved config validation
```

---

# 61. No Semantic Ownership Validation

V2.2 validates that ownership declarations are structurally consistent with the
accepted profile contract.

It does NOT inspect the final source tree to prove exactly-one-owner.

That belongs to later V2 validation.

Do not claim source-level ownership PASS in V2.2.

---

# 62. No Live Network Dependency in Tests

The required V2.2 test suite must pass without GitHub/GitLab/network availability.

Network fetch behavior may be tested using:

```text
local temporary Git repositories
mock/fake command runner
file-based sources
```

Do not make normal unit tests flaky through live upstream requests.

---

# 63. Python Compatibility / Dependencies

Preserve the V2.1 compatibility baseline unless a change is justified.

Prefer standard library.

If an external dependency is introduced:

```text
justify it
document it
pin it appropriately
```

Do not introduce a dependency solely to avoid writing a small amount of clear
standard-library code.

---

# 64. CLI Boundary

The accepted final design contains conceptual commands such as:

```text
v2 fetch
v2 prepare
```

V2.2 may implement a minimal CLI only if it is useful to exercise the V2.2
boundary.

Do not implement the final complete CLI.

If CLI work is unnecessary for acceptance, prefer tested Python APIs.

Do not implement:

```text
generate 11
generate 51
validate profile source
validate all-profiles
build
```

---

# 65. Required Commands

At completion, run:

```text
V2.1 + V2.2 tests
syntax/import checks
```

Use repository-appropriate commands.

At minimum, record equivalents of:

```bash
python3 -m compileall -q .github/scripts/v2
PYTHONPATH=.github/scripts python3 -m unittest discover -s .github/scripts/v2/tests -v
```

If additional focused V2.2 tests are run, record them.

Do not claim PASS unless commands actually ran successfully.

---

# 66. Repository Safety

Before implementation:

```text
git status --short
```

Record the state.

The worktree may already contain:

```text
analysis reports
task documents
V2.1 implementation
V2.1 report
```

Do not delete or clean them.

Do not treat untracked project documents as disposable.

At completion:

```text
git status --short
```

again.

Report which files were created or modified by V2.2.

---

# 67. Allowed Files

V2.2 may create/modify only:

```text
.github/scripts/v2/**
XXKSU_SUSFS_V2_2_REPORT.md
```

V2.2 may add production manifest files under:

```text
.github/scripts/v2/**
```

if needed.

Do not modify:

```text
.github/scripts/transform_10_to_11.py
.github/scripts/deinline_50_to_51.py
```

Do not modify existing generated patches.

Do not modify fixtures.

Do not modify workflows.

Do not modify prior Phase/V2 reports or task documents.

---

# 68. Git Restrictions

Do NOT run mutating repository-management commands such as:

```text
git add
git commit
git reset
git checkout
git restore
git clean
git stash
```

Do not change branch or remote configuration.

Read-only Git commands are allowed.

A temporary Git repository created entirely under a test temporary directory is
allowed for tests.

Do not commit project work.

---

# 69. Implementation Quality

V2.2 code must remain:

```text
small
typed
deterministic
fail-closed
testable
explicit about network boundaries
explicit about immutable identity
safe around filesystem paths
```

Avoid:

```text
god objects
global mutable cache state
implicit network fallback
branch-name-only identity
unsafe YAML
shell=True
silent manifest normalization
automatic hybrid repair
semantic policy leakage
```

---

# 70. Required V2.2 Report

Create:

```text
./XXKSU_SUSFS_V2_2_REPORT.md
```

Use these exact sections:

```text
1. Executive Result
2. Files Created / Modified
3. V2.1 Regression Status
4. V2.2 Data Models
5. Input Reference Model
6. Hashing Contract
7. Source Tree Hash Contract
8. Git Identity Contract
9. Content-Addressed Cache
10. Atomic Cache Population
11. Cache Integrity Verification
12. Network / Offline Boundary
13. Fetch Contract
14. Offline Preparation Contract
15. PreparedInput Model
16. Provenance Model
17. Deterministic Serialization
18. Target Manifest Schema
19. Profile Manifest Schema
20. Six Supported Profiles
21. Manual Contract Validation
22. LSM/BL Contract Validation
23. Shared 11 Invariant
24. Transport-Neutral 51 Invariant
25. BL Composite Ownership Representation
26. Adapter Declaration Validation
27. Fixture Provenance
28. Path / Symlink Safety
29. Error Model
30. Test Architecture
31. Six-Profile Positive Tests
32. Invalid-Hybrid Negative Tests
33. Cache Negative Tests
34. Offline Guarantee Test
35. Determinism Tests
36. Repository Input Tests
37. Commands Executed
38. Test Results
39. Git Status Before / After
40. Design Deviations
41. Remaining V2.2 Limitations
42. V2.3 Readiness
43. Confidence Report
```

---

# 71. Required Report Questions

The report must explicitly answer:

1. What exact files were created?
2. What exact files were modified?
3. Were any V2.1 implementation files changed? Why?
4. Do all V2.1 tests still pass?
5. What external dependencies were added?
6. What hash algorithm is used?
7. How is a source tree hashed?
8. Are absolute paths excluded from tree identity?
9. How are executable bits handled?
10. How are symlinks handled?
11. Is `.git` included in prepared source-tree hashing?
12. How are Git repository/ref/commit/tree identities represented?
13. Can a mutable branch name be used as the sole offline identity?
14. How is cache corruption detected?
15. Are cache writes atomic?
16. Can offline prepare invoke fetch/network?
17. What happens when an offline object is missing?
18. How is deterministic provenance identity calculated?
19. Which manifest serialization format is used?
20. How are unknown schema versions handled?
21. Are all three targets represented?
22. Are all six profiles represented and independently tested?
23. How are manual fixture requirements enforced?
24. How are lsm_bl fixture prohibitions enforced?
25. How is the exact Kconfig contract validated?
26. How is shared 11 enforced?
27. How is one target-specific transport-neutral 51 enforced?
28. How is `XXKSU_BL_COMPOSITE` represented?
29. Does V2.2 inspect source to prove ownership?
30. Does V2.2 resolve final `.config`?
31. Does V2.2 apply any patch or fixture?
32. Does V2.2 perform semantic classification?
33. Were existing generators changed?
34. Were existing patches changed?
35. Were fixtures changed?
36. Were workflows changed?
37. What test commands were actually executed?
38. Did all V2.1 + V2.2 tests pass?
39. Is pinned offline preparation demonstrably fail-closed?
40. Is V2.2 sufficiently stable to begin V2.3?

---

# 72. Acceptance Criteria

V2.2 is complete only if ALL required items are true:

```text
[ ] V2.1 tests remain green.
[ ] Typed V2.2 input/provenance/manifest models exist.
[ ] Cryptographic content hashing is implemented.
[ ] Deterministic tree hashing is implemented and tested.
[ ] Absolute path does not affect tree identity.
[ ] Relevant executable mode affects tree identity.
[ ] Symlink behavior is explicit and safe.
[ ] Content-addressed cache exists.
[ ] Cache reads verify integrity.
[ ] Cache corruption fails closed.
[ ] Cache population avoids exposing partial objects.
[ ] Fetch/network boundary is explicit.
[ ] Offline prepare cannot invoke network acquisition.
[ ] Missing offline input fails explicitly.
[ ] PreparedInput contains immutable resolved identities.
[ ] Provenance is deterministic.
[ ] Volatile timestamps do not affect provenance identity.
[ ] Target manifest schema is versioned.
[ ] Profile manifest schema is versioned.
[ ] Unknown schema fails closed.
[ ] Exactly three accepted target IDs are supported.
[ ] Exactly six accepted profile IDs are supported.
[ ] All six valid profiles have positive tests.
[ ] Manual Kconfig contract is validated.
[ ] Manual requires both fixtures.
[ ] LSM/BL Kconfig contract is validated.
[ ] LSM/BL forbids both fixtures.
[ ] ARM64/KALLSYMS prerequisites are represented for lsm_bl.
[ ] BL internal SCT fallback is not misrepresented as TAMPER=y.
[ ] Shared 11 invariant is enforced.
[ ] One transport-neutral target-specific 51 invariant is enforced.
[ ] Target/adapter relationship is validated.
[ ] Invalid hybrids fail closed.
[ ] Fixture contents are provenance/hash aware.
[ ] Manifest-derived paths are safe.
[ ] No semantic classification is implemented.
[ ] No source mutation is implemented.
[ ] No patch/fixture application is implemented.
[ ] No final .config resolution is implemented.
[ ] No build/runtime validation is implemented.
[ ] Existing generators remain unchanged.
[ ] Existing generated patches remain unchanged.
[ ] Existing fixtures remain unchanged.
[ ] Existing workflows remain unchanged.
[ ] Tests run without required live network access.
[ ] Syntax/import checks pass.
[ ] Test commands/results are recorded.
[ ] Git status is recorded before and after.
[ ] No files outside the authorized scope were modified by this task.
```

Any required unchecked item means:

```text
V2.2 COMPLETE: NO
```

---

# 73. Review Gate

V2.2 completion does NOT authorize V2.3.

After V2.2:

```text
STOP
```

Do not begin:

```text
semantic inventory
semantic IDs
semantic fingerprints
coverage ledger
mixed-hunk classification
KEEP/REMOVE/REROUTE/SPLIT policy
10→11 transformation
50→51 transformation
target adapters
fixture adaptation
source-tree transformation
```

even if V2.2 finishes early.

V2.3 requires separate human authorization after review of:

```text
XXKSU_SUSFS_V2_2_REPORT.md
```

---

# 74. Final Status

The V2.2 report must end with exactly:

```text
V2.2 PROVENANCE COMPLETE: YES / NO
V2.2 CACHE/OFFLINE PREPARATION COMPLETE: YES / NO
V2.2 MANIFEST CONTRACT COMPLETE: YES / NO
V2.2 TESTS PASS: YES / NO
SAFE TO BEGIN V2.3: YES / NO
```

`SAFE TO BEGIN V2.3: YES` means only that V2.2 is technically ready for human
review and possible authorization.

It does NOT authorize V2.3.

---

# 75. STOP

After the V2.2 implementation is complete, tests have actually run, and:

```text
XXKSU_SUSFS_V2_2_REPORT.md
```

has been written:

**STOP.**

Do not stage.

Do not commit.

Do not begin V2.3.