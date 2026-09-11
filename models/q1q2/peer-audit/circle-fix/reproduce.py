import importlib.util
import pathlib
import sys
root=pathlib.Path('/Users/flower/math/2026/B题')
path=root/'models/q1q2/peer-audit/differential_q1.py'
spec=importlib.util.spec_from_file_location('audit',path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
# Run the unchanged audit main, preserving the original evidence. Materialize
# fixtures before redirecting only the artifact directory.
fixtures=list(m.fixtures())
m.fixtures=lambda:iter(fixtures)
m.HERE=root/'models/q1q2/peer-audit/circle-fix'
m.HERE.mkdir(exist_ok=True)
sys.argv=[str(path),'--seed','2026091107','--random-cases','8000']
m.main()
