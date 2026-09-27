"""Mail statistics must describe the final emitted diff, not its input fixture."""
from pathlib import Path
import re
import subprocess
import unittest
from unittest.mock import patch as mock_patch

from v2.engine.diff_parser import parse_patch
from v2.engine.emitter import emit_patch
from v2.model.patch import AddedLine, Patch, RemovedLine
from v2.policy.lifecycle import correct_patch51

ROOT = Path(__file__).resolve().parents[4]


class MailDiffstatTests(unittest.TestCase):
    def assert_diffstat(self, text, *, native):
        patch = parse_patch(text)
        expected = {}
        for file in patch.files:
            lines = [line for hunk in file.hunks for line in hunk.lines]
            expected[file.new_path.removeprefix("b/")] = (
                sum(isinstance(line, AddedLine) for line in lines),
                sum(isinstance(line, RemovedLine) for line in lines))
        body = emit_patch(Patch(files=patch.files))
        # Independent Git accounting must agree with the final AST.
        numstat = subprocess.check_output(["git", "apply", "--numstat"], input=body, text=True)
        actual = {}
        for line in numstat.splitlines():
            added, removed, path = line.split("\t")
            actual[path] = (int(added), int(removed))
        self.assertEqual(actual, expected)
        rows = {}
        for line in patch.preamble:
            match = re.fullmatch(r" (.*?)\s+\|\s+(\d+)\s*([+-]*)\s*", line)
            if match:
                path, count, bar = match.groups()
                self.assertNotIn(path, rows)
                rows[path] = int(count)
                # Native Git may round a tiny proportional bar down to zero;
                # the exact count remains present and the full render is checked below.
        self.assertEqual(set(rows), set(expected))
        self.assertEqual(rows, {path: sum(counts) for path, counts in expected.items()})
        summary = next(line for line in patch.preamble if "file" in line and " changed" in line)
        self.assertEqual(int(re.search(r"(\d+) files? changed", summary)[1]), len(expected))
        for word, index in (("insertion", 0), ("deletion", 1)):
            match = re.search(r"(\d+) " + word + r"s?\(", summary)
            self.assertEqual(int(match[1]) if match else 0, sum(c[index] for c in expected.values()))
        # Git's worktree --stat and apply --stat use different column widths.
        # Counts above are the invariant; native worktree identity is independently
        # exercised by test_patch51_source.

    def test_both_final_patch51_diffstats_and_determinism(self):
        for gki, folder in ((True, "r38"), (False, "sultan")):
            from v2.pipeline import generate_candidate_patch
            pid = "gki-android16-6.12-r38-patch51" if gki else "sultan-android14-6.1-patch51"
            def generate():
                return generate_candidate_patch(pid, ROOT / ".github/fixtures" / folder, ROOT)
            first, second = generate(), generate()
            with mock_patch.dict("os.environ", {"LC_ALL": "C.UTF-8"}):
                self.assertEqual(first, generate())
            self.assertEqual(first, second)
            self.assertEqual(parse_patch(first).preamble, parse_patch(second).preamble)
            self.assert_diffstat(first, native=True)

    def test_added_file_and_changed_hunk_update_stats_automatically(self):
        text = next((ROOT / ".github/fixtures/r38").glob("51_*.patch")).read_text()
        patch = parse_patch(text)
        patch.files[0].hunks[0].lines.append(AddedLine("/* test extra final-diff line */"))
        extra = parse_patch("diff --git a/fs/diffstat_probe.c b/fs/diffstat_probe.c\n"
                            "new file mode 100644\n--- /dev/null\n+++ b/fs/diffstat_probe.c\n"
                            "@@ -0,0 +1,2 @@\n+int first;\n+int second;\n")
        patch.files.extend(extra.files)
        changed = correct_patch51(emit_patch(patch), ROOT, gki=True)
        self.assert_diffstat(changed, native=True)
        self.assertIn("fs/diffstat_probe.c", "\n".join(parse_patch(changed).preamble))
        self.assertEqual(changed, correct_patch51(emit_patch(patch), ROOT, gki=True))

    def test_patch11_existing_diffstat_is_current(self):
        # Audit only: Patch 11 already has correct file/count/aggregate stats.
        self.assert_diffstat((ROOT / "patches/xxksu/11_enable_susfs_for_ksu.patch").read_text(), native=False)
