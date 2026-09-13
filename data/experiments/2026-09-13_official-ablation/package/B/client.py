"""Serial feedback-only client. Importing this file makes no HTTP request."""
import json
import math
import time
import base64
from contextlib import contextmanager
import socket
import threading
from http.client import HTTPConnection, HTTPException, IncompleteRead
from numbers import Real
from uuid import uuid4
from urllib.request import Request
from urllib.error import URLError
from urllib.parse import urlsplit


@contextmanager
def open_response(request, timeout):
    # The fixed transport only talks to loopback HTTP. Own the socket before
    # connect so one watchdog can interrupt connect, send, headers and body.
    parts = urlsplit(request.full_url)
    host = "127.0.0.1" if parts.hostname == "localhost" else parts.hostname
    sock = socket.socket(socket.AF_INET6 if host == "::1" else socket.AF_INET)
    conn = HTTPConnection(host, parts.port or 80, timeout=timeout)
    expired = threading.Event()

    def close_socket():
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        sock.close()

    def expire():
        expired.set()
        close_socket()

    def connect(address, timeout, source_address):
        sock.settimeout(timeout)
        sock.connect(address)
        return sock

    conn._create_connection = connect
    timer = threading.Timer(timeout, expire)
    response = None
    timer.start()
    try:
        conn.request("POST", parts.path, body=request.data,
                     headers={"Content-Type": "application/json"})
        response = conn.getresponse()
        response.code = response.status
        yield response
        if expired.is_set():
            raise TimeoutError("HTTP absolute deadline expired")
    except Exception as exc:
        if expired.is_set():
            raise TimeoutError("HTTP absolute deadline expired") from exc
        raise
    finally:
        timer.cancel()
        timer.join()
        close_socket()
        if response is not None:
            response.close()
        conn.close()


class Rejected(RuntimeError):
    pass


class HttpTransport:
    def __init__(self, base_url, timeout_s=5., retries=2):
        parts=urlsplit(base_url)
        if parts.scheme!="http" or parts.hostname not in ("127.0.0.1","localhost","::1") or parts.path not in ("", "/") or parts.query or parts.fragment or parts.username:
            raise ValueError("The documented simulator is a local loopback HTTP service")
        self.base_url=base_url.rstrip("/")
        self.timeout_s,self.retries=timeout_s,retries
        self.failures=[]

    def _timeout(self,deadline):
        remaining=self.timeout_s if deadline is None else deadline-time.monotonic()
        if remaining<=0:
            raise TimeoutError("Client's available real-time budget expired")
        return min(self.timeout_s,remaining)

    def __call__(self,path,raw,*,deadline=None,transcript=None):
        # Exactly the same immutable body/request_id on an ambiguous transport retry.
        request=Request(self.base_url+path,data=raw,headers={"Content-Type":"application/json"},method="POST")
        self.failures=[]
        for attempt in range(self.retries+1):
            body=bytearray()
            status=None
            try:
                with open_response(request, timeout=self._timeout(deadline)) as response:
                    status=response.code
                    # read1 preserves received fragments on a later disconnect.
                    # The watchdog also covers getresponse's status/header reads.
                    while True:
                        self._timeout(deadline)
                        chunk=response.read1(65536)
                        if not chunk:
                            if response.length:
                                raise IncompleteRead(b"",response.length)
                            break
                        body.extend(chunk)
                result=json.loads(body.decode("utf-8"))
                if not isinstance(result,dict):
                    raise ValueError("Expected a JSON response object")
                self._timeout(deadline)
                return status,result
            except (URLError,OSError,HTTPException,
                    ValueError) as exc:
                # OSError includes socket.error/timeout, ConnectionError,
                # BrokenPipeError and connect/send failures.
                # HTTPException also covers RemoteDisconnected, bad
                # status lines and truncated headers/bodies. A send failure does
                # NOT prove non-execution: never mint a new ID to recover it.
                if isinstance(exc,IncompleteRead):
                    body.extend(exc.partial)
                row={"event":"transport_failure","path":path,"attempt":attempt+1,
                     "request":json.loads(raw),"request_body_b64":base64.b64encode(raw).decode("ascii"),
                     "http_status":status,"error":repr(exc),
                     "phase":"response_body" if status is not None else "connect_send_or_headers",
                     "execution_state":"unknown",
                     "response_body_b64":base64.b64encode(body).decode("ascii")}
                self.failures.append(row)
                if transcript is not None:
                    transcript.append(row)
                if attempt==self.retries:
                    raise
                delay=.05*(attempt+1)
                if deadline is not None and deadline-time.monotonic()<=delay:
                    raise TimeoutError("Insufficient real-time budget for retry") from exc
                time.sleep(delay)


class Client:
    """The policy receives this facade; it is not given World, sources, or a seed."""
    def __init__(self,transport,robot_id="offline-robot",transcript=None):
        self.__transport=transport
        self.robot_id=robot_id
        self.position=(0.,0.)
        self.channel=1
        self.virtual_s=0.
        self.deadline=None
        self.sequence=0
        self.__request_prefix="b42-"+uuid4().hex
        # A new object is a new run, never a session recovery mechanism.
        # Recovery needs persisted pending bytes/ID, confirmed state and deadline;
        # replaying /enter cannot recover them. Do not send new actions after an
        # unresolved transport failure (including a speculative /exit).
        self.__stopped=False
        self.__max_virtual_s=None
        self.transcript=transcript

    def call(self,path,position=None,channel=None):
        if self.__stopped:
            raise RuntimeError("Client stopped; cannot recover a session by re-entering or querying exit")
        # Keep one second for persistence and another for an explicit normal exit.
        deadline=None if self.deadline is None else self.deadline-(1. if path=="/exit" else 2.)
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError("Client's available real-time budget expired")
        self.sequence+=1
        payload={"arena_id":"default","robot_id":self.robot_id,"request_id":f"{self.__request_prefix}-{self.sequence}"}
        if position is not None:
            if isinstance(channel,bool) or not isinstance(channel,Real) or not 1<=channel<=20 or channel!=int(channel):
                raise ValueError("channel must be an integer in 1..20")
            p=[float(v) for v in position]
            if len(p)!=2 or not all(math.isfinite(v) and abs(v)<=2000000 for v in p):
                raise ValueError("unsafe coordinate")
            payload.update(position={"x":p[0],"y":p[1]},channel=int(channel))
        raw=json.dumps(payload,ensure_ascii=False,allow_nan=False,separators=(",",":")).encode("utf-8")
        began=time.monotonic()
        try:
            if isinstance(self.__transport,HttpTransport):
                status,response=self.__transport(path,raw,deadline=deadline,transcript=self.transcript)
            else:
                status,response=self.__transport(path,raw)
            if not isinstance(response, dict):
                raise ValueError("Expected a JSON response object")
            if status == 200 and type(response.get("accepted")) is not bool:
                raise ValueError("Missing or invalid accepted flag")
            if status!=200 or response.get("accepted") is not True:
                if self.transcript is not None:
                    self.transcript.append({"path":path,"request":payload,"http_status":status,"response":response})
        except Exception:
            self.__stopped=True
            raise
        if status!=200 or response.get("accepted") is not True:
            raise Rejected(f"{path}: HTTP {status}, accepted={response.get('accepted')}")
        try:
            def finite_number(field):
                value = response[field]
                if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
                    raise ValueError(f"Invalid finite number: {field}")
                return float(value)

            # Parse the entire fixed response before changing confirmed state.
            # virtual_s is the server's cumulative value, never local travel cost.
            virtual_s = finite_number("virtual_time_s")
            finite_number("real_timestamp_ms")
            new_deadline = self.deadline
            max_virtual_s = self.__max_virtual_s
            if path == "/enter":
                finite_number("max_real_duration_s")
                remaining = finite_number("remaining_real_duration_s")
                max_virtual_s = finite_number("max_virtual_duration_s")
                # Use request start: conservatively deduct response latency.
                new_deadline = began + remaining
                if not math.isfinite(new_deadline):
                    raise ValueError("Invalid real-time deadline")
            elif path == "/measure":
                if response["measure_result"] not in ("near", "direction", "no_signal"):
                    raise ValueError("Invalid measure_result")
                if response["measure_result"] == "direction":
                    angle = finite_number("svd_deg")
                    if not 0 <= angle < 360:
                        raise ValueError("Invalid svd_deg")
            elif path == "/clear":
                if response["clear_result"] not in ("success", "no_target_in_range"):
                    raise ValueError("Invalid clear_result")
            elif path == "/exit" and response["exit_reason"] != "user_exit":
                raise ValueError("Invalid exit_reason")
            new_position = self.position if position is None else tuple(p)
            new_channel = int(channel) if path == "/measure" else self.channel
            stopped = path == "/exit" or (max_virtual_s is not None and virtual_s >= max_virtual_s)
            if self.transcript is not None:
                self.transcript.append({"path":path,"request":payload,"http_status":status,"response":response})
        except Exception:
            # An unparseable acknowledgement or failed persistence leaves the
            # action unresolved. Catching it must never permit a new action ID.
            self.__stopped=True
            raise
        self.virtual_s, self.deadline, self.__max_virtual_s, self.position, self.channel, self.__stopped = (
            virtual_s, new_deadline, max_virtual_s, new_position, new_channel, stopped)
        return response

    def enter(self):
        return self.call("/enter")

    def measure(self,position,channel):
        return self.call("/measure",position,channel)

    def clear(self,position,channel):
        return self.call("/clear",position,channel)

    def exit(self):
        return self.call("/exit")
