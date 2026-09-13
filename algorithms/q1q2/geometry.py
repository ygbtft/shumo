"""Closed forward wedges and bounded-polyhedral geometry; metres and radians."""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from fractions import Fraction
from decimal import Decimal, localcontext
from itertools import combinations
import math
from typing import Sequence
import numpy as np
from .basic_geometry import bearing, angle_delta, distance, advance

Point2 = tuple[float, float]


def point(value) -> Point2:
    a = np.asarray(value, dtype=float)
    if a.shape != (2,) or not np.isfinite(a).all():
        raise ValueError('expected a finite two-dimensional point')
    return float(a[0]) + 0.0, float(a[1]) + 0.0


def cross(a, b):
    return a[0]*b[1] - a[1]*b[0]


def unit(theta):
    return np.array((math.cos(theta), math.sin(theta)))


@dataclass(frozen=True)
class NumericPolicy:
    length_abs: float = 1e-10
    angle_abs: float = 1e-12
    relative: float = 1e-12

    def __post_init__(self):
        if any(not math.isfinite(x) or x < 0 for x in
               (self.length_abs, self.angle_abs, self.relative)):
            raise ValueError('invalid tolerance')

    def length(self, scale=1.0):
        return self.length_abs + self.relative*abs(scale)

    def squared(self, scale=1.0):
        return self.length(max(1., scale))*max(1., abs(scale))*2


@dataclass(frozen=True)
class BearingMeasurement:
    position: Point2
    bearing_deg: float
    half_width_deg: float = 1.0
    measurement_id: str = ''
    channel: int | None = None
    request_id: str | None = None
    origin: str | None = None
    error_mode: str | None = 'THEORETICAL_1_DEG'
    rounding_assumption_source: str | None = None
    session_id: str | None = None
    stage_id: str | None = None
    stability_id: str | None = None
    raw_bearing_deg: float | None = None
    _exact_bearing: Fraction = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        object.__setattr__(self, 'position', point(self.position))
        if not all(math.isfinite(v) for v in (self.bearing_deg, self.half_width_deg)):
            raise ValueError('nonfinite angle')
        if self.half_width_deg < 0:
            raise ValueError('negative half width')
        if self.half_width_deg > 90:
            raise ValueError('UNSUPPORTED_NONCONVEX_ANGLE')
        if self.raw_bearing_deg is None:
            object.__setattr__(self, 'raw_bearing_deg', self.bearing_deg)
        elif not math.isfinite(self.raw_bearing_deg):
            raise ValueError('nonfinite raw bearing')
        object.__setattr__(self, '_exact_bearing', Fraction(str(self.bearing_deg)) % 360)
        object.__setattr__(self, 'bearing_deg', self.bearing_deg % 360 + 0.0)


@dataclass(frozen=True)
class HalfPlane:
    normal: Point2
    offset: float
    source: str = ''
    _exact_row: tuple[Fraction, Fraction, Fraction] = field(init=False, repr=False, compare=False)
    _normal_degrees: Fraction | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self):
        n = np.array(point(self.normal))
        # Manual coefficients mean exact binary floats; wedges replace this row
        # with decimal-degree, high-precision trigonometric coefficients.
        raw = (*map(Fraction, map(float, n)), Fraction(float(self.offset)))
        object.__setattr__(self, '_exact_row', raw)
        length = math.hypot(*n)
        if length == 0 or not math.isfinite(self.offset):
            raise ValueError('invalid half plane')
        object.__setattr__(self, 'normal', point(n/length))
        object.__setattr__(self, 'offset', float(self.offset/length))


class RegionKind(str, Enum):
    EMPTY = 'EMPTY'
    POINT = 'POINT'
    SEGMENT = 'SEGMENT'
    POLYGON = 'POLYGON'
    UNBOUNDED = 'UNBOUNDED'


@dataclass(frozen=True)
class Region:
    kind: RegionKind | None
    vertices: tuple[Point2, ...] = ()
    feasible_point: Point2 | None = None
    recession_direction: Point2 | None = None
    residual: float | None = None
    status: str = 'OK'
    method: str = ''
    conflict_constraints: tuple[int, ...] = ()
    minimum_intersection_sine: float | None = None
    condition_number: float | None = None
    vertex_scale: float | None = None


@dataclass(frozen=True)
class DiameterResult:
    length: float | None
    squared: float | None
    endpoints: tuple[Point2, Point2] | None = None
    indices: tuple[int, int] | None = None
    status: str = 'OK'
    tie_rule: str = 'lexicographically_smallest_normalized_vertex_indices'


@lru_cache(maxsize=4096)
def _sincos_degrees(angle):
    """80 digit trig with exact quadrant and diagonal identities (no snapping).

    Trig approximates transcendental coefficients; subsequent rational predicates
    are exact for those approximants, not for the original transcendental values.
    """
    quadrant, r = divmod(angle % 360, 90)
    with localcontext() as ctx:
        ctx.prec = 90
        if r == 0:
            sn, cs = Decimal(0), Decimal(1)
        elif r == 45:
            sn = cs = Decimal('0.5').sqrt()
        else:
            pi = Decimal('3.1415926535897932384626433832795028841971693993751058209749445923078164062862089986280348253421170679')
            x = Decimal(r.numerator)/Decimal(r.denominator)*pi/180
            sn, cs, st, ct = x, Decimal(1), x, Decimal(1)
            for k in range(1, 100):
                st *= -x*x/((2*k)*(2*k+1))
                ct *= -x*x/((2*k-1)*(2*k))
                sn += st
                cs += ct
        ctx.prec = 80
        sn, cs = Fraction(+sn), Fraction(+cs)
    return ((sn, cs), (cs, -sn), (-sn, -cs), (-cs, sn))[int(quadrant)]


def wedge_halfplanes(obs: BearingMeasurement) -> tuple[HalfPlane, ...]:
    # Keep the decimal measurement semantics and form offsets before rounding.
    # Normalizing binary64 normals first changes exact rays and tiny regions.
    t = obs._exact_bearing
    e = Fraction(str(obs.half_width_deg))
    x, y = map(lambda v: Fraction(str(v)), obs.position)
    sn, cs = _sincos_degrees(t)
    if e == 90:
        normals = [(-cs, -sn)]
    else:
        sl, cl = _sincos_degrees(t-e)
        su, cu = _sincos_degrees(t+e)
        normals = [(sl, -cl), (-su, cu), (-cs, -sn)]
    directions = [t+180] if e == 90 else [t-e-90, t+e+90, t+180]
    result = []
    for i, (a, b) in enumerate(normals):
        c = a*x+b*y
        hp = HalfPlane(normal=(float(a), float(b)), offset=float(c), source=f'{obs.measurement_id}:{i}')
        object.__setattr__(hp, '_exact_row', (a, b, c))
        object.__setattr__(hp, '_normal_degrees', directions[i] % 360)
        result.append(hp)
    return tuple(result)


def _orientation(a, b, c):
    # Filter ordinary determinants, resolve cancellation with original floats.
    x, y = b[0]-a[0], b[1]-a[1]
    u, v = c[0]-a[0], c[1]-a[1]
    z = x*v-y*u
    if isinstance(z, Fraction):
        return z
    if math.isfinite(z) and abs(z) > 8*np.finfo(float).eps*(abs(x*v)+abs(y*u)):
        return z
    a, b, c = [tuple(map(Fraction, p)) for p in (a, b, c)]
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def _exact_hull(points):
    pts = sorted(set(points))
    if len(pts) < 2:
        return tuple(pts)
    def half(seq):
        out = []
        for p in seq:
            while len(out) > 1 and _orientation(out[-2], out[-1], p) <= 0:
                out.pop()
            out.append(p)
        return out
    return tuple(half(pts)[:-1]+half(pts[::-1])[:-1])


def _farthest_pair(vertices):
    # Binary64 coordinates (and dyadic Fractions) share a power-of-two
    # denominator. Preserve exact rational inputs; never round them to float.
    ratios = [tuple(Fraction(c).as_integer_ratio() for c in p) for p in vertices]
    if ratios and all(d & (d-1) == 0 for p in ratios for _, d in p):
        denominator = max(d for p in ratios for _, d in p)
        v = [tuple(n*(denominator//d) for n, d in p) for p in ratios]
        best, pair = -1, (0, 0)
        for i, (x, y) in enumerate(v):
            for j in range(i, len(v)):
                d = (x-v[j][0])**2+(y-v[j][1])**2
                if d > best:
                    best, pair = d, (i, j)
        return Fraction(best, denominator*denominator), pair
    v = [tuple(map(Fraction, p)) for p in vertices]
    best, pair = Fraction(-1), (0, 0)
    for i in range(len(v)):
        for j in range(i, len(v)):
            d = (v[i][0]-v[j][0])**2+(v[i][1]-v[j][1])**2
            if d > best:
                best, pair = d, (i, j)
    return best, pair


def convex_hull(points: Sequence[Point2], policy: NumericPolicy) -> tuple[Point2, ...]:
    """CCW extreme vertices, starting at the exact lexicographic minimum.

    Sort exactly first: tolerance-based comparisons are not transitive. Clean
    the cyclic hull afterwards, removing near-collinear points inside neighbour
    chords, including across the seam; protected diameter endpoints remain.
    """
    pts = sorted(set(point(p) for p in points))
    if len(pts) <= 1:
        return tuple(pts)
    def half(seq):
        out = []
        for p in seq:
            while len(out) > 1 and _orientation(out[-2], out[-1], p) <= 0:
                out.pop()
            out.append(p)
        return out
    hull = half(pts)[:-1] + half(pts[::-1])[:-1]
    if len(hull) <= 2:
        return tuple(hull)
    perimeter = sum(math.dist(a, b) for a, b in zip(hull, hull[1:]+hull[:1]))
    extent = math.hypot(max(p[0] for p in hull)-hull[0][0],
                        max(p[1] for p in hull)-min(p[1] for p in hull))
    # Area/perimeter bounds the cleanup below the polygon's thickness. A
    # length tolerance alone would erase genuine corners of a thin polygon.
    tol = min(policy.length(extent), polygon_area(hull)/perimeter/4)
    n = len(hull)
    # Cleanup must never erase an endpoint needed for the true diameter.
    _, protected = _farthest_pair(hull)
    previous = [(i-1) % n for i in range(n)]
    following = [(i+1) % n for i in range(n)]
    alive = [True]*n
    pending = deque(range(n))
    remaining = n
    while pending and remaining > 3:
        i = pending.popleft()
        if not alive[i] or i in protected:
            continue
        left, right = previous[i], following[i]
        a, b, c = hull[left], hull[i], hull[right]
        ab, bc, ac = np.subtract(b, a), np.subtract(c, b), np.subtract(c, a)
        # Remove only points between their neighbours and within a scaled
        # distance of that chord; retain original coordinates, never average.
        if np.dot(ab, bc) >= 0 and abs(cross(ab, ac)) <= tol*math.hypot(*ac):
            alive[i] = False
            remaining -= 1
            following[left], previous[right] = right, left
            pending.extend((left, right))
    cleaned = [p for i, p in enumerate(hull) if alive[i]]
    start = min(range(len(cleaned)), key=cleaned.__getitem__)
    return tuple(cleaned[start:]+cleaned[:start])


def polygon_area(vertices):
    if len(vertices) < 3:
        return 0.
    a = np.asarray(vertices)-vertices[0]
    return abs(sum(cross(a[i], a[(i+1) % len(a)]) for i in range(len(a))))/2


def _intersection(a, b):
    a, b = tuple(map(Fraction, a)), tuple(map(Fraction, b))
    det = cross(a, b)
    if not det:
        return None
    return ((a[2]*b[1]-a[1]*b[2])/det,
            (a[0]*b[2]-a[2]*b[0])/det)


def _exact_vertices(rows):
    # O(M²) intersections, each checked against M rows: O(M³) arithmetic
    # operations; growth of rational numerators/denominators costs extra.
    integer_rows = []
    for row in rows:
        row = tuple(map(Fraction, row))
        denominator = math.lcm(*(v.denominator for v in row))
        integers = tuple(v.numerator*(denominator//v.denominator) for v in row)
        divisor = math.gcd(*integers)
        integer_rows.append(tuple(v//divisor for v in integers) if divisor else integers)
    found = set()
    for a, b in combinations(integer_rows, 2):
        d = a[0]*b[1]-a[1]*b[0]
        if not d:
            continue
        x, y = a[2]*b[1]-a[1]*b[2], a[0]*b[2]-a[2]*b[0]
        if d < 0:
            x, y, d = -x, -y, -d
        if all(aa*x+bb*y <= cc*d for aa, bb, cc in integer_rows):
            found.add((Fraction(x, d), Fraction(y, d)))
    return found


def intersect_halfplanes(hps: Sequence[HalfPlane], policy: NumericPolicy) -> Region:
    """Exact predicates on input coefficients; tolerance is only for display cleanup.

    Incremental boundary feasibility and the recession cone use rational signs.
    Enumeration is deliberately used for bounded intersections: accepting an
    approximate deque vertex is not a certificate that no extreme was lost.
    """
    # Eighty digit trig is not an exact transcendental oracle. If distinct
    # angular boundaries approach its precision floor, even rational signs
    # of the approximants cannot establish the original topology.
    # The 70-digit cutoff leaves ten guard digits below the trig precision.
    angular = [h for h in hps if h._normal_degrees is not None]
    for a, b in combinations(angular, 2):
        if ((a._normal_degrees-b._normal_degrees) % 180 and
                abs(cross(a._exact_row, b._exact_row)) < Fraction(1, 10**70)):
            return Region(kind=None, status='NUMERICAL_UNRESOLVED', method='trig_precision_limit')
    # Conflict indices belong to the caller, even when equal rows are removed.
    original_indices = {}
    for index, h in enumerate(hps):
        original_indices.setdefault(h._exact_row, index)
    rows = list(original_indices)
    p = (Fraction(0), Fraction(0))
    for i, (a, b, c) in enumerate(rows):
        if a*p[0]+b*p[1] <= c:
            continue
        base = (c/a, Fraction(0)) if a else (Fraction(0), c/b)
        v = (-b, a)
        lo = hi = None
        for j, (aa, bb, cc) in enumerate(rows[:i]):
            slope = aa*v[0]+bb*v[1]
            rhs = cc-aa*base[0]-bb*base[1]
            if not slope:
                if rhs < 0:
                    return Region(kind=RegionKind.EMPTY, method='exact_feasibility', conflict_constraints=(original_indices[rows[j]], original_indices[rows[i]]))
            elif slope > 0:
                hi = rhs/slope if hi is None else min(hi, rhs/slope)
            else:
                lo = rhs/slope if lo is None else max(lo, rhs/slope)
        if lo is not None and hi is not None and lo > hi:
            return Region(kind=RegionKind.EMPTY, method='exact_feasibility')
        t = max(Fraction(0), lo) if lo is not None else Fraction(0)
        if hi is not None:
            t = min(t, hi)
        p = (base[0]+t*v[0], base[1]+t*v[1])
    try:
        feasible = point(p)
        directions = [(Fraction(1), Fraction(0))] if not rows else [
            v for a, b, _ in rows for v in ((-b, a), (b, -a))]
        for v in directions:
            if all(a*v[0]+b*v[1] <= 0 for a, b, _ in rows):
                m = max(map(abs, v))
                w = tuple(float(x/m) for x in v)
                length = math.hypot(*w)
                return Region(
                    kind=RegionKind.UNBOUNDED,
                    feasible_point=feasible,
                    recession_direction=tuple(x/length for x in w),
                    residual=0.,
                    method='exact_recession',
                )
        exact = _exact_hull(_exact_vertices(rows))
        rounded = [point(v) for v in exact]
        # Region cleanup may remove rounding noise, never metre-sized corners
        # of a microscopic set. Public point-cloud cleanup retains its policy.
        ulp = max((math.ulp(x) for v in rounded for x in v), default=0.)
        cleanup = NumericPolicy(length_abs=min(policy.length_abs, 4*ulp), angle_abs=policy.angle_abs, relative=policy.relative)
        world = convex_hull(rounded, cleanup)
        if not world or min(len(world), 3) != min(len(exact), 3):
            return Region(kind=None, status='NUMERICAL_UNRESOLVED', method='unrepresentable_dimension')
        scale = max(math.dist(v, feasible) for v in world)
        if not math.isfinite(scale):
            raise OverflowError
        # Reject coordinates whose float representation loses the local shape.
        # Exact topology is insufficient when output metres cannot encode it.
        exact_d2, _ = _farthest_pair(exact)
        world_d2, _ = _farthest_pair(world)
        rounding = 4*max(math.ulp(x) for v in world for x in v)
        d2_float = float(exact_d2)
        if not math.isfinite(d2_float) or (exact_d2 and not d2_float):
            raise OverflowError
        d = math.sqrt(d2_float)
        error_bound = Fraction(rounding)*(2*Fraction(d)+Fraction(rounding))
        if abs(world_d2-exact_d2) > error_bound:
            return Region(kind=None, status='NUMERICAL_UNRESOLVED', method='unrepresentable_diameter')
        normals = [h.normal for h in hps]
        sines = [abs(cross(a, b)) for a, b in combinations(normals, 2) if cross(a, b)]
        sine = min(sines, default=1.)
        residual = max((h.normal[0]*v[0]+h.normal[1]*v[1]-h.offset
                        for h in hps for v in world), default=0.)
        return Region(kind=RegionKind.POINT if len(exact) == 1 else
            RegionKind.SEGMENT if len(exact) == 2 else RegionKind.POLYGON, vertices=world, feasible_point=feasible, residual=residual, method='exact_enumeration', minimum_intersection_sine=sine, condition_number=(1+math.sqrt(max(0., 1-sine*sine)))/sine, vertex_scale=scale)
    except (OverflowError, ValueError):
        return Region(kind=None, status='NUMERICAL_UNRESOLVED', method='unrepresentable_coordinates')


def diameter(region: Region) -> DiameterResult:
    """All-pairs exact squared distances: O(V²) operations, plus rational bit costs."""
    if region.status != 'OK':
        return DiameterResult(length=None, squared=None, status='NUMERICAL_UNRESOLVED')
    if region.kind == RegionKind.EMPTY:
        return DiameterResult(length=None, squared=None, status='EMPTY')
    if region.kind == RegionKind.UNBOUNDED:
        return DiameterResult(length=math.inf, squared=math.inf, status='UNBOUNDED')
    if not region.vertices:
        return DiameterResult(length=None, squared=None, status='NUMERICAL_UNRESOLVED')
    best, pair = _farthest_pair(region.vertices)
    endpoints = tuple(point(region.vertices[k]) for k in pair)
    length = math.dist(*endpoints)
    try:
        squared = float(best)
    except OverflowError:
        squared = math.inf
    if not math.isfinite(length) or not math.isfinite(squared) or (best and squared == 0):
        return DiameterResult(length=None, squared=None, status='NUMERICAL_UNRESOLVED')
    return DiameterResult(length=length, squared=squared, endpoints=endpoints, indices=pair)
