"""Standard Q2 outer recommendation; production geometry and objective unchanged."""
from pathlib import Path
from dataclasses import asdict, replace
import argparse, hashlib, json, math, time
import numpy as np
from ...geometry import BearingMeasurement, NumericPolicy
from ...feasible import PhysicsConfig, build_source_set, Feedback, check_candidate
from ...q2 import SearchConfig, select_second_point, sample_sources, score_point, boundary_point
from ...run import jsonable
from ...optional.certified import certify
from ...diagnostics import clearance_summary
HERE=Path(__file__).resolve().parent
CFG=SearchConfig(time_budget_s=14400., tie_floor_m=0., tie_multiplier=0.)
SS=build_source_set(BearingMeasurement((0.,0.),0.),PhysicsConfig(),CFG.policy)
def save(name,obj):
    (HERE/name).write_text(json.dumps(jsonable(obj),ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['search','refine','certify','paper']);a=p.parse_args()
    if a.stage=='search':
        t=time.monotonic();r=select_second_point(SS,CFG,extra_points=[(750.,400.)]);save('search.json',r)
        print(r.q_best,r.score.J_hat,r.stop_reason,r.completed_stages,time.monotonic()-t,flush=True)
    elif a.stage=='refine':
        refine()
    elif a.stage=='certify':
        certify_final()
    else:
        finalize_paper()
def refine():
    # Independent complete standard four-disk bounding rectangle, both signs.
    # x >= 0 and the disks centred at 5*u imply x <= 1005, |y| <= 1000.
    started=time.monotonic();cache={};rows=[];history=[]
    def value(q,level=0):
        q=tuple(float(x) for x in q);key=(q,level)
        if check_candidate(SS,q,False,CFG.policy).status!='IN' or q==(0.,0.):return math.inf
        if key not in cache:
            sm=sample_sources(SS,level,CFG.source_grids,q,inward=CFG.near_offset_m,second_half_width_deg=1.)
            cache[key]=score_point(SS,q,sm,CFG).J_hat
        return cache[key]
    for step in (50.,25.):
        n=0
        for x in np.arange(0,1005.00001,step):
            for y in np.arange(-1000,1000.00001,step):
                q=(float(x),float(y));v=value(q)
                if math.isfinite(v):rows.append(dict(q=q,J_hat=v,step_m=step));n+=1
        history.append(dict(stage='augmented_grid',step_m=step,admissible=n,best=min(rows,key=lambda r:r['J_hat'])))
        print(history[-1],flush=True)
    for deg in np.arange(0,360,1.):
        q=boundary_point(SS,math.radians(float(deg)),replace(CFG,boundary_precision_m=1e-7))
        if q:
            for f in (1.,.999):
                z=tuple(f*x for x in q);v=value(z)
                if math.isfinite(v):rows.append(dict(q=z,J_hat=v,boundary_deg=float(deg),fraction=f))
    save('augmented-grid.json',dict(config=CFG,rows=rows,history=history))
    starts=[]
    for r in sorted(rows,key=lambda r:r['J_hat']):
        if all(math.dist(r['q'],q)>=25 for q in starts):starts.append(tuple(r['q']))
        if len(starts)==12:break
    finals=[]
    for q in starts:
        initial=q;step=25.;trace=[]
        while step>=.1953125:
            opts=[(value((q[0]+dx,q[1]+dy)),(q[0]+dx,q[1]+dy)) for dx in (-step,0,step) for dy in (-step,0,step)]
            v,z=min(opts)
            if v<value(q)-1e-10:q=z
            else:trace.append(dict(step_m=step,q=q,J_hat=value(q)));step/=2
        finals.append(q);history.append(dict(stage='augmented_local',initial=initial,q=q,J_hat=value(q),trace=trace))
        print(history[-1],flush=True)
    # Golden-section boundary refinement around the best positive-y 1-degree sample.
    br=min((r for r in rows if r.get('fraction')==1. and r['q'][1]>0),key=lambda r:r['J_hat'])
    def bq(deg):return boundary_point(SS,math.radians(deg),replace(CFG,boundary_precision_m=1e-7))
    lo,hi=br['boundary_deg']-1.,br['boundary_deg']+1.;ratio=(math.sqrt(5)-1)/2
    aa,bb=hi-ratio*(hi-lo),lo+ratio*(hi-lo);fa,fb=value(bq(aa),2),value(bq(bb),2)
    for _ in range(32):
        if fa<fb:
            hi,bb,fb=bb,aa,fa;aa=hi-ratio*(hi-lo);fa=value(bq(aa),2)
        else:
            lo,aa,fa=aa,bb,fb;bb=lo+ratio*(hi-lo);fb=value(bq(bb),2)
    q=bq(aa if fa<fb else bb)
    # Report a reproducible decimal command coordinate, moved 1e-5 m inward.
    norm=math.hypot(*q);q=tuple(round(x*(1-1e-5/norm),6) for x in q)
    finals.extend([q,(q[0],-q[1]),(750.,400.)])
    final_values=[dict(q=q,J_hat=value(q,2)) for q in dict.fromkeys(finals)]
    best=min(final_values,key=lambda r:r['J_hat']);bestq=tuple(best['q'])
    # Reflect symmetry to publish the north-side representative, then re-evaluate exactly.
    bestq=(bestq[0],abs(bestq[1]));best=dict(q=bestq,J_hat=value(bestq,2))
    sensitivity=[]
    for origin in (bestq,(750.,400.)):
        for step in (1.,5.,25.):
            for dx,dy in ((step,0),(-step,0),(0,step),(0,-step)):
                z=(origin[0]+dx,origin[1]+dy);v=value(z,2)
                sensitivity.append(dict(origin=origin,q=z,offset_m=step,J_hat=v if math.isfinite(v) else None,status='IN' if math.isfinite(v) else 'OUT'))
    save('refined.json',dict(config=CFG,history=history,final_values=final_values,best=best,
        boundary_angle_interval_deg=[lo,hi],boundary_precision_m=1e-7,coordinate_inward_m=1e-5,
        local_min_step_m=.1953125,sensitivity=sensitivity,evaluations=len(cache),elapsed_seconds=time.monotonic()-started,
        status='NUMERICAL_CANDIDATE',scope='Complete augmented 50/25 m grids; 1 degree boundary; 12 local starts; no global outer certificate'))
    print('BEST',best,flush=True)

def certify_final():
    from ...geometry import convex_hull, diameter, Region, RegionKind
    from importlib.metadata import version
    data=json.loads((HERE/'refined.json').read_text());qs=[tuple(data['best']['q']),(750.,400.)]
    finer=((17,49),(33,97),(65,193));fcfg=replace(CFG,source_grids=finer,refine_pairs=True)
    union=set();own={};audits={}
    for q in qs:
        records=[]
        for level in range(3):
            sm=sample_sources(SS,level,CFG.source_grids,q,inward=CFG.near_offset_m,second_half_width_deg=1.)
            score=score_point(SS,q,sm,replace(CFG,refine_pairs=True))
            records.append(dict(kind='source_augmented',grid=CFG.source_grids[level],score=score))
        for factor in (.1,10.):
            pol=replace(CFG.policy,length_abs=CFG.policy.length_abs*factor,angle_abs=CFG.policy.angle_abs*factor,relative=CFG.policy.relative*factor)
            sm=sample_sources(SS,2,CFG.source_grids,q,inward=CFG.near_offset_m*factor,second_half_width_deg=1.)
            records.append(dict(kind='tolerance',factor=factor,score=score_point(SS,q,sm,replace(CFG,policy=pol,refine_pairs=True))))
        sm=sample_sources(SS,2,finer,q,inward=CFG.near_offset_m,second_half_width_deg=1.)
        own[q]=sm;union.update(sm.points)
        shifted=sample_sources(SS,2,finer,q,inward=CFG.near_offset_m,second_half_width_deg=1.,shifted=True)
        shscore=score_point(SS,q,shifted,fcfg)
        records.append(dict(kind='shifted_fine',grid=finer[-1],score=shscore))
        for w in shscore.top_pairs:union.update((w.x,w.y))
        audits[q]=records
        print('audited',q,flush=True)
    common=replace(own[qs[0]],points=tuple(sorted(union)),augmentation_q=None)
    # First fair pass collects locally refined witnesses; second freezes the union.
    for q in qs:
        score=score_point(SS,q,common,fcfg)
        for w in score.top_pairs:union.update((w.x,w.y))
    common=replace(common,points=tuple(sorted(union)))
    rows=[]
    for q in qs:
        score=score_point(SS,q,common,fcfg)
        cert=certify(SS,q,tol=.001,max_nodes=2000000,time_limit_s=1800.,dps=30)
        assert cert.converged and cert.lower_m<=score.J_hat+.001 and score.J_hat<=cert.upper_m
        fb=Feedback(score.witness.branch,score.witness.common_bearing_deg,1.)
        ds=replace(common,points=tuple(sorted(set(common.points)|{score.witness.x,score.witness.y})))
        clear=clearance_summary(SS,q,fb,ds,CFG.policy)
        verts=clear.outer_vertices
        outer_d=diameter(Region(kind=RegionKind.POLYGON,vertices=convex_hull(verts,CFG.policy))).length
        centers=[(r*math.cos(a),r*math.sin(a)) for r in (5.,1000.) for a in (-math.pi/180,math.pi/180)]
        margins=[1000.-math.dist(q,c) for c in centers]
        from mpmath.ctx_iv import MPIntervalContext
        iv=MPIntervalContext();iv.dps=30;ivq=tuple(iv.mpf(x) for x in q)
        residual_intervals=[]
        for r in (5,1000):
            for sign in (-1,1):
                a=sign*iv.pi/180
                residual=(ivq[0]-r*iv.cos(a))**2+(ivq[1]-r*iv.sin(a))**2-1000**2
                assert residual.b<0
                residual_intervals.append([math.nextafter(float(residual.a),-math.inf),math.nextafter(float(residual.b),math.inf)])
        movement=math.hypot(*q)
        row=dict(q=q,score=score,certificate=cert,clearance=clear,outer_diameter_m=outer_d,
            all_feedback_radius_upper_Jung_m=cert.upper_m/math.sqrt(3),
            movement_m=movement,movement_seconds=movement/5,movement_and_detection_seconds=movement/5+5,
            four_disk_distance_margins_m=margins,four_disk_squared_residual_intervals_m2=residual_intervals,check=check_candidate(SS,q,False,CFG.policy),audits=audits[q])
        rows.append(row);print('CERTIFIED',q,cert.lower_m,cert.upper_m,'r_U',clear.r_U,'H_U',clear.H_U,flush=True)
    hashes={n:hashlib.sha256((HERE.parents[1]/n).read_bytes()).hexdigest() for n in ('q2.py','feasible.py','geometry.py','diagnostics.py','optional/certified.py')}
    save('report.json',dict(first=SS.first,physics=SS.physics,config=fcfg,common_samples=len(common.points),
        rows=rows,production_sha256=hashes,versions={n:version(n) for n in ('numpy','mpmath')},
        interval_options=dict(tol=.001,max_nodes=2000000,time_limit_s=1800.,dps=30),
        status='NUMERICAL_CANDIDATE_WITH_CERTIFIED_FIXED_Q_DIAMETER',
        radius_scope='r_U, H_U and outer diameter conditional on each row common feedback; not worst over all feedbacks',
        outer_scope='float64 checked circumscribed polygon, not interval certification',
        lower_improvement_m=rows[1]['certificate'].lower_m-rows[0]['certificate'].upper_m))

def finalize_paper():
    report=json.loads((HERE/'report.json').read_text());refined=json.loads((HERE/'refined.json').read_text())
    a,b=report['rows'];qa=a['q'];ca,cb=a['certificate'],b['certificate']
    def f(x):return f'{x:.6f}'
    def up(x):return f'{math.ceil(x*1e6)/1e6:.6f}'
    def down(x):return f'{math.floor(x*1e6)/1e6:.6f}'
    def bounds(c):return f"[{down(c['lower_m'])},{up(c['upper_m'])}]"
    def coord(q):return '('+','.join(f(x) for x in q)+')'
    lines=['<!-- Q2-OUTER-RESULTS-BEGIN -->',
        '**表2（续）　标准场景的第二检测点推荐与固定点统一复评（距离：米；时间：秒）**','',
        '| 方案 | 第二点 $q$ | 公共复评 $\\widehat J$ | 连续认证 $[J_L,J_U]$ | 条件 $r_U$ | 条件外包直径 | 条件 $H_U$ | 移动距离 | 移动时间 | 移动＋检测 |',
        '|---|---|---:|---|---:|---:|---:|---:|---:|---:|']
    for label,r in [('当前分辨率下推荐点',a),('固定点对照',b)]:
        c=r['clearance'];lines.append(f"| {label} | ${coord(r['q'])}$ | {f(r['score']['J_hat'])} | ${bounds(r['certificate'])}$ | {up(c['r_U'])} | {up(r['outer_diameter_m'])} | {up(c['H_U'])} | {f(r['movement_m'])} | {f(r['movement_seconds'])} | {f(r['movement_and_detection_seconds'])} |")
    h=refined['history'];grids=[x for x in h if x['stage']=='augmented_grid']
    lines+=['',f"标准场景推荐采用 $q^*={coord(qa)}$ 米，关于首测方向反射的 $({f(qa[0])},-{f(qa[1])})$ 米具有相同的连续目标值。本处星号标记搜索所得推荐点，不表示已证明全局最优；坐标保留六位小数用于复现，不表示已认证相应位置精度或唯一最优站点。推荐点与固定点均按0.001米区间宽度容差复核，实际区间宽度分别为 {f(ca['gap_m'])} 米和 {f(cb['gap_m'])} 米。由固定点下界减去推荐点上界，推荐方案使连续最坏直径至少减少 {down(report['lower_improvement_m'])} 米；移动并检测用时按 $\\|q\\|/5+5$ 计算，不计求解器运行时间及后续清除动作。",'',
        f"保收域由式（22）给出，完整扫描包围矩形为 $[0,1005]\\times[-1000,1000]$。含逐站边界接触源对补样的50米、25米网格分别取得 {grids[0]['admissible']}、{grids[1]['admissible']} 个严格可行非首站点，其最佳 $\\widehat J$ 分别为 {f(grids[0]['best']['J_hat'])}、{f(grids[1]['best']['J_hat'])} 米；另以1度步长扫描边界及其0.999倍内侧点。从12个相距至少25米的低值起点作局部细化，站点步长由25米递减至0.1953125米。最佳正半平面边界网格点左右1度范围另作32轮黄金分割，边界径向二分精度为 $10^{{-7}}$ 米；输出坐标先内移 $10^{{-5}}$ 米、再保留六位小数，随后对实际输出坐标复评。四圆盘距离平方约束均经过30位区间运算核验为严格成立。",'',
        f"网格及局部站点初评采用 $9\\times25$ 源网格与合法边界补样，候选终评采用 $33\\times97$；表2（续）再将推荐点和固定点同时加密至 $65\\times193$，合并双方补样及错位采样见证后冻结 {report['common_samples']} 个公共源样本。最长8个源对分别细化8轮。浮点长度绝对容差为 $10^{{-10}}$ 米、相对容差与角判定参数均为 $10^{{-12}}$，近场偏移为 $10^{{-7}}$ 米，并同时乘0.1与10复核。本次取主目标的数值最小候选，配置中并列带置零；未将移动时间加权进入目标。",'']
    for label,r in [('推荐点',a),('固定点',b)]:
        source=[x['score']['J_hat'] for x in r['audits'] if x['kind']=='source_augmented']
        tv=[x['score']['J_hat'] for x in r['audits'] if x['kind']=='tolerance']
        sh=[x['score']['J_hat'] for x in r['audits'] if x['kind']=='shifted_fine'][0]
        lines.append(f"{label}在 $9\\times25$、$17\\times49$、$33\\times97$ 下的含补样评分依次为 {', '.join(f(x) for x in source)} 米；0.1倍/10倍容差评分为 {f(tv[0])}/{f(tv[1])} 米，细网格错位评分为 {f(sh)} 米。上述有限采样变化只反映所做细化，不是外层误差界。")
    lines+=['',f"表2（续）的覆盖量分别对应推荐点与固定点最长源对的共同示向度 $\\beta={f(a['clearance']['feedback']['bearing_deg'])}^\\circ$、${f(b['clearance']['feedback']['bearing_deg'])}^\\circ$，不是对全部反馈的最坏覆盖半径。$r_U$ 为保守外包的覆盖半径，$H_U$ 为该外包到检测点的最远距离上界；使用的圆盘切线外包边数分别为 {a['clearance']['outer_sides']}、{b['clearance']['outer_sides']}。外包量展示向上取整，沿用float64残差检查，不称区间认证。两点均有 $J_L>40$ 米，因而各自至少存在一种反馈，使任意统一20米落点都不能保证一次清除；这一不可能性来自合法源对下界，不能由 $r_U>20$ 单独推出。",'']
    for label,origin in [('推荐点',qa),('固定点',[750.,400.])]:
        chunks=[]
        for step in (1.,5.,25.):
            rr=[r for r in refined['sensitivity'] if r['origin']==origin and r['offset_m']==step]
            vals=[r['J_hat'] for r in rr if r['J_hat'] is not None]
            chunks.append(f"±{step:g}米的可行轴向扰动评分范围为 [{f(min(vals))},{f(max(vals))}] 米（{len(vals)}/4个扰动可行）")
        lines.append(label+'的邻域复评中，'+'；'.join(chunks)+'。')
    lines+=['',"推荐点位于保收域边界附近，向域外扰动的站点被排除。结果完成了标准首测场景的外层推荐与固定点统一对照；近边界首站、域外首站属于其他输入，未在本表求解。未对检测点连续域建立全局下界，故本结论限于当前网格、边界扫描及局部细化产生的最佳候选，不宣称外层全局最优。完整配置、网格、轨迹、见证与复现命令见[外层实验说明](q1q2/benchmarks/q2_outer/README.md)及[统一复评报告](q1q2/benchmarks/q2_outer/report.json)。",'<!-- Q2-OUTER-RESULTS-END -->']
    block='\n'.join(lines).replace('\\\\','\\')
    (HERE/'paper-results.md').write_text(block+'\n')
    paper=HERE.parents[2]/'paper-full.md';text=paper.read_text()
    if '<!-- Q2-OUTER-RESULTS-BEGIN -->' in text:
        start=text.index('<!-- Q2-OUTER-RESULTS-BEGIN -->');end=text.index('<!-- Q2-OUTER-RESULTS-END -->')+len('<!-- Q2-OUTER-RESULTS-END -->')
    else:
        start=text.index('**【TODO-1：');end=text.index('】**',start)+3
    text=text[:start]+block+text[end:]
    old=next(line for line in text.splitlines() if line.startswith('针对问题2，'))
    new=f"针对问题2，利用首次正反馈对固定未知接收半径进行条件化，导出完整保收域，并将未知第二读数下的最坏直径转化为共同反馈源位置对的最大距离。标准首测场景的保收域精确约化为四圆盘交；经50/25米网格、边界扫描与多起点细化，推荐第二点 ${coord(qa)}$ 米，其连续最坏直径认证区间为 ${bounds(ca)}$ 米，移动并检测需 {a['movement_and_detection_seconds']:.3f} 秒。相较固定点 $(750,400)$ 米，最坏直径至少缩小 {math.floor(report['lower_improvement_m']*1000)/1000:.3f} 米，但仍不能保证任何反馈后均可用一次20米统一落点清除。另证明移动预算仅10米时，最坏剩余歧义至少1000米。推荐点为当前分辨率下的最佳数值候选，固定坐标认证不证明外层全局最优。"
    text=text.replace(old,new)
    text=text.replace('### 5.3 问题2固定检测点的连续认证结果','### 5.3 问题2的第二检测点推荐与连续认证结果')
    text=text.replace('它们不代替尚待汇总的第二点优化实验。','第二点优化的数值结果另见第5.3节。')
    text=text.replace('这些是求解方案的初始分辨率，不表示已经完成相应全域计算。','这些为基础分辨率；标准场景已完成的全域扫描与加密记录见第5.3节。')
    text=text.replace('数值并列阈值取0.1米与终选比较最大细化变化二者的较大值，进入该带的候选再按移动距离择优。该带只表示当前数值分辨率下效果相当。','默认数值并列阈值取0.1米与终选比较最大细化变化二者的较大值，进入该带的候选再按移动距离择优。该带只表示当前数值分辨率下效果相当；第5.3节外层定稿实验另将并列带置零，以报告主目标的数值最小候选。')
    text=text.replace('- **TODO-1｜问题2最终推荐方案：**补充第5.3节所列外层候选选择、统一对照和反馈后清除结果。固定点认证已完成，不再作为空缺。','- **TODO-1｜已完成：问题2标准场景最终推荐方案。**第5.3节表2（续）已给出外层搜索所得推荐点、与固定点的同精度认证、条件覆盖外包、清除判定、移动时间及网格/容差细化记录；脚本与原始报告见 `q1q2/benchmarks/q2_outer/`。结论为当前分辨率下的最佳候选，未声称连续外层全局最优；其他首测场景不在本次定稿范围。')
    text=text.replace('本次论文修订读取既有报告，未重新运行benchmark、正式测试或查询实时统计库。','Q3/Q4部分读取既有报告，未重新运行其benchmark、正式测试或查询实时统计库；Q2标准场景的外层搜索与固定坐标认证已按第5.3节新增脚本重跑。')
    evidence='| 标准场景第二检测点推荐 | 全域网格、边界扫描、多起点细化及两点同精度认证 | 推荐坐标的连续直径已认证；外层仅为数值候选 |'
    if evidence not in text:
        anchor='| 七站全向覆盖 |'
        text=text.replace(anchor,evidence+'\n'+anchor)
    archive='| [Q2外层推荐与统一复评](q1q2/benchmarks/q2_outer/report.json)、[复现说明](q1q2/benchmarks/q2_outer/README.md) | 标准场景推荐点与固定点的0.001米认证、条件覆盖及移动代价；不认证连续外层最优 |'
    if archive not in text:
        anchor='| [Q3/Q4独立基准]'
        text=text.replace(anchor,archive+'\n'+anchor)
    paper.write_text(text)

if __name__=='__main__':main()
