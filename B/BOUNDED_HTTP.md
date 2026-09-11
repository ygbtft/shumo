# 当前主力 HTTP 交付入口

2026-09-11 已验证：`cover21` 工厂 → Q3 `CoupledCompletionPolicy` / Q4 `CoupledWidthPolicy` → `Client` → `HttpTransport` → 自建回环 HTTP 服务 → **B/simulator.py** → `/exit`。
只验证了本地 mock，没有官方模拟器调用、登录或正式测试。本结果证明我方链路能跑通，不是官方成绩。

## 本地复现

在 B/ 下运行（使用裸 import），无需启动其他服务：

```sh
cd /Users/flower/math/2026/B题/B
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
Q34_PYTHON=/Users/flower/math/2026/B题/models/q1q2/.venv/bin/python
"$Q34_PYTHON" -B run_bounded_robot.py --series cover21 --problem 3 --method range_area7 --seed 42
"$Q34_PYTHON" -B run_bounded_robot.py --series cover21 --problem 4 --method range_grid21_29 --seed 42
```

`-B` 禁止写入字节码；借用该环境的解释器，不修改 models/q1q2。也可在 B/ 创建有 NumPy 的虚拟环境。此次 Python 3.14.6、NumPy 2.5.3、macOS ARM64。

- 默认 `--mode mock-http`：自建 `HTTPServer(('127.0.0.1', 0))`，操作系统分配空闲端口；只请求本进程拥有的服务，退出时关闭。显式指定 `--mode mock-http` 效果相同。该模式拒绝 `--base-url` 等演练参数，避免误连已有服务。
- `--mode offline`：保留原来的参考 peer mock 进程内运行，结果标为 `offline_peer_only`。这与自带 World 使用不同场景/误差生成器，不能按同 seed 当作同一场景比较。
- `--series` 默认仍是旧 `icra`，主力必须指定 `--series cover21`。方法不自动替换。
- 沿用 `cover21_confirmation` 的工厂、规格、已保存的路线数据及其依赖；没有重算站点、修改测向/清除/终止数学口径。仍需完整 B/ checkout，历史 `dist` 包尚不包含此新入口。

## 本次实际输出

| 指标 | Q3 range_area7 | Q4 range_grid21_29 |
|---|---:|---:|
| seed | 42 | 42 |
| 工厂类 / 站数 | CoupledCompletionPolicy / 7 | CoupledWidthPolicy / 21 |
| 清除数 / 真源数 | 10 / 10 | 10 / 10 |
| 清除比例 | 100% | 100% |
| 总虚拟时间 / 秒 | 3312.579681 | 5847.482087 |
| 平均定位清除时间 / 秒每源 | 331.2579681 | 584.7482087 |
| 指令数（含 enter、exit） | 141 | 293 |
| measure / clear 次数 | 127 / 12 | 281 / 10 |
| 成功 / 失败 clear 次数 | 10 / 2 | 10 / 0 |
| 切频次数 | 119 | 259 |
| policy.run 墙钟秒（含 HTTP、逐响应落盘） | 0.080077 | 0.125278 |
| 程序墙钟秒 program_wall_s | 0.711529 | 0.608710 |
| 官方调用数 | 0 | 0 |

两局均为 `full_coverage_and_all_discovered_cleared`，`entered=true`、`exited=true`，最后响应 `exit_reason=user_exit`；无区域更新不一致。源数仅由 runner 在评分时读取，策略没有获得真值。

`per_source_s = total_virtual_s / cleared`，包含最后一次成功清除之后仍必要的未知频道排查。虚拟费保持原口径：逐段移动距离/5（mock 四舍五入到微秒）+ 5×测向 + 切频数 + 5×成功清除 + 3×失败清除。指令数包括零虚拟费用的 enter/exit。

`program_wall_s` 从入口开始执行（主要导入之前）计至服务关闭、最终汇总写入之前，包括导入、路线加载、场景/策略初始化、HTTP 和请求日志落盘；不含解释器启动、最终 summary 写入、打印及进程销毁。`wall_s` 只计 policy.run，`cpu_s` 是该段进程 CPU 时间。均不是官方 GUI 的“程序运行时间”，也不保证跨 NumPy/BLAS 环境逐局虚拟时间完全一致。

原始证据：

- [Q3 summary](robot_runs/20260911-150857-232004-bounded-mock-http/summary.json)，[客户端请求](robot_runs/20260911-150857-232004-bounded-mock-http/requests.jsonl)，[服务端请求](robot_runs/20260911-150857-232004-bounded-mock-http/mock_http_requests.jsonl)。实际端口 49866。
- [Q4 summary](robot_runs/20260911-150857-873900-bounded-mock-http/summary.json)，[客户端请求](robot_runs/20260911-150857-873900-bounded-mock-http/requests.jsonl)，[服务端请求](robot_runs/20260911-150857-873900-bounded-mock-http/mock_http_requests.jsonl)。实际端口 50009。
- 每个目录另有 `config.json`（含环境、客户端 SHA256）、`policy.json`（实际类、参数、站点）、`endpoint.json`、`scoring_only.json`。新运行生成新的带时间戳目录，异常写 `failure.txt` 并返回失败。
- [复核结果](robot_runs/bounded-http-verification.json)：两端全部 434 条记录一致，逐条费用账本与最终汇总一致；5 个非法开关组合均在建立连接前拒绝。复核脚本禁用 socket connect/bind 检查这些拒绝分支，不触发演练请求。

```sh
"$Q34_PYTHON" -B verify_bounded_http.py \
  robot_runs/20260911-150857-232004-bounded-mock-http \
  robot_runs/20260911-150857-873900-bounded-mock-http
```

## 用户登录官方演练后的切换（本次未执行）

用户手动登录并开启一局**演练**，确认官方服务监听 `127.0.0.1:2026`，取得该局 robot_id 后，可在上述主力命令后追加：

```sh
--mode practice --base-url http://127.0.0.1:2026 --robot-id '该局实际robot_id' --confirm-practice
```

Q3/Q4 各自使用对应问题的独立演练局；`--confirm-practice` 是用户的演练声明，HTTP API 本身不能识别演练/正式模式。缺少声明或 robot_id 时入口报错，不发请求。`--base-url` 在 practice 模式可省略，默认上述官方回环地址；没有自动登录、模式探测或正式测试开关。

practice 直接向该地址发送同一工厂策略的请求，不启动自带 mock。记录客户端响应、清除数、虚拟时间/每源时间和运行时间，不伪造不可知的真实源数/清除比例。此路径只完成装配和前置开关验证，官方兼容性尚未经实际运行验证。

本任务未编辑 client.py；工作区中其并行健壮性修改属于另一 agent。客户端公开接口保持调用方式不变。本次解决入口错位，客户端重试、时限等审计项由该并行任务处理。
