"""Bounded Patch 51 postimage corrections against authenticated kernel preimages.

These transformations fail on changed source shapes; they do not infer semantics
from helper names or successful application. Public patches are never inputs.
"""

from difflib import unified_diff
import hashlib
import json
import subprocess
from pathlib import Path

from ..engine.diff_parser import parse_patch
from ..engine.emitter import emit_patch
from ..model.patch import Patch
from ..source.bundle import create_source_bundle, load_source_bundle
from ..source.patch_apply import apply_patch_to_bundle


def r38_sources(root: Path) -> dict[str, str]:
    data = json.loads((root / ".github/fixtures/v2/r38-sources.json").read_text())
    sources = {}
    for path, entry in data["files"].items():
        content = entry["content"]
        if hashlib.sha256(content.encode()).hexdigest() != entry["sha256"]:
            raise ValueError(f"r38 source hash mismatch: {path}")
        sources[path] = content
    return sources


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"unreviewed lifecycle source shape: {old[:100]!r}")
    return source.replace(old, new, 1)


def fix_namei(source: str) -> str:
    # filename_lookup owns a nested nameidata; the outer retry context never
    # borrows fake_filename. It preserves dfd, flags, and ordinary root lookup.
    for indent, flags in (("\t\t\t", "flags | LOOKUP_DIRECTORY"),
                          ("\t\t\t\t", "flags")):
        old = (f"{indent}path_put(&path);\n{indent}restore_nameidata();\n"
               f"{indent}set_nameidata(nd, old_dfd, fake_filename, NULL);\n"
               f"{indent}error = path_lookupat(nd, {flags}, &path);")
        new = (f"{indent}struct path fake_path;\n\n"
               f"{indent}error = filename_lookup(old_dfd, fake_filename, {flags}, &fake_path, NULL);\n"
               f"{indent}path_put(&path);")
        source = replace_once(source, old, new)
        tail = (f"{indent}\treturn error;\n{indent}}}\n{indent[:-1]}}}")
        source = replace_once(source, tail,
                              f"{indent}\treturn error;\n{indent}}}\n"
                              f"{indent}path = fake_path;\n{indent[:-1]}}}")
    start = source.index("static struct file *path_openat(")
    end = source.index("\nstruct file *do_filp_open(", start)
    part = source[start:end]
    part = replace_once(part, "\tint old_dfd = nd->dfd;",
                        "\tint old_dfd = nd->dfd;\n\tstruct filename *old_name = nd->name;")
    part = replace_once(part,
                        "\tif (fake_filename && !IS_ERR(fake_filename))\n\t\tputname(fake_filename);",
                        "\tif (fake_filename && !IS_ERR(fake_filename)) {\n"
                        "\t\tnd->name = old_name;\n\t\tputname(fake_filename);\n\t}")
    return source[:start] + part + source[end:]


def fix_namespace(source: str) -> str:
    start = source.index("static struct mount *clone_mnt(")
    end = source.index("\nstatic void cleanup_mnt(", start)
    part = source[start:end]
    if "bool is_mnt_ksu_unshared = false;" not in part:
        part = replace_once(part, "\tint err;\n", "\tint err;\n"
                            "#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT\n"
                            "\tbool is_mnt_ksu_unshared = false;\n#endif\n")
        anchor = "\t\t\t\tmnt = susfs_alloc_unshare_ksu_vfsmnt(old->mnt_devname, old->mnt_id);"
        part = replace_once(part, anchor, anchor + "\n\t\t\t\tis_mnt_ksu_unshared = true;")
        part = replace_once(part,
                            "\tif (static_branch_unlikely(&susfs_is_sdcard_android_data_not_decrypted)) {\n"
                            "\t\tif (susfs_is_current_ksu_domain() && (flag & CL_COPY_MNT_NS))\n"
                            "\t\t\tmnt->mnt.mnt_flags |= VFSMOUNT_MNT_FLAGS_KSU_UNSHARED_MNT;\n\t}",
                            "\tif (unlikely(is_mnt_ksu_unshared))\n"
                            "\t\tmnt->mnt.mnt_flags |= VFSMOUNT_MNT_FLAGS_KSU_UNSHARED_MNT;")
    # The parent flag describes the parent's allocation, not the new allocation.
    part = replace_once(part, "\tif (unlikely(is_mnt_ksu_unshared))\n",
                        "\tmnt->mnt.mnt_flags &= ~VFSMOUNT_MNT_FLAGS_KSU_UNSHARED_MNT;\n"
                        "\tif (unlikely(is_mnt_ksu_unshared))\n")
    # Group-ID allocation can fail before mnt_flags is initialized.
    part = replace_once(part, " out_free:\n\tmnt_free_id(mnt);",
                        " out_free:\n#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT\n"
                        "\tif (!is_mnt_ksu_unshared)\n#endif\n\t\tmnt_free_id(mnt);")
    return source[:start] + part + source[end:]


PAGEMAP_WALK = """#ifdef CONFIG_KSU_SUSFS_SUS_MAP
/* Caller holds mmap_lock. Hidden pages have the same zero representation as
 * unmapped holes, including read length and position; never skip a walk chunk.
 */
static int susfs_pagemap_walk(struct mm_struct *mm, unsigned long start,
                            unsigned long end, struct pagemapread *pm)
{
	while (start < end) {
		struct vm_area_struct *vma = find_vma(mm, start);
		unsigned long next = end;
		int ret;

		if (vma)
			next = min(end, start < vma->vm_start ? vma->vm_start : vma->vm_end);
		if (vma && start >= vma->vm_start && vma->vm_file &&
		    SUSFS_IS_INODE_SUS_MAP(file_inode(vma->vm_file))) {
			pagemap_entry_t pme = make_pme(0, 0);

			for (; start < next; start += PAGE_SIZE) {
				ret = add_to_pagemap(&pme, pm);
				if (ret)
					return ret;
			}
		} else {
			ret = walk_page_range(mm, start, next, &pagemap_ops, pm);
			if (ret)
				return ret;
		}
		start = next;
	}
	return 0;
}
#endif

"""


def fix_task_mmu(source: str, *, gki: bool) -> str:
    start = source.index("static ssize_t pagemap_read(")
    part = source[start:]
    part = replace_once(part, "#ifdef CONFIG_KSU_SUSFS_SUS_MAP\n"
                        "\t\tstruct vm_area_struct *vma;\n"
                        "#endif // #ifdef CONFIG_KSU_SUSFS_SUS_MAP\n", "")
    old = ("#ifdef CONFIG_KSU_SUSFS_SUS_MAP\n"
           "\t\tvma = vma_lookup(mm, start_vaddr);\n"
           "\t\tif (vma && vma->vm_file && SUSFS_IS_INODE_SUS_MAP(file_inode(vma->vm_file)))\n"
           "\t\t\tgoto bypass_orig_flow;\n"
           "#endif // #ifdef CONFIG_KSU_SUSFS_SUS_MAP\n"
           "\t\tret = walk_page_range(mm, start_vaddr, end, &pagemap_ops, &pm);\n"
           "#ifdef CONFIG_KSU_SUSFS_SUS_MAP\n"
           "bypass_orig_flow:\n#endif // #ifdef CONFIG_KSU_SUSFS_SUS_MAP")
    part = replace_once(part, old, "#ifdef CONFIG_KSU_SUSFS_SUS_MAP\n"
                        "\t\tret = susfs_pagemap_walk(mm, start_vaddr, end, &pm);\n#else\n"
                        "\t\tret = walk_page_range(mm, start_vaddr, end, &pagemap_ops, &pm);\n#endif")
    source = source[:start] + PAGEMAP_WALK + part
    if gki:
        # All normal and lock-reacquire callers converge here, including the
        # partial-VMA gather (start != 0). Filtering here cannot skip progress.
        source = replace_once(source, "\tunsigned long end = VMA_PAD_START(vma);\n",
                              "\tunsigned long end = VMA_PAD_START(vma);\n\n"
                              "#ifdef CONFIG_KSU_SUSFS_SUS_MAP\n"
                              "\tif (vma->vm_file && SUSFS_IS_INODE_SUS_MAP(file_inode(vma->vm_file)))\n"
                              "\t\treturn;\n#endif\n")
    return source


def correct_patch51(text: str, root: Path, *, gki: bool) -> str:
    if gki:
        sources = r38_sources(root)
    else:
        bundle = load_source_bundle(root / ".github/fixtures/v2/v29-baselines/sultan-android14-6.1.json")
        sources = {entry.path: entry.content for entry in bundle.files}
    transforms = {"fs/namespace.c": fix_namespace,
                  "fs/proc/task_mmu.c": lambda src: fix_task_mmu(src, gki=gki)}
    if gki:
        transforms["fs/namei.c"] = fix_namei
    patch = parse_patch(text)
    for index, file in enumerate(patch.files):
        path = file.old_path.removeprefix("a/")
        if path not in transforms:
            continue
        before = sources[path]
        bundle = create_source_bundle("gki-android16-6.12" if gki else "sultan-android14-6.1",
                                      "6.12" if gki else "6.1", {path: before})
        post = apply_patch_to_bundle(bundle, emit_patch(Patch(files=[file]))).files[0].content
        corrected = transforms[path](post)
        diff = f"diff --git a/{path} b/{path}\n" + "".join(unified_diff(
            before.splitlines(True), corrected.splitlines(True), f"a/{path}", f"b/{path}"))
        patch.files[index] = parse_patch(diff).files[0]
    if set(transforms) != {file.old_path.removeprefix("a/") for file in patch.files} & set(transforms):
        raise ValueError("missing lifecycle patch file")
    # Reuse the legacy generator's native Git diffstat approach, but only AFTER
    # every source correction. --stat reports without applying or mutating files.
    if "---" in patch.preamble:
        body = emit_patch(Patch(files=patch.files))
        stat = subprocess.check_output(
            ["git", "-c", "core.quotePath=false", "-c", "color.ui=false", "apply", "--stat"],
            input=body, text=True)
        patch.preamble = patch.preamble[:patch.preamble.index("---") + 1] + stat.splitlines() + [""]
    return emit_patch(patch)
