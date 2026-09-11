"""Regressions for review C1/C2/H1; only owned loopback ports are used."""
import socket
import subprocess
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from bounded_http import owned_mock_http
from client import Client, HttpTransport
from simulator import Protocol, World


class DeadlineTests(unittest.TestCase):
    def test_trickled_headers_and_body_share_absolute_deadline(self):
        for phase, timeout_s, budget, retries in (('headers', 5., .12, 0),
                                                   ('headers', .1, .32, 2),
                                                   ('body', .1, .32, 2)):
            sent = []
            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *args):
                    pass

                def do_POST(self):
                    sent.append(self.rfile.read(int(self.headers['Content-Length'])))
                    try:
                        self.wfile.write(b'HTTP/1.0 200 OK\r\n')
                        if phase == 'body':
                            self.wfile.write(b'Content-Length: 100\r\n\r\n')
                        for _ in range(30):
                            self.wfile.write(b'X-K: v\r\n' if phase == 'headers' else b' ')
                            self.wfile.flush()
                            time.sleep(.03)
                    except OSError:
                        pass
            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01})
            thread.start()
            try:
                transport = HttpTransport(f'http://127.0.0.1:{server.server_port}', timeout_s=timeout_s, retries=retries)
                began = time.monotonic()
                with self.assertRaises(TimeoutError):
                    transport('/enter', b'{"request_id":"same"}', deadline=began + budget)
                elapsed = time.monotonic() - began
                self.assertLess(elapsed, budget + .15)
                self.assertGreaterEqual(len(sent), 1 if retries == 0 else 2)
                self.assertEqual(len(set(sent)), 1)
                self.assertEqual(len({r['request_body_b64'] for r in transport.failures}), 1)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


class ResponseTests(unittest.TestCase):
    def test_invalid_success_is_atomic_and_latches_stop(self):
        cases = [('/measure', {'accepted': None}),
                 ('/measure', {'accepted': True}),
                 ('/measure', {'measure_result': 'unknown'}),
                 ('/measure', {'measure_result': 'direction'}),
                 ('/measure', {'measure_result': 'direction', 'svd_deg': float('nan')}),
                 ('/clear', {'clear_result': 'unknown'}),
                 ('/exit', {'exit_reason': 'unknown'}),
                 ('/enter', {'remaining_real_duration_s': 'bad'}),
                 ('/enter', {'max_virtual_duration_s': float('inf')})]
        for field in ('virtual_time_s', 'remaining_real_duration_s', 'max_virtual_duration_s',
                      'real_timestamp_ms', 'max_real_duration_s'):
            for value in (float('nan'), float('inf'), -float('inf'), True):
                cases.append(('/enter', {field: value}))
        for path, changes in cases:
            with self.subTest(path=path, changes=changes):
                calls = []
                protocol = Protocol(World([]))
                def transport(p, raw):
                    calls.append(p)
                    if len(calls) == 1:
                        return protocol.dispatch(p, raw)
                    response = dict(accepted=True, virtual_time_s=10, real_timestamp_ms=0, max_real_duration_s=1200,
                                    remaining_real_duration_s=60, max_virtual_duration_s=1000)
                    if changes == {'accepted': True}:
                        response = changes
                    else:
                        response.update(changes)
                    return 200, response
                cli = Client(transport)
                cli.enter()
                before = (cli.virtual_s, cli.deadline, cli.position, cli.channel)
                with self.assertRaises((KeyError, ValueError, TypeError)):
                    cli.call(path, (10, 20), 2) if path in ('/measure', '/clear') else cli.call(path)
                self.assertEqual((cli.virtual_s, cli.deadline, cli.position, cli.channel), before)
                sequence = cli.sequence
                for action in (cli.enter, cli.exit, lambda: cli.measure((1, 2), 1)):
                    with self.assertRaises(RuntimeError):
                        action()
                self.assertEqual(cli.sequence, sequence)
                self.assertEqual(len(calls), 2)

    def test_persistence_failure_stops_before_state_commit(self):
        class Journal:
            def append(self, row):
                raise OSError('disk full')
        world = World([])
        cli = Client(Protocol(world).dispatch)
        cli.enter()
        before = (cli.virtual_s, cli.deadline, cli.position, cli.channel)
        cli.transcript = Journal()
        with self.assertRaises(OSError):
            cli.measure((20, 30), 2)
        self.assertEqual((cli.virtual_s, cli.deadline, cli.position, cli.channel), before)
        with self.assertRaises(RuntimeError):
            cli.measure((0, 0), 1)
        self.assertEqual(world.commands, 2)


class MockReadTests(unittest.TestCase):
    def test_partial_headers_and_body_release_single_server(self):
        for raw in (b'POST /enter HTTP/1.0\r\nX-K: ',
                    b'POST /enter HTTP/1.0\r\nContent-Length: 100\r\n\r\n{'):
            journal = []
            world = World([])
            with owned_mock_http(world, journal, read_timeout_s=.15) as url:
                sock = socket.create_connection(('127.0.0.1', int(url.rsplit(':', 1)[1])))
                try:
                    sock.sendall(raw)
                    # Keep bytes arriving faster than a socket inactivity timeout.
                    def trickle():
                        try:
                            for _ in range(20):
                                time.sleep(.03)
                                sock.sendall(b' ')
                        except OSError:
                            pass
                    sender = threading.Thread(target=trickle)
                    sender.start()
                    began = time.monotonic()
                    Client(HttpTransport(url, timeout_s=.8, retries=0)).enter()
                    self.assertLess(time.monotonic() - began, .6)
                    self.assertEqual(world.commands, 1)
                    self.assertEqual(len(journal), 1)
                finally:
                    sock.close()
                    sender.join()

    def test_teardown_interrupts_open_partial_request(self):
        for raw in (b'POST /enter HTTP/1.0\r\nX-K: ',
                    b'POST /enter HTTP/1.0\r\nContent-Length: 100\r\n\r\n{'):
            code = f'''
import socket, time
from bounded_http import owned_mock_http
from simulator import World
with owned_mock_http(World([]), [], read_timeout_s=30) as url:
    sock = socket.create_connection(('127.0.0.1', int(url.rsplit(':', 1)[1])))
    sock.sendall({raw!r})
    time.sleep(.1)
    began = time.monotonic()
print(time.monotonic() - began)
'''
            result = subprocess.run([sys.executable, '-B', '-c', code], capture_output=True,
                                    text=True, timeout=3, check=True)
            self.assertLess(float(result.stdout), .5)
