"""Independent exact/LP oracles. Deliberately imports no production module."""
from __future__ import annotations
import json
import math
import random
from fractions import Fraction as F
from itertools import combinations
from pathlib import Path
import mpmath as mp
import numpy as np
from scipy.optimize import linprog

HERE = Path(__file__).resolve().parent
SEED = 20260911
mp.mp.dps = 80


def frac(x):
    return F(str(x))


def det(a, b):
    return a[0]*b[1]-a[1]*b[0]


def sub(a, b):
    return (a[0]-b[0], a[1]-b[1])


def norm2(v):
    return v[0]**2+v[1]**2


def encode(x):
    if isinstance(x, F):
        return str(x)
    if isinstance(x, (list, tuple)):
        return [encode(v) for v in x]
    if isinstance(x, dict):
        return {k: encode(v) for k, v in x.items()}
    return x


def feasible(rows):
    """Eliminate y, solve a 1-D exact interval, then back-substitute."""
    pos = [r for r in rows if r[1] > 0]
    neg = [r for r in rows if r[1] < 0]
    one = [(a, c) for a, b, c in rows if b == 0]
    for a, b, c in pos:
        for d, e, f in neg:
            one.append((a/b-d/e, c/b-f/e))
    lo = hi = None
    for a, c in one:
        if a == 0:
            if c < 0:
                return None
        elif a > 0:
            hi = c/a if hi is None else min(hi, c/a)
        else:
            lo = c/a if lo is None else max(lo, c/a)
    if lo is not None and hi is not None and lo > hi:
        return None
    x = max(F(0), lo) if lo is not None else F(0)
    x = min(x, hi) if hi is not None else x
    yl = max(((c-a*x)/b for a, b, c in neg), default=None)
    yh = min(((c-a*x)/b for a, b, c in pos), default=None)
    y = max(F(0), yl) if yl is not None else F(0)
    y = min(y, yh) if yh is not None else y
    assert all(a*x+b*y <= c for a, b, c in rows)
    return x, y


def recession(rows):
    # Every nonzero vector can be rescaled so one coordinate is +1 or -1.
    hom = [(a, b, F(0)) for a, b, _ in rows]
    for a, b in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
        p = feasible(hom+[(F(a), F(b), F(1)), (F(-a), F(-b), F(-1))])
        if p is not None:
            return p
    return None


def hull(points):
    """Exact Jarvis wrapping, unlike production's monotone chain."""
    pts = sorted(set(points))
    if len(pts) <= 1:
        return pts
    out = [pts[0]]
    while True:
        p = out[-1]
        q = next(v for v in pts if v != p)
        for r in pts:
            z = det(sub(q, p), sub(r, p))
            if z < 0 or (z == 0 and norm2(sub(r, p)) > norm2(sub(q, p))):
                q = r
        if q == out[0]:
            break
        out.append(q)
        assert len(out) <= len(pts)
    return out


def vertex_truth(v):
    best = F(0)
    pairs = []
    for i in range(len(v)):
        for j in range(i, len(v)):
            d = norm2(sub(v[i], v[j]))
            if d > best:
                best, pairs = d, []
            if d == best:
                pairs.append((i, j))
    return dict(vertices=encode(v), diameter_squared=str(best),
                diameter=math.sqrt(float(best)), farthest_pairs=pairs)


def lp_truth(rows):
    if not rows:
        return dict(kind='UNBOUNDED', feasible_point=[0, 0], statuses=[0, 3])
    arr = np.array([[float(x) for x in r] for r in rows])
    lengths = np.linalg.norm(arr[:, :2], axis=1)
    arr /= lengths[:, None]
    opts = dict(primal_feasibility_tolerance=1e-9, dual_feasibility_tolerance=1e-9)
    def solve(c):
        return linprog(c, A_ub=arr[:, :2], b_ub=arr[:, 2],
                       bounds=[(None, None)]*2, method='highs', options=opts)
    r = solve([0, 0])
    result = dict(kind='UNKNOWN', statuses=[int(r.status)], feasible_point=None)
    if r.status == 2:
        result['kind'] = 'EMPTY'
    elif r.success:
        result['feasible_point'] = r.x.tolist()
        axes = [solve(c) for c in [(1, 0), (-1, 0), (0, 1), (0, -1)]]
        result['statuses'] += [int(a.status) for a in axes]
        result['kind'] = ('UNBOUNDED' if any(a.status == 3 for a in axes)
                          else 'BOUNDED' if all(a.success for a in axes) else 'UNKNOWN')
    return result


def oracle(rows):
    p = feasible(rows)
    result = dict(kind='EMPTY', vertices=[], diameter=None, diameter_squared=None,
                  feasible_point=encode(p), recession_direction=None, farthest_pairs=[])
    if p is not None:
        r = recession(rows)
        if r is not None:
            result.update(kind='UNBOUNDED', recession_direction=encode(r))
        else:
            candidates = set()
            for a, b in combinations(rows, 2):
                d = det(a, b)
                if d == 0:
                    continue
                q = ((a[2]*b[1]-a[1]*b[2])/d, (a[0]*b[2]-a[2]*b[0])/d)
                if all(c[0]*q[0]+c[1]*q[1] <= c[2] for c in rows):
                    candidates.add(q)
            v = hull(candidates)
            assert v, 'bounded nonempty polyhedron must have vertices'
            result.update(vertex_truth(v))
            result['kind'] = 'POINT' if len(v) == 1 else 'SEGMENT' if len(v) == 2 else 'POLYGON'
    lp = lp_truth(rows)
    expected_lp = result['kind'] if result['kind'] in ('EMPTY', 'UNBOUNDED') else 'BOUNDED'
    lp['agrees_with_exact'] = lp['kind'] == expected_lp
    result['lp'] = lp
    return result


def sincos(degrees):
    # Canonical quadrant reduction preserves exact cardinal/opposite identities.
    t = frac(degrees) % 360
    q, r = divmod(t, 90)
    if r == 0:
        s, c = F(0), F(1)
    elif r == 45:
        # Common rational approximation, so x/y symmetry remains exact.
        s = c = F(mp.nstr(mp.sqrt(mp.mpf('0.5')), 65))
    else:
        angle = mp.mpf(r.numerator)/r.denominator*mp.pi/180
        s, c = F(mp.nstr(mp.sin(angle), 65)), F(mp.nstr(mp.cos(angle), 65))
    return [(s, c), (c, -s), (-s, -c), (-c, s)][int(q)]


def observation_rows(obs):
    rows = []
    for o in obs:
        x, y = map(frac, o['position'])
        t, e = frac(o['bearing_deg']), frac(o['half_width_deg'])
        s, c = sincos(t)
        if e == 90:
            normals = [(-c, -s)]
        else:
            sl, cl = sincos(t-e)
            su, cu = sincos(t+e)
            normals = [(sl, -cl), (-su, cu), (-c, -s)]
        rows.extend((a, b, a*x+b*y) for a, b in normals)
    return rows


def obs(x, y, t, e):
    return dict(position=[x, y], bearing_deg=t, half_width_deg=e)


def build_cases():
    rng = random.Random(SEED)
    cases = []
    def add(name, category, rows=None, observations=None, tags=(), closed=None, relation=None, points=None):
        inp = {}
        if points is not None:
            pts = [tuple(map(frac, p)) for p in points]
            truth = vertex_truth(hull(pts))
            truth['kind'] = 'POINT' if len(truth['vertices']) == 1 else 'SEGMENT' if len(truth['vertices']) == 2 else 'POLYGON'
            inp['points'] = encode(pts)
            method = 'Fraction Jarvis hull + exhaustive rational squared distances'
        else:
            if observations is not None:
                inp['observations'] = observations
                rows = observation_rows(observations)
            else:
                rows = [tuple(map(frac, r)) for r in rows]
                inp['halfplanes'] = encode(rows)
            inp['oracle_halfplanes'] = encode(rows)
            truth = oracle(rows)
            method = 'Fraction Fourier-Motzkin + exact intersections + exhaustive pairs; independent scipy HiGHS LP'
        if closed:
            # Closed answers are additional independent checks, never derived from producer.
            assert truth['kind'] == closed['kind'], (name, truth, closed)
            if closed.get('diameter') is not None:
                assert math.isclose(truth['diameter'], closed['diameter'], rel_tol=1e-12, abs_tol=1e-12)
            if 'vertices' in closed:
                tv = [[float(F(x)) for x in p] for p in truth['vertices']]
                assert len(tv) == len(closed['vertices'])
                assert all(min(math.dist(p, q) for q in tv) < 1e-9
                           for p in closed['vertices'])
            truth['closed_form'] = closed
            method += '; closed form'
        c = dict(case_id=name, category=category, tags=list(tags), input=inp,
                 ground_truth=truth, truth_method=method)
        if relation:
            c['invariant'] = relation
        cases.append(c)
        return c

    add('whole_plane', 'degenerate', observations=[], closed=dict(kind='UNBOUNDED'))
    add('ray_intersection', 'closed_form', observations=[obs(0, 1, 0, 0), obs(2, 0, 90, 0)], closed=dict(kind='POINT', diameter=0, vertices=[[2, 1]]))
    add('facing_rays', 'closed_form', observations=[obs(0, 0, 0, 0), obs(10, 0, 180, 0)], closed=dict(kind='SEGMENT', diameter=10, vertices=[[0,0],[10,0]]))
    add('away_rays', 'closed_form', observations=[obs(0, 0, 180, 0), obs(10, 0, 0, 0)], closed=dict(kind='EMPTY'))
    for t in [0, 1, 45, 89, 179, 359.9]:
        for e in [0, 1e-10, 1, 45, 90]:
            add(f'single_{t}_{e}', 'degenerate', observations=[obs(3, -7, t, e)], tags=['single_wedge', 'recession'], closed=dict(kind='UNBOUNDED'))
    for name, rows, kind in [
        ('point', [(1,0,2),(-1,0,-2),(0,1,3),(0,-1,-3)], 'POINT'),
        ('segment', [(1,0,10),(-1,0,0),(0,1,0),(0,-1,0)], 'SEGMENT'),
        ('line', [(1,-1,2),(-1,1,-2)], 'UNBOUNDED'),
        ('strip', [(0,1,1),(0,-1,1)], 'UNBOUNDED'),
        ('empty', [(1,0,0),(-1,0,-1)], 'EMPTY')]:
        add(name, 'degenerate', rows=rows, closed=dict(kind=kind))
    # S1=(-a,0), S2=(0,-a), bearing 0/90, t=tan(e).
    # Opposite vertices (a*t/(1-t), same) and (-a*t/(1+t), same).
    for a in [1, 100, 1000000]:
        for e in [1, 10, 30]:
            t = math.tan(math.radians(e))
            add(f'orthogonal_{a}_{e}', 'closed_form', observations=[obs(-a,0,0,e),obs(0,-a,90,e)],
                closed=dict(kind='POLYGON', diameter=2*math.sqrt(2)*a*t/(1-t*t), formula='2 sqrt(2) a tan(e)/(1-tan(e)^2)'))
    square = [obs(-1,-1,45,45), obs(1,1,225,45)]
    add('square_wedges', 'closed_form', observations=square, closed=dict(kind='POLYGON',diameter=math.sqrt(8),vertices=[[-1,-1],[1,-1],[1,1],[-1,1]]))
    # Each inward 90-degree wedge is one polygon support halfplane.
    for n in [3,4,5,6,8,12,31,64]:
        oo=[]
        for k in range(n):
            t=360*k/n
            oo.append(obs(10*math.cos(math.radians(t)),10*math.sin(math.radians(t)), t+180,90))
        d = 20/math.cos(math.pi/n)*(1 if n%2==0 else math.cos(math.pi/(2*n)))
        add(f'regular_{n}', 'closed_form', observations=oo, tags=['regular_polygon','parallel_edges','ties'],
            closed=dict(kind='POLYGON',diameter=d,formula='2 r sec(pi/n) [even:1, odd:cos(pi/(2n))]', input_rounding='float support positions'))
    # Narrow 1-degree wedges: lower boundaries support the regular polygon;
    # place each station far enough along the negative edge tangent that the
    # upper/front constraints are redundant throughout the circumcircle.
    for n in [3,4,5,6,8,12]:
        radius=10/math.cos(math.pi/n)
        h=radius+2*radius/math.tan(math.radians(2))
        oo=[]
        for k in range(n):
            t=2*math.pi*k/n
            oo.append(obs(10*math.cos(t)+h*math.sin(t),
                          10*math.sin(t)-h*math.cos(t),360*k/n+91,1))
        d=2*radius*(1 if n%2==0 else math.cos(math.pi/(2*n)))
        add(f'regular_narrow_{n}', 'closed_form', observations=oo,
            tags=['regular_polygon','one_degree_wedges'],
            closed=dict(kind='POLYGON',diameter=d,
                        formula='2 r sec(pi/n) [even:1, odd:cos(pi/(2n))]',
                        input_rounding='float stations; redundant boundaries with circumcircle margin'))
    for n in [1,2,3,4,8,16,32]:
        for k in range(12):
            oo=[]
            gx,gy = rng.uniform(-100,100),rng.uniform(-100,100)
            for _ in range(n):
                x,y = rng.uniform(-1000,1000),rng.uniform(-1000,1000)
                e=rng.choice([0.001,1,10,45,90])
                t=math.degrees(math.atan2(gy-y,gx-x)) + rng.uniform(-0.8,0.8)*e
                if k%3==0:
                    t=rng.uniform(-720,720)
                oo.append(obs(x,y,t,e))
            add(f'random_obs_{n}_{k}', 'random', observations=oo,tags=[f'N={n}'])
    for n in [3,5,10,25]:
        for k in range(8):
            rows=[(1,0,10),(-1,0,10),(0,1,10),(0,-1,10)]
            for _ in range(n):
                a,b=rng.randint(-20,20),rng.randint(-20,20)
                if a or b:
                    rows.append((a,b,rng.randint(-30,200)))
            add(f'random_rational_{n}_{k}', 'random', rows=rows,tags=['rational_normals'])
    for power in [4,8,10,12,14]:
        z=F(1,10**power)
        add(f'long_triangle_{power}', 'adversarial', rows=[(0,-1,0),(-z,1,0),(z,1,1)], tags=['near_parallel','large_diameter'])
        add(f'thin_rectangle_{power}', 'adversarial', rows=[(1,0,1),(-1,0,0),(0,1,z),(0,-1,0)], tags=['near_collinear','thin'])
        add(f'tiny_gap_{power}', 'adversarial', rows=[(1,0,0),(-1,0,-z)], tags=['empty','tolerance_band'])
        add(f'narrow_obs_{power}', 'adversarial', observations=[obs(-1,0,0,10**(-power)),obs(0,-1,90,10**(-power))],tags=['narrow_wedge'])
        add(f'collinear_stations_{power}', 'adversarial', observations=[obs(0,0,0,1),obs(1,10**(-power),0,1),obs(2,0,180,1)],tags=['near_collinear_stations'])
    for t in [-720.1,-0.1,0,359.9,360,719.9]:
        add(f'wrap_{t}', 'adversarial', observations=[obs(-1,0,t,1),obs(0,-1,90,1)], tags=['cross_zero'])
    # Exact rational rigid rotation (3/5,4/5), reflection, translations and scales.
    bases=[c for c in cases if c['case_id'] in ['square_wedges','point','segment','line','empty','random_rational_10_1']]
    for base in bases:
        rows=[tuple(map(F,r)) for r in base['input']['oracle_halfplanes']]
        for name, mat, scale, shift in [
            ('rotate',((F(3,5),F(-4,5)),(F(4,5),F(3,5))),F(1),(F(0),F(0))),
            ('reflect',((F(-1),F(0)),(F(0),F(1))),F(1),(F(0),F(0))),
            ('small',((F(1),F(0)),(F(0),F(1))),F(1,1000000),(F(0),F(0))),
            ('large_translate',((F(1),F(0)),(F(0),F(1))),F(1000000),(F(2000000),F(-2000000)))]:
            transformed=[]
            for a,b,c in rows:
                na,nb=mat[0][0]*a+mat[0][1]*b,mat[1][0]*a+mat[1][1]*b
                transformed.append((na,nb,scale*c+na*shift[0]+nb*shift[1]))
            add(base['case_id']+'_'+name,'invariant',rows=transformed, relation=dict(base=base['case_id'],kind='similarity',scale=float(scale)),tags=[name])
    for base in [c for c in cases if c['case_id'] in ['square_wedges','orthogonal_100_1','random_obs_8_1','facing_rays']]:
        oo=base['input']['observations'][:]
        rng.shuffle(oo)
        add(base['case_id']+'_shuffle_duplicate','invariant', observations=oo+oo,
            relation=dict(base=base['case_id'],kind='same',scale=1),tags=['shuffle','duplicate'])
        if base['ground_truth']['kind']=='POLYGON':
            # e=90 observation x <= 1e9: independently known redundant here.
            add(base['case_id']+'_redundant','invariant',observations=oo+[obs(1e9,0,180,90)],
                relation=dict(base=base['case_id'],kind='same',scale=1),tags=['redundant'])
    add('square_cut','invariant',observations=square+[obs(0,0,180,90)],relation=dict(base='square_wedges',kind='nonincrease',scale=1),tags=['added_constraint'])
    for n in [1,2,3,4,8,32,100,300]:
        for k in range(5):
            pts=[(rng.randint(-1000,1000),rng.randint(-1000,1000)) for _ in range(n)]
            add(f'hull_cloud_{n}_{k}','random',points=pts+pts[:3],tags=['isolated_hull','isolated_calipers'])
    for name,pts in [('collinear',[(i,2*i) for i in range(-10,11)]),('square',[(0,0),(2,0),(2,2),(0,2),(1,0),(1,1),(0,0)]),('thin',[(0,0),(1,0),(1,F(1,10**14)),(0,F(1,10**14))])]:
        add('hull_'+name,'adversarial',points=pts,tags=['isolated_hull','isolated_calipers','ties'])
    byid={c['case_id']: c for c in cases}
    assert len(byid)==len(cases)
    for c in cases:
        rel=c.get('invariant')
        if not rel:
            continue
        a,b=c['ground_truth'],byid[rel['base']]['ground_truth']
        if rel['kind']!='nonincrease':
            assert a['kind']==b['kind'], c['case_id']
        if a['diameter'] is not None and b['diameter'] is not None:
            if rel['kind']=='nonincrease':
                assert a['diameter']<=b['diameter']*rel['scale']+1e-12
            else:
                assert math.isclose(a['diameter'],b['diameter']*rel['scale'],rel_tol=1e-12,abs_tol=1e-12)
    return cases


def main():
    cases=build_cases()
    with (HERE/'cases.jsonl').open('w') as f:
        for c in cases:
            f.write(json.dumps(c,ensure_ascii=False,allow_nan=False)+'\n')
    print(f'Generated {len(cases)} independent cases -> {HERE / "cases.jsonl"}')

if __name__=='__main__':
    main()
