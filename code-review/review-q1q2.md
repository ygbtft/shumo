# Q1/Q2 生产代码复审：风格、可读性与残留正确性

审计日期：2026-09-11。范围为 `models/q1q2/` 下 geometry、circle、feasible、q2、diagnostics、adapters、plots、q1、run、`__init__` 及 `optional/certified.py`，共 3272 行。以下文件位置均相对 `/Users/flower/math/2026/B题/models/q1q2/`；行号对应本次读取版本。

先读 PLAN.md v3 的输入合同、§2—3、§5—7、§8、§11—12 与附录 A，再逐文件检查；之后查阅上一轮 static-review，仅用于辨别已经修复和仍然存在的问题。本轮没有修改生产代码、注释、测试或已有 benchmark 产物；运行仅限本地只读调用和既有单测。

## 结论与证据等级

本轮没有确认 P1 阻断问题。应优先处理：冲突约束索引错位、边界候选的虚假合法世界标记、自定义源网格失去嵌套性、同点距离字段错误、不可实现反馈被赋予清除动作，以及 F7/F8/T3 的输出口径错误。其余主要是兼容残留、无效配置、位置参数过长和数学意图缺注释。

- **P1 阻断**：足以否定常规主链路核心结果，本轮未确认。
- **P2 该修**：已复现或可直接由调用链验证的结果/合同错误，或会妨碍交付的资源问题。
- **P3 优化**：可读性、冗余和局部整理；不能当作数学错误。
- 每条另标“实测”“静态确定”或“风险”，不把未复现的数值疑点写成真 bug。

保留的合理结构：理论 1° / 最近舍入外包 1.005° / 官方未知是三种数学口径，不是版本兼容开关；`require_direction`、行动域消融和未知/已知接收半径用于 PLAN 指定实验，不应删。Q1 精确有理谓词、最小圆支撑复核和区间认证也不是可随意删除的“炫技”。`ordinary_three_point_circle` 与 `forced_circle` 即使很短也具有不同数学合同，应保留语义区分。各结果 dataclass 有实际跨模块和序列化用途，不建议改成无结构字典。

## 1. geometry.py

### G1 · P2 · 正确性：去重后冲突索引不再指向输入约束（实测）

**位置：geometry.py:324、332—337。** `rows` 先按系数去重，再把其下标 `(j, i)` 放进 `Region.conflict_constraints`，没有映射回 `hps`。有重复约束时，对调用者而言给出的“冲突约束”可能根本不冲突。

复现：依次输入 `x≤0, x≤0, y≤0, x≥1`，返回 `EMPTY, conflict_constraints=(0,2)`；取原输入第 0、2 条重新求交却返回 `UNBOUNDED`。正确冲突应含第 3 条。**建议：**去重时同步保留首个原始索引，返回原索引，或直接返回约束 source 标识；不得让消费者猜索引属于哪个中间数组。区域 EMPTY 本身没有算错，错的是证明性诊断。

### G2 · P3 · 兼容冗余：删除已经停用的 deque 外壳（静态确定）

**位置：geometry.py:297—306。** `_enumerated_vertices(rows, tol)` 明写 Compatibility，`tol` 未使用；`_deque_vertices` 只转调它，实际主入口在 360 行直接走 `_exact_vertices`。范围内生产代码没有其他调用。**建议：**两者直接删除，测试/benchmark 若仍引用旧入口则改为当前入口，不保留“deque 名字 + 枚举实现”的接口假象。不要为了恢复旧名字重新引入有缺陷的浮点 deque。

### G3 · P3 · 隐式状态：把隐藏的精确系数字段声明出来（静态确定）

**位置：geometry.py:80、92—93、175—177、319—324。** frozen dataclass 之外动态增加 `_exact_bearing`、`_exact_row`、`_normal_degrees`，后面用 `hasattr` 区分来源。读类型定义无法知道真正参与几何判定的字段；序列化和 dataclass 相等性也看不到它们。**建议：**声明为 `field(init=False, repr=False, compare=False)` 等明确字段，角度元信息用显式 `None`；构造时一次设置。仍可用 frozen dataclass 的 `object.__setattr__`，问题是字段隐身，不是该机制本身。明确注释：手工 HalfPlane 是二进制 float 系数语义，角锥系数则由十进制度数和高精度三角近似构造。

### G4 · P3 · 注释与无效参数：当前精度/复杂度合同应对应实际算法（静态确定）

**位置：geometry.py:134—155、220—225、365—369、401—419。** `convex_hull` 文档中的“near duplicates”不足以解释实际删除的是邻边内部近共线点；`dimension=lambda v:min(len(v),3)` 不如直接比较 `min(len(world),3)` 与 `min(len(exact),3)`。`diameter(..., policy)` 完全不使用 policy。**建议：**补一句 80 位三角近似与有理运算各负责什么、70 位阈值为什么留安全距离；文档说明精确枚举的算术操作复杂度为 O(M³)、直径全对枚举 O(V²)，有理数位长成本另计。删除无效 policy 参数并统一调用，不让调用者以为调它会改变直径；这不要求删除凸包真正使用的容差。

## 2. circle.py

### C1 · P3 · 兼容式无效参数：政策对象传了一圈但部分函数不使用（静态确定）

**位置：circle.py:104—140、175—178、79—98。** `forced_circle`、`_contains`、`enumerate_circle` 的 policy 不参与计算；导出精度预算却固定为 `2e-12*radius + 64*ulp(radius)`。这容易造成“传入 NumericPolicy 就能调所有圆判据”的误读。**建议：**从这些实际不依赖 policy 的接口去掉参数，向上清理无意义传递；保留 `diameter_circle_cover` 真正用到的 Thales 未决带。把导出的固定相对精度命名为局部常量，并解释它是输出可表示性门槛，与覆盖判定容差不同。

### C2 · P3 · 重复计算：Q1 同一顶点集求两次最小圆（静态确定）

**位置：circle.py:260；q1.py:45、48。** `solve` 已算出最小圆，`diameter_circle_cover` 为 κ 再算一次，而且两处 seed 均为 0。**建议：**结果装配只算一次；将已有圆作为必需参数传给覆盖诊断，或在 Q1 装配 κ。不要新增“可传圆，也可省略自动重算”的兼容分支。独立 Thales 判定仍须保留，不能改成两个浮点半径相减。

### C3 · P3 · 注释缺口：两套显式栈的不变量不易从代码看懂（静态确定）

**位置：circle.py:160—172、201—214、217—228。** `state=0/1` 的含义、`result` 为什么可以跨栈帧保留，以及浮点提议支撑→原坐标精确复核→精确回退的顺序缺少就地说明。**建议：**加两三句解释 state 是“先解不含末点的子问题/返回后检查末点”，boundary 是强制圆周支撑，失败才切换回退；给 `len(q) <= 80` 命名并注明枚举 O(V⁴) 的成本限制。不必为了消除这点结构重复而发明泛型 Welzl 回调框架。

## 3. feasible.py

### F1 · P2 · 正确性：同站特判的距离字段固定填 5（实测，上一轮风险仍在）

**位置：feasible.py:349—352。** `S∈C_dir` 正确，但 `distance_to_closure=near_radius` 不一定成立。首站 `(0,0)`、目标圆心 `(1000,0)`、半径 1、读数 0° 时，实际闭包距离是 999，返回字段却是 5。**建议：**特判只直接断言 C_dir 成员；距离需要时调用 `closure_distance`，或者置 `None` 并注明未算。不能把“严格大于 5 的已知下界”填进“到闭包的距离”。

### F2 · P3 · 无复用的可选参数和晦涩回夹（静态确定）

**位置：feasible.py:85、97—98、334—336。** `radial_interval` 的 `lower/upper` 在范围内所有生产调用都未传；函数职责本来就是 F 的完整径向区间。`min(max(0., eps-inset), max(min(0., -eps+inset), alpha))` 需要反复拆解。**建议：**删除无使用场景的 lower/upper，把回夹写成 `inner_eps=max(0,eps-inset)` 后 `a=min(inner_eps,max(-inner_eps,alpha))`，并解释这是为构造实际内部见证，不是扩大可行域。

### F3 · P3 · 注释缺口：边界语义与量纲应就地可读（静态确定）

**位置：feasible.py:171—183、197—245、353—364。** 最应补注释的是：为何按 rho_lo 分成 low/high；high 目标是消去 r1² 后的线性支撑函数；各 `violation/g_low/g_high` 单位都是 m²；`1e-8` 是 h² 的裁剪阈值，不是距离容差。`BoundaryPiece.attained` 只按来源赋值，不能描述 wedge 段包含开端点的情况，内部正确性依赖 `_boundary_witness` 再核验。**建议：**明确它只是片段元信息、不可直接用作端点合法证据，或删掉这个易误用的布尔字段，保留实际见证检查。近切计算是否误分类本轮未构造新反例，不把固定阈值本身判成真 bug。

## 4. q2.py

### Q2-1 · P2 · 正确性：BOUNDARY 结果下实际世界的接收半径不合法（实测）

**位置：q2.py:330—369、525—527、648—654；feasible.py:401—431。** 保留 BOUNDARY 推荐点是 PLAN §7.6 允许的，不能仅因它非 IN 就判 bug。问题是 `_pair_witness` 固定给每个世界 `rho=max(rho_lo,r1)`，不检查 `r2≤rho`，最后无条件 `actual_legal=True`；后验/清除链也没有明确拒绝保收未决前提。

默认 F、`q=(-1e-10,0)` 返回 `BOUNDARY, max_violation=3.0000000000001e-7 m²`。取样本 `(1000,0),(1500,0)` 评分，世界分别输出 `(rho,r2)=(1000,1000.0000000001)`、`(1500,1500.0000000001)`，两者均不能以所报半径收到 direction，却标实际合法。极小预算搜索也实际返回了该 q；不是只能从错误的域外手工调用触发。

**建议：**保留边界结果和残差，但给它独立“保收未决”说明，不能自动走依赖已保收的保证链。每个输出世界独立核验同一个 rho 覆盖两站；如果只要构造存在性世界，可取 `max(rho_lo,r1,r2)` 并检查不超过 rho_hi，但必须说明这不证明 q 对所有世界保收。超出 rho_hi 的见证不能标合法。正常 IN 候选主结果不因此自动失效。

### Q2-2 · P2 · 正确性：允许的自定义网格不保证样本嵌套（实测，上一轮未修项）

**位置：q2.py:52—53、255—281。** 极坐标部分累计 0…level，但独立边界采样只取本级 `grids[level][0]`。首站 `(1000,0)`、0°、默认物理参数、网格 `((4,4),(5,5),(6,6))`：level0 有 32 点，level1 有 51 点，仍丢失 11 个旧点，包括 `(1799.975929404661,-9.308789600504884)`。默认 9/17/33 并不自动代表自定义配置也嵌套。

**建议：**边界样本也按 `for k in range(level+1)` 累计，或输入合同只接受严格嵌套网格并在入口验证；前者更直白。实测证明的是集合不嵌套，不声称这组例子的 J_hat 一定下降；它已足以破坏 PLAN §7.2 的单调性依据。

### Q2-3 · P2 · 结果口径：站点步长数量任意，阶段诊断却写死三阶段（静态确定）

**位置：q2.py:42—45、550—556、729—749、805—806、899。** SearchConfig 接受 `station_steps_m=()`、`(50,)`、`(25,50,10)`。搜索按实际数量生成 grid winner；`station_refinement_change` 却一律将前 3 个解释成 coarse/fine/local。三次网格时，第三个网格赢家会冒充局部细化赢家；空元组遇到排名翻转还可能在 `[-1]` 处异常。**建议：**本竞赛就只支持两级由粗到细网格，构造时明确验证长度、顺序和需要的嵌套关系；不用为任意阶段序列构建兼容框架。计数配置也宜拒绝非整数，别等到 range/linspace 才报错。

### Q2-4 · P2 · 资源/停止：deadline 检查间隔过粗，frontier 公共复评没有预算（实测局部超时；其余静态确定）

**位置：q2.py:707—718、766—779、833—874、948—982。** 初次采样和整圈边界构造之间无时间检查；单次 score 的块循环和方向边界采样也无可中断点。小网格 `((2,2),)*3`、预算 0.001/0.01 秒，实际分别约 0.149/0.148 秒才返回。该小例只证明软预算，不用倍数夸大常规 180 秒场景。更值得修的是 frontier：每个预算搜索结束后，对全部累计候选做细级补点和两遍公共评分，没有 deadline，成本可能远大于原搜索。

**建议：**至少在边界射线、评分块、终选单项和 frontier 公共阶段检查统一截止时间，保存最后一轮完成的公平比较结果；未完成一整轮不能混排。明确 `time_budget_s` 是每次搜索软预算还是整条 frontier 的预算。不需要线程、任务池或取消框架。

### Q2-5 · P3 · 过度间接与失效配置（静态确定）

**位置：q2.py:315—318、624—628、642、19—37；run.py:284。** `select_second_point` 只转调 `_search`；`sample_sources` 又通过临时 `SearchConfig()` 隐式选择默认网格，调用者因此经常绕过公共入口调用 `_sample_sources`。`evaluate(...,stage)` 不读 stage，`SearchConfig.seed` 只被记录而不驱动搜索。**建议：**合并采样入口，明确必需的网格/偏移/角宽；合并搜索包装层，保留 frontier 真正需要的额外候选参数。删除未使用 stage 和 seed，或将 manifest 明确写成“搜索确定性，圆算法固定 seed=0”。保留这些字段并不增加可复现性。

### Q2-6 · P3 · 可读性：长位置构造和深推导式掩盖最终口径（静态确定）

**位置：q2.py:690—696、868—873、934—936、988—993。** 20 多项位置参数构造 Q2Result/多项 CandidateResult，审计时必须不断对照字段顺序；frontier 在推导式中用海象运算调用候选检查，再在嵌套 min 中选择赢家。**建议：**结果一律关键字构造；用普通循环完成“检查→建备选→找最小 J→按 tie 比移动”。不要引入 ResultBuilder、工厂或新配置层。`_direction_boundary_samples.evaluate`（174—220 行）同时返回分数并向外部 set 添点，应改名体现记录行为或把更新放回调用侧，并注释金分割只是保留局部合法见证，非全局最大证书。

### Q2-7 · P3 · 注释/账本：明确 evaluation 和敏感性究竟统计什么（静态确定）

**位置：q2.py:874、886—890、915—940、1014—1015。** `evaluations += 7` 是手数当前调用数；baseline、coarse_best 重评及救援评分没有统一计数，frontier 又给每个结果加整组共享次数和累计共享耗时。**建议：**定义统计单位为“score_point 调用次数”或“唯一候选数”，只用一个计数入口；共享 frontier 复评单列总成本，避免把所有结果的 elapsed_seconds 相加后重复计费。846、875、885、938 行最应补一句样本代际说明：何时公共点集冻结、哪些旧审计字段仍有效。`tolerance_scope` 已诚实标 full_chain_audit_pending，不能再把当前变化量称为全几何链路 S7 已完成。

## 5. diagnostics.py

### D1 · P2 · 正确性：不可实现 near 仍被赋予可执行清除状态（实测，上一轮未修项）

**位置：diagnostics.py:39—51；feasible.py:405—408。** 默认 F、q=S、反馈 near，`posterior_contains` 正确筛出空集；`clearance_summary` 随即无条件返回 `ON_SITE`、后续 5 秒。首次已经 direction，同地点固定误差与距离下不可能变 near。**建议：**入口明确要求合法、已接受且与当前模型一致的反馈，并拒绝可直接证明矛盾的 q=S/near、空 F 等情况。不能仅因没有采到点就判反馈不可能，需区分“空样本”与“已证不可实现”。正常合法 near 的 5 米解析保证保留。

### D2 · P2 · 比较口径：启发式公共补点忽略配置的 ε₂ 和 near 偏移（静态确定）

**位置：diagnostics.py:244—247；q2.py:250—251、404—408。** `compare_heuristics` 调 `_sample_sources` 时不传 `second_half_width_deg`、`near_offset_m`，始终按 1°/1e-7 补方向接触点。随后重新包装 `SourceSamples`，丢失 augmentation_q/angle 元数据，score_point 的角宽不匹配补点分支不会触发。主搜索终选却正确传递配置。因此 ε₂ 非 1° 时，“同信息、同精度”的比较没有使用相同的定制边界搜索规则，可能产生漏采差异。

**建议：**每次补点显式传配置的角宽和偏移，再取公共并集；沿用主链的“保留局部见证→公共复评”次序。`reassess_old_point` 的第 277 行也应显式传角宽，虽随后评分可能补救，但不应依赖元数据触发第二次隐藏计算。本轮未宣称某组默认参数的推荐排序因此翻转。

### D3 · P3 · 减少重复判定并补时间/裕量注释（静态确定）

**位置：diagnostics.py:250—255、49、52—71、79—84、100—106。** 启发式重新手写移动预算和 arena 限制，与已有 `check_admissibility` 重复，且它只收 IN 而搜索允许保留 BOUNDARY，输出须说明差别。清除的 5 秒、速度 5 m/s、32/64 边和 0.1 米切换门槛散落多处。**建议：**调用同一准入函数，再明确比较仅用已判 IN；给成本和加密阈值命名常量并注释“当前测量之后的移动+清除，不含本次测量和求解墙钟”。`e20_outer_sufficient` 应说明它用的是哪个外包及何种裕量，避免被误当区间证书。不增加通用时间账本类。

## 6. adapters.py

### A1 · P3 · 合并无必要的输入形状与重复模式字段（静态确定）

**位置：adapters.py:118—121、125—152；geometry.py:60—62。** 手工 JSON 同时接受裸列表和 `{"measurements":...}`，而仓内 standard.json 已用后者；`rounding_mode` 与 `error_mode` 在命名模式下总填同一个值，再维护一套相等性校验。**建议：**竞赛输入统一为带 measurements 的对象；在当前没有独立量化规则的模型中保留一个 error_mode 和 assumption_source 即可，删除重复字段及对照分支，并更新调用/数据。不删除显式 mock Observation 与公共 JSONL 两个入口：它们是 PLAN 要求的真实数据源，不属于旧接口迁就。

### A2 · P3 · 可读性：观察记录与角度记录改成关键字构造（静态确定）

**位置：adapters.py:55—60、69—77、118—121、24—27。** 多个可空身份字段与模式字符串连续位置传入，容易交换 session/stage/stability 或重复 mode。`assumption_source` 三层条件表达式也不利于确认“官方未知”分支。**建议：**显式关键字构造，两三个普通 if/return 给模式解释。`seen` 的 request 去重与 `positions` 的重复测量去重有不同业务语义，应保留并注释，而非因它们都是去重就硬合并。

本轮未确认适配层新增真 bug；accepted/transport/清除过滤及跨会话拒绝已有实现，不能重复列为缺失。

## 7. plots.py

### PLOT1 · P2 · 资源：绘图中途异常会遗留 Figure（静态确定）

**位置：plots.py:72—115。** `plt.close(fig)` 只在两个格式都成功保存后执行。未知 panel kind、无效数据或 savefig 异常都会绕过关闭。反复在同一进程里调用 render 可累积 Figure。**建议：**每次创建后 `try: ... finally: plt.close(fig)`；不需要新增资源管理类。复核可用未知 kind 触发 104 行 ValueError，比对调用前后 `plt.get_fignums()`，无需写图片。

### PLOT2 · P3 · 约束注释：图规格 schema 应能直接查到（静态确定）

**位置：plots.py:24—57、71—104、118—124。** 多层 `.get` 本身并非兼容旧版证据：颜色、图例和多面板确实可选。但 geometry/heatmap/curve/bars 的必需字段和单位散在分支内，`spec.get('panels',(spec,))` 又同时接受两种面板形状。**建议：**在 render 文档中列四类必需键、允许空值、coordinates 单位和保存结果前提；统一为 panels 数组。CSV 的嵌套值 JSON 化用普通循环写出，明确 None 代表未评估，不是零。不建议创建一套图形类继承体系。

## 8. q1.py

### Q1-1 · P3 · 去重可拍平为显式集合（静态确定）

**位置：q1.py:24—42。** 对 clean 每条再执行 `any`，单纯几何重复检查 O(N²)；`getattr` 同字段反复访问也增加阅读负担。**建议：**保留身份一致性、request 去重和同地点不同读数诊断的三个目的，另用 `seen_geometry={(position,bearing,width)}` 做几何去重；不要把它们揉成一个难读 key 生成器。对缺失 session/channel 的允许规则加一句：缺字段是手工几何输入，不意味着已经证明同一物理会话。

### Q1-2 · P3 · 结果装配减少无效工作（静态确定）

**位置：q1.py:45—49。** 无顶点时先求空输入最小圆，再立刻覆盖该结果；有顶点时又与 C2 重复求圆。**建议：**按 region 状态先分支，再计算一次圆并关键字构造 Q1Result。空集面积 None、点/线段面积 0 的口径应保留，不要为统一类型把空集也改 0。

## 9. run.py

### R1 · P2 · 正确性：F7 把全局见证无条件画到所有反馈面板（实测）

**位置：run.py:132—145。** 循环中的 feedback 每次变化，所画线却固定使用 `result.score.witness`。默认物理配置、首站 `(0,0)` 读数 0°、q=(100,0)，候选 IN；粗小网格实测主见证为 direction，端点约 `(104.999343471,-0.081029986)` 与 `(1499.771542735,26.178609656)`。F7_0 direction 面板两点都属于后验；F7_1 near 面板仍画同一线，两点均不属于该 near 后验。

**建议：**只有经 `posterior_contains(ss,q,feedback,[x,y],policy).all()` 复核的点对才画进该面板；其他反馈取自己的支撑/见证或不画。只比较 branch 名还不够，两个 direction 反馈也可能有不同 β。这是论文图的实际错误，不是主 J 评分错误。

### R2 · P2 · 正确性：F8 两条曲线使用不同角宽模型（静态确定）

**位置：run.py:153—161。** `DiagnosticConfig(source_origin=...)` 默认半宽 `(1,1)`，下一行精确角锥却用首测半宽及 `result.config.second_half_width_deg`。1.005° 敏感性或自定义角宽时，标作近似/精确对比的两条曲线不是同一数学输入。例如两半宽都改为 2° 时，正确 A_lin 是当前绘制值的 4 倍。

**建议：**显式传 `half_widths_deg=(ss.first.half_width_deg,result.config.second_half_width_deg)`，caption 同步写角宽。第 110 行绘图采样也应使用结果配置，或直接保存并复用实际终选样本；现在它重新走默认网格/1° 补点，不能让图注暗示这些就是计算 R_hat 的样本。

### R3 · P2 · 正确性：T3 仍宣称已废弃的 deque 主算法（实测输出，静态确定）

**位置：run.py:97—101；geometry.py:288—294、360、401—419。** 求解输出 method 为 `exact_enumeration`，T3 却写 `deque/vertex recheck: O(M log M)+O(MV)`、枚举只在 degenerate 时发生。当前所有有界交都枚举交点并验证原约束，算术操作数 O(M³)；直径也是 O(V²) 全对枚举。圆的候选枚举回退另为 O(V⁴)。**建议：**T3 直接写当前实际路径与回退，不套旧 PLAN 的算法表；注明高精度/有理数位长开销。不能为“符合表格”删除 benchmark 修复。

### R4 · P3 · 冗余映射与一行条件流（静态确定）

**位置：run.py:25—30、86、271、278。** 通用 jsonable 对“具有 diameter_estimate_m 属性”的对象隐式加导出键，使普通序列化掺入 Q2 专例；图编号用五层三元式；多 bundle 表格采用覆盖式推导合并。**建议：**Q2 导出显式读 `score.J_hat` 或在具体 Q2 序列化处写清字段，删除影子别名；图号用小字典加明确默认名；表格用循环，重名时明确拼接或报错。当前只有少数固定 bundle，不需要通用注册器或插件式 renderer。

## 10. __init__.py

### INIT1 · P3 · 文档口径过时（静态确定）

**位置：__init__.py:1。** “default float64 implementation” 已无法概括 geometry 的 Decimal/Fraction 谓词和 circle 精确支撑验证。**建议：**改成“Q1/Q2 implementation of PLAN v3”，或明确“float 输入/输出；几何使用高精度近似与有理谓词复核”。此文件保持只有包说明即可，不加导出兼容表、惰性加载器或版本判断。

## 11. optional/certified.py

### CERT1 · P3 · 认证表示差异需要具体说明（静态确定；未发现新的区间界方向错误）

**位置：optional/certified.py:3—5、54—75、92—105、115—139。** 模块已有“float 代表精确二进制值”的说明，但与 geometry 对角度做 `Fraction(str(...))` 的十进制度数语义不同。**建议：**就地补充：本证书针对传入 binary float 定义的连续问题，不是对所有生产中间几何近似的逐项认证；差异通常微小，仍不能把两个输入语义说成严格相同。保持独立原始输入入口与局部 MPIntervalContext，不调用生产候选/采样作为证书前提。

### CERT2 · P3 · 注释缺口：向外导出、分支剪枝与初始种子的预算（静态确定）

**位置：optional/certified.py:17—22、77—81、149、155—170、179—193。** 最值得补的是：`float(endpoint)` 后再 nextafter 的方向；maximum/minimum 是区间端点单调外包；poly/叉积用于排除整个盒与构造合法下界的条件不同；种子阶段也计入 elapsed 但循环中尚未检查预算。**建议：**把 149 行三层嵌套坐标 enclosure 推导式展开成两个循环；把 8、32768 等分别命名为角点尝试频率和缓存上限，注明只影响性能；说明超小 time_limit 仍先完成种子不是硬实时。不要删 outward nextafter 或把严格 direction 边界改成容差通过。

### CERT3 · P3 · 删除无使用价值的序列化包装与硬编码版本标签（静态确定）

**位置：optional/certified.py:38—41。** `to_dict` 只有 `asdict(self)`，无额外合同；backend 固定写 `mpmath.iv 1.3.0`，它不是运行时依赖版本检查。**建议：**若调用者已有 dataclass 序列化，直接用 asdict，删除该包装；backend 只写 mpmath.iv，依赖版本由复现 manifest 统一记录，或读取一次真实版本。不新增“针对不同 mpmath 版本选择算法”的兼容分支。本轮本机区间冒烟通过，不能据此声称已完成 Windows 或全套认证审计。

## 本轮实际验证及可复现入口

使用已有 `/Users/flower/math/2026/B题/models/q1q2/.venv/bin/python`（Python 3.14.6），没有安装依赖；系统 python3 缺 NumPy，首次尝试导入失败后切换到该环境。所有 Python 用 `-B`，pytest 禁用缓存写入。

```sh
cd /Users/flower/math/2026/B题
models/q1q2/.venv/bin/python -B -m pytest \
  models/q1q2/tests/test_geometry.py \
  models/q1q2/tests/test_circle.py \
  models/q1q2/tests/test_adapters.py \
  models/q1q2/tests/test_feasible.py \
  -q -p no:cacheprovider --import-mode=importlib
```

结果：**129 passed in 0.34s**。未重跑全部 benchmark、全部 Q2 搜索或完整认证套件；这些通过结果不覆盖上述新增反例。

以下第一段复现 G1、F1、D1、Q2-1、Q2-2，直接在上述根目录的 Python 中执行即可，无文件写入：

```python
from models.q1q2.geometry import BearingMeasurement, HalfPlane, NumericPolicy, intersect_halfplanes
from models.q1q2.feasible import PhysicsConfig, Feedback, build_source_set, check_candidate, closure_distance
from models.q1q2.q2 import SearchConfig, SourceSamples, score_point, _sample_sources
from models.q1q2.diagnostics import clearance_summary

p = NumericPolicy()
h = [HalfPlane((1, 0), 0), HalfPlane((1, 0), 0),
     HalfPlane((0, 1), 0), HalfPlane((-1, 0), -1)]
r = intersect_halfplanes(h, p)
print(r.kind, r.conflict_constraints)
print(intersect_halfplanes([h[i] for i in r.conflict_constraints], p).kind)

first = BearingMeasurement((0, 0), 0)
clipped = build_source_set(first, PhysicsConfig(arena_center=(1000, 0), arena_radius=1), p)
print(check_candidate(clipped, (0, 0), True, p).distance_to_closure,
      closure_distance(clipped, (0, 0))[0])  # 5 vs 999
ss = build_source_set(first, PhysicsConfig(), p)
print(clearance_summary(ss, (0, 0), Feedback('near'),
      SourceSamples(((1000, 0),), 0, (2, 2)), p).status)  # ON_SITE
q = (-1e-10, 0)
print(check_candidate(ss, q, False, p).status)  # BOUNDARY
w = score_point(ss, q, SourceSamples(((1000., 0.), (1500., 0.)), 0, (2, 2)), SearchConfig()).witness
print(w.actual_legal, [(z['rho'], z['second_distance_m']) for z in w.worlds])

ss = build_source_set(BearingMeasurement((1000, 0), 0), PhysicsConfig(), p)
grids = ((4, 4), (5, 5), (6, 6))
a, b = _sample_sources(ss, 0, grids), _sample_sources(ss, 1, grids)
print(len(a.points), len(b.points), len(set(a.points) - set(b.points)))  # 32 51 11
```

R1 的 F7 检查使用实际诊断和图规格装配，不需要保存/渲染图片：

```python
from models.q1q2.geometry import BearingMeasurement, NumericPolicy
from models.q1q2.feasible import PhysicsConfig, build_source_set, check_candidate, posterior_contains
from models.q1q2.q2 import SearchConfig, Q2Result, score_point, _sample_sources, _conditional_diagnostics
from models.q1q2.run import q2_bundle

p = NumericPolicy()
ss = build_source_set(BearingMeasurement((0, 0), 0), PhysicsConfig(), p)
q = (100, 0)
cfg = SearchConfig(source_grids=((3, 4),) * 3, pair_rounds=0)
samples = _sample_sources(ss, 0, cfg.source_grids, q)
score = score_point(ss, q, samples, cfg)
clear, angular = _conditional_diagnostics(ss, q, score, samples, cfg)
r = Q2Result(q, check_candidate(ss, q, False, p), score, 100, 20, 5,
             config=cfg, clearance_diagnostics=clear, angular_comparison=angular)
figures = [f for f in q2_bundle(ss, r).figures if f['id'].startswith('F7')]
for f, c in zip(figures, clear):
    pair = f['panels'][0]['lines'][0]['values']
    print(f['id'], c.feedback.kind, posterior_contains(ss, q, c.feedback, pair, p).tolist())
# F7_0 direction [True, True]
# F7_1 near [False, False]
```

另执行了 `certify(默认ss,(0,0),max_nodes=0,time_limit_s=0)`：返回 `CERTIFIED_BOUNDS`，`[1495.0030558992114, 1505.9165262597212]`，停止原因为 node_budget。此项只验证可选模块在当前环境的冒烟路径及资源退出状态，不是连续全局最优认证。

## 建议落地顺序

先修 G1、Q2-1/2/3、F1、D1/2、R1/2/3 的结果或合同问题，再补资源退出与 Figure 清理；最后统一删除兼容外壳、无效参数和改关键字构造。注释重点放在原始数值语义、开边界合法性、公共样本代际、平方量纲、停止预算和虚拟行动时间。不要在这次风格整理中改变已经 benchmark 修复的几何判据、回退算法或误差模型。
