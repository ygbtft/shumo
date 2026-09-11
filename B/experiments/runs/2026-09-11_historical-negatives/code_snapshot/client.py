"""Serial feedback-only client. Importing this file makes no HTTP request."""
import json
import math
import time
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

    def __call__(self,path,raw):
        # Exactly the same immutable body/request_id on an ambiguous transport retry.
        request=Request(self.base_url+path,data=raw,headers={"Content-Type":"application/json"},method="POST")
        for attempt in range(self.retries+1):
            try:
                with urlopen(request,timeout=self.timeout_s) as response:
                    return response.status,json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                return exc.code,json.loads(exc.read().decode("utf-8"))
            except (URLError,TimeoutError,ConnectionError,OSError):
                if attempt==self.retries:
                    raise
                time.sleep(.05*(attempt+1))


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
        self.transcript=transcript

    def call(self,path,position=None,channel=None):
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise TimeoutError("Client's available real-time budget expired")
        self.sequence+=1
        payload={"arena_id":"default","robot_id":self.robot_id,"request_id":f"b42-{self.sequence}"}
        if position is not None:
            p=[float(v) for v in position]
            if not all(math.isfinite(v) and abs(v)<=2000000 for v in p):
                raise ValueError("unsafe coordinate")
            payload.update(position={"x":p[0],"y":p[1]},channel=int(channel))
        raw=json.dumps(payload,ensure_ascii=False,allow_nan=False,separators=(",",":")).encode("utf-8")
        began=time.monotonic()
        status,response=self.__transport(path,raw)
        if self.transcript is not None:
            self.transcript.append({"path":path,"request":payload,"http_status":status,"response":response})
        if status!=200 or response.get("accepted") is not True:
            raise Rejected(f"{path}: HTTP {status}, accepted={response.get('accepted')}")
        self.virtual_s=float(response["virtual_time_s"])
        if path=="/enter":
            self.deadline=began+int(response["remaining_real_duration_s"])
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
