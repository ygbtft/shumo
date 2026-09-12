"""Offline paired OFAT training and frozen independent validation. No network transport.
Run with sibling mock/.venv/bin/python; --output must be a fresh directory.
"""
import os
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'): os.environ[key]='1'
import argparse, csv, hashlib, json, math, sys, time, types, shutil
from pathlib import Path
from dataclasses import asdict
from concurrent.futures import ProcessPoolExecutor
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
import mock
from mock.scenario_gen import Scenario, ScenarioConfig, generate
from mock.error_field import ErrorConfig, ErrorField
from mock.simulator import Simulator, Limits
from mock.protocol import Protocol
import numpy as np
import bounded_candidates as builders
from client import Client
# Values chosen before seeing any training results. Default is always included.
GRID={3:{'share_limit':[0,1,2,4,6,10,20], 'localization_weight':[0,.02,.04,.08,.16,.32],
         'steps':[4,6,8,10], 'max_active':[1,2,3,4,5], 'remainder_weight':[0,.5,1,1.5,2]},
      4:{'share_limit':[0,1,2,4,6,10,20], 'share_cooldown':[0,50,100,150,250,400,800],
         'transverse_m':[10,20,30,40,60,80,100], 'angle_min':[1.02,2,5,10],
         'angle_max':[5,10,20,30], 'localization_weight':[0,.04,.08,.16],
         'steps':[4,6,8,10], 'pause_limit':[0,4,8,16,24], 'fraction':[.05,.1,.15,.25,.35,.5]}}
DEFAULT={'share_limit':6,'localization_weight':.08,'steps':10,'max_active':3,'remainder_weight':1,
         'share_cooldown':150,'transverse_m':40,'angle_min':1.02,'angle_max':30,'pause_limit':16,'fraction':.15}
METHOD={3:'range_area7',4:'range_grid21_29'}

def cases(p,repeats,start):
    errors=[ErrorConfig(),ErrorConfig(model='smooth')]+[ErrorConfig(model='adversarial',adversarial_sign=s) for s in ('positive','negative','spatial')]
    i=0
    for rep in range(repeats):
        for n in range(10,17):
            for layout in ('uniform','edge','clustered'):
                for error in errors:
                    cfg=ScenarioConfig(count_min=n,count_max=n,position_distribution=layout,directional_fraction=.5 if p==4 else 0.,direction_distribution='outward' if rep%2 else 'uniform',radius_distribution='fixed' if rep%2 else 'uniform',radius_fixed=1000.)
                    seed=start+i;i+=1
                    yield dict(case_id=f'q{p}_{seed}',scenario=generate(seed,cfg).to_dict(),error=asdict(error),category=f'{layout}/{error.model}/{error.adversarial_sign}')

class Transport:
    def __init__(self,protocol): self.protocol=protocol
    def __call__(self,path,raw):
        r=self.protocol.handle('POST',path,raw,{'Content-Type':'application/json'})
        return r.status,r.body

def construct(p,client,changes):
    spec=builders.SPECS[p][METHOD[p]].copy()
    spec.update({k:v for k,v in changes.items() if k not in ('angle_min','angle_max','max_active')})
    policy=builders.build(client,spec,p,builders.load_paths(p))
    if 'max_active' in changes: policy.max_active=changes['max_active']
    # Experimental instance-only override of the hardcoded angle clamps. The
    # original method still supplies anchor and length. Defaults preserve exact arithmetic.
    if 'angle_min' in changes or 'angle_max' in changes:
        lo,hi=changes.get('angle_min',1.02),changes.get('angle_max',30.)
        assert 1.02<=lo<=hi<=30
        original=policy.probes
        def probes(self,ch,step):
            anchor,u,length,points=original(ch,step)
            if length<=0:return anchor,u,length,points
            width=min(length*math.tan(math.radians(hi)),max(length*math.tan(math.radians(lo)),self.transverse_m))
            v=np.array([-u[1],u[0]])
            points=[anchor+length*u+width*v,anchor+length*u-width*v]
            points.sort(key=lambda q:float(np.linalg.norm(q-self.client.position)))
            return anchor,u,length,points
        policy.probes=types.MethodType(probes,policy)
    assert policy.trial_radius==({3:50.,4:35.}[p])
    if p==4: assert policy.bracket_trial_radius==35.
    return policy

def execute(task):
    p,label,changes,f=task
    scenario=Scenario.from_dict(f['scenario'])
    sim=Simulator(scenario,ErrorField(scenario.seed,ErrorConfig(**f['error'])),Limits(countdown_s=0))
    policy=construct(p,Client(Transport(Protocol(sim)),robot_id='mock-robot'),changes)
    events=[];original=policy.clear
    def clear(point,ch,certified=False):
        success=original(point,ch,certified)
        events.append(dict(channel=ch,certified=certified,success=success))
        return success
    policy.clear=clear
    error=''
    try: stats=policy.run()
    except Exception as exc: error=repr(exc);stats=policy.stats.copy()
    measures=switches=misses=0;channel=1
    for e in sim.trace:
        if e['path']=='/measure':
            measures+=1;new=e['request']['channel'];switches+=int(new!=channel);channel=new
        if e['path']=='/clear': misses+=e['response'].get('clear_result')=='no_target_in_range'
    assert misses==sum(not e['success'] for e in events)
    return dict(problem=p,setting=label,changes=changes,case_id=f['case_id'],category=f['category'],sources=len(scenario.sources),cleared=len(sim.cleared),all_cleared=len(sim.cleared)==len(scenario.sources) and not error,failure=error,total_virtual_s=sim.virtual_time_s,measurements=measures,switches=switches,misses=misses,certified_failures=sum(e['certified'] and not e['success'] for e in events),stats=stats)

def summarize(rows,out):
    result=[]
    for p in (3,4):
        base={r['case_id']:r for r in rows if r['problem']==p and r['setting']=='baseline'}
        for label in dict.fromkeys(r['setting'] for r in rows if r['problem']==p):
            group=[r for r in rows if r['problem']==p and r['setting']==label]
            n=np.array([r['sources'] for r in group]);d=np.array([r['total_virtual_s']-base[r['case_id']]['total_virtual_s'] for r in group])
            ids=np.random.default_rng(20260912).integers(len(group),size=(4000,len(group)))
            ci=np.quantile(d[ids].sum(1)/n[ids].sum(1),[.025,.975]).tolist()
            item=dict(problem=p,setting=label,changes=group[0]['changes'],runs=len(group),all_cleared=sum(r['all_cleared'] for r in group),sources=int(n.sum()),seconds_per_source=sum(r['total_virtual_s'] for r in group)/int(n.sum()),delta=float(d.sum()/n.sum()),ci=ci,faster=int((d < -1e-6).sum()),slower=int((d>1e-6).sum()),same=int((abs(d)<=1e-6).sum()),worst_s=float(max(0,d.max())),worst_percent=max(0,max(100*x/base[r['case_id']]['total_virtual_s'] for x,r in zip(d,group))),worst_case=group[int(d.argmax())]['case_id'])
            for key in ('measurements','switches','misses','certified_failures'):item[key]=sum(r[key] for r in group)
            for key in ('shared_known_measurements','shared_negative_cooldown_skips','active_measurements','source_interruptions','packet_fallbacks','optical_fallback_calls','bracket_pair_cuts'):item[key]=sum(r['stats'].get(key,0) for r in group)
            item['maximum_source_primary_rf']=max(r['stats'].get('maximum_source_primary_rf',0) for r in group)
            result.append(item)
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    with (out/'summary.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(result[0]));writer.writeheader();writer.writerows(result)
    return result

def run_phase(out,fixtures,settings,workers):
    out.mkdir();(out/'fixtures.json').write_text(json.dumps(fixtures))
    tasks=[(p,label,change,f) for p in (3,4) for f in fixtures[p] for label,change in settings[p].items()]
    rows=[];began=time.perf_counter()
    with (out/'trials.jsonl').open('x') as stream,ProcessPoolExecutor(max_workers=workers) as pool:
        for row in pool.map(execute,tasks,chunksize=5):
            rows.append(row);stream.write(json.dumps(row)+'\n')
            if len(rows)%2000==0: stream.flush();print(f'{out.name}: {len(rows)}/{len(tasks)} ({time.perf_counter()-began:.1f}s)',flush=True)
    summary=summarize(rows,out)
    (out/'completion.json').write_text(json.dumps(dict(runs=len(rows),failed=sum(not r['all_cleared'] for r in rows),wall_s=time.perf_counter()-began),indent=2))
    return summary

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    snap=out/'code_snapshot';snap.mkdir()
    for f in ROOT.glob('*.py'):shutil.copy2(f,snap/f.name)
    shutil.copytree(ROOT/'layouts',snap/'layouts');shutil.copytree(Path(mock.__file__).parent,out/'mock_snapshot',ignore=shutil.ignore_patterns('.venv','__pycache__','.git'))
    protected=list(ROOT.glob('*.py'))+[ROOT/'models/paper-full.md']
    hashes={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in protected if f.exists()}
    config=dict(python=sys.executable,mock_path=mock.__file__,train_seeds=[202630000,202630419],validation_seeds=[202640000,202641049],grid=GRID,defaults=DEFAULT,baseline_specs=builders.SPECS,sha256=hashes,official_calls=0,selection='OFAT lowest pooled training seconds among 100% full-clear settings; validate all individual winners and combined winners frozen before validation; no validation retuning')
    (out/'config.json').write_text(json.dumps(config,indent=2))
    settings={p:{'baseline':{}} for p in (3,4)}
    for p in (3,4):
        for key,values in GRID[p].items():
            for v in values:
                if v!=DEFAULT[key]:settings[p][f'{key}={v}']={key:v}
    train=run_phase(out/'training',{p:list(cases(p,4,202630000)) for p in (3,4)},settings,args.workers)
    selected={p:{'baseline':{}} for p in (3,4)}
    for p in (3,4):
        combined={}
        for key in GRID[p]:
            group=[r for r in train if r['problem']==p and (r['setting']=='baseline' or key in r['changes']) and r['all_cleared']==r['runs']]
            best=min(group,key=lambda r:r['seconds_per_source'])
            if best['setting']!='baseline' and best['delta'] < -1e-6:
                selected[p][best['setting']]=best['changes'];combined.update(best['changes'])
        if len(combined)>1:selected[p]['combined']=combined
    (out/'frozen_selection.json').write_text(json.dumps(selected,indent=2))
    run_phase(out/'validation',{p:list(cases(p,10,202640000)) for p in (3,4)},selected,args.workers)
    unchanged=all(hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==h for f,h in hashes.items())
    (out/'integrity.json').write_text(json.dumps(dict(original_files_unchanged=unchanged,official_calls=0),indent=2))
    assert unchanged
    print('Completed:',out,flush=True)
if __name__=='__main__':main()
