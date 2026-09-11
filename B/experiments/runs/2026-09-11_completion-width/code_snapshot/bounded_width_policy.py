"""Q4 controls transverse travel while retaining the safe wide-pair condition."""
import math
import numpy as np
from wide_probe_policy import WidePacketPolicy


class BoundedWidthPacketPolicy(WidePacketPolicy):
    def __init__(self, *args, transverse_m=40., width_rule="constant", **kwargs):
        if not 0. < transverse_m <= 100. or width_rule not in ("constant", "uncertainty"):
            raise ValueError("Invalid bounded transverse-width rule")
        kwargs["probe_angle"] = 30.
        super().__init__(*args, **kwargs)
        self.transverse_m, self.width_rule = transverse_m, width_rule
        self.stats.update(configured_probe_angle_deg=None, configured_angle_schedule="bounded_transverse_width", transverse_target_m=transverse_m,
                          transverse_width_rule=width_rule, probe_angle_cap_deg=30.)

    def probes(self, ch, step):
        anchor, u, length, previous = super().probes(ch, step)
        if length <= 0.:
            return anchor, u, length, previous
        target = self.transverse_m
        if self.width_rule == "uncertainty":
            target = min(target, .15*self.circle(ch)[1])
        width = min(length*math.tan(math.radians(30.)), max(length*math.tan(math.radians(1.02)), target))
        v = np.array([-u[1], u[0]])
        points = [anchor+length*u+width*v, anchor+length*u-width*v]
        points.sort(key=lambda q: float(np.linalg.norm(q-self.client.position)))
        return anchor, u, length, points
