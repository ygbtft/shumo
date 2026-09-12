"""Independent direct-angle extremizer checks for the added budget bounds.

Supplemental to the unchanged 48-case suite. The oracle constructs the station
where the angle is maximized and evaluates its two bearings, without calling
production angle helpers to construct the expected angle.
"""
import argparse
import json
import math
from pathlib import Path
from ...geometry import BearingMeasurement, NumericPolicy
from ...feasible import PhysicsConfig, build_source_set
from ...q2 import (short_baseline_lower_bound, tight_short_baseline_lower_bound,
                  source_pair_budget_lower_bound)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    ss = build_source_set(BearingMeasurement((0, 0), 0), PhysicsConfig(), NumericPolicy())
    rows = []
    for budget in (0, 5, 10, 13, 15, 20, 25, 26, 26.15, 26.151, 30, 100):
        t = 2000*budget**2/(750000+budget**2)
        z = math.sqrt(max(0, budget**2-t*t))
        angle = math.degrees(math.atan2(-z, 1500-t)-math.atan2(-z, 500-t))
        old = short_baseline_lower_bound(ss, 500, 1500, budget)
        new = tight_short_baseline_lower_bound(ss, 500, 1500, budget)
        passed = (new is not None) == (angle <= 2)
        if new is not None:
            passed &= abs(new['angle_bound_deg']-angle) <= 2e-13 and new['lower_bound_m'] == 1000
        if old is not None:
            passed &= new is not None and new['angle_bound_deg'] <= old['angle_bound_deg']
        rows.append(dict(budget_m=budget, old=old, new=new, expected_max_angle_deg=angle, passed=bool(passed), truth_method='direct_bearings_at_analytic_extremizing_station'))
    for gamma in (-.4, -.2, .2, .4):
        x, y = (500., 0.), (1499*math.cos(math.radians(gamma)), 1499*math.sin(math.radians(gamma)))
        bound = source_pair_budget_lower_bound(ss, x, y, 10)
        rows.append(dict(initial_angle_deg=gamma, actual=bound, passed=bound is not None and abs(bound['lower_bound_m']-math.sqrt(500**2+1499**2-2*500*1499*math.cos(math.radians(gamma)))) < 1e-10, truth_method='law_of_cosines_and_angular_triangle_inequality'))
    report = dict(n_cases=len(rows), n_pass=sum(r['passed'] for r in rows), results=rows)
    args.report.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'results'}))
    return int(report['n_pass'] != report['n_cases'])


if __name__ == '__main__':
    raise SystemExit(main())
