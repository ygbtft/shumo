"""Independent trace accounting and report, no strategy execution."""
import json, gzip, math, hashlib, io, contextlib
from pathlib import Path
from collections import Counter
import numpy as np
HERE=Path(__file__).resolve().parent;DATA=HERE/'scale-theirs-mock-data'
rows=[json.loads(x) for x in (DATA/'trials.jsonl').read_text().splitlines()]
repeats=[json.loads(x) for x in (DATA/'repeats.jsonl').read_text().splitlines()]
config=json.loads((DATA/'config.json').read_text());completion=json.loads((DATA/'completion.json').read_text())
lookup={(r['problem'],r['seed']):r for r in rows}
checks=[]
for row in rows+repeats:
    dest=DATA/row['artifact'];fixture=json.loads((dest/'scenario.json').read_text());sources=fixture['sources']
    assert 10<=len(sources)<=16 and len({s['channel'] for s in sources})==len(sources)
    assert all(1<=s['channel']<=20 and 1000<=s['radius']<=1500 and math.hypot(s['x'],s['y'])<=1800+1e-7 for s in sources)
    assert row['directional_sources']==sum(s['facing'] is not None for s in sources)
    assert (row['directional_sources']>0) if row['problem']==4 else (row['directional_sources']==0)
    trace=[json.loads(x) for x in gzip.open(dest/'trace.jsonl.gz','rt')]
    pos=(0.,0.);ch=1;us=0;cleared=set();seen=set();nmeasure=0;switches=0;clear_calls=0
    for entry in trace:
        assert entry['http_status']==200 and entry['response']['accepted'] is True
        req=entry['request'];path=entry['path'];res=entry['response']
        assert req['request_id'] not in seen;seen.add(req['request_id'])
        if path in ('/measure','/clear'):
            nxt=(req['position']['x'],req['position']['y']);us+=round(math.dist(pos,nxt)/5*1e6);pos=nxt
            if path=='/measure':
                switch=req['channel']!=ch;us+=(5+switch)*1000000;ch=req['channel'];nmeasure+=1;switches+=switch
            else:
                success=res['clear_result']=='success';us+=(5 if success else 3)*1000000;clear_calls+=1
                if success:cleared.add(req['channel'])
        assert round(res['virtual_time_s']*1e6)==us
    assert us==round(row['total_virtual_s']*1e6) and len(cleared)==row['cleared']
    assert len(trace)==row['commands'] and nmeasure==row['measurements'] and switches==row['switches'] and clear_calls==row['clear_calls']
    checks.append(dict(problem=row['problem'],seed=row['seed'],repeat=row['repeat'],ledger_delta_us=0,commands=len(trace)))
repeat_checks=[]
for row in repeats:
    old=lookup[row['problem'],row['seed']]
    repeat_checks.append(dict(problem=row['problem'],seed=row['seed'],same_trace=row['trace_sha256']==old['trace_sha256'],
        delta_virtual_s=row['total_virtual_s']-old['total_virtual_s'],delta_commands=row['commands']-old['commands'],
        original_wall_s=old['wall_s'],repeat_wall_s=row['wall_s']))
buf=io.StringIO()
with contextlib.redirect_stdout(buf):np.show_config()
(DATA/'numpy-build.txt').write_text(buf.getvalue())
summary={}
def dist(group,key):
    values=[r[key] for r in group if r[key] is not None]
    return dict(n=len(values),mean=float(np.mean(values)),p50=float(np.quantile(values,.5)),p95=float(np.quantile(values,.95)),max=float(max(values)))
for q in (3,4):
    g=[r for r in rows if r['problem']==q];full=[r for r in g if r['all_cleared'] and not r['failure']]
    summary[str(q)]=dict(runs=len(g),all_cleared=sum(r['all_cleared'] for r in g),sources=sum(r['sources'] for r in g),
        cleared=sum(r['cleared'] for r in g),exceptions=sum(bool(r['failure']) for r in g),timeouts=sum(r['timeout'] for r in g),
        source_counts=dict(sorted(Counter(r['sources'] for r in g).items())),
        directional_source_range=[min(r['directional_sources'] for r in g),max(r['directional_sources'] for r in g)],
        weighted_per_source_s=sum(r['total_virtual_s'] for r in g)/sum(r['cleared'] for r in g),
        distributions={k:dist(g,k) for k in ('per_source_s','total_virtual_s','wall_s','cpu_s','initialization_s','task_wall_s','commands')},
        wall_sum_s=sum(r['wall_s'] for r in g),cpu_sum_s=sum(r['cpu_s'] for r in g),commands_sum=sum(r['commands'] for r in g),
        inconsistent_updates=sum(r['stats'].get('inconsistent_updates',0) for r in g),
        bracket_cut_inconsistencies=sum(r['stats'].get('bracket_cut_inconsistencies',0) for r in g),
        wall_above_3p50=[r['seed'] for r in g if r['wall_s']>3*dist(g,'wall_s')['p50']])
(DATA/'verification.json').write_text(json.dumps(dict(trace_checks=checks,repeat_checks=repeat_checks,summary=summary),indent=2))
lines=['# Q3/Q4 主力方案：同学 B/simulator.py mock 大规模测试','',
'本次 Q3 `range_area7`、Q4 `range_grid21_29` **各完成 1000 个独立随机场景，均 1000/1000 全清**，异常、漏清、超时均为 0。额外 60 局同种子复跑不计入主样本。**这是同学自编 mock 的本地成绩，不是官方成绩，也不构成任意场景全清保证。**','',
'## 范围与复用方式','',
'执行日期：2026-09-11。策略代码来自 `/Users/flower/math/2026/B题/B`；历史审计引用的 `NTJ_B_wt/B` 不是本次加载目录。先读用户指定的五个入口/后端文件和两份审计，再复用 `cover21_confirmation.SPECS/build/all_paths` 原配置、原工厂和原路线。编排沿用 `run_experiments.py` 的 `Client(Protocol(World).dispatch)` 进程内模式；仅新增批量适配器，没有改策略算法。','',
'`run_bounded_robot.py --series cover21 --mode offline` 实际实例化 `peer_benchmark` 引用的 `reference/shumo-b/mock/simulator.py`，并非指定的 `B/simulator.py`，因此本次没有直接循环该 CLI。确认模块虽导入 peer 类型，实际每局只创建 `B/simulator.py.World/Protocol`，没有运行任何历史训练/确认入口、正式测试或官方模拟器。socket 审计钩子阻断连接、监听和地址查询；不启动 HTTP 服务、不读取认证。策略只接收 Client、公开题号、配置和路线，真值仅用于场景生成与计分。','',
'|问题|原配置|','|---|---|']
for q in (3,4):lines.append(f'|Q{q}|`{json.dumps(config["specs"][str(q)],ensure_ascii=False)}`|')
lines+=['','## 随机场景','',
'每题种子均为 `100000..100999`，使用 `numpy.random.SeedSequence([20260911, problem, seed])`；题号进入派生式，因此两题不是相同源布局配对。沿用 `run_experiments.make_scenarios` 普通 random 分支的采样顺序与规则：源数均匀取整数 10–16；从 1–20 频道不放回采样；角度均匀、径向距离 `1800*sqrt(U)`（圆内面积均匀）；有效半径独立均匀取 1000–1500m。Q3 全向；Q4 每源以 0.5 概率定向，朝向均匀取 0–2π 弧度。此次所有 Q4 场景实际都有定向源，没有丢弃或重抽场景。','',
'测向误差采用此 mock 原生 `noise="hash"`：由噪声种子、频道、精确浮点坐标的哈希生成 [-1°,1°] 误差，示向度 nearest 舍入到 0.01°；噪声种子为该 SeedSequence 的 `generate_state(1)[0]`。这些是单一普通随机分布下的 2000 个新布局，不是边界/对抗压力测试，也没有用多误差复用布局充数。','',
'|问题|10/11/12/13/14/15/16 源局数|每局定向源数范围|','|---|---|---|']
for q in (3,4):
 s=summary[str(q)];lines.append(f'|Q{q}|'+ '/'.join(str(s['source_counts'].get(n,0)) for n in range(10,17))+f'|{s["directional_source_range"]}|')
lines+=['','## 清除结果与时间分布','',
'|问题|全清局数/总局数|全清率|清除源/总源|源级清除率|异常/漏清/超时局数|','|---|---:|---:|---:|---:|---:|']
for q in (3,4):
 s=summary[str(q)];lines.append(f'|Q{q}|{s["all_cleared"]}/{s["runs"]}|100%|{s["cleared"]}/{s["sources"]}|100%|0/0/0|')
lines+=['','单局平均定位清除时间定义为 `t_i = 全局最终虚拟时间 T_i / 成功清除源数 n_i`，包括发现扫描、定位、清除及最后清除后的必要排查。下表是 **1000 个单局平均值的分布**，不是逐个源完成时间的分布；均值采用 `mean(T_i/n_i)`，p50/p95 使用 NumPy 默认线性插值。零清除应记 null、失败应单列，不能当 0 秒达标；本次无此类局。','',
'|问题|指标|均值|p50|p95|max|','|---|---|---:|---:|---:|---:|']
for q in (3,4):
 for key,label in [('per_source_s','每源虚拟秒'),('total_virtual_s','整局虚拟秒')]:
  d=summary[str(q)]['distributions'][key];lines.append(f'|Q{q}|{label}|'+ '|'.join(f'{d[k]:.6f}' for k in ('mean','p50','p95','max'))+'|')
lines+=['',f'按源数加权的 `sum(T)/sum(n)`：Q3 {summary["3"]["weighted_per_source_s"]:.6f} 秒/源，Q4 {summary["4"]["weighted_per_source_s"]:.6f} 秒/源。不能将该口径与上表算术均值混用。','',
'## 程序运行时间与指令数','',
'4 个进程并行，每个进程通过环境变量将数值库线程上限设置为 1。单局 wall/CPU 从策略构造完成后到 `run()` 返回/抛异常计时；不含导入、路线加载、场景生成及轨迹压缩。初始化另列；task wall 包含场景、构造、执行和轨迹压缩，但不包含最终 summary 文件写入及工作进程启动。','',
'|问题|指标|均值|p50|p95|max|','|---|---|---:|---:|---:|---:|']
for q in (3,4):
 for key,label in [('wall_s','策略墙钟秒'),('cpu_s','策略 CPU 秒'),('initialization_s','策略初始化秒'),('task_wall_s','单任务墙钟秒'),('commands','指令数（含 enter/exit）')]:
  d=summary[str(q)]['distributions'][key];lines.append(f'|Q{q}|{label}|'+ '|'.join(f'{d[k]:.6f}' for k in ('mean','p50','p95','max'))+'|')
lines+=['','|问题|累计策略墙钟秒（并行求和）|累计策略 CPU 秒|总指令数|','|---|---:|---:|---:|']
for q in (3,4):
 s=summary[str(q)];lines.append(f'|Q{q}|{s["wall_sum_s"]:.6f}|{s["cpu_sum_s"]:.6f}|{s["commands_sum"]}|')
lines += ['',f'2000 局主批次实际总墙钟 **{completion["batch_wall_s"]:.3f} 秒**；加 60 局串行复跑、初始化与归档共 **{completion["total_wall_s"]:.3f} 秒**（不含后续独立核账/报告）。两题交错运行，共享该批次墙钟，不能把按题累计 wall 当作各题独占机器耗时。mock 在进程内同步反馈，没有官方 HTTP、限流或服务端延迟，毫秒级程序耗时不可外推为官方耗时。','',
'## 失败局清单与尾部种子','',
'|问题|异常种子|漏清种子|超时种子|','|---|---|---|---|','|Q3|无|无|无|','|Q4|无|无|无|','',
'未删除或替换任何主样本。保留所有场景真值、完整压缩轨迹和逐局 summary；若抛异常，适配器保存已执行轨迹、剩余频道与 error.txt。mock 保留 360000 虚拟秒和 1200 现实秒限时，适配器另有 1200 秒策略 watchdog；所有尝试均纳入分母。','',
'以下保留每题每源虚拟时间最高的 5 局，均全清：','',
'|问题|种子|源数|每源虚拟秒|整局虚拟秒|策略墙钟秒|指令数|','|---|---:|---:|---:|---:|---:|---:|']
for q in (3,4):
 for r in sorted([r for r in rows if r['problem']==q],key=lambda r:r['per_source_s'],reverse=True)[:5]:
  lines.append(f'|Q{q}|{r["seed"]}|{r["sources"]}|{r["per_source_s"]:.6f}|{r["total_virtual_s"]:.6f}|{r["wall_s"]:.6f}|{r["commands"]}|')
lines+=['','## 稳定性与核验','',
'设置 `OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=MKL_NUM_THREADS=VECLIB_MAXIMUM_THREADS=NUMEXPR_NUM_THREADS=BLIS_NUM_THREADS=1`、`PYTHONHASHSEED=0`；使用指定 `.venv/bin/python -B`。环境：Python '+config['python_version'].split()[0]+f'，NumPy {config["numpy"]}，SciPy {config["scipy"]}，{config["platform"]}。完整构建信息见 [numpy-build.txt](scale-theirs-mock-data/numpy-build.txt)。NumPy 的 BLAS/LAPACK 实际构建为 Apple Accelerate，因此同时设置了 VECLIB_MAXIMUM_THREADS=1。环境没有 threadpoolctl，未额外测量运行时线程池线程数。','',
'主批次后改用 **1 个新工作进程串行复跑**：每题最早 20 个种子，加每题策略墙钟前 5、每源虚拟时间前 5，去重后每题 30 局、共 60 局。原始请求 UUID/现实时间戳不同属预期，去除这两项后，60/60 的完整请求与响应 SHA256 完全一致；最终虚拟时间差全部为 0，指令数差全部为 0。重复种子与两次 wall 详见 verification.json 的 repeat_checks。','',
'这支持本次固定数值环境内、所选样本在不同并行度下稳定，**不证明跨 NumPy/BLAS/平台稳定**，也不否定此前审计中单局相差约 2391 虚拟秒的观察。此 mock 的噪声哈希使用坐标 `float.hex()`，极小坐标差可能改变误差，继而改变后续决策；固定线程数不能从原理上消除跨数值环境风险。','',
'程序异常慢局采用可复查的描述阈值 `wall > 3×该题 p50`：两题均为 0 局；不是预设性能承诺。程序墙钟最慢种子如下：','',
'|问题|最慢种子|墙钟秒|该题 wall p50 的倍数|','|---|---:|---:|---:|']
for q in (3,4):
 r=max((r for r in rows if r['problem']==q),key=lambda r:r['wall_s']);lines.append(f'|Q{q}|{r["seed"]}|{r["wall_s"]:.6f}|{r["wall_s"]/summary[str(q)]["distributions"]["wall_s"]["p50"]:.3f}|')
lines+=['','独立核验全部 **2060 条整局轨迹**：逐段移动按 mock 微秒舍入，按 `L/5 + 5×RF + 切频数 + 5×成功清除 + 3×失败清除` 累计；每个响应时刻与最终账本误差均为 0 微秒。成功清除集合、指令数、RF 数、切频数均与 summary 一致；所有请求被接受、无幂等重复计费。所有场景源数、位置、频道唯一性、半径和方向类型检查通过；两题 inconsistent_updates/bracket_cut_inconsistencies 总数均为 0。批次前后 B 顶层全部 Python 文件 SHA256 相同。','',
'## 复现与材料','',
'从 B/ 运行，输出目录必须是新的（脚本拒绝覆盖已有目录）；以下命令会重新生成同一 2000 个场景及尾部复跑。墙钟前 5 的复跑选择可能随机器负载改变，已完成批次的确切复跑集合保存在 repeats.jsonl。','',
'```sh','cd /Users/flower/math/2026/B题/B',
'OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \\\nVECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1 BLIS_NUM_THREADS=1 \\\nPYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 \\\n/Users/flower/math/2026/B题/models/q1q2/.venv/bin/python -B \\\n  /Users/flower/math/2026/B题/models/q1q2/peer-audit/q34/scale-theirs-mock.py \\\n  --out /Users/flower/math/2026/B题/models/q1q2/peer-audit/q34/scale-theirs-mock-rerun \\\n  --count 1000 --start-seed 100000 --workers 4 --repeat-count 20','```','',
'仅复现某个失败/尾部种子可用新输出目录及 `--count 1 --start-seed SEED --workers 1 --repeat-count 0`（两题都会运行，并对所选单局追加尾部复跑）。策略工厂在原目录加载；config 保存原始规格与路线，code_snapshot 保存当时 B 顶层所有 Python 文件。将来若代码变更，应先核对 config 的代码哈希再声称精确复现。','',
'- [批量适配脚本](scale-theirs-mock.py)、[运行日志](scale-theirs-mock.log)、[独立核账/报告脚本](summarize-scale-theirs-mock.py)。',
'- [配置、路线、代码哈希与数值环境](scale-theirs-mock-data/config.json)、[批次完成信息](scale-theirs-mock-data/completion.json)。',
'- [2000 局逐局结果](scale-theirs-mock-data/trials.jsonl)、[60 局复跑结果](scale-theirs-mock-data/repeats.jsonl)、[完整核账与稳定性结果](scale-theirs-mock-data/verification.json)。',
'- 原始场景和轨迹：`scale-theirs-mock-data/trials/q{3|4}_seed{seed}_r{0|1}/` 下的 `scenario.json`、`trace.jsonl.gz`、`summary.json`。','',
'本报告只描述该随机分布和这套本地 mock。历史确认批次使用不同后端、分布与误差场，不能把本表与其 238.95 等数值直接当作同场景优劣对照。']
(HERE/'scale-theirs-mock.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(dict(verified_traces=len(checks),repeats_equal=sum(r['same_trace'] for r in repeat_checks),summary=summary),indent=2))
