"""Read archived official traces and regenerate four paper tables; no simulator calls."""
from collections import Counter, defaultdict
from decimal import Decimal, localcontext
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
TRACE_INDEX = json.loads((ROOT / 'data/experiment_index.json').read_text(encoding='utf8'))
OUT = ROOT / 'paper/tables'
OUT.mkdir(parents=True, exist_ok=True)
RUNS = ROOT / 'data/experiments'
SOURCES = {
    'ablation': '2026-09-13_official-ablation',
    'sensitivity': '2026-09-13_official-sensitivity',
    'q3_first': '2026-09-13_official-q3-fused-five',
    'q3_repeat': '2026-09-13_official-q3-fused-five-repeat',
    'q3_refinement': '2026-09-13_official-q3-refinement',
    'q4_fused': '2026-09-13_official-q4-fused-five',
    'q4_repeat': '2026-09-13_official-q4-nearest-five',
}
DEFAULTS = {
    3: dict(task_order='two_opt', trial_radius=50, share_limit=6,
            max_active=3, localization_weight=.08, remainder_weight=1.5),
    4: dict(dispatch='two_opt', trial_radius=35, share_limit=6,
            share_cooldown=150, transverse_m=40, fraction=.15, steps=10, pause_limit=16),
}
EXPECTED = {
    3: dict(DEFAULTS[3], task_order='nearest', trial_radius=65, max_active=2),
    4: dict(DEFAULTS[4], dispatch='nearest'),
}
LABELS = dict(trial_radius='试清门限', share_limit='顺路补测上限',
              max_active='主定位预算', localization_weight='定位代价权重',
              remainder_weight='余程权重', share_cooldown='负反馈冷却距离',
              transverse_m='横向探测目标距离', fraction='纵向探测比例',
              steps='交错探测预算', pause_limit='任务打断预算')
UNITS = dict(trial_radius='米', max_active='轮', share_cooldown='米',
             transverse_m='米', steps='轮', pause_limit='次')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str,
                               allow_nan=False) + '\n', encoding='utf8')


def read_trace(path):
    rows = [json.loads(x) for x in path.read_text(encoding='utf8').splitlines() if x.strip()]
    assert all(x['http_status'] == 200 and x['response']['accepted'] for x in rows), path
    ids = [x['request']['request_id'] for x in rows]
    assert len(ids) == len(set(ids)), path
    enters = [x for x in rows if x['path'] == '/enter']
    exits = [x for x in rows if x['path'] == '/exit']
    assert len(enters) == len(exits) == 1 and rows[0] == enters[0] and rows[-1] == exits[0], path
    start, end = enters[0]['response'], exits[0]['response']
    ms = end['real_timestamp_ms'] - start['real_timestamp_ms']
    assert ms > 0 and start['virtual_time_s'] == 0
    return dict(enter_real_timestamp_ms=start['real_timestamp_ms'],
                exit_real_timestamp_ms=end['real_timestamp_ms'],
                program_runtime_s=Decimal(ms) / 1000,
                exit_virtual_s=Decimal(str(end['virtual_time_s'])),
                accepted_requests=len(rows), trace=str(path.relative_to(ROOT)), trace_sha256=sha(path))


def load_cases():
    cases, source_audit, omitted = [], [], []
    old = {}
    for p, folder in [(3, 'q3-nearest-20260913'), (4, 'q4-ablation-metrics-20260913')]:
        path = ROOT / 'data/evidence' / folder / f'q{p}_per_case_metric_audit.json'
        old.update({c['case_code']: c for c in json.loads(path.read_text(encoding='utf8'))['cases']})
    for batch, name in SOURCES.items():
        folder = RUNS / name
        path = folder / 'runs.jsonl'
        raw = [json.loads(x) for x in path.read_text(encoding='utf8').splitlines() if x.strip()]
        source_audit.append(dict(batch=batch, path=str(path.relative_to(ROOT)),
                                 sha256=sha(path), archived_cases=len(raw)))
        for run in raw:
            a, robot = run['authoritative'], run['robot']
            if run['phase'] == 'calibration':
                omitted.append(dict(case_code=a['case_code'], batch=batch, reason='接入校验，不计入实验均值'))
                continue
            p = run['problem']
            assert robot['mode'] == 'practice' and robot['status'] == 'policy-completed'
            assert robot['mock_executions'] == 0
            assert a['problem_no'] == p and a['cleared_jammer_count'] == a['jammer_count'] > 0
            if batch == 'ablation':
                trace = ROOT / TRACE_INDEX[a['case_code']]['trace']
            else:
                trace = ROOT / TRACE_INDEX[a['case_code']]['trace']
            audit = read_trace(trace)
            virtual = Decimal(a['virtual_time_us']) / 1_000_000
            assert abs(audit['exit_virtual_s'] - virtual) <= Decimal('.000001')
            if batch == 'ablation':
                reference = old[a['case_code']]
                assert sha(trace) == reference['trace_sha256']
                assert math.isclose(float(audit['program_runtime_s']), reference['program_runtime_s'], abs_tol=1e-12)
            parameters = dict(DEFAULTS[p])
            if batch == 'ablation':
                variant = robot['variant']
                parameters['trial_radius'] = variant['gate']
                if variant['component'] == 'online_nearest':
                    parameters['task_order' if p == 3 else 'dispatch'] = 'nearest'
                parameters['ablation_component'] = variant['component']
            else:
                parameters.update(robot['parameters'])
            cases.append(dict(case_code=a['case_code'], problem=p, batch=batch,
                              phase=run['phase'], setting=run.get('setting', run.get('variant')),
                              block=run['block'], order=run['order'], parameters=parameters,
                              cleared=a['cleared_jammer_count'], actual_sources=a['jammer_count'],
                              virtual_time_us=a['virtual_time_us'],
                              average_localization_clear_s=virtual / a['cleared_jammer_count'],
                              client_policy_wall_s=robot['wall_s'],
                              clear_failures=a['clear_failure_count'],
                              optical_fallback_calls=robot['policy']['optical_fallback_calls'],
                              **audit))
    assert len(cases) == len({c['case_code'] for c in cases}) == 927
    assert len(omitted) == 4
    return cases, source_audit, omitted


def summarize(key, label, selected, section, baseline):
    assert selected, key
    metrics = ['cleared', 'average_localization_clear_s', 'program_runtime_s']
    means = {m: sum((Decimal(str(c[m])) for c in selected), Decimal(0)) / len(selected) for m in metrics}
    for m in metrics:
        assert math.isclose(float(means[m]), statistics.fmean(float(c[m]) for c in selected), rel_tol=1e-13)
    configs = {json.dumps(c['parameters'], sort_keys=True) for c in selected}
    row = dict(key=key, label=label, section=section, n=len(selected), means=means,
               all_clear_cases=sum(c['cleared'] == c['actual_sources'] for c in selected),
               total_clear_failures=sum(c['clear_failures'] for c in selected),
               total_optical_fallback_calls=sum(c['optical_fallback_calls'] for c in selected),
               sample_sd={m: statistics.stdev(float(c[m]) for c in selected) for m in metrics},
               parameters=[json.loads(c) for c in sorted(configs)],
               cases=[c['case_code'] for c in selected])
    if baseline is None:
        row['deviation_percent'] = {m: Decimal(0) for m in metrics[1:]}
    else:
        row['deviation_percent'] = {m: (means[m] / baseline['means'][m] - 1) * 100 for m in metrics[1:]}
    return row


def make_tables(cases):
    pick = lambda **kw: [c for c in cases if all(c[k] == v for k, v in kw.items())]
    q3 = pick(batch='q3_first') + pick(batch='q3_repeat')
    q4 = pick(batch='ablation', problem=4, setting='online_nearest__g35')
    for p, cs in [(3, q3), (4, q4)]:
        assert len(cs) == 10
        assert all({k: c['parameters'][k] for k in EXPECTED[p]} == EXPECTED[p] for c in cs)
    baselines = {
        3: summarize('q3_baseline', 'baseline（第二次正式方案）：最近邻＋65米＋max_active=2', q3, 'baseline', None),
        4: summarize('q4_baseline', 'baseline（第二次正式方案）：最近邻＋35米＋fraction=0.15＋share_limit=6', q4, 'baseline', None),
    }
    labels = [('full', 'two_opt任务排序'), ('online_nearest', '最近邻任务排序'),
              ('no_share', '关闭顺路已知源补测'), ('scan_then_service', '先扫描后清除'),
              ('no_negative', '关闭负反馈位置裁剪')]
    tables = []
    for p in (3, 4):
        gate = {3: 50, 4: 35}[p]
        rows = [baselines[p]]
        variants = labels + ([('nearest_sensing', '测向选点改为保收最近邻')] if p == 3 else [])
        for key, name in variants:
            if p == 4 and key == 'online_nearest':
                continue
            variant = f'{key}__g{gate}'
            cs = pick(batch='ablation', problem=p, setting=variant)
            assert len(cs) == 10
            rows.append(summarize(variant, f'{name}，{gate}米', cs, '原消融', baselines[p]))
        for gate in ([20, 80] if p == 3 else [20, 40, 80]):
            variant = f'full__g{gate}'
            cs = pick(batch='ablation', problem=p, setting=variant)
            assert len(cs) == 10
            rows.append(summarize(variant, f'two_opt任务排序，{gate}米', cs, '原消融', baselines[p]))
        tables.append(dict(number=p-2, problem=p, title=f'Q{p} 消融实验及正式采用方案对照', rows=rows))
    config = json.loads((RUNS / SOURCES['sensitivity'] / 'config.json').read_text(encoding='utf8'))
    comparison_labels = {
        3: 'two_opt排序＋50米＋max_active=3',
        4: 'two_opt排序＋35米＋fraction=0.15＋share_limit=6',
    }
    for p in (3, 4):
        rows = [baselines[p]]
        for s in config['settings']:
            if s['problem'] != p:
                continue
            setting = s['setting']
            if setting == 'baseline':
                label = comparison_labels[p] + '（宽扫对照）'
            else:
                k, value = setting.split('=')
                label = f'two_opt排序，{LABELS[k]}={value}{UNITS.get(k, "")}'
            cs = pick(batch='sensitivity', problem=p, phase='screen', setting=setting)
            assert len(cs) == 10
            rows.append(summarize(setting, label, cs, '单参数宽扫', baselines[p]))
        if p == 3:
            for setting, label, n in [('baseline', 'two_opt排序＋50米＋3轮（中止批次对照）', 3),
                                      ('candidate', 'two_opt排序＋65米＋2轮（中止批次候选）', 4)]:
                cs = pick(batch='q3_refinement', setting=setting)
                assert len(cs) == n
                rows.append(summarize('refinement_' + setting, label, cs, '追加探索', baselines[p]))
        else:
            for batch, label in [('q4_fused', '最近邻＋35米＋fraction=0.30＋share_limit=2'),
                                  ('q4_repeat', 'baseline 同配置后续复测（独立5局）')]:
                cs = pick(batch=batch)
                assert len(cs) == 5
                rows.append(summarize(batch, label, cs, '追加复测', baselines[p]))
        for setting, label, n in [('baseline', comparison_labels[p] + '（联合扰动同期对照）', 40),
                                  ('perturbed', 'two_opt排序联合随机扰动（每局参数不同）', 80)]:
            cs = pick(batch='sensitivity', problem=p, phase='robustness', setting=setting)
            assert len(cs) == n
            rows.append(summarize('robustness_' + setting, label, cs, '联合扰动', baselines[p]))
        tables.append(dict(number=p, problem=p, title=f'Q{p} 参数实验及追加复测结果', rows=rows))
    assert [len(t['rows']) for t in tables] == [9, 8, 26, 34]
    covered = {code for t in tables for row in t['rows'] for code in row['cases']}
    assert covered == {c['case_code'] for c in cases}
    return baselines, tables


def markdown_table(t):
    lines = [f'## 表{t["number"]}　{t["title"]}', '',
             '| 方案或参数设置 | 局数 | 平均清除数 | 平均定位清除时间（秒） | 时间偏移 | 平均程序运行时间（秒） | 运行时间偏移 |',
             '|---|---:|---:|---:|---:|---:|---:|']
    for r in t['rows']:
        m, d = r['means'], r['deviation_percent']
        label = r['label']
        if r['section'] == 'baseline':
            label = '**' + label + '**'
        lines.append(f'| {label} | {r["n"]} | {m["cleared"]:.2f} | {m["average_localization_clear_s"]:.2f} | '
                     f'{d["average_localization_clear_s"]:+.2f}% | {m["program_runtime_s"]:.4f} | '
                     f'{d["program_runtime_s"]:+.2f}% |')
    lines += ['', '注：偏移均相对于本表首行，按未舍入均值计算；负值表示耗时更短。所有列入案例最终均全部清除。']
    if t['number'] == 1:
        lines += ['Q3 baseline唯一指第二次正式方案：最近邻排序、trial_radius=65米、max_active=2、share_limit=6、localization_weight=0.08、remainder_weight=1.5，统计取同配置两轮各5局演练。消融对照以two_opt排序、trial_radius=50米、max_active=3、share_limit=6、localization_weight=0.08、remainder_weight=1.5为实验起点，分别改变行中所列机制或门限。这些组按所列配置进行实验，并非仅相对交付baseline改变一个机制。']
    elif t['number'] == 2:
        lines += ['Q4 baseline唯一指第二次正式方案：最近邻排序、trial_radius=35米、fraction=0.15、share_limit=6、share_cooldown=150米、transverse_m=40米、steps=10、pause_limit=16，统计取同配置10局演练。消融对照以two_opt排序及上述数值参数为实验起点，分别改变行中所列机制或门限；20/40/80米行仍为two_opt排序。']
    else:
        lines += ['本表唯一baseline为第二次正式方案；首行列出主要参数，完整配置见下文。单参数宽扫采用two_opt排序；只改变行中所列参数，其余数值按下文的宽扫配置固定。统计分母统一为第二次正式方案的同配置演练均值，原始实验配置不变。']
        if t['number'] == 3:
            lines += ['Q3 baseline：最近邻排序、trial_radius=65米、max_active=2、share_limit=6、localization_weight=0.08、remainder_weight=1.5。宽扫固定配置：two_opt排序、trial_radius=50米、share_limit=6、max_active=3、localization_weight=0.08、remainder_weight=1.5。中止批次仅完成对照3局、候选4局，全部保留，不能当作完整复验。baseline两轮5局已合并，未重复添加这10局。']
        else:
            lines += ['Q4 baseline：最近邻排序、trial_radius=35米、share_limit=6、share_cooldown=150米、transverse_m=40米、fraction=0.15、steps=10、pause_limit=16。宽扫固定配置：two_opt排序，trial_radius=35米、share_limit=6、share_cooldown=150米、transverse_m=40米、fraction=0.15、steps=10、pause_limit=16。后续同配置5局独立列示，不与原10局混并；联合扰动80局是多种配置的汇总，不是某一个参数方案。']
    return '\n'.join(lines) + '\n'


def latex_table(t):
    def escape(s):
        return s.replace('\\', r'\textbackslash{}').replace('_', r'\_').replace('%', r'\%').replace('&', r'\&')
    head = '方案或参数设置 & 局数 & 平均清除数 & $\\bar t$/秒 & $\\Delta_t$/\\% & $\\bar r$/秒 & $\\Delta_r$/\\% \\\\'
    lines = ['% UTF-8; load ctex, longtable, booktabs, array. Values match Markdown tables.',
             r'\begingroup\small\setlength{\tabcolsep}{3pt}',
             r'\begin{longtable}{p{0.37\textwidth}rrrrrr}',
             r'\caption{' + escape(t['title']) + r'}\label{tab:official-q' + str(t['problem']) + '-' + str(t['number']) + r'}\\',
             r'\toprule', head, r'\midrule\endfirsthead', r'\toprule', head, r'\midrule\endhead',
             r'\midrule\multicolumn{7}{r}{续下页}\\\endfoot', r'\bottomrule\endlastfoot']
    for r in t['rows']:
        m, d = r['means'], r['deviation_percent']
        lines.append(escape(r['label']) + f' & {r["n"]} & {m["cleared"]:.2f} & {m["average_localization_clear_s"]:.2f} & '
                     f'{d["average_localization_clear_s"]:+.2f} & {m["program_runtime_s"]:.4f} & '
                     f'{d["program_runtime_s"]:+.2f}' + r' \\')
    lines += [r'\end{longtable}\endgroup', '% Include the matching Markdown table notes in the manuscript.']
    return '\n'.join(lines) + '\n'


def formal_provenance():
    output = []
    for p, folder in [(3, 'q3-fused-formal-20260913'), (4, 'q4-nearest-formal-20260913')]:
        base = ROOT / 'data/formal' / f'q{p}' / 'attempt2'
        traces = list((base / 'results').rglob('requests.jsonl'))
        assert len(traces) == 1
        configs = list((base / 'results').rglob('config.json'))
        assert len(configs) == 1
        config = json.loads(configs[0].read_text(encoding='utf8'))
        params = config['parameters']
        assert params == EXPECTED[p], params
        report = base / 'REPORT.md'
        assert ('第 2 次' if p == 3 else 'formal_index=2') in report.read_text(encoding='utf8')
        output.append(dict(problem=p, formal_index=2, parameters=params,
                           config=str(configs[0].relative_to(ROOT)), config_sha256=sha(configs[0]),
                           report=str(report.relative_to(ROOT)), report_sha256=sha(report),
                           excluded_from_practice_means=True, **read_trace(traces[0])))
    return output


def write_paper_materials(baselines, tables, cases):
    lookup = {(t['number'], r['key']): r for t in tables for r in t['rows']}
    def val(t, key, metric='average_localization_clear_s', digits=2):
        return f"{lookup[t, key]['means'][metric]:.{digits}f}"
    def delta(t, key, metric='average_localization_clear_s'):
        return f"{lookup[t, key]['deviation_percent'][metric]:+.2f}%"
    def relative(t, a, b, metric='average_localization_clear_s'):
        return (lookup[t, a]['means'][metric] / lookup[t, b]['means'][metric] - 1) * 100
    notes = r'''# Q3、Q4 消融与参数实验论文素材

本材料依据2026年9月13日已归档的官方模拟器本地演练，整理四张结果表及可改入论文的正文。基准方案按各题第二次正式测试的实际冻结配置确认；正式测试单局成绩用于核对方案身份，不计入下列演练均值。

## 基准方案与数据范围

问题三的baseline为最近邻任务排序、试清门限65米、主定位预算2轮，其他参数为顺路补测上限6、定位代价权重0.08、余程权重1.5。该配置对应第二次正式案例`3VUE-GVZH-MPKV-GBWE`。统计样本取正式测试前两轮各5局演练，合计10局；两轮全部保留，不只选取成绩较好的第二轮。“最近邻＋50米＋max_active=3”是单列的配置对照组。

问题四的baseline为最近邻任务排序、试清门限35米，其他参数为顺路补测上限6、负反馈冷却距离150米、横向探测目标距离40米、纵向探测比例0.15、交错探测预算10轮、任务打断预算16次。该配置对应第二次正式案例`5FS5-MYSH-FKHB-PRX4`。为延续原消融每方案10局的比较口径，统一采用原消融中该配置的10局作为分母；正式测试前另有同配置5局复测，在表4单列，不与原10局混并。这是对统计分组的固定选择，不是按成绩筛选案例。

本次共纳入927个不同的官方演练案例：消融160局、参数宽扫500局、联合扰动240局、Q3融合方案10局、Q3中止复验7局、Q4融合参数候选5局、Q4第二次正式方案同配置复测5局。另有4局接入校验未计入结果表。表1与表3重复展示同一组Q3基准，表2与表4重复展示同一组Q4基准，不能把四表行数乘以局数当成独立总样本量。本次未重新调用模拟器，未混入本地mock结果。

## 统计口径（可用于论文方法部分）

实验采用官方模拟器生成的独立演练案例，记录清除干扰源个数、平均定位清除时间和程序运行时间。设第$j$局实际清除源数为$C_j$，官方累计虚拟时间为$T_j$，则单局平均定位清除时间为$t_j=T_j/C_j$。对于含$n$局的方案，三个报告指标分别计算为

$$
\overline C=\frac1n\sum_{j=1}^{n}C_j,\qquad
\overline t=\frac1n\sum_{j=1}^{n}\frac{T_j}{C_j},\qquad
\overline r=\frac1n\sum_{j=1}^{n}r_j.
$$

程序运行时间$r_j$统一取官方退出响应与进入响应的`real_timestamp_ms`之差并换算成秒，包含两次响应时间戳之间的程序计算和接口交互，不包含案例创建、进入前界面等待及结束后的归档。它属于真实经过时间，不能解释为纯CPU耗时。

定位清除时间与程序运行时间相对基准的偏移分别为

$$
\Delta_t=\left(\frac{\overline t}{\overline t_0}-1\right)\times100\%,\qquad
\Delta_r=\left(\frac{\overline r}{\overline r_0}-1\right)\times100\%.
$$

负值表示时间减少。每局等权，不以总虚拟时间除以总清除数替代逐局算术平均。计算使用未舍入数据，显示时才保留小数。10局组均除以10，追加复测和联合扰动按表中实际局数计算。

927局均最终清除全部实际干扰源，因此不同方案的平均清除数主要反映测试案例的源数构成，不能将平均清除数较大直接解释为清除能力更强。“全部清除”也不等于“没有失败的清除尝试”；失败动作已包含在官方虚拟总时间中。

消融与参数宽扫以各表注明的two_opt配置为实验起点。所有偏移以第二次正式方案的同配置演练均值为分母；对照组仍按实际参数标注，跨配置的均值差不能直接解释为只改变一个因素的效果。

## 四张结果表

'''
    text = notes + '\n'.join(markdown_table(t) for t in tables)
    text += '\n## 结果分析（可用于论文正文）\n\n'
    text += (
        f'问题三的消融结果见表1。正式采用方案的平均定位清除时间为{val(1, "q3_baseline")}秒，'
        f'平均程序运行时间为{val(1, "q3_baseline", "program_runtime_s", 4)}秒。'
        f'最近邻50米方案的平均定位清除时间为{val(1, "online_nearest__g50")}秒，'
        f'相对正式采用方案低{abs(relative(1, "online_nearest__g50", "q3_baseline")):.2f}%，'
        f'但程序运行时间高{relative(1, "online_nearest__g50", "q3_baseline", "program_runtime_s"):.2f}%。'
        f'先扫描后清除、测向选点改为保收最近邻的平均定位清除时间分别为'
        f'{val(1, "scan_then_service__g50")}秒和{val(1, "nearest_sensing__g50")}秒。'
        '这些结果表明，定位清除效率与程序计算耗时并不总是同向变化。'
        '以题目关注的平均定位清除时间衡量，现有演练数据没有显示正式采用的65米融合方案优于所有对照配置。'
        '该方案10局最终均全清，但累计出现8次失败的清除尝试；最近邻50米组为1次，'
        '两者案例不同，不能据此单独归因于门限变化。\n\n'
        f'问题四的消融结果见表2。在原8组各10局消融数据中，最近邻35米方案的平均定位清除时间'
        f'{val(2, "q4_baseline")}秒最低。two_opt排序、35米、fraction=0.15、share_limit=6的对照组为{val(2, "full__g35")}秒，'
        f'比最近邻基准高{relative(2, "full__g35", "q4_baseline"):.2f}%；'
        f'反向以two_opt排序、35米、fraction=0.15、share_limit=6的对照组为分母，最近邻方案对应的观测降幅为'
        f'{abs(relative(2, "q4_baseline", "full__g35")):.2f}%。'
        '两个百分比使用不同分母，不能互换。由于各组运行于不同官方案例，'
        '该结果支持其作为本批数据中表现较好的候选配置，尚不能证明其全局最优。\n\n'
        f'问题三的参数宽扫结果见表3。在two_opt排序基础上将顺路补测上限设为2时，'
        f'平均定位清除时间为{val(3, "share_limit=2")}秒，'
        f'相对正式采用方案的偏移为{delta(3, "share_limit=2")}。'
        f'将试清门限分别设为65米和80米时，该指标分别为{val(3, "trial_radius=65")}秒'
        f'和{val(3, "trial_radius=80")}秒。主定位预算为1轮时，虽然平均定位清除时间为'
        f'{val(3, "max_active=1")}秒，10局中累计发生36次失败清除和35次光学覆盖点清除尝试；'
        '预算为2轮的10局对应3次失败清除和0次光学覆盖点清除尝试。'
        '因而预算选择还需结合实际执行路径解释，不能仅凭某一组较低的均值确定。'
        '顺路补测、门限和定位预算的单参数结果均来自two_opt排序，不能将各自观测收益直接相加来预测融合方案。\n\n'
        f'问题四的参数结果见表4。在two_opt排序宽扫中，纵向探测比例0.30、顺路补测上限2分别得到'
        f'{val(4, "fraction=0.3")}秒和{val(4, "share_limit=2")}秒。'
        '将这两个参数同时加入最近邻35米方案后，5局平均定位清除时间为'
        f'{val(4, "q4_fused")}秒，相对统一基准为{delta(4, "q4_fused")}；'
        '第二次正式方案同配置（最近邻、35米、fraction=0.15、share_limit=6）的后续5局则为'
        f'{val(4, "q4_repeat")}秒，相对统一基准为{delta(4, "q4_repeat")}。'
        '后一批平均定位清除时间比融合参数批次低'
        f'{abs(relative(4, "q4_repeat", "q4_fused")):.2f}%，但其程序运行时间为'
        f'{val(4, "q4_repeat", "program_runtime_s", 4)}秒，高于融合参数批次的'
        f'{val(4, "q4_fused", "program_runtime_s", 4)}秒。'
        '该追加比较与采用fraction=0.15、share_limit=6的选择相符，但每组仅5个不同案例，只能作为描述性证据。\n\n'
        '联合扰动数据在表3、表4末尾保留。按本材料的逐局等权口径，Q3扰动组和同期two_opt固定配置对照的'
        f'平均定位清除时间分别为{val(3, "robustness_perturbed")}秒、{val(3, "robustness_baseline")}秒，'
        f'扰动组高{relative(3, "robustness_perturbed", "robustness_baseline"):.2f}%；'
        f'Q4分别为{val(4, "robustness_perturbed")}秒、{val(4, "robustness_baseline")}秒，'
        f'扰动组高{relative(4, "robustness_perturbed", "robustness_baseline"):.2f}%。'
        '这些同期比较与表中的统一基准偏移有不同分母。每题80局扰动和40局同期对照均最终全清，'
        '但全清结果不能代替效率稳健性检验。\n\n')
    text += r'''## 解释边界与论文使用说明

- two_opt排序同默认配置在不同批次的平均定位清除时间已有变化：Q3消融为247.50秒、参数宽扫为263.93秒；Q4分别为509.25秒和451.31秒。不能把不同批次之间的全部差异解释为参数或排序效果。
- Q3融合方案第一轮5局为271.91秒，第二轮5局为241.08秒；统一baseline采用全部10局的256.49秒。Q4同配置复测5局为440.09秒，原10局为463.81秒。所有批次保留，重复运行不构成同案例配对。
- 表中统一baseline用于结果整理，是事后确定的描述性比较分母。原参数宽扫的随机化、原同期对照及预设检验仍对应其原实验设计；不能直接把旧检验的p值或区间贴到新分母上。
- 原参数实验对48项宽扫比较进行Holm校正，未得到5%水平的显著性结论。原联合扰动检验采用源加权指标，其单侧97.5%比值上界Q3为1.08312、Q4为1.15711，均未小于预设1.05。这里没有用新的算术平均口径重新宣称其通过稳健性判据。该事实依据原冻结分析及`robustness.json`，不是从本四表推算的新检验。
- Q3中止批次实际完成3局对照和4局候选；Q3融合第二轮及Q4后续复测均为查看前批结果后的追加运行。本材料保留全部结果，不将其写成预先固定样本量的确认性优效试验。
- 可写“在本批官方演练中观察到平均定位清除时间较低”“在已测案例中全部完成清除”。不宜写“证明正式采用方案最优”“各模块均有显著贡献”“参数变化不影响性能”。对于Q3，正式采用方案在平均定位清除时间上并非所有已测方案中的最低值。
- 参数含义：`trial_radius`为试清门限；`share_limit`为单次顺路补测数量上限；`max_active`为Q3主定位预算；`localization_weight`与`remainder_weight`分别为定位代价与余程权重；Q4的`share_cooldown`控制负反馈后的补测冷却距离，`transverse_m`为横向探测目标距离，`fraction`为纵向探测比例，`steps`为交错探测预算，`pause_limit`为任务打断预算。预算为上限，不能写成每个源都执行满额轮数。

## 数据来源、复算与口径修订

四表共有77行，但baseline跨表重复出现；去重后为927局，累计清除11967个源。每局的实际参数、官方源数、虚拟总时间、进入/退出时间戳、失败清除次数、原始请求日志路径和SHA-256均见`逐局审计.json`。`四表数据.json`保存未舍入均值、偏移、组内标准差、全部案例清单和实际参数集合；`审计结果.json`记录检查结果。未将组内标准差当作相同场景的因果误差。

旧参数报告用`robot.wall_s`计时，本次四表统一使用官方进入与退出响应的时间戳。因此Q3基准程序运行时间从旧口径0.7247秒修订为0.7217秒，时间偏移也相应重算；定位清除时间和实际清除数不受影响。旧记录和旧报告保持原样，逐局审计同时保留两种程序时间以便核对。

原始来源包括：

- `data/experiments/2026-09-13_official-ablation`：160局正式纳入的消融演练及2局接入。
- `data/experiments/2026-09-13_official-sensitivity`：500局参数宽扫、240局联合扰动及2局接入；原冻结分析见`PLAN.md`、`analysis_plan.json`、`REPORT.md`、`robustness.json`。
- `data/experiments/2026-09-13_official-q3-fused-five`与`...-repeat`：Q3融合方案两轮各5局。
- `data/experiments/2026-09-13_official-q3-refinement`：Q3实际完成的7局参数复验。
- `data/experiments/2026-09-13_official-q4-fused-five`与`...-q4-nearest-five`：Q4两个后续候选各5局。
- `data/formal/q3/attempt2`、`data/formal/q4/attempt2`：第二次正式测试方案身份和冻结参数，不作为表中均值样本。

在项目根目录执行以下命令可只读核验原始数据并重建本目录的四表、正文和审计文件：

```sh
python experiments/build_tables.py
```

`.tex`文件为四表的LaTeX排版输入，可在加载`ctex`、`longtable`、`booktabs`、`array`的文档中使用；表号由论文实际位置自动编排。使用时须同时保留对应Markdown中的表注，尤其是各对照组的具体配置、实际局数与比较基准说明。
'''
    (OUT / '论文素材.md').write_text(text, encoding='utf8')
    kit = ROOT / 'paper/materials'
    kit.mkdir(exist_ok=True)
    (kit / 'kit-q34.md').write_text(
        '# 问题三、四论文素材：第二次正式测试方案\n\n'
        '当前模型推导见[建模说明](../modeling-q34.md)，'
        '运行入口见[当前代码说明](../../README.md)。'
        '以下四表与正文由同一复算脚本生成；可下载表格及审计文件位于'
        '[四表目录](../tables/四表汇总.md)。\n\n' + text, encoding='utf8')
    analysis = text.split('## 结果分析（可用于论文正文）\n\n', 1)[1].split('## 数据来源、复算与口径修订', 1)[0]
    (kit / 'kit-optimization.md').write_text(
        '# Q3、Q4 当前方案的实验结果分析\n\n'
        '基准统一为各题第二次正式采用方案；完整四表、参数和统计口径见'
        '[Q3/Q4论文素材](kit-q34.md)。\n\n' + analysis, encoding='utf8')


def main():
    with localcontext() as ctx:
        ctx.prec = 40
        cases, sources, excluded = load_cases()
        baselines, tables = make_tables(cases)
        provenance = formal_provenance()
        dump(OUT / '逐局审计.json', dict(cases=cases, sources=sources, excluded=excluded,
                                        formal2_provenance=provenance))
        dump(OUT / '四表数据.json', dict(baselines=baselines, tables=tables,
                                       unique_practice_cases=len(cases), displayed_rows=77))
        for t in tables:
            stem = f'表{t["number"]}_Q{t["problem"]}_' + ('消融实验' if t['number'] < 3 else '参数实验')
            (OUT / (stem + '.md')).write_text(markdown_table(t), encoding='utf8')
            (OUT / (stem + '.tex')).write_text(latex_table(t), encoding='utf8')
        write_paper_materials(baselines, tables, cases)
        (OUT / '四表汇总.md').write_text('# Q3、Q4 官方演练结果：以第二次正式采用方案为基准\n\n'
             '表1、表2为消融数据；表3、表4为参数宽扫、追加复测及联合扰动数据。完整统计口径和可用于论文的分析见《论文素材.md》。\n\n'
             + '\n'.join(markdown_table(t) for t in tables), encoding='utf8')
        audit = dict(complete=True, simulator_calls=0, unique_practice_cases=len(cases),
                     problem_counts=dict(Counter(c['problem'] for c in cases)),
                     batch_counts=dict(Counter(c['batch'] for c in cases)),
                     all_clear_cases=sum(c['cleared'] == c['actual_sources'] for c in cases),
                     total_cleared=sum(c['cleared'] for c in cases),
                     excluded_calibration_cases=len(excluded), excluded_formal_cases=2,
                     accepted_requests=sum(c['accepted_requests'] for c in cases),
                     table_rows=[len(t['rows']) for t in tables],
                     arithmetic_crosscheck=True, baseline_parameters_checked_against_formal2=True,
                     original_ablation_80_plus_80_trace_hashes_verified=True,
                     runtime_definition='(exit.real_timestamp_ms-enter.real_timestamp_ms)/1000',
                     max_abs_client_vs_official_runtime_s=max(abs(c['client_policy_wall_s'] - float(c['program_runtime_s'])) for c in cases))
        dump(OUT / '审计结果.json', audit)
        print(json.dumps(audit, ensure_ascii=False, indent=2))
        for p, b in baselines.items():
            print('BASELINE', p, json.dumps(b['means'], default=str))


if __name__ == '__main__':
    main()
