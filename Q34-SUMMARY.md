# Q3 / Q4 汇总 —— 代码来源、审计对拍、外围修复、官方演练战果

> 面向后续 agent 与作者本人。记录问题3、4 从"同学分支代码"到"在官方模拟器演练稳定全清"的全过程与当前状态。硬约束见 [HANDOFF.md §0](HANDOFF.md)，环境见 [ENV-HANDOFF.md](ENV-HANDOFF.md)，guest 部署见 [B/GUEST_DEPLOY.md](B/GUEST_DEPLOY.md)。最后更新：2026-09-11。

## 0. 一句话结论

Q3/Q4 策略代码（合并自同学 `NTJ_B` 分支，经多 agent 审计 + 对拍 + 本地大规模 + 外围 bug 修复）在**官方模拟器演练**上稳定全清。以模拟器权威统计库为准：当前定型策略所跑各局全部 `cleared==jammer_count`——**Q3 5/5 局清 63 源、Q4 6 局清 80 源**（含至少 19 个 GUI 确认的定向源），源加权用时全面优于参考截图。唯一未全清的是一条**早期探索局**（CNDW 10/15，非定型策略）。全程仅用**演练测试**，从未触碰正式测试。

## 1. 官方演练战果（全部 practice，从不碰正式）

> **数据来源升级**：以下以模拟器自写的权威明文库 `C:\Jammers\JammersSimulatorData\practice-statistics-queue.sqlite3`（表 `practice_statistics_tasks`）为准，而非机器狗自报 `summary.json` 或界面截图。字段含真实源数 `jammer_count`、`cleared_jammer_count`、`clear_failure_count`、`end_reason`、`virtual_time_us`。签名的 `.jlog` 行为日志负载是加密二进制，本地不可解（也不逆向），故以此统计库为权威本地判据。核对方法：只读拷贝该库后查询，绝不写实时库。

均在 guest（Parallels + Win11 ARM64 + Prism）内 `C:\BRobot` 运行，`robot_id=参赛队号`。

### Q3（`range_area7`，7 站全向覆盖）—— 5/5 全清

| 案例码 | 源数 | 清除 | clear_fail | 每源虚拟秒 | 结束 |
|---|---:|---:|---:|---:|---|
| G2A3-4AXU-V5DH-GDQ9 | 11 | 11 | 1 | 297.4 | user_exit |
| FQK3-PR75-VDPD-F6V9 | 15 | 15 | 0 | 242.7 | user_exit |
| VNT5-4QM8-6XSJ-NMHQ | 16 | 16 | 2 | 183.1 | user_exit |
| S8EC-4VBV-GDWM-K3KP | 11 | 11 | 0 | 260.3 | user_exit |
| EFE6-TXDA-F5UK-JZMX | 10 | 10 | 0 | 300.7 | user_exit |
| **合计** | **63** | **63/63** | | **源加权 ≈ 249.4** | |

（另有 `UATV-FA9K-BVGW-QACB` 为 `manual_abort_before_enter`，进场前中止，不计一局。）

### Q4（`range_grid21_29`，21 站任意方向覆盖）—— 6 局全清 + 1 早期未全清

| 案例码 | 源数 | 清除 | clear_fail | 每源虚拟秒 | 全清 | 备注 |
|---|---:|---:|---:|---:|:--:|---|
| 3ZJ3-6N8G-ZK22-B5KH | 12 | 12 | 0 | 488.6 | ✓ | |
| F2UK-ARDY-R6ZA-7XJG | 14 | 14 | 1 | 437.0 | ✓ | |
| KXNZ-5Z9X-XS36-8DU8 | 14 | 14 | 0 | 445.6 | ✓ | 6 全向 / 8 定向 |
| X55H-2ZHD-VC6H-EP6D | 12 | 12 | 0 | 470.5 | ✓ | 计时不干净（见下），但模拟器记 12/12 全清 |
| SZZS-7SJB-K6VX-VPRN | 14 | 14 | 0 | 417.3 | ✓ | 11 全向 / 3 定向；修后代码 |
| 6WK5-U77M-QK6K-PU2Y | 14 | 14 | 0 | 444.3 | ✓ | 6 全向 / 8 定向；修后代码 |
| **全清合计** | **80** | **80/80** | | **源加权 ≈ 449.1** | | |
| CNDW-U29G-NUXR-UVKU | 15 | **10** | **431** | — | ✗ | **早期探索/坏策略局**：924 测量、611 切频、431 次清除失败，未全清 |

- **参考对比**：某参考截图 Q3 ≈ 341s/源、Q4 ≈ 658s/源；我方当前策略 Q3 ≈ 249、Q4 ≈ 449，均更优。
- 修后代码（SZZS、6WK5）`transport_failures=0`、summary 正常产出。

### 诚实说明（重要）

- **完整权威记录**：进场的 12 局中 **11 局全清**，唯一未全清的是**早期** `CNDW`（15 源清 10、431 次清除失败），对应当时尚未定型的策略。当前定型策略（`range_area7` / `range_grid21_29`）所跑各局在权威库中**全部 cleared==jammer_count**，且与机器狗 `summary.json` 自报数一致。
- 之前口径"10/10 全清"只统计了跟踪到的成功局，未含 `CNDW` 早期失败与 `X55H`；现改以模拟器统计库为准，如实列出全部。
- 案例码此前有截图 OCR 错误（`6MKS`→`6WK5`、`X55H-22HD`→`X55H-2ZHD`），已按库订正。

### 非计入 / 异常局

- **CNDW（Q4）早期未全清**：10/15、431 次清除失败，非当前定型策略成绩。
- **162156（Q4）send 抖动中止**：发送阶段瞬时网络错误致整局中止，未 `/exit`，**统计库无此行**。已据此修客户端（§3 S0）。
- **X55H（Q4）计时不干净**：`162156` 失败后在同一演练会话原地重跑所得；模拟器记 12/12 全清，但每源时间可能受前次触碰影响。规矩：某局失败即视演练会话已污染，须重开新演练，不原地重跑。

## 2. 代码来源、审计与对拍

- **来源**：Q3/Q4 策略代码来自同学 `NTJ_B` 分支，`git merge origin/NTJ_B` 并入 `B题/B/`（作为基座）。我方原独立开发的是 Q1/Q2（见 `models/q1q2/`）。
- **审计**（多 agent 并发，只读，产物在 `models/q1q2/peer-audit/q34/`）：覆盖搜索、定位清除、路线时间、定向源、总体 5 份报告。结论：**当前 Q3 七站全向覆盖成立、Q4 二十一站任意方向覆盖成立**（已用整数运算独立复核主布局）；主搜索链路无导致漏检/错误停止的真 bug。
- **对拍**：用我方 Q1/Q2 与同学 Q1/Q2 双实现 + 独立 Fraction/枚举裁判做差分。结论详见 `models/q1q2/reviews/`（我方 Q1/Q2 更正确，同学 Q1/Q2 有错答案；此为选型依据，不影响本汇总的 Q3/Q4 策略）。
- **本地大规模**：合并后端到端 4460 局全清（含 ±1° 误差对抗场），无过拟合迹象。

## 3. 本轮健壮性与外围 bug 修复（2026-09-11）

均在 `B题/B/`，用 `mock/.venv/bin/python`（含 numpy/scipy）验证。全套测试 **27 passed / 127 subtests**；主候选 Q3/Q4 mock-http 全清、零回归。

| # | 文件 | 问题 | 修法 | 验证 |
|---|---|---|---|---|
| S0 | `client.py` / `bounded_http.py` | 发送/连接阶段瞬时网络失败重试耗尽后整程崩溃、只留 failure.txt、丢已确认进度 | except 收敛为 `(URLError,OSError,HTTPException,ValueError)`（覆盖 sendall/connect 抖动、IncompleteRead、RemoteDisconnected）；重试**复用同 request_id 与同字节**（绝不换新 ID）；异常路径也写 `summary.json`（status=failed、execution_state、已确认 cleared/virtual_s） | `tests/test_send_failures.py` 真打 socket.sendall/connect：6 种故障 + "服务端已执行才断"歧义场景，断言两次同 ID、只执行一次、恢复后正常落盘；耗尽场景断言失败也落 summary。**已在真实演练路径验证**（Q4 第4/5 局 tf=0） |
| B1 | `route_algorithms.py` | 近似方格当精确格点→无效下界、`certified_optimal` 伪报 | 用 `Fraction` 精确判"坐标是否为格距整数倍"，否则回退始终有效的 `(n-1)·min_edge` 界；`certified_optimal` 要求 `0 ≤ value−下界 ≤ 1e-6`（下界须真为下界） | `_regression_checks()`：三组扰动/精确布局断言下界≤真最优、扰动不再误报 |
| B2 | `route_algorithms.py` | 插入贪心无视比较预算 | 预算耗尽即返回共享初始化序的可行解 | `budget=2 → comparisons=2`；多预算切点全覆盖、非零原点亦然 |
| B3 | `visibility_certificate.py` / `icra_final_checks.py` | `verify_cells` 单独调用即误得覆盖保证 | `verify_cells` 显式返回 `coverage_guarantee=False`+缺失项，assert 全改 ValueError（`-O` 下亦生效）；新增 `certify_layout_coverage`：要求布局/路线/问题类型上下文 + 坐标集精确相等 + `Fraction` 校验叶方块面积精确铺满 3600² 根方形，方给强保证 | `tests/test_visibility_certificate.py`：完整分区+合格叶→过；部分叶/越界站/非凸包内→拒 |
| B4 | `discovery_priority_policy.py` | 对已跳过 RF 的精确已知源重复奖励未来节省 | 删除重复记账项（`JointTaskPolicy` 本就跳过其扫描 RF，节省恒为 0） | 默认 `clear_weight=0` 故主候选零影响；`tests/test_discovery_priority_policy.py` 断言默认不变、启用时不再重复奖励 |

> B1/B2/B4 均不影响当前主候选路径（Q3 走 `remaining_route`、默认 clear_weight=0），属"合并基座的正确性/健壮性补强"。

## 3b. 清除门优化（清除失手时间—风险权衡，2026-09-11）

官方权威统计库显示各局全清但少数局有 1–2 次清除失手（`clear_failure_count`）。失手来自"试探性清除"：定位区域未收紧到 20m 时赌一把清除（赌中省时、赌空浪费一次清除的虚拟时间）。以 **22,320 局** mock 扫参（训练/验证种子分离防过拟合、含 ±1° 误差场与 Q4 定向源）验证时间—失手权衡，最终把试探门（`trial_radius`）：

| 方法 | 原门 | 新门 | 失手变化（独立验证） | 时间变化 | 判定 |
|---|---:|---:|---|---|---|
| Q3 `range_area7` | 80m | **50m** | 2881→2337（−18.9%） | **−0.059 s/源（更快）** | 净赢 |
| Q4 `range_grid21_29` | 40m | **35m** | 1032→808（−21.7%） | +0.155 s/源（+0.03%） | 小代价换稳（已选定） |

- 零失手（20m 门）可达成，但 Q3/Q4 分别 +2.9/+2.2 s/源；时间是计分主指标，故不采用。**未声称任意场景零失手或逐局无回退**。
- 仅改两处配置门限（`coupled_dispatch_experiments.py`、`cover21_experiments.py`），策略类与几何内核零改动。可用构建器参数恢复原门（Q3 `trial_radius=80.`、Q4 `40.`）。
- 完整报告与可复现脚本：[B/CLEAR_GATE_TRADEOFF.md](B/CLEAR_GATE_TRADEOFF.md)、`B/clear_gate_sweep.py`、`B/tests/test_clear_gate.py`；归档 `B/experiments/runs/2026-09-11_clear-gate-*`。

## 3c. 全项目代码 Review（2026-09-11）

多 agent 只读审计,覆盖 Q1–Q4,报告在 [code-review/](code-review/)：[review-q1q2.md](code-review/review-q1q2.md)、[review-q34-core.md](code-review/review-q34-core.md)、[review-q34-policy.md](code-review/review-q34-policy.md)。**三区皆无 P1 阻断**（主候选结果站得住）。发现的 P2 真问题已分 6 个并发 agent 修复并复验（2026-09-11）：

- **客户端/协议**：C1 连接/发送/读头/读正文纳入同一绝对截止；C2 成功响应先校验（拒 nan）再原子提交、解析失败锁停；H1 半包有界读取期限+退出关连接。
- **认证/校验**：整数版证书与 icra_final_checks 的 `assert`→`if/raise`（`-O` 下亦生效）、固定竞赛域与索引口径；回放包含检查覆盖点/线段端部；visibility 见证半径与索引口径修正。
- **核心/mock**：几何裁判返回真包含圆（向外舍入）；coverage 退化相交；intelligent GA 对单点/重复稳健；simulator mock 幂等纳入执行锁（消除重复计费竞态）。
- **策略/入口**：discovery 彻底删除 `clear_weight` 隐藏开关；主入口 `bounded_candidates.py` 仅注册两定型候选、直接实例化、隔离历史实验树（新旧入口逐字段+全轨迹 SHA 一致）。
- **Q1/Q2**：半平面冲突索引口径、同站距离字段、BOUNDARY 世界半径、绘图 Figure 泄漏、F7/F8/T3 输出口径等。

**复验**：Q3/Q4 `tests/` 132 passed / 230 subtests、主候选 mock-http 全清；Q1/Q2 `tests/` 1172 passed、四块 benchmark 285/285、312/330（18 为支撑点顺序良性差异）、531/531、48/48。

## 4. 复现（本地）

```bash
# 本地 mock-http（无需官方模拟器）——用 mock/.venv（含 numpy/scipy）
cd B题/B
../mock/.venv/bin/python -B run_bounded_robot.py --series cover21 --problem 3 --method range_area7      --mode mock-http --seed 11
../mock/.venv/bin/python -B run_bounded_robot.py --series cover21 --problem 4 --method range_grid21_29 --mode mock-http --seed 11
# 测试与回归
../mock/.venv/bin/python -m pytest tests/ -q
../mock/.venv/bin/python route_algorithms.py   # B1/B2 回归
```

官方演练（仅在用户手动登录并开好某题**演练测试**后，由用户说"开了"再跑；命令与 guest 部署见 [B/GUEST_DEPLOY.md](B/GUEST_DEPLOY.md)）。**绝不自动开测、绝不碰正式测试。**

## 5. 待办

- Q3/Q4 **独立建模文档 + 我方独立 benchmark/几何复核**（当前正确性主要靠同学代码审计 + 官方演练全清 + 本地大规模，尚缺我方独立真值 benchmark，类比 Q1/Q2 的 `benchmarks/`）。
- 汇总所有官方演练录制归档（延迟/计时逐笔核对）。
- 与 Q1/Q2 论文合并成整篇（Q3/Q4 的覆盖证书、发现→定位→清除闭环、定向源负反馈几何、耦合调度）。
