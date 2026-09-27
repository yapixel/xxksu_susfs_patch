"""Execute corrected production C control flow with bounded kernel API mocks."""
from pathlib import Path
import json
import subprocess
import tempfile
import unittest

from v2.engine.diff_parser import parse_patch
from v2.engine.emitter import emit_patch
from v2.model.patch import Patch
from v2.policy.lifecycle import correct_patch51, r38_sources
from v2.source.bundle import create_source_bundle, load_source_bundle
from v2.source.patch_apply import apply_patch_to_bundle

ROOT = Path(__file__).resolve().parents[4]


def target_headers(gki):
    return json.loads((ROOT / ".github/fixtures/v2/target-api-contracts.json").read_text())[
        "gki" if gki else "sultan"]["excerpts"]


def rollup_harness():
    headers = target_headers(True)
    return ROLLUP_MOCKS.replace("NATIVE_ITERATOR", headers["vma_iterator"]).replace(
        "NATIVE_VMA_HELPERS", headers["vma_next"] + headers["vma_iter_invalidate"])


def target_sources(gki):
    if gki:
        return r38_sources(ROOT)
    bundle = load_source_bundle(ROOT / ".github/fixtures/v2/v29-baselines/sultan-android14-6.1.json")
    return {entry.path: entry.content for entry in bundle.files}


def postimages(gki, corrected=True):
    target = "gki-android16-6.12" if gki else "sultan-android14-6.1"
    directory = ROOT / ".github/fixtures" / ("r38" if gki else "sultan")
    if corrected:
        from v2.pipeline import generate_candidate_patch
        pid = "gki-android16-6.12-r38-patch51" if gki else "sultan-android14-6.1-patch51"
        text = generate_candidate_patch(pid, directory, ROOT)
    else:
        # Historical defective outputs are negative-test goldens only.
        text = next(directory.glob("51_*.patch")).read_text()
    sources = target_sources(gki)
    patch = parse_patch(text)
    patch.files = [file for file in patch.files if file.old_path.removeprefix("a/") in sources]
    bundle = create_source_bundle(target, "6.12" if gki else "6.1", sources)
    return {entry.path: entry.content for entry in apply_patch_to_bundle(bundle, emit_patch(patch)).files}


def function(source, signature):
    start = source.index(signature)
    begin = source.index("{", start)
    depth = 1
    end = begin + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end] + "\n"


def run_c(source, *, syntax_only=False):
    with tempfile.TemporaryDirectory(prefix="patch51-c-") as tmp:
        path = Path(tmp) / "test.c"
        path.write_text("#include <stddef.h>\n" + source)
        compiled = subprocess.run(["gcc", "-std=gnu11", "-Wall", "-Werror=implicit-function-declaration",
                        "-Werror=return-type", str(path), *(["-fsyntax-only"] if syntax_only else ["-o", str(Path(tmp) / "test")])],
                       capture_output=True, text=True)
        if compiled.returncode:
            raise AssertionError(compiled.stderr)
        if syntax_only:
            return 0
        return subprocess.run([str(Path(tmp) / "test")], capture_output=True, timeout=15).returncode


def pagemap_harness(source, *, gki):
    # Keep each target's real types, constants, make_pme and add_to_pagemap.
    # In particular, Sultan takes an address argument and GKI does not.
    start = source.index("typedef struct {\n\tu64 pme;")
    end = source.index("static int pagemap_pte_hole(", start)
    native = source[start:end]
    walk = PAGEMAP_WALK_MOCK.replace(
        "APPEND_ENTRY", "add_to_pagemap(&p, pm)" if gki else "add_to_pagemap(s, &p, pm)")
    return PAGEMAP_MOCKS + native + walk


def namei_harness(source):
    """Execute target nested lookup setup/restore instead of a substitute owner."""
    mocks = NAMEI_MOCKS
    start = source.index("struct nameidata {")
    end = source.index("} __randomize_layout;", start) + len("} __randomize_layout;")
    native_struct = source[start:end]
    mocks = mocks.replace(
        "NATIVE_NAMEIDATA_STRUCT",
        "#define EMBEDDED_LEVELS 2\n#define __randomize_layout\n"
        "struct qstr { int unused; }; struct delayed_call { int unused; };\n"
        "typedef unsigned short umode_t; typedef int vfsuid_t;\n" + native_struct)
    mocks = mocks.replace("static struct nameidata *active;",
        "static struct { struct nameidata *nameidata; } task;\n"
        "#define current (&task)\n#define active (current->nameidata)\n"
        "#include <stdlib.h>\n#define kfree free\n"
        "#define LOOKUP_MOUNTPOINT 128\n#define AUDIT_INODE_NOEVAL 1\n")
    native = "".join(function(source, sig) for sig in (
        "static void __set_nameidata(", "static inline void set_nameidata(",
        "static void restore_nameidata("))
    mocks = mocks.replace("NATIVE_NAMEIDATA_LIFETIME", native)
    mocks = mocks.replace("NATIVE_FILENAME_LOOKUP",
        "static void audit_inode(struct filename *,struct dentry *,int);\n" +
        function(source, "int filename_lookup("))
    return mocks


class LifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gki = postimages(True)
        cls.sultan = postimages(False)

    def test_pagemap_vma_boundaries_both_targets(self):
        for gki, sources in ((True, self.gki), (False, self.sultan)):
            source = sources["fs/proc/task_mmu.c"]
            helper = function(source, "static int susfs_pagemap_walk(")
            self.assertEqual(run_c(pagemap_harness(source, gki=gki) + helper + PAGEMAP_CASES), 0)

    def test_pagemap_rejects_other_targets_append_api(self):
        for gki, sources in ((True, self.gki), (False, self.sultan)):
            source = sources["fs/proc/task_mmu.c"]
            helper = function(source, "static int susfs_pagemap_walk(")
            correct = "add_to_pagemap(&pme, pm)" if gki else "add_to_pagemap(start, &pme, pm)"
            wrong = "add_to_pagemap(start, &pme, pm)" if gki else "add_to_pagemap(&pme, pm)"
            self.assertEqual(helper.count(correct), 1)
            with self.assertRaisesRegex(AssertionError, "too (few|many) arguments"):
                run_c(pagemap_harness(source, gki=gki) +
                      helper.replace(correct, wrong) + PAGEMAP_CASES)

    def test_pagemap_actual_read_lengths_offsets_and_partial_vmas(self):
        for gki, sources in ((True, self.gki), (False, self.sultan)):
            source = sources["fs/proc/task_mmu.c"]
            functions = function(source, "static int susfs_pagemap_walk(")
            if gki:
                functions += function(source, "static inline void __collapse_pagemap_result(")
            functions += function(source, "static ssize_t pagemap_read(")
            self.assertEqual(run_c(pagemap_harness(source, gki=gki) +
                                   PAGEMAP_READ_MOCKS + functions + PAGEMAP_READ_CASES), 0)
            if gki:
                emulated = pagemap_harness(source, gki=True).replace(
                    "#define __PAGE_SIZE PAGE_SIZE", "#define __PAGE_SIZE (4 * PAGE_SIZE)")
                emulated = emulated.replace(
                    "? 123+s/PAGE_SIZE:0,0)", "? 123+s/PAGE_SIZE:0,v && s>=v->vm_start ? PM_PRESENT|PM_FILE:0)")
                self.assertEqual(run_c(emulated + PAGEMAP_READ_MOCKS +
                                       functions + PAGEMAP_EMULATED_CASES), 0)


    def test_nameidata_retries_and_local_lookup_ownership(self):
        names = ("static int do_tmpfile(", "static int do_o_path(",
                 "static struct file *path_openat(", "struct file *do_filp_open(")
        functions = "".join(function(self.gki["fs/namei.c"], name) for name in names)
        self.assertEqual(run_c(namei_harness(self.gki['fs/namei.c']) + functions + NAMEI_CASES), 0)
        original = postimages(True, False)["fs/namei.c"]
        functions = "".join(function(original, name) for name in names)
        self.assertNotEqual(run_c(namei_harness(original) + functions + NAMEI_CASES), 0,
                            "regression must reproduce the original lifetime failure")

    def test_mount_provenance_transition_inheritance_and_early_failure(self):
        for sources in (self.gki, self.sultan):
            clone = function(sources["fs/namespace.c"], "static struct mount *clone_mnt(")
            # Execute the real allocator/flag/failure paths. Unrelated successful
            # clone linking is removed at its exact boundary, not modeled anew.
            middle = clone.index("\tatomic_inc(&sb->s_active);")
            tail = clone.index(" out_free:")
            clone = clone[:middle] + "\treturn mnt;\n\n" + clone[tail:]
            free_id = function(sources["fs/namespace.c"], "static void mnt_free_id(")
            self.assertEqual(run_c(MOUNT_MOCKS + free_id + clone + MOUNT_CASES), 0)

    def test_smaps_normal_and_reacquired_partial_gather(self):
        source = self.gki["fs/proc/task_mmu.c"]
        gather = function(source, "static void smap_gather_stats(")
        rollup = function(source, "static int show_smaps_rollup(")
        # Normal and reacquired case 1/2 pass zero; case 4 passes last_vma_end.
        # Every caller enters the same function. Execute each distinct start mode.
        self.assertIn("smap_gather_stats(vma, &mss, last_vma_end)", rollup)
        self.assertIn("mmap_read_lock_killable", rollup)
        self.assertEqual(run_c(SMAPS_MOCKS + gather + SMAPS_CASES), 0)
        old = function(postimages(True, False)["fs/proc/task_mmu.c"], "static void smap_gather_stats(")
        self.assertNotEqual(run_c(SMAPS_MOCKS + old + SMAPS_CASES), 0)

    def test_smaps_actual_rollup_reacquire_branches(self):
        source = self.gki["fs/proc/task_mmu.c"]
        rollup = function(source, "static int show_smaps_rollup(")
        loop = rollup[rollup.index("\tdo {"):rollup.index("\nempty_set:")]
        wrapper = ("static unsigned long run_rollup(void) {\n"
                   "struct mem_size_stats mss={0}; struct mm_struct *mm=NULL;\n"
                   "void *priv=NULL; int ret=0; struct vma_iterator vmi={0}; unsigned long last_vma_end=0;\n"
                   "struct vm_area_struct *vma=vma_next(&vmi);\n" + loop +
                   "\nout_put_mm: return mss.swap;\n}\n")
        gather = function(source, "static void smap_gather_stats(")
        harness = SMAPS_MOCKS + rollup_harness() + gather + wrapper + ROLLUP_CASES
        self.assertEqual(run_c(harness), 0)
        old = function(postimages(True, False)["fs/proc/task_mmu.c"], "static void smap_gather_stats(")
        self.assertNotEqual(run_c(SMAPS_MOCKS + rollup_harness() + old + wrapper + ROLLUP_CASES), 0)

    def test_native_target_contracts(self):
        for gki in (False, True):
            sources = target_sources(gki)
            specs = [
                ("fs/namei.c", "static inline void set_nameidata(", "void (*)(struct nameidata *, int, struct filename *, const struct path *)"),
                ("fs/namei.c", "static void restore_nameidata(", "void (*)(void)"),
                ("fs/namei.c", "int filename_lookup(", "int (*)(int, struct filename *, unsigned, struct path *, struct path *)"),
                ("fs/namei.c", "int vfs_tmpfile(" if gki else "static int vfs_tmpfile(",
                 "int (*)(struct " + ("mnt_idmap" if gki else "user_namespace") + " *, const struct path *, struct file *, umode_t)"),
                ("security/security.c", "int security_setprocattr(",
                 "int (*)(" + ("int" if gki else "const char *") + ", const char *, void *, size_t)"),
                ("fs/proc/task_mmu.c", "static void smap_gather_stats(",
                 "void (*)(struct vm_area_struct *, struct mem_size_stats *, unsigned long)"),
                ("fs/namespace.c", "static struct mount *clone_mnt(",
                 "struct mount *(*)(struct mount *, struct dentry *, int)"),
                ("fs/namespace.c", "static struct mount *alloc_vfsmnt(",
                 "struct mount *(*)(const char *)"),
                ("fs/namespace.c", "static void mnt_free_id(", "void (*)(struct mount *)"),
            ]
            code = ("typedef unsigned short umode_t;\n"
                    "struct nameidata; struct filename; struct path; struct file;\n"
                    "struct mnt_idmap; struct user_namespace; struct vm_area_struct;\n"
                    "struct mem_size_stats; struct mount; struct dentry;\n")
            for path, signature, expected in specs:
                declaration = function(sources[path], signature).split("{", 1)[0].strip()
                symbol = signature.split("(")[0].split()[-1].lstrip("*")
                code += declaration + ";\n"
                code += '_Static_assert(__builtin_types_compatible_p(typeof(&' + symbol + '), ' + expected + '), "' + symbol + '");\n'
            headers = target_headers(gki)
            code += "struct mm_struct; struct mm_walk_ops; struct ma_state {int unused;};\n"
            code += headers["vma_iterator"]
            for name, expected in (
                ("find_vma", "struct vm_area_struct *(*)(struct mm_struct *, unsigned long)"),
                ("walk_page_range", "int (*)(struct mm_struct *, unsigned long, unsigned long, const struct mm_walk_ops *, void *)"),
                ("vma_next", "struct vm_area_struct *(*)(struct vma_iterator *)"),
            ):
                code += headers[name].split("{", 1)[0].rstrip(";\n") + ";\n"
                code += '_Static_assert(__builtin_types_compatible_p(typeof(&' + name + '), ' + expected + '), "' + name + '");\n'
            self.assertEqual(run_c(code, syntax_only=True), 0)

    def test_generation_deterministic_and_changed_preimage_fails(self):
        for gki in (True, False):
            directory = ROOT / ".github/fixtures" / ("r38" if gki else "sultan")
            text = next(directory.glob("51_*.patch")).read_text()
            self.assertEqual(correct_patch51(text, ROOT, gki=gki), correct_patch51(text, ROOT, gki=gki))
            with self.assertRaises(ValueError):
                correct_patch51(text.replace("vma_lookup(mm, start_vaddr)", "unreviewed_lookup(mm, start_vaddr)"), ROOT, gki=gki)


PAGEMAP_MOCKS = r'''
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#define CONFIG_KSU_SUSFS_SUS_MAP 1
#define PAGE_SHIFT 12
#define PAGE_SIZE 4096UL
#define __PAGE_SIZE PAGE_SIZE
#define PMD_SIZE (8 * PAGE_SIZE)
#define PMD_MASK (~(PMD_SIZE - 1))
#define BIT_ULL(n) (1ULL << (n))
#define GENMASK_ULL(h,l) ((~0ULL << (l)) & (~0ULL >> (63-(h))))
#define min(a,b) ((a)<(b)?(a):(b))
#define file_inode(f) (f)
#define SUSFS_IS_INODE_SUS_MAP(f) (*(f))
typedef uint64_t u64;
#include <stdbool.h>
struct vm_area_struct { unsigned long vm_start,vm_end; int *vm_file; };
struct mm_struct { struct vm_area_struct *v; int n; unsigned long task_size; };
struct mm_walk_ops {int unused;}; static struct mm_walk_ops pagemap_ops;
static struct vm_area_struct *find_vma(struct mm_struct *mm,unsigned long s) {
 for(int i=0;i<mm->n;i++) if(mm->v[i].vm_end>s) return &mm->v[i]; return NULL;
}
'''
PAGEMAP_WALK_MOCK = r'''
static int walk_page_range(struct mm_struct *mm,unsigned long s,unsigned long e,const struct mm_walk_ops *ops,void *private) {
 struct pagemapread *pm=private;
 for(;s<e;s+=PAGE_SIZE) { struct vm_area_struct *v=find_vma(mm,s);
  pagemap_entry_t p=make_pme(v && s>=v->vm_start ? 123+s/PAGE_SIZE:0,0);
  assert(pm->pos<pm->len);
  int ret=APPEND_ENTRY; if(ret) return ret;
 } return 0;
}
'''
PAGEMAP_CASES = r'''
int main(void) {
 int hidden=1,visible=0;
 /* All 2^8 visible/hidden layouts include both transitions, multiple VMA
  * boundaries, all hidden and all visible. Exercise subrange reads too. */
 for(int mask=0;mask<256;mask++) {
  struct vm_area_struct v[8]; struct mm_struct mm={v,8};
  for(int i=0;i<8;i++) v[i]=(struct vm_area_struct){i*PAGE_SIZE,(i+1)*PAGE_SIZE,mask&(1<<i)?&hidden:&visible};
  for(int first=0;first<8;first++) for(int last=first+1;last<=8;last++) {
   pagemap_entry_t buffer[32]; struct pagemapread pm={.len=32,.buffer=buffer};
   assert(susfs_pagemap_walk(&mm,first*PAGE_SIZE,last*PAGE_SIZE,&pm)==0);
   assert(pm.pos==last-first);
   for(int i=first;i<last;i++) assert(pm.buffer[i-first].pme==(mask&(1<<i)?0:123UL+i));
  }
 }
 struct vm_area_struct v[]={{PAGE_SIZE,2*PAGE_SIZE,&hidden},{3*PAGE_SIZE,5*PAGE_SIZE,&visible}};
 struct mm_struct mm={v,2}; pagemap_entry_t buffer[6]; struct pagemapread pm={.len=6,.buffer=buffer};
 assert(susfs_pagemap_walk(&mm,0,6*PAGE_SIZE,&pm)==1 && pm.pos==6);
 assert(pm.buffer[0].pme==0 && pm.buffer[1].pme==0 && pm.buffer[2].pme==0 && pm.buffer[3].pme==126 && pm.buffer[4].pme==127 && pm.buffer[5].pme==0);
 return 0;
}
'''


PAGEMAP_READ_MOCKS = r'''
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#include <errno.h>
#include <sys/types.h>
#define GFP_KERNEL 0
#define CAP_SYS_ADMIN 0
#define __user
#define unlikely(x) (x)
struct file {struct mm_struct *private_data;};
static int init_user_ns,lock_held;
static int mmget_not_zero(struct mm_struct *mm) {return 1;}
static void mmput(struct mm_struct *mm) {}
static int file_ns_capable(struct file *f,int *ns,int cap) {return 1;}
static void *kmalloc_array(size_t n,size_t size,int flags) {return calloc(n,size);}
static void *kcalloc(size_t n,size_t size,int flags) {return calloc(n,size);}
static void kfree(void *p) {free(p);}
static int mmap_read_lock_killable(struct mm_struct *mm) {assert(!lock_held);lock_held=1;return 0;}
static void mmap_read_unlock(struct mm_struct *mm) {assert(lock_held);lock_held=0;}
static unsigned long untagged_addr(unsigned long a) {return a;}
static unsigned long untagged_addr_remote(struct mm_struct *mm,unsigned long a) {assert(lock_held);return a;}
static int copy_to_user(void *d,const void *s,size_t n) {assert(!lock_held);memcpy(d,s,n);return 0;}
'''
PAGEMAP_READ_CASES = r'''
int main(void) {
 int hidden=1,visible=0;
 /* Both transitions and visible-hidden-visible within one 8-page chunk;
  * longer VMAs exercise starts/ends inside a VMA, plus holes and EOF. */
 struct vm_area_struct v[]={{PAGE_SIZE,3*PAGE_SIZE,&visible},
  {3*PAGE_SIZE,5*PAGE_SIZE,&hidden},{5*PAGE_SIZE,17*PAGE_SIZE,&visible},
  {20*PAGE_SIZE,24*PAGE_SIZE,&hidden}};
 struct mm_struct mm={v,4,32*PAGE_SIZE}; struct file f={&mm};
 for(int first=0;first<=33;first++) for(int n=1;n<=35;n++) {
  u64 out[40]; for(int j=0;j<40;j++)out[j]=~0ULL;
  loff_t pos=first*PM_ENTRY_BYTES;
  ssize_t got=pagemap_read(&f,(char*)out,n*PM_ENTRY_BYTES,&pos);
  int entries=first>=32?0:min(n,32-first);
  assert(got==entries*PM_ENTRY_BYTES);
  assert(pos==(first+entries)*PM_ENTRY_BYTES && !lock_held);
  for(int j=0;j<entries;j++) {
   int a=first+j,vis=(a>=1&&a<3)||(a>=5&&a<17);
   assert(out[j]==(vis?123UL+a:0));
  }
  assert(out[entries]==~0ULL);
  /* A following read must start at the next virtual page, not a VMA/chunk edge. */
  if(first+entries<32) {
   int a=first+entries,vis=(a>=1&&a<3)||(a>=5&&a<17);
   assert(pagemap_read(&f,(char*)out,PM_ENTRY_BYTES,&pos)==PM_ENTRY_BYTES);
   assert(out[0]==(vis?123UL+a:0) && pos==(a+1)*PM_ENTRY_BYTES);
  }
 }
 return 0;
}
'''

NAMEI_MOCKS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <errno.h>
#define CONFIG_KSU_SUSFS_OPEN_REDIRECT 1
#define unlikely(x) (x)
#define likely(x) (x)
#define IS_ERR(p) ((intptr_t)(p)<0)
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define PTR_ERR(p) ((intptr_t)(p))
#define ND_ROOT_PRESET 1
#define LOOKUP_RCU 2
#define LOOKUP_REVAL 4
#define LOOKUP_DIRECTORY 8
#define __O_TMPFILE 16
#define O_PATH 32
#define FMODE_OPENED 1
#define EOPENSTALE 1000
#define WARN_ON(x) assert(!(x))
#define SUSFS_IS_INODE_OPEN_REDIRECT_WITHOUT_UID_CHECK(i) (redirect)
struct filename { int alive; };
struct dentry { int *d_inode; };
struct vfsmount {int unused;}; static struct vfsmount mount;
struct path { struct dentry *dentry; struct vfsmount *mnt; };
NATIVE_NAMEIDATA_STRUCT
struct open_flags { int open_flag,lookup_flags,mode; };
struct file { int f_flags,f_mode; struct path f_path; };
static struct filename original={1},fake;
static struct dentry dent;
static struct file result;
static struct nameidata *active;
static int redirect=1,root_preset,attempt,allocated,freed,refs,lookup_error,open_error,lookup_calls;
static unsigned expected_flags;
NATIVE_NAMEIDATA_LIFETIME
static int current_cred(void) {return 0;}
static struct file *alloc_empty_file(int flags,int cred) {result=(struct file){flags,FMODE_OPENED,{&dent,&mount}};return &result;}
static int path_lookupat(struct nameidata *nd,unsigned flags,struct path *p) {
 assert(nd->name->alive);
 if(nd->name==&fake) {
  assert(nd->dfd==73 && nd->saved && nd->saved->name==&original);
  assert((flags & ~LOOKUP_RCU)==expected_flags); lookup_calls++;
  if(lookup_error) return lookup_error;
 }
 refs++; *p=(struct path){&dent,&mount}; return 0;
}
static struct filename *susfs_open_redirect_spoof_do_sys_openat(int *inode) { assert(!fake.alive); fake.alive=1;allocated++;return &fake;}
static void putname(struct filename *name) { assert(name->alive); assert(!active || active->name!=name); name->alive=0;freed++; }
static void path_put(struct path *p) { assert(refs>0);refs--; }
NATIVE_FILENAME_LOOKUP
static int mnt_want_write(struct vfsmount *mnt) {return 0;}
static void mnt_drop_write(struct vfsmount *mnt) {}
struct mnt_idmap {int unused;};
static struct mnt_idmap idmap;
static struct mnt_idmap *mnt_idmap(struct vfsmount *mnt) {return &idmap;}
static int vfs_tmpfile(struct mnt_idmap *id,const struct path *p,struct file *f,umode_t mode) {return open_error;}
static void audit_inode(struct filename *name,struct dentry *d,int flag) {assert(name->alive);}
static int vfs_open(struct path *p,struct file *f) {return open_error;}
static const char *path_init(struct nameidata *nd,unsigned flags) {assert(nd->name->alive);nd->path=(struct path){&dent,&mount};return "name";}
static int link_path_walk(const char *s,struct nameidata *nd) {assert(nd->name->alive);return 0;}
static const char *open_last_lookups(struct nameidata *nd,struct file *f,const struct open_flags *op) {return NULL;}
static void terminate_walk(struct nameidata *nd) {}
static int do_open(struct nameidata *nd,struct file *f,const struct open_flags *op) {assert(nd->name->alive);return ++attempt<3?-EOPENSTALE:0;}
static void fput(struct file *f) {}
'''
NAMEI_CASES = r'''
int main(void) {
 struct open_flags op={0};
 assert(do_filp_open(73,&original,&op)==&result);
 assert(attempt==3 && allocated==3 && freed==3 && original.alive);
 for(int mode=0;mode<2;mode++) for(int preset=0;preset<2;preset++)
 for(int redir=0;redir<2;redir++) for(int err=0;err<3;err++) {
  struct nameidata nd; root_preset=preset; redirect=redir; allocated=freed=refs=lookup_calls=0;
  lookup_error=err==1?-ENOENT:0; open_error=err==2?-EACCES:0;
  struct path root={&dent,&mount};
  set_nameidata(&nd,73,&original,preset?&root:NULL); expected_flags=64|(mode?LOOKUP_DIRECTORY:0);
  if(mode) do_tmpfile(&nd,64,&op,&result); else do_o_path(&nd,64,&result);
  assert(nd.name==&original && original.alive && refs==0 && allocated==freed);
  assert(lookup_calls==(!preset && redir)); restore_nameidata();
 }
 return 0;
}
'''

MOUNT_MOCKS = r'''
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#include <stdint.h>
#define CONFIG_KSU_SUSFS_SUS_MOUNT 1
#define CL_COPY_MNT_NS 1
#define CL_SLAVE 2
#define CL_PRIVATE 4
#define CL_SHARED_TO_SLAVE 8
#define CL_MAKE_SHARED 16
#define MNT_WRITE_HOLD 32
#define MNT_MARKED 64
#define MNT_INTERNAL 128
#define VFSMOUNT_MNT_FLAGS_KSU_UNSHARED_MNT 256
#define DEFAULT_KSU_MNT_ID 1000
#define unlikely(x) (x)
#define ERR_PTR(e) ((void *)(intptr_t)(e))
struct super_block {int s_active;}; struct dentry {int dummy;};
struct mount {struct {struct super_block *mnt_sb;int mnt_flags;} mnt; int mnt_id,mnt_group_id; char *mnt_devname;};
static struct mount allocated;
static int susfs_is_sdcard_android_data_not_decrypted,key,domain,flip,ida_owned,free_count,group_error;
static int static_branch_unlikely(int *p) {return key;}
static int susfs_is_current_ksu_domain(void) {return domain;}
static struct mount *alloc_common(int ida) {allocated=(struct mount){.mnt_id=ida?701:99};ida_owned=ida;if(flip)key=!key;return &allocated;}
static struct mount *alloc_vfsmnt(const char *name) {return alloc_common(1);}
static struct mount *susfs_alloc_non_unshare_ksu_vfsmnt(const char *name) {return alloc_common(1);}
static struct mount *susfs_alloc_unshare_ksu_vfsmnt(const char *name,int id) {return alloc_common(0);}
static int mnt_alloc_group_id(struct mount *m) {return group_error;}
static int mnt_id_ida;
static void ida_free(int *ida,int id) {assert(ida == &mnt_id_ida);assert(ida_owned);assert(id==allocated.mnt_id);free_count++;}
static void free_vfsmnt(struct mount *m) {}
'''
MOUNT_CASES = r'''
int main(void) {
 for(int initial=0;initial<2;initial++) for(int change=0;change<2;change++)
 for(int dom=0;dom<2;dom++) for(int inherited=0;inherited<2;inherited++)
 for(int copy=0;copy<2;copy++) for(int fail=0;fail<2;fail++) {
  struct mount old={.mnt={NULL,inherited?VFSMOUNT_MNT_FLAGS_KSU_UNSHARED_MNT:0}};
  key=initial;flip=change;domain=dom;group_error=fail?-ENOMEM:0;free_count=0;
  struct mount *m=clone_mnt(&old,NULL,CL_MAKE_SHARED|(copy?CL_COPY_MNT_NS:0));
  if(!fail) {assert(!!(m->mnt.mnt_flags&VFSMOUNT_MNT_FLAGS_KSU_UNSHARED_MNT)==!ida_owned);mnt_free_id(m);}
  assert(free_count==ida_owned);
 } return 0;
}
'''

SMAPS_MOCKS = r'''
#include <assert.h>
#define CONFIG_KSU_SUSFS_SUS_MAP 1
#define VM_SHARED 1
#define VM_WRITE 2
#define VMA_PAD_START(v) ((v)->vm_end)
#define file_inode(f) (f)
#define SUSFS_IS_INODE_SUS_MAP(f) ((f)->hidden)
struct mm_struct;
struct file {int hidden,f_mapping;};
struct vm_area_struct {unsigned long vm_start,vm_end,vm_flags;struct file *vm_file;void *vm_mm;};
struct mem_size_stats {unsigned long swap;};
struct mm_walk_ops {int unused;};
static struct mm_walk_ops smaps_walk_ops,smaps_shmem_walk_ops;
static int calls;
static int shmem_mapping(int x) {return x;}
static unsigned long shmem_swap_usage(struct vm_area_struct *v) {return 42;}
static int walk_page_range(struct mm_struct *mm,unsigned long s,unsigned long e,const struct mm_walk_ops *ops,void *private) {struct mem_size_stats *m=private;calls++;m->swap+=e-s;return 0;}
'''
SMAPS_CASES = r'''
int main(void) {
 for(int hidden=0;hidden<2;hidden++) for(int shmem=0;shmem<2;shmem++)
 for(int mode=0;mode<3;mode++) {
  struct file f={hidden,shmem}; struct vm_area_struct v={4096,16384,VM_SHARED,&f,NULL};
  struct mem_size_stats m={0}; calls=0;
  /* normal, reacquired case1/2 partial VMA, and no remaining pages */
  smap_gather_stats(&v,&m,mode==0?0:mode==1?8192:16384);
  if(hidden||mode==2) assert(calls==0 && m.swap==0);
  else assert(calls==1 && m.swap>0);
 } return 0;
}
'''

ROLLUP_MOCKS = r'''
#include <stdbool.h>
#define for_each_vma(iter,vma) while (((vma)=vma_next(&(iter))) != NULL)
struct mm_struct {int unused;};
static struct vm_area_struct sequence[2];
static int total,contended,lock_held,iterator_paused;
#include <limits.h>
struct ma_state {int index,paused;};
NATIVE_ITERATOR
static struct vm_area_struct *mas_find(struct ma_state *s,unsigned long max) {
 assert(lock_held); s->paused=0; iterator_paused=0;
 return s->index<total?&sequence[s->index++]:NULL;
}
static void mas_pause(struct ma_state *s) {assert(lock_held);s->paused=1;iterator_paused=1;}
NATIVE_VMA_HELPERS
static int mmap_lock_is_contended(struct mm_struct *mm) {int ret=contended;contended=0;return ret;}
static void mmap_read_unlock(struct mm_struct *mm) {assert(lock_held && iterator_paused);lock_held=0;}
static int mmap_read_lock_killable(struct mm_struct *mm) {assert(!lock_held);lock_held=1;return 0;}
static void release_task_mempolicy(void *p) {}
'''
ROLLUP_CASES = r'''
int main(void) {
 for(int contend=0;contend<2;contend++) for(int hidden=0;hidden<2;hidden++)
 for(int kind=1;kind<=4;kind++) {
  struct file visible={0,0},second={hidden,0};
  sequence[0]=(struct vm_area_struct){4096,8192,0,&visible,NULL};
  sequence[1]=(struct vm_area_struct){kind==4?4096:8192,16384,0,&second,NULL};
  total=kind==3?1:2;contended=contend;lock_held=1;calls=0;
  unsigned long expected=4096;
  if(total==2 && !hidden) expected+=contend&&kind==4?8192:16384-sequence[1].vm_start;
  assert(run_rollup()==expected);
  assert(lock_held);
 } return 0;
}
'''


PAGEMAP_EMULATED_CASES = r'''
int main(void) {
 int hidden=1,visible=0;
 struct vm_area_struct v[]={{4*PAGE_SIZE,12*PAGE_SIZE,&visible},
  {12*PAGE_SIZE,20*PAGE_SIZE,&hidden},{20*PAGE_SIZE,28*PAGE_SIZE,&visible},
  {28*PAGE_SIZE,36*PAGE_SIZE,&hidden}};
 struct mm_struct mm={v,4,64*PAGE_SIZE}; struct file f={&mm};
 for(int first=0;first<=64;first+=4) for(int n=1;n<=17;n++) {
  u64 out[20]; for(int j=0;j<20;j++)out[j]=~0ULL;
  loff_t pos=first*PM_ENTRY_BYTES;
  int entries=min(n,(64-first)/4);
  assert(pagemap_read(&f,(char*)out,n*PM_ENTRY_BYTES,&pos)==entries*PM_ENTRY_BYTES);
  /* This kernel's read function advances the internal offset in base pages;
   * its outer emulation interface translates the public page-size units. */
  assert(pos==(first+4*entries)*PM_ENTRY_BYTES && !lock_held);
  for(int j=0;j<entries;j++) {
   int a=first+4*j,vis=(a>=4&&a<12)||(a>=20&&a<28);
   assert(out[j]==(vis?(PM_PRESENT|PM_FILE):0));
  }
  assert(out[entries]==~0ULL);
 }
 return 0;
}
'''
