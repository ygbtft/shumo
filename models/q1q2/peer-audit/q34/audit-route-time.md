# Q3 路线优化与时间目标审计

总体印象：同学已经从“覆盖站点 TSP”推进到“扫描与定位清除任务联合重排”，虚拟时间账本和实验归档比较扎实；当前 Q3 是有合理几何约束的时间导向启发式，尚不是整局时间最优算法，238.95 秒/源也只是特定合成确认批次的成绩。

**优先发现：**`route_algorithms.py:48–55` 将近似方格当精确方格，会给出无效下界，且可复现 `certified_optimal=True` 对应非最优路线；`route_algorithms.py:117–135` 的插入贪心不执行比较预算约束。两项详见“真bug”，目前没有证据表明它们造成当前 `range_area7` 的时间成绩失真。

审计日期：2026-09-11。只读同学工作区 `/Users/flower/math/2026/NTJ_B_wt/B`；本报告的“同学代码”均指该目录，与文档中同学自己引用的第三方/peer不同。我方尚未开发 Q3/Q4，本次不改同学代码，也不建设我方策略。依据我方 [PLAN.md](/Users/flower/math/2026/B题/models/q1q2/PLAN.md)、本地题面/附件2全文提取、GOAL、REPORT、MODELING_TRAPS及指定代码/更新报告。以下 `file:行号` 均指本次读取的 live 文件。

## 路线方案

### 当前实现与历史迭代

- **当前研究主候选是 Q3 `range_area7`。** [REPORT.md:126](/Users/flower/math/2026/NTJ_B_wt/B/REPORT.md:126) 起保留最近 Q3/Q4 结果；报告更上方是后来执行的 Q1/Q2 复核与暂停说明，不能把最下方早期推荐当当前配置。[REPORT_COVER21_UPDATE.md:5](/Users/flower/math/2026/NTJ_B_wt/B/REPORT_COVER21_UPDATE.md:5) 明确本批推荐。
- 工厂定义在 [coupled_dispatch_experiments.py:23](/Users/flower/math/2026/NTJ_B_wt/B/coupled_dispatch_experiments.py:23)：`ring7 + area_prior=True + remainder_weight=1 + dispatch_model='base' + range_skip=True`，实例为 `CoupledCompletionPolicy`。最新确认从旧配置继承这一方法：[cover21_confirmation.py:25](/Users/flower/math/2026/NTJ_B_wt/B/cover21_confirmation.py:25)。7站覆盖的配置/坐标来自冻结 `run_config.json`，并非旧19站三角格。
- `REPORT_ALGORITHM_UPDATE.md` 是早期三角格算法比较；`REPORT_MISSION_UPDATE.md` 的 Q3 `clearance7=255.82` 是87—96种子阶段。它们解释演进，但均不是最新成绩。早期 `active_2opt/active_genetic` 的817.8等数值也不能拿来描述最新主力。
- live CLI [run_bounded_robot.py:23](/Users/flower/math/2026/NTJ_B_wt/B/run_bounded_robot.py:23) 仍默认旧 `icra` 系列，且方法必填；复现当前候选须明确 `--series cover21 --problem 3 --method range_area7`。这是本地合成后端入口，不是官方客户端。
- 本次核对指定5个重点文件及当前调度、测向、几何、客户端共10个文件的 SHA256，全部与最新 cover21 确认快照一致。**文件仍在 live 中不等于当前候选调用它。**静态 `optimize()` 属历史/工具层；当前任务重排实际复用 `adaptive_routes.remaining_route()`。

### 算法逐项判断

|模块|实际目标与机制|审计结论|
|---|---|---|
|`coverage.route`、`Problem.cost`|从原点开始、终点自由的开路径欧氏长度|不是闭合TSP；不强制回原点符合 `/exit` 不移动规则。静态只算路长。|
|`route_algorithms.two_opt`|固定首站，逆转区间，端点自由时包含后缀反转|`77–99` 的边差公式正确；对称距离下内部边抵消。预算/轮数有限，不保证到达2-opt局部最优。|
|最近邻/插入贪心|最近距离选下站/最小增量插入|路径机制正确，保留所有站点；插入贪心有预算bug，见后文。|
|遗传算法|32个体、4精英、锦标赛、顺序交叉、混合变异，部分候选再2-opt|`215–229` 实现与机制相符；排序后的最小抽样索引确是锦标赛优胜者，并非写错选择公式。交叉与扰动固定原点、保排列。没有找到漏站或重复站bug。|
|免疫/蚁群/粒子群/烟花|不同离散搜索机制，共享2-opt初解和部分局部改良|只能按显式混合算法解释，算法名称不提供全局最优保证。|
|`adaptive_routes.remaining_route`|从当前实际位置对剩余点最近邻+最多3轮2-opt|允许逆转首段并计当前点到首站距离，公式正确；`AdaptiveOrder` 每次仅取重排后的首站，移除后再执行，包含定位绕行后的实际位置。|

本次额外做了100组随机排列/交叉/静态与动态2-opt下降验证，均通过。这验证排列与下降性质，不把启发式输出等同于枚举最优。旧 [route_algorithm_checks.py:17](/Users/flower/math/2026/NTJ_B_wt/B/route_algorithm_checks.py:17) 的小规模枚举检查也主要验证下界、合法排列和“输出不可能优于真最优”，并不要求每个方法找到最优。

**消融必须准确命名。** [route_ablation.py:31](/Users/flower/math/2026/NTJ_B_wt/B/route_ablation.py:31) 的 `polish=False` 只取消搜索中的局部改良；[route_algorithms.py:58](/Users/flower/math/2026/NTJ_B_wt/B/route_algorithms.py:58) 仍先构造2-opt初解，`Search.best` 从它启动。因此它是“相同2-opt热启动下去掉后续局部搜索”的消融，不能写成“纯遗传/完全去掉2-opt”。配置已披露公共预处理不计候选比较数；同样次数的 O(n) 全评分和 O(1) delta 比较也不等于同CPU预算。报告对混合算法已有说明，不能据此反指其伪造算法。

## 时间口径正确性

### 任务最终计分：正确

题面 [B题.txt:29](/Users/flower/math/2026/NTJ_B_wt/B/inputs_readonly_extract/B题.txt:29) 明确先保证全清，平均定位清除时间为“定位清除总时间/被清除个数”。附件2第4节及第8节给出：

\[
T=L/5+5N_{measure}+N_{switch}+5N_{clear,success}+3N_{clear,fail},\qquad t=T/N_{cleared}.
\]

成功清除5秒已经含光学定位3秒与激光2秒，不能另加一次光学时间。只有测量可能切频，clear不改变测向频道；初始位置原点、初始频道1；enter/exit不增加虚拟时间。没有回原点要求。

[client.py:64](/Users/flower/math/2026/NTJ_B_wt/B/client.py:64) 在接受响应后更新虚拟时钟、位置，只有 `/measure` 更新频道；不自行按一个简化路长推算最终成绩。[icra_confirmation.py:134](/Users/flower/math/2026/NTJ_B_wt/B/icra_confirmation.py:134) 取后端实际 `virtual_time_s/len(sim.cleared)`。旧 [metaheuristic_experiments.py:179](/Users/flower/math/2026/NTJ_B_wt/B/metaheuristic_experiments.py:179) 也是同口径。

本次独立读取最新 `range_area7` 的195条完整任务轨迹，共27,169条记录，按实际动作重算移动、检测、切频、成功/失败清除：

- 逐动作整数微秒差异 **0**，最终总时间、成功清除数及每源时间与CSV全一致。
- 63局在最后一个成功清除后仍有虚拟耗时，说明没有截断必要的未知数量排查。
- 后端 [mock/simulator.py:110](/Users/flower/math/2026/NTJ_B_wt/B/reference/shumo-b/mock/simulator.py:110) 将每段移动时间舍入到最近微秒；不舍入实数公式最大累计残差约 `4.89e-6 s`。这不构成漏计费用。微秒舍入的具体实现属于本地后端口径，不把它冒称附件明确规定。

跨场景汇总应区分 `mean(T_i/n_i)` 与 `sum(T_i)/sum(n_i)`。最新 [icra_confirmation.py:107](/Users/flower/math/2026/NTJ_B_wt/B/icra_confirmation.py:107) 两者分别保存，GOAL的240目标采用前者；这与单局题面定义不冲突，但截图究竟如何汇总40个源尚不清楚。

### 优化器评分：不是完整虚拟时间目标

[route_algorithms.py:68](/Users/flower/math/2026/NTJ_B_wt/B/route_algorithms.py:68) 只累计站间距离。在**所有站都要访问、站内服务费用不随顺序变化**的抽象模型中，最小L等价于最小L/5；真实任务的发现时刻、共享测向、清除绕行、提前停止与切频都随路线变，不能沿用该等价。

当前 `range_area7` 的 `dispatch_model='base'` 进入 [joint_task_policy.py:67](/Users/flower/math/2026/NTJ_B_wt/B/joint_task_policy.py:67)：将剩余扫描站和已知源的MEC圆心当作任务点，重排后只执行首个任务。**任务排序仍没有直接计入各任务检测数、切频和清除成功概率。**

当前测向选点 [completion_sensing_policy.py:75](/Users/flower/math/2026/NTJ_B_wt/B/completion_sensing_policy.py:75) 用面积先验下协方差代理，评分是：

\[
\text{residual uncertainty}+0.08\left[(\|q-current\|+\|q-MECcenter\|)/5+5\right].
\]

这里将米量纲不确定度和带权秒数混合；0.08是启发式权重。包含下一次检测和到预测完工点的移动，却没有逐项模拟切频、可变后续检测、成功/失败清除及后续扫描。它应称“时间导向的测向代理评分”，不能称“直接最小化虚拟时间/最坏定位直径”。面积均匀先验与协方差更新也不是题面规定的噪声/位置分布。

与我方 PLAN 的关系：我方Q2以完整保收候选域内最坏定位直径为主，移动只在效果相当时择优；同学Q3允许为整局效率权衡几何不确定度。这是任务目标不同，不能判为违反Q2设计；也不能把他们的Q3代理选点当作我方Q2最坏值求解器。最终清除应继续依赖MEC外包而非协方差或直径一半；本实现把这两层分开了。

### 现实耗时：独立指标

确认程序在策略构造后才启动单局墙钟/CPU，另记初始化；预计算路线、场景构造及轨迹压缩不在单局 `wall_s` 内：[icra_confirmation.py:128](/Users/flower/math/2026/NTJ_B_wt/B/icra_confirmation.py:128)。进程内mock不含真实HTTP/官方服务延迟，因此0.026秒量级不能直接与截图1.19秒比较。客户端确实读取 `remaining_real_duration_s` 建截止时间；虚拟时间低不等于现实限时必能满足。

## 报告结果可信度

### Q3数值可追溯，但不是官方或稳定达标证据

本次直接重算逐局CSV，未照抄报告表：

|同一 `range_area7` 的确认批次|普通任务数|普通算术平均秒/源|
|---|---:|---:|
|117—126，coupled|150|259.80055|
|127—136，history|150|238.15398|
|137—146，deferred|150|247.52257|
|147—156，cover21|150|238.95168|
|四批合并|600|**246.10720**|

最新45个压力案例平均 **281.40031秒/源**。238.95确实低于240，合并普通与最新压力均未低于240。相同方法在不同场景批次间波动明显，不能把批次变容易解释成算法提升。[REPORT_COVER21_UPDATE.md:74](/Users/flower/math/2026/NTJ_B_wt/B/REPORT_COVER21_UPDATE.md:74) 已主动说明这一限制；没有证据说该报告刻意改分母刷达标。

GOAL记载截图为Q3 **341.05秒/源、40/40、程序1.19秒**，并明确截图没有逐局数据、源码与运行条件。截图值只能作外部参照，既不一定是40局，也不能确定其跨局权重。当前238.95的数值较小，**不足以声称击败该官方实现**；240是研究挑战目标，不是题目规定阈值，更不是任意场景耗时上界。

### 真值独立性的三个层次

1. **与决策逻辑隔离：有实质支持。** 最新策略只获得Client、公开站点和固定参数；`regions`源于合法反馈，不读取真实源位置/半径/数量。生成器与后端位于 `reference/shumo-b/mock`，真值另存 `scenarios_scoring_only`，评分才读取清除集合。静态算法更完全不导入模拟器。Python私有属性不等于安全沙箱，但本次检查调用链没有发现主动偷读真值。
2. **冻结后新场景：代码结构与归档支持。** [icra_confirmation.py:121](/Users/flower/math/2026/NTJ_B_wt/B/icra_confirmation.py:121) 先冻结，再迭代生成场景；[cover21_confirmation.py:96](/Users/flower/math/2026/NTJ_B_wt/B/cover21_confirmation.py:96) 校验训练阶段内核哈希。新普通种子147—156、新压力SeedSequence流与训练分开。只是归档/代码证据，不能独立证明作者此前绝未查看过任何数据，也不消除多轮反复调研对整体生成器的适应。
3. **与官方真实分布独立一致：没有证据。** 普通场景由mock生成，采用均匀/贴边/成簇位置与5种误差模型；接收半径默认均匀等均是实验设计。压力是手工生成的边界、近共线、最小半径等构型。后端独立实现有助于防止策略与自身模拟器共享同一bug，但仍是合成真值，不能证明官方物理边界、噪声场和场景分布一致。

150个普通记录是3位置分布×5误差×10种子。同位置分布/种子跨误差复用源几何，不能作为150个完全独立的源布局；压力45个为15组几何×3误差。累计59514是多方法、多阶段执行数，也不是59514个独立场景。按种子块做统计优于把所有行当独立，但十个种子块仍不足以保证未知官方分布的尾部。

本次另外不加载源文件/模拟器，仅以归档反馈重放当前类的3条任务，共467个请求：路径、频道、请求标识等完全一致，坐标在 `1e-7m` 容差内一致，实际最大差约 `3.03e-12m`。这支持所查轨迹可由公开反馈驱动，**不是三次新的物理全清验证**，也不能替代全域几何证明。

### 路线与调度/覆盖的耦合

当前组合比“先走完整扫描TSP再定位”合理：清除任务与扫描站同列、按实际落脚点重新规划，已知频道可共享测向；已发现16个不同频道才允许取消剩余发现任务，否则继续完整覆盖并清完所有已知源。[joint_task_policy.py:79](/Users/flower/math/2026/NTJ_B_wt/B/joint_task_policy.py:79) 与 [efficient_joint_policy.py:15](/Users/flower/math/2026/NTJ_B_wt/B/efficient_joint_policy.py:15) 给出终止路径。排序保排列只是保持覆盖证书的前提之一；具体站点全域覆盖仍需另证，不能拿route checks替代。

[耦合距离删除:68](/Users/flower/math/2026/NTJ_B_wt/B/coupled_dispatch_policy.py:68) 仅对已知且未清源，在扫描期间证得 `dist(station,MECcenter)>1500+MECradius+1e-5` 时跳过RF。若MEC确实外包真源，这个无接收判据成立；不会据此删除未知频道或伪改客户端状态。不过跳过测量改变频道、测量记忆等，可能影响未来调度，所以**“删掉必无信号RF”不自动保证整局每例更快**。后续faithful/deferred版本专门维护内部计划，正说明两种保证应区分。

局部清除采用20m顶点圆盘交集中的最近点，局部省路成立不等于全局省路。当前探测评分也只考虑预测圆心，不显式考虑剩余扫描任务。`REPORT_MISSION_UPDATE.md` 保留Q4反例：定位任务省652.76秒，扫描从7站增至17站，多2183.32秒，整局慢1530.56秒。它虽是Q4实例，却直接说明联合任务代理仍有局部选择与全局发现顺序失配，不能承诺Q3无此类现象。

对于另行试验的服务入口/出口有向路线，[coupled_dispatch_policy.py:29](/Users/flower/math/2026/NTJ_B_wt/B/coupled_dispatch_policy.py:29) 明确补了反转区间内部所有有向边的差，未犯“把对称2-opt边差直接套有向任务”的错误。但入口、出口和内部服务常数只是该代理模型的固定量，实际服务随新反馈变化；当前Q3 `base` 也未启用这一有向版本。

## 真bug

### B1：近似方格推导出无效下界，并可错误标记最优（P2，保证有效性）

**位置：**[route_algorithms.py:48](/Users/flower/math/2026/NTJ_B_wt/B/route_algorithms.py:48) 的 `np.allclose(...,atol=1e-8)`，接着49—55行以精确棋盘格假设断言同色边至少 `sqrt(2)*min_edge`；[183行](/Users/flower/math/2026/NTJ_B_wt/B/route_algorithms.py:183) 用该下界提前结束搜索，[387行](/Users/flower/math/2026/NTJ_B_wt/B/route_algorithms.py:387) 输出认证标识。

精确方格上的证明思路正确，但“坐标接近整数倍”不保证实际边长满足精确格点下界。输入合法且满足要求的四站：

```python
points = [[0,0], [1000,0], [999.999995,1000], [2000,0]]
```

枚举原点固定的全部6种排列：真最优 `3414.2135588375613m`，程序下界 `3414.213562373095m`，下界反而高 `3.53553378e-6m`。

进一步把第三站改为 `[999.9999988,1000]`，`optimize(...,'insertion_greedy')` 返回：

- `certified_optimal=True`；返回路长 `3414.213563221623m`。
- 枚举最优 `3414.213561524567m`；差 `1.69705618e-6m`，超过其认证使用的 `1e-6m` 容差。

**影响范围：**这是可复现的无效认证，不应照搬该通用“最优”标签。绝对误差很小，不是造成几十秒/源差异的性能错误；没有据此否定精确规则格点的解析最优路线，也未证明当前ring7候选受影响。建议我方复用时仅对有精确格点证据的布局启用棋盘界，或为扰动扣除严格误差上界；其余用始终有效的最小边长度界。

### B2：插入贪心无视比较预算（P2，资源合同）

**位置：**[route_algorithms.py:117](/Users/flower/math/2026/NTJ_B_wt/B/route_algorithms.py:117)，129—130行只累加计数，不检查 `budget.remaining`；[373行](/Users/flower/math/2026/NTJ_B_wt/B/route_algorithms.py:373) 直接调用。

同一四站输入调用 `optimize(points,'insertion_greedy',budget=2)`，返回 `comparison_budget=2, comparisons=11`，即1次初解评分加10次插入比较。因此“统一预算限制所有候选方法”不成立。更大站点集合会继续完整枚举插入位置，不因预算耗尽停止。

旧检查 [route_algorithm_checks.py:26](/Users/flower/math/2026/NTJ_B_wt/B/route_algorithm_checks.py:26) 只对 `STOCHASTIC` 方法断言预算，不涵盖插入贪心，故没发现。公共初始化2-opt本就明确在该比较预算之外，应与这个未披露的预算失效分开。当前Q3通过 `remaining_route()` 调度，不调用插入贪心，所以这不推翻238.95的重算结果。

### 未升级为当前成绩bug的边界

- 静态 `cost` 不含动作费、当前代理非完整时间目标、`polish=False` 仍用2-opt热启动，都是必须解释的范围限制；未把它们误写成已复现漏计或交叉算法错误。
- [metaheuristic_experiments.py:135](/Users/flower/math/2026/NTJ_B_wt/B/metaheuristic_experiments.py:135) 的 `trace_metrics` 不检查 `accepted`，也不去重幂等重试，清除只统计总调用数。它适用于现有全接受、无重试的mock轨迹；若直接拿来核算官方/客户端录制，可能把未执行/重放动作算进移动与检测计数。最终时间来自后端，不是这个函数，且本次所查195局全接受，故不认定当前分数被污染。
- 早期训练汇总 [spatial_decision_experiments.py:164](/Users/flower/math/2026/NTJ_B_wt/B/spatial_decision_experiments.py:164) 用 `per_source_s or 0`，零清除失败会被计成0秒/源，应保留失败单列。最新确认用另一个汇总函数，本次所查均非零清除；这是复用旧实验脚本时的明确警惕点，不据此指控现有全清均值错误。

## 可复用点

1. **优先复用动作账本与实验结构。** 全序列响应计分、清除不切频、成功/失败分费、初始化与CPU分列、最后清除后搜索计时、同场景配对与保存回退；先用小型独立账本核算，避免优化了另一个指标。
2. **复用开路径2-opt、动态剩余站重排与排列不变量。** 首点固定/当前起点、自由终点、后缀反转、有向边另算内部反向代价这些实现细节处理得对。不移植有问题的近似棋盘认证或无预算插入实现。
3. **复用“覆盖保底+反馈定位+显式结束证书”的架构。** 未知频道始终保留，16源上限须来自真实发现；已知源的几何排除与未知源覆盖分开。对于我方纯角锥Q1模型，接收半径/目标圆等物理裁剪应在后续Q3层加入，不倒灌修改Q1定义。
4. **复用MEC清除域和已知源无接收判据的思路。** 先保证真源包含，再判断20m保证清除或1500m必无信号；仅对充分证据删除动作，不用协方差替代保证圆。现有几何数值退化已被他们自己在REPORT顶端承认，不能随整套代码一并继承“任意病态输入均可靠”的保证。
5. **学习实验上的克制。** 参数先冻结、新种子确认、普通/压力分开、失败与变慢案例保留；但必须注明合成分布、布局复用和源数权重。对我方而言，可参考240作为工程目标，不能将合成单批达标写成官方成绩。

本次验证产物：[验证脚本](./verify-route-time.py)、[结构化结果与哈希](./route-time-validation.json)、[195局独立拆账](./route-time-trace-recompute.json)、[运行日志](./route-time-verification.log)。运行命令：

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/flower/math/2026/B题/models/q1q2/.venv/bin/python -B /Users/flower/math/2026/B题/models/q1q2/peer-audit/q34/verify-route-time.py
```

核验过程保留的解释：首次实数时间核账因逐段微秒舍入未通过严格相等；首次逐字JSON重放因约1e-12m浮点坐标差未通过。随后分别使用后端公开微秒取整规则和明确的坐标容差复查，没有改变策略或轨迹。未重跑大规模策略矩阵、未连接官方服务、未验证全部覆盖证明或所有数值退化路径。上述结论的证据范围仅限本报告列明的实现检查、枚举反例、账本复算与反馈重放。
