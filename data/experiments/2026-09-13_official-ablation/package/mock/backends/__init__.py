"""Factory: change only backend configuration, keep strategy code unchanged."""
import json
from pathlib import Path
from .base import Backend
from .inproc import InProcMock
from .http import HttpMock, HttpOfficial
from .recording import RecordingBackend
from ..error_field import ErrorConfig, ErrorField
from ..protocol import Protocol
from ..scenario_gen import Scenario, ScenarioConfig, generate
from ..simulator import Limits, Simulator


def create_backend(config):
    root = Path.cwd()
    if isinstance(config, (str, Path)):
        path = Path(config).resolve(); root = path.parent
        config = json.loads(path.read_text(encoding='utf-8'))
    cfg = dict(config)
    kind = cfg.pop('kind')
    record = cfg.pop('record', None)
    if kind == 'inproc_mock':
        robot = cfg.pop('robot_id', 'mock-robot')
        seed = cfg.pop('seed', 0)
        source_file = cfg.pop('scenario_file', None)
        sc = ScenarioConfig(**cfg.pop('scenario', {}))
        ec = ErrorConfig(**cfg.pop('error', {}))
        limits = Limits(**cfg.pop('limits', {'countdown_s':0}))
        case = generate(seed, sc)
        if source_file:
            data = json.loads((root/source_file).read_text(encoding='utf-8'))
            case = Scenario.from_dict(data['scenario'])
            ec = ErrorConfig(**data.get('error', {}))
        if cfg: raise ValueError(f'unknown backend options: {sorted(cfg)}')
        backend = InProcMock(Protocol(Simulator(case, ErrorField(case.seed, ec), limits), robot), robot)
    elif kind in ('http_mock','http_official'):
        if kind == 'http_official' and not cfg.get('robot_id'):
            raise ValueError('http_official requires the logged-in team robot_id')
        backend = (HttpOfficial if kind == 'http_official' else HttpMock)(**cfg)
    else: raise ValueError(f'unknown backend kind: {kind}')
    return RecordingBackend(backend, root/record) if record else backend

__all__ = ['Backend','InProcMock','HttpMock','HttpOfficial','RecordingBackend','create_backend']
