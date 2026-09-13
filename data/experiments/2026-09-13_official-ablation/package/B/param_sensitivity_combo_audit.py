"""Re-evaluate already frozen combinations on training fixtures, without retuning.
This audit may run alongside validation; it never reads validation results.
"""
import argparse,json
from pathlib import Path
import param_sensitivity as s

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',type=Path,required=True);args=parser.parse_args()
    out=args.run
    selection=json.loads((out/'frozen_selection.json').read_text())
    fixtures={int(p):fs for p,fs in json.loads((out/'training/fixtures.json').read_text()).items()}
    settings={p:{'baseline':{},'combined':selection[str(p)]['combined']} for p in (3,4)}
    s.run_phase(out/'combination_training',fixtures,settings,4)
if __name__=='__main__':main()
