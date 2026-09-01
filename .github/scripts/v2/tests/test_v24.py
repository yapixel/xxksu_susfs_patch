import unittest

from v2.engine import parse_patch
from v2.policy import (
    OwnerKind, PolicyAction, PolicyIncomplete, PolicyOccurrence,
    decide_patch51 as production_decide_patch51,
)
from v2.policy.patch51 import classify_patch51
from v2.semantic import (
    CandidateObservation, Confidence, EvidenceKind, InventoryIncomplete, RelationshipType,
    SemanticId, SemanticKind, SemanticRegistry, SemanticRelationship, SemanticSpecification,
    SemanticInventory, default_registry, inventory_patch,
)


def decide_patch51(source, **kwargs):
    return classify_patch51(source, validate=kwargs.get("require_complete", True))


_OFFICIAL = {
    "susfs.uname.behavior": ("kernel/sys.c", "susfs_spoof_uname"),
    "susfs.stat.kstat": ("fs/stat.c", "kstat"),
    "susfs.stat.mount_id": ("fs/stat.c", "mnt_id"),
    "transport.exec.linux_call": ("fs/exec.c", "ksu_handle_execveat"),
    "transport.access.linux_call": ("fs/open.c", "ksu_handle_faccessat"),
    "transport.stat.linux_call": ("fs/stat.c", "ksu_handle_stat"),
    "transport.fstat_return.linux_call": ("fs/stat.c", "ksu_handle_vfs_fstat"),
    "transport.read.linux_call": ("fs/read_write.c", "ksu_handle_sys_read"),
    "transport.reboot.linux_call": ("kernel/reboot.c", "ksu_handle_sys_reboot"),
    "transport.setuid.linux_call": ("kernel/sys.c", "ksu_handle_setresuid"),
    "transport.input.official_assumption": ("drivers/input/input.c", "ksu_handle_input_handle_event"),
    "official50.selinux.avc": ("security/selinux/avc.c", "slow_avc_audit"),
    "official50.selinux.setprocattr": ("security/selinux/hooks.c", "my_setprocattr"),
    "official50.selinux.fake_status": ("security/selinux/selinuxfs.c", "ksu_fake_status"),
    "official50.selinux.context_access": ("security/selinux/selinuxfs.c", "my_write_context"),
    "official50.selinux.services_wrappers": ("security/selinux/ss/services.c", "backup_sepolicy"),
}

_REPLACEMENTS = {
    "transport.exec.linux_call": ("transport.exec.definition", "kernel/feature/sucompat.c",
                                  "ksu_handle_execveat", "definition", RelationshipType.PROVIDES_TRANSPORT_FOR),
    "transport.access.linux_call": ("transport.access.definition", "kernel/feature/sucompat.c",
                                    "ksu_handle_faccessat", "definition", RelationshipType.PROVIDES_TRANSPORT_FOR),
    "transport.stat.linux_call": ("transport.stat.definition", "kernel/feature/sucompat.c",
                                  "ksu_handle_stat", "definition", RelationshipType.PROVIDES_TRANSPORT_FOR),
    "transport.fstat_return.linux_call": ("transport.fstat_return.definition", "kernel/runtime/ksud.c",
                                          "ksu_handle_newfstat_ret", "definition",
                                          RelationshipType.PROVIDES_TRANSPORT_FOR),
    "transport.read.linux_call": ("transport.read.internal_fallback", "kernel/hook/syscall_table_hook_arm64.c",
                                  "ksu_handle_sys_read_fd", "fallback",
                                  RelationshipType.PROVIDES_TRANSPORT_FOR),
    "transport.reboot.linux_call": ("transport.reboot.definition", "kernel/supercall/supercall.c",
                                    "ksu_handle_sys_reboot", "definition", RelationshipType.PROVIDES_TRANSPORT_FOR),
    "transport.setuid.linux_call": ("transport.setuid.definition", "kernel/hook/setuid_hook.c",
                                    "ksu_handle_setresuid", "definition",
                                    RelationshipType.PROVIDES_TRANSPORT_FOR),
    "transport.input.official_assumption": ("transport.input.registration", "kernel/feature/vol_detector.c",
                                            "input_register_handler", "caller",
                                            RelationshipType.REPLACES_BEHAVIOR_OF),
    "official50.selinux.avc": ("selinux.avc.replace", "kernel/downstream/slow_avc_audit_defs.h",
                               "slow_avc_audit", "caller", RelationshipType.REPLACES_BEHAVIOR_OF),
    "official50.selinux.setprocattr": ("selinux.setprocattr", "kernel/feature/selinux_hide.c",
                                       "ksu_hide_setprocattr", "caller", RelationshipType.REPLACES_BEHAVIOR_OF),
    "official50.selinux.fake_status": ("selinux.fake_status", "kernel/feature/selinux_hide.c",
                                       "ksu_fake_status_page", "caller", RelationshipType.REPLACES_BEHAVIOR_OF),
    "official50.selinux.context_access": ("selinux.context_access", "kernel/feature/selinux_hide.c",
                                          "write_context", "caller", RelationshipType.REPLACES_BEHAVIOR_OF),
    "official50.selinux.services_wrappers": ("selinux.context_access", "kernel/feature/selinux_hide.c",
                                             "write_context", "caller", RelationshipType.REPLACES_BEHAVIOR_OF),
}


def official(value, *, line=1, container=None, mixed=False, container_text=None, abi=None, path=None):
    default_path, symbol = _OFFICIAL[value]
    text = f"{symbol}();"
    return CandidateObservation("official-50-test", "official_50", path or default_path, text,
                                source_kind="official_50", symbols=(symbol,), container_id=container,
                                mixed=mixed, start_line=line, abi={"validated": True, **(abi or {})}, role="caller",
                                evidence_kind=EvidenceKind.SYNTHETIC,
                                container_text=container_text or text)


def source_observation(path, symbol, role):
    text = f"void {symbol}(void) {{" if role == "definition" else f"{symbol}();"
    return CandidateObservation("xxksu-test", "xxksu", path, text, source_kind="xxksu",
                                symbols=(symbol,), container_id=f"replacement:{symbol}", start_line=1,
                                abi={"validated": True}, role=role, evidence_kind=EvidenceKind.SYNTHETIC,
                                container_text=text)


def inventory(*observations, registry=None, replacements=True):
    result = SemanticInventory(allow_synthetic=True, registry=registry)
    official_units = {}
    for observation in observations:
        resolved = result.add_candidate(observation)
        official_units.setdefault(str(resolved.semantic_id), resolved)
    if replacements:
        sources = {}
        for semantic_id in tuple(official_units):
            replacement = _REPLACEMENTS.get(semantic_id)
            if not replacement:
                continue
            source_id, path, symbol, role, relation = replacement
            if source_id not in sources:
                sources[source_id] = result.add_candidate(source_observation(path, symbol, role))
            source = sources[source_id]
            target = official_units[semantic_id]
            result.add_relationship(SemanticRelationship(relation, source.semantic_id, target.semantic_id,
                                                         (source.evidence[0],)))
    return result


class Patch51PolicyTests(unittest.TestCase):
    def test_pure_keep_and_transport_reroute_remove(self):
        source = inventory(official("susfs.uname.behavior"), official("transport.reboot.linux_call"),
                           official("official50.selinux.services_wrappers"))
        decisions = {str(item.semantic_id): item for item in decide_patch51(source).decisions}
        self.assertEqual(decisions["susfs.uname.behavior"].action, PolicyAction.KEEP)
        self.assertEqual(decisions["transport.reboot.linux_call"].action, PolicyAction.REROUTE)
        self.assertEqual(decisions["official50.selinux.services_wrappers"].action, PolicyAction.REMOVE)

    def test_safe_mixed_split_preserves_independent_susfs(self):
        text = "kstat();\nmnt_id();\nksu_handle_stat();"
        source = inventory(
            official("susfs.stat.kstat", line=20, container="fs/stat.c:h1", mixed=True, container_text=text),
            official("susfs.stat.mount_id", line=21, container="fs/stat.c:h1", mixed=True, container_text=text),
            official("transport.stat.linux_call", line=22, container="fs/stat.c:h1", mixed=True,
                     container_text=text))
        ledger = decide_patch51(source)
        self.assertEqual(ledger.mixed_blocks[0].action, PolicyAction.SPLIT)
        self.assertEqual({item.action for item in ledger.mixed_blocks[0].members},
                         {PolicyAction.KEEP, PolicyAction.REROUTE})
        actions = {str(item.semantic_id): item.action for item in ledger.decisions}
        self.assertEqual(actions["susfs.stat.kstat"], PolicyAction.KEEP)
        self.assertEqual(actions["susfs.stat.mount_id"], PolicyAction.KEEP)

    def test_unsafe_or_ambiguous_mixed_block_is_unknown_and_fatal(self):
        text = "if (enabled) {\nkstat();\nksu_handle_stat();\n}"
        source = inventory(official("susfs.stat.kstat", line=20, container="fs/stat.c:h1", mixed=True,
                                    container_text=text),
                           official("transport.stat.linux_call", line=21, container="fs/stat.c:h1", mixed=True,
                                    container_text=text))
        ledger = decide_patch51(source, require_complete=False)
        self.assertEqual(ledger.mixed_blocks[0].action, PolicyAction.UNKNOWN)
        with self.assertRaises(PolicyIncomplete):
            decide_patch51(source)

    def test_unsupported_semantics_are_unknown_and_wrong_path_fails_inventory(self):
        custom = SemanticSpecification(SemanticId("official50.new.behavior"), SemanticKind.SUSFS_BEHAVIOR,
                                       "new", ("fs/new.c",), symbols=("new_behavior",),
                                       source_kinds=("official_50",), confidence=Confidence.HIGH)
        registry = SemanticRegistry((*tuple(default_registry()), custom))
        unknown = CandidateObservation("official-50-test", "official_50", "fs/new.c", "new_behavior();",
                                       source_kind="official_50", symbols=("new_behavior",), start_line=1,
                                       evidence_kind=EvidenceKind.SYNTHETIC, container_text="new_behavior();")
        source = inventory(unknown, registry=registry)
        self.assertEqual(decide_patch51(source, require_complete=False).decisions[0].action, PolicyAction.UNKNOWN)
        with self.assertRaises(PolicyIncomplete):
            decide_patch51(source)
        with self.assertRaises(InventoryIncomplete):
            decide_patch51(inventory(official("transport.exec.linux_call", path="fs/stat.c")))

    def test_function_name_and_git_apply_status_do_not_drive_policy(self):
        custom = SemanticSpecification(SemanticId("official50.new.behavior"), SemanticKind.SUSFS_BEHAVIOR,
                                       "new", ("fs/new.c",), symbols=("ksu_handle_execveat",),
                                       source_kinds=("official_50",), confidence=Confidence.HIGH)
        registry = SemanticRegistry((*tuple(default_registry()), custom))
        def candidate(status):
            return CandidateObservation("official-50-test", "official_50", "fs/new.c",
                                        "ksu_handle_execveat();", source_kind="official_50",
                                        symbols=("ksu_handle_execveat",), start_line=1,
                                        abi={"git_apply": status}, evidence_kind=EvidenceKind.SYNTHETIC,
                                        container_text="ksu_handle_execveat();")
        first = decide_patch51(inventory(candidate("success"), registry=registry), require_complete=False).decisions[0]
        second = decide_patch51(inventory(candidate("failure"), registry=registry), require_complete=False).decisions[0]
        self.assertEqual((first.action, first.rationale), (PolicyAction.UNKNOWN, second.rationale))

    def test_arbitrary_arguments_cannot_receive_destructive_policy(self):
        forged = (
            CandidateObservation("official-50-test", "official_50", "fs/exec.c",
                                 "ksu_handle_execveat(delete_everything());", source_kind="official_50",
                                 symbols=("ksu_handle_execveat",), start_line=1, role="caller",
                                 evidence_kind=EvidenceKind.SYNTHETIC,
                                 container_text="ksu_handle_execveat(delete_everything());"),
            CandidateObservation("official-50-test", "official_50", "security/selinux/ss/services.c",
                                 "backup_sepolicy(forged_payload());", source_kind="official_50",
                                 symbols=("backup_sepolicy",), start_line=1, role="caller",
                                 evidence_kind=EvidenceKind.SYNTHETIC,
                                 container_text="backup_sepolicy(forged_payload());"),
        )
        decisions = decide_patch51(inventory(*forged), require_complete=False).decisions
        self.assertEqual({item.action for item in decisions}, {PolicyAction.UNKNOWN})

    def test_selinux_domains_are_resolved_and_explicitly_accounted(self):
        source = inventory(*(official(value) for value in (
            "official50.selinux.avc", "official50.selinux.setprocattr", "official50.selinux.fake_status",
            "official50.selinux.context_access", "official50.selinux.services_wrappers")))
        decisions = decide_patch51(source).decisions
        self.assertEqual([item.action for item in decisions].count(PolicyAction.REROUTE), 4)
        self.assertEqual([item.action for item in decisions].count(PolicyAction.REMOVE), 1)
        self.assertTrue(all(item.owner == OwnerKind.XXKSU_RUNTIME for item in decisions))

    def test_unrelated_changed_line_in_known_hunk_becomes_fatal_unknown(self):
        patch = parse_patch("""diff --git a/fs/exec.c b/fs/exec.c
--- a/fs/exec.c
+++ b/fs/exec.c
@@ -1 +1,3 @@
 ksu_handle_execveat();
+ksu_handle_execveat();
+totally_new_privilege_bypass();
""")
        source = inventory_patch(patch, source_identity="official-50-test", source_type="official_50",
                                 evidence_kind=EvidenceKind.SYNTHETIC, allow_synthetic=True)
        self.assertGreater(source.ledger.unknown_count, 0)
        with self.assertRaises(InventoryIncomplete):
            decide_patch51(source)

    def test_removed_and_added_diff_sides_never_form_a_false_split(self):
        patch = parse_patch("""diff --git a/fs/stat.c b/fs/stat.c
--- a/fs/stat.c
+++ b/fs/stat.c
@@ -1 +1,2 @@
-ksu_handle_stat();
+kstat();
+mnt_id();
""")
        source = inventory_patch(patch, source_identity="official-50-test", source_type="official_50",
                                 evidence_kind=EvidenceKind.SYNTHETIC, allow_synthetic=True)
        ledger = decide_patch51(source, require_complete=False)
        self.assertNotIn(PolicyAction.SPLIT, {item.action for item in ledger.mixed_blocks})
        self.assertEqual({item.container_id for item in ledger.mixed_blocks}, {"fs/stat.c:0:AddedLine"})

    def test_missing_replacement_relationship_is_unknown_and_fatal(self):
        source = inventory(official("transport.reboot.linux_call"), replacements=False)
        self.assertEqual(decide_patch51(source, require_complete=False).decisions[0].action, PolicyAction.UNKNOWN)
        with self.assertRaises(PolicyIncomplete):
            decide_patch51(source)

    def test_repeated_semantic_id_is_accounted_per_occurrence(self):
        source = inventory(official("transport.exec.linux_call", line=8, container="fs/exec.c:h1"),
                           official("transport.exec.linux_call", line=80, container="fs/exec.c:h2"))
        ledger = decide_patch51(source)
        self.assertEqual(len([item for item in ledger.decisions
                              if str(item.semantic_id) == "transport.exec.linux_call"]), 2)

    def test_fabricated_occurrence_cannot_satisfy_coverage(self):
        ledger = decide_patch51(inventory(official("susfs.uname.behavior")))
        actual = ledger.decisions[0].occurrence
        forged = PolicyOccurrence(actual.semantic_id, "sha256:" + "0" * 64, actual.container_id,
                                  actual.path, actual.start_line, actual.end_line)
        with self.assertRaises(PolicyIncomplete):
            ledger.validate_complete((forged,))

    def test_required_preserved_semantics_are_occurrence_local_in_mixed_block(self):
        text = "kstat();\nksu_handle_stat();"
        source = inventory(official("susfs.stat.kstat", line=1, container="stat:mixed", mixed=True,
                                    container_text=text),
                           official("transport.stat.linux_call", line=2, container="stat:mixed", mixed=True,
                                    container_text=text),
                           official("susfs.stat.mount_id", line=30, container="stat:other"))
        with self.assertRaises(PolicyIncomplete):
            decide_patch51(source)

    def test_one_preserved_pair_cannot_cover_two_transport_occurrences(self):
        text = "kstat();\nmnt_id();\nksu_handle_stat();\nksu_handle_stat();"
        source = inventory(official("susfs.stat.kstat", line=1, container="stat:mixed", mixed=True,
                                    container_text=text),
                           official("susfs.stat.mount_id", line=2, container="stat:mixed", mixed=True,
                                    container_text=text),
                           official("transport.stat.linux_call", line=3, container="stat:mixed", mixed=True,
                                    container_text=text),
                           official("transport.stat.linux_call", line=4, container="stat:mixed", mixed=True,
                                    container_text=text))
        with self.assertRaises(PolicyIncomplete):
            decide_patch51(source)

    def test_output_is_transport_neutral_deterministic_and_complete(self):
        observations = (official("susfs.uname.behavior"), official("transport.exec.linux_call", line=8))
        first = decide_patch51(inventory(*observations))
        second = decide_patch51(inventory(*reversed(observations)))
        self.assertEqual(first.canonical_json(), second.canonical_json())
        serialized = first.canonical_json().lower()
        self.assertNotIn("manual", serialized)
        self.assertNotIn("lsm_bl", serialized)
        self.assertNotIn("kernel_version", serialized)
        self.assertEqual(len([item for item in first.decisions
                              if item.occurrence.evidence_fingerprint]), 2)

    def test_production_requires_and_accepts_the_complete_official50_policy_baseline(self):
        with self.assertRaises(PolicyIncomplete):
            production_decide_patch51(inventory(official("susfs.uname.behavior")))
        with self.assertRaises(PolicyIncomplete):
            production_decide_patch51(inventory(*(official(value) for value in _OFFICIAL)))
        ledger = classify_patch51(inventory(*(official(value) for value in _OFFICIAL)))
        self.assertEqual({str(item.semantic_id) for item in ledger.decisions}, set(_OFFICIAL))

    def test_unverified_inventory_never_reaches_policy(self):
        candidate = official("susfs.uname.behavior")
        candidate = CandidateObservation(candidate.source_identity, candidate.source_type, candidate.path,
                                         candidate.text, source_kind=candidate.source_kind, symbols=candidate.symbols,
                                         start_line=1, evidence_kind=EvidenceKind.UNVERIFIED,
                                         container_text=candidate.text)
        with self.assertRaises(InventoryIncomplete):
            decide_patch51(SemanticInventory().detect_and_resolve((candidate,)))


if __name__ == "__main__":
    unittest.main()
