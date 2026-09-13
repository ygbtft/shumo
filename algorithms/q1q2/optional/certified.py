"""Independent interval certificate for fixed-q J (PLAN appendix A).

Only raw SourceSet fields are read; no production geometry/sampling is called.
Float inputs denote their exact binary values. Angles are in degrees, converted
with interval pi. Production wedges instead use decimal-degree semantics.
This certificate bounds the raw binary-input continuous problem, not every
production intermediate approximation; the two semantics are not identical.
See benchmark README for the covering/pruning proof.
"""
from dataclasses import dataclass
from functools import lru_cache
from itertools import product
import heapq
import math
import time

from mpmath.ctx_iv import MPIntervalContext


# Moving one float outward after conversion encloses endpoint rounding.
_SOURCE_CACHE_LIMIT = 32768  # Performance only; eviction cannot change bounds.
_CORNER_TRY_FREQUENCY = 8  # Performance only; every witness is still verified.


def _down(x):
    return math.nextafter(float(x.a), -math.inf)


def _up(x):
    return math.nextafter(float(x.b), math.inf)


@dataclass(frozen=True)
class Certificate:
    lower_m: float
    upper_m: float
    gap_m: float
    converged: bool
    status: str
    stop_reason: str
    nodes: int
    active_boxes: int
    elapsed_seconds: float
    witness: dict | None
    dps: int
    backend: str = 'mpmath.iv'


def certify(source_set, q, epsilon2=1., *, tol=.1, max_nodes=200000,
            time_limit_s=60., dps=30):
    """Return L <= J(q) <= U; convergence is explicit, never assumed.

    q=S uses fixed-repeat semantics (diam F). Otherwise this computes the pair
    definition, whose posterior interpretation presupposes q in C_sig.
    Empty or unresolved F is not assigned diameter zero: at least one actual
    source witness is required before a certificate is returned.
    """
    p, first = source_set.physics, source_set.first
    values = (*first.position, *p.arena_center, *q, first.bearing_deg,
              first.half_width_deg, p.arena_radius, p.rho_hi, p.near_radius,
              epsilon2, tol, time_limit_s)
    if not all(math.isfinite(v) for v in values):
        raise ValueError('finite inputs required')
    if not (0 < epsilon2 < 45 and 0 <= first.half_width_deg <= 90
            and tol > 0 and time_limit_s >= 0 and max_nodes >= 0 and dps >= 20
            and p.arena_radius > 0 and 0 < p.near_radius < p.rho_hi):
        raise ValueError('unsupported angle, physics, precision or budget')
    started = time.monotonic()
    iv = MPIntervalContext()
    iv.dps = dps
    V = iv.mpf
    s, c, qv = [tuple(map(V, z)) for z in (first.position, p.arena_center, q)]
    near, rho, radius = map(V, (p.near_radius, p.rho_hi, p.arena_radius))
    n2 = near**2
    sc = tuple(a-b for a, b in zip(s, c))
    sc2 = sum(z**2 for z in sc)
    theta, eps = V(first.bearing_deg), first.half_width_deg
    delta = 2*V(epsilon2)*iv.pi/180
    cos2, tan = iv.cos(delta)**2, iv.tan(delta)
    same = tuple(q) == tuple(first.position)

    # min/max are monotone in each endpoint, giving interval outer bounds.
    def maximum(a, b):
        return V([max(a.a, b.a), max(a.b, b.b)])

    def minimum(a, b):
        return V([min(a.a, b.a), min(a.b, b.b)])

    @lru_cache(maxsize=_SOURCE_CACHE_LIMIT)
    def source(ab, tb):
        # Full [-eps,eps] is covered, including rays absent from float F events.
        angle = (theta+V(ab))*iv.pi/180
        u = (iv.cos(angle), iv.sin(angle))
        proj = sum(a*b for a, b in zip(sc, u))
        disc = proj**2 + radius**2-sc2
        if disc.b < 0:
            return None
        root = iv.sqrt(V([max(V(0), disc.a), disc.b]))
        lo, hi = maximum(near, -proj-root), minimum(rho, -proj+root)
        if (hi-lo).b < 0 or hi.b <= near.a:
            return None
        # Convex interpolation avoids extra dependency width at t=1.
        t = V(tb)
        r = (1-t)*lo+t*hi
        xy = tuple(a+r*b for a, b in zip(s, u))
        # A point parameter describes an exact mathematical source, even when
        # its coordinates are irrational. Prove radial existence/membership by
        # construction; no rounded boundary coordinates are used as witnesses.
        legal = (ab[0] == ab[1] and tb[0] == tb[1]
                 and disc.a >= 0 and (hi-lo).a >= 0 and r.a > near.b)
        return xy, legal

    def pair_data(box, branch, witness=False):
        xx, yy = source(box[0], box[1]), source(box[2], box[3])
        if xx is None or yy is None:
            return None
        x, lx = xx
        y, ly = yy
        if witness and not (lx and ly):
            return None
        dist = iv.sqrt(sum((a-b)**2 for a, b in zip(x, y)))
        if branch == 'same_station':
            return dist
        a, b = tuple(xi-qi for xi, qi in zip(x, qv)), tuple(yi-qi for yi, qi in zip(y, qv))
        aa, bb = sum(z**2 for z in a), sum(z**2 for z in b)
        if branch == 'near':
            if witness:
                return dist if aa.b <= n2.a and bb.b <= n2.a else None
            if aa.a > n2.b or bb.a > n2.b:
                return None
            return minimum(dist, 2*near)
        # Strict distance: only upper-bound relaxation allows equality. A box
        # entirely <=5 cannot contain direction, including exactly 5.
        if aa.b <= n2.a or bb.b <= n2.a:
            return None
        w = sum(ai*bi for ai, bi in zip(a, b))
        poly = w**2-cos2*aa*bb
        det = a[0]*b[1]-a[1]*b[0]
        left, right = tan*w-det, tan*w+det
        # Pruning needs one constraint false throughout the box; a lower-bound
        # witness needs every constraint proven at a legal point parameter.
        if witness:
            return dist if (aa.a > n2.b and bb.a > n2.b and w.a >= 0
                            and poly.a >= 0) else None
        if w.b < 0 or poly.b < 0 or left.b < 0 or right.b < 0:
            return None
        return dist

    lower, witness = 0., None
    def try_point(params, branch):
        nonlocal lower, witness
        box = tuple((v, v) for v in params)
        d = pair_data(box, branch, True)
        if d is not None and (witness is None or _down(d) > lower):
            lower = max(0., _down(d))
            enclosures = []
            for i in (0, 2):
                coordinates = []
                for z in source(box[i], box[i+1])[0]:
                    coordinates.append([_down(z), _up(z)])
                enclosures.append(coordinates)
            witness = dict(parameters=list(params), branch=branch,
                           coordinate_enclosures=enclosures,
                           distance_interval_m=[max(0., _down(d)), _up(d)])

    root = ((-eps, eps), (0., 1.), (-eps, eps), (0., 1.))
    branches = ('same_station',) if same else ('near', 'direction')
    # Independent seeds, including inward approximants to the open first edge.
    # Seeding counts in elapsed time but finishes before budget checks: very
    # small time limits are soft limits, not a hard-real-time deadline.
    for params in product(sorted(set([-eps, 0., eps])), (0., 1e-10, .5, 1.),
                          sorted(set([-eps, 0., eps])), (0., 1e-10, .5, 1.)):
        for branch in branches:
            try_point(params, branch)
    heap, counter, nodes = [], 0, 0
    def push(box, branch, inherited=math.inf):
        nonlocal counter
        d = pair_data(box, branch)
        if d is not None:
            upper = min(inherited, _up(d))
            if upper > lower:
                counter += 1
                heapq.heappush(heap, (-upper, counter, box, branch))

    for branch in branches:
        push(root, branch)
    reason = 'gap'
    while heap and _up(V(-heap[0][0])-V(lower)) > tol:
        if nodes >= max_nodes or time.monotonic()-started >= time_limit_s:
            reason = 'node_budget' if nodes >= max_nodes else 'time_budget'
            break
        neg_u, serial, box, branch = heapq.heappop(heap)
        # Split by estimated physical width. This affects priority only, never
        # interval bounds or the domain cover. Children share the exact split.
        widths = [(b-a)*(p.rho_hi*math.pi/180 if i%2 == 0 else p.rho_hi-p.near_radius)
                  for i, (a, b) in enumerate(box)]
        k = max(range(4), key=widths.__getitem__)
        a, b = box[k]
        mid = a+(b-a)/2
        if mid == a or mid == b:
            heapq.heappush(heap, (neg_u, serial, box, branch))
            reason = 'parameter_resolution'
            break
        # Midpoints are dense; corners accelerate boundary maxima. Every seed
        # goes through the same interval proof, without feasibility tolerances.
        try_point([a+(b-a)/2 for a, b in box], branch)
        if nodes % _CORNER_TRY_FREQUENCY == 0:
            for params in product(*[sorted(set([a, b])) for a, b in box]):
                try_point(params, branch)
        for half in ((a, mid), (mid, b)):
            child = list(box)
            child[k] = half
            push(tuple(child), branch, -neg_u)
        nodes += 1
    if witness is None:
        raise ValueError('NO_VERIFIED_SOURCE: empty F or unresolved degenerate membership')
    upper = max(lower, -heap[0][0] if heap else lower)
    gap = max(0., _up(V(upper)-V(lower))) if upper > lower else 0.
    converged = gap <= tol
    return Certificate(
        lower_m=lower,
        upper_m=upper,
        gap_m=gap,
        converged=converged,
        status='CERTIFIED_FIXED_Q_TOL' if converged else 'CERTIFIED_BOUNDS',
        stop_reason='gap' if converged else reason,
        nodes=nodes,
        active_boxes=len(heap),
        elapsed_seconds=time.monotonic()-started,
        witness=witness,
        dps=dps,
    )


def assess(j_hat, certificate, tol):
    """Interval-band acceptance; PASS is not proof of accurate J if gap is large."""
    if not math.isfinite(j_hat) or not math.isfinite(tol) or tol < 0:
        raise ValueError('finite J_hat and nonnegative tolerance required')
    iv = MPIntervalContext()
    iv.dps = certificate.dps
    j, t = iv.mpf(j_hat), iv.mpf(tol)
    if j < iv.mpf(certificate.lower_m)-t:
        return 'UNDERESTIMATE'
    if j > iv.mpf(certificate.upper_m)+t:
        return 'OVERESTIMATE'
    return 'PASS'
