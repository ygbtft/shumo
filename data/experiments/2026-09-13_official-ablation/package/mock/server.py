"""Local mock HTTP server, default 127.0.0.1:2026."""
import argparse
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import threading
from .error_field import ErrorConfig, ErrorField
from .protocol import MAX_BODY, Protocol
from .scenario_gen import Scenario, generate, load_config
from .simulator import InterfaceClosed, Limits, Simulator

class MockHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, protocol, max_connections=64):
        if max_connections < 1: raise ValueError('max_connections must be positive')
        self.protocol = protocol
        # 假设 A7：最多 64 个同时连接，超过时仅保护新连接。
        self.slots = threading.BoundedSemaphore(max_connections)
        super().__init__(address, Handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            try:
                self.protocol.sim.check_open()
                body = json.dumps(self.protocol.sim.envelope()).encode()
                request.settimeout(1)
                request.sendall(b'HTTP/1.1 429 Too Many Requests\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body)
            except (OSError, InterfaceClosed): pass
            finally: self.shutdown_request(request)
            return
        try: super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try: super().process_request_thread(request, client_address)
        finally: self.slots.release()

class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def setup(self):
        super().setup()
        self.connection.settimeout(5)  # 假设 A8：不完整报文读取超时。

    def log_message(self, *args): pass

    def send_reply(self, reply):
        raw = json.dumps(reply.body, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
        self.send_response(reply.status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Connection', 'close')
        if reply.status == 405: self.send_header('Allow', 'POST')
        self.end_headers()
        if self.command != 'HEAD': self.wfile.write(raw)
        self.close_connection = True

    def send_error(self, code, message=None, explain=None):
        # BaseHTTPRequestHandler 的可形成响应的解析错误也保持 JSON。
        self.send_reply(self.server.protocol.reject(code))

    def handle_one_request(self):
        try:
            sim = self.server.protocol.sim
            if not sim.limits.replay_after_end: sim.check_open()
            super().handle_one_request()
        except (InterfaceClosed, ConnectionError, socket.timeout):
            self.close_connection = True

    def __getattr__(self, name):
        if name.startswith('do_'): return self.dispatch
        raise AttributeError(name)

    def dispatch(self):
        protocol = self.server.protocol
        try:
            if not protocol.sim.limits.replay_after_end: protocol.sim.check_open()
            if self.path not in ('/enter', '/measure', '/clear', '/exit'):
                return self.send_reply(protocol.reject(404))
            if self.command != 'POST': return self.send_reply(protocol.reject(405))
            # 假设 A8：使用 Content-Length；不支持 chunked/重复 framing 头。
            lengths = self.headers.get_all('Content-Length', [])
            if self.headers.get('Transfer-Encoding') or len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
                return self.send_reply(protocol.reject(400))
            length = int(lengths[0])
            if length > MAX_BODY: return self.send_reply(protocol.reject(413))
            for key in ('Content-Type', 'Content-Encoding'):
                if len(self.headers.get_all(key, [])) > 1: return self.send_reply(protocol.reject(415))
            raw = self.rfile.read(length)
            if len(raw) != length: return self.send_reply(protocol.reject(400))
            self.send_reply(protocol.handle(self.command, self.path, raw, dict(self.headers), defer_release=True))
        except InterfaceClosed:
            self.close_connection = True
        except (ConnectionError, socket.timeout):
            self.close_connection = True
        except Exception:
            self.send_reply(protocol.reject(500))
        finally:
            protocol.complete_pending()

    def handle_expect_100(self):
        # 假设 A8：不实现 Expect 握手，拒绝为结构错误。
        self.send_reply(self.server.protocol.reject(400))
        return False

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port', type=int, default=2026)
    p.add_argument('--robot-id', default='mock-robot')
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--config')
    p.add_argument('--scenario', help='scenario_gen output or evaluator case JSON')
    p.add_argument('--countdown', type=float, default=5)
    p.add_argument('--window', type=float, default=1500)
    p.add_argument('--real-limit', type=float, default=1200)
    p.add_argument('--virtual-limit', type=float, default=360000)
    p.add_argument('--max-records', type=int, default=200000)
    p.add_argument('--max-connections', type=int, default=64)
    p.add_argument('--invalid-limit', type=int, default=1000)
    p.add_argument('--replay-after-end', action='store_true')
    p.add_argument('--closed', action='store_true', help='simulate interface not open')
    p.add_argument('--fail-first', action='store_true', help='inject one HTTP 500')
    p.add_argument('--output', default='mock/results/server-session.json')
    args = p.parse_args()
    cfg, error_cfg = load_config(args.config)
    scenario = generate(args.seed, cfg)
    if args.scenario:
        saved = json.loads(Path(args.scenario).read_text(encoding='utf-8'))
        scenario = Scenario.from_dict(saved['scenario'])
        error_cfg = ErrorConfig(**saved.get('error', {}))
    sim = Simulator(scenario, ErrorField(scenario.seed, error_cfg), Limits(args.countdown, args.window, args.real_limit, args.virtual_limit, args.max_records, args.replay_after_end))
    sim.enabled = not args.closed
    protocol = Protocol(sim, args.robot_id, args.invalid_limit)
    protocol.fail_next = args.fail_first
    server = MockHTTPServer(('127.0.0.1', args.port), protocol, args.max_connections)
    print(f'LOCAL MOCK http://127.0.0.1:{server.server_port}; robot_id={args.robot_id}; countdown={args.countdown}s', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        server.server_close()
        output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({'scenario': scenario.to_dict(), 'error': asdict(error_cfg), 'trace': sim.trace, 'end_reason': sim.end_reason}, indent=2), encoding='utf-8')
        print(f'Saved {output}')

if __name__ == '__main__': main()
