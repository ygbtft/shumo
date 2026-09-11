# 模拟器环境续验结果

验证时间：2026-09-10 20:46—21:00，北京时间。开始前完整阅读 `ENV-HANDOFF.md`；按完整版对照、采样脚本、guest Python 的顺序推进。

## 1. 完整版对照：能运行，精简版省内存；速度优势尚不能成立

VM 始终为 `Windows 11`，UUID `{f11d8098-10fe-40d9-871e-27af1e66161e}`。未修改 VM 配置、Parallels 设置、Windows/WebView2 版本，未重启或新建 VM。所有模拟器启动都使用 `schtasks /it /ru flower`，实测 session_id=2。只在登录页进行启动对照，没有登录或启动任何官方测试。

完整版从指定原始压缩包解压，经 Downloads 共享目录整体复制到 `C:\JammersFull`；`WebView2Runtime` 与 exe 同级。共 **259 文件、711,808,082 B**，所有文件源/目标 SHA-256 一致。压缩包 SHA-256 与交接文档一致。证据：[full-copy.json](evidence/full-copy.json)。

### 内存与启动记录

内存采用每次启动后 60—90 秒的样本中位数，单位 MiB（2²⁰ B）。进程树只含当前模拟器及后代，排除其它程序的 WebView2。

| 项目 | 完整版首次运行 | 完整版再次运行 | 精简版再次运行 |
|---|---:|---:|---:|
| 首次观测到进程（秒） | 2.429 | 0.062 | 0.067 |
| 首次观测到 2026 监听（秒） | 2.458 | 0.077 | 0.095 |
| 首次观测到 WebView2 子进程（秒） | 3.072 | 0.632 | 0.667 |
| 主进程 Working Set | 101.66 | 49.00 | 49.33 |
| 进程树 Working Set 合计 | 670.14 | 595.55 | 411.39 |
| 进程树 Private Bytes 合计 | 458.52 | 336.23 | 191.51 |
| 最后样本 WebView2 子进程数 | 6 | 7 | 6 |
| GUI 截图 | 约 11 秒及 145 秒均白屏 | 登录页完整 | 登录页完整 |
| 90 秒时仍运行、监听 | 是 | 是 | 是 |

原始证据：每个目录均有 `summary.json`、`samples.csv`、进程树及启动日志：[full-first](evidence/full-first/summary.json)、[full-repeat](evidence/full-repeat/summary.json)、[slim-repeat](evidence/slim-repeat/summary.json)。GUI：[首次完整版白屏](evidence/jammers-full-after.png)、[再次完整版成功](evidence/jammers-full-repeat.png)、[精简版成功](evidence/jammers-slim-repeat.png)。截图时间见 [screenshot-times.json](evidence/screenshot-times.json)。

额外进行了各一次定时截图复测（30 秒进程观察）：完整版在任务启动后约 **4.8 秒**的截图已显示完整登录页；精简版约 **4.9 秒**的截图只显示顶栏、约 **9.9 秒**截图显示完整登录页。更早的图片分别是桌面和黑屏。这些只是截图观测的上界，不是精确 GUI ready 事件；也可能包含桌面合成/捕获延迟，不能据此断言完整版更快。证据：[完整版定时帧](evidence/full-visual-frames.json)、[完整版登录页](evidence/full-visual-8s.png)、[精简版定时帧](evidence/slim-visual-frames.json)、[精简版登录页](evidence/slim-visual-13s.png)，对应 guest `launch_utc` 位于各 `*-visual/summary.json`。宿主/guest 时差界限见第 4 节。

计时起点为 `schtasks /run` 前；轮询约 0.5—0.7 秒一次。首次运行不是控制过文件缓存/Prism 缓存的严格冷启动，后续是热启动，且各版本分处不同数据目录。不要把首次与热启动时间直接相除推导 Prism 减速。所有 Working Set 相加可能重复计算共享页，因此同时提供 Private Bytes。

**支持的结论：** 登录页稳定状态下，完整版进程树 Working Set 比精简版多约 **184 MiB（45%）**，Private Bytes 多约 **145 MiB（76%）**；主进程约 49 MiB，差异主要在子进程。优先精简版有实际内存证据。完整版也可作为本机的备用启动方案，但首次长时间白屏原因未定位，尚未验证登录后完整测试能力。

**未证实的结论：** 精简版一定启动更快、`/measure` 或 `/clear` 一定更快。两版热启动端口时间近似，GUI 截图没有显示精简版固定速度优势，实际请求尚未开测。

### 运行时、日志与交接文档纠正

- 完整版实际使用 `C:\JammersFull\WebView2Runtime\msedgewebview2.exe`，版本 **151.0.4129.86**，Windows 进程架构查询为 **0x8664（x64）**。
- 精简版使用系统 WebView2 **152.0.4191.66**，对应进程架构 **0xAA64（ARM64）**；模拟器本身两版均为 x64。证据：[full-architecture.json](evidence/full-architecture.json)、[slim-architecture.json](evidence/slim-architecture.json)。这印证了完整版额外使用 x64 WebView2 的判断。
- 三次完整版、两次精简版启动日志均只记录正常启动及 WebView2 Environment 创建成功，**没有** `fixed WebView2 runtime version does not match the build manifest`，没有 controller 超时。首次白屏说明仅 Environment 成功不足以认定 GUI 已渲染；原因未查明，未修改任何运行时参数。
- 两份 exe 都是 18,768,896 B，**但不是同一字节内容改名**。精简版 SHA-256 为 `2373b9e7af83735a04309e2983eb433ec46faf7e0b8494410ce7fded2a297c27`；完整版为 `110542502401761b81f701ca1a866092e38d4ac290fa025bf18aed73ff8e9628`。源文件和 guest 文件一致。因此本次是两个官方发行包的整体对照，不能把全部差异单独归因于 CPU 模拟层。

架构识别使用只读 Windows [GetProcessInformation / PROCESS_MACHINE_INFORMATION](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/ns-processthreadsapi-process_machine_information)，没有反汇编、调试、读取模拟器进程内存或绕过校验。本机 `IsWow64Process2` 对 x64 和 ARM64 都返回 process_machine=0，不能单独依赖这个值判断原生架构。

## 2. 延迟脚本已部署，官方 RTT 待用户开演练

源码：[benchmark_api.py](benchmark_api.py)。已复制到 guest **`C:\JammersBench\benchmark_api.py`**，仅依赖 Python 标准库。详细操作与口径：[README.md](README.md)。

脚本严格串行，为每个动作生成新 request_id；默认每个接口 10 次预热、200 次采样，保存逐请求 JSONL 与 p50/p95/p99 汇总，并按 `measure_result` / `clear_result` 拆分。异常、拒绝、无响应不混入成功 RTT。使用 `/enter` 的实际现实时间余量和虚拟时间限额；出现不确定结果立即停，不自动重试或推进下个新动作。

在宿主与 **guest 原生 ARM64 Python** 上，用独立回环随机端口的协议 mock 验证了：成功串行流程、逐次新建连接、accepted=false、无 HTTP 响应的断连、现实截止、HTTP 429；另验唯一 ID、精确字段、预热排除、分位数和 `--practice` 开关。全部通过。mock 只验证客户端协议控制流程，不是物理环境求解器，未触碰官方 2026 端口。guest 证据：[benchmark-smoke.json](evidence/benchmark-smoke.json)，复核脚本保存在 guest `C:\JammersBench\jammers_benchmark_smoke.py` 及宿主 Downloads 中转目录。

用户完成登录、选择演练且接口就绪后，在 Windows PowerShell 执行：

```powershell
& C:\Python314-arm64\python.exe C:\JammersBench\benchmark_api.py --practice --count 200 --warmup 10 --output C:\JammersBench\results-slim-01
```

随后按提示输入参赛队号。脚本正常结束会 `/exit` 结束本次演练；输出目录必须是新目录。

**仍未知：官方 `/measure`、`/clear` 的 p50/p95，以及实际策略能否在 20 分钟内完成。** 本次没有登录信息，按用户要求仅做好脚本，没有开始官方测试。未来测得的是这套 VM 的端到端 RTT；没有原生 x64 Windows 对照就无法分离 Prism 自身开销。不能用 mock 延迟代替官方延迟。

## 3. Python ARM64 原生安装成功

使用 [Python 官方 3.14.7 发布页](https://www.python.org/downloads/release/python-3147/) 的 ARM64 installer；官方将 Windows ARM64 包标注为 Experimental。本机实际安装和标准库验证成功。

- 安装位置：**`C:\Python314-arm64\python.exe`**，所有用户可用，添加 PATH；未安装额外 Python launcher，未重启 Windows。
- 安装器退出码 **0**，SHA-256 与官网一致：`9a3fe120cc81bc2cb099550f794d8356811f96a86c7f438519243c3485db928d`；Authenticode **Valid**，签名主体 Python Software Foundation。证据：[python-installer.json](evidence/python-installer.json)，完整安装日志保存在 `evidence/python-install*.log`。
- `sys.version` 显示 **MSC v.1944 64 bit (ARM64)**，`sysconfig.get_platform()` 为 **win-arm64**，Windows 进程架构与 native_machine 均为 **0xAA64**。证据：[python-inventory.json](evidence/python-inventory.json)。
- pip **26.2.1** 可运行；SSL、SQLite 可导入；HTTP 客户端与 mock 六种场景在 guest 上通过。

Python 机器狗可以直接连接本机回环，不需要宿主转发。新开的 PowerShell 可使用 PATH；为避免已有终端未刷新，给出的命令采用绝对路径。

## 4. 时间和最终状态

三次采样以宿主调用前后的时间包夹 guest UTC 时间戳。最短调用测得 guest 相对宿主偏差为 **+419 ±487 毫秒**，即约 **[-68,+906] 毫秒**，因此宿主/guest 相差小于 1 秒，远低于 60 秒阈值。没有修改系统时钟。证据：[time-sync.json](evidence/time-sync.json)。这只验证宿主与 guest 一致，**不等于已验证官方认证服务器时钟**；真正开测的服务器校时结果仍以 GUI 为准。

最终保留精简版登录页，PID **4320**、session **2**；`127.0.0.1:2026` 和 `::1:2026` 均由该 PID 监听。完整版已停止，临时对照计划任务均已删除，官方文件哈希保持不变。证据：[final-state.json](evidence/final-state.json)、[最终截图](evidence/jammers-final.png)、[VM 最终配置](evidence/vm-config-after.txt)。

本次所有新资产仅为完整版独立目录、Python 安装、验证脚本与证据。未逆向、篡改或绕过模拟器，未使用宿主 HTTP 中转，未改变共享设置。
