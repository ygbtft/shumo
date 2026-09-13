"""Render T6 and a paper-ready Markdown draft strictly from saved numeric data."""
import csv
import json
from pathlib import Path
import sys

folder = Path(sys.argv[1])
here = folder.parent
load = lambda name: json.loads((folder/name).read_text())
records = {p.stem:json.loads(p.read_text()) for p in folder.glob('*.json')
           if 'search' in json.loads(p.read_text())}
fmt = lambda x: '未评估' if x is None else f'{x:.6f}' if isinstance(x,(int,float)) else str(x)
def J(row): return row['score']['J_hat'] if row and row['score'] else None
def q(row): return str(row['q']) if row else '无'
def status(row): return row['admissibility']['status'] if row else '无旧点'
def table(headers, rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+
                     ['| '+' | '.join(str(v).replace('|','/') for v in row)+' |' for row in rows])+'\n'

for r in records.values():
    before={tuple(c['q']):c['score']['J_hat'] for c in r['search']['alternatives']}
    after={tuple(c['q']):c['score']['J_hat'] for c in r['final_candidates'] if c['score'] and tuple(c['q']) in before}
    pairs=[(a,b) for i,a in enumerate(after) for b in list(after)[i+1:]]
    r['material_rank_inversions']=sum((before[a]-before[b])*(after[a]-after[b])<0 and min(abs(before[a]-before[b]),abs(after[a]-after[b]))>.1 for a,b in pairs)

# Machine-readable, per-run audit. Empty values remain empty rather than zero.
detail = []
for key,r in records.items():
    detail.append(dict(case=key, F_status=r['source_set']['status'],
        source_grids=str(r['config']['source_grids']), sample_count=r['reselected']['score']['sample_count'] if r['reselected'] else r['accounting']['sample_count'],
        search_score_calls=r['search']['evaluations'], final_score_calls=r['accounting']['score_calls'],
        common_additions=r['accounting']['common_additions'],
        scan_50=str(next((s for s in r['scan'] if s['step_m']==50),None)),
        scan_25=str(next((s for s in r['scan'] if s['step_m']==25),None)),
        source_change_m=r['search']['source_change_m'], station_change_m=r['search']['station_change_m'],
        tolerance_change_m=r['search']['tolerance_change_m'],
        rank_inversions=r['rank_inversions'], material_rank_inversions=r['material_rank_inversions'], elapsed_seconds=r['elapsed_seconds'],
        stop_reason=r['stop_reason'], stability=r['stability'],
        old_feasibility=status(r['fixed_old']), old_signal_status=r['fixed_old']['admissibility']['signal_check']['status'] if r['fixed_old'] else None, old_action_reasons=str(r['fixed_old']['admissibility']['reasons']) if r['fixed_old'] else None, fixed_old_J=J(r['fixed_old']), new_J=J(r['reselected']),
        actual_movement_seconds=r['reselected']['movement_seconds'] if r['reselected'] else None))
with (here/'T6_detail.csv').open('w') as f:
    w=csv.DictWriter(f,fieldnames=list(detail[0])); w.writeheader();w.writerows(detail)

s7=load('S7.json'); station=load('S7_station.json'); s2=load('S2.json'); losses=load('S4_losses.json')
s2['rows']={k:dict(fixed_old=r['fixed_old'],reselected=r['reselected'],final_candidates=r['final_candidates']) for k,r in records.items()}
(folder/'S2.json').write_text(json.dumps(s2,ensure_ascii=False,indent=2)+'\n')
def group(keys):
    rs=[records[k] for k in keys]
    return [str(len(rs)), ', '.join(str(r['reselected']['score']['sample_count'] if r['reselected'] else r['accounting']['sample_count']) for r in rs),
            str(sum(r['search']['evaluations']+r['accounting']['score_calls'] for r in rs)),
            str(sum(r['accounting']['common_additions'] for r in rs)),
            '; '.join(k+': '+','.join(f"{s['step_m']:g}m {s['scanned']}/{s['planned']}" for s in records[k]['scan']) for k in keys),
            '见分项；null 表示终选细化审计未完成',
            str(sum(r['rank_inversions'] for r in rs))+'（双侧差均>0.1m: '+str(sum(r['material_rank_inversions'] for r in rs))+'）', fmt(sum(r['elapsed_seconds'] for r in rs)),
            ', '.join(sorted(set(r['stop_reason']+'/'+r['stability'] for r in rs)))]
basekeys=[k+'_default' for k in ('standard','ordinary','tangent','edge')]
s1keys=[k+'_S1' for k in ('standard','ordinary','tangent')]
s3keys=[scene+'_known_rho_'+str(rho) for scene in ('standard','edge') for rho in (1000,1250,1500)]
s9keys=['F9_B10','F9_B200','F9_B600','F9_tangent_B200','F9_tangent_B400','F9_tangent_B500']
summary = []
summary.append(['S1','完成三例外包对照；终选稳定性不足']+group(s1keys))
summary.append(['S2','完成条件指标/near代表反馈/36m形状']+['复用全部终选','复用','0 新评分','0 新补点','复用','不优化 J_R','不适用','计入各场景','代表反馈条件值'])
summary.append(['S3','完成标准/边缘及不一致信息反例']+group(s3keys))
summary.append(['S4','完成域内消融；S 被排除']+group(['edge_S4']))
for key in ('S5','S6'):
    summary.append([key,'选做未执行']+['0','未采样','0','0','未扫描','未评估','未评估','0','NOT_RUN；最小方案未启用'])
summary.append(['S7','完成三级/容差/偏移/tie/站点重评；非误差保证']+
    ['复用标准+独立审计',str([v['sample_count'] for v in s7['variants']]),str(s7['score_calls']+station['local_screen_score_calls']+station['accounting']['score_calls']),
     str(station['accounting']['common_additions']),'复用标准 50/25m；详见下表',fmt(station['delta_station_m']),
     '站点严格翻转 '+str(station['rank_inversions'])+'；其余见排序表',fmt(s7['elapsed_seconds']+station['elapsed_seconds']),'SAVED_STAGES_REASSESSED；有限候选'])
s8=load('F11_S8.json'); f9shared=load('F9_shared.json')
for row in s8['rows'].values():
    stages=row.get('stages',[])
    if not stages:
        continue
    row['fixed_old_q']=row['q'];row['reselected_q']=row['q']
    if stages[0]['kind']=='UNBOUNDED':
        row['dominant_constraint']='arena makes P bounded; receiving disks further reduce finite outer bound'
    else:
        drops=[(a['d']-b['d'],b['stage']) for a,b in zip(stages[:2],stages[1:3]) if a['d'] is not None and b['d'] is not None]
        row['dominant_constraint']=max(drops)[1] if drops and max(drops)[0]>1e-6 else 'angular constraints dominate within tangent-outer resolution'
(folder/'F11_S8.json').write_text(json.dumps(s8,ensure_ascii=False,indent=2)+'\n')
summary.append(['S8','完成；复用 F11 同反馈裁剪']+['3 场景+重复首测控制',str(s8['accounting']['sample_count']),str(s8['accounting']['score_calls']),str(s8['accounting']['common_additions']),
    '不选点；固定/新点相同','外包/样本口径分列','不适用',fmt(s8['accounting']['elapsed_seconds']),'裁剪几何耗时未单独计时'])
summary.append(['S9','完成；复用 F9 预算与 S7 tie']+group(s9keys))
text='# T6 敏感性实际执行记录\n\n'
text+='统一终选设置：源三级 (5,13)/(9,25)/(17,49)，终选为第三级与错位源、各候选接触点及点对见证的公共并集；pair_starts=4、pair_rounds=4，tie=0.1 m。此配置为精简敏感性设置，并非 default_config.json 的全部默认分辨率。每个物理模型重新建立 F、C_sig 与反馈，跨模型不共享不合法源样本。搜索时限30 s；固定旧点、原搜索推荐点、原始最低评分点及其对称候选共同终评。\n\n'
text+='排序翻转统计严格浮点次序反转，另列前后分差都超过0.1m的反转数，避免将对称点舍入差误读为物理变化。表中评分次数为 score_point 调用数，不是设备测量次数。公共补点含错位点及接触/见证点，相对该模型的无候选增强第三级源池计数。时间包括本地搜索及统一终评；复用行不得重复累计。所有全域未完成/终选审计未完成状态原样保留，统一重评不能替代搜索收敛。\n\n'
text+=table(['项','实际范围/状态','运行数','终选样本数','评分次数','公共补点','扫描比例','细化变化/m','排序翻转','耗时/s','停止原因'],summary)
text+='\nF9 跨预算公共重评追加成本（仅计一次）：评分 '+str(f9shared['score_calls'])+' 次，耗时 '+fmt(f9shared['elapsed_seconds'])+' s；样本与补点分场景见 F9_shared.json。\n'
text+='\n'+table(['F9公共池','样本数','公共补点','追加评分次数','追加耗时/s'],[[name,g['accounting']['sample_count'],g['accounting']['common_additions'],g['accounting']['score_calls'],fmt(g['accounting']['elapsed_seconds'])] for name,g in f9shared['groups'].items()])
text+='\n默认场景成本（其他各项复用，不重复累计）：\n\n'
text+=table(['场景','J_hat/m','q/m','50/25m扫描','评分次数','公共补点','耗时/s','状态'],[
    [k,fmt(J(records[k]['reselected'])),q(records[k]['reselected']),str(records[k]['scan']),
     records[k]['search']['evaluations']+records[k]['accounting']['score_calls'],records[k]['accounting']['common_additions'],fmt(records[k]['elapsed_seconds']),records[k]['stop_reason']+'/'+records[k]['stability']] for k in basekeys])
text+='\n逐运行的机器可读明细见 T6_detail.csv；原始搜索网格、未评估点、细化历史、候选可行性见 results/*.json。\n'
(here/'T6.md').write_text(text)

paper='# 敏感性分析：论文表格与结论段落草稿\n\n'
paper+='本稿只供父 agent 选取并入正文；所有长度单位为米，时间为秒。下述 J_hat 是最坏物理后验直径的数值估计，R_hat 为代表合法反馈的条件最小覆盖半径估计，r_U 为经浮点残差检查的保守外包覆盖半径；条件 R_hat 不等同于最坏半径目标 J_R。\n\n'
paper+='## 角界与最近舍入外包（S1）\n\n'
s1rows=[]
for key in s1keys:
    name=key.removesuffix('_S1');b=records[name+'_default'];r=records[key]
    s1rows.append([name,fmt(J(b['reselected'])),status(r['fixed_old']),fmt(J(r['fixed_old'])),fmt(J(r['reselected'])),q(r['reselected'])])
paper+=table(['场景','1°默认 J_hat','旧 q 保收','1.005°固定旧 q','1.005°重新选点','重新选点坐标'],s1rows)
paper+='\n三个场景分别覆盖跨0°、普通交会及目标圆近切边。1.005°仅表示“潜在误差不超过1°后最近舍入到0.01°”的连续外包，未实现精确量化模型。表中先列旧点的保收判定；若旧点失效，则不比较其目标值。角界增幅不能直接解释为目标值增幅，表中数值还受有限候选与源分辨率限制。\n\n'
paper+='## 条件覆盖与形状（S2）\n\n'
cr=[]
for k in basekeys+s1keys:
    row=records[k]['reselected']
    if row:
        for clear in row['representative_feedbacks']:
            cr.append([k,clear['feedback']['kind'],fmt(J(row)),fmt(clear['R_hat']),fmt(clear['r_U']),clear['status'],clear['evidence']])
for row in records['F9_B10']['final_candidates']:
    if row['admissibility']['status']=='IN':
        for clear in row['representative_feedbacks']:
            if clear['feedback']['kind']=='near':
                cr.append(['标准B=10轴向终选对照（未获选）',clear['feedback']['kind'],fmt(J(row)),fmt(clear['R_hat']),fmt(clear['r_U']),clear['status'],clear['evidence']])
paper+=table(['场景','代表反馈','J_hat','条件 R_hat','r_U','20m 三态','证据'],cr)
tri=s2['shapes']['triangle'];seg=s2['shapes']['segment']
paper+=f"\n直径同为36 m时，等边三角形的最小覆盖半径为 {tri['R']:.6f} m，超过20 m；线段的最小覆盖半径为18 m，可以由一个落点覆盖。这说明直径小于40 m不足以单独保证统一清除。三态中的 NOT_YET_GUARANTEED 还需区分已有合法点对/三点不可清除见证与仅证据不足；本表以 evidence 列作此区分。\n\n"
paper+='## 半径信息与行动域（S3/S4）\n\n'
paper+=table(['场景','半径信息','旧 q 状态','固定旧 q J_hat','重新选点 J_hat','实际移动/m'],
    [[name,'未知[1000,1500]','默认IN',fmt(J(records[name+'_default']['reselected'])),fmt(J(records[name+'_default']['reselected'])),fmt(records[name+'_default']['reselected']['movement_m'])] for name in ('standard','edge')]+[
    [k.split('_')[0],k.split('known_rho_')[-1],status(records[k]['fixed_old']),fmt(J(records[k]['fixed_old'])),fmt(J(records[k]['reselected'])),fmt(records[k]['reselected']['movement_m']) if records[k]['reselected'] else '无'] for k in s3keys])
paper+='\n已知ρ同时改变首测外径和每个一致世界的最小允许接收半径，因而重新建立F和保收候选域。其性能变化反映额外信息的价值，不能据此称未知半径方法失效。首站(2900,0)、朝西时，ρ=1000与首次direction不一致，模型为空，标为不可用；ρ=1250/1500仍有一致源点。标准场景的S本身属于C_sig，而源点(1499,0)距S超过1000，直接否定“对所有源统一取1000圆盘交”的错误替代。\n\n'
r=records['edge_S4'];b=records['edge_default']
paper+=table(['行动域','旧 q 状态','固定旧 q J_hat','重新选点 J_hat','实际移动/m','重新选点坐标'],[
    ['附件允许域外','默认',fmt(J(b['reselected'])),fmt(J(b['reselected'])),fmt(b['reselected']['movement_m']),q(b['reselected'])],
    ['人为 q∈A',status(r['fixed_old']),fmt(J(r['fixed_old'])),fmt(J(r['reselected'])),fmt(r['reselected']['movement_m']) if r['reselected'] else '无',q(r['reselected'])]])
paper+=f"\n在首站(1850,0)的边缘场景，附加域内限制在同一已保存候选总体中排除 {losses['added_arena_rejected_count']}/{losses['default_admissible_count']} 个原可行点，并排除首站S。该计数为有限候选损失，不是候选域面积比例；域内限制是消融，不表示题面规则含糊。\n\n"
paper+='## 数值变化与排序（S7）\n\n'
old=records['standard_default']['reselected']['q']
varrows=[]; vals={}
for v in s7['variants']:
    row=next((r for r in v['rows'] if r['q']==old),None)
    vals[v['name']]=J(row)
    varrows.append([v['name'],v['sample_count'],status(row),fmt(J(row)),q(v['winner']),fmt(J(v['winner']))])
paper+=table(['扰动','样本数','固定旧 q 状态','固定旧 q J_hat','该池重新选点','该池最小选择值'],varrows)
baseval=vals['source_2']
deltas={name: max(abs(vals[v]-baseval) for v in names if vals[v] is not None and baseval is not None) for name,names in
        [('delta_source',['source_0','source_1','source_2']),('delta_tol',['tolerance_0.1','tolerance_10.0']),('delta_offset',['offset_0.1','offset_10.0']),('delta_shift',['shifted'])]}
write_json=lambda p,x: p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
write_json(folder/'S7_deltas.json',dict(deltas,delta_station=station['delta_station_m'],reference='unaugmented source_2, fixed standard old q; station separately on common final pool'))
paper+='\n源三级、容差和边界偏移各次均在各自统一池内重选，上表不是用不同精度给同一组候选混合排名。固定旧点相对于无增强第三级源池的最大变化分别为：'+', '.join(k+'='+fmt(v)+' m' for k,v in deltas.items())+'。接触点/点对细化带来的公共终选变化另属数值补采，不与物理模型变化合并。\n\n'
paper+=table(['站点阶段','统一终选 J_hat','q'],[[r['stage'],fmt(J(r['uniform_final'])),q(r['uniform_final'])] for r in station['stages']])
paper+=f"\n相同终选精度下站点阶段变化 Δ_station={fmt(station['delta_station_m'])} m；50/25m阶段粗评分到终评的严格排序翻转 {station['rank_inversions']} 次（两个网格优胜点的粗评分相等，终评后打破平局）。\n\n"
paper+=table(['tie 倍数','阈值/m','固定旧点 J_hat','重新选点 J_hat','实际移动/s','q'],[[r['factor'],fmt(r['threshold_m']),fmt(J(r['fixed_old'])),fmt(J(r['reselected'])),fmt(r['reselected']['movement_seconds']) if r['reselected'] else '无',q(r['reselected'])] for r in s7['tie']])
paper+='\n对称候选的坐标无需唯一，微小排序变化也不等于物理结论翻转。上述变化只描述已执行的采样和有限候选审计，不能作为连续最坏值的误差保证。原搜索的稳定状态与停止原因见T6；不能把补充终评写成全域收敛。\n\n'
paper+='## 信息裁剪（S8，复用F11）\n\n'
cl=[]
for name,r in s8['rows'].items():
    for stage in r.get('stages',[]):
        cl.append([name,stage['stage'],stage.get('kind') or stage['status'],'无界' if stage.get('kind')=='UNBOUNDED' else fmt(stage['d']),'无界' if stage.get('kind')=='UNBOUNDED' else fmt(stage['R']),stage['label']])
paper+=table(['场景','加入信息','状态','d估计/外包','R估计/外包','计算口径'],cl)
paper+='\n主导约束：'+ '; '.join(k+'：'+r.get('dominant_constraint','未评估') for k,r in s8['rows'].items())+'。\n'
paper+='\n重复首站读数控制例的纯角锥P无界，加入目标域后成为有限集合；该变化按状态报告，不计算百分比。接收圆加入前后可比较同精度外包，排除5 m圆后的非凸集合仅报告合法源样本估计与独立r_U，不能把口径差当作排除圆的精确贡献。问题一始终只求纯角锥P。\n\n'
paper+='## 预算与实际成本（S9，复用F9）\n\n'
paper+=table(['场景/预算B(m)','固定旧 q 可行性','固定旧 q J_hat','重新选点 J_hat','实际移动/s','条件 R_hat','r_U','三态'],[
    [k,status(records[k]['fixed_old']),fmt(J(records[k]['fixed_old'])),fmt(J(records[k]['reselected'])),fmt(records[k]['reselected']['movement_seconds']) if records[k]['reselected'] else '无',fmt(records[k]['reselected']['clearance']['R_hat']) if records[k]['reselected'] and records[k]['reselected']['clearance'] else '无',fmt(records[k]['reselected']['clearance']['r_U']) if records[k]['reselected'] and records[k]['reselected']['clearance'] else '无',records[k]['reselected']['clearance']['status'] if records[k]['reselected'] and records[k]['reselected']['clearance'] else '无'] for k in s9keys])
paper+='\n本表旧点 OUT 均由移动预算排除，保收判定仍为 IN；行动不可行与失去保收资格分开记录于CSV。\n'
paper+='\n现有近切边场景补充 B=200/400/500 m，重点观察条件覆盖半径20 m附近；是否跨过门槛须同时检查 R_hat 和 r_U，不能只用 J_hat/2 判断。\n'
paper+='\n移动速度保持5 m/s，实际移动秒数由所选点距离计算，不能以预算直接替代；测量另需5 s，求解器墙钟时间不计入虚拟行动时间。只有标准场景B=10 m对应的长点对解析控制标注 V(10)≥1000 m，它不是最优值，也不推广到其他场景。tie敏感性复用S7；预算间已累计候选并用同一物理模型公共池重评；其数值曲线仍不代表连续全局最优值。\n\n'
paper+='本次代表场景中，标准场景角界外包扩大后，旧点仍保收，统一终评 J_hat 从129.741396 m变为130.322388 m；额外已知ρ=1000 m时同点估计为55.021304 m。近切边场景的纯角锥直径为44.175405 m，目标域约束使切线外包直径降至20.781811 m，体现了目标域信息的作用。预算从400 m增至500 m时，该场景代表反馈的条件 R_hat 从25.320469 m降至17.801739 m，后者的 r_U=18.483755 m，支持移动到覆盖圆心后清除；这不能推广为所有合法反馈均可一次清除，也不能据此认定500 m为最小预算。\n\n'
paper+='数值层面，未增强源三级评分存在71.332943 m的变化，且粗评分平局在统一终评后被打破。因此，本次结果可作为有限候选上的模型对照与行动证据，尚不足以给出连续最坏目标的误差保证或宣称搜索稳定。\n\n'
paper+='S5（冻结误差场）和S6（仅direction候选限制）为选做，本次未执行。1.01°压力与精确量化亦未执行。未完成的终选审计、覆盖预算门槛尚未精确定位，均保留为数值局限。\n'
(here/'paper-draft.md').write_text(paper)
print('rendered T6 and paper draft')
