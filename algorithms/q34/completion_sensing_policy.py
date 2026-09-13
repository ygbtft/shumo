"""Q3 sensing ranks expected completion travel under an explicit region prior."""
import math
import numpy as np

from clearance_policy import ClearanceJointPolicy
from geometry import minimum_circle
from intelligent import candidate_points, guaranteed_omni, hypotheses
from joint_policy import choose_covariance
from policies import Policy


def area_quadrature(poly):
    """Positive degree-2 triangle quadrature; exact uniform-region moments.

The subsequent nonlinear bearing surrogate is only approximated by these
nodes. A degenerate region uses a uniform longest segment (or a single point).
"""
    p = np.asarray(poly, dtype=float)
    origin = p[0]
    relative = p - origin
    if len(p) >= 3:
        b, c = relative[1:-1], relative[2:]
        areas = np.abs(b[:, 0]*c[:, 1] - b[:, 1]*c[:, 0]) / 2
        keep = areas > 0.
        b, c, areas = b[keep], c[keep], areas[keep]
        if areas.sum() > 1e-14:
            nodes = np.stack(((b+c)/6, 2*b/3+c/6, b/6+2*c/3), axis=1).reshape(-1, 2)
            weights = np.repeat(areas / areas.sum() / 3, 3)
            return nodes + origin, weights
    d2 = np.sum((p[:, None, :] - p[None, :, :])**2, axis=2)
    i, j = np.unravel_index(d2.argmax(), d2.shape)
    if d2[i, j] <= 1e-24:
        return p[:1].copy(), np.array([1.])
    center, half = (p[i]+p[j])/2, (p[j]-p[i])/2
    t = math.sqrt(3/5)
    return np.array([center-t*half, center, center+t*half]), np.array([5/18, 8/18, 5/18])


def completion_choice(poly, observations, current, remainder_weight=0., area_prior=False, expanded=False, weight=.08):
    if remainder_weight == 0. and not area_prior and not expanded:
        return choose_covariance(poly, observations, current, False, weight)
    center, radius = minimum_circle(poly)
    # Uniform area is a ranking prior, not the official source distribution; covariance is m².
    if area_prior:
        samples, weights = area_quadrature(poly)
        reference = poly[0]
        mu = np.sum((samples-reference)*weights[:, None], axis=0) + reference
        centered = samples-mu
        covariance = (centered*weights[:, None]).T @ centered + np.eye(2)*.01
    else:
        centered = poly-poly.mean(axis=0)
        covariance = centered.T @ centered / max(1, len(poly)) + np.eye(2)*.01
        samples = hypotheses(poly)
        weights = np.full(len(samples), 1/len(samples))
    candidates = list(candidate_points(poly, observations, current))
    if expanded:
        anchor, angle = observations[0]
        theta = math.radians(angle)
        u, v = np.array([math.cos(theta), math.sin(theta)]), np.array([-math.sin(theta), math.cos(theta)])
        width = float(np.clip(radius*.3, 25., 250.))
        for fraction in (.35, .5, 1.15, 1.3):
            for lateral in (-width, -width/3, 0., width/3, width):
                q = anchor + fraction*(center-anchor) + lateral*v
                relative = q-anchor
                # Keep the original <1900 m first-bearing action rectangle.
                if not (-150. <= relative @ u <= 1652. and abs(relative @ v) <= 277.):
                    continue
                if np.linalg.norm(q-current) <= 1. or any(np.linalg.norm(q-p) <= 1. for p, _ in observations):
                    continue
                if not any(np.linalg.norm(q-p) < 1e-8 for p in candidates):
                    candidates.append(q)
    choices = []
    for q in candidates:
        if not guaranteed_omni(q, poly, observations[0][0]):
            continue
        delta = samples-q
        distance = np.maximum(1., np.linalg.norm(delta, axis=1))
        normal = np.column_stack((-delta[:, 1], delta[:, 0])) / distance[:, None]
        cn = normal @ covariance
        # Linearized uniform angular error ±1.01° has variance bound²/3.
        noise = (distance*math.radians(1.01))**2 / 3
        denominator = np.sum(cn*normal, axis=1) + noise
        post = covariance[None, :, :] - cn[:, :, None]*cn[:, None, :] / denominator[:, None, None]
        disc = np.maximum(0., (post[:, 0, 0]-post[:, 1, 1])**2 + 4*post[:, 0, 1]**2)
        eigen = (post[:, 0, 0]+post[:, 1, 1]+np.sqrt(disc))/2
        # sqrt(3 * largest eigenvalue) is a ranking proxy, never a certified radius.
        uncertainty = np.sqrt(np.maximum(0., eigen))*math.sqrt(3)
        residual = float(weights @ uncertainty)
        # The MEC center is a completion-location proxy, never true position.
        # /5 + 5 uses 5 m/s and 5 s RF. Weighted return travel is only a ranking
        # term; it is never charged to the virtual-time ledger.
        travel = (np.linalg.norm(q-current) + remainder_weight*np.linalg.norm(q-center))/5 + 5
        choices.append((float(residual + weight*travel), q))
    if choices:
        return min(choices, key=lambda x: x[0])[1]
    return choose_covariance(poly, observations, current, False, weight)


class CompletionClearancePolicy(ClearanceJointPolicy):
    def __init__(self, *args, remainder_weight=0., area_prior=False, expanded=False, **kwargs):
        if not 0. <= remainder_weight <= 2.:
            raise ValueError("Completion proxy weight outside tested range")
        super().__init__(*args, **kwargs)
        if self.mixed:
            raise ValueError("Omni reception certificates apply to Q3 only")
        self.remainder_weight, self.area_prior, self.expanded = remainder_weight, area_prior, expanded
        self.stats.update(completion_proxy_weight=remainder_weight, uniform_area_ranking_prior=area_prior,
                          expanded_sensing_candidates=expanded)

    def complete_source(self, ch):
        if ch in self.cleared:
            return
        # max_active (3 in the frozen Q3 candidate) counts primary rounds; sharing RF is separate.
        for _ in range(self.max_active):
            poly = self.regions[ch]
            center, radius = self.circle(ch)
            if radius <= 20.-1e-5:
                if not self.clear(center, ch, True):
                    raise RuntimeError("Certified optical clear failed")
                return
            # At most one uncertified trial per source (frozen Q3 gate: 50 m).
            if radius <= self.trial_radius and ch not in self._trial_done:
                self._trial_done.add(ch)
                self.stats["early_optical_trials"] += 1
                if self.clear(center, ch):
                    self.stats["early_optical_success"] += 1
                    return
                q = center
            else:
                q = completion_choice(poly, self.observations[ch], self.client.position,
                                      self.remainder_weight, self.area_prior, self.expanded, self.time_weight)
            self.stats["active_measurements"] += 1
            result = self.measure(q, ch)
            self.stats["active_no_signal"] += int(result == "no_signal")
            if ch in self.cleared:
                return
            if result == "no_signal":
                break
        # Disable further active RF so the fallback terminates via finite optical coverage.
        old_active = self.active
        self.active = False
        try:
            Policy.complete_source(self, ch)
        finally:
            self.active = old_active
