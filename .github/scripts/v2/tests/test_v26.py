"""Unit tests for V2.6 fixture adaptation mechanics."""

import unittest

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

_SAMPLE_SECURITY_6_1 = """/* security/security.c */
#include <linux/security.h>

static int lsm_superblock_alloc(struct super_block *sb)
{
	return 0;
}

#include <linux/lsm_hook_defs.h>
#undef LSM_HOOK

int security_bprm_check(struct linux_binprm *bprm)
{
	int ret;

	ret = call_int_hook(bprm_check_security, 0, bprm);
	if (ret)
		return ret;
	return 0;
}

int security_inode_rename(struct inode *old_dir, struct dentry *old_dentry,
			   struct inode *new_dir, struct dentry *new_dentry,
			   unsigned int flags)
{
	if (unlikely(IS_PRIVATE(d_backing_inode(old_dentry)) ||
            (d_is_positive(new_dentry) && IS_PRIVATE(d_backing_inode(new_dentry)))))
		return 0;
	return 0;
}

int security_file_permission(struct file *file, int mask)
{
	int ret;

	ret = call_int_hook(file_permission, 0, file, mask);
	if (ret)
		return ret;
	return 0;
}

int security_task_fix_setuid(struct cred *new, const struct cred *old, int flags)
{
	return call_int_hook(task_fix_setuid, 0, new, old, flags);
}

int security_setprocattr(const char *lsm, const char *name, void *value, size_t size)
{
	struct security_hook_list *hp;

	hlist_for_each_entry(hp, &security_hook_heads.setprocattr, list) {
		if (lsm != NULL && strcmp(lsm, hp->lsm))
			continue;
	}
	return 0;
}
"""

_SAMPLE_SECURITY_6_12 = """/* security/security.c 6.12 */
#include <linux/security.h>

static int lsm_superblock_alloc(struct super_block *sb)
{
	return 0;
}

#include <linux/lsm_hook_defs.h>
#undef LSM_HOOK

int security_bprm_check(struct linux_binprm *bprm)
{
	int ret;

	return 0;
}

int security_inode_rename(struct inode *old_dir, struct dentry *old_dentry,
			   struct inode *new_dir, struct dentry *new_dentry,
			   unsigned int flags)
{
	if (unlikely(IS_PRIVATE(d_backing_inode(old_dentry)) ||
            (d_is_positive(new_dentry) && IS_PRIVATE(d_backing_inode(new_dentry)))))
		return 0;
	return 0;
}

int security_file_permission(struct file *file, int mask)
{
	int ret;

	ret = call_int_hook(file_permission, 0, file, mask);
	if (ret)
		return ret;
	return 0;
}

int security_task_fix_setuid(struct cred *new, const struct cred *old, int flags)
{
	return call_int_hook(task_fix_setuid, 0, new, old, flags);
}

int security_setprocattr(const char *lsm, const char *name, void *value, size_t size)
{
	struct security_hook_list *hp;

	hlist_for_each_entry(hp, &security_hook_heads.setprocattr, list) {
		if (lsm != NULL && strcmp(lsm, hp->lsm))
			continue;
	}
	return 0;
}
"""


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
        self.adapter_gki_6_1 = get_adapter("sultan-android14-6.1")
        self.adapter_gki_6_12 = get_adapter("gki-android16-6.12")
        self.adapter_sultan = get_adapter("sultan-android14-6.1")
        self.bundle_gki_6_1 = _make_clean_bundle("sultan-android14-6.1", "6.1.25")
        self.bundle_gki_6_12 = _make_clean_bundle("gki-android16-6.12", "6.12.0")
        self.bundle_sultan = _make_clean_bundle("sultan-android14-6.1", "6.1.25")

    def test_expected_13_operations_total_on_gki_6_1(self):
        plan = self.adapter_gki_6_1.adapt_fixtures(self.bundle_gki_6_1)
        self.assertEqual(plan.operation_count, 13)

        scope_min_ops = [op for op in plan.operations if op.fixture_name == FIXED_FIXTURES[0]]
        self.assertEqual(len(scope_min_ops), 7)

        manual_sec_ops = [op for op in plan.operations if op.fixture_name == FIXED_FIXTURES[1]]
        self.assertEqual(len(manual_sec_ops), 6)

        expected_ids = {
            "manual.scope_min.exec",
            "manual.scope_min.access",
            "manual.scope_min.stat",
            "manual.scope_min.newfstat_ret",
            "manual.scope_min.fstat64_ret",
            "manual.scope_min.fstatat64",
            "manual.scope_min.reboot",
            "manual.security.decl",
            "manual.security.bprm",
            "manual.security.rename",
            "manual.security.file_permission",
            "manual.security.setuid",
            "manual.security.setprocattr",
        }
        self.assertEqual({op.operation_id for op in plan.operations}, expected_ids)

    def test_adaptation_model_on_gki_6_12(self):
        plan = self.adapter_gki_6_12.adapt_fixtures(self.bundle_gki_6_12)
        self.assertEqual(plan.operation_count, 13)

    def test_adaptation_model_on_sultan_6_1(self):
        plan = self.adapter_sultan.adapt_fixtures(self.bundle_sultan)
        self.assertEqual(plan.operation_count, 13)

    def test_adaptation_is_deterministic(self):
        plan1 = self.adapter_gki_6_1.adapt_fixtures(self.bundle_gki_6_1)
        plan2 = self.adapter_gki_6_1.adapt_fixtures(self.bundle_gki_6_1)

        self.assertEqual(plan1.identity, plan2.identity)
        self.assertEqual(plan1.canonical_json(), plan2.canonical_json())

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
            self.adapter_gki_6_1.adapt_fixtures(incomplete_bundle)

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
            self.adapter_gki_6_1.adapt_fixtures(altered_bundle)

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
            self.adapter_gki_6_1.adapt_fixtures(ambiguous_bundle)

    def test_duplicate_operation_fails_closed(self):
        plan = self.adapter_gki_6_1.adapt_fixtures(self.bundle_gki_6_1)
        first_op = plan.operations[0]
        with self.assertRaises(DuplicateAdaptationOperation):
            FixtureAdaptationPlan(
                target_id="sultan-android14-6.1",
                bundle_identity=str(self.bundle_gki_6_1.identity),
                operations=(first_op, first_op),
            )

    def test_incompatible_fixture_name_fails_closed(self):
        with self.assertRaises(IncompatibleFixtureTarget):
            self.adapter_gki_6_1.adapt_fixtures(self.bundle_gki_6_1, ("unsupported-fixture.patch",))

    def test_bundle_target_incompatibility_fails_closed(self):
        # Pass 6.12 bundle to 6.1 adapter
        with self.assertRaises(UnsupportedTarget):
            self.adapter_gki_6_1.adapt_fixtures(self.bundle_gki_6_12)

    def test_apply_plan_to_bundle(self):
        plan = self.adapter_gki_6_1.adapt_fixtures(self.bundle_gki_6_1)
        adapted_bundle = plan.apply_to_bundle(self.bundle_gki_6_1)

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
        self.assertNotEqual(adapted_bundle.identity, self.bundle_gki_6_1.identity)
        self.assertTrue(adapted_bundle.verify_file("fs/exec.c", exec_file.content))

    def test_individual_fixture_adaptation(self):
        # Test adapt_fixture for each fixture separately
        scope_ops = self.adapter_gki_6_1.adapt_fixture(self.bundle_gki_6_1, FIXED_FIXTURES[0])
        self.assertEqual(len(scope_ops), 7)

        sec_ops = self.adapter_gki_6_1.adapt_fixture(self.bundle_gki_6_1, FIXED_FIXTURES[1])
        self.assertEqual(len(sec_ops), 6)


if __name__ == "__main__":
    unittest.main()
