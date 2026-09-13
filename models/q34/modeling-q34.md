# 问题3与问题4：覆盖驱动的发现、定位与清除模型

版本：第二次正式测试方案，2026-09-13。Q3采用最近邻任务排序、65米试清门限、主定位预算2轮；Q4采用最近邻任务排序、35米门限及默认参数。当前配置以`B/bounded_candidates.py`为准；本稿保留适用的模型推导，实验数据统一引用[当前四表](../../B/experiments/paper_materials/2026-09-13_formal2_baselines/四表汇总.md)。

核心方法是：用有限站点的连续覆盖保证发现，以含真源的位置外包指导定位和清除，将未完成扫描与已知源服务共同排序，并以有限光学覆盖完成未能充分收敛的定位任务。**覆盖、包含性与有限结束各有独立依据；任务排序、测向评分和试探门限承担效率优化，不因此获得全局最优保证。**

## 0. 实现范围与证据口径

### 0.1 当前主候选

| 项目 | Q3：`range_area7` | Q4：`range_grid21_29` |
|---|---|---|
| 实例类 | `OmniNegativeCompletionPolicy` | `CoupledWidthPolicy` |
| 场景处理 | 全向源，`mixed=False` | 全向/定向混合，统一按未知朝向处理，`mixed=True` |
| 发现布局 | 原点＋半径1140米的六个等角点，共7站 | `grid21_29` 的21个固定整数坐标 |
| 调度模型 | `dispatch_model="base"`，`task_order="nearest"`，源以包含圆心作位置代理 | 同为 `base`，`prediction="center"`，`dispatch="nearest"` |
| 服务粒度 | 选中一个源后原子完成；最多2次主要主动测量，再有限光学兜底 | 按源分包；每源累计最多10轮、20次主要 RF，再有限光学兜底 |
| 提前试探门 | `trial_radius=65` 米 | `bracket_trial_radius=35` 米，由 `trial_radius=35` 传入 |
| 测向/探针对应参数 | `area_prior=True`，`remainder_weight=1.5`，`time_weight=0.08`；未启用 expanded 候选 | 纵向分位 `fraction=0.15`，横向目标40米，负反馈共享冷却150米 |
| 共用机制 | 保守位置区域、包含圆、共享已知频道测量、已知源距离跳扫、公开16源上限 | 同左；默认全局中断上限16次 |

显式配置与直接构造见 [B/bounded_candidates.py:13](../../B/bounded_candidates.py)；继承默认值见 [B/joint_task_policy.py:14](../../B/joint_task_policy.py)、[B/policies.py:12](../../B/policies.py)、[B/interleaved_policy.py:19](../../B/interleaved_policy.py)。Q3 实例虽继承了 bracket 相关字段，主服务不使用其40米字段；Q4 主循环调用 `source_packet`，不调用同类可访问的旧 `complete_source`。

### 0.2 实际调用关系

```text
bounded_candidates.build
  Q3 → OmniNegativeCompletionPolicy
       run: JointTaskPolicy.run
       next_task: CoupledDispatchMixin(base)
                  → EfficientJointPolicy → JointTaskPolicy → 最近邻任务
       source: CompletionClearancePolicy.complete_source
       clear: ClearanceMixin → JointTaskPolicy → Policy → Client

  Q4 → CoupledWidthPolicy
       run: InterleavedMixin.run
       next_task: CoupledDispatchMixin(base) → InterleavedMixin → 最近邻任务
       source: InterleavedMixin.source_packet
       probes: BoundedWidthPacketPolicy → WideProbeMixin → ProbeJointPolicy
       clear: JointTaskPolicy → Policy → Client
```

两者测量均经 `CertifiedRangeSkipMixin`，最终由 `Policy.measure` 接受反馈；Q4 另经 `ProbeJointPolicy.measure` 维护负反馈冷却。依据见 [B/coupled_dispatch_policy.py:67](../../B/coupled_dispatch_policy.py)、[B/joint_task_policy.py:95](../../B/joint_task_policy.py)、[B/completion_sensing_policy.py:110](../../B/completion_sensing_policy.py)、[B/interleaved_policy.py:99](../../B/interleaved_policy.py)。

当前 CLI 仅注册 `cover21` 系列及这两个候选，默认模式是 `mock-http`；旧审计所述“默认 icra、跨多层实验工厂转发”已被入口修复替代。[B/run_bounded_robot.py:40](../../B/run_bounded_robot.py)。

### 0.3 与 Q1/Q2 的衔接

沿用 [Q1/Q2 PLAN](../q1q2/PLAN.md) 的三个区分：集合后验不等于概率后验；直径不等于覆盖半径；数值候选不等于已证最优。但本实现没有直接调用 `models/q1q2` 求解器，Q3 的主动选点也不是 Q2 的连续最坏直径优化器。

本文将精确物理位置可行集记为 $K_{c,t}$，代码实际维护的凸多边形外包记为 $P_{c,t}$，满足目标关系 $K_{c,t}\subseteq P_{c,t}$。此处 $P$ 包含源域和距离信息，**不是 Q1 的纯角锥交集**。理论最小覆盖半径写为 $R(P)$，程序返回的、经过全顶点距离复核的包含半径写为 $\widehat r(P)$，避免将数值输出和理论最小值无条件等同。

“已证明”指在明确物理假设、精确几何关系下成立的性质；“整数复核”仅指指定覆盖证书的整数谓词和分区检查；“浮点实现”仍有容差与数值边界；“经验”只覆盖注明配置的实验。既有审计与修复记录见第9节，本次未重新执行其中的大规模实验。

## 1. 问题建模：未知源数下的在线任务

### 1.1 世界、反馈与行动

源域为 $A=D(0,1800)$。有效频道集合为 $\mathcal C=\{1,\ldots,20\}$，每频道至多一源；真实源数 $N\in[10,16]$ 未知。源 $c$ 的位置 $g_c\in A$、固定有效接收半径 $\rho_c\in[1000,1500]$ 均不公开。Q4 还未知源类型和定向源的单位朝向 $n_c$。

对未清除源，其接收集合定义为

$$
V_c=\begin{cases}
D(g_c,\rho_c),&\text{全向},\\
D(g_c,\rho_c)\cap\{q:n_c^T(q-g_c)\ge0\},&\text{定向}.
\end{cases}\tag{1}
$$

定向覆盖是含边界的180°半圆盘；$n_c$ 表示源朝向，示向度则指检测点到源的方位，两者不同。到达 $q$ 后，对指定频道检测：在 $V_c$ 内且距源不超过5米返回 `near`；在 $V_c$ 内且距离大于5米返回含误差示向度的 `direction`；其余返回 `no_signal`。Q4 即使距源小于5米，处于背面也可能无信号。清除仅要求 $\|q-g_c\|_2\le20$，与源朝向无关。

行动由 `/measure(q,c)`、`/clear(q,c)` 表示；没有免费移动或同时读全频道的操作。起点为原点，初始测量频道为1；`/exit` 不要求返回原点。机器人可以走到源圆域之外，接口坐标分量须有限且绝对值不超过2000000米。

以上为附件合同，见 [附件2文本:5](../../mock/materials/附件2.txt)；本地实现对应 [B/simulator.py:77](../../B/simulator.py)。一次合法反馈只约束该频道，不能以别的频道无信号排除本频道的位置。

### 1.2 信息状态与目标

令 $H_t$ 为已接受的请求及反馈历史，策略为 $a_t=\pi(H_t)$。维护：实际位置 $x_t$、测向机频道 $f_t$、未访问站集合 $U_t$、已发现频道集合 $D_t$、成功清除集合 $C_t$，以及各已知未清源的 $P_{c,t}$、成功示向记录、试探标志与累计预算。`regions` 和 `cleared` 的并集对应已知存在的不同频道；真源坐标、实际源数、半径、朝向和评分真值不进入策略状态。[B/policies.py:11](../../B/policies.py)、[B/interleaved_policy.py:25](../../B/interleaved_policy.py)。

任务先要求所有源清除，再追求单局平均时间

$$
\bar T=\frac{T_{\rm exit}}{N_{\rm cleared}},\qquad N_{\rm cleared}=N.\tag{2}
$$

全清时分母为固定但事前未知的 $N$，因而单局降低总虚拟时间与降低平均时间等价。未全清的低时间不视为更优；验证必须并列全清率与耗时。没有给定官方场景概率分布，本文不把主策略写成已求解的贝叶斯最优控制或整局 minimax。实际方法是在正确性约束下，以滚动任务排序和局部评分近似降低完成时间。

### 1.3 误差与静态性假设

源、有效半径及朝向在本次定位阶段保持不变；同点同源误差在稳定时段内固定，不通过重复同点取平均来缩小角界。理论误差为±1°；当前 `B/geometry.py` 使用 **1.01°工程半宽**。该半宽可外包“潜在±1°误差后最近舍入到0.01°”，也可外包通常的0.01°截断误差；它不是官方舍入流程已经查明的结论，更不是对任意未知量化误差的保证。与 PLAN 中理论1°及最近舍入1.005°应明确分列。[B/geometry.py:6](../../B/geometry.py)、[Q1/Q2 PLAN §0.6](../q1q2/PLAN.md)。

采用二维欧氏移动、无障碍绕行、提交坐标无额外执行偏差的模拟环境。收到的合法反馈遵守式（1）及所用总角界，是后续包含性论证的前提。HTTP失败、响应不完整、`accepted=false` 都不是物理 `no_signal`。

## 2. 覆盖证书：未知频道至少被发现一次

### 2.1 Q3 七站全向充分性

取原点和半径 $a=1140$ 米上的 $n=6$ 个等角站。对距原点 $r\in[0,1800]$ 的源，在最近环站的扇区中夹角满足 $|\theta|\le\pi/n$。最坏角位置是 $|\theta|=\pi/n$，至最近站的距离平方为

$$
f(r)=\min\{r^2,\ r^2+a^2-2ra\cos(\pi/n)\}.\tag{3}
$$

两支在 $r_0=a/[2\cos(\pi/n)]$ 相交。$r\le r_0$ 时第一支递增；$r\ge r_0$ 时第二支为凸二次函数，其区间最大值出现在端点。因此本布局的连续覆盖半径为

$$
r_{\rm cov}=\max\left\{\frac{1140}{2\cos(\pi/6)},
\sqrt{1800^2+1140^2-2\cdot1800\cdot1140\cos(\pi/6)}\right\}
=992.689147\ldots<1000.\tag{4}
$$

故任意合法全向源均在至少一站的最小接收范围内，余量约7.310853米。证明覆盖了内部与圆周，非只检查边界或有限样点。生成器在覆盖半径不严格小于1000米时拒绝布局。[B/ring_coverage.py:11](../../B/ring_coverage.py)。

七站是一个已证充分方案，没有证明站数全局最少。它也不能用于任意定向源：取 $g=(1800,0)$、朝东，七站都在严格背面，全部无信号。

### 2.2 Q4 任意方向的凸包充分性

设有限站集为 $S$，对源位置 $g$ 定义最小半径内的站集

$$
S_g=\{s\in S:\|s-g\|\le1000\}.
$$

**命题1（固定位置的闭半平面覆盖）。** 若 $g\in\operatorname{conv}(S_g)$，则对任意单位朝向 $n$，至少一个 $s\in S_g$ 满足 $n^T(s-g)\ge0$。

**证明。** 存在非负权重 $\lambda_i$ 且权重和为1，使 $g=\sum_i\lambda_i s_i$。若所有站均严格在背面，则 $\sum_i\lambda_i n^T(s_i-g)<0$，与 $n^T(g-g)=0$ 矛盾。距离又不超过1000米，故至少一个站可接收。真实半径增加不会削弱覆盖。证毕。

事实上，对固定 $g$、最小半径和闭180°模型，若 $g$ 不在该有限凸包内，严格分离可给出一个使全部 $S_g$ 处于背面的朝向；空集同样不覆盖。但后述“整个叶格共用一组站”的条件只是便于计算的全域充分证书，并非布局覆盖的必要条件。

主布局实际坐标由下列集合组成，符号取值表示全部相应组合：

| 组别 | 实际坐标（米） | 数量 |
|---|---|---:|
| 中心 | $(0,0)$ | 1 |
| 内层轴点 | $(\pm999,0),(0,\pm999)$ | 4 |
| 内层对角点 | $(\pm706,\pm706)$ | 4 |
| 外层轴点 | $(\pm1864,0),(0,\pm1864)$ | 4 |
| 外层其余点 | $(\pm1614,\pm932),(\pm932,\pm1614)$ | 8 |

这是整数布局，不是把理想圆周坐标保留几位小数的图示。实际顺序存于 [B/layouts/grid21_29.json:4](../../B/layouts/grid21_29.json)，运行只读其 `route`。外层域外站不可随意投影回1800米源圆：圆周源朝外时，所有不同于源的圆内点都在其严格背面。

### 2.3 从局部命题到连续全域证书

从根方形 $[-1800,1800]^2$ 四叉细分。叶格记为 $Q(c,h)=c+[-h,h]^2$。仅当格子与源圆盘不相交时可省略；其余格子选择对整个格子均在接收半径内的站：

$$
I_Q=\left\{i:\sqrt{(|s_{ix}-c_x|+h)^2+(|s_{iy}-c_y|+h)^2}
\le1000-10^{-5}\right\}.\tag{5}
$$

式（5）是站到方格的最远角点距离。再要求整个 $Q$ 落在 $\operatorname{conv}\{s_i:i\in I_Q\}$ 内。若凸包边约束为 $a_j^Tx+b_j\le0$，则矩形上的最大值为

$$
a_j^Tc+b_j+h(|a_{jx}|+|a_{jy}|),\tag{6}
$$

浮点版本要求每条边均保留严格内缩余量。由凸性，四角包含即整格包含；结合命题1即可保证格内每个源位置、每个朝向存在接收站。最后必须检查叶格构成源圆盘上的完整、无内部重叠的四叉分区，防止只验证几个正确小块却遗漏其余区域。

实现见 [B/visibility_certificate.py:35](../../B/visibility_certificate.py)、[B/icra_final_checks.py:24](../../B/icra_final_checks.py)。`sample_reject` 和 `directional_witness` 可寻找特定盲区反例；采样无反例不证明全域覆盖。达到深度或单元预算而返回 `unresolved_cell` 表示未决，不必然表示布局不覆盖；`grid21_29` 保存的浮点证书最深为14，不能拿默认深度13的一次未决当作反例。

### 2.4 整数复核与域的边界

对整数站点取尺度 $M=2^d$，$0\le d\le16$，使站点和全部四叉角点变为整数。生成器精确比较平方距离及凸包边叉积。对逆时针凸包边向量 $e$、边起点 $v$，整格位于左侧等价于

$$
\operatorname{cross}(e,c-v)-h(|e_x|+|e_y|)\ge0,\tag{7}
$$

其中此式使用同尺度整数坐标。允许等号对应题设的闭半平面。生成器的距离上限用有理数 $1000-10^{-5}$ 的平方乘 $M^2$ 后向下取整；坐标分量绝对值不超过1950、尺度不超过65536的限制使所用 int64 运算低于溢出界。[B/integer_visibility_certificate.py:29](../../B/integer_visibility_certificate.py)。

独立验证器使用 Python 大整数，逐角点检查到所有选中站的距离严格小于1000米，并枚举站点三角形验证角点处于闭凸包；再以整数四叉树复核无漏格、无重复及无重叠。它独立重验的是 **严格小于1000米**，不宣称重新验证生成器全部 $10^{-5}$ 米余量。前提检查使用显式异常，`python -O` 不会移除。[B/integer_visibility_certificate.py:97](../../B/integer_visibility_certificate.py)。

| 同一 `grid21_29` 点集的证据 | 记录 |
|---|---|
| 保存的浮点严格凸包证书 | 7420叶格，19429访问节点，最深14；最小接收距离余量0.062188213米、最小凸包余量0.002886329米 |
| 修复记录中的重新生成整数证书 | 6976叶格，18837分区节点，独立验证通过 |
| 本次文档核对 | 入口实际路线点集与归档 `points`、归档 `route` 的坐标集精确相等；未重生成证书 |

两种证书允许的凸包边界和细分停止条件不同，叶格数不同不构成矛盾。保存证书见 [rounded-cover21/certified_layouts.json](../../B/experiments/runs/2026-09-11_rounded-cover21/certified_layouts.json)，整数再验证见 [认证工具修复记录](../../code-review/fix-q34-certification-p2.md)。证书索引属于原 `points` 行号，不能把重排后的路线数组直接按旧索引解释。

**题目需要源圆盘覆盖，不要求整个根方形覆盖。** 当前 `verify_cells` 已检查圆盘分区和叶几何，但返回 `coverage_guarantee=False`，说明它尚未绑定问题、布局与实际路线，也未证明整方形。另一个强接口 `certify_layout_coverage` 要求 Q4 上下文、坐标集相等及叶格精确面积铺满 $3600^2$；它拒绝圆盘证书是有意行为，不能据此否定主布局。[B/visibility_certificate.py:151](../../B/visibility_certificate.py)。当前入口不在运行时自动生成或重验覆盖证书，覆盖结论依赖冻结坐标与归档证据的一致性。

## 3. 集员定位：维护真源的保守外包

### 3.1 成功示向的集合更新

精确物理可行集可先在联合世界中定义：对一个已知且尚未清除的频道，保留所有满足源域、固定半径、固定类型/朝向及该频道清除前全部合法反馈的 $(g,\rho,\tau,n)$，其中 $\tau$ 表示源类型；再投影到位置坐标得到 $K_{c,t}$。成功反馈要求测点属于同一个接收集合，无信号要求测点不属于该集合；不能对每次观测重新选择不同半径或朝向。当前程序只保留这些联合约束中易于证明和计算的部分，形成下面的凸位置外包。

对检测点 $s$、读数 $\theta$、总角半宽 $\varepsilon=1.01^\circ$，令 $u_\pm=(\cos(\theta\pm\varepsilon),\sin(\theta\pm\varepsilon))$。闭前向角锥为

$$
W(s,\theta)=\{g:\operatorname{cross}(u_-,g-s)\ge0,
\operatorname{cross}(u_+,g-s)\le0\}.\tag{8}
$$

零半宽时显式加入前向约束，避免退化为整条直线。收到 `direction` 还说明源距 $s$ 不超过1500米。定义圆盘的64边切线外包

$$
\widehat D(c,r)=\bigcap_{j=0}^{63}\{g:v_j^T(g-c)\le r\},
\quad v_j=(\cos(2\pi j/64),\sin(2\pi j/64)).\tag{9}
$$

首次由 $\widehat D(0,1800)$ 初始化，之后执行

$$
P_{c,t+1}=P_{c,t}\cap W(s,\theta)\cap\widehat D(s,1500).\tag{10}
$$

代码半平面裁剪留小量外放，保留点、线段退化；空交集不解释成“该频道不存在”，而是保留已有区域、记录 `inconsistent_updates`，首次即空则报错。[B/geometry.py:30](../../B/geometry.py)、[B/policies.py:23](../../B/policies.py)。

集员定位指对所有与信息一致的位置保留集合。当前实现不精确维护未知半径与朝向的联合可行集，不利用 `direction` 排除5米内区域，也不保留精确接收圆弧；因此式（10）是含真源的外包，不是完整物理后验。只要反馈与总角界正确，忽略这些约束会损失定位精度而不主动删除真源。浮点外放是工程保护，不等于全运算区间认证。

### 3.2 全向继续接收的充分条件

成功锚点 $s$ 对候选源 $g$ 提供 $\rho\ge\max(1000,\|s-g\|)$。因此对全向源，一个可证明保收的条件为

$$
\forall g\in P:\quad \|q-g\|\le\max(1000,\|s-g\|).\tag{11}
$$

当前 Q3 为控制评分成本，只使用更保守的两个全区域充分条件之一：所有顶点至 $q$ 小于1000米；或者 $q$ 对区域内所有点均不比 $s$ 更远。后者利用平方距离差的仿射性，在顶点检查。[B/intelligent.py:89](../../B/intelligent.py)；Q3 候选筛选见 [B/completion_sensing_policy.py:73](../../B/completion_sensing_policy.py)。

`signal_minimax.reception_certificate` 实现了允许不同位置由不同分支满足式（11）的检验。令

$$
\Delta(g)=\|q-g\|^2-\|s-g\|^2
=q^Tq-s^Ts-2(q-s)^Tg.
$$

仅需在 $P\cap\{\Delta\ge0\}$ 上复核最大距离小于1000米；该集合为凸多边形，凸距离函数的最大值可取顶点。此检验比“两个条件分别对全区域成立”更完整，但仍针对位置外包和成功锚点，不能称为所有历史联合世界的精确保收域。[B/signal_minimax.py:11](../../B/signal_minimax.py)。

该模块还将可能示向区间分桶，用“误差半宽＋桶半宽”的扩张角锥包含桶中全部成功方向反馈，并取覆盖半径上界；`near` 分支半径至多5米。它未纳入 `no_signal` 分支，只有已获保收条件时才能用于下一次全部反馈的保证。**这些连续桶上界工具没有进入当前主候选的评分链，不能把其保证附加到 Q3 的协方差代理上，更不能作为 Q4 全反馈 minimax。**[B/signal_minimax.py:40](../../B/signal_minimax.py)。

## 4. 从位置区域到清除动作

### 4.1 MEC 与20米判据

对非空有界位置集合，定义

$$
R(P)=\min_z\max_{g\in P}\|z-g\|,
\qquad E_{20}(P)=\bigcap_{g\in P}D(g,20).\tag{12}
$$

则 $E_{20}(P)\ne\varnothing\iff R(P)\le20$。对凸多边形，只需检查全部顶点。程序用固定种子随机增量法计算圆心，最后把半径扩大到所有顶点至该圆心的最大距离，作为 $\widehat r$；即使数值圆心没有达到理论最优，包含性复核仍比“宣称已算出精确MEC”更直接地支撑清除。[B/geometry.py:121](../../B/geometry.py)。

当前认证清除门为 $\widehat r\le20-10^{-5}$ 米。它给出充分条件；若 $\widehat r$ 超过20米，只能说当前外包与当前包含圆尚不足以保证，不能证明真实可行集 $K$ 不可一次清除。直径 $d(P)\le40$ 也不充分：边长40米等边三角形的最小圆半径为 $40/\sqrt3>20$。

`near` 是另一条认证路径：已有合法信号且距源不超过5米，立即另发清除动作；只有 `clear_result="success"` 才加入清除集合。`near` 本身不等于成功清除。[B/policies.py:23](../../B/policies.py)。

### 4.2 Q3 就近保证清除落点

已满足认证半径时，Q3 尝试求当前位置到 $E_{20}(P)$ 的近点，减少只为到圆心产生的移动。对顶点等半径圆盘交，最近点候选包括：当前位置、单圆径向投影、两圆交点、已验证包含圆心。实现用 $20-10^{-6}$ 米内缩半径，逐候选检查全部顶点距离，仅在移动确实减少时替换原落点。[B/clearance_policy.py:8](../../B/clearance_policy.py)。

这是带数值余量的局部清除落点优化，不能表述为整局路线一定更短。**Q4 主候选没有 `ClearanceMixin`，其认证清除通常在包含圆心，near 在原测点。**

### 4.3 认证清除与试探清除

未到20米认证门但 $\widehat r\le r_{\rm trial}$ 时，允许每源至多一次专门的提前圆心试探。Q3 取65米，Q4 取35米。65/35米是“何时值得尝试”的策略门，不改变20米物理清除半径，也不提供成功概率保证。

Q3 试探失败后保留区域，在圆心继续测量；Q4 试探失败后沿原成对探针规则继续定位。只有成功响应改变 `cleared`，失败不会被算作完成，也不在当前主链中追加“20米圆外”的负约束。[B/completion_sensing_policy.py:117](../../B/completion_sensing_policy.py)、[B/interleaved_policy.py:107](../../B/interleaved_policy.py)。

“每源一次”仅指该提前试探分支；光学兜底仍可尝试圆心及多个格心，故不是每源总清除请求至多一次，也不是总失败至多一次。

门限影响试清、后续测向和移动之间的取舍。当前65/35米选择是启发式参数；官方消融、宽扫及追加复测见[四张实验表及分析](../../B/experiments/paper_materials/2026-09-13_formal2_baselines/论文素材.md)，不能从较低门限直接推出整局时间更短。

### 4.4 有限光学覆盖兜底

主动测量达到预算、未收信号或探针纵向长度过小时，关闭主动测向并进入有限光学完成。先尝试当前区域圆心；若失败，将 $P$ 投影到首次示向的正交坐标系，以略外扩的有界矩形包住区域。将每个方向分为长度不超过28米的小格，按蛇形次序访问格心。

每个格内点到格心的距离满足

$$
r_{\rm cell}\le\frac{\sqrt{28^2+28^2}}2
=\frac{28}{\sqrt2}\approx19.799<20.\tag{13}
$$

因此，只要 $P$ 包含真源且光学按20米距离规则成功，有限格心中必有一次清除成功。该证明不要求继续接收 RF，不要求识别朝向，也不要求每次方向更新收缩固定比例。默认28米是证明条件；通用函数的其他 `step` 值不能无条件沿用式（13）。[B/geometry.py:207](../../B/geometry.py)、[B/policies.py:68](../../B/policies.py)。

认证清除失败、首次区域为空或有限覆盖耗尽时程序报错；保留旧区域可以避免主动擦除已知源，但若反馈已违反模型，不能再声称保证自动恢复。

## 5. 定向源负反馈几何

### 5.1 单次 no_signal 的信息边界

已知源的一次无信号意味着“超出实际半径，或处于定向背面”。例如源位于原点、朝东、半径1000米，在 $(-1,0)$ 检测仅距1米仍无信号。因此 Q4 不能据单次无信号排除检测点周围1000米圆盘，也不能删除该频道。

当前Q3通过`OmniNegativeCompletionPolicy`将真实阴性与同源成功锚点结合。设$a$处成功接收、$q$处实际返回无信号，则全向源满足$\|g-q\|>\rho\ge\|g-a\|$，从而

$$
(q-a)^Tg<\frac{\|q\|^2-\|a\|^2}{2}.
$$

程序取相应闭半平面并增加向外数值余量，保守裁剪位置外包；没有成功锚点时，不将一般单次阴性当成精确位置排除。该距离支配推理不适用于定向接收。Q4采用下述成对几何条件。`ProbeJointPolicy` 的150米负反馈冷却仅用于抑制附近可选共享测量，不是位置排除规则。[B/policies.py:23](../../B/policies.py)、[B/completion_sensing_policy.py:137](../../B/completion_sensing_policy.py)、[B/efficient_joint_policy.py:32](../../B/efficient_joint_policy.py)。

### 5.2 成对探针的构造

以最近实际收到示向度的检测点 $s$ 为原点，读数方向为纵轴 $u$，横轴 $v\perp u$。用 $t=\tan1.02^\circ$ 外包1.01°角锥；真源局部坐标满足 $x\ge0, |y|\le tx$。在当前多边形纵向投影 $[x_{\min},x_{\max}]$ 内取

$$
\ell=x_{\min}+0.15(x_{\max}-x_{\min}),\qquad
w=\min\{\ell\tan30^\circ,\ \max(\ell\tan1.02^\circ,40)\},\tag{14}
$$

并设置 $q_\pm=s+\ell u\pm wv$。若 $\ell\le10^{-3}$ 则转光学兜底；否则先测离当前位置近的一点。40米是横向目标，受两个几何界夹持，不是每轮固定横移40米。[B/efficient_joint_policy.py:71](../../B/efficient_joint_policy.py)、[B/bounded_width_policy.py:17](../../B/bounded_width_policy.py)、[B/interleaved_policy.py:119](../../B/interleaved_policy.py)。

### 5.3 双阴性截断定理

令 $k=w/\ell$。当 $k\ge t$ 且 $k^2+2kt\le1$ 时，对任一远侧候选 $g=(x,y)$、$x\ge\ell$，有

$$
\begin{aligned}
\|q_\pm-g\|^2-\|s-g\|^2
&=\ell^2(1+k^2)-2\ell x\mp2k\ell y\\
&\le\ell^2(1+k^2)-2\ell x(1-kt)\\
&\le\ell^2(k^2+2kt-1)\le0.
\end{aligned}\tag{15}
$$

两个探点均不比已成功接收的锚点远，故都在真实接收半径内。线段 $[s,g]$ 与纵向截线 $x=\ell$ 的交点的横向坐标为 $\ell y/x$，绝对值不超过 $t\ell\le k\ell$，所以交点位于 $[q_-,q_+]$。任何包含 $s$ 和 $g$ 的闭接收半平面均包含该交点，不可能把两个探点都置于严格背面。因而至少一个探点应接收到 `direction` 或 `near`。

**命题2。** 若上述同一对探点均返回真实 `no_signal`，可排除 $x\ge\ell$ 的候选；为保守处理边界，保留

$$
P\leftarrow P\cap\{g:u^T(g-s)\le\ell+10^{-6}\}.\tag{16}
$$

当前 $k\in[\tan1.02^\circ,\tan30^\circ]$ 满足条件。实现只在两点都阴性后截断，并使包含圆缓存失效；任一点有方向就用新角锥更新并结束本包，near 则立即清除。空截断记录异常并转兜底。[B/wide_probe_policy.py:9](../../B/wide_probe_policy.py)、[B/interleaved_policy.py:123](../../B/interleaved_policy.py)。

一对探测在任务调度意义上是原子的：不能测第一点阴性后就将其当作完整截断证据，也不能跨恢复重置这对探针的参数。包内允许已有的共享动作；它们不构成将源任务交还调度器。每源轮数跨任务累计，不能把“最多10轮”误写成每次恢复又有10轮。

此处没有推翻 Q1/Q2 中定向单点保收可能退化的结论。单点要求 $\exists q\ \forall\text{一致世界}\ \mathrm{recv}(q)$，成对论证要求 $\forall\text{远侧一致世界}\ [\mathrm{recv}(q_-)\lor \mathrm{recv}(q_+)]$，其中 $\mathrm{recv}$ 表示接收到信号，成功点可随世界改变。方向未知通过多点析取和负反馈解决，无须先估计唯一朝向。单点退化结论仍须保留 PLAN 的非共线候选等前提。

### 5.4 历史负反馈的凸性扩展（非当前默认）

`negative_hull_policy.py` 处理“两成功点 $a,b$＋一个负点 $q$”：对候选源 $g$，式（1）的接收集合为凸集，并包含 $g,a,b$。若 $q\in\operatorname{conv}\{g,a,b\}$，应接收而与阴性矛盾。非退化时由此得到排除锥

$$
g\in q+\operatorname{cone}(q-a,q-b).\tag{17}
$$

代码保留该锥的补半平面与 $P$ 的交，外放边界后取并集的凸包，近共线等情况保守跳过。凸包可能填回一些已排除位置，但不会由此删真源，所以仍是外包，非精确非凸后验。该模块只记录实际 RF 阴性，不把内部推断标签混入实测历史。[B/negative_hull_policy.py:10](../../B/negative_hull_policy.py)。

另有“一成功锚点＋两个历史负点”的距离支配与线段相交方法，与式（17）不同；其审计见 [定向审计](../q1q2/peer-audit/q34/audit-directional.md)。这些历史裁剪均未被 `bounded_candidates` 的两项实例启用，论文若介绍应列作可扩展机制，不能将其区域缩小或成绩计入当前主方案。

## 6. 时间导向的耦合调度与任务重排

### 6.1 扫描站与源服务共用任务集合

每轮建立

$$
\mathcal T_t=\{(\mathrm{survey},i,s_i):i\in U_t\}
\cup\{(\mathrm{source},c,z_c):c\in D_t\setminus C_t\},\tag{18}
$$

其中$z_c$是当前包含圆心，只作为服务位置代理。第二次正式方案在两题中均选择当前位置最近的任务：

$$
a_t=\mathop{\arg\min}_{a\in\mathcal T_t}\|p(a)-x_t\|_2.
$$

得到新反馈后重新构造任务集合。当前在线任务选择不执行2-opt改良，也不要求回到原点。该最近邻选择为启发式，不能认证整局最短时间。[B/adaptive_routes.py:7](../../B/adaptive_routes.py)、[B/joint_task_policy.py:82](../../B/joint_task_policy.py)、[B/interleaved_policy.py:51](../../B/interleaved_policy.py)。

该结构将定位绕行后的实际位置带回下一次规划。Q3 选中源后完成该源再重排；Q4 只完成一个定位包，再与剩余扫描/源任务竞争。Q4 全局中断计数达到默认16次时强制续做上次未完成源，主要约束额外绕行；有限结束还依赖不可重置的每源预算。[B/interleaved_policy.py:51](../../B/interleaved_policy.py)。

扫描任务在指定站对未清频道逐个测量，优先测当前频道以少切频；扫描阶段抑制可选共享和任务插入，near 的即时清除仍执行。对未知频道必须保持完整覆盖，对已知且已达认证精度的频道可免去重复扫描。[B/joint_task_policy.py:109](../../B/joint_task_policy.py)、[B/interleaved_policy.py:180](../../B/interleaved_policy.py)。

### 6.2 Q3 的面积先验与完工路程代理

Q3 从首次示向轴附近的有限纵向/横向点及圆心前后点生成候选，并排除距当前位置或已测点不足约1米的重复点。当前未启用扩展候选网格；候选先通过全向保收充分条件。[B/intelligent.py:99](../../B/intelligent.py)。

区域均匀面积先验只用于排序。实现将凸多边形三角剖分，每个三角形用三个正权节点积分；对二次多项式矩精确，所以可得到面积均值及协方差。线段退化采用最长线段的三点积分，点退化用单点。之后的非线性测向代理仅为积分近似，不能因低阶矩精确就称其风险估计精确。[B/completion_sensing_policy.py:12](../../B/completion_sensing_policy.py)。

设积分节点和权重为 $(g_i,\omega_i)$，均值为 $\mu=\sum_i\omega_i g_i$，区域协方差加正则项为 $\Sigma=\sum_i\omega_i(g_i-\mu)(g_i-\mu)^T+0.01I$，单位为平方米。对候选 $q$，令 $d_i=\max(1,\|g_i-q\|)$；将 $g_i-q$ 旋转90°后除以 $d_i$ 得到实现使用的横向向量 $n_i$，定义

$$
\sigma_i^2=(d_i\varepsilon)^2/3,\qquad
\Sigma_i'=\Sigma-\frac{\Sigma n_i n_i^T\Sigma}
{n_i^T\Sigma n_i+\sigma_i^2},\qquad
U(q)=\sum_i\omega_i\sqrt{3\lambda_{\max}(\Sigma_i')}.\tag{19}
$$

这里 $\varepsilon$ 用弧度。主评分为

$$
J_{\rm proxy}(q)=U(q)+0.08\left[\frac{\|q-x_t\|+1.5\|q-z_c\|}{5}+5\right].\tag{20}
$$

第二段距离以1.5的余程权重模拟测量后到预期完工位置的剩余路程；$z_c$ 不是源真值。0.08 是把秒折算到米量纲评分的经验权重。协方差公式和除以3的噪声代理不表示已验证独立、高斯或均匀噪声；式（20）也没有完整模拟后续切频、可变测量数、成功/失败清除与扫描改序。因此应称“时间导向的有限候选测向评分”，不称连续最坏误差或整局虚拟时间的精确最优。[B/completion_sensing_policy.py:73](../../B/completion_sensing_policy.py)。

### 6.3 同位置共享测量

定位或清除到达的位置可顺便测其他已知未清源，默认至多6个，禁止递归共享。候选过滤包含已足够精确、重复近点、距离过远及交会角太小等条件；Q4 再用150米阴性冷却抑制短距离重复无效共享。它只减少可选服务，不能删除未知频道的覆盖任务。共享的每次 RF 仍付5秒与可能的切频费，不能算成免费信息。[B/joint_task_policy.py:34](../../B/joint_task_policy.py)、[B/efficient_joint_policy.py:43](../../B/efficient_joint_policy.py)。

### 6.4 已知源的距离证书跳扫

若当前已知未清源由 $D(z_c,\widehat r_c)$ 包含，拟扫描点 $q$ 满足

$$
\|q-z_c\|>1500+\widehat r_c+10^{-5},\tag{21}
$$

则由反三角不等式，对所有 $g\in P_c$ 均有 $\|q-g\|>1500$，故无论类型、朝向、实际半径如何都收不到信号，可以不发这条扫描 RF。

实现仅在 `_surveying` 且频道已有区域时触发，返回内部标签 `certified_no_reception`；不伪造服务器响应，不修改客户端真实位置、频道或时钟。Q4 可把该推断点记入冷却记忆，但没有据此做位置阴影裁剪。[B/coupled_dispatch_policy.py:73](../../B/coupled_dispatch_policy.py)。

`surveyed` 因而是“已处理的站点记录”，不等于实际 RF 次数。未知频道不满足跳扫前提，在覆盖站仍真正测量。当前简单 range 删除会改变后续频道、记忆及调度，不能直接套用历史 faithful/deferred 变体“相同计划下整局费用不增”的更强结论。

### 6.5 路线与发现优先的扩展边界

`coupled_dispatch_policy` 另有 `arc` 与 `locked`：前者为任务设置入口、出口，比较有向转移；后者固定站序并插入源任务。反转有向路线时，内部弧方向也改变，代码显式计入该差值，不能仅用对称2-opt的两条边公式。当前两主候选 `base` 在入口直接转父类，不执行这两类优化。[B/coupled_dispatch_policy.py:9](../../B/coupled_dispatch_policy.py)。

`discovery_priority_policy` 用384个内部位置、128个边界位置，Q4 每位置12朝向构造有限探索先验，按未扫假设的可见比例奖励候选扫描任务。这是启发式发现收益，样本耗尽不提供“区域已无源”的证书，也不替代连续站点扫描。审计修复后已彻底删除 `clear_weight` 及其隐藏重排开关：已达认证精度的已知源原本就免去后续扫描，不能因先清它再重复奖励一次“省去未来 RF”。当前主候选不使用 discovery 排序。[B/discovery_priority_policy.py:15](../../B/discovery_priority_policy.py)、[修复记录](../../code-review/fix-discovery-clear-weight.md)。

`coverage.py` 的格点生成与静态2-opt、`intelligent.genetic_route` 及 `route_algorithms.py` 的遗传/免疫/蚁群/粒子群/烟花等属于布局或路线对照，不是主任务调度器。格点函数接受的任意间距不自动获证；随机算法均带既定初始化/局部改良，不能仅凭算法名宣称最优。[B/coverage.py:28](../../B/coverage.py)、[B/intelligent.py:9](../../B/intelligent.py)、[B/route_algorithms.py:232](../../B/route_algorithms.py)。

路线审计已将近似格点误认成精确格点的下界问题改为 `Fraction` 精确判倍数；插入贪心预算用尽返回完整可行排列。比较预算统计全评分和增量比较，不等于CPU预算；`certified_optimal` 只在指定静态开路线模型中比较有效下界及数值容差，绝不认证动态 Q3/Q4 总时间最优。[B/route_algorithms.py:32](../../B/route_algorithms.py)。

## 7. 时间账本与结果统计

令 $L$ 为所有被接受动作造成的总直线移动长度，$M$ 为实际 RF 测量数，$S$ 为 RF 切频数，$C_s,C_f$ 分别为成功和失败清除数。理论虚拟时间账本为

$$
T=\frac L5+5M+S+5C_s+3C_f.\tag{22}
$$

成功清除的5秒已经包含光学定位与清除，不再加3秒。失败清除也会移动到请求坐标；clear 不改 RF 频道。每个测点扫描20频道须20次 RF，当前频道优先时是100秒测量＋19秒切频。`enter/exit` 不增加虚拟时间，但未知数情况下最后一个源清除后的必要排查仍在总时间内。

费用合同见 [附件2文本:84](../../mock/materials/附件2.txt) 及第4节后续条目；实现见 [B/simulator.py:77](../../B/simulator.py)。本地 World 对每段移动时间独立舍入到微秒再累计，复核应按逐动作整数账本；不能用最终总路长一次舍入要求完全相等，也不能把本地具体舍入算法当作官方逐段舍入方式已获证明。

客户端采用服务器返回的累计虚拟时间，完整解析并成功写日志后才提交确认状态；仅 measure 更新 RF 频道，clear 只更新位置等相应状态。传输失败或响应解析失败不映射成无信号，未决动作锁停后不能随意继续发新动作；重试复用同一请求标识和不可变请求体。[B/client.py:157](../../B/client.py)、[协议修复记录](../../code-review/q34-protocol-fix.md)。

由此可见，少一次试探失败不必恰好省3秒：位置、后续测向和任务顺序会改变。站数更少、静态路径更短、局部不确定度更小均不是整局支配关系。

当前实验表按每局等权统计。设方案共$m$局，第$i$局清除$C_i$个源、累计官方虚拟时间为$T_i$，真实程序耗时为$r_i$，则

$$
\overline C=\frac1m\sum_{i=1}^m C_i,\qquad
\overline t=\frac1m\sum_{i=1}^m\frac{T_i}{C_i},\qquad
\overline r=\frac1m\sum_{i=1}^m r_i.\tag{23}
$$

$r_i$取官方退出响应与进入响应的`real_timestamp_ms`之差并换算成秒。各方案的时间偏移为$(\overline t/\overline t_0-1)\times100\%$，程序时间同理。基准为各题第二次正式采用方案的既有演练数据，不把单局正式成绩混入均值；所有实际组别、局数和参数见[四表素材](../../writing-kit/kit-q34.md)。各局为新的官方案例，平均清除数差异反映案例构成，不能等同于清除能力差异。

## 8. 停止准则与有限结束论证

### 8.1 两种合法完成条件

1. **公开上限完成：**实际成功清除了16个不同频道，故已清除全部源。
2. **覆盖排尽完成：**全部必要扫描站已处理，所有已发现源均成功清除，仍未知频道在全部覆盖站完成真实检测。

发现16个频道时，可以取消剩余发现站，因为不可能存在第17源；但已知未清源仍须完成。清除10个、连续无信号、有限假设样本为零或队列暂时只含源任务，都不是独立停止依据。[B/efficient_joint_policy.py:15](../../B/efficient_joint_policy.py)、[B/joint_task_policy.py:128](../../B/joint_task_policy.py)、[B/interleaved_policy.py:200](../../B/interleaved_policy.py)。

**命题3（覆盖排尽的完备性）。** 假设使用已获证站点、未知频道完整检测且已发现源全部清除。如果退出后仍有未清源，则其频道一直未发现；由第2节覆盖结论，至少一个已测站应返回方向或 near，与始终未发现矛盾。故不存在遗漏源。

该论证允许已知源的精确免测和式（21）跳扫，因为频道一经发现便不再成为未知；这些规则均不作用于仍未知频道。不能仅凭 `len(surveyed[ch])` 判定实测覆盖，要结合规则的适用对象。

### 8.2 有限动作与时间上限的不同层次

Q3 每个主循环要么消耗一个剩余站，要么完成一个已知源；站数有限、源最多16个，每源主要主动测量至多2次，随后光学格数有限。Q4 每个源包或者完成源、进入有限兜底，或者消耗一次不可恢复的轮数；每源至多10轮，每轮至多两次主要 RF。共享测量每次最多6个且禁止递归，站点任务也有限。因此在正确反馈、区域保持包含且操作可执行的条件下，不能无限重复定位或无限等待未知源数达到16。[B/completion_sensing_policy.py:114](../../B/completion_sensing_policy.py)、[B/interleaved_policy.py:99](../../B/interleaved_policy.py)、[B/joint_task_policy.py:50](../../B/joint_task_policy.py)。

“最多2次/20次”限于源服务的主要主动 RF，不包括扫描与其他源服务时的共享测量。有限结束不表示每轮直径减半；纵向分位0.15及接收更新也不支持这种收缩率。

历史 [B/WIDE_PROBE_GUARANTEE.md](../../B/WIDE_PROBE_GUARANTEE.md) 给出了在站点范围、最多10轮主探测、共享上限、光学路径和全局至多24次中断等限定下的335136虚拟秒、9766请求的宽松计数界；既有审计核对了继承结构，但未独立重建全部最坏动作轨迹。本文将其列为**有条件的既有上界推导**，不将其作为本次新认证，也不推广到任意构造参数或现实1200秒期限。当前默认中断上限16小于该论证允许上限，仍须保留其他前提。

## 9. 当前版本的代码与实验核验

当前工厂仅注册Q3最近邻65米/2轮与Q4最近邻35米/默认参数。核心定位、覆盖和负反馈实现与第二次正式冻结包一致；统一入口支持配置核对，并记录所有请求与真实时间戳。

整理后的代码在原Windows环境回放27个已保存官方案例，5746条请求的端点、频道和位置逐条匹配，最大位置差为0。该回放没有联网或产生新模拟案例，结论是已记录轨迹上的实现一致性，不能替代新场景性能测试。记录见[回放审计](../../B/cleanup_formal2/replay.json)。

当前四表纳入927个不同的官方演练案例，逐局核对官方成绩与进入/退出时间戳；完整配置、范围、分组和证据见[论文实验素材](../../writing-kit/kit-q34.md)。历史基线数据仅作为表中明确标记的对照，不作为当前代码的默认参数。

## 10. 假设、局限与论文表述边界

| 性质或简化 | 采用理由 | 对结论的影响 |
|---|---|---|
| 静止源、固定半径/朝向、可靠合法反馈 | 支持跨时刻约束交集与成功锚点 | 源运动、间歇发射或无信号故障会破坏负反馈与覆盖排尽推理 |
| 1.01°总角外包与64边圆盘外包 | 容纳已声明角误差/常见量化，保持凸多边形计算 | 外包偏大；数值余量不是任意舍入及病态输入的形式化保证 |
| 不维护完整 $(g,\rho,n)$ 后验 | 减少状态维数，保留有证明的局部约束 | 信息未充分利用，不能称“精确物理定位区域” |
| MEC/全顶点包含与光学格心覆盖 | 将位置不确定性转为可执行清除条件 | 精确度不足时仍可有限完成，但可能消耗更多移动和失败清除 |
| 面积先验、协方差、有限候选、最近邻任务选择 | 提供计算可控的下一步选择 | 不提供真实概率置信区间、全局最优或逐场景时间支配 |
| 固定获证站点 | 连续覆盖与具体坐标绑定 | 改点、投影、舍入或部分删站后须重新证明，不能只保留站数标签 |
| 试探门与共享冷却 | 已测场景下的时间/失败权衡 | 65/35米、40米横向目标、0.15分位、150米冷却均非物理定理常数 |
| 有限预算与异常退出 | 避免无限主动测向和不确定协议续跑 | 有限算法结束不等于任意剩余现实时间内完成；异常不是全清 |

论文可概括为：**在最小接收半径约束下，以七站最近距离覆盖解决全向发现，以二十一站局部可接收凸包解决任意朝向发现；通过有界误差位置外包和成对负反馈逐步收紧已知源区域，按20米包含条件清除，并用有限光学覆盖完成剩余不确定性；扫描与源服务依据实时公开状态共同重排，以降低实际完成时间。** 随后应紧接说明：布点覆盖和双阴性截断有几何依据，路线、测向评分和提前试探为启发式，性能数字按实验配置报告。

### 10.1 当前文件指纹

核心源码、运行包与第二次正式版本的一致性见[B/cleanup_formal2/REPORT.md](../../B/cleanup_formal2/REPORT.md)。运行包逐文件SHA-256保存在[B/dist/manifest.json](../../B/dist/manifest.json)，原始记录不因代码清理改写。
