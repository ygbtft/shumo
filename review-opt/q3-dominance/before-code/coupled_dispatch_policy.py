"""Link scan order with localization entry/exit predictions using public state."""
import numpy as np

from bounded_width_policy import BoundedWidthPacketPolicy
from completion_sensing_policy import CompletionClearancePolicy
from wide_probe_policy import WidePacketPolicy


def arc_route(entries, exits, current, polish=True):
    """Open nearest-neighbor route, then exact directed segment reversals.

    Each task's internal service cost is constant for a fixed task set, so it
    cancels when comparing task orders. Only inter-task transfers are ranked.
    """
    entries, exits = np.asarray(entries), np.asarray(exits)
    n = len(entries)
    costs = np.linalg.norm(exits[:, None] - entries[None, :], axis=2)
    start = np.linalg.norm(entries - current, axis=1)
    unused, route = list(range(n)), []
    while unused:
        values = start[unused] if not route else costs[route[-1], unused]
        route.append(unused.pop(int(np.argmin(values))))
    route = np.asarray(route, dtype=int)
    if polish:
        for _ in range(3):
            changed = False
            for i in range(n-1):
                for j in range(i+1, n):
                    if i == 0:
                        delta = start[route[j]]-start[route[i]]
                    else:
                        delta = costs[route[i-1], route[j]]-costs[route[i-1], route[i]]
                    if j+1 < n:
                        delta += costs[route[i], route[j+1]]-costs[route[j], route[j+1]]
                    # Reversing a directed path changes all its internal arcs.
                    a, b = route[i:j], route[i+1:j+1]
                    delta += float((costs[b, a]-costs[a, b]).sum())
                    if delta < -1e-7:
                        route[i:j+1] = route[i:j+1][::-1]
                        changed = True
            if not changed:
                break
    return route


def insert_sources(tasks, station_count, current):
    """Cheapest insertion of known-source centers; scan order stays fixed."""
    # The task prefix contains station_count scans; the suffix contains known sources.
    # Preserve scan relative order only; cheapest insertion is not globally optimal.
    points = np.asarray([task[2] for task in tasks])
    route, pending = list(range(station_count)), list(range(station_count, len(tasks)))
    while pending:
        options = []
        for item in pending:
            for at in range(len(route)+1):
                previous = current if at == 0 else points[route[at-1]]
                cost = np.linalg.norm(points[item]-previous)
                if at < len(route):
                    cost += np.linalg.norm(points[route[at]]-points[item])-np.linalg.norm(points[route[at]]-previous)
                options.append((float(cost), item, at))
        _, item, at = min(options)
        route.insert(at, item)
        pending.remove(item)
    return route


class CertifiedRangeSkipMixin:
    def __init__(self, *args, range_skip=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.range_skip = range_skip
        self.stats.update(certified_range_scan_skips=0, inferred_negative_memory_updates=0)

    def measure(self, p, ch):
        if self.range_skip and self._surveying and ch in self.regions and ch not in self.cleared:
            center, radius = self.circle(ch)
            if np.linalg.norm(p-center) > 1500. + radius + 1e-5:
                # Every feasible source is farther than its maximum possible
                # receiving radius. This is an inference, not a fabricated RF
                # response: no client position/channel/time is modified.
                self.stats["certified_range_scan_skips"] += 1
                # Q4 memory only filters sharing usefulness via cooldown; it never clips region.
                if hasattr(self, "_last_negative"):
                    self._last_negative[ch] = np.asarray(p).copy()
                    self.stats["inferred_negative_memory_updates"] += 1
                # Internal event only: never serialize this as an official RF response.
                return "certified_no_reception"
        return super().measure(p, ch)


class CoupledDispatchMixin:
    def __init__(self, *args, dispatch_model="arc", entry_blend=1., arc_polish=True, **kwargs):
        if dispatch_model not in ("base", "arc", "locked") or not 0. <= entry_blend <= 1.:
            raise ValueError("Unknown route model or entry weight")
        super().__init__(*args, **kwargs)
        self.dispatch_model, self.entry_blend, self.arc_polish = dispatch_model, entry_blend, arc_polish
        self.stats.update(coupled_route_plans=0, fixed_scan_order=dispatch_model == "locked",
                          service_entry_weight=entry_blend, coupled_dispatch_model=dispatch_model)

    def service_entry(self, ch, center):
        # Q3's exact next sensing point is expensive to score for every task;
        # this round uses the center model there and tests fixed scan order.
        if not self.mixed:
            return center
        radius = self.circle(ch)[1]
        step = self._rounds[ch]
        if (radius <= 20.-1e-5 or step >= self.bracket_steps
                or (radius <= self.bracket_trial_radius and ch not in self.bracket_tried)):
            return center
        entry = self.probes(ch, step)[3][0]
        return (1-self.entry_blend)*center + self.entry_blend*entry

    def next_task(self, unused):
        if self.dispatch_model == "base" or (self.dispatch_model == "arc" and self.entry_blend == 0.):
            return super().next_task(unused)
        if len(set(self.regions) | self.cleared) == 16:
            self.stats["known_upper_bound_skips"] += len(unused)
            unused.clear()
        previous = getattr(self, "_last_partial", None)
        if previous is not None and previous not in self.cleared and self.stats["source_interruptions"] >= self.pause_limit:
            self.stats["forced_continuations"] += 1
            return "source", previous, self.circle(previous)[0]
        tasks = [("survey", i, self.stations[i]) for i in unused]
        station_count = len(tasks)
        tasks.extend(("source", ch, self.circle(ch)[0]) for ch in self.regions if ch not in self.cleared)
        if not tasks:
            return None
        self.stats["coupled_route_plans"] += 1
        if self.dispatch_model == "locked":
            route = insert_sources(tasks, station_count, self.client.position)
        else:
            entries = [p if kind == "survey" else self.service_entry(key, p) for kind, key, p in tasks]
            exits = [p for _, _, p in tasks]
            route = arc_route(entries, exits, self.client.position, self.arc_polish)
        task = tasks[int(route[0])]
        if previous is not None and previous not in self.cleared and task[:2] != ("source", previous):
            self.stats["source_interruptions"] += 1
            self._interrupted_channels.add(previous)
        return task


class CoupledWidthPolicy(CertifiedRangeSkipMixin, CoupledDispatchMixin, BoundedWidthPacketPolicy):
    pass


class CoupledWidePolicy(CertifiedRangeSkipMixin, CoupledDispatchMixin, WidePacketPolicy):
    pass


class CoupledCompletionPolicy(CertifiedRangeSkipMixin, CoupledDispatchMixin, CompletionClearancePolicy):
    pass
