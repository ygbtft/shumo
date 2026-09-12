"""Physical worst posterior diameter: source pairs, full-domain grids, local refinement."""
from __future__ import annotations
from dataclasses import dataclass, field, replace
from itertools import product
import math
import time
from typing import Sequence
import numpy as np
from .geometry import (Point2, NumericPolicy, Region, RegionKind, point, unit, distance,
                       bearing, angle_delta, convex_hull, diameter)
from .feasible import (SourceSet, CandidateCheck, Feedback, check_candidate, closure_distance,
                       circle_intersections, _boundary_witness)


@dataclass(frozen=True)
class SearchConfig:
    station_steps_m: tuple[float, float] = (50., 25.)
    source_grids: tuple[tuple[int, int], ...] = ((9, 25), (17, 49), (33, 97))
    starts: int = 12
    station_initial_step_m: float = 25.
    station_min_step_m: float = 1.5625
    pair_starts: int = 8
    pair_rounds: int = 8
    refine_pairs: bool = False
    time_budget_s: float = 180.
    movement_budget_m: float | None = None
    policy: NumericPolicy = field(default_factory=NumericPolicy)
    second_half_width_deg: float = 1.
    block_size: int = 256
    boundary_step_deg: float = 5.
    boundary_precision_m: float = 1e-5
    near_offset_m: float = 1e-7
    require_direction: bool = False
    restrict_action_to_arena: bool = False
    tie_floor_m: float = .1
    tie_multiplier: float = 1.

    def __post_init__(self):
        if not 0 < self.second_half_width_deg < 45:
            raise ValueError('UNSUPPORTED_Q2_ANGLE: require 0 < epsilon2 < 45 degrees')
        positive = (*self.station_steps_m, self.station_initial_step_m, self.station_min_step_m,
                    self.boundary_step_deg, self.boundary_precision_m, self.near_offset_m)
        if any(not math.isfinite(x) or x <= 0 for x in positive):
            raise ValueError('invalid search resolution')
        if not math.isfinite(self.time_budget_s) or self.time_budget_s < 0:
            raise ValueError('invalid wall-clock budget')
        if self.movement_budget_m is not None and (not math.isfinite(self.movement_budget_m) or self.movement_budget_m < 0):
            raise ValueError('negative/nonfinite movement budget')
        if self.starts < 1 or self.pair_starts < 1 or self.block_size < 1 or self.pair_rounds < 0:
            raise ValueError('invalid iteration count')
        if len(self.source_grids) != 3 or any(a < 2 or r < 2 for a, r in self.source_grids):
            raise ValueError('three source grids with at least two samples per coordinate required')
        if any(not math.isfinite(v) or v < 0 for v in (self.tie_floor_m, self.tie_multiplier)):
            raise ValueError('tie parameters must be finite and nonnegative')


@dataclass(frozen=True)
class SourceSamples:
    points: tuple[Point2, ...]
    level: int
    grid: tuple[int, int]
    excluded_boundary_samples: int = 0
    additional_count: int = 0
    offset_m: float = 1e-7
    shifted: bool = False
    direction_half_width_deg: float | None = None
    augmentation_q: Point2 | None = None


@dataclass(frozen=True)
class PairWitness:
    x: Point2
    y: Point2
    branch: str
    common_bearing_deg: float | None
    distance_m: float
    constraint_residuals: dict
    near_boundary: bool
    actual_legal: bool
    worlds: tuple[dict, dict]
    supremum_semantics: str = 'actual_legal_sample_pair; continuous supremum may be unattained'


@dataclass(frozen=True)
class Score:
    J_hat: float | None
    near_score_m: float | None
    direction_score_m: float | None
    sample_count: int
    witness: PairWitness | None
    top_pairs: tuple[PairWitness, ...] = ()
    near_possibility: str = 'NOT_CHECKED'
    local_improvement_m: float | None = None
    status: str = 'NUMERICAL_CANDIDATE'
    threshold_exploration_m: float | None = None


@dataclass(frozen=True)
class CandidateResult:
    q: Point2
    check: CandidateCheck
    score: Score
    movement_m: float
    source_values_m: tuple[float, ...] = ()
    sensitivity_range_m: tuple[float, float] | None = None
    source_change_m: float | None = None
    tolerance_change_m: float | None = None
    additional_samples: int = 0
    audit_values_m: dict[str, tuple[float, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class Q2Result:
    q_best: Point2 | None
    candidate_check: CandidateCheck | None
    score: Score | None
    movement_m: float | None
    movement_seconds: float | None
    measurement_seconds: float | None
    alternatives: tuple[CandidateResult, ...] = ()
    refinement_history: tuple[dict, ...] = ()
    sensitivity_range_m: tuple[float, float] | None = None
    source_change_m: float | None = None
    station_change_m: float | None = None
    tolerance_change_m: float | None = None
    stability: str = 'NEEDS_REFINEMENT'
    status: str = 'NUMERICAL_CANDIDATE'
    stop_reason: str = 'COMPLETED'
    completed_stages: tuple[str, ...] = ()
    # score_point invocations, including interrupted calls; cache hits excluded.
    evaluations: int = 0
    elapsed_seconds: float = 0.
    config: SearchConfig | None = None
    first: object | None = None
    physics: object | None = None
    grid_records: tuple[dict, ...] = ()
    baseline: Score | None = None
    tie_threshold_m: float | None = None
    improvement_status: str | None = None
    angular_comparison: tuple[dict, ...] = ()
    clearance_diagnostics: tuple[object, ...] = ()
    objective: str = 'physical_posterior_worst_diameter'
    numerical_assessment: dict = field(default_factory=dict)
    # Frontier shared cost is recorded once on the first result, never per row.
    frontier_shared_evaluations: int = 0
    frontier_shared_elapsed_seconds: float = 0.


class _BudgetExpired(Exception):
    pass


def _check_deadline(deadline):
    if deadline is not None and time.monotonic() >= deadline:
        raise _BudgetExpired


def _direction_boundary_samples(ss, q, count, half_width, inward, deadline=None):
    """Analytic angular-contact pairs, with adaptive boundary maximization.

    For a boundary anchor x, intersect the rays rotated by +/- 2 epsilon
    with every segment/arc. This includes interior edge contacts missed by
    radial grids. Refine sampled local maxima along each anchor boundary.
    These are legal lower-bound samples, not a continuous upper certificate.
    """
    if point(q) == ss.first.position:
        return ()
    q = np.asarray(q)
    delta = math.radians(2*half_width)*(1-1e-11)
    rotations = [np.array(((math.cos(a), -math.sin(a)),
                           (math.sin(a), math.cos(a)))) for a in (-delta, 0., delta)]
    pieces = tuple(dict.fromkeys(ss.boundaries))
    result = set()

    legal_cache = {}

    def legal(x):
        key = tuple(x)  # Exact coordinates, scoped to this ss/q/angle/inward call.
        if key in legal_cache:
            return legal_cache[key]  # Includes cached None.
        value = construct_legal(x)
        legal_cache[key] = value
        return value

    def construct_legal(x):
        x, attained = _boundary_witness(ss, x)
        if not attained:
            params = ss.parameters(x)
            x = ss.parameter_point(*params, inward=inward) if params else None
        return x if x is not None and ss.contains([x])[0] else None

    def evaluate_and_record_pair(piece, t):
        _check_deadline(deadline)
        x = legal(piece.at(t))
        if x is None or distance(x, q) <= ss.physics.near_radius:
            return -1., None
        best, pair = -1., None
        for rotation in rotations:
            v = rotation @ (np.asarray(x)-q)
            v /= np.linalg.norm(v)
            candidates = []
            # Strict direction side of the near boundary also matters when q
            # lies inside F: the other endpoint need not be on the boundary of F.
            candidates.append(point(q+(ss.physics.near_radius+inward)*v))
            for other in pieces:
                _check_deadline(deadline)
                if other.kind == 'segment':
                    edge = np.asarray(other.end)-other.start
                    a = np.asarray(other.start)-q
                    det = v[0]*edge[1]-v[1]*edge[0]
                    if det == 0:
                        candidates.extend((other.start, other.end))
                        continue
                    radius = (a[0]*edge[1]-a[1]*edge[0])/det
                    u = (a[0]*v[1]-a[1]*v[0])/det
                    if radius >= 0 and 0 <= u <= 1:
                        candidates.append(other.at(float(u)))
                elif other.kind == 'arc':
                    a = q-other.center
                    projection = float(a @ v)
                    disc = projection**2-float(a @ a)+other.radius**2
                    if disc >= 0:
                        for radius in (-projection-math.sqrt(disc), -projection+math.sqrt(disc)):
                            y = q+radius*v
                            if radius >= 0 and other.angle_contains(math.atan2(y[1]-other.center[1], y[0]-other.center[0])):
                                candidates.append(point(y))
                else:
                    candidates.append(other.start)
            for y in candidates:
                y = legal(y)
                if y is None or distance(y, q) <= ss.physics.near_radius:
                    continue
                if abs(angle_delta(bearing(q, x), bearing(q, y))) > 2*half_width:
                    continue
                d = distance(x, y)
                if d > best:
                    best, pair = d, (x, y)
        if pair is not None:
            result.update(pair)
        return best, pair

    for piece in pieces:
        if piece.kind == 'point':
            evaluate_and_record_pair(piece, 0.)
            continue
        ts = np.linspace(0., 1., count)
        values = [evaluate_and_record_pair(piece, float(t))[0] for t in ts]
        for i in range(1, len(ts)-1):
            if values[i] < 0 or not (values[i] >= values[i-1] and values[i] >= values[i+1]):
                continue
            if values[i-1] == values[i] == values[i+1]:
                continue
            lo, hi = ts[i-1], ts[i+1]
            # Golden-section search retains every tested legal contact pair.
            # It explores local maxima and supplies no global upper certificate.
            ratio = (math.sqrt(5)-1)/2
            a, b = hi-ratio*(hi-lo), lo+ratio*(hi-lo)
            fa, fb = evaluate_and_record_pair(piece, a)[0], evaluate_and_record_pair(piece, b)[0]
            for _ in range(18):
                if fa < fb:
                    lo, a, fa = a, b, fb
                    b = lo+ratio*(hi-lo)
                    fb = evaluate_and_record_pair(piece, b)[0]
                else:
                    hi, b, fb = b, a, fa
                    a = hi-ratio*(hi-lo)
                    fa = evaluate_and_record_pair(piece, a)[0]
    return tuple(sorted(result))


def sample_sources(ss, level, grids, q=None, *, inward, shifted=False,
                   second_half_width_deg, deadline=None):
    """Nested legal source samples; grids, inward metres and angle degrees explicit.

    Coordinates are world metres; alpha is a first-bearing offset in radians,
    while radial interpolation t is dimensionless. Sampling is deterministic
    exploration of bounded uncertainty, not draws from a probability prior.
    """
    _check_deadline(deadline)
    if level not in (0, 1, 2):
        raise ValueError('source level must be 0, 1, or 2')
    found, excluded = [], 0
    for k in range(level+1):
        na, nr = grids[k]
        for lo, hi in ss.angle_intervals:
            fractions = (np.arange(na-1)+.5)/(na-1) if shifted else np.linspace(0, 1, na)
            angles = list(lo+(hi-lo)*fractions)+[lo, hi]
            for alpha in angles:
                _check_deadline(deadline)
                interval = ss.radial_interval(float(alpha))
                if interval is None:
                    continue
                ts = (np.arange(nr-1)+.5)/(nr-1) if shifted else np.linspace(0, 1, nr)
                for t in ts:
                    _check_deadline(deadline)
                    p = ss.parameter_point(float(alpha), float(t), inward)
                    if p is not None:
                        found.append(p)
                    else:
                        excluded += 1
                if interval.high > interval.low:
                    for r in (ss.physics.rho_lo, ss.physics.rho_hi, interval.low, interval.high):
                        if interval.low <= r <= interval.high:
                            p = ss.parameter_point(float(alpha), (r-interval.low)/(interval.high-interval.low), inward)
                            if p is not None:
                                found.append(p)
    # Custom grids need not divide one another: retain every earlier boundary point.
    for k in range(level+1):
        for piece in ss.boundaries:
            for t in np.linspace(0, 1, grids[k][0]):
                _check_deadline(deadline)
                p, attained = _boundary_witness(ss, piece.at(float(t)))
                if attained:
                    found.append(p)
    base = len(set(found))
    if q is not None:
        near = ss.physics.near_radius
        near_angles = [a for k in range(level+1)
                       for a in np.linspace(0, 2*math.pi, 4*grids[k][0], endpoint=False)]
        intersections = []
        for piece in ss.boundaries:
            if piece.kind == 'arc':
                intersections.extend(circle_intersections(q, near, piece.center, piece.radius))
            elif piece.kind == 'segment':
                a = np.asarray(piece.start)-q
                v = np.asarray(piece.end)-piece.start
                vv = float(v @ v)
                discriminant = float(a @ v)**2-vv*(float(a @ a)-near**2)
                if vv and discriminant >= 0:
                    for t in ((-float(a @ v)-math.sqrt(discriminant))/vv,
                              (-float(a @ v)+math.sqrt(discriminant))/vv):
                        if 0 <= t <= 1:
                            intersections.append(piece.at(t))
        near_angles.extend(math.atan2(x[1]-q[1], x[0]-q[0]) for x in intersections)
        for a in near_angles:
            _check_deadline(deadline)
            for radius in (0., near*.5, near-inward, near, near+inward):
                p = point(np.asarray(q)+radius*unit(a))
                if ss.contains([p])[0]:
                    found.append(p)
        for k in range(level+1):
            found.extend(_direction_boundary_samples(ss, q, grids[k][0],
                                                      second_half_width_deg, inward, deadline=deadline))
    pts = tuple(sorted(set(found)))
    return SourceSamples(
        points=pts,
        level=level,
        grid=grids[level],
        excluded_boundary_samples=excluded,
        additional_count=len(pts)-base,
        offset_m=inward,
        shifted=shifted,
        direction_half_width_deg=second_half_width_deg if q is not None else None,
        augmentation_q=point(q) if q is not None else None,
    )


def _sample_diameter(points, policy):
    hull = convex_hull(points, policy)
    if not hull:
        return None
    region = Region(kind=RegionKind.POINT if len(hull) == 1 else RegionKind.SEGMENT if len(hull) == 2
                    else RegionKind.POLYGON, vertices=hull)
    return diameter(region)


def _pair_witness(ss, q, x, y, config, same_point=False):
    x, y, q = point(x), point(y), point(q)
    if not ss.contains([x, y]).all():
        return None
    r = [distance(z, q) for z in (x, y)]
    near = ss.physics.near_radius
    if same_point:
        branch, beta = 'direction', ss.first.bearing_deg
    elif max(r) <= near:
        branch, beta = 'near', None
    elif min(r) > near:
        angles = [bearing(q, z) for z in (x, y)]
        delta = angle_delta(angles[1], angles[0])
        if abs(delta) > 2*config.second_half_width_deg:
            return None
        branch, beta = 'direction', (angles[0]+delta/2) % 360
        if any(abs(angle_delta(a, beta)) > config.second_half_width_deg for a in angles):
            # Try representable neighbours before labelling the pair unattainable.
            possible = [beta, float(np.nextafter(beta, -math.inf)), float(np.nextafter(beta, math.inf))]
            beta = next((b % 360 for b in possible if all(abs(angle_delta(a, b % 360)) <=
                         config.second_half_width_deg for a in angles)), None)
            if beta is None:
                return None
    else:
        return None
    residuals = {'second_range_minus_near_m': tuple(v-near for v in r)}
    if beta is not None:
        residuals['second_angle_minus_halfwidth_deg'] = tuple(
            abs(angle_delta(bearing(q, z), beta))-(ss.first.half_width_deg if same_point else config.second_half_width_deg)
            for z in (x, y))
    worlds = tuple({'p': z, 'rho': max(ss.physics.rho_lo, distance(z, ss.first.position), d),
                    'first_distance_m': distance(z, ss.first.position), 'second_distance_m': d,
                    'first_error_deg': angle_delta(ss.first.bearing_deg, bearing(ss.first.position, z)),
                    'second_error_deg': None if beta is None else angle_delta(beta, bearing(q, z))}
                   for z, d in zip((x, y), r))
    # This constructs an existence world, not universal reception at a BOUNDARY q.
    # Both observations must share one radius within the physical interval.
    if any(w['rho'] > ss.physics.rho_hi for w in worlds):
        return None
    residuals['reception_radius_semantics'] = 'existence_only_not_universal_reception'
    boundary = any(abs(v-near) <= config.policy.length(ss.physics.rho_hi) for v in r)
    if beta is not None:
        boundary |= any(abs(v) <= math.degrees(config.policy.angle_abs)
                        for v in residuals['second_angle_minus_halfwidth_deg'])
    return PairWitness(
        x=x,
        y=y,
        branch=branch,
        common_bearing_deg=beta,
        distance_m=distance(x, y),
        constraint_residuals=residuals,
        near_boundary=boundary,
        actual_legal=True,
        worlds=worlds,
    )


def _refine_pair(ss, q, witness, samples, config, deadline=None):
    if q == ss.first.position:
        return witness
    x, y = ss.parameters(witness.x), ss.parameters(witness.y)
    if x is None or y is None:
        return witness
    state = np.array((*x, *y))
    eps = math.radians(ss.first.half_width_deg)
    step = np.array((2*eps/(samples.grid[0]-1), 1/(samples.grid[1]-1))*2)
    best = witness
    offsets = np.asarray(list(product((-1, 0, 1), repeat=4)))
    for _ in range(config.pair_rounds):
        improved = False
        for candidate in state+offsets*step:
            _check_deadline(deadline)
            if not (-eps <= candidate[0] <= eps and -eps <= candidate[2] <= eps):
                continue
            px = ss.parameter_point(candidate[0], candidate[1], config.near_offset_m)
            py = ss.parameter_point(candidate[2], candidate[3], config.near_offset_m)
            if px is None or py is None:
                continue
            w = _pair_witness(ss, q, px, py, config)
            if w is not None and w.distance_m > best.distance_m:
                best, next_state, improved = w, candidate.copy(), True
        if improved:
            state = next_state
        else:
            step /= 2
    return best


def score_point(source_set: SourceSet, q: Point2, samples: SourceSamples, config: SearchConfig, deadline=None) -> Score:
    _check_deadline(deadline)
    ss, q = source_set, point(q)
    if (samples.augmentation_q == q and samples.direction_half_width_deg !=
            config.second_half_width_deg):
        extra = _direction_boundary_samples(ss, q, samples.grid[0],
                                            config.second_half_width_deg, samples.offset_m, deadline=deadline)
        samples = replace(samples, points=tuple(sorted(set(samples.points).union(extra))))
    if not samples.points:
        return Score(
            J_hat=None,
            near_score_m=None,
            direction_score_m=None,
            sample_count=0,
            witness=None,
            status='NUMERICAL_UNRESOLVED',
        )
    points = np.asarray(samples.points, dtype=float)
    if not ss.contains(points).all():
        raise ValueError('source samples must be actual legal F members')
    if q == ss.first.position:
        d = _sample_diameter(samples.points, config.policy)
        w = _pair_witness(ss, q, *d.endpoints, config, same_point=True)
        return Score(
            J_hat=d.length,
            near_score_m=None,
            direction_score_m=d.length,
            sample_count=len(points),
            witness=w,
            top_pairs=(w,),
            near_possibility='IMPOSSIBLE_BY_FIRST_DIRECTION',
        )
    points = points[np.linalg.norm(points-q, axis=1) <= ss.physics.rho_hi]
    if not len(points):
        return Score(
            J_hat=None,
            near_score_m=None,
            direction_score_m=None,
            sample_count=0,
            witness=None,
            status='NUMERICAL_UNRESOLVED',
        )
    a = points-q
    r = np.linalg.norm(a, axis=1)
    near_mask = r <= ss.physics.near_radius
    near_d = _sample_diameter(points[near_mask], config.policy)
    near_score, top = None, []
    if near_d is not None:
        near_score = near_d.length
        top.append(_pair_witness(ss, q, *near_d.endpoints, config))
    ids = np.flatnonzero(~near_mask)
    direction_score = 0. if len(ids) else None
    if len(ids):
        top.append(_pair_witness(ss, q, points[ids[0]], points[ids[0]], config))
    tan = math.tan(math.radians(2*config.second_half_width_deg))
    threshold_exploration = None
    for start in range(0, len(ids), config.block_size):
        _check_deadline(deadline)
        left = ids[start:start+config.block_size]
        aa, bb = a[left], a[ids]
        dot = aa @ bb.T
        det = aa[:, 0, None]*bb[None, :, 1]-aa[:, 1, None]*bb[None, :, 0]
        d2 = np.sum((points[left, None, :]-points[None, ids, :])**2, axis=2)
        slack = config.policy.angle_abs*r[left, None]*r[None, ids]
        band = (dot >= 0) & (np.abs(det) <= tan*dot+slack) & (left[:, None] < ids[None, :])
        if np.any(band):
            threshold_exploration = max(threshold_exploration or 0., math.sqrt(float(np.max(d2[band]))))
        flat = np.flatnonzero(band)
        if len(flat):
            keep = min(config.pair_starts*2, len(flat))
            while True:
                selected = flat[np.argpartition(d2.ravel()[flat], -keep)[-keep:]]
                chosen = selected[np.argsort(d2.ravel()[selected])[::-1]]
                legal_pairs = []
                for index in chosen:
                    _check_deadline(deadline)
                    i, j = np.unravel_index(index, dot.shape)
                    w = _pair_witness(ss, q, points[left[i]], points[ids[j]], config)
                    if w is not None:
                        legal_pairs.append(w)
                        if len(legal_pairs) >= config.pair_starts:
                            break
                if len(legal_pairs) >= config.pair_starts or keep == len(flat):
                    top.extend(legal_pairs)
                    if legal_pairs:
                        direction_score = max(direction_score, legal_pairs[0].distance_m)
                    break
                keep = min(len(flat), 2*keep)
        top = sorted((w for w in top if w is not None), key=lambda w: -w.distance_m)[:config.pair_starts]
    before = max(v for v in (near_score, direction_score) if v is not None)
    if config.refine_pairs:
        top = [_refine_pair(ss, q, w, samples, config, deadline=deadline) for w in top]
        for w in top:
            if w.branch == 'near':
                near_score = max(near_score or 0., w.distance_m)
            else:
                direction_score = max(direction_score or 0., w.distance_m)
    top.sort(key=lambda w: -w.distance_m)
    best = top[0] if top else None
    near_distance, _, attained = closure_distance(ss, q)
    possibility = ('POSSIBLE' if near_d is not None or near_distance < ss.physics.near_radius or
                   (near_distance == ss.physics.near_radius and attained) else
                   'IMPOSSIBLE' if near_distance > ss.physics.near_radius else 'BOUNDARY_UNRESOLVED')
    value = max(v for v in (near_score, direction_score) if v is not None)
    return Score(
        J_hat=value,
        near_score_m=near_score,
        direction_score_m=direction_score,
        sample_count=len(points),
        witness=best,
        top_pairs=tuple(top),
        near_possibility=possibility,
        local_improvement_m=value-before if config.refine_pairs else None,
        threshold_exploration_m=threshold_exploration,
    )


def short_baseline_lower_bound(source_set, a, b, budget_m, half_width_deg=1.):
    if not all(math.isfinite(v) for v in (a, b, budget_m, half_width_deg)) or budget_m < 0:
        raise ValueError('invalid lower-bound parameters')
    ss = source_set
    if not ss.physics.near_radius < a < b or budget_m >= a-ss.physics.near_radius:
        return None
    u = unit(math.radians(ss.first.bearing_deg))
    x, y = point(np.asarray(ss.first.position)+a*u), point(np.asarray(ss.first.position)+b*u)
    if not ss.contains([x, y]).all():
        return None
    angle = math.asin(budget_m/a)+math.asin(budget_m/b)
    if angle > 2*math.radians(half_width_deg):
        return None
    return {'lower_bound_m': b-a, 'budget_m': budget_m, 'pair': (x, y),
            'angle_bound_deg': math.degrees(angle), 'kind': 'analytic_impossibility_lower_bound',
            'requires_nonempty_budget_domain': True}


def same_ray_max_angle_deg(a, b, budget_m):
    """G3: outward-rounded upper bound on the disk's maximum angle (degrees).

    Inputs denote exact binary64 values. Evaluate the unchanged analytic formula
    with a private 50-decimal-digit mpmath.iv context, including interval pi.
    Converting its upper endpoint to float then stepping toward +inf encloses
    conversion rounding. This relies on the interval backend's inclusion contract,
    not on an assumed libm error bound. Zero budget has exactly zero angle.
    The unrestricted disk also bounds any signal/action-constrained subset.
    Use same_ray_max_angle_estimate_deg only for non-certifying fast estimates.
    """
    if not all(math.isfinite(v) for v in (a, b, budget_m)) or not 0 <= budget_m < a < b:
        raise ValueError('expected 0 <= budget < a < b')
    if budget_m == 0:
        return 0.
    from mpmath.ctx_iv import MPIntervalContext
    iv = MPIntervalContext()
    iv.dps = 50
    a, b, budget = (iv.mpf(float(v)) for v in (a, b, budget_m))
    angle = iv.atan2(budget*(b-a),
                     iv.sqrt((a*a-budget*budget)*(b*b-budget*budget)))*180/iv.pi
    return math.nextafter(float(angle.b), math.inf)


def same_ray_max_angle_estimate_deg(a, b, budget_m):
    """Non-certifying binary64 estimate of G3; never use to trigger a lower bound.

    Rounding can underestimate the angle, including rounding an angle strictly
    above a threshold onto that threshold. The default API uses interval bounds.
    """
    if not all(math.isfinite(v) for v in (a, b, budget_m)) or not 0 <= budget_m < a < b:
        raise ValueError('expected 0 <= budget < a < b')
    u, v = budget_m/a, budget_m/b
    return math.degrees(math.atan2(u*((b-a)/b),
                                   math.sqrt((1-u)*(1+u))*math.sqrt((1-v)*(1+v))))


def tight_short_baseline_lower_bound(source_set, a, b, budget_m, half_width_deg=1.):
    """G4, additional same-ray sufficient condition; the legacy API is unchanged.

    Applies to signal-guaranteeing stations within the budget. A failed condition
    says nothing about achievability. This is not the exact minimax value V(B).
    The angle test is conservative for exact binary64 radial/degree inputs:
    only an outward-rounded upper bound <= the threshold triggers the result.
    Unresolved boundary cases return None. Existing source/near geometry checks
    retain their original semantics; this is not a new geometry certificate.
    """
    if not all(math.isfinite(v) for v in (a, b, budget_m, half_width_deg)) or budget_m < 0 or not 0 <= half_width_deg <= 90:
        raise ValueError('invalid lower-bound parameters')
    ss = source_set
    if not ss.physics.near_radius < a < b or budget_m >= a-ss.physics.near_radius:
        return None
    u = unit(math.radians(ss.first.bearing_deg))
    x, y = point(np.asarray(ss.first.position)+a*u), point(np.asarray(ss.first.position)+b*u)
    if not ss.contains([x, y]).all():
        return None
    angle = same_ray_max_angle_deg(a, b, budget_m)
    # Multiplication by two is exact for the admitted binary64 widths [0, 90].
    # Written positively so a non-finite/unresolved angle cannot pass via NaN.
    if not angle <= 2*half_width_deg:
        return None
    return {'lower_bound_m': b-a, 'budget_m': budget_m, 'pair': (x, y),
            'angle_bound_deg': angle, 'kind': 'analytic_same_ray_tight_lower_bound',
            'requires_nonempty_budget_domain': True}


def source_pair_budget_lower_bound(source_set, x, y, budget_m, half_width_deg=1.):
    """G1/G2: sufficient budget bound for any actual first-compatible source pair.

    Adds their initial angular separation to the two movement deflections.
    Checks one supplied pair, not the supremum over all source pairs. Restricted
    to signal-guaranteeing stations; strict near exclusion is mandatory.
    """
    if not all(math.isfinite(v) for v in (budget_m, half_width_deg)) or budget_m < 0 or not 0 <= half_width_deg <= 90:
        raise ValueError('invalid lower-bound parameters')
    x, y = point(x), point(y)
    ss = source_set
    if not ss.contains([x, y]).all():
        return None
    rx, ry = distance(ss.first.position, x), distance(ss.first.position, y)
    if budget_m >= min(rx, ry)-ss.physics.near_radius:
        return None
    gamma = abs(angle_delta(bearing(ss.first.position, x), bearing(ss.first.position, y)))
    angle = gamma+math.degrees(math.asin(budget_m/rx)+math.asin(budget_m/ry))
    if angle > 2*half_width_deg:
        return None
    return {'lower_bound_m': distance(x, y), 'budget_m': budget_m, 'pair': (x, y),
            'angle_bound_deg': angle, 'initial_angle_deg': gamma,
            'kind': 'analytic_source_pair_budget_lower_bound',
            'requires_nonempty_budget_domain': True}


def candidate_bbox(ss, config):
    p0 = ss.actual_point
    if p0 is None:
        return None
    r = max(ss.physics.rho_lo, distance(p0, ss.first.position))
    x0, x1, y0, y1 = ss.physics.action_bounds
    box = [max(x0, p0[0]-r), min(x1, p0[0]+r), max(y0, p0[1]-r), min(y1, p0[1]+r)]
    if config.movement_budget_m is not None:
        b, s = config.movement_budget_m, ss.first.position
        box = [max(box[0], s[0]-b), min(box[1], s[0]+b), max(box[2], s[1]-b), min(box[3], s[1]+b)]
    return tuple(box)


def check_admissibility(ss, q, config):
    q = point(q)
    signal = check_candidate(ss, q, config.require_direction, config.policy)
    reasons = []
    if config.movement_budget_m is not None and distance(q, ss.first.position) > config.movement_budget_m:
        reasons.append('outside_movement_budget')
    if config.restrict_action_to_arena and distance(q, ss.physics.arena_center) > ss.physics.arena_radius:
        reasons.append('outside_added_arena_action_domain')
    return {'signal_check': signal, 'status': 'OUT' if reasons else signal.status,
            'action_admissible': not reasons, 'reasons': tuple(reasons)}


def _admissible(ss, q, config):
    assessment = check_admissibility(ss, q, config)
    return assessment['signal_check'] if assessment['status'] in ('IN', 'BOUNDARY') else None


def refinement_assessment(candidate, history=()):
    required = ('source', 'tolerance', 'shifted', 'local_refinement', 'common_final')
    audits = candidate.audit_values_m if candidate else {}
    missing = tuple(name for name in required if not audits.get(name))
    values = [v for seq in audits.values() for v in seq]
    if candidate and candidate.sensitivity_range_m:
        values.extend(candidate.sensitivity_range_m)
    if candidate and candidate.score.J_hat is not None:
        values.append(candidate.score.J_hat)
    spread = max(values)-min(values) if values else None
    threshold = max(.1, .01*candidate.score.J_hat) if candidate and candidate.score.J_hat is not None else None
    rank_flip = any(r.get('rank_flip') or r.get('coarse_to_fine_significant_flip') for r in history)
    stable = not missing and spread is not None and spread <= threshold and not rank_flip
    return {'status': 'STABLE_UNDER_REFINEMENT' if stable else 'NEEDS_REFINEMENT',
            'completed_comparisons': tuple(k for k in required if audits.get(k)),
            'not_evaluated': missing, 'completed_change_m': spread, 'threshold_m': threshold,
            'rank_flip': rank_flip,
            'tolerance_scope': 'score_threshold_and_near_offset_only; full_chain_audit_pending'}


def station_refinement_change(final, stage_winners):
    lookup = {r.q: r.score.J_hat for r in final}
    missing = tuple(i for i in range(3) if i >= len(stage_winners) or stage_winners[i] not in lookup)
    values = tuple(lookup[q] for q in stage_winners[:3] if q in lookup)
    return (max(values)-min(values) if not missing else None,
            {'stages': ('coarse_grid', 'fine_grid', 'station_local'),
             'values_m': values, 'not_evaluated_stage_indices': missing})


def _retained_points(scores):
    points = set()
    for score in scores:
        if score is None:
            continue
        for w in (*score.top_pairs, score.witness):
            if w is not None:
                points.update((w.x, w.y))
    return points


def _conditional_diagnostics(ss, q, score, samples, config, deadline=None):
    from .diagnostics import clearance_summary, angular_comparison
    if check_candidate(ss, q, False, config.policy).status != 'IN':
        return (), ()  # BOUNDARY does not establish the guaranteed-reception premise.
    points = set(samples.points) | _retained_points((score,))
    samples = replace(samples, points=tuple(sorted(points)))
    feedbacks = []
    if score.witness:
        w = score.witness
        feedbacks.append(Feedback(kind=w.branch, bearing_deg=w.common_bearing_deg, half_width_deg=config.second_half_width_deg))
    if score.near_score_m is not None and not any(f.kind == 'near' for f in feedbacks):
        feedbacks.append(Feedback(kind='near'))
    if not any(f.kind == 'direction' for f in feedbacks):
        for p in samples.points:
            if distance(p, q) > ss.physics.near_radius:
                feedbacks.append(Feedback(kind='direction', bearing_deg=bearing(q, p), half_width_deg=config.second_half_width_deg))
                break
    clear, angular = [], []
    for feedback in feedbacks:
        _check_deadline(deadline)
        clear.append(clearance_summary(ss, q, feedback, samples, config.policy))
        _check_deadline(deadline)
        if feedback.kind == 'direction':
            angular.append(angular_comparison(ss, q, feedback))
    _check_deadline(deadline)
    return tuple(clear), tuple(angular)


def boundary_point(ss, theta, config, deadline=None):
    s = np.asarray(ss.first.position)
    if not ss.physics.action_contains(s):
        return None
    upper = 2*ss.physics.rho_hi+distance(ss.actual_point, s)
    if config.movement_budget_m is not None:
        upper = min(upper, config.movement_budget_m)
    low = 0.
    # Convex C_sig is used here; C_dir and action ablations filter the generated points later.
    for _ in range(64):
        _check_deadline(deadline)
        if upper-low <= config.boundary_precision_m:
            break
        mid = (low+upper)/2
        q = point(s+mid*unit(theta))
        c = check_candidate(ss, q, False, config.policy)
        if c.status == 'IN':
            low = mid
        else:
            upper = mid
    return point(s+low*unit(theta))


def _choose_spread(records, count):
    ordered = sorted(records, key=lambda r: r.score.J_hat)
    selected = []
    for spacing in (50., 0.):
        for r in ordered:
            if r.q not in [s.q for s in selected] and all(distance(r.q, s.q) >= spacing for s in selected):
                selected.append(r)
                if len(selected) == count:
                    return selected
    return selected


def select_second_point(ss: SourceSet, config: SearchConfig, extra_points=()) -> Q2Result:
    started = time.monotonic()
    deadline = started+config.time_budget_s
    history, completed, grid_records, records, cache = [], [], [], {}, {}
    evaluations = 0
    def counted_score(*args, **kwargs):
        nonlocal evaluations
        evaluations += 1
        return score_point(*args, **kwargs)
    samples_by_level = {}
    baseline = None
    stage_winners = []
    completed_fair = ()
    def expired():
        return time.monotonic() >= deadline
    def samples(level):
        if level not in samples_by_level:
            samples_by_level[level] = sample_sources(ss, level, config.source_grids, inward=config.near_offset_m, deadline=deadline, second_half_width_deg=config.second_half_width_deg)
        return samples_by_level[level]
    def evaluate(q, level):
        _check_deadline(deadline)
        q = point(q)
        check = _admissible(ss, q, config)
        if check is None:
            return None
        if check.status == 'BOUNDARY' and ss.physics.action_contains(ss.first.position):
            for fraction in (1e-8, 1e-6):
                adjusted = point((1-fraction)*np.asarray(q)+fraction*np.asarray(ss.first.position))
                interior = _admissible(ss, adjusted, config)
                if interior is not None and interior.status == 'IN':
                    q, check = adjusted, interior
                    break
        key = (q, level)
        if key not in cache:
            score = counted_score(ss, q, samples(level), replace(config, refine_pairs=False), deadline=deadline)
            if score.J_hat is None:
                return None
            cache[key] = CandidateResult(q=q, check=check, score=score, movement_m=distance(q, ss.first.position))
        result = cache[key]
        records[q] = result
        return result
    def output(status='NUMERICAL_CANDIDATE', reason='COMPLETED', final=(), tie=None):
        eligible = list(final) if final else [v for v in records.values() if v.q != ss.first.position]
        if eligible and not final:
            # Interrupted mixed stages are compared at the common coarse setting.
            eligible = [cache[(v.q, 0)] for v in eligible if (v.q, 0) in cache]
        if eligible:
            threshold = tie if tie is not None else config.tie_floor_m
            best_value = min(v.score.J_hat for v in eligible)
            best = min((r for r in eligible if r.score.J_hat <= best_value+threshold), key=lambda r: (r.movement_m, r.q))
        else:
            best = None
        station_change, station_audit = station_refinement_change(final, stage_winners)
        assessment = refinement_assessment(best, history)
        assessment['station_comparison'] = station_audit
        assessment['reception_guarantee'] = ('PROVEN' if best and best.check.status == 'IN'
                                               else 'UNRESOLVED')
        stability = assessment['status']
        clear, angular = (), ()
        if best and final and not expired():
            clear, angular = _conditional_diagnostics(ss, best.q, best.score, samples_by_level[2], config, deadline=deadline)
        assessment['conditional_diagnostics'] = 'COMPLETED' if clear else 'NOT_EVALUATED'
        improvement = None
        if best and baseline:
            spread = (best.sensitivity_range_m[1]-best.sensitivity_range_m[0]
                      if best.sensitivity_range_m else math.inf)
            improvement = ('NO_CLEAR_NUMERICAL_IMPROVEMENT' if baseline.J_hat-best.score.J_hat <= spread
                           else 'NUMERICAL_IMPROVEMENT')
        return Q2Result(
            q_best=best.q if best else None,
            candidate_check=best.check if best else None,
            score=best.score if best else None,
            movement_m=best.movement_m if best else None,
            movement_seconds=best.movement_m/5 if best else None,
            measurement_seconds=5. if best else None,
            alternatives=tuple(eligible),
            refinement_history=tuple(history),
            sensitivity_range_m=best.sensitivity_range_m if best else None,
            source_change_m=best.source_change_m if best else None,
            station_change_m=station_change,
            tolerance_change_m=best.tolerance_change_m if best else None,
            stability=stability,
            status=status,
            stop_reason=reason,
            completed_stages=tuple(completed),
            evaluations=evaluations,
            elapsed_seconds=time.monotonic()-started,
            config=config,
            first=ss.first,
            physics=ss.physics,
            grid_records=tuple(grid_records),
            baseline=baseline,
            tie_threshold_m=tie,
            improvement_status=improvement,
            angular_comparison=angular,
            clearance_diagnostics=clear,
            numerical_assessment=assessment,
        )
    try:
        if ss.status != 'OK':
            return output('INCONSISTENT_FIRST_OBSERVATION', ss.status)
        if config.movement_budget_m == 0:
            baseline = counted_score(ss, ss.first.position, samples(0), config, deadline=deadline)
            return output('NO_DISTINCT_CANDIDATE', 'ZERO_BUDGET_EXCLUDES_S')
        if config.restrict_action_to_arena and config.movement_budget_m is not None:
            if distance(ss.first.position, ss.physics.arena_center) > ss.physics.arena_radius+config.movement_budget_m:
                return output('EMPTY_ADMISSIBLE_SET', 'BUDGET_DISJOINT_FROM_ADDED_ARENA_ACTION_CONSTRAINT')
        if expired():
            return output('NUMERICAL_UNRESOLVED', 'TIME_BUDGET')
        baseline = counted_score(ss, ss.first.position, samples(0), config, deadline=deadline)
        evaluate(ss.first.position, 0)
        box = candidate_bbox(ss, config)
        if box[0] > box[1] or box[2] > box[3]:
            return output('EMPTY_ADMISSIBLE_SET', 'ADDITIONAL_ACTION_CONSTRAINTS')
        extras = list(extra_points)
        boundary_records = []
        for theta in np.arange(0, 360, config.boundary_step_deg):
            q = boundary_point(ss, math.radians(theta), config, deadline=deadline)
            if q is not None:
                extras.extend((q, point(.999*np.asarray(q)+.001*np.asarray(ss.first.position))))
                boundary_records.append((math.radians(theta), q))
        u = unit(math.radians(ss.first.bearing_deg))
        v = np.array((-u[1], u[0]))
        s = np.asarray(ss.first.position)
        for sign in (-1, 1):
            extras.extend((point(s+sign*200*v), point(s+200*u+sign*200*v),
                           point(s+750*u+sign*750*v)))
        for q in extras:
            if expired():
                return output(reason='TIME_BUDGET')
            evaluate(q, 0)
        for step in config.station_steps_m:
            xs = np.arange(math.ceil(box[0]/step)*step, box[1]+step*1e-10, step)
            ys = np.arange(math.ceil(box[2]/step)*step, box[3]+step*1e-10, step)
            scanned = 0
            for index, (x, y) in enumerate(product(xs, ys)):
                if expired():
                    history.append({'stage': 'grid', 'step_m': step, 'scanned': scanned, 'planned': len(xs)*len(ys), 'complete': False})
                    grid_records.extend({'q': (float(xx), float(yy)), 'step_m': step,
                                         'status': 'NOT_EVALUATED', 'diameter_estimate_m': None}
                                        for j, (xx, yy) in enumerate(product(xs, ys)) if j >= index)
                    return output(reason='TIME_BUDGET')
                r = evaluate((x, y), 0)
                grid_records.append({'q': (float(x), float(y)), 'step_m': step,
                                     'status': r.check.status if r else 'OUT',
                                     'diameter_estimate_m': r.score.J_hat if r else None})
                scanned += 1
            history.append({'stage': 'grid', 'step_m': step, 'scanned': scanned, 'planned': len(xs)*len(ys), 'complete': True})
            completed.append(f'grid_{step:g}m')
            distinct = [r for r in records.values() if r.q != ss.first.position]
            if distinct:
                stage_winners.append(min(distinct, key=lambda r: r.score.J_hat).q)
        distinct = [r for r in records.values() if r.q != ss.first.position]
        if not distinct:
            return output('NUMERICAL_UNRESOLVED', 'NO_DISTINCT_POINT_FOUND_IN_FINITE_SEARCH')
        starts = _choose_spread(distinct, config.starts)
        for sign in (-1, 1):
            side = [r for r in distinct if sign*np.dot(np.asarray(r.q)-s, v) > 0]
            if side:
                r = min(side, key=lambda r: r.score.J_hat)
                if r.q not in [x.q for x in starts]:
                    starts.append(r)
        boundary_options = [records[q] for _, q in boundary_records if q in records and q != ss.first.position]
        if boundary_options:
            b = min(boundary_options, key=lambda r: r.score.J_hat)
            if b.q not in [r.q for r in starts]:
                starts.append(b)
        local = []
        for initial in starts:
            current = evaluate(initial.q, 1)
            step = config.station_initial_step_m
            while step >= config.station_min_step_m:
                if expired():
                    return output(reason='TIME_BUDGET')
                neighbours = [current]
                for dx, dy in product((-step, 0., step), repeat=2):
                    q = point(np.asarray(current.q)+(dx, dy))
                    if q == ss.first.position:
                        continue
                    r = evaluate(q, 1)
                    if r:
                        neighbours.append(r)
                best = min(neighbours, key=lambda r: (r.score.J_hat, r.movement_m))
                if best.score.J_hat < current.score.J_hat:
                    current = best
                else:
                    step /= 2
            local.append(current.q)
        if boundary_options:
            theta = math.atan2(b.q[1]-s[1], b.q[0]-s[0])
            angular_step = math.radians(config.boundary_step_deg/2)
            for _ in range(8):
                options = []
                for angle in (theta-angular_step, theta, theta+angular_step):
                    q = boundary_point(ss, angle, config, deadline=deadline)
                    if q is not None:
                        for inward in (1., .999):
                            r = evaluate(point(s+inward*(np.asarray(q)-s)), 1)
                            if r and r.q != ss.first.position:
                                options.append((r, angle))
                if options:
                    r, theta = min(options, key=lambda item: item[0].score.J_hat)
                    local.append(r.q)
                angular_step /= 2
                if expired():
                    return output(reason='TIME_BUDGET')
        completed.append('station_local_refinement')
        if local:
            stage_winners.append(min(local, key=lambda q: records[q].score.J_hat))
        local = list(dict.fromkeys(local+stage_winners))
        # Add spatially dispersed rejected regions to the independent shifted-source audit.
        audit = _choose_spread([r for r in distinct if r.q not in local], min(4, len(distinct)))
        local.extend(r.q for r in audit)
        station_audits = []
        half_step = config.station_min_step_m/2
        for q in tuple(local):
            if expired():
                return output(reason='TIME_BUDGET')
            origin_score = evaluate(q, 1)
            options = [origin_score]
            for dx, dy in product((-half_step, half_step), repeat=2):
                candidate = point(np.asarray(q)+(dx, dy))
                if candidate != ss.first.position:
                    candidate_score = evaluate(candidate, 1)
                    if candidate_score:
                        options.append(candidate_score)
            best = min(options, key=lambda r: r.score.J_hat)
            station_audits.append(best.q)
        local = list(dict.fromkeys(local+station_audits))
        history.append({'stage': 'shifted_station_audit', 'offset_m': half_step,
                        'positions': tuple(station_audits)})
        common = samples(2)
        additions = set(common.points)
        refined, counts = {}, {}
        final_config = replace(config, refine_pairs=True)
        for q in local:
            if expired():
                return output(reason='TIME_BUDGET')
            near_samples = sample_sources(ss, 2, config.source_grids, q, second_half_width_deg=config.second_half_width_deg, deadline=deadline, inward=config.near_offset_m)
            counts[q] = near_samples.additional_count
            additions.update(near_samples.points)
            score = counted_score(ss, q, near_samples, final_config, deadline=deadline)
            refined[q] = score
            for w in score.top_pairs:
                additions.update((w.x, w.y))
        common = replace(common, points=tuple(sorted(additions)), additional_count=len(additions)-len(common.points))
        # Freeze this sample generation for every finalist. Source/tolerance
        # audits below describe their own generations, not a full-chain S7 bound.
        final = []
        shifted = sample_sources(ss, 2, config.source_grids, inward=config.near_offset_m, shifted=True, deadline=deadline, second_half_width_deg=config.second_half_width_deg)
        audit_samples = replace(common, points=tuple(sorted(set(common.points) | set(shifted.points))))
        for q in local:
            if expired():
                return output(reason='TIME_BUDGET')
            score = counted_score(ss, q, common, final_config, deadline=deadline)
            source_values = tuple(counted_score(ss, q, samples(k), replace(config, refine_pairs=False), deadline=deadline).J_hat for k in range(3))
            shifted_score = counted_score(ss, q, audit_samples, final_config, deadline=deadline)
            # Witness points from independent audit become common input for the final fair pass.
            for w in shifted_score.top_pairs:
                additions.update((w.x, w.y))
            tol_values = []
            for factor in (.1, 10.):
                policy = replace(config.policy, length_abs=config.policy.length_abs*factor,
                                 relative=config.policy.relative*factor, angle_abs=config.policy.angle_abs*factor)
                varied = sample_sources(ss, 2, config.source_grids, q, second_half_width_deg=config.second_half_width_deg, deadline=deadline, inward=config.near_offset_m*factor)
                varied = replace(varied, points=tuple(sorted(set(common.points) | set(varied.points))))
                tol_values.append(counted_score(ss, q, varied, replace(final_config, policy=policy), deadline=deadline).J_hat)
            values = (*source_values, score.J_hat, shifted_score.J_hat, *tol_values)
            final.append(CandidateResult(q=q, check=_admissible(ss, q, config), score=score, movement_m=distance(q, s), source_values_m=source_values, sensitivity_range_m=(min(values), max(values)), source_change_m=abs(source_values[-1]-source_values[-2]), tolerance_change_m=max(tol_values+[score.J_hat])-min(tol_values+[score.J_hat]), additional_samples=counts[q], audit_values_m={'source': source_values, 'tolerance': tuple([score.J_hat]+tol_values),
                                          'shifted': (score.J_hat, shifted_score.J_hat),
                                          'local_refinement': (refined[q].J_hat-(refined[q].local_improvement_m or 0.), refined[q].J_hat)}))
        # Freeze the union after shifted audit; old audit values remain historical
        # comparisons and common_final records the change to this generation.
        common = replace(audit_samples, points=tuple(sorted(set(audit_samples.points) | additions)))
        fair = []
        for r in final:
            if expired():
                return output(reason='TIME_BUDGET')
            score = counted_score(ss, r.q, common, final_config, deadline=deadline)
            fair.append(replace(r, score=score, sensitivity_range_m=(min(r.sensitivity_range_m[0], score.J_hat),
                                                                   max(r.sensitivity_range_m[1], score.J_hat)),
                                audit_values_m=dict(r.audit_values_m, common_final=(r.score.J_hat, score.J_hat))))
        samples_by_level[2] = common
        baseline = counted_score(ss, ss.first.position, common, config, deadline=deadline)
        completed.extend(('common_final_reassessment', 'source_tolerance_shifted_audit'))
        completed_fair = tuple(fair)
        before_order = [r.q for r in sorted(final, key=lambda r: r.score.J_hat)]
        after_order = [r.q for r in sorted(fair, key=lambda r: r.score.J_hat)]
        coarse_best = min(local, key=lambda q: counted_score(ss, q, samples(0), replace(config, refine_pairs=False), deadline=deadline).J_hat)
        final_best = min(fair, key=lambda r: r.score.J_hat)
        coarse_final = next(r for r in fair if r.q == coarse_best)
        significant_flip = coarse_final.score.J_hat-final_best.score.J_hat > max(.1, .01*final_best.score.J_hat)
        history.append({'stage': 'final_common_samples', 'count': len(common.points), 'rank_flip': before_order != after_order,
                        'coarse_to_fine_significant_flip': significant_flip,
                        'shifted_source_count': len(shifted.points), 'audited_rejected_regions': len(audit)})
        if significant_flip and not expired():
            # A rank reversal triggers a complete medium-source rescan, not a preferred-region rescan.
            step = config.station_steps_m[-1]
            xs = np.arange(math.ceil(box[0]/step)*step, box[1]+step*1e-10, step)
            ys = np.arange(math.ceil(box[2]/step)*step, box[3]+step*1e-10, step)
            rescanned, rescue = 0, []
            for x, y in product(xs, ys):
                if expired():
                    break
                r = evaluate((x, y), 1)
                if r is not None and r.q != ss.first.position:
                    rescue.append(r)
                rescanned += 1
            history.append({'stage': 'rank_flip_medium_rescan', 'scanned': rescanned,
                            'planned': len(xs)*len(ys), 'complete': rescanned == len(xs)*len(ys)})
            if rescanned == len(xs)*len(ys):
                completed.append('rank_flip_medium_rescan')
            new_qs = [r.q for r in _choose_spread(rescue, config.starts) if r.q not in local]
            new_records = []
            for q in new_qs:
                if expired():
                    break
                extra = sample_sources(ss, 2, config.source_grids, q, second_half_width_deg=config.second_half_width_deg, deadline=deadline, inward=config.near_offset_m)
                additions.update(extra.points)
                score = counted_score(ss, q, extra, final_config, deadline=deadline)
                for w in score.top_pairs:
                    additions.update((w.x, w.y))
                new_records.append(CandidateResult(q=q, check=_admissible(ss, q, config), score=score, movement_m=distance(q, s)))
            if new_records and not expired():
                # Rescue adds a generation: commit only after all candidates
                # finish on its frozen union; earlier audits keep their scope.
                rescue_common = replace(common, points=tuple(sorted(set(common.points) | additions)))
                updated = []
                for r in fair+new_records:
                    if expired():
                        break
                    score = counted_score(ss, r.q, rescue_common, final_config, deadline=deadline)
                    old_range = r.sensitivity_range_m
                    updated.append(replace(r, score=score, sensitivity_range_m=(min(old_range[0], score.J_hat),
                                            max(old_range[1], score.J_hat)) if old_range else None,
                                           audit_values_m=dict(r.audit_values_m, common_final=(*r.audit_values_m.get('common_final', (r.score.J_hat,)), score.J_hat))))
                if len(updated) == len(fair)+len(new_records):
                    fair, common = updated, rescue_common
                    completed_fair = tuple(fair)
                    samples_by_level[2] = common
                    completed.append('rank_flip_fair_final_reassessment')
        if significant_flip and expired():
            return output(reason='TIME_BUDGET', final=fair)
        spread = max((r.sensitivity_range_m[1]-r.sensitivity_range_m[0] for r in fair if r.sensitivity_range_m), default=0.)
        tie = config.tie_multiplier*max(config.tie_floor_m, spread)
        return output(final=fair, tie=tie)
    except _BudgetExpired:
        return output(reason='TIME_BUDGET', final=completed_fair)


def movement_frontier(source_set: SourceSet, budgets_m: Sequence[float], config: SearchConfig) -> tuple[Q2Result, ...]:
    """Each search gets time_budget_s; the shared comparison gets one extra such budget.

    Interrupted shared work preserves the original search results, explicitly
    marked as not comparable on common samples. No partial scores are committed.
    """
    budgets = sorted(set(float(b) for b in budgets_m))
    if any(not math.isfinite(b) or b < 0 for b in budgets):
        raise ValueError('nonnegative finite budgets required')
    results, candidates = [], set()
    for budget in budgets:
        result = select_second_point(source_set, replace(config, movement_budget_m=budget), candidates)
        candidates.update(r.q for r in result.alternatives)
        results.append(result)
    if not results or source_set.status != 'OK':
        return tuple(results)
    shared_evaluations = 0
    def counted_score(*args, **kwargs):
        nonlocal shared_evaluations
        shared_evaluations += 1
        return score_point(*args, **kwargs)
    started = time.monotonic()
    deadline = started+config.time_budget_s
    try:
        common = sample_sources(source_set, 2, config.source_grids, inward=config.near_offset_m, deadline=deadline, second_half_width_deg=config.second_half_width_deg)
        points = set(common.points)
        retained = set()
        for result in results:
            retained.update(_retained_points((result.score, result.baseline, *(r.score for r in result.alternatives))))
            if result.q_best is not None:
                candidates.add(result.q_best)
        points.update(retained)
        candidates.discard(source_set.first.position)
        candidates = sorted(q for q in candidates if _admissible(source_set, q, replace(config, movement_budget_m=None)))
        for q in candidates:
            _check_deadline(deadline)
            points.update(sample_sources(source_set, 2, config.source_grids, q, second_half_width_deg=config.second_half_width_deg, deadline=deadline, inward=config.near_offset_m).points)
        common = replace(common, points=tuple(sorted(points)))
        fine = replace(config, refine_pairs=True)
        preliminary = {q: counted_score(source_set, q, common, fine, deadline=deadline) for q in candidates}
        retained.update(_retained_points(preliminary.values()))
        points.update(retained)
        common = replace(common, points=tuple(sorted(points)))
        scores = {q: counted_score(source_set, q, common, fine, deadline=deadline) for q in candidates}
        baseline = counted_score(source_set, source_set.first.position, common, fine, deadline=deadline)
        retained.update(_retained_points((*scores.values(), baseline)))
        diagnostic_samples = replace(common, points=tuple(sorted(set(common.points) | retained)))
        # No old fixed-q audit is valid for this new sample/feedback generation.
        output = []
        tie = max([config.tie_multiplier*config.tie_floor_m]+[r.tie_threshold_m or 0. for r in results])
        for budget, old in zip(budgets, results):
            _check_deadline(deadline)
            cfg = replace(config, movement_budget_m=budget)
            alternatives = []
            for q in candidates:
                check = _admissible(source_set, q, cfg)
                if check is not None and scores[q].J_hat is not None:
                    alternatives.append(CandidateResult(q=q, check=check, score=scores[q],
                        movement_m=distance(q, source_set.first.position)))
            alternatives = tuple(alternatives)
            minimum, best = None, None
            if alternatives:
                minimum = min(r.score.J_hat for r in alternatives)
                tied = [r for r in alternatives if r.score.J_hat <= minimum+tie]
                best = min(tied, key=lambda r: (r.movement_m, r.q))
            clear, angular = _conditional_diagnostics(source_set, best.q, best.score, diagnostic_samples, cfg, deadline=deadline) if best else ((), ())
            assessment = refinement_assessment(best)
            assessment.update(reception_guarantee='PROVEN' if best and best.check.status == 'IN' else 'UNRESOLVED',
                              conditional_diagnostics='COMPLETED' if clear else 'NOT_EVALUATED',
                              station_comparison={'status': 'NOT_EVALUATED'},
                              reason='frontier_final_samples_changed; prior_comparisons_invalidated')
            history = old.refinement_history+({'stage': 'frontier_common_reassessment',
                      'samples': len(common.points), 'minimum_estimate_m': minimum, 'tie_threshold_m': tie,
                      'retained_witness_points': tuple(sorted(retained)),
                      'prior_stages_scope': 'search_history_only_not_current_fixed_q_audits'},)
            output.append(replace(old, q_best=best.q if best else None, score=best.score if best else None,
                                  candidate_check=best.check if best else None,
                                  movement_m=best.movement_m if best else None,
                                  movement_seconds=best.movement_m/5 if best else None,
                                  measurement_seconds=5. if best else None, baseline=baseline,
                                  alternatives=alternatives, tie_threshold_m=tie,
                                  sensitivity_range_m=None, source_change_m=None, station_change_m=None,
                                  tolerance_change_m=None, stability='NEEDS_REFINEMENT', improvement_status=None,
                                  clearance_diagnostics=clear, angular_comparison=angular, config=cfg,
                                  status='NUMERICAL_CANDIDATE' if best else old.status,
                                  completed_stages=('frontier_common_reassessment',),
                                  refinement_history=history, numerical_assessment=assessment))
        _check_deadline(deadline)
        # Store the shared cost once, on the first row; per-search counters and
        # elapsed_seconds exclude it, so summing the frontier cannot double bill.
        output[0] = replace(output[0], frontier_shared_evaluations=shared_evaluations,
                            frontier_shared_elapsed_seconds=time.monotonic()-started)
        return tuple(output)
    except _BudgetExpired:
        results[0] = replace(results[0], frontier_shared_evaluations=shared_evaluations,
                             frontier_shared_elapsed_seconds=time.monotonic()-started)
        return tuple(replace(r, stop_reason='FRONTIER_COMMON_TIME_BUDGET',
                             numerical_assessment=dict(r.numerical_assessment,
                                 frontier_common_comparison='NOT_COMPLETED',
                                 frontier_budget_scope='per_search_plus_one_shared_budget'))
                     for r in results)
