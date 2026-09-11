"""Analytic source boundaries and universal signal/direction candidate predicates."""
from __future__ import annotations
from dataclasses import dataclass
import math
import numpy as np
from numpy.typing import ArrayLike, NDArray
from .geometry import (Point2, NumericPolicy, BearingMeasurement, HalfPlane, Region,
                       point, unit, bearing, angle_delta, distance, wedge_halfplanes,
                       intersect_halfplanes)

BoolArray = NDArray[np.bool_]
TAU = 2*math.pi


@dataclass(frozen=True)
class PhysicsConfig:
    rho_lo: float = 1000.
    rho_hi: float = 1500.
    near_radius: float = 5.
    clearance_radius: float = 20.
    arena_radius: float = 1800.
    arena_center: Point2 = (0., 0.)
    action_bounds: tuple[float, float, float, float] = (-2000000., 2000000., -2000000., 2000000.)

    def __post_init__(self):
        values = (self.rho_lo, self.rho_hi, self.near_radius, self.clearance_radius, self.arena_radius)
        if not all(math.isfinite(x) and x > 0 for x in values) or self.rho_lo > self.rho_hi:
            raise ValueError('invalid physics')
        if self.near_radius >= self.rho_hi:
            raise ValueError('near radius must be smaller than receiving radius')
        if self.near_radius > self.clearance_radius:
            raise ValueError('near radius cannot exceed the physical clearance radius')
        object.__setattr__(self, 'arena_center', point(self.arena_center))
        x0, x1, y0, y1 = self.action_bounds
        if not all(math.isfinite(v) for v in self.action_bounds) or x0 > x1 or y0 > y1:
            raise ValueError('invalid action bounds')

    def action_contains(self, q):
        x0, x1, y0, y1 = self.action_bounds
        return x0 <= q[0] <= x1 and y0 <= q[1] <= y1


@dataclass(frozen=True)
class BoundaryPiece:
    kind: str
    source: str
    start: Point2
    end: Point2
    center: Point2 | None = None
    radius: float | None = None
    angle_start: float = 0.
    angle_end: float = 0.
    attained: bool = True

    def at(self, t):
        if self.kind == 'arc':
            return point(np.asarray(self.center)+self.radius*unit(self.angle_start+t*(self.angle_end-self.angle_start)))
        return point((1-t)*np.asarray(self.start)+t*np.asarray(self.end))

    def angle_contains(self, theta):
        return (theta-self.angle_start) % TAU <= self.angle_end-self.angle_start+1e-14


@dataclass(frozen=True)
class RadialInterval:
    low: float
    high: float
    low_open: bool


@dataclass(frozen=True)
class SourceSet:
    first: BearingMeasurement
    physics: PhysicsConfig
    policy: NumericPolicy
    status: str
    boundaries: tuple[BoundaryPiece, ...] = ()
    low_boundaries: tuple[BoundaryPiece, ...] = ()
    high_boundaries: tuple[BoundaryPiece, ...] = ()
    angle_events: tuple[float, ...] = ()
    angle_intervals: tuple[tuple[float, float], ...] = ()
    actual_point: Point2 | None = None
    strict_boundary: str = 'distance_from_first > near_radius'

    def radial_interval(self, alpha: float, lower=None, upper=None):
        eps = math.radians(self.first.half_width_deg)
        if not -eps <= alpha <= eps:
            return None
        p = self.physics
        u = unit(math.radians(self.first.bearing_deg)+alpha)
        s = np.asarray(self.first.position)-p.arena_center
        projection = float(s @ u)
        discriminant = projection**2+p.arena_radius**2-float(s @ s)
        if discriminant < 0:
            return None
        root = math.sqrt(discriminant)
        low = max(p.near_radius, -projection-root, lower if lower is not None else 0.)
        high = min(p.rho_hi, -projection+root, upper if upper is not None else math.inf)
        if high < low or high <= p.near_radius:
            return None
        return RadialInterval(low, high, low == p.near_radius)

    def contains(self, points: ArrayLike, closed=False) -> BoolArray:
        a = np.atleast_2d(np.asarray(points, dtype=float))
        p = self.physics
        delta = a-self.first.position
        r = np.linalg.norm(delta, axis=1)
        angles = np.degrees(np.arctan2(delta[:, 1], delta[:, 0]))
        da = (angles-self.first.bearing_deg+180) % 360-180
        angular = np.abs(da) <= self.first.half_width_deg
        if closed:
            angular = np.abs(da) <= self.first.half_width_deg+math.degrees(self.policy.angle_abs)
        return (np.isfinite(a).all(axis=1) & angular &
                ((r >= p.near_radius) if closed else (r > p.near_radius)) &
                (r <= p.rho_hi+(self.policy.length(p.rho_hi) if closed else 0)) &
                (np.linalg.norm(a-p.arena_center, axis=1) <=
                 p.arena_radius+(self.policy.length(p.arena_radius) if closed else 0)))

    def parameters(self, p):
        alpha = math.radians(angle_delta(bearing(self.first.position, p), self.first.bearing_deg))
        eps = math.radians(self.first.half_width_deg)
        alpha = min(eps, max(-eps, alpha))
        interval = self.radial_interval(alpha)
        if interval is None:
            return None
        t = ((distance(p, self.first.position)-interval.low)/(interval.high-interval.low)
             if interval.high > interval.low else 0.)
        return alpha, min(1., max(0., t))

    def parameter_point(self, alpha, t, inward=1e-7):
        interval = self.radial_interval(float(alpha))
        if interval is None or not 0 <= t <= 1:
            return None
        r = interval.low+t*(interval.high-interval.low)
        if interval.low_open and r <= interval.low:
            r = min(interval.high, interval.low+inward)
        result = point(np.asarray(self.first.position)+r*unit(math.radians(self.first.bearing_deg)+alpha))
        return result if self.contains([result])[0] else None


@dataclass(frozen=True)
class CandidateCheck:
    status: str
    max_violation: float | None
    extremal_source: Point2 | None = None
    witness_attained: bool = False
    g_low: float | None = None
    g_high: float | None = None
    direction_status: str | None = None
    distance_to_closure: float | None = None
    conservative_direction_interior: bool = False
    reason: str = ''
    exact_definition: str = 'q in Q and forall p in F: |q-p| <= max(rho_lo, |p-S|)'


@dataclass(frozen=True)
class Feedback:
    kind: str
    bearing_deg: float | None = None
    half_width_deg: float = 1.

    def __post_init__(self):
        if self.kind not in ('near', 'direction'):
            raise ValueError('GUARANTEE_MISMATCH: no_signal is outside the guaranteed-signal model')
        if self.kind == 'direction' and (self.bearing_deg is None or not math.isfinite(self.bearing_deg)):
            raise ValueError('direction requires finite bearing')
        if not math.isfinite(self.half_width_deg) or not 0 <= self.half_width_deg <= 90:
            raise ValueError('invalid feedback half width')


def circle_intersections(c1, r1, c2, r2):
    delta = np.asarray(c2)-c1
    d = float(np.linalg.norm(delta))
    if d == 0 or d > r1+r2 or d < abs(r1-r2):
        return ()
    a = (r1*r1-r2*r2+d*d)/(2*d)
    h2 = r1*r1-a*a
    if h2 < -1e-8:
        return ()
    base = np.asarray(c1)+a*delta/d
    perpendicular = np.array((-delta[1], delta[0]))/d
    h = math.sqrt(max(0., h2))
    return (point(base+h*perpendicular), point(base-h*perpendicular))


def _line_circle(hp, center, radius):
    n = np.asarray(hp.normal)
    offset = hp.offset-float(n @ center)
    if abs(offset) > radius:
        return ()
    base = np.asarray(center)+offset*n
    d = math.sqrt(max(0., radius*radius-offset*offset))
    v = np.array((-n[1], n[0]))
    return point(base+d*v), point(base-d*v)


def _boundaries(ss, lower, upper):
    if lower > upper:
        return ()
    s, p = ss.first.position, ss.physics
    hps = wedge_halfplanes(ss.first)
    circles = ((s, lower, 'inner_limit' if lower == p.near_radius else 'radial_split'),
               (s, upper, 'receiving' if upper == p.rho_hi else 'radial_split'),
               (p.arena_center, p.arena_radius, 'arena'))
    def legal(x):
        r = distance(x, s)
        tol = ss.policy.length(max(p.arena_radius, p.rho_hi))*4
        return (lower-tol <= r <= upper+tol and
                distance(x, p.arena_center) <= p.arena_radius+tol and
                all(np.dot(h.normal, x)-h.offset <= tol for h in hps))
    result = []
    for center, radius, label in circles:
        events = [0., TAU]
        for c2, r2, _ in circles:
            for x in circle_intersections(center, radius, c2, r2):
                events.append(math.atan2(x[1]-center[1], x[0]-center[0]) % TAU)
        for hp in hps:
            for x in _line_circle(hp, center, radius):
                events.append(math.atan2(x[1]-center[1], x[0]-center[0]) % TAU)
        events = sorted(set(events))
        for a, b in zip(events[:-1], events[1:]):
            midpoint = np.asarray(center)+radius*unit((a+b)/2)
            if legal(midpoint):
                result.append(BoundaryPiece('arc', label, point(np.asarray(center)+radius*unit(a)),
                                            point(np.asarray(center)+radius*unit(b)), point(center),
                                            radius, a, b, label != 'inner_limit'))
        for a in events[:-1]:
            x = point(np.asarray(center)+radius*unit(a))
            if legal(x) and distance(x, s) > p.near_radius:
                result.append(BoundaryPiece('point', label, x, x))
    for hp in hps:
        n = np.asarray(hp.normal)
        base, v = hp.offset*n, np.array((-n[1], n[0]))
        events = []
        for center, radius, _ in circles:
            events.extend(float((np.asarray(x)-base) @ v) for x in _line_circle(hp, center, radius))
        for other in hps:
            a = np.dot(other.normal, v)
            if a != 0:
                events.append((other.offset-np.dot(other.normal, base))/a)
        events = sorted(set(events))
        for a, b in zip(events[:-1], events[1:]):
            if legal(base+(a+b)/2*v):
                x, y = point(base+a*v), point(base+b*v)
                result.append(BoundaryPiece('segment', 'wedge', x, y))
    return tuple(result)


def build_source_set(first: BearingMeasurement, physics: PhysicsConfig, policy: NumericPolicy) -> SourceSet:
    from dataclasses import replace
    ss = SourceSet(first, physics, policy, 'INCONSISTENT_FIRST_OBSERVATION')
    eps, theta = math.radians(first.half_width_deg), math.radians(first.bearing_deg)
    events = [-eps, eps]
    d = distance(first.position, physics.arena_center)
    if d > physics.arena_radius:
        direction = math.atan2(physics.arena_center[1]-first.position[1], physics.arena_center[0]-first.position[0])
        offset = math.asin(physics.arena_radius/d)
        for t in (direction-offset, direction+offset):
            a = (t-theta+math.pi) % TAU-math.pi
            if -eps <= a <= eps:
                events.append(a)
    for r in (physics.near_radius, physics.rho_lo, physics.rho_hi):
        for x in circle_intersections(first.position, r, physics.arena_center, physics.arena_radius):
            a = math.radians(angle_delta(bearing(first.position, x), first.bearing_deg))
            if -eps <= a <= eps:
                events.append(a)
    events = sorted(set(events))
    intervals = [(a, b) for a, b in zip(events[:-1], events[1:]) if ss.radial_interval((a+b)/2) is not None]
    intervals.extend((a, a) for a in events if ss.radial_interval(a) is not None)
    actual = None
    for a, b in intervals:
        actual = ss.parameter_point((a+b)/2, .5)
        if actual is not None:
            break
    if actual is None:
        return replace(ss, angle_events=tuple(events))
    ss = replace(ss, status='OK', actual_point=actual, angle_events=tuple(events), angle_intervals=tuple(intervals))
    return replace(ss, boundaries=_boundaries(ss, physics.near_radius, physics.rho_hi),
                   low_boundaries=_boundaries(ss, physics.near_radius, min(physics.rho_lo, physics.rho_hi)),
                   high_boundaries=_boundaries(ss, max(physics.near_radius, physics.rho_lo), physics.rho_hi))


def _extrema_points(pieces, direction=None):
    for piece in pieces:
        yield piece.start
        yield piece.end
        if piece.kind == 'arc' and direction is not None:
            v = direction(piece)
            if np.linalg.norm(v) == 0:
                yield piece.at(.5)
            else:
                angle = math.atan2(v[1], v[0])
                if piece.angle_contains(angle):
                    yield point(np.asarray(piece.center)+piece.radius*unit(angle))


def closure_distance(source_set, q):
    if source_set.contains([q], closed=True)[0]:
        return 0., point(q), bool(source_set.contains([q])[0])
    pts = list(_extrema_points(source_set.boundaries, lambda piece: np.asarray(q)-piece.center))
    for piece in source_set.boundaries:
        if piece.kind == 'segment':
            v = np.asarray(piece.end)-piece.start
            v2 = float(v @ v)
            if v2:
                t = np.clip(np.dot(np.asarray(q)-piece.start, v)/v2, 0, 1)
                pts.append(piece.at(float(t)))
    if not pts:
        return math.inf, None, False
    distances = [distance(q, x) for x in pts]
    i = int(np.argmin(distances))
    minimum = distances[i]
    witness, attained = _boundary_witness(source_set, pts[i])
    return minimum, witness, attained


def _boundary_witness(ss, x):
    """Represent a closed analytic extremum inside its closed constraints.

    Do not confuse trig roundoff on a closed edge with the excluded first-near
    circle. The latter remains a limit witness, even if its rounded norm is > R.
    """
    r = distance(x, ss.first.position)
    rounding = 32*np.finfo(float).eps*max(1., r, *map(abs, x),
                                          *map(abs, ss.first.position))
    if abs(r-ss.physics.near_radius) <= rounding:
        return point(x), False
    if ss.contains([x])[0]:
        return point(x), True
    params = ss.parameters(x)
    if params is not None and ss.contains([x], closed=True)[0]:
        alpha, t = params
        eps = math.radians(ss.first.half_width_deg)
        for inset in (1e-15, 1e-14, 1e-13, 1e-12):
            a = min(max(0., eps-inset), max(min(0., -eps+inset), alpha))
            candidate = ss.parameter_point(a, min(1-inset, max(inset, t)))
            if candidate is not None:
                return candidate, True
    return point(x), False


def check_candidate(source_set: SourceSet, q: Point2, require_direction: bool, policy: NumericPolicy) -> CandidateCheck:
    q = point(q)
    ss, p = source_set, source_set.physics
    if ss.status != 'OK':
        return CandidateCheck('UNRESOLVED', None, reason=ss.status)
    if not p.action_contains(q):
        return CandidateCheck('OUT', None, reason='outside_action_domain')
    if q == ss.first.position:
        return CandidateCheck('IN', 0., direction_status='IN', reason='same_point_first_direction',
                              distance_to_closure=closure_distance(ss, q)[0],
                              exact_definition='S in C_dir subset C_sig; repeated bearing is fixed')
    low = [(distance(q, x)**2-p.rho_lo**2, x) for x in
           _extrema_points(ss.low_boundaries, lambda piece: np.asarray(piece.center)-q)]
    h = np.asarray(q)-ss.first.position
    high = [(float(h @ h-2*h @ (np.asarray(x)-ss.first.position)), x) for x in
            _extrema_points(ss.high_boundaries, lambda piece: -h)]
    combined = low+high
    if not combined:
        return CandidateCheck('UNRESOLVED', None, reason='no_analytic_boundary')
    violation, witness = max(combined, key=lambda z: z[0])
    witness, witness_attained = _boundary_witness(ss, witness)
    tol = policy.squared(max(p.rho_hi, np.linalg.norm(h)))
    status = 'OUT' if violation > tol else 'IN' if violation < -tol else 'BOUNDARY'
    ds, near_distance, inside = None, None, False
    if require_direction and status != 'OUT':
        near_distance, closest, attained = closure_distance(ss, q)
        margin = near_distance-p.near_radius
        inside = margin > policy.length(p.rho_hi)
        if inside:
            ds = 'IN'
        elif margin < -policy.length(p.rho_hi):
            ds = 'OUT'
        elif margin == 0 and attained:
            ds = 'OUT'
        else:
            ds = 'BOUNDARY_UNRESOLVED'
        if ds == 'OUT':
            status = 'OUT'
            witness, witness_attained = closest, attained
            # If the closest point is excluded, strict distance < R leaves room
            # to construct an actual nearby world. Equality has no such room.
            if not attained and margin < 0:
                params = ss.parameters(closest)
                if params is not None:
                    for fraction in (1e-8, 1e-10, 1e-12):
                        candidate = ss.parameter_point(params[0], max(fraction, params[1]))
                        if candidate is not None and distance(q, candidate) <= p.near_radius:
                            witness, witness_attained = candidate, True
                            break
        elif ds == 'BOUNDARY_UNRESOLVED':
            status = 'UNRESOLVED'
    return CandidateCheck(status, violation, witness, witness_attained,
                          max((v for v, _ in low), default=None),
                          max((v for v, _ in high), default=None), ds, near_distance, inside,
                          reason='near_separating_world' if ds == 'OUT' else '',
                          exact_definition=('q in C_sig and forall p in F: |q-p| > near_radius'
                                            if require_direction else CandidateCheck.exact_definition))


def posterior_contains(source_set: SourceSet, q: Point2, feedback: Feedback,
                       points: ArrayLike, policy: NumericPolicy) -> BoolArray:
    # K membership uses the guaranteed-reception premise; this mask does not prove it.
    # Clearance/conditional diagnostics must check that premise before offering actions.
    points = np.atleast_2d(np.asarray(points, dtype=float))
    mask = source_set.contains(points)
    if point(q) == source_set.first.position:
        if feedback.kind != 'direction' or angle_delta(feedback.bearing_deg, source_set.first.bearing_deg) != 0:
            return np.zeros(len(points), dtype=bool)
        return mask
    delta = points-q
    r = np.linalg.norm(delta, axis=1)
    if feedback.kind == 'near':
        return mask & (r <= source_set.physics.near_radius)
    angles = np.degrees(np.arctan2(delta[:, 1], delta[:, 0]))
    da = (angles-feedback.bearing_deg+180) % 360-180
    return mask & (r > source_set.physics.near_radius) & (np.abs(da) <= feedback.half_width_deg)


def posterior_outer_polygon(source_set: SourceSet, q: Point2, feedback: Feedback, sides: int = 32) -> Region:
    if sides < 4:
        raise ValueError('at least four tangent half planes')
    ss, p = source_set, source_set.physics
    hps = list(wedge_halfplanes(ss.first))
    if feedback.kind == 'direction' and point(q) != ss.first.position:
        hps.extend(wedge_halfplanes(BearingMeasurement(q, feedback.bearing_deg, feedback.half_width_deg, 'second')))
    disks = [(p.arena_center, p.arena_radius, 'arena'), (ss.first.position, p.rho_hi, 'first_receiving'),
             (q, p.near_radius if feedback.kind == 'near' else p.rho_hi, 'second')]
    for center, radius, label in disks:
        for i in range(sides):
            n = unit(TAU*i/sides)
            hps.append(HalfPlane(point(n), float(n @ center+radius), label))
    return intersect_halfplanes(hps, ss.policy)
