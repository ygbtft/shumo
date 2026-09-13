"""Optional tests: no production solver/geometry used to construct the truths."""
import math
from types import SimpleNamespace as NS
import pytest
pytest.importorskip('mpmath')
from mpmath import mp
from algorithms.q1q2.optional.certified import certify, assess


def source(a=10., b=100., *, eps=0., theta=0., s=(0., 0.), center=None, radius=None):
    return NS(first=NS(position=s, bearing_deg=theta, half_width_deg=eps),
              physics=NS(arena_center=center if center is not None else ((a+b)/2, 0.),
                         arena_radius=radius if radius is not None else (b-a)/2,
                         rho_hi=1500., near_radius=5.))


@pytest.mark.parametrize('a,b,h,e', [(10,100,20,1), (10,100,20,.5),
                                  (20,80,40,1), (10,100,200,1), (500,1400,20,.01)])
def test_segment_exact(a,b,h,e):
    c = certify(source(a,b), (0.,h), e, tol=.02)
    with mp.workdps(80):
        delta = 2*mp.mpf(e)*mp.pi/180
        exact = b-max(mp.mpf(a), mp.mpf(h)*(b-h*mp.tan(delta))/(h+b*mp.tan(delta)))
        assert mp.mpf(c.lower_m) <= exact <= mp.mpf(c.upper_m)
    assert c.converged and c.gap_m <= .02
    assert assess(float(exact),c,.02) == 'PASS'
    assert assess(c.upper_m+1,c,.02) == 'OVERESTIMATE'
    assert assess(c.lower_m-1,c,.02) == 'UNDERESTIMATE'


@pytest.mark.parametrize('a,b,q,exact,branch', [
    (10,20,(15.,0.),10.,'near'),
    (5,1500,(100.,0.),1395.,'direction'),
    (10,100,(0.,0.),90.,'same_station'),
])
def test_strict_and_closed_edges(a,b,q,exact,branch):
    c = certify(source(a,b), q, tol=.02)
    assert c.lower_m <= exact <= c.upper_m
    assert c.converged and c.witness['branch'] == branch
    # Parameter witnesses (not rounded coordinate midpoints) are authoritative.
    for i in (1,3):
        assert a+c.witness['parameters'][i]*(b-a) > 5


def test_same_station_sector_and_wrap():
    ss=source(eps=.2,center=(0.,0.),radius=1800.)
    c=certify(ss,(0.,0.),.01,tol=.02)
    with mp.workdps(80):
        e=mp.mpf(.2)*mp.pi/180
        exact=max(3000*mp.sin(e),mp.sqrt(1495**2+4*5*1500*mp.sin(e)**2))
        assert c.lower_m <= exact <= c.upper_m
    # Exactly representable 360-degree rotation must give overlapping bounds.
    base=source(eps=1.,center=(0.,0.),radius=1800.)
    wrap=source(eps=1.,theta=360.,center=(0.,0.),radius=1800.)
    x=certify(base,(750.,400.),tol=.1)
    y=certify(wrap,(750.,400.),tol=.1)
    assert x.converged and y.converged
    assert max(x.lower_m,y.lower_m) <= min(x.upper_m,y.upper_m)


def test_budget_preserves_cover_and_dependencies():
    ss=source()
    c=certify(ss,(0.,20.),max_nodes=0,tol=.0001)
    assert not c.converged and c.stop_reason == 'node_budget'
    assert c.lower_m < 15.45951 < c.upper_m
    assert c.status == 'CERTIFIED_BOUNDS'
    # The minimal input NS has no production methods or float angle events.
    assert c.witness is not None


def test_empty_and_invalid():
    with pytest.raises(ValueError,match='NO_VERIFIED_SOURCE'):
        certify(source(center=(-100.,0.),radius=1.),(0.,20.))
    with pytest.raises(ValueError):
        certify(source(),(0.,20.),epsilon2=45.)
    with pytest.raises(ValueError):
        certify(source(),(math.nan,20.))


def test_clipped_arena_outside_first_station():
    # Ray from x=-20 hits disk [-10,10]; F is that segment. Both sources
    # seen from q=-30 have precisely the same bearing, so J=20.
    ss=source(s=(-20.,0.),center=(0.,0.),radius=10.)
    c=certify(ss,(-30.,0.),tol=.02)
    assert c.converged and c.lower_m <= 20 <= c.upper_m
