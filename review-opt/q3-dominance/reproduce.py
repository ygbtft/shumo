"""Local mock paired reproduction; Q34_CODE selects the frozen before-code directory.

No sockets, official backend or hidden-state policy inputs. Truth is read only
by the post-run scorer. Configuration matches opt-q34.md confirm split.
"""
import os,sys,json,math,time,hashlib
from pathlib import Path
from dataclasses import asdict
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'): os.environ[key]='1'
ROOT=Path('/Users/flower/math/2026/B题'); sys.path[:0]=[os.environ.get('Q34_CODE',str(ROOT/'B')),str(ROOT)]
import numpy as np
import mock
from mock.scenario_gen import ScenarioConfig,generate
from mock.error_field import ErrorConfig,ErrorField
from mock.simulator import Simulator,Limits
from mock.protocol import Protocol
from client import Client
import bounded_candidates as bc
class Transport:
    def __init__(self,protocol): self.protocol=protocol
    def __call__(self,path,raw):
        r=self.protocol.handle('POST',path,raw,{'Content-Type':'application/json'}); return r.status,r.body

class RecordedRegions(dict):
    def __init__(self):super().__init__();self.history=[]
    def __setitem__(self,key,value):
        self.history.append((key,np.asarray(value).copy()));super().__setitem__(key,value)

def margin(poly,point):
    axis=int(np.ptp(poly,axis=0).argmax());a=poly[poly[:,axis].argmin()];b=poly[poly[:,axis].argmax()];edge=b-a;length=np.linalg.norm(edge)
    if length==0:return -float(np.linalg.norm(point-a))
    off=poly-a
    if np.all(edge[0]*off[:,1]-edge[1]*off[:,0]==0):
        t=np.clip((point-a)@edge/(length*length),0,1);return -float(np.linalg.norm(point-a-t*edge))
    edges=np.roll(poly,-1,axis=0)-poly;norms=np.linalg.norm(edges,axis=1);rel=point-poly
    return float(((edges[:,0]*rel[:,1]-edges[:,1]*rel[:,0])[norms>0]/norms[norms>0]).min())

def run(args):
    problem,idx,split,variant=args
    seed={'screen':202609120,'validate':202609220,'confirm':202610120}[split]+idx
    count=[10,13,16][idx%3];layout=['uniform','edge','clustered'][(idx//3)%3]
    ec=[ErrorConfig(),ErrorConfig(model='smooth'),ErrorConfig(model='adversarial',adversarial_sign='spatial'),ErrorConfig(model='adversarial',adversarial_sign='positive'),ErrorConfig(model='adversarial',adversarial_sign='negative')][idx%5]
    cfg=ScenarioConfig(count_min=count,count_max=count,position_distribution=layout,directional_fraction=.5 if problem==4 else 0.,direction_distribution='outward' if idx%2 else 'uniform',radius_distribution='fixed' if idx%2 else 'uniform',radius_fixed=1000.)
    sc=generate(seed,cfg);sim=Simulator(sc,ErrorField(seed,ec),Limits(countdown_s=0));client=Client(Transport(Protocol(sim)),robot_id='mock-robot')
    policy=bc.build(client,next(iter(bc.SPECS[problem].values())),problem,bc.load_paths(problem))
    policy.regions=RecordedRegions()
    stats={};failure='';began=time.perf_counter()
    try:stats=policy.run()
    except Exception as e:failure=repr(e)
    # Truth is used solely in this post-run scorer; policy sees only protocol replies.
    m=s=cs=cf=0;dist=0.;pos=np.zeros(2);ch=1
    for event in sim.trace:
        if event['path'] not in ('/measure','/clear') or not event['response'].get('accepted'):continue
        payload=event['request'];q=np.array([payload['position']['x'],payload['position']['y']]);dist+=np.linalg.norm(q-pos);pos=q
        if event['path']=='/measure':m+=1;s+=int(ch!=payload['channel']);ch=payload['channel']
        elif event['response']['clear_result']=='success':cs+=1
        else:cf+=1
    truth={g.channel:np.array(g.position) for g in sc.sources}
    margins=[margin(poly,truth[ch]) for ch,poly in policy.regions.history]
    return dict(region_updates=len(margins),min_truth_margin=min(margins,default=0),problem=problem,idx=idx,seed=seed,split=split,variant=variant,sources=len(sc.sources),cleared=len(sim.cleared),failure=failure,T=sim.virtual_time_s,M=m,S=s,Cs=cs,Cf=cf,L=float(dist),ledger_error=sim.virtual_time_s-(dist/5+5*m+s+5*cs+3*cf),stats=stats,wall_s=time.perf_counter()-began,scenario=asdict(cfg),error=asdict(ec))

if __name__=='__main__':
    from concurrent.futures import ProcessPoolExecutor
    split=sys.argv[1];n=int(sys.argv[2]);out=Path(sys.argv[3]);label=sys.argv[4]
    tasks=[(3,i,split,label) for i in range(n)]
    with out.open('w') as f,ProcessPoolExecutor(max_workers=4) as pool:
        for i,row in enumerate(pool.map(run,tasks)):
            f.write(json.dumps(row)+'\n');f.flush()
            if i%20==0:print(i+1,len(tasks),flush=True)
