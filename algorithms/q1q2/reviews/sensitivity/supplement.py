"""Postprocess saved search candidates; bounded S7 station and S3 consistency audits."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import time
import numpy as np
from algorithms.q1q2 import sensitivity as s
from algorithms.q1q2.geometry import BearingMeasurement, NumericPolicy, distance
from algorithms.q1q2.feasible import PhysicsConfig, build_source_set, check_candidate
from algorithms.q1q2.q2 import SearchConfig, check_admissibility, score_point
from algorithms.q1q2.run import write_json

folder = Path(sys.argv[1])
raw = json.loads((folder/'standard_default.json').read_text())
cfgdata = raw['config']
cfgdata['policy'] = NumericPolicy(**cfgdata['policy'])
cfg = SearchConfig(**cfgdata)
ss = build_source_set(BearingMeasurement((0., 0.), 0.), PhysicsConfig(), cfg.policy)
started = time.monotonic()
old = tuple(raw['reselected']['q'])
qs, stages = [old], []
for step in (50., 25.):
    rows = [r for r in raw['search']['grid_records'] if r['step_m'] == step and r['diameter_estimate_m'] is not None
            and tuple(r['q']) != ss.first.position and check_admissibility(ss, r['q'], cfg)['status'] == 'IN']
    if rows:
        q = tuple(min(rows, key=lambda r: (r['diameter_estimate_m'], distance(r['q'], ss.first.position)))['q'])
        qs.append(q)
        stages.append(dict(stage=f'grid_{step:g}', q=q, coarse_J=next(r['diameter_estimate_m'] for r in rows if tuple(r['q'])==q)))
local = next((r['positions'] for r in raw['search']['refinement_history'] if r['stage'] == 'shifted_station_audit'), [])
medium = s.samples(ss, cfg, level=1)
local_scored = [(tuple(q), score_point(ss, q, medium, replace(cfg, refine_pairs=False)))
                for q in local if check_admissibility(ss, q, cfg)['status'] == 'IN']
if local_scored:
    q = min(local_scored, key=lambda row: row[1].J_hat)[0]
    qs.append(q)
    stages.append(dict(stage='local_and_shifted_station', q=q))
rows, pool, cost = s.common_evaluation(ss, cfg, qs)
lookup = {r['q']:r for r in rows}
for stage in stages:
    stage['uniform_final'] = lookup[stage['q']]
new = s.choose(rows, ss, cfg.tie_floor_m)
values = [stage['uniform_final']['score'].J_hat for stage in stages]
grid_stages=[r for r in stages if 'coarse_J' in r]
rank_inversions=sum((a['coarse_J']-b['coarse_J'])*(a['uniform_final']['score'].J_hat-b['uniform_final']['score'].J_hat)<0 for i,a in enumerate(grid_stages) for b in grid_stages[i+1:])
write_json(folder/'S7_station.json', dict(rank_inversions=rank_inversions, stages=stages, fixed_old=lookup[old], reselected=new,
    delta_station_m=max(values)-min(values) if len(values)>1 else None,
    local_screen_score_calls=len(local_scored), accounting=cost,
    scan=raw['scan'], elapsed_seconds=time.monotonic()-started,
    stop_reason='SAVED_STAGES_REASSESSED',
    limitation='raw search may have stopped during finalist audit; stage comparison is finite, not certified'))
# Extra information can contradict the accepted first signal; do not score an empty F.
first = BearingMeasurement((2900.,0.),180.)
models = {str(rho):build_source_set(first, PhysicsConfig(rho_lo=rho, rho_hi=rho), cfg.policy) for rho in (1000.,1250.,1500.)}
write_json(folder/'S3_inconsistent.json', dict(first=first, known_radius_models=models,
    interpretation='known rho=1000 unavailable: nearest arena source is 1100 m away; no optimization or J comparison',
    score_calls=0))
# Report losses on the identical saved candidate population, not unequal partial scans.
edge = json.loads((folder/'edge_default.json').read_text())
first = BearingMeasurement(tuple(edge['source_set']['first']['position']),edge['source_set']['first']['bearing_deg'])
model = build_source_set(first, PhysicsConfig(), cfg.policy)
probe = {tuple(r['q']) for r in edge['search']['alternatives']}
probe.add(first.position)
valid = [q for q in probe if check_admissibility(model,q,cfg)['status']=='IN']
rejected = [q for q in valid if check_admissibility(model,q,replace(cfg,restrict_action_to_arena=True))['status']!='IN']
write_json(folder/'S4_losses.json',dict(population='saved default alternatives plus S; finite sample, not area ratio',
    default_admissible_count=len(valid), added_arena_rejected_count=len(rejected),
    rejected_points=rejected, S_excluded=first.position in rejected, score_calls=0))
print('supplement complete', flush=True)
