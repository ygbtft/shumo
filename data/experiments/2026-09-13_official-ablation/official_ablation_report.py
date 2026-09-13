"""Render this archived batch; its narrative is pinned to the original run log."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

NAMES={'full':'Full','no_share':'No shared sensing','scan_then_service':'Scan then service',
       'no_negative':'No negative cuts','online_nearest':'Nearest task','nearest_sensing':'Nearest sensing'}
NARRATIVE_RUNS_SHA256='60613be67e6f5f13422d5902ea01b440393439e7666d4fba2dcdc7a0e20b0b90'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);args=parser.parse_args();out=args.output
    assert hashlib.sha256((out/'runs.jsonl').read_bytes()).hexdigest()==NARRATIVE_RUNS_SHA256, 'Reassess narrative for a different batch'
    data=json.loads((out/'analysis.json').read_text());audit=json.loads((out/'audit.json').read_text())
    assert audit['validation_runs']==160 and not audit['partial']
    summary=data['summary'];comparisons=data['comparisons'];adjusted=data['adjusted']
    runs=[json.loads(l) for l in (out/'runs.jsonl').read_text().splitlines()]
    runs=[r for r in runs if r['phase']=='validation']
    mechanism=[]
    for s in summary:
        group=[r for r in runs if r['problem']==s['problem'] and r['variant']==s['variant']]
        row=dict(problem=s['problem'],variant=s['variant'],runs=len(group))
        for key in ('shared_known_measurements','ablation_disabled_negative_calls','omni_negative_cuts',
                    'bracket_pair_cuts','bracket_cut_inconsistencies','ablation_scoring_calls','active_measurements','active_no_signal',
                    'early_optical_trials','early_optical_success','bracket_optical_trials','bracket_optical_success'):
            row[key]=sum(r['robot']['policy'].get(key,0) for r in group)
        row['negative_pair_branch_entries']=row['bracket_pair_cuts']+row['bracket_cut_inconsistencies']
        if s['variant'].startswith('no_share__'):assert row['shared_known_measurements']==0
        if s['problem']==3 and s['variant'].startswith('no_negative__'):assert row['omni_negative_cuts']==0
        if s['problem']==4 and s['variant'].startswith('no_negative__'):
            assert row['bracket_pair_cuts']==row['ablation_disabled_negative_calls']
        mechanism.append(row)
    with (out/'mechanism_checks.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(mechanism[0]));w.writeheader();w.writerows(mechanism)
    with (out/'trials.csv').open(encoding='utf-8-sig') as f:trials=[r for r in csv.DictReader(f) if r['phase']=='validation']
    figures=out/'figures';figures.mkdir(exist_ok=True)
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,2,figsize=(14,6),layout='constrained')
    for p,ax in zip((3,4),axes):
        group=[r for r in summary if r['problem']==p]
        for i,r in enumerate(group):
            values=[float(t['seconds_per_source']) for t in trials if int(t['problem'])==p and t['variant']==r['variant']]
            ax.scatter(values,i+np.linspace(-.12,.12,len(values)),s=17,color='#9bb7ca',alpha=.8)
            ax.errorbar(r['seconds_per_source'],i,
                        xerr=[[r['seconds_per_source']-r['ci_low']],[r['ci_high']-r['seconds_per_source']]],
                        fmt='o',color='#173f5f',capsize=3)
        ax.set_yticks(range(len(group)),[NAMES[r['variant'].split('__')[0]]+f" ({r['gate_m']:g} m)" for r in group])
        ax.invert_yaxis();ax.set_xlabel('Official virtual seconds / source');ax.set_title(f'Q{p}: 10 independent official cases per setting')
        ax.grid(axis='x',alpha=.2)
    fig.suptitle('Dots: individual cases; dark marks: sum(time) / sum(sources), 95% bootstrap CI')
    fig.savefig(figures/'official_scores.png',dpi=180);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(16,6),layout='constrained')
    keys=['movement_s_per_source','measurement_s_per_source','switch_s_per_source','failed_clear_s_per_source','successful_clear_s_per_source']
    for p,ax in zip((3,4),axes):
        group=[r for r in summary if r['problem']==p];left=np.zeros(len(group))
        for key,label,color in zip(keys,['Movement','Measurements','Channel switches','Failed clears','Successful clears'],['#337c99','#e2b04f','#9a7bb0','#ce695f','#78a977']):
            values=np.array([r[key] for r in group]);ax.barh(range(len(group)),values,left=left,label=label,color=color);left+=values
        ax.set_yticks(range(len(group)),[NAMES[r['variant'].split('__')[0]]+f" ({r['gate_m']:g} m)" for r in group])
        ax.invert_yaxis();ax.set_xlabel('Seconds / source');ax.set_title(f'Q{p}: time decomposition')
    axes[1].legend(loc='upper left',bbox_to_anchor=(1.02,1),fontsize=8)
    fig.savefig(figures/'official_costs.png',dpi=180);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(17,6),layout='constrained')
    for p,ax in zip((3,4),axes):
        group=[r for r in summary if r['problem']==p]
        for index,r in enumerate(group):
            cases=[t for t in trials if int(t['problem'])==p and t['variant']==r['variant']]
            x=[int(t['sources']) if p==3 else int(t['directional_sources'])/int(t['sources']) for t in cases]
            y=[float(t['seconds_per_source']) for t in cases]
            label=NAMES[r['variant'].split('__')[0]]+f" ({r['gate_m']:g} m)"
            ax.scatter(x,y,label=label,color=plt.get_cmap('tab10')(index),s=30,alpha=.75)
        ax.set_xlabel('Source count' if p==3 else 'Directional source fraction')
        ax.set_ylabel('Official virtual seconds / source');ax.set_title(f'Q{p}: observed case composition')
        ax.grid(alpha=.2);ax.legend(fontsize=7,loc='upper left',bbox_to_anchor=(1.02,1))
    fig.suptitle('Descriptive case-level scatter; different settings receive different official cases')
    fig.savefig(figures/'official_case_composition.png',dpi=180);plt.close(fig)
    lines=['# 官方模拟器消融实验结果','',
        f"已完成 16 组 × 10 局 = 160 局官方演练，另有 2 局接入校验。批次全排除 {audit['all_cleared']}/160 局。本档案不包含本地 mock 评分，也未使用正式测试额度。",'',
        '## 先读结论','',
        '这批官方数据还不足以证明所有模块都能提高效率。14 项主比较在 Holm 多重比较校正后均未达到 0.05 水平；不能把均值排序直接写成算法优劣或最优门限。', '',
        '问题三的两个较大观察差异是：扫描与服务分阶段比完整策略慢 25.32%，测向最近邻慢 19.92%。后者累计失败排除 301 次，完整策略为 7 次。原始差值的未校正 bootstrap 区间均为正，但主随机化检验的校正后 p 值分别为 0.1777、0.1367，证据强度应如实区分。', '',
        '问题四尤其不能照着原始均值排名：完整策略组平均每局 12.4 个源、定向源占 62.9%；分阶段组平均 13.8 个源、定向源占 53.6%。原始均值中分阶段反而快 2.81%，而预先记录的源构成调整模型估计其慢 47.67 秒/源。这表明结论对案例构成和模型假设敏感，调整结果仅是辅助证据。', '',
        '源构成调整后的辅助分析支持问题三分阶段、问题三测向最近邻、问题四分阶段存在较大代价；它不能替代未通过多重校正的主比较。其余机制及门限变化在本批样本下尚不能下肯定结论。', '',
        '20 米完整策略在问题三、四各 10 局均无失败排除尝试；这不等于证明它最快。问题四默认完整策略的双负反馈裁剪只触发 2 次，关闭该裁剪组触发 0 次，样本对这一机制的检验很弱。', '',
        '## 计分与实验口径','',
        '计时直接取官方保存的虚拟微秒数。本文组内秒/源 = 总虚拟秒数 / 总源数，是本实验的汇总口径；同时保留逐局成绩和逐局等权均值（summary.csv 的 mean_case_seconds_per_source），不将组间汇总称为官方另行给出的总分。每次调用的位移、测量、切频、成功/失败排除耗时与官方返回值逐项核对，误差仅在微秒舍入范围。', '',
        '官方每次分配新案例，无法把这些数据表述为同一场景配对消融。排程采用 10 个随机运行顺序区组，每区组包含全部 16 组。2 局接入校验不参与下列比较。', '',
        '每组只有 10 局，案例几何分布不可观测。表中 95% 区间为独立案例 bootstrap 百分位区间；14 项与本题默认完整策略的比较同时报告 Holm 校正的随机化检验。未显著不等于效果为零，也不能凭均值更低认定门限更优。', '',
        '## 原始官方成绩','',
        '|问题|设置|全排除局数|源总数|定向源占比|秒/源|95% 区间|失败排除次数|',
        '|---|---|---:|---:|---:|---:|---|---:|']
    for r in summary:
        lines.append(f"|{r['problem']}|{r['label']}，{r['gate_m']:g}米|{r['completed']}/{r['runs']}|{r['sources']}|{r['directional_fraction']:.1%}|{r['seconds_per_source']:.3f}|[{r['ci_low']:.3f}, {r['ci_high']:.3f}]|{r['misses']}|")
    lines+=['','## 相对默认完整策略的变化','',
        '问题三默认门限 50 米，问题四默认门限 35 米。正数表示变体更慢。差值区间是未作多重比较校正的 95% 区间；推断结论参考 Holm 校正后的 p 值。','',
        '|问题|变体|差值（秒/源）|变化|差值 95% 区间|Holm p|','|---|---|---:|---:|---|---:|']
    for r in comparisons:
        lines.append(f"|{r['problem']}|{r['variant']}|{r['delta_seconds_per_source']:+.3f}|{r['relative_pct']:+.2f}%|[{r['ci_low']:+.3f}, {r['ci_high']:+.3f}]|{r['p_holm_14']:.4f}|")
    lines+=['','## 案例构成敏感性分析','',
        '另以总时间为因变量，纳入设置和源数量，问题四再纳入定向源数量，采用 HC3 稳健标准误。差值除以本题所有局的平均源数，得到参考案例下的秒/源差值。这依赖线性加性模型，不能消除未观测的几何难度；它是敏感性分析，不能取代原始官方结果。统计方法及确定时点见 analysis_plan.json。','',
        '|问题|变体|调整后差值（秒/源）|95% 区间|Holm p|','|---|---|---:|---|---:|']
    for r in adjusted:
        p_text=f"{r['p_holm_14']:.4f}" if r['p_holm_14']>=.0001 else '<0.0001'
        lines.append(f"|{r['problem']}|{r['variant']}|{r['delta_seconds_per_source']:+.3f}|[{r['ci_low']:+.3f}, {r['ci_high']:+.3f}]|{p_text}|")
    lines+=['','## 机制是否真正触发','',
        '消融组名称并不保证每局都会用到被移除的机制。下表汇总实际运行计数；若完整策略与对应消融组都未遇到某分支，这批案例就不能识别该分支的因果收益。', '',
        '|问题|设置|共享补测次数|全向负反馈裁剪次数|双负反馈分支次数|被拦截的反馈调用次数|测向最近邻评分调用次数|',
        '|---|---|---:|---:|---:|---:|---:|']
    for r in mechanism:
        lines.append(f"|{r['problem']}|{r['variant']}|{r['shared_known_measurements']}|{r['omni_negative_cuts']}|{r['negative_pair_branch_entries']}|{r['ablation_disabled_negative_calls']}|{r['ablation_scoring_calls']}|")
    lines+=['',
        '计数解释：问题四关闭负反馈组的“双负反馈分支次数”指进入该分支的次数，实际裁剪已替换为恒等操作；其拦截次数应与分支次数一致。问题三的拦截计数覆盖反馈记录入口的调用，不等于本可裁剪的次数。关闭共享补测的所有局均核验共享次数为零。', '',
        '## 核验与文件','',
        '- `trials.csv`：全部 162 局，含 calibration/validation 标识、案例编码、源构成和耗时分解。',
        '- `summary.csv`：16 组原始官方汇总；`comparisons.csv`：14 项原始比较。',
        '- `adjusted_sensitivity.csv`：源构成调整后的辅助比较。',
        '- `mechanism_checks.csv`：各变体的实际机制触发次数。',
        '- `runs.jsonl`：官方权威成绩行及机器狗统计；`audit.json`：逐局核验。',
        '- `config.json`：冻结排程；`runtime_manifest.json`：冻结代码散列。',
        '- `jlogs/`：官方保存的加密行为日志原件。',
        '- `evidence/`：集中归档的逐局请求响应、官方成绩、完成截图、UI 文本和统计字段导出。',
        '- `evidence_index.json`：归档文件散列及完整自动化证据的原始路径；原始路径还保留全部界面过程和官方统计数据库的只读副本。','',
        '![官方成绩及区间](figures/official_scores.png)','',
        '![耗时构成](figures/official_costs.png)','']
    lines+=['![案例构成与单位耗时](figures/official_case_composition.png)','']
    (out/'REPORT.md').write_text('\n'.join(lines))
    print(out/'REPORT.md')


if __name__=='__main__':main()
