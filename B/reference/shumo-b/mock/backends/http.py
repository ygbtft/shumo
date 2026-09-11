"""Windows-compatible loopback transports; no GUI, VM, login or remote API code."""
import http.client
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from .base import Backend
from ..protocol import Reply
from ..simulator import InterfaceClosed

class HttpMock(Backend):
    kind = 'http_mock'

    def __init__(self, base_url='http://127.0.0.1:2026', robot_id='mock-robot', timeout=5, retries=2):
        super().__init__(robot_id, retries)
        url = urlparse(base_url)
        if url.scheme != 'http' or url.hostname != '127.0.0.1' or url.path not in ('', '/') or url.query or url.fragment or url.username:
            raise ValueError('base_url must be http://127.0.0.1:<port>')
        self.base_url, self.timeout = base_url.rstrip('/'), timeout

    def exchange(self, path, payload):
        raw = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
        req = Request(self.base_url+path, data=raw, headers={'Content-Type':'application/json'}, method='POST')
        try:
            with urlopen(req, timeout=self.timeout) as response:
                return Reply(response.status, json.loads(response.read().decode('utf-8')))
        except HTTPError as error:
            return Reply(error.code, json.loads(error.read().decode('utf-8')))
        except (URLError, OSError, http.client.HTTPException) as error:
            raise InterfaceClosed(str(error)) from error

class HttpOfficial(HttpMock):
    """Run INSIDE official simulator's Windows guest after user starts a practice session.

    This adapter intentionally only calls the four published robot endpoints.
    The port alone cannot identify whether the listening service is mock or official;
    recorded provenance is the operator's configuration, not a verified server identity.
    """
    kind = 'http_official'

    def __init__(self, base_url='http://127.0.0.1:2026', robot_id='mock-robot', timeout=5, retries=2, *, session_mode):
        if session_mode != 'practice':
            raise ValueError('HttpOfficial is restricted to user-started practice sessions')
        super().__init__(base_url, robot_id, timeout, retries)

    def exchange(self, path, payload):
        if path not in ('/enter', '/measure', '/clear', '/exit'):
            raise ValueError('Only the four published robot actions are permitted')
        return super().exchange(path, payload)
