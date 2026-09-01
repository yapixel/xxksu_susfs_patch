# xxKSU + SuSFS V2.2 Implementation Report

## 1. Executive Result

V2.2 adds the typed, deterministic input trust layer: SHA-256 content/tree
hashing, immutable content-addressed caching, explicit fetch/offline prepare
boundaries, provenance records, and strict target/profile manifest validation.
No semantic inventory, patch transformation, source mutation, build, or V2.3
work was performed.

## 2. Files Created / Modified

Created:

- `.github/scripts/v2/model/manifest.py`
- `.github/scripts/v2/model/provenance.py`
- `.github/scripts/v2/source/__init__.py`
- `.github/scripts/v2/source/cache.py`
- `.github/scripts/v2/source/fetch.py`
- `.github/scripts/v2/source/hashing.py`
- `.github/scripts/v2/source/identity.py`
- `.github/scripts/v2/source/prepare.py`
- `.github/scripts/v2/manifests/__init__.py`
- `.github/scripts/v2/manifests/defaults.py`
- `.github/scripts/v2/tests/test_v22.py`
- `XXKSU_SUSFS_V2_2_REPORT.md`

Modified:

- `.github/scripts/v2/__init__.py` (additive V2.2 exports)
- `.github/scripts/v2/model/__init__.py` (additive V2.2 exports)

No file outside the authorized V2 package/report scope was modified.

## 3. V2.1 Regression Status

The V2.1 parser, emitter, models, and tests remain intact. Only package export
initializers were extended so V2.2 APIs are importable; no V2.1 behavior was
changed. All V2.1 tests pass.

## 4. V2.2 Data Models

Typed dataclasses provide `InputRef`, `RepositoryRef`, `PatchRef`,
`FixtureRef`, `PreparedSource`, `PreparedInput`, `Provenance`, `HashDigest`,
`GitIdentity`, `TargetManifest`, `ProfileManifest`, and `ManifestSet`.

## 5. Input Reference Model

References carry kind, source, requested ref, optional resolved commit/tree,
optional content digest, artifact path, and original source. A branch name is
never treated as the only immutable identity for offline preparation.

## 6. Hashing Contract

Content uses `sha256:<lowercase-hex>` via Python standard-library `hashlib`.
Content changes produce different identities; timestamps, inode, mtime, and
filesystem location are excluded.

## 7. Source Tree Hash Contract

`hash_tree` traverses deterministically by normalized relative POSIX path,
records directory/file/symlink type, file bytes, and only the executable bit.
Absolute paths and enumeration order do not affect the digest.

## 8. Git Identity Contract

`GitIdentity` records original repository URL, conservative normalized URL,
requested ref, required immutable commit, optional tree ID, and content hash.
An unresolved mutable branch cannot satisfy a `GitIdentity`.

## 9. Content-Addressed Cache

`ContentAddressedCache(root)` stores objects below
`objects/sha256/<two>/<remaining>` under an explicit caller-selected root.
The working tree is never used as the cache.

## 10. Atomic Cache Population

Writes use a same-directory temporary file, flush/fsync, content verification,
and `os.replace`. Existing objects are verified and reused; different content
cannot overwrite an identity.

## 11. Cache Integrity Verification

Reads recompute SHA-256 and compare it with the requested object identity.
Missing objects raise `CacheObjectMissing`; corruption or declared hash
mismatch raises `CacheCorruption`.

## 12. Network / Offline Boundary

`fetch` is the only acquisition boundary. `prepare` is offline-only and has no
network fallback or implicit call to fetch.

## 13. Fetch Contract

`fetch(reference, cache, acquire=...)` requires explicit acquisition for remote
sources; local file sources are supported for deterministic tests. It verifies
declared content hashes and returns a typed cache entry. It does not transform
patches, apply fixtures, or build.

## 14. Offline Preparation Contract

`prepare` validates the target/profile manifest, requires immutable content
hashes, verifies cache objects, and constructs prepared/provenance records.
Missing cached inputs raise `OfflineInputMissing`; no redownload is attempted.

## 15. PreparedInput Model

`PreparedInput` contains target/profile IDs, ordered verified `PreparedSource`
records, and a deterministic `Provenance` object. It is serializable with
canonical JSON and contains no semantic transformation result.

## 16. Provenance Model

Provenance records schema, target/profile, manifest digest, preparation version,
reference metadata, cache identity, and content identity. Operational timestamps
are absent, so they cannot affect identity.

## 17. Deterministic Serialization

Machine output uses JSON with sorted keys, compact separators, and stable UTF-8
encoding. `PreparedInput.to_json()` and manifest canonical views are repeatable.

## 18. Target Manifest Schema

Target manifests require `xxksu-susfs-target/v1`, one of exactly three target
IDs, upstream input references, target adapter ID, one shared 11 ID, one
transport-neutral target 51 ID, and both profile IDs.

## 19. Profile Manifest Schema

Profile manifests require `xxksu-susfs-profile/v1`, a complete profile ID,
matching target/mode, exact Kconfig map, prerequisites, fixture declarations,
ownership map, shared 11 ID, target 51 ID, and adapter relationship.

## 20. Six Supported Profiles

All six are represented and independently validated:

- `gki-android14-6.1-manual`
- `gki-android14-6.1-lsm_bl`
- `gki-android16-6.12-manual`
- `gki-android16-6.12-lsm_bl`
- `sultan-android14-6.1-manual`
- `sultan-android14-6.1-lsm_bl`

## 21. Manual Contract Validation

Manual requires the exact Kconfig contract (`LSM=n`, `BL=n`, `TAMPER=n`,
`KPROBES=n`) plus both named fixtures. Ownership values must be the two manual
fixture providers; automated transport owners are rejected.

## 22. LSM/BL Contract Validation

`lsm_bl` requires `LSM=y`, `BL=y`, `TAMPER=n`, `KPROBES=n`, ARM64, KALLSYMS,
and `XXKSU_BL_COMPOSITE`. Fixtures are forbidden. Internal BL syscall fallback
is represented as a composite owner, not as `TAMPER=y`.

## 23. Shared 11 Invariant

Every profile must use the literal `shared-11`; mode-specific 11 IDs are
rejected.

## 24. Transport-Neutral 51 Invariant

Each target has one target-specific 51 policy referenced identically by manual
and lsm_bl profiles. Mode-specific 51 IDs are rejected.

## 25. BL Composite Ownership Representation

The explicit `XXKSU_BL_COMPOSITE` owner records branch-link plus xxKSU’s
internally managed syscall fallback without changing the declared TAMPER
Kconfig value.

## 26. Adapter Declaration Validation

The three accepted adapter IDs are mapped one-to-one to their target IDs;
cross-target adapters fail validation. Adapter behavior is not implemented.

## 27. Fixture Provenance

Fixture references are typed and include deterministic repository-relative paths.
Their bytes can be hashed and cached; V2.2 never applies them.

## 28. Path / Symlink Safety

Manifest/cache-relative paths reject absolute paths, drive-qualified paths,
NULs, and `..` traversal. Tree hashing excludes `.git`, does not follow
symlinks, and hashes link targets as typed entries.

## 29. Error Model

Typed failures cover manifest/schema/target/profile/config/fixture errors,
unresolved identity, unsafe paths, missing offline inputs, cache misses,
corruption, and fetch failures. Errors do not embed arbitrary command output.

## 30. Test Architecture

The standard-library `unittest` suite combines the unchanged V2.1 tests with
focused V2.2 tests. Temporary directories isolate cache/tree tests; no live
network is required.

## 31. Six-Profile Positive Tests

Tests validate all three target manifests and both profiles for each target
independently, including exact mode Kconfig and target-specific 51 references.

## 32. Invalid-Hybrid Negative Tests

Tests reject unknown schema/target/profile, target/profile mismatch, manual
automated transport, missing manual fixture, lsm_bl fixture presence, config
hybrids, shared-11 violations, and mode-specific 51 selection.

## 33. Cache Negative Tests

Tests cover missing objects, corrupted objects, declared hash mismatch, unsafe
cache digest paths, and absence of leftover temporary objects.

## 34. Offline Guarantee Test

The test patches the fetch boundary to fail if called and verifies offline
prepare completes without invoking it. Missing pinned cache content fails closed.

## 35. Determinism Tests

Tests cover equal/changed content, equal trees at different absolute roots,
executable-bit changes, symlink identity, `.git` exclusion, deterministic
manifest serialization, and reproducible prepared provenance.

## 36. Repository Input Tests

Both existing manual fixture files are read from the repository and their
content hashes are derived and checked for stability. No fixture is modified.

## 37. Commands Executed

From WSL Debian with Python 3.11:

```text
python3 -m compileall -q .github/scripts/v2
PYTHONPATH=.github/scripts python3 -m unittest discover -s .github/scripts/v2/tests -v
PYTHONPATH=.github/scripts python3 -c "import v2; print(v2.parse_patch(\"\").structural_key())"
```

## 38. Test Results

All 32 tests passed: all 16 V2.1 tests and 16 V2.2 tests. Compileall passed;
the import smoke check returned `((), (), ())`.

## 39. Git Status Before / After

Before implementation, status contained the pre-existing untracked V2.1/V2
reports/design/task documents and `.github/scripts/v2/`; no tracked files were
modified. After implementation, the same pre-existing entries remain, with
the V2.2 additions under `.github/scripts/v2/` and this report. Nothing was
staged, committed, reset, cleaned, or otherwise repository-managed.

## 40. Design Deviations

No accepted architecture was changed. JSON was used instead of YAML to avoid a
new dependency. The default manifests keep kernel and official-10 identities
explicitly unresolved where immutable evidence is not established, while
recording established official-50 and xxKSU revisions.

## 41. Remaining V2.2 Limitations

Remote Git acquisition beyond the injected fetch callback is intentionally not
implemented; no archive extraction, full Git object/tree resolver, or final
`.config` resolution is included. These are explicit V2.2 boundaries.

## 42. V2.3 Readiness

The provenance, cache/offline, and manifest contract foundation is stable for
human review and possible V2.3 authorization. V2.3 semantic work was not begun.

## 43. Confidence Report

| Area | Confidence | Evidence |
|---|---|---|
| content/tree hashing | HIGH | deterministic and mode/symlink tests |
| cache integrity/atomicity | HIGH | round-trip, corruption, mismatch tests |
| offline boundary | HIGH | missing-input and fetch-not-called tests |
| manifest contracts | HIGH | six positives and hybrid negatives |
| provenance determinism | HIGH | canonical serialization/reproducibility tests |
| upstream fetch integration | MEDIUM | explicit injectable boundary; no live network by design |
| semantic ownership | NOT IMPLEMENTED | reserved for V2.3 |

V2.2 PROVENANCE COMPLETE: YES
V2.2 CACHE/OFFLINE PREPARATION COMPLETE: YES
V2.2 MANIFEST CONTRACT COMPLETE: YES
V2.2 TESTS PASS: YES
SAFE TO BEGIN V2.3: YES
