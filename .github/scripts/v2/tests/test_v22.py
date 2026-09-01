import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
if str(SCRIPT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT.parent))

from v2.manifests import build_manifest_sets
from v2.model.manifest import (
    InvalidConfigContract, InvalidFixtureContract, ManifestError, TargetProfileMismatch,
    UnknownProfile, UnknownTarget, UnsupportedManifestSchema, load_manifest_set,
)
from v2.model.provenance import InputRef
from v2.source.cache import CacheCorruption, CacheObjectMissing, ContentAddressedCache
from v2.source.fetch import fetch
from v2.source.hashing import UnsafePath, hash_bytes, hash_tree
from v2.source.identity import GitIdentity, canonical_repository_url
from v2.source.prepare import OfflineInputMissing, prepare


class V22HashCacheTests(unittest.TestCase):
    def test_content_and_tree_hash_determinism(self):
        self.assertEqual(hash_bytes(b"same"), hash_bytes(b"same"))
        self.assertNotEqual(hash_bytes(b"same"), hash_bytes(b"changed"))
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            for root in (Path(one), Path(two)):
                (root / "sub").mkdir()
                (root / "sub" / "file").write_text("data", encoding="utf-8")
            self.assertEqual(hash_tree(one), hash_tree(two))

    def test_tree_modes_symlinks_and_git_exclusion(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            (root / "x").write_text("x", encoding="utf-8")
            first = hash_tree(root)
            mode = (root / "x").stat().st_mode
            os.chmod(root / "x", mode | stat.S_IXUSR)
            self.assertNotEqual(first, hash_tree(root))
            (root / ".git").mkdir()
            (root / ".git" / "ignored").write_text("volatile", encoding="utf-8")
            changed = hash_tree(root)
            (root / ".git" / "ignored").write_text("other", encoding="utf-8")
            self.assertEqual(changed, hash_tree(root))
            os.symlink("x", root / "link")
            with_link = hash_tree(root)
            os.unlink(root / "link")
            (root / "x").write_text("different", encoding="utf-8")
            os.symlink("x", root / "link")
            self.assertNotEqual(with_link, hash_tree(root))

    def test_cache_round_trip_corruption_and_missing(self):
        with tempfile.TemporaryDirectory() as root:
            cache = ContentAddressedCache(root)
            entry = cache.put_bytes(b"payload")
            self.assertEqual(cache.read_bytes(entry.digest), b"payload")
            entry.path.write_bytes(b"corrupt")
            with self.assertRaises(CacheCorruption):
                cache.read_bytes(entry.digest)
            with self.assertRaises(CacheObjectMissing):
                cache.read_bytes(hash_bytes(b"missing"))

    def test_cache_declared_hash_and_path_safety(self):
        with tempfile.TemporaryDirectory() as root:
            cache = ContentAddressedCache(root)
            with self.assertRaises(CacheCorruption):
                cache.put_bytes(b"x", hash_bytes(b"y"))
            with self.assertRaises(ValueError):
                cache.read_bytes("sha256:../bad")
            self.assertEqual(list(Path(root).rglob(".tmp-*")), [])

    def test_fetch_is_explicit(self):
        with tempfile.TemporaryDirectory() as root:
            cache = ContentAddressedCache(root)
            calls = []
            ref = InputRef("remote", "git", "https://example.invalid/repo", requested_ref="main")
            entry = fetch(ref, cache, lambda seen: calls.append(seen.name) or b"remote-data")
            self.assertEqual(calls, ["remote"])
            self.assertEqual(cache.read_bytes(entry.digest), b"remote-data")

    def test_git_identity_is_immutable_and_url_policy_is_conservative(self):
        self.assertEqual(canonical_repository_url("https://example.invalid/repo.git/"), "https://example.invalid/repo")
        identity = GitIdentity("https://example.invalid/repo.git", "main", "a" * 40)
        self.assertEqual(identity.to_dict()["resolved_commit"], "a" * 40)
        with self.assertRaises(ValueError):
            GitIdentity("https://example.invalid/repo", "main", "")


class V22ManifestTests(unittest.TestCase):
    def test_all_six_profiles_validate_independently(self):
        manifests = build_manifest_sets()
        self.assertEqual(len(manifests), 3)
        self.assertEqual(sum(len(item.profiles) for item in manifests), 6)
        for manifest_set in manifests:
            for profile in manifest_set.profiles:
                profile.validate(manifest_set.target)
                self.assertEqual(profile.patch_51_id, manifest_set.target.patch_51_id)

    def test_deterministic_manifest_serialization(self):
        first = build_manifest_sets()[0].canonical_json()
        second = load_manifest_set(json.loads(first)).canonical_json()
        self.assertEqual(first, second)

    def test_manifest_rejects_unknowns_and_mismatch(self):
        raw = build_manifest_sets()[0].to_dict()
        raw["target"]["schema"] = "xxksu-susfs-target/v99"
        with self.assertRaises(UnsupportedManifestSchema):
            load_manifest_set(raw)
        raw = build_manifest_sets()[0].to_dict()
        raw["target"]["target_id"] = "unknown"
        with self.assertRaises(UnknownTarget):
            load_manifest_set(raw)
        raw = build_manifest_sets()[0].to_dict()
        raw["profiles"][0]["profile_id"] = "unknown-profile"
        with self.assertRaises(UnknownProfile):
            load_manifest_set(raw)
        raw = build_manifest_sets()[0].to_dict()
        raw["profiles"][0]["mode"] = "lsm_bl"
        with self.assertRaises(TargetProfileMismatch):
            load_manifest_set(raw)

    def test_invalid_hybrid_contracts_fail_closed(self):
        raw = build_manifest_sets()[0].to_dict()
        manual = raw["profiles"][0]
        manual["kconfig"]["CONFIG_KSU_LSM_SECURITY_HOOKS"] = "y"
        with self.assertRaises(InvalidConfigContract):
            load_manifest_set(raw)
        raw = build_manifest_sets()[0].to_dict()
        raw["profiles"][1]["fixtures"] = raw["profiles"][0]["fixtures"]
        with self.assertRaises(InvalidFixtureContract):
            load_manifest_set(raw)
        raw = build_manifest_sets()[0].to_dict()
        raw["profiles"][0]["fixtures"] = raw["profiles"][0]["fixtures"][:1]
        with self.assertRaises(InvalidFixtureContract):
            load_manifest_set(raw)

    def test_shared_11_and_transport_neutral_51(self):
        raw = build_manifest_sets()[0].to_dict()
        raw["profiles"][1]["patch_11_id"] = "11-lsm"
        with self.assertRaises(ManifestError):
            load_manifest_set(raw)
        raw = build_manifest_sets()[0].to_dict()
        raw["profiles"][1]["patch_51_id"] = "51-lsm_bl"
        with self.assertRaises(ManifestError):
            load_manifest_set(raw)


class V22PreparationTests(unittest.TestCase):
    def _manifest(self, cache):
        base = build_manifest_sets()[0]
        content = b"pinned kernel bytes"
        digest = hash_bytes(content)
        cache.put_bytes(content, digest)
        target = InputRef("kernel", "tree", "local-test", resolved_commit="abc", content_hash=digest)
        target_manifest = type(base.target)(base.target.schema, base.target.target_id, (target,), base.target.adapter_id,
                                            base.target.patch_51_id, base.target.profiles)
        profile = base.profiles[1]
        return target_manifest, profile

    def test_offline_prepare_is_reproducible_and_never_fetches(self):
        with tempfile.TemporaryDirectory() as root:
            cache = ContentAddressedCache(root)
            target, profile = self._manifest(cache)
            prepared = prepare(target, cache, profile)
            prepared_again = prepare(target, cache, profile)
            self.assertEqual(prepared.provenance.identity, prepared_again.provenance.identity)
            self.assertEqual(prepared.to_json(), prepared_again.to_json())

    def test_offline_prepare_does_not_call_fetch(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as root:
            cache = ContentAddressedCache(root)
            target, profile = self._manifest(cache)
            with patch("v2.source.fetch.fetch", side_effect=AssertionError("network boundary crossed")) as mocked:
                prepare(target, cache, profile, offline=True)
            mocked.assert_not_called()

    def test_offline_missing_input_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            cache = ContentAddressedCache(root)
            target = build_manifest_sets()[0].target
            profile = build_manifest_sets()[0].profiles[1]
            missing = InputRef("kernel", "tree", "local-test", resolved_commit="abc", content_hash=hash_bytes(b"missing"))
            target = type(target)(target.schema, target.target_id, (missing,), target.adapter_id, target.patch_51_id, target.profiles)
            with self.assertRaises(OfflineInputMissing):
                prepare(target, cache, profile)

    def test_repository_fixtures_are_hashable(self):
        fixture_root = Path(__file__).resolve().parents[4] / ".github" / "fixtures"
        hashes = [hash_bytes(path.read_bytes()) for path in sorted(fixture_root.glob("*.patch"))
                  if path.name in {"scope-min-manual-hooks-v2.3.patch", "manual-security-hooks-v2.0.patch"}]
        self.assertEqual(len(hashes), 2)
        self.assertEqual(hashes, [hash_bytes(path.read_bytes()) for path in sorted(fixture_root.glob("*.patch"))
                                  if path.name in {"scope-min-manual-hooks-v2.3.patch", "manual-security-hooks-v2.0.patch"}])

    def test_relative_path_validation(self):
        from v2.source.hashing import validate_relative_path
        self.assertEqual(validate_relative_path("a/./b"), "a/b")
        with self.assertRaises(UnsafePath):
            validate_relative_path("../outside")
        with self.assertRaises(UnsafePath):
            validate_relative_path("/outside")


if __name__ == "__main__":
    unittest.main()
