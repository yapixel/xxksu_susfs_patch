"""Transport-neutral semantic policy for official 50 -> 51 intent."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Optional, Tuple

from ..semantic import (
    Confidence, CoverageState, EvidenceKind, RelationshipType, SemanticId,
    SemanticInventory, SemanticKind, SemanticUnit,
)
from .model import (
    MixedBlockDecision, MixedMember, OwnerKind, PolicyAction, PolicyCoverageLedger,
    PolicyDecision, PolicyIncomplete, PolicyOccurrence,
)


@dataclass(frozen=True)
class _Rule:
    kind: SemanticKind
    domain: str
    action: PolicyAction
    owner: OwnerKind
    rationale: str
    preserves: Tuple[str, ...] = ()
    replacements: Tuple[str, ...] = ()
    relationship: Optional[RelationshipType] = None


_RULES = {
    "susfs.uname.behavior": _Rule(SemanticKind.SUSFS_BEHAVIOR, "uname", PolicyAction.KEEP,
                                  OwnerKind.PATCH_51, "preserve independent SuSFS uname behavior"),
    "susfs.stat.kstat": _Rule(SemanticKind.SUSFS_BEHAVIOR, "stat", PolicyAction.KEEP,
                              OwnerKind.PATCH_51, "preserve independent SuSFS kstat behavior"),
    "susfs.stat.mount_id": _Rule(SemanticKind.SUSFS_BEHAVIOR, "stat", PolicyAction.KEEP,
                                 OwnerKind.PATCH_51, "preserve independent SuSFS mount identity behavior"),
    "transport.exec.linux_call": _Rule(
        SemanticKind.LINUX_CALL_SITE, "exec", PolicyAction.REROUTE, OwnerKind.PROFILE_MANIFEST,
        "official handler topology is incompatible with xxKSU",
        replacements=("transport.exec.definition",), relationship=RelationshipType.PROVIDES_TRANSPORT_FOR),
    "transport.access.linux_call": _Rule(
        SemanticKind.LINUX_CALL_SITE, "access", PolicyAction.REROUTE, OwnerKind.PROFILE_MANIFEST,
        "official access ABI is incompatible with xxKSU",
        replacements=("transport.access.definition",), relationship=RelationshipType.PROVIDES_TRANSPORT_FOR),
    "transport.stat.linux_call": _Rule(
        SemanticKind.LINUX_CALL_SITE, "stat", PolicyAction.REROUTE, OwnerKind.PROFILE_MANIFEST,
        "profile composition owns compatible stat transport",
        ("susfs.stat.kstat", "susfs.stat.mount_id"), ("transport.stat.definition",),
        RelationshipType.PROVIDES_TRANSPORT_FOR),
    "transport.fstat_return.linux_call": _Rule(
        SemanticKind.LINUX_CALL_SITE, "fstat-return", PolicyAction.REROUTE, OwnerKind.PROFILE_MANIFEST,
        "official fstat handler is absent from xxKSU",
        replacements=("transport.fstat_return.definition",),
        relationship=RelationshipType.PROVIDES_TRANSPORT_FOR),
    "transport.read.linux_call": _Rule(
        SemanticKind.LINUX_CALL_SITE, "read", PolicyAction.REROUTE, OwnerKind.PROFILE_MANIFEST,
        "xxKSU uses compatible read transport rather than the official handler",
        replacements=("transport.read.internal_fallback", "transport.read.manual_fixture"),
        relationship=RelationshipType.PROVIDES_TRANSPORT_FOR),
    "transport.reboot.linux_call": _Rule(
        SemanticKind.LINUX_CALL_SITE, "reboot", PolicyAction.REROUTE, OwnerKind.PROFILE_MANIFEST,
        "official reboot return contract is incompatible with xxKSU",
        replacements=("transport.reboot.definition",), relationship=RelationshipType.PROVIDES_TRANSPORT_FOR),
    "transport.setuid.linux_call": _Rule(
        SemanticKind.LINUX_CALL_SITE, "setuid", PolicyAction.REROUTE, OwnerKind.PROFILE_MANIFEST,
        "profile security transport owns setuid delivery",
        preserves=("susfs.uname.behavior",), replacements=("transport.setuid.definition",),
        relationship=RelationshipType.PROVIDES_TRANSPORT_FOR),
    "transport.input.official_assumption": _Rule(
        SemanticKind.LINUX_CALL_SITE, "input", PolicyAction.REROUTE, OwnerKind.XXKSU_RUNTIME,
        "xxKSU owns safe mode through input registration",
        replacements=("transport.input.registration",), relationship=RelationshipType.REPLACES_BEHAVIOR_OF),
    "official50.selinux.avc": _Rule(
        SemanticKind.SELINUX_BEHAVIOR, "selinux", PolicyAction.REROUTE, OwnerKind.XXKSU_RUNTIME,
        "xxKSU slow-AVC replacement owns this behavior",
        replacements=("selinux.avc.replace",), relationship=RelationshipType.REPLACES_BEHAVIOR_OF),
    "official50.selinux.setprocattr": _Rule(
        SemanticKind.SELINUX_BEHAVIOR, "selinux", PolicyAction.REROUTE, OwnerKind.XXKSU_RUNTIME,
        "xxKSU SELinux hide owns setprocattr behavior",
        replacements=("selinux.setprocattr",), relationship=RelationshipType.REPLACES_BEHAVIOR_OF),
    "official50.selinux.fake_status": _Rule(
        SemanticKind.SELINUX_BEHAVIOR, "selinux", PolicyAction.REROUTE, OwnerKind.XXKSU_RUNTIME,
        "xxKSU fake status replacement owns this behavior",
        replacements=("selinux.fake_status",), relationship=RelationshipType.REPLACES_BEHAVIOR_OF),
    "official50.selinux.context_access": _Rule(
        SemanticKind.SELINUX_BEHAVIOR, "selinux", PolicyAction.REROUTE, OwnerKind.XXKSU_RUNTIME,
        "xxKSU transaction replacement owns context/access behavior",
        replacements=("selinux.context_access",), relationship=RelationshipType.REPLACES_BEHAVIOR_OF),
    "official50.selinux.services_wrappers": _Rule(
        SemanticKind.SELINUX_BEHAVIOR, "selinux", PolicyAction.REMOVE, OwnerKind.XXKSU_RUNTIME,
        "official backup-policy wrappers are unused by xxKSU replacement",
        replacements=("selinux.context_access",), relationship=RelationshipType.REPLACES_BEHAVIOR_OF),
}

_EXPECTED_PATHS = {
    "susfs.uname.behavior": ("kernel/sys.c",),
    "susfs.stat.kstat": ("fs/stat.c",),
    "susfs.stat.mount_id": ("fs/stat.c",),
    "transport.exec.linux_call": ("fs/exec.c",),
    "transport.access.linux_call": ("fs/open.c",),
    "transport.stat.linux_call": ("fs/stat.c",),
    "transport.fstat_return.linux_call": ("fs/stat.c",),
    "transport.read.linux_call": ("fs/read_write.c",),
    "transport.reboot.linux_call": ("kernel/reboot.c",),
    "transport.setuid.linux_call": ("kernel/sys.c",),
    "transport.input.official_assumption": ("drivers/input/input.c",),
    "official50.selinux.avc": ("security/selinux/avc.c",),
    "official50.selinux.setprocattr": ("security/selinux/hooks.c",),
    "official50.selinux.fake_status": ("security/selinux/selinuxfs.c",),
    "official50.selinux.context_access": ("security/selinux/selinuxfs.c",),
    "official50.selinux.services_wrappers": ("security/selinux/ss/services.c",),
}

_EXPECTED_SYMBOLS = {
    "susfs.uname.behavior": ("susfs_spoof_uname",),
    "susfs.stat.kstat": ("kstat",),
    "susfs.stat.mount_id": ("mnt_id", "mnt_id_unique"),
    "transport.exec.linux_call": ("ksu_handle_execveat",),
    "transport.access.linux_call": ("ksu_handle_faccessat",),
    "transport.stat.linux_call": ("ksu_handle_stat",),
    "transport.fstat_return.linux_call": ("ksu_handle_vfs_fstat",),
    "transport.read.linux_call": ("ksu_handle_sys_read",),
    "transport.reboot.linux_call": ("ksu_handle_sys_reboot",),
    "transport.setuid.linux_call": ("ksu_handle_setresuid",),
    "transport.input.official_assumption": ("ksu_handle_input_handle_event",),
    "official50.selinux.avc": ("slow_avc_audit",),
    "official50.selinux.setprocattr": ("my_setprocattr",),
    "official50.selinux.fake_status": ("ksu_fake_status",),
    "official50.selinux.context_access": ("my_write_context", "my_write_access"),
    "official50.selinux.services_wrappers": ("backup_sepolicy",),
}

_MEDIUM_CONFIDENCE = {"official50.selinux.setprocattr", "official50.selinux.context_access"}
_REQUIRED_BASELINE = frozenset(_RULES)

# A policy source can contain arguments, but a nested call or a second call is
# not a bounded call-site observation. Such content must be reclassified.
_CONTROL_CALLS = {"if", "for", "while", "switch", "sizeof", "typeof"}


def _reviewed_statement(key: str, evidence) -> bool:
    lines = tuple(item.strip() for item in evidence.fingerprint.normalized_statements if item.strip())
    expected = set(_EXPECTED_SYMBOLS.get(key, ()))
    if len(lines) != 1 or not expected:
        return False
    line = lines[0]
    if any(char in line for char in "{}"):
        return False
    calls = re.findall(r"\b([A-Za-z_]\w*)\s*\(", line)
    calls = [item for item in calls if item not in _CONTROL_CALLS]
    return len(calls) == 1 and calls[0] in expected and line.rstrip().endswith(";")


def _source_shape(source_id: str, source: SemanticUnit, evidence) -> bool:
    expected_paths = {
        "transport.exec.definition": ("kernel/feature/sucompat.c",),
        "transport.access.definition": ("kernel/feature/sucompat.c",),
        "transport.stat.definition": ("kernel/feature/sucompat.c",),
        "transport.fstat_return.definition": ("kernel/runtime/ksud.c",),
        "transport.read.internal_fallback": ("kernel/hook/syscall_table_hook_arm64.c",),
        "transport.read.manual_fixture": ("security/security.c",),
        "transport.reboot.definition": ("kernel/supercall/supercall.c",),
        "transport.setuid.definition": ("kernel/hook/setuid_hook.c",),
        "transport.input.registration": ("kernel/feature/vol_detector.c",),
        "selinux.avc.replace": ("kernel/feature/selinux_hide.c", "kernel/downstream/slow_avc_audit_defs.h"),
        "selinux.setprocattr": ("kernel/feature/selinux_hide.c",),
        "selinux.fake_status": ("kernel/feature/selinux_hide.c",),
        "selinux.context_access": ("kernel/feature/selinux_hide.c",),
    }
    expected_symbols = {
        "transport.exec.definition": ("ksu_handle_execveat",),
        "transport.access.definition": ("ksu_handle_faccessat",),
        "transport.stat.definition": ("ksu_handle_stat",),
        "transport.fstat_return.definition": ("ksu_handle_newfstat_ret", "ksu_handle_fstat64_ret"),
        "transport.read.internal_fallback": ("ksu_handle_sys_read_fd",),
        "transport.read.manual_fixture": ("ksu_file_permission",),
        "transport.reboot.definition": ("ksu_handle_sys_reboot",),
        "transport.setuid.definition": ("ksu_handle_setresuid",),
        "transport.input.registration": ("input_register_handler", "vol_detector_event"),
        "selinux.avc.replace": ("slow_avc_audit",),
        "selinux.setprocattr": ("ksu_hide_setprocattr",),
        "selinux.fake_status": ("ksu_fake_status_page",),
        "selinux.context_access": ("write_context", "write_access"),
    }
    return (source.kind in {SemanticKind.HANDLER_DEFINITION, SemanticKind.RUNTIME_REGISTRATION,
                            SemanticKind.SYSCALL_TABLE_HOOK, SemanticKind.SELINUX_BEHAVIOR} and
            source.location.path in expected_paths.get(source_id, ()) and
            evidence.fingerprint.source_kind in {"xxksu", "fixture_manual_security", "fixture_scope_min"} and
            evidence.attributes.get("abi", {}).get("validated") is True and
            any(symbol in evidence.fingerprint.called_symbols for symbol in expected_symbols.get(source_id, ())))


def _replacement_sources(inventory: SemanticInventory, unit: SemanticUnit,
                         rule: _Rule) -> tuple[tuple[SemanticId, ...], tuple[str, ...]]:
    if not rule.replacements:
        return (), ()
    found: list[SemanticId] = []
    evidence_fingerprints: list[str] = []
    for source in inventory.units:
        source_id = str(source.semantic_id)
        if source_id not in rule.replacements:
            continue
        if not any(_source_shape(source_id, source, evidence)
                   for evidence in source.evidence
                   if inventory.is_resolved_evidence(source, evidence)):
            continue
        for relationship in source.relationships:
            if relationship.target != unit.semantic_id or relationship.relation != rule.relationship:
                continue
            if relationship.evidence and all(
                    inventory.is_resolved_evidence(source, item) and _source_shape(source_id, source, item)
                    for item in relationship.evidence):
                found.append(source.semantic_id)
                evidence_fingerprints.extend(str(item.fingerprint.digest) for item in relationship.evidence)
                break
    return tuple(sorted(set(found), key=str)), tuple(sorted(set(evidence_fingerprints)))


def _occurrence(unit: SemanticUnit, evidence) -> PolicyOccurrence:
    raw_container = evidence.attributes.get("container_id")
    if not raw_container:
        raw_container = (f"{evidence.location.path}:{evidence.location.start_line or 'unbounded'}:"
                         f"{unit.semantic_id}")
    start = evidence.location.start_line
    end = evidence.location.end_line + 1 if evidence.location.end_line is not None else None
    return PolicyOccurrence(unit.semantic_id, str(evidence.fingerprint.digest), str(raw_container),
                            evidence.location.path, start, end)


def _decision(inventory: SemanticInventory, unit: SemanticUnit, evidence,
              occurrence: PolicyOccurrence, local_occurrences: tuple[PolicyOccurrence, ...]) -> PolicyDecision:
    key = str(unit.semantic_id)
    rule = _RULES.get(key)
    rank = {Confidence.UNKNOWN: 0, Confidence.LOW: 1, Confidence.MEDIUM: 2, Confidence.HIGH: 3}
    minimum = Confidence.MEDIUM if key in _MEDIUM_CONFIDENCE else Confidence.HIGH
    replacements, replacement_evidence = (_replacement_sources(inventory, unit, rule)
                                           if rule is not None else ((), ()))
    required_preserves = set(rule.preserves if rule else ())
    local_ids = {str(item.semantic_id) for item in local_occurrences}
    preserved = tuple(item for item in local_occurrences if str(item.semantic_id) in required_preserves)
    supported = (rule is not None and unit.kind == rule.kind and unit.domain == rule.domain and
                 (unit.state != CoverageState.MIXED or required_preserves.issubset(local_ids)) and
                 unit.location.path in _EXPECTED_PATHS.get(key, ()) and occurrence.path in _EXPECTED_PATHS.get(key, ()) and
                 occurrence.start_line is not None and inventory.is_resolved_evidence(unit, evidence) and
                 _reviewed_statement(key, evidence) and
                 (rule.action == PolicyAction.KEEP or evidence.attributes.get("abi", {}).get("validated") is True) and
                 rank[unit.confidence] >= rank[minimum] and
                 rank[evidence.confidence] >= rank[minimum] and
                 (not rule.replacements or replacements))
    if not supported:
        return PolicyDecision(occurrence, PolicyAction.UNKNOWN, OwnerKind.UNRESOLVED,
                              "no reviewed official-50 semantic policy matches this occurrence")
    return PolicyDecision(occurrence, rule.action, rule.owner, rule.rationale, preserved, replacements,
                          replacement_evidence,
                          rule.relationship.value if replacements and rule.relationship else None)


def _mixed_decisions(inventory: SemanticInventory, decisions: tuple[PolicyDecision, ...],
                     evidence_by_occurrence: dict[str, object], required_mixed_ids: set[str]):
    containers: dict[str, list[PolicyDecision]] = {}
    for decision in decisions:
        if decision.occurrence.identity in required_mixed_ids:
            containers.setdefault(decision.occurrence.container_id, []).append(decision)
    result = []
    for container, members in containers.items():
        mixed_members = tuple(MixedMember(item.occurrence, item.action) for item in members)
        semantic_ids = {str(item.semantic_id) for item in members}
        actions = {item.action for item in members}
        paths = {item.occurrence.path for item in members}
        if len(semantic_ids) < 2 or len(paths) != 1:
            result.append(MixedBlockDecision(container, PolicyAction.UNKNOWN, mixed_members,
                                             "mixed evidence does not identify independent same-file units"))
            continue
        if PolicyAction.UNKNOWN in actions:
            result.append(MixedBlockDecision(container, PolicyAction.UNKNOWN, mixed_members,
                                             "mixed block contains unsupported semantic evidence"))
            continue
        if len(actions) == 1:
            result.append(MixedBlockDecision(container, next(iter(actions)), mixed_members,
                                             "all independently accounted occurrences have the same semantic intent"))
            continue
        ordered = sorted(((item.occurrence.start_line, item.occurrence.end_line, item.occurrence.identity)
                          for item in members), key=lambda item: (item[0] is None, item[0] or 0, item[2]))
        bounded = all(start is not None and end is not None for start, end, _ in ordered)
        non_overlapping = bounded and all(left[1] <= right[0] for left, right in zip(ordered, ordered[1:]))
        evidence = [evidence_by_occurrence[item.occurrence.identity] for item in members]
        container_text = inventory.container_text_for(container, next(iter(paths)), "official_50")
        statements = [tuple(text.strip() for text in item.fingerprint.normalized_statements if text.strip())
                      for item in evidence]
        simple_calls = all(len(lines) == 1 and re.fullmatch(r"[A-Za-z_]\w*\s*\([^;{}]*\)\s*;",
                                                           lines[0]) for lines in statements)
        container_lines = tuple(line.strip() for line in (container_text or "").splitlines() if line.strip())
        member_lines = tuple(lines[0] for lines in statements if len(lines) == 1)
        exact_container = bool(container_text) and sorted(container_lines) == sorted(member_lines)
        safely_bounded = bounded and non_overlapping and simple_calls and exact_container
        action = PolicyAction.SPLIT if safely_bounded else PolicyAction.UNKNOWN
        rationale = ("member dispositions and non-overlapping standalone statements prove a safe semantic split"
                     if safely_bounded else "mixed actions overlap or lack an exact standalone-statement container")
        result.append(MixedBlockDecision(container, action, mixed_members, rationale))
    return tuple(result)


def _build_policy(inventory: SemanticInventory, required_ids: Optional[Iterable[str]] = None
                  ) -> tuple[PolicyCoverageLedger, tuple[PolicyOccurrence, ...]]:
    relevant = tuple((unit, evidence) for unit in inventory.units for evidence in unit.evidence
                     if evidence.fingerprint.source_kind == "official_50")
    present = {str(unit.semantic_id) for unit, _ in relevant}
    expected_ids = frozenset(required_ids) if required_ids is not None else _REQUIRED_BASELINE
    missing = sorted(expected_ids - present)
    extra = sorted(present - expected_ids)
    if missing or extra:
        raise PolicyIncomplete(f"official-50 policy baseline is incomplete: missing={missing}, extra={extra}")
    occurrences = [_occurrence(unit, evidence) for unit, evidence in relevant]
    by_container: dict[str, list[PolicyOccurrence]] = {}
    for occurrence in occurrences:
        by_container.setdefault(occurrence.container_id, []).append(occurrence)
    ledger = PolicyCoverageLedger(str(inventory.identity))
    decisions = []
    evidence_by_occurrence = {}
    for (unit, evidence), occurrence in zip(relevant, occurrences):
        local = tuple(by_container[occurrence.container_id])
        decision = _decision(inventory, unit, evidence, occurrence, local)
        decisions.append(decision)
        evidence_by_occurrence[occurrence.identity] = evidence
        ledger.add(decision)
    mixed_occurrences = tuple(item for items in by_container.values()
                              if len({str(item.semantic_id) for item in items}) > 1 or
                              any(unit.state == CoverageState.MIXED
                                  for unit, evidence in relevant if _occurrence(unit, evidence).identity in
                                  {member.identity for member in items})
                              for item in items)
    mixed_ids = {item.identity for item in mixed_occurrences}
    for mixed in _mixed_decisions(inventory, tuple(decisions), evidence_by_occurrence, mixed_ids):
        ledger.add_mixed(mixed)
    return ledger, tuple(occurrences)


def classify_patch51(inventory: SemanticInventory, *, validate: bool = True) -> PolicyCoverageLedger:
    """Return diagnostic fixture decisions; this never authorizes source transformation."""
    inventory.validate_complete()
    required_ids = tuple(str(unit.semantic_id) for unit in inventory.units
                         if any(item.fingerprint.source_kind == "official_50" for item in unit.evidence))
    ledger, occurrences = _build_policy(inventory, required_ids)
    if validate:
        mixed_ids = {block.container_id for block in ledger.mixed_blocks}
        ledger.validate_complete(occurrences, tuple(item for item in occurrences if item.container_id in mixed_ids))
    return ledger


def decide_patch51(inventory: SemanticInventory) -> PolicyCoverageLedger:
    """Build production policy intent from a complete authoritative inventory."""
    inventory.validate_complete()
    evidence = tuple(item for unit in inventory.units for item in unit.evidence)
    if inventory.ledger.allow_synthetic or any(item.evidence_kind != EvidenceKind.VERIFIED for item in evidence):
        raise PolicyIncomplete("production policy requires VERIFIED semantic evidence")
    if not inventory.required_semantic_ids:
        raise PolicyIncomplete("production policy requires an explicit official-50 semantic scope")
    ledger, occurrences = _build_policy(inventory, inventory.required_semantic_ids)
    mixed_ids = {block.container_id for block in ledger.mixed_blocks}
    ledger.validate_complete(occurrences, tuple(item for item in occurrences if item.container_id in mixed_ids))
    return ledger
