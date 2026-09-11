"""Read-only peer audit; no sockets, official requests, or peer-directory writes."""
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
from unittest.mock import patch
from http.client import IncompleteRead

ROOT = Path('/Users/flower/math/2026/NTJ_B_wt/B')
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import client
from simulator import World, Source, Protocol

result = {'official_requests': 0, 'network_requests': 0}
class BrokenResponse:
    status = 200
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self): raise IncompleteRead(b'{"accepted":true,', 100)
with patch.object(client, 'urlopen', return_value=BrokenResponse()) as opener:
    try:
        client.HttpTransport('http://127.0.0.1:2026')('/measure', b'{}')
    except Exception as exc:
        result['truncated_response'] = {'exception': type(exc).__name__, 'attempts': opener.call_count, 'configured_attempts': 3}

# Restarting a Client in the same session silently replays the old enter response.
w = World([Source(1, 0., 0.)]); transport = Protocol(w).dispatch
a = client.Client(transport); a.enter(); a.measure((100., 0.), 2)
b = client.Client(transport); r = b.enter()
result['same_session_restart'] = {'accepted': r['accepted'], 'client_position': b.position,
    'server_position': w.position, 'client_virtual_s': b.virtual_s, 'server_virtual_s': w.time_us / 1e6}

class LostResponse:
    def __init__(self):
        self.world = World([Source(1, 0., 0.)]); self.protocol = Protocol(self.world)
        self.bodies = []
    def __call__(self, request, timeout):
        self.bodies.append(request.data)
        status, body = self.protocol.dispatch('/enter', request.data)
        if len(self.bodies) == 1: raise ConnectionResetError('accepted but response lost')
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return json.dumps(body).encode()
        response = Response(); response.status = status
        return response
lost = LostResponse()
with patch.object(client, 'urlopen', side_effect=lost), patch.object(client.time, 'sleep'):
    client.Client(client.HttpTransport('http://localhost:2026')).enter()
result['supported_retry'] = {'attempts': len(lost.bodies), 'same_bytes': lost.bodies[0] == lost.bodies[1], 'executed_actions': lost.world.commands}

result['batches'] = {}
for name in ['history-confirmation', 'deferred-confirmation', 'cover21-confirmation']:
    p = ROOT / 'experiments/runs' / ('2026-09-11_' + name)
    cfg = json.loads((p/'run_config.json').read_text())
    rows = [json.loads(s) for s in (p/'trials.jsonl').read_text().splitlines()]
    bad_snapshot = [f for f,h in cfg['code_sha256'].items() if hashlib.sha256((p/'code_snapshot'/f).read_bytes()).hexdigest() != h]
    live_differences = [f for f,h in cfg['code_sha256'].items() if not (ROOT/f).exists() or hashlib.sha256((ROOT/f).read_bytes()).hexdigest() != h]
    errors = []
    for s in csv.DictReader((p/'summary.csv').open()):
        group = [r for r in rows if r['problem']==int(s['problem']) and r['method']==s['method'] and r['split']==s['split']]
        mean = sum(r['per_source_s'] for r in group)/len(group)
        if abs(mean-float(s['mean_per_source_s']))>1e-8: errors.append(s['method'])
    result['batches'][name] = {'rows':len(rows), 'unique_problem_case_pairs':len({(r['problem'],r['case_id']) for r in rows}),
        'all_cleared':sum(r['all_cleared'] for r in rows), 'failures':sum(bool(r['failure']) for r in rows),
        'snapshot_mismatches':bad_snapshot,'live_differences':live_differences,'summary_mean_mismatches':errors,
        'official_calls_config':cfg['official_calls'],'log_tail':(p/'log.txt').read_text().splitlines()[-1]}
    if name=='cover21-confirmation': latest, config, batch = rows,cfg,p

# Independent physics and integer-microsecond accounting on all latest traces.
# Recompute reception predicate/bearing residual without calling either simulator.
violations=[]; commands=0; max_angle=0.
for row in latest:
    prefix=f"q{row['problem']}__{row['case_id']}"
    truth=json.loads((batch/'scenarios_scoring_only'/f'{prefix}.json').read_text())['scenario']
    sources={s['channel']:s for s in truth['sources']}; cleared=set(); pos=(0.,0.); channel=1; us=0
    path=batch/'traces'/f"{prefix}__{row['method']}.jsonl.gz"
    entries=[json.loads(s) for s in gzip.open(path,'rt')]
    for e in entries:
        commands+=1; req,resp=e['request'],e['response']; endpoint=e['path']
        assert resp['accepted'] is True
        if endpoint in ('/measure','/clear'):
            q=(req['position']['x'],req['position']['y']); ch=req['channel']
            us+=round(math.dist(pos,q)/5*1e6); pos=q
            s=sources.get(ch); alive=s is not None and ch not in cleared
            distance=math.dist(q,(s['x'],s['y'])) if alive else math.inf
            if endpoint=='/clear':
                success=alive and distance<=20.; us+=(5 if success else 3)*1000000
                if success: cleared.add(ch)
                assert resp['clear_result']==('success' if success else 'no_target_in_range')
            else:
                us+=(5+int(ch!=channel))*1000000; channel=ch
                face=True
                if alive and s['direction_deg'] is not None:
                    theta=math.radians(s['direction_deg'])
                    face=(q[0]-s['x'])*math.cos(theta)+(q[1]-s['y'])*math.sin(theta)>=-1e-8
                expected='no_signal' if not alive or distance>s['radius']+1e-9 or not face else 'near' if distance<=5 else 'direction'
                assert resp['measure_result']==expected, (prefix,row['method'],e)
                if expected=='direction':
                    angle=math.degrees(math.atan2(s['y']-q[1],s['x']-q[0]))%360
                    residual=abs((resp['svd_deg']-angle+180)%360-180)
                    max_angle=max(max_angle,residual); assert residual<=1.00500001
        assert round(resp['virtual_time_s']*1e6)==us
    assert len(entries)==row['commands'] and len(cleared)==row['cleared']
    assert round(row['total_virtual_s']*1e6)==us and set(sources)==cleared
result['latest_independent_trace_check']={'traces':len(latest),'commands':commands,'violations':violations,'max_bearing_residual_deg':max_angle}

import numpy as np
import cover21_confirmation as engine
from peer_benchmark import Simulator, Limits, Protocol as PeerProtocol, PeerTransport, ErrorConfig, ErrorField
from mock.scenario_gen import Scenario, Source as PeerSource
paths={k:np.array(v) for k,v in config['paths'].items()}
result['live_reruns']=[]
for problem,method in [(3,'range_area7'),(4,'range_grid21_29'),(4,'count_locked_grid21_29')]:
    for split in ('ordinary','stress'):
        group=[r for r in latest if r['problem']==problem and r['method']==method and r['split']==split]
        row=max(group,key=lambda r:r['total_virtual_s'])
        prefix=f"q{problem}__{row['case_id']}"
        data=json.loads((batch/'scenarios_scoring_only'/f'{prefix}.json').read_text())
        sc=data['scenario']; scenario=Scenario(sc['seed'],tuple(PeerSource(**s) for s in sc['sources']),sc['config'])
        sim=Simulator(scenario,ErrorField(sc['seed'],ErrorConfig(**data['error'])),Limits(countdown_s=0))
        policy=engine.build(client.Client(PeerTransport(PeerProtocol(sim)),robot_id='mock-robot'),config['specs'][str(problem)][method],problem,paths)
        stats=policy.run()
        old=[json.loads(s) for s in gzip.open(batch/'traces'/f'{prefix}__{method}.jsonl.gz','rt')]
        same=len(old)==len(sim.trace) and all(x['path']==y['path'] and x['request']==y['request'] and
            {k:v for k,v in x['response'].items() if k!='real_timestamp_ms'}=={k:v for k,v in y['response'].items() if k!='real_timestamp_ms'} for x,y in zip(old,sim.trace))
        # Policy replay receives only saved responses and requests, with no truth transport.
        cursor=[0]; replay_deltas=[]; replay_errors=[]
        def feedback_only(path, raw):
            e=old[cursor[0]]; request=json.loads(raw)
            assert e['path']==path
            for k in ('arena_id','robot_id','request_id','channel'):
                assert e['request'].get(k)==request.get(k), (cursor[0], k)
            if 'position' in request:
                delta=math.dist(tuple(e['request']['position'].values()),tuple(request['position'].values()))
                replay_deltas.append(delta)
                assert delta<1e-7, (cursor[0], delta)
            cursor[0]+=1; return 200,e['response']
        try:
            engine.build(client.Client(feedback_only,robot_id='mock-robot'),config['specs'][str(problem)][method],problem,paths).run()
        except Exception as exc: replay_errors.append(repr(exc))
        result['live_reruns'].append({'problem':problem,'method':method,'split':split,'case_id':row['case_id'],
            'class_mro':[c.__name__ for c in type(policy).__mro__], 'stations':len(policy.stations),
            'virtual_s':sim.virtual_time_s,'recorded_virtual_s':row['total_virtual_s'],'actions_equal':same,
            'all_cleared':len(sim.cleared)==len(scenario.sources),'feedback_only_replayed':cursor[0]==len(old),
            'feedback_max_position_delta_m':max(replay_deltas,default=0.),'feedback_errors':replay_errors})

result['latest_metrics']=[]
for problem,method in [(3,'range_area7'),(4,'range_convex22'),(4,'range_grid21_29'),(4,'count_locked_grid21_29')]:
    for split in ('ordinary','stress'):
        group=[r for r in latest if r['problem']==problem and r['method']==method and r['split']==split]
        result['latest_metrics'].append({'problem':problem,'method':method,'split':split,'n':len(group),
            'mean_per_source_s':np.mean([r['per_source_s'] for r in group]),'p95_total_s':np.quantile([r['total_virtual_s'] for r in group],.95),
            'max_total_s':max(r['total_virtual_s'] for r in group),'mean_commands':np.mean([r['commands'] for r in group])})
result['paired']=[]
for method,base in [('range_grid21_29','range_convex22'),('count_locked_grid21_29','range_grid21_29')]:
    a={r['case_id']:r for r in latest if r['problem']==4 and r['method']==method}
    b={r['case_id']:r for r in latest if r['problem']==4 and r['method']==base}
    delta=[a[k]['total_virtual_s']-b[k]['total_virtual_s'] for k in a]
    result['paired'].append({'method':method,'base':base,'slower':sum(d>1e-6 for d in delta),'max_regression_s':max(delta)})
(OUT/'verification-overall.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
