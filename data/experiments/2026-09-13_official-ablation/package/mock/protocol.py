"""Strict HTTP+JSON validation and shared in-process/HTTP admission logic."""
from collections import deque
from copy import deepcopy
from dataclasses import dataclass
import json
import math
import re
import threading
import unicodedata
from .simulator import InterfaceClosed

PATHS = {'/enter', '/measure', '/clear', '/exit'}
MAX_BODY = 65536

@dataclass(frozen=True)
class Reply:
    status: int
    body: dict

class Invalid(ValueError): pass

def decode_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise Invalid('duplicate key')
            result[key] = value
        return result
    def constant(value): raise Invalid('nonfinite JSON')
    try:
        if raw.startswith(b'\xef\xbb\xbf'): raise Invalid('BOM')
        data = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)
        if not isinstance(data, dict): raise Invalid('not an object')
        def depth(value, level=1):
            if isinstance(value, (dict, list)):
                if level > 16: raise Invalid('too deep')
                children = value.values() if isinstance(value, dict) else value
                for v in children: depth(v, level+1)
        depth(data)
        return data
    except (ValueError, UnicodeError, RecursionError) as e:
        raise Invalid(str(e)) from e

def identifier(value, max_bytes):
    if not isinstance(value, str): return False
    try: size = len(value.encode('utf-8'))
    except UnicodeError: return False
    return 1 <= size <= max_bytes and not any(unicodedata.category(c) in ('Cc', 'Cf', 'Cs') for c in value)

def number(value):
    if type(value) not in (int, float): return False
    try: return math.isfinite(value)
    except OverflowError: return False

def validate(path, data):
    required = {'arena_id', 'robot_id', 'request_id'}
    if path in ('/measure', '/clear'): required |= {'position', 'channel'}
    if not required <= data.keys(): raise Invalid('missing field')
    if not isinstance(data['arena_id'], str): raise Invalid('arena_id type')
    if not identifier(data['robot_id'], 64) or not identifier(data['request_id'], 128):
        raise Invalid('identifier format')
    unknown = bool(data.keys() - required)
    if path in ('/measure', '/clear'):
        p, c = data['position'], data['channel']
        if not isinstance(p, dict) or not {'x', 'y'} <= p.keys(): raise Invalid('position')
        if any(not number(p[k]) or abs(p[k]) > 2_000_000 for k in ('x', 'y')):
            raise Invalid('coordinate')
        if not number(c) or not 1 <= c <= 20 or c != int(c): raise Invalid('channel')
        unknown |= bool(p.keys() - {'x', 'y'})
    return unknown

def fingerprint(path, data):
    # 假设 A6：按解析后的动作语义比较，键顺序、空白、1/1.0、-0/0 不影响 ID。
    values = [path, data['arena_id'], data['robot_id']]
    if path in ('/measure', '/clear'):
        values += [float(data['position']['x']), float(data['position']['y']), int(data['channel'])]
    return tuple(values)

class Protocol:
    def __init__(self, sim, robot_id='mock-robot', invalid_limit=1000, invalid_window_s=1.0):
        if not identifier(robot_id, 64): raise ValueError('invalid configured robot_id')
        if invalid_limit < 0 or invalid_window_s <= 0: raise ValueError('invalid traffic protection settings')
        self.sim, self.robot_id = sim, robot_id
        self.cache = {}
        self._guard = threading.RLock()
        self._pending = None
        self._invalid = deque()
        # 假设 A7：仅无效请求保护，不对正常串行合法动作限速。
        self.invalid_limit, self.invalid_window_s = invalid_limit, invalid_window_s
        self.fail_next = False  # 假设 A8：本地一次性 500 注入，无 HTTP 管理路径。

    def reject(self, status):
        if status == 500:
            return Reply(status, self.sim.envelope())
        with self._guard:
            now = self.sim.clock()
            while self._invalid and self._invalid[0] <= now - self.invalid_window_s:
                self._invalid.popleft()
            if self.invalid_limit and len(self._invalid) >= self.invalid_limit:
                status = 429
            else: self._invalid.append(now)
        return Reply(status, self.sim.envelope())

    def handle(self, method, path, raw, headers=None, defer_release=False):
        arrival = self.sim.clock()  # raw 已完整到达；解析耗时不使已到达动作失效。
        if not self.sim.limits.replay_after_end:
            self.sim.check_open(arrival)
        elif self.sim.end_reason is None:
            self.sim.check_open(arrival)
        if path not in PATHS: return self.reject(404)
        if method != 'POST': return self.reject(405)
        headers = {k.lower(): v for k, v in (headers or {}).items()}
        ct = headers.get('content-type', '')
        if not re.fullmatch(r'application/json\s*(?:;\s*charset\s*=\s*(?:utf-8|"utf-8")\s*)?', ct.strip(), re.I):
            return self.reject(415)
        if headers.get('content-encoding', 'identity').strip().lower() != 'identity':
            return self.reject(415)
        if len(raw) > MAX_BODY: return self.reject(413)
        try:
            data = decode_json(raw)
            unknown = validate(path, data)
        except Invalid:
            return self.reject(400)
        if unknown or data['arena_id'] != 'default' or data['robot_id'] != self.robot_id:
            return self.reject(200)
        key, fp = data['request_id'], fingerprint(path, data)
        wait_for = None
        with self._guard:
            if key in self.cache:
                original, reply = self.cache[key]
                return deepcopy(reply) if fp == original else self.reject(409)
            self.sim.check_open(arrival)
            if self._pending:
                pending_key, pending_fp, event, result, owner = self._pending
                if key != pending_key or fp != pending_fp: return self.reject(409)
                wait_for = event, result
            else:
                if len(self.cache) >= self.sim.limits.max_records: return self.reject(429)
                event, result = threading.Event(), []
                self._pending = (key, fp, event, result, threading.get_ident())
        if wait_for:
            wait_for[0].wait()
            return deepcopy(wait_for[1][0])
        try:
            if self.fail_next:
                self.fail_next = False
                raise RuntimeError('injected internal error')
            reply = Reply(200, self.sim.execute(path, data, arrival))
        except Exception:
            reply = self.reject(500)
        with self._guard:
            if reply.body['accepted']:
                self.cache[key] = fp, deepcopy(reply)
            result.append(reply)
            if not defer_release:
                self.complete_pending()
        return deepcopy(reply)

    def complete_pending(self):
        """HTTP owner releases admission only after its complete response was sent."""
        with self._guard:
            if self._pending and self._pending[4] == threading.get_ident():
                self._pending[2].set()
                self._pending = None
