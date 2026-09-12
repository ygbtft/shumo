"""Three additional budgets on the existing tangent scene, then shared F9 scoring."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import time
from models.q1q2 import sensitivity as s
from models.q1q2.geometry import BearingMeasurement, NumericPolicy
from models.q1q2.feasible import PhysicsConfig, build_source_set
from models.q1q2.q2 import SearchConfig, check_admissibility, short_baseline_lower_bound
from models.q1q2.run import write_json

folder=Path(sys.argv[1])
def load(name): return json.loads((folder/(name+'.json')).read_text())
def model_cfg(raw):
    first=raw['source_set']['first']
    ss=build_source_set(BearingMeasurement(tuple(first['position']),first['bearing_deg'],first['half_width_deg']),PhysicsConfig(),NumericPolicy())
    data=raw['config']; data['policy']=ss.policy
    return ss,SearchConfig(**data)
raw=load('tangent_default');ss,cfg=model_cfg(raw);old=tuple(raw['reselected']['q'])
for budget in (200.,400.,500.):
    key='F9_tangent_B'+str(int(budget))
    if (folder/(key+'.json')).exists():
        continue
    record,pool=s.run_case(key,ss,replace(cfg,movement_budget_m=budget),old)
    write_json(folder/(key+'.json'),record)
    print(key,record['reselected']['score'].J_hat if record['reselected'] else None,flush=True)
# Wait-free prerequisite: call this after the main run finishes writing standard F9 files.
started=time.monotonic();groups={};total_calls=0
for name,keys in [('standard',['F9_B10','F9_B200','F9_B600']),('tangent',['F9_tangent_B200','F9_tangent_B400','F9_tangent_B500'])]:
    base=load(name+'_default');ss,cfg=model_cfg(base)
    raws={k:load(k) for k in keys}
    points=[tuple(base['reselected']['q'])]
    points += [tuple(row['q']) for r in raws.values() for row in r['final_candidates']]
    if name == 'standard':
        points.append((10.,0.))  # Legal B=10 axial finalist supplies S2 near control.
    rows,pool,cost=s.common_evaluation(ss,cfg,points)
    curves=[]
    # A single pool and cumulative feasible candidate population at each budget.
    for key,r in raws.items():
        restricted=replace(cfg,movement_budget_m=r['config']['movement_budget_m'])
        adjusted=[]
        for row in rows:
            assessment=check_admissibility(ss,row['q'],restricted)
            adjusted.append(dict(row,admissibility=assessment,
                score=row['score'] if assessment['status']=='IN' else None,
                clearance=row['clearance'] if assessment['status']=='IN' else None,
                representative_feedbacks=row['representative_feedbacks'] if assessment['status']=='IN' else []))
        oldrow=next(row for row in adjusted if row['q']==tuple(base['reselected']['q']))
        new=s.choose(adjusted,ss,cfg.tie_floor_m)
        curves.append(dict(key=key,budget_m=restricted.movement_budget_m,fixed_old=oldrow,reselected=new))
        r['before_F9_shared_final']={k:r[k] for k in ('fixed_old','reselected','final_candidates')}
        r.update(fixed_old=oldrow,reselected=new,final_candidates=adjusted,
                 F9_shared_accounting_reference='F9_shared.json/'+name)
        write_json(folder/(key+'.json'),r)
    # Infinite budget is a labelled reference, not a finite B value.
    curves.append(dict(key=name+'_unrestricted',budget_m=None,fixed_old=next(row for row in rows if row['q']==tuple(base['reselected']['q'])),reselected=s.choose(rows,ss,cfg.tie_floor_m)))
    groups[name]=dict(curve=curves,accounting=cost)
    total_calls+=cost['score_calls']
ss,_=model_cfg(load('standard_default'))
write_json(folder/'F9_shared.json',dict(groups=groups,score_calls=total_calls,elapsed_seconds=time.monotonic()-started,
    analytic_B10_standard_only=short_baseline_lower_bound(ss,500.,1500.,10.),
    note='same physical model, frozen shared final pool, cumulative candidates; .1m tie can increase J by at most tie within that pool'))
print('shared F9 complete')
