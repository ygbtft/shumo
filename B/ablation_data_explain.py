"""Postprocess frozen results into an accessible data index and scene explanations.

Analysis-only companion: does not change the frozen experiment or rerun strategies.
Its own source hash is recorded independently from the execution snapshot.
"""
import argparse
import csv
import gzip
import hashlib
import json
import shutil
from pathlib import Path


def table(headers, rows):
    return '\n'.join(['|'+'|'.join(headers)+'|','|'+'|'.join(['---']*len(headers))+'|']+
                     ['|'+'|'.join(map(str,r))+'|' for r in rows])


def f(value):
    return '不作效率比较' if value is None else f'{value:+.3f}'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args().output.resolve()
    rows=json.loads((out/'validation/summary.json').read_text())
    gates=json.loads((out/'validation/gate_comparisons.json').read_text())
    audit=json.loads((out/'audit.json').read_text())
    summaries={(r['problem'],r['variant']):r for r in rows}
    costs=['move_s','measure_s','switch_s','clear_success_s','clear_failure_s']
    mechanism_checks=[]
    for phase in ('pilot','validation','stress'):
        grouped={}
        with (out/phase/'trials.jsonl').open() as stream:
            for line in stream:
                r=json.loads(line); stats=r['stats']; key=(r['problem'],r['variant'])
                record=grouped.setdefault(key,dict(phase=phase,problem=r['problem'],variant=r['variant'],
                    runs=0,negative_cuts=0,negative_cut_cases=0,raw_pair_branches=0,
                    disabled_pair_branches=0,shared_measurements=0,range_skips=0,
                    early_attempts=0,early_successes=0,grid_attempts=0))
                actual=(stats.get('omni_negative_cuts',0) if r['problem']==3 else
                        stats.get('bracket_pair_cuts',0)-stats.get('ablation_disabled_negative_calls',0))
                assert actual>=0
                if r['component']=='no_negative' or (r['problem']==4 and r['component']=='weak_no_grid'):
                    assert actual==0
                record['runs']+=1; record['negative_cuts']+=actual; record['negative_cut_cases']+=actual>0
                if r['problem']==4:
                    record['raw_pair_branches']+=stats.get('bracket_pair_cuts',0)
                    record['disabled_pair_branches']+=stats.get('ablation_disabled_negative_calls',0)
                record['shared_measurements']+=stats.get('shared_known_measurements',0)
                record['range_skips']+=stats.get('certified_range_scan_skips',0)
                for k in ('early_attempts','early_successes','grid_attempts'): record[k]+=r[k]
        mechanism_checks.extend(grouped.values())
    with (out/'mechanism_checks.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(mechanism_checks[0]));writer.writeheader();writer.writerows(mechanism_checks)
    primary=[r for r in rows if r['family']=='core' and r['component']!='full']
    lines=['# 先看这里：消融实验数据',
           f"已完成{audit['executions']:,}次执行，其中正式验证每题2100个新场景；8项契约与统计测试通过，全部轨迹及动作账本已核验，{audit['replayed_runs']}次代表场景重放一致。完整策略与各普通组件对照的全清情况见下表；缺失网格的交互失败单独报告。",
           '## 1. 拿掉一个机制，究竟多花了多少时间？',
           '每行差值都以相同门限的完整策略为参照，正数表示拿掉该机制后更慢。五项成本差相加即总差值，成功清除项在全清对照中为零。',
           table(['题目','门限','移除/替代','总Δ秒/源','移动Δ','检测Δ','切频Δ','成功清除Δ','失败清除Δ','全清'],
             [[f"Q{r['problem']}",f"{r['gate']:g}",r['label'],f(r['delta_s']),
               *[f(r['delta_'+c]) for c in costs],f"{r['all_cleared']}/{r['runs']}"] for r in primary]),
           '## 2. 这些机制在20米下还有效吗？']
    comparison=[]
    for p in (3,4):
        default={3:50,4:35}[p]
        for r in primary:
            if r['problem']!=p or r['gate']!=default:continue
            other=summaries[p,f"{r['component']}__g20"]
            supported=lambda x:x['delta_s'] is not None and x['ci95_s'][0]>0 and x.get('p_holm',1)<.05
            if supported(r) and supported(other):
                conclusion='两种门限下均有平均收益'
            elif supported(r): conclusion='当前门限支持，20米复核证据不足'
            elif supported(other): conclusion='20米支持，当前门限证据不足'
            else: conclusion='不能确认稳定平均收益'
            if supported(r) and r['delta_percent']<1 and supported(other) and other['delta_percent']<1:
                conclusion+='，但均不足1%'
            comparison.append([f'Q{p}',r['label'],f"{r['delta_percent']:+.2f}%" if r['delta_percent'] is not None else '不可比',
                               f"{other['delta_percent']:+.2f}%" if other['delta_percent'] is not None else '不可比',conclusion])
    lines += [table(['题目','机制','当前门限耗时增加','20米耗时增加','结论'],comparison),
        '## 3. 20米、当前门限、宽门限如何取舍？',
        table(['题目','门限','秒/源','全清','累计失手','提前试清成功/尝试','兜底中心/网格尝试'],
          [[f"Q{r['problem']}",f"{r['gate']:g}",f"{r['seconds_per_source']:.3f}" if r['seconds_per_source'] is not None else '不可比',
            f"{r['all_cleared']}/{r['runs']}",r['misses'],f"{r['early_successes']}/{r['early_attempts']}",
            f"{r['fallback_center_attempts']}/{r['grid_attempts']}"] for r in rows if r['component']=='full'])]
    for p in (3,4):
        default={3:50,4:35}[p]
        options=[r for r in rows if r['problem']==p and r['component']=='full' and r['seconds_per_source'] is not None]
        fastest=min(options,key=lambda x:x['seconds_per_source'])
        twenty=summaries[p,'full__g20']; current=summaries[p,f'full__g{default}']
        delta=twenty['seconds_per_source']-current['seconds_per_source']
        lines.append(f"Q{p}：在本次预定候选中，{fastest['gate']:g}米的样本平均耗时最低，为{fastest['seconds_per_source']:.3f}秒/源。"
                     f"20米相对当前{default}米改变{delta:+.3f}秒/源（{100*delta/current['seconds_per_source']:+.3f}%），"
                     f"累计失手从{current['misses']}变为{twenty['misses']}。这是门限取舍证据，不据此自动修改默认参数。")
        if fastest['gate']!=default:
            comparison=next(g for g in gates if g['problem']==p and g['from_gate']==default and g['to_gate']==fastest['gate'])
            lo,hi=comparison['ci95_s']
            lines.append(f"{default}→{fastest['gate']:g}米的配对差值为{comparison['delta_s']:+.4f}秒/源，"
                         f"95%区间[{lo:+.4f},{hi:+.4f}]。"+
                         ('区间跨零，不能确认这个样本最快门限比当前门限有平均效率优势。' if lo<=0<=hi else
                          '区间不跨零；仍需同时考虑失手成本与适用的场景分布。'))
    lines += [table(['题目','门限变化','总Δ秒/源','移动Δ','检测Δ','切频Δ','成功清除Δ','失败清除Δ','失手Δ'],
        [[f"Q{r['problem']}",f"{r['from_gate']:g}→{r['to_gate']:g}",f(r['delta_s']),
          *[f(r['delta_'+c]) for c in costs],r['delta_misses']] for r in gates]),
        '## 4. 光学网格到底有没有用？']
    for p in (3,4):
        gate={3:50,4:35}[p]; weak='nearest_sensing' if p==3 else 'no_negative'
        full=summaries[p,f'full__g{gate}']; single=summaries[p,f'no_grid__g{gate}']
        kept=summaries[p,f'{weak}__g{gate}']; removed=summaries[p,f'weak_no_grid__g{gate}']
        lines.append(f"Q{p}：完整策略调用网格{full['grid_attempts']}次；单独关闭网格全清{single['all_cleared']}/{single['runs']}。"
                     f"在“{kept['label']}”条件下，保留网格全清{kept['all_cleared']}/{kept['runs']}，"
                     f"再关闭网格仅{removed['all_cleared']}/{removed['runs']}。这证明网格在该退化条件下承担完成保障，"
                     '不等于完整策略在每个场景都需要网格。')
    recommendations=[]
    for p in (3,4):
        default={3:50,4:35}[p]
        for r in primary:
            if r['problem']!=p or r['gate']!=default: continue
            other=summaries[p,f"{r['component']}__g20"]
            supported=lambda x:x['delta_s'] is not None and x['ci95_s'][0]>0 and x.get('p_holm',1)<.05
            if supported(r) and supported(other):
                advice='建议保留原机制'
                if r['delta_percent']<1 and other['delta_percent']<1:
                    advice='保留为小幅优化，不作为主要效率贡献'
            else: advice='保留比较证据，当前不足以确认原机制稳定占优'
            recommendations.append([f'Q{p}',r['label'],advice])
    lines += ['## 5. 保留建议与数据边界',
        table(['题目','对照','数据支持的建议'],recommendations),
        '门限属于时间与试错次数的取舍。Q3的80米和Q4的40米虽为样本均值最低，但相对当前门限的配对区间都跨零，'
        '不以微小均值差直接替换默认值。20米在本批完整策略中没有失手，代价为小幅增加总耗时，继续保留为明确的折中候选。'
        '光学网格继续作为有限完成兜底，其条件完成性证据与日常效率贡献分开。生产策略未因本次结果改动。',
        '结果来自均衡分层的合成本地场景；旧45局压力集单列于stress，不声称代表官方分布。各消融是完整系统背景下的条件效应，不能相加。',
        '## 文件入口',
        '- [完整数据报告](REPORT.md)：设计、区间、逐局胜负和复现命令。',
        '- [核心及门限汇总](validation/summary.csv)、[门限成本对照](validation/gate_comparisons.csv)。',
        '- [逐局结果](validation/trials.csv)、[逐局配对](validation/paired.csv)、[分组统计](validation/subgroups.csv)。',
        '- [代表场景解释](case_explanations.csv)：各对照的中位差、最大收益/退化、首个失败及首次轨迹分歧。',
        '- [审计](audit.json)、[全部失败索引](failures.csv)、[预检记录](tests.log)。',
        '- [机制生效核验](mechanism_checks.csv)：实际负反馈裁剪、共享、删测和兜底次数。原始stats中的第四问bracket_pair_cuts在禁剪组仍计进入分支的次数，实际裁剪须扣除ablation_disabled_negative_calls；核验表已按此处理。',
        '- [核心效应图](figures/core_effects.png)、[门限取舍图](figures/gate_tradeoff.png)、[门限成本图](figures/gate_cost_breakdown.png)。',
        '入口说明和选例解释可用本归档的`postprocess/ablation_data_explain.py --output 本归档路径`重新生成。',
        '完全重新执行相同实验时，在新的空目录复制本归档的`config.json`、`seed_audit.json`、`frozen/`，'
        '再分别建立`pilot/`、`validation/`、`stress/`并只复制各自`fixtures.json`，随后按REPORT中的命令将ARCHIVE改为新目录依次执行。'
        '这属于固定输入复现，不是新增独立样本；不要重新--prepare沿用本轮种子，否则种子排重检查会正确拒绝。']
    (out/'READ_ME_FIRST.md').write_text('\n\n'.join(lines)+'\n')
    selected=json.loads((out/'selected_cases.json').read_text()); explanations=[]
    def normalize(e):
        return dict(path=e['path'],request={k:v for k,v in e['request'].items() if k!='request_id'},
                    response={k:v for k,v in e['response'].items() if k!='real_timestamp_ms'})
    for item in selected:
        changed=json.loads(gzip.decompress((out/item['trace_file']).read_bytes()))
        original=json.loads(gzip.decompress((out/item['reference_trace_file']).read_bytes()))
        ta,tb=changed['trace'],original['trace']; ra,rb=changed['row'],original['row']
        index=next((i for i,(a,b) in enumerate(zip(ta,tb)) if normalize(a)!=normalize(b)),min(len(ta),len(tb)))
        explanations.append(dict(**item,sources=ra['sources'],cleared=ra['cleared'],reference_cleared=rb['cleared'],
            first_divergent_action_index=index,
            changed_action=normalize(ta[index]) if index<len(ta) else None,
            reference_action=normalize(tb[index]) if index<len(tb) else None,
            **{'delta_'+c:ra['costs'][c]-rb['costs'][c] for c in costs},
            cost_interpretation='完整任务成本差' if ra['all_cleared'] and rb['all_cleared'] else '含提前停止，不作效率比较'))
    with (out/'case_explanations.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(explanations[0]));writer.writeheader()
        writer.writerows({k:json.dumps(v,ensure_ascii=False) if isinstance(v,dict) else v for k,v in r.items()} for r in explanations)
    dest=out/'postprocess';dest.mkdir(exist_ok=True)
    if Path(__file__).resolve()!=(dest/Path(__file__).name).resolve():
        shutil.copy2(__file__,dest/Path(__file__).name)
    report=out/'REPORT.md'
    text=report.read_text()
    text=text.replace('如需全新重复执行，在工作区用suite的--prepare创建新输出目录，再从新目录的冻结脚本运行。',
        '如需完全重新执行相同输入，请按READ_ME_FIRST.md复制冻结代码、配置和三个fixtures.json到新的空目录，再逐阶段执行；此类复现不增加独立样本量。')
    report.write_text(text)
    (dest/'manifest.json').write_text(json.dumps(dict(
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        inputs={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                (out/'validation/summary.json',out/'validation/gate_comparisons.json',out/'selected_cases.json',out/'audit.json')},
        role='Analysis-only explanation of frozen results; no changed strategies or scored runs.'),indent=2)+'\n')
    manifest={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest()
              for p in out.rglob('*') if p.is_file() and p.name!='artifact_sha256.json' and 'traces' not in p.parts}
    (out/'artifact_sha256.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Wrote READ_ME_FIRST.md and',len(explanations),'scene explanations')


if __name__=='__main__':main()
