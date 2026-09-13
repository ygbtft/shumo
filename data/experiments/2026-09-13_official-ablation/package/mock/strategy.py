"""Strategy contract: observations in, one next action out; no ground truth."""
from dataclasses import dataclass
import math
from typing import Protocol
from .geometry import advance, distance

@dataclass(frozen=True)
class Action:
    path: str
    position: tuple[float, float] | None = None
    channel: int | None = None

    def payload(self, robot_id, request_id):
        data = dict(arena_id='default', robot_id=robot_id, request_id=request_id)
        if self.position is not None:
            data['position'] = dict(x=self.position[0], y=self.position[1])
        if self.channel is not None: data['channel'] = self.channel
        return data

@dataclass(frozen=True)
class Observation:
    last_action: Action
    response: dict
    position: tuple[float, float]
    current_channel: int
    virtual_time_s: float
    remaining_real_s: float
    cleared_channels: frozenset[int]
    action_count: int

class Strategy(Protocol):
    def next_action(self, observation: Observation) -> Action:
        """Return /measure, /clear, or /exit. Runner owns /enter and request IDs."""
        ...

def intersect(p, angle, q, other):
    u = (math.cos(math.radians(angle)), math.sin(math.radians(angle)))
    v = (math.cos(math.radians(other)), math.sin(math.radians(other)))
    cross = u[0]*v[1] - u[1]*v[0]
    if abs(cross) < .08: return None
    d = (q[0]-p[0], q[1]-p[1])
    t = (d[0]*v[1]-d[1]*v[0])/cross
    s = (d[0]*u[1]-d[1]*u[0])/cross
    if not 0 <= t <= 1600 or not 0 <= s <= 1600: return None
    return p[0]+t*u[0], p[1]+t*u[1]

class Baseline:
    """Serpentine 600 m grid + two-bearing intersection + local refinement.

    Includes an outside ring because directional emitters can point out of the arena.
    Deliberately simple; grid search overhead is counted in full.
    """
    def __init__(self, seed=0, spacing=600, extent=2400):
        self.spacing, self.extent = spacing, extent
        self._program = None
        self._cleared = set()

    def next_action(self, observation):
        if self._program is None:
            self._program = self._run()
            return next(self._program)
        try: return self._program.send(observation)
        except StopIteration: return Action('/exit')

    def _measure(self, point, channel):
        obs = yield Action('/measure', point, channel)
        return obs.response

    def _clear(self, point, channel):
        obs = yield Action('/clear', point, channel)
        if obs.response.get('clear_result') == 'success':
            self._cleared.add(channel)
            return True
        return False

    def _localize(self, p, first, channel):
        if first['measure_result'] == 'near':
            yield from self._clear(p, channel)
            return
        angle = first['svd_deg']
        for attempt in range(4):
            baseline = 200 if attempt == 0 else 45
            estimate = None
            for side in (1, -1):
                q = advance(p, angle + side*90, baseline)
                result = yield from self._measure(q, channel)
                if result['measure_result'] == 'near':
                    yield from self._clear(q, channel)
                    return
                if result['measure_result'] == 'direction':
                    estimate = intersect(p, angle, q, result['svd_deg'])
                    if estimate is not None: break
            if estimate is None: return
            if (yield from self._clear(estimate, channel)): return
            result = yield from self._measure(estimate, channel)
            if result['measure_result'] == 'near':
                yield from self._clear(estimate, channel)
                return
            if result['measure_result'] == 'no_signal':
                # Estimate can fall behind a directional sector. Optical search ignores angle.
                for dx, dy in ((30,0),(-30,0),(0,30),(0,-30),(30,30),(-30,30),(30,-30),(-30,-30)):
                    if (yield from self._clear((estimate[0]+dx, estimate[1]+dy), channel)): return
                return
            p, angle = estimate, result['svd_deg']

    def _run(self):
        grid = [i*self.spacing for i in range(-self.extent//self.spacing, self.extent//self.spacing+1)]
        # Start at origin, then cover a fixed search grid without reading case truth.
        waypoints = [(0., 0.)]
        for row, y in enumerate(grid):
            waypoints.extend((float(x), float(y)) for x in (grid if row % 2 == 0 else grid[::-1]))
        for point in waypoints:
            for channel in range(1, 21):
                if channel in self._cleared: continue
                result = yield from self._measure(point, channel)
                if result['measure_result'] != 'no_signal':
                    yield from self._localize(point, result, channel)
        yield Action('/exit')
