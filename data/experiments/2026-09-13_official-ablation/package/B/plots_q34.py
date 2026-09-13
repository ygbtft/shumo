"""Paper figures only; no policy/geometry edits and no official requests.

Reproduce: ../mock/.venv/bin/python -B plots_q34.py --seed 11
Outputs PNG (180 dpi) and vector PDF. Practice observations are the rounded,
statistics-database-derived rows in ../Q34-SUMMARY.md, NOT per-source timings.
The in-process mock uses exactly bounded_http.mock_world + simulator.Protocol
and bounded_candidates.build. Ground truth is accessed only for plotting/checks.
"""
from pathlib import Path
import argparse
import json
import warnings
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Circle, Polygon, Rectangle, Wedge
from matplotlib.collections import PatchCollection
from scipy.spatial import ConvexHull

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / 'models/q34/figures'
CN = True

def tr(cn, en):
    return cn if CN else en

def style():
    global CN
    for name in ('Noto Sans CJK SC', 'PingFang SC', 'Arial Unicode MS'):
        try:
            font_manager.findfont(name, fallback_to_default=False)
        except ValueError:
            continue
        plt.rcParams.update({'font.family': name, 'axes.unicode_minus': False})
        fig, ax = plt.subplots(figsize=(6, 2))
        ax.set_title('中文字体测试：覆盖布局、发现定位清除、时间构成')
        ax.set_xlabel('试探半径 / m'); ax.set_ylabel('失手次数')
        with warnings.catch_warnings(record=True) as ws:
            warnings.simplefilter('always')
            fig.canvas.draw()
        if not any('Glyph' in str(w.message) for w in ws):
            fig.tight_layout(); fig.savefig(OUT/'font_check.png', dpi=180)
            plt.close(fig)
            print('Font verified:', name, flush=True)
            break
        plt.close(fig)
    else:
        CN = False
        plt.rcParams['font.family'] = 'DejaVu Sans'
    plt.rcParams.update({'font.size': 11, 'axes.titlesize': 13, 'legend.fontsize': 9,
                        'pdf.fonttype': 42, 'axes.unicode_minus': False})

def save(fig, name, note):
    fig.text(.5, .018, note, ha='center', va='bottom', fontsize=9)
    fig.tight_layout(rect=(0, .075, 1, .96))
    for ext in ('png', 'pdf'):
        fig.savefig(OUT/f'{name}.{ext}', dpi=180, bbox_inches='tight')
    plt.close(fig)
    print('Saved', name, flush=True)

def arena(ax):
    ax.add_patch(Circle((0, 0), 1800, fill=False, color='black', lw=1.5,
                        label=tr('源位置域（半径 1800 m）', 'Source domain (radius 1800 m)')))
    ax.set(xlim=(-2300, 2300), ylim=(-2300, 2300), xlabel='x / m', ylabel='y / m')
    ax.set_aspect('equal'); ax.grid(alpha=.2)

def coverage(problem):
    from bounded_candidates import load_paths
    from ring_coverage import covering_radius
    from visibility_certificate import rectangle_certificate, verify_cells
    p = next(iter(load_paths(problem).values()))
    fig, ax = plt.subplots(figsize=(9, 7))
    if problem == 3:
        for i, q in enumerate(p):
            ax.add_patch(Circle(q, 1000, fc='C0', ec='C0', alpha=.10,
                label=tr('最小接收半径 1000 m', 'Minimum receiving radius 1000 m') if i == 0 else None))
        note = tr(f'来源：bounded_candidates.load_paths(3)；解析最远近站距离 {covering_radius(6,1140):.2f} m < 1000 m',
                  f'Source: bounded_candidates.load_paths(3); exact covering radius {covering_radius(6,1140):.2f} m < 1000 m')
    else:
        cert = rectangle_certificate(p)
        verify_cells(p, cert)  # disk partition and each local hull; no full-square claim
        patches = [Rectangle((x-h, y-h), 2*h, 2*h) for x, y, h, ids in cert['cells']]
        coll = PatchCollection(patches, facecolor='C0', edgecolor='white', alpha=.25, linewidth=.3)
        ax.add_collection(coll)
        coll.set_clip_path(Circle((0, 0), 1800, transform=ax.transData))
        cell = min(cert['cells'], key=lambda c: np.linalg.norm(np.array(c[:2])-[600,600]))
        x,y,h,ids = cell
        hull = p[ids][ConvexHull(p[ids]).vertices]
        ax.add_patch(Polygon(hull, fc='C1', ec='C1', alpha=.25,
                             label=tr('示例方块的可接收站凸包', 'Receivable-station hull for one cell')))
        ax.add_patch(Rectangle((x-h,y-h),2*h,2*h,fc='C3',ec='C3',alpha=.8,
                              label=tr('示例获证方块', 'Example certified cell')))
        note = tr(f'来源：layouts/grid21_29.json；{len(patches)} 个方块覆盖源圆域（图中裁剪至圆域）\n各方块在统一 1000 m 可接收站凸包内，保证任意 180° 朝向接收；非全方形覆盖声明',
                  f'Source: layouts/grid21_29.json; {len(patches)} certified cells cover the source disk\nEach cell lies in its uniformly receivable (1000 m) station hull; arbitrary 180-degree source facing')
    ax.plot(p[:,0],p[:,1], '--',color='C0',lw=.9,alpha=.6,label=tr('布局访问顺序', 'Layout visit order'))
    ax.scatter(p[:,0],p[:,1],c='C0',edgecolors='white',s=65,zorder=5,label=tr('观测站', 'Stations'))
    for i,(x,y) in enumerate(p): ax.annotate(str(i+1),(x,y),xytext=(5,5),textcoords='offset points',fontsize=9)
    arena(ax)
    ax.set_title(tr(f'Q{problem}：'+('七站全向覆盖' if problem==3 else '二十一站任意朝向覆盖'),
                    f'Q{problem}: '+('7-station omnidirectional coverage' if problem==3 else '21-station arbitrary-facing coverage')))
    ax.legend(loc='upper center', bbox_to_anchor=(.5, 1.015), ncol=2, fontsize=8)
    ax.set_ylim(-2300, 2650)
    save(fig,f'q{problem}_coverage',note)

def simulate(problem, seed):
    from bounded_candidates import build, SPECS, load_paths
    from bounded_http import mock_world
    from simulator import Protocol
    from client import Client
    world = mock_world(problem,seed)
    protocol = Protocol(world,robot_id='offline-robot')
    trace, history = [], {}
    policy = None
    def snapshot():
        if policy is None: return
        for ch, poly in policy.regions.items():
            a = np.array(poly).copy()
            hist = history.setdefault(ch,[])
            if not hist or not np.array_equal(hist[-1][1],a):
                hist.append((len(trace),a))
    def transport(path,raw):
        snapshot()
        status, response = protocol.dispatch(path,raw)
        trace.append(dict(path=path,request=json.loads(raw),response=response))
        return status,response
    spec = next(iter(SPECS[problem].values()))
    policy = build(Client(transport,robot_id='offline-robot'),spec,problem,load_paths(problem))
    policy.run(); snapshot()
    assert len(world.cleared)==len(world.sources), 'Mock failed to clear all sources'
    if problem==4: assert any(s.facing is not None for s in world.sources.values())
    print(f'Q{problem} mock seed={seed}: {len(world.cleared)}/{len(world.sources)} cleared, {world.time_us/1e6:.6f} s',flush=True)
    return world,trace,history

def trajectory(problem,seed,data):
    from geometry import minimum_circle
    world,trace,history=data
    actions=[r for r in trace if r['path'] in ('/measure','/clear')]
    xy=lambda r: [r['request']['position']['x'],r['request']['position']['y']]
    path=np.array([[0,0]]+[xy(r) for r in actions])
    eligible=[ch for ch in history if len(history[ch])>=2 and (problem==3 or world.sources[ch].facing is not None)]
    ch=max(eligible,key=lambda c: (len(history[c]),-c))
    source=world.sources[ch]
    fig,axes=plt.subplots(1,3,figsize=(18,6))
    ax=axes[0]; arena(ax)
    ax.plot(path[:,0],path[:,1],color='C0',lw=.8,alpha=.65,label=tr('机器狗实跑轨迹','Robot trajectory'))
    for pred,marker,color,label in (
        (lambda r:r['path']=='/measure','.', 'C1',tr('测量点','Measurements')),
        (lambda r:r['path']=='/clear' and r['response']['clear_result']=='success','x','C2',tr('成功清除点','Successful clears'))):
        pts=np.array([xy(r) for r in actions if pred(r)])
        if len(pts): ax.scatter(*pts.T,s=22,marker=marker,color=color,label=label,zorder=4)
    for s in world.sources.values():
        ax.scatter(s.x,s.y,s=22,marker='*',color='black')
        if s.facing is not None:
            ax.arrow(s.x,s.y,160*np.cos(s.facing),160*np.sin(s.facing),width=4,head_width=50,color='C3')
    ax.scatter(source.x,source.y,s=160,facecolors='none',edgecolors='C3',label=f'Ch {ch}')
    ax.set_title(tr('整局轨迹（红箭头为源朝向）','Full run (red arrows: source facing)') if problem==4 else tr('整局轨迹（全向源）','Full run (omnidirectional sources)'))
    ax.legend(loc='upper left',fontsize=8)
    ax=axes[1]
    hist=history[ch]
    chosen=np.unique(np.linspace(0,len(hist)-1,min(4,len(hist)),dtype=int))
    for k,i in enumerate(chosen):
        poly=hist[i][1]
        ax.add_patch(Polygon(poly,fc=f'C{k}',ec=f'C{k}',alpha=.24,label=tr(f'区域更新 {i+1}',f'Region update {i+1}')))
    pts=np.array([xy(r) for r in actions if r['request']['channel']==ch and r['path']=='/measure' and r['response']['measure_result']!='no_signal'])
    ax.scatter(*pts.T,marker='o',s=24,color='C1',label=tr('接收到信号的测量点','Signal measurements'))
    clears=np.array([xy(r) for r in actions if r['path']=='/clear' and r['request']['channel']==ch])
    ax.scatter(*clears.T,marker='x',s=55,color='C2',label=tr('清除尝试点','Clear attempts'))
    ax.scatter(source.x,source.y,marker='*',s=100,color='black',label=tr('真值（仅绘图）','Truth (plotting only)'))
    if source.facing is not None:
        angle=np.degrees(source.facing)
        ax.add_patch(Wedge((source.x,source.y),180,angle-90,angle+90,fc='C3',alpha=.12))
        ax.arrow(source.x,source.y,160*np.cos(source.facing),160*np.sin(source.facing),head_width=20,color='C3')
    ax.autoscale_view(); ax.margins(.12); ax.set_aspect('equal'); ax.grid(alpha=.2)
    ax.set(xlabel='x / m',ylabel='y / m',title=tr(f'频道 {ch}：可行区域收缩',f'Channel {ch}: feasible-region contraction'))
    ax.legend(fontsize=8)
    zoom=ax.inset_axes([.15,.10,.43,.36])
    for k,i in enumerate(chosen):
        zoom.add_patch(Polygon(hist[i][1],fc=f'C{k}',ec=f'C{k}',alpha=.3))
    zoom.scatter(source.x,source.y,marker='*',s=35,color='black')
    zoom.scatter(*clears.T,marker='x',s=25,color='C2')
    zoom.set(xlim=(source.x-75,source.x+75),ylim=(source.y-75,source.y+75))
    zoom.set_aspect('equal'); zoom.tick_params(labelsize=6); zoom.grid(alpha=.2)
    zoom.set_title(tr('清除点局部放大 / m','Clearance detail / m'),fontsize=8)
    ax=axes[2]
    radii=[minimum_circle(poly)[1] for _,poly in hist]
    ax.semilogy(np.arange(1,len(hist)+1),radii,'o-',label=tr('可行区域包含圆半径','Region enclosing-circle radius'))
    ax.axhline(20,color='C2',ls='--',label=tr('认证清除界 20 m','Certified-clear bound 20 m'))
    gate=50 if problem==3 else 35
    ax.axhline(gate,color='C1',ls=':',label=tr(f'试探门 {gate} m',f'Trial gate {gate} m'))
    ax.set(xlabel=tr('公开反馈后的区域更新序号','Region update after public feedback'),ylabel=tr('包含圆半径 / m','Enclosing radius / m'),title=tr('定位精度演进','Localization precision'))
    ax.grid(alpha=.2); ax.legend(fontsize=8)
    fig.suptitle(tr(f'Q{problem}：发现 → 定位 → 清除闭环（本地 mock，seed={seed}）',f'Q{problem}: discovery → localization → clearance (local mock, seed={seed})'))
    save(fig,f'q{problem}_closed_loop',tr(f'来源：bounded_http.mock_world + simulator.Protocol + bounded_candidates 当前策略；全清 {len(world.cleared)}/{len(world.sources)}\n真值只用于事后标注，未提供给策略；区域取自策略公开反馈状态。',
        f'Source: bounded_http.mock_world + simulator.Protocol + current bounded_candidates; cleared {len(world.cleared)}/{len(world.sources)}\nTruth used only in post-run graphics; regions recorded from policy feedback states.'))

def practice():
    text=(ROOT.parent/'Q34-SUMMARY.md').read_text()
    groups={3:[],4:[]}; problem=None
    for line in text.splitlines():
        if line.startswith('### Q3'): problem=3
        elif line.startswith('### Q4'): problem=4
        elif line.startswith('## 2.'): break
        if problem and line.startswith('| '):
            cols=[x.strip() for x in line.strip('|').split('|')]
            if len(cols)>4 and cols[1].isdigit() and cols[2].isdigit():
                groups[problem].append((cols[0],int(cols[1]),int(cols[2]),float(cols[4])))
    assert [len(groups[p]) for p in (3,4)]==[5,6]
    assert [sum(r[1] for r in groups[p]) for p in (3,4)]==[63,80]
    fig,axs=plt.subplots(1,2,figsize=(12,6))
    for ax,p,ref in zip(axs,(3,4),(341,658)):
        rows=groups[p]; vals=[r[3] for r in rows]; weighted=np.average(vals,weights=[r[1] for r in rows])
        ax.boxplot([vals],positions=[1],widths=.3,showfliers=False)
        for x,r,label_y in zip(np.linspace(.91,1.09,len(rows)),sorted(rows,key=lambda r:r[3]),np.linspace(min(vals)-15,max(vals)+15,len(rows))):
            contaminated=r[0].startswith('X55H')
            ax.scatter(x,r[3],color='C1' if contaminated else 'C0',marker='D' if contaminated else 'o',zorder=4)
            ax.annotate(r[0][:4]+(' *' if contaminated else ''),(x,r[3]),xytext=(1.35,label_y),fontsize=8,va='center',arrowprops={'arrowstyle':'-', 'color':'.5', 'lw':.6})
        ax.axhline(weighted,color='C2',label=tr(f'源加权均值 ≈ {weighted:.1f}',f'Source-weighted mean ≈ {weighted:.1f}'))
        ax.axhline(ref,color='C3',ls='--',label=tr(f'参考截图 ≈ {ref}',f'Reference screenshot ≈ {ref}'))
        ax.set(xlim=(.6,1.7),ylim=(140,710),xticks=[1],xticklabels=['practice'],ylabel=tr('逐局总时间 / 源数（s/源）','Run total time / source count (s/source)'),title=f'Q{p}: {len(rows)} '+tr('局','runs')+f' / {sum(r[1] for r in rows)} '+tr('源','sources'))
        ax.grid(axis='y',alpha=.2); ax.legend(loc='upper left')
        print(f'Practice Q{p} weighted mean from rounded table: {weighted:.6f}',flush=True)
    fig.suptitle(tr('官方模拟器 practice：逐局每源用时与参考成绩','Official simulator practice: run-level time per source'))
    save(fig,'q34_practice_scores',tr('来源：Q34-SUMMARY.md 中权威 practice_statistics_tasks 统计库转录表（已取整至 0.1 s/源），未读取原库。\n箱线统计单位为局，并非单源耗时；* X55H 计时受前次运行影响。早期 CNDW 未全清 10/15，不属定型策略；参考非配对实验。',
        'Source: Q34-SUMMARY.md transcription of authoritative practice_statistics_tasks (rounded to 0.1 s/source); raw DB not read.\nBoxplots are runs, not individual sources. * X55H timing contaminated; early CNDW cleared 10/15, excluded as exploratory. Reference is unpaired.'))

def tradeoff():
    text=(ROOT/'CLEAR_GATE_TRADEOFF.md').read_text().split('## 扩展扫参（每设置1050局）')[1].split('\n## ')[0]
    rows={3:[],4:[]}
    for line in text.splitlines():
        if line.startswith('|Q'):
            c=line.strip('|').split('|'); rows[int(c[0][1])].append((float(c[1]),int(c[3]),float(c[4])))
    fig,axs=plt.subplots(1,2,figsize=(13,6))
    for ax,p,gate in zip(axs,(3,4),(50,35)):
        a=np.array(sorted(rows[p])); assert len(a)==6
        right=ax.twinx()
        ax.plot(a[:,0],a[:,1],'o-',color='C0',label=tr('清除失手总数','Failed clear attempts'))
        right.plot(a[:,0],a[:,2],'s--',color='C1',label=tr('源加权每源时间','Source-weighted time'))
        ax.axvline(gate,color='C2',ls=':',lw=2,label=tr(f'选定 {gate} m',f'Selected {gate} m'))
        selected=a[a[:,0]==gate][0]
        ax.scatter([gate],[selected[1]],s=130,facecolors='none',edgecolors='C2',zorder=5)
        ax.set(xlabel='trial_radius / m',ylabel=tr('清除失手 / 次（1050 局合计）','Failed clears / count (1050 runs)'),title=f'Q{p}')
        right.set_ylabel(tr('源加权时间 / (s/源)','Source-weighted time / (s/source)'),color='C1')
        right.ticklabel_format(axis='y',useOffset=False)
        ax.tick_params(axis='y',colors='C0'); right.tick_params(axis='y',colors='C1')
        ax.grid(alpha=.2); ax.set_ylim(-30,a[:,1].max()*1.25); right.margins(y=.18)
        handles,labels=ax.get_legend_handles_labels(); h,l=right.get_legend_handles_labels()
        ax.legend(handles+h,labels+l,loc='upper center',fontsize=8)
    fig.suptitle(tr('清除门限：时间与失手权衡（扩展扫参，本地 mock）','Clear-gate tradeoff: refinement sweep (local mock)'))
    save(fig,'q34_clear_gate_tradeoff',tr('来源：CLEAR_GATE_TRADEOFF.md 扩展扫参表；每设置 1050 局，共用种子 202610000—202611049，全部全清。\n左右轴分别表示失手和每源时间；连线仅引导阅读，不能解释为未测门限结果。',
        'Source: CLEAR_GATE_TRADEOFF.md refinement table; 1050 runs per gate, paired seeds 202610000–202611049; all cleared.\nSeparate axes for failures and time; lines connect measured settings only.'))

def composition(runs):
    fig,ax=plt.subplots(figsize=(9,6))
    bottoms=np.zeros(2)
    values=[]
    for world,trace,_ in runs:
        failures=sum(r['path']=='/clear' and r['response']['clear_result']!='success' for r in trace)
        parts=np.array([world.moves/5,world.measures*5,world.switches,len(world.cleared)*5,failures*3])
        assert abs(parts.sum()-world.time_us/1e6)<.001
        values.append(parts/len(world.sources))
    values=np.array(values)
    labels=[tr('移动','Movement'),tr('测量','Measurement'),tr('切频','Channel switch'),tr('成功清除','Successful clear'),tr('清除失手','Failed clear')]
    for i,label in enumerate(labels):
        ax.bar(['Q3','Q4'],values[:,i],bottom=bottoms,label=label,width=.5)
        bottoms+=values[:,i]
    for i,total in enumerate(bottoms): ax.text(i,total+5,f'{total:.1f}',ha='center')
    ax.set(ylabel=tr('源加权时间 / (s/源)','Source-weighted time / (s/source)'),title=tr('闭环示例局：虚拟时间构成（本地 mock）','Example runs: virtual-time composition (local mock)'))
    ax.set_ylim(0,bottoms.max()*1.23); ax.grid(axis='y',alpha=.2); ax.legend(ncol=3,loc='upper left')
    save(fig,'q34_mock_time_components',tr('来源：两张闭环轨迹图对应实跑的 simulator.World 动作账本；移动按 5 m/s，测量 5 s，切频 1 s，清除成功/失手 5/3 s。\n仅为本地 mock 的动作分解，不是官方 practice 时间构成。','Source: simulator.World action ledgers for the two trajectory runs; speed 5 m/s, measurement 5 s, switch 1 s, clear success/failure 5/3 s.\nLocal mock decomposition only; not official practice timing.'))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed',type=int,default=11)
    parser.add_argument('--font-check-only',action='store_true')
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    style()
    if args.font_check_only: return
    for p in (3,4): coverage(p)
    runs=[]
    for p in (3,4):
        data=simulate(p,args.seed); runs.append(data); trajectory(p,args.seed,data)
    practice(); tradeoff(); composition(runs)

if __name__=='__main__': main()
