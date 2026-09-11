"""Complete polygon reception test and continuous angular-bucket MEC bounds."""
import math
import numpy as np
from geometry import clip,bearing_clip,minimum_circle


def reception_certificate(q,poly,anchor):
    """Full condition over containing polygon, with conservative numeric margins.

    Violation requires BOTH d(q,g)>1000 AND d(q,g)>d(anchor,g).
    The latter squared-distance difference is affine in g. Over its positive
    halfplane intersected with P, maximum d(q,g) occurs at a polygon vertex.
    """
    q=np.asarray(q);s=np.asarray(anchor);poly=np.asarray(poly)
    if np.linalg.norm(q-s)<1e-10:return dict(guaranteed=True,method="same_position",critical_radius_m=None)
    normal=2*(q-s);bound=float(q@q-s@s);difference=bound-poly@normal
    if difference.max()<-1e-5:return dict(guaranteed=True,method="distance_dominance",critical_radius_m=None)
    positive=clip(poly,normal,bound)
    if not len(positive):return dict(guaranteed=True,method="empty_positive_halfplane",critical_radius_m=None)
    radius=float(np.linalg.norm(positive-q,axis=1).max())
    return dict(guaranteed=radius<1000.-1e-5,method="mixed_minimum_range_and_dominance",critical_radius_m=radius,
                clipped_vertices=positive.tolist())


def possible_bearing_interval(poly,q,error_deg=1.01):
    delta=np.asarray(poly)-q
    if np.linalg.norm(delta,axis=1).min()<1e-7:return 0.,360.
    angle=np.sort(np.mod(np.degrees(np.arctan2(delta[:,1],delta[:,0])),360.))
    gaps=np.diff(np.r_[angle,angle[0]+360.]);i=int(gaps.argmax())
    # A strict gap >180 means all vectors lie in an open halfplane, so the
    # convex polygon directions occupy the complementary arc. Boundary and
    # inside-polygon cases conservatively retain the entire bearing circle.
    if gaps[i]<=180.+1e-7:return 0.,360.
    start=float(angle[(i+1)%len(angle)]);end=start+360.-float(gaps[i])
    return start-error_deg,end+error_deg


def posterior_radius_upper(poly,q,bin_deg=1.,error_deg=1.01,save_bins=False):
    if not 0.<bin_deg<90.:raise ValueError("Invalid angular bin size")
    low,high=possible_bearing_interval(poly,q,error_deg)
    count=max(1,int(math.ceil((high-low)/bin_deg)));edges=np.linspace(low,high,count+1)
    initial=minimum_circle(poly)[1];worst=min(5.,initial);records=[]
    for a,b in zip(edges[:-1],edges[1:]):
        middle=(a+b)/2;halfwidth=error_deg+(b-a)/2
        post=bearing_clip(poly,q,middle,halfwidth)
        if not len(post):continue
        radius=min(initial,minimum_circle(post)[1]);worst=max(worst,radius)
        if save_bins:records.append(dict(interval_deg=[float(a),float(b)],expanded_halfwidth_deg=halfwidth,radius_upper_m=radius))
    return dict(radius_upper_m=worst,bin_count=count,maximum_bin_deg=bin_deg,
                reading_interval_deg=[low,high],bins=records if save_bins else None)
