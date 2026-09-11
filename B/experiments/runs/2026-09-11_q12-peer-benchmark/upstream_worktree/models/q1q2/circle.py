"""Welzl circles and Thales coverage for complete bounded vertex sets."""
from __future__ import annotations
from dataclasses import dataclass, replace
from itertools import combinations
import math
import random
from typing import Sequence
import numpy as np
from .geometry import (Point2, NumericPolicy, Region, RegionKind, DiameterResult,
                       point, distance, cross)


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


class ForcedSupportError(ArithmeticError):
    pass


def forced_circle(points: Sequence[Point2], policy: NumericPolicy) -> CircleResult:
    """Every supplied point is required on the circumference, including obtuse triples."""
    if len(points) > 3:
        raise ValueError('at most three forced boundary points')
    p = np.asarray(points, dtype=float)
    if len(p) == 0:
        return CircleResult(None, None, method='forced_boundary')
    if len(p) == 1:
        return CircleResult(point(p[0]), 0., (0,), 0., method='forced_boundary')
    if len(p) == 2:
        c = (p[0]+p[1])/2
        return CircleResult(point(c), distance(p[0], p[1])/2, (0, 1), 0., method='forced_boundary')
    a, b = p[1]-p[0], p[2]-p[0]
    det = cross(a, b)
    if abs(det) <= policy.squared(max(np.linalg.norm(a), np.linalg.norm(b))):
        raise ForcedSupportError('COLLINEAR_OR_NEAR_COLLINEAR_FORCED_SUPPORT')
    c = p[0]+np.linalg.solve(2*np.array((a, b)), np.array((a @ a, b @ b)))
    return CircleResult(point(c), distance(c, p[0]), (0, 1, 2), 0., method='forced_boundary')


def _contains(circle, p, policy):
    return circle.center is not None and distance(circle.center, p) <= circle.radius+policy.length(circle.radius)


def enumerate_circle(vertices, policy):
    p = tuple(point(x) for x in vertices)
    candidates = []
    for size in (1, 2, 3):
        for ids in combinations(range(len(p)), size):
            try:
                c = forced_circle([p[i] for i in ids], policy)
            except ForcedSupportError:
                continue
            if all(_contains(c, x, policy) for x in p):
                candidates.append(replace(c, support_vertex_indices=ids, method='candidate_enumeration'))
    if not candidates:
        return CircleResult(None, None, status='NUMERICAL_UNRESOLVED')
    c = min(candidates, key=lambda v: (v.radius, v.support_vertex_indices))
    return replace(c, containment_residual=max(distance(x, c.center)-c.radius for x in p))


def ordinary_three_point_circle(points: Sequence[Point2], policy: NumericPolicy) -> CircleResult:
    if not 1 <= len(points) <= 3:
        raise ValueError('ordinary circle requires one to three points')
    return enumerate_circle(points, policy)


def minimum_circle(vertices: Sequence[Point2], policy: NumericPolicy, seed: int) -> CircleResult:
    original = tuple(point(v) for v in vertices)
    if not original:
        return CircleResult(None, None, status='EMPTY', seed=seed)
    unique = list(dict.fromkeys(original))
    origin = np.asarray(unique[0])
    scale = max(1., max(distance(p, origin) for p in unique))
    normalized = [point((np.asarray(v)-origin)/scale) for v in unique]
    order = list(range(len(unique)))
    random.Random(seed).shuffle(order)
    # Frames encode W(n, boundary); no Python recursion depends on the vertex count.
    stack = [(len(order), (), 0)]
    result = CircleResult(None, None)
    diagnostics = ()
    try:
        while stack:
            n, boundary, state = stack.pop()
            if n == 0 or len(boundary) == 3:
                result = forced_circle([normalized[i] for i in boundary], policy)
                result = replace(result, support_vertex_indices=boundary)
            elif state == 0:
                stack.append((n, boundary, 1))
                stack.append((n-1, boundary, 0))
            elif not _contains(result, normalized[order[n-1]], policy):
                stack.append((n-1, boundary+(order[n-1],), 0))
        if not all(_contains(result, p, policy) for p in normalized):
            raise ForcedSupportError('CONTAINMENT_RECHECK_FAILED')
        support = ordinary_three_point_circle([normalized[i] for i in result.support_vertex_indices], policy)
        if abs(support.radius-result.radius) > policy.length(result.radius)*4:
            raise ForcedSupportError('SUPPORT_MINIMALITY_RECHECK_FAILED')
    except ForcedSupportError as exc:
        diagnostics = (str(exc),)
        if len(normalized) > 80:
            return CircleResult(None, None, status='NUMERICAL_UNRESOLVED', seed=seed, diagnostics=diagnostics)
        result = enumerate_circle(normalized, policy)
    if result.center is None:
        return replace(result, seed=seed, diagnostics=diagnostics)
    center = point(origin+scale*np.asarray(result.center))
    radius = result.radius*scale
    residual = max(distance(v, center)-radius for v in original)
    return CircleResult(center, radius,
                        tuple(original.index(unique[i]) for i in result.support_vertex_indices),
                        residual, 'OK' if residual <= policy.length(scale)*4 else 'NUMERICAL_UNRESOLVED',
                        seed, result.method, diagnostics)


def diameter_circle_cover(region: Region, d: DiameterResult, policy: NumericPolicy) -> CoverResult:
    if region.kind == RegionKind.EMPTY:
        return CoverResult('NOT_APPLICABLE')
    if region.kind == RegionKind.UNBOUNDED:
        return CoverResult('NOT_APPLICABLE', finite_cover=False)
    if d.endpoints is None or region.status != 'OK':
        return CoverResult('UNRESOLVED')
    a, b = map(np.asarray, d.endpoints)
    center = point((a+b)/2)
    if d.length == 0:
        return CoverResult('YES', center, 0., finite_cover=True, midpoint_radius=0.)
    v = np.asarray(region.vertices)
    t = np.einsum('ij,ij->i', v-a, v-b)
    k = int(np.argmax(t))
    maximum = max(0., float(t[k]))
    tol = policy.squared(d.length)
    # Diameter endpoints have algebraically zero Thales residual; test the other vertices.
    others = [float(t[i]) for i in range(len(t)) if i not in d.indices]
    status = 'NO' if maximum > tol else ('YES' if not others or max(others) <= 0 else 'UNRESOLVED')
    mec = minimum_circle(region.vertices, policy, 0)
    kappa = 2*mec.radius/d.length if mec.status == 'OK' else None
    eta = math.sqrt(1+4*maximum/d.squared)
    return CoverResult(status, center, maximum, kappa, eta,
                       region.vertices[k] if status == 'NO' else None,
                       k if status == 'NO' else None, True, eta*d.length/2, tol)


def clearance_diameter_regime(diameter_m: float, radius_m: float = 20.) -> str:
    if not math.isfinite(diameter_m) or diameter_m < 0 or radius_m <= 0:
        raise ValueError('invalid diameter or clearance radius')
    if diameter_m <= math.sqrt(3)*radius_m:
        return 'EXISTS_COVER_CENTER'
    if diameter_m <= 2*radius_m:
        return 'SHAPE_DEPENDENT'
    return 'IMPOSSIBLE'
