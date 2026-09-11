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
from adaptive_routes import remaining_route
from coupled_dispatch_policy import CoupledCompletionPolicy,CoupledWidthPolicy
from negative_hull_policy import NegativeHullMixin
from service_aware_policy import ServiceAwareMixin

class Transport:
    def __init__(self,protocol): self.protocol=protocol
    def __call__(self,path,raw):
        r=self.protocol.handle('POST',path,raw,{'Content-Type':'application/json'}); return r.status,r.body

class TimeProxy:
    def next_task(self,unused):
        if len(set(self.regions)|self.cleared)==16:
            self.stats['known_upper_bound_skips']+=len(unused); unused.clear()
        prev=getattr(self,'_last_partial',None)
        if prev is not None and prev not in self.cleared and self.stats['source_interruptions']>=self.pause_limit:
            return 'source',prev,self.circle(prev)[0]
        tasks=[('survey',i,self.stations[i]) for i in unused]+[('source',c,self.circle(c)[0]) for c in self.regions if c not in self.cleared]
        if not tasks:return None
        points=np.array([t[2] for t in tasks]); route=remaining_route(points,self.client.position,True)
        def score(order):
            pos=self.client.position; channel=self.client.channel; cleared=set(self.cleared); total=0.
            for idx in order:
                kind,key,p=tasks[idx]; total+=np.linalg.norm(p-pos)/5; pos=p
                if kind=='source':
                    # Frozen one-completion approximation, no truth and no discovery reward.
                    if self.circle(key)[1]>20.-1e-5:
                        total+=5+(channel!=key);channel=key
                    total+=5;cleared.add(key)
                else:
                    cs=[]
                    for c in range(1,21):
                        if c in cleared: continue
                        if c in self.regions:
                            center,r=self.circle(c)
                            if r<=20.-1e-5 or np.linalg.norm(p-center)>1500+r+1e-5:continue
                        cs.append(c)
                    if cs:
                        total+=5*len(cs)+len(cs)-(channel in cs)
                        # Mirror ascending scan with current-channel-first.
                        channel=max(c for c in cs if c!=channel) if len(cs)>1 else cs[0]
            return total
        orders=[np.r_[route[j:j+1],route[:j],route[j+1:]] for j in range(min(4,len(route)))]
        chosen=int(min(enumerate(orders),key=lambda x:(score(x[1]),x[0]))[1][0]);task=tasks[chosen]
        if prev is not None and prev not in self.cleared and task[:2]!=('source',prev):
            self.stats['source_interruptions']+=1;self._interrupted_channels.add(prev)
        return task

class PacketShare:
    def source_packet(self,ch):
        old=self.share;self.share=False
        try:super().source_packet(ch)
        finally:self.share=old
        if old:self.share_at(self.client.position,ch)


class OmniNegative:
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.negatives={c:[] for c in range(1,21)}
        self.stats['omni_negative_cuts']=0
    def measure(self,p,ch):
        result=super().measure(p,ch)
        if result=='no_signal':self.negatives[ch].append(np.asarray(p).copy())
        if ch in self.regions and ch not in self.cleared:
            from geometry import clip
            poly=self.regions[ch]
            for q in self.negatives[ch]:
                for a,_ in self.observations[ch]:
                    n=2*(q-a);bound=float(q@q-a@a)+1e-4
                    if np.max(poly@n)>bound+1e-5:
                        new=clip(poly,n,bound)
                        if not len(new):raise RuntimeError('negative inconsistent')
                        poly=new;self.stats['omni_negative_cuts']+=1
            self.regions[ch]=poly;self._circles.pop(ch,None)
        return result

class PairOrder:
    def probes(self,ch,step):
        anchor,u,length,points=super().probes(ch,step)
        from intelligent import hypotheses,reception_probability
        samples=hypotheses(self.regions[ch]);center=self.circle(ch)[0]
        def cost(q):
            prob=np.mean([reception_probability(q,g,self.observations[ch],True) for g in samples])
            return np.linalg.norm(q-self.client.position)/5+5+(1-prob)*(np.linalg.norm(points[0]-points[1])/5+5)
        points=sorted(points,key=cost)
        return anchor,u,length,points

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
    spec=next(iter(bc.SPECS[problem].values())).copy();spec.pop('kind');points=bc.load_paths(problem)[spec.pop('layout')]
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
    split=sys.argv[1];n=int(sys.argv[2]);out=Path(sys.argv[3]);variants=sys.argv[4:]
    tasks=[(p,i,split,v) for p in (3,) for i in range(n) for v in variants if (p==4 or not (v.startswith(('cool','width')) or v in ('packet_share','pair_order'))) and (p==3 or v!='omni_negative')]
    with out.open('w') as f,ProcessPoolExecutor(max_workers=4) as pool:
        for i,row in enumerate(pool.map(run,tasks)):
            f.write(json.dumps(row)+'\n');f.flush()
            if i%20==0:print(i+1,len(tasks),flush=True)
