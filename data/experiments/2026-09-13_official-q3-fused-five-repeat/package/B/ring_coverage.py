"""Q3-only center/ring station designs, with a continuous disk coverage proof.

The peer paper suggested center + eight radius-1300 stations.  These independent
implementations retain that useful idea and check BOTH boundary and interior.
There is no simulator, hidden scenario, or network dependency in this module.
"""
import math
import numpy as np


def covering_radius(n, ring_radius, arena_radius=1800.):
    """Exact maximum distance to nearest center/ring station over the arena.

    In the nearest ring station's sector, |theta| <= pi/n.  Distance increases
    with |theta|, so use theta=pi/n.  Along that ray, the squared nearest
    distance is min(r*r, r*r+a*a-2*r*a*cos(pi/n)).  The branches meet at
    r=a/(2*cos(pi/n)); the second branch is convex.  Its maximum on the
    remaining interval is at an endpoint.  This also handles rings too far out.
    """
    if n < 3 or ring_radius <= 0 or arena_radius <= 0:
        raise ValueError("Require n >= 3 and positive radii")
    c = math.cos(math.pi/n)
    split = ring_radius/(2*c)
    if split >= arena_radius:
        return arena_radius
    boundary = math.sqrt(arena_radius**2+ring_radius**2-2*arena_radius*ring_radius*c)
    return max(split, boundary)


def stations(n, ring_radius, arena_radius=1800., receive_min=1000.):
    if covering_radius(n, ring_radius, arena_radius) >= receive_min:
        raise ValueError("No strict Q3 coverage margin for this design")
    angles = np.arange(n)*2*math.pi/n
    return np.vstack((np.zeros(2), ring_radius*np.column_stack((np.cos(angles),np.sin(angles)))))


# Frozen from geometry before evaluating source scenes.  n counts outer points.
DESIGNS = {"peer_ring9_r1300": (8, 1300.),
           "ring7_r1140": (6, 1140.),
           "ring9_r960": (8, 960.),
           "ring13_r870": (12, 870.)}


def metadata():
    return {name: {"n_outer": n, "stations": n+1, "ring_radius_m": a,
                   "coverage_radius_m": covering_radius(n,a),
                   "coverage_margin_m": 1000-covering_radius(n,a),
                   "static_open_route_m": a+(n-1)*2*a*math.sin(math.pi/n),
                   "problem": 3, "guarantees_arbitrary_direction": False}
            for name,(n,a) in DESIGNS.items()}
