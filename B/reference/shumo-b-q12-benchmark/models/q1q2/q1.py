"""Arbitrary-N observations; the primary region is the pure wedge intersection."""
from dataclasses import dataclass
from typing import Sequence
from .geometry import (BearingMeasurement, NumericPolicy, Region, DiameterResult,
                       wedge_halfplanes, intersect_halfplanes, diameter, polygon_area)
from .circle import CircleResult, CoverResult, minimum_circle, diameter_circle_cover


@dataclass(frozen=True)
class Q1Result:
    measurements: tuple[BearingMeasurement, ...]
    region: Region
    diameter: DiameterResult
    coverage: CoverResult
    minimum_circle: CircleResult
    area_m2: float | None
    diagnostics: tuple[str, ...]
    policy: NumericPolicy
    object_name: str = 'pure_angular_region'


def solve(measurements: Sequence[BearingMeasurement], policy: NumericPolicy) -> Q1Result:
    observations = tuple(measurements)
    for field in ('channel', 'session_id', 'stage_id', 'stability_id'):
        if len({getattr(m, field) for m in observations if getattr(m, field) is not None}) > 1:
            raise ValueError(f'inconsistent {field}')
    seen, request_ids, diagnostics, clean = {}, {}, [], []
    for m in observations:
        if m.request_id is not None:
            if m.request_id in request_ids:
                if request_ids[m.request_id] != m:
                    raise ValueError('conflicting duplicate request_id')
                continue
            request_ids[m.request_id] = m
        key = m.position, m.channel, m.stage_id
        if key in seen and seen[key] != m.bearing_deg:
            diagnostics.append('SAME_POSITION_DIFFERENT_BEARING')
        seen[key] = m.bearing_deg
        if any((x.position, x.bearing_deg, x.half_width_deg) ==
               (m.position, m.bearing_deg, m.half_width_deg) for x in clean):
            continue
        clean.append(m)
    region = intersect_halfplanes(tuple(h for m in clean for h in wedge_halfplanes(m)), policy)
    d = diameter(region, policy)
    circle = minimum_circle(region.vertices, policy, seed=0)
    if not region.vertices:
        circle = CircleResult(None, None, status=region.status if region.kind is None else region.kind.value)
    return Q1Result(tuple(clean), region, d, diameter_circle_cover(region, d, policy), circle,
                    polygon_area(region.vertices) if region.vertices else None, tuple(diagnostics), policy)
