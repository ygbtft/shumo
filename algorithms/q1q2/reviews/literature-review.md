# 2026 国赛 B 题：有界示向误差定位与检测点选择文献调研备忘录

文献检索与核对日期：2026-09-11。本文提供 Q1/Q2 的文献依据与方法适用范围；当前推导见 [Q1/Q2 模型正文](../../../paper/modeling-q1q2.md)。

**一句话核心发现：我们的“±1°前向角锥交集＋最坏定位直径”与 Tokekar–Isler（2013）直接契合，但其全域静态布点保证不能直接用于条件化的第二点选择；最小覆盖圆、20 米清除判据和未知接收半径下的保收域，需要我们另行建模与证明。** [作者版，2013][C13]

## 一、核心文献精读

### 1. 文献版本与阅读证据

**TOKEKAR P, ISLER V. Sensor placement and selection for bearing sensors with bounded uncertainty[C]//2013 IEEE International Conference on Robotics and Automation. 2013: 2515–2520. DOI: 10.1109/ICRA.2013.6630920.** [作者书目页，2013][CH13]；[机构书目与摘要，2013][CM13]。

已下载并通读作者主页提供的 **6 页会议作者版**，查看了公式和图示的页面渲染。下文“会议 PDF p.3”等均指该文件内的页序／页脚编号，**不冒充已经逐页核对过的 IEEE 正式排版页码**。[全文，2013][C13]

另取得 **TR 12-006，2012-02-24**：文件共 32 个 PDF 页面，其中正文／附录印刷页码为 1–30，前有封面和空页；选读了模型、下界证明、布点构造及附录 C。它是会议论文指向的长证明版本，不能把 2012 技术报告与 2013 会议论文当成两项独立成果。[技术报告，2012][T12]

IEEE Xplore 的当前工具访问未返回可读正文；核心结论以作者版和技术报告核对。Google Scholar 查询未能取得可读结果，故**没有声称核对了 Scholar 被引总数或完整被引列表**；后续追引改用 Semantic Scholar 的 DOI 检索结果定位候选，再看论文或出版社参考文献。ResearchGate 搜索页虽提供文本，但本备忘录不以其自动摘要或“相关论文”列表确认引用关系。

### 2. 确切问题、误差集合与量词

原问题在边长为 \(d\) 的正方形 \(A\) 内布置传感器，目标和传感器均在 \(A\)，不考虑遮挡。测量为

\[
\theta_i^m=\theta_i^t+n_i,\qquad n_i\in[-\alpha,\alpha],\qquad
\widehat P(S,\theta^m)=\bigcap_iW(s_i,\theta_i^m).
\]

\(W\) 是全开角 \(2\alpha\) 的**无界前向楔形／角锥**。它代表读数的逆像，并非固定视场。原文定义的交集没有再与 \(A\) 相交，且明确允许无界。主度量为面积或直径，不是均方误差，也不是最小包围圆半径。会议 PDF p.3，§III-A、§III-B、式 (1)：

\[
U_D(S)=\max_{x\in A}\max_{\theta^m\in\Theta(x)}
\operatorname{diam}\widehat P(S,\theta^m).
\tag{文献式1}
\]

面积指标相应替换为 \(\operatorname{area}\)。**最坏情况同时遍历真实位置与所有合法读数**，不是只取零噪声，也不是平均位置误差。[作者版，2013，p.3][C13]

可用于方法说明的短引文是 “unknown but bounded noise”（p.1）和 “We use worst-case intersection as the uncertainty measure.”（p.3，Fig.3）。这里只短引，其他内容均作释义。[作者版，2013][C13]

**对 Q1/Q2 模型 的解释：**令 \(\alpha=1^\circ\) 就得到我们的测向集合模型。既然集合来自有界误差，集合求交无须噪声独立、零均值或高斯；这不是声称误差没有相关性，而是没有额外相关结构时考虑全部界内组合。我们对“同地点同源读数固定”的处理来自题设，原文没有给出这一重访合同。[Q1/Q2 模型正文](../../../paper/modeling-q1q2.md)

### 3. Placement 与 selection 到底做了什么

**Placement：**给定允许不确定性，尽量少放传感器；构造三角格点并在正方形边界补点。作者报告双准则近似：当 \(0<\alpha\le\pi/4\) 且满足目标精度条件时，数量至多为最优的 9 倍，直径／面积至多为相应目标的 5.88／7.76 倍。它允许数量和精度同时放宽，**不是“同样数量的传感器下三角网格已被证明最优”**。作者结尾仍将三角布点是否最优列为后续问题。[作者摘要，2013][CH13]；[会议全文，2013，Theorem 1、§VI][C13]

**证明的几何骨架（技术报告 §4、§5，附录 A、B）：**空圆给任何布点的下界，局部三角形／六边形构型给上界，然后比较覆盖全域所需数量。若存在半径 \(r\) 的无传感器圆盘，其圆心是合法目标位置，选择零测量误差可使半径 \(r\sin\alpha\) 的圆盘包含在角锥交集中，因此

\[
U_D(S)\ge 2r\sin\alpha,\qquad U_A(S)\ge\pi r^2\sin^2\alpha.
\tag{Lemma 2}
\]

若最大空圆半径为 \(r^*\)，且 \(d>2r^*\)，则传感器数下界为 \((d-2r^*)^2/(\pi r^{*2})\)。构造网格的边长分别取

\[
r=\frac{U_D^*}{2\sin\alpha},\qquad
r=\frac{\sqrt{U_A^*/\pi}}{\sin\alpha}.
\]

两式是**分别优化直径与面积时的两种参数设定**，不能随意把两个目标数值同时代入同一张网格。[技术报告，2012，Lemma 2、Corollaries 1–2、§5][T12]

**Selection：**已有上述布点且有粗定位，选择包围目标的局部构型查询。\(0<\alpha<\pi/6\) 用三角形的 3 个顶点；\(\pi/6\le\alpha\le\pi/4\) 用 6 个传感器，六边形分析要求目标在中心半径 \(r/\sqrt3\) 的圆内。查询数为常数，但找到适用局部构型需要先验定位；不是任意三个传感器，也不是只增加第二次测量。[会议全文，2013，p.5 Lemmas 3–4、p.6 Corollary 3][C13]

针对本题 \(1^\circ<\pi/18\)，三角形内目标的局部上界还可直接读出

\[
U_D\le11.35r\sin\alpha,\qquad U_A\le23.46r^2\sin^2\alpha.
\]

这里 \(r\) 是等边三角形边长；**不能拿它代替我们任意两检测点的基线**。这组局部界比全角度统一常数更贴近本题，但成立前提也更强。[作者版，2013，p.5 Lemma 3][C13]

大噪声端另有定性结论：\(\alpha\ge\pi/2\) 时，任意有限布点都存在使纯角锥交集无界的合法读数；\(\pi/4<\alpha<\pi/2\) 的扩展分析只保证在给定条件下用更多格点获得有界交集，不能把5.88／7.76倍常数扩展过去。[会议全文，2013，p.4 Lemma 1、p.5 Lemma 5][C13]

### 4. 原文数值保证必须附带的核对说明

**以下是本次独立复算发现的问题，不是作者发布的勘误。**不能无标注改写后仍称“原文定理”。

1. **精度条件有代数不一致。**会议 Theorem 1（PDF p.3）及 TR Theorem 1（印刷 p.6／PDF p.8）实际排印为 \(U_D^*<d/(7\sin\alpha)\)，面积条件为 \(U_A^*<\pi d^2\sin^2\alpha/196\)。但 TR 附录 C 的计数论证使用 \(d>14r\) 和 \(r=U_D^*/(2\sin\alpha)\)，其代数等价条件应为 \(U_D^*<d\sin\alpha/7\)。两者不同；已通过页面渲染确认，不是文本抽取误读。[原件，2013][C13]；[TR，2012，印刷 p.28／PDF p.30][T12]
2. **TR 式 (9) 的不等号方向。**原文写 \(n^*\le(d/r-2)^2/\pi\)。由前一行 \(n^*\ge(d/r^*-2)^2/\pi\)、\(r^*\le r\) 及 \(d>2r\)，应推出 \(n^*\ge(d/r-2)^2/\pi\)。后续 9 倍比较也需要这个下界方向。[TR，2012，附录 C，式 (9)][T12]
3. **“14”还不足以支持展示的粗计数不等式。**令 \(t=d/r\)，TR 式 (8) 的上界为 \(a(t)=2t^2/\sqrt3+(11+2/\sqrt3)t+19\)，对应 9 倍下界为 \(b(t)=9(t-2)^2/\pi\)。本次复算：\(a(14)=415.4871>b(14)=412.5296\)，且差值在略大于 14 时仍为正；该粗比较需要 \(t\gtrsim14.12084\)。取 \(d/r\ge15\) 足以修复**这个计数步骤**，不等于已经重新证明全文的所有常数。离散精确计数可能更紧，但此处未据此重建定理。[公式来源：TR，2012，附录 C，式 (8)–(9)][T12]

另有**区域口径提醒**：TR 附录 C 最后一种大角噪声情形，在工作区边界附近使用了与 \(A\) 边界相交的论证；会议 Lemma 1 后又在讨论纯角锥无界时出现工作区尺度的有限不确定性描述。这些段落不宜用来模糊“纯角锥交集”和“工作区裁剪交集”。本题 \(1^\circ\) 属于小角度分支，Q1/Q2 模型 明确区分 \(P\) 与 \(K\) 的做法更适合复现。[TR，2012，印刷 p.30／PDF p.32][T12]；[会议全文，2013，p.4][C13]

**论文使用建议：**引用其集合模型、对抗最坏指标和三角布点的近似思想；5.88／7.76／9 写为“该文报告的双准则保证”，不要作为我们算法的数值认证。若要实际采用其布点参数，必须独立核对所用分支和边界处理。

### 5. 圆覆盖、复杂度和保证的边界

原文的“圆”主要用于**空圆下界、覆盖工作区以及局部目标范围**；空圆论证是 \(D(x,r\sin\alpha)\subseteq\widehat P\)，方向是内含，不是用半径 \(\operatorname{diam}(\widehat P)/2\) 的圆覆盖它。本次没有在核心全文发现 Q1/Q2 模型 的直径圆覆盖充要条件、Jung 界、\(\kappa/\eta\) 或20米清除定理；不能将这些归给 Tokekar–Isler。[作者版，2013，§IV–V][C13]；[TR，2012，附录 A.2][T12]

论文给出网格数量规模 \(O((d/r)^2)\)（精度细于工作区尺度时），以及局部常数查询数。**这不是计算任意布点连续最坏值的运行时间界**，更不是我们内外层网格求解器的复杂度。按规则枚举网格点具有随输出点数线性增长的成本，是本备忘录的实现推断；论文没有提供解决任意连续第二点问题的精确算法或 NP-hard 证明。[作者版，2013，Lemma 6、Corollary 3][C13]。一般三角定位布点问题的 NP-hard 与整数规划框架应另引 Tekdas–Isler（2010），不能移植成“本题二维单步问题已证明 NP-hard”。[R5，2010][R5]

## 二、相关文献清单（表格）

共 15 项，含核心论文及 14 项相关文献。证据等级：“全文核对”指读到了所述模型／定理所在部分，不代表所有相关论文均逐页精读；“摘要”不用于推断未读的算法细节。书目信息尽量以作者、机构、出版社或 Crossref 核对。**“同一研究方向”与“确实引用核心论文”分开标注。**

| 编号 | 标题、作者 | 年份与出处 | 一句话贡献及与本题的关系 | 阅读证据／与核心的关系 |
|---|---|---|---|---|
| R1 | **Sensor Placement and Selection for Bearing Sensors with Bounded Uncertainty**；Pratap Tokekar, Volkan Isler | **2013**, ICRA: 2515–2520；[DOI][R1] | 有界方位角锥、交集直径／面积及全域布点双准则近似；Q1、Q2 的直接方法出处。 | 6页作者版精读；TR证明选读；常数条件问题见第一节。 |
| R2 | **Set membership localization of mobile robots via angle measurements**；Andrea Garulli, Antonio Vicino | **2001**, IEEE Trans. Robotics and Automation, 17(4): 450–463；[DOI][R2] | 用有界视觉角误差估计机器人位置及不确定区域，并递归处理动态定位；Q1 集员解释、Q3 序贯集合更新。 | [作者机构摘要][G01]；全文未取得，不引用其具体公式；是核心论文参考文献。 |
| R3 | **Robust Autonomous Robot Localization Using Interval Analysis**；Michel Kieffer, Luc Jaulin, Éric Walter, Dominique Meizel | **2000**, Reliable Computing, 6(3): 337–362；[出版社][R3] | 区间分析用于非线性全局定位和离群值处理；支持 Q2 连续最坏值认证的可选方向。 | 出版社摘要；对象是超声距离测量，不是方位角模型，不能直接照搬。 |
| R4 | **Sensor Selection in Arbitrary Dimensions**；Volkan Isler, Malik Magdon-Ismail | **2008**, IEEE Trans. Automation Science and Engineering, 5(4): 651–660；[DOI][R4] | 对已给定凸多面测量，平面上至多4个传感器可取得全交集面积的2倍近似；Q1 冗余测量压缩、Q3 多观测选择。 | [前身技术报告全文，2007][IM07]与[期刊机构摘要，2008][IM08]；核心论文直接引用。面积保证不是直径保证。 |
| R5 | **Sensor Placement for Triangulation-Based Localization**；Onur Tekdas, Volkan Isler | **2010**, IEEE Trans. Automation Science and Engineering, 7(3): 681–685；[DOI][R5] | 一般布点的整数规划框架及困难性，并给方位双站几何代理的常数近似；Q2 几何准则、Q3 候选站组合。 | [作者全文][TI10]；核心论文直接引用。 |
| R6 | **Optimal sensor placement for target localisation and tracking in 2D and 3D**；Shiyu Zhao, Ben M. Chen, Tong H. Lee | **2013**, International Journal of Control, 86(10): 1687–1704；[DOI][R6] | 以 FIM 和框架理论分析测向／测距／RSS 的最优几何；Q2 的高斯辅助对照及“正交”成立条件。 | [2012预印本模型／定理][Z12]、[2013正式书目][Z13]；相关工作，未证实直接引用 R1。 |
| R7 | **Cautious Greedy Strategy for Bearing-only Active Localization: Analysis and Field Experiments**；Joshua Vander Hook, Pratap Tokekar, Volkan Isler | **2014**, Journal of Field Robotics, 31(2): 296–318；[DOI][R7] | 主动选择测量位置，计入行走和测量耗时，并分析歧义及性能界；Q2 next-best-view、Q3 时间目标。 | [作者全文][VH14]，§3 的高斯／EKF模型与定理段落已核对；同团队相关工作，非本次确认的 R1 直接被引。 |
| R8 | **Minimizing Uncertainty through Sensor Placement with Angle Constraints**；Ioana O. Bercea, Volkan Isler, Samir Khuller | **2016**, CCCG: 287–294；[完整预印本][R8] | 将成对传感器的角覆盖与距离／可见性限制结合，给双准则近似；Q2 夹角约束、Q3 组合布点。 | 完整预印本模型与结果核对；[作者出版目录][BK16]确认会议年份。未在所读全文参考文献中发现 R1，不标为直接后续引用。 |
| R9 | **Aerial Radio-Based Telemetry for Tracking Wildlife**；Haluk Bayram, Nikolaos Stefas, Volkan Isler | **2018**, IROS: 4723–4728；[DOI][R9] | **有界角锥求交，以面积阈值和总定位时间在线选点**，并作竞争分析和外场验证；Q2、Q3 最贴近的扩展对照。 | [机构摘要][B18]；会议全文未取得；检索到 TR 17-004（2017）但下载失败。Semantic Scholar 报告其引用 R1，属索引确认、未核会议文末。 |
| R10 | **Trajectory Optimization for Target Localization With Bearing-Only Measurement**；Shaoming He, Hyo-Sang Shin, Antonios Tsourdos | **2019**, IEEE Trans. Robotics, 35(3): 653–668；[DOI][R10] | 根据几何可观测性导出受航向约束的一步最优机动；Q2 观测点／运动约束对照。 | [作者稿全文][H19] §III–IV及仿真噪声说明；不是有界角锥直径优化，未证实直接引用 R1。 |
| R11 | **Particle filter-based aerial tracking for moving targets**；M. Koray Yılmaz, Haluk Bayram | **2023**, Journal of Field Robotics, 40(2): 368–392；[出版社][R11] | 将有界离散测向区域与粒子滤波、doubling 选点结合用于移动无线电目标；Q3、Q4 的动态扩展参考。 | 摘要及文末参考文献可读，方法全文未取得；**出版社文末明确列出 R1**。2022-11-26先在线，正式卷期为2023。 |
| R12 | **Sensor Selection via Convex Optimization**；Siddharth Joshi, Stephen Boyd | **2009**, IEEE Trans. Signal Processing, 57(2): 451–462；[DOI][R12] | 传感器子集选择的凸松弛、舍入与实例性能界；Q3 组合选择的统计模型备选。 | [作者全文][JB09] §I、§III；独立同分布零均值高斯线性测量，不能给本题 \(J\) 直接提供保证。 |
| R13 | **Near-Optimal Sensor Placements in Gaussian Processes: Theory, Efficient Algorithms and Empirical Studies**；Andreas Krause, Ajit Singh, Carlos Guestrin | **2008**, Journal of Machine Learning Research, 9: 235–284；[期刊页][R13] | 借助互信息的次模结构分析传感器选择并给相应近似保证；Q3 信息量基线。 | [全文][K08]和期刊摘要；保证有模型条件，非“所有贪心选点都近最优”。 |
| R14 | **Smallest enclosing disks (balls and ellipsoids)**；Emo Welzl | **1991**, New Results and New Trends in Computer Science, LNCS 555: 359–370；[DOI][R14] | 固定维度随机增量最小包围球算法；Q1 最小覆盖圆及其支撑点的算法出处。 | [作者全文][W91]及[作者书目][WB91]；应独立于 R1 引用。 |
| R15 | **Ueber die kleinste Kugel, die eine räumliche Figur einschliesst**；Heinrich Jung | **1901**, Journal für die reine und angewandte Mathematik, 123: 241–257；[DOI][R15] | 直径与包围球半径的经典界，平面为 \(R\le d/\sqrt3\)；Q1 反例尺度、Q2／Q3 清除阈值。 | 原文书目核对，**未精读德文原件**；平面定理另由[2024数学论文摘要][J24]核对，Q1/Q2 模型已有自足证明。 |

### 追引结论与检索局限

本次使用的 [Semantic Scholar DOI 查询接口][SS13]返回 R9、R11、Tokekar 的2014博士论文及一篇2019相机网络研讨会论文。**索引结果不是完整被引史，也不是内容继承的证明。**R11 的直接引用已由出版社参考文献复核；R9 的引用关系目前仅由索引确认。2019研讨会论文[原件参考文献第10项][AN19]也明确引用 R1，但与 B 题建模联系弱，未挤占主表名额。

R8 与 R10 虽然时间更晚且方法相关，本次证据不支持称其为“引用 R1 的改进”。尤其 R8 的 \(\alpha\) 是**期望交会角的下限**，R1 的 \(\alpha\) 是**测量误差半宽**，符号同名但含义不同。[R8，2016，§1.1][R8]；[R1，2013，§III-A][C13]

检索覆盖 bearing-only／AOA、bounded-error／set-membership、guaranteed localization、sensor placement／selection、GDOP、active localization／next-best-view、最小包围圆与 Jung；主要采用标题检索、作者资料、前向被引和核心参考文献反向追溯。没有证据证明“国赛命题人以 R1 为理论源头”：可说**高度相关的直接理论依据**，不写未经证实的命题来源。

## 三、与我们建模的对照

### 1. 保留、补充引用与需要避免的移植

| Q1/Q2 模型位置／现有做法 | 文献核对 | 建议 |
|---|---|---|
| §2，\(P=\cap W_i\)，转半平面求交 | 与 R1 模型一致；R2是更早集员角定位工作。 | 保留。称“有界角误差的集合可行域”，给 R1、R2 引用。窄角锥交集**有界时**才是有界凸多边形，不能省略无界／退化状态。 |
| §3，直径、最小圆、Thales检验、Jung界 | 原文只以直径／面积衡量不确定性，不能支持 \(R=d/2\)。 | 保留自足证明；最小圆算法引 R14，半径界引 R15。直径圆覆盖失败不等于无法用稍大的圆覆盖。 |
| §0.5，同点固定、异点未知有界函数 | 与集员框架相容，但不是原文已处理的重访模型。 | 保留；同点重测不缩小集合，不能套用独立高斯重复观测的信息叠加。 |
| §5，首次反馈后的 \(F\)、未知固定 \(\rho\)、保收域 \(C_{\rm sig}\) | R1没有有限接收半径、near或共享未知\(\rho\)；R8只有其另行规定的距离／角覆盖限制。 | 属于本题的实质建模适配；引用相关思想，但候选域公式必须自己证明。 |
| §6，\(J(q)=\sup_o\operatorname{diam}K_o(q)\) | 与 R1 的对抗目标一致，但位置范围、信息状态、决策量不同。 | 写“条件化的一步稳健观测设计”，不写“直接采用该文最优布点算法”。 |
| §6.2，共同反馈的不可区分点对 | 是将外层读数上确界转成成对歧义的等价表达；核心未给出此求解入口。 | 作为本文推导亮点，保留量词交换和near分支证明；不声称不可区分性思想首次出现。 |
| §6.6、附录B，面积线性化和GDOP | 与 R5、R6 的几何结构相关，但度量不能混名。 | v3 已将GDOP降为可选辅助，方向正确；用户背景中的“直径＋GDOP选择”已不是当前主模型。 |
| §7，内层源采样＋外层站点网格／局部细化 | 不具备 R1 的解析全域近似定理。 | 保留 `NUMERICAL_CANDIDATE`；细化稳定不等于保证误差、全局最优或近似比。 |
| §3.7、§6.9，20米清除三态 | R9已有“定位到阈值”的在线思想，但其摘要使用面积阈值。 | 我们应突出**阈值的操作语义和几何充要判据**，不是仅突出多加一个数值阈值。 |

各文献主张及来源见第二节；本表对 Q1/Q2 模型 的评价是本次比较判断。

保收域是本文与这些文献的一个具体差别。对首次全向direction后的 \(F\)，Q1/Q2 模型推导

\[
C_{\rm sig}=Q\cap\bigcap_{p\in F}D\!\left(p,\max\{1000,\|p-S\|\}\right).
\]

这里首次正反馈已排除 \(\rho<\|p-S\|\) 的世界，因此统一取1000米只能得到保守子集。R1的全域无接收距离模型不能替代这个条件化步骤；R8中的已知距离阈值也不等于共享未知接收半径。[Q1/Q2 模型正文](../../../paper/modeling-q1q2.md)；[R1，2013][C13]；[R8，2016][R8]

### 2. 第二点究竟优化什么：四类准则不可互换

以下 \(K_o(q)\) 都使用 Q1/Q2 模型 的完整物理条件集合；同一个比较实验必须固定 \(F\)、候选域、误差半宽、near合同和反馈可实现条件。

| 准则 | 一个清楚的定义 | 它回答的问题 | 本题取舍 |
|---|---|---|---|
| 最坏直径 | \(\inf_q\sup_o\operatorname{diam}K_o(q)\) | 两次观测后最远还能混淆多远的两个源位置？ | 当前Q2主目标；与R1最直接衔接。 |
| 最坏覆盖半径 | \(\inf_q\sup_o\min_c\sup_{p\in K_o(q)}\|p-c\|\) | 看到读数后再选一个落点，最坏误差能多小？ | 比直径更直接连接20米清除；不能将 \(\min_c\) 放到反馈前。 |
| 最坏面积 | \(\inf_q\sup_o\operatorname{area}K_o(q)\) | 剩余可行位置的平面范围能多小？ | 可作R9风格基线；细长集合可能面积很小而仍不能清除。 |
| 高斯A／D／E准则 | 最小 \(\operatorname{tr}I^{-1}\)、最大 \(\log\det I\)、最大 \(\lambda_{\min}I\) | 在指定统计／局部模型下改善总方差、椭圆面积或最差方向信息。 | 必须另给概率噪声和目标位置的处理方法；不能充当全部有界误差的保证。 |
| 信息增益 | \(\mathbb E_o[H(p\mid\mathcal H)-H(p\mid\mathcal H,o,q)]\) | 平均减少多少概率不确定性？ | 需要位置先验和似然，题设只给硬界，无法唯一确定。 |

R1／R9支持集合直径与面积两条路线；R6／R12／R13支持统计实验设计和信息量路线。这里对 \(K_o\) 的统一公式是为本题重写，不是这些论文共用同一个模型。[R1，2013][C13]；[R9，2018摘要][B18]；[R6，2012作者稿／2013期刊][Z12]；[R12，2009][JB09]；[R13，2008][K08]

**GDOP特别需要定义。**Tekdas–Isler使用的双站代理是

\[
U(s_1,s_2,p)=\frac{r_1r_2}{|\sin\phi|},
\]

具有面积量纲。Q1/Q2 模型 的条带面积 \(4r_1r_2\varepsilon_1\varepsilon_2/|\sin\phi|\) 与其成比例。[R5，2010，作者稿 Fig.1][TI10]

而若另行假设两个角误差独立、方差为 \(\sigma_\theta^2\)，并在给定目标处线性化，则本次复算得到

\[
I=\frac1{\sigma_\theta^2}\sum_{i=1}^2\frac{n_in_i^T}{r_i^2},\quad
\operatorname{tr}I^{-1}=\sigma_\theta^2\frac{r_1^2+r_2^2}{\sin^2\phi},\quad
\det I=\frac{\sin^2\phi}{\sigma_\theta^4r_1^2r_2^2}.
\]

所以“RMS位置误差除以角噪声标准差”的几何因子为 \(\sqrt{r_1^2+r_2^2}/|\sin\phi|\)，与面积代理不是一个量。公式由方位导数 \(n_i^T/r_i\) 和二维矩阵求逆直接得到；统计信息矩阵的建模背景参见 R6 和 R7。[R6，2012／2013][Z12]；[R7，2014，式 (4)–(6)][VH14]

固定两站到**同一目标**的距离时，正交使上述若干准则更好；移动第二站时距离和夹角一起改变，真实目标还未知，因此“90°必然全局最优”不成立。高斯分布无有限硬支撑，\(\pm1^\circ\) 不能未经说明当成 \(\pm3\sigma\)；设均匀误差而令 \(\sigma=\varepsilon/\sqrt3\) 也是额外概率假设。[模型比较推论；R6，2013][R6]

### 3. 能强化 Q1/Q2 模型、但不必扩大默认实现的工具

**（a）最坏直径与最坏覆盖半径的优化关系。**Q1/Q2 模型已证明每点的 \(J/2\le J_R\le J/\sqrt3\)。设在同一候选域内 \(q_D\) 精确最小化 \(J\)，\(q_R\) 精确最小化 \(J_R\)，则

\[
J_R(q_D)\le\frac{J(q_D)}{\sqrt3}
\le\frac{J(q_R)}{\sqrt3}
\le\frac2{\sqrt3}J_R(q_R).
\]

这说明精确的直径最优解对覆盖半径目标具有 \(2/\sqrt3\approx1.1547\) 的近似保证，虽然两种准则可给不同排序。若只有 \(J(q)\le\inf J+\delta\) 的**可靠界**，右侧增加 \(\delta/\sqrt3\)；仅凭网格解不能宣称具有该近似比；标准场景的全域误差证书及其适用范围另见 [Q1/Q2 素材](../../../paper/materials/kit-q12.md)。这是**本备忘录由 Q1/Q2 模型 与 Jung 界作出的推论**，不是 R1 原文定理，也不声称文献首次。[Q1/Q2 模型正文](../../../paper/modeling-q1q2.md)；[Jung界的现代文献核对，2024][J24]

**（b）清除目标应使用自由圆心或可清除落点集。**

\[
E_{20}(K)=\bigcap_{p\in K}D(p,20),\qquad
E_{20}(K)\ne\varnothing\iff R(K)\le20.
\]

这是统一行动可行性的充要条件。\(d\le20\sqrt3\) 足以清除，\(d>40\) 不可能统一清除，中间段必须计算形状或 \(R\)。此处“可清除”允许在测量后移动到合适位置；原地清除还须 \(\sup_{p\in K}\|p-q\|\le20\)。Q3若追求更短时间，可在 \(E_{20}\) 中选距当前位置最近的点，未必必须走到最小圆心。这些结论已有 Q1/Q2 模型 自足证明，基础几何引 R14／R15。[Q1/Q2 模型正文](../../../paper/modeling-q1q2.md)；[R14，1991][W91]；[R15，1901][R15]

**（c）未知共享参数要提升到联合集合。**扩展至多个no_signal时，维护 \((p,\rho)\)；定向源还要保留共享发射朝向。只有在明确可消元的正信号场景才把 \(\rho\) 投影掉。R3的区间方法可作为非线性联合可行集合的求解方向，但其定位对象不同，不能直接为我们带圆弧的集合提供现成证书。暂不替换 Q1/Q2 模型 默认采样路线。[R3，2000摘要][R3]；[Q1/Q2 模型正文](../../../paper/modeling-q1q2.md)

**（d）统一报告下界见证与外包上界。**合法的共同反馈点对给 \(J(q)\) 下界；包含整个反馈集合的圆才给清除保证。有限样本最小圆只能覆盖样本。若要升级至 guaranteed localization，可用区间分支／约束传播或解析外包控制遗漏部分；仅“网格很密”不够。[R3，2000][R3]；[Q1/Q2 模型正文](../../../paper/modeling-q1q2.md)

### 4. 多传感器选择：三种组合问题要分开

**已拿到读数后的集合压缩。**R4 的四传感器结果针对给定测量、非空有界凸多面交集的面积近似。它不是“只需先测任意4次”，也不是“最小圆至多3个支撑点，所以只需3个传感器”。支撑点来自约束交会，保留这些点并不能排除删去其他约束后新增的外部区域。[R4，2008][IM08]；[前身全文，2007][IM07]

**测量前的统计子集选择。**R12给凸松弛及实例松弛差距，未保证差距普遍很小；R13的互信息次模性质和近似界依赖其高斯过程设定，不能从“集合越交越小”直接推出最坏直径收益次模。[R12，2009，摘要及§III][JB09]；[R13，2008][K08]

**我们可以从长歧义点对构造另一个离散组合模型。**这是对 Q1/Q2 模型 的本次延伸：固定有限源样本集 \(X\)、候选站集 \(Q\)、阈值 \(\tau\)，令

\[
\mathcal U_\tau=\{\{x,y\}\subset X:\|x-y\|>\tau\},\qquad
A_q=\{\{x,y\}\in\mathcal U_\tau:\mathcal O_q(x)\cap\mathcal O_q(y)=\varnothing\}.
\]

\(\mathcal O_q(x)\) 是源在 \(x\) 时允许的反馈集。在固定初始保收域、不同站点角误差可任取界内值、near/direction规则已固定的情况下，选择若干站使 \(\cup_qA_q=\mathcal U_\tau\)，等价于**分开所有离散长点对**。可写0–1覆盖模型

\[
\min\sum_{q\in Q}z_q,\qquad
\sum_{q:\{x,y\}\in A_q}z_q\ge1\quad(\{x,y\}\in\mathcal U_\tau),
\qquad z_q\in\{0,1\}.
\]

这是集合覆盖，而非直接证明原直径函数次模。分开点对的计数收益才具有集合并的边际递减结构。多站协同可能对直径产生“单站不改善、合并后明显改善”，不能照搬互信息的贪心近似比。R5的整数规划、R8的成对依赖分析可作为方法背景，但上述“站点覆盖待分开的源位置对”是为本题重写，**与 R8 的“传感器对覆盖目标”不是同一个集合系统**。[R5，2010][TI10]；[R8，2016][R8]

适用限制：该模型只保证离散样本；连续源域仍需认证。允许no_signal且共享\(\rho\)、误差有空间相关约束、或候选点随反馈改变时，须重新证明联合反馈可分解性。一次选一站的自适应树及带路径成本的序贯决策，不等同于上述静态最小站数模型。此组合模型仅为方法讨论，未用于当前算法及结果表。

R8还给出可用来衡量理论结果强弱的参照：对其角覆盖参数 \(\alpha\le\pi/3\)、\(\delta>1\)，将角覆盖要求放宽为 \((1-1/\delta)\alpha\) 可获得 \(O(\log\delta)\) 的数量近似；加入距离或可见性限制时，相应结果带 \(\log k_{\rm OPT}\) 因子。这里讨论的是该文离散候选／目标模型的双准则保证，不能据此给我们的连续直径选点加上近似比。[R8，2016，摘要及Table 1][R8]

## 四、可引用清单与贡献定位

### 1. 可以直接放入参考文献表的核心条目

正文篇幅有限时，优先使用以下8项；其余完整书目已在第二节列出，按实际使用增补，避免只为数量堆砌引用。

1. **TOKEKAR P, ISLER V.** Sensor placement and selection for bearing sensors with bounded uncertainty[C]//2013 IEEE International Conference on Robotics and Automation. 2013: 2515–2520. [DOI: 10.1109/ICRA.2013.6630920][R1].
2. **GARULLI A, VICINO A.** Set membership localization of mobile robots via angle measurements[J]. IEEE Transactions on Robotics and Automation, 2001, 17(4): 450–463. [DOI: 10.1109/70.954757][R2].
3. **WELZL E.** Smallest enclosing disks (balls and ellipsoids)[C]//MAURER H, ed. New Results and New Trends in Computer Science. Lecture Notes in Computer Science, vol. 555. Berlin, Heidelberg: Springer, 1991: 359–370. [DOI: 10.1007/BFb0038202][R14].
4. **JUNG H.** Ueber die kleinste Kugel, die eine räumliche Figur einschliesst[J]. Journal für die reine und angewandte Mathematik, 1901, 123: 241–257. [DOI: 10.1515/crll.1901.123.241][R15].
5. **TEKDAS O, ISLER V.** Sensor placement for triangulation-based localization[J]. IEEE Transactions on Automation Science and Engineering, 2010, 7(3): 681–685. [DOI: 10.1109/TASE.2009.2037135][R5].
6. **ZHAO S, CHEN B M, LEE T H.** Optimal sensor placement for target localisation and tracking in 2D and 3D[J]. International Journal of Control, 2013, 86(10): 1687–1704. [DOI: 10.1080/00207179.2013.792606][R6].
7. **VANDER HOOK J, TOKEKAR P, ISLER V.** Cautious greedy strategy for bearing-only active localization: Analysis and field experiments[J]. Journal of Field Robotics, 2014, 31(2): 296–318. [DOI: 10.1002/rob.21499][R7].
8. **BAYRAM H, STEFAS N, ISLER V.** Aerial radio-based telemetry for tracking wildlife[C]//2018 IEEE/RSJ International Conference on Intelligent Robots and Systems. 2018: 4723–4728. [DOI: 10.1109/IROS.2018.8594503][R9].

引用定位：角锥交集／最坏直径用1、2；最小圆算法用3；Jung界用4；距离和交会角的共同影响用5、6；主动选点及时间目标用7、8。R2、R9本次只读到可信摘要，正文只引用该层面的方法事实，不引用未读定理、页码或实验细节。

### 2. 我们可以声称怎样的增量

| 拟作为贡献的内容 | 新颖性判断 | 适合写进国赛论文的表述 |
|---|---|---|
| ±1°角锥交集、凸几何求解、最坏直径 | **成熟方法，不新。**R1／R2已覆盖基本思想。 | “依据有界误差集员模型建立可行域，并采用最坏直径评价定位歧义。” |
| 直径圆覆盖反例、最小覆盖圆、Jung界 | **基础几何，不是新理论。** | “针对题目提出直径圆覆盖充要判据，并构造满足测向合同的反例。”价值在问题适配、证明完整性和可复核构造。 |
| \(\kappa=2R/d\)、\(\eta=2\max\|x-m\|/d\)及紧界 | **可作解释性指标，不能因换名字声称首创。**\(\kappa\)本质是半径／直径比的归一化，\(\eta\)由最远对几何导出。 | “区分最佳圆心与直径中点的覆盖膨胀，量化使用直径中点的额外风险。” |
| \(E_{20}\)、34.64／40米三段判据、清除三态 | **任务层面的有效增量，数学基础经典。**本次核心及直接后续中未见相同清除合同。 | “将定位集合转化为统一清除落点的存在性判定，建立测向精度与20米清除动作之间的联系。” |
| 未知固定接收半径的完整保收域、四圆盘标准场景约化 | **较强的本题特定增量。**本次未找到相同公式；不构成全球首创证明。 | “利用首次正反馈对接收半径进行条件化，导出策略类内完整保收域，并给出标准场景解析约化。” |
| 不可区分点对的 \(J\) 等价公式 | **值得突出的问题重写。**“不可区分性／对抗下界”是一般思想。 | “将未知第二读数的最坏后验直径等价转化为共同反馈源位置对的最大距离，降低读数枚举负担。” |
| 短基线不可辨识下界 \(V(B)\ge b-a\) | **具体解析命题可作贡献；不能声称首次发现短基线病态。**R5／R6／R10已有几何与可观测性背景，R7已有定位时间下界。 | “构造同射线候选源对，证明给定移动预算下的剩余歧义下界，并解释小步测量无效区。” |
| 序贯搜索、测向、移动直到达到阈值 | **一般策略不新。**R7、尤其R9已有明显先例。 | “在既有主动定位思想上结合保收约束、20米清除与题设时间成本设计策略。”Q3/Q4 的实现与官方数据见 [模型正文](../../../paper/modeling-q34.md)。 |
| 网格＋局部细化推荐第二点 | **数值算法组合，不自带最优性。** | “求取连续稳健目标的数值候选解，报告分辨率、加密变化和典型最不利见证。” |

上表“未见”只限本次取得的论文与摘要，**不是穷尽性新颖性检索结论**。最有说服力的贡献组合是：**题设物理信息的严格条件化 → 共同反馈的最坏歧义 → 清除动作的几何可行性**，而不是把经典几何或统计准则重新命名。

两项具体命题的定位还可以写得更准确。对 \(d>0\)，Q1/Q2 模型 的 \(1\le\kappa\le\eta\le\sqrt3\)、\(\kappa\le2/\sqrt3\) 分别来自最小圆定义、最远对的平行四边形恒等式与Jung界；等边三角形达到两项上界。它们说明“最佳圆心最多膨胀15.47%”与“直径中点可能膨胀73.21%”是不同问题，适合做清晰的解释性结果，不宜包装为新的几何理论。[Q1/Q2 模型正文](../../../paper/modeling-q1q2.md)；[Jung界核对，2024][J24]

短基线命题则有明确的本题条件：若 \(x=S+au,y=S+bu\in F\)、\(5<a<b\)、\(B<a-5\)，且

\[
\arcsin(B/a)+\arcsin(B/b)\le2\varepsilon_2,
\]

那么预算圆内任意合法第二站仍无法排除这对位置给出共同direction，因而 \(V(B)\ge b-a\)；原地按固定读数合同单列。\(a=500,b=1500,B=10,\varepsilon_2=1^\circ\) 给出 \(1.528^\circ<2^\circ\) 和 \(V(10)\ge1000\) 米。这是保守的可构造下界，既不是紧最优值，也不是 R1 的空圆下界；可以作为本文针对移动预算推导的命题。[Q1/Q2 模型正文](../../../paper/modeling-q1q2.md)

### 3. 可直接改写入论文的相关工作与方法定位段落

有界方位误差可通过测量逆像描述为包含真实位置的角锥，多次观测通过集合求交得到位置可行域。Tokekar和Isler研究了该模型下以交集直径或面积衡量最坏不确定性的传感器布点与选择问题；Garulli和Vicino则将集员估计用于含有界角误差的机器人定位。[R1，2013][C13]；[R2，2001][G01]。本文采用这一集合建模思路，在首次观测后进一步引入目标活动区域、未知接收半径及近场反馈，建立第二检测点的保收条件，并以共同反馈源位置对的最大间距评价最坏定位歧义。

主动无线电定位已有综合测量位置、定位阈值与行走／测量耗时的研究，其中Bayram等使用有界角锥交集的面积作为在线定位指标。[R7，2014][VH14]；[R9，2018摘要][B18]。本文针对20米清除要求，以最小覆盖圆半径判定是否存在对所有可行源位置均有效的清除落点，并依据Jung界区分直径能够直接判定和必须进一步检查区域形状的情形。[R14，1991][W91]；[R15，1901][R15]。相应增量在于定位信息与可执行清除动作的衔接，数值选点结果的精度以网格细化证据说明。

**建议最小补强实验（尚未执行）：**在同一保收域上比较最坏直径、最坏面积、固定假设下的GDOP／D准则及移动最短基线；统一源样本复评，报告最坏歧义、覆盖半径、20米可清除状态和耗时。面积或GDOP选点也必须用同一有界误差模型接受清除核验。另保留“同直径的线段／等边三角形”与“10米预算下至少1000米歧义”的解析例，分别说明度量差异和短基线限制。[Q1/Q2 模型正文](../../../paper/modeling-q1q2.md)

[C13]: https://tokekar.com/pubs/tokekar2013asensor.pdf
[CH13]: https://tokekar.com/tokekar2013asensor.html
[CM13]: https://experts.umn.edu/en/publications/sensor-placement-and-selection-for-bearing-sensors-with-bounded-u
[T12]: https://citeseerx.ist.psu.edu/document?doi=b9c1259b8bfc812df7768bf53e39b3eb439f533f&repid=rep1&type=pdf
[R1]: https://doi.org/10.1109/ICRA.2013.6630920
[R2]: https://doi.org/10.1109/70.954757
[G01]: https://usiena-air.unisi.it/handle/11365/3355
[R3]: https://link.springer.com/article/10.1023/A:1009990700281
[R4]: https://doi.org/10.1109/TASE.2008.917096
[IM07]: https://www.cs.rpi.edu/research/pdf/07-03.pdf
[IM08]: https://experts.umn.edu/en/publications/sensor-selection-in-arbitrary-dimensions/
[R5]: https://doi.org/10.1109/TASE.2009.2037135
[TI10]: https://www-users.cse.umn.edu/~isler/pub/tase10.pdf
[R6]: https://doi.org/10.1080/00207179.2013.792606
[Z12]: https://arxiv.org/pdf/1210.7397
[Z13]: https://www.tandfonline.com/doi/abs/10.1080/00207179.2013.792606
[R7]: https://doi.org/10.1002/rob.21499
[VH14]: https://josh.vanderhook.info/media/pdf/JoshV_JFR_2013_Localization.pdf
[R8]: https://arxiv.org/abs/1607.05791
[BK16]: https://www.cs.umd.edu/users/samir/grant/allpubs.html
[R9]: https://doi.org/10.1109/IROS.2018.8594503
[B18]: https://experts.umn.edu/en/publications/aerial-radio-based-telemetry-for-tracking-wildlife/
[R10]: https://doi.org/10.1109/TRO.2019.2896436
[H19]: https://fileserver-az.core.ac.uk/download/188365792.pdf
[R11]: https://onlinelibrary.wiley.com/doi/10.1002/rob.22134
[R12]: https://doi.org/10.1109/TSP.2008.2007095
[JB09]: https://stanford.edu/~boyd/papers/pdf/sensor_selection.pdf
[R13]: https://jmlr.org/papers/v9/krause08a.html
[K08]: https://jmlr.csail.mit.edu/papers/volume9/krause08a/krause08a.pdf
[R14]: https://doi.org/10.1007/BFb0038202
[W91]: https://people.inf.ethz.ch/emo/PublFiles/SmallEnclDisk_LNCS555_91.pdf
[WB91]: https://people.inf.ethz.ch/emo/MiscellaneousPubl.html
[R15]: https://doi.org/10.1515/crll.1901.123.241
[J24]: https://arxiv.org/abs/2407.03553
[SS13]: https://api.semanticscholar.org/graph/v1/paper/DOI:10.1109/ICRA.2013.6630920?fields=title,citations.title,citations.year,citations.externalIds
[AN19]: https://robots-wild-rss.github.io/rss2019-workshop/paper/Towards%20Automated%20Monitoring%20of%20Animal%20Movement%20using%20Camera%20Networks%20and%20AI.pdf
