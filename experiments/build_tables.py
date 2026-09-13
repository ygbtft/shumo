"""Read archived official traces and regenerate four experiment tables; no simulator calls."""
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
OUT = ROOT / 'outputs/tables'
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


def main():
    OUT.mkdir(parents=True, exist_ok=True)
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
        (OUT / '四表汇总.md').write_text('# Q3、Q4 官方演练结果：以第二次正式采用方案为基准\n\n'
             '表1、表2为消融数据；表3、表4为参数宽扫、追加复测及联合扰动数据。统计口径见 experiments/README.md。\n\n'
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
