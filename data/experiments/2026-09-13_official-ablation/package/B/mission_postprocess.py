"""Summarize the new holdout without changing any frozen candidate or score."""
import csv
import json
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-11_mission-confirmation"


def main():
    cfg=json.loads((OUT/"run_config.json").read_text());assert cfg["confirmation_seeds"]==list(range(87,97))
    summary_path=OUT/"summary.md"
    text=summary_path.read_text().replace("seed42派生77—86","seed42派生87—96")
    summary_path.write_text(text)
    (OUT/"documentation_corrections.json").write_text(json.dumps(dict(change="Inherited summary heading corrected from 77—86 to 87—96; run_config and all actual row seeds already correct; no score or candidate change"),indent=2))
    rows=[json.loads(l) for l in (OUT/"trials.jsonl").read_text().splitlines()]
    comparisons={3:(("clearance7","peer_layout9_proxy"),("clearance9","peer_layout9_proxy"),("clearance7","fast7"),("clearance7","clearance9")),
                 4:(("quarter22","square45_conservative"),("quarter22","fast22"),("quarter_prediction22","quarter22"),
                    ("clearance_quarter22","quarter22"),("clearance_f015_22","quarter22"),("clearance_f03_22","quarter22"))}
    analysis=[];rng=np.random.default_rng(42)
    for problem,pairs in comparisons.items():
        for candidate,baseline in pairs:
            for split in ("ordinary","stress"):
                g=[r for r in rows if r["problem"]==problem and r["method"]==candidate and r["split"]==split]
                b={r["case_id"]:r for r in rows if r["problem"]==problem and r["method"]==baseline and r["split"]==split}
                delta=np.array([r["total_virtual_s"]-b[r["case_id"]]["total_virtual_s"] for r in g])
                record=dict(problem=problem,candidate=candidate,baseline=baseline,split=split,runs=len(g),
                    mean_per_source_improvement=1-np.mean([r["per_source_s"] for r in g])/np.mean([r["per_source_s"] for r in b.values()]),
                    faster=int((delta<-1e-6).sum()),slower=int((delta>1e-6).sum()),tied=int((abs(delta)<=1e-6).sum()),
                    mean_command_change=np.mean([r["commands"]-b[r["case_id"]]["commands"] for r in g]),
                    worst_regression_s=float(max(0.,delta.max())),worst_case=g[int(delta.argmax())]["case_id"] if delta.max()>1e-6 else None,
                    regressions=[dict(case_id=r["case_id"],delta_s=float(d),candidate_s=r["total_virtual_s"],baseline_s=b[r["case_id"]]["total_virtual_s"]) for r,d in zip(g,delta) if d>1e-6])
                if split=="ordinary":
                    seeds=sorted({r["seed"] for r in g});a=[];base=[]
                    for seed in seeds:
                        group=[r for r in g if r["seed"]==seed];a.append(np.mean([r["per_source_s"] for r in group]));base.append(np.mean([b[r["case_id"]]["per_source_s"] for r in group]))
                    ids=rng.integers(0,len(seeds),(10000,len(seeds)))
                    effects=1-np.array(a)[ids].mean(axis=1)/np.array(base)[ids].mean(axis=1)
                    record["seed_block_bootstrap_95_interval"]=np.quantile(effects,[.025,.975]).tolist()
                analysis.append(record)
    (OUT/"paired_analysis.json").write_text(json.dumps(dict(base_seed=42,replicates=10000,cluster="ten seed blocks, preserving the 15 layout/error settings",comparisons=analysis),indent=2))
    summary=list(csv.DictReader((OUT/"summary.csv").open()))
    selected={3:("peer_layout9_proxy","fast7","clearance7","clearance9"),4:("fast22","quarter22","clearance_f015_22")}
    table=["|问题/策略|普通/压力全清|普通/压力平均每源秒|普通/压力最大总秒|普通/压力平均指令|普通/压力最大策略墙钟秒|", "|---|---:|---:|---:|---:|---:|"]
    for problem,methods in selected.items():
        for method in methods:
            a=next(r for r in summary if int(r["problem"])==problem and r["method"]==method and r["split"]=="ordinary")
            b=next(r for r in summary if int(r["problem"])==problem and r["method"]==method and r["split"]=="stress")
            table.append(f"|Q{problem} {method}|{a['all_cleared']}/{a['runs']}；{b['all_cleared']}/{b['runs']}|{float(a['mean_per_source_s']):.2f}/{float(b['mean_per_source_s']):.2f}|{float(a['max_total_s']):.2f}/{float(b['max_total_s']):.2f}|{float(a['mean_commands']):.2f}/{float(b['mean_commands']):.2f}|{float(a['max_wall_s']):.4f}/{float(b['max_wall_s']):.4f}|")
    update="""## 2026-09-11继续优化：非对称探测、完整保收定义与清除可行域

本轮完成4278次训练和2145次新场景确认，**6423次全部清除**；累计计分离线执行22554次。goal保持active：当前没有一套方法在所有场景和指标上全面胜出，240/460s普通平均每源目标也尚未达到。源码缺失和官方未运行的证据边界不变。

### 新增改进及证据

- 将“已发现16个不同频道后停止发现阶段”独立实现，删除没有实际收益的动态覆盖计算。它与旧替代版195条已录制任务逐请求等价；不能把此前收益归给没有触发的替代扫描。[实现](efficient_joint_policy.py)。
- 第四问成对探测可取任意合法正距离，不必机械二分。比较首步分位、每步分位、增长步长、共享冷却和外圈优先后，四分之一探测+150m共享冷却的普通与压力表现较均衡；外圈优先、单次旋转未稳定胜出。冷却不排除任何可行位置。
- 第二问把完整保收定义化成半平面裁剪和顶点距离检查，能接纳原两类充分条件并集漏掉的合法近处检测点；对所有可能返回角度做区间外包，给出连续最坏后验MEC上界。[证明及限制](C_SIG_AND_MINIMAX.md)。其在线minimax排名在Q3训练中收益很小、CPU更高，故不为了方法名称复杂而推荐。
- 第三问增加“最近保证清除位置”：在各顶点20m圆盘交集中找离当前位置最近的点；不必总走到MEC圆心。有限候选算法经过独立法锥最优性证书及退化用例核查。它只对本次移动最优，整局仍可能变慢。[完整证明与局部最优反例](ROBUST_GUARANTEES_UPDATE.md)。

### 新确认：87—96及独立压力流

11个候选在生成新真值之前冻结，每候选150普通和45压力场景，总2145次，111.83s完成；无未清源、异常或区域不一致。以下是同场景配对数据，不能用上一轮77—86的绝对均值直接判断本轮算法进退。

"""+"\n".join(table)+"""

Q3七点清除可行域版比同场景七点快速版普通均值仅约0.47%改善；九点版压力最大总时间更小，但普通均值和指令更多。Q4四分之一版比快速二分版普通均值改善约2.64%、压力约6.18%，压力最大总时间从9674.25降到8281.04s；它的CPU和部分逐例耗时仍有退步。0.15分位清除位置版将压力最大再降至7764.30s，但普通均值、指令及CPU更高。

逐例回退必须一起看：Q4四分之一版对快速二分版在普通场景120局更快、30局更慢，压力37局更快、8局更慢；普通最坏回退为uniform/iid/93增加1530.56s，压力为boundary_tangent/n13/positive增加463.89s。普通均值改善的10个种子块bootstrap区间为1.73%—3.70%，只反映这组有限数据，不能推出逐例或最坏情况优势。Q3七点清除可行域版对同学九点布局代理的150普通场景均更快，但45压力中仍有9局变慢，最大回退344.38s；九点清除可行域版把这项最大回退减至7.53s，代价是更多指令和较高普通均值。

对已见uniform/iid/93的两条反馈轨迹再作任务拆账发现：quarter22的源定位/清除任务比fast22少652.76s，扫描任务却多2183.32s；访问站点从7个增为17个，最终净慢1530.56s。两者均没有触发有限光学网格兜底。局部定位变快仍可能通过落脚点、固定误差读数与后续任务顺序增加发现成本；这只是该局的成本分解，尚不是新参数在未见场景有效的因果保证。[完整公开反馈任务诊断](experiments/runs/2026-09-11_mission-confirmation/reused_slow_case_task_diagnosis.json)。

因此继续保留效率与尾部两类候选：Q3七点清除可行域版偏效率、九点版偏尾部；Q4四分之一版较均衡，0.15版作为压力尾部候选。不能称任何一个为全指标或全局最优。[完整表：总时间、P95、源数加权、CPU和初始化](experiments/runs/2026-09-11_mission-confirmation/summary.md)，[配对退步及按种子分块区间](experiments/runs/2026-09-11_mission-confirmation/paired_analysis.json)。

### 可复现运行与尚缺证据

增加了自己启动的随机端口本地HTTP服务核查：四个策略通过实际HttpTransport与同学未修改协议交互，均15/15清除，指令序列和虚拟时间与进程内后端完全一致。[HTTP记录](experiments/runs/2026-09-11_mission-confirmation/http_checks.json)。这仍是我们自己的本地协议测试，未连接任何现有官方服务，不能作官方成绩或等价于官方软件耗时。

本轮独立归档核查68项通过：44条完整记录只用公开反馈逐请求重放，事后核对区域包含真值及认证光学覆盖；另重算全部2145条确认轨迹的640276条指令，检查接收、角度舍入和逐动作计时。确认轨迹没有同地点重复读数，因此本组数据本身不能检验“同地点误差固定”；其依据仍是已保存的误差场规则检查，以及[同学提供演练记录的一组同点重复核查](experiments/runs/2026-09-10_peer-benchmark/recording_audit.json)，后者也不是官方来源认证。原附件、同学原图、公开探索、两个上游clone均未修改。[本轮核查结果](experiments/runs/2026-09-11_mission-confirmation/final_checks.json)。连续覆盖和有限结束来自独立几何推导，数值边界使用记录中的容差，不把这些有限轨迹当作最坏情况证明。

新离线入口：`/Users/dingdingzai/anaconda3/bin/python -B B/run_bounded_robot.py --series mission --problem 3 --method clearance7 --seed 42`；第四问使用`--problem 4 --method quarter22`。默认旧series仍可复现历史命令。输出仅在B/robot_runs，CLI不含正式HTTP模式。

本轮Q3普通较低值255.82s/源、Q4约523.62s/源，均未达240/460；压力尾部、指令和真实运行时间均独立报告。累计22554是策略执行数，包含训练复用，不是独立案例数或官方机会。无账号注册、无报名身份使用、正式请求0。本队官方演练仍需用户实际提供可运行环境及操作条件；缺同学一完整源码，不声称已经全面超过其完整实现。三名计算机队员仍可将B作为认真选择的主候选，但国奖可行性仍要由实际官方演练和最终论文质量检验。

训练与数学记录：[非对称探测1860次](experiments/runs/2026-09-11_asymmetric-probes/summary.md)、[保收与旋转1674次](experiments/runs/2026-09-11_reception-layout/summary.md)、[清除可行域744次](experiments/runs/2026-09-11_clearance-neighborhood/summary.md)、[Q2连续最坏界](experiments/runs/2026-09-11_q2-minimax/summary.md)。
"""
    (ROOT/"REPORT_MISSION_UPDATE.md").write_text(update)
    print("Corrected metadata-only heading; wrote paired analysis and report update")


if __name__=="__main__":main()
