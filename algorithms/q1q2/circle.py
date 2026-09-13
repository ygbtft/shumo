"""Welzl circles and Thales coverage for complete bounded vertex sets."""
from __future__ import annotations
from dataclasses import dataclass, replace
from itertools import combinations
import math
import random
from fractions import Fraction as F
from decimal import Decimal, localcontext
from typing import Sequence
import numpy as np
from .geometry import (Point2, NumericPolicy, Region, RegionKind, DiameterResult,
                       point, cross)


@dataclass(frozen=True)
class CircleResult:
    center: Point2 | None
    radius: float | None
    support_vertex_indices: tuple[int, ...] = ()
    containment_residual: float | None = None
    status: str = 'OK'
    seed: int | None = None
    method: str = 'welzl_explicit_stack'
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True)
class CoverResult:
    status: str
    forced_center: Point2 | None = None
    thales_max: float | None = None
    kappa: float | None = None
    eta: float | None = None
    counterexample_vertex: Point2 | None = None
    counterexample_index: int | None = None
    finite_cover: bool = False
    midpoint_radius: float | None = None
    tolerance_m2: float | None = None


# Output representability thresholds, independent of coverage tolerances.
_EXPORT_RELATIVE_ERROR = 2e-12
_ENUMERATION_VERTEX_LIMIT = 80  # O(V⁴) exact fallback is reserved for small inputs.


class ForcedSupportError(ArithmeticError):
    pass


def _rational_points(points):
    return tuple(tuple(F(x) for x in point(v)) for v in points)


def _distance2(a, b):
    return sum((x-y)**2 for x, y in zip(a, b))


def _exact_boundary(p):
    """Circumcircle of binary64 inputs, with no geometric tolerance."""
    if not p:
        return None
    c = p[0]
    if len(p) == 2:
        c = tuple((x+y)/2 for x, y in zip(*p))
    elif len(p) == 3:
        a = tuple(p[1][i]-p[0][i] for i in range(2))
        b = tuple(p[2][i]-p[0][i] for i in range(2))
        det = a[0]*b[1]-a[1]*b[0]
        if not det:
            raise ForcedSupportError('COLLINEAR_FORCED_SUPPORT')
        aa, bb = sum(x*x for x in a), sum(x*x for x in b)
        c = (p[0][0]+(aa*b[1]-bb*a[1])/(2*det),
             p[0][1]+(a[0]*bb-b[0]*aa)/(2*det))
    return c, _distance2(c, p[0])


def _root(q):
    # Avoid overflow/underflow of the squared radius before taking its root.
    with localcontext() as ctx:
        ctx.prec = 80
        return float((Decimal(q.numerator)/Decimal(q.denominator)).sqrt())


def _export_circle(exact, points, ids, method, seed=None):
    c, r2 = exact
    # Boundary support is an unordered set; publish input indices canonically.
    ids = tuple(sorted(ids))
    try:
        center, radius = tuple(map(float, c)), _root(r2)
        if not all(math.isfinite(x) for x in (*center, radius)):
            raise OverflowError
        # Certification is on the input floats; lost pre-input digits cannot be
        # recovered. Do not publish OK when rounding the center destroys local
        # geometry, even if a coordinate-ULP-based external check would allow it.
        error = _root(_distance2(tuple(map(F, center)), c))
        # The fixed relative export budget scales with the radius and includes
        # binary64 radius roundoff; it is not a coverage tolerance.
        # There is no absolute metre floor or coordinate-magnitude allowance.
        budget = _EXPORT_RELATIVE_ERROR*radius + 64*math.ulp(radius)
        residual = max(math.dist(center, v)-radius for v in points)
        resolved_radius = (r2 == 0 or (radius > 0 and
                           F(math.ulp(radius)) <= F(radius)*F(1e-12)))
        status = 'OK' if resolved_radius and error <= budget and residual <= budget else 'NUMERICAL_UNRESOLVED'
        return CircleResult(
            center=center,
            radius=radius,
            support_vertex_indices=ids,
            containment_residual=residual,
            status=status,
            seed=seed,
            method=method,
            diagnostics=() if status == 'OK' else ('CENTER_ROUNDING_EXCEEDS_LOCAL_PRECISION',),
        )
    except (OverflowError, ValueError):
        return CircleResult(
            center=None,
            radius=None,
            status='NUMERICAL_UNRESOLVED',
            seed=seed,
            method=method,
            diagnostics=('UNREPRESENTABLE_CIRCLE',),
        )


def forced_circle(points: Sequence[Point2]) -> CircleResult:
    """Every supplied point is on the boundary, including obtuse triples.

    Exact arithmetic distinguishes collinearity from small area at any scale.
    """
    if len(points) > 3:
        raise ValueError('at most three forced boundary points')
    p = tuple(point(v) for v in points)
    if not p:
        return CircleResult(center=None, radius=None, method='forced_boundary')
    return _export_circle(_exact_boundary(_rational_points(p)), p,
                          tuple(range(len(p))), 'forced_boundary')


def _proposal_circle(points):
    """Normalized floating circumcircle, ONLY a proposal for exact certification.

    An unreliable triple triggers the existing exact fallback. In particular an
    obtuse triple still forces all three points onto the circumference.
    """
    if not points:
        return CircleResult(center=None, radius=None)
    c = tuple(points[0])
    if len(points) == 2:
        c = tuple((a+b)/2 for a, b in zip(*points))
    elif len(points) == 3:
        x, y = points[0]
        ax, ay = points[1][0]-x, points[1][1]-y
        bx, by = points[2][0]-x, points[2][1]-y
        det = ax*by-ay*bx
        if not math.isfinite(det) or abs(det) <= 1e-14*(abs(ax*by)+abs(ay*bx)):
            raise ForcedSupportError('UNRELIABLE_FLOAT_PROPOSAL')
        aa, bb = ax*ax+ay*ay, bx*bx+by*by
        c = (x+(aa*by-bb*ay)/(2*det), y+(ax*bb-bx*aa)/(2*det))
    radius = math.dist(c, points[0])
    if not all(math.isfinite(v) for v in (*c, radius)):
        raise ForcedSupportError('NONFINITE_FLOAT_PROPOSAL')
    return CircleResult(center=c, radius=radius)


def _contains(circle, p):
    # Used only to propose a support; exact certification below is mandatory.
    return (circle.center is not None and circle.radius is not None and
            math.dist(circle.center, p) <= circle.radius+32*math.ulp(circle.radius))


def enumerate_circle(vertices):
    p = tuple(point(x) for x in vertices)
    q = _rational_points(p)
    best, support = None, ()
    for size in (1, 2, 3):
        for ids in combinations(range(len(p)), size):
            try:
                c = _exact_boundary([q[i] for i in ids])
            except ForcedSupportError:
                continue
            if best is not None and c[1] >= best[1]:
                continue
            if all(_distance2(c[0], x) <= c[1] for x in q):
                best, support = c, ids
    if best is None:
        return CircleResult(center=None, radius=None, status='NUMERICAL_UNRESOLVED')
    return _export_circle(best, p, support, 'candidate_enumeration_exact')


def _certified_support(q, ids):
    """Containment + center in convex hull of boundary => global minimum."""
    p = [q[i] for i in ids]
    c = _exact_boundary(p)
    if c is None or any(_distance2(c[0], v) > c[1] for v in q):
        return None
    if len(p) == 3:
        a = tuple(p[1][i]-p[0][i] for i in range(2))
        b = tuple(p[2][i]-p[0][i] for i in range(2))
        v = tuple(c[0][i]-p[0][i] for i in range(2))
        det = cross(a, b)
        u, w = cross(v, b)/det, cross(a, v)/det
        if u < 0 or w < 0 or u+w > 1:
            return None
    return c


def _exact_welzl(q, order):
    # state 0 first solves without the last point; state 1 checks it on return.
    # result is the completed child circle, retained across popped parent frames.
    # boundary contains points forced onto the circumference, not just inside.
    stack = [(len(order), (), 0)]
    result, ids = None, ()
    while stack:
        n, boundary, state = stack.pop()
        if n == 0 or len(boundary) == 3:
            result, ids = _exact_boundary([q[i] for i in boundary]), boundary
        elif state == 0:
            stack.append((n, boundary, 1))
            stack.append((n-1, boundary, 0))
        elif result is None or _distance2(result[0], q[order[n-1]]) > result[1]:
            stack.append((n-1, boundary+(order[n-1],), 0))
    return result, ids


def ordinary_three_point_circle(points: Sequence[Point2]) -> CircleResult:
    if not 1 <= len(points) <= 3:
        raise ValueError('ordinary circle requires one to three points')
    return enumerate_circle(points)


def minimum_circle(vertices: Sequence[Point2], seed: int) -> CircleResult:
    original = tuple(point(v) for v in vertices)
    if not original:
        return CircleResult(center=None, radius=None, status='EMPTY', seed=seed)
    unique = list(dict.fromkeys(original))
    q = _rational_points(unique)
    order = list(range(len(unique)))
    random.Random(seed).shuffle(order)
    origin = np.asarray(unique[0])
    scale = max(math.dist(p, origin) for p in unique)
    method = 'welzl_certified_support'
    try:
        if scale == 0:
            ids = (0,)
        elif not math.isfinite(scale):
            raise ForcedSupportError('NORMALIZATION_OVERFLOW')
        else:
            # Normalize even sub-unit geometry. Tolerances are roundoff-relative,
            # never a fixed length in metres or an area with a unit-scale floor.
            normalized = [point((np.asarray(v)-origin)/scale) for v in unique]
            # Same stack invariant as _exact_welzl; floats only propose support.
            stack = [(len(order), (), 0)]
            result = CircleResult(center=None, radius=None)
            while stack:
                n, boundary, state = stack.pop()
                if n == 0 or len(boundary) == 3:
                    result = _proposal_circle([normalized[i] for i in boundary])
                    result = replace(result, support_vertex_indices=boundary)
                elif state == 0:
                    stack.append((n, boundary, 1))
                    stack.append((n-1, boundary, 0))
                elif not _contains(result, normalized[order[n-1]]):
                    stack.append((n-1, boundary+(order[n-1],), 0))
            ids = result.support_vertex_indices
        # Recheck the proposed support in original coordinates before export.
        exact = _certified_support(q, ids)
        if exact is None:
            raise ForcedSupportError('SUPPORT_CERTIFICATE_FAILED')
    except ForcedSupportError:
        # Only a failed proposal invokes exact Welzl, then bounded enumeration.
        method = 'welzl_exact_fallback'
        try:
            _, ids = _exact_welzl(q, order)
            exact = _certified_support(q, ids)
        except ForcedSupportError:
            exact = None
        if exact is None:
            if len(q) <= _ENUMERATION_VERTEX_LIMIT:
                return replace(enumerate_circle(original), seed=seed)
            return CircleResult(
                center=None,
                radius=None,
                status='NUMERICAL_UNRESOLVED',
                seed=seed,
                diagnostics=('EXACT_SUPPORT_CERTIFICATE_FAILED',),
            )
    return _export_circle(exact, original,
                          tuple(original.index(unique[i]) for i in ids), method, seed)


def diameter_circle_cover(region: Region, d: DiameterResult, policy: NumericPolicy, mec: CircleResult) -> CoverResult:
    # mec must be the already computed minimum circle of region.vertices.
    # Thales signs independently decide coverage; radius subtraction never does.
    if region.kind == RegionKind.EMPTY:
        return CoverResult(status='NOT_APPLICABLE')
    if region.kind == RegionKind.UNBOUNDED:
        return CoverResult(status='NOT_APPLICABLE', finite_cover=False)
    if d.endpoints is None or d.status != 'OK' or region.status != 'OK':
        return CoverResult(status='UNRESOLVED')
    a, b = _rational_points(d.endpoints)
    v = _rational_points(region.vertices)
    if not v or d.length is None or not math.isfinite(d.length):
        return CoverResult(status='UNRESOLVED')
    center = tuple(float((x+y)/2) for x, y in zip(a, b))
    d2 = _distance2(a, b)
    if d2 == 0:
        if any(x != a for x in v):
            return CoverResult(status='UNRESOLVED')
        return CoverResult(status='YES', forced_center=center, thales_max=0., finite_cover=True, midpoint_radius=0.)
    t = [sum((x[j]-a[j])*(x[j]-b[j]) for j in range(2)) for x in v]
    k = max(range(len(t)), key=t.__getitem__)
    maximum = max(F(0), t[k])
    # Exact sign prevents a rounded negative/zero dot product from asserting YES.
    # Retain the public policy's conservative indeterminate band for positive
    # residuals; it never enlarges the set declared covered.
    tol = policy.squared(d.length)
    if not math.isfinite(tol):
        return CoverResult(status='UNRESOLVED')
    status = 'YES' if maximum == 0 else 'NO' if maximum > F(tol) else 'UNRESOLVED'
    length = _root(d2)
    kappa = 2*(mec.radius/length) if mec.status == 'OK' else None
    eta = _root(1+4*maximum/d2)
    midpoint_radius = _root(d2/4+maximum)
    try:
        maximum_float = float(maximum)
    except OverflowError:
        return CoverResult(status='UNRESOLVED')
    return CoverResult(
        status=status,
        forced_center=center,
        thales_max=maximum_float,
        kappa=kappa,
        eta=eta,
        counterexample_vertex=region.vertices[k] if status == 'NO' else None,
        counterexample_index=k if status == 'NO' else None,
        finite_cover=True,
        midpoint_radius=midpoint_radius,
        tolerance_m2=tol,
    )


def clearance_diameter_regime(diameter_m: float, radius_m: float = 20.) -> str:
    if not math.isfinite(diameter_m) or diameter_m < 0 or not math.isfinite(radius_m) or radius_m <= 0:
        raise ValueError('invalid diameter or clearance radius')
    if diameter_m <= math.sqrt(3)*radius_m:
        return 'EXISTS_COVER_CENTER'
    if diameter_m <= 2*radius_m:
        return 'SHAPE_DEPENDENT'
    return 'IMPOSSIBLE'
