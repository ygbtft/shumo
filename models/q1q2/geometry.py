"""Closed forward wedges and bounded-polyhedral geometry; metres and radians."""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from enum import Enum
from functools import cmp_to_key
from itertools import combinations
import math
from typing import Sequence
import numpy as np
from mock.geometry import bearing, angle_delta, distance, advance

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
    rounding_mode: str | None = None
    error_mode: str | None = 'THEORETICAL_1_DEG'
    rounding_assumption_source: str | None = None
    session_id: str | None = None
    stage_id: str | None = None
    stability_id: str | None = None
    raw_bearing_deg: float | None = None

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
        object.__setattr__(self, 'bearing_deg', self.bearing_deg % 360 + 0.0)


@dataclass(frozen=True)
class HalfPlane:
    normal: Point2
    offset: float
    source: str = ''

    def __post_init__(self):
        n = np.array(point(self.normal))
        length = np.linalg.norm(n)
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


def wedge_halfplanes(obs: BearingMeasurement) -> tuple[HalfPlane, ...]:
    theta, eps = map(math.radians, (obs.bearing_deg, obs.half_width_deg))
    # Exact right-angle identities prevent trigonometric roundoff turning rays into slivers.
    u = unit(theta)
    u[np.abs(u) < 4*np.finfo(float).eps] = 0
    n = np.array((-u[1], u[0]))
    normals = (-u,) if obs.half_width_deg == 90 else (
        math.sin(eps)*(-u)-math.cos(eps)*n,
        math.sin(eps)*(-u)+math.cos(eps)*n, -u)
    return tuple(HalfPlane(point(v), float(v @ obs.position),
                           f'{obs.measurement_id}:{i}') for i, v in enumerate(normals))


def convex_hull(points: Sequence[Point2], policy: NumericPolicy) -> tuple[Point2, ...]:
    pts = sorted(set(point(p) for p in points))
    if len(pts) <= 1:
        return tuple(pts)
    def half(seq):
        out = []
        for p in seq:
            while len(out) > 1 and cross(np.subtract(out[-1], out[-2]),
                                         np.subtract(p, out[-1])) <= 0:
                out.pop()
            out.append(p)
        return out
    return tuple(half(pts)[:-1] + half(pts[::-1])[:-1])


def polygon_area(vertices):
    if len(vertices) < 3:
        return 0.
    a = np.asarray(vertices)-vertices[0]
    return abs(sum(cross(a[i], a[(i+1) % len(a)]) for i in range(len(a))))/2


def _intersection(a, b):
    det = cross(a[:2], b[:2])
    if det == 0:
        return None
    return np.array(((a[2]*b[1]-a[1]*b[2])/det,
                     (a[0]*b[2]-a[2]*b[0])/det))


def _enumerated_vertices(rows, tol):
    found = []
    for a, b in combinations(rows, 2):
        p = _intersection(a, b)
        if p is not None and np.all(rows[:, :2] @ p-rows[:, 2] <= tol*(1+np.linalg.norm(p))):
            found.append(point(p))
    return found


def _deque_vertices(rows, tol):
    def compare(a, b):
        va, vb = np.array((-a[1], a[0])), np.array((-b[1], b[0]))
        ha = int(va[1] < 0 or (va[1] == 0 and va[0] < 0))
        hb = int(vb[1] < 0 or (vb[1] == 0 and vb[0] < 0))
        if ha != hb:
            return ha-hb
        z = cross(va, vb)
        return -1 if z > 0 else 1 if z < 0 else 0
    ordered = sorted(rows, key=cmp_to_key(compare))
    unique = []
    for row in ordered:
        if unique and compare(unique[-1], row) == 0:
            if row[2] < unique[-1][2]:
                unique[-1] = row
        else:
            unique.append(row)
    queue = deque()
    def outside(row, a, b):
        p = _intersection(a, b)
        if p is None:
            raise ArithmeticError('parallel deque boundaries')
        return row[:2] @ p-row[2] > tol*(1+np.linalg.norm(p))
    try:
        for row in unique:
            while len(queue) > 1 and outside(row, queue[-2], queue[-1]):
                queue.pop()
            while len(queue) > 1 and outside(row, queue[0], queue[1]):
                queue.popleft()
            queue.append(row)
        while len(queue) > 2 and outside(queue[0], queue[-2], queue[-1]):
            queue.pop()
        while len(queue) > 2 and outside(queue[-1], queue[0], queue[1]):
            queue.popleft()
        if len(queue) < 3:
            return []
        q = list(queue)
        vertices = [_intersection(q[i], q[(i+1) % len(q)]) for i in range(len(q))]
        if any(p is None or np.any(rows[:, :2] @ p-rows[:, 2] > tol*(1+np.linalg.norm(p)))
               for p in vertices):
            return []
        return [point(p) for p in vertices]
    except ArithmeticError:
        return []


def intersect_halfplanes(hps: Sequence[HalfPlane], policy: NumericPolicy) -> Region:
    if not hps:
        return Region(RegionKind.UNBOUNDED, feasible_point=(0., 0.),
                      recession_direction=(1., 0.), residual=0., method='whole_plane')
    normals = np.array([h.normal for h in hps])
    offsets = np.array([h.offset for h in hps])
    origin = np.linalg.lstsq(normals, offsets, rcond=None)[0]
    scale = max(1., float(np.max(np.abs(offsets-normals @ origin))))
    rows = np.column_stack((normals, (offsets-normals @ origin)/scale))
    tol = policy.length()
    p = np.zeros(2)
    ambiguous = False
    for i, row in enumerate(rows):
        violation = float(row[:2] @ p-row[2])
        if violation <= tol*(1+np.linalg.norm(p)):
            ambiguous |= violation > 0
            continue
        base = row[:2]*row[2]
        v = np.array((-row[1], row[0]))
        low, high = -math.inf, math.inf
        conflict = [i]
        for j in range(i):
            a = float(rows[j, :2] @ v)
            b = float(rows[j, 2]-rows[j, :2] @ base)
            if a == 0:
                if b < -tol:
                    return Region(RegionKind.EMPTY, method='incremental', conflict_constraints=(j, i))
                ambiguous |= b < 0
                continue
            if abs(a) < policy.angle_abs:
                ambiguous = True
            t = b/a
            if a > 0 and t < high:
                high = t
                conflict = (conflict + [j])[-3:]
            elif a < 0 and t > low:
                low = t
                conflict = (conflict + [j])[-3:]
        if low > high:
            if low-high <= tol*(1+abs(low)+abs(high)) or ambiguous:
                return Region(None, status='NUMERICAL_UNRESOLVED', method='incremental_boundary')
            return Region(RegionKind.EMPTY, method='incremental', conflict_constraints=tuple(conflict))
        p = base+min(max(0., low), high)*v
    feasible = point(origin+scale*p)
    if ambiguous and np.max(rows[:, :2] @ p-rows[:, 2]) > 0:
        # A tolerance-band feasible point cannot prove a nonempty set.
        alternatives = _enumerated_vertices(rows, 0.)
        if alternatives:
            p = np.asarray(alternatives[0])
            feasible = point(origin+scale*p)
        elif np.any(normals @ np.asarray(feasible)-offsets >
                    16*np.finfo(float).eps*(np.abs(normals) @ np.abs(feasible)+np.abs(offsets))):
            # Boundary points need not have strictly negative floating residuals.
            # Only arithmetic roundoff is excused here, not the policy tolerance:
            # a genuinely inconsistent narrow strip must remain unresolved.
            return Region(None, feasible_point=feasible, status='NUMERICAL_UNRESOLVED',
                          method='feasibility_residual_recheck')
    for n in normals:
        for v in (np.array((-n[1], n[0])), np.array((n[1], -n[0]))):
            residual = max(float(nj[0]*v[0]+nj[1]*v[1]) for nj in normals)
            if residual <= 0:
                return Region(RegionKind.UNBOUNDED, feasible_point=feasible,
                              recession_direction=point(v), residual=residual, method='recession')
            # Tiny positive dot products do not establish recession.
    vertices = _deque_vertices(rows, tol)
    method = 'deque'
    if len(vertices) < 3 or polygon_area(vertices) == 0:
        vertices = _enumerated_vertices(rows, tol)
        method = 'enumeration_fallback'
    hull = convex_hull(vertices, policy)
    if not hull:
        return Region(None, feasible_point=feasible, status='NUMERICAL_UNRESOLVED', method=method)
    # Exact duplicates are already removed; small area alone is not a rank decision.
    world = tuple(point(origin+scale*np.array(v)) for v in hull)
    residual = float(np.max(normals @ np.asarray(world).T-offsets[:, None]))
    sines = [abs(cross(a, b)) for a, b in combinations(normals, 2) if cross(a, b) != 0]
    sine = min(sines, default=1.)
    status = 'NUMERICAL_UNRESOLVED' if residual > policy.length(max(map(lambda v: distance(v, feasible), world)))*4 else 'OK'
    return Region((RegionKind.POINT if len(world) == 1 else RegionKind.SEGMENT if len(world) == 2
                   else RegionKind.POLYGON), world, feasible, residual=residual, status=status,
                  method=method, minimum_intersection_sine=sine,
                  condition_number=(1+math.sqrt(max(0., 1-sine*sine)))/sine,
                  vertex_scale=max(distance(v, feasible) for v in world))


def diameter(region: Region, policy: NumericPolicy) -> DiameterResult:
    if region.status != 'OK':
        return DiameterResult(None, None, status='NUMERICAL_UNRESOLVED')
    if region.kind == RegionKind.EMPTY:
        return DiameterResult(None, None, status='EMPTY')
    if region.kind == RegionKind.UNBOUNDED:
        return DiameterResult(math.inf, math.inf, status='UNBOUNDED')
    v = np.asarray(region.vertices)
    n = len(v)
    if n == 1:
        return DiameterResult(0., 0., (point(v[0]), point(v[0])), (0, 0))
    best, pair = -1., (0, 1)
    def update(i, j):
        nonlocal best, pair
        ij = tuple(sorted((i % n, j % n)))
        d2 = float(np.sum((v[ij[0]]-v[ij[1]])**2))
        if d2 > best or (d2 == best and ij < pair):
            best, pair = d2, ij
    if n == 2:
        update(0, 1)
    else:
        j = 1
        for i in range(n):
            edge = v[(i+1) % n]-v[i]
            count = 0
            while cross(edge, v[(j+1) % n]-v[i]) > cross(edge, v[j]-v[i]) and count < n:
                j = (j+1) % n
                count += 1
            update(i, j)
            update(i+1, j)
            if abs(cross(edge, v[(j+1) % n]-v[j])) <= policy.squared(np.linalg.norm(edge)):
                update(i, j+1)
                update(i+1, j+1)
    return DiameterResult(math.sqrt(best), best, tuple(point(v[k]) for k in pair), pair)
