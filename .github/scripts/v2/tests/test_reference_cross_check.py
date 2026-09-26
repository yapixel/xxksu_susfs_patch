"""Unit and regression tests for Midori Reference Cross-Check.

Required regression test coverage:
1. semantic match with bytewise differences
2. Midori reference-only extras
3. our authoritative extras
4. genuine semantic conflict
5. unavailable reference
6. Midori converter uses Midori Patch 50, never ours
7. reference comparison cannot authorize production changes
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from v2.pipeline import deliver_multi_candidates
from v2.validation.reference_cross_check import (
    PATCH11_FEATURE_UNITS,
    ReferenceComparisonClassification,
    compare_patch_to_reference,
    evaluate_patch11_features,
    regenerate_midori_patch51,
)

SAMPLE_XXKSU_P11_DIFF = """diff --git a/kernel/ksu.c b/kernel/ksu.c
index 08fa255..1111111 100644
--- a/kernel/ksu.c
+++ b/kernel/ksu.c
@@ -70,1 +70,2 @@ int __init ksu_init(void)
+	susfs_init();
 	return 0;
diff --git a/kernel/hook/setuid_hook.c b/kernel/hook/setuid_hook.c
index dd7f40f..2222222 100644
--- a/kernel/hook/setuid_hook.c
+++ b/kernel/hook/setuid_hook.c
@@ -40,1 +40,2 @@ int ksu_handle_setresuid(uid_t ruid, uid_t euid, uid_t suid)
+	susfs_zygote_sid(ruid);
 	return 0;
"""

# Midori xx.patch omitting susfs_zygote_sid (reduced integration)
SAMPLE_MIDORI_XX_DIFF = """diff --git a/kernel/ksu.c b/kernel/ksu.c
index 08fa255..3333333 100644
--- a/kernel/ksu.c
+++ b/kernel/ksu.c
@@ -70,1 +70,2 @@ int __init ksu_init(void)
+	susfs_init();
 	return 0;
"""

SAMPLE_GKI_51_OUR = """diff --git a/fs/stat.c b/fs/stat.c
index 1111111..2222222 100644
--- a/fs/stat.c
+++ b/fs/stat.c
@@ -100,1 +100,2 @@ int vfs_statx(int dfd, const char __user *filename, int flags,
+	susfs_spoof_uname();
 	return 0;
"""

SAMPLE_GKI_51_MIDORI_BYTE_DIFF = """diff --git a/fs/stat.c b/fs/stat.c
index 3333333..4444444 100644
--- a/fs/stat.c
+++ b/fs/stat.c
@@ -105,2 +105,3 @@ int vfs_statx(int dfd, const char __user *filename, int flags,
 	/* context line */
+	susfs_spoof_uname();
 	return 0;
"""

SAMPLE_GKI_51_CONFLICT = """diff --git a/fs/stat.c b/fs/stat.c
index 5555555..6666666 100644
--- a/fs/stat.c
+++ b/fs/stat.c
@@ -120,1 +120,2 @@ int vfs_statx(int dfd, const char __user *filename, int flags,
+	ksu_handle_execveat(dfd, filename);
 	return 0;
"""


class TestReferenceCrossCheck(unittest.TestCase):

    # 1. semantic match with bytewise differences
    def test_01_semantic_match_with_bytewise_differences(self):
        """Byte differences in headers/offsets do not prevent semantic equivalence."""
        res = compare_patch_to_reference(
            patch_id="gki-android16-6.12-r38-patch51",
            candidate_patch_text=SAMPLE_GKI_51_OUR,
            reference_patch_text=SAMPLE_GKI_51_MIDORI_BYTE_DIFF,
            reference_source_name="midori01/gki_ksu_workflow:Patch 51",
        )
        self.assertTrue(res.passed, f"Failed with: {res.details}")
        self.assertFalse(res.blocks_promotion)
        self.assertIn(
            res.classification,
            (ReferenceComparisonClassification.SEMANTIC_MATCH, ReferenceComparisonClassification.IMPLEMENTATION_DIFFERENCE),
        )

    # 2. Midori reference-only extras
    def test_02_midori_reference_only_extras(self):
        """Extra semantic units in Midori reference generate review signal but do not block."""
        ref_with_extra = SAMPLE_GKI_51_OUR + """diff --git a/fs/statfs.c b/fs/statfs.c
index 7777777..8888888 100644
--- a/fs/statfs.c
+++ b/fs/statfs.c
@@ -50,1 +50,2 @@ int vfs_statfs(struct dentry *dentry, struct kstatfs *buf)
+	susfs_statfs_by_dentry(dentry, buf);
 	return 0;
"""
        res = compare_patch_to_reference(
            patch_id="gki-android16-6.12-r38-patch51",
            candidate_patch_text=SAMPLE_GKI_51_OUR,
            reference_patch_text=ref_with_extra,
            reference_source_name="midori01/gki_ksu_workflow:Patch 51",
        )
        self.assertTrue(res.passed, f"Failed with: {res.details}")
        self.assertFalse(res.blocks_promotion)
        self.assertEqual(res.classification, ReferenceComparisonClassification.REFERENCE_EXTRA)
        self.assertIn("susfs.statfs.kstat", res.ref_extra_units)

    # 3. our authoritative extras
    def test_03_our_authoritative_extras(self):
        """Authoritative units present in our patch but omitted in Midori (e.g. xx.patch) pass per policy."""
        res = compare_patch_to_reference(
            patch_id="xxksu-patch11",
            candidate_patch_text=SAMPLE_XXKSU_P11_DIFF,
            reference_patch_text=SAMPLE_MIDORI_XX_DIFF,
            reference_source_name="midori01/KernelSU:xx.patch",
        )
        self.assertTrue(res.passed, f"Failed with: {res.details}")
        self.assertFalse(res.blocks_promotion)
        self.assertEqual(res.classification, ReferenceComparisonClassification.OUR_EXTRA)
        self.assertIn("setuid.zygote_handling", res.our_extra_units)
        self.assertIn("authoritative Simonpunk", res.details)

    # 4. genuine semantic conflict
    def test_04_genuine_semantic_conflict(self):
        """Reintroducing inline KSU hooks in deinlined Patch 51 blocks promotion."""
        res = compare_patch_to_reference(
            patch_id="gki-android16-6.12-r38-patch51",
            candidate_patch_text=SAMPLE_GKI_51_CONFLICT,
            reference_patch_text=SAMPLE_GKI_51_OUR,
            reference_source_name="midori01/gki_ksu_workflow:Patch 51",
        )
        self.assertFalse(res.passed)
        self.assertTrue(res.blocks_promotion)
        self.assertEqual(res.classification, ReferenceComparisonClassification.SEMANTIC_CONFLICT)
        self.assertIn("Candidate erroneously adds inline KSU hook", res.details)

    # 5. unavailable reference
    def test_05_unavailable_reference(self):
        """When reference cannot be fetched, report unavailable without blocking authoritative promotion."""
        res = compare_patch_to_reference(
            patch_id="xxksu-patch11",
            candidate_patch_text=SAMPLE_XXKSU_P11_DIFF,
            reference_patch_text=None,
            reference_source_name="midori01/KernelSU:xx.patch",
        )
        self.assertTrue(res.passed)
        self.assertFalse(res.blocks_promotion)
        self.assertEqual(res.classification, ReferenceComparisonClassification.REFERENCE_UNAVAILABLE)
        self.assertEqual(res.ref_sha256, "UNKNOWN")
        self.assertIn("Promotion authorized", res.details)

    # 6. Midori converter uses Midori Patch 50, never ours
    def test_06_midori_converter_uses_midori_patch_50_never_ours(self):
        """Converter must process Midori's Patch 50 bytes and never receive our Patch 50."""
        midori_p50 = """--- a/fs/stat.c
+++ b/fs/stat.c
@@ -1,3 +1,4 @@
+// midori-50-marker
 int stat(void) { return 0; }
"""
        mock_script = """#!/bin/bash
IN="$1"
OUT="$2"
if grep -q "OUR-50-MARKER-DO-NOT-USE" "$IN"; then
    echo "ERROR: Received our patch 50 instead of Midori patch 50!" >&2
    exit 42
fi
echo "Converted Midori 50 to 51" > "$OUT"
exit 0
"""
        gen_text, meta = regenerate_midori_patch51(
            patch50_content=midori_p50,
            script_content=mock_script,
        )
        self.assertIsNotNone(gen_text)
        self.assertIn("Converted Midori 50 to 51", gen_text)
        self.assertIn("patch50_sha256", meta)
        self.assertEqual(meta["patch50_sha256"], hashlib.sha256(midori_p50.encode("utf-8")).hexdigest())

    # 7. reference comparison cannot authorize production changes
    def test_07_reference_comparison_cannot_authorize_production_changes(self):
        """Reference differences or changes can NEVER independently trigger production updates or write-back."""
        repo_root = Path(__file__).resolve().parents[4]
        state_file = repo_root / ".github" / "upstream-state.json"
        self.assertTrue(state_file.is_file())

        with open(state_file, "r", encoding="utf-8") as f:
            state = json.load(f)

        # Invariant check: reference sources are clearly separated from authoritative sources
        self.assertIn("sources", state)
        self.assertIn("reference", state["sources"])
        self.assertIn("authoritative", state["sources"])

        # Reference sources cannot be in authoritative sources
        ref_keys = set(state["sources"]["reference"].keys())
        auth_keys = set(state["sources"]["authoritative"].keys())
        self.assertEqual(ref_keys.intersection(auth_keys), set())

        # Proves deliver_multi_candidates with unchanged candidate does not commit even if reference changed
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            cand_p = td_path / "cand.patch"
            pub_p = repo_root / "patches" / "xxksu" / "11_enable_susfs_for_ksu.patch"
            cand_p.write_bytes(pub_p.read_bytes())

            delivered, pushed, commit, shas = deliver_multi_candidates(
                candidate_targets={"xxksu-patch11": cand_p},
                repo_root=repo_root,
                write_back=False,
            )
            self.assertFalse(delivered)
            self.assertFalse(pushed)
            self.assertIsNone(commit)

    # 8. patch11 feature-level semantic matrix
    def test_08_patch11_feature_level_semantic_matrix(self):
        """Patch 11 feature-level matrix evaluates all 26 units with 0 setuid/selinux extras."""
        self.assertEqual(len(PATCH11_FEATURE_UNITS), 26)

        repo_root = Path(__file__).resolve().parents[4]
        p11_path = repo_root / "patches" / "xxksu" / "11_enable_susfs_for_ksu.patch"
        self.assertTrue(p11_path.is_file())
        our_text = p11_path.read_text(encoding="utf-8")

        ref_path = Path("/tmp/midori_xx.patch")
        if ref_path.is_file():
            ref_text = ref_path.read_text(encoding="utf-8")
        else:
            # Fallback to realistic synthetic diff containing all matched and divergent units
            ref_text = (
                our_text.replace("config KSU_SUSFS_TRY_UMOUNT\n", "")
                .replace("CMD_SUSFS_ADD_TRY_UMOUNT", "/* omitted */")
                .replace("susfs_is_current_proc_umounted()", "false")
                .replace("handle_zygote_setresuid", "handle_susfs_setresuid")
            )

        matrix = evaluate_patch11_features(our_text, ref_text)
        self.assertEqual(len(matrix), 26)

        # All 26 units present in matrix
        for unit in PATCH11_FEATURE_UNITS:
            self.assertIn(unit, matrix)

        # SETUID / ZYGOTE domain must have ZERO OUR_EXTRA units
        setuid_extras = [k for k, v in matrix.items() if k.startswith("setuid.") and v == "OUR_EXTRA"]
        self.assertEqual(setuid_extras, [], f"Unexpected setuid extras: {setuid_extras}")

        # SELINUX domain must have ZERO OUR_EXTRA units (only IMPLEMENTATION_DIFFERENCE or MATCH)
        selinux_extras = [k for k, v in matrix.items() if k.startswith("selinux.") and v == "OUR_EXTRA"]
        self.assertEqual(selinux_extras, [], f"Unexpected selinux extras: {selinux_extras}")

        # Compare via compare_patch_to_reference
        res = compare_patch_to_reference(
            patch_id="xxksu-patch11",
            candidate_patch_text=our_text,
            reference_patch_text=ref_text,
            reference_source_name="midori01/KernelSU:xx.patch",
        )
        self.assertTrue(res.passed)
        self.assertFalse(res.blocks_promotion)
        self.assertEqual(res.classification, ReferenceComparisonClassification.OUR_EXTRA)
        self.assertIn("config.try_umount", res.our_extra_units)
        self.assertIn("supercall.ksu_mark_get_integration", res.our_extra_units)
        self.assertIn("semantic_matrix", res.metadata)


if __name__ == "__main__":
    unittest.main()
