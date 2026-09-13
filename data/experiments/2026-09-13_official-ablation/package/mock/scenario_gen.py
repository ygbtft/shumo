"""Configurable synthetic cases, never exposed to the strategy."""
from dataclasses import asdict, dataclass, field
import argparse
import json
import math
from pathlib import Path
import random
from .error_field import ErrorConfig
from .geometry import ARENA_RADIUS

@dataclass(frozen=True)
class Source:
    channel: int
    x: float
    y: float
    radius: float
    direction_deg: float | None = None

    @property
    def position(self):
        return self.x, self.y

    def __post_init__(self):
        if type(self.channel) is not int or not 1 <= self.channel <= 20:
            raise ValueError('source channel outside 1..20')
        if not all(math.isfinite(v) for v in (self.x, self.y, self.radius)):
            raise ValueError('nonfinite source')
        if math.hypot(self.x, self.y) > ARENA_RADIUS + 1e-9:
            raise ValueError('source outside arena')
        if not 1000 <= self.radius <= 1500:
            raise ValueError('source radius outside 1000..1500')
        if self.direction_deg is not None and not 0 <= self.direction_deg < 360:
            raise ValueError('direction outside [0,360)')

@dataclass(frozen=True)
class ScenarioConfig:
    count_min: int = 10
    count_max: int = 16
    position_distribution: str = 'uniform'  # uniform | edge | clustered
    edge_power: float = 8.0
    clusters: int = 3
    cluster_sigma_m: float = 180.0
    radius_distribution: str = 'uniform'  # uniform | fixed | beta
    radius_min: float = 1000.0
    radius_max: float = 1500.0
    radius_fixed: float = 1250.0
    radius_beta_a: float = 2.0
    radius_beta_b: float = 2.0
    directional_fraction: float = 0.5
    ensure_mixed: bool = True
    direction_distribution: str = 'uniform'  # uniform | fixed | inward | outward | vonmises
    direction_deg: float = 0.0
    direction_kappa: float = 4.0
    empirical_counts: tuple = ()
    empirical_positions: tuple = ()
    empirical_radius_intervals: tuple = ()

    def __post_init__(self):
        if not 10 <= self.count_min <= self.count_max <= 16:
            raise ValueError('counts must be 10..16')
        if self.position_distribution not in ('uniform', 'edge', 'clustered', 'empirical'):
            raise ValueError('invalid position distribution')
        if self.radius_distribution not in ('uniform', 'fixed', 'beta', 'empirical'):
            raise ValueError('invalid radius distribution')
        if self.direction_distribution not in ('uniform', 'fixed', 'inward', 'outward', 'vonmises'):
            raise ValueError('invalid direction distribution')
        for v in (self.edge_power, self.cluster_sigma_m, self.radius_beta_a, self.radius_beta_b):
            if not math.isfinite(v) or v <= 0:
                raise ValueError('distribution parameters must be positive finite')
        if type(self.clusters) is not int or self.clusters < 1:
            raise ValueError('clusters must be positive integer')
        if not 1000 <= self.radius_min <= self.radius_max <= 1500 or not 1000 <= self.radius_fixed <= 1500:
            raise ValueError('invalid radius bounds')
        if not 0 <= self.directional_fraction <= 1:
            raise ValueError('directional_fraction outside [0,1]')
        if not math.isfinite(self.direction_deg) or not math.isfinite(self.direction_kappa) or self.direction_kappa < 0:
            raise ValueError('invalid direction parameters')
        if any(type(n) is not int or not 10<=n<=16 for n in self.empirical_counts):
            raise ValueError('empirical counts outside 10..16')
        if any(len(p)!=2 or not all(math.isfinite(v) for v in p) or math.hypot(*p)>1800 for p in self.empirical_positions):
            raise ValueError('invalid empirical positions')
        if any(len(p)!=2 or not 1000<=p[0]<=p[1]<=1500 for p in self.empirical_radius_intervals):
            raise ValueError('invalid empirical radius intervals')
        if self.position_distribution=='empirical' and not self.empirical_positions:
            raise ValueError('empirical positions missing')
        if self.radius_distribution=='empirical' and not self.empirical_radius_intervals:
            raise ValueError('empirical radius intervals missing')

@dataclass(frozen=True)
class Scenario:
    seed: int
    sources: tuple[Source, ...]
    config: dict = field(default_factory=dict)

    def __post_init__(self):
        if len({s.channel for s in self.sources}) != len(self.sources):
            raise ValueError('duplicate source channels')

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(data['seed'], tuple(Source(**s) for s in data['sources']), data.get('config', {}))

def generate(seed, config=None):
    cfg = config or ScenarioConfig()
    rng = random.Random(seed)
    def disk(power=2):
        r = ARENA_RADIUS * rng.random() ** (1 / power)
        theta = rng.uniform(0, 2 * math.pi)
        return r * math.cos(theta), r * math.sin(theta)
    # 假设 A1：数量离散均匀、频道无放回均匀；各分布默认独立。
    n = rng.choice(cfg.empirical_counts) if cfg.empirical_counts else rng.randint(cfg.count_min, cfg.count_max)
    channels = rng.sample(range(1, 21), n)
    centers = [disk() for _ in range(cfg.clusters)]
    flags = [rng.random() < cfg.directional_fraction for _ in range(n)]
    if cfg.ensure_mixed and 0 < cfg.directional_fraction < 1:
        if all(flags): flags[rng.randrange(n)] = False
        if not any(flags): flags[rng.randrange(n)] = True
    sources = []
    for c, directional in zip(channels, flags):
        if cfg.position_distribution == 'empirical':
            # 假设 A11：完整定位案例的经验位置有放回抽样，保留偏差说明。
            x,y=rng.choice(cfg.empirical_positions)
        elif cfg.position_distribution == 'clustered':
            cx, cy = rng.choice(centers)
            for _ in range(100000):
                x, y = rng.gauss(cx, cfg.cluster_sigma_m), rng.gauss(cy, cfg.cluster_sigma_m)
                if math.hypot(x, y) <= ARENA_RADIUS: break
            else: raise ValueError('cluster rejection sampler exhausted; reduce sigma')
        else:
            x, y = disk(cfg.edge_power if cfg.position_distribution == 'edge' else 2)
        if cfg.radius_distribution == 'empirical':
            # 假设 A11：半径仅部分识别，在经验约束区间内均匀抽样。
            radius=rng.uniform(*rng.choice(cfg.empirical_radius_intervals))
        elif cfg.radius_distribution == 'fixed': radius = cfg.radius_fixed
        else:
            u = rng.random() if cfg.radius_distribution == 'uniform' else rng.betavariate(cfg.radius_beta_a, cfg.radius_beta_b)
            radius = cfg.radius_min + (cfg.radius_max - cfg.radius_min) * u
        direction = None
        if directional:
            mode = cfg.direction_distribution
            if mode == 'uniform': direction = rng.uniform(0, 360)
            elif mode == 'fixed': direction = cfg.direction_deg
            elif mode == 'vonmises': direction = math.degrees(rng.vonmisesvariate(math.radians(cfg.direction_deg), cfg.direction_kappa))
            else: direction = math.degrees(math.atan2(y, x)) + (180 if mode == 'inward' else 0)
            direction %= 360
        sources.append(Source(c, x, y, radius, direction))
    return Scenario(seed, tuple(sources), asdict(cfg))

def load_config(path=None):
    data = json.loads(Path(path).read_text(encoding='utf-8')) if path else {}
    if set(data) - {'scenario', 'error'}: raise ValueError('unknown configuration section')
    return ScenarioConfig(**data.get('scenario', {})), ErrorConfig(**data.get('error', {}))

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--config')
    p.add_argument('--output', default='mock/results/scenario.json')
    args = p.parse_args()
    cfg, error = load_config(args.config)
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({'scenario': generate(args.seed, cfg).to_dict(), 'error': asdict(error)}, indent=2), encoding='utf-8')
    print(out)

if __name__ == '__main__': main()
