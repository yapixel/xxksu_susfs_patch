# xxKSU SuSFS De-inlined Patches & Automated Matrix CI

Automated patch generation, verification, and end-to-end multi-kernel testing for **xxKSU (`backslashxx/KernelSU`) + SuSFS (De-inlined Hooks)**.

---

## 📁 Repository Structure & Patch Layout

```text
xxksu_susfs_patch/
├── .github/
│   ├── scripts/
│   │   ├── transform_10_to_11.py          # 11 补丁生成引擎 (KernelSU AST 插桩)
│   │   └── deinline_50_to_51.py           # 51 补丁生成引擎 (内核解内联)
│   ├── workflows/
│   │   ├── generate-11-ksu-patch.yml      # 11 补丁专用维护与验证工作流
│   │   ├── generate-51-kernel-patches.yml # 51 补丁多内核 Matrix 并行工作流
│   │   └── auto-clean-actions.yml         # GitHub Actions 运行记录清理
│   └── fixtures/                          # CI 辅助修补补丁 (Sultan 编译修补)
│       ├── sultan/
│       ├── manual-security-hooks-v2.0.patch
│       └── scope-min-manual-hooks-v2.3.patch
│
└── patches/                               # 🎯 用户直接取用的标准补丁库
    ├── xxksu/                             # 📦 针对 KernelSU (backslashxx) 的全局通用 11 补丁
    │   └── 11_enable_susfs_for_ksu.patch
    │
    ├── sultan-android14-6.1/              # 📦 针对 Sultan 6.1 (Pixel 8 / Shiba) 的 51 补丁
    │   └── 51_deinlined_susfs_hooks_sultan-android14-6.1.patch
    │
    ├── gki-android14-6.1/                 # 📦 针对 Google GKI 6.1 (Pixel 7 / Pantah / Cheetah) 的 51 补丁
    │   └── 51_deinlined_susfs_hooks_gki-android14-6.1.patch
    │
    └── gki-android16-6.12/                # 📦 针对 Google GKI 6.12 (Android 16 / Pixel 9) 的 51 补丁
        └── 51_deinlined_susfs_hooks_gki-android16-6.12.patch
```

---

## 🌟 核心特性与架构

1. **`11` 补丁（全局通用 xxKSU 补丁）**：
   * 作用对象：`backslashxx/KernelSU`。
   * 与底层 Linux 内核版本解耦，通用适配 5.10 ~ 6.12。
   * 开辟 SuSFS Supercall 路由（`0xFAFAFAFA`），分发 15 个 `CMD_SUSFS_*` 控制指令。
   * 适配 Zygote / Zygote_Next 双域 SID 隔离与自动卸载。

2. **`51` 补丁（多内核解内联挂钩）**：
   * 作用对象：Linux 内核核心子系统（`fs/`、`mm/`、`kernel/`、`include/linux/`）。
   * 自动剥离与 xxKSU 冲突的 8 个内联系统调用文件。
   * 动态适配各内核版本特有结构（如 6.12 的 `struct mnt_idmap *idmap`、Pixel GKI 的 `trace/hooks/blk.h` 锚点）。
   * 由内核源码树中的 Linux 原生 `git format-patch` 二进制程序直接导出，零 `.orig` / `.rej` 残留。
