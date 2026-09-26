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
index f0ea0561195b..4c2895f80f7d 100755
--- a/fs/susfs.c
+++ b/fs/susfs.c
@@ -24,6 +24,7 @@
 #include <linux/susfs.h>
 #include "fuse/fuse_i.h"
 #include "mount.h"
+#include <uapi/linux/magic.h>
 
 extern bool susfs_is_current_ksu_domain(void);
 extern void setup_selinux(const char *domain, struct cred *cred);
@@ -134,7 +135,7 @@ void susfs_add_sus_path_loop(void __user **user_info) {
 	SUSFS_LOGI("CMD_SUSFS_ADD_SUS_PATH_LOOP -> ret: %d\\n", info.err);
 }
 
-static void susfs_run_sus_path_loop(void) {
+void susfs_run_sus_path_loop(void) {
 	struct st_susfs_sus_path_list *cursor = NULL;
 	struct path path;
 	struct inode *inode;
@@ -707,6 +708,62 @@ void susfs_sus_kstat_spoof_proc_fd_seq_show(int *out_target_mnt_id, unsigned lo
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
@@ -1267,6 +1324,11 @@ void susfs_get_enabled_features(void __user **user_info) {
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
index 77e11b6e931b..a0c7dfa9790f 100755
--- a/include/linux/susfs.h
+++ b/include/linux/susfs.h
@@ -104,6 +104,20 @@ struct st_susfs_sus_kstat_hlist {
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
@@ -203,6 +217,12 @@ void susfs_add_sus_kstat(void __user **user_info);
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

GKI_6_12_EXTRA_CHUNKS = {
    'drivers/input/input.c': (
        "diff --git a/drivers/input/input.c b/drivers/input/input.c\n"
        "index 372c9df..e59059f 100644\n"
        "--- a/drivers/input/input.c\n"
        "+++ b/drivers/input/input.c\n"
        "@@ -354,6 +354,8 @@ static void input_event_dispose(struct input_dev *dev, int disposition,\n"
        " \t}\n"
        " }\n"
        "\n"
        "+extern struct static_key_false ksu_input_hook_key_false;\n"
        "+\n"
        " void input_handle_event(struct input_dev *dev,\n"
        " \t\t\tunsigned int type, unsigned int code, int value)\n"
        " {\n"
    )
}

def is_sultan_target(target: str) -> bool:
    return "sultan" in target.lower()

def is_gki_6_12_target(target: str) -> bool:
    t = target.lower()
    return "6.12" in t or t in ("gki", "gki-android16-6.12")

def deinline_patch_content(content: str, target: str = "gki", date_str: str | None = None) -> str:
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

    # Target-isolated drivers/input/input.c insertion
    if is_sultan_target(target) and 'drivers/input/input.c' in SULTAN_EXTRA_CHUNKS:
        out_chunks.append(SULTAN_EXTRA_CHUNKS['drivers/input/input.c'].strip())
    elif is_gki_6_12_target(target) and 'drivers/input/input.c' in GKI_6_12_EXTRA_CHUNKS:
        out_chunks.append(GKI_6_12_EXTRA_CHUNKS['drivers/input/input.c'].strip())

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

            # In fs/proc/fd.c, wrap unused variables in proper CONFIG_KSU_SUSFS_* guards
            # Use direct string replacement to avoid regex template unescaping of '\n'
            if file_path == 'fs/proc/fd.c':
                target1 = '+\tstruct mount *mnt = NULL;'
                repl1 = '+#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT\n+\tstruct mount *mnt = NULL;\n+#endif // #ifdef CONFIG_KSU_SUSFS_SUS_MOUNT'
                hunk_body = hunk_body.replace(target1, repl1)

                target2 = '+\tint mnt_id = 0;\n+\tunsigned long ino = 0;'
                repl2 = '+#ifdef CONFIG_KSU_SUSFS_OPEN_REDIRECT\n+\tint mnt_id = 0;\n+\tunsigned long ino = 0;\n+#endif // #ifdef CONFIG_KSU_SUSFS_OPEN_REDIRECT'
                hunk_body = hunk_body.replace(target2, repl2)

            # Fail closed if any hunk line contains a split/unterminated character literal
            for line in hunk_body.splitlines():
                if re.search(r"""(?:seq_putc|seq_pad)\s*\([^,]+,\s*'(\\[^']*)?\s*$""", line):
                    raise ValueError(f"Corrupt character literal with unescaped newline in hunk for {file_path}: {line}")


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

        # Append extra Sultan chunks for fs/susfs.c and include/linux/susfs.h in order (Sultan ONLY)
        # Standalone SuSFS source files must never be emitted into GKI Patch 51.
        has_super_c = 'diff --git a/fs/super.c' in content
        trigger_file = 'fs/super.c' if has_super_c else 'fs/statfs.c'
        if file_path == trigger_file and is_sultan_target(target):
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
    if date_str is None:
        date_str = datetime.datetime.now(datetime.timezone.utc).strftime('%a, %d %b %Y %H:%M:%S +0000')

    git_subject = f"SUSFS de-inlined hooks for {target}"
    git_header = f"""From: yapixel <yapixel@users.noreply.github.com>
Date: {date_str}
Subject: [PATCH] {git_subject}

---
{diffstat}

"""

    return git_header + diff_body


def deinline_patch(input_patch, output_patch, target="gki"):
    if not os.path.isfile(input_patch):
        print(f"❌ Error: Input patch {input_patch} not found")
        sys.exit(1)

    print(f"📖 Reading upstream 50 patch: {input_patch} (Target: {target})")
    with open(input_patch, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    date_str = None
    if os.path.isfile(output_patch):
        with open(output_patch, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if line.startswith('Date: '):
                    date_str = line[len('Date: '):].strip()
                    break

    final_patch = deinline_patch_content(content, target=target, date_str=date_str)

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
