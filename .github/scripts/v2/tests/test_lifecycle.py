"""Execute corrected production C control flow with bounded kernel API mocks."""
from pathlib import Path
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


def postimages(gki, corrected=True):
    target = "gki-android16-6.12" if gki else "sultan-android14-6.1"
    directory = ROOT / ".github/fixtures" / ("r38" if gki else "sultan")
    text = next(directory.glob("51_*.patch")).read_text()
    if corrected:
        text = correct_patch51(text, ROOT, gki=gki)
    if gki:
        sources = r38_sources(ROOT)
    else:
        bundle = load_source_bundle(ROOT / ".github/fixtures/v2/v29-baselines/sultan-android14-6.1.json")
        sources = {entry.path: entry.content for entry in bundle.files}
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


def run_c(source):
    with tempfile.TemporaryDirectory(prefix="patch51-c-") as tmp:
        path = Path(tmp) / "test.c"
        path.write_text("#include <stddef.h>\n" + source)
        compiled = subprocess.run(["gcc", "-std=gnu11", "-Wall", "-Werror=implicit-function-declaration",
                        "-Werror=return-type", str(path), "-o", str(Path(tmp) / "test")],
                       capture_output=True, text=True)
        if compiled.returncode:
            raise AssertionError(compiled.stderr)
        return subprocess.run([str(Path(tmp) / "test")], capture_output=True).returncode


class LifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gki = postimages(True)
        cls.sultan = postimages(False)

    def test_pagemap_vma_boundaries_both_targets(self):
        for sources in (self.gki, self.sultan):
            helper = function(sources["fs/proc/task_mmu.c"], "static int susfs_pagemap_walk(")
            self.assertEqual(run_c(PAGEMAP_MOCKS + helper + PAGEMAP_CASES), 0)

    def test_nameidata_retries_and_local_lookup_ownership(self):
        names = ("static int do_tmpfile(", "static int do_o_path(",
                 "static struct file *path_openat(", "struct file *do_filp_open(")
        functions = "".join(function(self.gki["fs/namei.c"], name) for name in names)
        self.assertEqual(run_c(NAMEI_MOCKS + functions + NAMEI_CASES), 0)
        original = postimages(True, False)["fs/namei.c"]
        functions = "".join(function(original, name) for name in names)
        self.assertNotEqual(run_c(NAMEI_MOCKS + functions + NAMEI_CASES), 0,
                            "regression must reproduce the original lifetime failure")

    def test_mount_provenance_transition_inheritance_and_early_failure(self):
        for sources in (self.gki, self.sultan):
            clone = function(sources["fs/namespace.c"], "static struct mount *clone_mnt(")
            # Execute the real allocator/flag/failure paths. Unrelated successful
            # clone linking is removed at its exact boundary, not modeled anew.
            middle = clone.index("\tatomic_inc(&sb->s_active);")
            tail = clone.index(" out_free:")
            clone = clone[:middle] + "\treturn mnt;\n\n" + clone[tail:]
            self.assertEqual(run_c(MOUNT_MOCKS + clone + MOUNT_CASES), 0)

    def test_smaps_normal_and_reacquired_partial_gather(self):
        source = self.gki["fs/proc/task_mmu.c"]
        gather = function(source, "static void smap_gather_stats(")
        rollup = function(source, "static int show_smaps_rollup(")
        # Case 1/2 after lock reacquire passes last_vma_end; case 4 and normal
        # loop also enter the same function. Execute every distinct start mode.
        self.assertIn("smap_gather_stats(vma, &mss, last_vma_end)", rollup)
        self.assertIn("mmap_read_lock_killable", rollup)
        self.assertEqual(run_c(SMAPS_MOCKS + gather + SMAPS_CASES), 0)
        old = function(postimages(True, False)["fs/proc/task_mmu.c"], "static void smap_gather_stats(")
        self.assertNotEqual(run_c(SMAPS_MOCKS + old + SMAPS_CASES), 0)

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
#define PAGE_SIZE 4096UL
#define min(a,b) ((a)<(b)?(a):(b))
#define file_inode(f) (f)
#define SUSFS_IS_INODE_SUS_MAP(f) (*(f))
typedef unsigned long pagemap_entry_t;
struct vm_area_struct { unsigned long vm_start,vm_end; int *vm_file; };
struct mm_struct { struct vm_area_struct *v; int n; };
struct pagemapread { int pos,len; pagemap_entry_t buffer[32]; };
static int pagemap_ops;
static struct vm_area_struct *find_vma(struct mm_struct *mm,unsigned long s) {
 for(int i=0;i<mm->n;i++) if(mm->v[i].vm_end>s) return &mm->v[i]; return NULL;
}
static pagemap_entry_t make_pme(unsigned long f,unsigned long flags) { return f|flags; }
static int add_to_pagemap(pagemap_entry_t *e,struct pagemapread *pm) {
 assert(pm->pos<pm->len); pm->buffer[pm->pos++]=*e; return pm->pos==pm->len;
}
static int walk_page_range(struct mm_struct *mm,unsigned long s,unsigned long e,void *ops,struct pagemapread *pm) {
 for(;s<e;s+=PAGE_SIZE) { struct vm_area_struct *v=find_vma(mm,s);
  pagemap_entry_t p=v && s>=v->vm_start ? 123+s/PAGE_SIZE:0;
  int ret=add_to_pagemap(&p,pm); if(ret) return ret;
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
   struct pagemapread pm={.len=32};
   assert(susfs_pagemap_walk(&mm,first*PAGE_SIZE,last*PAGE_SIZE,&pm)==0);
   assert(pm.pos==last-first);
   for(int i=first;i<last;i++) assert(pm.buffer[i-first]==(mask&(1<<i)?0:123UL+i));
  }
 }
 struct vm_area_struct v[]={{PAGE_SIZE,2*PAGE_SIZE,&hidden},{3*PAGE_SIZE,5*PAGE_SIZE,&visible}};
 struct mm_struct mm={v,2}; struct pagemapread pm={.len=6};
 assert(susfs_pagemap_walk(&mm,0,6*PAGE_SIZE,&pm)==1 && pm.pos==6);
 assert(pm.buffer[0]==0 && pm.buffer[1]==0 && pm.buffer[2]==0 && pm.buffer[3]==126 && pm.buffer[4]==127 && pm.buffer[5]==0);
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
struct path { struct dentry *dentry; int mnt; };
struct nameidata { int dfd,state; struct filename *name; struct path path; };
struct open_flags { int open_flag,lookup_flags,mode; };
struct file { int f_flags,f_mode; struct path f_path; };
static struct filename original={1},fake;
static struct dentry dent;
static struct file result;
static struct nameidata *active;
static int redirect=1,root_preset,attempt,allocated,freed,refs,lookup_error,open_error,lookup_calls;
static unsigned expected_flags;
static void set_nameidata(struct nameidata *nd,int dfd,struct filename *name,void *root) {
 assert(name->alive); nd->name=name; nd->dfd=dfd; nd->state=root_preset; nd->path=(struct path){&dent,1}; active=nd;
}
static void restore_nameidata(void) { active=NULL; }
static int current_cred(void) {return 0;}
static struct file *alloc_empty_file(int flags,int cred) {result=(struct file){flags,FMODE_OPENED,{&dent,1}};return &result;}
static int path_lookupat(struct nameidata *nd,unsigned flags,struct path *p) {
 assert(nd->name->alive); refs++; *p=(struct path){&dent,1}; return 0;
}
static struct filename *susfs_open_redirect_spoof_do_sys_openat(int *inode) { assert(!fake.alive); fake.alive=1;allocated++;return &fake;}
static void putname(struct filename *name) { assert(name->alive); assert(!active || active->name!=name); name->alive=0;freed++; }
static void path_put(struct path *p) { assert(refs>0);refs--; }
static int filename_lookup(int dfd,struct filename *name,unsigned flags,struct path *p,void *root) {
 assert(dfd==73 && name==&fake && name->alive && root==NULL);
 assert(active->name==&original && flags==expected_flags); lookup_calls++;
 if(lookup_error) return lookup_error;
 refs++; *p=(struct path){&dent,1}; return 0;
}
static int mnt_want_write(int mnt) {return 0;}
static void mnt_drop_write(int mnt) {}
static int mnt_idmap(int mnt) {return 0;}
static int vfs_tmpfile(int id,struct path *p,struct file *f,int mode) {return open_error;}
static void audit_inode(struct filename *name,struct dentry *d,int flag) {assert(name->alive);}
static int vfs_open(struct path *p,struct file *f) {return open_error;}
static const char *path_init(struct nameidata *nd,unsigned flags) {assert(nd->name->alive);return "name";}
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
  set_nameidata(&nd,73,&original,NULL); expected_flags=64|(mode?LOOKUP_DIRECTORY:0);
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
static struct mount *alloc_common(int ida) {allocated=(struct mount){0};ida_owned=ida;if(flip)key=!key;return &allocated;}
static struct mount *alloc_vfsmnt(char *name) {return alloc_common(1);}
static struct mount *susfs_alloc_non_unshare_ksu_vfsmnt(char *name) {return alloc_common(1);}
static struct mount *susfs_alloc_unshare_ksu_vfsmnt(char *name,int id) {return alloc_common(0);}
static int mnt_alloc_group_id(struct mount *m) {return group_error;}
static void mnt_free_id(struct mount *m) {if(!(m->mnt.mnt_flags&VFSMOUNT_MNT_FLAGS_KSU_UNSHARED_MNT)){assert(ida_owned);free_count++;}}
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
struct file {int hidden,f_mapping;};
struct vm_area_struct {unsigned long vm_start,vm_end,vm_flags;struct file *vm_file;void *vm_mm;};
struct mem_size_stats {unsigned long swap;};
struct mm_walk_ops {int unused;};
static struct mm_walk_ops smaps_walk_ops,smaps_shmem_walk_ops;
static int calls;
static int shmem_mapping(int x) {return x;}
static unsigned long shmem_swap_usage(struct vm_area_struct *v) {return 42;}
static int walk_page_range(void *mm,unsigned long s,unsigned long e,const struct mm_walk_ops *ops,struct mem_size_stats *m) {calls++;m->swap+=e-s;return 0;}
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
