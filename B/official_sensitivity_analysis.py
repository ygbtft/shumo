"""Audit official evidence and report prespecified sensitivity/robustness results."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import re

import numpy as np
from scipy.stats import beta, t as student_t
import official_sensitivity_config as cfg


def dump(path,value):
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    tmp.replace(path)


def csvout(path,rows):
    if not rows:
        return
    with path.open('w',newline='',encoding='utf-8-sig') as f:
        keys=list(dict.fromkeys(k for row in rows for k in row))
        writer=csv.DictWriter(f,keys)
        writer.writeheader()
        writer.writerows(rows)


def audit_trial(run):
    score=run['authoritative']
    evidence=Path(run['evidence'])
    paths=list(evidence.glob('*/robot-run/requests.jsonl'))
    assert len(paths)==1,(run['order'],paths)
    trace=[json.loads(line) for line in paths[0].read_text().splitlines()]
    position=(0.,0.)
    channel=1
    distance=virtual=maximum_error=0.
    counts=Counter()
    seen={}
    accepted=[]
    for event in trace:
        if event.get('event')=='transport_failure':
            counts['retries']+=1
            continue
        q,r,path=event['request'],event['response'],event['path']
        assert event['http_status']==200 and r.get('accepted') is True,(run['order'],event)
        request_id=q['request_id']
        if request_id in seen:
            assert seen[request_id]==(path,q,r),'Conflicting request replay'
            counts['duplicate_responses']+=1
            continue
        seen[request_id]=(path,q,r)
        accepted.append(path)
        cost=0.
        if path in ('/measure','/clear'):
            point=(q['position']['x'],q['position']['y'])
            movement=math.dist(position,point)
            distance+=movement
            cost+=movement/5
            position=point
        if path=='/measure':
            counts['measurements']+=1
            switched=int(q['channel']!=channel)
            counts['switches']+=switched
            channel=q['channel']
            cost+=5+switched
        if path=='/clear':
            success=r['clear_result']=='success'
            counts['cleared']+=int(success)
            counts['misses']+=int(not success)
            cost+=5 if success else 3
        maximum_error=max(maximum_error,abs(r['virtual_time_s']-virtual-cost))
        virtual=r['virtual_time_s']
    assert accepted[0]=='/enter' and accepted[-1]=='/exit'
    assert maximum_error<2e-6,(run['order'],maximum_error)
    assert abs(virtual-score['virtual_time_us']/1e6)<2e-6
    assert counts['cleared']==score['cleared_jammer_count'] and counts['misses']==score['clear_failure_count']
    screenshots=list(evidence.glob('*-run/*completed.uia.json'))
    assert len(screenshots)==1
    texts=[r['text'] for r in json.loads(screenshots[0].read_text(encoding='utf-8-sig'))]
    matches=[re.search(r'本次案例含干扰源(\d+)个，其中全向(\d+)个、定向(\d+)个',s) for s in texts]
    matches=[m for m in matches if m]
    assert len(matches)==1
    n,omni,directional=map(int,matches[0].groups())
    assert n==omni+directional==score['jammer_count'] and score['case_code'] in texts
    robot=run['robot']
    assert robot['parameters']==run['parameters'] and robot['mock_executions']==0
    assert robot['mode']=='practice' and robot['assignment']['order']==run['order']
    row={key:run[key] for key in ('phase','problem','setting','block','order')}
    row.update(case_code=score['case_code'],official_row_id=score['id'],practice_run_no=str(score['practice_run_no']),
        parameters=json.dumps(run['parameters'],sort_keys=True),sources=n,omni_sources=omni,directional_sources=directional,
        completed=int(n==counts['cleared'] and robot['status']=='policy-completed'),
        cleared=counts['cleared'],misses=counts['misses'],virtual_time_us=score['virtual_time_us'],
        total_s=score['virtual_time_us']/1e6,seconds_per_source=score['virtual_time_us']/1e6/n,
        distance_m=distance,movement_s=distance/5,measurements=counts['measurements'],
        switches=counts['switches'],measurement_s=5*counts['measurements'],switch_s=counts['switches'],
        failed_clear_s=3*counts['misses'],successful_clear_s=5*counts['cleared'],
        retries=counts['retries'],duplicate_responses=counts['duplicate_responses'],
        max_action_ledger_error_s=maximum_error,wall_s=run['wall_s'],
        round_counters_recorded=run['problem']==4,
        sources_at_round_budget=robot['sources_at_round_budget'] if run['problem']==4 else None,
        maximum_rounds=max(robot['source_rounds'].values(),default=0) if run['problem']==4 else None,
        end_reason=score['end_reason'],evidence=run['evidence'])
    stats=robot['policy']
    for key in ('shared_known_measurements','shared_negative_cooldown_skips','source_interruptions',
                'optical_fallback_calls','bracket_pair_cuts','active_measurements','certified_clears',
                'omni_negative_cuts','packet_fallbacks','forced_continuations'):
        row[key]=stats.get(key)
    return row


def ratio(rows):
    return sum(r['total_s'] for r in rows)/sum(r['sources'] for r in rows)


def summarize(rows):
    out=[]
    for phase,p,setting in sorted(set((r['phase'],r['problem'],r['setting']) for r in rows)):
        group=[r for r in rows if (r['phase'],r['problem'],r['setting'])==(phase,p,setting)]
        n=sum(r['sources'] for r in group)
        s=dict(phase=phase,problem=p,setting=setting,runs=len(group),all_cleared=sum(r['completed'] for r in group),
            sources=n,tau=ratio(group),misses=sum(r['misses'] for r in group),
            directional_fraction=sum(r['directional_sources'] for r in group)/n,
            max_observed_case_seconds=max(r['total_s'] for r in group))
        for key in ('movement_s','measurement_s','switch_s','failed_clear_s','successful_clear_s','measurements','switches','misses'):
            s[key+'_per_source']=sum(r[key] for r in group)/n
        out.append(s)
    return out


def holm(rows):
    largest=0.
    for i,row in enumerate(sorted(rows,key=lambda r:r['p_randomization'])):
        largest=max(largest,min(1.,(len(rows)-i)*row['p_randomization']))
        row['p_holm_48']=largest


def block_bootstrap(a,b,repeats,seed):
    """Rows are time-block totals (seconds, sources), never matched scenes."""
    a,b=np.asarray(a,float),np.asarray(b,float)
    assert a.shape==b.shape and a.ndim==2 and a.shape[1]==2
    rng=np.random.default_rng(seed)
    delta=[]
    relative=[]
    for begin in range(0,repeats,5000):
        ids=rng.integers(len(a),size=(min(5000,repeats-begin),len(a)))
        aa,bb=a[ids].sum(1),b[ids].sum(1)
        x,y=aa[:,0]/aa[:,1],bb[:,0]/bb[:,1]
        delta.extend((x-y).tolist())
        relative.extend((x/y).tolist())
    return np.asarray(delta),np.asarray(relative)


def screen_comparisons(rows,settings):
    comparisons=[]
    for spec in settings:
        p,setting=spec['problem'],spec['setting']
        if setting=='baseline':
            continue
        group=sorted([r for r in rows if r['phase']=='screen' and r['problem']==p and r['setting']==setting],key=lambda r:r['block'])
        base=sorted([r for r in rows if r['phase']=='screen' and r['problem']==p and r['setting']=='baseline'],key=lambda r:r['block'])
        if len(group)!=10 or len(base)!=10:
            continue
        assert [r['block'] for r in group]==[r['block'] for r in base]==list(range(1,11))
        a=np.array([[r['total_s'],r['sources']] for r in group])
        b=np.array([[r['total_s'],r['sources']] for r in base])
        observed=ratio(group)-ratio(base)
        delta,relative=block_bootstrap(a,b,10000,216091304)
        masks=np.array(list(itertools.product((0,1),repeat=10)),dtype=bool)[:,:,None]
        left=np.where(masks,a,b).sum(1)
        right=np.where(masks,b,a).sum(1)
        null=left[:,0]/left[:,1]-right[:,0]/right[:,1]
        ci=np.quantile(delta,[.025,.975])
        key,value=next(iter(spec['changes'].items()))
        comparisons.append(dict(problem=p,setting=setting,parameter=key,value=value,
            delta_s_per_source=observed,relative_pct=100*(ratio(group)/ratio(base)-1),
            ci_low=float(ci[0]),ci_high=float(ci[1]),
            p_randomization=float((np.abs(null)>=abs(observed)-1e-10).mean()),
            all_clear=all(r['completed'] for r in group+base)))
    if len(comparisons)==48:
        holm(comparisons)
    return comparisons


def robust_comparisons(rows):
    result=[]
    for p in (3,4):
        group=[r for r in rows if r['phase']=='robustness' and r['problem']==p and r['setting']=='perturbed']
        base=[r for r in rows if r['phase']=='robustness' and r['problem']==p and r['setting']=='baseline']
        if not group or not base:
            continue
        complete=len(group)==80 and len(base)==40
        blocks=sorted(set(r['block'] for r in group+base))
        valid=[]
        for block in blocks:
            a=[r for r in group if r['block']==block]
            b=[r for r in base if r['block']==block]
            if len(a)==2 and len(b)==1:
                valid.append(([sum(r['total_s'] for r in a),sum(r['sources'] for r in a)],
                              [sum(r['total_s'] for r in b),sum(r['sources'] for r in b)]))
        success=sum(r['completed'] for r in group)
        lower=float(beta.ppf(.025,success,len(group)-success+1)) if success else 0.
        item=dict(problem=p,perturbed_runs=len(group),baseline_runs=len(base),
            perturbed_all_clear=success,baseline_all_clear=sum(r['completed'] for r in base),
            perturbed_tau=ratio(group),baseline_tau=ratio(base),ratio=ratio(group)/ratio(base),
            clear_probability_lower97_5=lower,complete=complete,full_blocks=len(valid),
            ratio_upper97_5=None,ratio_ci95=None,noninferiority_pass=False,
            observed_all_clear=all(r['completed'] for r in group+base),overall_pass=False,
            verdict='incomplete; no confirmatory conclusion')
        if complete:
            assert len(valid)==40
            _,relative=block_bootstrap([a for a,b in valid],[b for a,b in valid],100000,216091305+p)
            upper=float(np.quantile(relative,.975))
            item.update(ratio_upper97_5=upper,ratio_ci95=np.quantile(relative,[.025,.975]).tolist(),
                noninferiority_pass=upper<1.05,
                overall_pass=upper<1.05 and item['observed_all_clear'])
            item['verdict']='prespecified robustness criteria passed' if item['overall_pass'] else (
                'completion criterion failed' if not item['observed_all_clear'] else
                'insufficient evidence for <=5% degradation' if item['ratio']<1.05 else
                'observed degradation >=5%; robustness criterion not met')
        result.append(item)
    return result


def adjusted_robustness(rows):
    """Secondary only: account for public source composition and time blocks."""
    result=[]
    for p in (3,4):
        sub=[r for r in rows if r['phase']=='robustness' and r['problem']==p]
        if len(sub)!=120:
            continue
        nbar=float(np.mean([r['sources'] for r in sub]))
        dbar=float(np.mean([r['directional_sources'] for r in sub]))
        x=np.array([[1.,int(r['setting']=='perturbed'),r['sources']-nbar]
                    +([r['directional_sources']-dbar] if p==4 else [])
                    +[int(r['block']==b) for b in range(2,41)] for r in sub])
        y=np.array([r['total_s'] for r in sub])
        rank=int(np.linalg.matrix_rank(x))
        if rank!=x.shape[1]:
            result.append(dict(problem=p,status='rank deficient; no adjusted estimate'))
            continue
        inverse=np.linalg.inv(x.T@x)
        coef=inverse@x.T@y
        leverage=np.sum((x@inverse)*x,axis=1)
        residual=(y-x@coef)/(1-leverage)
        cov=inverse@((x*residual[:,None]).T@(x*residual[:,None]))@inverse
        se=math.sqrt(max(0,cov[1,1]))/nbar
        effect=float(coef[1]/nbar)
        cut=float(student_t.ppf(.975,len(y)-rank))
        result.append(dict(problem=p,status='secondary only',delta_s_per_source=effect,
            ci_low=effect-cut*se,ci_high=effect+cut*se,reference_sources=nbar,
            model='total_s ~ perturbed + source_count + time_block'+(' + directional_count' if p==4 else ''),
            standard_errors='HC3; model-dependent; does not remove unobserved geometry'))
    return result


def figures(out,rows,summary,comparisons,robust):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    dest=out/'figures'
    dest.mkdir(exist_ok=True)
    plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False})
    by_setting={(s['problem'],s['setting']):s for s in summary if s['phase']=='screen'}
    cm={(s['problem'],s['setting']):s for s in comparisons}
    for p in (3,4):
        fig,axes=plt.subplots(3,3,figsize=(13,10))
        for ax,(key,values) in zip(axes.flat,cfg.GRID[p].items()):
            xx=[];yy=[]
            for j,value in enumerate(values):
                setting='baseline' if value==cfg.DEFAULT[p][key] else f'{key}={value:g}'
                data=[r for r in rows if r['phase']=='screen' and r['problem']==p and r['setting']==setting]
                if not data:
                    continue
                ax.scatter([j]*len(data),[r['seconds_per_source'] for r in data],s=9,alpha=.35,color='#64748b')
                xx.append(j);yy.append(ratio(data))
                ax.annotate(f"{sum(r['completed'] for r in data)}/{len(data)}",(j,max(r['seconds_per_source'] for r in data)),
                            xytext=(0,4),textcoords='offset points',ha='center',fontsize=7)
            ax.plot(xx,yy,'o-',color='#0369a1',markersize=4,label='Pooled time/source')
            ax.axvline(values.index(cfg.DEFAULT[p][key]),color='#be123c',ls='--',alpha=.7)
            ax.set_xticks(range(len(values)),[f'{v:g}' for v in values])
            ax.set_xlabel(cfg.LABELS[key]);ax.set_ylabel('Seconds / source')
        for ax in list(axes.flat)[len(cfg.GRID[p]):]:
            ax.axis('off')
        fig.suptitle(f'Q{p}: official independent cases; labels = complete/runs; dashed = default')
        fig.tight_layout();fig.savefig(dest/f'q{p}_sensitivity.png',dpi=180);fig.savefig(dest/f'q{p}_sensitivity.pdf');plt.close(fig)
        fig,axes=plt.subplots(3,3,figsize=(13,10))
        for ax,(key,values) in zip(axes.flat,cfg.GRID[p].items()):
            x=[];y=[];lo=[];hi=[]
            for j,value in enumerate(values):
                setting='baseline' if value==cfg.DEFAULT[p][key] else f'{key}={value:g}'
                if setting=='baseline':
                    x.append(j);y.append(0);lo.append(0);hi.append(0)
                elif (p,setting) in cm:
                    r=cm[p,setting]
                    x.append(j);y.append(r['delta_s_per_source']);lo.append(r['ci_low']);hi.append(r['ci_high'])
            ax.vlines(x,lo,hi,color='#0369a1');ax.scatter(x,y,color='#0369a1',s=20)
            ax.axhline(0,color='#64748b',lw=.8);ax.axvline(values.index(cfg.DEFAULT[p][key]),color='#be123c',ls='--')
            ax.set_xticks(range(len(values)),[f'{v:g}' for v in values]);ax.set_xlabel(cfg.LABELS[key]);ax.set_ylabel('Delta seconds / source')
        for ax in list(axes.flat)[len(cfg.GRID[p]):]:
            ax.axis('off')
        fig.suptitle(f'Q{p}: differences vs shared default; unadjusted 95% time-block bootstrap intervals')
        fig.tight_layout();fig.savefig(dest/f'q{p}_differences.png',dpi=180);plt.close(fig)
    if robust:
        fig,axes=plt.subplots(1,2,figsize=(11,4))
        for ax,r in zip(axes,robust):
            p=r['problem']
            ax.axvline(1.05,color='#be123c',ls='--',label='5% noninferiority boundary')
            ax.axvline(1,color='#64748b',lw=.8)
            ax.scatter([r['ratio']],[0],s=40,color='#0369a1')
            if r['ratio_ci95']:
                ax.hlines(0,*r['ratio_ci95'],color='#0369a1',lw=3)
            ax.set_yticks([]);ax.set_xlabel('Perturbed / default pooled time')
            ax.set_title(f"Q{p}: cleared {r['perturbed_all_clear']}/{r['perturbed_runs']} perturbed, "
                         f"{r['baseline_all_clear']}/{r['baseline_runs']} default")
            ax.legend(fontsize=7)
        fig.tight_layout();fig.savefig(dest/'joint_robustness.png',dpi=180);fig.savefig(dest/'joint_robustness.pdf');plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,4))
    for ax,p in zip(axes,(3,4)):
        sub=[s for s in summary if s['problem']==p and s['phase']=='robustness']
        left=np.zeros(len(sub))
        for key,label in [('movement_s','Movement'),('measurement_s','Measurement'),('switch_s','Switch'),('failed_clear_s','Failed clear'),('successful_clear_s','Successful clear')]:
            values=[s[key+'_per_source'] for s in sub]
            ax.barh(range(len(sub)),values,left=left,label=label);left+=values
        ax.set_yticks(range(len(sub)),[s['setting'] for s in sub]);ax.set_xlabel('Seconds / source');ax.set_title(f'Q{p}: official action ledger')
    axes[-1].legend(fontsize=7)
    fig.tight_layout();fig.savefig(dest/'joint_costs.png',dpi=180);plt.close(fig)


def report(out,rows,summary,comparisons,robust,audit):
    lines=['# 官方模拟器参数敏感性与联合扰动实验','',
        f"已归档 {len(rows)}/742 局：接入 {audit['phases'].get('calibration',0)}/2，宽扫 {audit['phases'].get('screen',0)}/500，联合扰动 {audit['phases'].get('robustness',0)}/240。",'',
        '**数据全部来自原官方模拟器演练。未运行mock，未使用正式测试额度。** 每次演练为独立新案例；随机区组平衡运行顺序，不构成相同场景配对。','',
        '## 预设判据与结论','',
        '两题分别要求联合扰动80/80全清、同期默认40/40全清，且扰动/默认源加权耗时比的单侧97.5% bootstrap上界小于1.05。区组重采样100000次；两题采用Bonferroni校正。配置和排程均在敏感性结果出现之前冻结。','',
        '|题目|扰动全清|默认全清|扰动秒/源|默认秒/源|耗时比|上界97.5%|全清概率下界97.5%|主要结论|',
        '|---|---:|---:|---:|---:|---:|---:|---:|---|']
    verdicts={'prespecified robustness criteria passed':'通过预设稳健性判据',
        'completion criterion failed':'全清判据未通过',
        'insufficient evidence for <=5% degradation':'证据不足以确认退化不超过5%',
        'observed degradation >=5%; robustness criterion not met':'观测退化至少5%，判据未通过',
        'incomplete; no confirmatory conclusion':'场次未完成，不作验证结论'}
    for r in robust:
        upper='未计算' if r['ratio_upper97_5'] is None else f"{r['ratio_upper97_5']:.5f}"
        lines.append(f"|Q{r['problem']}|{r['perturbed_all_clear']}/{r['perturbed_runs']}|{r['baseline_all_clear']}/{r['baseline_runs']}|"
            f"{r['perturbed_tau']:.3f}|{r['baseline_tau']:.3f}|{r['ratio']:.5f}|{upper}|{r['clear_probability_lower97_5']:.3%}|{verdicts[r['verdict']]}|")
    if len(robust)==2 and all(r['overall_pass'] for r in robust):
        lines+=['','在预先指定的多参数联合扰动分布及独立官方演练案例中，两题策略均保持全部清除，平均每源耗时增加的统计上界低于5%，支持性能并非仅由一组精细调参获得。']
    else:
        lines+=['','当前数据未同时满足两题的全部预设稳健性判据，不能写成“已证明成功不依赖参数偶然性”。完成可靠性、观测效率及统计精度应分开解释。']
    lines+=['','这些结论仅针对预设离散参数分布和官方演练案例；不代表每一种组合或连续参数域均已充分验证。概率下界依赖独立、分布稳定的案例假设；bootstrap为有限样本近似，不是严格最坏情况保证。','',
        '## 宽范围单因素结果','',
        '|题目|设置|全清/局数|秒/源|失手/源|', '|---|---|---:|---:|---:|']
    for s in summary:
        if s['phase']=='screen':
            lines.append(f"|Q{s['problem']}|{s['setting']}|{s['all_cleared']}/{s['runs']}|{s['tau']:.3f}|{s['misses_per_source']:.4f}|")
    lines+=['','宽扫每设置10局，主要用于识别响应趋势、预算门槛和明显退化。全部原始散点和失败均保留；差异未显著不能表述为不敏感。48项比较的原始区间和Holm校正结果见comparisons.csv。','',
        '10个区组的双侧精确随机化检验最小p值为2/1024；同时校正48项比较时，最小Holm调整值也不低于0.09375，因此本轮宽扫无法给出5%水平的多重比较显著性结论。图中横轴为离散测试值，连线不表示连续参数响应的插值模型。','',
        '## 证据与局限','',
        '- trials.csv：逐局官方成绩、源数、动作账本、实际参数及证据目录。',
        '- config.json / analysis_plan.json：预先冻结的742局排程、宽扫范围、联合扰动分布及主要判据。',
        '- summary.csv / comparisons.csv / robustness.json：全部组汇总、宽扫对比和独立联合扰动结果。',
        '- adjusted_robustness.csv：按公开源数量、Q4定向数及时间区组调整的HC3辅助比较；不替代主判据。',
        '- audit.json：官方成绩、案例码、动作成本和参数归属核验；jlogs/与jlog_manifest.json保存官方加密日志原件。',
        '- 运行中消融结果未与本实验合并；随机种子只控制参数与顺序，不控制官方场景。',
        '- 未全清的短耗时不构成效率优势；没有相同案例默认组，不能计算逐局因果退化或宣称逐局占优。',
        '- Q3使用完整定位循环，未记录逐源轮数；round_counters_recorded为false，预算触达数与最大轮数留空。Q4记录的是交错探测轮数。两题active_measurements均为真实主定位测量总数。',
        '- optical_fallback_calls统计光学覆盖点的逐次清除尝试，不能解释为进入兜底的源数；Q4的packet_fallbacks才统计进入兜底的源任务数。',
        '- 未记录的内部计数保持空值；预算未触发与参数路径无效不等于普遍鲁棒。','',
        '![Q3参数曲线](figures/q3_sensitivity.png)','',
        '![Q4参数曲线](figures/q4_sensitivity.png)','',
        '![Q3差值区间](figures/q3_differences.png)','',
        '![Q4差值区间](figures/q4_differences.png)']
    if robust:
        lines+=['','![联合扰动复验](figures/joint_robustness.png)','',
                '![联合扰动动作成本](figures/joint_costs.png)']
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('output',type=Path)
    parser.add_argument('--partial',action='store_true')
    args=parser.parse_args()
    out=args.output.resolve()
    config=json.loads((out/'config.json').read_text())
    runs=[json.loads(line) for line in (out/'runs.jsonl').read_text().splitlines()]
    assert len({r['order'] for r in runs})==len(runs)
    assert len({r['authoritative']['case_code'] for r in runs})==len(runs)
    assert cfg.canonical_hash(config['schedule'])==config['schedule_sha256']
    rows=[]
    for run in runs:
        expected=config['schedule'][run['order']-1]
        assert all(run[k]==v for k,v in expected.items())
        rows.append(audit_trial(run))
    complete=len(rows)==742
    summary=summarize(rows)
    comparisons=screen_comparisons(rows,config['settings'])
    robust=robust_comparisons(rows)
    adjusted=adjusted_robustness(rows)
    audit=dict(recorded_runs=len(rows),complete=complete,phases=dict(Counter(r['phase'] for r in rows)),
        all_cleared=sum(r['completed'] for r in rows),unique_cases=len(rows),
        official_ledger_verified=True,gui_counts_verified=True,parameters_and_schedule_verified=True,
        maximum_action_error_s=max((r['max_action_ledger_error_s'] for r in rows),default=0),
        mock_executions=0,official_formal_runs=0)
    csvout(out/'trials.csv',rows);csvout(out/'summary.csv',summary);csvout(out/'comparisons.csv',comparisons)
    csvout(out/'adjusted_robustness.csv',adjusted)
    dump(out/'robustness.json',robust);dump(out/'audit.json',audit)
    figures(out,rows,summary,comparisons,robust)
    report(out,rows,summary,comparisons,robust,audit)
    print(json.dumps(dict(audit=audit,robustness=robust),ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
