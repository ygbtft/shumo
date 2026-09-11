import json,sys
import numpy as np
from pathlib import Path
rows=[json.loads(s) for s in Path(sys.argv[1]).read_text().splitlines()]
for p in (3,4):
    base={r['idx']:r for r in rows if r['problem']==p and r['variant']=='base'}
    for v in dict.fromkeys(r['variant'] for r in rows if r['problem']==p):
        group=[r for r in rows if r['problem']==p and r['variant']==v]; n=sum(r['sources'] for r in group)
        d=np.array([r['T']-base[r['idx']]['T'] for r in group]);ns=np.array([r['sources'] for r in group]);ids=np.random.default_rng(42).integers(len(group),size=(4000,len(group)));ci=np.quantile(d[ids].sum(1)/ns[ids].sum(1),[.025,.975])
        dif={k:round(sum(r[k]-base[r['idx']][k] for r in group)/n,4) for k in ['M','S','L','Cf']}
        print(p,v,len(group),n,'ok',sum(r['cleared']==r['sources'] and not r['failure'] for r in group),'T',round(sum(r['T'] for r in group)/n,4),'delta',round(d.sum()/n,4),'ci',ci.round(3),'slower',sum(d>1e-5),'worst',round(max(d),2),dif)
print('max ledger error',max(abs(r['ledger_error']) for r in rows))
print('failures',[(r['problem'],r['seed'],r['variant'],r['failure']) for r in rows if r['failure']])
