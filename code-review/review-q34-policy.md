# Q3/Q4 策略、调度、路线及客户端只读审计

审计日期：2026-09-11。基于当前工作区（包括未提交的修复），不是历史 code_snapshot。行号相对 `/Users/flower/math/2026/B题/B/`。没有修改源码、注释或实验产物；只新增本报告。测试使用 `../mock/.venv/bin/python -B`，网络复现只连接本次创建的随机回环端口。

严重度：P1 阻断；P2 该修；P3 优化。条目另标「真问题 / 冗余 / 可读性 / 注释」，避免把风格当 bug。未发现足以认定两项主候选在正常协议下不能完成闭环的 P1。确认了 4 项 P2 正确性/资源问题，其中 3 项在客户端/演练服务，1 项在非主候选 discovery 消融策略；另有主入口的实验依赖需要收敛。

## 1. 先确认真正调用链

### 1.1 注册、工厂和布局

两项主候选均可由以下入口选择（这里只列命令，不在审计中写 robot_runs）：

```sh
../mock/.venv/bin/python -B run_bounded_robot.py --series cover21 --problem 3 --method range_area7
../mock/.venv/bin/python -B run_bounded_robot.py --series cover21 --problem 4 --method range_grid21_29
```

`run_bounded_robot.py:54–61` → `cover21_confirmation.py:25–40`。后者的 `build` 是 `cover21_experiments.build` 的别名，而该别名又指向 `public_count_experiments.build`。用 `sys.setprofile` 实际记录了以下工厂链，两项候选相同：

```text
public_count_experiments.py:31
→ lean_scan_experiments.py:37
→ cheap_prediction_experiments.py:41
→ batched_history_experiments.py:41
→ deferred_skip_experiments.py:46
→ faithful_skip_experiments.py:53
→ historical_pair_experiments.py:51
→ fast_dispatch_experiments.py:42
→ negative_hull_experiments.py:46
→ coupled_dispatch_experiments.py:53  [在这里真正实例化]
```

前九层只是对不属于自己的 kind 转发；不能因此认定主候选使用了历史负反馈、廉价预测、固定站序或发现优先策略。

| 项目 | Q3 range_area7 | Q4 range_grid21_29 |
|---|---|---|
| 最终类 | CoupledCompletionPolicy | CoupledWidthPolicy |
| 最初参数来源 | coupled_dispatch_experiments.py:23–28，经 prior SPECS 复制 | coupled_dispatch_experiments.py:24、33；cover21_experiments.py:25–30 替换 layout |
| 显式参数 | kind=coupled_completion, dispatch_model=base, range_skip=True, layout=ring7, area_prior=True, remainder_weight=1 | kind=coupled_width, dispatch_model=base, range_skip=True, layout=grid21_29, fraction=.15, share_cooldown=150, transverse_m=40 |
| 布局 | spatial_decision_experiments.py:55 → ring_coverage.stations(6,1140)：原点+6个外圈点 | cover21_experiments.py:35–45 → rounded-cover21/certified_layouts.json 的 grid21_29.route，共21点 |
| 生效默认值 | share=True, share_limit=6, task_order=two_opt, trial_radius=80, max_active=3, time_weight=.08 | share=True, share_limit=6, trial_radius=40（工厂补入）, bracket_steps=10, pause_limit=16, prediction=center, dispatch=two_opt, width_rule=constant |

`icra_confirmation.SPECS` **不含**这两个名字；默认 `--series icra` 不能直接选择它们。

### 1.2 运行时闭环

Q3：

```text
JointTaskPolicy.run (joint_task_policy.py:79)
→ CoupledDispatchMixin.next_task (:105)，base 分支直接 super
→ EfficientJointPolicy.next_task → JointTaskPolicy.next_task → remaining_route
→ 扫描：CertifiedRangeSkipMixin.measure → JointTaskPolicy.measure
        → JointPolicy.measure → Policy.measure → Client
→ 定位：CompletionClearancePolicy.complete_source (:105)
        → 面积先验 completion_choice；最多3轮主RF
→ 清除：ClearanceMixin.clear → JointTaskPolicy.clear → Policy.clear
→ 失败兜底：关闭 active 后直接 Policy.complete_source，有限光学覆盖
```

Q4：

```text
InterleavedMixin.run (interleaved_policy.py:162)
→ CoupledDispatchMixin.next_task 的 base 分支
→ InterleavedMixin.next_task → remaining_route（中心预测）
→ source_packet (:97) → BoundedWidthPacketPolicy.probes
  → 每包最多两个探点；成功方向或完整双阴性才返回调度器
  → 双阴性 clip + 清掉 MEC 缓存
  → 每源最多10轮，耗尽后 fallback → Policy.complete_source
→ measure 经 CertifiedRangeSkipMixin、ProbeJointPolicy、JointTaskPolicy、JointPolicy、Policy
→ clear 经 JointTaskPolicy、Policy（不走 Q3 ClearanceMixin 的就近光学投影）
```

两项都不会进入 `arc_route`、`insert_sources`、`service_entry`、`ServiceAwareMixin.next_task` 或 `DiscoveryPriorityMixin.next_task`。Q4 的 `ProbeJointPolicy.complete_source` 虽可从类上取到，但主 run 调用 `source_packet`，不能把前者误记为主执行路径。

终止口径：16 是公开上限；否则必须所有站点处理完、所有发现源清掉，未知频道具有完整扫描记录。距离跳扫仅针对已知未清源且只在 surveying 时发生，不替代未知频道的覆盖扫描。`surveyed` 在该路径含“已由推断完成处理”的站点，不能解释为真实 RF 调用数。

### 1.3 指定文件的归属

| 文件 | 归属与本次重点 |
|---|---|
| route_algorithms.py | 离线路线比较/生成；主候选初始化没有调用 optimize；也会因实验导入链被导入 |
| adaptive_routes.py | remaining_route 是两项主运行时；AdaptiveOrder/AdaptivePolicy 是旧对照 |
| joint_task_policy.py | 两项共用状态与分享测量；Q3 主 run；Q4 继承初始化/measure/clear |
| completion_sensing_policy.py | Q3 主定位；expanded 等分支是消融 |
| discovery_priority_policy.py | 非主候选实验策略；近期修复专项复审 |
| coupled_dispatch_policy.py | 两项主类与距离跳扫；base 以外调度分支是对照 |
| service_aware_policy.py | 非主候选实验策略，不在这两项实际工厂链中 |
| interleaved_policy.py | Q4 主 run、分包预算、回退；Q3 packet 变体是对照 |
| client.py | 两项公共客户端；HttpTransport 用于 mock-http/practice |
| bounded_http.py | HTTP 演练/实践运行入口及日志；本地 HTTPServer 是演练设施 |
| run_bounded_robot.py | 主 CLI；也保留多代实验入口 |
| icra_confirmation.py | 历史确认实验引擎；SPECS/all_paths 被旧入口使用，主候选只间接依赖部分构建路径 |

## 2. 逐文件意见

### 2.1 client.py

- **C1｜client.py:42、51–67｜P2｜真问题：响应头阶段没有绝对截止时间。** `_timeout(deadline)` 在 urlopen 前设置的是 socket 单次阻塞超时；urlopen 返回前已经读取响应头。对端每隔短于 timeout 的间隔发一行头，可以让读取头部持续越过 deadline，直到代码进入 body 阶段才报超时。本次 .12 秒预算实际约 .37 秒才返回 TimeoutError，见复现 A。实际截止时间前预留的1/2秒不能保证覆盖这种情况。建议在固定 transport 内把连接、发送、头部和正文纳入同一个绝对截止时间，超时主动关闭连接；失败仍用同一 ID 重试，不引入新动作。不要仅在 urlopen 返回后增加一次检查并声称已解决总时长问题。
- **C2｜client.py:135–156｜P2｜真问题：成功响应的解析失败没有锁停客户端，状态提交也不是原子的。** `try/except` 只包 transport；接受 `{"accepted":true}` 后，147行 KeyError 在锁停范围外；随后仍能发下一条新 ID 动作。已在正常 enter 后复现 `/enter,/measure,/measure`，见复现 B。`float('nan')` 等非有限时间也未被拒绝，`/enter` 可能先写 virtual_s、再因剩余时间字段失败而留下半提交状态。建议先核验当前固定协议的必需字段、结果枚举及有限时间，将响应完整解析到局部变量，再一次提交公共状态；解析/日志持久化失败时锁停，不能让上层 catch 后继续。主候选 runner 当前会让异常上抛并结束，因此“继续发第二条”是公共 Client 的缺陷，不宣称现有主 run 已经这样做。
- **C3｜client.py:51–61、136–139｜P3｜兼容冗余/可读性。** 对 `read1`、fp/raw/_sock 的层层 getattr 以及“不是 HttpTransport 就只传两参数”隐含多个 transport 协议；无 read1 时读正文前只检查一次 deadline，行为还弱于正式分支。固定比赛 Python/urllib 与现有两种 transport 后，明确所需接口；测试替身实现同一个接口，删掉旧 read 回退。私有 socket 访问应集中到一个明确的读取函数，并说明所依赖的固定结构。不可顺手删掉正文分块计时、HTTPError 正文读取或同 ID 重试，这些是有作用的容错，不是版本兼容。
- **C4｜client.py:120–123、147–152｜P3｜注释。** 保留现有预留时间注释，补清“deadline 是 enter 请求开始时刻+返回剩余秒数，因此保守扣掉响应耗时；这是本地保护而不是服务端时间同步”。注明 virtual_s 是服务端累计值，不由客户端按距离累加；出口一旦停止不能通过新 enter 恢复。

近期修改判断：扩大到 OSError/HTTPException 的捕获范围、不可变请求体重试、失败碎片日志、异常后不补发 exit 均通过现有回归；C1/C2 是尚未覆盖的缺口，不否定这次修复本身。

### 2.2 bounded_http.py

- **H1｜bounded_http.py:58–63、81–89｜P2｜真问题：半包未关闭会卡住 mock 服务及退出。** 新长度检查只能处理 read 已返回的 EOF；连接仍开着时 `rfile.read(length)` 没有超时。单线程 HTTPServer 无法处理后续请求，finally 的 shutdown 等待 serve_forever 返回，也无法完成。复现 C 在打印 leaving context 后1.5秒仍不结束。建议为已接受连接设置有界读取期限，覆盖请求头及正文；退出时关闭当前连接使阻塞读取解锁。不能仅把工作线程设为 daemon：当前 shutdown/join 仍会等待。
- **H2｜bounded_http.py:155–163｜P3｜日志口径。** `execution_state="unknown" if journal.failures ...` 判断的是“整个运行有没有失败过”，不是“最后一条动作是否尚未确认”。例如一条测量重试成功，随后策略发生纯计算异常，仍标 unknown。建议按 pending request_id 追踪是否收到有效确认；confirmed_only 明确指“报告只含已确认状态”，不要把累计失败数当 pending 状态。`commands=journal.count-journal.failures` 目前是收到完整响应的调用数，不必然是 accepted 动作数；失败摘要最好同时写清这个口径。
- **H3｜bounded_http.py:99–111、117–145｜P3｜封装边界。** Journal、owned_mock_http 和 run_http 各有复用意义（测试会单独使用），不建议为少几个类强行拍平。需要收敛的是 mock 后端、practice 执行和评分混在同一大函数中的分支；保留一个公共执行/落盘过程，把 mock 创建与评分限于入口的确定分支。`getattr(policy,"cleared",())` 在当前固定 factory 都提供 cleared 的情况下可改为显式初始化失败分支。
- **H4｜bounded_http.py:128–145｜P3｜注释。** 最该解释的是三种账本：客户端确认响应数、后端收到的 HTTP 尝试数、去重后真实动作数；重试时三者本来就不同。现在去重校验方向正确，补一条约束注释即可，别又改回请求行数相等。

### 2.3 run_bounded_robot.py

- **R1｜run_bounded_robot.py:11–14、34–58｜P2｜运行依赖/过度封装：主候选仍依赖整条旧实验树。** 工厂十层转发、paths 十九层转发已经动态确认。即使只跑 Q3 ring7，也会读取 polar、convex、closed/rounded 等实验 JSON；`replacement_experiments.py:51–55` 还会在缺旧 polar 证书时生成并写文件。这不是对主候选的必要兼容。建议建立只含两个候选的显式注册及两项布局加载，直接实例化 CoupledCompletionPolicy/CoupledWidthPolicy；历史实验 CLI 留在实验目录。复核方式：在临时隔离环境让 `Path.read_text` 仅对旧 layout-alternatives JSON 抛 FileNotFoundError，当前 Q3 all_paths 即失败，而其 ring7 本可直接生成。不要在原目录删除文件验证。当前完整工作区能运行，此条不是宣称现有路径已丢失。
- **R2｜run_bounded_robot.py:24、34–56｜P3｜旧入口/多分支冗余。** 默认 series=icra 与当前定型方法名不配套，八套历史选择分支增加使用负担。主交付入口按 problem 选择两项定型候选即可；若保留对照入口，移到单独脚本，并明确默认值。方法列表应来自该固定注册，避免复制映射。
- **R3｜run_bounded_robot.py:63–78｜P3｜可读性/注释。** 场景生成、初始化、开始计时、策略执行和保存被多次塞在同一行。拆成普通语句；注释写清 offline 使用 peer 后端、mock-http 使用 B/simulator.py，两个模式同 seed 不意味着同真值；wall_s 排除导入/路径/初始化，program_wall_s 才含前述阶段。不要用 offline 的结果冒充 HTTP 性能。

### 2.4 icra_confirmation.py（SPECS/方法注册为主）

- **I1｜icra_confirmation.py:23–42｜P3｜历史注册冗余。** 这是旧确认候选表，不是当前主候选表。`all_paths` 为旧 square45 额外读 selected_routes.json。与 R1 一并移出正式入口；旧证据仍应保留对应快照和候选定义，不能把历史表就地覆盖成新候选，导致旧实验含义改变。
- **I2｜icra_confirmation.py:81–94、120–145；cover21_confirmation.py:132–136｜P3｜脚手架隐式副作用。** 多代 confirmation 通过改 engine.OUT/SPECS/all_paths/cases/builders 等全局量复用引擎；顺序调用不同实验 main 会改变全局状态，阅读单个引擎无法确定真正构造类。实验侧可用一个显式 `run(specs, paths, build, cases, out)` 函数，直接传参，删除 `_prior_*` 配合全局换绑的层层适配。主候选只导入 cover21_confirmation 时尚未执行这些 main，不能把这一风险说成当前导入就会重写引擎。
- **I3｜icra_confirmation.py:88–94、115；cover21_confirmation.py:125–129｜P3｜脚手架注释/误导。** 1950次、77–86、旧基线等描述被后代脚本靠字符串 replace 修改。改为从本轮 specs/cases 的实际元数据生成说明，避免复制的“冻结/未用于调参/全部通过”固定文字被误读为本次运行证据。这里只指出重复与误导，不要求重做所有历史实验。

### 2.5 route_algorithms.py

- **T1｜route_algorithms.py:48–60、125–143、395｜修复复核通过。** B1 已把近整数 allclose 换成对输入浮点数的精确 Fraction 整数倍检查，不再给近方格错误套棋盘下界；最优标记还要求差值非负。B2 在每次插入比较前查预算，耗尽后保留已完成插入，再按 initial 顺序补齐 unused，未丢站或超预算。模块内回归覆盖三组近方格/精确方格、预算1–12、非零原点索引，全部通过。这里只确认这些输入范围；不是对任意极端尺度浮点输入的形式化证明。
- **T2｜route_algorithms.py:48–53｜P3｜可读性。** 两层 Fraction 推导式再叠 all/颜色求和难读，可用普通 `for point`、`for coordinate` 分别计算整格坐标、判定格点、累计奇偶。**保留精确有理判断**，不要为“简单语法”退回 round/allclose，否则恢复 B1。
- **T3｜route_algorithms.py:200–204、231、350、385｜P3｜隐式副作用/元编程。** 预算预留临时修改 limit，宜改为显式保留一个验证评分槽或传局部比较额度；父选取写成两次清晰的锦标赛选择；多样性分数用具名循环/中间变量；`globals()[method]` 改显式函数字典。不是要求把有实际复用价值的 Problem/Budget/Search 全部拆掉。
- **T4｜route_algorithms.py:61–62、371–401｜P3｜脚手架指标口径。** optimize('two_opt') 返回的是共同初始化时已经算好的 initial，且这部分比较不计入 Search.budget；history/raw_proposal_best 初始化于 initial，对 greedy/insertion 的输出未必表示返回路径的搜索历史。现有 shared_setup_s 和模块说明已有部分解释，建议在结果字段附近补“预算只计搜索阶段、非全算法计算量；历史字段适用随机搜索”，或仅为随机方法输出这组字段。避免拿 comparisons=1 解释为2-opt只做一次比较。主候选运行不执行此 optimize。

### 2.6 adaptive_routes.py

- **A1｜adaptive_routes.py:23–25｜P3｜可读性/注释。** 将三元表达式拆成 `if i==0` 与普通前驱边分支，明确这是开放路线：起点是当前已接受位置、终点自由，因此要评估反转到末尾的后缀，不计返回原点距离。距离是对称的，所以内部反转边相互抵消；这和 coupled 的有向情形不同。
- **A2｜adaptive_routes.py:34–67｜P3｜非主候选抽象层。** AdaptiveOrder 通过迭代器执行重规划、累计统计并读取可变 client.position，再把 Policy.stations 从数组替换成该对象，接口不直观。主候选只需要 remaining_route。将旧 AdaptivePolicy/AdaptiveOrder 移至对照模块；若还要用该对照，直接在它的 run 中维护 unused 与统计即可。remaining_route 不必为了旧迭代器增加兼容协议。

### 2.7 joint_task_policy.py

- **J1｜joint_task_policy.py:16–31｜P3｜多分支/继承冗余。** 初始化先按 JointPolicy 的 Q3 模式构造，再重写 mixed 并初始化 bracket，Q3 同样携带永不执行的 bracket 状态；Q4 主 run 又不走本类 complete_source。定型整理时保留共用 region/measure/share 状态，把 Q3完成和Q4分包明确放在两项策略里；不要再通过一个 mixed 参数切换多代 complete_source。保留必要共用方法即可，不建议复制几何实现。
- **J2｜joint_task_policy.py:33–65｜P3｜注释/隐式副作用。** measure 可能递归触发跨频道 share，clear 成功也可能触发 share； `_sharing` 防递归，`_surveying` 禁止扫描时插入额外分享。最应在两入口说明“调用返回时 client.channel 可能已被分享测量改变；必须读 client 真实状态”，以及 `_attempted` 是用来抑制近位置重复测量。53–58行补 cross 的几何含义、1米/0.2阈值和1000+radius只是效用过滤而非不可能接收证书。
- **J3｜joint_task_policy.py:79–105｜P3｜重复/可读性。** 89、93、98行等多动作语句拆开；与 interleaved_policy.py:174–199 的逐站频道扫描及终止核验重复，可合并为一个有实际双处复用的简单方法（如 scan_station），不再增加扫描任务类/工厂。98行 surveyed 表示频道在该站已处理，包括上层 certified skip；未知频道仍必须真实扫描。停止说明应明确16是上限，不是隐藏源数。

### 2.8 completion_sensing_policy.py

- **Q1｜completion_sensing_policy.py:39–70、95–103｜P3｜消融开关冗余。** 主候选固定 area_prior=True、remainder_weight=1、expanded=False；非面积/expanded/零权重回退是实验对照，并非正式版本兼容。将正式路径固定为面积先验实现，消融留实验文件，避免三个布尔/权重条件组合在主逻辑里。当前 area_quadrature 的退化线段/点处理有数值意义，应保留。
- **Q2｜completion_sensing_policy.py:75–88｜P3｜注释缺口。** 补清 covariance 单位为m²，noise 采用均匀角误差±1.01°经线性化后的方差（除3），sqrt(3*最大特征值)是排序代理而非认证半径；travel 的 `/5+5` 是5m/s与5秒RF，remainder_weight 只给中心代理返程加权，不写入虚拟时间。面积先验不是官方源分布。函数顶部已有“非线性近似”说明，应延续而不是重复代码。
- **Q3｜completion_sensing_policy.py:108–137｜P3｜停止判据注释。** 注明 max_active=3 限主主动轮数，分享测量单独统计；radius<=20−1e−5 是认证清除，80米 trial 是每源一次未认证尝试。active=False 的回退意图是禁止再次启动主动RF，直接保证有限光学完成；这里保存旧 active 并 finally 恢复的写法是正确的，不应为拍平删除。

### 2.9 discovery_priority_policy.py

- **D1｜discovery_priority_policy.py:16–20、61、78–83｜P2｜真问题：重复记账修复未清除 clear_weight 的行为入口。** 删除旧“精确源奖励”是正确的，现有三项回归通过；但 clear_weight 还保留在 `if self.discovery_weight or self.clear_weight` 中。discovery_weight=0 时，只把 clear_weight 从0改1仍会启用 route 前若干任务的提升重排，哪怕根本没有已知源。复现 D 产生 survey 3→survey 4。这不是重复扣费还存在，而是已经废弃的参数暗中变成另一种路线优化开关。建议从构造、校验、字段和条件中彻底删除 clear_weight；同步删除/明确归档 discovery_priority_experiments.py:28–29、37–38 的 clear_reward/clear 变体。不要保留“兼容旧参数但忽略”适配。
- **D2｜discovery_priority_policy.py:47–54、65、72｜P3｜兼容/可读性。** getattr(_last_partial) 和 hasattr(predicted_action) 再配 lambda 是为原子/分包多种基类做运行时探测；实验若仍保留，直接分两个明确入口/使用统一明确的预测函数，不靠属性存在推断语义。remaining_worlds 三元表达式和 np.r_ 的提升操作可以分为 if/else 与 concatenate，命名 promoted_order。
- **D3｜discovery_priority_policy.py:21–37、62–68｜P3｜概率注释。** 给384个面积点、128个边界点、12个朝向的混合权重口径补注释：这是固定搜索优先级先验，边界被人为加权；1000m是最小接收半径，不能把 gains 当真实发现概率。negative history 在这里是“所有未知频道均已扫描的站点集合”，不是每个已知源的 RF 后验。现有模块说明已经明确不删覆盖站，应保留。

### 2.10 coupled_dispatch_policy.py

- **K1｜coupled_dispatch_policy.py:83–131、134–143｜P3｜过度封装/死分支（仅相对主候选）。** 两个正式类都固定 dispatch_model=base；此时 CoupledDispatchMixin 只增加一些永远为零/不用的 arc、locked 统计后转发 super。正式类可只组合 CertifiedRangeSkipMixin 与实际 Q3/Q4基础类；arc/locked 与 CoupledWidePolicy 留在对照模块。不要误删 CertifiedRangeSkipMixin，它是两个 range 方法的实际差异。
- **K2｜coupled_dispatch_policy.py:68–79｜P3｜注释/固定接口。** 现有“三角不等式、非伪造响应、不改位置频道时间”注释正确；再说明 Q4 的 `_last_negative` 更新仅用于 share_cooldown 效用过滤，不裁切 region。把 hasattr(_last_negative) 改成明确的 Q4 钩子/两项短实现即可，勿为兼容未来策略保留属性探测。返回 certified_no_reception 是内部事件字符串，不能当作官方 RF response 写进真实请求账本。
- **K3｜coupled_dispatch_policy.py:9–40、43–59｜P3｜非主候选可读性。** arc_route 的29行拆 if；保留33–34行内部反向弧差，不能照搬对称2-opt删掉它。insert_sources 注释补 station_count 表示 tasks 前缀是扫描任务，后缀是已知源；该算法只保持扫描相对次序，未承诺全局最优。暂未发现这两种路线实现的确定性正确性错误，不把启发式次优记作 bug。

### 2.11 service_aware_policy.py

- **S1｜service_aware_policy.py:103–157、160–165｜P3｜非主候选过度封装。** ServiceAwareMixin 完整覆盖了 CoupledDispatchMixin.next_task，却继续继承它的 dispatch_model 初始化、校验和统计；相当于同时暴露两套调度模式配置。若只保留正式两项，则整个 service 策略移至实验；若继续保留该对照，直接让它使用自己的 service_mode，删除无实际决策作用的另一套开关。不是要求改动正式 range 策略。
- **S2｜service_aware_policy.py:20–35、49–56、87–96｜P3｜晦涩数组式/注释。** 2D前缀和与 before/after/removed/left/right 并非炫技性无用代码，但需要给出索引语义：precedence[a,b] 是 a先于b 时加的成本；反转区间只改变区间内部有序对；square 对应矩形和。插入可先写清每个候选的“入边+出边−旧边+两侧先后成本”，再用数组实现。1e−7 接受阈值与1e−6重算带应解释为浮点消差保护，不能默默删掉重算。
- **S3｜service_aware_policy.py:114–132｜P3｜模型口径。** 已有5秒RF→25米注释很好；补充这是冻结当前区域的任务排序目标，不是精确未来总成本，忽略后续区域收缩/切频/提前clear；needed 的距离条件依赖实际启用 range_skip，若留作通用实验入口需校验这一前提。当前 service_aware_experiments.candidate 复制 range 基线，range_skip=True，因此不把它报成现有候选 bug。

### 2.12 interleaved_policy.py

- **P1｜interleaved_policy.py:19–25、35–48、139–155｜P3｜多分支冗余。** Q4正式值是 prediction=center、dispatch=two_opt；Q3 packet 分支不用于 range_area7。把主用Q4分包过程和对照Q3包隔开，去掉正式入口的 action/nearest 选择。否则读者很容易把 choose_covariance 误当Q4实际动作预测，或把Q3主候选错认为会打断定位。
- **P2｜interleaved_policy.py:74–95、101–138、157–160、200–205｜P3｜关键约束注释。** `_rounds` 是每频道生命周期累计包轮数，不因离开该源重置；`_primary_counts` 仅主测量，不含分享RF；source_interruptions 是全局打断预算，不是每源16次。双阴性后 clipping 的 u 来自已观测方向，切线位置是 anchor投影+length，加1e−6保持保守包含；单个 no_signal 不能作同样截断。`_circles.pop` 是 region变更后必须失效缓存，不能当“多余清理”删除。现有最终轮立即fallback的注释已足够。
- **P3｜interleaved_policy.py:162–208｜P3｜重复/可读性。** 与 JointTaskPolicy.run 共用扫描子流程，终止核验也可以用一个简单函数；保留两套明确的 source 分支即可。74–86的“每源只fallback一次”状态有实际终止约束价值，不建议删除 `_fallback_done` 来减变量。运行期关键断言若作为正式失败保护，应使用显式异常，避免以 python -O 运行时消失；这是执行约束建议，当前未观察到不变量违反。

## 3. 脚手架只需处理的误导性重复

- **F1｜cover21_final_checks.py:26、183｜P3｜候选清单陈旧。** 这里Q3最终检查选择 lean_deferred_area7，不是用户已定型的 range_area7；不能把文件名“final_checks”当作当前主候选测试证据。verify_bounded_http.py:50–52 则已明确两项正确主候选。后续只维护一份定型清单，让新最终检查引用；旧结果标对应方法即可。
- **F2｜verify_bounded_http.py:48｜P3｜网络修复后的验证口径未同步。** `summary.commands == summary.http_requests == len(rows)` 只适用于无重试的正常路径；网络修复后同ID重试应多一个HTTP尝试而不是多一个动作。应把该检查明确限定为“无故障smoke”，或按 request_id/accepted/event 去重核账；不能用它否决已经成功恢复的重试日志。发送故障测试已按新口径校验。
- **F3｜discovery_priority_experiments.py:28–29、37–38｜P2（与D1同一问题，不另计）｜消融名称失真。** 仍有 clear_reward 名字，实际不再奖励清源，甚至只启用额外重排。删掉重复候选或重新命名为真实实验因素，并保留历史快照对应关系。

`*_experiments.py`/`*_final_checks.py` 中未被上述工厂、布局加载或策略继承调用的实验执行函数，不属于此次主闭环。没有按“只要导入就算执行”扩大结论，也没有审查/修改全部历史快照。

## 4. 可复制复现

以下均在 B/ 下用 `../mock/.venv/bin/python -B` 执行；除测试系统临时目录外不写实验目录。

### A. 慢响应头越过绝对截止时间（C1）

```python
import time, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from client import HttpTransport

class H(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers['Content-Length']))
        self.wfile.write(b'HTTP/1.0 200 OK\r\n')
        self.wfile.flush()
        for _ in range(8):
            time.sleep(.04)
            self.wfile.write(b'X-K: v\r\n')
            self.wfile.flush()
        self.wfile.write(b'Content-Length: 2\r\n\r\n{}')
        self.wfile.flush()
    def log_message(self, *args):
        pass

server = HTTPServer(('127.0.0.1', 0), H)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
start = time.monotonic()
try:
    transport = HttpTransport(f'http://127.0.0.1:{server.server_port}', retries=0)
    transport('/enter', b'{"request_id":"test"}', deadline=start+.12)
except Exception as exc:
    print(type(exc).__name__, time.monotonic()-start)
finally:
    server.shutdown()
    server.server_close()
    thread.join()
```

实际：TimeoutError，约0.37秒；不是约0.12秒。时长允许调度误差，但稳定大于头部慢发总时长。

### B. 成功响应缺字段后仍可发新动作（C2）

```python
from client import Client
calls = []
def transport(path, raw):
    calls.append(path)
    if path == '/enter':
        return 200, dict(accepted=True, virtual_time_s=0,
                        remaining_real_duration_s=60, max_virtual_duration_s=1000)
    if len(calls) == 2:
        return 200, {'accepted': True}
    return 200, dict(accepted=True, virtual_time_s=1, measure_result='no_signal')

client = Client(transport)
client.enter()
try:
    client.measure((1, 2), 1)
except KeyError:
    pass
client.measure((3, 4), 1)
print(calls)  # ['/enter', '/measure', '/measure']
```

### C. 未完成请求阻塞 mock teardown（H1）

把下面代码放进子进程，以 `subprocess.run(..., timeout=1.5)` 执行；不要直接在需保留的长寿命进程运行。父进程捕获 TimeoutExpired 会终止/回收该子进程。

```python
import socket, time
from bounded_http import owned_mock_http
from simulator import World
class J:
    def append(self, row):
        pass
with owned_mock_http(World([]), J()) as url:
    sock = socket.create_connection(('127.0.0.1', int(url.rsplit(':', 1)[1])))
    sock.sendall(b'POST /enter HTTP/1.0\r\nContent-Length: 100\r\n\r\n{')
    time.sleep(.1)
    print('leaving context', flush=True)
print('closed', flush=True)
```

实际：子进程只打印 leaving context；1.5秒后父进程超时回收。`sock` 故意未关闭，模拟发送停滞；正常连接关闭/EOF情况已由近期长度检查处理。

### D. clear_weight 废弃残留改变调度（D1）

```python
import numpy as np
from types import SimpleNamespace
from discovery_priority_policy import DiscoveryClearancePolicy
rng = np.random.default_rng(99)
for _ in range(8):
    points = rng.normal(size=(12, 2))*100
for weight in (0., 1.):
    policy = DiscoveryClearancePolicy(
        SimpleNamespace(position=np.array([0., 0.])), points,
        discovery_weight=0., clear_weight=weight)
    print(weight, policy.next_task(list(range(12)))[:2])
```

实际：`0.0 ('survey', 3)`、`1.0 ('survey', 4)`；初始 regions 为空，不存在清源收益。固定12点用于复现调度函数，不声称它是正式覆盖布局。

## 5. 实际验证及边界

1. `../mock/.venv/bin/python -B -m unittest discover -s tests -p 'test_client.py' -v`：11/11通过。
2. 同命令运行 `test_send_failures.py`：3/3通过，含真实 connect/sendall 故障、执行后断连、相同bytes/ID恢复、失败摘要。
3. 同命令运行 `test_discovery_priority_policy.py`：3/3通过；其固定夹具未覆盖D1的额外路线重排差异。
4. `../mock/.venv/bin/python -B route_algorithms.py`：audit_regressions=passed，近格点下界及插入预算回归通过。
5. 两项工厂/MRO与路径调用链：动态追踪完成；加载 paths 时用 mock 禁止 Path.write_text，当前已有文件下未触发写入。
6. 使用当前 factory、B/simulator.py 的内存 Protocol 和 bounded_http.mock_world(seed=42) 执行两主候选及 range_skip=False 控制，各10源，全清、inconsistent_updates=0：

| 方法 | range_skip | 虚拟秒 | RF数 | 总动作 | 距离跳扫 |
|---|---:|---:|---:|---:|---:|
| Q3 range_area7 | True | 3312.579681 | 127 | 141 | 4 |
| Q3 同参数控制 | False | 3336.579681 | 131 | 145 | 0 |
| Q4 range_grid21_29 | True | 5847.482087 | 281 | 293 | 21 |
| Q4 同参数控制 | False | 5973.482087 | 302 | 314 | 0 |

两组控制各自移动路长相同；该seed节省分别为4次/21次RF与相应切频。这个结果只确认当前调用链与一次闭环，不外推所有场景的性能优势。没有重新执行3900条确认实验，没有连接已有官方服务，没有把模拟成绩称为官方成绩。系统 `python3` 最初因缺numpy无法导入测试，随后使用项目venv重跑得到上述通过结果。

## 6. 建议处理顺序

先修 C1/C2/H1 的客户端截止、失败状态和mock退出；再删除 D1 的废弃参数及误导消融。随后执行 R1：将两项正式候选从十层实验工厂和十九层路径加载中抽出，保持当前有效参数及布局点不变。最后做逐文件P3清理与注释。路线B1/B2的精确判断、同ID重试、Q4双阴性成对原子性和有限光学fallback均是必要约束，不属于应删除的“防御性冗余”。
