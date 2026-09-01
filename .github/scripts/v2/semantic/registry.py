"""Reviewable semantic specification registry; factual only."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional, Tuple

from .model import (
    Confidence, SemanticId, SemanticKind, SemanticLocation, SemanticSpecificationError,
)


ROLE_SENSITIVE_KINDS = {
    SemanticKind.HANDLER_DEFINITION,
    SemanticKind.HANDLER_DECLARATION,
    SemanticKind.LINUX_CALL_SITE,
    SemanticKind.RUNTIME_REGISTRATION,
    SemanticKind.STATIC_KEY_GATE,
    SemanticKind.LSM_SECURITY_HOOK,
    SemanticKind.KPROBE,
    SemanticKind.SYSCALL_TABLE_HOOK,
    SemanticKind.ARM64_BRANCH_LINK,
    SemanticKind.MANUAL_SOURCE_HOOK,
    SemanticKind.FIXTURE_HOOK,
    SemanticKind.TRANSPORT_WRAPPER,
}


@dataclass(frozen=True)
class SemanticSpecification:
    semantic_id: SemanticId
    kind: SemanticKind
    domain: str
    paths: Tuple[str, ...]
    symbols: Tuple[str, ...] = field(default_factory=tuple)
    source_kinds: Tuple[str, ...] = field(default_factory=tuple)
    expected_functions: Tuple[str, ...] = field(default_factory=tuple)
    source_roles: Tuple[str, ...] = field(default_factory=tuple)
    confidence: Confidence = Confidence.UNKNOWN
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.paths or not self.domain or not isinstance(self.kind, SemanticKind) or self.kind == SemanticKind.UNKNOWN:
            raise SemanticSpecificationError("specification requires domain, kind, and paths")
        if self.kind in ROLE_SENSITIVE_KINDS and not self.source_roles:
            raise SemanticSpecificationError("role-sensitive specification requires source roles")
        if not isinstance(self.confidence, Confidence):
            try:
                object.__setattr__(self, "confidence", Confidence(self.confidence))
            except ValueError as exc:
                raise SemanticSpecificationError("invalid specification confidence") from exc

    def to_dict(self) -> dict:
        return {"semantic_id": str(self.semantic_id), "kind": self.kind.value, "domain": self.domain,
                "paths": list(self.paths), "symbols": list(self.symbols), "source_kinds": list(self.source_kinds),
                "expected_functions": list(self.expected_functions), "source_roles": list(self.source_roles),
                "confidence": self.confidence.value,
                "notes": self.notes}


class SemanticRegistry:
    def __init__(self, specifications: Iterable[SemanticSpecification] = ()):
        self._specs: dict[str, SemanticSpecification] = {}
        for spec in specifications:
            self.add(spec)

    def add(self, spec: SemanticSpecification) -> None:
        key = str(spec.semantic_id)
        previous = self._specs.get(key)
        if previous is not None and (previous.kind != spec.kind or previous.domain != spec.domain or previous.symbols != spec.symbols):
            raise SemanticSpecificationError(f"incompatible specification collision: {key}")
        self._specs[key] = spec

    def get(self, semantic_id: SemanticId | str) -> Optional[SemanticSpecification]:
        return self._specs.get(str(semantic_id))

    def __iter__(self):
        return iter(tuple(self._specs[key] for key in sorted(self._specs)))

    def to_dict(self) -> list[dict]:
        return [spec.to_dict() for spec in self]

    def match(self, candidate: "CandidateLike") -> tuple[SemanticSpecification, ...]:
        matches = []
        for spec in self:
            if candidate.path not in spec.paths:
                continue
            if spec.source_kinds and candidate.source_kind not in spec.source_kinds:
                continue
            if spec.expected_functions and candidate.function not in spec.expected_functions:
                continue
            if spec.source_roles and candidate.role not in spec.source_roles:
                continue
            if spec.symbols and not set(spec.symbols).intersection(candidate.symbols):
                continue
            matches.append(spec)
        return tuple(matches)


class CandidateLike:
    path: str
    function: Optional[str]
    source_kind: str
    symbols: Tuple[str, ...]
    role: str


def default_registry() -> SemanticRegistry:
    def s(value: str, kind: SemanticKind, domain: str, paths: tuple[str, ...], *, symbols=(), source_kinds=(), functions=(), roles=(), confidence=Confidence.UNKNOWN, notes=""):
        return SemanticSpecification(SemanticId(value), kind, domain, paths, tuple(symbols), tuple(source_kinds), tuple(functions), tuple(roles), confidence, notes)

    specs = [
        s("integration.susfs.initialization", SemanticKind.SUSFS_BEHAVIOR, "integration", ("kernel/ksu.c",), symbols=("susfs_init",), source_kinds=("official_10", "xxksu"), confidence=Confidence.HIGH),
        s("config.susfs.control", SemanticKind.CONFIG_CONTROL, "config", ("kernel/Kconfig",), symbols=("CONFIG_KSU_SUSFS",), source_kinds=("official_10", "xxksu"), confidence=Confidence.HIGH),
        s("config.lsm_security_hooks", SemanticKind.CONFIG_CONTROL, "config", ("kernel/Kconfig",), symbols=("CONFIG_KSU_LSM_SECURITY_HOOKS",), source_kinds=("xxksu",), confidence=Confidence.HIGH),
        s("config.arm64_branch_link", SemanticKind.CONFIG_CONTROL, "config", ("kernel/Kconfig",), symbols=("CONFIG_KSU_HACK_ARM64_BRANCH_LINK",), source_kinds=("xxksu",), confidence=Confidence.HIGH),
        s("config.syscall_tamper", SemanticKind.CONFIG_CONTROL, "config", ("kernel/Kconfig",), symbols=("CONFIG_KSU_TAMPER_SYSCALL_TABLE",), source_kinds=("xxksu",), confidence=Confidence.HIGH),
        s("config.kprobe_ksud", SemanticKind.CONFIG_CONTROL, "config", ("kernel/Kconfig",), symbols=("CONFIG_KSU_KPROBES_KSUD",), source_kinds=("xxksu",), confidence=Confidence.HIGH),
        s("susfs.uname.behavior", SemanticKind.SUSFS_BEHAVIOR, "uname", ("kernel/sys.c",), symbols=("susfs_spoof_uname",), confidence=Confidence.HIGH),
        s("susfs.stat.kstat", SemanticKind.SUSFS_BEHAVIOR, "stat", ("fs/stat.c",), symbols=("kstat", "susfs"), confidence=Confidence.HIGH),
        s("susfs.stat.mount_id", SemanticKind.SUSFS_BEHAVIOR, "stat", ("fs/stat.c",), symbols=("mnt_id", "mnt_id_unique"), confidence=Confidence.HIGH),
        s("transport.exec.definition", SemanticKind.HANDLER_DEFINITION, "exec", ("kernel/feature/sucompat.c",), symbols=("ksu_handle_execveat",), source_kinds=("xxksu",), roles=("definition",), confidence=Confidence.HIGH),
        s("transport.exec.linux_call", SemanticKind.LINUX_CALL_SITE, "exec", ("fs/exec.c",), symbols=("ksu_handle_execveat",), source_kinds=("official_50",), roles=("caller",), confidence=Confidence.HIGH),
        s("transport.exec.manual_fixture", SemanticKind.MANUAL_SOURCE_HOOK, "exec", ("fs/exec.c",), symbols=("ksu_handle_execveat",), source_kinds=("fixture_scope_min",), roles=("caller",), confidence=Confidence.HIGH),
        s("transport.exec.fixture_declaration", SemanticKind.HANDLER_DECLARATION, "exec", ("fs/exec.c",), symbols=("ksu_handle_execveat",), source_kinds=("fixture_scope_min",), roles=("declaration",), confidence=Confidence.HIGH),
        s("transport.exec.branch_link", SemanticKind.ARM64_BRANCH_LINK, "exec", ("kernel/hook/branch_link_hook_arm64.c",), symbols=("ksu_do_execveat_common",), source_kinds=("xxksu",), roles=("definition",), confidence=Confidence.HIGH),
        s("official_only.exec.sucompat", SemanticKind.HANDLER_DEFINITION, "exec", ("kernel/feature/sucompat.c",), symbols=("ksu_handle_execveat_sucompat",), source_kinds=("official_10",), roles=("definition",), confidence=Confidence.HIGH, notes="official interface; absent from actual xxKSU"),
        s("transport.access.linux_call", SemanticKind.LINUX_CALL_SITE, "access", ("fs/open.c",), symbols=("ksu_handle_faccessat",), source_kinds=("official_50",), roles=("caller",), confidence=Confidence.HIGH),
        s("transport.access.manual_fixture", SemanticKind.MANUAL_SOURCE_HOOK, "access", ("fs/open.c",), symbols=("ksu_handle_faccessat",), source_kinds=("fixture_scope_min",), roles=("caller",), confidence=Confidence.HIGH),
        s("transport.access.fixture_declaration", SemanticKind.HANDLER_DECLARATION, "access", ("fs/open.c",), symbols=("ksu_handle_faccessat",), source_kinds=("fixture_scope_min",), roles=("declaration",), confidence=Confidence.HIGH),
        s("transport.access.branch_link", SemanticKind.ARM64_BRANCH_LINK, "access", ("kernel/hook/branch_link_hook_arm64.c",), symbols=("ksu_vfs_faccessat",), source_kinds=("xxksu",), roles=("definition",), confidence=Confidence.HIGH),
        s("transport.stat.linux_call", SemanticKind.LINUX_CALL_SITE, "stat", ("fs/stat.c",), symbols=("ksu_handle_stat",), source_kinds=("official_50",), roles=("caller",), confidence=Confidence.HIGH),
        s("transport.stat.manual_fixture", SemanticKind.MANUAL_SOURCE_HOOK, "stat", ("fs/stat.c",), symbols=("ksu_handle_stat",), source_kinds=("fixture_scope_min",), roles=("caller",), confidence=Confidence.HIGH),
        s("transport.stat.fixture_declaration", SemanticKind.HANDLER_DECLARATION, "stat", ("fs/stat.c",), symbols=("ksu_handle_stat",), source_kinds=("fixture_scope_min",), roles=("declaration",), confidence=Confidence.HIGH),
        s("transport.stat.branch_link", SemanticKind.ARM64_BRANCH_LINK, "stat", ("kernel/hook/branch_link_hook_arm64.c",), symbols=("ksu_vfs_fstatat",), source_kinds=("xxksu",), roles=("definition",), confidence=Confidence.HIGH),
        s("transport.fstat_return.definition", SemanticKind.HANDLER_DEFINITION, "fstat-return", ("kernel/runtime/ksud.c",), symbols=("ksu_handle_newfstat_ret", "ksu_handle_fstat64_ret"), source_kinds=("xxksu",), roles=("definition",), confidence=Confidence.HIGH),
        s("transport.fstat_return.manual_fixture", SemanticKind.MANUAL_SOURCE_HOOK, "fstat-return", ("fs/stat.c",), symbols=("ksu_handle_newfstat_ret", "ksu_handle_fstat64_ret"), source_kinds=("fixture_scope_min",), roles=("caller",), confidence=Confidence.HIGH),
        s("transport.fstat_return.fixture_declaration", SemanticKind.HANDLER_DECLARATION, "fstat-return", ("fs/stat.c",), symbols=("ksu_handle_newfstat_ret", "ksu_handle_fstat64_ret"), source_kinds=("fixture_scope_min",), roles=("declaration",), confidence=Confidence.HIGH),
        s("transport.fstat_return.internal_fallback", SemanticKind.SYSCALL_TABLE_HOOK, "fstat-return", ("kernel/hook/syscall_table_hook_arm64.c",), source_kinds=("xxksu",), roles=("fallback",), confidence=Confidence.HIGH),
        s("official_only.fstat.definition", SemanticKind.HANDLER_DEFINITION, "fstat-return", ("kernel/runtime/ksud.c",), symbols=("ksu_handle_vfs_fstat",), source_kinds=("official_10",), roles=("definition",), confidence=Confidence.HIGH, notes="official interface; actual xxKSU uses return handlers"),
        s("transport.read.linux_call", SemanticKind.LINUX_CALL_SITE, "read", ("fs/read_write.c",), symbols=("ksu_handle_sys_read",), source_kinds=("official_50",), roles=("caller",), confidence=Confidence.HIGH),
        s("transport.read.manual_fixture", SemanticKind.MANUAL_SOURCE_HOOK, "read", ("security/security.c",), symbols=("ksu_file_permission",), source_kinds=("fixture_manual_security",), roles=("caller",), confidence=Confidence.HIGH),
        s("transport.read.internal_fallback", SemanticKind.SYSCALL_TABLE_HOOK, "read", ("kernel/hook/syscall_table_hook_arm64.c",), symbols=("ksu_handle_sys_read_fd",), source_kinds=("xxksu",), roles=("fallback",), confidence=Confidence.HIGH),
        s("official_only.read.definition", SemanticKind.HANDLER_DEFINITION, "read", ("kernel/runtime/ksud.c",), symbols=("ksu_handle_sys_read",), source_kinds=("official_10",), roles=("definition",), confidence=Confidence.HIGH, notes="official interface; actual xxKSU uses install-RC behavior"),
        s("transport.reboot.definition", SemanticKind.HANDLER_DEFINITION, "reboot", ("kernel/supercall/supercall.c",), symbols=("ksu_handle_sys_reboot",), source_kinds=("xxksu",), roles=("definition",), confidence=Confidence.HIGH),
        s("transport.reboot.linux_call", SemanticKind.LINUX_CALL_SITE, "reboot", ("kernel/reboot.c",), symbols=("ksu_handle_sys_reboot",), source_kinds=("official_50",), roles=("caller",), confidence=Confidence.HIGH),
        s("transport.reboot.manual_fixture", SemanticKind.MANUAL_SOURCE_HOOK, "reboot", ("kernel/reboot.c",), symbols=("ksu_handle_sys_reboot",), source_kinds=("fixture_scope_min",), roles=("caller",), confidence=Confidence.HIGH),
        s("transport.reboot.fixture_declaration", SemanticKind.HANDLER_DECLARATION, "reboot", ("kernel/reboot.c",), symbols=("ksu_handle_sys_reboot",), source_kinds=("fixture_scope_min",), roles=("declaration",), confidence=Confidence.HIGH),
        s("transport.reboot.internal_fallback", SemanticKind.SYSCALL_TABLE_HOOK, "reboot", ("kernel/hook/syscall_table_hook_arm64.c",), symbols=("ksu_handle_sys_reboot",), source_kinds=("xxksu",), roles=("fallback",), confidence=Confidence.HIGH),
        s("transport.setuid.definition", SemanticKind.HANDLER_DEFINITION, "setuid", ("kernel/hook/setuid_hook.c",), symbols=("ksu_handle_setresuid",), source_kinds=("xxksu",), roles=("definition",), confidence=Confidence.HIGH),
        s("transport.setuid.manual_fixture", SemanticKind.MANUAL_SOURCE_HOOK, "setuid", ("security/security.c",), symbols=("ksu_task_fix_setuid",), source_kinds=("fixture_manual_security",), roles=("caller",), confidence=Confidence.HIGH),
        s("transport.setuid.fixture_declaration", SemanticKind.HANDLER_DECLARATION, "setuid", ("security/security.c",), symbols=("ksu_task_fix_setuid",), source_kinds=("fixture_manual_security",), roles=("declaration",), confidence=Confidence.HIGH),
        s("transport.bprm.manual_fixture", SemanticKind.MANUAL_SOURCE_HOOK, "bprm", ("security/security.c",), symbols=("ksu_bprm_check",), source_kinds=("fixture_manual_security",), roles=("caller",), confidence=Confidence.HIGH),
        s("transport.bprm.fixture_declaration", SemanticKind.HANDLER_DECLARATION, "bprm", ("security/security.c",), symbols=("ksu_bprm_check",), source_kinds=("fixture_manual_security",), roles=("declaration",), confidence=Confidence.HIGH),
        s("transport.rename.manual_fixture", SemanticKind.MANUAL_SOURCE_HOOK, "rename", ("security/security.c",), symbols=("ksu_inode_rename",), source_kinds=("fixture_manual_security",), roles=("caller",), confidence=Confidence.HIGH),
        s("transport.rename.fixture_declaration", SemanticKind.HANDLER_DECLARATION, "rename", ("security/security.c",), symbols=("ksu_inode_rename",), source_kinds=("fixture_manual_security",), roles=("declaration",), confidence=Confidence.HIGH),
        s("transport.setprocattr.manual_fixture", SemanticKind.MANUAL_SOURCE_HOOK, "setprocattr", ("security/security.c",), symbols=("ksu_hide_setprocattr",), source_kinds=("fixture_manual_security",), roles=("caller",), confidence=Confidence.MEDIUM),
        s("transport.setprocattr.fixture_declaration", SemanticKind.HANDLER_DECLARATION, "setprocattr", ("security/security.c",), symbols=("ksu_hide_setprocattr",), source_kinds=("fixture_manual_security",), roles=("declaration",), confidence=Confidence.MEDIUM),
        s("transport.setuid.lsm", SemanticKind.LSM_SECURITY_HOOK, "setuid", ("kernel/hook/lsm_hooks_list.c", "kernel/hook/lsm_hooks_static.c"), symbols=("security_task_fix_setuid",), source_kinds=("xxksu",), roles=("caller",), confidence=Confidence.HIGH),
        s("transport.input.official_assumption", SemanticKind.LINUX_CALL_SITE, "input", ("drivers/input/input.c",), symbols=("ksu_handle_input_handle_event",), source_kinds=("official_50",), roles=("caller",), confidence=Confidence.HIGH),
        s("transport.input.registration", SemanticKind.RUNTIME_REGISTRATION, "input", ("kernel/feature/vol_detector.c",), symbols=("input_register_handler", "vol_detector_event"), source_kinds=("xxksu",), roles=("caller", "definition"), confidence=Confidence.HIGH),
        s("official_only.input.definition", SemanticKind.HANDLER_DEFINITION, "input", ("kernel/runtime/ksud.c",), symbols=("ksu_handle_input_handle_event",), source_kinds=("official_10",), roles=("definition",), confidence=Confidence.HIGH, notes="official interface; actual xxKSU registers volume detector"),
        s("transport.ksud.kprobe", SemanticKind.KPROBE, "transport", ("kernel/hook/kp_ksud.c",), symbols=("register_kprobe", "register_kretprobe"), source_kinds=("xxksu",), roles=("caller",), confidence=Confidence.HIGH),
        s("transport.bl.branch_link", SemanticKind.ARM64_BRANCH_LINK, "transport", ("kernel/hook/branch_link_hook_arm64.c",), symbols=("branch_link",), source_kinds=("xxksu",), roles=("caller", "definition"), confidence=Confidence.HIGH),
        s("transport.bl.internal_fallback", SemanticKind.SYSCALL_TABLE_HOOK, "transport", ("kernel/hook/syscall_table_hook_arm64.c",), symbols=("syscall_table",), source_kinds=("xxksu",), roles=("caller", "fallback"), confidence=Confidence.HIGH),
        s("transport.bl.composite", SemanticKind.TRANSPORT_WRAPPER, "transport", ("kernel/hook/branch_link_hook_arm64.c", "kernel/hook/syscall_table_hook_arm64.c"), symbols=("branch_link", "syscall_table"), source_kinds=("xxksu",), roles=("caller", "definition", "fallback"), confidence=Confidence.HIGH),
        s("selinux.avc.replace", SemanticKind.SELINUX_BEHAVIOR, "selinux", ("kernel/feature/selinux_hide.c", "kernel/downstream/slow_avc_audit_defs.h"), symbols=("slow_avc_audit",), source_kinds=("xxksu",), confidence=Confidence.HIGH),
        s("selinux.fake_status", SemanticKind.SELINUX_BEHAVIOR, "selinux", ("kernel/feature/selinux_hide.c",), symbols=("ksu_fake_status_page",), source_kinds=("xxksu",), confidence=Confidence.HIGH),
        s("selinux.setprocattr", SemanticKind.SELINUX_BEHAVIOR, "selinux", ("kernel/feature/selinux_hide.c",), symbols=("ksu_hide_setprocattr",), source_kinds=("xxksu", "fixture_manual_security"), confidence=Confidence.MEDIUM),
        s("selinux.context_access", SemanticKind.SELINUX_BEHAVIOR, "selinux", ("kernel/feature/selinux_hide.c",), symbols=("write_context", "write_access"), source_kinds=("xxksu",), confidence=Confidence.MEDIUM),
    ]
    return SemanticRegistry(specs)
