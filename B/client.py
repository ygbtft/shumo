"""Serial feedback-only client. Importing this file makes no HTTP request."""
import json
import math
import time
import base64
from http.client import IncompleteRead
from numbers import Real
from uuid import uuid4
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit


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
                try:
                    response=urlopen(request,timeout=self._timeout(deadline))
                except HTTPError as exc:
                    # Error bodies can also be truncated; parse inside the retry scope.
                    response=exc
                with response:
                    status=response.code
                    # read1 returns available bytes, retaining fragments even if the
                    # next read resets. Recompute the socket timeout after headers
                    # and each chunk instead of granting a fresh full timeout.
                    reader=getattr(response,"read1",None)
                    if reader is None:
                        self._timeout(deadline)
                        body.extend(response.read())
                    else:
                        while True:
                            timeout=self._timeout(deadline)
                            fp=getattr(response,"fp",None)
                            sock=getattr(getattr(fp,"raw",None),"_sock",None)
                            if sock is not None:
                                sock.settimeout(timeout)
                            chunk=reader(65536)
                            if not chunk:
                                if getattr(response,"length",0):
                                    raise IncompleteRead(b"",response.length)
                                break
                            body.extend(chunk)
                result=json.loads(body.decode("utf-8"))
                if not isinstance(result,dict):
                    raise ValueError("Expected a JSON response object")
                return status,result
            except (URLError,TimeoutError,ConnectionError,OSError,IncompleteRead,
                    ValueError) as exc:
                if isinstance(exc,IncompleteRead):
                    body.extend(exc.partial)
                row={"event":"transport_failure","path":path,"attempt":attempt+1,
                     "request":json.loads(raw),"request_body_b64":base64.b64encode(raw).decode("ascii"),
                     "http_status":status,"error":repr(exc),
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
        except Exception:
            self.__stopped=True
            raise
        if self.transcript is not None:
            self.transcript.append({"path":path,"request":payload,"http_status":status,"response":response})
        if status!=200 or response.get("accepted") is not True:
            raise Rejected(f"{path}: HTTP {status}, accepted={response.get('accepted')}")
        self.virtual_s=float(response["virtual_time_s"])
        if path=="/enter":
            self.deadline=began+int(response["remaining_real_duration_s"])
            self.__max_virtual_s=float(response["max_virtual_duration_s"])
        if path=="/exit" or (self.__max_virtual_s is not None and self.virtual_s>=self.__max_virtual_s):
            self.__stopped=True
        if position is not None:
            self.position=tuple(p)
        if path=="/measure":
            self.channel=int(channel)
        return response

    def enter(self):
        return self.call("/enter")

    def measure(self,position,channel):
        return self.call("/measure",position,channel)

    def clear(self,position,channel):
        return self.call("/clear",position,channel)

    def exit(self):
        return self.call("/exit")
