"""Run from a tree containing models/q1q2 and mock, before or after the P2 patch."""
import json
import math
import time
from dataclasses import replace
import numpy as np
from models.q1q2.geometry import BearingMeasurement, HalfPlane, NumericPolicy, intersect_halfplanes
from models.q1q2.feasible import PhysicsConfig, Feedback, build_source_set, check_candidate, closure_distance, posterior_contains
from models.q1q2.q2 import SearchConfig, SourceSamples, score_point, _sample_sources, select_second_point, Q2Result, _conditional_diagnostics
from models.q1q2.diagnostics import clearance_summary
from models.q1q2.run import q2_bundle, q1_bundle
from models.q1q2.plots import ResultBundle, PlotStyle, render
import matplotlib.pyplot as plt
import tempfile
p = NumericPolicy()
h = [HalfPlane((1, 0), 0), HalfPlane((1, 0), 0), HalfPlane((0, 1), 0), HalfPlane((-1, 0), -1)]
r = intersect_halfplanes(h, p)
out = {'G1': {'indices': r.conflict_constraints, 'subset_kind': intersect_halfplanes([h[i] for i in r.conflict_constraints], p).kind.value}}
first = BearingMeasurement((0, 0), 0)
clipped = build_source_set(first, PhysicsConfig(arena_center=(1000, 0), arena_radius=1), p)
out['F1'] = {'reported': check_candidate(clipped, (0, 0), True, p).distance_to_closure, 'actual': closure_distance(clipped, (0, 0))[0]}
ss = build_source_set(first, PhysicsConfig(), p)
cloud = SourceSamples(((1000., 0.), (1500., 0.)), 0, (2, 2))
clear = clearance_summary(ss, (0, 0), Feedback('near'), cloud, p)
out['D1'] = {'status': clear.status, 'seconds': clear.subsequent_total_seconds}
q = (-1e-10, 0)
w = score_point(ss, q, cloud, SearchConfig()).witness
out['Q2-1'] = {'status': check_candidate(ss, q, False, p).status, 'legal': w.actual_legal, 'worlds': w.worlds}
shifted = build_source_set(BearingMeasurement((1000, 0), 0), PhysicsConfig(), p)
a, b = [_sample_sources(shifted, k, ((4, 4), (5, 5), (6, 6))) for k in (0, 1)]
out['Q2-2'] = {'counts': [len(a.points), len(b.points)], 'lost': len(set(a.points)-set(b.points))}
out['Q2-4'] = []
for budget in (.001, .01):
 t = time.monotonic(); result = select_second_point(ss, SearchConfig(source_grids=((2, 2),)*3, time_budget_s=budget))
 out['Q2-4'].append({'budget': budget, 'elapsed': time.monotonic()-t, 'stop': result.stop_reason})
before = set(plt.get_fignums())
with tempfile.TemporaryDirectory() as dest:
 try:
  render(ResultBundle(figures=({'id': 'bad', 'kind': 'bad'},)), dest, PlotStyle(font_family='DejaVu Sans'))
 except ValueError:
  pass
out['PLOT1'] = {'leaked': len(set(plt.get_fignums())-before)}
plt.close('all')
q = (100, 0)
cfg = SearchConfig(source_grids=((3, 4),)*3, pair_rounds=0)
samples = _sample_sources(ss, 0, cfg.source_grids, q)
score = score_point(ss, q, samples, cfg)
clear, angular = _conditional_diagnostics(ss, q, score, samples, cfg)
r = Q2Result(q, check_candidate(ss, q, False, p), score, 100, 20, 5, config=cfg, clearance_diagnostics=clear, angular_comparison=angular)
figures = q2_bundle(ss, r).figures
out['R1'] = [{'feedback': c.feedback.kind, 'lines': [posterior_contains(ss, q, c.feedback, line['values'], p).tolist() for line in f['panels'][0].get('lines', ())]} for f, c in zip([f for f in figures if f['id'].startswith('F7')], clear)]
wide = build_source_set(replace(first, half_width_deg=2.), PhysicsConfig(), p)
figures = q2_bundle(wide, replace(r, config=replace(cfg, second_half_width_deg=2.), clearance_diagnostics=(), angular_comparison=())).figures
f8 = next(f for f in figures if f['id'] == 'F8')
a, b = np.asarray(wide.actual_point), np.asarray(wide.actual_point)-(750, 10)
expected = 4*np.linalg.norm(a)*np.linalg.norm(b)*math.radians(2)**2/abs((a[0]*b[1]-a[1]*b[0])/(np.linalg.norm(a)*np.linalg.norm(b)))
out['R2'] = {'linear_area': f8['series'][0]['y'][0], 'expected': expected, 'ratio': f8['series'][0]['y'][0]/expected}
out['R3'] = q1_bundle({}).tables['T3']
print(json.dumps(out, indent=2))
