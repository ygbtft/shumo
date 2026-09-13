import json
from .base import Backend
from ..error_field import ErrorField
from ..protocol import Protocol
from ..scenario_gen import generate
from ..simulator import Limits, Simulator

class InProcMock(Backend):
    kind = 'inproc_mock'

    def __init__(self, protocol=None, robot_id='mock-robot', seed=0, scenario_config=None, error_config=None):
        super().__init__(robot_id)
        if protocol is None:
            case = generate(seed, scenario_config)
            protocol = Protocol(Simulator(case, ErrorField(seed, error_config), Limits(countdown_s=0)), robot_id)
        self._protocol = protocol

    def exchange(self, path, payload):
        return self._protocol.handle('POST', path, json.dumps(payload, ensure_ascii=False).encode('utf-8'), {'Content-Type':'application/json'})
