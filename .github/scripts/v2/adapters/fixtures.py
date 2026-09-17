"""Deterministic fixture adaptation mechanics and operation models for V2.6."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple, TYPE_CHECKING

from ..model.provenance import HashDigest, canonical_json
from .base import (
    AdapterError,
    AnchorLocation,
    AnchorSpec,
    MissingSemanticAnchor,
    MultipleSemanticAnchors,
    UnsupportedKernelVersion,
    UnsupportedTarget,
)

from ..source.bundle import MissingBundleFile

if TYPE_CHECKING:
    from ..source.bundle import SourceBundle
    from .base import TargetAdapter


FIXED_FIXTURES: Tuple[str, ...] = (
    "scope-min-manual-hooks-v2.3.patch",
    "manual-security-hooks-v2.0.patch",
)

ADAPTATION_PLAN_SCHEMA = "xxksu-susfs-adaptation-plan/v1"


class FixtureAdaptationError(AdapterError):
    """Base error for fixture adaptation failures."""
    pass


class IncompatibleFixtureTarget(FixtureAdaptationError, UnsupportedTarget):
    pass


class DuplicateAdaptationOperation(FixtureAdaptationError):
    pass


class MissingFixtureSource(FixtureAdaptationError, MissingSemanticAnchor):
    pass


class AmbiguousFixtureMatch(FixtureAdaptationError, MultipleSemanticAnchors):
    pass


class FixtureContractViolation(FixtureAdaptationError):
    pass


class Placement(str, Enum):
    BEFORE = "BEFORE"
    AFTER = "AFTER"
    REPLACE = "REPLACE"


@dataclass(frozen=True)
class AdaptationOperation:
    operation_id: str
    fixture_name: str
    file_path: str
    anchor_location: AnchorLocation
    placement: Placement
    payload: str
    target_id: str
    function: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.operation_id or not self.fixture_name or not self.file_path:
            raise FixtureContractViolation("AdaptationOperation requires id, fixture_name, and file_path")
        if not isinstance(self.anchor_location, AnchorLocation):
            raise FixtureContractViolation("invalid anchor_location")

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "fixture_name": self.fixture_name,
            "file_path": self.file_path,
            "function": self.function,
            "placement": self.placement.value,
            "payload": self.payload,
            "target_id": self.target_id,
            "anchor_location": self.anchor_location.to_dict(),
        }

    def canonical_json(self) -> str:
        return canonical_json(self.to_dict())

    @property
    def identity(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def apply(self, source_text: str) -> str:
        loc = self.anchor_location
        if loc.start_offset is None or loc.end_offset is None:
            raise FixtureContractViolation("anchor_location offsets must be resolved to apply operation")
        if self.placement == Placement.BEFORE:
            return source_text[:loc.start_offset] + self.payload + source_text[loc.start_offset:]
        elif self.placement == Placement.AFTER:
            return source_text[:loc.end_offset] + self.payload + source_text[loc.end_offset:]
        elif self.placement == Placement.REPLACE:
            return source_text[:loc.start_offset] + self.payload + source_text[loc.end_offset:]
        raise FixtureContractViolation(f"unknown placement: {self.placement}")


@dataclass(frozen=True)
class FixtureAdaptationPlan:
    target_id: str
    bundle_identity: str
    operations: Tuple[AdaptationOperation, ...]
    schema: str = ADAPTATION_PLAN_SCHEMA
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema != ADAPTATION_PLAN_SCHEMA:
            raise FixtureContractViolation(f"unsupported adaptation plan schema: {self.schema}")
        seen_ids: set[str] = set()
        seen_offsets: dict[str, set[int]] = {}
        for op in self.operations:
            if op.operation_id in seen_ids:
                raise DuplicateAdaptationOperation(f"duplicate operation: {op.operation_id}")
            seen_ids.add(op.operation_id)
            if op.anchor_location.start_offset is not None:
                offsets = seen_offsets.setdefault(op.file_path, set())
                if op.anchor_location.start_offset in offsets:
                    raise DuplicateAdaptationOperation(
                        f"duplicate anchor target in {op.file_path} at offset {op.anchor_location.start_offset}"
                    )
                offsets.add(op.anchor_location.start_offset)

    @property
    def operation_count(self) -> int:
        return len(self.operations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "target_id": self.target_id,
            "bundle_identity": self.bundle_identity,
            "operations": [op.to_dict() for op in sorted(self.operations, key=lambda o: o.operation_id)],
            "metadata": dict(self.metadata),
        }

    def canonical_json(self) -> str:
        return canonical_json(self.to_dict())

    @property
    def identity(self) -> HashDigest:
        return HashDigest("sha256", hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest())

    def get_operations_for_file(self, file_path: str) -> Tuple[AdaptationOperation, ...]:
        return tuple(op for op in self.operations if op.file_path == file_path)

    def apply_to_bundle(self, bundle: SourceBundle) -> SourceBundle:
        if str(bundle.identity) != self.bundle_identity and bundle.target_id != self.target_id:
            raise FixtureContractViolation(
                f"bundle target {bundle.target_id} does not match plan target {self.target_id}"
            )

        by_file: dict[str, list[AdaptationOperation]] = {}
        for op in self.operations:
            by_file.setdefault(op.file_path, []).append(op)

        result_bundle = bundle
        for file_path, ops in by_file.items():
            file_entry = bundle.get_file(file_path)
            if file_entry.content is None:
                raise MissingFixtureSource(f"file content for {file_path} not present in bundle")

            # Apply in descending start_offset order to keep earlier character offsets valid
            sorted_ops = sorted(ops, key=lambda o: o.anchor_location.start_offset or 0, reverse=True)
            content = file_entry.content
            for op in sorted_ops:
                content = op.apply(content)

            result_bundle = result_bundle.with_updated_file(file_path, content)

        return result_bundle


@dataclass(frozen=True)
class FixtureOperationSpec:
    operation_id: str
    fixture_name: str
    file_path: str
    function: Optional[str]
    default_anchor_text: str
    placement: Placement
    payload: str
    context_before: Tuple[str, ...] = ()
    context_after: Tuple[str, ...] = ()


# 1. scope-min-manual-hooks-v2.3.patch (7 operations)
_SCOPE_MIN_FIXTURE = "scope-min-manual-hooks-v2.3.patch"
_SCOPE_MIN_SPECS: Tuple[FixtureOperationSpec, ...] = (
    FixtureOperationSpec(
        operation_id="manual.scope_min.exec",
        fixture_name=_SCOPE_MIN_FIXTURE,
        file_path="fs/exec.c",
        function="do_execveat_common",
        default_anchor_text="if (IS_ERR(filename))",
        placement=Placement.BEFORE,
        payload="""#ifdef CONFIG_KSU
	extern int ksu_handle_execveat(int *, struct filename **, void *, void *, int *);
	ksu_handle_execveat(&fd, &filename, &argv, &envp, &flags);
#endif

""",
    ),
    FixtureOperationSpec(
        operation_id="manual.scope_min.access",
        fixture_name=_SCOPE_MIN_FIXTURE,
        file_path="fs/open.c",
        function="faccessat",
        default_anchor_text="return do_faccessat(dfd, filename, mode, 0);",
        placement=Placement.BEFORE,
        payload="""#ifdef CONFIG_KSU
	extern int ksu_handle_faccessat(int *, const char __user **, int *, int *);
	ksu_handle_faccessat(&dfd, &filename, &mode, NULL);
#endif
""",
    ),
    FixtureOperationSpec(
        operation_id="manual.scope_min.stat",
        fixture_name=_SCOPE_MIN_FIXTURE,
        file_path="fs/stat.c",
        function="newfstatat",
        default_anchor_text="error = vfs_fstatat(dfd, filename, &stat, flag);",
        placement=Placement.BEFORE,
        payload="""#ifdef CONFIG_KSU
	extern int ksu_handle_stat(int *, const char __user **, int *);
	ksu_handle_stat(&dfd, &filename, &flag);
#endif

""",
    ),
    FixtureOperationSpec(
        operation_id="manual.scope_min.newfstat_ret",
        fixture_name=_SCOPE_MIN_FIXTURE,
        file_path="fs/stat.c",
        function="newfstat",
        default_anchor_text="return error;",
        placement=Placement.BEFORE,
        payload="""#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wdeclaration-after-statement"
#if defined(CONFIG_KSU) && !defined(CONFIG_KSU_KPROBES_KSUD)
	extern void ksu_handle_newfstat_ret(unsigned int *, struct stat __user **);
	ksu_handle_newfstat_ret(&fd, &statbuf);
#endif
#pragma GCC diagnostic pop

""",
    ),
    FixtureOperationSpec(
        operation_id="manual.scope_min.fstat64_ret",
        fixture_name=_SCOPE_MIN_FIXTURE,
        file_path="fs/stat.c",
        function="fstat64",
        default_anchor_text="return error;",
        placement=Placement.BEFORE,
        payload="""#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wdeclaration-after-statement"
#if defined(CONFIG_KSU) && !defined(CONFIG_KSU_KPROBES_KSUD) // for 32-bit
	extern void ksu_handle_fstat64_ret(unsigned long *, struct stat64 __user **);
	ksu_handle_fstat64_ret(&fd, &statbuf);
#endif
#pragma GCC diagnostic pop

""",
    ),
    FixtureOperationSpec(
        operation_id="manual.scope_min.fstatat64",
        fixture_name=_SCOPE_MIN_FIXTURE,
        file_path="fs/stat.c",
        function="fstatat64",
        default_anchor_text="error = vfs_fstatat(dfd, filename, &stat, flag);",
        placement=Placement.BEFORE,
        payload="""#ifdef CONFIG_KSU // for 32-bit
	extern int ksu_handle_stat(int *, const char __user **, int *);
	ksu_handle_stat(&dfd, &filename, &flag);
#endif

""",
    ),
    FixtureOperationSpec(
        operation_id="manual.scope_min.reboot",
        fixture_name=_SCOPE_MIN_FIXTURE,
        file_path="kernel/reboot.c",
        function="reboot",
        default_anchor_text="/* We only trust the superuser with rebooting the system. */",
        placement=Placement.BEFORE,
        payload="""#if defined(CONFIG_KSU) && !defined(CONFIG_KSU_KPROBES_KSUD)
	extern int ksu_handle_sys_reboot(int, int, unsigned int, void __user **);
	ksu_handle_sys_reboot(magic1, magic2, cmd, &arg);
#endif

""",
    ),
)


# 2. manual-security-hooks-v2.0.patch (6 operations)
_MANUAL_SECURITY_FIXTURE = "manual-security-hooks-v2.0.patch"
_MANUAL_SECURITY_SPECS: Tuple[FixtureOperationSpec, ...] = (
    FixtureOperationSpec(
        operation_id="manual.security.decl",
        fixture_name=_MANUAL_SECURITY_FIXTURE,
        file_path="security/security.c",
        function=None,
        default_anchor_text="#include <linux/lsm_hook_defs.h>",
        placement=Placement.AFTER,
        payload="""

#ifdef CONFIG_KSU
extern int ksu_bprm_check(struct linux_binprm *bprm);
extern int ksu_inode_rename(struct inode *old_dir, struct dentry *old_dentry,
				struct inode *new_dir, struct dentry *new_dentry);
extern int ksu_task_fix_setuid(struct cred *new, const struct cred *old, int flags);
extern int ksu_file_permission(struct file *file, int mask);
extern int ksu_hide_setprocattr(const char *name, void *value, size_t size);
#endif
""",
    ),
    FixtureOperationSpec(
        operation_id="manual.security.bprm",
        fixture_name=_MANUAL_SECURITY_FIXTURE,
        file_path="security/security.c",
        function="security_bprm_check",
        default_anchor_text="ret = call_int_hook(bprm_check_security, 0, bprm);",
        placement=Placement.BEFORE,
        payload="""#ifdef CONFIG_KSU
	ksu_bprm_check(bprm);
#endif
""",
    ),
    FixtureOperationSpec(
        operation_id="manual.security.rename",
        fixture_name=_MANUAL_SECURITY_FIXTURE,
        file_path="security/security.c",
        function="security_inode_rename",
        default_anchor_text="if (unlikely(IS_PRIVATE(d_backing_inode(old_dentry))",
        placement=Placement.BEFORE,
        payload="""#ifdef CONFIG_KSU
	ksu_inode_rename(old_dir, old_dentry, new_dir, new_dentry);
#endif
""",
    ),
    FixtureOperationSpec(
        operation_id="manual.security.file_permission",
        fixture_name=_MANUAL_SECURITY_FIXTURE,
        file_path="security/security.c",
        function="security_file_permission",
        default_anchor_text="ret = call_int_hook(file_permission, 0, file, mask);",
        placement=Placement.BEFORE,
        payload="""#ifdef CONFIG_KSU
	ksu_file_permission(file, mask);
#endif
""",
    ),
    FixtureOperationSpec(
        operation_id="manual.security.setuid",
        fixture_name=_MANUAL_SECURITY_FIXTURE,
        file_path="security/security.c",
        function="security_task_fix_setuid",
        default_anchor_text="return call_int_hook(task_fix_setuid, 0, new, old, flags);",
        placement=Placement.BEFORE,
        payload="""#ifdef CONFIG_KSU
	ksu_task_fix_setuid(new, old, flags);
#endif
""",
    ),
    FixtureOperationSpec(
        operation_id="manual.security.setprocattr",
        fixture_name=_MANUAL_SECURITY_FIXTURE,
        file_path="security/security.c",
        function="security_setprocattr",
        default_anchor_text="hlist_for_each_entry(hp, &security_hook_heads.setprocattr, list) {",
        placement=Placement.BEFORE,
        payload="""#ifdef CONFIG_KSU
	ksu_hide_setprocattr(name, value, size);
#endif
""",
    ),
)


_FIXTURE_SPECS: Mapping[str, Tuple[FixtureOperationSpec, ...]] = {
    _SCOPE_MIN_FIXTURE: _SCOPE_MIN_SPECS,
    _MANUAL_SECURITY_FIXTURE: _MANUAL_SECURITY_SPECS,
}


def get_fixture_operation_specs(fixture_name: str) -> Tuple[FixtureOperationSpec, ...]:
    if fixture_name not in _FIXTURE_SPECS:
        raise IncompatibleFixtureTarget(f"unknown or unsupported fixture: {fixture_name}")
    return _FIXTURE_SPECS[fixture_name]


def adapt_fixture_for_adapter(
    adapter: TargetAdapter,
    bundle: SourceBundle,
    fixture_name: str,
) -> Tuple[AdaptationOperation, ...]:
    adapter.validate_source_bundle(bundle)
    specs = get_fixture_operation_specs(fixture_name)

    operations: list[AdaptationOperation] = []
    seen_ids: set[str] = set()

    for spec in specs:
        if spec.operation_id in seen_ids:
            raise DuplicateAdaptationOperation(f"duplicate fixture operation spec: {spec.operation_id}")
        seen_ids.add(spec.operation_id)

        # Check adapter-specific anchor override first, then fallback to default spec
        override_spec = adapter.get_fixture_anchor_spec(fixture_name, spec.operation_id)
        if override_spec is not None:
            anchor_spec = override_spec
        else:
            anchor_spec = AnchorSpec(
                file_path=spec.file_path,
                anchor_text=spec.default_anchor_text,
                function=spec.function,
                context_before=spec.context_before,
                context_after=spec.context_after,
            )

        try:
            anchor_location = adapter.locate_anchor_in_bundle(bundle, anchor_spec)
        except (MissingSemanticAnchor, MissingBundleFile) as exc:
            raise MissingFixtureSource(
                f"missing source anchor for {spec.operation_id} in {spec.file_path}: {exc}"
            ) from exc
        except MultipleSemanticAnchors as exc:
            raise AmbiguousFixtureMatch(
                f"ambiguous source anchor for {spec.operation_id} in {spec.file_path}: {exc}"
            ) from exc

        operations.append(
            AdaptationOperation(
                operation_id=spec.operation_id,
                fixture_name=fixture_name,
                file_path=spec.file_path,
                anchor_location=anchor_location,
                placement=spec.placement,
                payload=spec.payload,
                target_id=adapter.target_id,
                function=spec.function,
            )
        )

    return tuple(operations)


def adapt_fixtures_for_adapter(
    adapter: TargetAdapter,
    bundle: SourceBundle,
    fixture_names: Iterable[str] = FIXED_FIXTURES,
) -> FixtureAdaptationPlan:
    adapter.validate_source_bundle(bundle)

    plan_operations: list[AdaptationOperation] = []
    seen_ids: set[str] = set()

    for fname in fixture_names:
        ops = adapt_fixture_for_adapter(adapter, bundle, fname)
        for op in ops:
            if op.operation_id in seen_ids:
                raise DuplicateAdaptationOperation(f"duplicate operation across fixtures: {op.operation_id}")
            seen_ids.add(op.operation_id)
            plan_operations.append(op)

    return FixtureAdaptationPlan(
        target_id=adapter.target_id,
        bundle_identity=str(bundle.identity),
        operations=tuple(plan_operations),
    )
