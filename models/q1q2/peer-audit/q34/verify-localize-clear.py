"""Read-only peer audit. Writes only its JSON result beside this script."""
import sys
sys.dont_write_bytecode = True
from pathlib import Path
import json, math, hashlib
import numpy as np

ROOT = Path('/Users/flower/math/2026/NTJ_B_wt/B')
sys.path.insert(0, str(ROOT))
from geometry import update_region, minimum_circle, optical_cover, hull
from clearance_policy import closest_clearance_point
from historical_pair_policy import exclusion_planes, exclude_historical_pair
from batched_history_policy import apply_pair_sequence
from deferred_skip_policy import pair_nonreception_certificate
from cheap_prediction_policy import cheap_pair_nonreception_certificate
from service_aware_policy import reversal_prefix, reversal_delta, route_objective, service_route
from coupled_dispatch_policy import arc_route
from fast_dispatch_policy import fast_arc_route
from ring_coverage import covering_radius
from peer_benchmark import Client, PeerTransport, Simulator, ErrorField, ErrorConfig, Limits, Protocol, ScenarioConfig, generate
from mock.scenario_gen import Source, Scenario
import deferred_confirmation as factory

rng = np.random.default_rng(42)
result = {'seed': 42, 'official_calls': 0, 'checks': {}, 'runs': []}
def inside(p, g):
    if len(p) == 1:
        return np.linalg.norm(p[0]-g) < 1e-6
    if len(p) == 2:
        d=p[1]-p[0]; t=np.clip((g-p[0])@d/max(1e-30,d@d),0,1)
        return np.linalg.norm(p[0]+t*d-g) < 1e-6
    d=np.roll(p,-1,axis=0)-p; v=g-p
    return np.all(d[:,0]*v[:,1]-d[:,1]*v[:,0] >= -1e-6*np.maximum(1,np.linalg.norm(d,axis=1)))

for i in range(400):
    g=rng.normal(size=2); g*=rng.uniform(0,1799)/np.linalg.norm(g)
    p=None
    for j in range(5):
        theta=rng.uniform(0,2*math.pi); d=rng.uniform(5.01,1500)
        s=g+d*np.array([math.cos(theta),math.sin(theta)])
        bearing=math.degrees(math.atan2(*(g-s)[::-1]))
        measured=round((bearing+(-1 if j%2 else 1))%360,2)%360
        p=update_region(p,s,measured)
        assert inside(p,g)
        c,r=minimum_circle(p)
        assert np.linalg.norm(g-c)<=r+1e-6
        cover,cr=optical_cover(p,measured)
        assert cr<20 and np.linalg.norm(cover-g,axis=1).min()<20
result['checks']['bearing_updates_and_optical_cover']=2000

for i in range(200):
    p=hull(rng.uniform(-8,8,(10,2)))+rng.uniform(-1800,1800,2)
    current=rng.uniform(-2500,2500,2)
    q=closest_clearance_point(p,current)
    c,r=minimum_circle(p)
    assert np.linalg.norm(p-q,axis=1).max()<20
    assert np.linalg.norm(q-current)<=np.linalg.norm(c-current)+1e-6
result['checks']['clearance_feasibility_and_center_comparison']=200

tested=0
for i in range(10000):
    s,a,b,g=rng.uniform(-2000,2000,(4,2))
    planes=exclusion_planes(s,a,b)
    if planes is None: continue
    n,h=planes
    predicted=np.all(n@g-h < -1e-4)
    if predicted:
        u,v=np.linalg.solve(np.column_stack((g-s,-(b-a))),a-s)
        assert 0<=u<=1 and 0<=v<=1
        assert np.linalg.norm(g-a)<=np.linalg.norm(g-s)+1e-7
        assert np.linalg.norm(g-b)<=np.linalg.norm(g-s)+1e-7
        tested+=1
result['checks']['historical_exclusion_independent_witnesses']=tested

certified=0
for i in range(300):
    theta=rng.uniform(0,2*math.pi)
    rotation=np.array([[math.cos(theta),-math.sin(theta)],[math.sin(theta),math.cos(theta)]])
    shift=rng.uniform(-1500,1500,2)
    q=shift; a=np.array([500.,-100.])@rotation.T+shift; b=np.array([500.,100.])@rotation.T+shift
    p=np.array([[800.,-10.],[1000.,-10.],[1000.,10.],[800.,10.]])@rotation.T+shift
    assert pair_nonreception_certificate(p,q,a,b) is not None
    assert cheap_pair_nonreception_certificate(p,q,a,b) is not None
    for g in p:
        u,v=np.linalg.solve(np.column_stack((g-q,-(b-a))),a-q)
        assert 0<u<1 and 0<v<1
        assert max(np.linalg.norm(g-a),np.linalg.norm(g-b))<np.linalg.norm(g-q)
    certified+=1
result['checks']['full_polygon_negative_prediction']=certified

cuts=0
for i in range(200):
    p=hull(rng.uniform(-2000,2000,(12,2)))
    records=[exclusion_planes(*rng.uniform(-2000,2000,(3,2))) for j in range(12)]
    plain, x=apply_pair_sequence(p,records,False)
    batch, y=apply_pair_sequence(p,records,True)
    assert np.array_equal(plain,batch)
    assert x['cuts']==y['cuts'] and x['inconsistent']==y['inconsistent']
    cuts+=x['cuts']
result['checks']['batch_sequences']={'sequences':200,'cuts':cuts}

for i in range(150):
    n=int(rng.integers(2,24)); entries=rng.uniform(-2000,2000,(n,2)); exits=rng.uniform(-2000,2000,(n,2)); current=rng.uniform(-2000,2000,2)
    assert np.array_equal(arc_route(entries,exits,current),fast_arc_route(entries,exits,current))
    costs=np.linalg.norm(exits[:,None]-entries[None,:],axis=2); start=np.linalg.norm(entries-current,axis=1)
    precedence=rng.uniform(0,50,(n,n)); route=rng.permutation(n); pre=reversal_prefix(route,costs,precedence)
    a,b=sorted(rng.choice(n,2,replace=False)); rr=route.copy(); rr[a:b+1]=rr[a:b+1][::-1]
    predicted=reversal_delta(route,a,b,costs,start,pre)
    actual=route_objective(rr,costs,start,precedence)-route_objective(route,costs,start,precedence)
    assert abs(predicted-actual)<1e-7
result['checks']['directed_route_and_precedence_deltas']=150
result['checks']['q3_ring7_cover_radius_m']=covering_radius(6,1140.)
p=np.array([[10.,0.],[1.,0.],[2.,0.]])
zero=np.zeros((3,3)); origin=np.zeros(2)
free=service_route(p,p,origin,zero,2,'free')
locked=service_route(p,p,origin,zero,2,'locked')
assert not np.array_equal(free,locked)
result['document_counterexample']={'claim':'SERVICE_AWARE_GUARANTEE.md:13 zero weights reuse fast_arc_route; valid only for free mode', 'entries_and_exits':p.tolist(),'station_count':2,'free_route':free.tolist(),'locked_route':locked.tolist(),'free_distance_m':10.,'locked_distance_m':19.}

paths=factory.all_paths()
def signature(e):
    r=e['request']; return (e['path'],r.get('channel'),r.get('position'))
def movement(trace):
    old=(0.,0.); moves=[]
    for e in trace:
        p=e['request'].get('position')
        if p is not None:
            q=(p['x'],p['y'])
            if q!=old: moves.append((old,q))
            old=q
    return moves
def switches(trace):
    channel=1; n=0
    for e in trace:
        if e['path']=='/measure':
            ch=e['request']['channel']; n+=ch!=channel; channel=ch
    return n

families={3:['area_return1_7','range_area7','faithful_area7','deferred_area7'],
          4:['width40_f015_22','range_width015','faithful_width015','deferred_width015','predict8_width015']}
for problem in (3,4):
    for seed in range(42,49):
        scenario=generate(seed,ScenarioConfig(directional_fraction=.5 if problem==4 else 0.))
        if seed==48:
            scenario=Scenario(seed,tuple(Source(i+1,1799.999*math.cos(i*math.pi/8),1799.999*math.sin(i*math.pi/8),1000.,(i*22.5 if problem==4 and i else None)) for i in range(16)))
        traces={}; times={}
        for method in families[problem]:
            sim=Simulator(scenario,ErrorField(seed,ErrorConfig()),Limits(countdown_s=0))
            trace=[]; client=Client(PeerTransport(Protocol(sim)),robot_id='mock-robot',transcript=trace)
            policy=factory.build(client,factory.SPECS[problem][method],problem,paths)
            stats=policy.run()
            assert len(sim.cleared)==len(scenario.sources)
            traces[method]=trace; times[method]=sim.virtual_time_s
            result['runs'].append({'problem':problem,'seed':seed,'method':method,'cleared':len(sim.cleared),'virtual_s':sim.virtual_time_s,'requests':len(trace),'stop_reason':stats['stop_reason'],'inconsistent_updates':stats['inconsistent_updates'], 'skips':stats.get('certified_scan_skips',stats.get('faithful_stationary_skips',stats.get('certified_range_scan_skips',0)))})
        base=traces[families[problem][0]]
        for method in families[problem][2:]:
            new=traces[method]; index=0
            for entry in new:
                while index<len(base) and signature(base[index])!=signature(entry):
                    assert base[index]['path']=='/measure' and base[index]['response']['measure_result']=='no_signal'
                    index+=1
                assert index<len(base)
                assert {k:v for k,v in entry['response'].items() if k in ('measure_result','svd_deg','clear_result')}=={k:v for k,v in base[index]['response'].items() if k in ('measure_result','svd_deg','clear_result')}
                index+=1
            assert index==len(base)
            assert movement(base)==movement(new)
            saving=5*(len(base)-len(new))+switches(base)-switches(new)
            assert abs(times[families[problem][0]]-times[method]-saving)<1e-5
result['checks']['physical_run_count']=len(result['runs'])
result['checks']['deletion_pairs']=35
from policies import Policy
fallbacks=[]
for seed in (42,43):
    scenario=generate(seed,ScenarioConfig(directional_fraction=0.))
    source=scenario.sources[0]
    # Truth selects a reproducible test query; the policy only gets RF replies.
    s=np.array([source.x-999.,source.y])
    sim=Simulator(scenario,ErrorField(seed,ErrorConfig()),Limits(countdown_s=0))
    client=Client(PeerTransport(Protocol(sim)),robot_id='mock-robot')
    p=Policy(client,[],active=False)
    client.enter(); p.measure(s,source.channel)
    assert source.channel in p.regions
    p.complete_source(source.channel)
    assert source.channel in sim.cleared
    assert p.stats['optical_fallback_calls']>0
    fallbacks.append(p.stats['optical_fallback_calls'])
    client.exit()
result['checks']['forced_optical_fallback_attempts']=fallbacks
files=['intelligent.py','policies.py','coupled_dispatch_policy.py','deferred_skip_policy.py','fast_dispatch_policy.py','joint_policy.py','joint_task_policy.py','efficient_joint_policy.py','completion_sensing_policy.py','service_aware_policy.py','cooperative_policy.py','historical_pair_policy.py','batched_history_policy.py','faithful_skip_policy.py','safe_sensing_policy.py','clearance_policy.py','geometry.py','interleaved_policy.py']
result['live_sha256']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files}
out=Path(__file__).with_name('verify-localize-clear.json')
out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result['checks'],ensure_ascii=False,indent=2))
