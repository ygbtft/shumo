# 统一的本地机器狗测试环境

> **最高优先级硬约束：所有官方模拟器行为只能用于“演练测试”。未经用户明确书面许可，绝不启动、操作或探测“正式测试”，绝不触碰相关按钮、接口或流程。代码不包含任何自动开启测试的功能。用户须在官方界面手动登录、选择演练测试并等待接口开放，再运行 HttpOfficial。若某项验证只能通过正式测试完成，必须停止并询问用户。**
>
> 四个公开机器狗接口不提供演练/正式模式查询。`session_mode: "practice"` 是操作者对已开启演练会话的声明，不能被描述为服务器模式认证。本工具不操作官方 GUI，不连接登录、测试创建或管理端点。`HttpOfficial` 只允许 `/enter`、`/measure`、`/clear`、`/exit`，并要求显式声明 `session_mode="practice"`。

这是独立实现的本地工具，依据题面、附件 1/2 及 `ENV-HANDOFF.md` 的接口事实。未使用官方二进制、服务器案例数据或任何逆向能力。**目前没有官方演练实测数据，官方契约零差异与经验先验均尚未获真机验证。**

## 目录与依赖

```text
mock/
  .venv/                         本机虚拟环境，不能复制到 Windows 使用
  geometry.py                    方位、距离、覆盖判定
  simulator.py                   状态、微秒计时、物理结果与期限
  protocol.py / server.py        严格 JSON、幂等、并发与 HTTP
  error_field.py                 iid / smooth / ±1 / empirical 固定误差场
  scenario_gen.py                可配置案例与经验先验抽样
  strategy.py                    Action、Observation、Strategy、Baseline
  client_or_inproc.py            公共运行器，兼容旧客户端名字
  backends/
    base.py / __init__.py         后端契约与配置工厂
    inproc.py / http.py           InProcMock、HttpMock、HttpOfficial
    recording.py                 逐次尝试 JSONL 录制
  run.py / replay.py / differ.py 单局运行、原动作回放、微秒级差分
  validate.py                   纯离线、跨平台后端链路自检
  calibration/
    observations.py              定位证据、不确定度、留出测量
    error_fit.py                 残差区间、边际分布、空间半变异函数
    prior_fit.py / __main__.py    半径约束、位置/数量/类型先验与导出
  evaluator.py                  强制压力矩阵、失败案例、分位数与最坏组合
  viz.py                        离线轨迹图；仅此模块需要 matplotlib
  bundle.py                     导出可直接复制到 guest 的源码 ZIP
  configs/                      后端、问题 3/4、困难分布、标定示例
  tests/                        规则、HTTP、后端、录制、差分、标定测试
  materials/                    题面与附件提取结果、原始公式 XML、读取依据
  results/                      实验报告、JSONL、失败案例、轨迹图
  requirements*.txt             核心、可视化、测试、材料读取的分离依赖
```

要求 Python 3.10+。HTTP、内存仿真、策略和录制只用标准库；批量统计与标定需要 NumPy。matplotlib 单独安装。所有文件文本使用 UTF-8，没有 macOS 专用调用，也不依赖 VM 工具、shell 脚本或桌面自动化。

下述 macOS/Linux 命令从 **B题目录（mock 的父目录）** 执行：

```bash
python3 -m venv mock/.venv
mock/.venv/bin/python -m pip install -r mock/requirements.txt
# 可选：画图 / 开发测试
mock/.venv/bin/python -m pip install -r mock/requirements-viz.txt
mock/.venv/bin/python -m pip install -r mock/requirements-dev.txt
```

## 启动本地 mock

```bash
mock/.venv/bin/python -m mock --seed 202600 --config mock/configs/q4.json
```

默认只监听 `127.0.0.1:2026`，`robot_id=mock-robot`。启动后 5 秒开放，随后 25 分钟窗口；`/enter` 后另计最多 20 分钟，以较早截止者为准。虚拟上限 360000 秒。每个动作立即计算，无现实 5 秒等待。允许域外位置，每分量上限 ±2000000 米。

第二个终端等倒计时结束后：

```bash
mock/.venv/bin/python -m mock.run --backend-config mock/configs/backend-http-mock.json --record mock/results/http-session.jsonl
```

本地快速调试可加 `--countdown 0`。服务一局结束后仍保留监听但直接关连接；新局需重启服务。Ctrl+C 导出带真值的服务器轨迹到 `mock/results/server-session.json`。`--scenario <case.json>` 可加载生成器、失败案例或样例的准确场景。

故障选项：`--closed`（始终不开放）、`--fail-first`（一次 500）、`--max-records`（默认 200000）、`--max-connections`（默认 64）、`--invalid-limit`（默认每秒 1000 个无效请求）、`--replay-after-end`（非默认的结束后历史重放假设）。所有 CLI 支持 `--help`。

## 三个后端，策略代码相同

配置只改变连接方式：

| kind | 实现 | 用途 |
|---|---|---|
| `inproc_mock` | `InProcMock` | 批量评测，经过同一 JSON/协议逻辑 |
| `http_mock` | `HttpMock` | 本地网络契约检查 |
| `http_official` | `HttpOfficial` | guest 内，用户已开启的官方演练 |

```bash
mock/.venv/bin/python -m mock.run --backend-config mock/configs/backend-inproc.json --record mock/results/inproc-session.jsonl
```

`Backend.exchange(path, payload)` 是一次物理尝试；`send(Action, request_id=None)` 分配 ID，并仅在连接类异常时按配置重试，复用原动作和原 ID。HTTP 错误与 `accepted=false` 不自动重试。录制层在重试循环内，因此每次尝试都被记下。

机器狗只实现 `next_action(observation) -> Action`；公共运行器负责 `/enter`、后端调用与 ID。观察包含上次动作/响应、机器狗位置、测向机当前频道、虚拟时刻、剩余现实时间、已清除频道和动作计数，**不包含源真值、源总数、误差模型或案例生成配置**。更换后端无需修改策略。

```python
# mock/my_strategy.py
from mock.strategy import Action

class MyStrategy:
    def __init__(self, seed=0):
        self.done = False

    def next_action(self, observation):
        if not self.done:
            self.done = True
            return Action('/measure', (0.0, 0.0), 1)
        return Action('/exit')
```

用 `--strategy mock.my_strategy:MyStrategy` 指定。baseline 是 600 米蛇形网格扫描、双点交会和局部复测；外圈延伸至 ±2400 米，用于接收朝外辐射的定向源。它是链路基准，不保证所有场景清完，也没有优化最后清除后的搜索开销。

## 蒙特卡洛与禁止假设过拟合

```bash
mock/.venv/bin/python -m mock.evaluator --runs 100 --workers 4 --seed 202600 --config mock/configs/q4.json --output mock/results/my-q4-matrix --plot
```

**`--runs` 是每个组合的局数。默认强制执行至少 15 个组合，总计 1500 局：**

- 位置：均匀面积 / 贴边 / 成簇。
- 误差：地点 iid 均匀 / 空间平滑 / 恒 +1° / 恒 -1° / 空间固定 ±1°。

同一位置配置下，各误差条件复用相同种子与源场景。不能通过 `--error-models` 缩减必测集合。标定后的经验分布是额外条件，通常扩展为 24 个组合。`--case` 是单例诊断，不作为完整压力矩阵报告。

问题 3 用 `q3.json`，问题 4 用 `q4.json`；`edge_outward.json` 与 `clustered.json` 提供朝外辐射、低半径、集中朝向等额外压力条件。它们也会运行全部必测位置 × 误差组合。

每个条件输出 `summary.json`、`rows.csv`、`rows.json`、`sample.json`、`worst.json`；每个未清完、运行错误或达到动作上限的案例写到 `failures/seed-*.json`。保存场景真值、误差配置、种子、策略名字、动作上限与接受动作轨迹。顶层 `summary.json` 给出最差平均清除比例的组合，以及平均时间最大的组合。比例相同时按更慢的平均时间排序。现有输出条件目录不能覆写，避免陈旧失败文件混入新实验。

两个主指标：

- 清除比例 = 清除数 / 总数。
- 平均定位清除时间 = **整局已接受动作的累计虚拟时间** / 清除数；包含移动、切频、检测、失败光学搜索及最后一次清除之后的搜索。

输出各局指标的均值、标准差、p0/p5/p25/p50/p75/p95/p100，并另给跨局汇总比例和汇总时间。清除数为 0 时平均时间为 `null`，单独计入 `zero_clear_runs`，不当作 0 秒参与均值。现实运行时间单独报告。

重放已知失败：

```bash
mock/.venv/bin/python -m mock.evaluator --case mock/results/clustered/adversarial-spatial/failures/seed-202632.json --output mock/results/my-replay --plot
mock/.venv/bin/python -m mock.viz mock/results/my-replay/replay.json --coverage --output mock/results/my-replay/coverage.png
```

默认重用保存的策略名和动作上限，允许显式替换策略作对照。重放复现物理结果与虚拟时间，现实时间戳和随机请求 ID 本身不要求一致。

## 官方演练录制：在 Windows guest 内运行

本工具**不会替用户开启任何官方测试**。另一环境任务负责 guest 的 Python 安装；这里只提供可移植代码。不能从宿主访问 guest 的回环地址。将代码复制/拉取到 guest 后，从包含 `mock` 的父目录运行 PowerShell：

```powershell
py -3 -m venv mock\.venv
mock\.venv\Scripts\python.exe -m pip install -r mock\requirements.txt
Copy-Item mock\configs\backend-official.example.json mock\configs\backend-official.local.json
```

编辑 `backend-official.local.json`，把 `robot_id` 改为当前登录参赛队号，保持 `session_mode` 为 `practice`。用户手动登录官方模拟器，**选择演练测试**，等界面明确显示接口已开放后：

```powershell
mock\.venv\Scripts\python.exe -m mock.run --backend-config mock\configs\backend-official.local.json --record mock\results\practice.jsonl --output mock\results\practice-run.json
```

别让本地 mock 同时占用该端口。后端配置不会识别端口上服务的身份，也无法判断官方界面选中了哪种测试；演练模式必须由用户在运行前确认。记录文件已存在时拒绝覆盖，每次演练使用新文件名。

无需携带本机虚拟环境、材料或实验数据。可生成便于复制的包：

```bash
mock/.venv/bin/python -m mock.bundle
```

产物 `mock/dist/mock-core.zip` 包含源码、测试、示例配置、README 和依赖声明，排除 `.venv`、结果、材料和 `*.local.json`。guest 上可先运行 `python -m mock.validate --output mock/results/guest-offline-check`；它只连接自己新建的随机端口 mock，不接触已有模拟器。

当前已在宿主验证核心链路和打包；**尚未在 Windows guest 实际运行**。

## JSONL 录制、原动作回放、差分

每行包括 `schema_version/run_id/backend/sequence`、`request_id/action/position/channel`、完整 `request`、`http_status`、完整 `response`、`transport_error`、记录时刻与现实耗时；并投影 `accepted/virtual_time_s/measure_result/svd_deg/clear_result/real_timestamp_ms`。响应和请求均保留原值。每笔 flush，记录层不额外发送请求；也不 fsync 每行，不承诺断电无损。后端名称是配置声明的来源标签。

将录制动作原样送给配置好的内存场景：

```bash
mock/.venv/bin/python -m mock.replay mock/results/inproc-session.jsonl --backend-config mock/configs/backend-inproc.json --record mock/results/replayed.jsonl
mock/.venv/bin/python -m mock.differ mock/results/inproc-session.jsonl mock/results/replayed.jsonl --scene-alignment known_mock_scene --output mock/results/diff.json
```

回放保留全部请求内容和 ID，记录中的重试也逐次回放；不自动新增重试或 `/exit`。对于官方录制，内存后端的 `robot_id` 必须配成相同参赛队号。要比较判定，还需在 `scenario_file` 提供经证据重建的场景，而不是任意随机场景。

**单份演练记录就能检查计时契约：**

```powershell
mock\.venv\Scripts\python.exe -m mock.differ mock\results\practice.jsonl --output mock\results\practice-timing-audit.json
```

差分比较 HTTP 状态、`accepted`、`virtual_time_s`、`measure_result`、`clear_result`、`exit_reason`。时间按十进制数转整数微秒，**无容差、1 微秒也报差异**。每条报告带动作序号、ID、期望/实际微秒、移动/切频/动作分项，以及可能的出错规则。重复 ID 会核对首次完整响应，包含其现实时间戳。

跨环境的现实时间戳不直接比较；示向度差值单列为统计量。`remaining_real_duration_s` 依赖实际入场时刻，不作为跨环境相等字段。连接关闭会单独报告；未解决的丢响应不会被当作已知未执行。

“确定性零差异”只描述所比较记录的覆盖范围。报告给出覆盖过的动作和结果类型。官方接口不透露完整源坐标、半径、朝向，因此任意 mock 场景与官方演练的 `measure/clear` 结果并不应强求相等。**先核对不依赖真值的计时契约，再在同场景重建证据充分时核对判定。**

## 从演练观测标定，而不是虚构真值

复制 `configs/calibration-manifest.example.json` 为本地配置，填写每个录制路径、问题编号、演练结束界面给出的 `total_sources`（可同时填 `directional_count`）。未获知的数量保留 `null`。

每个已定位源可提供：

```json
{
  "channel": 7,
  "x": 100.0,
  "y": 200.0,
  "uncertainty_m": 0.5,
  "kind": "unknown",
  "method": "independent"
}
```

这里的数值只是格式示例，**不得把示例或清除点当成真实坐标**。独立定位证据用 `method: "independent"`；从示向度求得的定位用 `method: "bearing_holdout"` 并列出 `support_request_ids`，这些测量不参与其自身残差标定。已知朝向时可增加 `direction_deg`、`direction_uncertainty_deg`。未知源类型保留 `unknown`。

`auto_localize: true` 会对成功清除的频道自动构造保守定位区域：采用一半方向观测的 ±1.005° 扇区，以及接收/near/成功清除的距离外包方形约束，另一半方向留作残差样本。输出包含该区域的中心和最大顶点距离，不能把它当作精确定位。若约束冲突会标记无效。

```bash
mock/.venv/bin/python -m mock.calibration mock/configs/calibration-manifest.local.json --output mock/results/calibrated
```

输出：

- `calibration.json`：每个源的定位证据、残差区间、样本排除原因、边际直方图/分位数、同场景同频道的距离分箱相关/半变异统计、接收半径约束、类型证据与经验先验。
- `empirical-config.json`：可直接交给 `scenario_gen` 或 `evaluator --config`。样本不足时保留默认假设，不捏造参数。

默认只接收定位导致的方位不确定度 ≤0.1° 的留出样本。残差区间额外包含 0.005° 的返回舍入误差；同地点重测去重。清除成功通常只有 20 米定位约束，近距离误差标定会因此被拒绝。20 个可用样本后才导出经验误差分布；相关长度估计是有样本量要求的描述性建议，不是已证实的场模型。

接收信号给半径下界；`no_signal` 只有在确定为全向，或已知位于定向覆盖内部时才给半径上界。源在清除前、确定距离小于 1000 米却无信号，可以作为定向证据。仅收到信号不能证明全向；问题 3 的题设可提供全向先验。已清除之后的无信号不用于推断半径。

只将已知总数且全部定位的案例导出为经验位置样本；局部定位的案例仍保留在报告中，不伪装成人口分布。半径通常仅能得到区间；在区间内抽样仍是假设。经验误差与位置、半径配置仍须通过完整压力矩阵。所有报告保留 `provenance`，合成验证数据不会被称作官方数据。

## 假设清单与协议边界

| 编号 | 附件未明确处与当前默认值 |
|---|---|
| A1 | 源数在 10..16 离散均匀、频道无放回均匀；位置默认面积均匀；半径默认 [1000,1500] 均匀；各采样默认独立，无最小源间距。贴边使用 r=1800·U^(1/8)，成簇为 3 个均匀中心、σ=180m 高斯簇，越界拒绝重采样。 |
| A1 | 默认定向概率 0.5、朝向均匀；0<p<1 时强制两类都有（全同类时随机翻转一个），p=0/1 允许纯类对照。半径允许 fixed/beta；朝向允许 fixed/inward/outward/vonmises。固定半径是敏感性对照，不声称每源半径必然相同。 |
| A2 | iid 指**不同地点**的独立伪随机场，同地点同频道固定；地点键为 float64 精确坐标（±0 合并），默认跨频道独立，可设 shared。smooth 为 16 个随机平面波经 tanh 压缩，默认尺度 200m；边际分布不是均匀。 |
| A3 | “对抗性”是静态 +1°、-1° 或地点固定的 ±1° 符号场，不是对策略在线求解的全局最坏攻击。 |
| A4 | 源点与检测点重合时视为覆盖，返回 near；覆盖角浮点边界容差 1e-10°。 |
| A5 | 每动作移动耗时四舍五入至最近微秒，半向上；再加整秒动作费。示向度半向上保留两位后归一化。潜在误差严格 [-1,1]°，显示舍入最多另引入 0.005°。待演练计时 oracle 校准微秒取整规则。 |
| A6 | 幂等按解析后的动作语义比较：键顺序/空白、1/1.0、±0 不算变更；ID 会话内全路径共享。默认结束关接口优先于缓存重放；可切换 replay_after_end 对照。附件对已退出后的重试与关闭接口有边界张力，不能宣称已知官方优先级。 |
| A7 | 幂等容量 200000；同时连接 64；无效请求每秒 1000 个触发 429，正常串行合法请求不限速。500 不计作客户端无效流量。HTTP 新动作保留占用至完整响应发送结束。 |
| A8 | 本地用命令启动准备倒计时，无官方登录或 GUI。一次服务对应一局，默认选择直接关连接这一允许行为。输入报文读取超时 5s；只支持 Content-Length，不实现 chunked/Expect 握手；重复 framing 头按错误拒绝。HEAD 按 HTTP 语义不发送实体正文。故障注入只服务本地测试。 |
| A9 | 总时间取整局已接受动作耗时，包括失败和清除后的搜索。清除 0 个时平均时间为 null，均值排除并单列数量。 |
| A10 | MC 省略准备倒计时；仍检查现实/虚拟限时。默认动作上限 10000 是评测保护，达到后发 /exit 并标记 failure，不是题目规则。任意第三方策略的永久阻塞代码不能由同进程超时强杀。 |
| A11 | 经验模型采用有限样本 bootstrap/分位数映射，半径在观测约束区间内均匀取样；平滑经验映射使用近似正态 CDF。源位置以完全定位案例的中心估计抽样，仍有定位误差、有限样本和策略选择偏差。 |
| A12 | 录制每笔 flush、不逐笔 fsync；回放按记录顺序立即执行，不重现原始网络延迟、倒计时或并发时序。此类现实生命周期差异会报告，不虚构与官方一致。 |

公开协议已实现的状态包括 200+accepted=true/false、400、404、405、409、413、415、429、500，以及无 JSON 的连接关闭。未知字段（含 position 子字段）、标识不匹配、结构错误不消耗 ID；拒绝请求不修改位置/频道/时间，返回虚拟时间 0。只有 accepted=true 的 measure 更新测向机频道，即使结果为 no_signal；clear 永远不切频。截止前完整到达并登记的动作允许完成，因此最后一条可跨过虚拟上限。

## 验证与已有实验

```bash
mock/.venv/bin/python -m pytest mock/tests -q -o cache_dir=mock/.pytest_cache
```

`materials/` 保存已完整读取的 4 页题面、两附件文本、15 张表格所在正文、28 个公式节点和原 XML；分数在公式提取中保留为 `(分子)/(分母)`。

实验汇总见 `results/VALIDATION.md`。HTTP 与内存同场景验证、失败重放、合成标定均有独立产物。有限样本清除率不是全清保证；已保留成簇/最短接收半径组合的真实 mock 失败案例，便于后续策略改进。
