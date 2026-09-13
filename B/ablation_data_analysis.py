"""Rebuild tables, paired inference, cost accounting, trace audit and replays."""
import os
for _key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[_key]='1'
import argparse
import csv
import gzip
import itertools
import json
from pathlib import Path
import numpy as np
import ablation_data_suite as s

COSTS = ['move_s','measure_s','switch_s','clear_success_s','clear_failure_s']
COST_LABELS = ['移动','检测','切频','成功清除','失败清除']


def csv_write(path, records):
    if not records: return
    keys = list(dict.fromkeys(k for r in records for k in r))
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=keys); writer.writeheader()
        writer.writerows({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v
                         for k,v in r.items()} for r in records)


def bootstrap_weights(rows, count=4000):
    """Resample scenes within fixed design cells; all paired runs share weights."""
    rng=np.random.default_rng(2160913)
    strata={}
    for i,r in enumerate(rows): strata.setdefault(r['stratum'],[]).append(i)
    weights=np.zeros((count,len(rows)),dtype=np.int16)
    for indices in strata.values():
        weights[:,indices]=rng.multinomial(len(indices),np.full(len(indices),1/len(indices)),size=count)
    return weights


def paired(group, base, weights):
    n=np.array([r['sources'] for r in group])
    d=np.array([r['total_virtual_s']-b['total_virtual_s'] for r,b in zip(group,base)])
    good=np.array([r['all_cleared'] and b['all_cleared'] for r,b in zip(group,base)])
    observed=float(d.sum()/n.sum())
    boot=weights@d/n.sum()
    ci=np.quantile(boot,[.025,.975]).tolist()
    p=float((1+np.sum(np.abs(boot-observed)>=abs(observed)-1e-12))/(len(boot)+1))
    result=dict(delta_s=observed if good.all() else None,
        ci95_s=ci if good.all() else None, p_bootstrap=p if good.all() else None,
        complete_pairs=int(good.sum()), faster=int(((d < -1e-6)&good).sum()),
        slower=int(((d > 1e-6)&good).sum()), same=int(((abs(d)<=1e-6)&good).sum()),
        noncomparable=int((~good).sum()),
        delta_percent=float(100*d.sum()/sum(r['total_virtual_s'] for r in base)) if good.all() else None,
        max_regression_s=float(max(0.,d[good].max())) if good.any() else None,
        max_regression_case=group[int(np.where(good,d,-np.inf).argmax())]['case_id'] if good.any() else None)
    for key in COSTS:
        result['delta_'+key]=sum(r['costs'][key]-b['costs'][key] for r,b in zip(group,base))/int(n.sum()) if good.all() else None
    if good.all():
        assert abs(sum(result['delta_'+k] for k in COSTS)-observed)<1e-4
    complete_diff=np.array([int(r['all_cleared'])-int(b['all_cleared']) for r,b in zip(group,base)])
    result['completion_delta_pp']=float(100*complete_diff.mean())
    result['completion_ci95_pp']=np.quantile(100*(weights@complete_diff)/len(group),[.025,.975]).tolist()
    return result


def reference(p, v):
    if v['component']=='weak_no_grid':
        return f"{'nearest_sensing' if p==3 else 'no_negative'}__g{s.DEFAULT_GATE[p]:g}"
    if v['family']=='gate': return f'full__g{s.DEFAULT_GATE[p]:g}'
    return f"full__g{v['gate']:g}"


def describe(group):
    n=sum(r['sources'] for r in group); complete=all(r['all_cleared'] for r in group)
    per=np.array([r['total_virtual_s']/r['sources'] for r in group if r['all_cleared']])
    result=dict(runs=len(group),sources=n,all_cleared=sum(r['all_cleared'] for r in group),
                clear_rate=100*sum(r['all_cleared'] for r in group)/len(group),
                seconds_per_source=sum(r['total_virtual_s'] for r in group)/n if complete else None,
                stopped_seconds_per_true_source=sum(r['total_virtual_s'] for r in group)/n,
                missing_sources=sum(r['sources']-r['cleared'] for r in group),
                unexpected_errors=sum(bool(r['failure']) and not r['unavailable'] for r in group),
                median_s=float(np.median(per)) if complete else None,
                p90_s=float(np.quantile(per,.9)) if complete else None,
                p95_s=float(np.quantile(per,.95)) if complete else None)
    for key in ['distance_m','measurements','switches','misses','successes',
                *[f'{k}_{field}' for k in ('early','certified','fallback_center','grid') for field in ('attempts','successes')]]:
        result[key]=sum(r[key] for r in group)
    result['early_success_rate']=result['early_successes']/result['early_attempts'] if result['early_attempts'] else None
    for key in COSTS: result[key+'_per_source']=sum(r['costs'][key] for r in group)/n
    result['trigger_cases']={key:sum(r['stats'].get(key,0)>0 for r in group) for key in
        ('shared_known_measurements','omni_negative_cuts','bracket_pair_cuts',
         'certified_range_scan_skips','optical_fallback_calls','ablation_scoring_calls')}
    return result


def summarize_phase(out, phase):
    rows=s.load_rows(out/phase/'trials.jsonl')
    groups={}
    for r in rows: groups.setdefault((r['problem'],r['variant']),[]).append(r)
    for group in groups.values(): group.sort(key=lambda r:r['case_id'])
    summaries=[]; pairs=[]; strata=[]; gates=[]; selected=[]
    for p in (3,4):
        full=groups[p,f'full__g{s.DEFAULT_GATE[p]:g}']
        weights=bootstrap_weights(full)
        for v in s.variants(p):
            group=groups[p,v['id']]; ref=reference(p,v); base=groups[p,ref]
            assert [(r['case_id'],r['fixture_sha256']) for r in group]==[(r['case_id'],r['fixture_sha256']) for r in base]
            item=dict(problem=p,variant=v['id'],label=s.LABELS[v['component']],family=v['family'],
                      component=v['component'],gate=v['gate'],reference=ref,
                      **describe(group),**paired(group,base,weights))
            summaries.append(item)
            for r,b in zip(group,base):
                good=r['all_cleared'] and b['all_cleared']
                pairs.append(dict(problem=p,variant=v['id'],reference=ref,case_id=r['case_id'],
                    sources=r['sources'],paired_complete=good,total_s=r['total_virtual_s'],
                    reference_total_s=b['total_virtual_s'],delta_s=r['total_virtual_s']-b['total_virtual_s'] if good else None,
                    **{'delta_'+k:r['costs'][k]-b['costs'][k] if good else None for k in COSTS}))
            for factor in ('layout','error','n','radius','direction'):
                for value in sorted({str(r['factors'][factor]) for r in group}):
                    indices=[i for i,r in enumerate(group) if str(r['factors'][factor])==value]
                    part=[group[i] for i in indices]; bpart=[base[i] for i in indices]
                    strata.append(dict(problem=p,variant=v['id'],reference=ref,factor=factor,value=value,
                        **describe(part),**paired(part,bpart,weights[:,indices])))
            if phase=='validation' and v['id']!=ref:
                comparable=[(r,b) for r,b in zip(group,base) if r['all_cleared'] and b['all_cleared']]
                if comparable:
                    diffs=np.array([r['total_virtual_s']-b['total_virtual_s'] for r,b in comparable])
                    for role,index in [('median',int(np.abs(diffs-np.median(diffs)).argmin())),
                                       ('largest_gain',int(diffs.argmin())),('largest_regression',int(diffs.argmax()))]:
                        r,b=comparable[index]
                        selected.append(dict(problem=p,variant=v['id'],reference=ref,case_id=r['case_id'],
                            role=role,delta_s=float(diffs[index]),trace_file=r['trace_file'],reference_trace_file=b['trace_file']))
                failed=[r for r in group if not r['all_cleared']]
                if failed:
                    r=failed[0]; b=next(x for x in base if x['case_id']==r['case_id'])
                    selected.append(dict(problem=p,variant=v['id'],reference=ref,case_id=r['case_id'],
                        role='first_failure',delta_s=None,trace_file=r['trace_file'],reference_trace_file=b['trace_file']))
        gate_values=sorted(v['gate'] for v in s.variants(p) if v['component']=='full')
        for a,b in itertools.combinations(gate_values,2):
            ga=groups[p,f'full__g{a:g}']; gb=groups[p,f'full__g{b:g}']
            gates.append(dict(problem=p,from_gate=a,to_gate=b,
                **paired(gb,ga,weights),delta_misses=sum(r['misses']-x['misses'] for r,x in zip(gb,ga)),
                delta_measurements=sum(r['measurements']-x['measurements'] for r,x in zip(gb,ga)),
                delta_switches=sum(r['switches']-x['switches'] for r,x in zip(gb,ga)),
                delta_distance_m=sum(r['distance_m']-x['distance_m'] for r,x in zip(gb,ga))))
    family=[r for r in summaries if r['family']=='core' and r['component']!='full' and r['p_bootstrap'] is not None]
    running=0.
    for rank,r in enumerate(sorted(family,key=lambda r:r['p_bootstrap'])):
        running=max(running,min(1.,(len(family)-rank)*r['p_bootstrap']))
        r['p_holm']=running
    for r in summaries:
        if r['component']=='full' and r['reference']==r['variant']: verdict='参照'
        elif r['delta_s'] is None: verdict='含未完成任务，效率不可直接比较'
        elif r['ci95_s'][0]<=0<=r['ci95_s'][1] or (r.get('p_holm') is not None and r['p_holm']>=.05): verdict='平均差异证据不足'
        elif r['delta_s']<0: verdict='替代方案平均更快'
        elif r['delta_percent']<1: verdict='小幅平均收益（不足1%）'
        else: verdict='平均效率收益（至少1%）'
        r['verdict']=verdict
    dest=out/phase
    for name,data in [('summary',summaries),('paired',pairs),('subgroups',strata),('gate_comparisons',gates)]:
        csv_write(dest/(name+'.csv'),data)
        if name!='paired': s.write_json(dest/(name+'.json'),data)
    flat=[]
    for r in rows:
        flat.append({k:v for k,v in r.items() if k not in ('stats','costs')}|r['costs'])
    csv_write(dest/'trials.csv',flat)
    if phase=='validation': s.write_json(out/'selected_cases.json',selected)
    return summaries,gates


def audit(out):
    config=json.loads((out/'config.json').read_text()); s.verify_frozen(out,config)
    audit_rows=[]; failures=[]; total=0
    for phase in ('pilot','validation','stress'):
        rows=s.load_rows(out/phase/'trials.jsonl'); fs=json.loads((out/phase/'fixtures.json').read_text())
        expected={(p,f['case_id'],v['id']):s.digest(s.canonical(f))
                  for p in (3,4) for f in fs[str(p)] for v in s.variants(p)}
        found={}; max_error=0.; prefix_checks=0
        for i,r in enumerate(rows):
            key=(r['problem'],r['case_id'],r['variant'])
            assert key not in found and expected[key]==r['fixture_sha256']
            found[key]=r
            assert r['experiment_id']==config['experiment_id']
            raw=(out/r['trace_file']).read_bytes()
            assert s.digest(raw)==r['file_sha256']
            payload=json.loads(gzip.decompress(raw)); trace=payload['trace']
            assert s.digest(s.canonical(s.normalized_trace(trace)))==r['trace_sha256']
            stored=payload['row']
            assert all(stored[k]==v for k,v in r.items() if k not in ('trace_file','file_sha256'))
            position=(0.,0.); channel=1; distance=0.; m=sw=cs=cf=0
            for e in trace:
                if not e['response']['accepted']: continue
                if e['path'] in ('/measure','/clear'):
                    pos=e['request']['position']; q=(pos['x'],pos['y'])
                    distance+=s.math.dist(position,q); position=q
                    if e['path']=='/measure':
                        m+=1; sw+=int(e['request']['channel']!=channel); channel=e['request']['channel']
                    else:
                        ok=e['response']['clear_result']=='success'; cs+=ok; cf+=not ok
            assert (m,sw,cs,cf)==(r['measurements'],r['switches'],r['successes'],r['misses'])
            assert cs==r['cleared'] and distance==r['distance_m']
            error=distance/5+5*m+sw+5*cs+3*cf-r['total_virtual_s']
            max_error=max(max_error,abs(error)); assert abs(error)<=max(1,len(trace))*.5001e-6
            assert not r['failure'] or r['unavailable'],(phase,key,r['failure'])
            assert r['certified_attempts']==r['certified_successes']
            if not r['all_cleared']:
                failures.append(dict(phase=phase,problem=r['problem'],variant=r['variant'],case_id=r['case_id'],
                                     cleared=r['cleared'],sources=r['sources'],reason=r['failure'],trace_file=r['trace_file']))
                if r['component']=='weak_no_grid':
                    weak='nearest_sensing' if r['problem']==3 else 'no_negative'
                    ref=out/phase/'traces'/r['case_id']/f"{weak}__g{r['gate']:g}.json.gz"
                    kept=json.loads(gzip.decompress(ref.read_bytes()))
                    assert kept['row']['all_cleared']
                    assert trace[-1]['path']=='/exit'
                    assert s.normalized_trace(trace[:-1])==s.normalized_trace(kept['trace'][:len(trace)-1])
                    prefix_checks+=1
            if (i+1)%2000==0: print(f'audit {phase}: {i+1}/{len(rows)}',flush=True)
        assert set(expected)==set(found)
        total+=len(rows)
        audit_rows.append(dict(phase=phase,runs=len(rows),expected=len(expected),
            failed=sum(not r['all_cleared'] for r in rows),max_ledger_error_s=max_error,
            conditional_failure_prefix_checks=prefix_checks,all_trace_hashes_and_ledgers_verified=True))
    assert total==73005
    replay=[]
    fs=json.loads((out/'validation/fixtures.json').read_text())
    lookup={(int(p),f['case_id']):f for p,group in fs.items() for f in group}
    seen=set()
    for item in json.loads((out/'selected_cases.json').read_text()):
        for field in ('variant','reference'):
            key=(item['problem'],item['case_id'],item[field])
            if key in seen: continue
            seen.add(key); p,cid,vid=key
            variant=next(v for v in s.variants(p) if v['id']==vid)
            row,_=s.execute(p,variant,lookup[p,cid])
            old=json.loads(gzip.decompress((out/'validation/traces'/cid/(vid+'.json.gz')).read_bytes()))['row']
            assert row['trace_sha256']==old['trace_sha256'] and row['total_virtual_s']==old['total_virtual_s']
            replay.append(dict(problem=p,case_id=cid,variant=vid,identical=True))
    source_changes=[path for path,sha in config['source_sha256'].items()
                    if not Path(path).exists() or s.digest(Path(path).read_bytes())!=sha]
    # Shared workspace may change independently; execution authority is the verified frozen snapshot.
    s.write_json(out/'audit.json',dict(executions=total,phases=audit_rows,
        frozen_integrity=True,unexpected_errors=0,certified_failures=0,
        failed_runs=len(failures),replayed_runs=len(replay),replays=replay,
        live_files_changed_since_freeze=source_changes,official_calls=0))
    csv_write(out/'failures.csv',failures)
    print(f'AUDIT PASS: {total} executions; {len(replay)} identical replays',flush=True)


def fmt(x):
    return '不可比' if x is None else f'{x:.3f}'


def table(headers, rows):
    return '\n'.join(['|'+'|'.join(headers)+'|','|'+'|'.join(['---']*len(headers))+'|']+
                     ['|'+'|'.join(map(str,r))+'|' for r in rows])


def report(out, summaries, gates):
    config=json.loads((out/'config.json').read_text())
    lines=['# Q3/Q4 消融实验数据报告',
        '本轮比较冻结的当前策略与明确的组件替代方案。每题正式验证2100个新场景；预检210局和既有压力45局分别保存。共73,005次执行，同一场景跨策略配对；只使用本地合成模拟器。',
        '当前门限：Q3为50米、Q4为35米；核心对照另在20米重复。Q3选点余程权重为1.5。20米是提前试清门限，仍保留非认证光学兜底，不等于所有清除都有成功保证。',
        '所有设置与场景在运行前冻结，不依据结果筛选变体、删除失败或重新调参。正差值表示替代方案更慢；负差值表示替代方案更快。各项差值不可相加。',
        '## 核心机制：当前门限与20米分别比较']
    for p in (3,4):
        for gate in (s.DEFAULT_GATE[p],20.):
            group=[r for r in summaries if r['problem']==p and r['family']=='core' and r['gate']==gate]
            lines += [f'### Q{p}，门限{gate:g}米',table(
                ['设置','秒/源','较同门限完整策略Δ秒/源','Δ%','95%区间','全清','快/平/慢','判断'],
                [[r['label'],fmt(r['seconds_per_source']),fmt(r['delta_s']),fmt(r['delta_percent']),
                  '不可比' if r['ci95_s'] is None else f"[{r['ci95_s'][0]:.3f},{r['ci95_s'][1]:.3f}]",
                  f"{r['all_cleared']}/{r['runs']}",f"{r['faster']}/{r['same']}/{r['slower']}",r['verdict']] for r in group])]
    lines += ['## 门限：时间与失手同时呈现',table(
        ['问题','门限','秒/源','P95单局秒/源','失手','提前试清成功/尝试','兜底中心/格心尝试'],
        [[f"Q{r['problem']}",r['gate'],fmt(r['seconds_per_source']),fmt(r['p95_s']),r['misses'],
          f"{r['early_successes']}/{r['early_attempts']}",f"{r['fallback_center_attempts']}/{r['grid_attempts']}"]
         for r in summaries if r['component']=='full']),
        '### 较宽门限为何快或慢：逐项成本差（秒/源）',
        '下表为“改用后门限−前门限”。每行五项成本差相加得到总时间差，微小舍入误差除外。',table(
        ['问题','门限变化','总Δ','移动Δ','检测Δ','切频Δ','成功清除Δ','失败清除Δ','失手总数Δ'],
        [[f"Q{r['problem']}",f"{r['from_gate']:g}→{r['to_gate']:g}",fmt(r['delta_s']),
          *[fmt(r['delta_'+k]) for k in COSTS],r['delta_misses']] for r in gates]),
        '## 补充对照与完成性',table(
        ['问题','设置','参照','全清','秒/源','Δ秒/源','判断'],
        [[f"Q{r['problem']}",r['label'],r['reference'],f"{r['all_cleared']}/{r['runs']}",
          fmt(r['seconds_per_source']),fmt(r['delta_s']),r['verdict']] for r in summaries if r['family']=='supplement']),
        '弱定位禁网格分别对照“最近邻测向但保留网格”和“关闭负反馈裁剪但保留网格”，不能把提前失败的停止耗时当成效率。单独禁网格无变化只说明这一批完整策略未需要它。',
        '## 统计口径与结论边界',
        '总秒/源=各局总时间之和/真实源数之和；P90/P95是完整单局秒/源分布的分位数，不是均值区间。未全清设置的效率及尾部分位数留空，停止前耗时只存于原始/辅助字段。',
        '95%区间采用4000次分层配对场景bootstrap，同一场景各设置共同重采样；每次保留各因素格的样本数。核心18项比较的居中bootstrap近似双侧p值作Holm校正；门限及分组结果作解释性分析。低于1%的正收益在报告中标为小收益，1%只是预定展示分界，不是工程价值或统计显著性的充分条件。',
        '第三问：7种源数×3种分布×5种误差×2种半径×10个独立种子。第四问再交叉2种朝向，每格5个独立种子。分层平均代表本试验设定的均衡混合，不代表官方未知场景分布。',
        '对照边界：关闭补测仍保留扫描已知频道；关闭负反馈仍保留成功测向和距离删测，第四问仍测完整双负对；最近邻路线只替代在线排序；分阶段仍保留近距即时清除和公开16源上限免扫。20米复核以自身完整策略为参照。',
        '## 数据入口与复现',
        '- `validation/summary.csv`：主表、完成性、配对区间、Holm校正和机制触发局数。',
        '- `validation/trials.csv`、`paired.csv`：逐局全量结果与成本差。',
        '- `validation/subgroups.csv`：按分布、误差、源数、半径、朝向分组的相同口径结果。',
        '- `validation/gate_comparisons.csv`：门限两两配对及完整成本分解。',
        '- `pilot/`、`stress/`：预检和既有压力结果，独立统计。',
        '- `selected_cases.json`：中位差、最大收益、最大退化与首个失败的确定性选例。',
        '- `*/traces/`：每局压缩原始动作、任务选择、清除分类及数据行。',
        '- `audit.json`、`failures.csv`：全部轨迹/账本核查、失败前缀核查与代表场景重放。',
        '- `config.json`、`seed_audit.json`、`frozen/`：冻结参数、输入、种子排重及可执行快照。',
        '```sh',f'PYTHON="{config["python"]}"',f'ARCHIVE="{out}"',
        '"$PYTHON" -B "$ARCHIVE/frozen/B/ablation_data_suite.py" --output "$ARCHIVE" --phase pilot --workers 4',
        '"$PYTHON" -B "$ARCHIVE/frozen/B/ablation_data_suite.py" --output "$ARCHIVE" --phase validation --workers 4',
        '"$PYTHON" -B "$ARCHIVE/frozen/B/ablation_data_suite.py" --output "$ARCHIVE" --phase stress --workers 4',
        '"$PYTHON" -B "$ARCHIVE/frozen/B/ablation_data_analysis.py" --output "$ARCHIVE" --audit','```',
        '同一归档支持按完整数据行和轨迹哈希续跑；如需全新重复执行，在工作区用suite的--prepare创建新输出目录，再从新目录的冻结脚本运行。正式设置发生实现变化时建立新归档，不能混版。']
    (out/'REPORT.md').write_text('\n\n'.join(lines)+'\n')


def plots(out,summaries,gates):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    dest=out/'figures'; dest.mkdir(exist_ok=True)
    labels=dict(no_share='No shared observations',scan_then_service='Scan, then service',
                no_negative='No negative cuts',online_nearest='Nearest task',nearest_sensing='Nearest sensing')
    fig,axes=plt.subplots(1,2,figsize=(12,4.8))
    for ax,p in zip(axes,(3,4)):
        components=s.CORE[1:]+(['nearest_sensing'] if p==3 else [])
        for j,g in enumerate((s.DEFAULT_GATE[p],20.)):
            for i,c in enumerate(components):
                r=next(x for x in summaries if x['problem']==p and x['component']==c and x['gate']==g)
                if r['delta_s'] is None: continue
                d=r['delta_s']; lo,hi=r['ci95_s']
                ax.errorbar(d,i+(j-.5)*.22,xerr=[[max(0,d-lo)],[max(0,hi-d)]],fmt='o',capsize=3,
                            color=['#235789','#c96527'][j],label=f'Gate {g:g} m' if i==0 else None)
        ax.set_yticks(range(len(components)),[labels[c] for c in components]); ax.invert_yaxis()
        ax.axvline(0,color='gray',lw=1); ax.set_xlabel('Extra seconds/source vs full at same gate')
        ax.set_title(f'Q{p}: paired 95% intervals'); ax.legend()
    fig.tight_layout(); fig.savefig(dest/'core_effects.png',dpi=180); plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(10,4))
    for ax,p in zip(axes,(3,4)):
        group=[r for r in summaries if r['problem']==p and r['component']=='full']
        group.sort(key=lambda r:r['gate'])
        ax.plot([r['seconds_per_source'] for r in group],[r['misses']/r['sources'] for r in group],'o-',color='#235789')
        for r in group:
            ax.annotate(f"{r['gate']:g} m",(r['seconds_per_source'],r['misses']/r['sources']),xytext=(5,6),textcoords='offset points')
        ax.set_xlabel('Total seconds/source'); ax.set_ylabel('Failed clears/source'); ax.set_title(f'Q{p}: gate trade-off')
    fig.tight_layout(); fig.savefig(dest/'gate_tradeoff.png',dpi=180); plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,5))
    selected=[g for g in gates if g['from_gate']==s.DEFAULT_GATE[g['problem']]]
    x=np.arange(len(selected)); pos=np.zeros(len(selected)); neg=np.zeros(len(selected))
    for k,label in zip(COSTS,['Movement','RF measurements','Channel switches','Successful clears','Failed clears']):
        values=np.array([g['delta_'+k] for g in selected]); bottom=np.where(values>=0,pos,neg)
        ax.bar(x,values,bottom=bottom,label=label)
        pos+=np.maximum(values,0); neg+=np.minimum(values,0)
    ax.set_xticks(x,[f"Q{r['problem']}: {r['from_gate']:g} to {r['to_gate']:g} m" for r in selected])
    ax.axhline(0,color='black',lw=.8); ax.set_ylabel('Cost difference (seconds/source)'); ax.legend()
    fig.tight_layout(); fig.savefig(dest/'gate_cost_breakdown.png',dpi=180); plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True); parser.add_argument('--audit',action='store_true')
    args=parser.parse_args(); out=args.output.resolve()
    config=json.loads((out/'config.json').read_text()); s.verify_frozen(out,config)
    for phase in ('pilot','validation','stress'):
        print('Summarize:',phase,flush=True)
        summaries,gates=summarize_phase(out,phase)
        if phase=='validation': validation=(summaries,gates)
    report(out,*validation); plots(out,*validation)
    if args.audit: audit(out)
    s.write_json(out/'artifact_sha256.json',{str(p.relative_to(out)):s.digest(p.read_bytes())
        for p in out.rglob('*') if p.is_file() and p.name!='artifact_sha256.json' and 'traces' not in p.parts})
    print('Data report and analysis complete:',out,flush=True)


if __name__=='__main__': main()
