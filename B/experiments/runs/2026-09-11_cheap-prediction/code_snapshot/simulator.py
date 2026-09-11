"""Offline physics and JSON protocol fixture. Truth exists only in this module/runner.

This is independently implemented from the documents, not the official simulator.
Authentication, GUI/network lifecycle, encrypted logs and rate limiting are not emulated.
"""
from dataclasses import dataclass, asdict
import hashlib
import json
import math
import threading
import time
import unicodedata
import numpy as np


@dataclass(frozen=True)
class Source:
    channel: int
    x: float
    y: float
    radius: float = 1000.
    facing: float | None = None


class World:
    def __init__(self, sources, seed=42, noise="hash", rounding="nearest", remaining_real_s=1200):
        assert len({s.channel for s in sources}) == len(sources)
        assert all(1<=s.channel<=20 and 1000<=s.radius<=1500 and math.hypot(s.x,s.y)<=1800+1e-7 for s in sources)
        self.sources = {s.channel:s for s in sources}
        self.seed, self.noise, self.rounding = seed, noise, rounding
        self.position, self.channel = (0.,0.), 1
        self.time_us = 0
        self.cleared = set()
        self.entered, self.exited = False, False
        self.remaining_real_s = remaining_real_s
        self.start = None
        self.moves, self.measures, self.clears, self.switches, self.commands = 0., 0, 0, 0, 0
        self.response_counts = {}

    def error(self, position, channel):
        x, y = (0. if float(v)==0 else float(v) for v in position)
        if self.noise == "plus":
            return 1.
        if self.noise == "minus":
            return -1.
        if self.noise == "alternating":
            return 1. if math.sin((x+2*y)/301+channel) >= 0 else -1.
        if self.noise == "smooth":
            return math.sin(x/800+y/700+channel)
        key = f"{self.seed}:{channel}:{x.hex()}:{y.hex()}".encode()
        return 2*int.from_bytes(hashlib.blake2b(key,digest_size=8).digest(),"big")/(2**64-1)-1

    def response(self, accepted, **extra):
        return {"accepted":accepted, "real_timestamp_ms":int(time.time()*1000),
                "virtual_time_s": self.time_us/1e6 if accepted else 0, **extra}

    def act(self, path, payload):
        if path == "/enter":
            if self.entered or self.exited:
                return self.response(False)
            self.entered, self.start = True, time.monotonic()
            self.commands += 1
            return self.response(True,max_virtual_duration_s=360000,max_real_duration_s=1200,
                                 remaining_real_duration_s=self.remaining_real_s)
        if not self.entered or self.exited:
            return self.response(False)
        if self.time_us >= 360000_000000 or time.monotonic()-self.start >= self.remaining_real_s:
            self.exited = True
            raise ConnectionError("Offline deadline closed the simulated interface")
        self.commands += 1
        if path == "/exit":
            self.exited = True
            return self.response(True,exit_reason="user_exit")
        q = (float(payload["position"]["x"]), float(payload["position"]["y"]))
        channel = int(payload["channel"])
        distance = math.dist(self.position,q)
        self.moves += distance
        self.time_us += round(distance/5*1e6)
        self.position = q
        s = self.sources.get(channel)
        alive = s is not None and channel not in self.cleared
        if path == "/clear":
            self.clears += 1
            success = alive and math.dist(q,(s.x,s.y)) <= 20.
            self.time_us += (5 if success else 3)*1_000000
            if success:
                self.cleared.add(channel)
            result = "success" if success else "no_target_in_range"
            result_field = "clear_result"
            extra = {}
        else:
            self.measures += 1
            switch = channel != self.channel
            self.switches += int(switch)
            self.time_us += (5+int(switch))*1_000000
            self.channel = channel
            result, extra, result_field = "no_signal", {}, "measure_result"
            if alive:
                dx, dy = q[0]-s.x, q[1]-s.y
                r = math.hypot(dx,dy)
                # Boundary tolerance only absorbs floating arithmetic at exact 90 degrees.
                in_angle = s.facing is None or dx*math.cos(s.facing)+dy*math.sin(s.facing) >= -1e-10
                if r <= s.radius and in_angle:
                    if r <= 5.:
                        result = "near"
                    else:
                        result = "direction"
                        angle = (math.degrees(math.atan2(-dy,-dx))+self.error(q,channel))%360
                        angle = round(angle,2) if self.rounding=="nearest" else math.floor(angle*100)/100
                        extra["svd_deg"] = angle%360
        self.response_counts[result] = self.response_counts.get(result,0)+1
        return self.response(True,**{result_field:result},**extra)

    def score(self):
        return {"sources":len(self.sources),"cleared":len(self.cleared),
                "clear_fraction":len(self.cleared)/max(1,len(self.sources)),
                "all_cleared":len(self.cleared)==len(self.sources),
                "total_virtual_s":self.time_us/1e6,
                "per_source_s":self.time_us/1e6/max(1,len(self.cleared)),
                "move_m":self.moves,"measurements":self.measures,"clear_calls":self.clears,
                "switches":self.switches,"commands":self.commands,
                "missed_channels":sorted(set(self.sources)-self.cleared)}


class Protocol:
    def __init__(self, world, robot_id="offline-robot"):
        self.world, self.robot_id = world, robot_id
        self.cache = {}
        self.lock = threading.Lock()

    def rejected(self, status=400):
        return status,self.world.response(False)

    def dispatch(self,path,raw,method="POST",content_type="application/json",encoding="identity"):
        if path not in ("/enter","/exit","/measure","/clear"):
            return self.rejected(404)
        if method != "POST":
            return self.rejected(405)
        types = [x.strip().lower() for x in content_type.split(";")]
        if types[0] != "application/json" or (len(types)>1 and types[1:] != ["charset=utf-8"]) or encoding.lower()!="identity":
            return self.rejected(415)
        if len(raw)>65536:
            return self.rejected(413)
        def unique(pairs):
            d={}
            for k,v in pairs:
                if k in d:
                    raise ValueError("duplicate key")
                d[k]=v
            return d
        def bad_constant(v):
            raise ValueError(v)
        try:
            p=json.loads(raw.decode("utf-8"),object_pairs_hook=unique,parse_constant=bad_constant)
            if not isinstance(p,dict):
                raise ValueError("not object")
            def depth(v):
                if isinstance(v,dict):
                    return 1+max([depth(x) for x in v.values()],default=0)
                if isinstance(v,list):
                    return 1+max([depth(x) for x in v],default=0)
                return 0
            if depth(p)>16:
                raise ValueError("depth")
            allowed={"arena_id","robot_id","request_id"}
            if path in ("/measure","/clear"):
                allowed|={"position","channel"}
            if allowed-set(p):
                raise ValueError("missing field")
            for key,limit in [("robot_id",64),("request_id",128)]:
                v=p[key]
                if not isinstance(v,str) or not 1<=len(v.encode("utf-8"))<=limit or any(unicodedata.category(c) in ("Cc","Cf") for c in v):
                    raise ValueError("identifier")
            if not isinstance(p["arena_id"],str):
                raise ValueError("arena type")
            if path in ("/measure","/clear"):
                channel=p["channel"]
                if isinstance(channel,bool) or not isinstance(channel,(int,float)) or not 1<=channel<=20 or channel!=int(channel):
                    raise ValueError("channel")
                pos=p["position"]
                if not isinstance(pos,dict) or not {"x","y"} <= set(pos):
                    raise ValueError("position")
                for value in (pos["x"],pos["y"]):
                    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or abs(value)>2000000:
                        raise ValueError("coordinate")
                if set(pos)!={"x","y"}:
                    return self.rejected(200)
            if set(p)-allowed or p["arena_id"]!="default" or p["robot_id"]!=self.robot_id:
                return self.rejected(200)
        except (ValueError,TypeError,OverflowError,UnicodeError,RecursionError):
            return self.rejected(400)
        canonical=path+json.dumps(p,sort_keys=True,separators=(",",":"))
        rid=p["request_id"]
        if rid in self.cache:
            old,response=self.cache[rid]
            return (200,dict(response)) if old==canonical else self.rejected(409)
        if not self.lock.acquire(blocking=False):
            return self.rejected(409)
        try:
            response=self.world.act(path,p)
            if response["accepted"]:
                self.cache[rid]=(canonical,dict(response))
            return 200,response
        finally:
            self.lock.release()


def serialize_sources(sources):
    return [asdict(s) for s in sources]
