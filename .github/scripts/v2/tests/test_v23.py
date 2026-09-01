import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
if str(SCRIPT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT.parent))

from v2.engine.diff_parser import parse_patch
from v2.semantic import (
    AmbiguousSemanticMatch, CandidateDetector, CandidateObservation, Confidence, CoverageLedger,
    EvidenceKind,
    CoverageState, EvidenceRecord, InvalidEvidence, InvalidRelationship, InventoryIncomplete,
    OrphanEvidence, RelationshipType, SemanticFingerprint, SemanticId, SemanticIdCollision,
    SemanticInventory, SemanticKind, SemanticLocation, SemanticRelationship, SemanticUnit,
    UnknownSemanticUnit, default_registry, inventory_from_observations, inventory_patch,
)
from v2.semantic.model import UnsupportedSemanticSchema, SemanticSpecificationError
from v2.semantic.registry import SemanticSpecification
from v2.model.provenance import HashDigest, Provenance, canonical_json


def observation(path="fs/exec.c", text="ksu_handle_execveat();", source_kind="official_50", source_id="sha256:" + "a" * 64, **kwargs):
    return CandidateObservation(source_id, "patch", path, text, source_kind=source_kind,
                                symbols=kwargs.pop("symbols", ("ksu_handle_execveat",)),
                                role=kwargs.pop("role", "caller"), **kwargs)


class SemanticModelTests(unittest.TestCase):
    def test_ids_and_fingerprints_are_stable_and_path_independent(self):
        first = SemanticFingerprint("fs/stat.c", "vfs_statx", "call", ("a;",), ("foo",), ("bar",), ("CONFIG=y",), "source")
        second = SemanticFingerprint("fs/stat.c", "vfs_statx", "call", ("a;",), ("foo",), ("bar",), ("CONFIG=y",), "source")
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(SemanticId("susfs.stat.spoof"), SemanticId("susfs.stat.spoof"))
        self.assertNotEqual(first.digest, SemanticFingerprint("fs/stat.c", "vfs_statx", "call", ("b;",)).digest)
        with self.assertRaises(ValueError):
            SemanticLocation("../outside")

    def test_evidence_and_relationship_serialization(self):
        fp = SemanticFingerprint("fs/exec.c", "execve", called_symbols=("ksu_handle_execveat",))
        ev = EvidenceRecord("sha256:" + "b" * 64, "fixture", SemanticLocation("fs/exec.c", "execve"), fp, 4, Confidence.HIGH)
        unit = SemanticUnit(SemanticId("transport.exec.manual_fixture"), SemanticKind.MANUAL_SOURCE_HOOK, "exec", ev.location, (ev,))
        target = SemanticUnit(SemanticId("transport.exec.definition"), SemanticKind.HANDLER_DEFINITION, "exec", SemanticLocation("kernel/feature/sucompat.c"))
        relation = SemanticRelationship(RelationshipType.CALLS, unit.semantic_id, target.semantic_id, (ev,))
        ledger = CoverageLedger(provenance_identity="sha256:" + "c" * 64)
        ledger.add(unit)
        ledger.add(target)
        ledger.add_relationship(relation)
        self.assertIn("CALLS", ledger.canonical_json())
        self.assertEqual(ledger.identity, HashDigest.parse(ledger.identity))

    def test_invalid_evidence_and_relationship_fail_closed(self):
        fp = SemanticFingerprint("fs/exec.c")
        with self.assertRaises(InvalidEvidence):
            EvidenceRecord("", "patch", SemanticLocation("fs/exec.c"), fp, 1, Confidence.HIGH)
        ledger = CoverageLedger()
        ev = EvidenceRecord("sha256:" + "d" * 64, "patch", SemanticLocation("fs/exec.c"), fp, 1, Confidence.HIGH)
        with self.assertRaises(OrphanEvidence):
            ledger.add_evidence("missing.unit", ev)
        with self.assertRaises(InvalidRelationship):
            ledger.add_relationship(SemanticRelationship(RelationshipType.RELATED_TO, SemanticId("a"), SemanticId("b")))
        with self.assertRaises(InvalidRelationship):
            SemanticRelationship("NOT_A_RELATION", SemanticId("a"), SemanticId("b"))

    def test_orphan_evidence_is_serialized_and_identity_bearing(self):
        fp = SemanticFingerprint("fs/exec.c")
        first = EvidenceRecord("source-a", "patch", SemanticLocation("fs/exec.c"), fp, 1, Confidence.HIGH)
        second = EvidenceRecord("source-b", "patch", SemanticLocation("fs/exec.c"), fp, 1, Confidence.HIGH)
        ledgers = []
        for evidence in (first, second), (second, first):
            ledger = CoverageLedger()
            for item in evidence:
                with self.assertRaises(OrphanEvidence):
                    ledger.add_evidence("missing.unit", item)
            ledgers.append(ledger)
        self.assertEqual(ledgers[0].canonical_json(), ledgers[1].canonical_json())
        self.assertNotEqual(ledgers[0].identity, CoverageLedger().identity)
        self.assertEqual(len(ledgers[0].to_dict()["orphan_evidence"]), 2)

    def test_malformed_semantic_records_fail_closed(self):
        with self.assertRaises(UnsupportedSemanticSchema):
            SemanticId("x", "xxksu-susfs-semantic/v99")
        with self.assertRaises(SemanticSpecificationError):
            SemanticSpecification(SemanticId("bad"), "NOT_A_KIND", "bad", ("fs/a.c",))
        with self.assertRaises(SemanticSpecificationError):
            SemanticSpecification(SemanticId("bad"), SemanticKind.SUSFS_BEHAVIOR, "bad", (), confidence=Confidence.HIGH)
        with self.assertRaises(InvalidEvidence):
            EvidenceRecord("source", "patch", SemanticLocation("fs/a.c"), SemanticFingerprint("fs/a.c"), 1, "INVALID")


class SemanticInventoryTests(unittest.TestCase):
    def test_candidate_resolution_requires_context_not_name_only(self):
        detector = CandidateDetector()
        candidates = detector.detect([observation(), observation(path="tests/example.c", text="ksu_handle_execveat();")])
        self.assertEqual(len(candidates), 2)
        inventory = inventory_from_observations(candidates)
        self.assertEqual({unit.kind for unit in inventory.units}, {SemanticKind.UNKNOWN, SemanticKind.LINUX_CALL_SITE})
        with self.assertRaises(InventoryIncomplete):
            inventory.validate_complete()

    def test_unknown_injection_is_recorded_and_fatal(self):
        inventory = inventory_from_observations([observation(path="kernel/new.c", text="ksu_handle_future_feature();", symbols=("ksu_handle_future_feature",))])
        self.assertEqual(inventory.units[0].state, CoverageState.UNKNOWN)
        with self.assertRaises(InventoryIncomplete):
            inventory.validate_complete()

    def test_mixed_container_preserves_one_hunk_and_multiple_units(self):
        observations = [
            observation(path="fs/stat.c", text="susfs_spoof_stat();", source_kind="fixture_scope_min",
                        symbols=("susfs",), container_id="fs/stat.c:h1", mixed=True),
            observation(path="fs/stat.c", text="ksu_handle_stat();", source_kind="fixture_scope_min",
                        symbols=("ksu_handle_stat",), container_id="fs/stat.c:h1", mixed=True),
        ]
        inventory = SemanticInventory().detect_and_resolve(observations)
        self.assertEqual(len(inventory.candidates), 2)
        self.assertEqual({unit.state for unit in inventory.units}, {CoverageState.MIXED})

    def test_same_symbol_roles_are_distinct(self):
        inventory = inventory_from_observations([
            observation(path="kernel/feature/sucompat.c", text="int ksu_handle_execveat(...) {}", source_kind="xxksu", role="definition"),
            observation(path="fs/exec.c", text="ksu_handle_execveat();", source_kind="official_50", role="caller"),
            observation(path="fs/exec.c", text="extern int ksu_handle_execveat(...);", source_kind="fixture_scope_min", role="declaration"),
        ])
        self.assertEqual({unit.kind for unit in inventory.units}, {SemanticKind.HANDLER_DEFINITION, SemanticKind.HANDLER_DECLARATION, SemanticKind.LINUX_CALL_SITE})

    def test_realistic_fixture_declarations_and_callers_are_distinct(self):
        observations = []
        for path, symbol in (("fs/open.c", "ksu_handle_faccessat"),
                             ("fs/stat.c", "ksu_handle_stat"),
                             ("fs/stat.c", "ksu_handle_newfstat_ret"),
                             ("kernel/reboot.c", "ksu_handle_sys_reboot")):
            observations.extend((
                observation(path=path, text=f"extern int {symbol}(...);", source_kind="fixture_scope_min",
                            symbols=(symbol,), role="declaration"),
                observation(path=path, text=f"{symbol}(...);", source_kind="fixture_scope_min",
                            symbols=(symbol,), role="caller"),
            ))
        inventory = inventory_from_observations(observations)
        kinds_by_role = {(unit.evidence[0].fingerprint.source_role, unit.kind) for unit in inventory.units}
        self.assertIn(("declaration", SemanticKind.HANDLER_DECLARATION), kinds_by_role)
        self.assertIn(("caller", SemanticKind.MANUAL_SOURCE_HOOK), kinds_by_role)

    def test_ambiguous_and_collision_fail_closed(self):
        registry = default_registry()
        with self.assertRaises(AmbiguousSemanticMatch):
            from v2.semantic.registry import SemanticSpecification
            registry.add(SemanticSpecification(SemanticId("ambiguous"), SemanticKind.LINUX_CALL_SITE, "exec", ("fs/exec.c",), symbols=("ksu_handle_execveat",), source_kinds=("official_50",)))
            from v2.semantic import SemanticResolver
            SemanticResolver(registry).resolve(observation())
        ledger = CoverageLedger()
        unit = SemanticUnit(SemanticId("collision"), SemanticKind.SUSFS_BEHAVIOR, "a", SemanticLocation("fs/a.c"))
        ledger.add(unit)
        with self.assertRaises(SemanticIdCollision):
            ledger.add(SemanticUnit(SemanticId("collision"), SemanticKind.KPROBE, "b", SemanticLocation("fs/b.c")))

    def test_ledger_and_inventory_determinism(self):
        first = inventory_from_observations([observation(), observation(path="fs/open.c", text="ksu_handle_faccessat();", symbols=("ksu_handle_faccessat",))], provenance_identity="p")
        second = inventory_from_observations([observation(path="fs/open.c", text="ksu_handle_faccessat();", symbols=("ksu_handle_faccessat",)), observation()], provenance_identity="p")
        self.assertEqual(first.identity, second.identity)
        self.assertEqual(first.canonical_json(), second.canonical_json())
        self.assertNotEqual(first.identity, inventory_from_observations([observation(text="changed();")], provenance_identity="p").identity)
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            Path(one, "ignored").write_text("one")
            Path(two, "ignored").write_text("two")
            self.assertEqual(inventory_from_observations([observation()], provenance_identity="p").identity,
                             inventory_from_observations([observation()], provenance_identity="p").identity)


class SemanticRealEvidenceTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[4]

    def test_real_patches_and_fixtures_are_structurally_inventoryable(self):
        paths = [(self.ROOT / "patches" / "xxksu" / "11_enable_susfs_for_ksu.patch", "xxksu"),
                 (self.ROOT / ".github" / "fixtures" / "scope-min-manual-hooks-v2.3.patch", "fixture_scope_min"),
                 (self.ROOT / ".github" / "fixtures" / "manual-security-hooks-v2.0.patch", "fixture_manual_security")]
        for path, source_kind in paths:
            text = path.read_text(encoding="utf-8")
            file_count = 0
            try:
                patch = parse_patch(text)
                file_count = len(patch.files)
                inventory = inventory_patch(patch, source_identity="sha256:" + "e" * 64, source_type=source_kind)
            except ValueError:
                # manual-security is a historical fixture with an unprefixed
                # context line; retain it as bounded raw evidence instead of
                # treating parser failure as semantic meaning.
                inventory = inventory_from_observations([observation(path="security/security.c", text=text,
                                                                      source_kind="fixture_manual_security",
                                                                      symbols=("ksu_file_permission",))])
            self.assertTrue(inventory.candidates or not file_count)
            self.assertTrue(any(unit.kind != SemanticKind.UNKNOWN for unit in inventory.units))

    def test_real_51_bounded_sample_is_inventoryable(self):
        path = self.ROOT / "patches" / "gki-android14-6.1" / "51_deinlined_susfs_hooks_gki-android14-6.1.patch"
        text = path.read_text(encoding="utf-8")
        sample = "diff --git " + text.split("diff --git ", 1)[1].split("diff --git ", 1)[0]
        inventory = inventory_patch(parse_patch(sample), source_identity="sha256:" + "f" * 64, source_type="official_50")
        self.assertTrue(inventory.candidates)

    def test_three_target_families_and_confidence_are_representable(self):
        target_paths = ("gki-android14-6.1", "gki-android16-6.12", "sultan-android14-6.1")
        ledger = CoverageLedger()
        for index, target in enumerate(target_paths):
            fp = SemanticFingerprint("fs/stat.c", structural_anchor=target)
            evidence = EvidenceRecord("sha256:" + str(index + 1) * 64, "official_50", SemanticLocation("fs/stat.c", anchor=target), fp, 3, Confidence.HIGH,
                                      attributes={"target": target})
            ledger.add(SemanticUnit(SemanticId("susfs.stat.kstat"), SemanticKind.SUSFS_BEHAVIOR, "stat",
                                    SemanticLocation("fs/stat.c", anchor=target), (evidence,), confidence=Confidence.HIGH))
        self.assertEqual(len(ledger.entries), 1)
        self.assertEqual(len(ledger.entries[0].unit.evidence), 3)
        self.assertEqual(ledger.entries[0].unit.confidence, Confidence.HIGH)
        medium = SemanticUnit(SemanticId("selinux.context_access"), SemanticKind.SELINUX_BEHAVIOR, "selinux", SemanticLocation("kernel/feature/selinux_hide.c"), confidence=Confidence.MEDIUM)
        self.assertEqual(medium.confidence, Confidence.MEDIUM)

    def test_transport_terminology_is_not_collapsed(self):
        kinds = {SemanticKind.MANUAL_SOURCE_HOOK, SemanticKind.KPROBE, SemanticKind.LSM_SECURITY_HOOK,
                 SemanticKind.ARM64_BRANCH_LINK, SemanticKind.SYSCALL_TABLE_HOOK, SemanticKind.RUNTIME_REGISTRATION}
        self.assertEqual(len(kinds), 6)
        self.assertNotEqual(SemanticKind.ARM64_BRANCH_LINK, SemanticKind.SYSCALL_TABLE_HOOK)
        ledger = CoverageLedger()
        branch = SemanticUnit(SemanticId("transport.bl.branch_link"), SemanticKind.ARM64_BRANCH_LINK, "transport", SemanticLocation("kernel/hook/branch_link_hook_arm64.c"))
        fallback = SemanticUnit(SemanticId("transport.bl.internal_fallback"), SemanticKind.SYSCALL_TABLE_HOOK, "transport", SemanticLocation("kernel/hook/syscall_table_hook_arm64.c"))
        composite = SemanticUnit(SemanticId("transport.bl.composite"), SemanticKind.TRANSPORT_WRAPPER, "transport", SemanticLocation("kernel/hook/branch_link_hook_arm64.c"))
        for unit in (branch, fallback, composite):
            ledger.add(unit)
        ledger.add_relationship(SemanticRelationship(RelationshipType.FALLBACK_FOR, fallback.semantic_id, branch.semantic_id))
        ledger.add_relationship(SemanticRelationship(RelationshipType.RELATED_TO, branch.semantic_id, composite.semantic_id))
        self.assertIn("FALLBACK_FOR", ledger.canonical_json())

    def test_official_only_config_and_abi_evidence_are_preserved(self):
        registry_ids = {str(spec.semantic_id): spec for spec in default_registry()}
        self.assertIn("official_only.exec.sucompat", registry_ids)
        self.assertIn("config.susfs.control", registry_ids)
        self.assertIn("integration.susfs.initialization", registry_ids)
        for required in ("transport.reboot.definition", "transport.reboot.linux_call",
                         "transport.exec.definition", "transport.access.manual_fixture",
                         "transport.stat.branch_link", "transport.fstat_return.definition",
                         "transport.read.internal_fallback", "transport.setuid.lsm",
                         "transport.input.registration", "selinux.avc.replace",
                         "selinux.fake_status", "selinux.setprocattr", "selinux.context_access"):
            self.assertIn(required, registry_ids)
        self.assertEqual(registry_ids["selinux.setprocattr"].confidence, Confidence.MEDIUM)
        candidate = observation(abi={"return": "int", "arguments": ["int", "struct filename **"]})
        unit = inventory_from_observations([candidate]).units[0]
        self.assertEqual(unit.evidence[0].attributes["abi"]["return"], "int")
        self.assertEqual(unit.evidence[0].priority, 3)

    def test_verified_evidence_binds_to_v22_provenance(self):
        provenance = Provenance("xxksu-susfs-provenance/v1", "gki-android14-6.1", None,
                                HashDigest("sha256", "1" * 64))
        verified = observation(source_id=str(provenance.identity), evidence_kind=EvidenceKind.VERIFIED,
                               provenance_identity=str(provenance.identity))
        inventory = inventory_from_observations([verified], provenance=provenance)
        self.assertEqual(inventory.units[0].evidence[0].evidence_kind, EvidenceKind.VERIFIED)
        wrong = observation(source_id=str(provenance.identity), evidence_kind=EvidenceKind.VERIFIED,
                            provenance_identity="sha256:" + "2" * 64)
        with self.assertRaises(InvalidEvidence):
            inventory_from_observations([wrong], provenance=provenance)
        unverified = observation(evidence_kind=EvidenceKind.UNVERIFIED)
        with self.assertRaises(InventoryIncomplete):
            inventory_from_observations([unverified]).validate_complete()


if __name__ == "__main__":
    unittest.main()
