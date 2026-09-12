"""Verify instance overrides against the actual entry defaults on 24 paired cases."""
import argparse,json
from pathlib import Path
import param_sensitivity as s

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    results=[]
    for p in (3,4):
        for i,f in enumerate(s.cases(p,1,202629800)):
            if i>=12:break
            b=s.execute((p,'baseline',{},f))
            changes={'localization_weight':.08,'steps':10,'share_limit':6}
            if p==4:changes.update(angle_min=1.02,angle_max=30,transverse_m=40,share_cooldown=150,pause_limit=16,fraction=.15)
            else:changes.update(max_active=3,remainder_weight=1)
            c=s.execute((p,'explicit_defaults',changes,f))
            keys=('total_virtual_s','measurements','switches','misses','stats','all_cleared')
            assert all(b[k]==c[k] for k in keys)
            results.append(dict(problem=p,case_id=f['case_id'],equal=True,all_cleared=b['all_cleared']))
    with args.output.open('x') as f:json.dump(results,f,indent=2)
if __name__=='__main__':main()
