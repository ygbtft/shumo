# 2026 国赛 B 题 —— 无线电干扰源的快速自动定位与清除

本目录是 B 题的工作区。下面按"题目原始材料 / 官方模拟器相关 / 自研求解与建模"三类，说明每个文件与文件夹的职责。

> 硬约束：所有涉及官方模拟器的行为只用于**演练测试**。未经明确许可，绝不启动、操作或探测**正式测试**。详见 `ENV-HANDOFF.md` 与 `mock/README.md` 顶部。

---

## 一、题目原始材料（只读，勿改）

| 路径 | 职责 |
|---|---|
| `B题.pdf` | 官方题面。问题 1–4、附录 1（干扰源特征）、附录 2（测向机原理与工作方式）。 |
| `附件/附件1.docx` | 官方附件 1：问题 3 的测试说明与 HTTP+JSON 通信协议要点。 |
| `附件/附件2.docx` | 官方附件 2：接口完整规范（端点、字段、计时规则、错误码、示例代码、测试流程）。是自研 mock 与所有建模的接口事实来源。 |

## 二、官方模拟器相关

| 路径 | 职责 |
|---|---|
| `archive/Jammers-simulator-win64.7z` | 官方模拟器精简版（5.83 MB）。ARM Windows 上用系统自带 WebView2 即可运行，为首选。 |
| `archive/Jammers-simulator-full-win64.7z` | 官方模拟器完整版（225 MB，内含固定版 x64 WebView2）。无 Evergreen WebView2 的机器上兜底用。 |
| `ENV-HANDOFF.md` | 环境交接文档：如何在 Apple Silicon 上用 Parallels + Win11 ARM64 + Prism 跑通官方模拟器；含虚拟机配置、二进制逆向事实、四个操作坑（session 0 无桌面、共享目录、HTTP 中转、长 PowerShell）。 |
| `verification/` | 官方模拟器**平台可行性验证**的脚本与证据。`benchmark_api.py`、`*.ps1` 为启动/截图/连通性脚本；`evidence/` 保存运行截图、启动日志、架构探测等 46 项证据。结论：精简版在虚拟机内 GUI 正常、`127.0.0.1:2026` 监听、行为符合附件。 |
| `practice-logs/` | 官方**演练测试**的端到端实测与录制。`practice_e2e.py` 为实测脚本，`audit_recording.py` 为离线计时核对；`REPORT.md` 是延迟统计与规则核对报告（1367 笔请求、往返 p95≈0.23ms、20 分钟现实时间充裕）；`session-20260910/` 存该次演练的 JSONL 录制、截图与统计。 |

## 三、自研求解与建模

### `mock/` —— 统一本地测试环境（benchmark 脚手架）

按附件 2 规则独立实现的本地模拟器 + 蒙特卡洛评测框架，用于**无限次调参**和作为论文证据引擎。三个后端（内存 mock / 本地 HTTP / 官方 HTTP）共用同一策略接口，切后端只改配置。含录制/回放/微秒级差分、从演练观测标定、压力矩阵评测、轨迹可视化。**详细说明见 [`mock/README.md`](mock/README.md)**，跨机部署见 `mock/MACOS-WINDOWS-HANDOFF.md`。

### `models/` —— 数学建模与求解

各问题的数学模型与代码实现。

| 路径 | 职责 |
|---|---|
| `models/q1q2/` | 问题 1、2 的完整实现：集员估计几何内核、覆盖判定（含 κ/η 膨胀系数、20 米清除阈值主线）、第二检测点选择。**详见 [`models/q1q2/README.md`](models/q1q2/README.md)**。 |
| `models/q1q2/PLAN.md` | 设计文档 v3（经两轮审计 + 三维评审 + 整合终审）。数学定义、算法、验收标准的唯一权威。 |
| `models/q1q2/reviews/` | 评审记录：创造性 / 合理性 / 正确性三份规划评审，及实现完成后的静态代码审查。 |
| `models/q1q2/`（`geometry.py` `circle.py` `q1.py` `feasible.py` `q2.py` `diagnostics.py` `adapters.py` `plots.py` `run.py`） | 九个职责模块，见该目录 README 的模块表。 |
| `models/q1q2/tests/` | 单元测试与回归测试（198 passed）。 |
| `models/q1q2/data/`、`outputs/` | 解析案例输入配置；运行产物（JSON/CSV/图）。 |

> 问题 3、4（搜索定位清除策略）尚未开始，后续在 `models/` 下新增。

---

## 目录状态速览

- 问题 1、2：已实现并通过静态审查与动态测试（`models/q1q2/`，198 tests pass）。待补：完整敏感性方案、部分论文图表、mock 真实集成测试（见 `models/q1q2/README.md` 的 TODO）。
- 官方模拟器：平台已验证可跑（`verification/`），演练延迟已实测（`practice-logs/`）。
- benchmark 框架：已就绪（`mock/`），官方演练真机零差异标定待做。

## 杂项

`.git/` 版本库；`.gitignore` 忽略规则；`.pytest_cache/`、`__pycache__/`、`.venv/`、`.DS_Store` 为缓存/环境/系统文件，非项目内容。
