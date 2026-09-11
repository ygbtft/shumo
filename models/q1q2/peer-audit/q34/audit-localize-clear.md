# Q3 定位与清除调度审计

总体印象：同学的主力方案把“保证发现—包含性定位—有限清除”接成了闭环，主要风险在效率模型、保证的适用范围和数值实现边界；本次没有复现当前 Q3 主力的漏清或误清。

**优先结论：**发现一处可复现的保证表述缺口：`SERVICE_AWARE_GUARANTEE.md:13` 的“零权重复用原路线”仅对 `free` 成立，`locked` 有反例；另确认历史 `discovery_priority_policy.py:79–80` 的清除奖励重复计入已经免去的 RF，原报告已承认、当前主力未采用。二者均不能写成当前 `range_area7` 漏清。详见“真bug”。

审计日期：2026-09-11。同学工作区为 `/Users/flower/math/2026/NTJ_B_wt/B`，下文未加前缀的代码与保证文档路径均相对此目录；“我方 PLAN”专指 `/Users/flower/math/2026/B题/models/q1q2/PLAN.md`，不是同学目录的同名文件。只读审计同学 live 根目录代码，未修改策略、附件、场景或旧实验；新增验证与报告仅写我方 `peer-audit/q34/`。

## 调度思路

### 先辨认当前主力与历史迭代

已读 GOAL、REPORT、MODELING_TRAPS、指定保证与更新文档，并对照题面提取全文、附件2协议及我方 PLAN 的 §3.7、§4、§5、§6、§7.9。

[REPORT.md:116](/Users/flower/math/2026/NTJ_B_wt/B/REPORT.md:116) 明确以下是此前封存记录；顶部最新活动是 Q1/Q2 benchmark，持续优化暂停。封存阶段留下的主要候选在 [REPORT.md:122](/Users/flower/math/2026/NTJ_B_wt/B/REPORT.md:122)：**Q3 `range_area7`，Q4 `range_grid21_29`**。这不是所有 CLI 的默认配置：`run_bounded_robot.py:20–47` 要求显式 method，series 默认还是 `icra`。

`service_aware_policy.py` 是存在于 live 根目录的较新研究实现，但不是已替换主力的最终方案。其 [PAUSED.md](/Users/flower/math/2026/NTJ_B_wt/B/experiments/runs/2026-09-11_service-aware-dispatch/PAUSED.md) 记录标量组 1395 次训练全清、向量组另有未完成后审计工作，未生成 157—166 新确认，阶段未最终归档。不能因为文件较新或有 GUARANTEE 就把它当成经过新确认的推荐版本。

| 文件/策略层 | 实际职责与地位 |
|---|---|
| `policies.py`、`intelligent.py` | 基础反馈处理、角锥定位、有限主动测向与光学兜底；遗传路线和有限假设选点是早期工具，不是当前 Q3 主力调度的全部内容。 |
| `joint_policy.py` | 早期 Q3 immediate / deferred / opportunistic 对照；可按协方差代理选点，扫描后选择清源时机。这里的 `mode="deferred"` 是推迟清源，**不是**后来的 DeferredScan 请求删除。 |
| `joint_task_policy.py`、`efficient_joint_policy.py` | 把未访问站和已知未清源放入同一任务集合；加入“已实际发现16频道即可结束发现阶段”。这些仍是主力继承链。 |
| `completion_sensing_policy.py`、`clearance_policy.py` | 当前 Q3 的测向排名与清除落点：均匀面积积分先验、剩余路程代理、最近保证清除点。 |
| `coupled_dispatch_policy.py` | 距离证书删除、源服务入口/出口代理、固定站序插入等不同开关；Q3 主力实际使用 `dispatch_model="base", range_skip=True`。 |
| `fast_dispatch_policy.py` | 同一有向路线模型的计算加速；不产生新的定位信息。 |
| `faithful_skip_policy.py`、`deferred_skip_policy.py` | 为匹配的无删除基线维持计划状态，分别删除原地 RF、延后被删 RF 携带的移动；属于可选策略。 |
| `historical_pair_policy.py`、`batched_history_policy.py` | 用成功锚点与历史双负点保守收缩区域；后一文件保留裁剪顺序，只做批量预筛。非当前 Q3 默认。 |
| `safe_sensing_policy.py` | 更完整的全向保收充分检验，以及候选点上的连续示向分箱上界；是研究对照，当前 `range_area7` 没有调用它。 |
| `cooperative_policy.py` | 历史 Q3 共享探测、额外未知频道扫描及连续覆盖证书删站；不能把离散发现网格误当删站证明。当前主力共享来自 JointTask 层。 |
| `service_aware_policy.py` | 新增“先扫站、后清已知源”的检测费用次序罚项，是冻结当前区域的代价代理；训练后暂停。 |

当前 Q3 配置由 [coupled_dispatch_experiments.py:23](/Users/flower/math/2026/NTJ_B_wt/B/coupled_dispatch_experiments.py:23) 明确给出：七站、`area_prior=True`、`remainder_weight=1`，加 `range_skip=True`。主调用链为：

```text
CoupledCompletionPolicy
  → CompletionClearancePolicy → ClearanceJointPolicy
  → EfficientJointPolicy → JointTaskPolicy → JointPolicy → Policy

run: JointTaskPolicy.run
next_task: CoupledDispatchMixin(base) → EfficientJointPolicy → JointTaskPolicy
complete_source: CompletionClearancePolicy.complete_source
clear: ClearanceMixin → JointTaskPolicy → Policy → Client
```

### 何时继续探测，何时清源

Q3 七站是原点加半径1140米的六个等角点。`ring_coverage.py:11–34` 同时检查内部与边界，连续最远最近站距离为 **992.689147米 < 1000米**，因此适用于全向源。这个证书不能直接外推到 Q4。

每轮将未访问站作为 `survey` 任务，已发现未清源作为 `source` 任务，源任务暂以 MEC 中心表示；最近邻加 2-opt 得到候选顺序，只执行第一项，再基于最新反馈重算。入口在 `joint_task_policy.py:67–98`。所以当前 Q3 **不是每发现一个源立即清完，也不是先固定扫完七站**。

选中扫描任务后，在该站检测未清频道；已知区域已能保证20米清除的频道可免测，其他已知频道还可按严格距离证书免测。未知频道不能用区域证书删除。扫描期间 `_surveying=True` 抑制跨频道共享与任务插入；near 的实际清除仍会执行。

选中源任务后，当前 Q3 原子完成该源，最多3次主要主动测向，不会在每次测向后退回任务调度。`completion_sensing_policy.py:105–137` 的分支是：

1. 包围半径 `R≤20−10⁻⁵`：立即做保证清除。
2. `R≤trial_radius` 且还未试过：允许一次非保证的圆心光学试探；当前 Q3 继承默认80米试探门槛。失败不宣称已定位，也不删除区域，随后在圆心测向。
3. 否则从保收候选中选点测向；排名使用面积积分节点、线性化协方差、移动及预测完工路程。它是启发式，不是实际源概率分布或连续 minimax 最优解。
4. 预算用完或测向无信号：进入有限光学兜底。

`JointTaskPolicy.share_at` 可在定位/清除落点顺便测其他已知源，上限默认6个，且禁止递归共享。它不会搜索任意未知频道；尝试位置记忆防止无意义的同地重复。共享的几何评分只是是否值得多测的过滤，不是排除源的依据。

Q4及历史 packet 方案才把一次测向/完整一对探测作为分包任务。`interleaved_policy.py:97–160` 的 `_rounds[ch]` 跨任务累计，不会每次恢复重置；默认10轮、最多20次主要 RF，暂停预算默认16、允许上限24。Q3 主力不能照搬这些数字：它实际仍用原子3次测向。

## 清除正确性

### 从 direction 到“可以保证清除”

[policies.py:23](/Users/flower/math/2026/NTJ_B_wt/B/policies.py:23) 根据反馈分三种情况：

- `direction`：保存测点与示向，更新频道区域；不把中心线交点当源坐标。
- `near`：已有真实信号且距源≤5米，立即单独调用 clear；near 本身不是清除成功。
- `no_signal`：基础层不删除频道、不把位置或接收圆直接排除；Q4成对/历史模块只有满足额外几何前提才推导区域约束。

`geometry.py:74–82` 从1800米源圆的64边外包开始，逐次交示向角锥与以成功检测点为中心、1500米接收圆的切线外包。角半宽为1.01°，保守包含±1°及两位小数返回的舍入余量。它不利用 `direction` 排除5米近场，也没有精确恢复真实接收圆弧或朝向集合，故是**物理可行集的保守外包 P**，不是完整精确后验。

只要真源一直在 P 内，`minimum_circle(P)` 最后重算所有顶点到圆心距离的最大值（`geometry.py:131`），返回的半径即使因数值问题未达最小，仍用于包住当前 P。凸性保证顶点全包即整个多边形全包。因此 `R≤20−10⁻⁵` 是安全清除的充分证书。`R>20` 仅表示这份外包尚不能保证，不证明真实物理可行集绝不可能一次清除。

这与我方 [PLAN.md:334](/Users/flower/math/2026/B题/models/q1q2/PLAN.md:334) 的 `E20(K)=∩ D(g,20)`、`E20≠∅⇔R(K)≤20` 一致；没有落入 `D≤40⇒可清除` 的陷阱。直径40米等边三角形的最小圆半径约23.094米，仍不能保证清除。

### 清除落点、试探与兜底

[clearance_policy.py:8](/Users/flower/math/2026/NTJ_B_wt/B/clearance_policy.py:8) 枚举当前位置、单圆径向投影、两圆交点及 MEC 中心，再检查它们距所有顶点均不超过 `20−10⁻⁶`。这是把当前位置投影到顶点20米圆盘交的有限候选解法。内部用略缩的半径，因此准确说是“带安全余量的保证落点”，不应把浮点结果写成对原20米域的形式化精确投影。200组独立小检查中均满足全顶点清除距离，且移动不长于去MEC中心。

非保证光学试探是合法操作，失败成本3秒；成功才再计2秒清除。**尝试超出20米不等于误清，失败后仍标清除才是误清。** `Policy.clear` 只在实际响应 `clear_result="success"` 时加入 `cleared`（`policies.py:41–46`）；`Client` 先检查 HTTP 和 accepted，失败请求不会悄悄当成功。clear 不改测向机频道（`client.py:64–72`），符合附件2 §8。

`policies.py:68–80` 的兜底先试圆心，失败后将当前 P 在首次示向坐标系的外包矩形划成边长不超过28米的格子，访问格心，蛇形走完。`geometry.py:190–203` 给出每格覆盖半径≤`28/√2≈19.799`米，因此其中至少一次能清除真源，且不受Q4方向限制。主动定位不理想会变慢，但不会仅因定位尚粗而把源丢掉。本次另外强制走了两个单源完成兜底，分别第47、36个网格 clear 成功。

### 会不会漏清或无限推迟

对Q3主力，每个循环要么消耗一个剩余站，要么原子完成一个已知源；源最多16个。对分包方案，未完成的一包消耗不可重置的测向轮数，耗尽后强制光学完成。即使任务排序很差，也没有无限生成新站/新源或无限重置源预算的通路。暂停上限主要约束额外绕行，不是唯一有限结束依据。

已发现16个不同频道时可以丢弃剩余发现站，但还必须清完16源，见 `efficient_joint_policy.py:15–18` 与 `joint_task_policy.py:79–105`。否则只有“未知频道完整保证扫描 + 已知源全部清除”才能退出。`surveyed` 中可能包含推断免测记录，所以不能孤立地把其数量解释成实测数；退出证据依赖**未知频道未被这些区域规则跳过**。频道一经发现不会重新变成未知，这个归纳成立。

数值实现仍有边界：`policies.py:32–38` 在空裁剪时保留旧区域并计数，首次即空则报错；保证清除失败或光学覆盖耗尽也报错。它们不会谎报全清，但没有自动高精度修复。故“任意题设场景全清”的数学结论要附带正确反馈和数值包含前提，不是任意浮点病态、断网或现实预算不足时也能完成的无条件工程承诺。

## 各保证是否成立

| 保证文档 | 审计判定与关键限制 |
|---|---|
| **COUPLED_DISPATCH_GUARANTEE** | **距离跳过和有限结束论证成立，条件是 P 真包含源。** `‖q−c‖>1500+R+10⁻⁵` 蕴含所有可行源到 q 都超过最大接收半径；只用于已知未清源。代码 `coupled_dispatch_policy.py:68–80` 不修改客户端真实状态。原 range 版会改变频道/尝试记忆与任务轨迹，文档正确地没有承诺整局时间支配。 |
| **FAITHFUL_SKIP_GUARANTEE** | **在指定对照族内，保序删除和虚拟费用不增成立。** `faithful_skip_policy.py:25–41` 只删原地必无信号 RF，同时补 `_attempted`、负反馈冷却和 `_planned_channel`；扫描顺序读计划频道（43–59），实际频道仍由真实RF决定。删除 n 条 RF 省5n秒；频道切换的离散距离满足三角不等式，子序列切换数不增。不能外推到读时钟、按请求ID生成随机性或使用其他负反馈裁剪的策略，也不支配 `range_area7`。 |
| **DEFERRED_SCAN_GUARANTEE** | **在该实现内成立，没有发现漏源通路。** 20频道、最多16源，所以每站开始至少4个未知频道；该类不能删它们。扫描阶段没有共享/重新调度，必有保留RF携带到本站的移动，故可把“第一条必无信号RF的移动”延后。`deferred_skip_policy.py:82–100` 计数并断言，状态在保留动作与段末重新对齐。此保证不是“删除任何无信号点都不改变移动”。 |
| **HISTORICAL_PAIR_GUARANTEE** | **几何排除定理及保守外包实现成立。** 若 a、b 均不比成功点 s 离候选 g 更远，且 `[s,g]` 与 `[a,b]` 相交，任何包含 s 的接收闭半平面至少包含 a、b之一；其距离又在真实半径内，与双负反馈矛盾。`historical_pair_policy.py:11–34` 的三条交叉约束加两条距离约束符号吻合；37–56 保留补半平面并的凸包并外移余量。只可能损失排除强度，不能把区域中心满足条件误当整个区域可删。 |
| **BATCHED_HISTORY_EQUIVALENCE** | **精确算术逻辑成立，题设尺度上的数值等价有测试支持，不是任意尺度形式化证明。** `batched_history_policy.py:8–42` 每次有效裁剪后重新筛选整个后缀，保留原裁剪顺序；不会把后来生成的新顶点激活的约束永远遗漏。本次200序列、1258次有效裁剪与逐个原调用逐数组一致。 |
| **CHEAP_PREDICTION_GUARD** | **安全性成立；完全相同动作要另验。** 廉价预筛只拒绝，最终接受仍调用原全区域严格证书（`cheap_prediction_policy.py:8–27`）。即使预筛保守过头也只少删一条RF，不会产生虚假的无信号。它与未预筛版的普遍逐位等价没有形式化认证，文档也保留了此限制。 |
| **SERVICE_AWARE_GUARANTEE** | **安全与有限结束继承关系基本成立，费用排序不是实际费用保证。** 已精确频道罚项为0，范围外站罚项为0，其余 `25λ` 米对应5秒RF乘5米/秒（`service_aware_policy.py:114–132`）。反转增量计入内部有向弧和被倒置的任务对。文档第13行的零权重等价表述缺少 `mode="free"` 条件，有下节反例；不影响清除安全。 |

双负点预测与历史裁剪需区分：历史模块以**实际成功点**为锚，缩小 P；deferred 预测反设拟测 q 成功，用 a、b 推出整个 P 都矛盾，才删除 q 的RF，不裁剪 P。`pair_nonreception_certificate` 对每个顶点检查五条单位法向约束，并要求严格 `10⁻⁴` 米内缩。`logical_negatives` 可以包含已证跳过点，但其可信性通过前一步证书归纳建立；不是把没有发出的请求当成官方返回。

**较新 public-count 变体不能照搬“每站至少4个真实未知RF”。** 本次也读了 `public_count_scan_policy.py:14–45` 和 PUBLIC_COUNT_SCAN_GUARANTEE：确已发现16源且已到本站后，允许删剩余空频道。它另用“真实检测或已到站的16源空频道证书”计数，主动替换旧断言；未看到因这个扩展漏源的逻辑。它不属于上面63次小运行的覆盖对象，不能把本次实验当成对它的新增运行验证。

共同的 **335136秒 / 9766指令** 是限定站数、站点半径、主要RF、共享与打断预算的宽松计数界，不是策略构造器对任意用户参数都保证的API合同。WIDE_PROBE_GUARANTEE 把旧266976秒加最多24次打断的 `2×7100/5` 秒，得到335136秒，已计最后光学兜底前2500米段；本次未发现这段继承论证的直接反例。但本审计没有重建全部最坏动作轨迹的独立形式化证书，也没有证明1200秒现实期限内一定完成。`client.py:49–68` 会在现实预算用尽时中断，虚拟时钟证明不能替代官方执行可靠性。

本次独立小验证的脚本为 [verify-localize-clear.py](./verify-localize-clear.py)，结果为 [verify-localize-clear.json](./verify-localize-clear.json)：

- 2000次带±1°端点与两位舍入的区域更新：检查真源包含、包围圆及光学网格覆盖。
- 200组保证清除位置、1321个独立线段/距离排除见证、300组全区域双负点证书。
- 200组批处理序列、150组有向路线与次序代价增量对照。
- **63次完整本地协议运行全部清除，0区域不一致**：Q3四方法、Q4五方法，各六个普通种子加一个16源、最小接收半径、近圆周场景；Q4后者有15个朝外定向源及1个全向源。合计14个场景，不是63个独立场景，也不是官方成绩。
- **35组删除对照**：实际请求为基线仅删除 no_signal RF 的子序列，保留反馈相同，非零移动段相同，时间差等于 `5×删除数 + 切频减少数`。原 range 版单独运行，不强行要求它满足 faithful 的等价。
- 另2次强制单源光学兜底，均成功；不计入63次完整全源运行。

这些是审计小验证，补充而不替代证明；没有重跑或认证同学累计数万次历史实验。JSON保存所审主要 live 文件SHA256，重现命令：

```sh
/Users/flower/math/2026/B题/models/q1q2/.venv/bin/python -B /Users/flower/math/2026/B题/models/q1q2/peer-audit/q34/verify-localize-clear.py
```

## 真bug

### 1. 保证表述缺条件：零权重并非所有模式都等价于 fast_arc_route

定位：[SERVICE_AWARE_GUARANTEE.md:13](/Users/flower/math/2026/NTJ_B_wt/B/SERVICE_AWARE_GUARANTEE.md:13)；实现 [service_aware_policy.py:64](/Users/flower/math/2026/NTJ_B_wt/B/service_aware_policy.py:64) 只在 `mode=="free" and not np.any(precedence)` 时直接复用。`locked` 走69–70行的定向插入，87–88行还禁止反转多个扫描站。

最小反例：当前位置 `(0,0)`，任务0、1为按此顺序的扫描站 `(10,0)`、`(1,0)`，任务2为源代理 `(2,0)`，入口=出口，所有权重均0。

| 调用 | 输出任务序列 | 代理移动长度 |
|---|---|---:|
| `fast_arc_route` / `service_route(mode="free")` | `[1,2,0]` | 10米 |
| `service_route(mode="locked")` | `[2,0,1]` | 19米 |

这不是 locked 排序实现错误：锁住站序本来就增加约束。错误在于把“零权重控制等价”写成未限定模式的保证；我方复用时必须限定为 free，locked 应匹配同站序约束的对照。该差异已有本次实际函数调用与JSON记录。没有因此发现源定位、清除或有限结束错误。

### 2. 已承认的历史费用模型错误：对免测频道再次奖励“省测量费”

定位：[discovery_priority_policy.py:79](/Users/flower/math/2026/NTJ_B_wt/B/discovery_priority_policy.py:79) 在源 `R≤20−10⁻⁵` 时加 `clear_weight×6×len(unused)` 奖励；但 [joint_task_policy.py:96](/Users/flower/math/2026/NTJ_B_wt/B/joint_task_policy.py:96) 和 `interleaved_policy.py:186–188` 对这些未清精确频道本来就不再做RF。

例如已有精确源、还剩5站、`clear_weight=1`，模型为提前清源奖励30秒“未来RF节省”；真实扫描无论先清后清，该频道后续RF都是0次，节省应为0。把它解释成真实边际费用就是重复记账，会不当地改变任务优先级。任意启发式当然可以人为偏好早点清源，但不能把该奖励叫作已证明的费用收益。

[REPORT_TASK_UPDATE.md:11](/Users/flower/math/2026/NTJ_B_wt/B/REPORT_TASK_UPDATE.md:11) 已承认这项错误解释并排除相关候选。当前 `range_area7` 不走这个分支，新的 service-aware 在 `R≤20` 时也明确将罚项置0。因此这是**仍保留在live研究文件中的历史负例**，不是本次新发现的当前主力漏洞。

### 3. 本次没有坐实的错误，不冒充真bug

- 未复现当前 `range_area7` 或指定 faithful/deferred 家族在合法静态反馈下漏清、误清、无限拖延。
- 不能把有限候选、协方差、面积先验“不等于全局最优”算作代码错误：相关文件已明确它们只用于排名。真实效率回退则应保留为负结果。
- REPORT 顶部已有 Q1 LP 空集/无界/维数误判，涉及 `geometry.py:144–187`；当前 Q3 用 `update_region` 的有界外包裁剪，并不调用这条 LP 分类流水线。不能直接由Q1失败推断Q3本次漏包或漏清；同样也不能因此宣称Q3已获任意病态浮点的认证。
- 不将本次未重算全部粗界、未跑官方服务等覆盖范围限制伪装成已证明的算法失败。

## 可复用点

**最值得我方复用的是安全骨架，而非整套候选名称和历史默认值。**

1. **把发现状态、定位证书、清除状态分开。** 每频道保留观测与包含性区域；只有实际 clear 成功才标清除；near 单独执行clear。我方Q1/Q2已有外包与清除三态，可以直接对接这种任务状态，但我方尚未开发Q3/Q4。
2. **先实现有限保证，再优化排序。** Q3连续覆盖 + 每源有限主动预算 + 光学矩形覆盖 + 两种合法退出证据，可以独立于启发式形成基础方案。别把“已清已知源”当未知总数结束证书。
3. **复用 E20 最近保证落点。** 它把我方 PLAN §3.7/§7.9 的定义变为小规模可执行算法，常能比机械地走到MEC中心省路。应继续对所有顶点复查，并保留安全余量和中心后备。
4. **先用简单距离证书免测，若要费用不增定理则用独立计划状态。** faithful/deferred 的 `_planned_channel` 与实际 Client 状态分离有价值；不能仅删除请求而省略尝试记忆、冷却、站内原子性、至少一个保留移动载体等前提。后续我方若用时钟或负反馈改变决策，必须重写等价证明。
5. **历史双负点是有条件的几何信息。** 可复用五半平面及保守补集外包；Q3全向场景还有机会用更直接的距离排除，但不要未经证明放宽到任意Q4负反馈。普通收益、CPU成本与尾部应重新评估。
6. **有向任务路由及其独立验算。** 源入口/出口可以不同；反转路线要算内部反向弧，加入前后次序费用后还要算所有倒置任务对。先以完整枚举目标核对增量，再做前缀和加速。不要把代理路线下降称为真实剩余时间上界下降。

**是否复用了 Q1/Q2：是，复用了同学自己既有的几何原语与早期选点工具；没有复用我方现有Q1/Q2工程，也没有在线完整调用我方 PLAN 的Q2最坏不可区分点对优化。**

具体是：Q3 `Policy.measure` 调 `geometry.update_region/bearing_clip`，Q1 `solve_bearings` 也用 `bearing_planes`，二者共享角锥符号、凸几何和 `minimum_circle`，但Q3额外使用物理圆域外包，绕开Q1纯角锥的无界分类。早期 `intelligent.choose_second` 及当前 `completion_choice` 共用候选生成和 `guaranteed_omni`。

`guaranteed_omni`（`intelligent.py:80–85`）只接受“整个P在q的1000米圆内”或“q对所有P点均不比成功锚点更远”这两个充分条件；它比我方完整 `∀g:‖q−g‖≤max(1000,‖s−g‖)` 保守。`safe_sensing_policy.py:32` 才调用 `signal_minimax.reception_certificate` 的混合分区充分检验；`posterior_radius_upper` 给候选点连续示向分箱的包围半径上界，再加移动成本排名。它不是我方Q2的完整曲边候选域、不可区分点对最坏直径J及全域点优化，也不是当前Q3默认。

因此，我方可以把现有Q1/Q2的可靠外包、保收判定、证据状态接入这套调度骨架，再独立比较实际总时间；不宜为了照搬同学而退回有限假设均值、混淆Q1纯角锥与Q3物理区域，或把研究版 service-aware/历史负反馈直接设成最终默认。
