"""Rebuild manuscript tables and analysis from archived paired ablation results."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import component_ablation as a


def table(headers, rows):
    return '\n'.join(['|'+'|'.join(headers)+'|', '|'+'|'.join(['---']*len(headers))+'|'] +
                     ['|'+'|'.join(map(str,row))+'|' for row in rows])+'\n'


def read(path):
    return json.loads(path.read_text())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,required=True)
    args=parser.parse_args();out=args.archive.resolve()
    train=read(out/'training/summary.json');validation=read(out/'validation/summary.json')
    stress=read(out/'supplement/stress/summary.json')
    interaction=read(out/'supplement/interaction_validation/summary.json')
    idx={(r['problem'],r['setting']):r for r in validation}
    ix={(r['problem'],r['setting']):r for r in interaction}
    config=read(out/'config.json')
    relative=str(out.relative_to(a.ROOT))
    report=['# Q3/Q4 组件消融测试',
        '本报告仅使用同级本地 mock 完整执行策略和协议；没有访问官方模拟器、触发正式测试或修改 `models/paper-full.md`。主候选默认行为不变。所有消融从 `bounded_candidates.build` 构建后只改变该实验实例；不修改生产类、模块全局变量或默认配置。',
        '独立验证的主要结果：关闭共享使Q3/Q4增加20.1051/9.0297秒/源，取消扫描与服务交织增加47.8004/63.3208秒/源；全部单因素设置均1050/1050全清。Q4固定扫描相对顺序的替代反而节省5.3882秒/源，原动态站序相对该替代的必要性未获支持，且替代仍有417局变慢，不能直接据均值换默认。光学网格单独移除在完整基线中未触发；在最近邻测向/禁双负截断的交互对照中再移除网格，Q3/Q4分别仅62/1050、650/1050全清，构成有条件的正确性必要证据。',
        '## 方法与适用范围',
        f'主分析每题每设置训练210局（种子202650000—202650209），独立验证1050局（202660000—202661049），两组互不重叠，也不与既有敏感性种子重叠。Q3共11设置、Q4共9设置，共25,200次主分析执行。定义在训练前固定；所有设置均进入验证，不挑赢家、不据验证调参。训练的用途是核对生效路径与初步效应，不是优化旋钮。',
        '每105局遍历源数10—16 × 均匀/边缘/聚簇 × iid/平滑/恒+1°/恒−1°/空间±1°；重复轮交替均匀1000—1500米半径和固定1000米，Q4含50%定向源并交替均匀/向外朝向。Q3/Q4同号种子分别按本题生成；同题各消融共享完全相同的场景与位置键控静态误差场。不是官方真实分布的估计。',
        r'主指标为 $\tau=\sum_iT_i/\sum_iN_i$，$N_i$ 为真实源数，仅由事后评价器读取；策略从未读取真值。效应 $\Delta\tau=\tau_{\mathrm{ablation}}-\tau_{\mathrm{full}}$，正值表示完整组件节省了相应秒/源；比例分母为完整基线。逐局回退比较整局时间，容差 $10^{-6}$ 秒。配对95%区间用4000次整局bootstrap，每次重新计算源加权比值，随机种子20260912；未作多重比较校正。',
        r'账本逐局验证 $T=L/5+5M+S+5C_s+3C_f$，容许逐动作微秒舍入误差。移动包括所有接受的测量/清除动作，M是全部真实RF，S是初始频道1起算的真实测量切频，失手是全部失败清除（不限提前试探）。表中M/S/失手为累计次数，L为累计米。',
        '失败、未全清和异常不剔除，不改用已清源数作分母。缺失组件使策略首次无法完成时，显式停止并exit，保存完整动作前缀和未清频道；该行的时间仅是停止前耗时，不能视为全清效率，不能因更早失败就称提速。回退表对这类局另列不可比数，并只在成对全清局统计快/慢/同。原始CSV另存全部局的字面耗时差。',
        '每项效应是相对于完整模型的条件效应，包含测量、清除、共享、调度联动，不能把各行贡献相加，也不是唯一的因果份额或Shapley分摊。不宣称逐局占优。',
        '## 真实路径与精确消融定义',
        'Q3：`OmniNegativeCompletionPolicy → CoupledCompletionPolicy → CompletionClearancePolicy`；Q4：`CoupledWidthPolicy → InterleavedMixin.source_packet`。建模文档/旧评审中“Q3历史阴性未接入”的时点描述已落后于当前入口，本次以实际代码为准。',
        table(['ID','被替换/移除的实际行为','保留与命名边界'],[
            ['no_negative','Q3移除真实阴性与成功锚点的距离支配半平面；Q4令包内双负clip为恒等映射','保留正示向角更新、完整两点探测、终身预算、冷却、范围跳扫与光学兜底；不是取消全部阴性处理'],
            ['no_share','share=False，关闭定位/清除位置给其他已知源的可选补测','站扫仍会测已知未清频道；不称所有RF都变为专程'],
            ['scan_first','未扫站先行，扫描完后按最近源逐个完成，Q4不再在源间打断','保留扫描站间按实际位置的在线排序、16已知源上限免扫、扫描时near立即清除'],
            ['fixed_scan','dispatch_model=locked：冻结原站相对次序，以最小增量插入源任务','仍按实际位置重算源插入，不是完全固定巡回；也更换了任务插入启发式，效应不能独归扫描适应性'],
            ['online_nearest','task_order/dispatch=nearest：在线联合任务首项按最近代理点选择','去掉在线联合路径的2-opt改良；保留离线冻结布局/站序，不是完全取消所有2-opt'],
            ['no_early_trial','trial_radius=0；Q4同步bracket_trial_radius=0','仅关闭每源一次提前中心试探；保留兜底中心试清和格心覆盖，不承诺所有清除都已认证'],
            ['no_optical_grid','保留兜底中心试清，但禁止其失败后开始格心遍历','第一次需要缺失的网格时显式失清停止，不假装已清或重置定位预算'],
            ['vertex_prior','仅Q3：area_prior=False，用原顶点协方差和稀疏假设点替换面积积分','仍用协方差后验与完工路程综合评分；不称完全取消先验'],
            ['nearest_sensing','仅Q3：用原候选中通过原保收筛选的最近点替换整个综合评分','保留候选集合、去重、保收条件；无合格候选时只允许保收中心，否则显式失败；移除的是面积/协方差/完工路程综合排名'],
            ['certified_only','联合控制：trial_radius=0，并禁止所有非认证清除；仅留MEC≤20−1e−5和合法near认证','这才对应只凭认证清除；同时取消兜底非认证中心/格心动作，不是单个trial_radius组件的纯贡献'],
        ]),
        'Q4主探点由有界宽度的成对几何构造，默认任务代理为center；没有使用Q3面积积分或协方差测向选点，故这两行Q4为不适用。`AdaptiveOrder`包装器也未在当前主入口实例化，实际在线路线来自`remaining_route`；本报告只测试该真实路径。',
        '`route_ablation.py`研究的是静态格点路线、随机算法、固定比较预算和5个算法种子；`polish=False`仍有2-opt热启动。其静态路线米数不能代替Q3/Q4完整任务时间，不能复用为本轮全清证据。仅沿用同输入配对思想，本轮重新执行完整策略。',
        '计数说明：Q4的原`bracket_pair_cuts`在禁剪组仍是进入双负分支的次数，因为仅替换了clip；实际应用的双负裁剪数在该组为0，等于分支数减`ablation_disabled_negative_calls`。Q3的禁用hook次数则包括各类反馈，不是“省掉的有效裁剪数”。表格不把这些原始分支数误报成成功裁剪。',
        '## 训练结果（每设置210局）',
        table(['题目','设置','秒/源','Δ秒/源','全清/局数'],[
            [f"Q{r['problem']}",r['setting'],f"{r['seconds_per_source']:.4f}",f"{r['delta']:+.4f}",f"{r['all_cleared']}/{r['runs']}"] for r in train])]
    for p in (3,4):
        rows=[r for r in validation if r['problem']==p]
        report += [f'## Q{p} 独立验证（每设置1050局）',
            table(['设置','秒/源','Δ秒/源','Δ%','配对95%区间','全清/局数','全清率变化pp'],[
                [r['setting'],f"{r['seconds_per_source']:.4f}",f"{r['delta']:+.4f}",f"{r['delta_percent']:+.3f}",
                 f"[{r['ci'][0]:+.4f}, {r['ci'][1]:+.4f}]",f"{r['all_cleared']}/{r['runs']}",f"{r['clear_rate_delta_pp']:+.3f}"] for r in rows]),
            '### 总费用分项及其相对完整模型变化',
            table(['设置','测量M（Δ）','切频S（Δ）','失手（Δ）','移动L米（Δ）','格心清除次数'],[
                [r['setting'],f"{r['measurements']} ({r['delta_measurements']:+})",f"{r['switches']} ({r['delta_switches']:+})",
                 f"{r['misses']} ({r['delta_misses']:+})",f"{r['distance_m']:.1f} ({r['delta_distance_m']:+.1f})",r['optical_fallback_calls']] for r in rows]),
            '### 逐局回退',
            '下面的“更快/更慢”均指消融相对完整模型，故消融更快的局也正是完整模型相对该替代发生回退的局。最差秒数与最大比例可能来自不同场景。',
            table(['设置','更快/更慢/相同（成对全清）','不可比局','最差增加秒','最大增加%','最差秒数场景'],[
                [r['setting'],f"{r['complete_faster']}/{r['complete_slower']}/{r['complete_same']}",r['runs']-r['paired_complete'],
                 f"{r['worst_s']:.3f}",f"{r['worst_percent']:.3f}",r['worst_case']] for r in rows])]
    report += ['## 完整模型下的条件贡献与反证']
    for setting in ('no_negative','no_share','scan_first','fixed_scan','online_nearest','no_early_trial','vertex_prior','nearest_sensing'):
        values=[]
        for p in (3,4):
            if (p,setting) not in idx:continue
            r=idx[p,setting]
            evidence=('支持完整组件提高样本平均效率' if r['ci'][0]>0 else
                      '替代做法在本样本更快，原设计优越性未获支持' if r['ci'][1]<0 else
                      '区间跨零，平均必要性证据不足')
            values.append(f"Q{p} {r['delta']:+.4f}秒/源（{r['delta_percent']:+.3f}%），{evidence}；消融更快/更慢{r['complete_faster']}/{r['complete_slower']}局")
        report.append(f"- **{a.NAMES[setting]}**："+'；'.join(values)+'。')
    report += ['## 光学兜底：普通单因素与正确性压力必须分开',
        '主分析、独立验证及既有45局压力集的完整模型均未调用光学格心遍历，单独关掉网格时均未失清，时间差为0。故不能声称“单因素结果已经证明完整主候选必然需要网格”；也不能用未触发来证明任意合法输入均可删除它。',
        '有限格心覆盖为保留外包区域提供不依赖后续RF收缩的终止保障：28米方格的半对角线约19.799米，小于物理清除半径20米。删掉该步骤后，既有有限终止论证不再覆盖“主动预算耗尽且中心试清失败”的状态。',
        '训练已观察到Q3最近邻测向、Q4关闭双负截断后会调用网格，因此在看到补充结果前固定2×2对照：Q3综合/最近邻测向×网格开/关；Q4双负截断开/关×网格开/关。完整复用主训练与独立验证的全部场景，不筛选坏种子、不重新调参。补充属于训练启发的交互检验，不冒称训练前预注册的单因素。',
        table(['题目','设置','停止前秒/真实源','较完整Δ','全清/局数','全清率变化pp','测量','切频','失手','移动米'],[
            [f"Q{r['problem']}",r['setting'],f"{r['seconds_per_source']:.4f}",f"{r['delta']:+.4f}",
             f"{r['all_cleared']}/{r['runs']}",f"{r['clear_rate_delta_pp']:+.3f}",r['measurements'],r['switches'],r['misses'],f"{r['distance_m']:.1f}"] for r in interaction])]
    for p, weak, combo in ((3,'nearest_sensing','nearest_without_grid'),(4,'no_negative','negative_without_grid')):
        w,c=ix[p,weak],ix[p,combo]
        report.append(f"Q{p}：在{a.NAMES[weak]}条件下，保留网格全清{w['all_cleared']}/{w['runs']}，关闭网格仅{c['all_cleared']}/{c['runs']}，减少{w['all_cleared']-c['all_cleared']}个全清局（{100*(c['all_cleared']-w['all_cleared'])/c['runs']:.3f}个百分点）。因此网格在该退化定位条件下是正确性保障，不是可用更低停止耗时抵偿的效率选项。组合行低耗时来自提前停止，不能解释为收益。")
    report.append('失败见证已按原场景重放：`q3_202660000`在最近邻定位下，禁网格于中心试清失败时停止，已清0/10；保留网格则用35次格心清除请求完成10/10。`q4_202660005`在禁双负截断下，禁网格停止时已清6/10；保留网格只需1次格心清除请求，最终完成10/10。两组在缺失组件被调用前的全部接受动作与反馈逐项一致，见`failure_witness_q3.json`和`failure_witness_q4.json`。停止时的未清源数只表示剩余任务，不声称每个剩余源都独自无法清除。')
    report.append(table(['交互设置','题目','更快/更慢/相同（成对全清，相对完整模型）','不完整、不可比局'],[
        [r['setting'],f"Q{r['problem']}",f"{r['complete_faster']}/{r['complete_slower']}/{r['complete_same']}",r['runs']-r['paired_complete']]
        for r in interaction if 'without_grid' in r['setting']]))
    report += ['上述交互同时说明：负信息裁剪/综合评分可由光学搜索代偿，所以仅删除它们时主要体现效率贡献；网格提供抵御这些定位退化的完成保障。该条件结论不等于证明其在完整主策略的每局都必需。',
        '“仅凭认证清除”联合控制与“关闭提前试探”在本轮单因素场景的时间及全清结果一致，但两者代码行为并不等价：前者没有非认证光学兜底。不能从本轮零失手推成全输入终止保证。',
        '## 既有压力集（45局/题/设置，单列）',
        '沿用清除门验证归档的边界向外/相切、近共线、远端频道聚簇、半径转换场景，来源及SHA256见补充config。它们已用于历史分析，不称全新独立泛化样本，不与1050局验证混合。',
        table(['题目','设置','Δ秒/源','全清/局数','测量','切频','失手','移动米'],[
            [f"Q{r['problem']}",r['setting'],f"{r['delta']:+.4f}",f"{r['all_cleared']}/{r['runs']}",r['measurements'],r['switches'],r['misses'],f"{r['distance_m']:.1f}"] for r in stress]),
        '## 复现与审计',
        f'归档：`{relative}/`。`training`和`validation`各含fixtures、逐局trials.jsonl、配对paired.csv、summary.json/csv及completion.json；失败行包含完整动作前缀。`supplement`含压力集和交互两阶段同口径文件。论文草表另见`ABLATION_PAPER_TABLE.md`及归档内同名文件、LaTeX片段。',
        '主分析25,200次，压力900次，交互训练1,680次、验证8,400次，共36,180次有效执行；其中失败完成照实计入全清率，不等同于程序错误。主验证为每题1050个独立场景，重复基线执行不增加独立样本量。',
        '一次补充脚手架尝试在压力集完成后遇到Python进程池对局部克隆函数的序列化错误；没有产生交互计分行，原900次重复压力执行及错误日志保存在`supplement-setup-attempt`，不混入36,180次计数。修正为模块级worker后完整重跑；该问题不涉及策略或模拟器反馈。',
        '4项契约测试检查实例隔离、Q3半平面移除、Q4仍完整执行双负对及真实基线与既有harness逐局一致。`audit.json`记录全部结果的对齐、组件命中、异常、账本和生产文件完整性检查；共1671次失败完成均来自预定禁网格交互，策略意外异常0，认证失手0，最大账本舍入差约0.00004968秒。原始Q4禁剪组的分支计数命名边界已在上文说明。',
        '在B目录运行，输出目录须不存在：',
        '```sh\n/Users/flower/math/2026/B题/mock/.venv/bin/python -B component_ablation.py --output experiments/runs/ablation-reproduce --workers 4\n/Users/flower/math/2026/B题/mock/.venv/bin/python -B component_ablation_supplement.py --archive experiments/runs/ablation-reproduce --workers 4\n/Users/flower/math/2026/B题/mock/.venv/bin/python -B component_ablation_report.py --archive experiments/runs/ablation-reproduce\n/Users/flower/math/2026/B题/mock/.venv/bin/python -B -m unittest discover -s tests -p test_component_ablation.py -v\n```',
        '如未来生产文件变化，应在新临时父目录中把`code_snapshot`复制为`B`、`mock_snapshot`复制为同级`mock`，再放入归档的补充/报告脚本；补充脚本所用旧压力fixtures也已完整保存在`supplement/stress/fixtures.json`，可按config中的来源相对路径恢复。使用指定Python从该快照B目录执行。已有结果不能自动代表后续版本。']
    document='\n\n'.join(report)+'\n'
    (a.ROOT/'ABLATION.md').write_text(document)
    (out/'ABLATION.md').write_text(document)
    # Compact manuscript-ready paired Q3/Q4 mapping; underlying count tables above stay available.
    paper=['# Q3/Q4 消融表格草稿（可引用，未写入论文）',
        '为检验各组件对任务效率与完成性的作用，在相同源场景和静态误差场上配对运行完整模型与组件替代模型。训练与验证种子相互独立；下表使用每题1050局验证结果。评价指标为总虚拟时间与总真实源数之比。正差值表示删除该组件后耗时增加。',
        table(['消融/替代','Q3 Δ秒/源 [95%区间]','Q3 全清率','Q4 Δ秒/源 [95%区间]','Q4 全清率'],[
            [a.NAMES[setting]]+sum(([
                f"{idx[p,setting]['delta']:+.4f} [{idx[p,setting]['ci'][0]:+.4f}, {idx[p,setting]['ci'][1]:+.4f}]",
                f"{idx[p,setting]['all_cleared']}/{idx[p,setting]['runs']}"
                ] if (p,setting) in idx else ['不适用','—'] for p in (3,4)),[])
            for setting in a.NAMES if setting!='baseline']),
        f"完整模型Q3、Q4分别为{idx[3,'baseline']['seconds_per_source']:.4f}和{idx[4,'baseline']['seconds_per_source']:.4f}秒/源。各项差值不可直接相加。固定扫描行仍允许源任务插入；在线最近邻行只移除在线联合路线改良。认证控制是联合移除非认证清除，不能当作纯提前试探效应。",
        f"关闭顺路补测后，Q3、Q4分别增加{idx[3,'no_share']['delta']:.4f}和{idx[4,'no_share']['delta']:.4f}秒/源；扫描与服务分阶段执行分别增加{idx[3,'scan_first']['delta']:.4f}和{idx[4,'scan_first']['delta']:.4f}秒/源。这些结果量化了共享观测和联合调度的样本效率作用，不能推出逐局占优。",
        '单独关闭光学网格在上述样本中未改变结果，因完整模型未触发格心搜索。补充交互对照保持其余条件相同：',
        table(['问题','定位替代','保留网格全清','关闭网格全清','全清率变化pp'],[
            [f'Q{p}',a.NAMES[weak],f"{ix[p,weak]['all_cleared']}/1050",f"{ix[p,combo]['all_cleared']}/1050",
             f"{100*(ix[p,combo]['all_cleared']-ix[p,weak]['all_cleared'])/1050:.3f}"]
            for p,weak,combo in ((3,'nearest_sensing','nearest_without_grid'),(4,'no_negative','negative_without_grid'))]),
        '当定位采用上述退化方案时，去除光学网格会降低全清率，说明有限覆盖兜底在这些条件下承担正确性保障；停止前耗时较低不构成效率优势。该结论不扩张为完整主候选在每个合法输入上都必须使用网格。',
        '逐局回退、全部费用计数、训练及压力结果见ABLATION.md。数据仅来自本地合成mock，不代表官方场景分布。']
    paper_text='\n\n'.join(paper)+'\n'
    (a.ROOT/'ABLATION_PAPER_TABLE.md').write_text(paper_text)
    (out/'ABLATION_PAPER_TABLE.md').write_text(paper_text)
    tex=['% Requires booktabs and a Chinese-capable LaTeX document. Unit: seconds/source.',
         r'\begin{tabular}{lrrrr}',r'\toprule',r'消融设置 & Q3时间差 & Q3全清 & Q4时间差 & Q4全清 \\',r'\midrule']
    for setting in a.NAMES:
        if setting=='baseline':continue
        cells=[a.NAMES[setting]]
        for p in (3,4):
            if (p,setting) in idx:
                r=idx[p,setting];cells += [f"{r['delta']:+.4f}",f"{r['all_cleared']}/{r['runs']}"]
            else:cells += ['---','---']
        tex.append(' & '.join(cells)+r' \\')
    tex += [r'\bottomrule',r'\end{tabular}',
            '% Differences are paired, source-weighted and non-additive. Grid-only removal was not triggered in the full baseline.',
            '% See ABLATION_PAPER_TABLE.md for conditional completion failures in the factorial controls.']
    (out/'ablation_paper_table.tex').write_text('\n'.join(tex)+'\n')
    print('Wrote ABLATION.md, ABLATION_PAPER_TABLE.md and LaTeX table.')

if __name__=='__main__':main()
