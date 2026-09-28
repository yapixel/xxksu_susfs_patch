"""Unit tests for V2.6 fixture adaptation mechanics."""

import unittest
from test_lifecycle import target_sources

from v2.adapters import (
    FIXED_FIXTURES,
    AdaptationOperation,
    AmbiguousFixtureMatch,
    DuplicateAdaptationOperation,
    FixtureAdaptationPlan,
    FixtureContractViolation,
    SultanAndroid14_6_1Adapter,
    GKIAndroid16_6_12Adapter,
    IncompatibleFixtureTarget,
    MissingFixtureSource,
    MissingSemanticAnchor,
    MultipleSemanticAnchors,
    Placement,
    SultanAndroid14_6_1Adapter,
    UnsupportedKernelVersion,
    UnsupportedTarget,
    adapt_fixture_for_adapter,
    adapt_fixtures_for_adapter,
    get_adapter,
)
from v2.source.bundle import create_source_bundle


_SAMPLE_EXEC = """/* fs/exec.c */
#include <linux/fs.h>

static int do_execveat_common(int fd, struct filename *filename,
	struct user_arg_ptr argv,
	struct user_arg_ptr envp,
	int flags)
{
	struct linux_binprm *bprm;
	int retval;

	if (IS_ERR(filename))
		return PTR_ERR(filename);

	return retval;
}
"""

_SAMPLE_OPEN = """/* fs/open.c */
#include <linux/fs.h>

SYSCALL_DEFINE3(faccessat, int, dfd, const char __user *, filename, int, mode)
{
	return do_faccessat(dfd, filename, mode, 0);
}
"""

_SAMPLE_STAT = """/* fs/stat.c */
#include <linux/fs.h>

SYSCALL_DEFINE4(newfstatat, int, dfd, const char __user *, filename,
	struct stat __user *, statbuf, int, flag)
{
	struct kstat stat;
	int error;

	error = vfs_fstatat(dfd, filename, &stat, flag);
	if (error)
		return error;
	return cp_new_stat(&stat, statbuf);
}

SYSCALL_DEFINE2(newfstat, unsigned int, fd, struct stat __user *, statbuf)
{
	struct kstat stat;
	int error;

	if (!error)
		error = cp_new_stat(&stat, statbuf);

	return error;
}

SYSCALL_DEFINE2(fstat64, unsigned long, fd, struct stat64 __user *, statbuf)
{
	struct kstat stat;
	int error;

	if (!error)
		error = cp_new_stat64(&stat, statbuf);

	return error;
}

SYSCALL_DEFINE4(fstatat64, int, dfd, const char __user *, filename,
	struct stat64 __user *, statbuf, int, flag)
{
	struct kstat stat;
	int error;

	error = vfs_fstatat(dfd, filename, &stat, flag);
	if (error)
		return error;
	return cp_new_stat64(&stat, statbuf);
}
"""

_SAMPLE_REBOOT = """/* kernel/reboot.c */
#include <linux/reboot.h>

SYSCALL_DEFINE4(reboot, int, magic1, int, magic2, unsigned int, cmd, void __user *, arg)
{
	char buffer[256];
	int ret = 0;

	/* We only trust the superuser with rebooting the system. */
	if (!ns_capable(pid_ns->user_ns, CAP_SYS_BOOT))
		return -EPERM;
	return ret;
}
"""

_SAMPLE_SECURITY_6_1 = target_sources(False)["security/security.c"]

_SAMPLE_SECURITY_6_12 = target_sources(True)["security/security.c"]


def _make_clean_bundle(target_id="sultan-android14-6.1", version="6.1.25"):
    sec_content = _SAMPLE_SECURITY_6_12 if "6.12" in target_id else _SAMPLE_SECURITY_6_1
    return create_source_bundle(
        target_id=target_id,
        kernel_version=version,
        files={
            "fs/exec.c": _SAMPLE_EXEC,
            "fs/open.c": _SAMPLE_OPEN,
            "fs/stat.c": _SAMPLE_STAT,
            "kernel/reboot.c": _SAMPLE_REBOOT,
            "security/security.c": sec_content,
        },
    )


class TestV26FixtureAdaptation(unittest.TestCase):

    def setUp(self):
        self.adapter_sultan = get_adapter("sultan-android14-6.1")
        self.adapter_sultan2 = get_adapter("gki-android16-6.12")
        self.bundle_sultan = _make_clean_bundle("sultan-android14-6.1", "6.1.25")
        self.bundle_sultan2 = _make_clean_bundle("gki-android16-6.12", "6.12.0")

    def test_target_fixture_adaptation_matrix(self):
        expected_ids = {
            "manual.scope_min.exec", "manual.scope_min.access", "manual.scope_min.stat",
            "manual.scope_min.newfstat_ret", "manual.scope_min.fstat64_ret", "manual.scope_min.fstatat64",
            "manual.scope_min.reboot", "manual.security.decl", "manual.security.bprm",
            "manual.security.rename", "manual.security.file_permission", "manual.security.setuid",
            "manual.security.setprocattr",
        }
        for adapter, bundle in ((self.adapter_sultan, self.bundle_sultan), (self.adapter_sultan2, self.bundle_sultan2)):
            with self.subTest(target=bundle.target_id):
                plan = adapter.adapt_fixtures(bundle)
                self.assertEqual({op.operation_id for op in plan.operations}, expected_ids)
                repeated = adapter.adapt_fixtures(bundle)
                self.assertEqual(plan.canonical_json(), repeated.canonical_json())
                self.assertEqual(plan.identity, repeated.identity)
                for fixture, count in zip(FIXED_FIXTURES, (7, 6)):
                    partial = adapter.adapt_fixture(bundle, fixture)
                    self.assertEqual(len(partial), count)
                    self.assertEqual([op for op in plan.operations if op.fixture_name == fixture], list(partial))


    def test_missing_source_fails_closed(self):
        # Bundle missing fs/exec.c
        incomplete_bundle = create_source_bundle(
            target_id="sultan-android14-6.1",
            kernel_version="6.1.25",
            files={
                "fs/open.c": _SAMPLE_OPEN,
                "fs/stat.c": _SAMPLE_STAT,
                "kernel/reboot.c": _SAMPLE_REBOOT,
                "security/security.c": _SAMPLE_SECURITY_6_1,
            },
        )
        with self.assertRaises(MissingFixtureSource):
            self.adapter_sultan.adapt_fixtures(incomplete_bundle)

    def test_missing_anchor_in_source_fails_closed(self):
        # fs/open.c without do_faccessat anchor
        altered_bundle = create_source_bundle(
            target_id="sultan-android14-6.1",
            kernel_version="6.1.25",
            files={
                "fs/exec.c": _SAMPLE_EXEC,
                "fs/open.c": "/* completely different content */",
                "fs/stat.c": _SAMPLE_STAT,
                "kernel/reboot.c": _SAMPLE_REBOOT,
                "security/security.c": _SAMPLE_SECURITY_6_1,
            },
        )
        with self.assertRaises(MissingFixtureSource):
            self.adapter_sultan.adapt_fixtures(altered_bundle)

    def test_ambiguous_anchor_in_source_fails_closed(self):
        # Duplicate anchor in do_execveat_common
        dup_exec = _SAMPLE_EXEC.replace(
            "if (IS_ERR(filename))",
            "if (IS_ERR(filename))\n\tif (IS_ERR(filename))",
        )
        ambiguous_bundle = create_source_bundle(
            target_id="sultan-android14-6.1",
            kernel_version="6.1.25",
            files={
                "fs/exec.c": dup_exec,
                "fs/open.c": _SAMPLE_OPEN,
                "fs/stat.c": _SAMPLE_STAT,
                "kernel/reboot.c": _SAMPLE_REBOOT,
                "security/security.c": _SAMPLE_SECURITY_6_1,
            },
        )
        with self.assertRaises(AmbiguousFixtureMatch):
            self.adapter_sultan.adapt_fixtures(ambiguous_bundle)

    def test_duplicate_operation_fails_closed(self):
        plan = self.adapter_sultan.adapt_fixtures(self.bundle_sultan)
        first_op = plan.operations[0]
        with self.assertRaises(DuplicateAdaptationOperation):
            FixtureAdaptationPlan(
                target_id="sultan-android14-6.1",
                bundle_identity=str(self.bundle_sultan.identity),
                operations=(first_op, first_op),
            )

    def test_incompatible_fixture_name_fails_closed(self):
        with self.assertRaises(IncompatibleFixtureTarget):
            self.adapter_sultan.adapt_fixtures(self.bundle_sultan, ("unsupported-fixture.patch",))

    def test_bundle_target_incompatibility_fails_closed(self):
        # Pass 6.12 bundle to 6.1 adapter
        with self.assertRaises(UnsupportedTarget):
            self.adapter_sultan.adapt_fixtures(self.bundle_sultan2)

    def test_apply_plan_to_bundle(self):
        plan = self.adapter_sultan.adapt_fixtures(self.bundle_sultan)
        adapted_bundle = plan.apply_to_bundle(self.bundle_sultan)

        # Check that mutations occurred in bundle files
        exec_file = adapted_bundle.get_file("fs/exec.c")
        self.assertIn("ksu_handle_execveat", exec_file.content)

        open_file = adapted_bundle.get_file("fs/open.c")
        self.assertIn("ksu_handle_faccessat", open_file.content)

        stat_file = adapted_bundle.get_file("fs/stat.c")
        self.assertIn("ksu_handle_stat", stat_file.content)
        self.assertIn("ksu_handle_newfstat_ret", stat_file.content)
        self.assertIn("ksu_handle_fstat64_ret", stat_file.content)

        reboot_file = adapted_bundle.get_file("kernel/reboot.c")
        self.assertIn("ksu_handle_sys_reboot", reboot_file.content)

        sec_file = adapted_bundle.get_file("security/security.c")
        self.assertIn("extern int ksu_bprm_check", sec_file.content)
        self.assertIn("ksu_bprm_check(bprm)", sec_file.content)
        self.assertIn("ksu_inode_rename(old_dir", sec_file.content)
        self.assertIn("ksu_file_permission(file", sec_file.content)
        self.assertIn("ksu_task_fix_setuid(new", sec_file.content)
        self.assertIn("ksu_hide_setprocattr(name", sec_file.content)

        # Confirm new bundle has valid, updated SHA-256 identity
        self.assertNotEqual(adapted_bundle.identity, self.bundle_sultan.identity)
        self.assertTrue(adapted_bundle.verify_file("fs/exec.c", exec_file.content))


if __name__ == "__main__":
    unittest.main()
