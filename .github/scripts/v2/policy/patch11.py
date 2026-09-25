"""Transport-neutral semantic policy for official 10 -> shared 11 intent."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable, Optional, Tuple

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
    "config.susfs.control": _Rule(
        SemanticKind.CONFIG_CONTROL, "config", PolicyAction.KEEP,
        OwnerKind.PATCH_51, "preserve SuSFS configuration control in Kconfig",
    ),
    "integration.susfs.initialization": _Rule(
        SemanticKind.SUSFS_BEHAVIOR, "integration", PolicyAction.KEEP,
        OwnerKind.PATCH_51, "preserve SuSFS core initialization hook in ksu.c",
    ),
    "susfs.supercall.cmd_dispatch": _Rule(
        SemanticKind.SUSFS_BEHAVIOR, "supercall", PolicyAction.KEEP,
        OwnerKind.PATCH_51, "preserve SuSFS supercall command dispatch and boot monitor",
    ),
    "susfs.setuid.zygote_handling": _Rule(
        SemanticKind.SUSFS_BEHAVIOR, "setuid", PolicyAction.KEEP,
        OwnerKind.PATCH_51, "preserve SuSFS zygote credentials and SID handling in setresuid",
    ),
    "susfs.umount.webview_zygote": _Rule(
        SemanticKind.SUSFS_BEHAVIOR, "umount", PolicyAction.REROUTE, OwnerKind.XXKSU_RUNTIME,
        "xxKSU native kernel_umount path replaces official webview zygote umount modifications",
        replacements=("transport.umount.definition",),
        relationship=RelationshipType.REPLACES_BEHAVIOR_OF,
    ),
    "susfs.selinux.sid_management": _Rule(
        SemanticKind.SUSFS_BEHAVIOR, "selinux", PolicyAction.KEEP,
        OwnerKind.PATCH_51, "preserve SuSFS SELinux SID management helpers and definitions",
    ),
    "official_only.exec.sucompat": _Rule(
        SemanticKind.HANDLER_DEFINITION, "exec", PolicyAction.REROUTE, OwnerKind.XXKSU_RUNTIME,
        "xxKSU single ksu_handle_execveat path replaces official sucompat dispatch",
        replacements=("transport.exec.definition",),
        relationship=RelationshipType.REPLACES_BEHAVIOR_OF,
    ),
    "official_only.fstat.definition": _Rule(
        SemanticKind.HANDLER_DEFINITION, "fstat-return", PolicyAction.REROUTE, OwnerKind.XXKSU_RUNTIME,
        "xxKSU return handlers replace official vfs_fstat definition",
        replacements=("transport.fstat_return.definition",),
        relationship=RelationshipType.REPLACES_BEHAVIOR_OF,
    ),
    "official_only.read.definition": _Rule(
        SemanticKind.HANDLER_DEFINITION, "read", PolicyAction.REROUTE, OwnerKind.XXKSU_RUNTIME,
        "xxKSU internal read fallback replaces official sys_read definition",
        replacements=("transport.read.internal_fallback",),
        relationship=RelationshipType.REPLACES_BEHAVIOR_OF,
    ),
    "official_only.input.definition": _Rule(
        SemanticKind.HANDLER_DEFINITION, "input", PolicyAction.REROUTE, OwnerKind.XXKSU_RUNTIME,
        "xxKSU volume detector registration replaces official input hook",
        replacements=("transport.input.registration",),
        relationship=RelationshipType.REPLACES_BEHAVIOR_OF,
    ),
}

_EXPECTED_PATHS = {
    "config.susfs.control": ("kernel/Kconfig",),
    "integration.susfs.initialization": ("kernel/ksu.c",),
    "susfs.supercall.cmd_dispatch": ("kernel/supercall/dispatch.c", "kernel/supercall/supercall.c"),
    "susfs.setuid.zygote_handling": ("kernel/hook/setuid_hook.c",),
    "susfs.umount.webview_zygote": ("kernel/feature/kernel_umount.c", "kernel/downstream/ksu_hostsredirect.h"),
    "susfs.selinux.sid_management": ("kernel/selinux/rules.c", "kernel/selinux/selinux.c", "kernel/selinux/selinux.h"),
    "official_only.exec.sucompat": ("kernel/feature/sucompat.c",),
    "official_only.fstat.definition": ("kernel/runtime/ksud.c",),
    "official_only.read.definition": ("kernel/runtime/ksud.c",),
    "official_only.input.definition": ("kernel/runtime/ksud.c",),
}

_EXPECTED_SYMBOLS = {
    "config.susfs.control": ("CONFIG_KSU_SUSFS",),
    "integration.susfs.initialization": ("susfs_init",),
    "susfs.supercall.cmd_dispatch": ("susfs_cmd_dispatch", "susfs_auto_reboot", "susfs_start_sdcard_monitor_fn"),
    "susfs.setuid.zygote_handling": ("handle_zygote_setresuid", "susfs_zygote_sid"),
    "susfs.umount.webview_zygote": ("ksu_is_webview_zygote_umount_enabled", "susfs_is_current_webview_zygote"),
    "susfs.selinux.sid_management": ("susfs_set_sid", "susfs_get_sid", "susfs_set_priv_app_sid"),
    "official_only.exec.sucompat": ("ksu_handle_execveat_sucompat",),
    "official_only.fstat.definition": ("ksu_handle_vfs_fstat",),
    "official_only.read.definition": ("ksu_handle_sys_read",),
    "official_only.input.definition": ("ksu_handle_input_handle_event",),
}

_REQUIRED_BASELINE = frozenset(_RULES)


def _reviewed_statement(key: str, evidence) -> bool:
    expected = set(_EXPECTED_SYMBOLS.get(key, ()))
    if not expected:
        return False
    # For official-10 observations, statement may be a definition or call
    statements = tuple(item.strip() for item in evidence.fingerprint.normalized_statements if item.strip())
    if not statements:
        # Check called or required symbols in fingerprint
        all_symbols = set(evidence.fingerprint.called_symbols) | set(evidence.fingerprint.required_symbols)
        return bool(all_symbols.intersection(expected))
    line = statements[0]
    calls = re.findall(r"\b([A-Za-z_]\w*)\b", line)
    return any(sym in calls for sym in expected)


def _source_shape(source_id: str, source: SemanticUnit, evidence) -> bool:
    expected_paths = {
        "transport.exec.definition": ("kernel/feature/sucompat.c",),
        "transport.fstat_return.definition": ("kernel/runtime/ksud.c",),
        "transport.read.internal_fallback": ("kernel/hook/syscall_table_hook_arm64.c",),
        "transport.input.registration": ("kernel/runtime/ksud.c", "kernel/feature/vol_detector.c"),
        "transport.umount.definition": ("kernel/feature/kernel_umount.c",),
    }
    expected_symbols = {
        "transport.exec.definition": ("ksu_handle_execveat",),
        "transport.fstat_return.definition": ("ksu_handle_newfstat_ret", "ksu_handle_fstat64_ret"),
        "transport.read.internal_fallback": ("ksu_handle_sys_read_fd",),
        "transport.input.registration": ("input_register_handler", "vol_detector_event"),
        "transport.umount.definition": ("ksu_handle_umount",),
    }
    allowed_kinds = {
        SemanticKind.HANDLER_DEFINITION,
        SemanticKind.RUNTIME_REGISTRATION,
        SemanticKind.SYSCALL_TABLE_HOOK,
    }
    return (
        source.kind in allowed_kinds and
        source.location.path in expected_paths.get(source_id, ()) and
        evidence.fingerprint.source_kind == "xxksu" and
        evidence.attributes.get("abi", {}).get("validated") is True and
        any(symbol in evidence.fingerprint.called_symbols for symbol in expected_symbols.get(source_id, ()))
    )


def _replacement_sources(
    inventory: SemanticInventory, unit: SemanticUnit, rule: _Rule,
) -> tuple[tuple[SemanticId, ...], tuple[str, ...]]:
    if not rule.replacements:
        return (), ()
    found: list[SemanticId] = []
    evidence_fingerprints: list[str] = []
    for source in inventory.units:
        source_id = str(source.semantic_id)
        if source_id not in rule.replacements:
            continue
        if not any(
            _source_shape(source_id, source, evidence)
            for evidence in source.evidence
            if inventory.is_resolved_evidence(source, evidence)
        ):
            continue
        for relationship in source.relationships:
            if relationship.target != unit.semantic_id or relationship.relation != rule.relationship:
                continue
            if relationship.evidence and all(
                inventory.is_resolved_evidence(source, item) and _source_shape(source_id, source, item)
                for item in relationship.evidence
            ):
                found.append(source.semantic_id)
                evidence_fingerprints.extend(str(item.fingerprint.digest) for item in relationship.evidence)
                break
    return tuple(sorted(set(found), key=str)), tuple(sorted(set(evidence_fingerprints)))


def _occurrence(unit: SemanticUnit, evidence) -> PolicyOccurrence:
    raw_container = evidence.attributes.get("container_id")
    if not raw_container:
        raw_container = (
            f"{evidence.location.path}:{evidence.location.start_line or 'unbounded'}:"
            f"{unit.semantic_id}"
        )
    start = evidence.location.start_line
    end = evidence.location.end_line + 1 if evidence.location.end_line is not None else None
    return PolicyOccurrence(
        unit.semantic_id, str(evidence.fingerprint.digest), str(raw_container),
        evidence.location.path, start, end,
    )


def _decision(
    inventory: SemanticInventory,
    unit: SemanticUnit,
    evidence,
    occurrence: PolicyOccurrence,
    local_occurrences: tuple[PolicyOccurrence, ...],
) -> PolicyDecision:
    key = str(unit.semantic_id)
    rule = _RULES.get(key)
    rank = {Confidence.UNKNOWN: 0, Confidence.LOW: 1, Confidence.MEDIUM: 2, Confidence.HIGH: 3}
    minimum = Confidence.HIGH

    replacements, replacement_evidence = (
        _replacement_sources(inventory, unit, rule) if rule is not None else ((), ())
    )
    required_preserves = set(rule.preserves if rule else ())
    local_ids = {str(item.semantic_id) for item in local_occurrences}
    preserved = tuple(item for item in local_occurrences if str(item.semantic_id) in required_preserves)

    supported = (
        rule is not None and
        unit.kind == rule.kind and
        unit.domain == rule.domain and
        unit.location.path in _EXPECTED_PATHS.get(key, ()) and
        occurrence.path in _EXPECTED_PATHS.get(key, ()) and
        occurrence.start_line is not None and
        inventory.is_resolved_evidence(unit, evidence) and
        _reviewed_statement(key, evidence) and
        (rule.action == PolicyAction.KEEP or evidence.attributes.get("abi", {}).get("validated") is True) and
        rank[unit.confidence] >= rank[minimum] and
        rank[evidence.confidence] >= rank[minimum] and
        (not rule.replacements or replacements)
    )

    if not supported:
        return PolicyDecision(
            occurrence,
            PolicyAction.UNKNOWN,
            OwnerKind.UNRESOLVED,
            "no reviewed official-10 semantic policy matches this occurrence",
        )

    return PolicyDecision(
        occurrence,
        rule.action,
        rule.owner,
        rule.rationale,
        preserved,
        replacements,
        replacement_evidence,
        rule.relationship.value if replacements and rule.relationship else None,
    )


def _build_policy(
    inventory: SemanticInventory, required_ids: Optional[Iterable[str]] = None,
) -> tuple[PolicyCoverageLedger, tuple[PolicyOccurrence, ...]]:
    relevant = tuple(
        (unit, evidence)
        for unit in inventory.units
        for evidence in unit.evidence
        if evidence.fingerprint.source_kind == "official_10"
    )
    present = {str(unit.semantic_id) for unit, _ in relevant}
    expected_ids = frozenset(required_ids) if required_ids is not None else _REQUIRED_BASELINE
    missing = sorted(expected_ids - present)
    extra = sorted(present - expected_ids)
    if missing or extra:
        raise PolicyIncomplete(
            f"official-10 policy baseline is incomplete: missing={missing}, extra={extra}"
        )

    occurrences = [_occurrence(unit, evidence) for unit, evidence in relevant]
    by_container: dict[str, list[PolicyOccurrence]] = {}
    for occurrence in occurrences:
        by_container.setdefault(occurrence.container_id, []).append(occurrence)

    ledger = PolicyCoverageLedger(str(inventory.identity))
    for (unit, evidence), occurrence in zip(relevant, occurrences):
        local = tuple(by_container[occurrence.container_id])
        decision = _decision(inventory, unit, evidence, occurrence, local)
        ledger.add(decision)

    return ledger, tuple(occurrences)


def classify_patch11(
    inventory: SemanticInventory,
    *,
    validate: bool = True,
    require_baseline: bool = False,
) -> PolicyCoverageLedger:
    """Return official 10 -> shared 11 policy decisions."""
    inventory.validate_complete()
    if require_baseline or inventory.required_semantic_ids:
        required_ids = inventory.required_semantic_ids or _REQUIRED_BASELINE
    else:
        required_ids = tuple(
            str(unit.semantic_id)
            for unit in inventory.units
            if any(item.fingerprint.source_kind == "official_10" for item in unit.evidence)
        )
    ledger, occurrences = _build_policy(inventory, required_ids)
    if validate:
        ledger.validate_complete(occurrences, ())
    return ledger


def decide_patch11(inventory: SemanticInventory) -> PolicyCoverageLedger:
    """Build production policy intent from an authoritative official-10 inventory."""
    inventory.validate_complete()
    evidence = tuple(item for unit in inventory.units for item in unit.evidence)
    if inventory.ledger.allow_synthetic or any(item.evidence_kind != EvidenceKind.VERIFIED for item in evidence):
        raise PolicyIncomplete("production policy requires VERIFIED semantic evidence")
    if not inventory.required_semantic_ids:
        raise PolicyIncomplete("production policy requires an explicit official-10 semantic scope")
    ledger, occurrences = _build_policy(inventory, inventory.required_semantic_ids)
    ledger.validate_complete(occurrences, ())
    return ledger
