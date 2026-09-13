import json,sys
from client import Client
import official_sensitivity_config as cfg
def deny(*args,**kwargs):raise AssertionError('No requests in configuration check')
p=cfg.construct(4,Client(deny),{})
assert not any(x=='mock' or x.startswith('mock.') for x in sys.modules)
print(json.dumps(dict(parameters=cfg.actual_parameters(p,4),official_requests=0,mock_executions=0)))
