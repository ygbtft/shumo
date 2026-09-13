"""Deterministic, bounded error fields: repeated locations never resample."""
from dataclasses import dataclass, replace
import hashlib
import math
import random
import struct

@dataclass(frozen=True)
class ErrorConfig:
    model: str = 'iid'  # iid | smooth | adversarial
    length_scale_m: float = 200.0
    cross_channel: str = 'independent'  # independent | shared
    adversarial_sign: str = 'positive'  # positive | negative | spatial
    empirical_samples_deg: tuple = ()
    empirical_base: str = 'iid'

    def __post_init__(self):
        if self.model not in ('iid', 'smooth', 'adversarial', 'empirical'):
            raise ValueError('unknown error model')
        if not math.isfinite(self.length_scale_m) or self.length_scale_m <= 0:
            raise ValueError('length_scale_m must be finite and positive')
        if self.cross_channel not in ('independent', 'shared'):
            raise ValueError('invalid cross_channel')
        if self.adversarial_sign not in ('positive', 'negative', 'spatial'):
            raise ValueError('invalid adversarial_sign')
        if self.empirical_base not in ('iid','smooth'):
            raise ValueError('invalid empirical_base')
        if any(not math.isfinite(v) or not -1<=v<=1 for v in self.empirical_samples_deg):
            raise ValueError('empirical error samples outside [-1,1]')
        if self.model=='empirical' and len(self.empirical_samples_deg)<2:
            raise ValueError('empirical model requires at least two bounded samples')

class ErrorField:
    def __init__(self, seed=0, config=None):
        self.seed = seed
        self.config = config or ErrorConfig()
        self._waves = {}
        self._empirical = sorted(self.config.empirical_samples_deg)
        self._base = ErrorField(seed, replace(self.config,model=self.config.empirical_base)) if self.config.model=='empirical' else None

    def _uniform(self, x, y, channel):
        # 假设 A2：精确 float64 坐标为地点键；+0/-0 合并。散列无调用顺序依赖。
        data = str(self.seed).encode() + struct.pack('!ddi', x or 0., y or 0., channel)
        number = int.from_bytes(hashlib.blake2b(data, digest_size=8).digest(), 'big')
        return number / (2**64 - 1) * 2 - 1

    def value(self, point, channel):
        if self._base is not None:
            value=self._base.value(point,channel)
            # 假设 A11：经验分位数映射；平滑基场的标准正态 CDF 是近似。
            u=(value+1)/2 if self.config.empirical_base=='iid' else (1+math.erf(math.atanh(max(-.999999999,min(.999999999,value)))/math.sqrt(2)))/2
            index=min(len(self._empirical)-1,u*(len(self._empirical)-1))
            lo=int(index);hi=min(lo+1,len(self._empirical)-1)
            return self._empirical[lo]+(index-lo)*(self._empirical[hi]-self._empirical[lo])
        c = channel if self.config.cross_channel == 'independent' else 0
        x, y = point
        if self.config.model == 'iid':
            return self._uniform(x, y, c)
        if self.config.model == 'adversarial':
            # 假设 A3：静态端点压力场，非针对策略在线优化的最坏情况证明。
            sign = self.config.adversarial_sign
            if sign != 'spatial':
                return 1.0 if sign == 'positive' else -1.0
            return 1.0 if self._uniform(x, y, c) >= 0 else -1.0
        # 假设 A2：16 个随机平面波经 tanh 压缩，平滑且全局严格有界。
        if c not in self._waves:
            rng = random.Random(f'{self.seed}:smooth:{c}')
            scale = self.config.length_scale_m
            self._waves[c] = [(rng.gauss(0, 1) / scale, rng.gauss(0, 1) / scale,
                               rng.uniform(0, 2 * math.pi)) for _ in range(16)]
        z = sum(math.cos(kx*x + ky*y + phase) for kx, ky, phase in self._waves[c])
        return math.tanh(z / math.sqrt(8))
