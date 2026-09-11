"""Independent exact-rational oracle; never imports production geometry."""
from fractions import Fraction as F
from decimal import Decimal, localcontext
from itertools import combinations
from pathlib import Path
import json
import math
import random

ROOT = Path(__file__).resolve().parent


def square_distance(a, b):
    return sum((x-y)**2 for x, y in zip(a, b))


def candidate(points):
    if len(points) == 1:
        return points[0], F(0)
    a, b = points[:2]
    if len(points) == 2:
        c = tuple((x+y)/2 for x, y in zip(a, b))
    else:
        # Global perpendicular bisector equations, exact Cramer's rule.
        z = points[2]
        u, v = tuple(2*(b[i]-a[i]) for i in range(2)), tuple(2*(z[i]-a[i]) for i in range(2))
        det = u[0]*v[1]-u[1]*v[0]
        if not det:
            return None
        p = sum(x*x for x in b)-sum(x*x for x in a)
        q = sum(x*x for x in z)-sum(x*x for x in a)
        c = ((p*v[1]-q*u[1])/det, (u[0]*q-v[0]*p)/det)
    return c, square_distance(c, a)


def exact_mec(points):
    p = [tuple(F(x) for x in v) for v in points]
    best = None
    supports = []
    for n in range(1, min(3, len(p))+1):
        for ids in combinations(range(len(p)), n):
            c = candidate([p[i] for i in ids])
            if c is None or (best is not None and c[1] > best[1]):
                continue
            if all(square_distance(c[0], v) <= c[1] for v in p):
                if best is None or c[1] < best[1]:
                    best, supports = c, []
                supports.append(ids)
    return best, supports


def root(q):
    with localcontext() as ctx:
        ctx.prec = 80
        return float((Decimal(q.numerator)/Decimal(q.denominator)).sqrt())


def oracle(points, pair=None):
    p = [tuple(F(x) for x in v) for v in points]
    (c, r2), supports = exact_mec(p)
    d2 = max(square_distance(a, b) for a in p for b in p)
    pairs = [(i,j) for i in range(len(p)) for j in range(i, len(p)) if square_distance(p[i], p[j]) == d2]
    i,j = pair if pair is not None else pairs[0]
    assert square_distance(p[i], p[j]) == d2
    m = tuple((a+b)/2 for a,b in zip(p[i],p[j]))
    t = max(sum((v[k]-p[i][k])*(v[k]-p[j][k]) for k in range(2)) for v in p)
    mr2 = max(square_distance(v,m) for v in p)
    d, r = root(d2), root(r2)
    # Radius comparison is exact, not a float subtraction and not Thales.
    mathematical = 'YES' if 4*r2 <= d2 else 'NO'
    assert (t <= 0) == (mathematical == 'YES')
    tol = 2*(1e-10+1e-12*max(1,d))*max(1,d)
    # Near-zero dot products can change sign in float64, so both safe states
    # are allowed; NO is never allowed for an exactly covered set.
    allowed = [mathematical]
    if d and abs(float(t)) <= tol:
        allowed.append('UNRESOLVED')
        if t > 0:
            allowed = ['UNRESOLVED']
    return dict(center=list(map(float,c)), radius=r, diameter=d, diameter_squared=float(d2),
                pair=[i,j], farthest_pairs=pairs, supports=supports, forced_center=list(map(float,m)),
                thales_max=float(t), thales_exact=str(t), radius_squared_exact=str(r2),
                mathematical_cover=mathematical, allowed_cover_status=allowed,
                kappa=2*r/d if d else None, eta=2*root(mr2)/d if d else None,
                midpoint_radius=root(mr2), tolerance_m2=tol)


def generate():
    cases=[]
    def add(name, points, tags, closed=None, **extra):
        points=[[float(x),float(y)] for x,y in points]
        gt=oracle(points, extra.pop('pair',None))
        if closed:
            for key,val in closed.items():
                assert math.isclose(gt[key],val,rel_tol=2e-12,abs_tol=2e-12), (name,key,gt[key],val)
        nonzero_distances=[math.dist(a,b) for a,b in combinations(points,2) if a!=b]
        magnitude=max(abs(x) for v in points for x in v)
        # Three-point forced circles also depend on altitude, not just edge lengths.
        # Compute it from exact submitted coordinates to avoid cancellation.
        altitudes=[]
        if len(points)==3:
            a,b,c=[tuple(F(x) for x in p) for p in points]
            area2=abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))
            if area2 and nonzero_distances:
                altitudes.append(float(area2)/max(nonzero_distances))
        feature=min(nonzero_distances+altitudes,default=0.)
        limited=magnitude>1e6 or (0<feature<1e-3)
        extra['scale_assessment']=dict(coordinate_magnitude=magnitude,feature_m=feature,min_nonzero_pair_distance_m=min(nonzero_distances,default=0.),min_nonzero_triangle_altitude_m=min(altitudes,default=None),scale_limit=limited)
        tags=list(tags)+(['scale_limit'] if limited else ['resolved_scale'])
        cases.append(dict(case_id=name,input=dict(points=points,seeds=[0,1,7,42],**extra),ground_truth=gt,
                          truth_method='exact_fraction_enumeration'+('+closed_form' if closed else ''),
                          categories=tags,closed_form=closed))
    add('point',[(3,-2)],['degenerate','closed_form'],dict(radius=0,diameter=0))
    add('duplicates',[(2,3)]*4,['degenerate'])
    add('segment',[(0,0),(40,0)],['degenerate','closed_form'],dict(radius=20,diameter=40,kappa=1,eta=1))
    add('collinear',[(0,0),(2,0),(10,0),(2,0)],['degenerate'])
    add('collinear_three',[(0,0),(2,0),(10,0)],['degenerate'])
    for h in [1e-14,1e-9,0.5,1,2,math.sqrt(3)]:
        add('isosceles_'+str(h),[(-1,0),(1,0),(0,h)],['closed_form','degenerate' if h<1e-8 else 'adversarial'],
            dict(radius=1 if h<=1 else (1+h*h)/(2*h)))
    for h in [math.nextafter(1,0),1+1e-11,1+1e-8]:
        add('thales_boundary_'+str(h),[(-1,0),(1,0),(0,h)],['adversarial','boundary'])
    for label,p,r in [('acute',[(0,0),(4,0),(1,3)],math.sqrt(5)),('obtuse',[(0,0),(4,0),(1,1)],2),('right',[(0,0),(4,0),(0,3)],2.5)]:
        add(label,p,['closed_form'],dict(radius=r))
    for L in [1,20,20*math.sqrt(3),36,40,1000]:
        p=[(0,0),(L,0),(L/2,math.sqrt(3)*L/2)]
        O=(L/2,math.sqrt(3)*L/6); h=L/math.tan(math.radians(2))
        stations=[]
        for k in range(3):
            a=math.radians(120*k); x,y=-h-O[0],-O[1]
            s=[O[0]+math.cos(a)*x-math.sin(a)*y,O[1]+math.sin(a)*x+math.cos(a)*y]
            # All vertices lie in every wedge; active lower lines are the
            # triangle's three oriented side lines. Upper lines are redundant.
            for v in p:
                delta=(math.degrees(math.atan2(v[1]-s[1],v[0]-s[0]))-(1+120*k)+180)%360-180
                assert abs(delta)<=1+1e-10
            side_a,side_b=p[k],p[(k+1)%3]
            u=(math.cos(a),math.sin(a))
            for v in (side_a,side_b):
                assert abs(u[0]*(v[1]-s[1])-u[1]*(v[0]-s[0])) <= 1e-10*max(1,L)
            stations.append(dict(position=s,bearing_deg=1+120*k,half_width_deg=1,source_distance=math.dist(s,O)))
        # AB is an exact farthest pair for these rounded coordinates in this family.
        add('equilateral_'+str(L),p,['closed_form','tight_bound','wedge_constructible'],
            dict(radius=L/math.sqrt(3),diameter=L,kappa=2/math.sqrt(3),eta=math.sqrt(3),thales_max=L*L/2),
            stations=stations,source=O,ideal_side=L,clearance_expected=('EXISTS_COVER_CENTER' if L<=20*math.sqrt(3) else 'SHAPE_DEPENDENT' if L<=40 else 'IMPOSSIBLE'))
    for pair in [(0,2),(1,3)]:
        add('square_pair_'+str(pair),[(0,0),(4,0),(4,4),(0,4)],['closed_form','multiple_farthest_pairs'],
            dict(radius=4/math.sqrt(2),diameter=4*math.sqrt(2),kappa=1,eta=1),pair=pair)
    for n in range(3,14):
        R=7
        add('regular_'+str(n),[(R*math.cos(2*math.pi*i/n),R*math.sin(2*math.pi*i/n)) for i in range(n)],
            ['closed_form'],dict(radius=R,diameter=2*R if n%2==0 else 2*R*math.cos(math.pi/(2*n))))
    rng=random.Random(20260911)
    for k in range(100):
        p=[(rng.randint(-10000,10000)/100,rng.randint(-10000,10000)/100) for _ in range(rng.randint(3,12))]
        add('random_'+str(k),p,['random'])
    bases=list(cases[2:24])+cases[-8:]
    for base in bases:
        for scale,angle,shift,reflect in [(1,0.731,(123,-456),1),(1e-6,0,(0,0),-1),(1e6,0,(0,0),1),(1,0,(1e9,-1e9),1),(1e-3,0,(0,0),1),(1,0,(100000,-100000),1)]:
            c,s=math.cos(angle),math.sin(angle)
            p=[(shift[0]+scale*(c*x-s*y*reflect),shift[1]+scale*(s*x+c*y*reflect)) for x,y in base['input']['points']]
            add(base['case_id']+'_transform_'+str((scale,angle,shift)),p,['invariant','adversarial'],
                transform=dict(base=base['case_id'],scale=scale,angle=angle,shift=shift,reflect=reflect))
    # PLAN §11.1 square: exact quarter-turns avoid trigonometric station drift.
    a=20.660669*math.sqrt(2)
    vertices=[(0,0),(a,0),(a,a),(0,a)]
    center=(a/2,a/2); h=2*a/math.tan(math.radians(2))
    offset=(-h-center[0],-center[1]); stations=[]
    for k in range(4):
        x,y=offset
        station=(center[0]+x,center[1]+y)
        theta=1+90*k
        for v in vertices:
            delta=(math.degrees(math.atan2(v[1]-station[1],v[0]-station[0]))-theta+180)%360-180
            assert abs(delta)<=1+1e-10
        direction=[(1,0),(0,1),(-1,0),(0,-1)][k]
        for v in (vertices[k],vertices[(k+1)%4]):
            assert abs(direction[0]*(v[1]-station[1])-direction[1]*(v[0]-station[0]))<1e-10
        stations.append(dict(position=station,bearing_deg=theta,half_width_deg=1))
        offset=(-y,x)
    add('symmetric_four_station_square',vertices,['closed_form','anchor','wedge_constructible'],
        dict(diameter=a*math.sqrt(2),radius=a/math.sqrt(2),kappa=1,eta=1),
        display_name='对称四站正方形',stations=stations,anchor_expected=dict(diameter=41.321338,radius=20.660669,
            radius_diameter_ratio=0.5,cover='YES',regime='IMPOSSIBLE'),square_side=a)
    for value,label in [(0,'zero'),(20*math.sqrt(3),'jung_equal'),(40,'diameter_equal'),(36,'middle'),
                        (math.nextafter(20*math.sqrt(3),0),'jung_below'),(math.nextafter(20*math.sqrt(3),math.inf),'jung_above'),
                        (math.nextafter(40,0),'40_below'),(math.nextafter(40,math.inf),'40_above'),(-1,'negative')]:
        regime='ValueError' if value<0 else ('EXISTS_COVER_CENTER' if label in ['zero','jung_equal','jung_below'] else 'IMPOSSIBLE' if label=='40_above' else 'SHAPE_DEPENDENT')
        cases.append(dict(case_id='clearance_'+label,input=dict(diameter_m=value),ground_truth=dict(regime=regime),truth_method='closed_form_threshold',categories=['boundary','clearance']))
    for kind,status in [('EMPTY','NOT_APPLICABLE'),('UNBOUNDED','NOT_APPLICABLE'),('missing_endpoints','UNRESOLVED'),('region_unresolved','UNRESOLVED')]:
        cases.append(dict(case_id='status_'+kind,input=dict(special=kind),ground_truth=dict(status=status),truth_method='interface_contract',categories=['status','degenerate']))
    with (ROOT/'cases.jsonl').open('w') as f:
        for case in cases:
            f.write(json.dumps(case,ensure_ascii=False,allow_nan=False)+'\n')
    return cases

if __name__=='__main__':
    print(f'Generated {len(generate())} cases')
