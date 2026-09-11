# HANDOFF —— 2026 国赛 B 题工作进度（面向 agent 的快速同步）

> 本文件给后续 agent 快速了解"这道题做到哪了、怎么继续、有什么硬约束"。环境部署细节另见 [ENV-HANDOFF.md](ENV-HANDOFF.md)，目录导航见 [README.md](README.md)。最后更新：2026-09-11。

## 0. 最高硬约束（务必遵守）

1. **绝不触碰官方模拟器的"正式测试"**，除非用户明确书面许可。所有官方模拟器行为一律只用"演练测试"。不点"正式测试/开始正式/formal"按钮或流程，代码不含自动开测逻辑。若某验证只能靠正式测试，停下问用户。正式测试问题3/问题4 各仅 3 次、9/13 17:30 硬截止、不可逆。
2. **不逆向、不篡改、不绕过官方模拟器**（有 RSA 加密案例、ECDSA 日志签名、pristine 校验、在线心跳）。合法调参只用官方演练 + 自建 mock。
3. **机器狗程序必须与模拟器同机运行**（官方接口只监听 guest 内 127.0.0.1，宿主访问不到）。
4. **密码永不写入任何文件或日志**；API 只用 `robot_id = 参赛队号`。

## 1. 题目与选择

- 三题中已定 **B 题：无线电干扰源的快速自动定位与清除**。选题依据、A/B/C 对比见历史讨论；结论是 B 打在软件工程强项上，且平台可行性已实测通过。
- 题面 `B题.pdf`；官方附件 `附件/附件1.docx`（问题3测试说明+协议）、`附件/附件2.docx`（接口完整规范，是所有建模的接口事实来源）。

## 2. 目录地图

| 路径 | 内容 | 状态 |
|---|---|---|
| `B题.pdf`、`附件/` | 官方题面与附件（只读） | — |
| `ENV-HANDOFF.md` | 官方模拟器在 Apple Silicon 上的部署指南（Parallels+Win11 ARM+Prism）、二进制逆向事实、四个操作坑 | 完成 |
| `archive/` | 官方模拟器压缩包（精简版首选 5.83MB / 完整版兜底 225MB） | — |
| `verification/` | 官方模拟器平台可行性验证脚本 + 46 项证据 | 完成 |
| `practice-logs/` | 官方演练测试端到端实测与录制（`REPORT.md` 延迟统计） | 完成 |
| `mock/` | 统一本地测试环境：mock 模拟器 + 蒙特卡洛 + 三后端 + 录制/回放/差分 + 标定。见 `mock/README.md` | 框架完成 |
| `models/q1q2/` | 问题1、2 的设计/实现/评审/benchmark/认证/论文。见 `models/q1q2/README.md` | 完成 |
| `models/`（其它） | 问题3、4 建模 | **未开始** |

## 3. 各部分进度

### 3.1 官方模拟器环境（完成）

- 已在 **Apple M5 Pro + macOS + Parallels + Windows 11 ARM64 25H2 + Prism x64** 跑通精简版：GUI 登录界面正常、`127.0.0.1:2026` 监听、行为符合附件。
- guest 内已装 ARM64 Python（`C:\Python314-arm64\python.exe`）。
- **演练测试实测过一次**（问题4，案例含 15 源：全向5+定向10）：1367 笔请求全成功、现实耗时 2.46s、复用连接 /measure p95≈0.23ms → **20 分钟现实时间充裕、延迟不是瓶颈**（用长连接，别每笔新建）。计时规则（切频1s/检测5s/清除5s/3s/移动 d/5）逐笔核对吻合。录制见 `practice-logs/`。
- 坑（详见 ENV-HANDOFF §4）：`prlctl exec` 跑在 SYSTEM/session 0 无桌面，启动 GUI 要用 schtasks `/it` 丢进 session 2；共享目录只暴露 Desktop/Documents/Downloads；宿主 HTTP 中转被 pf 挡住；长 PowerShell 要写成 .ps1 传进去。

### 3.2 benchmark 框架 mock（框架完成，官方对齐待做）

- 三后端（InProcMock/HttpMock/HttpOfficial）共用同一策略接口，切后端只改配置。含录制/回放/微秒级差分、蒙特卡洛压力矩阵（3 分布 × 5 误差场，强制 ≥15 组合）、从演练观测标定、轨迹图。
- baseline 策略是朴素扫描（能清完但未优化时间）——**真正的搜索定位清除策略还没写**。
- 待做：用官方演练录制做 mock↔官方差分对齐（虚拟时间逐微秒）、误差场反演回填。

### 3.3 问题1、2（完成，达论文就绪的主体）

流程走完：设计 `PLAN.md` v3（两轮审计+三维评审+整合）→ 实现 9 模块 → 静态 review（5 阻断 bug 已修）→ 动态运行 → 四块正确性 benchmark（真值独立，抓出并修 3 个真 bug）→ Q2 认证式上下界 → 论文草稿。

- **模型要点**：±1° 示向度→前向角锥→半平面交=凸多边形定位区域（集员估计，非最小二乘）；直径圆覆盖判定（强制圆心+Thales、Jung 界 d/2<R≤d/√3、等边三角形反例）；κ/η 膨胀系数；**20 米清除三段判据**（E20 非空⟺R≤20：d≤34.64 必可、34.64–40 看形状、>40 不可能）把定位接到清除动作；Q2 保收域 C_sig（四圆盘约化）+ 最坏定位直径 J(q)（不可区分点对公式）+ 短基线不可辨识下界。
- **验证**：`tests/` 全过；benchmark 修复后 q1_geometry 264/285、q1_circle_cover 329/330、q2_candidate 502/531（核心判定0错）、q2_worst_diameter 46/48（低估归零）；认证 [L,U] 夹住闭式 J。第三方参考数值（对称四站 D=41.321338/R*=20.660669）已用生产代码复现命中。
- **论文**：`models/q1q2/paper-q1q2.md` 草稿成稿，8 篇核心文献引用与 `reviews/literature-review.md` 一致；诚实定位增量（保收域条件化、20米清除挂钩、不可区分点对公式、短基线下界为本题增量；κ/η、序贯搜索不夸大）。
- **待办（非阻断）**：完整敏感性 S1–S9、部分图表 F1/F4/F8/F10、认证模块 guest 实跑、mock 真集成、benchmark 残留过严项。详见 `models/q1q2/README.md`。

### 3.3.1 Q1/Q2 benchmark 如何使用

benchmark 用来**检测 Q1/Q2 生产代码是否正确**，铁律是**真值独立于被测代码**（闭式解析 / `fractions` 精确算术 / 独立枚举 / scipy LP / 蒙特卡洛世界采样），详见 [benchmarks/README.md](models/q1q2/benchmarks/README.md)。四块各自独立、互不依赖。

**运行（从仓库根目录，用 `models/q1q2/.venv`）：**

```bash
# 四块，各自读 cases.jsonl 喂生产代码、与独立真值比较、写 report.json
models/q1q2/.venv/bin/python -m models.q1q2.benchmarks.q1_geometry.run
models/q1q2/.venv/bin/python -m models.q1q2.benchmarks.q1_circle_cover.run
models/q1q2/.venv/bin/python -m models.q1q2.benchmarks.q2_candidate.run
models/q1q2/.venv/bin/python -m models.q1q2.benchmarks.q2_worst_diameter.run
```

- 加 `--regenerate` 重新生成案例（`generate.py` 产 `cases.jsonl` + 真值）。不加则复用已生成案例，只重跑对照。
- 每块产出 `benchmarks/<area>/report.json`：字段 `n_cases/n_pass/n_fail`、按 `categories` 分类（random/adversarial/degenerate/closed_form/invariant 等）、`failures[]`（含 `case_id/expected/actual/error/truth_method/note`）。`q1_geometry` 另存 `regression_baseline.json` 供回归 diff。

**Q2 认证式上下界（q2_worst_diameter 专有）**——补上"只有下界抓不到高估"的空缺：

```bash
# 需要 mpmath（隔离依赖，不在生产 requirements）
models/q1q2/.venv/bin/python -m pip install -r models/q1q2/benchmarks/q2_worst_diameter/requirements-certify.txt
# 用区间分析对每个 q 算认证区间 [L,U] ∋ 真 J(q)，判定生产 J_hat 是否落带内
models/q1q2/.venv/bin/python -m models.q1q2.benchmarks.q2_worst_diameter.run --certify --report models/q1q2/benchmarks/q2_worst_diameter/report-certified.json
# 可调：--certify-tol 0.1（带宽 U-L 目标）、--certify-seconds 60、--certify-nodes 200000
```

认证核心在 `models/q1q2/optional/certified.py`（mpmath.iv 四维分支定界，向外舍入保证包含性；生产主链路不依赖它，不装 mpmath 也能正常导入生产模块）。判定：`L−tol≤J_hat≤U+tol` PASS；`<L` UNDERESTIMATE（真 bug，应已为 0）；`>U` OVERESTIMATE（新增可抓）。

**看结果 / 判定失败性质（重要）：failures 数 ≠ 生产 bug 数。** 收到失败要先分类：
- 是核心答案错（区域分类/直径/覆盖判定/成员 IN-OUT/J 低估），还是仅元数据（见证 witness_attained、分离见证）？
- 是生产错，还是 benchmark oracle 过严 / 用错场景（如四圆盘 sector oracle 只对标准场景成立、极端尺度 1e-9 是 float64 极限、衰退方向非唯一）？
父 agent 必须抽查代表性失败、读 `expected` vs `actual` 后再定性，不可把失败总数直接当 bug 数。

**当前基线（修复后，供回归对照）：** q1_geometry 264/285、q1_circle_cover 329/330、q2_candidate 502/531（核心 IN/OUT 判定 0 错）、q2_worst_diameter 46/48（认证低估 grade A 归零）。残留均为 benchmark 过严或几何无害瑕疵，非错答案。改生产代码后应重跑四块，通过率不应低于此。

**测试 vs benchmark 的区别：** `models/q1q2/tests/` 是随代码走的单元/回归测试（`pytest`）；`benchmarks/` 是独立真值的正确性验证（更强、更慢、专抓 bug）。改生产后两者都要跑。

### 3.4 问题3、4（未开始）

- 问题3：未知数量(10–16)全向源的搜索/定位/清除，最小化虚拟时间。问题4：加定向源(未知方向/数量)。
- 已有的抓手：mock 框架可无限跑；Q1/Q2 的集员几何、20米清除判据、不可区分点对可直接复用；文献给了 Q3 的建模骨架——把"分开所有超 τ 的长歧义点对"写成 0–1 集合覆盖 ILP（见 `reviews/literature-review.md` §三.4）；主动定位/时间目标可引 R7/R9。
- 关键量化直觉：现实时间充裕，评分的稀缺资源是**虚拟时间**（检测5s、横穿3600m直径720s、扫20频道120s）。负信息(no_signal)可裁剪可行域（有效半径≥1000m→无信号可挖1000m圆）；未知源数需最优停止准则。

## 4. 怎么在本仓库工作

- Python 环境：`mock/.venv` 与 `models/q1q2/.venv`（各自 requirements）。纯 Python 跨平台，可复制进 guest。
- 常用命令见 `models/q1q2/README.md` 与 `mock/README.md`。测试：`.venv/bin/python -m pytest <dir> -q --import-mode=importlib`。
- 权威文档优先级：接口事实看 `附件/附件2.docx`；Q1/Q2 数学看 `models/q1q2/PLAN.md` v3；不要擅自改数学口径。
- git 已初始化，历史整洁（5 个提交）。

## 5. 工作方法约定（多 agent 协作）

- 已验证有效的流程：规划 agent 出设计 → 反复审计 → 实现 agent → 静态 review agent → 动态运行 → benchmark agent（真值独立）→ 修 bug → 认证。每步产物落盘（PLAN/reviews/benchmarks/report.json）。
- 评审要独立、真值不得调用被测生产函数；子 agent 结果不可全信，父 agent 要抽查/复跑关键结论。

## 6. 建议的下一步

1. **启动问题3、4 建模**（分值与工作量大头）：先规划 → 审计 → 实现搜索定位清除策略，在 mock 上跑蒙特卡洛做消融，再用官方演练验证。用上 Q1/Q2 的几何内核与集合覆盖 ILP 骨架。
2. 或先收尾 Q1/Q2 待办（敏感性/图表/论文配图）到完全论文就绪。
3. 需要官方演练实测时，登录须用户手动完成（参赛队号+密码），agent 只跑演练、绝不碰正式。
