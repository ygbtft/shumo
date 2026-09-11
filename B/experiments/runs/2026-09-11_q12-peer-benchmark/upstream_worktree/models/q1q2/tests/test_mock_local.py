"""Synthetic local observation tests; never invoke an official backend."""
import math
import pytest
from models.q1q2.geometry import BearingMeasurement, NumericPolicy
from models.q1q2.feasible import build_source_set, PhysicsConfig, check_candidate
from models.q1q2.adapters import ObservationRecord, ErrorMode, observations_to_bearings
from models.q1q2.q1 import solve


@pytest.mark.parametrize('error',[-1.,0.,1.])
@pytest.mark.parametrize('source',[(500.,0.),(1000.,1.),(1490.,-1.),(5.001,0.)])
def test_synthetic_nearest_rounding_contains_truth(source,error):
    stations = [(0.,0.),(750.,400.)]
    rows = []
    for i,s in enumerate(stations):
        if math.dist(s,source) <= 5:
            continue
        angle = (math.degrees(math.atan2(source[1]-s[1],source[0]-s[0]))+error)%360
        rounded = (math.floor(angle*100+.5)/100)%360
        rows.append(ObservationRecord('/measure',s,1,{'accepted':True,'measure_result':'direction','svd_deg':rounded},
                                      str(i),'synthetic',stability_id='frozen'))
    observations = observations_to_bearings(rows,1,ErrorMode.NEAREST_ROUNDING_OUTER_1_005_DEG)
    result = solve(observations,NumericPolicy())
    assert result.region.kind is not None
    for obs in observations:
        true = math.degrees(math.atan2(source[1]-obs.position[1],source[0]-obs.position[0]))
        assert abs((true-obs.bearing_deg+180)%360-180) <= obs.half_width_deg


def test_guaranteed_candidate_all_synthetic_radii_and_virtual_cost():
    ss = build_source_set(BearingMeasurement((0,0),0),PhysicsConfig(),NumericPolicy())
    q = (750,400)
    assert check_candidate(ss,q,False,NumericPolicy()).status == 'IN'
    for r in (5.001,500,1000,1500):
        for angle in (-.999,0,.999):
            p = (r*math.cos(math.radians(angle)),r*math.sin(math.radians(angle)))
            for rho in (max(1000,r),1500):
                assert math.dist(p,q) <= rho
    assert math.dist((0,0),q)/5+5 == pytest.approx(175.)
