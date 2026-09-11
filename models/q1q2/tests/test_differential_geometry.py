"""Frozen independent truths from the 2026091107 peer audit, before repair.

All 195 minimal geometry WRONG cases plus the three isolated diameter failures.
No peer implementation is imported, and no audit artifacts are rewritten.
"""
import json
import math
from fractions import Fraction
from pathlib import Path
import pytest
from models.q1q2.geometry import (BearingMeasurement, HalfPlane, NumericPolicy,
    Region, RegionKind, convex_hull, diameter, intersect_halfplanes, wedge_halfplanes)

CASES = json.loads((Path(__file__).parent/'data/q1_differential_geometry.json').read_text())
POLICY = NumericPolicy()

@pytest.mark.parametrize('case', CASES, ids=lambda c:c['case_id'])
def test_original_differential_wrong(case):
    inp, truth, tol = case['input'], case['oracle'], case['tolerance']
    if 'points' in inp:
        v = convex_hull(inp['points'], POLICY)
        region = Region(RegionKind.POLYGON, v)
    else:
        hps = ([hp for o in inp['observations']
                for hp in wedge_halfplanes(BearingMeasurement(**o))]
               if 'observations' in inp else
               [HalfPlane(tuple(r[:2]), r[2]) for r in inp['halfplanes']])
        region = intersect_halfplanes(hps, POLICY)
    # These particular saved cases are representable; require an actual answer.
    assert region.status == 'OK'
    result = diameter(region, POLICY)
    assert result.status == 'OK'
    assert abs(result.length-truth['diameter']) <= tol
    if 'kind' in truth:
        assert region.kind.value == truth['kind']
        expected = [tuple(float(Fraction(x)) for x in v) for v in truth['vertices']]
        for actual, reference in ((region.vertices, expected), (expected, region.vertices)):
            assert max(min(math.dist(a,b) for b in reference) for a in actual) <= tol

@pytest.mark.parametrize('scale', [1., 1e-12, 1e-100])
def test_exact_gap_and_dimension_at_every_scale(scale):
    box = [HalfPlane((1,0),scale), HalfPlane((-1,0),0),
           HalfPlane((0,1),scale), HalfPlane((0,-1),0)]
    assert intersect_halfplanes(box, POLICY).kind == RegionKind.POLYGON
    assert intersect_halfplanes(box+[HalfPlane((1,0),-scale)], POLICY).kind == RegionKind.EMPTY
    segment = box+[HalfPlane((0,1),0)]
    assert intersect_halfplanes(segment, POLICY).kind == RegionKind.SEGMENT
    assert intersect_halfplanes(segment+[HalfPlane((1,0),0)], POLICY).kind == RegionKind.POINT


def test_underflowing_squared_diameter_is_unresolved():
    r = Region(RegionKind.SEGMENT, ((0.,0.), (1e-200,0.)))
    assert diameter(r,POLICY).status == 'NUMERICAL_UNRESOLVED'


def test_trig_precision_limit_does_not_collapse_positive_width():
    obs = [BearingMeasurement((0.,0.),45.,1e-100),
           BearingMeasurement((1.,1.),225.,1e-100)]
    r = intersect_halfplanes([h for o in obs for h in wedge_halfplanes(o)], POLICY)
    assert r.status == 'NUMERICAL_UNRESOLVED'
    assert r.kind is None


def test_raw_angle_metadata_does_not_override_measurement():
    a = BearingMeasurement((0.,0.),90.,raw_bearing_deg=0.)
    assert wedge_halfplanes(a) == wedge_halfplanes(BearingMeasurement((0.,0.),90.))
