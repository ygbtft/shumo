"""One transport contract. Strategies receive the same Observation from every backend."""
from abc import ABC, abstractmethod
import http.client
import time
from urllib.error import URLError
from uuid import uuid4
from ..protocol import Reply
from ..simulator import InterfaceClosed

class Backend(ABC):
    kind = 'abstract'

    def __init__(self, robot_id='mock-robot', retries=0):
        self.robot_id, self.retries = robot_id, retries
        self._counter, self._prefix = 0, uuid4().hex
        self.last_request = None

    @abstractmethod
    def exchange(self, path: str, payload: dict) -> Reply:
        """Exactly one attempt; preserve supplied ID. Raise InterfaceClosed without JSON."""

    def send(self, action, request_id=None):
        self._counter += 1
        self.last_request = action.payload(self.robot_id, request_id or f'{self._prefix}-{self._counter}')
        for attempt in range(self.retries+1):
            try:
                return self.exchange(action.path, self.last_request)
            except InterfaceClosed:
                if attempt == self.retries: raise
                time.sleep(min(.1*2**attempt, .5))

    def close(self): pass
