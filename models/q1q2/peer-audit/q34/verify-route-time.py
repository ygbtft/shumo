"""Read-only peer audit; write evidence only beside this script. Python -B."""
import csv,gzip,hashlib,itertools,json,math,sys
from pathlib import Path
import numpy as np
ROOT=Path('/Users/flower/math/2026/NTJ_B_wt/B')
sys.path.insert(0,str(ROOT))
from route_algorithms import Problem,optimize,two_opt,Budget,order_crossover
from adaptive_routes import remaining_route
OUT=Path(__file__).resolve().parent
result={};rng=np.random.default_rng(42)
p=np.array([[0,0],[1000,0],[999.999995,1000],[2000,0]])
pr=Problem(p);opt=min(pr.cost(np.array((0,)+t)) for t in itertools.permutations(range(1,4)))
result['invalid_lower_bound']={'points':p.tolist(),'bound':pr.lower_bound,'enumerated_optimum':opt,'excess_m':pr.lower_bound-opt}
result['insertion_budget']=optimize(p,'insertion_greedy',budget=2)[1]
for t in range(100):
 points=np.vstack(([0.,0.],rng.normal(size=(7,2))*100));pr=Problem(points)
 a=np.r_[0,rng.permutation(np.arange(1,8))];b=np.r_[0,rng.permutation(np.arange(1,8))]
 pr.validate(order_crossover(a,b,rng));q=two_opt(pr,a,Budget(10000),30);assert pr.cost(q)<=pr.cost(a)+1e-7
 current=rng.normal(size=2)*100;nn=remaining_route(points,current,False);qq=remaining_route(points,current,True)
 cost=lambda a:np.linalg.norm(points[a[0]]-current)+np.linalg.norm(np.diff(points[a],axis=0),axis=1).sum()
 assert cost(qq)<=cost(nn)+1e-7 and sorted(qq)==list(range(8))
result['random_permutation_descent_checks']=100
folder=ROOT/'experiments/runs/2026-09-11_cover21-confirmation'
rows=[r for r in csv.DictReader((folder/'trials.csv').open()) if r['problem']=='3' and r['method']=='range_area7']
details=[];maxerr=0.;count=0
for r in rows:
 path=folder/'traces'/('q3__'+r['case_id']+'__range_area7.jsonl.gz');pos=(0.,0.);ch=1;total_us=0;unrounded=0.;success=0;lastclear=0
 counts={'measure':0,'switch':0,'success':0,'fail':0};movement=0.
 for line in gzip.open(path,'rt'):
  e=json.loads(line);resp=e['response'];assert resp['accepted'];request=e['request'];action=e['path'];count+=1
  if action in ('/measure','/clear'):
   q=(request['position']['x'],request['position']['y']);d=math.dist(pos,q);movement+=d;total_us+=math.floor(d/5*1e6+.5);unrounded+=d/5;pos=q
   if action=='/measure':
    switch=int(request['channel']!=ch);fee=5+switch;ch=request['channel'];counts['measure']+=1;counts['switch']+=switch
   else:
    ok=resp['clear_result']=='success';fee=5 if ok else 3;counts['success' if ok else 'fail']+=1
   total_us+=fee*1000000;unrounded+=fee
   if action=='/clear' and ok:success+=1;lastclear=total_us
  assert total_us==round(resp['virtual_time_s']*1e6),(r['case_id'],total_us,resp)
  maxerr=max(maxerr,abs(unrounded-resp['virtual_time_s']))
 total=total_us/1e6
 assert abs(total-float(r['total_virtual_s']))<1e-9 and success==int(r['cleared']) and abs(total/success-float(r['per_source_s']))<1e-9
 details.append({'case':r['case_id'],'split':r['split'],'total_s':total,'per_source_s':total/success,'post_last_clear_s':(total_us-lastclear)/1e6,'movement_m':movement,**counts})
result['trace_recompute']={'trials':len(rows),'entries':count,'integer_microsecond_mismatches':0,'max_unrounded_residual_s':maxerr,'post_last_clear_positive':sum(d['post_last_clear_s']>1e-6 for d in details)}
result['latest']={s:{'n':sum(r['split']==s for r in rows),'mean_per_source_s':float(np.mean([float(r['per_source_s']) for r in rows if r['split']==s]))} for s in ('ordinary','stress')}
result['cross_batch']=[]
for batch in ('coupled','history','deferred','cover21'):
 f=ROOT/f'experiments/runs/2026-09-11_{batch}-confirmation/trials.csv'
 rr=[r for r in csv.DictReader(f.open()) if r['problem']=='3' and r['method']=='range_area7' and r['split']=='ordinary']
 result['cross_batch'].append({'batch':batch,'n':len(rr),'mean_per_source_s':float(np.mean([float(r['per_source_s']) for r in rr]))})
result['q3_pooled_batches_mean']=sum(v['n']*v['mean_per_source_s'] for v in result['cross_batch'])/sum(v['n'] for v in result['cross_batch'])
files=['route_algorithms.py','adaptive_routes.py','route_ablation.py','route_algorithm_checks.py','metaheuristic_experiments.py','coupled_dispatch_policy.py','completion_sensing_policy.py','joint_task_policy.py','geometry.py','client.py']
result['live_snapshot_hashes']={f:{'live_sha256':hashlib.sha256((ROOT/f).read_bytes()).hexdigest(),'matches_cover21':(ROOT/f).read_bytes()==(folder/'code_snapshot'/f).read_bytes()} for f in files}
(OUT/'route-time-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
(OUT/'route-time-trace-recompute.json').write_text(json.dumps(details,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
p2=np.array([[0,0],[1000,0],[999.9999988,1000],[2000,0]])
pr2=Problem(p2);opt2=min(pr2.cost(np.array((0,)+t)) for t in itertools.permutations(range(1,4)))
_,meta2=optimize(p2,'insertion_greedy')
result['false_optimal_label']={'points':p2.tolist(),'enumerated_optimum_m':opt2,'returned_m':meta2['best_m'],'gap_m':meta2['best_m']-opt2,'certified_optimal':meta2['certified_optimal']}
# Replay three archived cases with feedback only; no simulator or source file is used.
from client import Client
from coupled_dispatch_policy import CoupledCompletionPolicy
cfg=json.loads((folder/'run_config.json').read_text());points=np.array(cfg['paths']['ring7'])
replays=[]
for case in ['uniform__iid__147','edge__adversarial-positive__147','range_transition__n16__positive']:
 trace=[json.loads(line) for line in gzip.open(folder/'traces'/('q3__'+case+'__range_area7.jsonl.gz'),'rt')]
 cursor=[0];max_coordinate_error=[0.]
 def transport(path,raw):
  e=trace[cursor[0]];actual=json.loads(raw);expected=e['request'].copy();assert path==e['path']
  if 'position' in actual:
   a=actual.pop('position');b=expected.pop('position');err=math.hypot(a['x']-b['x'],a['y']-b['y']);max_coordinate_error[0]=max(max_coordinate_error[0],err);assert err<1e-7,(case,cursor[0],err)
  assert actual==expected,(case,cursor[0]);cursor[0]+=1
  return 200,e['response'].copy()
 policy=CoupledCompletionPolicy(Client(transport,robot_id='mock-robot'),points,mixed=False,dispatch_model='base',range_skip=True,area_prior=True,remainder_weight=1.)
 policy.run();assert cursor[0]==len(trace);replays.append({'case':case,'matched_requests':cursor[0],'coordinate_tolerance_m':1e-7,'max_coordinate_error_m':max_coordinate_error[0]})
result['feedback_only_replay']=replays
(OUT/'route-time-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'false_optimal_label':result['false_optimal_label'],'feedback_only_replay':replays},indent=2))
