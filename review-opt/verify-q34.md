# Q3/Q4 改动独立复验报告

审计日期：2026-09-12。结论：**本次复验通过，未发现 P1 真源裁剪反例；Q4 未发现行为差异。Q3 独立样本收益为 0.34121%，不是原报告的 0.26%。** 该结论限于下述代码审查和本地实验，不是全浮点输入的形式化证明，也不是官方成绩。

本报告由独立审计者重新提取基线、编写测试驱动、运行并比较结果；未使用实施者的结果代替验证。所有 Python 命令均使用 `/Users/flower/math/2026/B题/mock/.venv/bin/python`。未访问官方模拟器，未运行 practice 或正式测试，未修改被审生产代码。

## 版本与隔离

改前从 Git **HEAD `aa018b70a9b63a3f97eb23bb79322ae38fea056c`** 逐文件执行 `git show HEAD:B/<文件>` 提取；改后从当前工作区复制到独立证据目录。保存了顶层 Python 模块和布局 JSON，不采用实施者的 before-code。两套文件中已有模块的内容差异仅为 `bounded_candidates.py`、`policies.py`，改后另有新增模块，包括 `omni_negative_policy.py`。运行后重新检查改后文件哈希，工作区与快照无漂移。

版本文件及 SHA256：[source-hashes.json](verify-q34-evidence/source-hashes.json)。测试与轨迹均保存在 [verify-q34-evidence](verify-q34-evidence/)。

## 回归与 mock-http

亲自执行 `python -B -m pytest tests -q`：**157 passed，238 subtests passed，10.90s**。没有跳过失败测试。见 [pytest.log](verify-q34-evidence/pytest.log)。

另在两个版本分别以 `--mode mock-http --seed 734121` 运行两个主候选；四次命令均退出 0，均自行绑定随机 loopback 端口：

|候选|改前全清|改后全清|改前虚拟秒|改后虚拟秒|两版本请求数|
|---|---:|---:|---:|---:|---:|
|Q3 range_area7|16/16|16/16|2871.315070|2871.315070|112|
|Q4 range_grid21_29|16/16|16/16|5812.732786|5812.732786|213|

四次 summary 均 `official_calls=0`、`all_cleared=true`。原始日志在 `before/robot_runs/`、`after/robot_runs/`，运行输出在 `before-http-q3.log` 等四份日志。这一 HTTP 场景的 Q3 没有提速，不能据此替代下述配对收益统计。

## Q4 逐字段不变性

对 HTTP seed 734121 的 `summary.json` 递归比较全部非实际耗时字段，包括嵌套 policy 统计；仅排除 `wall_s`、`cpu_s`、`initialization_s`、`program_wall_s`，**保留全部虚拟时间字段**。差异为零。

分别对客户端完整 `requests.jsonl` 和服务端完整 `mock_http_requests.jsonl` 的每条请求、响应和全部字段递归比较；只将 `request_id`、`real_timestamp_ms` 的值规范化，不删除记录或动作字段。两份完整轨迹均无差异。两版本规范化 SHA256 均为：

`bd6a441899e9ba00d06a92bd413c01e9ddb452180f1353dd69530d42ce3d3d46`

`policy.json`、`scoring_only.json` 亦逐字段相等。没有隐藏机器人位置、频道、反馈、清除结果、虚拟时间或计分字段的差异。

观察到的原始自然元数据差异也明确列出：213 条请求的 request_id 不同，7 条响应的真实时间戳不同；实际耗时如下（单位秒）：

|字段|改前|改后|
|---|---:|---:|
|wall_s|0.3090375420|0.3086775410|
|cpu_s|0.241953|0.241703|
|initialization_s|0.0000861670|0.0000807920|
|program_wall_s|0.4996137920|0.4981587500|

另外，独立种子区间的 **200 对 Q4** 均保存并解压完整轨迹逐字段比较，差异为零；每局结果 JSON 的全部字段亦相等，包括虚拟秒、策略统计、区域更新计数和最小包含余量。详见 [comparison.json](verify-q34-evidence/comparison.json) 和 [compare.py](verify-q34-evidence/compare.py)。

## 安全性：独立对抗测试与逐次区域检查

代码核查：固定半径 ρ 的全向源 g，真实成功锚点 a 与真实阴性点 q 满足 `‖g−q‖ > ρ ≥ ‖g−a‖`，因而 `(q−a)·g < (q−a)·(a+q)/2`。实现保留该闭半平面，额外向外放宽 `1e-4/(2‖q−a‖)` 米和 clip 容差；距离不超过 `1e-7` 米时跳过。该推导不受示向误差正负影响，但区域本身还必须正确包含示向误差。

反馈钩子只处理 `accepted is True` 的真实 `no_signal/direction`，排除已清频道；阴性先到与成功先到均能形成配对。Q4 仍调用默认空钩子，未启用距离支配。空/非有限交集保留旧区域的做法只能避免一次破坏，不能独立证明任意非空交集安全，因此额外直接检验了区域包含性。

自行编写 [adversarial.py](verify-q34-evidence/adversarial.py)，未调用新增测试或 fixture 的用例函数：

- **216 个支配闭边界测试**：72 个旋转方向，真源恰在等距平分线上，分别从多边形、线段、单点 regions 开始，经真实生产 `record_feedback` 更新，逐步断言仍包含真源。
- **21 个重合/近重合及退化测试**：锚点间距取 0、1e-12、1e-8、1e-7、1.0001e-7、1e-6、1e-3 米，覆盖跳过阈值两侧，分别测试点、线段、多边形。
- **54 个合法协议场景**：3 个真源位置、3 个轴向、恒 +1°/恒 −1°/空间 ±1° 场、阴性先到/成功先到两种顺序。半径固定 1000 米，测点取 1000、1000±1e-9、1000+1e-5、999 米并施加 1e-8 米横向扰动，构造近共线、近重合和接收边界。通过独立 `mock.protocol` 产生真实回复，再经 `Policy.measure` 的实际区域更新与反馈钩子处理；每步检查 regions[1]。对浮点距离确为 1000 米的测点另断言实际回复为 direction。

严格等距边界或完全重合点，不可能在固定半径全向模型下同时产生成功和阴性。因此前两类明确属于代数闭包/数值压力测试，不冒充合法物理反馈；第三类才是合法反馈路径。

结果：**291 场景全部通过，580 次区域赋值；合法协议组实际发生 54 次距离支配裁剪。** 独立包含判据对非退化凸多边形使用有向边距离，对线段/点使用到线段/点的距离；容差为 1e-7 米。最小余量为 `−5.0243e-15` 米，属于退化边界浮点舍入，远低于容差，未构成可分辨的真源排除。见 [adversarial-results.json](verify-q34-evidence/adversarial-results.json)。

在下面全部 800 次完整运行中，还替换 regions 字典记录器，**每次赋值立即计算真源包含余量**，记录反例位置、多边形及步骤；真源只供审计记录器使用，不传给策略。Q3 改前/后分别检查 7069/7319 次赋值，Q4 分别 8128/8128 次，共 **30644 次**，没有包含失败。Q3 最小余量 0.001190030 米，Q4 为 0.001346153 米。改后 Q3 距离支配实际裁剪 248 次、异常计数 0。

这些结果支持“本次合法测试中真源未被剪除”，不能扩展成对所有浮点输入的无条件保证。**没有发现需突出报告的 P1 反例。**

## 收益独立复现

选用未沿用实施者的种子 **734120–734319**，每题 200 对，两个版本共 800 次完整运行。自行编写 [audit.py](verify-q34-evidence/audit.py)，通过本地独立 `mock.protocol` 驱动主候选工厂，不复用实施者 reproduce.py。

索引 i 从 0 开始，源数 `[16,10,13][i%3]`；位置 `edge/clustered/uniform[(i//3)%3]`；误差循环恒 −1°、恒 +1°、空间 ±1°、smooth、iid；偶数局半径固定 1000 米，奇数局 uniform；Q3 全向，Q4 directional_fraction=0.5。逐对断言完整实际场景（含所有源参数）和误差配置一致。协议驱动固定真实时钟以排除机器负载差异，虚拟计时仍由模拟器逐动作累计；真实 HTTP 生命周期另由上述 mock-http 检验。

严格使用 **sum(整局虚拟秒)/sum(实际源数)**，不是逐局比值的平均，也不以成功清除数代替真实源数：

|题目|每版本局数|每版本真实源数|改前总虚拟秒|改后总虚拟秒|改前秒/源|改后秒/源|节省比例|
|---|---:|---:|---:|---:|---:|---:|---:|
|Q3|200|2600|635075.033829|632908.091058|244.259628396|243.426188868|**0.341210511%**|
|Q4|200|2600|1197032.777965|1197032.777965|460.397222294|460.397222294|0%|

Q3 节省 **2166.942771 秒合计，0.833439527 秒/源**。改前与改后均 **200/200 局全清、2600/2600 源清除、无运行异常**；Q4 两组也各 200/200 全清。收益没有以降低这批样本全清率换取。

Q3 36 局变快、10 局变慢、154 局虚拟时间相同。最差 seed 734201 变慢 96.752092 秒；最好 seed 734204 节省 278.282828 秒。因此不能宣称逐局占优。与实施者约 0.26% 的数值不完全相同，本独立样本为约 0.34%；不同样本的结果不应替换或拼接成同一实验。

原始逐局结果：[before.jsonl](verify-q34-evidence/before.jsonl)、[after.jsonl](verify-q34-evidence/after.jsonl)；800 份完整轨迹在 `before-traces/`、`after-traces/`，配对汇总见 comparison.json。

## 复跑命令

工作目录 `/Users/flower/math/2026/B题/B`。以下命令均仅使用本地 mock，证据脚本中的版本路径指向本报告保留的快照：

```sh
/Users/flower/math/2026/B题/mock/.venv/bin/python -B -m pytest tests -q
/Users/flower/math/2026/B题/mock/.venv/bin/python -B ../review-opt/verify-q34-evidence/audit.py before
/Users/flower/math/2026/B题/mock/.venv/bin/python -B ../review-opt/verify-q34-evidence/audit.py after
/Users/flower/math/2026/B题/mock/.venv/bin/python -B ../review-opt/verify-q34-evidence/adversarial.py
/Users/flower/math/2026/B题/mock/.venv/bin/python -B ../review-opt/verify-q34-evidence/http_runs.py
/Users/flower/math/2026/B题/mock/.venv/bin/python -B ../review-opt/verify-q34-evidence/compare.py
```
