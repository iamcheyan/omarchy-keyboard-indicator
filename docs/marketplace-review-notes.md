# 商店审核注意事项（Marketplace Review Notes）

> 2026-08-22 整理。来源：HANCORE-linux/omarchy-plugin-marketplace 本插件 issue
> [#1468](https://github.com/HANCORE-linux/omarchy-plugin-marketplace/issues/1468)
> 及兄弟插件 #1401、#1428 的审核往返。供上架前自查与复审对照。

## Published status

The plugin was approved and verified, and is now published at:
https://omarchyplugins.com/plugin.html?id=hancore.keyboard-center

The marketplace verification applies to the published snapshot and is not a
security audit.

## 一、商店审核机制速览

1. **按精确 HEAD 审核**：维护者在 issue 里引用具体 commit SHA（如 `62fcd38…`）。
   任何修复必须：上游仓库提交 → 在 issue 里评论附 commit 链接 → 等维护者按新 HEAD 复核。
   本地改完不推送 = 审核永远看不到。
2. **自动化基线（github-actions）**：扫描 `pkexec`/`sudo`/`systemctl`/`make` 等模式，
   命中则标 `privilege` / `service-management` 能力，状态 `review-required`。
   这不是拒绝，只是要求人工过目；但 README/代码里的每一处提权字样都会被列出来展示。
3. **人工复审（HANCORE-linux / collaborator）**：只盯两类事——供应链完整性、资源与注入边界。
   复审语言精确到 `文件:行号`，且每轮都重新按新 commit 复查。
4. **提交清单里明确**：「approval is for listing and is not a security review」——
   但实际上人工复审就是安全审查，标准见下。

## 二、审核人在意的点（从三单反馈提炼）

| # | 关注点 | 出处 | 判例 |
|---|--------|------|------|
| 1 | **供应链固定**：禁止 clone moving-HEAD 再以 root 构建 | #1468 第 1 轮 | 「unpinned remote-to-root supply-chain path」→ 必须 pin immutable commit 并校验 |
| 2 | **user-to-root TOCTOU**：校验过的用户可写路径不得再递给 pkexec 执行 | #1468 第 2 轮 | 「checkout can change after the status check; ignored files are not covered by git status」→ 特权步骤只收字节，不执行 Makefile/脚本 |
| 3 | **资源无界**：下载必须按声明大小截断，先限界后校验 | #1428 | 「downloads until EOF…consume unbounded disk space」 |
| 4 | **注入面**：外部数据（窗口标题/类名）进 Qt 必须显式 PlainText | #1401 | StyledText 默认 AutoText 可触发富文本资源加载 |
| 5 | **提权纪律**：固定内联命令、用户显式触发、无插值 | #1428 ONNX | `pkexec voxtype setup onnx --enable` 固定串，取消则不动 |
| 6 | **service-management 能力**：systemctl 调用会被标记，需在 README 说明用途 | #1428 基线 | 标 `review-required` 但可过 |
| 7 | **卸载卫生**：不得在用户配置里留悬挂钩子 | 提交清单 | 「does not overwrite user configuration without explicit consent」 |
| 8 | **仓库卫生**：无构建产物入库、README/license/preview 齐全、版本随修复递增 | 三单通用 | 验证 bot 检查 manifest 唯一性/Quattro 兼容 |

## 三、本仓库（keyboard-center）反馈与修复状态

| 轮次 | 审核意见 | 修复 |
|------|----------|------|
| 1 | moving-HEAD clone → root 构建 | `03a2e04`：pin `f564288a` + 校验 HEAD 与干净 checkout |
| 2 | 校验后把用户可写路径传给 pkexec 跑 make（TOCTOU） | `8447a0f`：临时目录非特权构建，pkexec 只收 base64 字节 + 固定内联安装器 + 目的地白名单 |

### 最新提审更新（2026-08-24）

本轮提交将语音触发从单一 CapsLock 选项扩展为三个彼此独立的开关：

- CapsLock dictation；
- Left Ctrl dictation；
- Right Ctrl dictation。

每个开关分别保存状态并生成 keyd 映射，关闭或开启其中一个不会改变另外两个。
Left/Right Ctrl 使用 `overload(control, f24)`，组合键保留 Ctrl，单独按键在松开时
切换 Voxtype。原有 CapsLock/Left Ctrl 交换开关、提权边界、状态机
事务顺序和 F24 Hyprland 绑定保持不变，F9 保留用户原有的切换行为。

同时更新了面板、英文/中文说明、schema 代际标记和独立映射回归测试。版本更新为
`0.4.1`。请审核方按最新 HEAD 重新运行 marketplace validation 并复审本轮功能。

## 四、本仓库对照自查要点

- [x] 特权步骤 = 固定内联 helper，stdin 收字节，目的地白名单（PRIVILEGED_HELPER）
- [x] keyd 源码 pin 到 immutable commit，非特权构建
- [x] 提权仅由用户切换开关触发，无后台静默提权
- [x] keyd 配置带 schema 代际标记，漂移可检测
- [x] 提交并推送全部本地修复（版本 0.4.1）
- [x] `.gitignore` 排除 `__pycache__/` 和 `*.pyc`
- [ ] README 的 systemctl/pkexec 描述与最终实现保持一致（审核基线按行引用）
