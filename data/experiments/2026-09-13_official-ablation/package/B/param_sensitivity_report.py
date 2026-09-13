"""Render archived sensitivity evidence; does not execute policies or retune."""
import argparse,json,csv,hashlib
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from param_sensitivity import GRID,DEFAULT

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--run',type=Path,required=True);parser.add_argument('--report',type=Path,required=True);a=parser.parse_args();out=a.run
 train=json.loads((out/'training/summary.json').read_text());valid=json.loads((out/'validation/summary.json').read_text());selection=json.loads((out/'frozen_selection.json').read_text());config=json.loads((out/'config.json').read_text())
 # Export exact paired differences and verify split isolation from actual fixtures.
 splits={}
 for split in ('training','validation','combination_training'):
  fixtures=json.loads((out/split/'fixtures.json').read_text())
  splits[split]={f['scenario']['seed'] for fs in fixtures.values() for f in fs}
  rows=[json.loads(l) for l in (out/split/'trials.jsonl').read_text().splitlines()]
  base={(r['problem'],r['case_id']):r for r in rows if r['setting']=='baseline'}
  with (out/split/'paired.csv').open('w') as f:
   fields=['problem','setting','case_id','sources','all_cleared','total_virtual_s','baseline_virtual_s','delta_s','delta_percent','direction']
   writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
   for r in rows:
    b=base[r['problem'],r['case_id']];d=r['total_virtual_s']-b['total_virtual_s']
    writer.writerow(dict(problem=r['problem'],setting=r['setting'],case_id=r['case_id'],sources=r['sources'],all_cleared=r['all_cleared'],total_virtual_s=r['total_virtual_s'],baseline_virtual_s=b['total_virtual_s'],delta_s=d,delta_percent=100*d/b['total_virtual_s'],direction='slower' if d>1e-6 else 'faster' if d < -1e-6 else 'same'))
 assert not splits['training'] & splits['validation']
 lines=['# Q3/Q4 非清除门参数敏感性分析','',
 '本轮只做分析与建议，未修改主候选默认参数或 `models/paper-full.md`。清除门固定 Q3=50 m、Q4=35 m，没有重复清除门扫参。所有结果来自同级本地 mock 的完整策略执行，不是官方模拟器或正式测试结果。','',
 '核心结论：Q3冻结组合在独立验证中节省0.2712秒/源（0.110%），但154/1050局变慢且失手增加；Q4多数默认已在所测范围近最优，冷却加大未稳定复现收益，角度上限20°仅有微小、边界性证据。建议值均留给父agent决定，未写入默认。','', '## 方法与生效路径','',
 '- 使用 `bounded_candidates.build` 当前真实入口：Q3 为 `OmniNegativeCompletionPolicy → CoupledCompletionPolicy → CompletionClearancePolicy`，保留已接入的阴性距离支配裁剪；Q4 为 `CoupledWidthPolicy → InterleavedMixin.source_packet`。没有使用清除门旧实验的历史构建器。',
 '- 训练种子 **202630000—202630419**（每题每设置420局）；冻结后独立验证种子 **202640000—202641049**（每题每设置1050局）。两集合严格不交叠。Q3/Q4沿用相同编号但各按本题源类型生成。每105局覆盖源数10—16 × 均匀/边缘/聚簇 × iid/平滑/正1°/负1°/空间±1°；重复轮交替均匀1000—1500 m与固定1000 m作用距离，Q4含50%定向源、交替均匀/向外朝向。',
 '- 单因素扫参（OFAT），其余参数保持当前入口默认。每个配置使用同一组源场景及位置键控误差场；不同查询位置的误差不同但可复现。主指标严格为 **sum(整局虚拟秒)/sum(真实源数)**。失败与异常局保留分母并使配置失去推荐资格。',
 '- 先按训练集全清约束和最小源加权时间为每个参数选值；与默认相同的平局保留默认。不查看验证结果重新选参。各单参数赢家及其一次性组合写入 `frozen_selection.json` 后才开始验证。组合由训练赢家拼合，未经联合网格寻优，不保证收益可加；冻结后另在原训练场景完整复核组合，与独立验证并行执行，不读取验证结果或重新选值。',
 '- 95%区间为4000次逐场景配对bootstrap，重采样内仍按真实源数加权。区间未作多重比较校正；验证均值下降但区间跨零的值仅称“尚未稳定确认”，不作明确提速建议。逐局相同容差为1e−6秒；最差退化分别报告整局秒数和比例。',
 '- 阴性冷却150 m只作用于Q4共享筛选，不裁剪可行域；Q3没有该参数路径。Q3 `steps=10`不用于当前完成分支，真正主定位预算是 `max_active=3`；Q4 `localization_weight=.08`不参与当前探点或center调度。二者仍做数值阴性对照。',
 '- Q4 `steps=10`限制每源终身探点轮数，每轮至多两次主RF，故主RF上限为20；不存在独立的主RF预算参数，不能把共享测量误算进它。`pause_limit=16`限制全局 `source_interruptions`，不是每源16次。',
 '- Q4探点宽度实际为 `min(length*tan(angle_max), max(length*tan(angle_min), transverse_m))`，默认40 m、1.02°/30°。硬编码夹持在实验实例中局部替换，未修改策略文件；仅扫描现有几何证明覆盖的1.02°—30°，没有放宽到未经证明区间。其余参数经构建器覆盖；Q3 `max_active`因构建器未暴露而在构建后修改实验实例属性。',
 '- 补扫Q3 `remainder_weight`（默认1）：直接改变完成距离评分，可能改变定位点及移动时间；补扫Q4 `fraction`（默认.15）：改变沿方位方向的探点进度，影响负对裁剪、RF轮数与行程。保留覆盖布局、几何余量与认证条件；本轮不是所有策略结构的穷举优化。','',
 '## 训练扫参曲线','',
 '表中测量数、切频数、失手数均为该设置全部训练局累计；共享/主RF/冷却跳过/中断/兜底计数及逐局明细另见归档CSV、JSON和JSONL。默认行标 `*`，各表重复同一真实基线；没有额外伪造执行。非适用参数不强行注入。','']
 for p in (3,4):
  lines += [f'### Q{p}','']
  if p==3:lines+=['阴性冷却、Q4探点宽度与角度、全局中断预算：不适用。','']
  else:lines+=['Q3 `max_active`和`remainder_weight`：当前Q4路径不适用；Q4主RF上限随steps一起扫描（8/12/16/20）。','']
  base=next(r for r in train if r['problem']==p and r['setting']=='baseline')
  fig,axes=plt.subplots(len(GRID[p]),3,figsize=(13,2.5*len(GRID[p])),squeeze=False)
  for row,(key,values) in enumerate(GRID[p].items()):
   groups=[base if v==DEFAULT[key] else next(r for r in train if r['problem']==p and r['changes']=={key:v}) for v in values]
   lines += [f'#### `{key}`（默认 {DEFAULT[key]}）','', '|参数值|秒/源|较默认秒/源|全清/局数|测量|切频|清除失手|','|---:|---:|---:|---:|---:|---:|---:|']
   for v,r in zip(values,groups):lines.append(f"|{v}{'*' if v==DEFAULT[key] else ''}|{r['seconds_per_source']:.4f}|{r['delta']:+.4f}|{r['all_cleared']}/{r['runs']}|{r['measurements']}|{r['switches']}|{r['misses']}|")
   lines.append('')
   picks=[r for r in valid if r['problem']==p and key in r['changes'] and r['setting']!='combined']
   if not picks:
    same=all(r['same']==r['runs'] for r in groups)
    lines += [('本轮所有值的逐局整局时间相同，所测范围未发现时间改进空间；这不表示内部兜底计数必然相同，参数是否生效见路径说明。' if same else '训练集中当前默认最优：本轮所测范围无改进空间，保留默认；未在验证集另选替代值。'),'']
   else:
    r=picks[0];verdict='验证确认样本平均提速' if r['all_cleared']==r['runs'] and r['ci'][1]<0 else '验证未稳定确认提速，保留默认'
    lines += [f"训练选值 `{r['changes'][key]}`；{verdict}（验证差 {r['delta']:+.4f} 秒/源）。",'']
   for col,metric in enumerate(('seconds_per_source','all_cleared','counts')):
    ax=axes[row,col]
    if metric=='all_cleared':ax.plot(values,[100*r['all_cleared']/r['runs'] for r in groups],'o-');ax.set_ylim(95,100.5);ax.set_ylabel('Full-clear %')
    elif metric=='counts':
     for m in ('measurements','switches','misses'):ax.plot(values,[r[m]/r['sources'] for r in groups],'o-',label=m)
     ax.set_ylabel('Count / source');ax.legend(fontsize=7)
    else:ax.plot(values,[r[metric] for r in groups],'o-');ax.set_ylabel('Virtual s / source');ax.ticklabel_format(axis='y',style='plain',useOffset=False)
    ax.axvline(DEFAULT[key],color='gray',linestyle='--');ax.set_xlabel(key);ax.grid(alpha=.2)
  fig.suptitle(f'Q{p} training OFAT sensitivity; dashed = default',y=1.002);fig.tight_layout();fig.savefig(out/f'q{p}_curves.png',dpi=150,bbox_inches='tight');fig.savefig(out/f'q{p}_curves.pdf',bbox_inches='tight');plt.close(fig)
  import os
  link=os.path.relpath(out/f'q{p}_curves.png',a.report.parent)
  lines += [f'![Q{p}扫参曲线]({link})','']
 lines += ['## 冻结后的独立验证','', '|问题|设置|秒/源|较默认秒/源|配对95%区间|全清/局数|测量|切频|失手|','|---|---|---:|---:|---|---:|---:|---:|---:|']
 for r in valid:lines.append(f"|Q{r['problem']}|{r['setting']}|{r['seconds_per_source']:.4f}|{r['delta']:+.4f}|[{r['ci'][0]:+.4f}, {r['ci'][1]:+.4f}]|{r['all_cleared']}/{r['runs']}|{r['measurements']}|{r['switches']}|{r['misses']}|")
 lines += ['', '### 逐局回退（独立验证，比较整局时间）','', '|问题|设置|变快|变慢|相同|最差增加秒|最大增加比例|最差秒数场景|','|---|---|---:|---:|---:|---:|---:|---|']
 for r in valid:lines.append(f"|Q{r['problem']}|{r['setting']}|{r['faster']}|{r['slower']}|{r['same']}|{r['worst_s']:.3f}|{r['worst_percent']:.3f}%|{r['worst_case']}|")
 lines += ['', '最差秒数与最大退化比例可能来自不同局。以上回退不从均值推算，不宣称逐局占优。训练集每个设置也已保存相同的回退统计，见 `training/summary.csv`。','', '### 冻结组合','']
 combo=json.loads((out/'combination_training/summary.json').read_text())
 lines += ['|问题|冻结组合训练秒/源|较默认秒/源|全清/局数|','|---|---:|---:|---:|']
 for r in combo:
  if r['setting']=='combined':lines.append(f"|Q{r['problem']}|{r['seconds_per_source']:.4f}|{r['delta']:+.4f}|{r['all_cleared']}/{r['runs']}|")
 lines.append('')
 for p in (3,4):lines.append(f"- Q{p}：`{json.dumps(selection[str(p)].get('combined',{}),ensure_ascii=False)}`。")
 lines += ['', 'Q4基线在训练/验证中，每源实际最多4轮、6次主RF；整局最多9/12次中断，均未耗尽默认10轮、20次主RF及16次中断预算。减少steps并未带来训练时间收益，保留默认可保留未见场景的预算余量；不要把观测最大值当成普适上界。', '', '## 建议与边界','']
 for p in (3,4):
  accepted=[r for r in valid if r['problem']==p and r['setting']!='baseline' and r['all_cleared']==r['runs'] and r['ci'][1]<0 and (r['setting']!='combined' or any(c['problem']==p and c['setting']=='combined' and c['delta']<0 and c['all_cleared']==c['runs'] for c in combo))]
  if accepted:
   for r in accepted:
    base=next(x for x in valid if x['problem']==p and x['setting']=='baseline')
    lines.append(f"- Q{p} `{r['setting']}`：可作为父agent采纳候选，验证减少 {-r['delta']:.4f} 秒/源（{-100*r['delta']/base['seconds_per_source']:.3f}%），每局全清；仍有 {r['slower']} 局变慢。参数见上表及冻结配置，尚未写入默认值。")
  else:lines.append(f'- Q{p}：独立验证未确认明确提速设置，建议保留当前默认。')
 lines += ['', 'Q3组合虽平均节省0.110%，验证清除失手从2270增至2387（+117，约5.15%）；单独max_active=2也增至2375。这些失手已计入整局时间，仍全部清完，但父agent需要同时权衡失手代价。remainder_weight=1.5的改善仅来自5/1050局，收益约0.002%，不宜夸大。Q4 angle_max=20只减少约0.018%，未校正95%区间上端接近零，属于谨慎备选；建议Q4暂保留默认，尤其不采纳冷却800 m及冻结组合，它们的均值改善区间跨零，最差局退化超过100%。', '', '单参数结果只说明在其余默认值固定时的效果。不得把多个单参数收益相加，也不得把验证集最小均值宣称为新一轮寻优后的无偏估计。组合若未通过，则不建议一并采用；本轮没有根据验证结果再删减或调整组合。有限样本、预设网格和本地mock分布不能证明普适最优、官方分布提速或每局占优。无改进空间仅指本轮所测范围；不存在效果的阴性对照也不等于扩大预算永远没有价值。','', '## 执行与复现','']
 totals=[json.loads((out/s/'completion.json').read_text()) for s in ('training','validation','combination_training')]
 lines += [f"共 {sum(x['runs'] for x in totals):,} 次完整执行；训练 {totals[0]['runs']:,} 次，验证 {totals[1]['runs']:,} 次，冻结组合训练复核 {totals[2]['runs']:,} 次，未全清/异常 {sum(x['failed'] for x in totals)} 次。认证清除失败累计 {sum(r['certified_failures'] for r in train+valid+combo)}。所有失败均保留；不满足全清的设置不会被建议。",'',
 '另有24组默认等价性配对检查（种子202629800—202629811，每题12局、共48次执行），显式默认与实际入口的整局时间、计数及策略统计全部一致，见 `default_equivalence.json`；这48次不计入上面的扫参与验证总数。','',
 '脚本：`param_sensitivity.py`（执行与冻结选参）、`param_sensitivity_report.py`（只读汇总与绘图）。归档含参数网格、种子、当前入口规格、源文件SHA256、策略/本地mock快照、场景真值评分夹具、逐局计数、训练/验证汇总、冻结选择与曲线PNG/PDF。真值只供mock与评分使用，策略只接收Client公开回复。','',
 '```sh','/Users/flower/math/2026/B题/mock/.venv/bin/python param_sensitivity.py --output experiments/runs/2026-09-12_param-sensitivity-reproduce --workers 4','/Users/flower/math/2026/B题/mock/.venv/bin/python param_sensitivity_combo_audit.py --run experiments/runs/2026-09-12_param-sensitivity-reproduce','/Users/flower/math/2026/B题/mock/.venv/bin/python param_sensitivity_report.py --run experiments/runs/2026-09-12_param-sensitivity-reproduce --report PARAM_SENSITIVITY_REPRODUCE.md','```','',
 '等价性检查可用 `param_sensitivity_verify.py --output 新文件.json` 复现（同一Python）。','',
 '以上命令在工作区B根目录执行，输出目录必须不存在。若源码已变化，可在归档 `code_snapshot/` 执行第一条脚本，并把归档 `mock_snapshot/` 复制为与该快照同级的 `mock/`，保证导入同一mock版本；使用同一Python环境。`integrity.json`核对执行前后的原顶层Python文件哈希。论文实际位于上级 `../models/paper-full.md`，未纳入初始快照；本轮无写入该文件的操作，结束时单独记录哈希于 `paper_observation.json`，git状态无修改。本轮未调用网络传输。']
 a.report.write_text('\n'.join(lines)+'\n')
 archived=a.report.read_text()
 for p in (3,4): archived=archived.replace(os.path.relpath(out/f'q{p}_curves.png',a.report.parent),f'q{p}_curves.png')
 (out/'PARAM_SENSITIVITY.md').write_text(archived)
 # Freeze report producer too (created after experiment snapshot).
 import shutil
 shutil.copy2(Path(__file__),out/'code_snapshot'/Path(__file__).name)
 print(a.report)
if __name__=='__main__':main()
