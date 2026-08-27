#!/usr/bin/env python3
"""
deinline_50_to_51.py
Deterministic De-inlining & Transformation Algorithm:
Parses upstream susfs4ksu 50 kernel patch and dynamically transforms it into a clean,
de-inlined 51 kernel hooks patch tailored for Sultan or Generic GKI kernels.
Automatically computes and embeds standard Git diffstat in the patch header.
"""

import sys
import os
import re
import argparse
import subprocess

def fix_hunk_line_counts(hunk_meta, hunk_body):
    """Accurately recalculates hunk header @@ -x,y +a,b @@ based on body lines."""
    m = re.match(r'@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@(.*)', hunk_meta)
    if not m:
        return hunk_meta
    old_start = int(m.group(1))
    new_start = int(m.group(3))
    tail = m.group(5)

    lines = [l for l in hunk_body.splitlines() if l != '']
    old_cnt = sum(1 for l in lines if not l.startswith('+'))
    new_cnt = sum(1 for l in lines if not l.startswith('-'))
    return f"@@ -{old_start},{old_cnt} +{new_start},{new_cnt} @@{tail}"

SULTAN_EXTRA_CHUNKS = {
    'drivers/input/input.c': """diff --git a/drivers/input/input.c b/drivers/input/input.c
index 78be582b5766..ca17a064ac9a 100644
--- a/drivers/input/input.c
+++ b/drivers/input/input.c
@@ -387,6 +387,8 @@ static void input_event_dispose(struct input_dev *dev, int disposition,
 	}
 }
 
+extern struct static_key_false ksu_input_hook_key_false;
+
 void input_handle_event(struct input_dev *dev,
 			unsigned int type, unsigned int code, int value)
 {
""",
    'fs/susfs.c': """diff --git a/fs/susfs.c b/fs/susfs.c
index 737a217343f1..4c2895f80f7d 100755
--- a/fs/susfs.c
+++ b/fs/susfs.c
@@ -23,6 +23,7 @@
 #include <linux/susfs.h>
 #include "fuse/fuse_i.h"
 #include "mount.h"
+#include <uapi/linux/magic.h>
 
 extern bool susfs_is_current_ksu_domain(void);
 extern void setup_selinux(const char *domain, struct cred *cred);
@@ -131,7 +132,7 @@ void susfs_add_sus_path_loop(void __user **user_info) {
 	SUSFS_LOGI("CMD_SUSFS_ADD_SUS_PATH_LOOP -> ret: %d\\n", info.err);
 }
 
-static void susfs_run_sus_path_loop(void) {
+void susfs_run_sus_path_loop(void) {
 	struct st_susfs_sus_path_list *cursor = NULL;
 	struct path path;
 	struct inode *inode;
@@ -610,6 +611,62 @@ void susfs_sus_kstat_spoof_show_map_vma(struct inode *inode, dev_t *out_dev, uns
 }
 #endif // #ifdef CONFIG_KSU_SUSFS_SUS_KSTAT
 
+/* try_umount */
+#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT
+static DEFINE_SPINLOCK(susfs_spin_lock_try_umount);
+extern void try_umount(const char *mnt, int flags);
+static LIST_HEAD(LH_TRY_UMOUNT_PATH);
+void susfs_add_try_umount(void __user **user_info) {
+	struct st_susfs_try_umount info = {0};
+	struct st_susfs_try_umount_list *new_list = NULL;
+
+	if (copy_from_user(&info, (struct st_susfs_try_umount __user*)*user_info, sizeof(info))) {
+		info.err = -EFAULT;
+		goto out_copy_to_user;
+	}
+
+	if (info.mnt_mode == TRY_UMOUNT_DEFAULT) {
+		info.mnt_mode = 0;
+	} else if (info.mnt_mode == TRY_UMOUNT_DETACH) {
+		info.mnt_mode = MNT_DETACH;
+	} else {
+		SUSFS_LOGE("Unsupported mnt_mode: %d\\n", info.mnt_mode);
+		info.err = -EINVAL;
+		goto out_copy_to_user;
+	}
+
+	new_list = kzalloc(sizeof(struct st_susfs_try_umount_list), GFP_KERNEL);
+	if (!new_list) {
+		info.err = -ENOMEM;
+		goto out_copy_to_user;
+	}
+
+	memcpy(&new_list->info, &info, sizeof(info));
+
+	INIT_LIST_HEAD(&new_list->list);
+	spin_lock(&susfs_spin_lock_try_umount);
+	list_add_tail(&new_list->list, &LH_TRY_UMOUNT_PATH);
+	spin_unlock(&susfs_spin_lock_try_umount);
+	SUSFS_LOGI("target_pathname: '%s', umount options: %d, is successfully added to LH_TRY_UMOUNT_PATH\\n", new_list->info.target_pathname, new_list->info.mnt_mode);
+	info.err = 0;
+out_copy_to_user:
+	if (copy_to_user(&((struct st_susfs_try_umount __user*)*user_info)->err, &info.err, sizeof(info.err))) {
+		info.err = -EFAULT;
+	}
+	SUSFS_LOGI("CMD_SUSFS_ADD_TRY_UMOUNT -> ret: %d\\n", info.err);
+}
+
+void susfs_try_umount(uid_t uid) {
+	struct st_susfs_try_umount_list *cursor = NULL;
+
+	// We should umount in reversed order
+	list_for_each_entry_reverse(cursor, &LH_TRY_UMOUNT_PATH, list) {
+		SUSFS_LOGI("umounting '%s' for uid: %u\\n", cursor->info.target_pathname, uid);
+		try_umount(cursor->info.target_pathname, cursor->info.mnt_mode);
+	}
+}
+#endif // #ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT
+
 /* spoof_uname */
 #ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME
 static struct st_susfs_uname my_uname = {0};
@@ -1197,6 +1254,11 @@ void susfs_get_enabled_features(void __user **user_info) {
 	if (info->err) goto out_copy_to_user;
 	buf_ptr = info->enabled_features + copied_size;
 #endif
+#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT
+	info->err = copy_config_to_buf("CONFIG_KSU_SUSFS_TRY_UMOUNT\\n", buf_ptr, &copied_size, SUSFS_ENABLED_FEATURES_SIZE);
+	if (info->err) goto out_copy_to_user;
+	buf_ptr = info->enabled_features + copied_size;
+#endif
 #ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME
 	info->err = copy_config_to_buf("CONFIG_KSU_SUSFS_SPOOF_UNAME\\n", buf_ptr, &copied_size, SUSFS_ENABLED_FEATURES_SIZE);
 	if (info->err) goto out_copy_to_user;
""",
    'include/linux/susfs.h': """diff --git a/include/linux/susfs.h b/include/linux/susfs.h
index 6ede62945a68..a0c7dfa9790f 100755
--- a/include/linux/susfs.h
+++ b/include/linux/susfs.h
@@ -102,6 +102,20 @@ struct st_susfs_sus_kstat_hlist {
 };
 #endif
 
+/* try_umount */
+#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT
+struct st_susfs_try_umount {
+	char                                    target_pathname[SUSFS_MAX_LEN_PATHNAME];
+	int                                     mnt_mode;
+	int                                     err;
+};
+
+struct st_susfs_try_umount_list {
+	struct list_head                        list;
+	struct st_susfs_try_umount              info;
+};
+#endif
+
 /* spoof_uname */
 #ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME
 struct st_susfs_uname {
@@ -201,6 +215,12 @@ void susfs_add_sus_kstat(void __user **user_info);
 void susfs_update_sus_kstat(void __user **user_info);
 #endif
 
+/* try_umount */
+#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT
+void susfs_add_try_umount(void __user **user_info);
+void susfs_try_umount(uid_t uid);
+#endif // #ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT
+
 /* spoof_uname */
 #ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME
 void susfs_set_uname(void __user **user_info);
"""
}

def deinline_patch(input_patch, output_patch, target="gki"):
    if not os.path.isfile(input_patch):
        print(f"❌ Error: Input patch {input_patch} not found")
        sys.exit(1)

    print(f"📖 Reading upstream 50 patch: {input_patch} (Target: {target})")
    with open(input_patch, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    excluded_files = [
        'fs/exec.c',
        'fs/open.c',
        'fs/read_write.c',
        'kernel/reboot.c',
        'security/selinux/avc.c',
        'security/selinux/hooks.c',
        'security/selinux/selinuxfs.c',
        'security/selinux/ss/services.c'
    ]

    file_chunks = content.split('diff --git ')
    out_chunks = []

    # Insert drivers/input/input.c for 6.1 kernels (Sultan & Pantah / GKI 6.1)
    if ("6.1" in target or "sultan" in target.lower()) and 'drivers/input/input.c' in SULTAN_EXTRA_CHUNKS:
        out_chunks.append(SULTAN_EXTRA_CHUNKS['drivers/input/input.c'].strip())

    for fchunk in file_chunks[1:]:
        first_line = fchunk.splitlines()[0] if fchunk.splitlines() else ''
        file_path = ''
        parts = first_line.split(' ')
        if len(parts) >= 2 and parts[1].startswith('b/'):
            file_path = parts[1][2:]
        elif len(parts) >= 1 and parts[0].startswith('a/'):
            file_path = parts[0][2:]

        # Rule 1: Exclude entire files
        if any(file_path == exc or file_path.startswith(exc + '/') for exc in excluded_files):
            continue

        # Split file into hunks
        hunk_chunks = re.split(r'\n(@@\s+-[0-9,]+\s+\+[0-9,]+\s+@@[^\n]*)', '\n' + fchunk)
        file_header = hunk_chunks[0].lstrip('\n')
        kept_hunks = []

        for i in range(1, len(hunk_chunks), 2):
            hunk_meta = hunk_chunks[i]
            hunk_body = hunk_chunks[i+1].lstrip('\n')

            # In fs/namespace.c, align Google Pixel GKI 6.1 trace/hooks/blk.h anchor
            if file_path == 'fs/namespace.c' and ("pantah" in target.lower() or "gki-android14-6.1" in target.lower()):
                if '#include "internal.h"' in hunk_body and '<trace/hooks/blk.h>' not in hunk_body:
                    hunk_body = hunk_body.replace(
                        ' #include "internal.h"\n',
                        ' #include "internal.h"\n #include <trace/hooks/blk.h>\n'
                    )

            # In fs/proc/fd.c, wrap unused variables in proper CONFIG_KSU_SUSFS_* guards
            if file_path == 'fs/proc/fd.c':
                hunk_body = re.sub(
                    r'(\+\tstruct mount \*mnt = NULL;)',
                    r'+#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT\n\1\n+#endif // #ifdef CONFIG_KSU_SUSFS_SUS_MOUNT',
                    hunk_body
                )
                hunk_body = re.sub(
                    r'(\+\tint mnt_id = 0;\n\+\tunsigned long ino = 0;)',
                    r'+#ifdef CONFIG_KSU_SUSFS_OPEN_REDIRECT\n\1\n+#endif // #ifdef CONFIG_KSU_SUSFS_OPEN_REDIRECT',
                    hunk_body
                )

            added_lines = [l[1:] for l in hunk_body.splitlines() if l.startswith('+') and not l.startswith('+++')]
            added_text = '\n'.join(added_lines)

            # Rule 2: Exclude pure KSU inline hooks inside functions
            is_ksu_hook = False
            if re.search(r'ksu_handle_|ksu_is_input_hook|ksu_is_init_rc_hook', added_text):
                is_ksu_hook = True
            elif '#ifdef CONFIG_KSU_SUSFS' in added_text and not '#include' in added_text and not 'CONFIG_KSU_SUSFS_' in added_text and not 'obj-$(CONFIG_KSU_SUSFS)' in added_text and not 'susfs_is_sus_su_ready' in added_text:
                is_ksu_hook = True

            if not is_ksu_hook:
                adjusted_meta = fix_hunk_line_counts(hunk_meta, hunk_body)
                kept_hunks.append(adjusted_meta + '\n' + hunk_body)

        if kept_hunks:
            full_file_diff = 'diff --git ' + file_header.strip() + '\n' + '\n'.join(kept_hunks)
            out_chunks.append(full_file_diff.strip())

        # Append extra Sultan chunks for fs/susfs.c and include/linux/susfs.h in order
        if file_path == 'fs/statfs.c':
            if 'fs/susfs.c' in SULTAN_EXTRA_CHUNKS:
                out_chunks.append(SULTAN_EXTRA_CHUNKS['fs/susfs.c'].strip())
            if 'include/linux/susfs.h' in SULTAN_EXTRA_CHUNKS:
                out_chunks.append(SULTAN_EXTRA_CHUNKS['include/linux/susfs.h'].strip())

    diff_body = '\n\n'.join(out_chunks) + '\n'

    # Compute genuine Git diffstat dynamically
    try:
        diffstat = subprocess.check_output(['git', 'apply', '--stat'], input=diff_body, text=True).strip('\n')
    except Exception:
        diffstat = ""

    import datetime
    current_utc_date = datetime.datetime.now(datetime.timezone.utc).strftime('%a, %d %b %Y %H:%M:%S +0000')

    git_subject = f"SUSFS de-inlined hooks for {target}"
    git_header = f"""From: yapixel <yapixel@users.noreply.github.com>
Date: {current_utc_date}
Subject: [PATCH] {git_subject}

---
{diffstat}

"""

    final_patch = git_header + diff_body

    os.makedirs(os.path.dirname(os.path.abspath(output_patch)), exist_ok=True)
    with open(output_patch, 'w', encoding='utf-8') as f:
        f.write(final_patch)

    print(f"✨ Pure Deinlined 51 patch generated: {output_patch} ({len(final_patch.splitlines())} lines)")

def main():
    parser = argparse.ArgumentParser(description="De-inline and transform upstream 50 patch into 51 Sultan/GKI patch")
    parser.add_argument("--input", "-i", required=True, help="Path to upstream 50 patch")
    parser.add_argument("--output", "-o", required=True, help="Path to output 51 patch")
    parser.add_argument("--target", "-t", default="gki", help="Target kernel type (e.g. sultan or gki)")
    args = parser.parse_args()

    deinline_patch(args.input, args.output, args.target)

if __name__ == "__main__":
    main()
