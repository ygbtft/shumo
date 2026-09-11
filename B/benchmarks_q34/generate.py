"""Deterministic standalone truth generation. Does not import production code."""
import copy, hashlib, json, math, random
from pathlib import Path
from oracle_coverage import certificate, partition, omni_cells, leaf
from oracle_localization import region, mec, negative_membership
from oracle_clearance import truth
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent

def main():
    rows=[]; fixtures=HERE/'fixtures'; fixtures.mkdir(exist_ok=True)
    def add(block,category,inp,gt,method):
        rows.append(dict(case_id=f'{block}/{category}/{len(rows):04d}',block=block,category=category,input=inp,ground_truth=gt,truth_method=method))
    def save(name,data):
        path=fixtures/(name+'.json'); path.write_text(json.dumps(data,separators=(',',':'))+'\n')
        return dict(fixture=str(path.relative_to(HERE)),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    selected=json.loads((ROOT/'experiments/runs/2026-09-11_cover21-confirmation/selected_layouts.json').read_text())
    closed=json.loads((ROOT/'experiments/runs/2026-09-11_closed-cover21/certified_layouts.json').read_text())
    for name,item in {**closed,**{k:selected[k] for k in ('grid21_29','grid21_7')}}.items():
        ref=save(name,item)
        for mode in ('strict','closed'):
            valid=certificate(item['points'],item['certificate'],mode)
            add('coverage','archived_'+mode,{**ref,'api':'certificate','mode':mode},dict(accepted=valid,partition=partition(item['certificate']['cells']),route_matches=set(map(tuple,item['points']))==set(map(tuple,item['route'])),n_leaves=len(item['certificate']['cells'])), 'Fraction trie disk partition + exact hull determinants/four corner squared distances')
    pts=[[0.,0.]]+[[1140*math.cos(k*math.pi/3),1140*math.sin(k*math.pi/3)] for k in range(6)]
    cells=omni_cells(pts); ref=save('q3_ring7',dict(points=pts,cells=cells))
    add('coverage','q3_omni',dict(ref,api='q3'),dict(covered=True,n_leaves=len(cells)), 'Independent Fraction uniform-station square cover of entire closed source disk')
    add('coverage','q3_not_q4',dict(ref,api='witness',source=[1800,0],facing=[1,0]),dict(receivers=0),'Exact squared distances and dot products: legal east-facing counterexample')
    # Fully dyadic synthetic certificates, with stations strictly outside each cell or on its corners.
    for mode,pad in [('strict',75),('closed',0)]:
        ps=[]; cs=[]
        for x in range(-1575,1800,450):
            for y in range(-1575,1800,450):
                ids=list(range(len(ps),len(ps)+4)); h=225
                ps.extend([[x+a*(h+pad),y+b*(h+pad)] for a,b in [(-1,-1),(1,-1),(1,1),(-1,1)]])
                cs.append([x,y,h,ids])
        base=dict(covered=True,arena_radius=1800,receive_radius=1000,scale=65536,cells=cs)
        for mutation in ('valid','missing','duplicate','overlap','off_tree','bad_id','collinear','out_of_range'):
            c=copy.deepcopy(base); p=copy.deepcopy(ps)
            if mutation=='missing': c['cells'].pop(30)
            if mutation=='duplicate': c['cells'].append(c['cells'][30])
            if mutation=='overlap': c['cells'].append([0,0,1800,[0,1,2]])
            if mutation=='off_tree': c['cells'][30][0]+=.125
            if mutation=='bad_id': c['cells'][30][3]=[-1,0,1]
            if mutation=='collinear':
                for i in c['cells'][30][3]: p[i][1]=0
            if mutation=='out_of_range': p[c['cells'][30][3][0]]=[1950,1950]
            ref=save('synthetic_'+mode+'_'+mutation,dict(points=p,certificate=c))
            for api_mode in ('strict','closed'):
                add('coverage',mode+'_'+mutation,dict(ref,api='certificate',mode=api_mode),dict(accepted=certificate(p,c,api_mode),partition=partition(c['cells'])), 'Exact rational convex hull + corner range + dyadic prefix partition')
    # Direct leaf predicates at equality, microscopic strictness, and degeneracy.
    for label,p in [('tangent',[[-300,-400],[300,-400],[300,400],[-300,400]]),('strict',[[-301,-401],[301,-401],[301,401],[-301,401]]),('collinear',[[-500,0],[0,0],[500,0]])]:
        add('coverage','leaf_'+label,dict(api='leaf',points=p,cell=[0,0,300,list(range(len(p)))]),dict(closed=leaf(p,[0,0,300,list(range(len(p)))],'closed'),strict=leaf(p,[0,0,300,list(range(len(p)))],'strict')),'Independent rational convex hull predicates')
    rng=random.Random(3404)
    for problem in (3,4):
        for i in range(24):
            source=[rng.randint(-1100,1100),rng.randint(-1100,1100)]
            initial=[[source[0]+x,source[1]+y] for x,y in [(-80,-80),(80,-80),(80,80),(-80,80)]]
            obs=[]
            for k in range(1+i%4):
                theta=(i*17+k*91)*math.pi/180; distance=200+137*k
                p=[source[0]+distance*math.cos(theta),source[1]+distance*math.sin(theta)]
                a=math.degrees(math.atan2(source[1]-p[1],source[0]-p[0]))
                err=[-1,0,1][i%3]; obs.append(dict(position=p,angle=round((a+err)%360,2),error=1.01))
            exact=region(initial,obs); vertices=[list(map(float,p)) for p in exact]
            gt=dict(vertices=vertices,mec=mec(vertices),source=source)
            add('localization','q%d_bearing_%d'%(problem,len(obs)),dict(problem=problem,initial=initial,observations=obs),gt,'60-digit independent trigonometry + rational closed half-plane intersection; exhaustive rational MEC supports')
        for angle in (0,90,179.99,359.99):
            obs=[dict(position=[0,0],angle=angle,error=1.01)]
            vertices=[list(map(float,p)) for p in region(None,obs)]
            add('localization','q%d_initial_outer64'%problem,dict(problem=problem,initial=None,observations=obs),dict(vertices=vertices,mec=mec(vertices)), 'Independent 64 tangent half-planes for 1800/1500 circles + rational clipping')
        for label,initial,obs,source in [
            ('zero_error_point',[[-100,-100],[100,-100],[100,100],[-100,100]],
             [dict(position=[-200,0],angle=0,error=0),dict(position=[0,-200],angle=90,error=0)],[0,0]),
            ('zero_error_segment',[[-100,-100],[100,-100],[100,100],[-100,100]],
             [dict(position=[-200,0],angle=0,error=0)],[0,0]),
            ('near_parallel',[[-100,-100],[100,-100],[100,100],[-100,100]],
             [dict(position=[-1000,0],angle=0,error=1.01),dict(position=[-999,-.001],angle=0,error=1.01)],[0,0]),
            ('receive_cap',None,[dict(position=[1000,0],angle=180,error=1.01)],[-500,0]),
            ('arena_cap',None,[dict(position=[1700,0],angle=0,error=1.01)],[1800,0])]:
            vertices=[list(map(float,p)) for p in region(initial,obs)]
            add('localization','q%d_%s'%(problem,label),dict(problem=problem,initial=initial,observations=obs),dict(vertices=vertices,mec=mec(vertices),source=source),'Independent rational half-plane intersection with exact ray degeneracy / circle tangent bounds')
        for distance in (999.999,1000,1000.001,1200):
            source=[distance,0]
            add('localization','q%d_no_signal_1000'%problem,dict(api='negative',problem=problem,source=source,position=[0,0],initial=[[900,-10],[1300,-10],[1300,10],[900,10]]),dict(feasible=negative_membership(source,[0,0],problem)), 'Exact closed 1000 m receive disk: Q3 negative excludes disk; Q4 orientation existentially permits negative')
    shapes=[('point',[[0,0]]),('segment20',[[-20,0],[20,0]]),('segment_out',[[-20.00001,0],[20.00001,0]]),('segment_in',[[-19.99998,0],[19.99998,0]]),('right',[[0,0],[24,0],[0,32]]),('acute',[[0,0],[38,0],[19,33]]),('obtuse',[[-19,0],[19,0],[0,1]]),('jung_below',[[-17,0],[17,0],[0,29]]),('collinear_duplicates',[[-15,0],[0,0],[15,0],[15,0]])]
    for i in range(30): shapes.append(('random',[[rng.randint(-30,30),rng.randint(-30,30)] for _ in range(3+i%5)]))
    for problem in (3,4):
        for name,ps in shapes:
            for shift in ([0,0],[1500,-700]):
                p=[[x+shift[0],y+shift[1]] for x,y in ps]
                add('clearance','q%d_%s'%(problem,name),dict(problem=problem,points=p),truth(p),'Independent Fraction one/two/three support circle enumeration; D²<=1200 / D²>1600 / intermediate exact MEC')
    (HERE/'cases.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
    print(json.dumps({'generated':len(rows),'blocks':{k:sum(r['block']==k for r in rows) for k in ('coverage','localization','clearance')}}),flush=True)
if __name__=='__main__': main()
