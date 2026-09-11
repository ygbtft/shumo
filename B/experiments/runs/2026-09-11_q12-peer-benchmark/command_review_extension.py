"""Run only the new boundary review, preserving the original diagnostic outputs."""
import ast
from fractions import Fraction
import json
import math
from pathlib import Path
import numpy as np

base = Path(__file__).resolve().parent
root = base.parents[2]
result = json.loads((base/"diagnostics/q1_halfplane_only.json").read_text())
source = ast.parse((root/"q12_benchmark_diagnostics.py").read_text())
main = next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=="main")
start = next(i for i,n in enumerate(main.body) if isinstance(n,ast.Assign)
             and any(isinstance(t,ast.Name) and t.id=="reviews" for t in n.targets))
def pts(values):
    return np.array([[float(Fraction(x)) if isinstance(x,str) else float(x) for x in p] for p in values])
namespace = dict(rows=result["results"], np=np, math=math, pts=pts, OUT=base/"diagnostics", json=json)
exec(compile(ast.Module(body=main.body[start:],type_ignores=[]), "q12_review_extension", "exec"), namespace)
