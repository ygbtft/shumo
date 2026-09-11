"""State machine, physical rules and microsecond clock (no wall-time sleeps)."""
from dataclasses import dataclass
import math
import time
from .geometry import bearing, covered, distance
from .error_field import ErrorField

class InterfaceClosed(ConnectionError):
    """No HTTP status or JSON body is available."""

@dataclass(frozen=True)
class Limits:
    countdown_s: float = 5.0
    window_s: float = 1500.0
    real_s: float = 1200.0
    virtual_s: float = 360000.0
    max_records: int = 200000  # 假设 A7：附件未给出容量。
    replay_after_end: bool = False  # 假设 A6：默认接口关闭优先于历史响应重放。

    def __post_init__(self):
        if self.countdown_s < 0 or not math.isfinite(self.countdown_s):
            raise ValueError('invalid countdown')
        if any(not math.isfinite(v) or v <= 0 for v in (self.window_s, self.real_s, self.virtual_s)):
            raise ValueError('invalid deadline')
        if self.max_records < 1: raise ValueError('max_records must be positive')

class Simulator:
    def __init__(self, scenario, error=None, limits=None, clock=time.monotonic, wall_clock=time.time):
        self.scenario = scenario
        self.error = error or ErrorField(scenario.seed)
        self.limits = limits or Limits()
        self.clock, self.wall_clock = clock, wall_clock
        self.open_at = clock() + self.limits.countdown_s
        self.entered_at = None
        self.ended_at = None
        self.end_reason = None
        self.position = (0., 0.)
        self.channel = 1
        self.time_us = 0
        self.cleared = set()
        self.sources = {s.channel: s for s in scenario.sources}
        self.trace = []
        self.enabled = True

    @property
    def virtual_time_s(self):
        return self.time_us / 1_000_000

    def envelope(self, accepted=False, **fields):
        return dict(accepted=accepted, real_timestamp_ms=int(self.wall_clock()*1000),
                    virtual_time_s=self.virtual_time_s if accepted else 0, **fields)

    def end(self, reason):
        if self.end_reason is None:
            self.end_reason = reason
            self.ended_at = self.clock()

    def check_open(self, arrival=None):
        now = self.clock() if arrival is None else arrival
        if not self.enabled or now < self.open_at:
            raise InterfaceClosed('interface_not_open')
        if self.end_reason is None:
            if now >= self.open_at + self.limits.window_s:
                self.end('window_timeout')
            elif self.entered_at is not None and now >= self.entered_at + self.limits.real_s:
                self.end('real_timeout')
            elif self.virtual_time_s >= self.limits.virtual_s:
                self.end('virtual_timeout')
        if self.end_reason is not None:
            raise InterfaceClosed(self.end_reason)

    def execute(self, path, payload, arrival):
        """Caller validated and registered this action before the deadline; single writer."""
        if path == '/enter':
            if self.entered_at is not None: return self.envelope()
            self.entered_at = arrival
            remaining = max(0, math.floor(min(self.limits.real_s, self.open_at + self.limits.window_s - arrival)))
            response = self.envelope(True, max_virtual_duration_s=self.limits.virtual_s,
                                     max_real_duration_s=self.limits.real_s, remaining_real_duration_s=remaining)
        elif self.entered_at is None:
            return self.envelope()
        elif path == '/exit':
            self.end('user_exit')
            response = self.envelope(True, exit_reason='user_exit')
        else:
            point = (float(payload['position']['x']), float(payload['position']['y']))
            channel = int(payload['channel'])
            source = self.sources.get(channel) if channel not in self.cleared else None
            move_s = distance(self.position, point) / 5
            fields = {}
            switch_s = 0
            if path == '/measure':
                switch_s = int(channel != self.channel)
                action_s = 5
                if source is None or not covered(source, point):
                    fields['measure_result'] = 'no_signal'
                elif distance(source.position, point) <= 5:
                    fields['measure_result'] = 'near'
                else:
                    fields['measure_result'] = 'direction'
                    angle = (bearing(point, source.position) + self.error.value(point, channel)) % 360
                    # 假设 A5：半向上舍入两位，然后归一化（避免 360.00）。
                    fields['svd_deg'] = (math.floor(angle*100 + 0.5) / 100) % 360
            else:
                success = source is not None and distance(point, source.position) <= 20
                action_s = 5 if success else 3
                fields['clear_result'] = 'success' if success else 'no_target_in_range'
            # Compute first, then commit: exceptions during physics cannot partly move the dog.
            # 假设 A5：每动作移动时间取最近微秒（半向上），再加整数动作时间。
            delta_us = math.floor(move_s*1_000_000 + 0.5) + (switch_s + action_s)*1_000_000
            self.position = point
            if path == '/measure': self.channel = channel
            elif success: self.cleared.add(channel)
            self.time_us += delta_us
            response = self.envelope(True, **fields)
        self.trace.append({'path': path, 'request': payload, 'response': response,
                           'position': list(self.position)})
        # 截止前登记的完整动作可完成，包括跨过虚拟上限的动作。
        if self.virtual_time_s >= self.limits.virtual_s:
            self.end('virtual_timeout')
        elif self.clock() >= self.open_at + self.limits.window_s:
            self.end('window_timeout')
        elif self.entered_at is not None and self.clock() >= self.entered_at + self.limits.real_s:
            self.end('real_timeout')
        return response
