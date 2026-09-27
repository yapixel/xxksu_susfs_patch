"""Execute generated remote-memory and native proc callers; no final-patch input."""
from pathlib import Path
import unittest
from test_lifecycle import function, run_c, target_headers, target_sources
from v2.pipeline import generate_candidate_patch
from v2.engine.diff_parser import parse_patch
from v2.engine.emitter import emit_patch
from v2.model.patch import Patch
from v2.source.bundle import create_source_bundle
from v2.source.patch_apply import apply_patch_to_bundle

ROOT = Path(__file__).resolve().parents[4]


def generated_sources(gki):
    target = "gki-android16-6.12" if gki else "sultan-android14-6.1"
    patch_id = "gki-android16-6.12-r38-patch51" if gki else "sultan-android14-6.1-patch51"
    upstream = ROOT / ".github/fixtures" / ("r38" if gki else "sultan")
    patch = parse_patch(generate_candidate_patch(patch_id, upstream, ROOT))
    paths = ("mm/memory.c", "fs/proc/base.c")
    patch.files = [f for f in patch.files if f.old_path.removeprefix("a/") in paths]
    sources = target_sources(gki)
    bundle = create_source_bundle(target, "6.12" if gki else "6.1", {p: sources[p] for p in paths})
    return {f.path: f.content for f in apply_patch_to_bundle(bundle, emit_patch(patch)).files}


def harness(sources, gki, *, enabled=True, io=True):
    headers = target_headers(gki)
    signature = headers["get_user_pages_remote"].removesuffix(";")
    # The declaration comes verbatim from the authenticated target header;
    # parameter names below follow that target's actual declaration.
    gup = signature + " { assert(!locked && nr_pages == 1); assert(lock_depth == 1); "
    gup += "gup_calls++; last_flags = gup_flags; struct vm_area_struct *v = vma_lookup(mm, start); "
    gup += "if (!v || v->vm_ops) return -1; refs++; *pages = &pages_data[start/PAGE_SIZE]; "
    if not gki:
        gup += "if (vmas) *vmas = v; "
    gup += "return 1; }\n"
    wrapper = headers["get_user_page_vma_remote"] if gki else ""
    memory = sources["mm/memory.c"]
    native = function(memory, "int __access_remote_vm(") + function(memory, "int access_remote_vm(")
    caller = function(sources["fs/proc/base.c"], "static ssize_t mem_rw(")
    return (f"#define GKI {int(gki)}\n#define HIDE {int(enabled)}\n" +
            ("#define CONFIG_KSU_SUSFS_SUS_MAP\n" if enabled else "") +
            ("#define CONFIG_HAVE_IOREMAP_PROT\n" if io else "") + MOCKS + gup + wrapper +
            native + caller + CASES)


class RemoteMemoryTests(unittest.TestCase):
    def test_generated_remote_access_and_proc_caller_both_targets(self):
        for gki in (False, True):
            sources = generated_sources(gki)
            for enabled in (True, False):
                for io in (True, False):
                    with self.subTest(gki=gki, enabled=enabled, io=io):
                        self.assertEqual(run_c(harness(sources, gki, enabled=enabled, io=io)), 0)


MOCKS = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#define PAGE_SIZE 16
#define FOLL_WRITE 1
#define FOLL_FORCE 2
#define FOLL_NOWAIT 4
#define EINVAL 22
#define EIO 5
#define ENOMEM 12
#define EFAULT 14
#define GFP_KERNEL 0
#define __user
#define unlikely(x) (x)
#define WARN_ON_ONCE(x) (x)
#define ERR_PTR(x) ((struct page *)(intptr_t)(x))
#define IS_ERR(p) ((intptr_t)(p) < 0)
#define min_t(t,a,b) ((t)(a)<(t)(b)?(t)(a):(t)(b))
struct mm_struct { int unused; } mm;
struct file { int hidden; struct mm_struct *private_data; } visible, hidden;
struct vm_area_struct;
struct vm_operations_struct { int (*access)(struct vm_area_struct *, unsigned long, void *, int, int); } ops;
struct vm_area_struct { unsigned long vm_start, vm_end; struct file *vm_file; struct vm_operations_struct *vm_ops; } vmas_data[8];
struct page { char data[PAGE_SIZE]; } pages_data[8];
static int present[8], lock_depth, refs, gup_calls, io_calls, dirty, expand_mode;
static unsigned last_flags;
#define file_inode(f) (f)
#define SUSFS_IS_INODE_SUS_MAP(f) ((f)->hidden)
static int mmap_read_lock_killable(struct mm_struct *m) { assert(!lock_depth); lock_depth=1; return 0; }
static void mmap_read_unlock(struct mm_struct *m) { assert(lock_depth==1); lock_depth=0; }
static unsigned long untagged_addr_remote(struct mm_struct *m, unsigned long a) { return a; }
static struct vm_area_struct *vma_lookup(struct mm_struct *m, unsigned long a) {
 assert(lock_depth==1); return a/PAGE_SIZE<8 && present[a/PAGE_SIZE] ? &vmas_data[a/PAGE_SIZE] : NULL;
}
static struct vm_area_struct *expand_stack(struct mm_struct *m, unsigned long a) {
 assert(lock_depth==1); lock_depth=0; /* real expansion drops and reacquires */
 if (expand_mode && a/PAGE_SIZE==4) {
   present[4]=1; vmas_data[4].vm_file=expand_mode==2?&hidden:NULL; lock_depth=1;
   return &vmas_data[4];
 }
 return NULL;
}
static void put_page(struct page *p) { assert(refs>0); refs--; }
static void *kmap(struct page *p) { assert(refs>0); return p->data; }
#define kmap_local_page kmap
static void kunmap(struct page *p) { assert(refs>0); }
static void unmap_and_put_page(struct page *p, void *a) { put_page(p); }
static void set_page_dirty_lock(struct page *p) { dirty++; }
#define copy_to_user_page(v,p,a,d,s,n) memcpy(d,s,n)
#define copy_from_user_page(v,p,a,d,s,n) memcpy(d,s,n)
static unsigned long __get_free_page(int f) { return (unsigned long)malloc(PAGE_SIZE); }
static void free_page(unsigned long p) { free((void *)p); }
static int mmget_not_zero(struct mm_struct *m) { return 1; }
static void mmput(struct mm_struct *m) {}
static int proc_mem_foll_force(struct file *f, struct mm_struct *m) { return 1; }
static int copy_from_user(void *d, const void *s, size_t n) { memcpy(d,s,n); return 0; }
#define copy_to_user copy_from_user
static int io_access(struct vm_area_struct *v, unsigned long a, void *buf, int n, int write) {
 assert(lock_depth==1); io_calls++; if(n>v->vm_end-a)n=v->vm_end-a;
 if(write)memcpy(pages_data[a/PAGE_SIZE].data+a%PAGE_SIZE,buf,n);
 else memcpy(buf,pages_data[a/PAGE_SIZE].data+a%PAGE_SIZE,n);
 return n;
}
static void reset(void) {
 assert(refs==0 && lock_depth==0); gup_calls=io_calls=dirty=expand_mode=0; last_flags=0;
 visible.hidden=0; hidden.hidden=1; ops.access=io_access;
 for(int i=0;i<8;i++) {
  present[i]=i<4; vmas_data[i]=(struct vm_area_struct){i*PAGE_SIZE,(i+1)*PAGE_SIZE,i==1?&hidden:&visible,NULL};
  memset(pages_data[i].data,'a'+i,PAGE_SIZE);
 }
 vmas_data[3].vm_file=NULL;
}
"""

CASES = r"""
int main(void) {
 char buf[128]; struct file mem={.private_data=&mm}; loff_t pos; int n;
 for(int write=0;write<=1;write++) {
  reset(); memset(buf,'W',sizeof(buf)); pos=3;
  assert(mem_rw(&mem,buf,7,&pos,write)==7 && pos==10);
  assert(last_flags==(FOLL_FORCE|(write?FOLL_WRITE:0)));
  assert(refs==0 && lock_depth==0 && dirty==write);
  if(write)assert(pages_data[0].data[3]=='W');else assert(buf[0]=='a');
  reset(); memset(buf,'W',sizeof(buf)); pos=17;
  assert(mem_rw(&mem,buf,7,&pos,write)==(HIDE?-EIO:7));
  assert(pos==(HIDE?17:24)); assert(!refs&&!lock_depth);
  if(HIDE)assert(gup_calls==0 && pages_data[1].data[1]=='b' && buf[0]=='W');
  reset(); memset(buf,'W',sizeof(buf)); pos=12;
  assert(mem_rw(&mem,buf,24,&pos,write)==(HIDE?4:24));
  assert(pos==(HIDE?16:36)); assert(!refs&&!lock_depth);
  if(HIDE)assert(pages_data[1].data[0]=='b' && buf[4]=='W');
  reset(); memset(buf,'W',sizeof(buf)); pos=16;
  assert(mem_rw(&mem,buf,24,&pos,write)==(HIDE?-EIO:24));
  assert(pos==(HIDE?16:40)); assert(!refs&&!lock_depth);
  reset(); pos=50; assert(mem_rw(&mem,buf,5,&pos,write)==5 && pos==55);
  reset(); pos=64; assert(mem_rw(&mem,buf,3,&pos,write)==-EIO && pos==64);
  reset(); expand_mode=1; pos=64; assert(mem_rw(&mem,buf,3,&pos,write)==3 && pos==67);
  reset(); expand_mode=2; pos=64;
  assert(mem_rw(&mem,buf,3,&pos,write)==(HIDE?-EIO:3)); assert(!refs&&!lock_depth);
  reset(); expand_mode=1;
  n=access_remote_vm(&mm,60,buf,8,write?FOLL_WRITE:0);
  assert(n==(GKI?8:4)); assert(!refs&&!lock_depth);
  for(int hidden_io=0;hidden_io<=1;hidden_io++) {
   reset(); vmas_data[0].vm_ops=&ops; vmas_data[0].vm_file=hidden_io?&hidden:&visible;
   pos=2;
#ifdef CONFIG_HAVE_IOREMAP_PROT
   n=HIDE&&hidden_io?-EIO:5;
#else
   n=-EIO;
#endif
   assert(mem_rw(&mem,buf,5,&pos,write)==n);
   assert(pos==(n>0?7:2)); assert(!refs&&!lock_depth);
   if(HIDE&&hidden_io)assert(!gup_calls&&!io_calls);
  }
 }
 return 0;
}
"""
