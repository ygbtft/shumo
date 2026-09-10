# macOS → Windows 官方演练环境：给接手 Agent 的部署 Handoff

> **最高优先级：只允许官方“演练测试”。没有用户明确书面许可，绝不启动、操作、探测或靠近任何“正式测试”入口、按钮或接口。本文只部署应用与机器狗运行环境；官方登录、选择演练、开启演练由用户操作。不得编写自动开启测试的路径。遇到只能通过正式测试验证的功能，停止并询问用户。**
>
> `/enter`、`/measure`、`/clear`、`/exit` 是两种测试共用的公开机器狗接口，没有独立的“演练 URL”，也没有测试类型查询接口。`session_mode="practice"` 只是操作者声明，不能证明服务端当前模式。未明确确认当前是演练会话时，不发送任何机器狗动作，也不用 `/enter` 作探活。

本文维护日期：2026-09-10。目标是让接手 agent 最短路径完成：**macOS 上复用或创建 Windows ARM64 VM → 安装官方模拟器和原生 Python → 部署统一 benchmark → 本地自检 → 用户开启演练后录制 → 回到 macOS 分析。** 本次编写仅核对资料和本地文件，没有执行 VM 安装、启动官方应用或开启测试。

## 1. 先分清两个环境，避免白搭 VM

| 工作 | 执行位置 | 是否需要 Windows |
|---|---|---|
| InProcMock、批量 Monte Carlo、策略开发、图形分析 | macOS 项目目录 | 否 |
| 本地 HttpMock、录制回放链路自检 | macOS 或 Windows | 否 |
| 官方模拟器 GUI、HttpOfficial 和演练录制 | 同一台 Windows guest 内 | 是 |
| 已录制官方 JSONL 的计时审计、差分、误差标定 | macOS | 否 |

官方模拟器只绑定 **guest 自己的 `127.0.0.1:2026`**。宿主上的 `127.0.0.1` 是宿主；guest 的 NAT IP 也不是公开机器狗服务地址。将录制器放进 guest，JSONL 经共享文件夹取回。不要为此配置端口转发、修改官方监听地址或架设代理。

先读本文件，再按需看：

- [统一 benchmark 用法](README.md)：后端、策略、录制、回放、强制压力矩阵、假设清单。
- [最初环境交接](../ENV-HANDOFF.md)：本机 VM、共享目录、session 0 等历史事实。
- [环境续验报告](../verification/REPORT.md)：Python 已安装、两版模拟器对照与证据。
- [最新官方演练记录](../practice-logs/REPORT.md)：真实演练的 HTTP/计时/延迟结果。

**以较新的证据修正旧文档的“待验证”状态。** 老交接中的“Python 待安装”和老 benchmark README 中的“没有官方演练数据”已被后续记录部分更新；不要重新做完所有旧任务。本 handoff 不要求执行那些历史任务。

## 2. 本机最快路径：现成 VM 与 Python 都已具备

2026-09-10 的已有证据如下；用户名、会话 ID、PID、IP 都要现场复核，不当成跨机器常量。

| 项目 | 本机记录 |
|---|---|
| 宿主 | Apple M5 Pro / 48 GB / macOS 27.0，arm64 |
| Parallels | Desktop 26.4.0-57513，已有授权 |
| CLI | `/Applications/Parallels Desktop.app/Contents/MacOS/prlctl` |
| VM 名称 / UUID | `Windows 11` / `{f11d8098-10fe-40d9-871e-27af1e66161e}` |
| Windows | 11 Pro 25H2，ARM64，build 26200.9168 |
| 资源 / 固件 | 4 vCPU、8 GB 内存、256 GB 动态磁盘；EFI ARM64、Secure Boot、TPM |
| 交互用户 / 会话 | `flower`；当时 Active console session 2 |
| 官方精简版 | `C:\Jammers\jammers-simulator.exe` |
| 官方备用完整版 | `C:\JammersFull\jammers-simulator-full.exe`，旁边有整个 `WebView2Runtime` |
| 原生 Python | **`C:\Python314-arm64\python.exe`，3.14.7，win-arm64** |
| 宿主中转目录 | `/Users/flower/Downloads/JammersXfer/` |
| guest 对应共享目录 | `\\Mac\Home\Downloads\JammersXfer\` |
| 项目根目录 | `/Users/flower/math/2026/B题/` |

macOS 终端先做只读盘点：

```bash
TASK_ROOT="/Users/flower/math/2026/B题"
PRL_BIN="/Applications/Parallels Desktop.app/Contents/MacOS/prlctl"
TASK_VM="Windows 11"
TASK_XFER="$HOME/Downloads/JammersXfer"

uname -m
"$PRL_BIN" list -a
"$PRL_BIN" list -i "$TASK_VM"
```

若 Parallels 服务尚未运行，用 `open -a "Parallels Desktop"`，等约 10–15 秒再查看。若现有 VM 处于 stopped/suspended 状态，用控制中心打开它或 `"$PRL_BIN" start "$TASK_VM"`；若已运行就继续使用。不要删除、重建或复位已经配置好的 VM。

VM 可用后读取 Windows 会话和 Python：

```bash
"$PRL_BIN" exec "$TASK_VM" query user
"$PRL_BIN" exec "$TASK_VM" 'C:\Python314-arm64\python.exe' --version
"$PRL_BIN" exec "$TASK_VM" 'C:\Python314-arm64\python.exe' -c 'import sys,sysconfig; print(sys.executable); print(sysconfig.get_platform())'
```

能看到原生 Python、交互桌面和现有模拟器时，跳到第 6 节部署 benchmark。先看 GUI 当前状态；如果用户已有运行中的会话，不关闭应用、不重启 VM、不发送试探请求。

## 3. 新 Mac 从零部署 VM（已有 VM 时跳过）

本指南的已验证路线是 **Apple Silicon → Parallels → Windows 11 ARM64 → Windows 的 x64 兼容层运行模拟器**。不要误选 x64 Windows ISO。Intel Mac 是另一条 x64 Windows 路线，不照搬本文 ARM64 镜像和 Python 安装器。

1. 从 [Parallels 官方下载页](https://www.parallels.com/products/desktop/download/) 安装 Parallels Desktop，完成用户自己的授权流程。
2. 打开安装助手；在 Control Center 点击 `+`，选择 **Get Windows 11 from Microsoft**，由助手下载并安装 ARM Windows。已有合适 ARM64 ISO 也可选择从镜像安装。这是 [Parallels 官方安装流程](https://kb.parallels.com/en/125375)。
3. 完成 Windows 首次设置与正常许可证流程，登录到一个真实交互桌面。本机资源配置为 4 vCPU、8 GB RAM、256 GB 动态磁盘；它是验证配置，不是声称最低要求。保持 Windows 11 所需的 Secure Boot/TPM，不做安装检查绕过。
4. 确认 Parallels Tools 已安装；没有则在 Parallels 菜单选择安装 Tools，并按安装器要求完成重启。重启只在部署阶段、没有活动演练时进行。
5. 保持默认共享/NAT 网络，开启该 VM 对宿主 Downloads 的共享，验证 guest 能访问 `\\Mac\Home\Downloads`。本机该共享入口实际可用；不要假设宿主任意目录都自动共享。
6. 等 Windows 桌面、网络和时间同步可用，再部署应用。安装或账户流程需要用户凭据时只让用户在系统 UI 输入；不要让用户把密码发到日志或命令行。

不要为了复刻环境强行替换一个已经正常工作的系统版本；先记录版本并做离线自检。新系统版本的兼容性以实际 GUI 和链路结果为准。

## 4. 传文件的统一做法：Downloads 共享 + 本地 .ps1

所有项目产物写在宿主 `mock/` 下。`Downloads/JammersXfer` 只做已明确用途的 VM 传输中转；官方安装目录与 benchmark 工作目录分离。

macOS：

```bash
mkdir -p "$TASK_XFER"
mkdir -p "$TASK_ROOT/mock/staging"
```

长 PowerShell 内容由 agent 写成 `.ps1`，先放到共享目录，再复制到 guest 本地执行。建议 `.ps1` 只写 ASCII；需要中文脚本时按 Windows PowerShell 5.1 的要求用 UTF-8 BOM。不要将长脚本塞进多层 `-Command` 引号。

假设 agent 已生成 `deploy-benchmark.ps1` 并放入中转目录，宿主调用模板如下：

```bash
"$PRL_BIN" exec "$TASK_VM" cmd.exe /c 'if not exist C:\JammersDeploy mkdir C:\JammersDeploy'
"$PRL_BIN" exec "$TASK_VM" cmd.exe /c 'copy /Y "\\Mac\Home\Downloads\JammersXfer\deploy-benchmark.ps1" C:\JammersDeploy\deploy-benchmark.ps1'
"$PRL_BIN" exec "$TASK_VM" powershell.exe -NoProfile -ExecutionPolicy Bypass -File 'C:\JammersDeploy\deploy-benchmark.ps1'
```

`ExecutionPolicy Bypass` 仅用于这次启动自写部署脚本，不修改系统全局执行策略。PS 脚本开头可用：

```powershell
$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8
```

本机曾试过宿主 HTTP 中转但 guest 无法连接；直接走已验证共享目录。不要把时间花在调整防火墙或猜测 guest IP 上。

## 5. 安装并启动官方模拟器（已安装则复用）

### 5.1 准备原始官方包

题目附件给出的下载入口：[官方发布分享目录](https://pan.baidu.com/s/1P1yfVjY0RufU93XOdzhOLw?pwd=2026)，提取码 `2026`。本机已有两个原始压缩包，当前已移动到 `archive/`，无需重复下载（旧 ENV-HANDOFF.md 的项目根目录路径已过时）：

- `$TASK_ROOT/archive/Jammers-simulator-win64.7z`：精简版，约 5.83 MiB。
- `$TASK_ROOT/archive/Jammers-simulator-full-win64.7z`：完整版，约 225.88 MiB。

优先精简版：本机它使用系统 ARM64 WebView2，进程树内存更低；已有实测不支持“精简版必然启动更快”的结论。宿主可用已安装的 `/opt/homebrew/bin/7zz` 解压原包：

```bash
/opt/homebrew/bin/7zz x "$TASK_ROOT/archive/Jammers-simulator-win64.7z" -o"$TASK_ROOT/mock/staging/slim"
cp "$TASK_ROOT/mock/staging/slim/Jammers-simulator/jammers-simulator.exe" "$TASK_XFER/jammers-simulator.exe"
```

先查看实际解压目录；发行包目录变化时按真实结构调整。历史包中精简版 exe 的 SHA-256 为 `2373b9e7af83735a04309e2983eb433ec46faf7e0b8494410ce7fded2a297c27`。这是该历史文件指纹，不能据此拒绝后来合法更新的新版本。

在 guest PowerShell 或部署脚本中，仅当目标尚未安装时复制：

```powershell
if (-not (Test-Path 'C:\Jammers\jammers-simulator.exe')) {
    New-Item -ItemType Directory 'C:\Jammers' -Force | Out-Null
    Copy-Item '\\Mac\Home\Downloads\JammersXfer\jammers-simulator.exe' 'C:\Jammers\jammers-simulator.exe'
}
Get-FileHash 'C:\Jammers\jammers-simulator.exe' -Algorithm SHA256
```

它是绿色软件，解压后运行即可。不要删除或修改旁边的 `JammersSimulatorData`，也不要从备用版覆盖现有目录。模拟器已经自行更新时，保留该状态。

精简版需要 WebView2。本机系统自带 ARM64 WebView2 已验证可用；新 VM 若缺少运行时，使用 [微软 WebView2 官方入口](https://developer.microsoft.com/en-us/microsoft-edge/webview2/) 安装适合 Windows ARM64 的 Evergreen Runtime。先验证，不主动替换正常运行的版本。

完整版只作备用：**必须整体复制解压目录**，让 `WebView2Runtime` 与 `jammers-simulator-full.exe` 同级；本机为 259 个文件、约 711.8 MB。单独复制 exe 不构成完整版安装。两版 exe 大小相同但 SHA-256 不同，不能声称只是改名。

### 5.2 GUI 必须运行在已登录的交互会话

最简单是在 Windows 桌面双击 exe。**不要直接通过普通 `prlctl exec ... jammers-simulator.exe` 启动 GUI。** 本机 `prlctl exec` 默认进入 SYSTEM/session 0，WebView2 无桌面窗口可附着，会产生约 60 秒 controller 超时；这不是 ARM 兼容性失败。

agent 必须自动启动应用时，在 guest 本地部署脚本中使用“仅手动触发”的交互计划任务。以下脚本仅启动应用，不操作登录或测试 UI；先确认当前没有任何模拟器进程。本机用户名示例是 `flower`，新机器需换成 `query user` 得到的已登录用户。

```powershell
$ErrorActionPreference = 'Stop'
$existing = @(Get-Process -Name 'jammers-simulator','jammers-simulator-full' -ErrorAction SilentlyContinue)
if ($existing.Count -gt 0) {
    Write-Output 'Simulator already running; inspect its GUI and reuse it.'
    return
}

$desktopUser = 'flower'
$taskName = 'JammersGui-' + [guid]::NewGuid().ToString('N')
$action = New-ScheduledTaskAction -Execute 'C:\Jammers\jammers-simulator.exe' -WorkingDirectory 'C:\Jammers'
$principal = New-ScheduledTaskPrincipal -UserId $desktopUser -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
$task = New-ScheduledTask -Action $action -Principal $principal -Settings $settings
Register-ScheduledTask -TaskName $taskName -InputObject $task | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Output "Manual-only GUI task: $taskName"
```

不设置定时 Trigger，因此不会在晚上某个时刻又启动应用。电池设置来自本机实际故障：任务可能显示排队但因电池供电被禁止启动。相关参数依据 [Microsoft 的交互 Principal](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtaskprincipal?view=windowsserver2025-ps) 与 [任务设置文档](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtasksettingsset?view=windowsserver2025-ps)。这是按验证教训整理的新启动配方，本文编写时没有在 guest 执行它。

确认 GUI 正常后，等用户正常退出应用，再删除本次自建任务：`Unregister-ScheduledTask -TaskName <刚输出的任务名> -Confirm:$false`。不要枚举删除其他任务，不杀全局 WebView2 进程，不清空启动日志。

只读验证：

```powershell
Get-Process -Name 'jammers-simulator','jammers-simulator-full' -ErrorAction SilentlyContinue | Select-Object Id,SessionId,ProcessName
Get-NetTCPConnection -LocalPort 2026 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess
```

宿主截图：

```bash
mkdir -p "$TASK_ROOT/mock/results/deployment"
"$PRL_BIN" capture "$TASK_VM" --file "$TASK_ROOT/mock/results/deployment/windows-gui.png"
```

看见真实渲染出的登录页或用户界面才算 GUI ready；端口 Listen、Environment created 日志、空 MainWindowTitle 都不能单独判断成败。检查屏幕只用于确认状态，不能点击正式测试区域。

## 6. 安装原生 ARM64 Python 与部署 benchmark

### 6.1 Python 已存在则直接跳过安装

本机使用 **`C:\Python314-arm64\python.exe`**。历史安装选择了 `Include_launcher=0`，因此 **不假定 `py -3` 可用**，后续统一用绝对路径。

新 VM 使用 [Python 官方 Windows ARM64 安装器](https://www.python.org/downloads/windows/)，本机已验证版本为 3.14.7；本机已缓存安装器于 `$TASK_XFER/python-3.14.7-arm64.exe`。Python 官方下载页提供 ARM64 与 x64 两类安装器，注意选 ARM64。不要下载 macOS 安装包放进 guest。

安装的 PowerShell 示例（管理员或 agent 的 SYSTEM 部署会话执行，先复制安装器至本地）：

```powershell
$ErrorActionPreference = 'Stop'
$pythonExe = 'C:\Python314-arm64\python.exe'
if (-not (Test-Path $pythonExe)) {
    New-Item -ItemType Directory 'C:\JammersDeploy' -Force | Out-Null
    $installer = 'C:\JammersDeploy\python-3.14.7-arm64.exe'
    Copy-Item '\\Mac\Home\Downloads\JammersXfer\python-3.14.7-arm64.exe' $installer
    $signature = Get-AuthenticodeSignature $installer
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') {
        throw 'Unexpected Python installer signature'
    }
    $argsList = @('/quiet','/norestart','InstallAllUsers=1','TargetDir=C:\Python314-arm64','PrependPath=1','Include_launcher=0','Include_test=0')
    $install = Start-Process $installer -ArgumentList $argsList -Wait -PassThru
    if ($install.ExitCode -notin @(0,3010)) { throw "Installer exit code: $($install.ExitCode)" }
    if ($install.ExitCode -eq 3010) { throw 'Installer requests a Windows restart; complete it before continuing deployment.' }
}
& $pythonExe -c "import sys,sysconfig; print(sys.executable); print(sys.version); print(sysconfig.get_platform())"
if ($LASTEXITCODE -ne 0) { throw 'Python verification failed' }
& $pythonExe -m pip --version
if ($LASTEXITCODE -ne 0) { throw 'pip verification failed' }
```

当前缓存安装器的 SHA-256：`9a3fe120cc81bc2cb099550f794d8356811f96a86c7f438519243c3485db928d`。要求新下载与发布页对应；版本升级时不能继续套用这个历史哈希。安装后应显示 `win-arm64`。不要求 guest 为了纯 HTTP 录制编译 NumPy 或 matplotlib。

### 6.2 从 macOS 生成纯源码包

在宿主项目根目录执行；若 mock 虚拟环境尚未创建，先 `python3 -m venv mock/.venv`。打包本身不需要第三方依赖：

```bash
cd "$TASK_ROOT"
mock/.venv/bin/python -m mock.bundle
cp mock/dist/mock-core.zip "$TASK_XFER/mock-core.zip"
```

ZIP 包含 `mock/` 源码、测试、示例配置及依赖声明，不携带 macOS `.venv`、历史结果、官方应用或本地参赛队配置。Windows 必须新建自己的 venv。

### 6.3 guest 解压并做离线验收

每次选择新的部署目录；示例第一次用 `C:\JammersBenchmark`。不要与历史 `C:\JammersBench` RTT 脚本目录混淆，也不要覆盖正在运行策略的源码。

```powershell
$ErrorActionPreference = 'Stop'
$benchRoot = 'C:\JammersBenchmark'
if (Test-Path $benchRoot) { throw 'Choose a fresh benchmark deployment directory or deliberately reuse the existing one.' }
New-Item -ItemType Directory $benchRoot | Out-Null
Copy-Item '\\Mac\Home\Downloads\JammersXfer\mock-core.zip' "$benchRoot\mock-core.zip"
Expand-Archive -LiteralPath "$benchRoot\mock-core.zip" -DestinationPath $benchRoot
Set-Location $benchRoot
& 'C:\Python314-arm64\python.exe' -m venv mock\.venv
if ($LASTEXITCODE -ne 0) { throw 'venv creation failed' }
& '.\mock\.venv\Scripts\python.exe' -m mock.validate --output mock\results\guest-offline-check
if ($LASTEXITCODE -ne 0) { throw 'Offline backend validation failed' }
```

期望自检打印 `deterministic_zero_difference: true`、`official_contacted: false`，并保存 HTTP 录制、回放和差分文件。它在随机本地端口启动自己的 mock，**不会访问官方 2026 端口**。这一步无需安装 NumPy，不受科学计算 wheel 兼容性影响。

只有需要在 guest 做统计/标定时才安装：

```powershell
& '.\mock\.venv\Scripts\python.exe' -m pip install -r mock\requirements.txt
```

绘图另用 `requirements-viz.txt`；开发测试另用 `requirements-dev.txt`。ARM64 wheel 缺失时，优先把统计/绘图放回 macOS，不为纯录制链路折腾编译器或更换整个 VM。完整 `mock` 套件在 Windows 的部署验收必须实际记录，不能拿历史 RTT 客户端 smoke 测试冒充。

## 7. 配好 HttpOfficial，再等待用户手动开始演练

先在 guest **交互用户的 PowerShell** 中打开部署根目录。配置文件只存参赛队号，不存登录密码、姓名或手机号。Windows PowerShell 5.1 的 `Set-Content -Encoding UTF8` 会添加 BOM，当前 Python 配置读取不接受该 BOM；按下例明确写无 BOM UTF-8：

```powershell
Set-Location 'C:\JammersBenchmark'
$teamId = Read-Host 'Logged-in team ID'
$config = [ordered]@{
    kind = 'http_official'
    base_url = 'http://127.0.0.1:2026'
    robot_id = $teamId
    timeout = 5
    retries = 2
    session_mode = 'practice'
}
$configPath = Join-Path (Get-Location) 'mock\configs\backend-official.local.json'
[IO.File]::WriteAllText($configPath, ($config | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
```

这里 `robot_id` 必须逐字节等于当前登录参赛队号。配置只换后端，策略无需改代码。

**到此即可报告“部署就绪”。** 接手 agent 不能为了把状态改成“测试通过”而代替用户开启测试。用户在模拟器中完成登录、手动选择**问题 3 或问题 4 的演练测试**、启动并等 5 秒倒计时结束，明确确认当前界面为演练且接口已开放后，才运行：

```powershell
Set-Location 'C:\JammersBenchmark'
$runTag = 'practice-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
& '.\mock\.venv\Scripts\python.exe' -m mock.run --backend-config mock\configs\backend-official.local.json --strategy mock.strategy:Baseline --record "mock\results\$runTag.jsonl" --output "mock\results\$runTag-run.json"
Write-Output "Recorded run tag: $runTag"
```

该命令会实际 `/enter`、运行策略并通常 `/exit` 结束本局，不是只读连接检查。不要与 RTT 采样器或另一只机器狗同时运行。发生不明状态时查看界面与本地记录，不盲目反复运行新进程；同动作重试由后端复用原 ID 处理。JSONL 文件不得覆写。

25 分钟测试窗口从倒计时结束开始；`/enter` 后最多 20 分钟，以较早者截止。尽量在窗口头 5 分钟入场；使用响应中的 `remaining_real_duration_s`。联网和与服务器时差 ≤60 秒由官方正常开测流程检查。根据附件，本届北京时间 2026-09-13 17:30 后不再开启新的演练；不要更改时钟、修改应用或绕过截止检查。

## 8. 导出日志，回 macOS 做校准与批量评测

在同一 guest PowerShell 中，使用上一步保留的 `$runTag`：

```powershell
$exportDir = "\\Mac\Home\Downloads\JammersXfer\practice-export\$runTag"
New-Item -ItemType Directory $exportDir | Out-Null
Copy-Item "mock\results\$runTag.jsonl" $exportDir
Copy-Item "mock\results\$runTag-run.json" $exportDir
```

从 GUI 记录该**演练**的案例编码、干扰源总数及全向/定向数量，与 JSONL 关联；不知道的真值写 unknown/null，清除点不等于源精确坐标。账户密码、登录凭据不进入导出包。

macOS 将对应目录复制到项目 `mock/results/practice-import/`，保留每局独立目录，再做离线计时审计：

```bash
cd "$TASK_ROOT"
mkdir -p mock/results/practice-import
cp -R "$TASK_XFER/practice-export/." mock/results/practice-import/
# 用刚导入的实际文件名替换以下占位符
mock/.venv/bin/python -m mock.differ "mock/results/practice-import/<runTag>/<runTag>.jsonl" --output mock/results/practice-timing-audit.json
```

`mock.differ` 单份录制即可核对虚拟计时与幂等规则；完整 HTTP/mock 判定差分需要有证据支持的同场景重建，不能把随机场景结果硬对齐官方观测。误差标定需要位置不确定度和留出测量，详细步骤见 [README 标定部分](README.md#从演练观测标定而不是虚构真值)。

在 macOS 跑策略的强制压力矩阵：

```bash
mock/.venv/bin/python -m pip install -r mock/requirements.txt
mock/.venv/bin/python -m mock.evaluator --runs 100 --workers 4 --seed 202600 --config mock/configs/q4.json --output mock/results/new-q4-benchmark
```

这是至少 15 个组合 × 100 局；**官方演练不用于几千局的自动批量重开**。大批量搜索放 mock，演练只在用户确认的单局内作验证。可视化依赖单独安装后加 `--plot`。

## 9. 现有演练证据与复用边界

已经存在 [practice-logs/REPORT.md](../practice-logs/REPORT.md)：2026-09-10 问题 4 演练，由另一任务在 guest ARM64 Python 采集 1367 条请求，全部 HTTP 200/accepted=true；总现实约 2.461 秒，最终虚拟 30115.333001 秒。界面给出 15 个源，其中全向 5、定向 10，脚本清除了 10 个。该脚本用于规则与延迟验证，不能当成本项目 baseline 的成绩。

可以直接读取这份旧录制做离线研究，**不需要为相同事实重新开演练**。它的计时复核是浮点理论增量与实际增量的舍入一致性，不能直接等同于本框架逐微秒整数审计或隐藏场景完全标定。精确阈值边界、长时超时仍未覆盖。

旧录制格式与 `mock.backends.recording` 不完全相同：有完整 request/response/http_status，但没有 `run_id`/`backend`；其 sequence 从 0 开始。旧记录的离线复核先使用 [audit_recording.py](../practice-logs/audit_recording.py)。如需送入标定器，**另存规范化副本**，为每次演练补充唯一 run_id、backend=`http_official` 等来源元数据，保留原请求 ID 和原始响应，绝不修改原录制文件。

该次测量显示复用连接和每笔新建连接有明显 RTT 差异。当前 `HttpOfficial` 使用 `urllib.request`，不是旧采集脚本的持久连接实现；不要把旧报告约 0.16ms 的复用连接中位数直接当作当前 adapter 的基准，也不能在没有原生 x64 Windows 对照时计算 Prism 独有减速。

## 10. 常见故障 → 下一步

| 现象 | 接手 agent 的处理 |
|---|---|
| 找不到 Parallels 服务 | 打开 Parallels 应用，等待短时间后再次 list；不重建 VM。 |
| GUI 在 session 0，约 60 秒后退出 | 停止重复错误启动；改用已登录桌面或本文 Interactive 任务。 |
| GUI 任务排队但不运行 | 检查交互用户 Active、无 Trigger 的任务设置和电池运行限制；只调整本次自建任务。 |
| 端口监听但白屏/标题为空 | 查看完整截图和 startup.log；不要仅凭进程/端口认定 ready。 |
| `\\Mac\Home` 下找不到项目 | 本机共享主要是 Downloads/Desktop/Documents；改用 Downloads/JammersXfer。 |
| `py` 找不到 | 本机没安装 launcher；用 `C:\Python314-arm64\python.exe`。 |
| `Unexpected UTF-8 BOM` | 配置用 UTF8Encoding(false) 重写；不要改记录的语义字段。 |
| `No module named mock` | cwd 应为 `C:\JammersBenchmark`，它的下一层才是 mock；不要 cd 到包内部。 |
| NumPy/matplotlib 安装受阻 | guest 先跑标准库录制/self-check；统计、绘图放回 macOS。 |
| `/enter` 断连 | 可能非演练开放期、倒计时未完或本局结束；先人工确认界面，不刷请求。 |
| `accepted=false` | 检查队号逐字节匹配、字段、动作顺序；virtual_time_s=0 不代表当前虚拟时钟归零。 |
| HTTP 409 | 检查并发客户端、同 ID 改内容；保证串行，网络重试复用原 ID。 |
| 已有活动测试或模式不明 | 保持现场，不停止进程、不重启、不探活；等待用户确认演练状态。 |

**不要复用历史 `run_interactive.ps1` 的清理逻辑。** 该旧脚本包含强杀全部 WebView2 和删除启动日志；本文用无清理副作用的启动配方替代。`compare_startup.ps1` 等启动对照脚本也不属于快速部署必要步骤。

## 11. Agent 的完成标准与交接输出

按实际进度报告，避免将“能安装”说成“官方已校准”：

1. **环境就绪**：现有 VM 信息已复核；Windows 有交互桌面；模拟器正常渲染；2026 端口由预期进程监听；Python 可执行。
2. **benchmark 就绪**：源码落在独立目录；guest venv 正确；`mock.validate` 离线通过；无 BOM 的后端配置准备好。此时没有用户开启演练也可以完成部署交付。
3. **演练链路验证**：仅在用户明确开启演练后，保存该局 JSONL、运行结果、GUI 案例数量信息；记录 accepted/错误情况和停止原因。
4. **macOS 分析可用**：日志已回收、离线审计有产物；批量模拟与真实演练结果分开标注。

最终交接至少写：VM 名称、Windows/Python 版本、交互用户名/会话、模拟器路径、benchmark 路径、精确启动命令、日志位置、离线验证结果、是否实际做过演练，以及尚待用户操作的事项。所有“已验证”都附本次证据路径；不要求重复历史完整版本对照，不触碰正式测试。
