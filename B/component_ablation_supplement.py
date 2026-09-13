"""Pre-existing stress fixtures and factorial fallback checks, separate from OFAT.
Frozen after main training, before inspecting supplemental outcomes; no tuning.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
import types
import component_ablation as a

INTERACTION = {3:['baseline','nearest_sensing','no_optical_grid','nearest_without_grid'],
               4:['baseline','no_negative','no_optical_grid','negative_without_grid']}
LABELS = {**a.NAMES, 'nearest_without_grid':'最近邻测向＋关闭光学格心',
          'negative_without_grid':'关闭双负截断＋关闭光学格心'}


def construct(p, client, setting):
    if setting not in ('nearest_without_grid','negative_without_grid'):
        return a.construct(p,client,setting)
    policy = a.construct(p,client,'nearest_sensing' if p==3 else 'no_negative')
    def absent_grid(poly,angle):
        policy.stats['ablation_missing_grid'] += 1
        raise a.ComponentUnavailable('Optical grid removed in factorial control: fallback center failed')
    class PrivatePolicy:
        complete_source = staticmethod(a.clone_function(a.Policy.complete_source,optical_cover=absent_grid))
    if p == 3:
        policy.complete_source = types.MethodType(a.clone_function(
            policy.complete_source.__func__,Policy=PrivatePolicy),policy)
    else:
        policy.fallback = types.MethodType(a.clone_function(a.InterleavedMixin.fallback,Policy=PrivatePolicy),policy)
    return policy


def execute(task):
    # Picklable module-level worker; the function with private globals stays local.
    return a.clone_function(a.execute, construct=construct)(task)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args();out=args.archive.resolve()/'supplement';out.mkdir()
    old=a.ROOT/'experiments/runs/2026-09-11_clear-gate-validation/fixtures.json'
    stress={int(p):[r for r in rows if r.get('split')=='stress']
            for p,rows in json.loads(old.read_text()).items()}
    config=dict(interaction=INTERACTION, names=LABELS,
                design='2x2: Q3 full/nearest sensing x grid on/off; Q4 negative cut on/off x grid on/off',
                stress_origin=str(old), stress_origin_sha256=hashlib.sha256(old.read_bytes()).hexdigest(),
                stress_is_preexisting=True, ordinary_seed_selection='Reuse complete main training/validation fixtures without filtering',
                frozen_before_supplement_outcomes=True, baseline_defaults_changed=False)
    (out/'config.json').write_text(json.dumps(config,ensure_ascii=False,indent=2))
    shutil.copy2(__file__,out/Path(__file__).name)
    a.run_phase(out/'stress',stress,args.workers)
    summarize=a.clone_function(a.summarize,NAMES=LABELS)
    run=a.clone_function(a.run_phase,SETTINGS=INTERACTION,execute=execute,summarize=summarize)
    for phase in ('training','validation'):
        fixtures={int(p):rows for p,rows in json.loads((args.archive/phase/'fixtures.json').read_text()).items()}
        run(out/('interaction_'+phase),fixtures,args.workers)
    print('Completed supplement:',out,flush=True)

if __name__=='__main__':main()
