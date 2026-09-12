# 问题1、2论文写作素材库

整理日期：2026-09-12。用途：作者查数、查证明、查实现和选择论据；不是论文初稿，不提供可直接粘贴的成品论述段落。

## 0. 使用口径与证据索引

- 路径根目录统一为 `/Users/flower/math/2026/B题/`；下文 `models/...:行号`、`review-opt/...:行号` 均相对此根目录。行号指本次读取的生产文件，不沿用旧审查报告中的失效代码行号。
- 数值保留归档 JSON 的精度。数学精确表达式、输入浮点数、计算结果、向外舍入展示值分列；不把相邻浮点数强行统一。无原始数值或无实现时写“无”。
- 复现编号 R0—R9 的完整命令在第10节，均含解释器路径。R0 是读取归档，R1 是读取证明，R2—R7 是重新计算；R8—R9 是历史验证的后续复验入口。**本次仅阅读文件、解析既有 JSON、写本素材文件；未执行这些求解/验证命令，未访问官方模拟器，未触发正式测试。**
- 标签：`[定理/有证明]`＝条件化数学命题；`[可验证充分条件]`＝单向保证或依赖已声明区间包含合同的证书；`[实测/统计]`＝有限案例/归档输出；`[启发式无保证]`＝搜索、近似或性能提议。符号和题设假设本身没有结论强度，记“无（定义/模型前提）”。同一项目的数学命题与实现输出可能分别标级。

| 资料简称 | 完整路径/覆盖范围 | 使用优先级、边界 |
|---|---|---|
| P | `models/q1q2/PLAN.md`，v3，尤其§0—7、§10—13、附录A | 数学对象、量词、物理前提的权威口径；其中算法复杂度及默认纯float说明有后续实现变化，不能当现状 |
| G/C/F/Q/D/A/V/Q1/R | `models/q1q2/{geometry,circle,feasible,q2,diagnostics,adapters,plots,q1,run}.py` | 当前生产事实；实现成功不自动证明数学模型与官方未知流程一致 |
| IC/OC | `models/q1q2/optional/{certified,outer_exclusion}.py` | 固定点连续最坏直径认证/标准场景外层排除认证；两个范围分开 |
| B1/B2/B3/B4 | `models/q1q2/benchmarks/{q1_geometry,q1_circle_cover,q2_candidate,q2_worst_diameter}/` 各 README、夹具、report.json；B4另含report-certified.json | 四块有限案例证据；不是官方评分，不是随机成功率 |
| BO | `models/q1q2/benchmarks/q2_outer/` 的README、report.json、refined.json、paper-results.md、EXCLUSION.md、exclusion证书 | 推荐点、统一复评、固定点区间、外层全域证书；旧report状态未自动改写为外层认证状态 |
| 历史审查 | `models/q1q2/reviews/{correctness,assumptions,static-review,literature-review,creativity}.md`；`models/q1q2/reviews/p3-cleanup/` | 提供证明修补、假设区分、文献证据等级、失败原因；历史问题须对照修复记录，不能重新当成现存缺陷 |
| 代码复审 | `code-review/review-q1q2.md` | 合同、精确谓词、状态传播、性能与可维护性审查；不等于正式验证证书 |
| 优化/创新/核验 | `review-opt/{opt-q12,innov-q12,verify-q12}.md` | 原型建议、三组贡献筛选、独立复核；原型运行时间不能迁移成生产端到端收益 |
| 实现补丁 | `review-opt/q12-production-paper-patch.md` | 更新已落地的精确算术优化与预算API；再接受后两项补丁修正 |
| 外层补丁 | `review-opt/q2-outer-exclusion-paper-patch.md` | 更新“无外层全局证书”的旧说法：现在仅标准连续场景有0.01 m证书 |
| 舍入补丁 | `review-opt/q12-budget-rounding-paper-patch.md` 及 `review-opt/q12-budget-rounding/` | 最新同射线角上界合同；1311项测试及四块benchmark最终证据 |

**写作时需纠正的版本差异**

| 旧表述 | 当前可用事实 | 出处、复现、强度与边界 |
|---|---|---|
| “无外层最优性误差界” | 标准模型已有 `CERTIFIED_OUTER_TAU`，精确gap=`1/100`；一般首站/非对称裁剪场景仍无此证书 | BO `exclusion/certificate.json` 的 `status/gap/model`；R0、R6；[可验证充分条件] |
| “新的同射线界尚未实现/仅binary64” | 已有向外舍入 `same_ray_max_angle_deg` 和默认调用它的tight接口；快速估计另命名 | models/q1q2/q2.py:590、614、627；舍入补丁§定位与修复；R5；[可验证充分条件]，只认证角条件 |
| “1172项测试” | 历史P3为1172；中间版本1290；最新日志为 `1311 passed in 7.91s` | `review-opt/q12-budget-rounding/tests.log:20`；R0文本/R9；[实测/统计]，不相加 |
| “半平面交队列、旋转卡壳、全float64” | 当前精确边界交点枚举、全顶点对距离；高精度三角近似＋有理谓词＋浮点导出 | models/q1q2/geometry.py:139、217、310、333、428；P3 README；R1/R2；[实测/统计]，不能写成已实现O(N log N) |
| “圆覆盖312/330，修复了18个生产几何错误” | 18项为旧oracle的 `forced.exception` 合同预期过时；改后330/330；支撑索引排序是另一项变动 | `models/q1q2/reviews/p3-cleanup/README.md`、`verification.json`；R0/R8；[实测/统计]，不是放宽容差换通过 |

## 1. 假设、符号与适用范围

| 作者需要说明的对象 | 精确定义/常数 | 出处与复现 | 强度、诚实边界 |
|---|---|---|---|
| 坐标与方向 | 世界平面坐标，长度m；东0°、逆时针；外部角度degree，三角公式内部radian；`u(θ)=(cosθ,sinθ)` | models/q1q2/PLAN.md:105、models/q1q2/geometry.py:25、29、52；R1 | 无（定义）；经纬度不能直接当米输入 |
| 物理范围 | `ρ_lo=1000.0`，`ρ_hi=1500.0`，near=`5.0`，清除=`20.0`，目标圆半径=`1800.0`，圆心=`(0.0,0.0)`；动作坐标界各轴`[-2000000.0,2000000.0]` | models/q1q2/feasible.py:16；BO/report.json `physics`；R0、R4 | 无（模型前提）；目标圆限制源，不自动限制检测点也在目标圆 |
| 同一源与观测身份 | 同一会话、频道、阶段、稳定时段；同一现实源的ρ固定；不同候选世界可取不同ρ | models/q1q2/PLAN.md:130、380；models/q1q2/q1.py:22、models/q1q2/adapters.py:98；R1 | 无（信息合同）；不能跨会话拼同频道，不能让同一世界前后换ρ |
| 有界角误差 | 理论连续半宽`1.0°`；最近舍入外包`1.005°`只在“潜在误差≤1°后最近舍入至0.01°”假设下成立 | models/q1q2/PLAN.md:95；models/q1q2/adapters.py:12、98；BO/report.json `first.half_width_deg`；R0/R1 | [定理/有证明]（条件舍入外包）；官方流程未知时无无条件1.005°保证；精确量化相容还要共同读数区间含格点 |
| 误差不确定性 | 同点固定读数，异点取允许有界误差的稳健外包；主结果无概率分布、独立性、零均值假设 | models/q1q2/PLAN.md:64、74、95；`reviews/assumptions.md`；R1 | 无（建模选择）；不是对一个未知连续空间误差场的精确辨识；不可把确定性网格当先验抽样 |
| Q1集合P | `P=∩W_i`，只用角锥；不加目标圆/接收圆/5m排除；`d=d(P)`、`R=R(P)` | models/q1q2/PLAN.md:149；models/q1q2/q1.py:22；R2 | 无（定义）；因此P可无界，不能拿有限画窗裁出“定位区域” |
| Q2集合F | 首次direction后 `F=A∩W_1∩{p:5<‖p−S‖≤1500}`；ρ合法区间为`[max(1000,‖p−S‖),1500]` | models/q1q2/PLAN.md:415、models/q1q2/feasible.py:259；R4 | [定理/有证明]（全向距离模型下消元）；near边界开，F可能非凸、非闭；定向设备共享朝向不在此模型内 |
| 后验与目标 | `K(q,o)`为反馈o后的真实物理可行集；`J(q)=sup_o diam K(q,o)`；`J_R(q)=sup_o R(K(q,o))`；`J*=inf_{q∈C_sig,q≠S}J(q)` | models/q1q2/PLAN.md:544、560、592、658；models/q1q2/feasible.py:417、models/q1q2/q2.py:455；R1/R3 | 无（定义）；Q2主目标是J，不是条件R、总清除时间或整局得分 |
| 状态与退化 | EMPTY→直径null；POINT→d=R=0；SEGMENT→R=d/2；非空UNBOUNDED→数学∞但JSON以状态＋null表达；未决不作空集 | models/q1q2/PLAN.md:141；models/q1q2/geometry.py:105、333；models/q1q2/q1.py:22；R2 | [定理/有证明]（集合事实）＋[实测/统计]（API合同）；`finite_cover`不等于直径圆覆盖，null不能画成0 |
| 预算值函数 | `V(B)=inf{J(q):q∈C_sig,‖q−S‖≤B}`，含S以定义B=0；同点`J(S)=diam F` | models/q1q2/PLAN.md:608；models/q1q2/q2.py:455、572；R1/R5 | [定理/有证明]；不含S的选点问题在B=0无新点，不能把它与V(0)混写 |

## 2. 模型建立与关键推导：问题1

| 素材条目 | 精确关系/证明骨架（非成文段落） | 代码、证明与数据出处 | 复现；强度；边界 |
|---|---|---|---|
| 角锥→半平面交 | `v=x−S`；`cross(u_−,v)≥0`、`cross(u_+,v)≤0`、`u(θ)·v≥0`。统一`n·x≤b`：下法向`(sin(θ−ε),−cos(θ−ε))`，上法向`(−sin(θ+ε),cos(θ+ε))`，前法向`−u(θ)`；均`b=n·S` | models/q1q2/PLAN.md:149；models/q1q2/geometry.py:166；B1/report.json `results` | R1/R2；[定理/有证明]；0<ε<90°前向冗余，ε=0不可删，否则射线变直线；ε=90°单半平面；>90°不支持凸角锥 |
| 分类先于顶点 | 先构造可行见证，再检查非零衰退方向，再枚举有界交点；不能从“没有交点”推出空集 | models/q1q2/PLAN.md:165；models/q1q2/geometry.py:333；B1/report.json `outcome_breakdown` | R1/R2；[定理/有证明]（分类依据）；无界带、半平面、整平面可能没有顶点；病态有限不等于无界 |
| 顶点直径 | `P=conv(V)`且V完整时，`d(P)=max_{v_i,v_j∈V}‖v_i−v_j‖`；两点写成凸组合后，距离≤顶点对距离的加权和≤最大值 | models/q1q2/PLAN.md:206；models/q1q2/geometry.py:217、428 | R1/R2；[定理/有证明]；必须非空有界凸多面集及完整V，不能拿圆弧样本直接替代 |
| 半径d/2强制圆心 | 取任一最远对A、B，`d>0`。若半径d/2圆覆盖A、B，三角不等式两端同为d，强制圆心`m=(A+B)/2` | models/q1q2/PLAN.md:226；models/q1q2/circle.py:291；`reviews/correctness.md`§一1 | R1/R2；[定理/有证明]；多最远对中点不同直接否定；中点相同仍需检验其它点 |
| 直径圆充要判据 | 等价四项：存在半径d/2覆盖圆；`P⊆D(m,d/2)`；全部顶点满足`(X−A)·(X−B)≤0`；`R(P)=d/2`。恒等式`(X−A)·(X−B)=‖X−m‖²−d²/4` | models/q1q2/PLAN.md:226；models/q1q2/circle.py:291；B2/cases.jsonl `ground_truth.thales_exact/mathematical_cover` | R1/R2；[定理/有证明]；一般紧集须对所有X量化，不能沿用“有限顶点枚举”的说法 |
| 数值判据与未决 | `T=max_V (X−A)·(X−B)≥0`。当前使用精确有理Thales符号；T=0给YES，显著正值给NO，极小正值可保留UNRESOLVED | models/q1q2/circle.py:291；B2/report.json `production_policy/observed_cover_statuses` | R2/R0；[可验证充分条件]；结果针对所构造/导出的数值几何，不是把所有真三角函数做符号化认证；“在容差内”不等于数学等于0 |
| 最小圆与Jung界 | 两点或三点支撑；`d/2≤R≤d/√3`。三点支撑时圆心在其凸包内，最大相邻圆心角≥2π/3，故某弦≥√3R；下界由直径两点 | models/q1q2/PLAN.md:258、296；models/q1q2/circle.py:190、231；文献综述R14/R15 | R1/R2；[定理/有证明]；平面有界非空集合，开集按闭包；三点支撑不是“三条观测足够” |
| κ与η | `κ=2R/d`；`η=2 max_X‖X−m‖/d=sqrt(1+4T/d²)`；`1≤κ≤η≤√3`且`κ≤2/√3`。κ衡量最佳中心膨胀，η衡量固定直径中点膨胀 | models/q1q2/PLAN.md:309；models/q1q2/circle.py:291；`reviews/creativity.md:30`；B2夹具 `ground_truth.kappa/eta` | R1/R2；[定理/有证明]；d=0时均无；添加观测可减小d、R但κ/η不保证单调；中心对称非空有界集κ=1；不是原创几何定理 |
| 清除动作的精确条件 | `E20(K)=∩_{p∈K}D(p,20)`；`E20(K)≠∅ ⇔ R(K)≤20`。统一落点可行集，不仅是一个中心估计 | models/q1q2/PLAN.md:333；models/q1q2/diagnostics.py:46、210；`innov-q12.md:61` | R1/R2；[定理/有证明]；程序未实现精确E20全边界；一个采样圆半径≤20不足以证明真实K可清除 |
| 20m三段判据 | `d≤20√3`：保证存在落点；`20√3<d≤40`：形状相关；`d>40`：不存在。阈值浮点记录`34.64101615137754`；用户要求的展示断点为34.641016、40 | models/q1q2/PLAN.md:333；models/q1q2/circle.py:342；B2夹具 `clearance_jung_equal.input.diameter_m` | R1/R2；[定理/有证明]；在等号上用`20√3`精确符号，不能用34.641016替代；40属于中间段，d≤40不是充分条件 |

### 2.1 反例与基准数值卡

| 对象 | 原始数值（单位m，T为m²） | 精确出处 | 复现；强度；边界 |
|---|---|---|---|
| 理想边长20等边三角形 | `d=20`；`R=20/√3`，夹具closed_form输出`11.547005383792516`；`T=200.0`；`κ=1.1547005383792517`；`η=1.7320508075688772`；d/2=`10`，不能覆盖。题目所需展示半径`11.547005` | B2 `cases.jsonl`，`case_id=equilateral_20`，`closed_form.{diameter,radius,thales_max,kappa,eta}`；models/q1q2/PLAN.md:270；models/q1q2/diagnostics.py:329 | R0/R2；[定理/有证明]（理想构造）；十进制是表达式的机器输出，不是精确实数 |
| 同一夹具的浮点顶点oracle | 顶点`[[0.0,0.0],[20.0,0.0],[10.0,17.32050807568877]]`；`d=20.0`；`R=11.547005383792515`；圆心`[10.0,5.773502691896256]`；`T=199.99999999999994`；`κ=1.1547005383792515`；`η=1.7320508075688772` | 同行 `input.points`、`ground_truth.{diameter,radius,center,thales_max,kappa,eta}` | R0/R2；[实测/统计]（精确有理枚举oracle的浮点导出）；与上一行末位不同是输入/计算语义差别，不能改数抹平；浮点夹具最远对列表只有`[[0,1]]`，不应当作理想三边不等 |
| 三站确能产生该反例 | 令`h=20cot2°`；第一站`[-572.7250656583121,0.0]`读数1°，其余绕三角形中心旋转120°/240°，读数121°/241°，半宽全1°；另两站`[306.36253282915595,-495.9944562442089]`、`[296.36253282915635,513.3149643198975]`；真源`[10.0,5.773502691896257]`；三距`582.7536662088172`、`582.7536662088171`、`582.7536662088172` | B2同行 `input.stations/input.source`；models/q1q2/PLAN.md:270；models/q1q2/diagnostics.py:329；`reviews/correctness.md`§一3 | R0/R2；[定理/有证明]（三锥两侧包含证明）＋[实测/统计]（坐标）；这是合法窄角锥反例，不只是任意三角形；公式不能无条件推广至cot(2ε)变号的角宽 |
| 四站正方形基准 | `D=41.321338`；`R*=20.660669`；`R/D=0.5`；`cover=YES`；`regime=IMPOSSIBLE`；边长`29.21859830750137`。站点`[-1673.4223634107568,0.0]`、`[29.21859830750137,-1673.4223634107568]`、`[1702.6409617182583,29.21859830750137]`、`[0.0,1702.6409617182583]`；读数1°/91°/181°/271°，半宽1° | B2 `report.json` 的 `anchors[0].{diameter,radius,radius_diameter_ratio,cover,regime,stations}`；B2夹具 `case_id=symmetric_four_station_square` 的 `input.square_side` | R0/R2；[实测/统计]，解析对称结构有证明；**纯角锥基准，站点尺度不满足1500m接收范围，不能称物理合法实测场景**；其直径圆可覆盖，却不能20m清除 |
| 四站理想表达式与锚点差异 | 夹具`closed_form.diameter=41.321338000000004`；`input.anchor_expected.diameter=41.321338`；报告测值为上一行`41.321338` | B2同一夹具上述字段及report `anchors[0]` | R0/R2；[实测/统计]；论文结果表取报告锚点，不用公式再算后覆盖归档值 |
| 中间段形状对照 | 边长36等边三角形`d=36.0`、`R=20.784609690826528`，不能20m覆盖；同长线段`d=36`、`R=18`，可覆盖 | B2夹具 `case_id=equilateral_36` 的 `ground_truth.diameter/radius`；models/q1q2/PLAN.md:333；线段为d/2精确推论 | R0/R2；[定理/有证明]；证明d≤40不充分。三角形可构造为合法测向尺度，不借四站不合法距离做物理反例 |

## 3. 模型建立与关键推导：问题2

| 素材条目 | 公式/推导节点 | 代码与证明出处 | 复现；强度；诚实边界 |
|---|---|---|---|
| 完整保收域 | `C_sig=Q∩∩_{p∈F}D(p,max(1000,‖p−S‖))`。固定p取首测合法最小ρ：满足该盘→全部合法ρ均收；违反→取此最小ρ构造第二次no_signal世界 | models/q1q2/PLAN.md:441；models/q1q2/feasible.py:354；`innov-q12.md:33` | R1/R4；[定理/有证明]；“完整”只指保收策略类；`∩D(p,1000)`只是保守子集；未比较允许no_signal的更好策略 |
| 有限边界极值 | 令h=q−S。近支`g_L=sup_{p∈F,r1≤1000}(‖q−p‖²−1000²)`；远支`g_H=‖h‖²−2inf_{p∈F,r1≥1000}h·(p−S)`；均≤0给保收。线段端点、圆弧端点与驻点，含开边界可达极限 | models/q1q2/PLAN.md:457；models/q1q2/feasible.py:293、354；BO/report.json `rows[*].check` | R1/R4；[定理/有证明]（约化）＋[可验证充分条件]（带数值未决的成员接口）；g单位m²；边界完整性不能由采样确认 |
| 凸性与保方向域 | C_sig为闭圆盘交与Q交，闭凸；合法S且F非空时S∈C_sig；任取实际p给有界性。`C_dir=C_sig\∪_{p∈F}D(p,5)`，可非凸 | models/q1q2/PLAN.md:441、481；models/q1q2/feasible.py:307、354 | R1/R4；[定理/有证明]；闭包到q距离>5是充分条件；等于5若仅在排除端点取到，仍可能保证direction，不能一律判OUT；near并非失败 |
| 标准四圆盘精确约化 | S=(0,0)，首测0°、半宽1°，F为未被A裁剪的`5<r≤1500,−1°≤α≤1°`扇环。令`u_±=(cos1°,±sin1°)`：`C_sig=∩_{r∈{5,1000},σ∈{−,+}}D(ru_σ,1000)`（动作界此处不活跃） | models/q1q2/PLAN.md:518；`reviews/creativity.md:261`、`innov-q12.md:49`；models/q1q2/feasible.py:354通用器；models/q1q2/benchmarks/q2_outer/run.py:138；models/q1q2/optional/outer_exclusion.py:77 | R1/R4；[定理/有证明]；不是任意裁剪首测都只有四盘；一般形式需0<a<r0≤rmax、半角<90° |
| 四盘证明链 | 必要性：角端点、r=1000及r→5极限；充分性：远端两盘约束使qx≥0→最小角投影在端点→近支距离平方关于r凸，仅查5/1000→远支平方相消后随r变得更宽松 | 同上；models/q1q2/PLAN.md:518；models/q1q2/optional/outer_exclusion.py:77 | R1/R4；[定理/有证明]；r=5中心是约束极限，不是允许产生direction的实际源；rmax超过1000不再影响Csig，但继续影响F、J |
| 标准外包框与对称性 | `C_sig⊆[0,1005]×[−1000,1000]`；反射y保持F、Csig和J。外层认证根盒`[0,1005]×[0,1000]` | models/q1q2/benchmarks/q2_outer/run.py:28；models/q1q2/optional/outer_exclusion.py:21、181；BO/exclusion/certificate.json `root/reflected_y` | R0/R6；[定理/有证明]；反射只用于标准对称模型；上半平面证书必须连同反射说明才覆盖全域 |
| 共同反馈点对公式 | `J(q)=sup{‖x−y‖:x,y∈F且共享第二反馈}`。near：两点距q均≤5；direction：两点距q均>5且最短夹角ψ≤2ε₂；取两分支并集的上确界 | models/q1q2/PLAN.md:560；models/q1q2/q2.py:367、455；models/q1q2/optional/certified.py:49；`innov-q12.md:85` | R1/R3；[定理/有证明]；两个可能世界，不是两个同时存在的同频道源；不可near/direction混配；q∈Csig且q≠S；一般上确界未必取得 |
| 点积/叉积与多项式 | a=x−q，b=y−q，δ=2ε₂，w=a·b。direction相容：`w≥0`且`∣cross(a,b)∣≤tanδ·w`；等价`w²−cos²δ‖a‖²‖b‖²≥0`并保留w≥0 | models/q1q2/PLAN.md:582；models/q1q2/q2.py:455；models/q1q2/optional/certified.py:49；models/q1q2/optional/outer_exclusion.py:37 | R1/R3/R6；[定理/有证明]；当前认证0<ε₂<45°；平方式删w≥0会接纳反向点对；数值等价式的区间紧度可不同 |
| 同点重复 | `q=S ⇒ J(S)=diam(F)`，重复固定读数不缩角锥；不用一般独立第二误差的点对式 | models/q1q2/PLAN.md:608；models/q1q2/q2.py:455；models/q1q2/optional/certified.py:49 | R1/R3（将q置S）；[定理/有证明]；不推出任意小的异点移动都连续逼近同点目标；禁止套无依据全局Lipschitz常数 |
| 直径目标与清除目标 | 同一域上`J(q)/2≤J_R(q)≤J(q)/√3`；若真正全局最小化J，则`J_R(q*)≤(2/√3)inf J_R`；若仅有目标误差δ，则增添`δ/√3`项 | models/q1q2/PLAN.md:658；`innov-q12.md:306`；models/q1q2/diagnostics.py:222 | R1；[定理/有证明]；认证推荐点仅0.01m目标差，不能称取得精确最优点或直接套无加性项比值；本题未求全部共同反馈三点组 |
| 长点对阈值解释 | `J(q)≤τ`等价于所有距离>τ的候选源对均不能共享反馈；固定长对的“仍相容检测点集”可作外层下界证据 | models/q1q2/PLAN.md:682；`reviews/creativity.md:187`；models/q1q2/optional/outer_exclusion.py:37、47 | R1/R6；[定理/有证明]；原始J无需凸；这是量词重写，不自动给多项式时间全局算法 |

### 3.1 预算不可辨识下界与临界裕度

| 素材条目 | 精确公式/条件 | 出处与复现 | 强度、边界 |
|---|---|---|---|
| 旧短基线界 | 同射线真实候选点x=S+au、y=S+bu，`5<a<b`、`B<a−5`；若`asin(B/a)+asin(B/b)≤2ε₂`，则所有预算内保收q有`J(q)≥b−a`，即`V(B)≥b−a` | models/q1q2/PLAN.md:608；models/q1q2/q2.py:572；R1/R5 | [定理/有证明]；须x,y真实属于F、预算域非空；角偏转相加通常不紧；旧API普通浮点，不是自动认证角判据 |
| 10m不可辨识实例 | `a=500,b=1500,B=10,ε₂=1°`；旧API角界`1.5279666912869418°≤2°`；下界`1000`m | `review-opt/verify-q12-data/budget-independent.json` 的 `table` 中B=10记录；最新 `review-opt/q12-budget-rounding/budget-bounds.json` 的 `results` 中 `budget_m=10` 的 `old/new.lower_bound_m`；models/q1q2/q2.py:572、627；R0/R5 | [定理/有证明]（有明显裕度的实例）；至少1000，不是恰好1000；不表示预算内不存在保收点 |
| 新的精确同射线最大角 | `Ψ(a,b,B)=atan[B(b−a)/sqrt((a²−B²)(b²−B²))]`，`0≤B<a<b`。固定圆周半径r时极值横坐标`t=(a+b)r²/(ab+r²)`，最大角随r不减，取r=B | `review-opt/innov-q12.md:223`；models/q1q2/q2.py:590、615；R1/R5 | [定理/有证明]；精确的是无约束预算圆盘内两固定源的最大夹角，不是完整minimax V(B) |
| 新下界的使用 | 在旧几何前提下以`Ψ≤2ε₂`代替旧角界；`B≤26.15`时仍至少保留1000m最坏歧义；B=26.15的当前角上界`1.9999420457645092°` | models/q1q2/q2.py:627；舍入补丁§临界行为；`threshold-comparison.json` 中budget=26.15 的 `new_angle_upper/new_trigger/lower_bound_m`；R0/R5 | [定理/有证明]（实例）＋[可验证充分条件]（当前角API）；未触发不代表能定位；26.15是有裕度的保证预算，不是全局任务可行性的临界距离 |
| 旧/新数学临界值 | 是两条角条件各自取等的根；原始高精度字符串见下表。新阈值的显示小数转binary64可能跨到不安全一侧 | `review-opt/verify-q12-data/budget-independent.json` 的 `old_threshold/new_threshold`；R0/R5 | [实测/统计]（高精度数值根），公式本身[定理/有证明]；这些点估计不是区间根证书；保证仍使用26.15m |
| 非共线推广 | 给定真实x,y，r_x=‖x−S‖、r_y=‖y−S‖、初始最短角γ；`B<min(r_x,r_y)−5`且`γ+asin(B/r_x)+asin(B/r_y)≤2ε₂ ⇒ V(B)≥‖x−y‖` | `innov-q12.md:200`；models/q1q2/q2.py:656；R1/R5；独立记录 `budget-independent.json.noncollinear` | [定理/有证明]；API仍普通浮点；只检查传入一对，不优化全部点对包络；多次测量推广须整条路径都在预算圆内，不能只限制每一步 |

| API | 当前数值合同 | 自动触发保证的资格 | 代码、复现与强度 |
|---|---|---|---|
| `same_ray_max_angle_deg` | 精确binary64输入；局部50位`MPIntervalContext`；区间π、sqrt、atan2；右端点转float后`nextafter(+∞)`；B=0精确返回0 | 给同射线角条件的保守上界；依赖mpmath.iv包含合同 | models/q1q2/q2.py:590；R5；[可验证充分条件]；非形式化验证库，缺mpmath不降级为快速估计 |
| `same_ray_max_angle_estimate_deg` | 普通binary64快速估计，可能低估角度 | 无；不得用于严格下界触发 | models/q1q2/q2.py:614；R5；[启发式无保证] |
| `tight_short_baseline_lower_bound` | 调用认证角上界，仅`angle_upper≤2*half_width_deg`通过；允许半宽[0,90]内乘2精确 | 角条件具保守性；其余源成员、near前置条件和返回距离沿用现有数值语义 | models/q1q2/q2.py:627；R5；[可验证充分条件]；不是完整几何链认证 |
| `short_baseline_lower_bound` / `source_pair_budget_lower_bound` | 旧arcsin相加/非共线推广；普通浮点 | 有数学充分条件，但API未整体改造成向外舍入认证器 | models/q1q2/q2.py:572、656；R5；[定理/有证明]（公式），实现临界处不能升格 |

### 3.2 临界角判定原始精度表

数据文件：`review-opt/q12-budget-rounding/threshold-comparison.json`。下表逐行对应数组索引0—6；字段依次为`budget/old_angle/old_trigger/new_angle_upper/new_trigger/lower_bound_m`。这里的old指**修复前的同射线快速公式**，不是旧的两个arcsin相加界。复现R0/R5；[实测/统计]（归档对照）＋[可验证充分条件]（新角上界）；false只表示本充分条件未触发。

| 预算binary64/m | 改前快速角/° | 改前触发 | 当前向外角上界/° | 当前触发 | 当前下界/m |
|---:|---:|---|---:|---|---:|
| `10.0` | `0.7640682458261854` | `true` | `0.7640682458261855` | `true` | `1000` |
| `26.15` | `1.9999420457645092` | `true` | `1.9999420457645092` | `true` | `1000` |
| `26.150756085730233` | `1.9999999999999234` | `true` | `1.9999999999999236` | `true` | `1000` |
| `26.150756085731228` | `1.9999999999999996` | `true` | `1.9999999999999998` | `true` | `1000` |
| `26.15075608573123` | `2.0` | `true` | `2.0000000000000004` | `false` | `null` |
| `26.150756085731235` | `2.0000000000000004` | `false` | `2.0000000000000004` | `false` | `null` |
| `26.15075608573223` | `2.0000000000000764` | `false` | `2.000000000000077` | `false` | `null` |

临界反例输入：`budget_hex=0x1.a2697f369e37cp+4`；`oracle_strictly_above_two=true`。100位独立角区间原字段`[4].oracle_interval`如下；复现R0，当前API复算R5：

```text
[2.00000000000000000193177267704169471852609062639016315127538332034445122615946278667332816590058936557057, 2.00000000000000000193177267704169471852609062639016315127538332034445122615946278667332816590058936577059]
```

| 临界根 | 归档高精度原始字符串 |
|---|---|
| 旧arcsin相加角条件 | `13.08880635142371211063543624799851472134323535368448819882067054197545632061440688320369068273761952` |
| 新同射线精确最大角条件 | `26.15075608573123131217441560989549761309895188762295393731829563478234669185124123119966917719835695` |

出处：`review-opt/verify-q12-data/budget-independent.json.old_threshold/new_threshold`；R0/R5；[实测/统计]（数值根）。不将字符串等同于向外包含区间。

## 4. 结果数值卡：推荐点、对照点与外层最优值

本节统一输入：`S=(0.0,0.0)`，首读`0.0°`，两次连续角半宽`1.0°`，物理常数见§1。原始固定点数据均来自`models/q1q2/benchmarks/q2_outer/report.json`（下称本节报告）；推荐点为`rows[0]`，对照为`rows[1]`。q*沿用推荐点记号，**坐标本身不宣称精确全局极小点**。

### 4.1 固定点J：原始浮点区间与向外展示区间

| 字段/量 | 推荐点rows[0] | 对照rows[1] | 出处、复现、强度、边界 |
|---|---:|---:|---|
| 推荐坐标 | `[843.035666,545.527004]` | `[750.0,400.0]` | 本节报告`rows[i].q`；R7；[实测/统计]，标准输入下有限搜索所得坐标 |
| 合法点对评分J_hat/m | `110.96932009598744` | `147.27202039123162` | 本节报告`rows[i].score.J_hat`；R7；[启发式无保证]，采样/局部细化不提供连续上界 |
| 固定点L/m | `110.96913484045108` | `147.27160958841893` | 本节报告`rows[i].certificate.lower_m`；R3；[可验证充分条件]，合法点对区间下界 |
| 固定点U/m | `110.97010129273485` | `147.27245694641758` | 本节报告`rows[i].certificate.upper_m`；R3；[可验证充分条件]，全部源点对盒区间上界 |
| 固定点gap/m | `0.0009664522837766755` | `0.0008473579986514325` | 本节报告`rows[i].certificate.gap_m`；R3；[可验证充分条件]，inspect converged |
| 证书状态 | `"CERTIFIED_FIXED_Q_TOL"` | `"CERTIFIED_FIXED_Q_TOL"` | 本节报告`rows[i].certificate.status`；R3；[可验证充分条件]，不是外层最优状态 |
| 达指定容差 | `true` | `true` | 本节报告`rows[i].certificate.converged`；R3；[可验证充分条件]，tol=0.001 |
| 节点数 | `2144` | `1432` | 本节报告`rows[i].certificate.nodes`；R3；[实测/统计]，同版本与参数；不承诺跨版本不变 |
| 活盒数 | `183` | `173` | 本节报告`rows[i].certificate.active_boxes`；R3；[实测/统计]，终止时保留的上界证据 |
| 区间精度 | `30` | `30` | 本节报告`rows[i].certificate.dps`；R3；[实测/统计]，mpmath.iv参数，非正确小数位数 |
| 六位向外展示区间/m | **[110.969134,110.970102]** | **[147.271609,147.272457]** | `models/q1q2/benchmarks/q2_outer/paper-results.md`固定点结果表；R0原值/R3重算；[可验证充分条件]，已有展示值，不用普通四舍五入替代 |

对照改进的报告原值：`lower_improvement_m=36.30150829568407`。来源为对照L减推荐U的普通float计算；不是独立外层下界。向下保守展示“至少36.301508m”可由两证书支持。R0/R3；[可验证充分条件]（区间分离），不能称所有场景均改进此值。

### 4.2 保收成员证据：不能只看浮点IN

四盘顺序固定为`5u_−,5u_+,1000u_−,1000u_+`，半径均1000。平方残差为`‖q−c‖²−1000²`；四个区间上端都严格<0，支持最终6位推荐坐标确在Csig内。复现R4；[可验证充分条件]（区间残差）/普通裕度列[实测/统计]。最小裕度不适合随意改写坐标。

| 字段 | 推荐点rows[0] | 对照rows[1] |
|---|---|---|
| `four_disk_distance_margins_m` | `[9.422302241546276e-06,0.09522154583680731,415.589331835518,449.13450545603246]` | `[154.36653808397796,154.44909516896735,513.4916419883004,543.090236353406]` |
| `four_disk_squared_residual_intervals_m2` | `[[-0.01884460452155901,-0.018844604521559002],[-190.43402453095337,-190.4340245309533],[-658464.1709355438,-658464.1709355436],[-696547.2069208302,-696547.20692083]]` | `[[-284904.04808792385,-284904.04808792373],[-285043.6673394221,-285043.667339422],[-763309.6175847601,-763309.6175847598],[-791233.4678844138,-791233.4678844135]]` |

数据出处：本节报告`rows[i].four_disk_distance_margins_m/four_disk_squared_residual_intervals_m2`；代码`models/q1q2/benchmarks/q2_outer/run.py:138`。一般`check.status=IN`本身为浮点成员检查，不等于以上区间复核；本例同时有两种证据。

### 4.3 代表反馈、清除诊断、行动代价

以下**均条件于各自评分见证构造的一个共同反馈**；不是所有反馈的最坏覆盖半径。复现R7/R0；具体反馈与见证[实测/统计]，清除外包[可验证充分条件]（带浮点外包合同），最坏反馈推广无。

| 字段/单位 | 推荐点rows[0] | 对照rows[1] |
|---|---|---|
| `rows[i].score.witness.x` | `[1401.027300892688,24.455022503287303]` | `[1361.2249574740094,23.760270014619056]` |
| `rows[i].score.witness.y` | `[1499.771542734586,-26.17860965592525]` | `[1499.771542734586,-26.17860965592525]` |
| `rows[i].score.witness.common_bearing_deg` | `317.95958369651805` | `329.38561112649506` |
| `rows[i].clearance.R_hat` | `55.48466004799372` | `73.6360101956158` |
| `rows[i].clearance.estimated_center` | `[1450.399421813637,-0.8617935763189735]` | `[1430.4982501042978,-1.2091698206530967]` |
| `rows[i].clearance.r_U` | `55.484660078584696` | `73.63601022627402` |
| `rows[i].clearance.cover_center` | `[1450.399421813659,-0.861793576322718]` | `[1430.4982501043391,-1.209169820657884]` |
| `rows[i].clearance.H_U` | `870.7177042700454` | `862.4300398732481` |
| `rows[i].clearance.status` | `"NOT_YET_GUARANTEED"` | `"NOT_YET_GUARANTEED"` |
| `rows[i].clearance.evidence` | `"impossible_pair"` | `"impossible_pair"` |
| `rows[i].outer_diameter_m` | `110.96932009636919` | `147.27202039174782` |
| `rows[i].all_feedback_radius_upper_Jung_m` | `64.06861785336051` | `85.02779266223176` |
| `rows[i].movement_m` | `1004.1458291708827` | `850.0` |
| `rows[i].movement_seconds` | `200.82916583417654` | `170.0` |
| `rows[i].movement_and_detection_seconds` | `205.82916583417654` | `175.0` |

出处：本节报告上述字段；`models/q1q2/diagnostics.py:46`、`models/q1q2/feasible.py:436`、models/q1q2/benchmarks/q2_outer/run.py:130。长度m、角degree、时间s；移动时间按5m/s，另一次检测5s，仅第二次检测的移动＋检测成本，不含整局清除。`all_feedback_radius_upper_Jung_m`是证书U除以普通`math.sqrt(3)`所得展示量；数学上J_R≤U/√3成立，但这些float小数未经新的向外舍入，不另称认证端点。

清除解释卡：两点均有合法代表反馈下的`impossible_pair`，且固定点J的L>40，说明**至少一个反馈无法由统一20m落点覆盖**；不表示每个反馈都不能清除。仅`r_U>20`本身不能作不可能性证明。推荐点J更小，同时其移动距离更长；不推出其总任务时间更短。

### 4.4 固定点下界见证的区间来源

| 固定点 | witness.parameters | witness.branch | witness.coordinate_enclosures |
|---|---|---|---|
| `[843.035666,545.527004]` | `[-1.0,0.9999995231628418,1.0,0.9339399337768555]` | `"direction"` | `[[[1499.7708299716087,1499.7708299716091],[-26.178597214601215,-26.178597214601208]],[[1401.0267853267276,1401.026785326728],[24.45501350404999,24.455013504049997]]]` |
| `[750.0,400.0]` | `[-1.0,0.9999995231628418,1.0,0.9073123931884766]` | `"direction"` | `[[[1499.7708299716087,1499.7708299716091],[-26.178597214601215,-26.178597214601208]],[[1361.2246751246914,1361.2246751246919],[23.76026508619338,23.76026508619339]]]` |

出处：本节报告`rows[i].certificate.witness`；R3；[可验证充分条件]。这组区间合法点对与`score.witness`的局部细化点对不同，二者不可拼成一个见证。坐标区间是已验证参数点的计算外包，不表示里面任取两个坐标都是真实源。

### 4.5 外层标准场景认证：最终数值

| 量 | 原始精度 | 精确出处与复现；强度、边界 |
|---|---|---|
| `model` | `"standard-S0-theta0-eps1-rho1000-1500-near5-arena1800-v1"` | `models/q1q2/benchmarks/q2_outer/exclusion/certificate.json.model`；R0/R6；[可验证充分条件]（模型/算法配置是合同信息）；限本标准场景 |
| `root` | `["0","1005","0","1000"]` | `models/q1q2/benchmarks/q2_outer/exclusion/certificate.json.root`；R0/R6；[可验证充分条件]（模型/算法配置是合同信息）；限本标准场景 |
| `reflected_y` | `true` | `models/q1q2/benchmarks/q2_outer/exclusion/certificate.json.reflected_y`；R0/R6；[可验证充分条件]（模型/算法配置是合同信息）；限本标准场景 |
| `tau` | `"1/100"` | `models/q1q2/benchmarks/q2_outer/exclusion/certificate.json.tau`；R0/R6；[可验证充分条件]（模型/算法配置是合同信息）；限本标准场景 |
| `k` | `"5032613263056833/144115188075855872"` | `models/q1q2/benchmarks/q2_outer/exclusion/certificate.json.k`；R0/R6；[可验证充分条件]（模型/算法配置是合同信息）；限本标准场景 |
| `target` | `"6100096079528237/54975581388800"` | `models/q1q2/benchmarks/q2_outer/exclusion/certificate.json.target`；R0/R6；[可验证充分条件]（模型/算法配置是合同信息）；限本标准场景 |
| `lower` | `"6100096079528237/54975581388800"` | `models/q1q2/benchmarks/q2_outer/exclusion/certificate.json.lower`；R0/R6；[可验证充分条件]（模型/算法配置是合同信息）；限本标准场景 |
| `upper` | `"244025833413685/2199023255552"` | `models/q1q2/benchmarks/q2_outer/exclusion/certificate.json.upper`；R0/R6；[可验证充分条件]（模型/算法配置是合同信息）；限本标准场景 |
| `gap` | `"1/100"` | `models/q1q2/benchmarks/q2_outer/exclusion/certificate.json.gap`；R0/R6；[可验证充分条件]（模型/算法配置是合同信息）；限本标准场景 |
| `converged` | `true` | `models/q1q2/benchmarks/q2_outer/exclusion/certificate.json.converged`；R0/R6；[可验证充分条件]（模型/算法配置是合同信息）；限本标准场景 |
| `status` | `"CERTIFIED_OUTER_TAU"` | `models/q1q2/benchmarks/q2_outer/exclusion/certificate.json.status`；R0/R6；[可验证充分条件]（模型/算法配置是合同信息）；限本标准场景 |
| `nodes` | `5319` | `models/q1q2/benchmarks/q2_outer/exclusion/certificate.json.nodes`；R0/R6；[可验证充分条件]（模型/算法配置是合同信息）；限本标准场景 |
| `pending` | `0` | `models/q1q2/benchmarks/q2_outer/exclusion/certificate.json.pending`；R0/R6；[可验证充分条件]（模型/算法配置是合同信息）；限本标准场景 |
| 精确下端十进制展开 | `110.96010129273485290468670427799224853515625` | 同certificate.lower的Fraction精确展开；`review-opt/verify-q12.md`§5.3；R0/R6；[可验证充分条件] |
| 精确上端十进制展开 | `110.97010129273485290468670427799224853515625` | 同certificate.upper的Fraction精确展开；同上 |
| 对外展示 | **110.960101≤J*≤110.970102**，精确gap **0.01m** | `exclusion/verification.json.display_lower/display_upper/gap`；R0/R6；[可验证充分条件] |
| 展示端点相减 | `0.010001` | `exclusion/verification.json.display_gap`；不是精确证书gap，不能将它“修正”为0.01 |

上下界的量词：下界覆盖所有标准保收q（原地可一并被下界覆盖），上界来自固定可行q_rec。故推荐点目标值至多比inf高0.01m；不证明坐标为唯一/精确最优，不给坐标误差。采用J*记号不要求先证明去掉S后的inf取得。证书范围由`model`、`root`和反射合同共同限定。


## 5. 求解方案与认证推导

### 5.1 从数学问题到生产候选

| 环节 | 当前做法/参数 | 出处、复现 | 强度与边界 |
|---|---|---|---|
| Q1半平面谓词 | 十进制度数80位三角近似→有理行；候选交点先整数齐次`(X,Y,D)`，D统一正号，成员用`aX+bY≤cD`；仅通过点导出Fraction | models/q1q2/geometry.py:139、310、333；`q12-production-paper-patch.md`；R2 | [可验证充分条件]（相对于近似有理行的精确检查）；仍O(M³)算术操作，另计整数位长；`10^-70`保护带不是额外物理角误差 |
| Q1直径与MEC | 全点对比较；二进制分母坐标可统一到整数分母；一般Fraction保留原路。浮点Welzl只提议支撑，原坐标精确包含/圆心在支撑凸包内复核，失败转精确后备；Q1仅算一次MEC | models/q1q2/geometry.py:217；models/q1q2/circle.py:139、190、207、231；models/q1q2/q1.py:22；R2 | [实测/统计]（实现合同）；直径O(V²)，不是卡壳；枚举后备O(V⁴)且有80点限额；不是全链O(V) |
| 通用候选检查 | 对完整线段/圆弧边界极值检查Csig；可行域径向边界用于提议点，最终仍用原成员检查 | models/q1q2/feasible.py:293、354；models/q1q2/q2.py:682、699、779；R4/R7 | [可验证充分条件]；浮点边界允许UNRESOLVED，不能按“疑似IN”进入有保证候选 |
| 默认外层搜索 | 站点步长`(50.0,25.0)`；源网格`((9,25),(17,49),(33,97))`；12起点；局部最小步长`1.5625`；点对细化8起点/8轮；默认180s；分块256；边界步进5° | models/q1q2/q2.py:16、814；R7 | [启发式无保证]；参数是默认，不是推荐点BO最终统一复评参数；时间预算是工程退出，不保证全局最优 |
| 终选公平复评 | 保留各级基础/边界/near补点，汇集候选点对见证；公共集合冻结后比J；错位网格、容差对照、局部点对细化纳入审计；审计代际变化时旧稳定性失效 | models/q1q2/q2.py:271、455、814；models/q1q2/benchmarks/q2_outer/run.py:98；R7 | [启发式无保证]＋[实测/统计]；J_hat是找到的合法点对下界近似，有限变动范围不是误差上界；不能把未完成审计当稳定 |
| 标准归档强化 | 搜索时间14400.0s、tie_floor=0.0、tie_multiplier=0.0；最终网格`((17,49),(33,97),(65,193))`；共享样本14289；两点完全同口径复评 | BO/report.json `config/common_samples/interval_options`；models/q1q2/benchmarks/q2_outer/run.py:13、98；R0/R7 | [实测/统计]；不是全部候选站或全部反馈遍历；样本相同只改善比较公平性 |

### 5.2 固定点区间认证：包含合同

| 必须保留的证明义务 | 具体机制 | 依据与复现 | 强度/边界 |
|---|---|---|---|
| 独立输入与参数域覆盖 | IC从原始首测/物理字段独立构造源的角α、径向插值t；两个源共4维根盒覆盖全部真实候选点对；包括near/direction/same_station分支 | models/q1q2/optional/certified.py:49；B4/README.md认证说明；R3 | [可验证充分条件]；不复用生产源采样作上界；原始float按精确二进制值，与生产十进制度三角近似语义不同 |
| 合法下界 | 仅在源成员、径向非空、严格r>5、共同反馈均验证后接受实际点对；距离区间下端向下导出 | models/q1q2/optional/certified.py:49；BO/report.json `rows[*].certificate.witness`；R3 | [可验证充分条件]；闭包极限不能冒充达到的direction见证；一个可行见证只给下界 |
| 全域上界 | 区间距离上端控制整盒；只排除已证不含合法点对的盒；保留活盒、继承父上界；全局U覆盖所有未排除部分 | models/q1q2/optional/certified.py:49；R3 | [可验证充分条件]；中心不合法不代表盒不合法；自然区间过宽影响效率，不允许为收敛删除未证盒 |
| 向外舍入 | 局部mpmath.iv上下文；`_down/_up`对最终float用nextafter向±∞；输入、sin/cos/π、根式和约束均依赖后端区间包含 | models/q1q2/optional/certified.py:25、29、49；R3 | [可验证充分条件]；不是“算更多小数自然精确”；mpmath.iv不是形式化证明系统 |
| 退出与判级 | 保持`L≤J(q)≤U`；只有gap达tol才`converged=true`；时间/节点用尽返回宽界与明确状态；`assess`的PASS和小gap分开 | models/q1q2/optional/certified.py:34、49、235；R3 | [可验证充分条件]；预算耗尽不等于失败案例的生产bug，也不等于已收敛；固定q函数本身不认证q∈Csig |

### 5.3 外层认证：凸二次盒下界＋圆盘排除

目标合同：对标准Csig全部q给共同下界L；取已验证推荐点固定q上界U；得`L≤J*≤J(q_rec)≤U`。**凸的是每个固定点对的辅助二次式，不是J。**

| 步骤 | 公式与必要核验 | 依据与复现 | 强度与边界 |
|---|---|---|---|
| 上界与精确目标 | q_rec四盘残差区间均<0，先获得固定点U；`τ=Fraction('0.01')`，目标`L=U−τ`全程Fraction，不用float减法 | models/q1q2/optional/outer_exclusion.py:77、181；BO/exclusion/certificate.json `tau/target/lower/upper/gap`；R6 | [可验证充分条件]；旧原型`0.010000000000005118`已被精确有理差替代；τ不是显示端点差 |
| 点对约束改写 | 对真实固定源x,y，`w(q)=‖q‖²−(x+y)·q+x·y`；`z(q)=cross(x,y)+q_x(x_y−y_y)+q_y(y_x−x_x)`；选`0<k<tan2°` | models/q1q2/optional/outer_exclusion.py:37、47；BO/EXCLUSION.md；R1/R6 | [定理/有证明]；k从较小有理数验证，不能把近似tan略偏大的值当安全阈值 |
| 整盒保留歧义 | 对站点矩形B，验证`min_B w≥0`、`min_B(kw−z)≥0`、`min_B(kw+z)≥0`，两源到B的最小距离平方均>25，且`‖x−y‖²≥L²`；则整个B都有J≥L | models/q1q2/optional/outer_exclusion.py:47；R1/R6 | [定理/有证明]＋[可验证充分条件]；必须整盒成立，不能只检查盒中心；direction必须严格>5 |
| 可分凸二次的精确最小值 | 每式形如`k(qx²+qy²)+bx qx+by qy+c`，k>0；每坐标最小点为`clip(−b_i/(2k),[l_i,u_i])`，Fraction精确比较；不需求解非凸J | models/q1q2/optional/outer_exclusion.py:26；独立checker `check_exclusion.py:30`采用另一种完成平方表达；R6 | [定理/有证明]；公式仅适用于该可分二次，不能迁移成J的凸性证明 |
| 四盘排除站点盒 | 盒到某个必需圆盘中心的最小距离平方区间下端>1000²→整盒不在Csig，可排除 | models/q1q2/optional/outer_exclusion.py:77；models/q1q2/benchmarks/q2_outer/check_exclusion.py:25、61；R6 | [可验证充分条件]；检查的是盒最近点，中心在盘外不足以排除 |
| 提议与证据分离 | 浮点静态源库、旋转接触与缩短点对用于找提议；接纳前用区间确认实际源合法，并以精确Fraction验整盒；最长边二分，共享精确中点 | models/q1q2/optional/outer_exclusion.py:119、58、181；R6 | [启发式无保证]（提议效率）＋[可验证充分条件]（接纳证据）；提议遗漏只使不收敛，不能虚构下界 |
| 全域覆盖与独立复核 | 根盒面积`1005000`；叶盒精确分割覆盖；disk叶排除可行性、pair叶给下界；独立checker不用搜索谓词；反射补下半域 | models/q1q2/benchmarks/q2_outer/check_exclusion.py:35、61；BO/exclusion/verification.json `area_exact/leaves/counts/x_slabs`；R6 | [可验证充分条件]；仅面积相等还不够，须边界、无空洞/重叠覆盖检查；上下半对称不能用于一般首测 |
| 预算未完成 | pending叶下界取0；节点预算9的归档为2个disk叶、6个pending，返回下界0、`converged=false` | BO/exclusion/budget/certificate.json、verification.json 的 `lower/converged/counts`；R0/R6（max_nodes=9） | [可验证充分条件]；有有效宽区间不代表达0.01m；不得忽略pending后宣称全域排除完成 |

## 6. 验证与证据：作者能据此写到哪一步

| 证据块 | 归档精确结果 | 数据出处、复现入口 | 强度与不可推出项 |
|---|---|---|---|
| Q1几何 | **285/285**，n_fail=0 | `models/q1q2/benchmarks/q1_geometry/report.json` 的 `n_cases/n_pass/n_fail`；最新复验同值见 `review-opt/q12-budget-rounding/benchmarks-summary.json.q1_geometry`；R0/R8 | [实测/统计]；解析分类、独立原始角判定、顶点完整性/变换等证据；不是无限输入正确性的穷尽证明 |
| Q1圆覆盖 | **330/330**，n_fail=0 | B2/report.json `n_cases/n_pass/n_fail`；最新摘要 `.q1_circle_cover`；R0/R8 | [实测/统计]；oracle有精确Fraction枚举与闭式；尺度极限可能允许NUMERICAL_UNRESOLVED，通过不等于330项全部输出确定数值 |
| Q2候选域 | **531/531**，n_fail=0 | B3/report.json `n_cases/n_pass/n_fail`；最新摘要 `.q2_candidate`；R0/R8 | [实测/统计]；边界、开端点、状态、实际见证及不变量；密集采样检查是辅证，不证明连续保收 |
| Q2最坏直径 | **48/48**，n_fail=0；`grade_counts={models/q1q2/adapters.py:0,B:0,models/q1q2/circle.py:40}`，另8项非J合同 | B4/report.json `n_cases/n_pass/n_fail/grade_counts/n_grade_not_applicable/certification.enabled`；R0/R8 | [实测/统计]；本报告`certification.enabled=false`，不可将48/48叫48个连续认证；闭式验收容差不是认证误差界 |
| 可选固定点认证专组 | **7/7**，n_fail=0 | B4/report-certified.json `n_cases/n_pass/n_fail`；各 `results[*].actual.certification`；R0/R8 | [实测/统计]；认证方法另依赖包含合同；PASS仍需看converged/gap。类别可重叠，不能把类别计数相加 |
| 新增预算benchmark | **16/16** | `review-opt/q12-budget-rounding/budget-bounds.json.n_cases/n_pass`；B4/run_budget_bounds.py:18；R0/R8 | [实测/统计]；独立极值站点直接方位角检查；不替代100位区间临界回归 |
| 最新本地测试 | **1311 passed in 7.91s**；相对1290增加21项舍入回归 | `review-opt/q12-budget-rounding/tests.log:20`；舍入补丁§验证入口；R9 | [实测/统计]；归档本地测试，不是官方模拟器正式测试或官方评分；本次未重跑，7.91s不是可移植性能承诺 |
| 外层原证书独立检查 | `valid=true`，`complete=true`；2660叶＝862disk＋1798pair；650个x分片；866实际源；精确覆盖面积1005000 | BO/exclusion/verification.json `valid/complete/leaves/counts/x_slabs/verified_source_points/area_exact`；R0/R6 | [可验证充分条件]；包含性依赖60位mpmath.iv合同＋Fraction检查，非形式化验证 |
| 外层再次独立审计 | archived/fresh均valid；866源，696横向分片；50dps固定点再次得到原上下界、2144节点 | `review-opt/verify-q12-data/outer-independent.json` 的 `archived/fresh/fresh_fixed_50dps`；R0，生成该独立审计全部旧字段的单一入口：无；固定点R3改dps=50可重算 | [实测/统计]＋[可验证充分条件]；696横分片与650竖分片不冲突；不可称两个checker逐项用了同一算法 |
| P3合同清理 | Q1有顶点仅1次MEC、无顶点0次；零预算评分1次；frontier共享评分只记一次；JSON不泄漏内部精确字段 | `models/q1q2/reviews/p3-cleanup/contracts.json`、`verify_contracts.py:1`；R0/R1 | [实测/统计]；是调用/序列化/账本合同，不是新的几何定理；旧1172不计入1311之外 |

### 6.1 可信度层级与区间方向检查表

| 对象 | 下界证据 | 上界证据 | 不能混写 |
|---|---|---|---|
| 固定q的J | 实际合法共同反馈点对；区间距离下端 | 覆盖全部源点对参数盒的区间上端 | J_hat不是上界；局部极大不是连续全局最大 |
| 外层J* | 覆盖全部可行q的整盒pair证据 | 一个已证可行q的固定点J上界 | 某点J下界不等于全域下界；推荐坐标不等于唯一精确最优坐标 |
| 后验R(K) | 实际两点/三点的最小圆半径 | 包含K的外包U及与半径配对的圆心 | 采样R_hat≤20不足以清除；外包r_U>20不足以否定存在落点 |
| 预算V(B) | 对全部预算内q均相容的一对真实源 | 本任务未提供V(B)精确全局上界曲线 | 下界没触发≠可达到小歧义；完整圆盘角极值≠预算minimax值 |

本表是前述命题/包含合同的方向索引，来源models/q1q2/PLAN.md:333、560、608、658，models/q1q2/optional/certified.py:49、models/q1q2/optional/outer_exclusion.py:47、181、models/q1q2/diagnostics.py:46；复现R1/R3/R5/R6；强度随对应证据，不另构成一轮实验。

## 7. 设计巧思与取舍

| 不显然的决策 | 为什么采用；否掉/保留的替代方案 | 证据位置与复现 | 强度、边界与写作价值 |
|---|---|---|---|
| Q1纯角锥与Q2物理集分开 | 回答直径圆题问保留纯几何P；物理半径/near另建F，避免用物理裁剪悄悄改变Q1对象 | models/q1q2/PLAN.md:149、380；models/q1q2/q1.py:22、models/q1q2/feasible.py:259；R1/R2 | [定理/有证明]；解释四站基准与物理合法例为何不能混用 |
| 拒绝大方框替代无界证明 | 图窗内总有有限多边形，会掩盖真实无界；改用可行性＋衰退方向见证 | models/q1q2/geometry.py:333；models/q1q2/PLAN.md:165；R1/R2 | [定理/有证明]；“近乎平行”不等于平行，不用经验sin阈值截掉远顶点 |
| 保留精确谓词，优化算术表示 | 否掉删除Fraction回到浮点HPI/卡壳的快捷替换；改用整数齐次交点、二进制共同分母快路径 | models/q1q2/geometry.py:217、310；`opt-q12.md:163/190`、实现补丁；R1/R2 | [可验证充分条件]（等价运算）；优化算术常数，不改变O(M³)/O(V²)；原型大点云加速倍数不能代表两站Q1总耗时 |
| 强制三点圆≠普通三点MEC | Welzl强制边界的三个非共线点即使钝角仍要外接圆；强制三共线无有限圆，触发不变量/后备；普通三点MEC才可取最长边圆 | models/q1q2/circle.py:58、125、225；`reviews/correctness.md`§一7；R2 | [定理/有证明]；P3的18项oracle预期修正须按此解释，不夸成发现18个几何漏洞 |
| 浮点只提议支撑 | 临时圆不必逐次做全部有理导出；最终原坐标全点包含＋圆心位于支撑凸包内再认证；提议错误只增加回退 | models/q1q2/circle.py:139、190、231；`opt-q12.md:209`；R2 | [可验证充分条件]；近共线、溢出、极端尺度允许未决；不声称所有输入均返回OK |
| 角闭包与实际合法见证分开 | 闭包可用于sup/保收极限，direction下界见证必须严格>5；对5m边界内移仅为构造合法点 | models/q1q2/feasible.py:327、models/q1q2/q2.py:271、367、models/q1q2/optional/certified.py:49；R3/R4 | [可验证充分条件]；不能把内移量加进物理误差；开放端点接触可以导致充分检查未决 |
| 不强制Csig变Cdir | near可在原地20m清除：真实距离≤5≤20，后续无需再测向；强制direction会丢掉有价值行动 | models/q1q2/PLAN.md:481；models/q1q2/diagnostics.py:46；R1/R4 | [定理/有证明]（合法near）；需实际可实现反馈，不能给矛盾near也报成功 |
| 固定反馈下清除中心与半径绑定 | 曾有ON_SITE时把圆心替换成q但仍保留另一个圆心对应半径的错误；当前将动作位置、估计中心、外包覆盖中心分字段 | 历史 `reviews/static-review.md` B1；models/q1q2/diagnostics.py:46；BO/report.json `rows[*].clearance`；R0/R7 | [可验证充分条件]；ON_SITE由H_U检验，保证圆仍须用cover_center/r_U成对；不能拿条件诊断当最坏反馈J_R |
| 用切线外包而不是圆弧内接采样作清除依据 | 圆盘切线多边形包含连续后验；32边起，必要时64边；r_U与H_U带严格裕量，near另走解析支路 | models/q1q2/feasible.py:436、models/q1q2/diagnostics.py:46；R1/R7 | [可验证充分条件]；当前外包检查为浮点工程合同，不是区间认证；r_U失败不能反推出真实R失败 |
| 不只采源端点 | 连续最坏点对可能一个端点、一个内部接触点；线段[10,100]、q=(0,20)、ε₂=1°闭式J=`15.459510178683203`，生产见证x=`84.54048982144855`、y=100 | B4/report-certified.json `results[case_id=segment_10_100_20_1].expected.J_exact_m/actual.witness`；models/q1q2/q2.py:271、455；R0/R8 | [定理/有证明]（闭式）＋[实测/统计]；只枚举F边界端点会漏极值，网格细化也不是认证 |
| 缓存精确键、限制作用域 | 方向接触补样的合法点构造重复多；缓存精确参数元组和None结果，限当前源集/角宽/内移量作用域；不全局量化q后复用 | models/q1q2/q2.py:158；`opt-q12.md:142`、实现补丁；R1/R7 | [实测/统计]；量化缓存会改变物理几何语义；本素材无独立新性能实测 |
| 公共样本冻结并记录审计代际 | 各候选自适应云不一样会不公平；保留所有新见证，冻结后重评；评分变更导致代表反馈、条件R、稳定性等旧字段一起重建/失效 | models/q1q2/q2.py:815；P3 README；`reviews/static-review.md` B3/B4；R7 | [实测/统计]；有限复评稳定不保证连续极值准确；deadline保留最后完整公平结果，不伪造未完成审计 |
| 默认J不是凸/拟凸目标 | 标准推荐点及其镜像各J≤`110.97010129273485`；中点`(843.035666,0)`处源`(849,0)`、`(1500,0)`共享向东反馈，间距`651`。Csig凸仍无法推出J拟凸 | `opt-q12.md:282`、`innov-q12.md:291`；BO固定点证书＋models/q1q2/q2.py:367；R1/R3/R4 | [定理/有证明]（反例，依赖固定点上界）；否掉一般凸优化和“盒中心分数就是盒下界”；二次辅助函数仍可凸 |
| 不把最优点限制在候选域边界 | 审查给出裁剪线段场景的内部优于全边界反例；因此边界射线搜索仅作候选增强，必须保留内部扫描 | `opt-q12.md:282`、`innov-q12.md:291`；models/q1q2/q2.py:815；R1 | [定理/有证明]（审查反例）；本素材不另给无原始精度的近似性能数；通用“最优必在边界”命题不成立 |
| 区间改写不只看节点数 | 原型q*径向单调改写2144→2121节点，却1.541→1.597秒（3次中位数记录）；未无条件替换；源对交换去重也需内存/全域覆盖合同 | `opt-q12.md:223`；R1；这些旧原型全部计时的持久单一复现入口：无 | [实测/统计]（旧原型记录）；不当作当前生产结果，不能用节点下降宣称端到端加速；不删除代数冗余却可加强区间界的约束 |
| 标准外层从“找好点”转“排除坏下界盒” | 点对提议负责效率，整盒精确证据负责正确性；失败提议导致未收敛而非错误剪枝；独立checker重验叶覆盖 | models/q1q2/optional/outer_exclusion.py:26、47、119、181；models/q1q2/benchmarks/q2_outer/check_exclusion.py:61；R6 | [可验证充分条件]；只认证目标值间隔，不认证坐标误差、唯一性、最省移动或任意模型 |
| 推荐坐标舍入后再认证 | 靠近四盘边界，先内移留余量，保留6位坐标，再对最终数值q重查四盘和固定点；不能拿未舍入优化点的合法性担保输出坐标 | models/q1q2/benchmarks/q2_outer/run.py:28、98；BO/report.json四盘残差；R0/R7 | [可验证充分条件]；最小距离裕度仅`9.422302241546276e-06`m，因此坐标随意截断风险实在存在 |
| 阈值舍入允许保守漏报 | 原普通角估计可能把略大于2°变成2.0而误触发；新接口用区间上端；相邻浮点的失败返回None | models/q1q2/q2.py:590、627；舍入补丁；R5 | [可验证充分条件]；精确数学根没有变，26.15m保证也没有取消；未通过不等于可定位 |
| 图表只展示已有证据 | render只消费保存的panel数据；等比例坐标、缺值与OUT/NOT_EVALUATED分开；图不能偷偷重新求解或把缺值填0 | models/q1q2/plots.py:60；models/q1q2/run.py:49、79、107；R1 | [实测/统计]（输出合同）；F7等代表反馈图不是全部反馈，样本云可能由配置重建，须核对与最终评分云的区别 |

## 8. 创新点候选：三组题目适配贡献与降级结论

**原创性结论：无学术首创证据；命题成立≠文献原创。** 以下是供作者决定取舍的证据单元，不是贡献段落成稿。以`review-opt/innov-q12.md:178`三组合并方案为主；其“尚无外层认证”“预算界未实现”的实现时态由最新补丁更新，原创性降级不变。

| 贡献组 | 可保留的具体增量 | 证明/实现/数值锚点、复现 | 强度与必须降级的部分 |
|---|---|---|---|
| I：首次正反馈条件化保收域（C1+C2） | 消去同一源固定未知ρ，得到保收策略类内完整域；标准扇环再精确约化为四盘；解释远端r>1000不再收紧Csig | models/q1q2/PLAN.md:441、518；models/q1q2/feasible.py:354；`innov-q12.md:33/49`；本库§3四盘、§4两点残差；R1/R4 | [定理/有证明]；定位为有证明的题目适配判据/特殊结构约化。稳健集合、圆盘交、凸性均已有；无全球首创证据；不把四盘子结果再拆成独立创新数量 |
| II：位置可行集与统一清除动作（C3+C4+C9） | E20与R≤20的精确桥梁；Jung三段判断；共同反馈三点组解释清除障碍；程序以外包给保守动作依据 | models/q1q2/PLAN.md:333、658；models/q1q2/diagnostics.py:46、210；`innov-q12.md:61/73/142`；20/36等边反例、四站基准；R1/R2/R7 | [定理/有证明]（等价/推论）＋[可验证充分条件]（动作外包）；不是新Jung/Helly定理；三点连续最坏覆盖半径未求解；不能称首次估计控制融合或整局最优 |
| III：共同反馈点对与预算下界（C5+C6） | 消去未知第二读数，near/direction两分支点对化；用持久歧义点对给全部预算内站点下界；新同射线最大角减少旧arcsin相加的保守性 | models/q1q2/PLAN.md:560、608；models/q1q2/q2.py:367、455、572、590、627；`innov-q12.md:85/97/223`；10m→1000m、26.15m；R1/R3/R5 | [定理/有证明]；题目适配的等价重写与解析下界；交换sup、不可区分世界、主动定位和短基线病态皆非新思想；V(B)尚非精确解 |
| 验证支撑，另列不计第4组 | 独立固定点包含区间；标准外层0.01m证书；公共样本复评、精确叶证据和临界舍入回归 | models/q1q2/optional/certified.py:49、models/q1q2/optional/outer_exclusion.py:181、models/q1q2/benchmarks/q2_outer/check_exclusion.py:61；BO证书；最新1311与四块统计；R3/R6/R8/R9 | [可验证充分条件]＋[实测/统计]；不是新发明区间分析或分支定界；benchmark放在哪个目录不创造数学新颖性 |

| 容易被包装成创新的对象 | 作者可保留的用途 | 必须删除/降级的说法 | 来源、复现、强度 |
|---|---|---|---|
| κ/η、强制圆心、Thales | 完整回答Q1并解释圆心选择损失 | “原创覆盖定理/全新指标方法” | `innov-q12.md:154`；models/q1q2/circle.py:291；R1/R2；[定理/有证明]，经典几何适配 |
| Jung三段、2/√3关系 | 解释20m任务阈值与选J的代价 | “新的定位极限”；未经全局前提直接声称近似比 | `innov-q12.md:73/306`；R1；[定理/有证明]，直接推论 |
| 多起点、序贯、共享复评 | 说明求解可用性与公平比较 | “新序贯决策理论/已解动态规划/全局搜索必达最优” | `innov-q12.md:166`；models/q1q2/q2.py:815；R7；[启发式无保证] |
| 三个支撑点 | 解释最小圆由少数极端候选源决定 | “只要三次测量就保留全部定位信息” | `reviews/creativity.md:92/424`；models/q1q2/circle.py:190；R1/R2；[定理/有证明]仅源支撑性质 |

### 8.1 文献使用卡（依据既有本地综述，不冒充本次外部全文复核）

| 文献线索 | 本地已经核对的证据等级与可用内容 | 不能借用的结论 | 本地出处、复现与强度 |
|---|---|---|---|
| Tokekar–Isler 2013，DOI `10.1109/ICRA.2013.6630920` | 6页作者版全文；另32页PDF技术报告选读。角锥集员与最坏直径最直接基线 | 全域静态传感器布点的近似常数不能移植到首测条件化第二点 | `reviews/literature-review.md`§一；`innov-q12.md:9`；R1；[实测/统计]（文献核对记录） |
| Garulli–Vicino 2001 | 机构摘要：有界角测量、集合递归定位 | 未取全文，不引用其具体公式作本题充要式来源 | 同综述R2；R1；[实测/统计]（摘要级） |
| Kieffer等2000 | 出版社摘要/页面：超声距离区间定位 | 不是方位点对认证的现成定理，不能声称首用区间定位 | 同综述R3、innov§1；R1；[实测/统计] |
| Isler–Magdon-Ismail 2008 | 前身技术报告全文＋期刊摘要；凸测量集合传感器压缩、面积近似 | 面积保证不是直径保证，源点支撑不是观测约束压缩 | 同综述R4；R1；[实测/统计] |
| Tekdas–Isler 2010；Zhao等2013 | 前者作者全文，后者预印本模型/定理与书目；距离—夹角几何代理、FIM基线 | 90°优势需固定距离等前提；统计CRLB不是有界误差覆盖保证 | 同综述R5/R6；models/q1q2/diagnostics.py:249；R1；[实测/统计] |
| Vander Hook等2014；Bayram等2018 | 前者作者全文、后者机构摘要；主动测向、移动/检测时间、定位阈值先例 | 不能宽泛宣称首次主动定位或首次阈值停止；摘要不能支持未核对定理 | 同综述R7/R9；R1；[实测/统计] |
| Bercea等2016 | 完整预印本模型与结果；传感器对角覆盖、距离/可见性 | 本题是检测点拆分源位置对，集合系统不同，不能照搬其近似保证 | 同综述R8；R1；[实测/统计] |
| Welzl；Jung | 最小圆、至多三点支撑、平面半径—直径界的经典出处 | 不以题目变量重命名冒充原创；不将2012技术报告与2013会议版计作两项独立成果 | 同综述R14/R15及innov§1；R1；[定理/有证明]（本库已给推导），原创性无 |

## 9. 局限、待补与图表选材

| 作者需要留白/限定的内容 | 目前有的证据 | 目前没有的证据；允许推进的范围 | 出处、复现、强度 |
|---|---|---|---|
| 一般场景外层最优性 | 标准连续对称场景目标值gap=0.01m | 任意首站、目标圆裁剪、其它角宽/ρ/near参数的同等外层证书：无；推荐点唯一性/坐标误差界：无 | models/q1q2/optional/outer_exclusion.py:181；BO证书model；R6；[可验证充分条件]限定模型 |
| 官方量化与误差场 | 理论1°与条件1.005°合同；同点固定机制 | 官方处理顺序、真实空间相关场、实际设备测量独立性证明：无；精确量化共同格点求解：无 | models/q1q2/PLAN.md:95；models/q1q2/adapters.py:12；R1；无（待确认前提） |
| 完整物理链认证 | 固定点区间、标准四盘成员、外层叶覆盖、同射线角上界 | 所有生产浮点边界/后验/清除圆/适配输入串联的形式化认证：无 | models/q1q2/optional/certified.py:1、models/q1q2/optional/outer_exclusion.py:181、models/q1q2/diagnostics.py:46、models/q1q2/q2.py:627；R1/R3/R6；[可验证充分条件]分模块 |
| 最坏覆盖半径与清除时间 | J与J_R双边关系；两点代表反馈清除诊断 | 全部共同反馈三点组优化、精确E20全边界、总清除时间最优或整局最优：无 | models/q1q2/PLAN.md:658；models/q1q2/diagnostics.py:46；R1/R7；[定理/有证明]关系，不补造实验 |
| 预算曲线 | 10m与≤26.15m的1000m下界；有限搜索前沿 | V(B)完整精确曲线、实际可定位临界预算：无 | models/q1q2/q2.py:572、627；R5；[定理/有证明]仅下界 |
| 运行性能与跨平台 | 历史环境记录numpy2.5.3、mpmath1.3.0；局部原型耗时；测试日志耗时 | 本次独立性能实测：无；Windows guest/官方环境认证复现：无；不把内核倍数当总体加速 | BO/report.json `versions`；opt/verify报告；R0；[实测/统计]历史记录 |
| 稳健性与泛化 | 有解析退化例、变换不变量、有限网格/容差审计、区间证书 | 无限实例成功率、概率置信区间、官方比赛清除率/成绩：无 | 四块report与BO；R0/R8；[实测/统计]有限样本 |

| 作者可选图/表 | 直接使用的素材字段 | 应标注的信息与不可画成的含义 | 依据、复现、强度 |
|---|---|---|---|
| 等边反例图 | B2夹具 `equilateral_20.input.points/stations`，ground_truth.center/forced_center/radius | 两个圆心、半径10与11.547005383792515；图上显示理想式时注明20/√3；三站可另放小图避免远站压缩三角形 | models/q1q2/diagnostics.py:329、models/q1q2/plots.py:60；R0/R2；[定理/有证明]＋[实测/统计] |
| 20m三段表/形状对照 | 精确阈值20√3、40；36三角形与36线段；四站41.321338 | 40是必要上限，非充分停止阈值；四站是纯几何 | models/q1q2/circle.py:342；R2；[定理/有证明] |
| 四盘候选域＋推荐点 | BO两行q、四盘中心公式、残差区间 | 标near分支保留；坐标等比例；显示q*镜像时不称唯一解 | models/q1q2/benchmarks/q2_outer/run.py:138；R4/R7；[可验证充分条件] |
| 两点J认证比较表 | BO `rows[*].certificate`，外层上下界另行 | J_hat、固定点L/U、外层J*区间三者分栏；r_U写“该代表反馈条件下” | 本库§4；R0/R3/R6；[可验证充分条件] |
| 预算角条件图/表 | 最新 `threshold-comparison.json`、旧/新根字符串、B=10/26.15 | 曲线画角上界和2°；不要命名“可定位临界图” | models/q1q2/q2.py:590、627；R0/R5；[定理/有证明]（公式） |
| 外层证书示意图 | certificate.json `leaves`、verification counts | disk排除/pair下界/pending未决三色；标准完成证书pending=0；图是证据可视化，不代替精确覆盖检查 | models/q1q2/optional/outer_exclusion.py:181、models/q1q2/benchmarks/q2_outer/check_exclusion.py:35；R0/R6；[可验证充分条件] |

## 10. 可复现命令登记表

所有命令从 `/Users/flower/math/2026/B题` 执行，解释器固定为 `/Users/flower/math/2026/B题/models/q1q2/.venv/bin/python`。命令只作为作者查阅素材；本次未执行其中生产计算、benchmark或tests。耗时字段和机器版本字段不要求重跑逐位相同；数学输入、上下界方向与收敛状态必须核对。历史报告源哈希和当前源码可能不同，复验要记录版本，不能强求不同实现产生同一分支序列。

### R0：读取任意既有JSON字段/JSONL案例，保持原始数字词法

下面是完整可执行读取器。两个参数是文件路径和JSON Pointer：数组用数字索引，JSONL对象用`@case_id`选择。表中每项给出的文件和字段直接填入这两个位置；空pointer输出全部。`parse_float=str`使读取小数不经浮点重新舍入；输出中的数字字符串仅是读取形式，不改变归档数值。

```sh
/Users/flower/math/2026/B题/models/q1q2/.venv/bin/python -B - 'models/q1q2/benchmarks/q2_outer/report.json' '/rows/0/certificate' <<'PY'
import json, sys
from pathlib import Path
p = Path('/Users/flower/math/2026/B题') / sys.argv[1]
parse = lambda s: json.loads(s, parse_float=str)
d = [parse(s) for s in p.read_text().splitlines() if s.strip()] if p.suffix == '.jsonl' else parse(p.read_text())
for token in sys.argv[2].split('/')[1:]:
    token = token.replace('~1', '/').replace('~0', '~')
    if token.startswith('@'):
        d = next(x for x in d if x.get('case_id') == token[1:])
    else:
        d = d[int(token)] if isinstance(d, list) else d[token]
print(json.dumps(d, ensure_ascii=False, indent=2))
PY
```

常用精确参数对：

| 文件参数 | pointer参数 |
|---|---|
| `models/q1q2/benchmarks/q1_circle_cover/cases.jsonl` | `/@equilateral_20`、`/@equilateral_36`、`/@symmetric_four_station_square` |
| `models/q1q2/benchmarks/q1_circle_cover/report.json` | `/anchors/0` |
| `models/q1q2/benchmarks/q2_outer/report.json` | `/rows/0`、`/rows/1`、`/config` |
| `models/q1q2/benchmarks/q2_outer/exclusion/certificate.json` | 空字符串；或`/lower`、`/upper`、`/gap` |
| `models/q1q2/benchmarks/q2_outer/exclusion/verification.json` | 空字符串 |
| `review-opt/q12-budget-rounding/threshold-comparison.json` | 空字符串；或`/4`查看临界误触发 |
| `review-opt/verify-q12-data/budget-independent.json` | `/old_threshold`、`/new_threshold` |
| `review-opt/q12-budget-rounding/benchmarks-summary.json` | 空字符串 |

### R1：证明与代码逐行复核（不把读源代码当作证明执行器）

数学通用命题没有“跑一次即证明全部输入”的命令。R1读取表中证明位置；R2—R6只重算具体实例或证书。

```sh
/Users/flower/math/2026/B题/models/q1q2/.venv/bin/python -B - 'models/q1q2/PLAN.md' 226 349 <<'PY'
import sys
from pathlib import Path
p = Path('/Users/flower/math/2026/B题') / sys.argv[1]
for i, line in enumerate(p.read_text().splitlines(), 1):
    if int(sys.argv[2]) <= i <= int(sys.argv[3]):
        print(f'{i}: {line}')
PY
```

同命令将三个参数改为 `review-opt/q12-budget-rounding/tests.log 1 25` 可读取1311日志；改为本库每项代码/证明路径与起止行可复核其依据。无原始数值的纯命题，数值重跑不适用，不补造数字。

### R2：问题1构造、直径、MEC、Thales与阈值重算（stdout）

```sh
cd '/Users/flower/math/2026/B题'
/Users/flower/math/2026/B题/models/q1q2/.venv/bin/python -B - <<'PY'
import json, math
from pathlib import Path
from models.q1q2.geometry import BearingMeasurement, NumericPolicy
from models.q1q2.circle import minimum_circle, clearance_diameter_regime
from models.q1q2.q1 import solve
from models.q1q2.run import jsonable
rows = [json.loads(s) for s in Path('models/q1q2/benchmarks/q1_circle_cover/cases.jsonl').read_text().splitlines() if s.strip()]
for name in ('equilateral_20', 'equilateral_36', 'symmetric_four_station_square'):
    row = next(r for r in rows if r['case_id'] == name)
    obs = tuple(BearingMeasurement(tuple(s['position']), s['bearing_deg'], s['half_width_deg']) for s in row['input']['stations'])
    print(json.dumps({'case_id': name, 'archived_ground_truth': row['ground_truth'],
        'archived_closed_form': row.get('closed_form'),
        'point_cloud_mec': jsonable(minimum_circle(row['input']['points'], seed=0)),
        'reconstructed_wedges': jsonable(solve(obs, NumericPolicy()))}, ensure_ascii=False, allow_nan=False))
for d in (20*math.sqrt(3), 36., 40., math.nextafter(40., math.inf)):
    print('clearance', repr(d), clearance_diameter_regime(d))
print('ideal_equilateral_20', {'diameter': 20, 'radius': 20/math.sqrt(3), 'kappa': 2/math.sqrt(3), 'eta': math.sqrt(3), 'T': 200})
print('segment_36', jsonable(minimum_circle(((0., 0.), (36., 0.)), seed=0)))
for name, obs in [('empty_input', ()), ('ray', (BearingMeasurement((0.,0.),0.,0.),)),
                  ('segment', (BearingMeasurement((0.,0.),0.,0.),BearingMeasurement((10.,0.),180.,0.)))]:
    print(name, json.dumps(jsonable(solve(obs, NumericPolicy())), ensure_ascii=False, allow_nan=False))
PY
```

理想式的普通math运算、浮点顶点oracle、重新相交角锥三个结果末位可不同；引用归档时使用R0对应字段，不用某次普通浮点重算覆盖归档原值。

### R3：两固定点连续J区间认证（stdout）

```sh
cd '/Users/flower/math/2026/B题'
/Users/flower/math/2026/B题/models/q1q2/.venv/bin/python -B - <<'PY'
import json
from dataclasses import asdict
from models.q1q2.geometry import BearingMeasurement, NumericPolicy
from models.q1q2.feasible import PhysicsConfig, build_source_set
from models.q1q2.optional.certified import certify
ss = build_source_set(BearingMeasurement((0.,0.),0.,1.), PhysicsConfig(), NumericPolicy())
for q in ((843.035666,545.527004),(750.,400.)):
    c = certify(ss, q, epsilon2=1., tol=.001, max_nodes=2000000, time_limit_s=1800., dps=30)
    print(json.dumps({'q': q, 'certificate': asdict(c)}, ensure_ascii=False, allow_nan=False))
PY
```

重算独立50位对照时将`dps=30`改为`dps=50`。改为q=S用于复核同点分支时，需另设合理预算，不能预先承诺原预算收敛。

### R4：四盘成员、原始裕度与区间平方残差（stdout）

```sh
cd '/Users/flower/math/2026/B题'
/Users/flower/math/2026/B题/models/q1q2/.venv/bin/python -B - <<'PY'
import json, math
from mpmath.ctx_iv import MPIntervalContext
from models.q1q2.geometry import BearingMeasurement, NumericPolicy
from models.q1q2.feasible import PhysicsConfig, build_source_set, check_candidate
from models.q1q2.run import jsonable
pol = NumericPolicy()
ss = build_source_set(BearingMeasurement((0.,0.),0.,1.), PhysicsConfig(), pol)
iv = MPIntervalContext(); iv.dps = 30
for q in ((843.035666,545.527004),(750.,400.)):
    centers = [(r*math.cos(a),r*math.sin(a)) for r in (5.,1000.) for a in (-math.pi/180,math.pi/180)]
    residuals = []
    for r in (5,1000):
        for sign in (-1,1):
            a=sign*iv.pi/180
            z=(iv.mpf(q[0])-r*iv.cos(a))**2+(iv.mpf(q[1])-r*iv.sin(a))**2-1000**2
            residuals.append([math.nextafter(float(z.a),-math.inf),math.nextafter(float(z.b),math.inf)])
    print(json.dumps({'q':q,'centers':centers,'four_disk_distance_margins_m':[1000.-math.dist(q,c) for c in centers],
        'four_disk_squared_residual_intervals_m2':residuals,'check':jsonable(check_candidate(ss,q,False,pol))},ensure_ascii=False))
PY
```

### R5：预算下界、快速/认证角API、临界根（stdout）

```sh
cd '/Users/flower/math/2026/B题'
/Users/flower/math/2026/B题/models/q1q2/.venv/bin/python -B - <<'PY'
import json, math
import mpmath as mp
from models.q1q2.geometry import BearingMeasurement, NumericPolicy
from models.q1q2.feasible import PhysicsConfig, build_source_set
from models.q1q2.q2 import (short_baseline_lower_bound, same_ray_max_angle_deg,
    same_ray_max_angle_estimate_deg, tight_short_baseline_lower_bound, source_pair_budget_lower_bound)
ss = build_source_set(BearingMeasurement((0.,0.),0.,1.), PhysicsConfig(), NumericPolicy())
for B in (10.,26.15,26.150756085730233,26.150756085731228,26.15075608573123,26.150756085731235,26.15075608573223):
    print(json.dumps({'budget':B,'budget_hex':B.hex(),'legacy_bound':short_baseline_lower_bound(ss,500.,1500.,B),
        'fast_angle':same_ray_max_angle_estimate_deg(500.,1500.,B),
        'angle_upper':same_ray_max_angle_deg(500.,1500.,B),
        'tight_bound':tight_short_baseline_lower_bound(ss,500.,1500.,B)},ensure_ascii=False))
for gamma in (-.4,-.2,0.,.2,.4):
    y=(1499*math.cos(math.radians(gamma)),1499*math.sin(math.radians(gamma)))
    print('noncollinear',gamma,source_pair_budget_lower_bound(ss,(500.,0.),y,10.))
mp.mp.dps=100
a,b=mp.mpf(500),mp.mpf(1500)
old=mp.findroot(lambda B:mp.asin(B/a)+mp.asin(B/b)-2*mp.pi/180,(13,14))
new=mp.findroot(lambda B:mp.atan(B*(b-a)/mp.sqrt((a*a-B*B)*(b*b-B*B)))-2*mp.pi/180,(26,27))
print('old_threshold',mp.nstr(old,100));print('new_threshold',mp.nstr(new,100))
PY
```

根求值是高精度数值复算，末尾格式依nstr有效位数；精确归档字符串读R0。临界审计的100位独立方位角区间见`threshold-comparison.json[*].oracle_interval`，不把快速公式的输出当该独立oracle。

### R6：标准外层0.01m证书重建＋独立检查（stdout，不写归档）

```sh
cd '/Users/flower/math/2026/B题'
/Users/flower/math/2026/B题/models/q1q2/.venv/bin/python -B - <<'PY'
import json
from models.q1q2.optional.outer_exclusion import certify_outer
from models.q1q2.benchmarks.q2_outer.check_exclusion import verify
c=certify_outer(tau='0.01',max_nodes=10000,time_limit_s=120.,dps=60,
    q=(843.035666,545.527004),fixed_max_nodes=200000,fixed_time_limit_s=60.)
print(json.dumps({k:v for k,v in c.items() if k not in ('leaves','fixed_certificate')},ensure_ascii=False,indent=2))
print(json.dumps(verify(c),ensure_ascii=False,indent=2))
PY
```

只复核已有证书：

```sh
cd '/Users/flower/math/2026/B题'
/Users/flower/math/2026/B题/models/q1q2/.venv/bin/python -B - <<'PY'
import json
from pathlib import Path
from models.q1q2.benchmarks.q2_outer.check_exclusion import verify
p=Path('models/q1q2/benchmarks/q2_outer/exclusion/certificate.json')
print(json.dumps(verify(json.loads(p.read_text())),ensure_ascii=False,indent=2))
PY
```

失败预算例将第一条命令`max_nodes=10000`改为9，保留pending与converged状态。独立检查会重新计算固定点证书；本次素材整理没有执行。

### R7：推荐点搜索与统一复评归档流程（输出重定向到内存，禁止paper阶段）

下面重算`refine`与`certify_final`，覆盖本库推荐坐标、J_hat、代表反馈、移动量等生产数值。它将模块的`save`替换为内存收集器，最终只输出stdout；`certify_final`按原流程读取已有`refined.json`。先核对本次重新找到的q与归档q一致，若不一致便停下核对，不能假装复现原报告。`run.py`的`paper`阶段会写`models/paper-full.md`，不在本库命令内。

```sh
cd '/Users/flower/math/2026/B题'
/Users/flower/math/2026/B题/models/q1q2/.venv/bin/python -B - <<'PY'
import json
from pathlib import Path
from models.q1q2.benchmarks.q2_outer import run as m
payload={}
m.save=lambda name,obj:payload.__setitem__(name,m.jsonable(obj))
m.refine()
archived=json.loads(Path('models/q1q2/benchmarks/q2_outer/refined.json').read_text())
if payload['refined.json']['best']['q'] != archived['best']['q']:
    raise RuntimeError('Recomputed recommendation differs: inspect inputs/version before fixed archive comparison')
m.certify_final()
print(json.dumps(payload,ensure_ascii=False,allow_nan=False))
PY
```

默认选择器本身的可复现入口（与BO强化流程不同）：

```sh
cd '/Users/flower/math/2026/B题'
/Users/flower/math/2026/B题/models/q1q2/.venv/bin/python -B - <<'PY'
import json
from models.q1q2.geometry import BearingMeasurement, NumericPolicy
from models.q1q2.feasible import PhysicsConfig, build_source_set
from models.q1q2.q2 import SearchConfig, select_second_point
from models.q1q2.run import jsonable
ss=build_source_set(BearingMeasurement((0.,0.),0.,1.),PhysicsConfig(),NumericPolicy())
print(json.dumps(jsonable(select_second_point(ss,SearchConfig())),ensure_ascii=False,allow_nan=False))
PY
```

### R8：四块benchmark与附加认证/预算的隔离复验命令（本次未执行）

为避免原运行器覆盖生产目录里的旧报告，复制当前q1q2到临时目录运行，读结果后删除副本。此命令不写其它agent报告、不调用官方服务；属于本地benchmark，仍不在本次执行范围内。四块原始README给出的模块入口均保留。

```sh
cd '/Users/flower/math/2026/B题'
/Users/flower/math/2026/B题/models/q1q2/.venv/bin/python -B - <<'PY'
import json, os, shutil, subprocess, tempfile
from pathlib import Path
root=Path('/Users/flower/math/2026/B题')
python=str(root/'models/q1q2/.venv/bin/python')
with tempfile.TemporaryDirectory(prefix='q12-writing-replay-') as tmp:
    t=Path(tmp)
    shutil.copytree(root/'models/q1q2',t/'models/q1q2',ignore=shutil.ignore_patterns('.venv','__pycache__','.pytest_cache'))
    env=dict(os.environ,PYTHONPATH=os.pathsep.join((str(t),str(root))),OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
    for area in ('q1_geometry','q1_circle_cover','q2_candidate','q2_worst_diameter'):
        subprocess.run([python,'-B','-m',f'models.q1q2.benchmarks.{area}.run'],cwd=t,env=env,check=True)
        report=json.loads((t/f'models/q1q2/benchmarks/{area}/report.json').read_text())
        print(area,{k:report[k] for k in ('n_cases','n_pass','n_fail')})
    # 原归档7例固定点认证：精确复用归档case_id与预算选项。
    archived=json.loads((root/'models/q1q2/benchmarks/q2_worst_diameter/report-certified.json').read_text())
    opts=archived['certification']['options']
    command=[python,'-B','-m','models.q1q2.benchmarks.q2_worst_diameter.run',
             '--certify','--certify-tol',str(opts['tol']),
             '--certify-seconds',str(opts['time_limit_s']),
             '--certify-nodes',str(opts['max_nodes']),
             '--report',str(t/'report-certified.json')]
    for row in archived['results']:
        command.extend(['--case',row['case_id']])
    subprocess.run(command,cwd=t,env=env,check=True)
    certified=json.loads((t/'report-certified.json').read_text())
    print('certified',{k:certified[k] for k in ('n_cases','n_pass','n_fail')})
    # 额外预算16例；报告只写临时目录。
    subprocess.run([python,'-B','-m','models.q1q2.benchmarks.q2_worst_diameter.run_budget_bounds',
                    '--report',str(t/'budget-bounds.json')],cwd=t,env=env,check=True)
    print((t/'budget-bounds.json').read_text())
PY
```

7例认证部分从原报告`results[*].case_id`读取完整筛选，复用`certification.options={tol:0.1,time_limit_s:30.0,max_nodes:200000}`；CLI参数已对照`models/q1q2/benchmarks/q2_worst_diameter/run.py:252`核实。它与普通48例是两次独立运行；不能把默认48例当7例认证重跑。

### R9：1311项本地测试历史入口（本次禁止执行，留供后续授权复验）

历史记录的确切调用：

```sh
cd '/Users/flower/math/2026/B题'
/Users/flower/math/2026/B题/models/q1q2/.venv/bin/python -m pytest models/q1q2/tests -q
```

日志读取用R1，无需重跑。后续若要保留工作区只读，可采用R8的临时副本机制，在临时cwd执行同一pytest参数。这里不提供任何官方模拟器或正式测试入口。

## 11. 作者引用前的最终对照

| 待引用核心结果 | 素材位置 | 最容易写错的边界 |
|---|---|---|
| 角锥半平面构造、直径圆充要判据 | §2 | 完整顶点；非空有界凸多面集；ε=0前向射线 |
| 20米等边反例、四站41.321338/20.660669 | §2.1 | 理想式/浮点oracle差末位；四站仅纯几何 |
| Jung三段、κ/η | §2 | 20√3与40端点；比值不随新增观测单调 |
| 四盘Csig、共同反馈点对公式 | §3 | 标准未裁剪场景；共享固定ρ；near/direction不能混合；原地特例 |
| 推荐q*与固定点认证比较 | §4 | 推荐点标记不证明唯一精确最优；固定点区间不是J_R |
| 110.960101≤J*≤110.970102 | §4、§5.3 | 精确gap为1/100，展示端点差0.010001；标准模型专用 |
| 10m→≥1000m、新同射线界、26.15裕度 | §3.1、§4 | 下界不等于精确V(B)；浮点显示临界值不能直接触发保证 |
| 285/285、330/330、531/531、48/48、1311 | §6 | 均为已有本地记录；普通48例不是连续认证；本次未运行 |
| 三组创新及降级 | §8 | 无学术首创证据；命题成立≠文献原创 |

