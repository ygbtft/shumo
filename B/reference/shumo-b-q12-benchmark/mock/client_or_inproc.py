"""Interchangeable transports plus observation-only runner and HTTP demo CLI."""
import argparse
from dataclasses import dataclass
import http.client
import importlib
import json
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4
from .protocol import Reply
from .simulator import InterfaceClosed
from .strategy import Action, Observation

class ActionRejected(RuntimeError):
    def __init__(self, reply):
        self.reply = reply
        super().__init__(f'HTTP {reply.status}: {reply.body}')

# Compatibility aliases for the original public module. Implementations live in backends/.
from .backends import InProcMock as InProcessClient, HttpMock as HTTPClient

@dataclass
class RunResult:
    trace: list
    stop_reason: str
    virtual_time_s: float
    cleared_channels: list
    runtime_s: float
    error: str | None = None

def load_strategy(spec='mock.strategy:Baseline', seed=0):
    module, name = spec.split(':', 1)
    return getattr(importlib.import_module(module), name)(seed=seed)

def run_strategy(client, strategy, max_actions=10000, clock=time.monotonic):
    """Only protocol observations enter the strategy. No source count or hidden metadata."""
    trace, position, channel, virtual = [], (0., 0.), 1, 0.
    cleared = set()
    start = clock()
    reason, error = 'action_limit', None
    try:
        action = Action('/enter')
        reply = client.send(action)
        if reply.status != 200 or reply.body.get('accepted') is not True: raise ActionRejected(reply)
        body = reply.body
        trace.append({'path':action.path, 'request':client.last_request, 'response':body, 'position':list(position)})
        deadline = clock() + body['remaining_real_duration_s']
        virtual_limit = body['max_virtual_duration_s']
        for index in range(max_actions+1):
            if clock() >= deadline:
                reason = 'client_real_limit'; break
            obs = Observation(action, dict(body), position, channel, virtual, max(0., deadline-clock()), frozenset(cleared), index)
            action = Action('/exit') if index == max_actions else strategy.next_action(obs)
            if not isinstance(action, Action) or action.path not in ('/measure', '/clear', '/exit'):
                raise ValueError('strategy must return measure/clear/exit Action')
            if clock() >= deadline:
                reason = 'client_real_limit'; break
            reply = client.send(action)
            if reply.status != 200 or reply.body.get('accepted') is not True: raise ActionRejected(reply)
            body = reply.body
            virtual = body['virtual_time_s']
            if action.path in ('/measure','/clear'): position = tuple(action.position)
            if action.path == '/measure': channel = int(action.channel)
            if body.get('clear_result') == 'success': cleared.add(action.channel)
            trace.append({'path':action.path, 'request':client.last_request, 'response':body, 'position':list(position)})
            if action.path == '/exit':
                reason = 'action_limit' if index == max_actions else 'user_exit'; break
            if virtual >= virtual_limit:
                reason = 'virtual_timeout'; break
    except InterfaceClosed as exc:
        reason, error = 'connection_closed', str(exc)
    except Exception as exc:
        reason, error = 'strategy_or_protocol_error', f'{type(exc).__name__}: {exc}'
    return RunResult(trace, reason, virtual, sorted(cleared), clock()-start, error)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url', default='http://127.0.0.1:2026')
    p.add_argument('--robot-id', default='mock-robot')
    p.add_argument('--strategy', default='mock.strategy:Baseline')
    p.add_argument('--max-actions', type=int, default=10000)
    p.add_argument('--output', default='mock/results/http-trace.json')
    args = p.parse_args()
    result = run_strategy(HTTPClient(args.url, args.robot_id), load_strategy(args.strategy), args.max_actions)
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(vars(result), indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in vars(result).items() if k != 'trace'}, indent=2))

if __name__ == '__main__': main()
