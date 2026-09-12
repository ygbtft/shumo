# Q3 历史真实阴性距离支配：实施结果与论文补丁说明

本任务仅修改 B 的 Q3 主候选 `range_area7`，未修改 `models/paper-full.md`，未访问官方模拟器或触发正式测试。Q4 `range_grid21_29` 保留原类、参数、路径、反馈推理与动作规则。证据目录为 [q3-dominance](q3-dominance/)。

## 实施内容与安全理由

新增 `B/omni_negative_policy.py`，在 `bounded_candidates.build` 的 Q3 分支启用 `OmniNegativeCompletionPolicy`；历史 `CoupledCompletionPolicy` 不启用。`Policy.measure` 仅新增默认无操作的 `record_feedback` 钩子，位置在 Client 验证接受反馈、成功示向角更新之后，共享与后续决策之前。Q4 仍调用默认空钩子。

设静止全向源位置为 g，固定未知半径为 ρ，a 为真实成功示向位置，q 为真实无信号位置。则

\[
\|g-q\|>\rho\geq\|g-a\|,\qquad
(q-a)^Tg < (q-a)^T(a+q)/2.
\]

因此仅排除在成功锚点约束下必能接收的候选：若候选 g 到 q 不比到 a 远，a 已成功意味着 q 也必成功，与真实阴性矛盾。实现保留闭半平面并向外放宽，不估计 ρ，不使用真源位置，也不扣除任意无信号圆盘。

工程处理：

- 仅缓存 `accepted is True` 且结果为 `no_signal` 的真实位置；拒绝、通信异常、`certified_no_reception` 不计入。成功锚点采用真实 `direction` 位置；`near` 已直接清除，不再参与待清源推理。
- 支持阴性先于发现、成功先于阴性、多锚点；按精确坐标去重，每个新配对只处理一次。先前交集由后续区域更新保留。
- 使用单位法向量和中点形式，避免平方差相消；平方距离外放量 `1e-4 m²` 折算成 `1e-4/(2‖q-a‖) m`，再由 `clip` 向外放 `1e-8 m`。`‖q-a‖≤1e-7 m` 时跳过约束，保留区域。
- 点/线段退化仍保留；空或非有限交集保留旧区域并计异常。真正变更时立即失效 `_circles[ch]`。300 局新推理不一致计数为零。
- 精确算术下的安全性来自上述蕴含；浮点实现使用保守外放和退化处理。有限样本检查不冒充全浮点输入的形式化证明。Q4 可因背向而在更近位置收不到，不能使用此推导。

50 米试清门、3 次主动预算、未知频道完整覆盖、16 源上限逻辑及有限光学兜底均保留。新增 22 个测试实例，覆盖边界等距、近等距、点/线段、共点/近共点、1000 个合法随机约束逐次包含性、反馈顺序、重复、多锚点、拒绝/推断标签、空交集、缓存失效、共享前更新和 Q4 隔离。

## 配对复现结果

使用指定 `/Users/flower/math/2026/B题/mock/.venv/bin/python`，直接经过本地 `mock.protocol` 运行当前主候选工厂；不使用官方服务。改前代码在首次生产编辑前完整保存到 `before-code`，改后保存到 `after-code`，均附 SHA256。计时为模拟器逐动作计费的虚拟时间。

种子 **202610120—202610419**，300 个同种子配对场景，每组 **3900 源**。此为原报告 confirm 集的复现，不是新增独立于原报告的验证集。口径严格为 **sum(T)/sum(源数)**，不是逐局秒/源的简单平均。

场景索引 i 从 0 开始：源数 `[10,13,16][i%3]`；位置 `uniform/edge/clustered[(i//3)%3]`；误差循环 iid、smooth、±1° spatial、恒 +1°、恒 −1°；奇数 i 固定半径 1000 米，偶数 i 半径按生成器 uniform；Q3 全向，其余生成器默认参数。两个版本的每局完整场景配置和误差配置均保存并逐字段断言相同。

|指标|改前|改后|
|---|---:|---:|
|总虚拟时间/秒|955717.618721|953242.914185|
|源加权时间/秒每源|245.0557996721|244.4212600474|
|全清局数|300/300|300/300|
|清除源数|3900/3900|3900/3900|
|移动总距离/米|3582938.093547|3571144.570832|
|测量次数 M|36654|36633|
|切频次数 S|34401|34387|
|失败清除次数|653|654|
|区域赋值记录数|10578|10891|
|最小真源包含余量/米|0.000951081956|0.000951081956|

实际平均节省 **0.6345396246 秒/源，0.2589367913%**，复现了约 0.26% 量级；不要把原型的 0.6392 秒直接写作生产实现结果。改后 142 局发生裁剪，共 300 次实际区域变更；原型的 506 次切割及 24990 次赋值不能沿用。新实现去重、增量处理及反馈钩子时机不同，动作轨迹与原型不完全相同；没有分离实验可把微小差异归因于某一工程变化。

4000 次整局配对 bootstrap（随机种子 42，每次重算源加权差），改后减改前的描述性 95% 区间为 **[−1.236354700, −0.108076407] 秒/源**。27 局变慢（总时间差 > 1e-6 秒）；最差种子 202610289 为 **+390.201905 秒/局**，最好 202610317 为 **−562.807214 秒/局**。这只描述本地合成混合场；不保证每局提速，不代表官方收益或多候选筛选校正结论。

## 正确性与独立 HTTP 检查

- `B/tests`：**157 passed，238 subtests passed**。原 Q4 seed42 回归 fixture 未改；Q3 mock-http 新快照单列，原 fixture 仍保留。
- `models/q1q2/tests`：首次 **1172 passed**；共享工作区其他任务新增测试后最终复核 **1289 passed**。本任务没有修改 Q1/Q2 生产代码或测试。
- 四块 benchmark：**285/285、330/330、531/531、48/48**，均零失败。mock 虚拟环境缺少 mpmath，四块 benchmark 改用现成 Q1/Q2 虚拟环境运行；报告重定向至本证据目录，未改 benchmark 生产文件。
- Q4 mock-http seed42：改前后均 **10/10 全清、5847.482087 秒、293 条请求**。所有请求/响应动作字段、计分字段、策略统计逐字段相等，`policy.json` 也相等。仅排除 wall/CPU/初始化耗时、随机 request_id、真实时间戳这些每次运行自然变化的元数据；没有排除任何动作位置、频道、反馈或虚拟时间。请求流规范化 SHA256 为 `f23fce2d13194e2acabbea4c9759bef49d88c02d17d0ce9cfffcf4adb42284a2`。
- Q3 mock-http seed42：改前 **3304.341074 秒**，改后 **3396.191321 秒**，均 10/10 全清，实际变慢 **91.850247 秒**。这是另一个本地后端的不同场景，不能与同数值种子的独立 mock 场景混为一谈。
- 额外在独立 HTTP 运行中逐次记录区域：Q3 **31 次**、Q4 **34 次**，全部包含真源，最小余量分别 **0.244314917 米、0.223130798 米**；完整多边形保存在 `http-region-audit.json`。300 局配对试验的每次赋值均复制留存于单局内，结束后逐次检查，逐局记录数/最小余量保存在 JSONL。

## 论文具体补丁建议（父 agent 执行，本文未直接改论文）

1. 对“Q3 一般阴性不裁剪”的现有表述，替换为：

> Q3 中，尚无成功锚点的无信号反馈只作历史记录，不单独裁剪定位域。对已获得成功示向位置 a 的全向源，将其与该频道的历史真实无信号位置 q 配对，利用距离支配关系构造保守半平面交。仅当候选位置在成功锚点约束下必能于 q 接收时，才排除该候选。此更新不需要已知接收半径；定向的 Q4 不使用该约束。

2. 在该段之后新增上文距离不等式推导，并补一句：

> 实现保留闭半平面并外放浮点容差；共点及近共点约束跳过，空交集保留旧区域。真实阴性与几何推断的不可接收标签分开存储，收紧定位域后重新计算包含圆。

3. 对历史阴影模块的介绍，保留事实并明确：

> 一般历史阴影模块未接入主候选；本次仅在 Q3 主候选接入真实阴性与成功锚点形成的距离支配半平面，两者不应混称。

4. 实验表新增“Q3 历史阴性距离支配（本地配对消融）”行，使用本次 **245.0558→244.4213 秒/源，节省 0.6345 秒/源（0.2589%），两组各 300/300 全清、3900 源**。原报告原型 **244.4166、0.6392、506 次、24990 次**如出现于此实现的说明，分别改为 **244.4213、0.6345、300 次实际裁剪、10891 次改后区域赋值**。保留原型历史表时不要覆盖其原始数值，应明确“原型”与“本次工程实现”。

5. 结果解释建议：

> 收益主要来自移动距离缩短，失败清除次数由 653 次变为 654 次，并未减少。该混合场景上的源加权平均时间降低约 0.26%，但仍有 27 局变慢；独立本地 HTTP 场景 seed42 同样全清，却增加 91.8502 秒。因此只报告样本平均改善，不声称策略逐局占优或官方模拟器收益。

6. 验证段使用本次区域记录口径；不要把“全清”与“所有记录区域包含真源”混为同一项证据，也不要把有限样本检查写作全输入证明。Q4 的时间或策略结论无需因本项更新。

## 可复现命令

工作目录 `/Users/flower/math/2026/B题/B`。以下没有官方服务入口；HTTP 命令仅 `--mode mock-http`，自主启动本地随机端口服务。

```sh
Q34_CODE=/Users/flower/math/2026/B题/review-opt/q3-dominance/before-code /Users/flower/math/2026/B题/mock/.venv/bin/python -B ../review-opt/q3-dominance/reproduce.py confirm 300 ../review-opt/q3-dominance/before.jsonl base
Q34_CODE=/Users/flower/math/2026/B题/review-opt/q3-dominance/after-code /Users/flower/math/2026/B题/mock/.venv/bin/python -B ../review-opt/q3-dominance/reproduce.py confirm 300 ../review-opt/q3-dominance/after.jsonl improved
/Users/flower/math/2026/B题/mock/.venv/bin/python -B ../review-opt/q3-dominance/analyze.py
/Users/flower/math/2026/B题/mock/.venv/bin/python -B ../review-opt/q3-dominance/http_region_audit.py
/Users/flower/math/2026/B题/mock/.venv/bin/python -B -m pytest tests -q
/Users/flower/math/2026/B题/models/q1q2/.venv/bin/python -B ../review-opt/q3-dominance/run_benchmarks.py
```

Q1/Q2 测试从项目根运行：

```sh
cd /Users/flower/math/2026/B题
mock/.venv/bin/python -B -m pytest models/q1q2/tests -q
```

当前入口独立 HTTP 全清复核（从 B 目录）：

```sh
/Users/flower/math/2026/B题/mock/.venv/bin/python -B run_bounded_robot.py --problem 3 --method range_area7 --mode mock-http --seed 42
/Users/flower/math/2026/B题/mock/.venv/bin/python -B run_bounded_robot.py --problem 4 --method range_grid21_29 --mode mock-http --seed 42
```

`analyze.py` 同时检查两组 300 个种子/配置对应、全清、区域包含，并生成 `comparison.json`。Q4 原始改前/改后 summary、policy、完整 HTTP 请求日志已另存 `q4-before/`、`q4-after/`；比较排除项在 JSON 中明列。`source-sha256.json` 固定改前后代码及本地 mock 文件哈希。
