"""Bounded real Kbuild object compilation and SuSFS object-symbol closure.

Source searches only locate potential providers. A provider is accepted only
when llvm-nm finds its global definition in an object built by this Kbuild/config.
This does not claim a final vmlinux link or device acceptance.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import time


def run(args, cwd, log=None):
    result = subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if log:
        with log.open("a") as out:
            out.write("$ " + shlex.join(map(str, args)) + "\n" + result.stdout)
    if result.returncode:
        raise RuntimeError(result.stdout[-12000:])
    return result.stdout


def kbuild_objects(plan, tree, output):
    """Read Kbuild's compiler commands, including composite/conditional members.
    Never infer an object filename from a C filename.
    """
    objects = {}
    for line in plan.splitlines():
        if " -c -o " not in line:
            continue
        args = shlex.split(line)
        at = args.index("-c")
        if args[at + 1] != "-o":
            raise RuntimeError("unrecognized Kbuild compiler command")
        obj, source = args[at + 2:at + 4]
        # Preserve the source spelling through the KernelSU symlink.
        path = Path(os.path.abspath(output / source))
        if path.is_relative_to(tree) and path.suffix == ".c" and path.is_file():
            objects[str(path.relative_to(tree))] = obj
    return objects


def symbols(objects, output, llvm):
    definitions, references = {}, {}
    for obj in sorted(objects):
        text = run(["llvm-nm" + llvm, "--format=posix", "--extern-only", str(output / obj)], output)
        for line in text.splitlines():
            fields = line.split()
            if len(fields) < 2:
                continue
            name, kind = fields[:2]
            if not name.startswith("susfs_"):
                continue
            if kind == "U":
                references.setdefault(name, []).append(obj)
            elif kind not in ("w", "v"):
                definitions.setdefault(name, []).append(obj)
    return definitions, references


def require_closure(objects, output, llvm="-14"):
    definitions, references = symbols(objects, output, llvm)
    missing = references.keys() - definitions.keys()
    if missing:
        raise RuntimeError(f"unresolved real-object SuSFS references: {sorted(missing)}")
    return definitions, references


def source_mentions(path, seen=None):
    """Provider discovery includes target unity builds; not a symbol oracle."""
    seen = set() if seen is None else seen
    path = path.resolve()
    if path in seen:
        return ""
    seen.add(path)
    text = path.read_text()
    for include in re.findall(r'^\s*#include\s+"([^"\n]+\.c)"', text, re.M):
        child = path.parent / include
        if child.is_file():
            text += source_mentions(child, seen)
    return text


def verify(tree, candidate, root, workspace, *, llvm="-14", jobs=4):
    from ..clean_room import fetch_git
    from ..pipeline import generate_patch11_from_tree
    started = time.monotonic()
    tree, workspace = tree.resolve(), workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    log = workspace / "kbuild.log"
    # Native Git parses the final candidate. There is no second touched-C list.
    numstat = run(["git", "apply", "--numstat", str(candidate.resolve())], tree)
    touched = {line.split("\t", 2)[2] for line in numstat.splitlines()
               if line.split("\t", 2)[2].endswith(".c")}
    if not touched:
        raise RuntimeError("final diff has no affected C translation units")
    state = json.loads((root / ".github/upstream-state.json").read_text())
    identity = state["sources"]["authoritative"]["backslashxx_kernelsu"]
    ksu = fetch_git(identity, workspace / "xxksu")
    patch = workspace / "ksu-integration.patch"
    patch.write_text(generate_patch11_from_tree(ksu, root))
    run(["git", "apply", "--check", str(patch)], ksu)
    run(["git", "apply", str(patch)], ksu)
    driver = tree / "drivers/kernelsu"
    if driver.exists() or driver.is_symlink():
        raise RuntimeError("build tree already contains KernelSU integration")
    driver.symlink_to(ksu / "kernel", target_is_directory=True)
    with (tree / "drivers/Makefile").open("a") as f:
        f.write("\nobj-$(CONFIG_KSU) += kernelsu/\n")
    with (tree / "drivers/Kconfig").open("a") as f:
        f.write('\nsource "drivers/kernelsu/Kconfig"\n')
    output = workspace / "objects"
    if output.exists():
        raise RuntimeError("Kbuild gate requires a fresh isolated output directory")
    make = ["make", f"O={output}", "ARCH=arm64", "LLVM=" + llvm]
    run(make + ["gki_defconfig"], tree, log)
    config = (output / ".config").read_text()
    required = ("KSU", "KSU_SUSFS", "KSU_SUSFS_SUS_MOUNT", "KSU_SUSFS_SUS_KSTAT", "KSU_SUSFS_SUS_MAP")
    for name in required:
        if f"CONFIG_{name}=y\n" not in config:
            raise RuntimeError(f"required build configuration absent: {name}")
    # Native SELinux Kbuild owns generated flask/av permission headers.
    run(make + [f"-j{jobs}", "prepare", "security/selinux/"], tree, log)
    return compile_objects(tree, candidate, workspace, make, touched, config, llvm, jobs, started)


def compile_objects(tree, candidate, workspace, make, touched, config, llvm, jobs, started):
    output, log = workspace / "objects", workspace / "kbuild.log"
    directories = sorted({p.split("/", 1)[0] + "/" for p in touched} | {"drivers/kernelsu/"})
    plan = run(make + ["-n", *directories], tree, log)
    mapping = kbuild_objects(plan, tree, output)
    if not touched <= mapping.keys():
        raise RuntimeError(f"affected source not compiled by actual CONFIG/Kbuild: {sorted(touched - mapping.keys())}")
    built = {mapping[p] for p in touched}
    run(make + [f"-j{jobs}", *sorted(built)], tree, log)
    texts = {path: source_mentions(tree / path) for path in mapping}
    while True:
        definitions, references = symbols(built, output, llvm)
        missing = references.keys() - definitions.keys()
        if not missing:
            break
        providers = {obj for path, obj in mapping.items() if obj not in built and
                     any(re.search(r"\b" + re.escape(name) + r"\b", texts[path]) for name in missing)}
        if not providers:
            raise RuntimeError(f"unresolved real-object SuSFS references: {sorted(missing)}")
        run(make + [f"-j{jobs}", *sorted(providers)], tree, log)
        built |= providers
    definitions, references = require_closure(built, output, llvm)
    # Native relocatable aggregation also rejects duplicate global definitions.
    aggregate = workspace / "patch51-objects.o"
    run(["ld.lld" + llvm, "-r", "-o", str(aggregate), *[str(output / p) for p in sorted(built)]], tree, log)
    unresolved = run(["llvm-nm" + llvm, "--undefined-only", str(aggregate)], tree, log)
    if re.search(r"\bsusfs_\w+", unresolved):
        raise RuntimeError("aggregate retains unresolved SuSFS symbols")
    report = {
        "PATCH51_OBJECT_COMPILE_PASS": True, "PATCH51_SYMBOL_CLOSURE_PASS": True,
        "full_vmlinux_link": "NOT_RUN", "config_sha256": hashlib.sha256(config.encode()).hexdigest(),
        "compiler": run(["clang" + llvm, "--version"], tree).splitlines()[0],
        "candidate_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
        "affected_sources": sorted(touched), "kbuild_objects": sorted(built),
        "source_objects": {p: mapping[p] for p in sorted(touched)},
        "symbols": {name: {"callers": callers, "providers": definitions[name]}
                    for name, callers in sorted(references.items())},
        "runtime_seconds": round(time.monotonic() - started, 3),
    }
    if "fs/susfs.c" in touched:
        report["historical_mutations"] = historical_probes(tree, workspace, make, report, llvm, log)
    (workspace / "gates.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def historical_probes(tree, workspace, make, report, llvm, log):
    """The two escaped Sultan defects must fail at their real build boundary.
    Mutants live only in the disposable validation tree and are always restored.
    These names select historical negative probes, never the positive oracle.
    """
    output = workspace / "objects"
    stat, namespace = tree / "fs/stat.c", tree / "fs/namespace.c"
    originals = {p: p.read_bytes() for p in (stat, namespace)}
    objects = report["kbuild_objects"]
    mapping = report["source_objects"]
    results = {}
    try:
        original = originals[stat].decode()
        include = "#include <linux/susfs_def.h>"
        if original.count(include) != 1:
            raise RuntimeError("historical header probe anchor changed")
        stat.write_text(original.replace(include, "/* missing required header */"))
        try:
            run(make + [mapping["fs/stat.c"]], tree, log)
        except RuntimeError:
            results["missing_required_header"] = "REJECTED_BY_KBUILD"
        else:
            raise RuntimeError("Kbuild did not detect missing SuSFS header")
        stat.write_bytes(originals[stat])
        run(make + [mapping["fs/stat.c"]], tree, log)
        names = ("susfs_get_non_sus_mnt_id_from_mnt", "susfs_get_non_sus_vfsmnt_from_vfsmnt")
        for removed in ((names[0],), (names[1],), names):
            source = originals[namespace].decode()
            for name in removed:
                pattern = r"(?m)^(int |struct vfsmount \*)" + name + r"\("
                source, count = re.subn(pattern, lambda m: m[1] + name + "_removed(", source)
                if count != 1:
                    raise RuntimeError("historical definition probe anchor changed: " + name)
            namespace.write_text(source)
            run(make + [mapping["fs/namespace.c"]], tree, log)
            try:
                require_closure(objects, output, llvm)
            except RuntimeError as exc:
                if not all(name in str(exc) for name in removed):
                    raise
                results["missing_" + "+".join(removed)] = "REJECTED_BY_OBJECT_CLOSURE"
            else:
                raise RuntimeError("missing definitions escaped object closure")
    finally:
        for path, content in originals.items():
            path.write_bytes(content)
        run(make + [mapping["fs/stat.c"], mapping["fs/namespace.c"]], tree, log)
    require_closure(objects, output, llvm)
    results["restored_postimage"] = "PASS"
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tree", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[4])
    args = parser.parse_args()
    print(json.dumps(verify(args.tree, args.candidate, args.root, args.workspace), indent=2))


if __name__ == "__main__":
    main()
