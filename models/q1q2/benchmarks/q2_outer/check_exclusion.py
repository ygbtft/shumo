"""Independent artifact verifier: no imports of outer_exclusion/search predicates.

Completing the square, exact sweep coverage, 60-digit interval membership,
and a fresh call of the existing fixed-q certifier form the trusted check.
All checks raise ValueError (also under python -O); artifact assertions are never
used as proof. JSON float inputs are interpreted as exact binary64 values.
"""
from collections import Counter
from dataclasses import asdict
from fractions import Fraction as F
from functools import lru_cache
import math

from mpmath.ctx_iv import MPIntervalContext
from ...optional.certified import certify
from ...geometry import BearingMeasurement, NumericPolicy
from ...feasible import PhysicsConfig, build_source_set


def require(condition, message):
    if not condition:
        raise ValueError(message)


def distance2(center, box):
    return sum((lo-v if v < lo else v-hi if v > hi else F(0))**2
               for v, lo, hi in zip(center, box[::2], box[1::2]))


def minimum(k, b, c, box):
    """Independent completed-square formula, not the search's clipped evaluate."""
    return k*distance2(tuple(-v/(2*k) for v in b), box)+c-sum(v*v for v in b)/(4*k)


def coverage(boxes):
    require(bool(boxes), 'empty partition')
    for b in boxes:
        require(0 <= b[0] < b[1] <= 1005 and 0 <= b[2] < b[3] <= 1000,
                'box outside root or degenerate')
    # Sweep all exact x events. Check each open slab's closed y partition.
    # Finitely many closed rectangles also cover all slab boundary lines.
    events = {}
    for i, b in enumerate(boxes):
        events.setdefault(b[0], [[], []])[0].append(i)
        events.setdefault(b[1], [[], []])[1].append(i)
    xs = sorted(events)
    require(xs[0] == 0 and xs[-1] == 1005, 'x coverage gap')
    active = set()
    for x in xs[:-1]:
        entering, exiting = events[x]
        active.difference_update(exiting)
        active.update(entering)
        ys = sorted((boxes[i][2], boxes[i][3]) for i in active)
        require(bool(ys) and ys[0][0] == 0 and ys[-1][1] == 1000, 'y coverage gap')
        require(all(a[1] == b[0] for a, b in zip(ys, ys[1:])), 'gap or positive-area overlap')
    area = sum((b[1]-b[0])*(b[3]-b[2]) for b in boxes)
    require(area == 1005000, 'wrong area')
    return dict(x_slabs=len(xs)-1, area_exact=str(area))


def verify(data):
    require(data['schema'] == 'q2-outer-exclusion-v1', 'unsupported schema')
    require(data['model'] == 'standard-S0-theta0-eps1-rho1000-1500-near5-arena1800-v1', 'unsupported model')
    require(tuple(map(F, data['root'])) == (0, 1005, 0, 1000)
            and data['reflected_y'] is True, 'unsupported root/symmetry')
    iv = MPIntervalContext(); iv.dps = 60
    V = iv.mpf
    def rational(v):
        v = F(v)
        return V(v.numerator)/V(v.denominator)
    sn, cs = iv.sin(iv.pi/180), iv.cos(iv.pi/180)
    k, target, tau = (F(data[key]) for key in ('k', 'target', 'tau'))
    require(k > 0 and rational(k).b < iv.tan(iv.pi/90).a, 'invalid tangent lower bound')
    require(tau > 0 and target >= 0, 'invalid target')
    @lru_cache(maxsize=None)
    def legal(p):
        require(len(p) == 2 and all(math.isfinite(v) for v in p), 'nonfinite source')
        x, y = map(V, p)
        rad = x*x+y*y
        require(rad.a > 25 and rad.b <= 2250000 and x.a > 0
                and (sn*x-cs*y).a >= 0 and (sn*x+cs*y).a >= 0, 'illegal actual source')
    counts = Counter()
    min_d2 = None
    boxes = []
    for i, leaf in enumerate(data['leaves']):
        box = tuple(map(F, leaf['box']))
        require(len(box) == 4, 'box must have four coordinates')
        boxes.append(box)
        kind = leaf['kind']; counts[kind] += 1
        if kind == 'disk':
            index = leaf['disk']
            require(type(index) is int and 0 <= index < 4, 'invalid disk index')
            r, sign = (5, 1000)[index//2], (-1, 1)[index % 2]
            center = (r*cs, sign*r*sn)
            # Interval lower distance to the entire rectangle, never center-only.
            d2 = V(0)
            for j, v in enumerate(center):
                dl = rational(box[2*j])-v
                dh = v-rational(box[2*j+1])
                dist = max(V(0), dl.a, dh.a)
                d2 += dist**2
            require(d2.a > 1000000, f'leaf {i}: disk does not exclude whole box')
        elif kind == 'pair':
            legal(tuple(leaf['x'])); legal(tuple(leaf['y']))
            x, y = tuple(map(F, leaf['x'])), tuple(map(F, leaf['y']))
            d2 = sum((a-b)**2 for a, b in zip(x, y))
            require(F(leaf['lower']) == target and d2 >= target**2, 'insufficient pair length')
            min_d2 = d2 if min_d2 is None else min(d2, min_d2)
            dot = sum(a*b for a, b in zip(x, y)); b = tuple(-a-v for a, v in zip(x, y))
            require(minimum(F(1), b, dot, box) >= 0, 'negative dot minimum')
            require(all(distance2(p, box) > 25 for p in (x, y)), 'strict near condition failed')
            cross = x[0]*y[1]-x[1]*y[0]
            for sign in (-1, 1):
                coeff = (k*b[0]+sign*(x[1]-y[1]), k*b[1]+sign*(y[0]-x[0]))
                require(minimum(k, coeff, k*dot+sign*cross, box) >= 0, 'angular box test failed')
        elif kind == 'pending':
            require(F(leaf['lower']) == 0, 'unsupported pending lower bound')
        else:
            raise ValueError('unknown leaf kind')
    covering = coverage(boxes)
    q = tuple(data['q'])
    require(len(q) == 2 and all(math.isfinite(v) for v in q), 'invalid incumbent')
    for r in (5, 1000):
        for sign in (-1, 1):
            require(((V(q[0])-r*cs)**2+(V(q[1])-sign*r*sn)**2).b < 1000000,
                    'incumbent not strictly in C_sig')
    ss = build_source_set(
        BearingMeasurement((0., 0.), 0., half_width_deg=1.),
        PhysicsConfig(rho_lo=1000., rho_hi=1500., near_radius=5.,
                      arena_radius=1800., arena_center=(0., 0.),
                      action_bounds=(-2000000., 2000000., -2000000., 2000000.)),
        NumericPolicy())
    # Replay the archived fixed-q node budget with ample time; no archived U is
    # trusted. A tighter fresh U still validates the archived enclosure.
    fc = data['fixed_certificate']
    fresh = certify(ss, q, tol=.001, max_nodes=fc['nodes'], time_limit_s=300., dps=30)
    upper = F(data['upper'])
    require(F(fresh.upper_m) <= upper and F(fc['upper_m']) == upper,
            'fresh fixed-q bound does not validate archived U')
    require(F(fc['lower_m']) <= F(fresh.upper_m)
            and F(fresh.lower_m) <= F(fc['upper_m']), 'fixed-q intervals disjoint')
    require(target == max(F(0), upper-tau), 'target mismatch')
    pending = counts['pending']; complete = pending == 0
    lower = target if complete else F(0)
    require(F(data['lower']) == lower and F(data['gap']) == upper-lower, 'false global bounds')
    require(data['pending'] == pending and data['converged'] is complete, 'false convergence')
    require(data['status'] == ('CERTIFIED_OUTER_TAU' if complete else 'CERTIFIED_OUTER_BOUNDS'), 'false status')
    require(data['stop_reason'] == 'complete' if complete else data['stop_reason'] in ('node_budget', 'time_budget'), 'false stop reason')
    # Full binary partition: internal nodes=leaves-1, processed excludes pending.
    require(data['nodes'] == 2*len(boxes)-1-pending, 'node accounting mismatch')
    require(lower <= F(fresh.upper_m) <= upper, 'incumbent/global containment failed')
    scale = 10**6
    floor = (lower*scale).__floor__()
    ceil = (upper*scale).__ceil__()
    return dict(valid=True, complete=complete, counts=dict(counts), leaves=len(boxes),
                **covering, lower=str(lower), upper=str(upper), gap=str(upper-lower),
                display_lower=f'{floor/scale:.6f}', display_upper=f'{ceil/scale:.6f}',
                display_gap=f'{(ceil-floor)/scale:.6f}',
                minimum_pair_distance_squared=str(min_d2), verified_source_points=legal.cache_info().currsize,
                fresh_certificate=asdict(fresh), checker_dps=60,
                scope='Standard symmetric continuous model; relies on mpmath.iv inclusion, not formal verification')
