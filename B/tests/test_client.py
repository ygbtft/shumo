"""Local-only regression tests. No official service or fixed port is contacted.

Run from B/: ../models/q1q2/.venv/bin/python -m unittest discover -s tests -v
"""
import base64
from contextlib import contextmanager
from http.client import IncompleteRead
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import inspect
import json
import threading
import unittest
from unittest.mock import patch

import numpy as np
from client import Client, HttpTransport, Rejected
from simulator import Protocol, Source, World


class Response:
    def __init__(self, body, fault=None, code=200):
        self.body,self.fault,self.code=body,fault,code
        self.length=0

    def __enter__(self):
        return self

    def __exit__(self,*args):
        pass

    def read1(self, size):
        if self.fault:
            raise self.fault
        body, self.body = self.body, b""
        return body


class Clock:
    now=100.

    def monotonic(self):
        return self.now

    def sleep(self,seconds):
        self.now+=seconds


@contextmanager
def local_server(protocol,truncate_first=False):
    requests=[]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass

        def do_POST(self):
            raw=self.rfile.read(int(self.headers['Content-Length']))
            requests.append((self.path,raw))
            status,result=protocol.dispatch(self.path,raw)
            body=json.dumps(result).encode()
            self.send_response(status)
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            self.wfile.write(body[:12] if truncate_first and len(requests)==1 else body)
            self.close_connection=True

    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        yield HttpTransport(f'http://127.0.0.1:{server.server_port}'),requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


class ClientTests(unittest.TestCase):
    def test_faults_replay_identical_bytes_and_execute_once(self):
        for fault in ('incomplete','json','utf8','reset'):
            with self.subTest(fault=fault):
                world=World([Source(2,100,0)])
                protocol=Protocol(world)
                journal=[]
                transport=HttpTransport('http://127.0.0.1:1')
                client=Client(transport,transcript=journal)
                sent=[]

                def open_mock(request,timeout):
                    raw=request.data
                    if request.full_url.endswith('/enter'):
                        status,result=protocol.dispatch('/enter',raw)
                        return Response(json.dumps(result).encode(),code=status)
                    sent.append(raw)
                    status,result=protocol.dispatch('/measure',raw)
                    body=json.dumps(result).encode()
                    if len(sent)==1:
                        if fault=='incomplete':
                            return Response(b'',IncompleteRead(body[:12],len(body)-12))
                        if fault=='json':
                            return Response(b'{"accepted":true,')
                        if fault=='utf8':
                            return Response(b'\xff')
                        raise ConnectionResetError('after execution')
                    return Response(body,code=status)

                with patch('client.open_response',side_effect=open_mock),patch('client.time.sleep'):
                    client.enter()
                    self.assertEqual(client.measure((100,0),2)['measure_result'],'near')
                self.assertEqual(len(sent),2)
                self.assertEqual(sent[0],sent[1])
                self.assertEqual(world.commands,2)
                self.assertEqual(world.measures,1)
                self.assertEqual(world.time_us,26_000000)
                self.assertEqual(client.virtual_s,26.)
                self.assertEqual(len(protocol.cache),2)
                failure=journal[1]
                self.assertEqual(failure['event'],'transport_failure')
                self.assertEqual(base64.b64decode(failure['request_body_b64']),sent[0])
                fragment=base64.b64decode(failure['response_body_b64'])
                self.assertEqual(fragment,{'incomplete':b'{"accepted":',
                    'json':b'{"accepted":true,','utf8':b'\xff','reset':b''}[fault])
                json.dumps(journal)  # Compatible with the runner's JSONL journal.

    def test_exhausted_retries_retain_all_fragments_and_stop(self):
        journal=[]
        transport=HttpTransport('http://127.0.0.1:1')
        client=Client(transport,transcript=journal)
        with patch('client.open_response',side_effect=lambda *a,**k:Response(b'',IncompleteRead(b'partial',9))) as opened,patch('client.time.sleep'):
            with self.assertRaises(IncompleteRead):
                client.enter()
            with self.assertRaises(RuntimeError):
                client.exit()
            self.assertEqual(opened.call_count,3)
        self.assertEqual(len(journal),3)
        self.assertEqual(len({r['request_body_b64'] for r in journal}),1)
        self.assertTrue(all(base64.b64decode(r['response_body_b64'])==b'partial' for r in journal))
        self.assertEqual(transport.failures,journal)

    def test_error_body_truncation_and_complete_rejection(self):
        raw=b'{"request_id":"one"}'
        good=b'{"accepted":false,"virtual_time_s":0}'
        for bad in (b'{',):
            failures=[Response(bad, code=400),
                      Response(good, code=400)]
            transport=HttpTransport('http://127.0.0.1:1')
            with patch('client.open_response',side_effect=failures) as opened,patch('client.time.sleep'):
                self.assertEqual(transport('/measure',raw),(400,json.loads(good)))
                self.assertEqual(opened.call_count,2)
            with patch('client.open_response',return_value=Response(good, code=400)) as opened:
                self.assertEqual(transport('/measure',raw)[0],400)
                self.assertEqual(opened.call_count,1)

    def test_rebuilt_client_cannot_replay_cached_enter(self):
        world=World([])
        protocol=Protocol(world)
        a=Client(protocol.dispatch)
        a.enter()
        a.measure((100,0),2)
        b=Client(protocol.dispatch)
        with self.assertRaises(Rejected):
            b.enter()
        self.assertEqual(world.position,(100.,0.))
        self.assertEqual(world.time_us,26_000000)
        self.assertEqual(world.commands,2)
        self.assertEqual(b.virtual_s,0.)
        self.assertIsNone(b.deadline)
        prefixes={key.rsplit('-',1)[0] for key in protocol.cache}
        self.assertEqual(len(prefixes),1)
        rows=[]
        c=Client(lambda p,r:(rows.append(json.loads(r)) or (200,world.response(False))))
        with self.assertRaises(Rejected):
            c.enter()
        self.assertNotIn(rows[0]['request_id'].rsplit('-',1)[0],prefixes)

    def test_deadline_limits_each_retry_and_no_exit_after_failure(self):
        clock=Clock()
        timeouts=[]
        sent=[]
        transport=HttpTransport('http://127.0.0.1:1')
        client=Client(transport)
        client.deadline=103.

        def fail(request,timeout):
            timeouts.append(timeout)
            sent.append((request.full_url,request.data))
            clock.now+=.2 if len(timeouts)==1 else timeout
            raise TimeoutError('injected timeout')

        with patch('client.time.monotonic',clock.monotonic),patch('client.time.sleep',clock.sleep),patch('client.open_response',side_effect=fail):
            with self.assertRaises(TimeoutError):
                client.measure((0,0),1)
            with self.assertRaises(RuntimeError):
                client.exit()
        self.assertEqual(len(timeouts),2)
        self.assertAlmostEqual(timeouts[0],1.)
        self.assertAlmostEqual(timeouts[1],.75)
        self.assertLessEqual(clock.now,101.)
        self.assertEqual(sent[0],sent[1])

    def test_exhausted_budget_and_exit_reserve(self):
        clock=Clock()
        client=Client(HttpTransport('http://127.0.0.1:1'))
        client.deadline=101.
        with patch('client.time.monotonic',clock.monotonic),patch('client.open_response') as opened:
            with self.assertRaises(TimeoutError):
                client.measure((0,0),1)
            with self.assertRaises(TimeoutError):
                client.exit()
            opened.assert_not_called()
        client.deadline=101.5
        body=b'{"accepted":true,"virtual_time_s":0,"real_timestamp_ms":0,"exit_reason":"user_exit"}'
        with patch('client.time.monotonic',clock.monotonic),patch('client.open_response',return_value=Response(body)) as opened:
            with self.assertRaises(TimeoutError):
                client.clear((0,0),1)
            client.exit()
            self.assertAlmostEqual(opened.call_args.kwargs['timeout'],.5)

    def test_chunk_reads_preserve_fragments_and_recheck_deadline(self):
        clock=Clock()
        class SlowResponse(Response):
            def read1(self,size):
                clock.now+=.6
                return b'{'  # Bytes keep arriving, but the absolute deadline wins.
        transport=HttpTransport('http://127.0.0.1:1')
        with patch('client.time.monotonic',clock.monotonic),patch('client.open_response',return_value=SlowResponse(b'')) as opened:
            with self.assertRaises(TimeoutError):
                transport('/enter',b'{"request_id":"one"}',deadline=101.)
        self.assertEqual(opened.call_count,1)
        self.assertEqual(base64.b64decode(transport.failures[0]['response_body_b64']),b'{{')

    def test_channels_validated_locally(self):
        world=World([])
        client=Client(Protocol(world).dispatch)
        client.enter()
        for channel in (1.5,True,False,'1',0,21,float('nan'),float('inf'),np.bool_(True)):
            for action in (client.measure,client.clear):
                with self.subTest(channel=channel,action=action.__name__),self.assertRaises(ValueError):
                    action((0,0),channel)
        self.assertEqual(world.commands,1)
        for channel in (1,1.,np.int64(2),np.float64(2.)):
            client.measure((0,0),channel)
        self.assertEqual(world.commands,5)

    def test_local_http_normal_and_truncated_paths(self):
        for truncated in (False,True):
            with self.subTest(truncated=truncated):
                world=World([Source(2,100,0)])
                with local_server(Protocol(world),truncated) as (transport,sent):
                    client=Client(transport)
                    client.enter()
                    self.assertEqual(client.measure((100,0),2)['measure_result'],'near')
                    self.assertEqual(client.clear((100,0),2)['clear_result'],'success')
                    self.assertEqual(client.exit()['exit_reason'],'user_exit')
                self.assertEqual(world.commands,4)
                self.assertEqual(client.virtual_s,31.)
                self.assertEqual(client.position,(100.,0.))
                self.assertEqual(client.channel,2)
                self.assertEqual(len(sent),4+int(truncated))
                if truncated:
                    self.assertEqual(sent[0],sent[1])

    def test_virtual_deadline_prevents_exit_probe(self):
        world=World([])
        client=Client(Protocol(world).dispatch)
        client.enter()
        client.measure((1800000,0),1)
        with self.assertRaises(RuntimeError):
            client.exit()
        self.assertEqual(world.commands,2)

    def test_public_api_signatures(self):
        for method,expected in {'enter':'(self)','measure':'(self, position, channel)',
                                'clear':'(self, position, channel)','exit':'(self)'}.items():
            self.assertEqual(str(inspect.signature(getattr(Client,method))),expected)


if __name__=='__main__':
    unittest.main()
