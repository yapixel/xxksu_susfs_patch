# yapixel/xxksu_susfs_patch 程式碼審查報告

- 審查對象：`github.com/yapixel/xxksu_susfs_patch` @ `fa0f719`（2026-09-29）
- 審查日期：2026-10-02
- 比對基準（全部實際取回後逐一核對，非憑記憶）：
  - xxKSU：`backslashxx/KernelSU` 作者鎖定的 `f263bdb9`，以及目前 master `5da23982`
  - SuSFS：`simonpunk/susfs4ksu` `gki-android16-6.12` @ `b213c541`、`sultan-shiba-susfs-minimal` @ `a8324101`，以及 Patch 11 宣稱的 lineage `c8f64e41`
  - 上游 Patch 10：`kernel_patches/KernelSU/10_enable_susfs_for_ksu.patch` @ `b213c541`
  - 核心原始碼：Google `android16-6.12-2025-09_r38`（commit `98d5b9e071f1`）、`kerneltoast/android_kernel_google_tensynos` @ `af5c65b9`
- 方法：建立「乾淨原始碼 + 上游 Patch 50」與「乾淨原始碼 + 本倉庫 Patch 51」兩棵樹，對每個差異 hunk 逐一分類；Patch 11 對照上游 Patch 10 與 xxKSU 原始碼逐段閱讀；Python 測試實際執行（macOS）。**未建置核心，未實機測試**；標註「讀碼推論」的項目未經執行驗證。

> 分級：**High** = 可能導致錯誤行為／建置失敗／洩漏；**Medium** = 邏輯不一致或可預見的維護風險；**Low** = 冗餘、風格、說明文字；**Info** = 觀察，不一定需要改。
> 「作者已文件化的刻意設計」與「錯誤」分開列出；「上游繼承」表示問題原樣來自 simonpunk 的 Patch 50 / 核心，不是本倉庫引入，但會隨本倉庫的產物出貨。

## 總結：建議優先處理

| # | 等級 | 項目 | 來源 | 章節 |
|---|---|---|---|---|
| 1 | High | 鎖定的 xxKSU `f263bdb9` 已因上游 force-push 變成不可達；Patch 11、Patch 51 Kbuild gate、clean-room 三條路徑都靠 SHA 抓它，一旦被 GC 會一起壞 | 本倉庫 | 2.1、5.1 |
| 2 | Medium | GKI Patch 51 刪掉上游 `mnt_id < DEFAULT_KSU_MNT_ID` 無鎖提早返回，app 每次 `statfs()` 都寫鎖全域 `mount_lock`；Sultan 版有保留，兩目標不一致 | 本倉庫 | 4.1 |
| 3 | Medium | Sultan Patch 51 改寫 SuSFS 核心，復活上游已退役的 `TRY_UMOUNT`（死碼、無法連結、走訪未上鎖），並把 `susfs_run_sus_path_loop` 改成全域 | 本倉庫 | 3.1 |
| 4 | Medium | Patch 11 外層條件 `\|\| new_uid == WEBVIEW_ZYGOTE_UID` 讓非 zygote 程序被標記「已卸載」但實際未卸載 | 本倉庫 | 1.1 |
| 5 | Medium | open-redirect 在 RCU-walk 期間呼叫 `getname_kernel()`（`GFP_KERNEL`），兩個目標都有 | 上游繼承 | 3.2、4.2 |
| 6 | Medium | 「GKI 6.12 = Pixel 9」與 Google 官方表格不符（Pixel 9 為 `android14-6.1`） | 本倉庫 | 4.5 |
| 7 | Medium | watcher 不檢查可達性、漂移時 exit 0、Patch 10 比對在缺 baseline 時靜默跳過、`ksu_commit` 覆寫只改 commit 欄位、Patch 11 模板沒有對上游 Patch 10 做語意檢查 | 本倉庫 | 5.2–5.5 |
| 8 | Medium | auto-clean 刪光失敗 run 且只留 5 個成功 run，文件引用的證據 run 抽查 6 個全部 404 | 本倉庫 | 5.5 |
| 9 | Low | Kconfig 說明文字過時、死變數、`KSU=y` 依賴、`d_path` 錯誤檢查、文件與已移除閘門不同步、各種過期 hash | 混合 | 1.x、2.x、3.4、4.4 |

**整體評價**：Patch 51 的 KSU transport 移除與作者的 5 項 lifecycle 修正（`clone_mnt`、pagemap、smaps_rollup、remote-memory）經逐行核對都是正確的，而且修掉的是上游真實存在的缺陷，值得回饋給 simonpunk。兩個 Patch 51 都能 0 fuzz 套用到經驗證的乾淨原始碼。主要問題集中在三處：一是本倉庫自行加入、與上游不一致的少數改動（上表 2–4）；二是溯源/自動化對「上游歷史被重寫」缺乏防護（上表 1、7）；三是文件與中繼資料過期。

---

## 0. 已驗證為「正確／無問題」的項目（先講結論，避免重複追查）

| 項目 | 結果 |
|---|---|
| 三個生產 patch 的 sha256 與 `patches/manifest.json` | 一致 |
| Patch 11 套用到鎖定的 `f263bdb9` | `git apply --check` 通過 |
| Patch 11 套用到 xxKSU 目前 master `5da23982` | 通過（上游變動的檔案不觸及 Patch 11 的 hunk） |
| `v29-baselines/xxksu.json` 內 13 個檔案 vs 上游 `f263bdb9` | 逐位元組一致 |
| `v29-baselines/*.json` 內容 hash vs 各 `BASELINE.json` `retained_file_hashes` | 全部一致 |
| SuSFS 核心 `fs/susfs.c` 需要的 KSU 側符號（`susfs_is_current_ksu_domain`、`setup_selinux`、`ksu_cred`） | xxKSU + Patch 11 皆有非 static 的全域定義，型別一致 |
| Patch 50 引用的 `susfs_ksu_sid`、`susfs_priv_app_sid` | Patch 11 有定義 |
| Patch 11 把上游單一的 `susfs_set_batch_sid()` 拆成 5 個函式 | 核心側（Patch 50 / `susfs.c`）不引用 `susfs_set_batch_sid`，**不會**造成連結失敗 |
| `susfs.h` 中各 handler 簽章 `void (void __user **)` vs xxKSU `ksu_handle_sys_reboot(..., void __user **arg)` | 一致，直接傳 `arg` 正確 |
| Patch 11 setresuid 邏輯 vs 上游 Patch 10（`handle_zygote_setresuid` / `handle_zygote_next_setresuid`） | 對 zygote / zygote_next 子程序：isolated → 卸載、manager / 已授權 → 不標記、其餘 → `NO_SU`，語意與上游等價（manager / 已授權在 xxKSU 原生流程中先行 `goto`）；**webview zygote 處理與外層 uid 旁路除外，見 1.1 / 1.7** |
| 未知 / 已棄用的 SUSFS 指令被吞掉 `return 0` | 使用者空間 `ksu_susfs` 會先把 `info.err = ERR_CMD_NOT_SUPPORTED`，因此仍會正確回報「不支援」，非問題 |

---

## 1. Patch 11（`patches/xxksu/11_enable_susfs_for_ksu.patch`）

### 1.1 [Medium] `WEBVIEW_ZYGOTE_UID` 外層判斷條件過寬
- 位置：`11_enable_susfs_for_ksu.patch:160`
  ```c
  if (susfs_is_current_zygote_domain() || new_uid == WEBVIEW_ZYGOTE_UID) {
      handle_zygote_setresuid(new, old, new_uid, false);
  ```
- 問題：webview_zygote 本身就是由 zygote fork 出來的，`setresuid(1053)` 發生時 current 仍在 `zygote` domain，`susfs_is_current_zygote_domain()` 已經為真，所以 `|| new_uid == WEBVIEW_ZYGOTE_UID` 對正常路徑是**多餘的**；它唯一新增的效果，是讓**非 zygote 的 root 程序**只要 `setresuid(1053)` 也進入 `handle_zygote_setresuid()`。
- 失敗情境：任一 root（非 zygote）程序 `setresuid(1053, ...)` →
  1. `susfs_set_current_proc_no_su()` 一定被設；
  2. 若 `ksu_uid_should_umount(1053)` 為真，再設 `TIF_PROC_UMOUNTED` 並排程 `susfs_extra_works`；
  3. 但 xxKSU 原生 `ksu_handle_umount()` 會因 `is_zygote(old)` 為假而拒絕卸載（`kernel_umount.c:105`），
  結果是**旗標說「已卸載」但實際沒有卸載**，SuSFS 核心依 `TIF_PROC_UMOUNTED` 做的隱藏判斷與實際掛載狀態不一致。
- 上游對照：`b213c541` 的 `ksu_handle_setresuid()` 只認 `susfs_zygote_sid` / `susfs_zygote_next_sid`，沒有這個 uid 旁路。
- 建議：外層改回只判斷 domain：
  ```c
  if (susfs_is_current_zygote_domain())
      handle_zygote_setresuid(new, old, new_uid, false);
  else if (susfs_is_current_zygote_next_domain())
      handle_zygote_setresuid(new, old, new_uid, true);
  ```
  webview zygote 的卸載需求已由 `should_umount` 裡的 `new_uid == WEBVIEW_ZYGOTE_UID` 處理，不需要外層旁路。

### 1.2 [Low] `susfs_is_boot_completed_triggered` 是死變數
- 位置：`11_enable_susfs_for_ksu.patch:362-364`；來源硬編碼於 `.github/scripts/v2/adapters/xxksu.py:251`
- 上游早已以 `susfs_is_sdcard_android_data_decrypted` 取代（SuSFS 歷史提交 `b917aac` 等），`b213c541` 的 `fs/susfs.c`、`susfs.h`、Patch 50、Patch 10 **完全沒有引用**；Patch 11 定義了卻從不設為 `true`、也沒人讀。
- 影響：多一個無用的全域符號（若 `HIDE_KSU_SUSFS_SYMBOLS` 未覆蓋，還會出現在 kallsyms），並與「以 Patch 10 為語意 lineage」的說法矛盾。
- 建議：刪除該定義與 adapter 中對應 payload。

### 1.3 [Low] Kconfig 說明文字來自舊版 SuSFS，與鎖定的 lineage 不符
- 位置：`11_enable_susfs_for_ksu.patch:34-111`
- 與 `b213c541` Patch 10 Kconfig 對照（只列有實質差異者）：

| 選項 | Patch 11 說法 | 上游 `b213c541` 說法 |
|---|---|---|
| `SUS_PATH` | 「(NOT recommended)」、「temp fix for the leaks of app path in /sdcard/Android/data」、「Effective only on zygote spawned user app process」 | 無 NOT recommended；建議頻繁變動路徑用 `add_sus_path_loop`；僅對帶 `TIF_PROC_UMOUNTED` 的 zygote/zygote_next 子程序生效 |
| `SUS_MOUNT` | 「Effective on all processes」、「mnt_id ... assigned to a much bigger number」 | 只在 /sdcard 解密前對 ksu 程序的掛載配假 id；僅對帶 `TIF_PROC_UMOUNTED` 的程序生效 |
| `SUS_KSTAT` | 「Effective only on zygote spawned user app process」 | 「Effective on all processes with (uid % 100000) >= 10000」 |
| `OPEN_REDIRECT` | 「(experimental)」、「uid < 2000」 | 非 experimental；兩路徑須先存在；SELinux 權限需自行處理；「pre-defined uid scheme」 |
| `SUS_MAP` | 「zygote spawned umounted user app process」 | 另需 `(uid % 100000) >= 10000` |

- 影響：僅說明文字，不影響編譯，但會誤導使用者對各功能生效範圍的判斷（特別是 `SUS_KSTAT` / `SUS_MOUNT` 的生效對象寫反了方向）。
- 建議：從鎖定的 Patch 10 同步 help 文字；或在 adapter 加一個「help 文字與 Patch 10 一致」的檢查。

### 1.4 [Low] `KSU_SUSFS` 未限制 `KSU=y`
- 位置：`11_enable_susfs_for_ksu.patch:26-29`；xxKSU `kernel/Kconfig:3-4` 中 `config KSU` 是 `tristate`，且 xxKSU master 剛「restore LKM support」（`89701bc8`）。
- 失敗情境：`CONFIG_KSU=m` + `CONFIG_KSU_SUSFS=y`（bool 依賴 m 時 Kconfig 允許為 y）→ 核心側（Patch 51、`fs/susfs.c`）引用的 `susfs_is_current_ksu_domain`、`susfs_ksu_sid`、`ksu_cred` 等定義在模組裡 → vmlinux 連結失敗；反向模組也拿不到未 `EXPORT_SYMBOL` 的 `susfs_*`。
- 上游同樣沒加，但 xxKSU 明確支援 LKM，比上游更容易踩到。
- 建議：`depends on KSU=y`。

### 1.5 [Low] SID 快取重複實作且缺少 fallback
- 位置：`11_enable_susfs_for_ksu.patch:230-234, 295-319`
- xxKSU 已有 `cached_zygote_sid` / `cached_su_sid` / `cached_init_sid` 與 `is_sid_match()`（`selinux.c:165`），在快取為 0 時會退回字串比對；Patch 11 另起一套 `susfs_*_sid`，快取為 0 時直接比對 `current_sid() == 0`，永遠為假。
- 另外上游把這五個變數宣告為 `__read_mostly`，Patch 11 沒有（熱路徑每次 setresuid 都會讀）。
- 作者在 `PATCH51_CORRECTIONS.md` 已自評為 LOW robustness concern，此處只補充：可以直接讓 `susfs_set_zygote_sid()` 等沿用 xxKSU 的快取來源，避免兩套 SID 在 policy 重新載入時不同步。

### 1.6 [Low] 重複 log 與冗餘 include、空白混用
- `11_enable_susfs_for_ksu.patch:400-403`：新增的 `#ifdef CONFIG_KSU_DEBUG pr_info("sys_reboot: intercepted call! ...")` 對**非 SUSFS** 的呼叫會與 xxKSU 原本無條件的 `pr_info("sys_reboot: magic: ...")` 重複；SUSFS 呼叫則因提前 `return 0` 不會被原生 log 記錄（這點是好的）。建議刪除新增那段。
- `11_enable_susfs_for_ksu.patch:356-360, 387-391`：xxKSU 是 unity build（`ksu.c` 依序 `#include` 各 `.c`），`objsec.h` 已在 `ksu.c:25` 引入，`dispatch.c` / `supercall.c` 中再引一次 `objsec.h`、`<linux/namei.h>` 屬冗餘（有 include guard，不會出錯）。
- `11_enable_susfs_for_ksu.patch:374`：`        	susfs_start_sdcard_monitor_fn();` 為「8 個空白 + tab」混用；`:191` `susfs_init();` 用 4 空白，與周圍 tab 縮排不一致（`checkpatch` 會報）。

### 1.7 [刻意設計，非錯誤] WebView zygote 會被卸載
- `11_enable_susfs_for_ksu.patch:136`：`should_umount` 包含 `new_uid == WEBVIEW_ZYGOTE_UID`。
- 上游 SuSFS 明確「不卸載 webview zygote」（`b1dceb4`：`// we should not umount for webview zygote`；現行 `b213c541` 只認 `is_appuid(ruid)`）。
- Patch 11 保留的是 xxKSU 原生 `kernel_umount.c` 的 case 4 行為，README 的 runtime 表也聲稱已驗證 WebView zygote 路徑。這屬於已文件化的 xxKSU 原生語意保留，**不列為錯誤**；只提醒：因 TIF 旗標會被 fork 繼承，所有 webview isolated renderer 也會帶 `TIF_PROC_UMOUNTED`，行為與上游 SuSFS 使用者的預期不同，建議在 README 明講。

---

## 2. 溯源／中繼資料一致性

### 2.1 [Medium，後果見 5.1 High] 鎖定的 xxKSU commit `f263bdb9` 已不在上游任何分支上
- `backslashxx/KernelSU` master 於 2026-10-01 被重寫（新 head `5da23982`，`19937348 "KernelSU v3.3.0+"` 取代了 `f263bdb9`）。`git branch -r --contains f263bdb9` 為空；目前只能靠「直接以 SHA fetch」取得。
- `AGENTS.md` 已說明 xxKSU force-push 屬正常、ancestry 不是接受前提，所以這不是違規；但風險是：
  - 不可達物件可能被 GitHub GC，屆時 `BASELINE.json` 的 `archive_url`（codeload by SHA）與 clean-room 會無法重現；
  - `f263bdb9 → 5da23982` 間有變動的受追蹤檔案：`kernel/Kconfig`（`KSU_KPROBES_KSUD` 變 deprecated）、`kernel/feature/kernel_umount.c`、`kernel/kernel_compat.h`、`kernel/kernel_includes.h`、`kernel/ksu.c`。我已確認這些變動不影響 Patch 11 的 hunk（Patch 11 仍可乾淨套用），可儘快重新接受新 head。
- 建議：把已驗證的 xxKSU tarball 存成 release asset（GKI r38 已經這樣做），不要依賴上游保留不可達物件。

### 2.2 [Low] Patch 11 的 Patch 10 lineage 與 watch 狀態不一致
- `patches/xxksu/BASELINE.json` / `manifest.json`：`c8f64e41`（Patch 10 sha `757d0991…`）
- `.github/upstream-state.json` `susfs_gki`：`b213c541`（Patch 10 sha `590e1bc9…`）
- 我比對過兩版 Patch 10 的差異，只有 index 行、riscv Kbuild、`PT_REGS_SYSCALL_PARM1` 這類上游 KernelSU 追平造成的變動，**對 Patch 11 鏡像的部分無語意影響**。但兩份紀錄互相矛盾，建議推進 lineage 到 `b213c541` 讓紀錄一致。

### 2.3 [Low] 文件描述的閘門已被移除，但文件仍寫成「現行有效」
- `b6a2383`（2026-09-28）刪除了 `validation/reference_cross_check.py` 與其測試、workflow 步驟。
- 但 `PATCH51_CORRECTIONS.md:60`（「Sensitive file differences now block as REVIEW_REQUIRED unless ... reference_cross_check.py」）、`:110`，以及 `UPSTREAM_TRACKING_AUDIT.md:75, 115-116` 仍描述這道閘門是現行保護。
- 讀者會以為敏感檔案差異仍受雙重 hash 審查保護，實際上已不存在。建議在這些段落加註「已於 b6a2383 移除」。

### 2.4 [Low] `HANDOVER.md` / `PATCH51_CORRECTIONS.md` 中的 hash 全部過期
- `HANDOVER.md` 列的 Patch 11 `a0419c3a…`、Sultan `67cc1506…`、GKI `d299ac9c…`、xxKSU `bb0be929…`，與現行 manifest（`c3f40703…`、`63a34d45…`、`f722add0…`、`f263bdb9`）**全部不同**。
- `HANDOVER.md` 有寫「Machine records override this dated snapshot」，所以不算錯，但 README 把它列為維護文件第一項，容易被誤用。建議標題直接加日期與「已過期」字樣，或改成只引用 manifest。

### 2.5 [Info] 中繼資料以手動提交推進
- `b15144a`（「reconcile upstream xxKSU drift at f263bdb9」）直接手改 `manifest.json`、`BASELINE.json`、`upstream-state.json`，而 `AGENTS.md:137-146` 說 `manifest.json` 是公開介面、發布只走 Actions（且有 `METADATA_ONLY_PROMOTION` 路徑）。Patch 位元組沒變，所以實際風險低，但與自訂流程不一致；同時 `v29-baselines/xxksu.json` 的 `metadata` 為空、沒有 `identity`，`BASELINE.json` 卻記錄了 `source_bundle.identity`。

---

## 3. Sultan Patch 51（`patches/sultan-android14-6.1/51_deinlined_susfs_hooks_sultan-android14-6.1.patch`）

### 3.0 驗證結果摘要
- `kerneltoast/android_kernel_google_tensynos` `16.0.0-sultan` head 仍為 `af5c65b9`（GitHub compare：identical），被 patch 的檔案沒有變動。
- 倉庫內 fixture 的 21 個 Sultan 檔與 GitHub 取回的原始檔逐位元組相同；`fs/susfs.c`、`susfs.h` 等於上游 `a8324101` 核心。
- 上游 Patch 50 與本倉庫 Patch 51 套用到乾淨樹都是 0 offset / 0 fuzz / 0 reject；Patch 51 的 18 個 index blob hash 全部吻合。
- `sultan-shiba-susfs-minimal` 與 `gki-android14-6.1` 的核心檔、Patch 10 完全相同，差別只有 Patch 50 中 6 處 Sultan 專屬調整，Patch 51 全部保留。
- A（乾淨樹 + Patch 50）與 B（乾淨樹 + Patch 51）差異 15 個檔：
  - 只有 Patch 50 動到的 8 個檔（`drivers/input/input.c`、`fs/exec.c`、`fs/open.c`、`fs/read_write.c`、`kernel/reboot.c`、3 個 selinux 檔）都屬於「xxKSU 原生負責的 KSU transport / selinux_hide」，移除合理。
  - `calculate_f_flags_wrapper` / `statfs_by_dentry_wrapper` 在 `fs/statfs.c` 有定義，簽章、config 守衛與 Patch 50 逐位元組一致。
  - `susfs_is_current_proc_no_su()` 在 Patch 50 只用來擋 3 個 sucompat transport，Patch 51 隨 hook 一併刪除；Patch 11 仍會設 `NO_SU`，但已沒有讀取者（xxKSU 以 seccomp + `TIF_KSU_MANAGED` 達到等效效果），無害。
  - 作者對 Sultan 的 3 項修正（`clone_mnt` 繼承旗標清除 + `out_free` 防護、pagemap 逐 VMA walker、remote-memory 每輪 `vma_lookup`）逐行對照原始碼確認正確。

### 3.1 [Medium] Patch 51 改寫 SuSFS 核心，復活上游已退役的 `TRY_UMOUNT` 程式碼（本倉庫自行引入）
- 位置：`51_…sultan….patch:2232-2233`（`susfs_run_sus_path_loop` 從 `static` 改成全域）、`:2241-2296`（整段 `CONFIG_KSU_SUSFS_TRY_UMOUNT`）、`:2312-2349`（`susfs.h` 對應結構與宣告）；來源是 `.github/scripts/v2/policy/sultan_source.py:10-27` 的 `CORE_REPLACEMENTS`（硬編碼字串替換）。
- 問題：
  1. `CONFIG_KSU_SUSFS_TRY_UMOUNT` 在 Patch 11 Kconfig 與上游 `a8324101` 都**不存在**，整段是死碼；
  2. 若有人手動開啟，`extern void try_umount(const char *, int)` 對應的是 xxKSU 中 `static inline` 的 `try_umount()`（`kernel_umount.c`），無法連結；且 `susfs_try_umount()` 走訪 `LH_TRY_UMOUNT_PATH` 時**沒有拿** `susfs_spin_lock_try_umount`，與 `susfs_add_try_umount()` 並發會有競態；
  3. `susfs_run_sus_path_loop` 改為非 static，但全倉庫沒有任何外部呼叫者；
  4. 與 README「不恢復已退役的舊黏合程式（retired legacy glue）」的聲明矛盾；
  5. 讓 Sultan Patch 51 依賴「使用者先放入**完全等於** `a8324101` 的 `susfs.c`/`susfs.h`」，SuSFS 核心只要一更新，Patch 51 就套不上（GKI Patch 51 沒有這個耦合）。
- 與 README 的矛盾：README Runtime Validation 表寫「Sultan `ADD_TRY_UMOUNT` … paths verified」。但在目前的 patch 組合下，`CONFIG_KSU_SUSFS_TRY_UMOUNT` 不存在，Patch 11 也沒有 `CMD_SUSFS_ADD_TRY_UMOUNT` handler（`susfs_def.h` 標為 `/* deprecated */`），`ksu_susfs add_try_umount` 只會得到 `ERR_CMD_NOT_SUPPORTED`。**請作者說明 README 所謂 verified 的 ADD_TRY_UMOUNT 是指 xxKSU 原生的 try-umount（`ksud` 的 umount list），還是 SuSFS 指令；若是後者，以目前產物不可能通過**，應修正 README 措辭。
- 建議：刪除 `CORE_REPLACEMENTS` 中 TRY_UMOUNT 與 `susfs_run_sus_path_loop` 兩組替換；`<uapi/linux/magic.h>` 的 include 也非必要（核心檔已能編譯）。讓 Sultan Patch 51 與 GKI 一樣不碰 SuSFS 核心檔。

### 3.2 [Medium，上游繼承] open-redirect 在 RCU-walk 期間做可睡眠配置
- 位置：`51_…sultan….patch:403-421`（`path_openat`），對應上游 Patch 50 同段；GKI 版本有相同結構（見第 4 節）。
- 問題：第一次 `do_filp_open()` 以 `LOOKUP_RCU` 進行，`path_init()` 已 `rcu_read_lock()`；`link_path_walk` / `open_last_lookups` 迴圈結束時 nd 仍可能在 RCU 模式（`complete_walk()` 要到 `do_open()` 才做）。此時呼叫 `susfs_open_redirect_spoof_do_sys_openat()`，其中 `getname_kernel()` 以 `GFP_KERNEL` 配置（可睡眠），之後才 `terminate_walk()` 釋放 RCU。
- 失敗情境：對被設定 open-redirect 的檔案做一般 `open()`，就會在 RCU 讀取區段內睡眠：開了 `CONFIG_DEBUG_ATOMIC_SLEEP` / `PROVE_RCU` 會出 splat；在非 preemptible RCU 的設定下屬真正的 RCU 違規，可能讓 grace period 提前結束。
- 建議：呼叫 spoof 前，若 `nd->flags & LOOKUP_RCU` 就先 `try_to_unlazy(nd)`，失敗則回傳 `-ECHILD` 讓 `do_filp_open` 以 ref-walk 重試；或把 `getname_kernel()` 延後到 `terminate_walk()` 之後。這是上游問題，建議同時回報 simonpunk。

### 3.3 [Low，上游繼承，行為變更] Sultan 原生的 `id.gms.unstable` uname 偽裝被無條件移除
- 位置：`51_…sultan….patch:2405-2443`（`kernel/sys.c` `newuname`），上游 Patch 50 `:2501` 同樣刪除。
- 問題：刪除不在 `#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME` 內；使用者若沒用 `ksu_susfs set_uname`，DroidGuard（`id.gms.unstable`）會看到 Sultan 的真實 release 字串，比原生核心更容易被辨識。
- 建議：保留原生判斷，SuSFS spoof 只在 buffer 已設定時覆蓋；或在 README 提醒使用者必須設定 uname。

### 3.4 [Low，上游繼承] `d_path()` 錯誤用 `NULL` 檢查
- 位置：`51_…sultan….patch:919-920`（`fs/notify/fdinfo.c`）、`:1136-1137`（`fs/proc/fd.c`）
- `d_path()` 失敗回傳 `ERR_PTR(-ENAMETOOLONG)` 等，**從不回傳 NULL**；`if (!dpath)` 擋不住，接著 `kern_path(dpath, …)` 會解參考錯誤指標造成 oops。觸發需要極長路徑，機率低但屬確定的程式錯誤。
- 建議：`if (IS_ERR(dpath)) goto out_kfree;`

### 3.5 [Low，上游繼承] 其他
- `51_…sultan….patch:911`：inotify fdinfo 的 SUS_MOUNT 分支檢查的是 inotify fd 自己的匿名檔 `file->f_path.mnt`（anon inode mount，`mnt_id` 永遠很小），條件永遠不成立，該分支是死路徑。
- `51_…sultan….patch:815-824`：`susfs_get_non_sus_vfsmnt_from_vfsmnt()` 的 fallback 在持有 `mount_lock` 時 `mntput`，並回傳沒有持有 reference 的 vfsmnt，呼叫端之後 `mntput` 會讓 refcount 少一；實務上幾乎走不到。
- `fanotify_fdinfo` 仍是兩參數簽章而 `show_fdinfo` 期待三參數：目前 Sultan 未開 `CONFIG_FANOTIFY` 所以不會觸發，若開啟會因 `-Werror=incompatible-pointer-types` 建置失敗。

### 3.6 [Info，上游繼承，兩個目標皆適用] Patch 11 先設 `TIF_PROC_UMOUNTED` 再卸載，原生卸載對 KSU 掛載實際上會跳過
- `51_…sultan….patch:813-826`、GKI `51_…r38.patch:682` 起（兩邊 `__lookup_mnt` hook 相同）：對帶 `TIF_PROC_UMOUNTED` 的程序，路徑走訪時跳過 `mnt_id >= DEFAULT_KSU_MNT_ID` 的掛載。
- Patch 11 `handle_zygote_setresuid()` 先 `susfs_set_current_proc_umounted()` 再 `ksu_handle_umount()`（與上游 `b213c541` 順序相同），xxKSU 的 `try_umount()` 用 `kern_path()` 找掛載點時看不到這些掛載，會因 `path.dentry != path.mnt->mnt_root` 而判定「已被卸載」直接略過。
- 結果：對 /sdcard 解密前由 KSU 建立的掛載，隱藏實際上只靠 lookup hook，沒有真正卸載（上游註解也寫明「with this hack, we do not even need to umount」）。屬讀碼推論、未實機驗證；若希望真正卸載，可把設旗標移到 `ksu_handle_umount()` 之後（舊版上游 `b1dceb4` 就是這個順序）。

### 3.7 [刻意設計，殘留問題] AVC log spoofing 開關在 Sultan 上靜默失效
- Patch 51 移除了 3 個 selinux 檔的 SuSFS hook（交給 xxKSU 原生 selinux_hide），但 Patch 11 仍處理 `CMD_SUSFS_ENABLE_AVC_LOG_SPOOFING`，它切換的 static key 已沒有使用者。使用者下指令會得到成功回應但沒有效果。建議 Patch 11 對這個指令回報不支援，或在 README 註明。

---

## 4. GKI Patch 51（`patches/gki-android16-6.12/51_deinlined_susfs_hooks_android16-6.12-2025-09_r38.patch`）

### 4.0 驗證結果摘要
- Google tag `android16-6.12-2025-09_r38` 存在（tag 物件 `1b0462bd` → commit `98d5b9e071f1`）。倉庫 `r38-sources.json` 內 20 個原始檔與 Google 該 commit **逐位元組相同**，內嵌 sha256 正確。所以作者 mirror 的 tarball 內容是可信的，只是驗證鏈沒有直接連到 Google（見 5.6）。
- `c8909f7` 是之後的分支點而非 r38，manifest 已註明它只是 provenance lineage，與實際套用目標分開，描述正確。
- 上游 Patch 50（`b213c541`）套到 r38：25 檔中 24 檔只有行號偏移；唯一 reject 是 `security/selinux/hooks.c` 第 1 個 hunk（上下文含 r38 沒有的 ANDROID KMI 註解），且屬 KSU 側，Patch 51 本來就不保留。
- 本倉庫 Patch 51 套到 r38：16 檔，0 offset / 0 fuzz / 0 reject，index blob hash 全部吻合。
- A/B 差異共 45 個 hunk，沒有找到無法解釋的 SuSFS 邏輯變更；KSU transport hook（input、exec、open、read、stat、reboot、setresuid、SELinux hide）的移除都正當。
- 作者 5 項修正（`clone_mnt` 繼承旗標清除、`out_free` 防護、`smap_gather_stats` 守衛、`susfs_pagemap_walk`、`__access_remote_vm` 補 `vma_lookup`）逐項確認正確，且修掉的是上游真實存在的缺陷，**建議回饋給 simonpunk**。
- `calculate_f_flags_wrapper` / `statfs_by_dentry_wrapper` 定義與 Patch 50 逐位元組一致；`NO_SU` 的 3 個讀取點都隨 sucompat 一起移除；Patch 51 需要的 KSU 側符號只有 `susfs_is_current_ksu_domain()`，Patch 11 有提供且型別相符；CONFIG 守衛一致。

### 4.1 [Medium] GKI 版刪掉了上游的無鎖提早返回，熱路徑每次都取全域 `mount_lock`；Sultan 版卻有保留
- 位置：`51_…r38.patch:836-876`（`fs/namespace.c` 三個 `susfs_get_non_sus_*` helper，全檔找不到任何 `if (mnt->mnt_id < DEFAULT_KSU_MNT_ID)`）；對照上游 `b213c541` Patch 50 `:906`、`:921`、`:935`，以及本倉庫 Sultan Patch 51 `:795`、`:809`（Sultan 6.1 沒有 `mnt_id_unique`，只有兩個 helper，且都保留了提早返回）。
- 問題：GKI 版三個 helper 都**一開始就 `lock_mount_hash()`**（`write_seqlock(&mount_lock)`），即使傳入的掛載根本不是 KSU 掛載。呼叫端之一是 `vfs_statfs()`（`51_…r38.patch:2046-2064`），只要 `susfs_is_current_proc_umounted()` 就會走到。xxKSU 預設 `default_non_root_profile.umount_modules = true`（`kernel/policy/allowlist.c:27`），幾乎所有一般 app 都帶這個旗標，所以 app 每次 `statfs()` 都會寫鎖全域 `mount_lock`，同時讓全系統正在進行的 RCU 路徑查找 seqcount 失效重試。
- 結果：輸出與上游完全相同（`mnt_id` 分配後不會再變，無鎖讀取是安全的），**只多了效能代價**，而且 GKI 和 Sultan 兩個目標的行為不一致。
- `PATCH51_CORRECTIONS.md:91` 把這段寫成「不採用 Midori 的 early-return 最佳化」，但這段其實是**上游 Patch 50 本身**的程式碼，說法有誤。
- 建議：恢復上游的提早返回（`susfs_get_non_sus_vfsmnt_from_vfsmnt` 提早返回時要照上游一樣 `mntget` + `dget`），讓 GKI 與 Sultan 一致。

### 4.2 [Medium，上游繼承] open-redirect 在 RCU-walk 期間做可睡眠配置
- 位置：`51_…r38.patch:404`（`susfs_open_redirect_spoof_do_sys_openat()`，內含 `getname_kernel()` / `GFP_KERNEL`）在 `:407` `terminate_walk(nd)` 之前執行。
- 與 Sultan 3.2 相同，修法相同。

### 4.3 [Low，上游繼承，僅讀碼推論] `SUS_PATH` 對 create/unlink 類操作會留下不一致的 dcache 狀態或產生 `..5.u.S` 實體
- 位置：`51_…r38.patch:63-114`（`lookup_dcache` / `lookup_one_qstr_excl`），等同上游 Patch 50 `:142-193`；Sultan `51_…sultan….patch:100-116` 同類。
- 情境：
  1. `lookup_dcache()` 把已快取的 sus dentry 藏起來回傳 `NULL` 後，`lookup_one_qstr_excl()` 會 `d_alloc()` 同名 dentry 再呼叫 `->lookup`。對非目錄 inode，`d_splice_alias()` 不會合併別名，可能在 dcache 中留下同一父目錄、同名的兩個 positive dentry。
  2. 接著改用 `susfs_fake_qstr_name`（`..5.u.S`）重試，回傳一個負 dentry。對 `unlink`/`rmdir` 這是預期中的 `-ENOENT`，但對 `mkdir`/`O_CREAT` 會**真的在磁碟上建立名為 `..5.u.S` 的項目**。這既是檔案系統污染，也可以用來探測某路徑是否被隱藏。
- 建議回報上游；本倉庫可考慮在 create 路徑改回傳 `-EEXIST` / `-EPERM` 之類的錯誤，而不是改名。

### 4.4 [Low，上游繼承] 其他
- `51_…r38.patch:1140-1146`（`fs/proc/fd.c`）與 `:969-975`（`fs/notify/fdinfo.c`）：`d_path()` 用 `if (!dpath)` 檢查，同 3.4。
- `51_…r38.patch:901-933`：`CONFIG_FANOTIFY=y` 時 `fanotify_fdinfo` 的 callback 簽章不符，clang ≥ 16 會編譯失敗，或觸發 CFI trap；GKI 預設 defconfig 沒開。
- fdinfo 的 SUS_MOUNT 區塊是死路徑（同 3.5）。`susfs_get_non_sus_vfsmnt_from_vfsmnt` fallback 在持鎖時 `mntput` 並回傳沒有 reference 的指標（同 3.5，實際走不到）。
- `avc.c` 的 `susfs_is_avc_log_spoofing_enabled` 是 SuSFS 自身功能（`susfs.c:1195`），卻被當成 KSU transport 一起移除，導致 AVC spoofing 開關靜默失效（同 3.7，兩個目標都受影響）。

### 4.5 [Medium] 「GKI android16-6.12 r38 = Pixel 9」的機型標示與 Google 官方資料不符
- 位置：`README.md` Production Patches 表、`patches/manifest.json` `compatibility_target`、`BASELINE.json` `metadata.compatibility_patches`
- Google 官方「Build Pixel kernels」頁面（https://source.android.com/docs/setup/build/building-pixel-kernels ）列出：Pixel 9 / 9 Pro / 9 Pro XL（caimito）、9 Pro Fold（comet）、9a（tegu）全部使用 **`android14-6.1`**；Pixel 6–8 同樣是 6.1（所以 Sultan 那邊「Pixel 7 Pro / 8 跑 6.1」是正確的）。
- 倉庫自己的 `.github/runtime-validation.json:8` 對 GKI 6.12 的裝置也寫 `"device": "Not specified"`（Sultan 那筆則明確寫 Pixel 7 Pro (cheetah)）。
- 建議：除非作者確實在某個 Pixel 9 的 6.12 社群移植核心上驗證過（若是，請寫明來源），否則應移除「Pixel 9」字樣，以免使用者把 6.12 的 patch 拿去套 Pixel 9 的 6.1 原廠核心。

---

## 5. 自動化工具鏈與 CI（`.github/scripts/v2`、`.github/workflows`）

測試：在 macOS / Python 3.12 執行完整 discover，252 個測試中 11 fail + 1 error，全部可歸因於環境（glibc `loff_t`、`RUNNER_TEMP`、Apple `patch` 對已套用 patch 會自動反向套用並回傳 0）；補齊環境後剩 2 個，同屬 Apple `patch` 行為。**未在 Linux 上實跑**，但沒有找到真正的程式邏輯錯誤導致的測試失敗。

### 5.1 [High] 三條驗證路徑都靠 SHA 抓取已孤立的 `f263bdb9`
- `generate-11-ksu-patch.yml:79`（`git fetch --depth=1 origin "$TARGET_COMMIT"`，Patch 11 產生）、`validation/patch51_kbuild.py:110-112`（讀 `upstream-state.json` 的 xxKSU identity 後 `fetch_git()`；**Patch 51** 的 Kbuild gate 也要編 xxKSU + Patch 11）、`clean_room.py:32-44`（`fetch_git()` 以 commit `fetch --depth=1`）與 `:186`。
- 一旦 GitHub 回收這個不可達 commit，Patch 11、Patch 51、clean-room 三條會**同時**失敗，且錯誤訊息只會是抓取失敗，不容易聯想到上游 force-push。
- 建議：見 2.1，把已驗證 tarball 存為 release asset，或儘快重新接受新 head。

### 5.2 [Medium] watcher 不檢查祖先關係／可達性
- `watch/checker.py:53-90` 只做 `git ls-remote` 取 head；`:260-271` 在受追蹤檔案 hash 不變時直接判 `IRRELEVANT_CHANGE`，dashboard 顯示 HEALTHY。
- 以 master `5da23982` 離線模擬：結果 `SAFE_REGEN_CANDIDATE`、不開 issue、CLI exit 0。
- `AGENTS.md:113-115` 明說 xxKSU 的 force-push 屬正常、ancestry 不是接受前提，這是刻意設計；但 5.1 的後果（被接受的 commit 變成不可達）**沒有任何地方偵測或提醒**。
- 建議：至少加一個「accepted commit 是否仍可由 tracking ref 到達」的資訊性檢查，不可達時在 dashboard 標示並提醒歸檔。

### 5.3 [Medium] Patch 11 是硬編碼模板，沒有任何機制檢查它與上游 Patch 10 的語意是否還一致
- `adapters/xxksu.py:132-294` 以字串常數寫死所有 hunk；`policy/patch11.py` 只在測試中被呼叫，production gate 只檢查 anchor 找不找得到。
- 已實際分歧：Kconfig 6 個 symbol 的 prompt/help 不同（上游在 `c023d8e`、`41e748a` 已修改）、`susfs_is_boot_completed_triggered`（上游 `b917aac` 已移除）、上游改為 `susfs_set_batch_sid()`。（上游對未知 SUSFS cmd 回 `-EINVAL`、模板回 `0`，但 xxKSU 所有呼叫端 `syscall_table_hook_arm64.c:53,137,217,274`、`kp_ksud.c:99` 都丟棄回傳值，**無實際影響**。）
- 好消息是模板用到的符號上游都還在，所以**不是編譯錯誤**。但「Patch 10 是 semantic lineage」的說法目前沒有程式保證。
- 建議：至少對 Patch 10 中 Kconfig 區塊與 `ksu_handle_sys_reboot` 的 cmd 列表做結構化比對，上游一改就 fail closed 要求人工審查。

### 5.4 [Medium] `ksu_commit` 手動覆寫只改 commit 欄位，其他 provenance 欄位不會同步
- `pipeline.py:204-250` `_plan_metadata_updates()` 只寫 `resolved_commit` / `commit`，不更新 `tracked_files`、`relevant_content_hash`、`tree`、`archive_sha256`、`archive_url`、`retained_file_hashes`。
- 失敗情境：`workflow_dispatch` 帶 `ksu_commit`（`generate-11-ksu-patch.yml:6,49`）推進 → `BASELINE.json` 的 commit 是新的、hash 與 archive 是舊的 → `accepted_sources()` 與 manifest 檢查照樣通過 → watcher 之後以新 commit 比對，持續回報 `NO_CHANGE`；只有每週 clean-room 會發現不一致。
- 建議：推進 commit 時一併重算並寫入所有 provenance 欄位，或在 promotion 前驗證 archive / tree / tracked hash 與新 commit 一致。

### 5.5 [Medium] 其他工具鏈問題
- **M1 漂移檢查被靜默跳過**：`watch/checker.py:469-476` 抓不到舊 commit 的 Patch 10/50 時只 `logger.warning`，接著 `semantic/gate.py:318` 的條件 `patch10_key in upstream_contents and baseline_contents and …` 在缺少 baseline 時直接略過 Patch 10 比對；子代理實測在 Patch 10 加一個新的上游呼叫仍 `passed=True`。應 fail closed。（同檔 `:305-316` 尋找 `patch10_key` 的迴圈重複寫了兩次，屬複製貼上殘留。）
- **M2 偵測到漂移仍 exit 0**：`watch/cli.py:117` 只有 dashboard 同步失敗或 manifest 驗證失敗才回 1；需要升級的漂移本身不影響 exit code，而 `escalation.py` 的 `escalate_issue()` 在 `gh` 失敗時 `except … return None`，`cli.py:74-76` 對 `None` 不做任何處理。結果是排程 workflow 綠燈、issue 也沒開成，維護者收不到通知。
- **M3 證據被自動清除**：`auto-clean-actions.yml:29-46` 只保留每個 workflow 最新 5 次成功 run，並刪除**所有**失敗與取消的 run（`gh run delete … || true`）。`HANDOVER.md`、`PATCH51_CORRECTIONS.md` 引用作為證據的 run（`36283493548`、`36284535551`、`36284739196`、`36296083518`、`36283493358`、`36294761634`）我以 GitHub API 逐一查詢**全部 404**（repo API 本身 200，整個 repo 目前只剩 32 個 run）。另外，2026-10-02 的 Upstream Watch run `36981486449` 結論是 success，與 M2 描述一致：xxKSU 上游已重寫，排程仍是綠燈。建議改成依天數保留，或至少不刪被文件引用的 run，並把關鍵證據存成 artifact／release。
- **M4 `[skip ci]` 與觸發路徑**：push 觸發的 paths 沒包含 `adapters/xxksu.py`、`engine/`、`source/`、`semantic/`、`upstream-state.json`、`BASELINE.json`；`899c010`、`2767ca6` 等改程式碼的 commit 用了 `[skip ci]`，違反 `AGENTS.md:32`（`[skip ci]` 僅限純文件）。目前 HEAD 之後有正常驗證過，但流程上會漏。
- **M5 watcher 的候選驗證不代表 production**：Patch 11 的套用驗證是套回同一份來源（循環）；Patch 51 用的是舊的 `.github/scripts/deinline_50_to_51.py`（`checker.py:504`），不是 production 產生器（`policy/patch51_source.py`），所以 watcher 說「可安全重生」不代表 production 會過。

### 5.6 [Low / Info]
- `validation/exact_patch.py` 呼叫 `patch` 沒有 `--forward`，也沒設 `LC_ALL=C`；修正時不要用 `--batch`（會自動反向套用）。
- `upstream-watch.yml:57-66`、`generate-51-kernel-patches.yml:119,235` 把 `workflow_dispatch` 輸入直接插入 shell；因為只有具寫入權限的人能觸發，風險低，但建議改成 `env:` 傳入。
- Actions 只釘 tag 沒有釘 commit SHA；有些保護條件用 `assert` 實作（`python -O` 會被移除）。
- r38 原始碼只對照作者自己 mirror 的 tarball hash（`yapixel/gki-build-assets`），沒有對照 Google 官方來源。
- `patches/xxksu/BASELINE.json` 記錄 Patch 11 `size: 16772`，實際檔案為 **15458** bytes（git 內容亦同），是舊版殘留。
- 各 `BASELINE.json` 的 `"status": "VERIFIED"` 與 `validation_results: PASS` 是寫入的字串，不是每次重算的結果。
- 沒有使用 `pull_request_target`；唯一用到的 secret 是 `GITHUB_TOKEN`，沒有被印出。
- 「四個 profile」的說法與程式碼一致，沒有文件聲稱六個已實作。

---

## 附錄

- [appendix_gki_findings.md](appendix_gki_findings.md)：GKI Patch 51 逐 hunk 分類表、套用紀錄、重現指令
- [appendix_sultan_findings.md](appendix_sultan_findings.md)：Sultan Patch 51 逐 hunk 分類表、套用紀錄、重現指令
- [appendix_tooling_findings.md](appendix_tooling_findings.md)：Python 工具鏈 / CI 審查細節與測試執行紀錄

> 附錄為子代理原始報告（英文）。主報告只收錄經過再次核實的項目；附錄中未被主報告引用的細節未經獨立驗證，使用前請自行確認。
