"""Exercise real urllib/http.client connect and sock.sendall paths on owned ports."""
import contextlib
from http.client import HTTPConnection, HTTPException, RemoteDisconnected, BadStatusLine
import io
import json
from pathlib import Path
import socket
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import bounded_http
from client import HttpTransport
from simulator import Source, World
from test_client import Clock, Response


class TinyPolicy:
    def __init__(self, cli, *args):
        self.cli = cli
        self.stations = np.array([[100., 0.]])
        self.cleared = set()

    def run(self):
        self.cli.enter()
        self.cli.measure((100, 0), 2)
        self.cli.clear((100, 0), 2)
        self.cleared.add(2)
        self.cli.exit()
        return {}


class SendFailureTests(unittest.TestCase):
    def test_real_sendall_connect_and_ambiguous_send_recovery_summary(self):
        for fault in (ConnectionResetError, BrokenPipeError, socket.timeout,
                      ConnectionRefusedError, RemoteDisconnected, HTTPException):
            for after_execution in (False, True):
                if after_execution and fault != ConnectionResetError:
                    continue
                with self.subTest(fault=fault, after_execution=after_execution), tempfile.TemporaryDirectory() as tmp:
                    world = World([Source(2, 100, 0)])
                    sent = []
                    injected = []
                    original_request = HTTPConnection.request
                    original_connect = HTTPConnection.connect
                    original_sendall = socket.socket.sendall

                    def request(conn, method, url, body=None, *args, **kwargs):
                        conn.test_path = url
                        if url == '/measure':
                            sent.append(body)
                        return original_request(conn, method, url, body, *args, **kwargs)

                    def connect(conn):
                        if conn.test_path == '/measure' and fault == ConnectionRefusedError and not injected:
                            injected.append(True)
                            raise fault('injected connect failure')
                        return original_connect(conn)

                    def sendall(sock, data, *args, **kwargs):
                        # urllib sends the immutable JSON body separately from headers.
                        if data in sent and fault != ConnectionRefusedError and not injected:
                            injected.append(True)
                            if after_execution:
                                original_sendall(sock, data, *args, **kwargs)
                                # The server has committed the action before the
                                # injected send error reaches the caller.
                                deadline = time.monotonic() + 2
                                while world.measures != 1 and time.monotonic() < deadline:
                                    time.sleep(.001)
                                self.assertEqual(world.measures, 1)
                            raise fault('injected sock.sendall failure')
                        return original_sendall(sock, data, *args, **kwargs)

                    args = SimpleNamespace(mode='mock-http', problem=3, seed=42,
                                           series='test', method='tiny')
                    with patch.object(bounded_http, 'ROOT', Path(tmp)), \
                         patch.object(bounded_http, 'mock_world', return_value=world), \
                         patch.object(HTTPConnection, 'request', request), \
                         patch.object(HTTPConnection, 'connect', connect), \
                         patch.object(socket.socket, 'sendall', sendall), \
                         contextlib.redirect_stdout(io.StringIO()):
                        (Path(tmp) / 'client.py').write_text('test fixture')
                        bounded_http.run_http(args, TinyPolicy, {}, {}, time.perf_counter())
                    self.assertEqual(len(injected), 1)
                    self.assertEqual(len(sent), 2)
                    self.assertEqual(sent[0], sent[1])
                    self.assertEqual(json.loads(sent[0])['request_id'], json.loads(sent[1])['request_id'])
                    self.assertEqual(world.measures, 1)
                    self.assertEqual(world.commands, 4)
                    folder = next((Path(tmp) / 'robot_runs').iterdir())
                    summary = json.loads((folder / 'summary.json').read_text())
                    self.assertTrue(summary['exited'])
                    self.assertTrue(summary['all_cleared'])
                    self.assertEqual(summary['commands'], 4)
                    self.assertEqual(summary['transport_failures'], 1)
                    self.assertEqual(summary['official_calls'], 0)
                    self.assertFalse((folder / 'failure.txt').exists())

    def test_http_header_exceptions_reuse_body(self):
        for fault in (RemoteDisconnected('closed'), BadStatusLine('broken'), HTTPException('send')):
            with self.subTest(fault=fault):
                transport = HttpTransport('http://127.0.0.1:1')
                with patch('client.open_response', side_effect=[fault, Response(b'{"accepted":true}')]) as opened, \
                     patch('client.time.sleep'):
                    transport('/measure', b'{"request_id":"same"}')
                self.assertIs(opened.call_args_list[0].args[0], opened.call_args_list[1].args[0])

    def test_exhaustion_writes_summary_and_preserves_deadline_reserve(self):
        for budget_limited in (False, True):
            with self.subTest(budget_limited=budget_limited), tempfile.TemporaryDirectory() as tmp:
                clock = Clock()
                calls = []
                class FailingPolicy(TinyPolicy):
                    def run(self):
                        if budget_limited:
                            self.cli.deadline = clock.now + 2.25
                        self.cli.measure((100, 0), 2)

                def fail(request, timeout):
                    calls.append(request.data)
                    if budget_limited:
                        clock.now += timeout
                    raise BrokenPipeError('permanent failure')

                args = SimpleNamespace(mode='mock-http', problem=4, seed=42,
                                       series='test', method='tiny')
                with patch.object(bounded_http, 'ROOT', Path(tmp)), \
                     patch('client.open_response', side_effect=fail), \
                     patch('client.time.monotonic', clock.monotonic), \
                     patch('client.time.sleep', clock.sleep), \
                     contextlib.redirect_stdout(io.StringIO()):
                    (Path(tmp) / 'client.py').write_text('test fixture')
                    with self.assertRaises((BrokenPipeError, TimeoutError)):
                        bounded_http.run_http(args, FailingPolicy, {}, {}, time.perf_counter())
                self.assertEqual(len(calls), 1 if budget_limited else 3)
                self.assertEqual(len(set(calls)), 1)
                if budget_limited:
                    self.assertEqual(clock.now, 100.25)
                folder = next((Path(tmp) / 'robot_runs').iterdir())
                summary = json.loads((folder / 'summary.json').read_text())
                self.assertEqual(summary['status'], 'failed')
                self.assertEqual(summary['execution_state'], 'unknown')
                self.assertEqual(summary['commands'], 0)
                self.assertEqual(summary['transport_failures'], len(calls))
                self.assertTrue((folder / 'failure.txt').exists())


if __name__ == '__main__':
    unittest.main()
