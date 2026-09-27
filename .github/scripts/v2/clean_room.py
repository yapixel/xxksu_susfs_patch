"""Read-only fresh-runner verification. No promotion or delivery entry points."""
from datetime import datetime, timezone
from email.utils import format_datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[3]


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def command(*args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def fetch_git(info, dest):
    dest.mkdir()
    command("git", "init", "-q", str(dest))
    command("git", "-C", str(dest), "remote", "add", "origin", info["repository"])
    commit = info.get("resolved_commit", info.get("commit"))
    command("git", "-C", str(dest), "fetch", "--depth=1", "origin", commit)
    command("git", "-C", str(dest), "checkout", "-q", "--detach", "FETCH_HEAD")
    require(command("git", "-C", str(dest), "rev-parse", "HEAD") == commit,
            f"source identity mismatch: {dest.name}")
    if info.get("tree"):
        require(command("git", "-C", str(dest), "rev-parse", "HEAD^{tree}") == info["tree"],
                f"tree identity mismatch: {dest.name}")
    return dest


def authenticated_archive(binding, archive, target):
    subprocess.run(["curl", "--fail", "--location", "--retry", "3", "--speed-time", "60",
                    "--speed-limit", "1024", binding["archive_url"], "-o", str(archive)], check=True)
    with archive.open("rb") as stream:
        require(hashlib.file_digest(stream, "sha256").hexdigest() == binding["archive_sha256"],
                "r38 archive SHA mismatch")
    target.mkdir()
    subprocess.run(["tar", "-xzf", str(archive), "-C", str(target)], check=True)


def generation_environment(root, dest, baselines):
    """Allowlist only code, input snapshots and metadata; never copy final patches."""
    shutil.copytree(root / ".github/scripts", dest / ".github/scripts",
                    ignore=shutil.ignore_patterns("tests", "__pycache__"))
    paths = [".github/upstream-state.json", ".github/fixtures/v2/r38-sources.json"]
    for target, baseline in baselines.items():
        paths += [f"patches/{target}/BASELINE.json", baseline["source_bundle"]["artifact_path"]]
    for folder, target in (("sultan", "sultan-android14-6.1"), ("r38", "gki-android16-6.12")):
        paths += [f".github/fixtures/{folder}/susfs-source-commit.txt",
                  f".github/fixtures/{folder}/{baselines[target]['susfs']['patch_50']}"]
    for rel in paths:
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / rel, out)


def generate_child(patch_id, source, forbidden_root):
    # The checkout remains available to the comparison/test process, never this
    # generator. Catch accidental Python fallbacks to its outputs as well.
    forbidden = Path(forbidden_root).resolve()
    def audit(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            path = Path(os.fsdecode(args[0])).resolve()
            if path.is_relative_to(forbidden) or path.name.startswith(("11_", "51_")):
                raise RuntimeError(f"generator attempted final-output/checkout read: {path}")
    sys.addaudithook(audit)
    from .pipeline import generate_candidate_patch
    sys.stdout.write(generate_candidate_patch(patch_id, Path(source), ROOT))


def generate_process(env_root, patch_id, source, *, missing=None):
    env = {**os.environ, "PYTHONPATH": str(env_root / ".github/scripts"),
           "GITHUB_WORKSPACE": str(env_root), "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([sys.executable, "-m", "v2.clean_room", "generate",
                             patch_id, str(source), str(ROOT)],
                            cwd=env_root, env=env, capture_output=True)
    if missing:
        require(result.returncode != 0 and missing in result.stderr.decode(),
                f"negative provenance check did not reject {missing}: {result.stderr.decode()}")
        return b""
    require(result.returncode == 0, result.stderr.decode())
    return result.stdout


def run_tests(result_path, focused=False):
    sys.path.insert(0, str(ROOT / ".github/scripts/v2/tests"))
    loader = unittest.defaultTestLoader
    suite = (loader.loadTestsFromNames(["test_lifecycle", "test_generator_regression", "test_mail_diffstat"])
             if focused else loader.discover(str(ROOT / ".github/scripts/v2/tests")))
    started = time.monotonic()
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    report = {"count": result.testsRun, "runtime": round(time.monotonic() - started, 3),
              "failures": len(result.failures), "errors": len(result.errors),
              "skips": [(str(test), reason) for test, reason in result.skipped]}
    Path(result_path).write_text(json.dumps(report))
    return 0 if result.wasSuccessful() and not result.skipped else 1


def repository_state(root):
    tracked = (subprocess.run(["git", "diff", "--exit-code"], cwd=root).returncode == 0
               and subprocess.run(["git", "diff", "--cached", "--exit-code"], cwd=root).returncode == 0)
    # Include ignored files too: bytecode/cache output is not silently tolerated.
    untracked = command("git", "ls-files", "--others", cwd=root).splitlines()
    return {"tracked": "CLEAN" if tracked else "DIRTY", "untracked": untracked}


def summary(report):
    lines = [f"# CLEAN-ROOM: {report['status']}", "", f"HEAD: {report['head']}", ""]
    for name, row in report.get("patches", {}).items():
        lines += [f"## {name}", ""]
        lines += [f"- {key}: {value}" for key, value in row.items()]
        lines.append("")
    tests = report.get("tests", {"count": "NOT_RUN", "runtime": "NOT_RUN",
                                 "failures": "NOT_RUN", "errors": "NOT_RUN", "skips": "NOT_RUN"})
    lines += ["## Tests", "", f"- {json.dumps(tests)}", "", "## Midori", ""]
    lines += [f"- {name}: {value}" for name, value in report.get("midori", {}).items()]
    state = report.get("repository", {})
    lines += ["", "## Repository", "", f"- tracked diff: {state.get('tracked', 'NOT_RUN')}",
              f"- unexpected untracked: {state.get('untracked') or 'NONE'}"]
    if report.get("error"):
        lines += ["", "Failure: " + report["error"].strip().splitlines()[-1][:500]]
    return "\n".join(lines) + "\n"


def verify(work, report):
    from .adapters.xxksu import PATCH11_CANONICAL_FILES
    from .engine.diff_parser import parse_patch
    from .manifests.patch_manifest import verify_patch_manifest
    from .semantic.gate import verify_semantic_gate_for_pipeline
    from .source.baseline import load_baseline_record, load_authoritative_bundle
    from .validation.exact_patch import validate_exact_patch_on_tree
    from .validation.reference_cross_check import run_reference_cross_check

    ok, errors = verify_patch_manifest(ROOT)
    require(ok, str(errors))
    manifest = json.loads((ROOT / "patches/manifest.json").read_text())["patches"]
    baselines = {}
    for entry in manifest:
        target = Path(entry["relative_path"]).parent.name
        path = ROOT / "patches" / target / "BASELINE.json"
        record = load_baseline_record(path)
        require(record.status == "VERIFIED", f"blocked baseline: {target}")
        load_authoritative_bundle(target, ROOT)
        baseline = baselines[target] = json.loads(path.read_text())
        artifact = baseline["patch_11" if target == "xxksu" else "patch_51"]
        require(artifact["patch_file"] == entry["relative_path"] and
                artifact["patch_sha256"].removeprefix("sha256:") == entry["sha256"],
                f"baseline/manifest mismatch: {target}")
        report["patches"][entry["id"]] = {
            "production SHA": sha((ROOT / entry["relative_path"]).read_bytes()),
            "manifest SHA": entry["sha256"], "generated SHA": "NOT_RUN",
            "equality": "NOT_RUN", "reconstruction": "NOT_RUN",
            "exact apply": "NOT_RUN", "target contracts": "NOT_RUN"}
    state = json.loads((ROOT / ".github/upstream-state.json").read_text())["sources"]["authoritative"]
    sources = {}
    for key, target, field in (("backslashxx_kernelsu", "xxksu", "upstream"),
                               ("susfs_sultan", "sultan-android14-6.1", "susfs"),
                               ("susfs_gki", "gki-android16-6.12", "susfs")):
        info = state[key]
        pin = baselines[target][field]
        require(info["commit"] == pin["resolved_commit"] and
                info["repository"].removesuffix(".git") == pin["repository"].removesuffix(".git"),
                f"authoritative identities disagree: {key}")
        tree = sources[target] = fetch_git(info, work / key)
        print(f"Accepted {key}: {info['commit']}", flush=True)
        for rel, expected in info["tracked_files"].items():
            require(sha((tree / rel).read_bytes()) == expected.removeprefix("sha256:"),
                    f"authoritative content mismatch: {key}/{rel}")

    # Independently fetched targets authenticate the source fixtures used by both
    # the generator and target-native C regression harnesses.
    targets = {"xxksu": sources["xxksu"]}
    targets["sultan-android14-6.1"] = fetch_git(
        baselines["sultan-android14-6.1"]["upstream"], work / "sultan-kernel")
    context = json.loads((ROOT / ".github/fixtures/v2/r38-sources.json").read_text())
    binding = baselines["gki-android16-6.12"]["metadata"]["compatibility_patches"]["gki-android16-6.12-r38"]
    require(all(context[k] == binding[k] for k in ("archive_url", "archive_sha256")),
            "r38 archive bindings disagree")
    archive = work / "r38.tar.gz"
    r38 = targets["gki-android16-6.12"] = work / "r38-kernel"
    authenticated_archive(binding, archive, r38)
    report["patches"]["gki-android16-6.12-r38-patch51"]["archive authentication"] = "PASS"
    for rel, entry in context["files"].items():
        require((r38 / rel).read_bytes() == entry["content"].encode() and
                sha((r38 / rel).read_bytes()) == entry["sha256"], f"r38 excerpt mismatch: {rel}")
    for target, folder in (("sultan-android14-6.1", "sultan"), ("gki-android16-6.12", "r38")):
        tree = sources[target]
        for rel in ("fs/susfs.c", "include/linux/susfs.h", "include/linux/susfs_def.h"):
            dest = targets[target] / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(tree / "kernel_patches" / rel, dest)
        name = baselines[target]["susfs"]["patch_50"]
        require((ROOT / ".github/fixtures" / folder / name).read_bytes() ==
                (tree / "kernel_patches" / name).read_bytes(), f"Patch 50 fixture mismatch: {target}")
        commit = subprocess.check_output(["git", "cat-file", "commit", "HEAD"], cwd=tree)
        require(commit == (ROOT / ".github/fixtures" / folder / "susfs-source-commit.txt").read_bytes(),
                f"Date provenance mismatch: {target}")
    for target in ("xxksu", "sultan-android14-6.1"):
        for entry in load_authoritative_bundle(target, ROOT).files:
            require((targets[target] / entry.path).read_bytes() == entry.content.encode(),
                    f"target source fixture mismatch: {target}/{entry.path}")

    contracts = json.loads((ROOT / ".github/fixtures/v2/target-api-contracts.json").read_text())
    for key, target in (("sultan", "sultan-android14-6.1"), ("gki", "gki-android16-6.12")):
        headers = []
        for rel, expected in contracts[key]["source_sha256"].items():
            raw = (targets[target] / rel).read_bytes()
            require(sha(raw) == expected, f"native API header mismatch: {target}/{rel}")
            headers.append(raw.decode())
        for name, excerpt in contracts[key]["excerpts"].items():
            require(any(excerpt in text for text in headers), f"non-native API excerpt: {target}/{name}")

    env_root = work / "generation"
    generation_environment(ROOT, env_root, baselines)
    empty = work / "empty"
    empty.mkdir()
    for entry in manifest:
        patch_id = entry["id"]
        target = Path(entry["relative_path"]).parent.name
        source = sources[target]
        row = report["patches"][patch_id]
        gate = verify_semantic_gate_for_pipeline(patch_id, source, repo_root=env_root)
        require(gate.passed, gate.details)
        first = generate_process(env_root, patch_id, source)
        second = generate_process(env_root, patch_id, source)
        require(first == second, f"nondeterministic generation: {patch_id}")
        row["generated SHA"] = sha(first)
        require(first == (ROOT / entry["relative_path"]).read_bytes() and
                sha(first) == entry["sha256"], f"production reproduction mismatch: {patch_id}")
        row.update({"equality": "PASS", "reconstruction": "PASS", "two-process determinism": "PASS"})
        if target != "xxksu":
            timestamp = int(command("git", "show", "-s", "--format=%ct", "HEAD", cwd=source))
            date = format_datetime(datetime.fromtimestamp(timestamp, timezone.utc))
            require(f"Date: {date}\n".encode() in first, f"noncanonical Date: {patch_id}")
            row["deterministic metadata"] = "PASS"
        else:
            paths = {f.old_path.removeprefix("a/") for f in parse_patch(first.decode()).files}
            require(paths == set(PATCH11_CANONICAL_FILES), "Patch 11 ownership boundary changed")
        missing = "Missing required KernelSU files" if target == "xxksu" else (
            "Upstream SuSFS 50 patch" if target.startswith("sultan") else "Patch 50 missing")
        generate_process(env_root, patch_id, empty, missing=missing)
        if target.startswith("gki"):
            ctx = env_root / ".github/fixtures/v2/r38-sources.json"
            saved = ctx.read_bytes()
            ctx.unlink()
            try:
                generate_process(env_root, patch_id, source, missing="r38-sources.json")
            finally:
                ctx.write_bytes(saved)
        row["negative provenance"] = "PASS"
        candidate = work / Path(entry["relative_path"]).name
        candidate.write_bytes(first)
        protected = {p: (targets[target] / p).read_bytes() for p in (
            "kernel/feature/kernel_umount.c", "kernel/downstream/ksu_hostsredirect.h")} if target == "xxksu" else {}
        ok, errors = validate_exact_patch_on_tree(targets[target], candidate, dry_run=False)
        require(ok, str(errors))
        for path, data in protected.items():
            require((targets[target] / path).read_bytes() == data, f"protected file changed: {path}")
        row["exact apply"] = "PASS (0 offsets / fuzz / rejects)"
        reference = run_reference_cross_check(patch_id, first.decode(), sha(first), repo_root=ROOT)
        if reference is not None:
            report["midori"][patch_id] = reference.classification.value
            print(json.dumps(reference.to_dict(), indent=2), flush=True)
            require(not reference.blocks_promotion and reference.classification.value != "REFERENCE_UNAVAILABLE",
                    f"incomplete/blocking reference check: {patch_id}: {reference.details}")

    for focused in (True, False):
        output = work / ("focused.json" if focused else "tests.json")
        result = subprocess.run([sys.executable, "-m", "v2.clean_room",
                                 "focused" if focused else "tests", str(output)], cwd=ROOT)
        data = json.loads(output.read_text())
        report["focused" if focused else "tests"] = data
        require(result.returncode == 0, f"tests failed or skipped: {data}")
        if focused:
            for row in report["patches"].values():
                row["target contracts"] = "PASS"
            report["patches"]["gki-android16-6.12-r38-patch51"]["lifecycle checks"] = "PASS"


def main():
    report = {"status": "FAIL", "head": command("git", "rev-parse", "HEAD", cwd=ROOT),
              "patches": {}, "midori": {}}
    print(report["head"], sys.version, command("git", "--version"), platform.platform(), flush=True)
    try:
        require(repository_state(ROOT) == {"tracked": "CLEAN", "untracked": []}, "checkout is not clean")
        with tempfile.TemporaryDirectory(prefix="xxksu-clean-room-", dir=os.environ.get("RUNNER_TEMP")) as tmp:
            work = Path(tmp).resolve()
            require(not work.is_relative_to(ROOT), "temporary root must be outside checkout")
            os.environ.update(TMPDIR=str(work), PYTHONDONTWRITEBYTECODE="1",
                              GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")
            tempfile.tempdir = str(work)
            verify(work, report)
        report["status"] = "PASS"
    except Exception as exc:
        report["error"] = str(exc)
        print(f"CLEAN-ROOM FAILED: {exc}", file=sys.stderr, flush=True)
    finally:
        report["repository"] = repository_state(ROOT)
        if report["repository"] != {"tracked": "CLEAN", "untracked": []}:
            report["status"] = "FAIL"
        text = summary(report)
        print(text)
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as out:
                out.write(text)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "verify"
    if mode == "generate":
        generate_child(*sys.argv[2:])
    elif mode in ("tests", "focused"):
        raise SystemExit(run_tests(sys.argv[2], mode == "focused"))
    else:
        raise SystemExit(main())
