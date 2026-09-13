"""Complete polygon reception test and continuous angular-bucket MEC bounds."""
import math
import numpy as np
from geometry import ANGLE_BOUND_DEG, clip, bearing_clip, minimum_circle

# Different units: squared-distance dominance and ordinary receiving distance.
DOMINANCE_MARGIN_M2 = 1e-5
RECEIVING_MARGIN_M = 1e-5


def reception_certificate(q,poly,anchor):
    """Full condition over containing polygon, with conservative numeric margins.

    Applies only to omnidirectional sources: anchor must be an actual successful
    reception point for this source, and nonempty poly must contain the source.
    Violation requires BOTH d(q,g)>1000 AND d(q,g)>d(anchor,g).
    The latter squared-distance difference is affine in g. Over its positive
    halfplane intersected with P, maximum d(q,g) occurs at a polygon vertex.
    """
    q=np.asarray(q)
    s=np.asarray(anchor)
    poly=np.asarray(poly)
    if np.linalg.norm(q-s)<1e-10:
        return dict(guaranteed=True,method="same_position",critical_radius_m=None)
    normal=2*(q-s)
    bound=float(q@q-s@s)
    difference=bound-poly@normal
    if difference.max()<-DOMINANCE_MARGIN_M2:
        return dict(guaranteed=True,method="distance_dominance",critical_radius_m=None)
    # difference = d(q,g)^2 - d(anchor,g)^2. Keep the nonnegative side;
    # outward clip slack can only make the sufficient certificate harder to pass.
    positive=clip(poly,normal,bound)
    if not len(positive):
        return dict(guaranteed=True,method="empty_positive_halfplane",critical_radius_m=None)
    radius=float(np.linalg.norm(positive-q,axis=1).max())
    return dict(guaranteed=radius<1000.-RECEIVING_MARGIN_M,method="mixed_minimum_range_and_dominance",critical_radius_m=radius,
                clipped_vertices=positive.tolist())


def possible_bearing_interval(poly,q,error_deg=ANGLE_BOUND_DEG):
    delta=np.asarray(poly)-q
    if np.linalg.norm(delta,axis=1).min()<1e-7:
        return 0.,360.
    angle=np.sort(np.mod(np.degrees(np.arctan2(delta[:,1],delta[:,0])),360.))
    gaps=np.diff(np.r_[angle,angle[0]+360.])
    i=int(gaps.argmax())
    # A strict gap >180 means all vectors lie in an open halfplane, so the
    # convex polygon directions occupy the complementary arc. Boundary and
    # inside-polygon cases conservatively retain the entire bearing circle.
    if gaps[i]<=180.+1e-7:
        return 0.,360.
    start=float(angle[(i+1)%len(angle)])
    end=start+360.-float(gaps[i])
    return start-error_deg,end+error_deg


def posterior_radius_upper(poly,q,bin_deg=1.,error_deg=ANGLE_BOUND_DEG,save_bins=False):
    # Conditional on successful reception from a nonempty containing region.
    # Callers need a reception guarantee, or must include the unchanged no-signal radius.
    if not 0.<bin_deg<90.:
        raise ValueError("Invalid angular bin size")
    low,high=possible_bearing_interval(poly,q,error_deg)
    count=max(1,int(math.ceil((high-low)/bin_deg)))
    edges=np.linspace(low,high,count+1)
    initial=minimum_circle(poly)[1]
    # near bounds distance by 5 m. Both old and updated circles enclose the posterior,
    # so their smaller radius remains an upper bound on its optimal enclosing radius.
    worst=min(5.,initial)
    records=[]
    for a,b in zip(edges[:-1],edges[1:]):
        # Half a reading bucket expands the cone to enclose every reading in that bucket.
        middle=(a+b)/2
        halfwidth=error_deg+(b-a)/2
        post=bearing_clip(poly,q,middle,halfwidth)
        if not len(post):
            continue
        radius=min(initial,minimum_circle(post)[1])
        worst=max(worst,radius)
        if save_bins:
            records.append(dict(interval_deg=[float(a),float(b)],expanded_halfwidth_deg=halfwidth,radius_upper_m=radius))
    return dict(radius_upper_m=worst,bin_count=count,maximum_bin_deg=bin_deg,
                reading_interval_deg=[low,high],bins=records if save_bins else None)
