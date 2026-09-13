"""Audit authoritative official practice scores and analyze independent cases."""
import argparse
import csv
import hashlib
import itertools
import json
import math
import re
from pathlib import Path
import numpy as np
from scipy.stats import t as student_t
import ablation_data_suite as suite


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')


def csvout(path, rows):
    if not rows: return
    keys=list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        w=csv.DictWriter(f, fieldnames=keys);w.writeheader();w.writerows(rows)


def trial(run):
    score=run['authoritative'];evidence=Path(run['evidence'])
    files=list(evidence.glob('*/robot-run/requests.jsonl'));assert len(files)==1
    trace=[json.loads(l) for l in files[0].read_text().splitlines()]
    position=(0.,0.);channel=1;distance=0.;measurements=switches=misses=successes=0
    virtual=0.;max_error=0.;ids=set();retries=0
    for e in trace:
        if e.get('event')=='transport_failure': retries+=1;continue
        q=e['request'];r=e['response'];path=e['path']
        assert r.get('accepted') is True and e['http_status']==200
        assert q['request_id'] not in ids;ids.add(q['request_id'])
        cost=0.
        if path in ('/measure','/clear'):
            point=(q['position']['x'],q['position']['y'])
            d=math.dist(position,point);distance+=d;position=point;cost+=d/5
        if path=='/measure':
            measurements+=1;sw=int(q['channel']!=channel);switches+=sw
            channel=q['channel'];cost+=5+sw
        if path=='/clear':
            success=r['clear_result']=='success'
            successes+=int(success);misses+=int(not success);cost+=5 if success else 3
        err=abs(r['virtual_time_s']-virtual-cost);max_error=max(max_error,err)
        virtual=r['virtual_time_s']
    assert trace[0]['path']=='/enter' and trace[-1]['path']=='/exit'
    assert max_error<2e-6,max_error
    assert abs(virtual-score['virtual_time_us']/1e6)<2e-6
    assert successes==score['cleared_jammer_count'] and misses==score['clear_failure_count']
    completed=list(evidence.glob('*-run/*completed.uia.json'));assert len(completed)==1
    texts=[r['text'] for r in json.loads(completed[0].read_text(encoding='utf-8-sig'))]
    counts=[re.search(r'本次案例含干扰源(\d+)个，其中全向(\d+)个、定向(\d+)个',s) for s in texts]
    counts=[m for m in counts if m];assert len(counts)==1
    n,omni,directional=map(int,counts[0].groups())
    assert n==omni+directional==score['jammer_count']
    assert score['case_code'] in texts
    spec=run['robot']['variant'];assert spec['id']==run['variant']
    assert run['robot']['mock_executions']==0
    return dict(phase=run['phase'],problem=run['problem'],variant=run['variant'],
        component=spec['component'],gate_m=spec['gate'],block=run['block'],order=run['order'],
        case_code=score['case_code'],official_row_id=score['id'],practice_run_no=str(score['practice_run_no']),
        sources=n,omni_sources=omni,directional_sources=directional,cleared=successes,
        completed=int(n==successes and run['robot']['status']=='policy-completed'),
        virtual_time_us=score['virtual_time_us'],total_s=virtual,seconds_per_source=virtual/n,
        distance_m=distance,movement_s=distance/5,measurements=measurements,measurement_s=5*measurements,
        switches=switches,switch_s=switches,misses=misses,failed_clear_s=3*misses,successful_clear_s=5*successes,
        ledger_rounding_s=virtual-(distance/5+5*measurements+switches+3*misses+5*successes),
        max_action_ledger_error_s=max_error,retries=retries,wall_s=run['wall_s'],
        end_reason=score['end_reason'],evidence=str(evidence),trace=str(files[0]),
        shared_measurements=run['robot']['policy'].get('shared_known_measurements',0),
        early_optical_trials=run['robot']['policy'].get('early_optical_trials',0),
        optical_fallback_calls=run['robot']['policy'].get('optical_fallback_calls',0),
        certified_clears=run['robot']['policy'].get('certified_clears',0))


def boot(rows,rng,size=10000):
    a=np.array([[r['total_s'],r['sources']] for r in rows])
    sampled=a[rng.integers(len(a),size=(size,len(a)))].sum(axis=1)
    return sampled[:,0]/sampled[:,1]


def ratio(rows):return sum(r['total_s'] for r in rows)/sum(r['sources'] for r in rows)


def holm(rows,key,target):
    ordered=sorted(rows,key=lambda r:r[key]);largest=0.
    for i,r in enumerate(ordered):
        largest=max(largest,min(1.,(len(ordered)-i)*r[key]));r[target]=largest


def main():
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path)
    parser.add_argument('--partial',action='store_true');args=parser.parse_args();out=args.output
    runs=[json.loads(l) for l in (out/'runs.jsonl').read_text().splitlines()]
    # Host writes runs before the last evidence copy completes. Exclude that transient row.
    if args.partial:runs=[r for r in runs if list(Path(r['evidence']).glob('*/robot-run/requests.jsonl'))]
    trials=[trial(r) for r in runs];rows=[r for r in trials if r['phase']=='validation']
    assert len({r['case_code'] for r in trials})==len(trials)
    config=json.loads((out/'config.json').read_text())
    for r in rows:
        expected=config['schedule'][r['order']-1]
        assert all(r[k]==expected[k] for k in ('problem','variant','block','order'))
    if not args.partial:
        assert len(rows)==160 and sorted(r['order'] for r in rows)==list(range(1,161))
    csvout(out/'trials.csv',trials)
    grouped={};summaries=[];comparisons=[];rng=np.random.default_rng(216091302)
    for setting in config['settings']:
        p=setting['problem'];v=setting['variant'];group=[r for r in rows if r['problem']==p and r['variant']==v]
        if not group:continue
        grouped[p,v]=group;n=sum(r['sources'] for r in group)
        ci=np.quantile(boot(group,rng),[.025,.975])
        s=dict(problem=p,variant=v,label=suite.LABELS[group[0]['component']],gate_m=group[0]['gate_m'],
            runs=len(group),completed=sum(r['completed'] for r in group),sources=n,
            mean_sources=n/len(group),directional_fraction=sum(r['directional_sources'] for r in group)/n,
            seconds_per_source=ratio(group),ci_low=ci[0],ci_high=ci[1],
            mean_case_seconds_per_source=float(np.mean([r['seconds_per_source'] for r in group])),
            misses=sum(r['misses'] for r in group))
        for key in ('movement_s','measurement_s','switch_s','failed_clear_s','successful_clear_s','measurements','shared_measurements'):
            s[key+'_per_source']=sum(r[key] for r in group)/n
        summaries.append(s)
    for (p,v),g in grouped.items():
        baseline=f'full__g{suite.DEFAULT_GATE[p]:g}';b=grouped.get((p,baseline))
        if not b or v==baseline:continue
        diff=ratio(g)-ratio(b);ci=np.quantile(boot(g,rng)-boot(b,rng),[.025,.975])
        c=dict(problem=p,variant=v,baseline=baseline,runs=len(g),baseline_runs=len(b),
            delta_seconds_per_source=diff,relative_pct=100*diff/ratio(b),ci_low=ci[0],ci_high=ci[1],
            efficiency_valid=all(r['completed'] for r in g+b))
        # Exact randomization: swap these two labels within each fully observed time block.
        # The scenes are independent; blocks refer ONLY to randomized run order.
        if len(g)==len(b)==10:
            ga=sorted(g,key=lambda r:r['block']);ba=sorted(b,key=lambda r:r['block'])
            assert [r['block'] for r in ga]==[r['block'] for r in ba]==list(range(1,11))
            null=[]
            for mask in itertools.product((0,1),repeat=10):
                left=[ga[i] if bit else ba[i] for i,bit in enumerate(mask)]
                right=[ba[i] if bit else ga[i] for i,bit in enumerate(mask)]
                null.append(ratio(left)-ratio(right))
            c['p_randomization']=sum(abs(d)>=abs(diff)-1e-10 for d in null)/len(null)
        comparisons.append(c)
    exact=[r for r in comparisons if 'p_randomization' in r]
    if len(exact)==14:holm(exact,'p_randomization','p_holm_14')
    # Secondary sensitivity analysis, prespecified before completion: OLS + HC3.
    # Adjust only for public end-of-run source counts; no hidden geometry is observed.
    adjusted=[]
    if not args.partial:
        for p in (3,4):
            sub=[r for r in rows if r['problem']==p]
            baseline=f'full__g{suite.DEFAULT_GATE[p]:g}'
            variants=[s['variant'] for s in config['settings'] if s['problem']==p and s['variant']!=baseline]
            nbar=np.mean([r['sources'] for r in sub]);dbar=np.mean([r['directional_sources'] for r in sub])
            x=np.array([[1]+[int(r['variant']==v) for v in variants]+[r['sources']-nbar]+
                        ([r['directional_sources']-dbar] if p==4 else []) for r in sub],dtype=float)
            y=np.array([r['total_s'] for r in sub]);inverse=np.linalg.inv(x.T@x);coef=inverse@x.T@y
            hat=np.sum((x@inverse)*x,axis=1);u=(y-x@coef)/(1-hat)
            cov=inverse@((x*u[:,None]).T@(x*u[:,None]))@inverse
            dof=len(sub)-x.shape[1];cut=student_t.ppf(.975,dof)
            for i,v in enumerate(variants,1):
                se=math.sqrt(cov[i,i]);effect=coef[i]/nbar
                adjusted.append(dict(problem=p,variant=v,baseline=baseline,reference_sources=nbar,
                    reference_directional_sources=dbar,delta_seconds_per_source=effect,
                    ci_low=(coef[i]-cut*se)/nbar,ci_high=(coef[i]+cut*se)/nbar,
                    p_hc3=float(2*student_t.sf(abs(coef[i]/se),dof)),
                    model='total_s ~ variant + source_count'+(' + directional_count' if p==4 else ''),
                    baseline_adjusted_seconds_per_source=coef[0]/nbar))
        holm(adjusted,'p_hc3','p_holm_14')
    csvout(out/'summary.csv',summaries);csvout(out/'comparisons.csv',comparisons)
    csvout(out/'adjusted_sensitivity.csv',adjusted)
    dump(out/'analysis.json',dict(summary=summaries,comparisons=comparisons,adjusted=adjusted))
    dump(out/'audit.json',dict(validation_runs=len(rows),calibration_runs=len(trials)-len(rows),
        all_cleared=sum(r['completed'] for r in rows),unique_official_cases=len(trials),
        per_action_ledger_verified=True,authoritative_counts_verified=True,official_gui_counts_verified=True,
        frozen_assignment_verified=True,local_mock_scored_runs=0,official_formal_runs=0,
        max_action_ledger_error_s=max(r['max_action_ledger_error_s'] for r in trials),partial=args.partial))
    print(json.dumps(dict(validation=len(rows),completed=sum(r['completed'] for r in rows)),ensure_ascii=False))


if __name__=='__main__':main()
