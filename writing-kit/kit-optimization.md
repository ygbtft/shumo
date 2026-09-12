# Q3/Q4 时间优化研究素材库

整理日期：2026-09-13。用途：供作者摘取的证据卡、公式、数值表、否决记录；不提供成文论文段落。配套基础模型与几何接口见 [kit-q34.md](kit-q34.md)。

- 指标统一为 `τ=Σ整局虚拟时间/Σ真实源数`，`Δτ=候选−基线`；单位默认 s/源，最差退化为 s/局。账本 `T=L/5+5M+S+5C_s+3C_f`；共享仍逐频道付 RF 费，失手也改变位置。出处：[opt-q34.md:28](/Users/flower/math/2026/B题/review-opt/opt-q34.md:28)（第28—44行）、[B/ABLATION.md:13](/Users/flower/math/2026/B题/B/ABLATION.md:13)（第13—19行）。
- **精度**：标明 JSON 字段的数字照录原始字面量；其余表明列“报告原精度”，不补造尾数。报告的差值可能由未舍入值计算，不用表面舍入均值重算替代。
- **标签**：`[定理/有证明]`用于带前提的解析命题；`[实测/统计]`用于有限样本、轨迹分解、浮点求解及 bootstrap。有证明的路由放松不自动把其浮点求解数值升级为精确算术定理。
- **版本**：默认采纳以 `q3-finalize.md` 为末次决策依据。旧参数报告的“四参数组合否决”仍成立；其中 `remainder_weight=1` 的旧默认记录不覆盖后来单独采纳的 `1.5`。
- **本次操作**：只整理文档、读取报告及其直接证据字段；未执行策略、官方模拟器、正式测试或下列历史复跑命令。材料只使用本地 mock 和解析证据；不收入恢复数据及其间接转引统计。`info-structure.md` 的正式统计段不取用。
- **复现口径**：每项给出取证位置及报告中的复跑入口。会生成结果的命令仅作复现素材，须在完整实验副本中用新输出名执行，保留冻结策略/mock/fixtures；不得直接覆盖归档。未验证的参数、缺失的精确值或没有依据的对应关系写“无”。不同报告的种子矩阵与基线不可直接拼成累计收益。

只读取证命令约定（各卡的 `R0 文件 起行 末行`、`R1 JSON 键路径` 均使用本组定义；无网络、无落盘；在项目根目录执行）：

```sh
cd /Users/flower/math/2026/B题
OPT_PY=/Users/flower/math/2026/B题/mock/.venv/bin/python
R0() { "$OPT_PY" -B -c 'import sys;from pathlib import Path;p=Path(sys.argv[1]);a,b=map(int,sys.argv[2:4]);print("\n".join(f"{p}:{i}: {s}" for i,s in enumerate(p.read_text().splitlines(),1) if a<=i<=b))' "$@"; }
R1() { "$OPT_PY" -B -c 'import json,sys
from pathlib import Path
d=json.loads(Path(sys.argv[1]).read_text(),parse_float=str)
for k in (sys.argv[2].split(".") if len(sys.argv)>2 else []):
    d=d[int(k)] if isinstance(d,list) else d[k]
print(json.dumps(d,ensure_ascii=False,indent=2))' "$@"; }
```

<a id="adopted"></a>
## 一、已采纳的优化：默认配置与证据

<a id="clear-gates"></a>
### 1.1 清除门：Q3 80→50 m；Q4 40→35 m

**强度 `[实测/统计]`；选门为经验取舍。** 50/35 m 是允许失败的提前试探门；物理成功距离仍为20 m，认证门仍为 `20−10⁻⁵ m`，每源至多一次专门提前试探，保留有限定位预算与光学兜底。采纳状态：[B/CLEAR_GATE_TRADEOFF.md:3](/Users/flower/math/2026/B题/B/CLEAR_GATE_TRADEOFF.md:3)，当前保留状态：[q3-finalize.md:7](/Users/flower/math/2026/B题/review-opt/q3-finalize.md:7)。

| 阶段 | 执行数 | 每题每设置与种子 | 用途/出处 |
|---|---:|---|---|
| 初扫 | 3150 | 210局；202609110—202609319；Q3八设置、Q4七设置 | 报告第25行 |
| 扩展 | 12600 | 1050局；202610000—202611049；两题各六设置 | 第26行；在此选50/35 |
| 冻结验证 | 6570 | 普通1050局；202620000—202621049；另45个既有压力场；各原门/新门/20控制 | 第27行；压力单列 |
| 合计 | **22320** | **22320/22320全清，异常0、认证清除失败0** | 第23—27行；完整执行数，非独立场景数 |

独立普通验证原始字段：`B/experiments/runs/2026-09-11_clear-gate-validation/ordinary/summary.json`，按 `problem,radius` 选数组行；每行 `runs=1050,sources=13650,all_cleared=1050`。

| 题/门 | `clear_failure_count` | `pooled_per_source_s` | `delta_per_source_s` |
|---|---:|---:|---:|
| Q3/80 | 2881 | 246.87834690212452 | 0.0 |
| Q3/50 | 2337 | 246.8196695597802 | -0.0586773423443226 |
| Q4/40 | 1032 | 467.5069747441026 | 0.0 |
| Q4/35 | 808 | 467.66225673355314 | 0.1552819894505499 |

| 采纳门 | 失手降幅（报告原精度） | `delta_95ci_s` | `slower_cases` | `worst_case_delta_s` |
|---|---:|---|---:|---:|
| Q3/50 | 18.88% | [-0.10427611875509536, -0.015040595726063] | 268 | 49.94058300000006 |
| Q4/35 | 21.71% | [0.06840964568276983, 0.24611998460363568] | 267 | 249.47286199999962 |

- **选参时的代价不能倒写**：扩展组 Q3 失手2860→2336（报告18.32%），`Δτ=0.019618306080585967`；Q4 1029→787（23.52%），`Δτ=0.2996148302564109`。出处：`clear-gate-refinement/summary.json` 对应 `clear_failure_count,delta_per_source_s`；[报告:70](/Users/flower/math/2026/B题/B/CLEAR_GATE_TRADEOFF.md:70)（第70—74行）。Q3扩展组并非净提速。
- **边界**：Q4独立验证明确付出约0.0332%的时间代价；不能写“两题均提速”“无时间退化”或“零失手保证”。20 m控制普通验证虽零失手，却比旧门多2.8827/2.1697 s/源（报告原精度，第80—87行）。4000次配对 bootstrap 仅描述预设混合场。
- **复现取证**：`R0 B/CLEAR_GATE_TRADEOFF.md 15 100`；`R1 B/experiments/runs/2026-09-11_clear-gate-validation/ordinary/summary.json`；完整曲线另见 [kit-q34 §5.2](kit-q34.md#52-清除门22320次完整执行的曲线)。

历史复跑（报告第114—120行；脚本实际位于 `B/`，以此为工作目录）：

```sh
cd /Users/flower/math/2026/B题/B
/Users/flower/math/2026/B题/mock/.venv/bin/python -B clear_gate_sweep.py --output experiments/runs/clear-gate-reproduce-training
/Users/flower/math/2026/B题/mock/.venv/bin/python -B clear_gate_sweep.py --output experiments/runs/clear-gate-reproduce-refinement --repeats 10 --seed-start 202610000 --q3-radii 80 70 60 50 40 20 --q4-radii 40 38 35 32 30 20
/Users/flower/math/2026/B题/mock/.venv/bin/python -B clear_gate_sweep.py --output experiments/runs/clear-gate-reproduce-validation --repeats 10 --seed-start 202620000 --q3-radii 80 50 20 --q4-radii 40 35 20 --stress
```

<a id="dominance"></a>
### 1.2 Q3 距离支配半平面：几何正确与样本提速分列

| 可摘要素 | 精确内容 | 强度/出处与边界 |
|---|---|---|
| 推导 | 同一静止全向源g、固定未知ρ、同频道成功锚点a与真实阴性q：`‖g−q‖>ρ≥‖g−a‖`，推出 `2(q−a)ᵀg<qᵀq−aᵀa` | `[定理/有证明]`；[opt-q34.md:60](/Users/flower/math/2026/B题/review-opt/opt-q34.md:60)（第60—82行）；实现保留闭半平面并外放 |
| 不能套Q4 | `g=(0,0), a=(100,0), q=(−1,0)`，源朝东；a成功、q阴性，但q更近 | `[定理/有证明]`反例；同报告第98行；定向阴性可能来自背面 |
| 已采纳 | 当前Q3含距离支配，Q4不启用 | [q3-finalize.md:3](/Users/flower/math/2026/B题/review-opt/q3-finalize.md:3)及第7行；旧opt报告第48行“尚未接入”为历史时点 |
| 不覆盖的用途 | 空频道没有成功锚点，不能靠该半平面判空；推断免扫不是真实阴性 | 同报告第73—99行；[q3-empty-confirmation/REPORT.md:13](/Users/flower/math/2026/B题/review-opt/q3-empty-confirmation/REPORT.md:13) |

独立复验 `[实测/统计]`：补读既有素材直接引用的 [verify-q34.md:63](/Users/flower/math/2026/B题/review-opt/verify-q34.md:63)（第63—84行）及 `review-opt/verify-q34-evidence/comparison.json`。种子734120—734319；每题每版本200局、2600源；两题两版本共800次执行。

| JSON字段 | Q3原值 | 含义/边界 |
|---|---:|---|
| `q3.before_per_source` | 244.25962839576923 | 独立200局改前 |
| `q3.after_per_source` | 243.42618886846154 | 同场景改后 |
| `q3.saved_per_source` | 0.8334395273076818 | 节省，符号与Δ相反 |
| `q3.saved_percent` | **0.34121051144697384** | 百分数；约0.3412% |
| `q3.before_all_clear / after_all_clear` | 200 / 200 | 全清不变 |
| `q3.faster / slower` | 36 / 10 | 相同154局；不逐局占优 |
| `q3.worst[0]` | 96.75209199999972 | seed734201；报告微秒口径+96.752092 |
| `q3.min_margin` | 0.0011900297866986882 | 本批包含余量，m |

- **30644的准确口径**：`q3.before_updates=7069, after_updates=7319; q4.before_updates=8128, after_updates=8128`，相加30644；两题 `bad=[]`。包括两题两版本的全部区域赋值检查；不是30644次距离支配裁剪，不是独立场景数。改后Q3实际裁剪248次、异常0（复验报告第63行）。Q4 `summary_diffs=[]; full_trace_diffs=[]; all_record_fields_equal=true`。
- **不同证据不混表**：原型300局为245.0558→244.4166、Δ−0.6392（报告原精度，opt第86—97行）；生产实施300局为245.05579967205128→244.4212600474359、节省0.2589367913204112%（`q3-dominance/comparison.json`）。都不是上述0.3412%的200局样本。
- **诚实边界**：无全浮点输入形式化保证；无新官方收益；无逐局不退化保证。闭半平面的数学证明与有限精度实现审计分开引用。
- **复现取证**：`R1 review-opt/verify-q34-evidence/comparison.json q3`、同命令末键改`q4`；`R0 review-opt/verify-q34.md 47 97`。

历史复跑（复验报告第88—96行；仅完整证据副本，脚本有固定快照/输出路径）：

```sh
cd /Users/flower/math/2026/B题/B
/Users/flower/math/2026/B题/mock/.venv/bin/python -B ../review-opt/verify-q34-evidence/audit.py before
/Users/flower/math/2026/B题/mock/.venv/bin/python -B ../review-opt/verify-q34-evidence/audit.py after
/Users/flower/math/2026/B题/mock/.venv/bin/python -B ../review-opt/verify-q34-evidence/adversarial.py
/Users/flower/math/2026/B题/mock/.venv/bin/python -B ../review-opt/verify-q34-evidence/compare.py
```

<a id="remainder"></a>
### 1.3 Q3 `remainder_weight: 1→1.5`：微小收益通过预设风险门槛

**强度 `[实测/统计]`。** 默认只改余程权重，保留50 m门、距离支配、`share_limit=6, localization_weight=.08, max_active=3`。出处：[q3-finalize.md:3](/Users/flower/math/2026/B题/review-opt/q3-finalize.md:3)（第3—17行）。31个冻结候选；普通2100局、27300源/设置，seed860000000—860002099；另210压力局，seed861000000—861000209。每105局平衡10—16源×三种位置×五种误差；相邻块交替均匀/固定1000 m半径。

原始数值来源：`review-opt/q3-finalize/validation/final_summary.json` → `baseline,remainder15`；入口复核来源：`after-verification.json` → `current_validation`。

| 项目/字段 | 原值 |
|---|---|
| `baseline.tau` | 246.18411945545787 |
| `remainder15.tau` | 246.18117990816847 |
| `remainder15.delta_tau` | -0.002939547289377285 |
| `remainder15.ci95` | [-0.0051002728695729235, -0.001227006611197653] |
| `remainder15.familywise95` | [-0.007102235541675676, -0.0005322869613212455] |
| `faster / slower / ties` | 14 / 2 / 2084 |
| `worst_seconds / worst_case` | 0.3836989999999787 / 860001355 |
| `baseline.misses → remainder15.misses` | 4625 → 4625 |
| `baseline.full_clear → remainder15.full_clear` | 2100 → 2100 |
| 改后真实入口 `current_validation.after_tau` | 246.1811799081685 |

- **报告摘用精度**：246.184119→246.181180；95%区间[−0.005100,−0.001227]；仅2局变慢，最差+0.384 s；约0.001194%收益。报告第37、105、113行。冻结候选与入口汇总末位略异，逐局时间与动作核验一致；保留各字段原值，不强行改齐。
- **采纳规则**：10000次配对 bootstrap，未校正与Bonferroni家族95%区间均排除0；普通与压力最差增时≤50 s；全清100%，失手不增，区域/物理违规0。预先冻结，非看过结果后设置门槛（第9—17行）。
- **尾部明细（报告第119—120行）**：seed860001246，10源，3528.475003→3528.541903，+0.066900，失手4/4；seed860001355，14源，3305.414210→3305.797909，+0.383699，失手7/7。压力集无变慢、失手不增、210/210全清。
- **边界**：不是结构性突破或全局最优；历史ICRA总入口的精确重放不一致未修复，不能宣称历史总入口也通过（第132行）。四参数组合仍否决；`empty_remainder`全部2310个新场景及1050个旧场景与单独余程配置等价，故不接冗余免测guard（第107—109行）。
- **复现取证**：`R1 review-opt/q3-finalize/validation/final_summary.json remainder15`；`R1 review-opt/q3-finalize/after-verification.json current_validation`；`R0 review-opt/q3-finalize.md 103 144`。

历史复跑（报告第137—144行；分析器固定阶段名不能误读新phase）：

```sh
cd /Users/flower/math/2026/B题/B
/Users/flower/math/2026/B题/mock/.venv/bin/python -B ../review-opt/q3-finalize/run_experiment.py --phase reproduce-validation --count 2100 --seed 860000000 --workers 6
/Users/flower/math/2026/B题/mock/.venv/bin/python -B ../review-opt/q3-finalize/stress.py --phase reproduce-stress --count 210 --seed 861000000 --workers 2
```

<a id="lower-bounds"></a>
## 二、下界与不可达性：证明、数值及前提

<a id="arbitrary-layout"></a>
### 2.1 任意合法覆盖布局的巡访下界

**强度 `[定理/有证明]`。** 主出处：[coverage-tour-lower-bounds.md:9](/Users/flower/math/2026/B题/review-opt/coverage-tour-lower-bounds.md:9)（第9—188行）；解析量保留精确式，数表为报告原精度。

| 必须随结论摘用的前提 | 精确范围 |
|---|---|
| 几何 | 源域`A=D(0,R), R=1800 m`；保证接收半径`r=1000 m`；有限站集S可在域外；Q3全向，Q4覆盖任意闭180°朝向 |
| 合法性 | Q3：`A⊆∪D(s,r)`；Q4：每个g均属于`conv(S_g)`，`S_g={s∈S:‖s−g‖≤r}` |
| 路径 | 从原点出发、终点自由；`n<16`时完成合法站集的覆盖巡访；服务移动可与巡站共用，不能另加一条清源移动下界 |
| 上限豁免 | 对`n=16`局，完整巡访移动与空频道扫描下界都取0；仅加必要动作时保留10 s/源 |
| 权重 | 151.846629等总体数要求`w₁₀=…=w₁₆`，使用`ΣT/Σn`；不是七种单局比值的算术平均 |
| 发现清除项 | 每源至少一次RF发现及一次成功清除，合计10n；不适用于无RF的纯光学盲清 |
| 空频道项 | 每个空频道完成合法RF覆盖；未知频道的真实测量义务不能借其他频道观测抵销。改变排尽证据时该加项须重证 |

证明链，可拆为引理：

1. **凸包内含盘**：Q3对任意单位u，圆周点Ru有可接收站s，`uᵀs≥R−‖s−Ru‖≥R−r=800`，故`D(0,800)⊆conv(S)`；Q4由局部凸包条件直接得`D(0,1800)⊆conv(S)`。记`b₃=800,b₄=1800`。出处第27—37行。
2. **起点为圆心的路径界**：报告援引Joris定理：从单位圆心出发且与所有切线相交的连续可求长曲线长度至少`c=1+√3+7π/6`。覆盖路径Γ凸包含`D(0,b)`，每向投影由0连续达到至少b，必交每条切线；因此`L(Γ)≥H₀(S)≥cb`。出处第39—56行。**外部最短曲线定理按报告转引；本库未重新核验原论文全文，不称本题首创定理**。不依赖外部定理的完整初等证明见下一卡。
3. **站数界**：Q3一站覆盖源圆周的最大角长为`2arcsin(5/9)<2π/5`，故`K₃≥6`，不证明6站可行或7站最少。Q4几乎处处至少三站在保证接收范围内；圆周外朝向每站承担角长≤`2arctan(5/9)<π/3`，至少七个域外站；域外站接收盘在源域内面积≤半盘，故`3πR²≤(K−7/2)πr²`，`K₄≥ceil(3R²/r²+7/2)=ceil(13.22)=14`。出处第94—131行。两条界无需同一构型同时取等即可用于不同计费项。

| 量（报告原精度） | Q3 | Q4 | 出处 |
|---|---:|---:|---|
| 任意合法布局，从原点完整开放巡访`ℓ=cb`，m | 5117.793789 | 11515.036026 | 第51—54行 |
| 该移动项`ℓ/5`，s/局 | 1023.558758 | 2303.007205 | 同表 |
| 等频总体：仅移动贡献，16源移动免费 | 67.487391 | **151.846629** | 第174—179行 |
| 再加每源一次发现及成功清除 | **77.487391** | **161.846629** | 同表 |
| 再加空频道RF，`k₃=6,k₄=14` | **92.322555** | **196.462014** | 同表 |
| 初等路径界＋发现清除＋空频道RF | **80.071959** | **168.898171** | 同表；不能称168.898171为“仅移动”界 |

通用权重式（报告第135—172行）：

\[
\tau\ge10+
\frac{(\ell_q/5)\sum_{n=10}^{15}w_n+5k_q\sum_{n=10}^{15}(20-n)w_n}
{\sum_{n=10}^{16}nw_n}.
\]

等频时`Σn=91`、`Σ₁₀¹⁵(20−n)=45`，得到`τ≥10+(6ℓ_q/5+225k_q)/91`；去掉空RF加项得161.846629/77.487391，再去掉10得仅移动贡献。

**可摘结论及边界**：

- Q4：**在上述等频权重与完整覆盖巡访范式内，150 s/源对任意合法有限覆盖布局不可达**；仅移动下界已超过150，不依赖当前21站，也不依赖至少两次定位RF假设。每个10—15源局的“移动＋发现清除”界也超过150（第147—155、181—186行）。
- Q3：任意布局界低于150，**尚不能排除150**；不是存在性或可达性证明。固定七站的条件数值界另见§2.4。
- 未知官方源数分布、更多16源局、改变排尽范式均不能直接搬用总体数；若全部为16源，此方法仅给10 s/源。下界与当前实测的差不是可兑现收益，当前布局近优证明：**无**。
- 数值严格性：报告第202—209行给Q4移动贡献的精确有理包络`[151.846628916429163900496103555132, 151.846628916429163900496103555133]`；超过150不依赖打印舍入。逐动作最近微秒舍入的强化界修正小于0.000008 s/源，结论不变（第188行）。显示为六位小数的界均视为精确式的近似显示，不把向上舍入小数当严格下端点。

复现取证：`R0 review-opt/coverage-tour-lower-bounds.md 25 209`；`R1 review-opt/coverage-tour-lower-bounds/bounds.json problems`。报告第211—215行离线复算入口（会写产物，仅在副本运行；不导入策略/模拟器）：

```sh
/Users/flower/math/2026/B题/mock/.venv/bin/python -B /Users/flower/math/2026/B题/review-opt/coverage-tour-lower-bounds/recompute.py
```

<a id="closed-curve-proof"></a>
### 2.2 “闭合曲线长度≥凸包周长”：可完整摘用的初等证明骨架

**强度 `[定理/有证明]`。** 出处：[coverage-tour-lower-bounds.md:60](/Users/flower/math/2026/B题/review-opt/coverage-tour-lower-bounds.md:60)（第60—77行）、[analytic_lower_bound.md:49](/Users/flower/math/2026/B题/review-opt/q4-layout-redesign/analytic_lower_bound.md:49)（第49—57行）。以下把报告的投影证明展开；不使用TSP求解器的“最优状态”作为证明。

设闭合可求长曲线γ长为L，凸包为K。方向`uθ=(cosθ,sinθ)`的投影宽度记`w_K(θ)`，投影总变差为`Vθ`。

\[
V_\theta\ge2w_K(\theta),\qquad
\int_0^\pi V_\theta\,d\theta
=\int_\gamma\!\int_0^\pi|u_\theta^Tt(s)|\,d\theta\,ds=2L.
\]

- 第一式：闭合的一维投影必须从最小值走到最大值并返回，变差至少两倍宽度。
- 第二式：弧长参数下切向量单位长，`∫₀^π|cosθ|dθ=2`；折线逐边相加亦得。
- 对凸多边形K，边界投影往返各一次，`∫₀^π 2w_K(θ)dθ=2P(K)`；一般凸包用凸多边形逼近。因此`2L≥2∫₀^πw_K(θ)dθ=2P(K)`，即`L≥P(K)`。若`D(0,b)⊆K`，各向宽度≥2b，另得`P(K)≥2πb`。

用于开放路径时必须先补闭合边。设终点e距原点d，则凸包还含`conv(D(0,b)∪{e})`，周长为

\[
P_b(d)=\begin{cases}
2\pi b,&d\le b,\\
2\pi b+2\sqrt{d^2-b^2}-2b\arccos(b/d),&d>b.
\end{cases}
\]

补长d回原点，故`L+d≥P_b(d)`。在`d>b`分支，`(P_b−d)'=2√(1−b²/d²)−1`，最小点`d=2b/√3`，值`5πb/3`；`d≤b`分支最小为`(2π−1)b>5πb/3`。于是

\[
\boxed{L\ge5\pi b/3.}
\]

Q4得`L≥3000π≈9424.777961 m`；加§2.1的14站空频道RF及发现清除，等频总体精确式为`10+(3600π+3150)/91≈168.898171 s/源>150`。此初等证据单独足够，但它**需要空频道RF加项**；不能把它说成初等“仅移动>150”证明。

复现：`R0 review-opt/coverage-tour-lower-bounds.md 58 77`、`R0 review-opt/q4-layout-redesign/analytic_lower_bound.md 47 59`；数值复算同§2.1。证明由上列恒等式及不等式逐步核验；无需新实验。

<a id="layout-157"></a>
### 2.3 Q4 布局重设计的较早解析下界：严格超过157.38

**强度 `[定理/有证明]`。** 出处：[q4-layout-redesign/analytic_lower_bound.md:3](/Users/flower/math/2026/B题/review-opt/q4-layout-redesign/analytic_lower_bound.md:3)（第3—100行）；与§2.1为不同强度的证明，不将两个下界相加。

| 前提/步骤 | 精确式与报告原值 |
|---|---|
| 额外坐标限制 | 每站`|x|,|y|≤1950 m`，是整数验证器的分量范围，**不是1950 m行动半径** |
| 覆盖/站数 | 同§2.1的Q4局部凸包覆盖；`K≥14` |
| 开放巡访长度 | 最后必经站s满足`‖s‖≤1950√2`；补边闭合后周长≥`3600π`，故`L≥3600π−1950√2≈8552.017106 m` |
| 10≤n≤15 | `T_n≥(3600π−1950√2)/5+70(20−n)+10n` |
| n=16豁免 | 移动/扫描免费，仅`T₁₆≥160 s` |
| 等频源加权 | `τ≥[(6/5)(3600π−1950√2)+4060]/91≈157.3892365665 s/源` |
| 保守下端 | 用`π>3.1415926, √2<1.4142136`即证`τ>157.38`；不是凭约数判不可达 |

- **范围**：本界逐源数排除10—14源的150；15源仅147.360228，16源仅10，不能单组排除（第74—96行）。源数等频混合后仍排除150。
- **边界**：定位服务先捷径化为必经站访问顺序，再对最后必经站补边；不要求最终清除/退出位置也在1950分量范围内。扩展证书坐标范围或改变空频道义务后，本界需重算；§2.1的较强界不需要1950限制。两者均不证明当前21站近优。
- **复现取证**：`R0 review-opt/q4-layout-redesign/analytic_lower_bound.md 47 100`。报告内独立命令：**无**；下式为本库只输出终端的数值复算，严格性由报告有理界承担：

```sh
/Users/flower/math/2026/B题/mock/.venv/bin/python -B - <<'PYCODE'
from math import pi, sqrt
from fractions import Fraction as F
print('L_display_m',3600*pi-1950*sqrt(2))
print('tau_display',(6*(3600*pi-1950*sqrt(2))/5+4060)/91)
lower=(F(6,5)*(3600*F('3.1415926')-1950*F('1.4142136'))+4060)/91
print('strict_rational_lower',lower,'greater_than_157.38',lower>F('157.38'))
PYCODE
```

<a id="q3-conditional"></a>
### 2.4 Q3 同范式理想地板：固定七站与服务圆放松

**强度：放松关系 `[定理/有证明]`；165.66数值 `[实测/统计]`（浮点MILP对偶界，有条件数值下界）。** 出处：[q3-joint-service/REPORT.md:60](/Users/flower/math/2026/B题/review-opt/q3-joint-service/REPORT.md:60)（第60—79行）。

- 前提：当前原七站；`n<16`保留全部站和`7(20−n)`次空频道RF；`n=16`删除全部扫描站义务。每源任意20 m清除圆，真实源坐标只在事后诊断使用。
- 放松：已知频道RF（包括发现）、切频、失败、定位不确定性与信息因果约束全部免费；动作仅留`5n+35(20−n)·1[n<16]`。
- 路由：服务圆i的中心`g_i`、半径`r_i=20`，站点半径0；边权`d⁻ᵢⱼ=max(0,‖g_i−g_j‖−r_i−r_j)`不超过真实边长。允许同一圆相邻两边使用不一致接触点，再求从原点开放TSP的对偶下界；得到更乐观的放松，不能直接当执行路线。

原始字段：`review-opt/q3-joint-service/conditional-floor-summary.json`。

| 批次/字段 | 原值 | 样本 |
|---|---:|---|
| `diagnosis.conditional_floor_tau` | 166.33607722612047 | 210局、2730源；报告训练/诊断口径 |
| `validation.conditional_floor_tau` | **165.66452961532642** | 420局、5460源；seed2026100000—2026100419 |
| 两组`max_gap_m` | 0.0 | 求解器容差意义零间隙，非整数精确最优证明 |

- **可摘结论**：这批混合场上，固定七站空频道义务时，联合排序即使获全知放松仍不足以达到150。
- **不可摘结论**：任意Q3布局/算法/分布均不能达到150；每个未来场景至少165.66；165.66为已实现工程成绩。以上证明均**无**。验证15源分组下界仅148.8792、16源104.8635（报告原精度），也不能写成每组均超过150。
- **复现取证**：`R1 review-opt/q3-joint-service/conditional-floor-summary.json`；`R0 review-opt/q3-joint-service/REPORT.md 60 79`。历史数值重算：在该实验完整副本目录执行 `/Users/flower/math/2026/B题/mock/.venv/bin/python -B conditional_floor.py`（报告第101行）；会读取固定阶段并输出结果。场景复跑见§3.1。

<a id="engineering"></a>
## 三、现实工程地板拆解：哪些路程可以共同承担

<a id="q3-breakdown"></a>
### 3.1 Q3：清除插入不是全部可省的折返

**统一强度 `[实测/统计]`。** 来源：[q3-joint-service/REPORT.md:42](/Users/flower/math/2026/B题/review-opt/q3-joint-service/REPORT.md:42)（第42—64行）；`diagnosis-geometry-summary.json`、`validation-geometry-summary.json`。所有分项为源加权s/源；前者210局训练诊断，后者420局独立验证，不能互换。

| 分项/JSON字段 | 训练诊断原值 | 独立验证原值 |
|---|---:|---:|
| 实际τ `actual_tau` | 246.4097671025641 | 244.69064538461538 |
| 实际扫描折线 `scan_actual_tau` | 103.6871057119539 | 103.72666918715852 |
| 成功清除插入 `clear_insertion_tau` | 71.29374642354209 | **69.12453641510758** |
| 非扫描RF定位绕行 `localization_tau` | **9.949011104901706** | 9.975881452098541 |
| 失败清除绕行 `failed_tau` | 0.2169001992593426 | 0.22802719683798048 |
| 实际动作 `action_tau` | 61.263003663003666 | 61.63553113553114 |
| 最短站序S* `scan_opt_tau` | 102.8087912087912 | 102.85054945054945 |
| 固定清除点几何增量 `fixed_points_geometric_increment_tau` | 52.04795876960856 | **51.329282637739595** |
| 联合次序损失 `combined_order_excess_tau` | 20.124102157096214 | **18.671373513977066** |
| 扫描次序损失 `scan_order_excess_tau` | 0.8783145031626912 | **0.8761197366090747** |

定义：从实际轨迹依次短接非扫描RF、失败清除，剩下扫描与成功清除折线C；再去成功清除得扫描折线S。对同样点集求从原点、终点自由的最短路径C*、S*。报告恒等式：

\[
C-S=(C^*-S^*)+(C-C^*)-(S-S^*).
\]

验证摘用式（报告第51—57行原显示精度）：`69.1245≈51.3293+18.6714−0.8761`。**必须扣回0.8761；不能写“69.12=51.33+18.67”**。51.33仅是固定本次实际成功清除落点时的几何增量，不是允许任意20 m清除落点下不可省的精确费用。9.95是训练诊断定位绕行的约数，验证同项约9.98。

| 全知/理想参照（JSON字段） | 训练诊断原值 | 独立验证原值 | 含义 |
|---|---:|---:|---|
| `clairvoyant_disc_movement_lower_tau` | **147.41611694600087** | **146.74304070561746** | 实际已访扫描站＋真源20 m服务圆的移动放松下界 |
| `disc_lower_plus_actual_actions_tau` | 208.67912060900449 | 208.3785718411486 | 上行＋各自原实际动作账单 |
| `fixed_points_and_actual_actions_tau` | 216.11975364140346 | 215.81536322382019 | 固定实际清除点最优排序，删除定位/失败绕行，保留动作账单 |

- **名称订正**：“全知最短扫描移动约147.4”应摘为“训练诊断中，扫描＋清除服务圆的全知移动放松下界约147.4”；纯扫描S*是102.8087912087912。将147.4标成纯扫描最短值的依据：**无**。
- **工程边界**：约208—216是保留现RF/动作账单的乐观参照，不是可实现策略，也不适用于换动作、换站点后的算法。固定点求解`gap=0`是浮点求解器意义，不替代几何精确证明。
- **实测未榨干折返**：`joint_split`验证联合次序损失19.0388，比基线多0.3674；移动τ+0.1789，动作τ−1.6597，净Δ−1.4808（报告第64行原精度）。不能把该候选均值收益归因于消除了18.67的折返。
- **复现取证**：`R1 review-opt/q3-joint-service/diagnosis-geometry-summary.json`；`R1 review-opt/q3-joint-service/validation-geometry-summary.json`。

历史场景及诊断复跑（报告第93—106行；后两行重算归档validation，非新phase）：

```sh
cd /Users/flower/math/2026/B题/review-opt/q3-joint-service
/Users/flower/math/2026/B题/mock/.venv/bin/python -B run_experiment.py --phase reproduce --count 420 --seed 2026100000 --settings baseline,rounded_control,joint_split,joint_atomic --workers 4
/Users/flower/math/2026/B题/mock/.venv/bin/python -B diagnose.py --phase validation --setting baseline --count 420
/Users/flower/math/2026/B题/mock/.venv/bin/python -B diagnose.py --phase validation --setting joint_split --count 420
```

<a id="q4-breakdown"></a>
### 3.2 Q4：约39.3→21.8的次序损失，约410—420的条件工程参照

**统一强度 `[实测/统计]`。** 来源：[q4-joint-service/REPORT.md:9](/Users/flower/math/2026/B题/review-opt/q4-joint-service/REPORT.md:9)（第9—37、86—113行）。诊断集105场、1365源，随机朝向/均匀半径；不能与420场完整验证的均值混表。

原始字段来自 `review-opt/q4-joint-service/diagnosis-geometry-summary.json`（基线）及 `diagnosis_joint-geometry-summary.json`（联合版）：

| 分项/字段，s/源 | 基线原值 | 联合版原值 |
|---|---:|---:|
| `tau` | 453.82151772747255 | 436.5834296835165 |
| `action_tau` | 126.81025641025641 | 123.7113553113553 |
| `scan_actual_tau` | 273.85802997163034 | 263.6986288994807 |
| `clear_extra_tau` | 38.25260771693688 | 33.790169122190186 |
| `pair_extra_tau` | 14.276985936654038 | 14.947644552752672 |
| `localization_extra_tau` | 0.0 | 0.0 |
| `failure_extra_tau` | 0.6236377412051379 | 0.435631847166313 |
| 次序损失下界 `observed_order_excess_lower_tau` | 39.23570483873252 | 21.73466313170674 |
| 次序损失上界 `observed_order_excess_upper_tau` | 39.30552436434712 | 21.963200735727842 |

- **分解规则**：实走路线→删除失败清除点→删除非扫描/非主探测RF→删除成对探点→删除成功清除点；相邻差为净插入。扫描骨架不是“所有驶向扫描点的入边”；换删除顺序会改变分摊。成对探测是动作类型，不能全归因于真值定向源（报告第24—26行）。
- **几何与次序**：固定扫描点最优移动259.167；加实际清除点278.814；再加实际主探点287.082—287.152（报告第28—37行原精度）。基线次序损失约39.3降至约21.8；探点净插入反增，主要节省来自扫描及清除衔接。
- **已有动作费**：基线空频道测量`empty_measure_tau=54.86813186813187`；总测量102.74358974358974、切频18.886446886446887、成功清除5.0、失败清除0.18021978021978022，均s/源。字段分别`action_measure_tau,action_switch_tau,action_success_tau,action_failure_tau`。

| 参照层 | 数值/字段 | 必须注明的范围 |
|---|---|---|
| 固定RF工作＋固定清除点，事后最优次序 | 413.89235567113053—413.9621751967452；基线`fixed_jobs_actual_actions_lower_tau / upper_tau` | 移动MILP下/上界＋原实际动作费；忽略发现/定位先后因果 |
| 固定RF工作＋连续认证清除点 | **409.2207304891184—413.3810937831558**；`flexible-floor-summary.json` → `lower_plus_actual_actions_tau,feasible_unordered_upper_plus_actual_actions_tau` | 下界为放松；上界仅无因果排序几何可行，不是在线策略可达保证 |
| 独立验证普通层 | 418.78（报告原精度） | 随机朝向/均匀半径；基线458.18、在线441.96；第106—111行 |
| 独立验证朝外/1000 m层 | 432.16（报告原精度） | 不能沿用普通层410—420承诺 |
| 独立验证完整混合 | 425.47—425.49（报告原精度） | 保留工作量的理想次序；不是普通层的410—420 |
| 更宽松的固定21站义务界 | 诊断308.14385490268177；验证约309.03 | n<16保留21站及空RF；每源仅5 s清除，免已知RF/切频/定位；用成功回执的40 m服务圆放松，第88、111行 |

**可摘工程判断**：普通场、当前站表、保留实测RF工作量，理想路线参照约410—420 s/源；在线诊断/普通验证约437—442。**410不是普适下界**；改变真实RF工作量、空频道证据或合法覆盖义务后可以低于该参照，须另证另测。下/上界之间仍有松弛间隙，不称连续清除点问题已求尽。

复现取证：`R1 review-opt/q4-joint-service/diagnosis-geometry-summary.json`；`R1 review-opt/q4-joint-service/diagnosis_joint-geometry-summary.json`；`R1 review-opt/q4-joint-service/flexible-floor-summary.json`；`R0 review-opt/q4-joint-service/REPORT.md 86 113`。报告第139行指定`diagnose.py,flexible_floor.py,path_solver.py`为地板分析脚本；诊断默认入口如下（已只读核对CLI；固定阶段输出，仅在副本运行）：

```sh
cd /Users/flower/math/2026/B题/review-opt/q4-joint-service
/Users/flower/math/2026/B题/mock/.venv/bin/python -B diagnose.py --phase diagnosis --count 105 --settings baseline
/Users/flower/math/2026/B题/mock/.venv/bin/python -B diagnose.py --phase diagnosis_joint --count 105 --settings joint_atomic
/Users/flower/math/2026/B题/mock/.venv/bin/python -B flexible_floor.py
```

<a id="rejected"></a>
## 四、被否决的候选：保留反面证据及否决理由

本块时间数据统一 `[实测/统计]`；每个几何反例另标 `[定理/有证明]`。均为未采纳候选或历史对照；不得与第一块默认优化合计收益。除标明JSON字段者外，下表小数均为**对应报告原精度**。

<a id="six-heuristics"></a>
### 4.1 六个移动融合启发式：没有达到1%的改善

对应可核对的六原型为`finish_path,scan_then_clear,sweep_clear,transit_sweep,horizon_scan,flow_clear`；由[q3-finalize.md:24](/Users/flower/math/2026/B题/review-opt/q3-finalize.md:24)回溯直接来源 [movement-fusion/REPORT.md:29](/Users/flower/math/2026/B题/review-opt/movement-fusion/REPORT.md:29)（第29—85行）。**“六启发式<1%”只可指没有一个达到1%的正向改善；不能写成六个都改善、也不能写成六个绝对变化均小于1%。**

同一独立420局，基线τ=244.573；各候选均420/420全清；seed202697000—202697419。

| 被否方案 | 候选τ；Δτ及95%区间 | 变慢局数；最差增加s | 为什么不采纳 |
|---|---|---|---|
| `finish_path`：扩大顺路补测候选并估完工路径 | 249.734；+5.161 [+4.720,+5.604] | 363；292.859 | 每源实际多走26.433 m；局部预测未描述反馈改变共享/清除位置/排序 |
| `scan_then_clear`：先扫后清 | 288.764；+44.191 [+42.175,+46.285] | 412；1433.896 | 二次服务行程，延后清除/共享及第16源发现；多203.847 m/源 |
| `sweep_clear`：冻结骨架，插入已认证清除 | 297.484；+52.911 [+50.499,+55.367] | 412；1433.896 | 未认证源拖到扫完；985次插入仍未抵销服务延后 |
| `transit_sweep`：骨架上加零绕行RF | 290.205；+45.632 [+43.267,+48.151] | 405；1450.219 | 新增1481次RF、1232次达到预测门；相对骨架有改进，相对实际基线仍慢 |
| `horizon_scan`：用后续站替专门补测 | 244.556；−0.017 [−0.101,+0.056] | 2；124.129 | 1795次考虑仅4次替换；2快/2慢/416同；区间跨零 |
| `flow_clear`：清除落点兼顾进出 | 244.547；−0.026 [−0.149,+0.077] | 88；83.229 | 最佳点估计仅少0.026 s/源；移动省0.093、动作多0.067；区间跨零 |

出处：报告第55—74行完整表，第78—83行逐项否决。强度 `[实测/统计]`；不能据此否定所有路径上的主动感知。后续2100局定稿复核仍拒绝这六项（[q3-finalize.md:45](/Users/flower/math/2026/B题/review-opt/q3-finalize.md:45)，第45—50行）。

复现取证：`R0 review-opt/movement-fusion/REPORT.md 47 107`。历史复跑（报告第99—107行）：

```sh
cd /Users/flower/math/2026/B题/review-opt/movement-fusion
/Users/flower/math/2026/B题/mock/.venv/bin/python -B experiment.py --phase reproduce --count 420 --seed 202697000 --workers 4 --traces --settings baseline,finish_path,scan_then_clear,sweep_clear,transit_sweep,horizon_scan,flow_clear
```

<a id="parameters-rejected"></a>
### 4.2 四参数组合：0.110%收益抵不过失手与尾部

| 被否方案 | 否决数据 | 理由/边界/出处 |
|---|---|---|
| Q3组合`share_limit=4,localization_weight=.32,max_active=2,remainder_weight=1.5` | 1050局：245.5929→245.3217，Δ−0.2712（0.110%），95%区间[−0.3600,−0.1808]；失手2270→2387（+117）；416快/154慢/480同；最差+155.513 s，最大+8.563% | 均值改善但违背减失手目标且尾部大；[B/PARAM_SENSITIVITY.md:7](/Users/flower/math/2026/B题/B/PARAM_SENSITIVITY.md:7)第7—17、224—245、261行。旧组合否决不覆盖后来单独采纳余程1.5 |
| Q4冷却150→800 m | Δ−0.3049，区间[−1.1049,+0.4891]；707快/195慢/148同；最差+2908.687 s、最大+102.428% | 收益未稳定复现且尾部极端；同报告第230—250行。冷却仅共享筛选，不是位置排除证书 |
| Q3单独`.32`与`.32+remainder1.5`的后续复核 | 新2100局可过新样本门槛，但历史seed202640088仍+149.254274 s | 不能用新样本抹去已知旧反例；[q3-finalize.md:107](/Users/flower/math/2026/B题/review-opt/q3-finalize.md:107)。余程1.5单独通过，见§1.3 |

复现取证：`R0 B/PARAM_SENSITIVITY.md 220 277`；`R0 review-opt/q3-finalize.md 103 109`。历史复跑（参数报告第287—295行，完整快照B及同级mock；当前默认已变化，不能直接把当前源码结果冒充旧参数基线）：

```sh
cd /Users/flower/math/2026/B题/B
/Users/flower/math/2026/B题/mock/.venv/bin/python -B param_sensitivity.py --output experiments/runs/2026-09-12_param-sensitivity-reproduce --workers 4
/Users/flower/math/2026/B题/mock/.venv/bin/python -B param_sensitivity_combo_audit.py --run experiments/runs/2026-09-12_param-sensitivity-reproduce
```

<a id="layout-rejected"></a>
### 4.3 缩短布局骨架：静态路短不等于整局τ低

| 被否方案 | 布局/否决数据 | 为什么不采纳；出处 |
|---|---|---|
| Q3自由七站`free26` | 最短开放路径6840.00→**6156.05 m**（报告−10.00%）；验证A：245.659→248.341，Δ+2.682，区间[+1.679,+3.701]，690/1260局慢、最差+956.799 s；验证B：246.113→248.851，Δ+2.738，区间[+1.716,+3.724]，702/1260局慢、最差+1205.144 s | 两组均退化；合并实际移动+5.613 s/源，其他动作−2.834、空频道动作−0.068，净+2.710；低源空RF仍`7(20−n)`。[q3-seven-free/REPORT.md:19](/Users/flower/math/2026/B题/review-opt/q3-seven-free/REPORT.md:19)第19—28、38—58、75—86行 |
| Q4 22站`fine_182` | 21站17826.74→22站**17543.99 m**，短282.75 m（**1.586%≈1.59%**）；525局验证481.54530→482.69493，退化0.239%；257快/268慢，最差+3397.400 s | 移动345.10486→341.62167，动作136.44044→141.07326；多一站的空RF及发现次序联动抵消短路。[q4-layout-redesign/REPORT.md:3](/Users/flower/math/2026/B题/review-opt/q4-layout-redesign/REPORT.md:3)第3—5、88—118行。3675次执行全清，不等于性能通过 |
| Q4不增站的`noncircular_731_0` | 21站开放巡访17826.74066→17737.39302 m（0.501%）；两组普通验证840场471.13918→467.31925（0.811%），95%区间[−6.174,−1.529]；含210压力场485.27249→481.22497（0.834%）；586快/464慢 | 普通均值复现，但含压力最差+2803.581508 s，seed210124160、16源，扫描11→21站；没有结构性突破。[q4-joint-layout/REPORT.md:3](/Users/flower/math/2026/B题/review-opt/q4-joint-layout/REPORT.md:3)第3—5、22、30—40、57行；保留实验注册 |

- **范围**：49套七站获证、20套训练、5套冻结代表两组独立验证，均未降τ；不能由有限搜索断言七站全局近优（Q3报告第3、13—15行）。Q4的固定点集MILP最优也不是布局全局最优。
- **复现取证**：`R0 review-opt/q3-seven-free/REPORT.md 17 105`；`R0 review-opt/q4-layout-redesign/REPORT.md 75 140`；`R0 review-opt/q4-joint-layout/REPORT.md 28 79`。
- **Q3复核入口**：报告第101行给出在`review-opt/q3-seven-free/`运行`audit.py,ledger.py,six_verify.py,finalize.py`；精确训练/验证参数在各阶段`manifest.json`。仅凭报告恢复整套计分CLI：**无**，不猜参数；可用以下原入口复核已有结果。

```sh
cd /Users/flower/math/2026/B题/review-opt/q3-seven-free
/Users/flower/math/2026/B题/mock/.venv/bin/python -B audit.py
/Users/flower/math/2026/B题/mock/.venv/bin/python -B ledger.py
/Users/flower/math/2026/B题/mock/.venv/bin/python -B six_verify.py
```

Q4历史复跑（各报告第134—138、73—77行；完整副本、新phase）：

```sh
cd /Users/flower/math/2026/B题/review-opt/q4-layout-redesign
/Users/flower/math/2026/B题/mock/.venv/bin/python -B benchmark.py --phase validation-replay --count 420 --seed 202708000 --candidates deform_4,family_684,fine_182 --workers 4
cd /Users/flower/math/2026/B题/review-opt/q4-joint-layout
/Users/flower/math/2026/B题/mock/.venv/bin/python -B benchmark.py --phase replay-a-new --count 420 --seed 210000000 --candidates noncircular_731_0 --workers 3
```

Q4两个运行器的`--count 420`为普通场数；报告完整验证另有105压力场，不能把525场表标成420场表。

<a id="empty-rejected"></a>
### 4.4 免测空频道：安全守卫零收益，删测有漏源反例

**安全方案与故意破坏对照分列**：守卫没有证明就保留原测量，因此正式候选全清；漏源来自用于否定删测的反事实构造，不是将漏源局当优化成绩。

| 题/被否做法 | 严格证据 `[定理/有证明]` | 实测否决 `[实测/统计]` |
|---|---|---|
| Q3：不新增同频道观测，靠其他六站阴性免第七站 | 七个整数独占见证`(0,0),(1140,0),(570,987),(−570,987),(−1140,0),(−570,−987),(570,−987)`；各自只在对应原站可见，半径1000；平方距离用精确分数核验。n<16时可添加一源而不超公开上限 | **42组**（6个n=10…15场景×7站）删测反事实，剩余公开响应含虚拟时间相同，添加源世界漏源。安全`negative_cover_guard`验证420局τ均**245.0652438324**；20352空RF、51718全部RF、48555切频均未少；37900次判断、0免测 |
| Q4：单纯1000 m盘并集判空 | 去中心后20站盘并集仍覆盖，但`g=(−850,−300),ρ=1000,n=(5,2)`定向源仅中心可见；中心距离平方812500<1000000，点积4850>0 | 该具体见证否定盘并集授权免测；必须保留局部可接收站凸包/任意朝向条件 |
| Q4：不新增同频道观测，靠其他20站阴性免一站 | 21个逐站独占定向见证，经任意精度整数距离/点积复核；未测任一站，仍有相容合法源 | **126对**（6场景×21站）不可区分反馈反例；安全`negative_hull_guard`验证210局τ均**473.357902**，省RF0、省移动0；主实验**92088次检查、92088次保留原测量、0免测**，每次保留存活整数见证 |

出处及计数边界：

- Q3：[q3-empty-confirmation/REPORT.md:60](/Users/flower/math/2026/B题/review-opt/q3-empty-confirmation/REPORT.md:60)，第60—79、91—114行；`certificate.json`、`audit.json`中的`counterfactuals`。42组是反事实测试数；37900是验证的免测判断数；不能混用。
- Q4：[q4-empty-confirmation/REPORT.md:15](/Users/flower/math/2026/B题/review-opt/q4-empty-confirmation/REPORT.md:15)，第15—27、42—54行；`certificate.json.exclusive_witnesses`、`disk_union_counterexample.json`、`audit.json.counterfactuals`。**92088不是92088个独立反例场景**；126对才是反事实反馈重放的计数。
- 固定负观测信息结构下，n<16空RF逐局仍为Q3 `7(20−n)`、Q4 `21(20−n)`。不能把车经过某点、其他频道测过某点、已知源半平面推理充作该空频道观测。到16源的公开上限停止本来已启用，不计本轮收益。
- 两个实验的旧ICRA历史总入口均未通过精确请求重放，不能写成“所有门槛通过”；故除零收益外也无晋级资格。Q3报告第127—136行，Q4第68行。未修改数值容差或旧归档。
- 只否定固定原站、无新增该频道观测的删测；不否定新布局、真实新增观测或别种排尽证据。

复现取证：`R0 review-opt/q3-empty-confirmation/REPORT.md 60 152`；`R0 review-opt/q4-empty-confirmation/REPORT.md 15 79`。历史复跑：

```sh
cd /Users/flower/math/2026/B题/review-opt/q3-empty-confirmation
/Users/flower/math/2026/B题/mock/.venv/bin/python -B run_experiment.py --phase validation_replay --count 420 --seed 202714000 --workers 4
/Users/flower/math/2026/B题/mock/.venv/bin/python -B audit.py
cd /Users/flower/math/2026/B题/review-opt/q4-empty-confirmation
/Users/flower/math/2026/B题/mock/.venv/bin/python -B certify.py
/Users/flower/math/2026/B题/mock/.venv/bin/python -B run_experiment.py --phase validation_again --count 210 --seed 202732000 --workers 4
/Users/flower/math/2026/B题/mock/.venv/bin/python -B check_root.py
```

<a id="joint-rejected"></a>
### 4.5 Q4 联合服务3.70%：均值复现，95局退化，默认未采纳

任务简称为`q4_jointmin`；指定报告内与**3.70%、95局退化**相对应的实际注册名是修复版 **`joint_atomic`**。`q4_jointmin`与其为同一注册键的证据：**无**；论文/复跑采用报告实际名称。

原始来源：`review-opt/q4-joint-service/final-summary.json` → `phases.validation_fixed`；文字出处：[q4-joint-service/REPORT.md:49](/Users/flower/math/2026/B题/review-opt/q4-joint-service/REPORT.md:49)（第49—84行）。

| 字段 | 原值 |
|---|---:|
| `baseline.tau` | 469.2677412723444 |
| `joint_atomic.tau` | 451.92671456813184 |
| `joint_atomic.delta_tau` | -17.341026704212457 |
| `joint_atomic.ci95` | [-19.976000762770983, -14.564421643777298] |
| `joint_atomic.faster / slower / ties` | 325 / **95** / 0 |
| `joint_atomic.worst_seconds` | **1393.86812** |
| `joint_atomic.full_clear / runs` | 420 / 420 |

- **可摘收益**：报告原精度469.268→451.927，−17.341 s/源（3.70%）；独立seed2026600000—2026600419。不能倒写为默认成绩。
- **否决理由**：尾部不能在线预知或撤销。最差seed2026600027，16源，站数14→20，多58次RF、多5274.34 m，+1393.87 s（约1394）；最坏五局全为16源。训练最差16源局扫站12→19，RF169→221（第74—84行）。静态次序变短可能推迟第16源发现，丢失公开上限早停；不能用隐藏源数分支补救。
- **版本边界**：V1有near先于区域的KeyError，旧压力只78/105完成，其成绩全部否决；这里只用修复冻结版。修复版训练/验证/压力2205次执行全清，97894次外包检查零违规；适配输入与目录作用域后的ICRA主检查32项通过，**原历史入口精确重放失败仍保留**（第117—125行）。不把技术门槛通过自动等同于性能风险可接受。
- **复现取证**：`R1 review-opt/q4-joint-service/final-summary.json phases.validation_fixed`；`R0 review-opt/q4-joint-service/REPORT.md 70 84`。

历史复跑（报告第129—139行，优先冻结snapshot；当前Q3并行变更会使旧`audit.py`生产哈希检查拒绝，不篡改归档以求通过）：

```sh
cd /Users/flower/math/2026/B题/review-opt/q4-joint-service
/Users/flower/math/2026/B题/mock/.venv/bin/python -B run_experiment.py --phase independent-replay --count 420 --seed 2026600000 --workers 4
/Users/flower/math/2026/B题/mock/.venv/bin/python -B stress.py --phase stress-replay --count 105 --seed 2026700000 --workers 4
```

<a id="six-station-counterexamples"></a>
### 4.6 六站84候选：整数盲区见证；不证明任意六站不可能

| 被否方案 | 否决证据 | 强度/边界 |
|---|---|---|
| 本轮搜索的84个Q3六站取整输出 | 初始12个＋60个多起点交换优化＋12个直接最坏覆盖半径局部优化；全被整数证书拒绝，**每个均有毫米坐标、Python整数平方距离验证的漏覆盖点** | `[定理/有证明]`针对每个给定点集的反例；有限搜索失败不证明任意六站不可能 |
| 将局部优化值当六站全局下界 | 最后一组最小浮点覆盖半径1003.117006 m | `[实测/统计]`找到的布局覆盖半径上界；不是六站最优值的下界，不能据1003>1000证明全族不可行 |
| 固定其他五站，把任意两原站合为一个任意位置站 | 21对均有两点距离>2000或锐角三角形MEC>1000的精确见证 | `[定理/有证明]`局部职责障碍；不覆盖同时移动其余五站 |

出处：[q3-seven-free/REPORT.md:3](/Users/flower/math/2026/B题/review-opt/q3-seven-free/REPORT.md:3)（第3、13—15、101—103行），证据`six_exact_rejections.json`；[detection-duties.md:5](/Users/flower/math/2026/B题/review-opt/detection-duties.md:5)及其直接链接[完整报告:95](/Users/flower/math/2026/B题/review-opt/detection-duties/REPORT.md:95)（第95—116行）。

可摘的精确合并反例：删原点及(1140,0)，剩余五站漏掉`(1560,840),(0,160),(1560,−840)`；三点MEC半径平方`28065114685440000000/27474370560000>1000²`。另对站对的两点`(1000,−80),(80,1760)`距离平方4232000>2000²。不是用采样无空洞证明覆盖。

复现取证：`R0 review-opt/q3-seven-free/REPORT.md 9 15`；`R1 review-opt/q3-seven-free/six_exact_rejections.json`；`R0 review-opt/detection-duties/REPORT.md 95 116`。历史精确见证复核入口分别为在`q3-seven-free/`执行`/Users/flower/math/2026/B题/mock/.venv/bin/python -B six_verify.py`，在`detection-duties/`执行同解释器`-B check_geometry.py`。

<a id="other-negative-evidence"></a>
### 4.7 其余指定研究：避免遗漏已有反证

下表 `[实测/统计]`，均按报告原精度。每行包含方案、数据、决定；P1—P5复跑命令见表后。取证可用`R0`配对应行号，不执行任何复跑也能定位数字。

| 被否方案 | 数据与理由 | 原始出处；复跑 |
|---|---|---|
| Q3阴性最小圆盘凸包`disk_hull` | 420局245.1539→243.8237，−1.3302（0.543%），区间[−1.8197,−0.8461]；48局慢、最差+654.8869，失手900→941。几何约束有效，尾部/失手不支持换默认 | [info-structure.md:79](/Users/flower/math/2026/B题/review-opt/info-structure.md:79)第79—87、108—116行；P1。只用此处新mock结果，不用该报告正式统计段 |
| 多源共用观测点`joint_hub` | Q3主RF3234→2251，却多9.2807 m/源、Δ+0.7642；Q4 62次RF有27次无信号、Δ+0.1230、最差+225.6774。局部预计节省未抵消绕行/接收不确定性 | 同报告第99—104、108—116行；P1 |
| 全局联合点代理路线`exact_joint` | Q3 244.739→242.754，−1.985，区间[−3.814,−0.330]，45局慢、最差+611.626；Q4 466.300→456.994，−9.306（2.00%），区间[−13.693,−4.740]，64局慢、最差+1884.146。TSP只解已知点代理，不能预测16源发现时机 | [travel-structural/REPORT.md:125](/Users/flower/math/2026/B题/review-opt/travel-structural/REPORT.md:125)第125—155行；各210局；P2 |
| Q3一次主要RF后重排`action_packets` | 210局244.990→241.114，−3.876（1.58%），区间[−5.793,−2.094]；61局慢、最差+789.168；无整局安全回退器 | 同报告第133—169行；P2 |
| Q3联合补测/清除`joint_split` | 420局244.6906→243.2098，−1.4808（0.605%），区间[−3.0682,+0.0808]；191局慢、最差+1125.07，最大+64.52%；训练选中但相对真实默认验证区间跨零，旧历史总检查未过 | [q3-joint-service/REPORT.md:3](/Users/flower/math/2026/B题/review-opt/q3-joint-service/REPORT.md:3)第3—9、29—38、81、89行；复跑§3.1 |
| Q3服务落点接管`duty_merge`/职责可行域移站`duty_flex` | 基线245.2669，分别244.8754/243.0990；后者−2.1680（0.8839%），97局慢、最差+1301.3362（79.7099%）；前者收益0.1596%，训练仍有+166.1234尾部。n<16空RF差均0 | [detection-duties.md:5](/Users/flower/math/2026/B题/review-opt/detection-duties.md:5)；[完整报告:132](/Users/flower/math/2026/B题/review-opt/detection-duties/REPORT.md:132)第132—165、201行；P3 |
| Q4短备用探点`short_backup` | 训练Δ+0.4604，最差+1389.75；虽少2681 m却多324次RF，交会信息质量退化 | [directional-probing/REPORT.md:34](/Users/flower/math/2026/B题/review-opt/directional-probing/REPORT.md:34)第34—38行；精确重跑该训练CLI报告未列，**无**；可R0取证 |
| Q4负反馈侧序`belief_side`/`reception_side` | 420局基线466.4854；训练预选465.4385（−0.2244%），对照465.1067（−0.2956%）；分别111/53局慢，最差+694.0022/+85.4860。小收益原型保留，未换默认；不能把验证更好的对照倒称预选赢家 | 同报告第104—126行；P4 |
| Q4单源局部预演`belief_rollout` | Δ−0.4512，区间[−2.6558,+1.6378]；200局慢、最差+1137.0080；少640次RF却多5801.80 m，朝外固定1000层反而增时 | 同报告第60—66、104—126行；P4 |
| 简单路线加RF/切频费`service`/`TimeProxy` | service独立60局Q3+1.1313、Q4+1.8480；Q4初筛−4.4262反转；TimeProxy初筛Q3+0.2362/Q4+0.2763，未推进。费用项更完整不等于对反馈后状态预测更准 | [opt-q34.md:114](/Users/flower/math/2026/B题/review-opt/opt-q34.md:114)第114—124行；P5 |
| 共享/冷却/横宽简单改参 | 6→1共享独立60局Q3+3.1249/Q4+2.4339；Q4冷却0为+2.2133、300为+0.8974；横宽60初筛−3.3505、独立+1.1419；拒绝 | 同报告第143—150行；P5。该六行淘汰表不是§4.1六个移动融合原型 |
| Q4原先验先测侧/包末共享 | 300局先测侧Δ+0.5044，区间[−1.688,+3.030]，138局慢、最差+2112.81；包末共享−0.1505但区间[−0.472,+0.241]，19局慢、最差+586.63，失手236→241；未推荐替换 | 同报告第152—172行；P5；与后来directional-probing侧序原型不是同一实验 |

补充消融反证 `[实测/统计]`，每题每设置1050独立场景，seed202660000—202661049；不是新优化的累计可加贡献：

| 被移除/替换项 | 实测结果（报告原精度） | 可用结论与边界 |
|---|---|---|
| 关闭共享 | Q3+20.1051/Q4+9.0297 s/源 | 少RF但总时间更多；支持现有共享的样本条件贡献 |
| 先扫描后逐源服务 | Q3+47.8004/Q4+63.3208 | 支持交织机制的条件贡献；不是每局优势 |
| Q4固定扫描相对顺序＋最小增量插源 | 470.1844→464.7962，Δ−5.3882（−1.146%），区间[−7.4462,−3.3944]；633快/417慢，最差+2930.280 s | **原动态站序相对此替代的优越性未获支持**；反证须保留；替代尾部仍大，不凭均值换默认 |
| 完整模型单独去光学格心 | 两题Δ0、1050/1050全清 | 本批未触发不证明可以删除有限兜底 |
| 退化定位时再去光学格心 | Q3最近邻测向仅62/1050全清；Q4禁双负截断仅650/1050全清 | 提前停止的低耗时不是提速；这是有条件正确性必要证据 |

出处：[B/ABLATION.md:71](/Users/flower/math/2026/B题/B/ABLATION.md:71)第71—85、124—168、171—223行；禁止相加不同消融贡献（第19行）。复现取证：`R0 B/ABLATION.md 124 223`；P6。

P1—P6 历史复跑索引（仅记录；须完整副本与新输出目录）：

```sh
# P1：info-structure.md 第160—168行；仅实验器，不运行含正式统计读取的分析器
cd /Users/flower/math/2026/B题/review-opt/info-structure
/Users/flower/math/2026/B题/mock/.venv/bin/python -B experiment.py --phase reproduce --count 420 --seed 202674000 --workers 4 --traces

# P2：travel-structural/REPORT.md 第175—188行
cd /Users/flower/math/2026/B题/B
/Users/flower/math/2026/B题/mock/.venv/bin/python -B ../review-opt/travel-structural/run_experiment.py --phase rerun-exact --count 210 --seed 202693000 --workers 4
/Users/flower/math/2026/B题/mock/.venv/bin/python -B ../review-opt/travel-structural/run_experiment.py --phase rerun-packets --count 210 --seed 202694000 --workers 4 --settings baseline,action_packets --problems 3

# P3：detection-duties/REPORT.md 第190—199行
cd /Users/flower/math/2026/B题/review-opt/detection-duties
/Users/flower/math/2026/B题/mock/.venv/bin/python -B experiment.py --phase reproduce-validation --count 420 --seed 202697000 --workers 4

# P4：directional-probing/REPORT.md 第146—151行
cd /Users/flower/math/2026/B题/review-opt/directional-probing
/Users/flower/math/2026/B题/mock/.venv/bin/python -B run_experiment.py --phase validation-replay --count 420 --seed 842000 --settings baseline,belief_side,reception_side,belief_rollout --workers 4
```

P5：`opt-q34-evidence.tar.gz`的冻结`probe.py,summarize.py`；原工作目录`/tmp/q34-opt-20260912`，脚本ROOT固定项目路径。报告第198—207行；先在完整临时副本解包并核对输入哈希。解包后工作目录运行：

```sh
/Users/flower/math/2026/B题/mock/.venv/bin/python -B probe.py validate 60 rerun-validate.jsonl base omni_negative pair_order share1 width60 service packet_share cool0 cool300
/Users/flower/math/2026/B题/mock/.venv/bin/python -B probe.py confirm 300 rerun-confirm.jsonl base omni_negative pair_order packet_share
/Users/flower/math/2026/B题/mock/.venv/bin/python -B summarize.py rerun-confirm.jsonl
```

P6：消融报告第263—272行；完整快照B及同级mock中运行，保留不全清的交互对照，不因更早失败记作收益：

```sh
cd /Users/flower/math/2026/B题/B
/Users/flower/math/2026/B题/mock/.venv/bin/python -B component_ablation.py --output experiments/runs/ablation-reproduce --workers 4
/Users/flower/math/2026/B题/mock/.venv/bin/python -B component_ablation_supplement.py --archive experiments/runs/ablation-reproduce --workers 4
```

### 4.8 摘用前核对表

| 易混淆项 | 本库采用的处理 |
|---|---|
| 默认与实验 | 清除门、Q3距离支配、Q3余程1.5为采纳项；其余明确标候选/否决/参照 |
| 理论与工程 | 151.846629/161.846629/196.462014为任意合法布局完整巡访范式的解析界；165.66452961532642为Q3固定七站样本的数值下界；410—420为Q4保留RF工作的工程参照 |
| 证书拒绝与反例 | unresolved/超时本身不能证明盲区；六站84候选、固定7/21站删测均另外有具体精确见证 |
| 数字重叠 | 147.41611694600087是训练诊断扫描＋清除服务圆移动界；69.12453641510758分解来自独立验证；不得拼成同一批账单 |
| 样本量 | 22320/800/2205等执行数不等于独立场景；30644为区域赋值检查；92088为守卫检查；反事实Q3 42组、Q4 126对 |
| 结果重跑 | 本次只做文档整理和只读取证；历史复跑命令未执行。各源文件/字段是可追溯依据，非本次重测报告 |
