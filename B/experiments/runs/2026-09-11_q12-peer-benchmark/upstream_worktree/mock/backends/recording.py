"""Transparent, flushed JSONL journal of every transport attempt, including retries."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from uuid import uuid4
from .base import Backend

FIELDS = ('accepted','virtual_time_s','measure_result','svd_deg','clear_result','real_timestamp_ms')

class RecordingBackend(Backend):
    def __init__(self, backend, output, run_id=None):
        super().__init__(backend.robot_id, backend.retries)
        self.backend, self.kind = backend, backend.kind
        self.run_id, self.sequence = run_id or uuid4().hex, 0
        path = Path(output); path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = path.open('x', encoding='utf-8')  # Never silently overwrite an oracle recording.

    def exchange(self, path, payload):
        self.sequence += 1
        started = time.perf_counter()
        row = dict(schema_version=1, run_id=self.run_id, backend=self.kind, sequence=self.sequence,
                   recorded_at=datetime.now(timezone.utc).isoformat(), request_id=payload.get('request_id'),
                   action=path, position=payload.get('position'), channel=payload.get('channel'),
                   request=deepcopy(payload), http_status=None, response=None, transport_error=None)
        try:
            reply = self.backend.exchange(path, payload)
            row.update(http_status=reply.status, response=deepcopy(reply.body))
            return reply
        except Exception as error:
            row['transport_error'] = {'type':type(error).__name__, 'message':str(error)}
            raise
        finally:
            row['duration_ms'] = (time.perf_counter()-started)*1000
            for field in FIELDS:
                row[field] = (row['response'] or {}).get(field)
            self.stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n')
            self.stream.flush()

    def close(self):
        self.stream.close()
        self.backend.close()
