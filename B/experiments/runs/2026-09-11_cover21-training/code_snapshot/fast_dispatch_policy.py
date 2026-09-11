"""Faster route accounting, with exact near-threshold comparisons preserved."""
import numpy as np
from coupled_dispatch_policy import CoupledWidthPolicy, CoupledCompletionPolicy
from negative_hull_policy import NegativeHullMixin


def fast_arc_route(entries, exits, current, polish=True):
    entries, exits = np.asarray(entries), np.asarray(exits)
    n=len(entries)
    costs=np.linalg.norm(exits[:,None]-entries[None,:],axis=2)
    start=np.linalg.norm(entries-current,axis=1)
    unused,route=list(range(n)),[]
    while unused:
        values=start[unused] if not route else costs[route[-1],unused]
        route.append(unused.pop(int(np.argmin(values))))
    route=np.asarray(route,dtype=int)
    def reverse_prefix():
        a,b=route[:-1],route[1:]
        return np.r_[0.,np.cumsum(costs[b,a]-costs[a,b])]
    if polish:
        prefix=reverse_prefix()
        for _ in range(3):
            changed=False
            for i in range(n-1):
                for j in range(i+1,n):
                    boundary=start[route[j]]-start[route[i]] if i==0 else costs[route[i-1],route[j]]-costs[route[i-1],route[i]]
                    if j+1<n:
                        boundary+=costs[route[i],route[j+1]]-costs[route[j],route[j+1]]
                    delta=boundary+prefix[j]-prefix[i]
                    # Avoid turning floating summation changes near the
                    # decision threshold into a different route.
                    if abs(delta+1e-7)<1e-6:
                        a,b=route[i:j],route[i+1:j+1]
                        delta=boundary+float((costs[b,a]-costs[a,b]).sum())
                    if delta < -1e-7:
                        route[i:j+1]=route[i:j+1][::-1]
                        prefix=reverse_prefix()
                        changed=True
            if not changed:
                break
    return route


def cached_insert_sources(tasks, station_count, current):
    points=np.asarray([task[2] for task in tasks])
    origin=len(points)
    cache={}
    def distance(a,b):
        key=(min(a,b),max(a,b))
        if key not in cache:
            p=current if a==origin else points[a]
            q=current if b==origin else points[b]
            cache[key]=np.linalg.norm(p-q)
        return cache[key]
    route,pending=list(range(station_count)),list(range(station_count,len(tasks)))
    while pending:
        options=[]
        for item in pending:
            for at in range(len(route)+1):
                previous=origin if at==0 else route[at-1]
                cost=distance(item,previous)
                if at<len(route):
                    cost+=distance(route[at],item)-distance(route[at],previous)
                options.append((float(cost),item,at))
        _,item,at=min(options)
        route.insert(at,item)
        pending.remove(item)
    return route


class FastDispatchMixin:
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.stats["dispatch_implementation"]="cached_distance_prefix_sum"

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
            route = cached_insert_sources(tasks, station_count, self.client.position)
        else:
            entries = [p if kind == "survey" else self.service_entry(key, p) for kind, key, p in tasks]
            exits = [p for _, _, p in tasks]
            route = fast_arc_route(entries, exits, self.client.position, self.arc_polish)
        task = tasks[int(route[0])]
        if previous is not None and previous not in self.cleared and task[:2] != ("source", previous):
            self.stats["source_interruptions"] += 1
            self._interrupted_channels.add(previous)
        return task


class FastWidthPolicy(FastDispatchMixin,CoupledWidthPolicy):
    pass


class FastCompletionPolicy(FastDispatchMixin,CoupledCompletionPolicy):
    pass


class FastNegativeWidthPolicy(NegativeHullMixin,FastWidthPolicy):
    pass
