"""Batch reversal candidates while preserving the scalar decision order."""
import numpy as np
from fast_dispatch_policy import fast_arc_route
from service_aware_policy import (directed_insertion, reversal_prefix,
    route_objective, ServiceAwareWidthPolicy, ServiceAwareCompletionPolicy)


def vector_service_route(entries, exits, current, precedence, station_count, mode="free", polish=True):
    entries, exits = np.asarray(entries), np.asarray(exits)
    if mode == "free" and not np.any(precedence):
        return fast_arc_route(entries, exits, current, polish)
    n = len(entries)
    costs = np.linalg.norm(exits[:, None]-entries[None, :], axis=2)
    start = np.linalg.norm(entries-current, axis=1)
    if mode == "locked":
        route = directed_insertion(costs, start, precedence, station_count)
    else:
        pending, chosen = list(range(n)), []
        while pending:
            p = np.asarray(pending)
            travel = start[p] if not chosen else costs[chosen[-1], p]
            scores = travel+precedence[np.ix_(p, p)].sum(1)
            chosen.append(pending.pop(int(np.argmin(scores))))
        route = np.asarray(chosen, dtype=int)
    if not polish:
        return route
    arc, square = reversal_prefix(route, costs, precedence)
    for _ in range(3):
        changed = False
        for i in range(n-1):
            lower = i+1
            while lower < n:
                js = np.arange(lower, n)
                if mode == "locked":
                    # Once an interval contains two stations, every longer
                    # interval is forbidden. Avoid scalar NumPy calls per pair.
                    station_prefix = np.r_[0, np.cumsum(route < station_count)]
                    js = js[station_prefix[js+1]-station_prefix[i] <= 1]
                    if not len(js):
                        break
                ends = route[js]
                delta = start[ends]-start[route[i]] if i == 0 else costs[route[i-1], ends]-costs[route[i-1], route[i]]
                interior = js+1 < n
                nxt = route[js[interior]+1]
                delta[interior] += costs[route[i], nxt]-costs[ends[interior], nxt]
                delta += arc[js]-arc[i]
                delta += square[js+1, js+1]-square[i, js+1]-square[js+1, i]+square[i, i]
                for near in np.flatnonzero(np.abs(delta+1e-7) < 1e-6):
                    j = int(js[near])
                    candidate = route.copy()
                    candidate[i:j+1] = candidate[i:j+1][::-1]
                    delta[near] = route_objective(candidate, costs, start, precedence)-route_objective(route, costs, start, precedence)
                better = np.flatnonzero(delta < -1e-7)
                if not len(better):
                    break
                # Apply only the first accepted scalar-order reversal. All
                # later candidates must be recomputed from the changed route.
                j = int(js[int(better[0])])
                route[i:j+1] = route[i:j+1][::-1]
                arc, square = reversal_prefix(route, costs, precedence)
                changed = True
                lower = j+1
        if not changed:
            break
    return route


class VectorServiceMixin:
    def next_task(self, unused):
        # Same public task construction and lifetime accounting as the scalar
        # dispatcher; only the internal route calculation is substituted.
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
        entries = [p if kind == "survey" else self.service_entry(key, p) for kind, key, p in tasks]
        exits = [p for _, _, p in tasks]
        precedence = self.precedence_costs(tasks, station_count)
        route = vector_service_route(entries, exits, self.client.position, precedence, station_count, self.service_mode, self.arc_polish)
        self.stats["service_route_plans"] += 1
        task = tasks[int(route[0])]
        if previous is not None and previous not in self.cleared and task[:2] != ("source", previous):
            self.stats["source_interruptions"] += 1
            self._interrupted_channels.add(previous)
        return task


class VectorServiceWidthPolicy(VectorServiceMixin, ServiceAwareWidthPolicy):
    pass


class VectorServiceCompletionPolicy(VectorServiceMixin, ServiceAwareCompletionPolicy):
    pass
