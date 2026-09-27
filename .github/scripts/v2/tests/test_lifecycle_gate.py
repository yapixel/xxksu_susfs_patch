from pathlib import Path
import hashlib
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from v2.pipeline import generate_candidate_patch
from v2.validation.reference_cross_check import (
    compare_patch_to_reference, fetch_reference_url, DEFAULT_MIDORI_CONVERSION_SCRIPT_URL,
    DEFAULT_MIDORI_GKI_PATCH_50_URL, DEFAULT_MIDORI_XX_PATCH_URL,
    ReferenceComparisonClassification as Classification,
)

ROOT = Path(__file__).resolve().parents[4]
PATCH_ID = "gki-android16-6.12-r38-patch51"


class LifecycleGateTests(unittest.TestCase):
    def test_exact_reviewed_pair_and_same_symbol_mutations(self):
        ours = generate_candidate_patch(PATCH_ID, ROOT / ".github/fixtures/r38", ROOT)
        ref = (ROOT / ".github/fixtures/midori/r38-reference51.patch").read_text()
        self.assertEqual(hashlib.sha256(ref.encode()).hexdigest(),
                         "8fc7905d5c8d804191a4d3c29f75409ea69924fa18f0eda038f7b45f102d7fd6")
        result = compare_patch_to_reference(PATCH_ID, ours, ref, "pinned Midori")
        self.assertTrue(result.passed)
        self.assertFalse(result.blocks_promotion)
        self.assertEqual(len(result.metadata["reviewed_lifecycle_differences"]), 3)
        for old, new in (("+\t\tnd->name = old_name;", "+\t\told_name = nd->name;"),
                         ("+\tif (!is_mnt_ksu_unshared)", "+\tif (is_mnt_ksu_unshared)"),
                         ("+\t\tstart = next;", "+\t\tstart = end;")):
            self.assertIn(old, ours)
            result = compare_patch_to_reference(PATCH_ID, ours.replace(old, new), ref, "pinned Midori")
            self.assertEqual(result.classification, Classification.REVIEW_REQUIRED)
            self.assertTrue(result.blocks_promotion)
            self.assertFalse(result.passed)
        old_production = next((ROOT / ".github/fixtures/r38").glob("51_*.patch")).read_text()
        self.assertTrue(compare_patch_to_reference(PATCH_ID, old_production, ref, "pinned Midori").blocks_promotion)

    def test_reference_urls_are_commit_pinned_and_wrong_bytes_fail(self):
        for url in (DEFAULT_MIDORI_XX_PATCH_URL, DEFAULT_MIDORI_GKI_PATCH_50_URL,
                    DEFAULT_MIDORI_CONVERSION_SCRIPT_URL):
            self.assertNotIn("/main/", url)
            self.assertNotIn("/xx.patch", url)
            with patch("urllib.request.urlopen") as mocked:
                mocked.return_value.__enter__.return_value.read.return_value = b"untrusted replacement"
                with self.assertRaisesRegex(ValueError, "hash mismatch"):
                    fetch_reference_url(url)

    def test_archive_authentication_precedes_extraction_and_fails_closed(self):
        workflow = (ROOT / ".github/workflows/generate-51-kernel-patches.yml").read_text()
        start = workflow.index("          archive_url=")
        end = workflow.index("\n\n", start)
        commands = "\n".join(line[10:] for line in workflow[start:end].splitlines())
        self.assertLess(commands.index("sha256sum --check --strict"), commands.index("tar -xzf"))
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            # Execute the workflow's exact authentication/extraction commands
            # with local curl/tar stubs; a mismatched download must never reach tar.
            fixtures = tmp / ".github/fixtures/v2"
            fixtures.mkdir(parents=True)
            (fixtures / "r38-sources.json").write_text(json.dumps({
                "archive_url": "https://invalid.test/archive", "archive_sha256": "0" * 64}))
            script = ('set -euo pipefail\n'
                      'curl() { printf corrupt > r38-source.tar.gz; }\n'
                      'tar() { touch EXTRACTED; }\n' + commands)
            result = subprocess.run(["bash", "-c", script], cwd=tmp, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((tmp / "EXTRACTED").exists())
