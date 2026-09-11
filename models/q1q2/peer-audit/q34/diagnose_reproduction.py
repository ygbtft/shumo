import sys,json,gzip,math
from pathlib import Path
import numpy as np
ROOT=Path('/Users/flower/math/2026/NTJ_B_wt/B');sys.path.insert(0,str(ROOT))
from client import Client
import cover21_confirmation as engine
from peer_benchmark import Simulator,Limits,Protocol,PeerTransport,ErrorField,ErrorConfig
from mock.scenario_gen import Source,Scenario
from bounded_width_policy import BoundedWidthPacketPolicy
batch=ROOT/'experiments/runs/2026-09-11_cover21-confirmation'
cfg=json.loads((batch/'run_config.json').read_text());paths={k:np.array(v) for k,v in cfg['paths'].items()}
output=[]
for method,case in [('range_grid21_29','uniform__adversarial-spatial__154'),('range_grid21_29','boundary_outward__n16__negative'),('count_locked_grid21_29','edge__adversarial-negative__152')]:
    data=json.loads((batch/'scenarios_scoring_only'/f'q4__{case}.json').read_text());sc=data['scenario']
    scenario=Scenario(sc['seed'],tuple(Source(**s) for s in sc['sources']),sc['config'])
    old=[json.loads(s) for s in gzip.open(batch/'traces'/f'q4__{case}__{method}.jsonl.gz','rt')]
    sim=Simulator(scenario,ErrorField(sc['seed'],ErrorConfig(**data['error'])),Limits(countdown_s=0))
    engine.build(Client(PeerTransport(Protocol(sim)),robot_id='mock-robot'),cfg['specs']['4'][method],4,paths).run()
    detail={'case':case,'method':method,'recorded_s':old[-1]['response']['virtual_time_s'],'rerun_s':sim.virtual_time_s}
    for i,(a,b) in enumerate(zip(old,sim.trace)):
        if a['request']!=b['request'] and 'first_request_difference' not in detail:
            detail['first_request_difference']={'index':i,'old':a['request'],'new':b['request']}
        ka={k:v for k,v in a['response'].items() if k not in ('real_timestamp_ms','virtual_time_s')}
        kb={k:v for k,v in b['response'].items() if k not in ('real_timestamp_ms','virtual_time_s')}
        if ka!=kb and 'first_physics_difference' not in detail:
            detail['first_physics_difference']={'index':i,'old_request':a['request'],'new_request':b['request'],'old_response':ka,'new_response':kb}
    cursor=[0];probe_details=[]
    original=BoundedWidthPacketPolicy.probes
    def observe(self,ch,step):
        value=original(self,ch,step)
        probe_details.append({'index_next':cursor[0],'ch':ch,'step':step,'current':self.client.position,
            'points':[q.tolist() for q in value[3]],'distances':[float(np.linalg.norm(q-self.client.position)) for q in value[3]]})
        return value
    def replay(path,raw):
        a=old[cursor[0]];b=json.loads(raw)
        assert a['path']==path and a['request'].get('channel')==b.get('channel')
        if 'position' in b:
            delta=math.dist(tuple(a['request']['position'].values()),tuple(b['position'].values()))
            if delta>1e-7:
                detail['replay_divergence']={'index':cursor[0],'delta_m':delta,'old_request':a['request'],'new_request':b,'last_probe':probe_details[-1]}
                raise RuntimeError('macroscopic replay divergence')
        cursor[0]+=1;return 200,a['response']
    BoundedWidthPacketPolicy.probes=observe
    try:engine.build(Client(replay,robot_id='mock-robot'),cfg['specs']['4'][method],4,paths).run()
    except RuntimeError:pass
    finally:BoundedWidthPacketPolicy.probes=original
    output.append(detail)
dest=Path(__file__).parent/'reproduction-diagnosis.json';dest.write_text(json.dumps(output,indent=2)+'\n')
print(json.dumps(output,indent=2))
