"""Finalize documentation/CLI artifacts without rerunning frozen experiments."""
import ast
import hashlib
import json
import math
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-11_icra-confirmation"


def main():
    checks=[]
    previous=json.loads((OUT/"final_checks.json").read_text());assert previous["passed"]==60 and previous["failed"]==0
    for p in ROOT.glob("*.py"):ast.parse(p.read_text(),filename=str(p))
    checks.append(dict(test="post_documentation_all_python_parses",passed=True))
    reports=[ROOT/name for name in ("REPORT.md","ICRA_CONNECTION.md","ROBUST_GUARANTEES_UPDATE.md","REPORT_ICRA_UPDATE.md","GOAL.md")]
    for p in reports:
        for target in re.findall(r"\]\(([^)]+)\)",p.read_text()):
            if target.startswith(("https:","http:","#")):continue
            assert (p.parent/target.split("#")[0]).exists(),(p,target)
    checks.append(dict(test="final_report_and_figure_links_resolve",passed=True))
    smoke=[]
    for folder in sorted((ROOT/"robot_runs").glob("*-bounded-offline")):
        result=json.loads((folder/"summary.json").read_text())
        if result["seed"]==42 and result["method"] in ("joint7","joint22"):
            assert result["all_cleared"] and result["cleared"]==15 and result["official_calls"]==0
            smoke.append(dict(path=str(folder.relative_to(ROOT)),summary=result))
    assert {r["summary"]["problem"] for r in smoke}=={3,4}
    (OUT/"cli_smoke.json").write_text(json.dumps(dict(scored_execution_count=0,runs=smoke),indent=2))
    checks.append(dict(test="offline_cli_q3_joint7_and_q4_joint22_seed42_all_clear",passed=True))
    paper=json.loads((ROOT/"experiments/runs/2026-09-11_icra-inspiration/paper_metadata.json").read_text())
    assert hashlib.sha256((ROOT/"reference/tokekar2013asensor.pdf").read_bytes()).hexdigest()==paper["sha256"]
    checks.append(dict(test="author_pdf_6_pages_sha256_preserved",passed=True))
    width=11.35*math.sin(math.radians(1.01));edge=20*math.sqrt(3)/width
    numeric=dict(icra_alpha_deg=1.01,icra_conditional_diameter_per_triangle_edge=width,
                 triangle_edge_sufficient_for_mec20_via_lemma_m=edge,
                 new_family_max_measurements=8004,new_family_max_optical_calls=1760,
                 new_family_max_move_m=1053800,new_family_virtual_bound_s=1053800/5+8004*6+1760*3+16*2,
                 new_family_command_bound=8004+1760+2)
    assert numeric["new_family_virtual_bound_s"]==264096 and numeric["new_family_command_bound"]==9766
    (OUT/"derived_math_values.json").write_text(json.dumps(numeric,indent=2))
    checks.append(dict(test="reported_conditional_lemma_and_new_budget_arithmetic",passed=True))
    result=dict(passed=len(checks),failed=0,checks=checks,prior_final_checks=60,prior_feedback_replays=40,official_calls=0)
    (OUT/"artifact_checks.json").write_text(json.dumps(result,indent=2))
    manifest=json.loads((ROOT/"FINAL_MANIFEST.json").read_text());assert manifest["total_offline_executions"]==16131
    old=OUT/"manifest_before_final_artifact_refresh.json"
    if not old.exists():old.write_bytes((ROOT/"FINAL_MANIFEST.json").read_bytes())
    artifacts=list(ROOT.glob("*.py"))+reports+[OUT/name for name in ("summary.md","trials.csv","run_config.json","final_checks.json","artifact_checks.json","derived_math_values.json","cli_smoke.json","paired_analysis.json","category_metrics.csv","confirmation_comparison.png","confirmation_comparison.pdf","directional22_certificate.png","directional22_certificate.pdf","next_steps.md")]
    manifest.update(python_files_parsed=len(list(ROOT.glob("*.py"))),final_verification_checks=60,artifact_checks=5,
        sha256={str(p.relative_to(ROOT.parent)):hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts})
    (ROOT/"FINAL_MANIFEST.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False))
    print(json.dumps(result,indent=2))


if __name__=="__main__":main()
