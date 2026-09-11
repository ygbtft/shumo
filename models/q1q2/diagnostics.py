"""Conditional coverage/action evidence, area diagnostics and reproducible cases."""
from __future__ import annotations
from dataclasses import dataclass, replace
import math
import numpy as np
from .geometry import (Point2, NumericPolicy, BearingMeasurement, point, unit,
                       distance, angle_delta, bearing)
from .circle import minimum_circle, ordinary_three_point_circle
from .feasible import (SourceSet, Feedback, build_source_set, posterior_contains,
                       posterior_outer_polygon, check_candidate, closure_distance)
from .q2 import SourceSamples

# Virtual action cost after the current measurement: movement plus clearing;
# excludes the current measurement and solver wall-clock time.
_CLEAR_SECONDS = 5.
_MOVE_SPEED_M_S = 5.
_OUTER_SIDES = (32, 64)
_OUTER_REFINE_MARGIN_M = .1


@dataclass(frozen=True)
class ClearanceSummary:
    feedback: Feedback
    R_hat: float | None
    estimated_center: Point2 | None
    support_points: tuple[Point2, ...]
    r_U: float | None
    cover_center: Point2 | None
    H_U: float | None
    status: str
    evidence: str
    residual: float | None
    threshold_margin_m: float | None
    outer_sides: int
    subsequent_movement_seconds: float | None
    subsequent_total_seconds: float | None
    must_move_proven: bool = False
    impossibility_witness: tuple[Point2, ...] = ()
    reason: str = ''
    conditional: bool = True
    radius_label: str = 'conditional_R_estimate_not_J_R'
    outer_vertices: tuple[Point2, ...] = ()
    clearance_radius_m: float = 20.


def clearance_summary(source_set: SourceSet, q: Point2, feedback: Feedback,
                      samples: SourceSamples, policy: NumericPolicy) -> ClearanceSummary:
    # Feedback is conditional on an accepted observation consistent with this model.
    # An empty sample alone is not a proof of an impossible feedback.
    ss, p = source_set, source_set.physics
    reason = None
    if ss.status != 'OK':
        reason = 'inconsistent_first_observation'
    elif point(q) == ss.first.position and (feedback.kind != 'direction' or
            angle_delta(feedback.bearing_deg, ss.first.bearing_deg) != 0):
        reason = 'contradicts_fixed_first_feedback'
    elif feedback.kind == 'near' and closure_distance(ss, q)[0] > p.near_radius:
        reason = 'near_disjoint_from_source_closure'
    if reason:
        return ClearanceSummary(
            feedback=feedback,
            R_hat=None,
            estimated_center=None,
            support_points=(),
            r_U=None,
            cover_center=None,
            H_U=None,
            status='INCONSISTENT_FEEDBACK',
            evidence='analytic_contradiction',
            residual=None,
            threshold_margin_m=None,
            outer_sides=0,
            subsequent_movement_seconds=None,
            subsequent_total_seconds=None,
            reason=reason,
        )
    if check_candidate(ss, q, False, policy).status != 'IN':
        return ClearanceSummary(
            feedback=feedback,
            R_hat=None,
            estimated_center=None,
            support_points=(),
            r_U=None,
            cover_center=None,
            H_U=None,
            status='RECEPTION_UNRESOLVED',
            evidence='reception_not_proven',
            residual=None,
            threshold_margin_m=None,
            outer_sides=0,
            subsequent_movement_seconds=None,
            subsequent_total_seconds=None,
            reason='requires_guaranteed_reception',
        )
    pts = np.asarray(samples.points, dtype=float).reshape(-1, 2)
    pts = pts[posterior_contains(ss, q, feedback, pts, policy)]
    circle = minimum_circle(pts, seed=0)
    supports = tuple(point(pts[i]) for i in circle.support_vertex_indices)
    if feedback.kind == 'near':
        return ClearanceSummary(
            feedback=feedback,
            R_hat=circle.radius,
            estimated_center=circle.center,
            support_points=supports,
            r_U=p.near_radius,
            cover_center=point(q),
            H_U=p.near_radius,
            status='ON_SITE',
            evidence='near_analytic',
            residual=0.,
            threshold_margin_m=p.clearance_radius-p.near_radius,
            outer_sides=0,
            subsequent_movement_seconds=0.,
            subsequent_total_seconds=_CLEAR_SECONDS,
            reason='K subset D(q, near_radius); clear remains a separate action',
            clearance_radius_m=p.clearance_radius,
        )
    margin = max(policy.length(p.arena_radius)*16, 1e-8)
    r_upper = h_upper = residual = None
    center, outer_vertices, sides_used = None, (), 0
    for sides in _OUTER_SIDES:
        outer = posterior_outer_polygon(ss, q, feedback, sides)
        sides_used = sides
        if outer.status != 'OK' or not outer.vertices:
            break
        c = minimum_circle(outer.vertices, seed=0)
        if c.status != 'OK' or c.center is None:
            break
        residual = max(outer.residual or 0., c.containment_residual or 0.)
        if residual > margin:
            break
        outer_vertices = outer.vertices
        center = c.center
        r_upper = max(distance(center, v) for v in outer.vertices)+margin
        h_upper = max(distance(q, v) for v in outer.vertices)+margin
        if min(abs(r_upper-p.clearance_radius), abs(h_upper-p.clearance_radius)) > max(_OUTER_REFINE_MARGIN_M, 8*margin):
            break
    on_site_impossible = any(distance(x, q) > p.clearance_radius+margin for x in pts)
    if h_upper is not None and h_upper < p.clearance_radius-margin:
        return ClearanceSummary(
            feedback=feedback,
            R_hat=circle.radius,
            estimated_center=circle.center,
            support_points=supports,
            r_U=r_upper,
            cover_center=center,
            H_U=h_upper,
            status='ON_SITE',
            evidence='outer_polygon_float64_checked',
            residual=residual,
            threshold_margin_m=p.clearance_radius-h_upper,
            outer_sides=sides_used,
            subsequent_movement_seconds=0.,
            subsequent_total_seconds=_CLEAR_SECONDS,
            outer_vertices=outer_vertices,
            clearance_radius_m=p.clearance_radius,
        )
    if r_upper is not None and r_upper < p.clearance_radius-margin:
        move = distance(q, center)/_MOVE_SPEED_M_S
        return ClearanceSummary(
            feedback=feedback,
            R_hat=circle.radius,
            estimated_center=circle.center,
            support_points=supports,
            r_U=r_upper,
            cover_center=center,
            H_U=h_upper,
            status='MOVE_TO_COVER_CENTER',
            evidence='outer_polygon_float64_checked',
            residual=residual,
            threshold_margin_m=p.clearance_radius-r_upper,
            outer_sides=sides_used,
            subsequent_movement_seconds=move,
            subsequent_total_seconds=move+_CLEAR_SECONDS,
            must_move_proven=on_site_impossible,
            reason='movement plan found; necessity of moving is separately recorded',
            outer_vertices=outer_vertices,
            clearance_radius_m=p.clearance_radius,
        )
    evidence, witness = 'sampling_only', ()
    if circle.status == 'OK' and supports:
        # At most three individually rechecked common-feedback points are enough.
        c = ordinary_three_point_circle(supports)
        if c.status == 'OK' and c.radius > p.clearance_radius+margin:
            witness = supports
            evidence = 'impossible_pair' if len(supports) == 2 else 'impossible_triple'
    return ClearanceSummary(
        feedback=feedback,
        R_hat=circle.radius,
        estimated_center=circle.center,
        support_points=supports,
        r_U=r_upper,
        cover_center=center,
        H_U=h_upper,
        status='NOT_YET_GUARANTEED',
        evidence=evidence,
        residual=residual,
        threshold_margin_m=None if r_upper is None else p.clearance_radius-r_upper,
        outer_sides=sides_used,
        subsequent_movement_seconds=None,
        subsequent_total_seconds=None,
        must_move_proven=on_site_impossible,
        impossibility_witness=witness,
        reason='impossible_single_guaranteed_clear' if witness else 'insufficient_evidence',
        outer_vertices=outer_vertices,
        clearance_radius_m=p.clearance_radius,
    )


def e20_outer_sufficient(summary: ClearanceSummary, landing: Point2, policy: NumericPolicy) -> bool:
    # Near uses its analytic disk; direction uses the saved tangent-polygon
    # outer approximation with a strict policy.length margin, not an interval
    # certificate for all production geometry intermediates.
    radius = summary.clearance_radius_m
    if summary.feedback.kind == 'near' and summary.cover_center is not None:
        return distance(landing, summary.cover_center)+summary.r_U < radius-policy.length(radius)
    if not summary.outer_vertices:
        return False
    return max(distance(landing, p) for p in summary.outer_vertices) < radius-policy.length(radius)


def worst_radius_scale(diameter_m):
    """Mathematical J_R bounds for a true J, never a guarantee derived from J_hat."""
    if diameter_m < 0 or not math.isfinite(diameter_m):
        raise ValueError('finite nonnegative true diameter required')
    return diameter_m/2, diameter_m/math.sqrt(3)


@dataclass(frozen=True)
class DiagnosticConfig:
    half_widths_deg: tuple[float, float] = (1., 1.)
    enable_gdop: bool = False
    reference_length_m: float = 1000.
    source_origin: str = 'assumed_source'


@dataclass(frozen=True)
class GeometryDiagnostic:
    r1: float
    r2: float
    phi_deg: float
    linear_area_m2: float | None
    gdop: float | None
    status: str
    source_origin: str
    auxiliary_model: str | None = None


def compare_geometry(source: Point2, stations: tuple[Point2, Point2], config: DiagnosticConfig) -> GeometryDiagnostic:
    source = point(source)
    r1, r2 = (distance(source, p) for p in stations)
    phi = angle_delta(bearing(stations[1], source), bearing(stations[0], source))
    sine = abs(math.sin(math.radians(phi)))
    if min(r1, r2) <= 5:
        return GeometryDiagnostic(
            r1=r1,
            r2=r2,
            phi_deg=phi,
            linear_area_m2=None,
            gdop=None,
            status='NEAR_NOT_APPLICABLE',
            source_origin=config.source_origin,
        )
    singular = sine <= 1e-15
    e1, e2 = map(math.radians, config.half_widths_deg)
    area = math.inf if singular else 4*r1*r2*e1*e2/sine
    gdop = None
    # Only this optional diagnostic assumes local Gaussian error; the bounded
    # angle model and worst-case objective do not assign source probabilities.
    if config.enable_gdop:
        if config.reference_length_m <= 0:
            raise ValueError('positive GDOP reference length required')
        gdop = math.inf if singular else math.hypot(r1, r2)/(config.reference_length_m*sine)
    return GeometryDiagnostic(
        r1=r1,
        r2=r2,
        phi_deg=phi,
        linear_area_m2=area,
        gdop=gdop,
        status='SINGULAR' if singular else 'LOCAL_LINEAR_APPROXIMATION',
        source_origin=config.source_origin,
        auxiliary_model='optional_local_gaussian_GDOP_only' if config.enable_gdop else None,
    )


def angular_comparison(ss, q, feedback):
    from .q1 import solve
    if feedback.kind != 'direction':
        return {'status': 'NOT_APPLICABLE', 'feedback': feedback}
    measurements = (ss.first,) if point(q) == ss.first.position else (
        ss.first, BearingMeasurement(
            position=q,
            bearing_deg=feedback.bearing_deg,
            half_width_deg=feedback.half_width_deg,
            measurement_id='second',
            channel=ss.first.channel,
        ))
    result = solve(measurements, ss.policy)
    return {'feedback': feedback, 'result': result, 'is_angular_worst_estimate': False,
            'label': 'same_representative_realizable_feedback'}


def posterior_area(ss, q, feedback, steps_m=(2., 1.)):
    steps_m = tuple(steps_m)
    if not steps_m or any(not math.isfinite(step) or step <= 0 for step in steps_m):
        raise ValueError('nonempty finite positive area grid spacings required')
    outer = posterior_outer_polygon(ss, q, feedback)
    if not outer.vertices:
        return {'status': 'NUMERICAL_UNRESOLVED', 'estimates_m2': (), 'change_m2': None}
    vertices = np.asarray(outer.vertices)
    low, high = vertices.min(axis=0), vertices.max(axis=0)
    if feedback.kind == 'near':
        low, high = np.asarray(q)-ss.physics.near_radius, np.asarray(q)+ss.physics.near_radius
    estimates = []
    for step in steps_m:
        nx, ny = np.maximum(1, np.ceil((high-low)/step).astype(int))
        dx, dy = (high-low)/np.array((nx, ny))
        hits = 0
        xs = low[0]+(np.arange(nx)+.5)*dx
        for i in range(ny):
            points = np.column_stack((xs, np.full(nx, low[1]+(i+.5)*dy)))
            hits += int(posterior_contains(ss, q, feedback, points, ss.policy).sum())
        estimates.append(float(hits*dx*dy))
    return {'status': 'RESOLUTION_INSUFFICIENT' if estimates[-1] == 0 else 'NUMERICAL_ESTIMATE',
            'estimates_m2': tuple(estimates), 'steps_m': tuple(steps_m),
            'change_m2': abs(estimates[-1]-estimates[-2]) if len(estimates) > 1 else None}


def equilateral_case(length_m=20.):
    if length_m <= 0:
        raise ValueError('positive triangle side required')
    L = length_m
    center = np.array((L/2, math.sqrt(3)*L/6))
    first = np.array((-L/math.tan(math.radians(2)), 0.))
    result = []
    for k in range(3):
        a = math.radians(120*k)
        rotation = np.array(((math.cos(a), -math.sin(a)), (math.sin(a), math.cos(a))))
        result.append(BearingMeasurement(
            position=point(center+rotation @ (first-center)),
            bearing_deg=1+120*k,
            half_width_deg=1.,
            measurement_id=f'equilateral_{k}',
            origin='analytic',
        ))
    return {'measurements': tuple(result), 'synthetic_truth': point(center), 'origin': 'analytic',
            'expected': {'diameter_m': L, 'radius_m': L/math.sqrt(3), 'area_m2': math.sqrt(3)*L*L/4,
                         'kappa': 2/math.sqrt(3), 'eta': math.sqrt(3)}}


def analytic_cases():
    return {
        'equilateral20': equilateral_case(20), 'equilateral36': equilateral_case(36),
        'orthogonal': {'measurements': (BearingMeasurement(position=(-500., 0.), bearing_deg=0., measurement_id='o1'),
                                       BearingMeasurement(position=(0., -500.), bearing_deg=90., measurement_id='o2')), 'origin': 'analytic'},
        'unbounded': {'measurements': (BearingMeasurement(position=(0., 0.), bearing_deg=0.),), 'origin': 'analytic'},
        'empty': {'measurements': (BearingMeasurement(position=(0., 0.), bearing_deg=180.), BearingMeasurement(position=(10., 0.), bearing_deg=0.)), 'origin': 'analytic'},
        'segment': {'measurements': (BearingMeasurement(position=(0., 0.), bearing_deg=0., half_width_deg=0.), BearingMeasurement(position=(10., 0.), bearing_deg=180., half_width_deg=0.)), 'origin': 'analytic'},
        'thin': {'measurements': (BearingMeasurement(position=(-500., 0.), bearing_deg=0., half_width_deg=.0001),
                                 BearingMeasurement(position=(0., -500.), bearing_deg=90., half_width_deg=.0001)), 'origin': 'analytic'},
    }


def sensitivity_cases(first, physics, policy):
    """S1/S3/S4 variants rebuild all changed physical information; execution is explicit."""
    scenarios = []
    for width, mode in ((1., 'THEORETICAL_1_DEG'), (1.005, 'NEAREST_ROUNDING_OUTER_1_005_DEG')):
        obs = replace(first, half_width_deg=width, error_mode=mode,
                      rounding_assumption_source='latent <=1 degree then nearest 0.01 degree' if width > 1 else 'theoretical total bound')
        scenarios.append(('S1', mode, build_source_set(obs, physics, policy), {}))
    for rho in (1000., 1250., 1500.):
        scenarios.append(('S3', f'known_rho_{rho:g}', build_source_set(first, replace(physics, rho_lo=rho, rho_hi=rho), policy), {}))
    scenarios.append(('S4', 'action_inside_arena', build_source_set(first, physics, policy), {'restrict_action_to_arena': True}))
    return tuple(scenarios)


def compare_heuristics(ss, config, recommended=None):
    from .q2 import score_point, sample_sources, check_admissibility
    s = np.asarray(ss.first.position)
    u = unit(math.radians(ss.first.bearing_deg))
    v = np.array((-u[1], u[0]))
    candidates = {'fixed_side_200': point(s+200*v), 'forward_then_side': point(s+200*u+200*v),
                  'orthogonal_assumed_midrange': point(s+750*u+750*v)}
    if recommended is not None:
        candidates['main'] = recommended
    points = set(sample_sources(ss, 2, config.source_grids, inward=config.near_offset_m, second_half_width_deg=config.second_half_width_deg).points)
    for q in candidates.values():
        points.update(sample_sources(ss, 2, config.source_grids, q, second_half_width_deg=config.second_half_width_deg, inward=config.near_offset_m).points)
    samples = SourceSamples(points=tuple(sorted(points)), level=2, grid=config.source_grids[2])
    for q in candidates.values():
        # Preserve the common sample pool: signal-legal anchors still contribute
        # contacts even when movement/arena budgets exclude their recommendation.
        if check_admissibility(ss, q, config)['signal_check'].status == 'IN':
            local_score = score_point(ss, q, samples, replace(config, refine_pairs=True))
            for witness in local_score.top_pairs:
                points.update((witness.x, witness.y))
    samples = replace(samples, points=tuple(sorted(points)), offset_m=config.near_offset_m)
    results = []
    for name, q in candidates.items():
        assessment = check_admissibility(ss, q, config)
        check = assessment['signal_check']
        # This diagnostic compares proven IN candidates; search may retain
        # BOUNDARY candidates with reception explicitly unresolved.
        feasible = assessment['status'] == 'IN'
        score = score_point(ss, q, samples, replace(config, refine_pairs=True)) if feasible else None
        clear = area = None
        if score and score.witness:
            w = score.witness
            feedback = Feedback(kind=w.branch, bearing_deg=w.common_bearing_deg, half_width_deg=config.second_half_width_deg)
            clear = clearance_summary(ss, q, feedback, samples, config.policy)
            area = posterior_area(ss, q, feedback)
        results.append({'strategy': name, 'q': q, 'candidate': check, 'score': score,
                        'clearance': clear, 'conditional_area': area, 'movement_m': distance(q, s),
                        'origin': 'same_information_numerical_comparison', 'admissibility_scope': 'proven_IN_only'})
    return tuple(results)


def reassess_old_point(ss, q, config):
    from .q2 import check_admissibility, score_point, sample_sources
    if q is None:
        return {'signal_check': None, 'status': 'NOT_EVALUATED',
                'action_admissible': False, 'reasons': ('no_old_point',), 'score': None}
    assessment = check_admissibility(ss, q, config)
    score = None
    if assessment['status'] == 'IN':
        samples = sample_sources(ss, 2, config.source_grids, q, second_half_width_deg=config.second_half_width_deg, inward=config.near_offset_m)
        score = score_point(ss, q, samples, replace(config, refine_pairs=True))
    return dict(assessment, score=score)
