"""Re-run the two current main candidates on saved truth, without peer writes."""
import sys,json,time
from pathlib import Path
import numpy as np
ROOT=Path('/Users/flower/math/2026/NTJ_B_wt/B');sys.path.insert(0,str(ROOT))
from client import Client
import cover21_confirmation as engine
from peer_benchmark import Simulator,Limits,Protocol,PeerTransport,ErrorField,ErrorConfig
from mock.scenario_gen import Source,Scenario
batch=ROOT/'experiments/runs/2026-09-11_cover21-confirmation'
cfg=json.loads((batch/'run_config.json').read_text());paths={k:np.array(v) for k,v in cfg['paths'].items()}
rows=[json.loads(s) for s in (batch/'trials.jsonl').read_text().splitlines()]
results=[];began=time.perf_counter()
for problem,method in [(3,'range_area7'),(4,'range_grid21_29')]:
    for row in rows:
        if row['problem']!=problem or row['method']!=method:continue
        case=row['case_id'];data=json.loads((batch/'scenarios_scoring_only'/f'q{problem}__{case}.json').read_text());sc=data['scenario']
        scenario=Scenario(sc['seed'],tuple(Source(**s) for s in sc['sources']),sc['config'])
        sim=Simulator(scenario,ErrorField(sc['seed'],ErrorConfig(**data['error'])),Limits(countdown_s=0))
        stats=engine.build(Client(PeerTransport(Protocol(sim)),robot_id='mock-robot'),cfg['specs'][str(problem)][method],problem,paths).run()
        results.append({'problem':problem,'method':method,'case_id':case,'split':row['split'],
            'all_cleared':len(sim.cleared)==len(scenario.sources),'commands':len(sim.trace),'recorded_commands':row['commands'],
            'virtual_s':sim.virtual_time_s,'recorded_s':row['total_virtual_s'],'per_source_s':sim.virtual_time_s/len(sim.cleared),
            'recorded_per_source_s':row['per_source_s']})
summary=[]
for problem in (3,4):
    for split in ('ordinary','stress'):
        group=[r for r in results if r['problem']==problem and r['split']==split]
        delta=[r['virtual_s']-r['recorded_s'] for r in group]
        summary.append({'problem':problem,'split':split,'n':len(group),'all_cleared':sum(r['all_cleared'] for r in group),
            'recorded_mean_per_source_s':float(np.mean([r['recorded_per_source_s'] for r in group])),
            'rerun_mean_per_source_s':float(np.mean([r['per_source_s'] for r in group])),
            'different_virtual_time_cases':sum(abs(d)>1e-6 for d in delta),'max_abs_total_delta_s':max(map(abs,delta)),
            'rerun_p95_total_s':float(np.quantile([r['virtual_s'] for r in group],.95)),
            'rerun_max_total_s':max(r['virtual_s'] for r in group)})
out={'python':sys.version,'numpy':np.__version__,'seconds':time.perf_counter()-began,'official_calls':0,'summary':summary,'trials':results}
(Path(__file__).parent/'main-reproduction.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(summary,indent=2))
