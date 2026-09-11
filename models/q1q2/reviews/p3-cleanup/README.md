# Q1/Q2 P3 清理与覆盖圆回归

日期：2026-09-11。范围仅 `models/q1q2/`。评审依据：`../../../../code-review/review-q1q2.md`。解释性整理不改变生产数学判据、误差模型、回退算法或 P1/P2 修复；接口、表示规范和成本统计的有意变化如下。

## A：复现结果与实际根因

运行原有 `benchmarks.q1_circle_cover.run` 得到 **312/330**，共 21,436 项检查。完整原报告保存在 [circle-before.json](circle-before.json)。统计 18 个失败的 `error[].field`，全部为 **`forced.exception`**，不是支撑索引比较失败。

例如 `isosceles_1e-14`：Welzl 随种子导出 `[1,0]` 或 `[0,1]`，圆心均 `(0,0)`、半径均 1，原 benchmark 已按独立支撑 MEC 检验，未要求数组顺序。真正失败在非零高度三点的强制外接圆：精确生产算法返回正确圆，旧 benchmark 却按绝对面积阈值要求 `ForcedSupportError`。

采取两项修改：

1. **生产端规范化**：`circle._export_circle` 在最终输出时排序支撑输入索引。几何计算仍使用原支撑及其坐标，内部 Welzl 栈与精确支撑复核不变；最终索引统一升序。运行器增加 `support.canonical_order` 断言，仍允许不同但合法的最小支撑集合。
2. **修正过时异常合同**：强制三点圆仅在精确行列式为零时必须抛异常。近共线但非零时继续用独立 Fraction/Decimal 真值检查圆心、半径，原有数值容差和未决规则没有放宽；未更改生成器或案例真值。

修改后 **330/330，22,644 项检查**。排序本身并不是消除这 18 个失败的原因；更新强制圆异常预期才消除了实际失败。

## B：22 条 P3 逐项处理

| 评审项 | 落地处理 |
|---|---|
| G2 | 删除停用的 `_enumerated_vertices` / `_deque_vertices` 兼容外壳；保留凸包清理实际使用的 deque 容器。 |
| G3 | `_exact_bearing`、`_exact_row`、`_normal_degrees` 成为显式 dataclass 字段（不参加 init/repr/compare）；角元信息明确为 None，删除 hasattr 分流。注释区分手工二进制 float 系数和十进制度数生成的角锥系数。输入白名单仅允许 init 字段；JSON 导出排除内部精确字段。 |
| G4 | 解释 80 位三角近似、有理谓词及 70 位精度保护带；凸包文档明确近共线内部点清理；删除 dimension lambda 和直径无效 policy。注明交点枚举 O(M³)、全对直径 O(V²)，另计有理数位长成本。 |
| C1 | 删除 forced/contains/enumerate 的无效 policy，并沿调用链删除 ordinary/minimum_circle 的无效传参。覆盖函数保留实际使用的 NumericPolicy。固定相对导出精度命名为 `_EXPORT_RELATIVE_ERROR`，说明这是输出可表示性门槛。 |
| C2 | 覆盖诊断必须接收已算好的 MEC；Q1 同一顶点集只计算一次。保留独立 Thales 精确符号及未决带，未改成半径相减。 |
| C3 | 解释两套 Welzl 栈的 state、child result、强制圆周 boundary；说明浮点提议→原坐标精确复核→精确回退顺序。80 点限制命名，注明枚举 O(V⁴)。 |
| F2 | 删除 radial_interval 未使用的 lower/upper；回夹改为 inner_eps 后显式 min/max，注明内移仅构造实际合法见证。 |
| F3 | 解释 rho_lo 分段、high 线性支撑目标及 violation 的 m² 单位；说明 h² 裁剪阈值不是距离容差。保留 attained 作为片段来源元信息，明确端点仍须 `_boundary_witness` 复核。 |
| Q2-5 | 合并为唯一 `sample_sources`，网格、inward、第二角宽显式传入；合并 `_search` 为 `select_second_point`，保留 frontier 使用的 extra_points。删除 evaluate 的 stage 和无效 SearchConfig.seed；manifest 明确搜索确定性、圆算法 seed=0。 |
| Q2-6 | 生产结果 dataclass 改用关键字构造；frontier 用普通循环检查、构建候选、取最小 J，再按 tie 比移动。方向边界函数改名 `evaluate_and_record_pair`，注明金分割只提供局部合法下界见证。 |
| Q2-7 | 每个评分作用域用 counted_score 单一入口统计实际 score_point 调用，包括基线、重评、救援及中断调用，缓存命中不计。frontier 共享次数/耗时仅记首行专用字段，各行保留各次搜索成本。注明公共点集冻结、审计代际及旧字段作用域；保留 full_chain_audit_pending。 |
| D3 | 启发式比较统一使用 check_admissibility，明确只比较已证 IN。清除时间、移动速度、32/64 边及加密阈值命名；解释当前测量后的虚拟行动成本、外包与严格裕量，并明确不是区间证书。 |
| A1 | 手工 JSON 统一为 measurements 对象；删除重复 rounding_mode 及其对照分支，保留 error_mode 与 rounding_assumption_source。更新测试输入，仍拒绝矛盾模式/宽度/来源；mock 和 JSONL 两个真实入口保留。 |
| A2 | ObservationRecord / BearingMeasurement 关键字构造；assumption_source 改普通 if/return；注释区分 request 重传冲突检查与重复几何测量去重。 |
| PLOT2 | render 文档列 geometry/heatmap/curve/bars 的必需字段、空值、单位及保存前提；统一 panels 数组，更新生产装配与原 P2 测试。CSV 嵌套值用普通循环导出，None 表示未评估。保留 Figure 的 try/finally 关闭。 |
| Q1-1 | 显式 seen_geometry 集合替代 O(N²) any；身份字段只读取一次后排除 None。保留身份、request、同地点不同读数三种检查，注明缺身份不证明同一物理会话。 |
| Q1-2 | 按有无顶点分支后再求圆；无顶点不作无效 MEC 调用，结果关键字装配。空集面积 None、点/线段面积 0 不变。 |
| R4 | 删除 Q2 的 diameter_estimate_m 影子属性及通用 serializer 特判；显式读取 score.J_hat。图号用映射与清楚的默认分支；多 bundle 同名表格用循环拼接，避免覆盖。 |
| INIT1 | 包文档说明 float 输入/输出和高精度/有理几何复核，删除过时的 default float64 描述。 |
| CERT1 | 明确区间证书针对原始 binary float 连续问题，生产角锥用十进制度数语义；不是对所有生产中间近似逐项认证。独立原始输入、局部 MPIntervalContext 均保留。 |
| CERT2 | 解释向外 nextafter、单调端点 min/max、整盒排除与合法下界见证的不同条件。坐标外包推导式展开为两层循环；角点频率/缓存上限命名，说明仅影响性能。解释种子计入 elapsed、超小时间预算不是硬实时。 |
| CERT3 | 删除无合同的 Certificate.to_dict，调用方改 asdict。backend 改为 mpmath.iv；manifest 记录实际可选依赖版本，没有版本选择算法分支。 |

另补坐标口径与概率说明：源点采用世界坐标（米）、alpha 是相对首测方向的弧度、t 无量纲；确定性样本并非来自概率先验。仅可选局部 GDOP 使用高斯辅助假设，主最坏情形模型仍是有界误差。

## 验证

统一解释器：`/Users/flower/math/2026/B题/models/q1q2/.venv/bin/python`。从仓库根目录执行：

```sh
models/q1q2/.venv/bin/python -B -m pytest models/q1q2/tests/ -q -p no:cacheprovider --import-mode=importlib
models/q1q2/.venv/bin/python -B -m models.q1q2.benchmarks.q1_geometry.run
models/q1q2/.venv/bin/python -B -m models.q1q2.benchmarks.q1_circle_cover.run
models/q1q2/.venv/bin/python -B -m models.q1q2.benchmarks.q2_candidate.run
models/q1q2/.venv/bin/python -B -m models.q1q2.benchmarks.q2_worst_diameter.run
models/q1q2/.venv/bin/python -B -m models.q1q2.reviews.p3-cleanup.verify_contracts
```

| 验证块 | 修改前 | 修改后 |
|---|---:|---:|
| tests | 1172（任务基线） | 1172/1172 |
| q1_geometry | 285/285 | 285/285 |
| q1_circle_cover | 312/330（本轮复现） | 330/330 |
| q2_candidate | 531/531 | 531/531 |
| q2_worst_diameter | 48/48 | 48/48 |

前三个非 circle 基线来自修改前已有报告。本轮全套重跑，最终日志均保存在本目录，四个 benchmark 完整报告位于各自目录。

[verify_contracts.py](verify_contracts.py) 额外核验 Q1 一次 MEC/无顶点零次调用、评分调用数与 frontier 共享账本、内部精确字段不泄漏到 JSON、区间证书直接序列化；结果见 [contracts.json](contracts.json)。Q1 CLI 使用 standard.json 的结果/图规格/manifest 保存在 [q1-cli](q1-cli/)。这些附加核验不增加或减少原 tests 的 1172 项，P2 测试仅按新的入口/输入形状迁移，数值与边界断言保留。

四块 benchmark 通过不意味着全输入数学认证，Q2 的 full_chain_audit_pending 等限定保持原样。本轮未执行 Windows 或全套区间认证。
