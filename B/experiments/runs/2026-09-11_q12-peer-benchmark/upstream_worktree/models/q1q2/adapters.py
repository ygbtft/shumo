"""Public observations only; no simulator/scenario truth enters a solver input."""
from __future__ import annotations
from dataclasses import dataclass, fields
from enum import Enum
import json
import math
from pathlib import Path
from typing import Iterable
from .geometry import BearingMeasurement, point


class ErrorMode(str, Enum):
    THEORETICAL_1_DEG = 'THEORETICAL_1_DEG'
    NEAREST_ROUNDING_OUTER_1_005_DEG = 'NEAREST_ROUNDING_OUTER_1_005_DEG'
    OFFICIAL_UNKNOWN = 'OFFICIAL_UNKNOWN'

    @property
    def half_width_deg(self):
        if self == ErrorMode.OFFICIAL_UNKNOWN:
            raise ValueError('OFFICIAL_UNKNOWN: choose an explicit mathematical error assumption before solving')
        return 1. if self == ErrorMode.THEORETICAL_1_DEG else 1.005

    @property
    def assumption_source(self):
        return ('theoretical ±1 degree returned-reading model' if self == ErrorMode.THEORETICAL_1_DEG else
                'assumed latent ±1 degree followed by nearest 0.01 degree rounding; not official fact' if
                self == ErrorMode.NEAREST_ROUNDING_OUTER_1_005_DEG else 'official rounding procedure unspecified')


@dataclass(frozen=True)
class ObservationRecord:
    action: str
    position: tuple[float, float] | None
    channel: int | None
    response: dict | None
    request_id: str | None = None
    session_id: str | None = None
    stage_id: str = 'uncleared'
    stability_id: str | None = None
    http_status: int | None = 200
    transport_error: object | None = None
    cleared_channels: frozenset[int] = frozenset()
    origin: str = 'public_observation'


def _interface_position(value):
    if isinstance(value, dict):
        value = value['x'], value['y']
    p = point(value)
    if any(abs(v) > 2000000 for v in p):
        raise ValueError('interface coordinate exceeds 2000000 metres')
    return p


def observation_record(observation, *, request_id=None, session_id=None, stability_id=None):
    action = observation.last_action
    return ObservationRecord(action.path, _interface_position(observation.position),
                             action.channel if action.channel is not None else observation.current_channel,
                             observation.response, request_id, session_id, stability_id=stability_id,
                             cleared_channels=frozenset(observation.cleared_channels), origin='synthetic_mock')


def read_jsonl(path: Path):
    records = []
    with Path(path).open(encoding='utf-8') as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            request = row.get('request') or {}
            position = row.get('position', request.get('position'))
            records.append(ObservationRecord(row['action'], _interface_position(position) if position is not None else None,
                                             row.get('channel', request.get('channel')), row.get('response'),
                                             row.get('request_id', request.get('request_id')), row.get('run_id'),
                                             row.get('stage_id', 'uncleared'), row.get('stability_id'),
                                             row.get('http_status'), row.get('transport_error'),
                                             frozenset(row.get('cleared_channels', ())), row.get('backend', 'public_jsonl')))
    return tuple(records)


def observations_to_bearings(rows: Iterable[ObservationRecord], channel: int, mode: ErrorMode) -> tuple[BearingMeasurement, ...]:
    mode = ErrorMode(mode)
    seen, positions, cleared, observations, identities = {}, set(), set(), [], set()
    for row in rows:
        if not isinstance(row, ObservationRecord):
            raise TypeError('expected ObservationRecord; use the explicit mock or JSONL wrapper')
        response = row.response or {}
        if row.transport_error is not None or row.http_status not in (None, 200) or response.get('accepted') is not True:
            continue
        key = row.session_id, row.request_id
        if row.request_id is not None:
            public = (row.action, row.position, row.channel, response)
            if key in seen:
                if seen[key] != public:
                    raise ValueError('conflicting duplicate request_id')
                continue
            seen[key] = public
        cleared.update((row.session_id, ch) for ch in row.cleared_channels)
        if row.action == '/clear' and response.get('clear_result') == 'success':
            cleared.add((row.session_id, row.channel))
        if row.action != '/measure' or row.channel != channel or (row.session_id, channel) in cleared:
            continue
        if response.get('measure_result') != 'direction':
            continue
        if row.stage_id != 'uncleared':
            raise ValueError('observation is not from the uncleared stage')
        identities.add((row.session_id, row.stage_id, row.stability_id))
        if len(identities) > 1:
            raise ValueError('cross-session/stage/stability observations cannot be merged')
        raw = response.get('svd_deg')
        if not isinstance(raw, (int, float)) or isinstance(raw, bool) or not math.isfinite(raw) or not 0 <= raw < 360:
            raise ValueError('invalid interface bearing')
        p = _interface_position(row.position)
        identity = p, raw, row.session_id, row.stage_id, row.stability_id
        if identity in positions:
            continue
        positions.add(identity)
        observations.append(BearingMeasurement(p, raw, mode.half_width_deg, row.request_id or f'observation_{len(observations)}',
                                               channel, row.request_id, row.origin, mode.value, mode.value,
                                               mode.assumption_source, row.session_id, row.stage_id,
                                               row.stability_id, raw))
    return tuple(observations)


def read_measurements(path: Path) -> tuple[BearingMeasurement, ...]:
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    rows = data['measurements'] if isinstance(data, dict) else data
    allowed = {f.name for f in fields(BearingMeasurement)}
    out = []
    for row in rows:
        unknown = set(row)-allowed
        if unknown:
            raise ValueError(f'unknown measurement fields: {sorted(unknown)}')
        row = dict(row)
        mode_name = row.get('error_mode')
        if mode_name is None:
            if row.get('rounding_mode') is not None or row.get('rounding_assumption_source') is not None:
                raise ValueError('rounding metadata requires an explicit error_mode')
            # Custom mathematical half widths carry no named physical error-model claim.
            row['error_mode'] = None
        else:
            mode = ErrorMode(mode_name)
            width = mode.half_width_deg
            if row.get('half_width_deg', width) != width:
                raise ValueError('half_width_deg conflicts with error_mode')
            if row.get('rounding_mode', mode.value) not in (None, mode.value):
                raise ValueError('rounding_mode conflicts with error_mode')
            supplied_source = row.get('rounding_assumption_source')
            if supplied_source is not None and supplied_source != mode.assumption_source:
                raise ValueError('rounding_assumption_source conflicts with error_mode')
            row.update(half_width_deg=width, rounding_mode=mode.value,
                       rounding_assumption_source=mode.assumption_source)
        out.append(BearingMeasurement(**row))
    return tuple(out)
