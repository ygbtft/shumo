"""Report the owned HTTP audit; only reads archives and writes audit artifacts."""
import gzip
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT))
from mock.evaluator import summarize
OUT=Path(__file__).resolve().parent
DATA=OUT/'ours-http-scale'
ARCH=ROOT/'B/experiments/runs/2026-09-11_cover21-confirmation'
rows=[json.loads(x) for x in (DATA/'rows.jsonl').read_text().splitlines()]
meta=json.loads((DATA/'summary.json').read_text())
design=json.loads((DATA/'design.json').read_text())
peer=[r for r in map(json.loads,(ARCH/'trials.jsonl').read_text().splitlines()) if r['method']=={3:'range_area7',4:'range_grid21_29'}[r['problem']]]


def group(p,profile):return [r for r in rows if r['problem']==p and r['profile']==profile]
def mean(rs):return float(np.mean([r['average_clear_time_s'] for r in rs]))
def boot(rs):
    # Entire seed block includes all positions and error conditions; do not treat
    # the 15 paired outcomes within a seed as 15 independent observations.
    seeds=sorted({r['seed'] for r in rs})
    a=np.array([mean([r for r in rs if r['seed']==s]) for s in seeds])
    rng=np.random.default_rng(2026091199)
    return np.percentile(a[rng.integers(0,len(a),(10000,len(a)))].mean(axis=1),[2.5,97.5]).tolist()

summary={}
for p in (3,4):
 for profile in ('default','shifted'):
    rs=group(p,profile); summary[f'{profile}/q{p}']={**summarize(rs),'seed_block_mean_ci95':boot(rs)}

# Verify stored truth pairing, every HTTP journal, and scoring without trusting
# the row's declared ratios. Count outcomes from public clear responses.
checks={'files':0,'http_attempts':0,'accepted_actions':0,'paired_truth_checks':0,'recovered_transport_failures':0,'audit_assertion_runs':[], 'errors':[]}
truth={}
for r in rows:
    path=DATA/r['profile']/f'q{r["problem"]}'/r['condition']/f'seed-{r["seed"]}.json.gz'
    saved=json.load(gzip.open(path,'rt'))
    checks['files']+=1
    attempts,t=saved['http_journal'],saved['trace']
    j=[x for x in attempts if x.get('event')!='transport_failure']
    retries=[x for x in attempts if x.get('event')=='transport_failure']
    assert len(j)==len(t)==r['actions'] and len(attempts)==r['http_attempts']
    lookup={x['request']['request_id']:x for x in j}
    assert all(x['request']==lookup[x['request']['request_id']]['request'] for x in retries)
    checks['recovered_transport_failures']+=len(retries)
    if r['failure']:
        assert r['cleared']==r['total'] and r['stop_reason']=='user_exit' and 'assert len(journal.rows) == len(sim.trace)' in r['error']
        checks['audit_assertion_runs'].append({'problem':r['problem'],'profile':r['profile'],'condition':r['condition'],'seed':r['seed'],'recovered_attempts':len(retries)})
    assert j[0]['path']=='/enter' and j[-1]['path']=='/exit'
    assert all(x['http_status']==200 and x['response']['accepted'] is True for x in j)
    assert all(x['request']==y['request'] and x['response']==y['response'] and x['path']==y['path'] for x,y in zip(j,t))
    assert saved['metrics']==r and t[-1]['response']['virtual_time_s']==r['total_time_s']
    assert r['total']==len(saved['scenario']['sources'])
    cleared={x['request']['channel'] for x in j if x['path']=='/clear' and x['response'].get('clear_result')=='success'}
    assert len(cleared)==r['cleared']
    assert r['average_clear_time_s']==r['total_time_s']/len(cleared)
    key=(r['problem'],r['profile'],r['condition'].split('__')[0],r['seed'])
    value=json.dumps(saved['scenario'],sort_keys=True)
    if key in truth:assert truth[key]==value; checks['paired_truth_checks']+=1
    else:truth[key]=value
    checks['http_attempts']+=len(attempts);checks['accepted_actions']+=len(t)

same={n:(ROOT/'mock'/n).read_bytes()==(ROOT/'B/reference/shumo-b/mock'/n).read_bytes() for n in ('scenario_gen.py','error_field.py','simulator.py','protocol.py','evaluator.py')}
assert meta['runs']==len(rows)==2400 and len(meta['conditions'])==60
assert not meta['changed_source_files']
(OUT/'scale-ours-mock-statistics.json').write_text(json.dumps(dict(summary=summary,verification=checks,reference_copy_identical=same),ensure_ascii=False,indent=2)+'\n')

lines=[]
def add(s=''):lines.append(s)
add('# Q3/Q4 我方本地 mock HTTP 蒙特卡洛交叉验证')
add('\n本报告全部为合成、非官方结果。正式测试与官方模拟器调用均为 0。未修改同学策略算法、客户端或 models/q1q2 生产代码。')
add('\n## 结论')
add(f'\n完整批次 **2400/2400 局全清，未恢复的策略执行失败 0；HTTP响应拒绝 0，已恢复连接失败 5 次（4局）**。默认矩阵每问 15×50=750 局；分布偏移矩阵每问 15×30=450 局。未发现本批误差端点或分布偏移导致漏源的反例，但全清不等于耗时不退化，更不是官方保证。')
for p in (3,4):
    a,b=summary[f'default/q{p}'],summary[f'shifted/q{p}']
    old=[r['per_source_s'] for r in peer if r['problem']==p and r['split']=='ordinary']
    av,bv=a['average_clear_time_s']['mean'],b['average_clear_time_s']['mean']
    add(f'\nQ{p}：默认每源均值 **{av:.2f} 秒**，同学归档普通集 {np.mean(old):.2f} 秒，差 {(av/np.mean(old)-1)*100:+.2f}%；偏移组 **{bv:.2f} 秒**，相对我方默认组 {(bv/av-1)*100:+.2f}%。两批种子不同，该差异是描述性结果，不能归因于某个单独参数。')
add('\n关键限制：我方 `mock/` 与同学 `B/reference/shumo-b/mock/` 的场景、误差、物理、协议和 evaluator 五个核心文件逐字节相同。同学确认集也使用这套参考生成器。因此默认矩阵属于**独立生成的新随机案例验证**，不是独立模型族验证；真正改变分布的是本报告预先固定的 shifted 组，仍受同一物理模型假设约束。不能将本结果包装为完全异构模拟器盲测。')
add('\n## 执行方法与预先固定设计')
add('\n选择 HTTP。原 `run_bounded_robot.py` 的 `--mode` 仅有 mock-http/offline/practice；mock-http 固定起其自建 World，`--base-url` 仅允许 practice。为避免进入官方分支，本次没有调用该 CLI，而在我方 [编排脚本](../../../../mock/peer_q34_http_audit.py) 中调用同一 cover21 工厂、冻结参数/路线及未修改的 `Client(HttpTransport(...), robot_id="mock-robot")`。每局先绑定 `127.0.0.1:0`，再仅连接分配给该局的端口；Python socket 审计钩子禁止连接任何其他地址。策略构造仅得到客户端、题号、策略参数与站点，不传源场景、误差配置或种子。')
add('\n提前导入根目录 mock，避免同学裸 import 将后端劫持到 reference 副本；运行时逐模块校验文件路径。cwd 为 `B/`；使用指定 venv，NumPy/BLAS 线程固定为 1，4 个本地进程并行。冻结的策略规格与当前工厂断言一致，路线读取最新 cover21 归档的 `run_config.json`。不运行同学场景生成函数。所有设计、运行环境、源码哈希见 [design.json](ours-http-scale/design.json)，开始/结束被监测源码哈希无变化。')
add('\n| 参数 | default | shifted（预先固定的联合压力，不作单因素因果归因） |\n|---|---|---|')
for a,b,c in [
 ('每组合局数/种子','50；2026091100–2026091149','30；2026092100–2026092129'),
 ('位置','均匀面积 / 贴边 power=8 / 3簇 σ=180m','均匀面积 / 贴边 power=32 / 1簇 σ=60m'),
 ('源数/频道','10..16 均匀、频道无放回','相同'),
 ('接收半径','[1000,1500] 均匀','固定 1000m'),
 ('Q3 定向比例','0','0'),
 ('Q4 定向比例/朝向','0.5、均匀朝向、强制两类混合','0.85、朝外、强制两类混合'),
 ('误差矩阵','iid / smooth / +1° / −1° / 地点固定 ±1°','完整保留相同五类'),
 ('smooth尺度/跨频道','200m / independent','800m / shared（iid和空间±1也共享）')]: add(f'| {a} | {b} | {c} |')
add('\n每个题号/位置/profile 内，5 种误差使用完全相同源真值与种子。每问每 profile 的 750/450 次执行不等于 750/450 个独立源场景：实际为 150/90 个位置场景，且不同位置也复用种子；下文总体均值区间按整块种子重采样。60 局初始链路冒烟包含每组合首种子，未据此调策略或分布；不将这些首种子宣称为严格未看过的盲测。')
add('\n## 与同学自建 B/simulator.py 的本地大样本对照')
theirs_path=OUT/'scale-theirs-mock-data/trials.jsonl'
if theirs_path.exists():
    theirs=[json.loads(x) for x in theirs_path.read_text().splitlines()]
    add('\n另一个本地审计已完成同学自建 World 每问1000局，详见 [scale-theirs-mock.md](scale-theirs-mock.md)。这里直接读取其逐局数据复算，仅取我方 default/uniform__iid 50局作最接近的分布比较，避免将3×5混合矩阵与单一均匀/iid总体直接混比。两边使用各自生成器、误差哈希与不同种子，Q4强制混合规则也有差异；不是同场景配对，更不是只替换后端的因果实验。')
    add('\n| 问题 | 同学World n/全清 | 同学均值 | 我方uniform/iid n/全清 | 我方均值 | 差异% | 同学P95 | 我方P95 |\n|---|---|---:|---|---:|---:|---:|---:|')
    for p in (3,4):
        ts=[r for r in theirs if r['problem']==p and r['repeat']==0]
        us=[r for r in group(p,'default') if r['condition']=='uniform__iid']
        ta=np.array([r['per_source_s'] for r in ts]);ua=np.array([r['average_clear_time_s'] for r in us])
        add(f'| Q{p} | {len(ts)}/{sum(r["all_cleared"] for r in ts)} | {ta.mean():.2f} | {len(us)}/{sum(r["total"]==r["cleared"] for r in us)} | {ua.mean():.2f} | {(ua.mean()/ta.mean()-1)*100:+.2f} | {np.percentile(ta,95):.2f} | {np.percentile(ua,95):.2f} |')
    add('\n该同学World结果与我方最接近的均匀/iid分布处于相近量级，结合全清结果，目前没有支持“只在自家mock才能工作”的证据。旧10种子/组合确认均值偏低、新默认总体变慢与shifted进一步变慢，提示效率依赖场景分布；尚不足以将差异识别为策略过拟合。')

add('\n## 指标口径与总体分布')
add('\n清除比例为每局清除数/真实总数；平均定位清除时间为整局全部接受动作累计虚拟秒/清除数，包含切频、失败搜索、清除后扫描。下列均值/分位数均针对逐局“秒/源”，不混用总时间或 pooled 均值。零清除应记 null 并单列，本批为 0 局。物理计时由我方模拟器产生；现实运行时间不冒充官方程序耗时。')
add('\n| 组 | 局数 | 清除比例均值/全清率 | 每源均值 | 标准差 | P5 | P25 | P50 | P75 | P95 | 最大值 | 均值95%区间（种子块bootstrap） |\n|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|')
for key,s in summary.items():
    d=s['average_clear_time_s'];q=d['quantiles'];ci=s['seed_block_mean_ci95']
    add(f'| {key} | {s["runs"]} | {s["cleared_fraction"]["mean"]:.2%}/{s["all_cleared_rate"]:.2%} | {d["mean"]:.2f} | {d["std"]:.2f} | '+ ' | '.join(f'{q[k]:.2f}' for k in ('p05','p25','p50','p75','p95','p100'))+f' | [{ci[0]:.2f}, {ci[1]:.2f}] |')
add('\nbootstrap 为固定种子 10000 次、同一 seed 下15组合整体抽样的描述性区间；不能消除模型选择偏差。每个默认组合零失败50局，对该指定合成分布的单侧95%失败率上限仍约5.82%；30局约9.50%（1−0.05^(1/n)）。不将全部配对执行当独立伯努利样本给出过窄上限，也不声称多重比较同时覆盖。')
for profile in ('default','shifted'):
 for p in (3,4):
    add(f'\n## {profile} Q{p} 完整 3×5 组合表')
    add('\n时间单位：虚拟秒/源。归档列为同学 cover21 普通确认集同组合10局（seed147–156）；差值非配对。shifted 与归档同时改变参数与种子。')
    add('\n| 位置×误差 | n | 平均清除比例 | 全清局 | 均值 | P50 | P95 | 最大 | 归档均值 | 差异% |\n|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|')
    for condition in [f'{pos}__{err}' for pos in ('uniform','edge','clustered') for err in ('iid','smooth','adversarial-positive','adversarial-negative','adversarial-spatial')]:
        rs=[r for r in group(p,profile) if r['condition']==condition];s=summarize(rs);d=s['average_clear_time_s'];q=d['quantiles']
        old=np.mean([r['per_source_s'] for r in peer if r['problem']==p and r['category']==condition and r['split']=='ordinary'])
        add(f'| {condition} | {len(rs)} | {s["cleared_fraction"]["mean"]:.2%} | {sum(r["cleared"]==r["total"] for r in rs)}/{len(rs)} | {d["mean"]:.2f} | {q["p50"]:.2f} | {q["p95"]:.2f} | {q["p100"]:.2f} | {old:.2f} | {(d["mean"]/old-1)*100:+.2f} |')
add('\n## 误差场退化与过拟合迹象')
add('\n以下按相同 seed/位置成对比较每源时间；每种误差跨三类位置均衡平均，给出相对 iid 的平均差值。+1/−1/空间±1没有造成漏源，耗时差异体现误差模型敏感性；不把“对抗”理解为针对策略在线求得的全局最坏攻击。')
add('\n| 组 | smooth−iid | +1−iid | −1−iid | 空间±1−iid |\n|---|---:|---:|---:|---:|')
for p in (3,4):
 for profile in ('default','shifted'):
    rs=group(p,profile);base={(r['condition'].split('__')[0],r['seed']):r['average_clear_time_s'] for r in rs if r['condition'].endswith('__iid')}
    deltas=[np.mean([r['average_clear_time_s']-base[(r['condition'].split('__')[0],r['seed'])] for r in rs if r['condition'].endswith('__'+e)]) for e in ('smooth','adversarial-positive','adversarial-negative','adversarial-spatial')]
    add(f'| {profile}/q{p} | '+' | '.join(f'{x:+.2f}' for x in deltas)+' |')
add('\n同学最新普通确认集是每问150局、压力45局，当前两主力归档均全清。本次默认组与归档的差异混合了随机样本与运行环境差异；我方已有复现审计提示精确坐标哈希误差场和近等距排序对浮点环境敏感，不能将所有均值差直接称为过拟合。本次 shifted 同时改变半径、位置集中程度、Q4方向以及误差相关结构，观察到的联合变化也不能识别哪个假设起作用。没有同场景竞争策略对照，因此不能据此评价策略排名或“过拟合损失”的大小。')
add('\n## 失败记录、慢局与复现')
add('\n完整2400局未出现未清完或非正常退出。原始 rows/summary 中有4个 failure 标记，是执行后的审计断言错误，均不是策略失败；原始文件不改写。具体为 Q4/default/uniform__iid，种子2026091100、2026091101、2026091102、2026091103，分别有2/1/1/1次 `URLError(OSError(49, "Can’t assign requested address"))`。原客户端复用原请求ID自动重试，均成功且不重复计时。错误提示与本地地址分配资源压力相容，本次未采集系统端口状态，不能声称已证实具体内核原因。核对脚本已区分尝试与成功响应，确认每次失败对应后续同ID/同参数成功响应；初版编排保存为 [runner-at-execution.py](ours-http-scale/runner-at-execution.py)，当前编排只修正此核对断言，原策略不变。下面列每组最慢3局作为耗时反例，完整源真值、误差配置、接受轨迹与客户端HTTP逐请求记录均在对应 gzip 文件中。')
add('\n| 组 | 位置×误差 | 种子 | 清除/总数 | 总虚拟秒 | 秒/源 | 请求数 |\n|---|---|---:|---:|---:|---:|---:|')
for p in (3,4):
 for profile in ('default','shifted'):
    for r in sorted(group(p,profile),key=lambda r:r['average_clear_time_s'],reverse=True)[:3]:
        path=f'ours-http-scale/{profile}/q{p}/{r["condition"]}/seed-{r["seed"]}.json.gz'
        add(f'| {profile}/q{p} | {r["condition"]} | [{r["seed"]}]({path}) | {r["cleared"]}/{r["total"]} | {r["total_time_s"]:.2f} | {r["average_clear_time_s"]:.2f} | {r["actions"]} |')
add('\n链路冒烟另有一局必须保留：`Q4/default/clustered__adversarial-negative/2026091100`，原始线程服务器返回409，停止时仅清3/11源、105个接受动作、1519.018938虚拟秒。证据：[原始失败](ours-http-smoke/default/q4/clustered__adversarial-negative/failures/seed-2026091100.json)。代码路径表明 `send_reply` 后到 `complete_pending` 释放占用前存在窗口，足以让已收到完整响应的客户端下一条串行请求被视为并发。本次在编排侧的 `SerialSessionHTTPServer` 对整个 handler 生命周期加锁，HTTP handler、协议、物理规则及客户端均不改；这是本地服务器调度适配，不能声称原服务器/客户端组合完全无缺陷。该首例在完整统计批次已重跑，原始冒烟未合入2400局。')
replays=json.loads((OUT/'ours-http-replays.json').read_text())
assert len(replays)==8 and all(r['same_time'] and r['same_actions'] and not r['replay_failure'] and r['replay_cleared']==r['total'] for r in replays)
add('\n修正核对断言后，以新进程串行复跑4个审计标记案例及4组各自最慢例，共8局：全部全清、无审计错误，最终虚拟时间和接受动作数与原批次完全相同。证据：[ours-http-replays.json](ours-http-replays.json)。这些重复不计入2400局主样本；仅核对本机同环境时间/动作数，不宣称跨环境逐字节复现。')
add('\n## 假设、验证与边界')
add('\n依据 [mock/README.md 假设清单](../../../../mock/README.md)：A1 的数量、频道、位置、半径与方向先验均为合成假设，shifted 是刻意替换的敏感性对照；A2 的 iid 是精确float64地点固定哈希，smooth是16平面波经tanh，非独立均匀边际；A3 仅静态误差压力；A4 重合near与浮点覆盖容差；A5 每动作移动半向上到微秒、示向度两位舍入，潜在±1°外另有最多0.005°显示误差；A6–A8 幂等、结束关闭、容量及HTTP生命周期是本地约定，本次仅加上述串行调度。A9 按整局计时；A10 省略倒计时但保持1200s现实、1500s窗口、360000s虚拟限制，本HTTP批次未另套 evaluator 的10000动作保护，原策略预算保持不变；A11 不使用经验标定；A12 归档动作与响应不等于重现实网时序。')
add(f'\n批次现实墙钟 {meta["elapsed_s"]:.2f}s（4进程，包含每局HTTP与gzip持久化，统计末尾写盘不计）；每局 runtime 包含导入/初始化及服务器关闭、但不含随后gzip写盘，不能与同学仅 policy.run 的 wall_s 直接比较。验证逐个读取全部 {checks["files"]} 个案例，核对 {checks["http_attempts"]} 次客户端HTTP尝试（含5次已恢复连接失败），核对成功响应与服务器接受轨迹逐条一致、/enter与/exit、清除success集合、最终时间、源总数及跨误差场景配对；全部通过。2400局执行开始/结束的源码监测哈希一致；随后仅修正编排计数断言并保留原版快照，未重跑/覆盖同学实验归档。')
add('\n仍不能证明任意位置、方向、误差或数值环境下全清，也不能验证官方计时契约。本批未主动注入网络故障，实际发生的5次本地连接失败均已恢复，不评估官方HTTP可靠性；串行调度适配后的结果仅代表该明确本地配置。')
add('\n复现（输出目录必须不存在；下面使用新的目录名）：\n\n```sh\ncd /Users/flower/math/2026/B题/B\nOPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \\\n  /Users/flower/math/2026/B题/models/q1q2/.venv/bin/python -B \\\n  ../mock/peer_q34_http_audit.py --runs 50 --shifted-runs 30 --workers 4 \\\n  --seed 2026091100 --output ../models/q1q2/peer-audit/q34/ours-http-scale-repro\n```')
add('\n单例重放（自身绑定全新本地端口，不连接原记录端口）：\n\n```sh\ncd /Users/flower/math/2026/B题/B\nOPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \\\n  /Users/flower/math/2026/B题/models/q1q2/.venv/bin/python -B \\\n  ../mock/peer_q34_http_audit.py --workers 1 \\\n  --case ../models/q1q2/peer-audit/q34/ours-http-scale/default/q4/clustered__adversarial-negative/seed-2026091100.json.gz \\\n  --output ../models/q1q2/peer-audit/q34/ours-http-one-repro\n```')
add('\n统计与报告重生成：\n\n```sh\n/Users/flower/math/2026/B题/models/q1q2/.venv/bin/python -B \\\n  /Users/flower/math/2026/B题/models/q1q2/peer-audit/q34/summarize_ours_mock.py\n```')
add('\n原始产物：[逐局结果](ours-http-scale/rows.jsonl)、[60组合汇总](ours-http-scale/summary.json)、[附加统计与验证](scale-ours-mock-statistics.json)。每个组合目录另含 rows.json、summary.json 与每局 seed-*.json.gz，全部分位数（含P0/P5/P25/P50/P75/P95/P100）、标准差、总时间、pooled指标和零清除数均保留。')
(OUT/'scale-ours-mock.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
