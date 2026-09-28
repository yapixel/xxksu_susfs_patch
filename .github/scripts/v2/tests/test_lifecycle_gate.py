from pathlib import Path
import hashlib
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]


class LifecycleGateTests(unittest.TestCase):

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
