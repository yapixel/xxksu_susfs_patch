"""Unit tests for V2.5 deterministic source bundle identity and strict anchor mechanics."""

import json
import unittest

from v2.adapters import (
    AdapterError,
    AmbiguousSemanticMatch,
    AnchorLocation,
    AnchorSpec,
    SultanAndroid14_6_1Adapter,
    GKIAndroid16_6_12Adapter,
    MissingSemanticAnchor,
    MultipleSemanticAnchors,
    SultanAndroid14_6_1Adapter,
    TargetAdapter,
    UnsupportedKernelVersion as AdapterUnsupportedKernelVersion,
    UnsupportedTarget as AdapterUnsupportedTarget,
    get_adapter,
)
from v2.source.bundle import (
    CorruptedSourceBundle,
    DuplicateBundleFile,
    MissingBundleFile,
    SourceBundle,
    SourceBundleError,
    SourceBundleFile,
    UnsupportedBundleSchema,
    UnsupportedKernelVersion,
    UnsupportedTarget,
    create_source_bundle,
    load_source_bundle,
)


_C_SAMPLE_EXEC = """/* fs/exec.c sample */
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

static int other_func(void)
{
	int retval = 0;
	if (IS_ERR(filename))
		return -1;
	return retval;
}
"""

_C_SAMPLE_OPEN = """/* fs/open.c sample */
#include <linux/fs.h>

SYSCALL_DEFINE3(faccessat, int, dfd, const char __user *, filename, int, mode)
{
	return do_faccessat(dfd, filename, mode, 0);
}
"""

_C_SAMPLE_NAMESPACE_GKI = """/* fs/namespace.c GKI 6.1 sample */
#include "pnode.h"
#include "internal.h"
#include <trace/hooks/blk.h>

static void mnt_add_count(struct mount *mnt, int n)
{
}
"""

_C_SAMPLE_NAMESPACE_SULTAN = """/* fs/namespace.c Sultan sample */
#include "pnode.h"
#include "internal.h"

int path_umount(struct path *path, int flags)
{
	return 0;
}
"""

_C_SAMPLE_STAT_6_12 = """/* fs/stat.c Linux 6.12 sample */
int vfs_statx(int dfd, struct filename *filename, int flags,
	      struct kstat *stat, u32 request_mask)
{
	struct mnt_idmap *idmap;

	idmap = mnt_idmap(path.mnt);
	return 0;
}
"""

_C_SAMPLE_STAT_6_1 = """/* fs/stat.c Linux 6.1 sample */
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
"""


class TestV25SourceBundle(unittest.TestCase):

    def test_source_bundle_deterministic_identity(self):
        files_a = {
            "fs/exec.c": _C_SAMPLE_EXEC,
            "fs/open.c": _C_SAMPLE_OPEN,
        }
        files_b = {
            "fs/open.c": _C_SAMPLE_OPEN,
            "fs/exec.c": _C_SAMPLE_EXEC,
        }
        bundle_a = create_source_bundle("sultan-android14-6.1", "6.1.25", files_a)
        bundle_b = create_source_bundle("sultan-android14-6.1", "6.1.25", files_b)

        self.assertEqual(bundle_a.identity, bundle_b.identity)
        self.assertEqual(bundle_a.canonical_json(), bundle_b.canonical_json())
        self.assertTrue(str(bundle_a.identity).startswith("sha256:"))

    def test_source_bundle_differing_inputs_different_identity(self):
        bundle1 = create_source_bundle("sultan-android14-6.1", "6.1.25", {"fs/open.c": _C_SAMPLE_OPEN})
        bundle2 = create_source_bundle("sultan-android14-6.1", "6.1.68", {"fs/open.c": _C_SAMPLE_OPEN})
        bundle3 = create_source_bundle("gki-android16-6.12", "6.12.0", {"fs/open.c": _C_SAMPLE_OPEN})
        bundle4 = create_source_bundle("sultan-android14-6.1", "6.1.25", {"fs/open.c": "/* different */"})

        self.assertNotEqual(bundle1.identity, bundle2.identity)
        self.assertNotEqual(bundle1.identity, bundle3.identity)
        self.assertNotEqual(bundle1.identity, bundle4.identity)

    def test_source_bundle_target_validation(self):
        with self.assertRaises(UnsupportedTarget):
            create_source_bundle("invalid-target", "6.1", {"fs/open.c": "code"})

    def test_source_bundle_kernel_version_validation(self):
        # 6.12 on 6.1 target
        with self.assertRaises(UnsupportedKernelVersion):
            create_source_bundle("sultan-android14-6.1", "6.12.0", {"fs/open.c": "code"})
        # 6.1 on 6.12 target
        with self.assertRaises(UnsupportedKernelVersion):
            create_source_bundle("gki-android16-6.12", "6.1.25", {"fs/open.c": "code"})
        # Empty version
        with self.assertRaises(UnsupportedKernelVersion):
            create_source_bundle("sultan-android14-6.1", "", {"fs/open.c": "code"})

    def test_source_bundle_schema_validation(self):
        bundle = create_source_bundle("sultan-android14-6.1", "6.1.25", {"fs/open.c": "code"})
        with self.assertRaises(UnsupportedBundleSchema):
            SourceBundle(
                target_id="sultan-android14-6.1",
                kernel_version="6.1.25",
                files=bundle.files,
                schema="invalid-schema/v2",
            )

    def test_source_bundle_corrupted_file_detected(self):
        bundle = create_source_bundle("sultan-android14-6.1", "6.1.25", {"fs/open.c": "real content"})
        real_file = bundle.files[0]
        # Hash mismatch
        with self.assertRaises(CorruptedSourceBundle):
            SourceBundleFile(
                path=real_file.path,
                content_hash=real_file.content_hash,
                size=real_file.size,
                content="tampered content with same length!",
            )
        # Size mismatch
        with self.assertRaises(CorruptedSourceBundle):
            SourceBundleFile(
                path=real_file.path,
                content_hash=real_file.content_hash,
                size=real_file.size + 10,
                content="real content",
            )

    def test_source_bundle_file_lookup_and_verification(self):
        bundle = create_source_bundle("sultan-android14-6.1", "6.1.25", {
            "fs/open.c": _C_SAMPLE_OPEN,
            "fs/exec.c": _C_SAMPLE_EXEC,
        })
        self.assertTrue(bundle.has_file("fs/open.c"))
        self.assertTrue(bundle.has_file("fs/exec.c"))
        self.assertFalse(bundle.has_file("fs/stat.c"))

        f = bundle.get_file("fs/open.c")
        self.assertEqual(f.path, "fs/open.c")
        self.assertEqual(f.content, _C_SAMPLE_OPEN)

        with self.assertRaises(MissingBundleFile):
            bundle.get_file("fs/stat.c")

        self.assertTrue(bundle.verify_file("fs/open.c", _C_SAMPLE_OPEN))
        with self.assertRaises(CorruptedSourceBundle):
            bundle.verify_file("fs/open.c", "modified content")

    def test_source_bundle_duplicate_file_rejected(self):
        bundle = create_source_bundle("sultan-android14-6.1", "6.1.25", {"fs/open.c": "content"})
        f = bundle.files[0]
        with self.assertRaises(DuplicateBundleFile):
            SourceBundle("sultan-android14-6.1", "6.1.25", (f, f))

    def test_source_bundle_path_escaping_rejected(self):
        with self.assertRaises(ValueError):
            create_source_bundle("sultan-android14-6.1", "6.1.25", {"../escape.c": "content"})

    def test_source_bundle_json_roundtrip(self):
        bundle = create_source_bundle(
            "sultan-android14-6.1", "6.1.25",
            {"fs/open.c": _C_SAMPLE_OPEN, "fs/exec.c": _C_SAMPLE_EXEC},
            metadata={"builder": "test"},
        )
        serialized = bundle.canonical_json()
        restored = load_source_bundle(serialized)

        self.assertEqual(bundle.identity, restored.identity)
        self.assertEqual(bundle.target_id, restored.target_id)
        self.assertEqual(bundle.kernel_version, restored.kernel_version)
        self.assertEqual(bundle.file_paths, restored.file_paths)
        self.assertEqual(bundle.metadata, restored.metadata)


class TestV25TargetAdapters(unittest.TestCase):

    def test_adapter_factory_and_identification(self):
        a1 = get_adapter("sultan-android14-6.1")
        self.assertIsInstance(a1, SultanAndroid14_6_1Adapter)
        self.assertEqual(a1.target_id, "sultan-android14-6.1")
        self.assertEqual(a1.adapter_id, "sultan_android14_6_1")

        a2 = get_adapter("gki-android16-6.12")
        self.assertIsInstance(a2, GKIAndroid16_6_12Adapter)
        self.assertEqual(a2.target_id, "gki-android16-6.12")
        self.assertEqual(a2.adapter_id, "gki_android16_6_12")

        a3 = get_adapter("sultan-android14-6.1")
        self.assertIsInstance(a3, SultanAndroid14_6_1Adapter)
        self.assertEqual(a3.target_id, "sultan-android14-6.1")
        self.assertEqual(a3.adapter_id, "sultan_android14_6_1")

        with self.assertRaises(AdapterUnsupportedTarget):
            get_adapter("unknown-target")

    def test_adapter_version_validation(self):
        a1 = get_adapter("sultan-android14-6.1")
        a1.validate_kernel_version("6.1")
        a1.validate_kernel_version("6.1.25")
        a1.validate_kernel_version("6.1-android14")
        with self.assertRaises(AdapterUnsupportedKernelVersion):
            a1.validate_kernel_version("6.12.0")
        with self.assertRaises(AdapterUnsupportedKernelVersion):
            a1.validate_kernel_version("5.15.0")

        a2 = get_adapter("gki-android16-6.12")
        a2.validate_kernel_version("6.12")
        a2.validate_kernel_version("6.12.5")
        with self.assertRaises(AdapterUnsupportedKernelVersion):
            a2.validate_kernel_version("6.1.25")


class TestV25AnchorMechanics(unittest.TestCase):

    def setUp(self):
        self.adapter_gki_6_1 = get_adapter("gki-android16-6.12")
        self.adapter_gki_6_12 = get_adapter("gki-android16-6.12")
        self.adapter_sultan = get_adapter("sultan-android14-6.1")

    def test_locate_anchor_exact_match(self):
        loc = self.adapter_gki_6_1.locate_anchor(
            _C_SAMPLE_OPEN,
            "return do_faccessat(dfd, filename, mode, 0);",
            file_path="fs/open.c",
        )
        self.assertEqual(loc.file_path, "fs/open.c")
        self.assertEqual(loc.line_number, 6)
        self.assertEqual(loc.matched_text, "return do_faccessat(dfd, filename, mode, 0);")

    def test_locate_anchor_missing_fails_closed(self):
        with self.assertRaises(MissingSemanticAnchor):
            self.adapter_gki_6_1.locate_anchor(
                _C_SAMPLE_OPEN,
                "non_existent_anchor_call();",
                file_path="fs/open.c",
            )

    def test_locate_anchor_ambiguous_without_function_fails_closed(self):
        # 'if (IS_ERR(filename))' appears twice in _C_SAMPLE_EXEC
        with self.assertRaises(MultipleSemanticAnchors):
            self.adapter_gki_6_1.locate_anchor(
                _C_SAMPLE_EXEC,
                "if (IS_ERR(filename))",
                file_path="fs/exec.c",
            )

    def test_locate_anchor_in_function_disambiguates(self):
        # Function-scoped search locates the unique match inside do_execveat_common
        loc = self.adapter_gki_6_1.locate_anchor(
            _C_SAMPLE_EXEC,
            "if (IS_ERR(filename))",
            file_path="fs/exec.c",
            function="do_execveat_common",
        )
        self.assertEqual(loc.function, "do_execveat_common")
        self.assertEqual(loc.line_number, 12)

        # And locates inside other_func
        loc2 = self.adapter_gki_6_1.locate_anchor(
            _C_SAMPLE_EXEC,
            "if (IS_ERR(filename))",
            file_path="fs/exec.c",
            function="other_func",
        )
        self.assertEqual(loc2.function, "other_func")
        self.assertEqual(loc2.line_number, 21)

    def test_locate_anchor_missing_function_fails_closed(self):
        with self.assertRaises(MissingSemanticAnchor):
            self.adapter_gki_6_1.locate_anchor(
                _C_SAMPLE_EXEC,
                "if (IS_ERR(filename))",
                file_path="fs/exec.c",
                function="non_existent_function",
            )

    def test_locate_anchor_with_context(self):
        spec = AnchorSpec(
            file_path="fs/exec.c",
            anchor_text="if (IS_ERR(filename))",
            function="do_execveat_common",
            context_before=("int retval;",),
            context_after=("return PTR_ERR(filename);",),
        )
        loc = self.adapter_gki_6_1.locate_anchor(_C_SAMPLE_EXEC, spec)
        self.assertEqual(loc.line_number, 12)

    def test_target_anchor_difference_gki_vs_sultan_namespace(self):
        gki_spec = self.adapter_gki_6_1.get_anchor_spec("namespace_include")
        sultan_spec = self.adapter_sultan.get_anchor_spec("namespace_include")

        # GKI anchor succeeds on GKI namespace source
        loc_gki = self.adapter_gki_6_1.locate_anchor(_C_SAMPLE_NAMESPACE_GKI, gki_spec)
        self.assertEqual(loc_gki.line_number, 3)

        loc_sultan_on_gki = self.adapter_gki_6_1.locate_anchor(_C_SAMPLE_NAMESPACE_SULTAN, gki_spec)
        self.assertEqual(loc_sultan_on_gki.line_number, 3)

        # Sultan anchor succeeds on Sultan namespace source
        loc_sultan = self.adapter_sultan.locate_anchor(_C_SAMPLE_NAMESPACE_SULTAN, sultan_spec)
        self.assertEqual(loc_sultan.line_number, 3)

    def test_target_anchor_difference_6_1_vs_6_12_stat(self):
        stat_6_12_spec = self.adapter_gki_6_12.get_anchor_spec("stat_idmap")

        # 6.12 idmap anchor succeeds on 6.12 source
        loc = self.adapter_gki_6_12.locate_anchor(_C_SAMPLE_STAT_6_12, stat_idmap_hook := stat_6_12_spec)
        self.assertEqual(loc.line_number, 7)

        # 6.12 idmap anchor fails on 6.1 source
        with self.assertRaises(MissingSemanticAnchor):
            self.adapter_gki_6_12.locate_anchor(_C_SAMPLE_STAT_6_1, stat_6_12_spec)

    def test_adapter_locate_anchor_in_bundle(self):
        bundle = create_source_bundle("gki-android16-6.12", "6.12.0", {
            "fs/open.c": _C_SAMPLE_OPEN,
            "fs/exec.c": _C_SAMPLE_EXEC,
        })
        spec = AnchorSpec(
            file_path="fs/open.c",
            anchor_text="return do_faccessat(dfd, filename, mode, 0);",
            function="faccessat",
        )
        loc = self.adapter_gki_6_1.locate_anchor_in_bundle(bundle, spec)
        self.assertEqual(loc.line_number, 6)

        # Bundle target mismatch
        wrong_bundle = create_source_bundle("sultan-android14-6.1", "6.1.25", {
            "fs/open.c": _C_SAMPLE_OPEN,
        })
        with self.assertRaises(AdapterUnsupportedTarget):
            self.adapter_gki_6_1.locate_anchor_in_bundle(wrong_bundle, spec)

        # Missing file in bundle
        missing_spec = AnchorSpec(file_path="fs/missing.c", anchor_text="foo")
        with self.assertRaises(MissingBundleFile):
            self.adapter_gki_6_1.locate_anchor_in_bundle(bundle, missing_spec)


if __name__ == "__main__":
    unittest.main()
