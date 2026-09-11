**最重要发现：当前 Q4 主力的全清和总体均值可以复验，但逐局耗时对数值环境很敏感——同一份场景、参数和策略源码，本机复跑出现单局多 2391.47 秒；此外，最新主力尚未接入现有 HTTP 交付入口。不能把这些离线均值直接当成可移植的官方成绩。**

审计日期：2026-09-11。对象为同学工作区 `/Users/flower/math/2026/NTJ_B_wt/B`，下文相对源码路径均以此为根；“我方”指 `/Users/flower/math/2026/B题/models/q1q2`。已读 GOAL.md、REPORT.md、MODELING_TRAPS.md，并对照我方 PLAN.md、题面与附件2的本地提取文本。只读同学生产代码及实验材料；本次验证程序、结果均写在本审计目录，无网络请求、无官方调用、未运行会覆盖同学归档的实验入口。

## 协议客户端正确性

### 优先问题：已有可复现缺陷，不宜原样作为正式客户端

**P1：响应体截断没有进入幂等重试，会在动作可能已经执行后中止整局。** [client.py:27](/Users/flower/math/2026/NTJ_B_wt/B/client.py:27) 在 `response.read()` 后解析 JSON，但 [client.py:31](/Users/flower/math/2026/NTJ_B_wt/B/client.py:31) 只捕获 URLError、TimeoutError、ConnectionError、OSError。标准库 `http.client.IncompleteRead` 不在其中。注入“已收到 HTTP 200，读取 body 时抛 IncompleteRead”后，配置允许三次尝试，实际只尝试一次即抛异常；[run_robot.py:62](/Users/flower/math/2026/NTJ_B_wt/B/run_robot.py:62) 写 failure 后重新抛出，无法继续清除。附件2 §5.3 要求处理连接中断，且这种不确定执行状态应复用原始动作和 ID。这里不是重复计费错误，而是失败恢复覆盖不完整。损坏 JSON 的解析异常同样直接外抛，且未保存原始响应片段。

**P2：同一测试会话内重新建立 Client 会复用旧 ID，甚至把缓存的 /enter 当作重新入场。** [client.py:46](/Users/flower/math/2026/NTJ_B_wt/B/client.py:46)、[client.py:53](/Users/flower/math/2026/NTJ_B_wt/B/client.py:53) 每个对象都从 `b42-1` 开始。最小复现：客户端 A enter 后移动到 `(100,0)`、检测频道2，服务端为26秒；客户端 B 对同一 Protocol 调用 enter，获得第一次 enter 的缓存成功响应，但 B 自认为在原点、0秒，服务端仍在 `(100,0)`、26秒。后续可能重放旧动作或409冲突。**限定于同一会话重启/重建，不影响每个新测试从空幂等缓存开始的正常一次运行。** 我方应使用每次运行唯一前缀，并将“恢复既有会话”设计成单独的持久状态恢复流程，不能靠重新 enter 恢复。

**P2：现实预算只在新动作开始时检查，没有约束每次网络等待和重试。** [client.py:50](/Users/flower/math/2026/NTJ_B_wt/B/client.py:50) 只检查当前是否已经超时；[client.py:25](/Users/flower/math/2026/NTJ_B_wt/B/client.py:25) 随后仍可能做三次各5秒的网络尝试及退避。remaining 为1秒时也可能进入这一路径。它不会绕过服务端期限，但不能保证客户端在 remaining 内结束，也没有预留退出/落盘预算。应将绝对期限传入 transport，逐次限制剩余 timeout；服务端关闭后不要用 exit 查询原因。

复现结果见 [verification-overall.json](verification-overall.json)，程序见 [verify_overall.py](verify_overall.py)。普通 ConnectionResetError 的对照也验证了：重试两次发送完全相同字节，服务端只执行一次；不能把上面的截断缺口扩大成“所有幂等重试都错”。

### 正常路径核对

| 附件2要求 | 当前实现与判断 |
|---|---|
| 精确 POST `/enter`、`/measure`、`/clear`、`/exit`；UTF-8 JSON | Client 四个公开方法正确；HttpTransport 使用 application/json、POST，不加查询字段。默认地址为127.0.0.1:2026；允许其他本机端口符合附件。见 client.py:17、24、75。 |
| arena_id、robot_id、request_id、position、channel | 正常策略发出的字段正确，arena固定default，practice需要显式队号。坐标检查finite及±2000000。客户端会用 `int(channel)` 静默截断调用者传入的1.5，而非本地拒绝，属于可复用接口的输入合同缺口；现有策略使用整数频道，未据此判定现有实验错误。 |
| 同时检查HTTP状态与accepted | client.py:64正确：非200或accepted不为True即停止；拒绝响应中的virtual_time_s=0不会覆盖上次有效状态。400/404/405/409/413/415/429/500统一作为拒绝处理，保守但缺少分类诊断。没有擅自将HTTP错误当no_signal。 |
| 串行新动作、重试同ID同内容 | 当前同步策略逐次等待；HttpTransport在重试循环外构造Request，重用同一body。Client自身没有锁，不能据类名宣称多线程调用也安全；当前运行器无此并发使用。 |
| 移动、切频与计时 | Client以成功响应为虚拟时钟真值；只有成功measure更新测向频道，clear只更新位置，不切测向频道。见client.py:66。策略没有为虚拟5秒现实sleep；0.05/0.10秒仅为网络退避。 |
| /enter返回的实际remaining | client.py:68用调用前monotonic加remaining，考虑了往返耗时，偏保守；不是硬编码1200秒。上述逐次网络期限约束仍缺失。 |
| direction/near/no_signal，success/no_target_in_range | policies.py:23正确分支，near后单独clear，只有direction读svd_deg。光学失败不伪装成功。 |
| 请求/响应记录 | run_robot.py:50每个完整响应落一行并关闭文件；HTTP业务拒绝会入日志。纯网络异常没有请求尝试级记录，主要只有failure.txt，难以调查“已发出但响应丢失”。本地JSONL不是官方加密日志。 |

`--confirm-practice` 只是操作者声明；附件没有查询演练/正式模式的接口，程序不能鉴别服务端当前模式。代码对此已诚实注明，不是额外的安全认证。[run_robot.py:22](/Users/flower/math/2026/NTJ_B_wt/B/run_robot.py:22)、[package_robot.py:19](/Users/flower/math/2026/NTJ_B_wt/B/package_robot.py:19)。

## 实验/结果可信度

### 先分清三个来源

1. **根目录 simulator.py 是同学自建 mock。** 文件 [simulator.py:1](/Users/flower/math/2026/NTJ_B_wt/B/simulator.py:1) 明确写明非官方实现，不模拟登录、GUI/网络生命周期、加密日志和限流。World实现物理与评分，Protocol实现内存JSON分发。旧 `run_experiments.py` 直接调用 `Protocol(world).dispatch`，没有TCP；`run_robot.py --mode offline`也是这套。见 [run_experiments.py:154](/Users/flower/math/2026/NTJ_B_wt/B/run_experiments.py:154)。
2. **9月11日最新系列主要跑另一套参考 mock，而不是根目录 simulator.py。** [peer_benchmark.py:14](/Users/flower/math/2026/NTJ_B_wt/B/peer_benchmark.py:14) 从 `reference/shumo-b/mock` 导入生成器、误差场、Simulator及Protocol；PeerTransport直接 `Protocol.handle("POST",...)`。最新确认由 [icra_confirmation.py:128](/Users/flower/math/2026/NTJ_B_wt/B/icra_confirmation.py:128) 建这个后端。这是跨实现基准，有助发现同学自建物理错误，但依然非官方。不能因为变量叫peer、Protocol或HTTP就称其为官方运行。
3. **reference中另有历史官方演练录制。** [reference/shumo-b/practice-logs/REPORT.md:3](/Users/flower/math/2026/NTJ_B_wt/B/reference/shumo-b/practice-logs/REPORT.md:3) 自述Q4演练1367请求，发现15频道、清除10源，虚拟30115.333001秒，用于延迟/规则验证。这不是最新主力成绩，也不是59514次全清的来源。本审计不独立认证官方来源；其引用的GUI截图缺失问题已由同学REPORT历史段说明。

最新 `http_checks.json` 的 `owned_loopback_http` 表示自建本地HTTP服务与内存执行的对照，里面也标了official_calls=0；不能因文件名有HTTP就当成官方演练。GOAL写“不注册、不使用报名身份、不消耗正式机会”与所查最新运行链一致。**能确认这些实验入口不会发官方请求；无法仅靠仓库证明当事人所有外部活动均为0。** 本次审计自身网络请求为0。

### 真值独立性：策略隔离较好，统计并非外部盲测

最新配置和代码先冻结，再生成新场景：[icra_confirmation.py:120](/Users/flower/math/2026/NTJ_B_wt/B/icra_confirmation.py:120)；[cover21_confirmation.py:96](/Users/flower/math/2026/NTJ_B_wt/B/cover21_confirmation.py:96)还核对训练策略哈希。参数选取依赖训练结果是正常流程，不能称完全无先验调参；确认集之后已被分析，不能下一轮继续称未见数据。

源位置、方向、半径、总数存在runner和后端中。策略构造只传Client、问题类型、公开参数、站点；评分在执行后读取sim.cleared与scenario.sources，见 icra_confirmation.py:129、135。未发现主力policy直接读取隐藏源数或位置。`source_count_scoring_only`、`scenarios_scoring_only`不是偷看证据；它们有明确评分用途。但同一Python进程并非安全沙箱，Client私有属性也不是访问控制。

真值生成器不是策略自己给出的估计，所以没有“拿自己的估计当真源验证”的循环。然而测量与评分共享同一个模拟器，生成分布又由研究者指定，故它是**独立于策略估计的合成真值**，不是官方真值或第三方盲测。参考后端分离和本次独立轨迹重算增强物理可信度，不证明官方误差分布一致。

最新普通集为3种位置分布×5种误差场×10种子，共150案例/问题；压力集45案例，含边界朝外/切向、近共线、聚簇远端频道20、接收半径转换，源数10/13/16及端点误差。见 [cover21_confirmation.py:53](/Users/flower/math/2026/NTJ_B_wt/B/cover21_confirmation.py:53)。普通Q4约50%定向是合成假设；压力构造为除第一个外均定向，不等同普通分布。相同种子/位置在不同误差与策略间复用，3900是20方法×195案例的**策略执行数**，不是3900独立随机场景；其390个problem/case组合自身也有上述配对依赖。

### 归档与独立重算

本次抽查三轮配置、全部逐局汇总、快照哈希及日志尾部：

| run目录（均为2026-09-11） | 执行数/归档全清数 | 核验源码快照数 | 结果 |
|---|---:|---:|---|
| history-confirmation | 2925/2925 | 108 | 全部快照哈希匹配；CSV每源算术均值与JSONL重算一致；日志正常完成 |
| deferred-confirmation | 3900/3900 | 121 | 同上 |
| cover21-confirmation | 3900/3900 | 141 | 同上；与当前live相比，配置列入的文件仅write_report.py不同 |

前两批live差异为run_bounded_robot.py与write_report.py，不能据入口扩展便称旧决策算法被改写。三批共10725记录均无failure；这是本次查阅归档的结果，不是本次重新执行10725局。

对最新3900条gzip轨迹，**本次另写物理核账程序逐条重算1000861个请求**：接收距离/方向、near/clear结果、每步移动四舍五入到微秒、检测/切频/清除费及最终清除集合均一致；方向残差最大1.004999707°，与“±1°潜在误差后两位最近舍入”相容。这项检查未调用两套simulator的物理判定；边界用了明确的小容差。它没有重新证明每一步区域包含或21站连续覆盖，也不逐点复算其哈希误差值，不冒充整套数学认证。证据：[verification-overall.json](verification-overall.json)。

### 新发现：均值可复验，但逐局复现对浮点环境敏感

本次用指定venv（Python3.14.6、NumPy2.5.3、单线程），载入冻结参数、保存的全部场景及误差配置，运行当前live主力各195局。**390/390全清**，结果如下；时间均为虚拟秒，均值为逐局“总时间/清除数”的算术平均：

| 主力/场景 | 局数 | 原每源均值 | 本次每源均值 | 总时间有变化的局数 | 单局总时间最大绝对差 |
|---|---:|---:|---:|---:|---:|
| Q3 range_area7 普通 | 150 | 238.951684 | 238.963259 | 60 | 86.291726 |
| Q3 range_area7 压力 | 45 | 281.400307 | 281.915802 | 16 | 208.784860 |
| Q4 range_grid21_29 普通 | 150 | 445.327406 | 445.186721 | 105 | 2391.466770 |
| Q4 range_grid21_29 压力 | 45 | 528.338197 | 529.371922 | 35 | 538.494455 |

关键反例为 `Q4/clustered__iid__152/range_grid21_29`：原2740.285591秒、148请求，本次5131.752361秒、236请求，均清除16源。**seed固定不等于跨环境轨迹固定；逐局收益与尾部结论需要冻结运行环境并单独验证。** 均值接近和全部清除支持其合成效率的大致量级，但不能掩盖这项敏感性。结果及复跑代码见 [main-reproduction.json](main-reproduction.json)、[reproduce_main.py](reproduce_main.py)。

已定位两个具体放大机制：

- **精确坐标哈希改变误差场取值。** [reference/shumo-b/mock/error_field.py:41](/Users/flower/math/2026/NTJ_B_wt/B/reference/shumo-b/mock/error_field.py:41)把float64坐标的字节作为iid键，spatial也取这个哈希的正负（:64）。在 `uniform__adversarial-spatial__154` 的第45个请求，同一频道16的坐标只差约4×10⁻¹³米，读数从91.41°变89.41°，整局6747.541538→5998.937246秒。它仍满足固定有界误差模型，不是官方物理违规；但会把数值库的小差异变成完全不同的合成观测，不能忽略其复现实验的代价。根目录自建World同样使用精确浮点哈希，见simulator.py:50。
- **近等距探测排序翻转。** [bounded_width_policy.py:27](/Users/flower/math/2026/NTJ_B_wt/B/bounded_width_policy.py:27)直接按浮点距离排序，没有近似相等时的稳定几何规则。`boundary_outward__n16__negative`第258个请求两候选距当前点分别382.7331210214844与382.73312102148446米，选择顺序翻转后实际目标点相距80米，no_signal/direction分支不同，时间8495.147416→8467.147416。固定负端点误差下也出现，所以不能全归咎于iid哈希。

本次还选两主力及count备选各自普通/压力最慢例做6条重跑及反馈重放：均全清；4条反馈重放在最大约5.3×10⁻¹²米的坐标差下保持动作序列，另2条在上述近等距探测处产生80米差异。严格字节相同的重放没有通过，不能声称6条全部逐请求完全一致。首轮审计程序因严格比较而退出，随后保留严格比较结果，并增加1e-7米的诊断比较；**没有修改同学算法、参数或原始轨迹来“修复”复现。** 详细首差异与探测距离见 [reproduction-diagnosis.json](reproduction-diagnosis.json)、[diagnose_reproduction.py](diagnose_reproduction.py)。

最新冻结配置只记录Python可执行文件的原机绝对路径、单线程和代码哈希，未完整锁定Python/NumPy/BLAS版本，见 [icra_confirmation.py:86](/Users/flower/math/2026/NTJ_B_wt/B/icra_confirmation.py:86)。现有证据支持上述数值敏感机制；尚未在原Anaconda环境复跑，不把所有跨环境差异归因于某一个特定NumPy版本。

### 时间、清除率与“胜出”的口径

归档最新普通Q3=238.95、Q4=445.33秒/源，对本批240/460门槛成立；本次重跑普通均值也低于门槛。压力则281.40/528.34，不能以普通均值代替任意场景保证。GOAL自身已承认旧range跨117—156四批普通均值为246.11/474.21；它不是新21站的跨批成绩。

独立核对归档配对，21站range较22站range有81/195局更慢，最大多993.54秒；普通P95总时间6501.25→6581.20，最大6701.94→6747.54；压力P95 7538.92→8057.51，最大8276.03→8495.15。**均值改善伴随两类P95和最大值上升。** count_locked_grid21_29普通/压力均值441.52/516.62更低，但相对21站range同样81/195局更慢，最大多1399.38秒。这些是归档同环境比较，不与本次不同环境重跑混成配对效果。

wall_s/cpu_s由policy.run前后计时，初始化单列，排除导入、场景生成、路线加载及事后gzip落盘；是内存协议执行，不含官方HTTP、GUI和完整进程启动。见 [icra_confirmation.py:129](/Users/flower/math/2026/NTJ_B_wt/B/icra_confirmation.py:129)。它们不能直接对比截图1.19/1.86秒的“程序运行时间”。题面还要求各问演练后3次正式记录与原名官方日志；现有最新离线材料尚未完成这个交付要求，符合他们当前主动保持离线的范围。

## 当前主力方案识别

### 阅读顺序与入口的历史层级

REPORT.md最上方已经是Q1/Q2复核并暂停持续优化；它没有新增Q3/Q4成绩（REPORT.md:3、7）。Q3/Q4应读其后的21站更新，不能取报告末尾“Q3主动三角格、Q4裁剪方格”当最新推荐。GOAL保留active描述，REPORT更新了暂停状态，二者是任务状态的时间差，不是新算法成绩。

最新明确推荐在 [REPORT.md:122](/Users/flower/math/2026/NTJ_B_wt/B/REPORT.md:122)：**Q3 range_area7；Q4 range_grid21_29，保留22站对照。** 没有全局自动切换的“当前最佳默认值”；必须指定series/method。

| 文件/入口 | 实际用途 | 是否最新主力/能否HTTP |
|---|---|---|
| run_robot.py | 9月10日六个方格/三角/active策略；默认Q4裁剪方格 | 早期Policy；唯一现成practice HTTP入口 |
| run_smart_robot.py | 遗传/自适应路线及Q3环形候选；auto读取9月10日selection | 历史路线优化系列；仅参考mock |
| run_bounded_robot.py | 根据icra/mission/task/wide/coupled/history/deferred/cover21构造冻结策略 | 最新应指定cover21；默认series仍icra；仅参考mock |
| launch.py / run_experiments.py | 启动9月10日independent或peer基准；有归档防覆盖与原机路径依赖 | 历史实验入口，不是当前策略启动器 |
| package_robot.py | 只打包run_robot、Client、旧Policy/geometry/intelligent/coverage/自建simulator和9月10日routes | 未包含bounded入口或21站主力策略依赖；不能复现最新报告成绩 |

关键证据：[run_robot.py:18](/Users/flower/math/2026/NTJ_B_wt/B/run_robot.py:18)、[run_smart_robot.py:18](/Users/flower/math/2026/NTJ_B_wt/B/run_smart_robot.py:18)、[run_bounded_robot.py:23](/Users/flower/math/2026/NTJ_B_wt/B/run_bounded_robot.py:23)、[run_bounded_robot.py:45](/Users/flower/math/2026/NTJ_B_wt/B/run_bounded_robot.py:45)、[launch.py:9](/Users/flower/math/2026/NTJ_B_wt/B/launch.py:9)、[package_robot.py:10](/Users/flower/math/2026/NTJ_B_wt/B/package_robot.py:10)。这属于**研究版本与交付版本未对齐**，不是打包程序暗中替换成绩的证据。

### 实际pipeline，不靠几十个policy文件名猜测

公共骨架为：预先认证的发现站点 → 对未知频道保证扫描 → direction更新保守多边形 → 将剩余扫描与已发现源定位清除作为任务调度 → MEC/保证清除位置或有限光学兜底 → 清除16源或完整覆盖且已发现源全部清除后退出。这里MEC圆心可用于路线预测，未被作为真值。

**Q3 range_area7** 经工厂实际生成 `CoupledCompletionPolicy`，7个ring7站点，`dispatch_model=base, range_skip=True, area_prior=True, remainder_weight=1`。通过两类充分保收条件筛选第二点，以区域面积先验的协方差/残余不确定性与移动代理排序，单源最多3次主动测量，必要时转光学完成；源任务与扫描任务联动，但不是Q4的分包中断实现。代码：[completion_sensing_policy.py:39](/Users/flower/math/2026/NTJ_B_wt/B/completion_sensing_policy.py:39)、[completion_sensing_policy.py:105](/Users/flower/math/2026/NTJ_B_wt/B/completion_sensing_policy.py:105)、[intelligent.py:80](/Users/flower/math/2026/NTJ_B_wt/B/intelligent.py:80)。**当前主力并没有在线运行他们研究过的完整C_sig连续minimax。** 区域均匀先验及协方差只是排名近似，不是题设分布或清除证书。

**Q4 range_grid21_29** 实际生成 `CoupledWidthPolicy`，21站为中心+8内+12外整数布局，`dispatch_model=base, range_skip=True, fraction=.15, share_cooldown=150, transverse_m=40`。继承链经过BoundedWidthPacketPolicy、WideProbeMixin、InterleavedMixin等：从成功接收锚点构造成对前向探测，横向目标40米并限制在1.02°—30°斜率范围；一次成功测向或完成一个负反馈探测对之后允许改派任务，累计RF预算不因中断重置。两点皆无信号时才依据接收几何收缩投影范围；单点无信号不贸然切掉源区域。见 [bounded_width_policy.py:17](/Users/flower/math/2026/NTJ_B_wt/B/bounded_width_policy.py:17)、[wide_probe_policy.py:16](/Users/flower/math/2026/NTJ_B_wt/B/wide_probe_policy.py:16)、[interleaved_policy.py:18](/Users/flower/math/2026/NTJ_B_wt/B/interleaved_policy.py:18)。

两主力都带距离证书删除：仅当当前已知源区域的包围圆与扫描点满足 `distance > 1500 + radius + 1e-5`，推知该频道此次必无信号，返回内部标签，不改Client实际位置/频道/时钟。[coupled_dispatch_policy.py:68](/Users/flower/math/2026/NTJ_B_wt/B/coupled_dispatch_policy.py:68)。未知频道依然扫描。它与后来的faithful/deferred/count删除不是同一个实现，**不能将后者“保持原计划不增加虚拟费用”的定理直接套到简单range相对任意基线的比较。**

count_locked_grid21_29是备选：固定站序插入源任务、历史8点负反馈预测、延后扫描及公开16源空频道删除，多层Mixin叠加；历史faithful/deferred适合展示有条件的费用删除定理，lean适合展示相同决策下计算加速。它们均不是因文件更新更晚就自动替代当前主推荐。准确规格见 [cover21_confirmation.py:25](/Users/flower/math/2026/NTJ_B_wt/B/cover21_confirmation.py:25)、[cover21_experiments.py:25](/Users/flower/math/2026/NTJ_B_wt/B/cover21_experiments.py:25)；本次实例化的类继承链已保存在verification-overall.json。

### 保证的有效范围

本次没有找到能直接推翻当前主力全清逻辑的算法反例：读数区域外包、MEC清除、有限RF预算、光学覆盖、未知数量结束证书构成了合理的保证链。源码使用1.01°工程角误差及64边外包圆盘（[geometry.py:6](/Users/flower/math/2026/NTJ_B_wt/B/geometry.py:6)、:74），MEC最后重新取所有顶点最大距离（:131），避免把小半径的漏包圆直接用于清除。Q3结束条件见joint_task_policy.py:100，Q4见interleaved_policy.py:193。

这不等于本审计认证了所有数值病态或335136秒/9766指令的完整最坏界。该界依赖最多10轮Q4主探测、全局中断≤24、布局/行动半径和有限光学路径等参数；不是任意policy参数、断网或即将现实超时的会话都保证完成。当前21站减少站数且最大半径小于1950米，报告给出了继承原界的理由（REPORT.md:213），本次未发现明显扩大预算的证据，但没有独立重证整套几何常数。

REPORT顶部承认的Q1退化分类缺陷属于另一条Q1求解接口；不能直接推断Q3/Q4一定漏源，也不能借Q3/Q4全清反过来抹去Q1缺陷。我们应继续使用我方PLAN的清晰区域合同，而非整体复制他们geometry.py。

## 整体总评与对我方建议

**总体评价：这是有实质几何和实验工程价值的离线研究原型，值得借鉴其保证优先的结构与失败留存；当前还不是可直接接官方、稳定逐局复现的交付成品。** 其优点是把发现、定位、清除、结束分开论证，并让效率启发式服从包含关系和有限兜底；缺点是研究工厂与归档路径耦合深、Mixin继承长、入口与打包落后、数值决策和误差场的复现敏感性未被原报告充分覆盖。

对我方按以下顺序复用与开发：

1. **先建立小而完整的端到端Q3/Q4基线。** 复用协议字段、串行状态更新、同ID重试思想及公开反馈日志格式；修补截断响应、会话ID、绝对期限和尝试级日志。将策略与transport明确分开，让同一个策略工厂可接我方mock或HTTP；打包测试必须核对方法、参数、站点哈希，避免旧入口运行出“看起来正确但不是报告那版”的程序。
2. **复用覆盖证书和有限结束结构，独立核验后再用具体坐标。** Q3七站、Q4二十一站是有价值的公开常量候选；保留域外站点，不能投影回1800米源域。布点证书应针对实际发送坐标、最小1000米接收半径和任意定向半平面。先保留简单覆盖备用，不从某规则两圈失败推出任意布局的全局下界。
3. **让我方Q1/Q2核心服务于Q3/Q4，保持口径分离。** 我方PLAN的Q1是纯角锥P；同学在线update_region同时加入源域和接收距离，属于Q3/Q4可用的保守物理区域，不能移作Q1定义。Q2的主目标是完整物理候选及连续最坏直径，MEC/20米清除状态并列；不要把他们当前协方差面积排序称为实现了我方minimax。1.005°最近舍入外包与他们1.01°含截断外包是不同假设，必须标明。
4. **优先复用保守包含与有限兜底，再增加智能调度。** 保留near立即clear、R≤20的包围证书、两负反馈成对推理、每源累计预算和未知数量停止条件。一次no_signal不等于没有源；达到10源不够；同点重复检测不是独立降噪；D≤40不保证20米圆盘覆盖。扫描与定位/清除任务的联合路线值得做，但TSP更短、MEC更小或平均更快都不是整局支配保证。
5. **将数值复现作为实验设计的一部分。** 锁定Python、NumPy、BLAS与线程，保存实际请求坐标；近等距探测采用明确稳定的候选编号/容差规则。若我方选择坐标量化，应量化实际动作后重新核验覆盖与保收，不能只改模拟器把不同地点偷偷当同地。合成评估同时保留精确哈希压力和平滑场；对少量均值收益，检验环境变化、配对基线和尾部是否改变结论。
6. **报告四类不同证据。** 数学保证、合成全清、同后端配对耗时、官方演练/正式日志分别报告。保留训练/冻结/确认划分、完整失败和变慢案例，计时覆盖完整最小程序及HTTP。最新390/390本机重跑只证明本批的实测表现；59514次累计执行不是独立样本量、官方成绩或获奖概率。官方环境具备后，再按题面完成真正的演练和正式交付。

不建议照搬几十个policy继承层和实验模块链。可复用的核心是“公开反馈状态机＋保守区域接口＋覆盖/清除/结束证书＋可替换任务评分＋独立评分与重放”，把其中必要的少数组件重新接到我方PLAN接口即可。

本次审计复核命令（只写本审计目录）：

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /Users/flower/math/2026/B题/models/q1q2/.venv/bin/python -B /Users/flower/math/2026/B题/models/q1q2/peer-audit/q34/verify_overall.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /Users/flower/math/2026/B题/models/q1q2/.venv/bin/python -B /Users/flower/math/2026/B题/models/q1q2/peer-audit/q34/diagnose_reproduction.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /Users/flower/math/2026/B题/models/q1q2/.venv/bin/python -B /Users/flower/math/2026/B题/models/q1q2/peer-audit/q34/reproduce_main.py
```
