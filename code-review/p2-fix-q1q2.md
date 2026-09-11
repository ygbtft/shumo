# Q1/Q2 指定 P2 修复与验收记录

2026-09-11。修复范围仅为 G1、F1、Q2-1、Q2-2、Q2-4、D1、D2、PLOT1、R1、R2、R3。未处理报告中的其他 P2/P3，未改 circle.py、精确几何谓词、误差角宽定义或 Q3/Q4 主候选代码。工作区原有及同期其他修改均保留。

11 项修复和新增回归已完成。**验收不能标为全部通过：圆 benchmark 的 329/330 门槛与当前已有精确圆合同冲突，修前独立复跑及修后均为 312/330。** 没有修改真值、放宽 benchmark 或恢复已修正的面积阈值来提高计数。其余三个 benchmark 均全过。

## 每条 finding 的根因、修复与复现

修前复现使用当前基准提交中的 Q1/Q2 Python 文件，在临时独立目录运行同一脚本；修后使用工作区。输入和脚本见 [reproduce.py](p2-evidence/reproduce.py)，原始输出见 [修前](p2-evidence/reproduce-before.json)、[修后](p2-evidence/reproduce-after.json)。这两个输出不把静态审计项伪称为已观测到排序翻转。

| Finding | 根因与改法 | 复现前 → 后；回归证据 |
|---|---|---|
| G1 | 去重数组索引冒充输入索引。保存每行首次出现的原始下标，冲突诊断映射回调用者输入。 | `x≤0,x≤0,y≤0,x≥1`：`(0,2)`、子集 UNBOUNDED → `(0,3)`、子集 EMPTY。`test_g1_conflict_indices_reproduce_empty_original_subset`。 |
| F1 | 同站特判把 near 半径下界写作实际闭包距离。保留同站 IN 结论，距离调用 `closure_distance`。 | 首站 `(0,0)`、目标圆 `(1000,0),R=1`：5 → 999 m；方向/信号仍 IN。`test_f1_same_station_reports_actual_clipped_distance`。 |
| Q2-1 | 世界半径只覆盖首站，却无条件宣称实际合法。改为 `max(rho_lo,r1,r2)`，超过 rho_hi 的世界拒绝进入见证；评分排除第二站绝不可能接收的源样本。存在性见证明确不证明全世界保收。搜索和 frontier 标出 `reception_guarantee`；BOUNDARY 不进入条件清除保证链。 | `q=(-1e-10,0)` 仍 BOUNDARY。原两世界分别 `rho=1000/1500 < r2` 却合法；现 1000 m 源使用 `rho=1000.0000000001`，1500 m 源因所需半径超上限被排除；此两点云评分只剩合法单点、J_hat=0。条件诊断不发布动作；直接清除诊断为 `RECEPTION_UNRESOLVED`。`test_q21_boundary_existence_worlds_share_a_legal_radius`。 |
| Q2-2 | 独立边界只采当前层，自定义网格分母不整除时丢失旧点。边界与 q 附近 near 角样本均累计 0…level；方向接触点维持原累计规则。 | `((4,4),(5,5),(6,6))`，首站 `(1000,0)`：32→51 丢 11 点，修后 32→62 丢 0 点。回归同时检查带 q 和不带 q 的三层集合包含关系。 |
| Q2-4 | 初始边界整圈、单次评分、接触点补充及 frontier 公共阶段缺少截止检查。传同一 deadline 至采样内循环、边界二分、评分块/点对、局部细化、终选项和条件诊断项。完整公共轮次才提交；中断不混排。 | 同机修前 0.001/0.01 s 预算约 0.2193/0.2193 s 返回；修后约 0.00111/0.01007 s。确定性时钟测试验证采样/接触点/评分内部中断；模拟 frontier 第一遍完成、第二遍中断，原结果完整保留并标 `FRONTIER_COMMON_TIME_BUDGET`，公共比较 `NOT_COMPLETED`。 |
| D1 | 任何 near 都直接赋予 ON_SITE，即便与固定首次 direction 矛盾。先拒绝空 F、同站反馈变化、闭包距离已证明不可能的 near；再检查保收前提。空样本不作为不可能证明。 | 同站 near：ON_SITE、5 s → `INCONSISTENT_FEEDBACK`、无动作时间。空 F/同站不同 direction 也拒绝；合法 q 的 near 即使样本为空仍保留 5 m 解析保证及 5 s。4 个相关回归用例。 |
| D2 | 比较启发式的补点漏传 ε₂、near 偏移，随后公共包装丢失补救元数据。显式传配置，先保留各点局部见证，再以公共并集复评；旧推荐点复评也显式传角宽。 | 静态原值固定 1°/1e-7；回归以 2°/1e-4 检查每次补点参数和最终共同点集，且各局部见证进入最终并集。不声称默认排序发生变化。`test_d2_configured_contact_sampling_and_common_witness_retention`。 |
| PLOT1 | `close` 只在两个格式保存成功后执行。Figure 创建后用 `try/finally` 关闭。 | 未知 kind：泄漏 1 个 Figure → 0；另测 savefig 异常仍关闭。`test_plot1_figures_close_even_when_render_fails` 两个参数化用例。 |
| R1 | 全局最坏点对无条件画入所有反馈面板。绘线前用该面板完整反馈（含 β）重新核验两端点。 | direction 面板 `[True,True]` 保留；near 面板原 `[False,False]` 错线 → 无线。判定包含 bearing，并非只比较 branch。 |
| R2 | F8 条带近似隐用 (1°,1°)，精确曲线用实际角宽。两者统一用首次半宽和结果配置 ε₂；图注注明角宽；绘图源采样使用结果网格/偏移/ε₂，并注明是重建点集。 | 双 2°：近似面积 9.7420458566 → 38.9681834262 m²，与独立公式一致，原值为正确值 1/4。与 R1 合并的真实 bundle 回归通过。 |
| R3 | T3 使用已废弃 deque 的复杂度。写明实际有界精确交点枚举、全对直径、Welzl 支撑复核、圆枚举回退及有理数位长开销。 | `deque/vertex recheck` → `exact_enumeration O(M³)`；直径 `O(V²)`，圆枚举回退 `O(V⁴)`。`test_r3_complexity_table_describes_executed_algorithms`。 |

预算为软预算，不能打断正在执行的一次 NumPy/几何原子调用。每次选点搜索各有 `time_budget_s`，整条 frontier 的公共补点/复评另有一次相同预算；不是每个候选重新领预算。公共阶段超时保留原搜索结果，但明确这些结果没有完成跨预算公共比较，不能据此宣称 frontier 单调。搜索终选/救援被打断时只使用已完成的公共比较或共同粗网格缓存。

`posterior_contains` 的既有 K 成员定义保持不变；它本身不证明保收。拒绝“保收未决→清除保证”的入口在 `_conditional_diagnostics` 和 `clearance_summary`。修复过程中曾尝试在布尔探针中增加域外接收筛选，因超出必要修复而撤回；最终 candidate benchmark 为 531/531。

## 测试结果

新增测试文件：[test_p2_review_regressions.py](../models/q1q2/tests/test_p2_review_regressions.py)。原 `test_review_regressions.py` 只给相关 mock 函数增加 deadline 参数接收，不改变断言。

| 指定环境与测试范围 | 结果 | 日志 |
|---|---:|---|
| `models/q1q2/.venv/bin/python`，`models/q1q2/tests/` 全套 | 1172 passed | [q12-tests-final.txt](p2-evidence/q12-tests-final.txt) |
| `mock/.venv/bin/python`，从 B 目录运行 `tests/` 全套 | 132 passed，230 subtests passed | [b-tests-final.txt](p2-evidence/b-tests-final.txt) |
| `mock/.venv/bin/python`，`mock/tests/` 全套 | 135 passed | [mock-tests-final.txt](p2-evidence/mock-tests-final.txt) |
| `mock/.venv/bin/python`，新增 P2 回归 | 20 passed | [p2-tests-mock-env.txt](p2-evidence/p2-tests-mock-env.txt) |

命令（除注明 B 的一条外均在仓库根目录）：

```sh
models/q1q2/.venv/bin/python -B -m pytest models/q1q2/tests/ -q -p no:cacheprovider --import-mode=importlib
# cwd: B/
../mock/.venv/bin/python -B -m pytest tests/ -q -p no:cacheprovider
# cwd: 仓库根目录
mock/.venv/bin/python -B -m pytest mock/tests/ -q -p no:cacheprovider --import-mode=importlib
mock/.venv/bin/python -B -m pytest models/q1q2/tests/test_p2_review_regressions.py -q -p no:cacheprovider --import-mode=importlib
```

首次额外运行 mock/tests 时从 mock 目录启动，出现包路径收集错误；依照 mock/README.md 改为根目录启动后全过，没有改测试或安装依赖。

## 四块 benchmark

直接运行各 `models.q1q2.benchmarks.<area>.run`，不改 cases.jsonl、生成器、容差、评分脚本。结果归档在本目录 `p2-evidence/`；原 benchmark/report.json 执行后恢复原字节，避免覆盖历史账本。

| Benchmark | 用户指定门槛 | 本次结果 | 验收 |
|---|---:|---:|---|
| q1_geometry | 264/285 | **285/285** | 达标 |
| q1_circle_cover | 329/330 | **312/330** | **未达指定门槛；修前已为此值** |
| q2_candidate | 502/531 | **531/531** | 达标 |
| q2_worst_diameter | 46/48 | **48/48** | 达标；A=0、B=0、C=40，另 8 项合同测试通过 |

[几何报告](p2-evidence/q1_geometry-after.json)、[圆报告](p2-evidence/q1_circle_cover-after.json)、[候选报告](p2-evidence/q2_candidate-after.json)、[最坏直径报告](p2-evidence/q2_worst_diameter-after.json)。

圆基线冲突已由修前实际复跑确认：[circle-before-rerun.json](p2-evidence/circle-before-rerun.json)，结果 **312/330、21436 项检查**。修前修后的 18 个失败 case_id 完全一致，失败字段全部为 `forced.exception`；本次未引入圆 benchmark 回归。已有 [circle-fix/fix-report.md](../models/q1q2/peer-audit/circle-fix/fix-report.md) 也记录了同一结果。旧脚本把固定绝对面积阈值以内的非共线三点当作必须抛 `ForcedSupportError`；现有生产代码以精确有理谓词区分非共线和共线，这是先前已完成的正确性修复。为达到 329/330 恢复旧阈值会改变数学合同，且不属于此次指定 P2；本次保留并显式报告冲突。

## 主候选未受影响的验证

按现有主候选命令，在 B 目录使用 `../mock/.venv/bin/python`，同为 seed=11 的本地 mock-http，使用 runner 自建的随机 loopback 端口：

```sh
../mock/.venv/bin/python -B run_bounded_robot.py --series cover21 --problem 3 --method range_area7 --mode mock-http --seed 11
../mock/.venv/bin/python -B run_bounded_robot.py --series cover21 --problem 4 --method range_grid21_29 --mode mock-http --seed 11
```

| 主候选 | cleared/sources | all_cleared | 请求数 | transport_failures | official_calls |
|---|---:|---|---:|---:|---:|
| Q3 range_area7 | 10/10 | true | 137 | 0 | 0 |
| Q4 range_grid21_29 | 10/10 | true | 325 | 0 | 0 |

原始 stdout：[Q3](p2-evidence/q3-mock-http.txt)、[Q4](p2-evidence/q4-mock-http.txt)，含独立 `B/robot_runs/...` 轨迹目录。此证据证明本次 seed=11 主候选均全清，不外推为所有随机场景保证。本次没有向官方服务发送请求。

文件摘要、基准提交、运行环境和主候选轨迹位置见 [manifest.json](p2-evidence/manifest.json)。
