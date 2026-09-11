# Q2 三方对拍（独立 oracle）

种子 `20260911`；候选 762 例，最坏直径 92 例；耗时 188.2 秒。双方实现及 oracle/fixture 的 SHA-256 前后相同：**True**。详见 `differential-q2.json`。

## 判定口径

随机首测 ε₁=ε₂=1°、场地圆心原点/半径1800 m；S 含原点、场地圆周、域外及域内。q 含四圆盘边界±0.0001 m、随机内外、近源、短基线与近平行。另保留固定 benchmark 的零角宽线段、窄角扇区等闭式回归（这些补充例不全是1°）。
候选 oracle 使用独立 sector_oracle（全扇区闭式）、sample（2049×129网格+12000随机世界），再加入33个角度的径向分段点 r=1000，防止均匀径向网格漏掉定义拐点。截断 F 的 IN 接受完整扇区超集证书或独立径向端点的一维角区间证书；C_sig OUT 必须有合法失收世界。采样未发现反例不能证明 IN；未知单列 ORACLE_UNRESOLVED。同学 P 使用原 adapter 的 disk_outer/bearing_clip/clip，不用真值点构造。
我方仅 IN 视为声称保收；BOUNDARY 和 UNRESOLVED 不视为 IN。同学 False 是未获证书，不自动算错误。C_dir 独立核查我方，同学没有对应接口，逐例标 API_UNPROVIDED。
J 是连续 sup。主配置为 sample_sources(level=2,q,ε₂)+score_point(SearchConfig 默认 refine_pairs=False)，另实测 refine_pairs=True。下界来自独立 atan2 全对枚举和闭式；[L,U] 合并 optional/certified 的区间带与闭式的40位区间运算外向舍入带（不把无理闭式的float近似当零宽精确区间）。certified 只接收 SimpleNamespace 原始参数，不读我方 F 边界/采样/谓词。1e-6 m 是比较浮点容差，绝不是连续误差保证。
UNDERESTIMATE 表示违反独立下界（含认证 L/闭式）；不是把 J_hat 的 NUMERICAL_CANDIDATE 声明改写成上界承诺。BOTH_OK 仅表示本轮一致性检查没有反驳，不表示精确相等或认证正确。2·半径上界允许保守，不要求逼近 J。只有同学值 ≥ 独立 U 才标 PROVEN_BY_ORACLE_U；介于 L、U 之间只能标 NOT_REFUTED_NOT_CERTIFIED。
对 C_sig 外点，分数只解释为 direction/near 点对泛函，不能当包含失收反馈的物理最坏后验 J；JSON 保存 reception 状态。

## 分类计数（标签可重叠）

| 分类 | 候选 | 直径 |
|---|---:|---:|
| DANGEROUS_FALSE_POSITIVE | 3 | 0 |
| UNDERESTIMATE | 0 | 0 |
| CONSERVATIVE | 168 | 86 |
| OURS_WRONG | 0 | 0 |
| THEIRS_WRONG | 3 | 0 |
| BOTH_OK | 587 | 92 |
| API_UNPROVIDED | 4 | 0 |
| ORACLE_UNRESOLVED | 0 | 0 |
| DIRECTION_FALSE_POSITIVE | 0 | 0 |

C_dir：同学 762 例均 API_UNPROVIDED（未重复加入上表 C_sig 计数）；方向 oracle 有成员真值 747 例。

## 保守性与召回

我方 C_dir 有独立真值且给出 IN/OUT 的 641 例中，一致 641 例。全部 C_dir 返回状态：`{'IN': 215, 'OUT': 437, 'BOUNDARY': 99, 'UNRESOLVED': 11}`；非二元返回没有计作声称方向保收。
按 fixture 边界容差口径接受的 C_sig 点共 386 个（包括数值边界带）：我方 IN 283/386=73.32%，同学 True 218/386=56.48%。这只是本测试集召回，不能外推分布。
排除 BOUNDARY 数值带后的 oracle IN 点 281 个：我方 281/281=100.00%，同学 216/281=76.87%。BOUNDARY 沿用生成器平方容差 1e-5 m²，不将其宣称为二进制输入的精确成员证明；微基线由精确世界覆盖此容差口径。
我方合法点状态：`{'IN': 283, 'BOUNDARY': 103}`。同学在这些点拒绝 168 个，可能来自 P 外包、未去掉首测5m开圆盘或数值安全裕量；不能将全部差异归因于 P 外包。

| 合法点举例 | q | 我方 | 同学 |
|---|---|---|---|
| fixture_four_disk_8_1000 | [1004.9992246684508, 0] | IN | False |
| fixture_four_disk_8_1500 | [1004.9992246684508, 0] | IN | False |
| fixture_four_disk_34_1000 | [573.8502812328818, -822.3532957921057] | IN | False |
| fixture_four_disk_34_1500 | [573.8502812328818, -822.3532957921057] | IN | False |
| fixture_four_disk_37_1000 | [635.5463149644568, -776.0637312234683] | IN | False |
| fixture_four_disk_37_1500 | [635.5463149644568, -776.0637312234683] | IN | False |
| fixture_four_disk_40_1000 | [693.5079724685778, -725.1407732889619] | IN | False |
| fixture_four_disk_40_1500 | [693.5079724685778, -725.1407732889619] | IN | False |

## 危险假阳：最小结构反例与世界

“最小”指删去无关自由度的单场景、单 q、单世界，不声称实数坐标存在最小非零扰动。所有严重项的完整输入与世界均在 JSON；以下列出每个危险假阳。

| case | S / θ / q | 声称保收者 | 世界 (p,ρ) |
|---|---|---|---|
| micro_-1e-12 | [0.0, 0.0] / 0.0 / [-1e-12, 0.0] | ['THEIRS_WRONG'] | `{"p": [1500.0, 0.0], "rho": 1500.0, "rho_squared_exact": "2250000", "squared_excess_exact": "73559785961562688241595415795989652905278641441/24519928653854221733733552434404946937899825954937634816", "kind": "no_signal", "note": "rho is defined exactly by sqrt(rho_squared_exact); displayed decimal is approximate"}` |
| micro_-5e-11 | [0.0, 0.0] / 0.0 / [-5e-11, 0.0] | ['THEIRS_WRONG'] | `{"p": [1500.0, 0.0], "rho": 1500.0, "rho_squared_exact": "2250000", "squared_excess_exact": "3591786423904487005741112629483527702842943129/23945242826029513411849172299223580994042798784118784", "kind": "no_signal", "note": "rho is defined exactly by sqrt(rho_squared_exact); displayed decimal is approximate"}` |
| micro_-9e-11 | [0.0, 0.0] / 0.0 / [-9e-11, 0.0] | ['THEIRS_WRONG'] | `{"p": [1500.0, 0.0], "rho": 1500.0, "rho_squared_exact": "2250000", "squared_excess_exact": "25254748293078759901061201562881404685728089/93536104789177786765035829293842113257979682750464", "kind": "no_signal", "note": "rho is defined exactly by sqrt(rho_squared_exact); displayed decimal is approximate"}` |

这3个微扰（若计数变化，以表为准）属于同一个根因：同学 `signal_minimax.py:15` 用 `‖q−S‖<1e-10` 代替坐标完全相同，并无条件返回 True。令 q=(−δ,0)，p=(1500,0)，ρ=1500，则失收平方余量为 3000δ+δ²>0。这是严格定义下的假阳，物理失收距离仅为 δ；没有发现米级失收反例。我方同点特判使用坐标相等，这些非零微扰返回 BOUNDARY。

## 低估：全部反例

| case | 我方 J_hat | refine=True | oracle L | oracle U | 同学 2U_R | 可达世界对 (p,ρ) / 反馈 |
|---|---:|---:|---:|---:|---:|---|
| 本轮未检出低估 | — | — | — | — | — | — |

表中世界对对应 oracle 采样下界；若更强的 L 来自区间证书，精确反例采用 JSON certificate.witness.parameters 与 coordinate_enclosures（其源点可能为无理数），而非舍入后的世界坐标。若仅闭式极限超过估计，闭式为 sup，不能冒充已达到的点对。

同学连续上界判定：`{'PROVEN_BY_ORACLE_U': 88, 'NOT_REFUTED_NOT_CERTIFIED': 4}`。区间 oracle 收敛 36/92；预算耗尽仍保留有效宽带，不能将宽带内判为高精度通过。
我方落入带内 92/92；refine=True 后仍违反 L 的 0 例。相同 oracle 点云隔离检查：0/0 通过；用来区分采样不足与点对枚举问题。


## 上界保守幅度（闭式真值子集）

| case | 真 J | 我方 J_hat−J | 同学 2U_R−J | 同学 2U_R/J |
|---|---:|---:|---:|---:|
| fixture_tangent_segment_4 | 0.610121049 | -0.000000000 | 9.389878951 | 16.390190 |
| fixture_tangent_segment_0 | 0.629920845 | -0.000000000 | 9.370079155 | 15.875010 |
| fixture_tangent_segment_3 | 33.399336272 | -0.000000000 | 495.891580658 | 15.847348 |
| fixture_tangent_segment_1 | 1.574079694 | -0.000000000 | 8.425920306 | 6.352918 |
| fixture_tangent_segment_2 | 144.991331931 | -0.000000001 | 103.603634952 | 1.714551 |
| fixture_segment_20_80_40_1 | 6.528213426 | -0.000000000 | 3.471786574 | 1.531813 |
| fixture_segment_10_100_20_0.5 | 8.348054588 | -0.000000000 | 3.617484024 | 1.433333 |
| fixture_segment_10_100_200_1 | 8.580375712 | -0.000000000 | 1.995902439 | 1.232612 |

直径场景中，独立 oracle 确认 C_sig 内 91 例、C_sig 外 1 例，其余 0 例候选真值未决。C_sig 外结果仅作点对泛函诊断，不计为物理保收动作验证。
`fixture_tangent_segment_3` 不保收世界：`{"p": [1000.0, 0.0], "rho": 1000.0, "rho_squared_exact": "1000000", "squared_excess_exact": "400", "kind": "no_signal", "note": "rho is defined exactly by sqrt(rho_squared_exact); displayed decimal is approximate"}`。

这里认证的是换算后的直径上界 2U_R≥J。仅此不能反向证明半径 U_R≥连续最坏 MEC 半径；一般平面集合满足 J/2≤J_R≤J/√3。diagnostics 的条件半径检查也不替代全反馈最坏半径认证。

## 尚未认证的同学直径上界

| case | oracle L | oracle U | 同学 2U_R | 我方 J_hat |
|---|---:|---:|---:|---:|
| random_2_parallel | 994.743566600 | 1003.146351368 | 1001.855164600 | 995.117283435 |
| random_10_same | 687.450279235 | 689.515665820 | 689.148797928 | 687.450279235 |
| random_10_parallel | 686.461650311 | 689.122033073 | 688.919209377 | 686.466881614 |
| random_10_random_0 | 98.794549709 | 124.205756503 | 107.673675759 | 100.209494555 |

## diagnostics 与范围限制

clearance_summary 在 71 个 oracle 可达反馈上检查条件半径 r_U≥可达点对距离/2；反驳 0 个。这只检验条件后验的覆盖界，不能把 R_hat 或 worst_radius_scale(J_hat) 当作连续最坏覆盖保证。

## 结论与复现

本轮检出 3 个保收危险假阳和 0 个最坏直径低估。错误归属见计数及逐例表；保守拒绝和上界偏松独立记录。未被下界反驳的同学上界，只有通过独立 U 的子集获得本轮连续上界证明，其余仍待更紧认证。

```sh
cd /Users/flower/math/2026/B题
models/q1q2/.venv/bin/python -B models/q1q2/peer-audit/differential_q2.py --seed 20260911 --scenes 16 --cert-nodes 2000 --extra-cert-nodes 20000
```

两份真值生成器均在临时目录重新执行，和保存 fixtures 语义一致：{'candidate': True, 'diameter': True}。
产物一致性核验（OUT世界、点对合法性/距离、区间顺序、哈希、真值重生成）：`{'protected_sources_unchanged': True, 'truth_regeneration': True, 'all_bands_consistent': True, 'all_lower_pairs_legal': True, 'all_pair_distances_match': True, 'all_OUT_have_independent_world': True}`。
脚本：`differential_q2.py`；逐例输入、双方返回值、反例世界、区间参数、哈希：`differential-q2.json`。增大 --cert-nodes 可收紧未收敛区间；节点数固定，另设30秒应急时限，因此时限触发时区间端点可随机器性能变化。
