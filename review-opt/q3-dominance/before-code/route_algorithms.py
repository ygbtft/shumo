"""Permutation routing variants; no simulator, source count or truth is imported.

All stochastic methods are explicitly discrete hybrids with the SAME bounded
2-opt operator. A budget counts candidate comparisons (full and delta scores),
not CPU instructions. Origin is a required station and is visited first.
These are auditable implementations of the named mechanisms, not reproductions
of paper-specific parameter settings or claims of a new AI algorithm.
"""
from dataclasses import dataclass
from fractions import Fraction
import math
import time
import numpy as np
from coverage import route, route_length

STOCHASTIC = ("genetic", "immune", "ant_colony", "particle_swarm", "fireworks", "iterated_search")
METHODS = ("greedy", "insertion_greedy", "two_opt") + STOCHASTIC


@dataclass
class Budget:
    limit: int
    comparisons: int = 0
    full_scores: int = 0
    delta_scores: int = 0

    @property
    def remaining(self):
        return self.limit - self.comparisons


class Problem:
    def __init__(self, points):
        self.points = np.asarray(points, float)
        if self.points.ndim != 2 or self.points.shape[1] != 2 or len(self.points) < 3:
            raise ValueError("Need at least three distinct planar stations")
        if not np.isfinite(self.points).all() or len(np.unique(self.points, axis=0)) != len(self.points):
            raise ValueError("Stations must be finite and distinct")
        origins = np.flatnonzero(np.linalg.norm(self.points, axis=1) < 1e-9)
        if len(origins) != 1:
            raise ValueError("Exactly one station at the fixed start is required")
        self.origin = int(origins[0])
        self.n = len(self.points)
        self.d = np.linalg.norm(self.points[:, None] - self.points[None, :], axis=2)
        self.min_edge = float(self.d[np.triu_indices(self.n, 1)].min())
        self.lower_bound = (self.n - 1) * self.min_edge
        self.bound_kind = "(n-1) times minimum interstation distance"
        # Prove integer multiples of h for the actual input floats. Even an
        # exactly integral floating-point quotient can hide division rounding.
        spacing = Fraction(self.min_edge)
        integer_grid = True
        parities = []
        for point in self.points:
            numerator_sum = 0
            for coordinate in point:
                scaled_coordinate = Fraction(float(coordinate)) / spacing
                if scaled_coordinate.denominator != 1:
                    integer_grid = False
                numerator_sum += scaled_coordinate.numerator
            parities.append(numerator_sum % 2)
        if integer_grid:
            colors = np.array(parities)
            a = int(np.count_nonzero(colors == colors[self.origin]))
            b = self.n-a
            # A-start path: at most A runs of B and at most B+1 runs of A.
            # Same-color edges cost >=sqrt(2)h, other edges >=h.
            same_edges = max(0, b-a, a-b-1)
            self.lower_bound += same_edges*(math.sqrt(2)-1)*self.min_edge
            self.bound_kind = f"square checkerboard: colors {a}/{b}, at least {same_edges} same-color edges"
        self.nn = self.indices(route(self.points, optimized=False))
        self.initial = self.indices(route(self.points, optimized=True))
        self.validate(self.initial)

    def indices(self, coordinates):
        return np.array([np.argmin(np.linalg.norm(self.points - q, axis=1)) for q in coordinates], dtype=int)

    def validate(self, order):
        assert len(order) == self.n and int(order[0]) == self.origin
        assert np.array_equal(np.sort(order), np.arange(self.n)), "Lost/duplicate coverage station"

    def cost(self, order, budget=None):
        if budget is not None:
            if budget.remaining <= 0:
                raise RuntimeError("Comparison budget exhausted")
            budget.comparisons += 1
            budget.full_scores += 1
        return float(self.d[order[:-1], order[1:]].sum())


def two_opt(problem, order, budget, sweeps=4):
    """Strict descent; suffix reversals are included because terminal is free."""
    order = np.array(order, dtype=int, copy=True)
    d, n = problem.d, problem.n
    for _ in range(sweeps):
        changed = False
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                if budget.remaining <= 0:
                    return order
                a, b, c = order[i-1], order[i], order[j]
                delta = d[a, c] - d[a, b]
                if j + 1 < n:
                    z = order[j+1]
                    delta += d[b, z] - d[c, z]
                budget.comparisons += 1
                budget.delta_scores += 1
                if delta < -1e-7:
                    order[i:j+1] = order[i:j+1][::-1]
                    changed = True
        if not changed:
            break
    return order


def perturb(order, rng, strength=1):
    """Mix inversion, relocation and swaps; origin is never moved."""
    q = np.array(order, copy=True)
    for _ in range(max(1, int(strength))):
        a, b = sorted(rng.choice(np.arange(1, len(q)), 2, replace=False))
        kind = int(rng.integers(3))
        if kind == 0:
            q[a:b+1] = q[a:b+1][::-1]
        elif kind == 1:
            q[a:b+1] = np.roll(q[a:b+1], 1 if rng.random() < .5 else -1)
        else:
            q[a], q[b] = q[b], q[a]
    return q


def insertion_greedy(problem, budget):
    order = [problem.origin]
    unused = set(range(problem.n)) - set(order)
    while unused:
        best = None
        for v in sorted(unused):
            for k in range(1, len(order)+1):
                if budget.remaining <= 0:
                    # Keep completed insertions and complete the feasible path
                    # in shared-initialization order without scoring candidates.
                    return np.array(order + [int(v) for v in problem.initial if v in unused])
                a = order[k-1]
                delta = problem.d[a, v]
                if k < len(order):
                    b = order[k]
                    delta += problem.d[v, b] - problem.d[a, b]
                budget.comparisons += 1
                budget.delta_scores += 1
                if best is None or (delta, v, k) < best:
                    best = (delta, v, k)
        _, v, k = best
        order.insert(k, v)
        unused.remove(v)
    return np.array(order)


def order_crossover(a, b, rng):
    lo, hi = sorted(rng.choice(np.arange(1, len(a)), 2, replace=False))
    child = np.full(len(a), -1, dtype=int)
    child[0] = a[0]
    child[lo:hi+1] = a[lo:hi+1]
    used = set(child[child >= 0])
    positions = list(range(hi+1, len(a))) + list(range(1, lo))
    values = [int(v) for v in np.concatenate((b[hi+1:], b[1:hi+1])) if v not in used]
    child[positions] = values
    return child


def swap_difference(source, target):
    """Discrete velocity mapping one permutation into another exactly."""
    work = np.array(source, copy=True)
    where = np.empty(len(work), dtype=int)
    where[work] = np.arange(len(work))
    result = []
    for i in range(1, len(work)):
        if work[i] == target[i]:
            continue
        j = int(where[target[i]])
        vi, vj = int(work[i]), int(work[j])
        work[i], work[j] = vj, vi
        where[vi], where[vj] = j, i
        result.append((i, j))
    return result


class Search:
    def __init__(self, problem, seed, limit, polish=True):
        self.p = problem
        self.rng = np.random.default_rng(seed)
        self.budget = Budget(limit)
        self.best = problem.initial.copy()
        self.best_cost = problem.cost(self.best, self.budget)
        self.history = [{"comparisons": 1, "best_m": self.best_cost}]
        self.polish = polish
        self.polishes = 0
        self.candidates = 0
        self.raw_best = self.best_cost

    @property
    def running(self):
        return self.budget.remaining > 1 and self.best_cost > self.p.lower_bound + 1e-6

    def evaluate(self, candidate, local=False):
        q = np.array(candidate, copy=True)
        value = self.p.cost(q, self.budget)
        self.candidates += 1
        self.raw_best = min(self.raw_best, value)
        if local and self.polish and self.budget.remaining > 1:
            # Reserve a full verification score; delta comparisons are charged.
            self.budget.limit -= 1
            q = two_opt(self.p, q, self.budget, sweeps=3)
            self.budget.limit += 1
            self.polishes += 1
            value = self.p.cost(q, self.budget)
        if value < self.best_cost - 1e-7:
            self.best, self.best_cost = q.copy(), value
            self.history.append({"comparisons": self.budget.comparisons, "best_m": value})
        return q, value

    def population(self, n):
        pop = [(self.best.copy(), self.best_cost)]
        for i in range(n-1):
            if not self.running:
                break
            if i % 4 == 3:
                q = np.r_[self.p.origin, self.rng.permutation([j for j in range(self.p.n) if j != self.p.origin])]
            else:
                q = perturb(self.best, self.rng, 1+i%4)
            pop.append(self.evaluate(q, local=False))
        return pop


def genetic(search):
    """Elitism + tournament selection + order crossover + mixed mutation."""
    pop = search.population(32)
    generation = 0
    while search.running:
        pop.sort(key=lambda t: t[1])
        new = pop[:4]
        while len(new) < 32 and search.running:
            first_tournament = search.rng.integers(len(pop), size=3)
            a = pop[min(first_tournament)][0]
            second_tournament = search.rng.integers(len(pop), size=3)
            b = pop[min(second_tournament)][0]
            child = order_crossover(a, b, search.rng)
            if search.rng.random() < .65:
                child = perturb(child, search.rng, 1 + int(search.rng.random() < .15))
            new.append(search.evaluate(child, local=(len(new) % 8 == generation % 8)))
        pop = new
        generation += 1


def immune(search):
    """Clonal selection: rank-dependent clones/hypermutation, memory, immigrants."""
    pop = search.population(24)
    while search.running:
        pop.sort(key=lambda t: t[1])
        pool = pop[:8]
        for rank, (parent, _) in enumerate(pop[:8]):
            clones = max(1, 8-rank)
            for c in range(clones):
                if not search.running:
                    break
                # Higher affinity => more clones, gentler mutation.
                child = perturb(parent, search.rng, 1+rank//2)
                pool.append(search.evaluate(child, local=c == 0))
        if search.running:
            for _ in range(4):
                if not search.running:
                    break
                q = np.r_[search.p.origin, search.rng.permutation([j for j in range(search.p.n) if j != search.p.origin])]
                pool.append(search.evaluate(q))
        # Suppress identical antibodies and preserve elite memory.
        unique = {}
        for q, value in sorted(pool, key=lambda t: t[1]):
            unique.setdefault(tuple(q), (q, value))
        pop = list(unique.values())[:24]


def ant_colony(search):
    """Ant System: pheromone * inverse-distance heuristic, evaporation, elite deposit."""
    p, rng = search.p, search.rng
    tau = np.ones((p.n, p.n), float)
    eta = (p.min_edge / np.maximum(p.d, p.min_edge*.01)) ** 3
    np.fill_diagonal(eta, 0.)
    generation = 0
    while search.running:
        ants = []
        for ant in range(20):
            if not search.running:
                break
            path = [p.origin]
            left = [i for i in range(p.n) if i != p.origin]
            while left:
                w = tau[path[-1], left] * eta[path[-1], left]
                # Exploration remains positive; q0 exploitation is .2.
                if rng.random() < .2:
                    ix = int(np.argmax(w))
                else:
                    ix = min(len(left)-1, int(np.searchsorted(np.cumsum(w), rng.random()*w.sum())))
                path.append(left.pop(ix))
            ants.append(search.evaluate(np.array(path), local=ant % 8 == generation % 8))
        tau *= .8
        for q, value in sorted(ants, key=lambda t: t[1])[:4] + [(search.best, search.best_cost)]:
            deposit = p.lower_bound / value
            tau[q[:-1], q[1:]] += deposit
            tau[q[1:], q[:-1]] += deposit
        np.clip(tau, .05, 20., out=tau)
        generation += 1


def particle_swarm(search):
    """Permutation PSO: swap velocities with inertia, personal and social attraction."""
    pop = search.population(24)
    personal = [(q.copy(), v) for q, v in pop]
    velocities = [[] for _ in pop]
    generation = 0
    while search.running:
        for i, (q, _) in enumerate(pop):
            if not search.running:
                break
            velocity = [s for s in velocities[i] if search.rng.random() < .35]
            velocity += [s for s in swap_difference(q, personal[i][0]) if search.rng.random() < .45]
            velocity += [s for s in swap_difference(q, search.best) if search.rng.random() < .55]
            velocity = velocity[-2*search.p.n:]
            child = q.copy()
            for a, b in velocity:
                child[a], child[b] = child[b], child[a]
            if search.rng.random() < .45 or not velocity:
                child = perturb(child, search.rng)
            item = search.evaluate(child, local=i % 8 == generation % 8)
            pop[i], velocities[i] = item, velocity
            if item[1] <= personal[i][1] + 1e-7:
                personal[i] = (item[0].copy(), item[1])
        generation += 1


def fireworks(search):
    """Discrete fireworks: fitness-dependent spark counts/amplitudes and diversity."""
    pop = search.population(6)
    while search.running:
        values = np.array([v for q, v in pop])
        spread = max(float(np.ptp(values)), 1.)
        qualities = (values.max() - values + .05*spread)
        counts = np.clip(np.rint(36*qualities/qualities.sum()), 2, 18).astype(int)
        amplitudes = 1 + np.rint(5*(values-values.min())/spread).astype(int)
        pool = pop.copy()
        for i, ((parent, _), count, amplitude) in enumerate(zip(pop, counts, amplitudes)):
            for k in range(int(count)):
                if not search.running:
                    break
                # Gaussian sparks occasionally jump beyond ordinary explosion radius.
                strength = int(amplitude) if k % 7 else max(1, int(abs(search.rng.normal(0, 3)))+1)
                pool.append(search.evaluate(perturb(parent, search.rng, strength), local=k == 0))
        pool.sort(key=lambda t: t[1])
        unique = {}
        for q, value in pool:
            unique.setdefault(tuple(q), (q, value))
        available = list(unique.values())
        selected = [available.pop(0)]
        # Elite retained; others maximize Hamming diversity weighted by quality.
        while available and len(selected) < 6:
            scores = []
            for q, value in available:
                nearest_selected_distance = min(np.count_nonzero(q != s[0]) for s in selected)
                quality_weight = (search.best_cost/value)**3
                scores.append(nearest_selected_distance * quality_weight)
            selected.append(available.pop(int(np.argmax(scores))))
        pop = selected


def iterated_search(search):
    """Perturb + 2-opt, neutral acceptance and annealed escape from local minima."""
    current, value = search.best.copy(), search.best_cost
    stale = 0
    while search.running:
        before = search.best_cost
        q = perturb(current, search.rng, 1 + min(4, stale//8))
        q, new = search.evaluate(q, local=True)
        temperature = search.p.min_edge * .2 * max(.05, search.budget.remaining/search.budget.limit)
        if new <= value+1e-7 or search.rng.random() < math.exp(min(0., (value-new)/temperature)):
            current, value = q, new
        stale = 0 if search.best_cost < before-1e-7 else stale+1
        if stale and stale % 24 == 0:
            current, value = search.best.copy(), search.best_cost


def optimize(points, method, seed=42, budget=100000, polish=True):
    began = time.perf_counter()
    problem = Problem(points)
    setup_s = time.perf_counter()-began
    if method not in METHODS:
        raise ValueError(method)
    search = Search(problem, seed, budget, polish=polish)
    if method == "greedy":
        best = problem.nn
    elif method == "insertion_greedy":
        best = insertion_greedy(problem, search.budget)
    elif method == "two_opt":
        best = problem.initial
    else:
        algorithms = {"genetic": genetic, "immune": immune, "ant_colony": ant_colony,
                      "particle_swarm": particle_swarm, "fireworks": fireworks,
                      "iterated_search": iterated_search}
        algorithms[method](search)
        best = search.best
    problem.validate(best)
    result = problem.points[best]
    value = route_length(result)
    if method in STOCHASTIC:
        assert value <= problem.cost(problem.initial)+1e-6
    # Budget excludes shared initialization (including initial 2-opt), not total algorithm work.
    # history/raw_proposal_best describe stochastic search; deterministic methods retain setup values.
    return result, {"method": method, "seed": seed, "stations": problem.n,
        "best_m": value, "initial_2opt_m": problem.cost(problem.initial),
        "lower_bound_m": problem.lower_bound, "bound_kind": problem.bound_kind,
        "certified_optimal": 0. <= value-problem.lower_bound <= 1e-6,
        "wall_s": time.perf_counter()-began, "shared_setup_s": setup_s,
        "comparison_budget": budget, "comparisons": search.budget.comparisons,
        "full_scores": search.budget.full_scores, "delta_scores": search.budget.delta_scores,
        "generated_candidates": search.candidates, "local_polishes": search.polishes,
        "polish_enabled": polish, "raw_proposal_best_m": search.raw_best,
        "indices": best.tolist(), "history": search.history}


def _regression_checks():
    """Run audit B1/B2 regressions without writing files (execute this module)."""
    from itertools import permutations
    import json

    reports = []
    for x in (999.999995, 999.9999988, 1000.):
        points = np.array([[0., 0.], [1000., 0.], [x, 1000.], [2000., 0.]])
        p = Problem(points)
        optimum = min(route_length(points[[0, *tail]]) for tail in permutations(range(1, 4)))
        assert p.lower_bound <= optimum
        _, meta = optimize(points, "insertion_greedy")
        if x != 1000.:
            assert p.bound_kind == "(n-1) times minimum interstation distance"
            assert not meta["certified_optimal"]
            assert Search(p, 42, 100).running
        else:
            assert p.bound_kind.startswith("square checkerboard:")
            assert meta["certified_optimal"]
        assert not meta["certified_optimal"] or meta["best_m"] - optimum <= 1e-6
        # Includes exhaustion before insertion, within a round, at a round
        # boundary, and enough budget to finish the original greedy algorithm.
        for limit in range(1, 13):
            result, bounded = optimize(points, "insertion_greedy", budget=limit)
            p.validate(np.array(bounded["indices"]))
            assert np.array_equal(result, points[bounded["indices"]])
            assert bounded["comparisons"] == min(limit, 11)
            assert bounded["full_scores"] == 1
            assert bounded["delta_scores"] == bounded["comparisons"] - 1
            if limit >= 11:
                assert bounded["indices"] == meta["indices"]
        empty = Budget(0)
        assert np.array_equal(insertion_greedy(p, empty), p.initial)
        assert empty.comparisons == 0
        _, bounded = optimize(points, "insertion_greedy", budget=2)
        reports.append({"third_station_x": x, "optimum_m": optimum,
                        "lower_bound_m": p.lower_bound, "best_m": meta["best_m"],
                        "certified_optimal": meta["certified_optimal"],
                        "budget_2_comparisons": bounded["comparisons"],
                        "budget_2_best_m": bounded["best_m"]})
    # A nonzero origin index must also survive every budget cutoff.
    points = points[[1, 2, 0, 3]]
    p = Problem(points)
    for limit in range(1, 13):
        _, meta = optimize(points, "insertion_greedy", budget=limit)
        p.validate(np.array(meta["indices"]))
        assert meta["comparisons"] <= limit
    print(json.dumps({"audit_regressions": "passed", "cases": reports}, indent=2))


if __name__ == "__main__":
    _regression_checks()
