"""Wider paired probes retain bounded-region cuts for unknown RF direction."""
import math
import numpy as np

from efficient_joint_policy import ProbeJointPolicy
from interleaved_policy import InterleavedProbePolicy


class WideProbeMixin:
    def __init__(self, *args, probe_angle=10., angle_mode="fixed", **kwargs):
        if not 1.02 <= probe_angle <= 30.:
            raise ValueError("Current movement proof covers probe angles from 1.02 to 30 degrees")
        if angle_mode not in ("fixed", "decay", "first"):
            raise ValueError("Unknown angle schedule")
        super().__init__(*args, **kwargs)
        if not self.mixed or self.bracket_steps > 10 or self.bracket_trial_radius > 80.:
            raise ValueError("Wide-probe certificate requires Q4, <=10 rounds and <=80 m trial radius")
        t = math.tan(math.radians(1.02))
        k = math.tan(math.radians(probe_angle))
        assert k >= t and k * k + 2 * k * t < 1.
        self.probe_angle, self.angle_mode = probe_angle, angle_mode
        self.stats.update(configured_probe_angle_deg=probe_angle, configured_angle_schedule=angle_mode)

    def probes(self, ch, step):
        anchor, u, length, original = super().probes(ch, step)
        beta = self.probe_angle
        if self.angle_mode == "first" and step > 0:
            beta = 1.02
        elif self.angle_mode == "decay":
            beta = max(1.02, beta / (1. + .5 * step))
        if beta == 1.02:
            # Exact control: keep the original operations and tie ordering.
            return anchor, u, length, original
        v = np.array([-u[1], u[0]])
        width = length * math.tan(math.radians(beta))
        points = [anchor + length * u + width * v, anchor + length * u - width * v]
        points.sort(key=lambda p: float(np.linalg.norm(p - self.client.position)))
        return anchor, u, length, points


class WideProbePolicy(WideProbeMixin, ProbeJointPolicy):
    pass


class WidePacketPolicy(WideProbeMixin, InterleavedProbePolicy):
    pass
