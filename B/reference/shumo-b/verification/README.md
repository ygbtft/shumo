# Windows ARM64 模拟器验证与演练 RTT 采样

本目录不修改模拟器。环境与历史结论见上一级 `ENV-HANDOFF.md`；本次结果见 `REPORT.md`。

## 用户登录后运行

1. 在 Windows 的精简版模拟器中自行登录，选择**演练测试**，等待倒计时结束、机器狗接口就绪。尽量在 25 分钟窗口开始后 5 分钟内运行。
2. 在 **Windows PowerShell** 中执行以下命令，按提示输入与当前登录完全一致的参赛队号：

```powershell
& C:\Python314-arm64\python.exe C:\JammersBench\benchmark_api.py --practice --count 200 --warmup 10 --output C:\JammersBench\results-slim-01
```

`--practice` 表示操作者已确认选择演练；接口不提供测试类型识别能力。脚本不负责登录、注册或开始测试。不要在正式测试中使用该采样流程；它会实际执行动作并在正常完成后调用 `/exit` 结束本局。

## 采样定义

- 默认依次执行 `/enter`、10 对预热、200 对正式采样、`/exit`；每对是 `/measure` 后 `/clear`。每条完整响应收完后才发送下一条，永不并发。
- 默认坐标 `(0,0)`，频道按 1..20 循环。请求合法但不是求解策略；每次动作都会增加虚拟时间，清除也可能成功。默认 422 个请求（含预热和进入/退出），采样分位数每个接口最多 200 条。
- RTT 用单调高精度计时，从发送 HTTP 到完整响应体读取完成，包括连接建立（若需要），不含 JSON 编解码、文件日志和策略计算。默认复用连接；`--connection new` 每次建连，可在另一局演练中与附件示例的连接方式对照。
- 用 `/enter` 返回的 `remaining_real_duration_s` 计算保守截止时间；默认预留 10 秒，按 5 秒请求超时判断是否还能发新动作，同时检查虚拟时间余量。不会固定假定完整 1200 秒。
- 每个新动作使用唯一 request_id。HTTP 非 200、accepted 非 true、无 JSON、断连、超时均保存证据后停止，不自动重试，不继续发送新动作。这样不会把未知是否执行的动作误当成未执行。需人工查看 GUI，再另开一局；不要在同一局盲目重跑脚本。
- 正常提前停在预算线前时会尝试 `/exit`；已无时间、连接故障或异常中止后不发送 `/exit` 查询原因。

输出目录必须不存在，以免覆盖旧样本：

- `requests.jsonl`：逐请求记录路径、payload、完整响应/错误、RTT、预热/采样标记，每次 flush。
- `summary.json`：成功采样的 p50/p95/p99/mean/max、样本数、结果类型分组、错误计数、运行环境和停止状态。无信号与方向响应、清除成功与无目标分别统计。没有某类结果就没有该类测量，不能用无目标的延迟冒充清除成功延迟。

不需要 pip 安装任何依赖。`--count` 可增加到 10000，但建议先查看默认样本与输出大小，再决定是否增加，避免无意义地扩大官方加密日志。

这些数据测量的是本 VM 中的端到端请求耗时。**没有原生 x64 Windows 的同版、同案例基线，就不能计算 Prism 独有开销或减速倍数。** 20 分钟是否足够，还要计入真实策略的计算、文件操作及尾部延迟；不能把 `1200000/p95` 当作保证可完成的动作数。

## 复核工具

- `copy_full.ps1`：整体复制官方完整版至 `C:\JammersFull`，逐文件 SHA-256 比对。
- `compare_startup.ps1`：仅在未登录、无活动测试时使用。关闭现有模拟器进程树，以 `schtasks /it /ru flower` 启动指定版本，采集会话、进程树内存、端口与原始日志。保留旧日志副本，不改模拟器文件。
- `capture_startup.py`：宿主执行，调用上述 guest 脚本并按时间截图；包含原进程停止和任务创建开销，GUI 时间应以 guest `launch_utc` 对齐图片时间。
- `process_architecture.ps1`：通过 Windows `GetProcessInformation(ProcessMachineTypeInfo)` 查询进程架构，不读取模拟器代码或内存。`IsWow64Process2` 在本机对 x64 和 ARM64 都返回 process_machine=0，单独用它不能区分两者。
- `python_inventory.py`：检查 Python 构建架构、Windows 进程架构、SSL 和 SQLite。
- `guest_time.ps1`：只读取 UTC 时间戳，不修改时钟。

长 PowerShell 脚本先经 `\\Mac\Home\Downloads\JammersXfer` 复制到 guest 本地后执行；GUI 始终启动在 session 2。无须改 VM 配置、共享目录或 Parallels 设置。
