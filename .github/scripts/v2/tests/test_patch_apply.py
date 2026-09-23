import unittest

from v2.source.bundle import create_source_bundle
from v2.source.patch_apply import SourceBundlePatchError, apply_patch_to_bundle


def patch(hunks):
    return "diff --git a/a b/a\n--- a/a\n+++ b/a\n" + "".join(hunks)


class PatchApplyTests(unittest.TestCase):
    def apply(self, source, text):
        bundle = create_source_bundle("xxksu", "6.1", {"a": source})
        return apply_patch_to_bundle(bundle, text).get_file("a").content

    def test_multiple_hunks_one_file(self):
        text = patch((
            "@@ -1,2 +1,2 @@\n a\n-b\n+B\n",
            "@@ -4,2 +4,2 @@\n d\n-e\n+E\n",
        ))
        self.assertEqual(self.apply("a\nb\nc\nd\ne\nf\n", text), "a\nB\nc\nd\nE\nf\n")

    def test_earlier_insertion_does_not_shift_later_old_hunk(self):
        text = patch((
            "@@ -1 +1,2 @@\n a\n+x\n",
            "@@ -3 +4 @@\n-c\n+C\n",
        ))
        self.assertEqual(self.apply("a\nb\nc\n", text), "a\nx\nb\nC\n")

    def test_earlier_deletion_does_not_shift_later_old_hunk(self):
        text = patch((
            "@@ -1,2 +1 @@\n-a\n-b\n+A\n",
            "@@ -4 +3 @@\n-d\n+D\n",
        ))
        self.assertEqual(self.apply("a\nb\nc\nd\n", text), "A\nc\nD\n")

    def test_context_mismatch_fails_closed(self):
        with self.assertRaises(SourceBundlePatchError):
            self.apply("a\nb\n", patch(("@@ -1 +1 @@\n-x\n+y\n",)))

    def test_overlapping_or_out_of_order_hunks_fail_closed(self):
        with self.assertRaises(SourceBundlePatchError):
            self.apply("a\nb\nc\n", patch((
                "@@ -2 +2 @@\n-b\n+B\n",
                "@@ -1 +1 @@\n-a\n+A\n",
            )))
        with self.assertRaises(SourceBundlePatchError):
            self.apply("a\nb\nc\n", patch((
                "@@ -1,2 +1,2 @@\n a\n-b\n+B\n",
                "@@ -2 +2 @@\n-b\n+C\n",
            )))

    def test_output_is_deterministic(self):
        text = patch(("@@ -2 +2 @@\n-b\n+B\n",))
        self.assertEqual(self.apply("a\nb\nc\n", text), self.apply("a\nb\nc\n", text))


if __name__ == "__main__":
    unittest.main()
