"""Read-only peer audit. Run with q1q2/.venv/bin/python -B; no network."""
import sys, json, math, hashlib
from pathlib import Path
import numpy as np
ROOT=Path('/Users/flower/math/2026/NTJ_B_wt/B')
sys.path.insert(0,str(ROOT))
from ring_coverage import metadata,stations
from coverage import route_length

def cross(a,b,c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
def hull(ps):
    ps=sorted(set(ps)); lo=[];hi=[]
    for seq,out in ((ps,lo),(ps[::-1],hi)):
        for p in seq:
            while len(out)>1 and cross(out[-2],out[-1],p)<=0:out.pop()
            out.append(p)
    return lo[:-1]+hi[:-1]
def exact_check(item):
    S=65536; A=1800*S; R=1000*S
    ps=[tuple(int(x)*S for x in p) for p in item['points']]
    assert all(tuple(x/S for x in q)==tuple(p) for q,p in zip(ps,item['points']))
    leaves=set(); min_cross=None; max_d2=0; cache={}
    for x,y,h,ids in item['certificate']['cells']:
        vals=(x*S,y*S,h*S);assert all(v==int(v) for v in vals)
        x,y,h=map(int,vals);assert (x,y,h) not in leaves;leaves.add((x,y,h))
        key=tuple(ids)
        if key not in cache:cache[key]=hull([ps[i] for i in ids])
        H=cache[key]; assert len(H)>=3
        for q in ((x-h,y-h),(x+h,y-h),(x+h,y+h),(x-h,y+h)):
            for i in ids:
                d2=sum((a-b)**2 for a,b in zip(q,ps[i]));assert d2<R*R;max_d2=max(max_d2,d2)
            for a,b in zip(H,H[1:]+H[:1]):
                z=cross(a,b,q);assert z>=0
                min_cross=z if min_cross is None else min(min_cross,z)
    todo=[(0,0,A)];seen=set();nodes=0;minimum=min(h for x,y,h in leaves)
    while todo:
        x,y,h=todo.pop();nodes+=1
        if (x,y,h) in leaves:seen.add((x,y,h));continue
        if max(abs(x)-h,0)**2+max(abs(y)-h,0)**2>A*A:continue
        assert h>=minimum and h%2==0
        hh=h//2;todo.extend((x+dx*hh,y+dy*hh,hh) for dx in (-1,1) for dy in (-1,1))
    assert seen==leaves
    assert set(map(tuple,item['points']))==set(map(tuple,item['route']))
    return dict(leaves=len(leaves),partition_nodes=nodes,strict_hull=min_cross>0,range_margin_m=1000-math.sqrt(max_d2)/S,route_m=route_length(item['route']))
selected=json.loads((ROOT/'experiments/runs/2026-09-11_cover21-confirmation/selected_layouts.json').read_text())
closed=json.loads((ROOT/'experiments/runs/2026-09-11_closed-cover21/certified_layouts.json').read_text())
results={'integer_certificates':{k:exact_check(v) for k,v in {**closed,'grid21_7':selected['grid21_7'],'grid21_29':selected['grid21_29']}.items()},'q3_analytic':metadata()}
# Independent distance/dot counterexample to reusing Q3 ring as Q4 coverage.
p=stations(6,1140.);g=np.array([1800.,0.]);delta=p-g
results['q3_ring_used_for_q4_counterexample']={'source':g.tolist(),'radius':1000,'face_deg':0,'receivable_stations':int(np.sum((np.linalg.norm(delta,axis=1)<=1000)&(delta[:,0]>=0)))}
assert results['q3_ring_used_for_q4_counterexample']['receivable_stations']==0
# Small live-policy checks: all omni Q3; one outward boundary directional source Q4.
import cover21_confirmation as live
from cover21_experiments import Source,Scenario,Simulator,ErrorField,ErrorConfig,Limits,Protocol,PeerTransport,Client
paths=live.all_paths();runs=[]
for problem,method in ((3,'range_area7'),(4,'range_grid21_29'),(4,'count_locked_grid21_29')):
    for n in (10,13,16):
        pos=[(1800.,0.)]+[(700*math.cos(i*2*math.pi/(n-1)+.137),700*math.sin(i*2*math.pi/(n-1)+.137)) for i in range(n-1)]
        sources=tuple(Source(ch,*xy,1000.,0. if problem==4 and j==0 else None) for j,(ch,xy) in enumerate(zip([20]+list(range(1,n)),pos)))
        scenario=Scenario(42,sources,{})
        sim=Simulator(scenario,ErrorField(42,ErrorConfig(model='adversarial',adversarial_sign='positive')),Limits(countdown_s=0))
        stats=live.build(Client(PeerTransport(Protocol(sim)),robot_id='mock-robot'),live.SPECS[problem][method],problem,paths).run()
        assert len(sim.cleared)==n and not stats['inconsistent_updates']
        assert sim.virtual_time_s<335136 and len(sim.trace)<=9766
        if n<16:assert stats.get('public_empty_scan_skips',0)==0
        runs.append(dict(problem=problem,method=method,n=n,cleared=len(sim.cleared),stations=stats['stations_visited'],stop_reason=stats['stop_reason'],virtual_s=sim.virtual_time_s,commands=len(sim.trace),public_empty_skips=stats.get('public_empty_scan_skips',0)))
results['live_smoke']=runs
# Exercise the public-count branch: channels 1..16 all visible at the origin.
sources=tuple(Source(i+1,700*math.cos(i*2*math.pi/16),700*math.sin(i*2*math.pi/16),1000.,180. if i==0 else None) for i in range(16))
sim=Simulator(Scenario(42,sources,{}),ErrorField(42,ErrorConfig(model='adversarial',adversarial_sign='positive')),Limits(countdown_s=0))
stats=live.build(Client(PeerTransport(Protocol(sim)),robot_id='mock-robot'),live.SPECS[4]['count_locked_grid21_29'],4,paths).run()
assert len(sim.cleared)==16 and stats['public_empty_scan_skips']==4
results['public_count_targeted']={k:stats.get(k) for k in ('public_empty_scan_skips','stations_visited','stop_reason','minimum_actual_unknown_per_station')}
results['public_count_targeted']['cleared']=len(sim.cleared)
names=['coverage.py','coverage_replacement.py','ring_coverage.py','visibility_certificate.py','integer_visibility_certificate.py','closed_cover21_search.py','odd_ring_cover_search.py','rounded_cover21_search.py','multicore_cover_search.py','lean_scan_policy.py','public_count_scan_policy.py','wide_probe_policy.py','discovery_priority_policy.py']
results['sha256']={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names}
print(json.dumps(results,ensure_ascii=False,indent=2))
