"""Public-state task routing with an explicit cost for unfinished RF scans.

The frozen-region objective ranks actions only. It neither supplies future
feedback nor certifies completion. All geometry and lifetime budgets are
inherited from the bounded policies.
"""
import numpy as np
from fast_dispatch_policy import fast_arc_route
from coupled_dispatch_policy import CoupledWidthPolicy, CoupledCompletionPolicy


def route_objective(route, costs, start, precedence):
    r = np.asarray(route, dtype=int)
    if not len(r):
        return 0.
    value = start[r[0]] + costs[r[:-1], r[1:]].sum()
    return float(value + np.triu(precedence[np.ix_(r, r)], 1).sum())


def reversal_prefix(route, costs, precedence):
    r = np.asarray(route, dtype=int)
    arc = np.r_[0., np.cumsum(costs[r[1:], r[:-1]] - costs[r[:-1], r[1:]])]
    w = precedence[np.ix_(r, r)]
    square = np.pad(np.triu(w.T-w, 1).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    return arc, square


def reversal_delta(route, i, j, costs, start, prefixes):
    r = route
    arc, square = prefixes
    delta = start[r[j]]-start[r[i]] if i == 0 else costs[r[i-1], r[j]]-costs[r[i-1], r[i]]
    if j+1 < len(r):
        delta += costs[r[i], r[j+1]]-costs[r[j], r[j+1]]
    delta += arc[j]-arc[i]
    delta += square[j+1, j+1]-square[i, j+1]-square[j+1, i]+square[i, i]
    return float(delta)


def directed_insertion(costs, start, precedence, station_count):
    """Keep scan order and vectorize every source/position insertion delta."""
    route = list(range(station_count))
    pending = list(range(station_count, len(start)))
    while pending:
        if not route:
            item = min(pending, key=lambda x: (float(start[x]), x))
            route.append(item)
            pending.remove(item)
            continue
        r, p = np.asarray(route), np.asarray(pending)
        before = np.column_stack((start[p], costs[np.ix_(r, p)].T))
        after = np.column_stack((costs[np.ix_(p, r)], np.zeros(len(p))))
        removed = np.r_[start[r[0]], costs[r[:-1], r[1:]], 0.]
        left = np.column_stack((np.zeros(len(p)), precedence[np.ix_(r, p)].T.cumsum(1)))
        right = np.column_stack((precedence[np.ix_(p, r)][:, ::-1].cumsum(1)[:, ::-1], np.zeros(len(p))))
        delta = before+after-removed+left+right
        item_at, location = np.unravel_index(int(np.argmin(delta)), delta.shape)
        item = pending.pop(int(item_at))
        route.insert(int(location), item)
    return np.asarray(route, dtype=int)


def service_route(entries, exits, current, precedence, station_count, mode="free", polish=True):
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
            # Choosing a task now fixes its precedence relative to all pending
            # tasks. This is a deterministic, frozen-state planning cost.
            scores = travel + precedence[np.ix_(p, p)].sum(1)
            chosen.append(pending.pop(int(np.argmin(scores))))
        route = np.asarray(chosen, dtype=int)
    if polish:
        prefixes = reversal_prefix(route, costs, precedence)
        for _ in range(3):
            changed = False
            for i in range(n-1):
                for j in range(i+1, n):
                    if mode == "locked" and np.count_nonzero(route[i:j+1] < station_count) > 1:
                        continue
                    delta = reversal_delta(route, i, j, costs, start, prefixes)
                    if abs(delta+1e-7) < 1e-6:
                        candidate = route.copy()
                        candidate[i:j+1] = candidate[i:j+1][::-1]
                        delta = route_objective(candidate, costs, start, precedence)-route_objective(route, costs, start, precedence)
                    if delta < -1e-7:
                        route[i:j+1] = route[i:j+1][::-1]
                        prefixes = reversal_prefix(route, costs, precedence)
                        changed = True
            if not changed:
                break
    return route


class ServiceAwareMixin:
    def __init__(self, *args, scan_cost_weight=1., scan_order_cost_s=0., service_mode="free", **kwargs):
        if not 0. <= scan_cost_weight <= 2. or not 0. <= scan_order_cost_s <= 50. or service_mode not in ("free", "locked"):
            raise ValueError("Unvalidated service-routing parameters")
        super().__init__(*args, **kwargs)
        self.scan_cost_weight, self.scan_order_cost_s = scan_cost_weight, scan_order_cost_s
        self.service_mode = service_mode
        self.stats.update(service_route_plans=0, service_scan_cost_weight=scan_cost_weight,
                          service_scan_order_cost_s=scan_order_cost_s, service_order_mode=service_mode,
                          modeled_known_scan_pairs=0)

    def precedence_costs(self, tasks, station_count):
        costs = np.zeros((len(tasks), len(tasks)))
        if self.scan_order_cost_s:
            # Only the relative order of remaining certified scan stations is
            # penalized; no source-location prior is used here.
            costs[:station_count, :station_count] = np.tril(np.full((station_count, station_count), 5.*self.scan_order_cost_s), -1)
        if not self.scan_cost_weight or not station_count:
            return costs
        stations = np.asarray([p for _, _, p in tasks[:station_count]])
        for index in range(station_count, len(tasks)):
            _, ch, center = tasks[index]
            radius = self.circle(ch)[1]
            if radius <= 20.-1e-5:
                continue  # already skipped by the actual scan policy
            needed = np.linalg.norm(stations-center, axis=1) <= 1500.+radius+1e-5
            self.stats["modeled_known_scan_pairs"] += int(needed.sum())
            # 5 s RF cost, converted to route meters at the specified 5 m/s.
            # Switch fees and future region shrinkage are not guessed as exact.
            costs[:station_count, index] = needed*(25.*self.scan_cost_weight)
        return costs

    def next_task(self, unused):
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
        route = service_route(entries, exits, self.client.position, precedence, station_count, self.service_mode, self.arc_polish)
        self.stats["service_route_plans"] += 1
        task = tasks[int(route[0])]
        if previous is not None and previous not in self.cleared and task[:2] != ("source", previous):
            self.stats["source_interruptions"] += 1
            self._interrupted_channels.add(previous)
        return task


class ServiceAwareWidthPolicy(ServiceAwareMixin, CoupledWidthPolicy):
    pass


class ServiceAwareCompletionPolicy(ServiceAwareMixin, CoupledCompletionPolicy):
    pass
