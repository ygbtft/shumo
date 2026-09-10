# B 题模拟器运行环境 —— 交接文档

面向：接手继续验证 B 题模拟器运行方法的 agent
撰写时间：2026-09-10 20:45 (UTC+8)
状态：**模拟器已在 Apple Silicon 上成功跑通并渲染出登录界面**，剩余验证项见文末

续验（2026-09-10 21:00）：完整版对照、演练 RTT 脚本、guest ARM64 Python 安装已完成，详见 [verification/REPORT.md](verification/REPORT.md)。完整版能渲染登录页但首启曾长时间白屏；精简版省内存，启动速度优势未证实。两份 exe 等大但 SHA-256 不同，不能视为同一文件改名。官方 RTT 仍待用户登录后开演练测量。

---

## 0. 一句话结论

官方只发布 Windows x64 版模拟器，没有 mac 版；但通过 **Parallels Desktop + Windows 11 ARM64 + Prism x64 模拟**已完整跑通，
**5.83 MB 精简版即可**，用系统自带的 ARM64 WebView2，无需 225 MB 完整版。

---

## 1. 精确环境清单（务必保持一致）

### 宿主

| 项 | 值 |
|---|---|
| 机器 | Apple M5 Pro，48 GB RAM，18 逻辑核 |
| 系统 | macOS 27.0 (build 26A428)，arm64 |
| Parallels Desktop | 26.4.0-57513，license ACTIVE / business / unlimited |
| prlctl 路径 | `/Applications/Parallels Desktop.app/Contents/MacOS/prlctl` |
| 7z 工具 | `/opt/homebrew/bin/7zz` |

Parallels 服务如果起不来（`prlctl` 报 *Unable to connect to Parallels Service*），
执行 `open -a "Parallels Desktop"` 后等约 12 秒即可恢复，不需要重启 Mac。

### 虚拟机

| 项 | 值 |
|---|---|
| 名称 | `Windows 11` |
| UUID | `{f11d8098-10fe-40d9-871e-27af1e66161e}` |
| 系统 | Windows 11 专业版 25H2，build **26200.9168**，**ARM64**，简体中文 |
| 安装 ISO | `/Users/flower/Downloads/26200.9168.260809-0632.25h2_ge_release_svc_refresh_CLIENTCONSUMER_RET_A64FRE_zh-cn.iso` |
| 内存 / 磁盘 | 8192 MB / 262144 MB（expanded） |
| 固件 | `efi-arm64`，Secure Boot on |
| TPM | 已启用，类型 `crb`（Win11 硬性要求） |
| 网络 | net0 = shared(NAT)，virtio；**guest 10.211.55.4，宿主 10.211.55.2，网关 10.211.55.1** |
| Parallels Tools | 已安装，26.4.0-57513 |
| 交互用户 | `flower`，console **session 2**，Active |
| WebView2 运行时 | **ARM64** 152.0.4191.66（系统自带，随 Edge 一起） |

`prlctl list -i "Windows 11"` 可复核以上全部字段。

---

## 2. 模拟器本体

### 官方分发（百度网盘）

链接 `https://pan.baidu.com/s/1P1yfVjY0RufU93XOdzhOLw?pwd=2026`，目录 `/CUMCM2026B`，**只有 4 个文件，全部 Windows**：

| 文件 | 大小 |
|---|---|
| `Jammers-simulator-win64.7z` | 5.83 MB（精简版） |
| `Jammers-simulator-full-win64.7z` | 225.88 MB（完整版） |
| `模拟器操作演示.mp4` | 124.64 MB |
| `先读下载说明.pdf` | 0.24 MB |

**没有任何 darwin / macos / linux 构建。**

### 本地已有文件

| 路径 | 说明 |
|---|---|
| `/Users/flower/math/2026/B题/Jammers-simulator-win64.7z` | 精简版，6,109,513 B |
| `/Users/flower/math/2026/B题/Jammers-simulator-full-win64.7z` | 完整版，236,850,965 B，sha256 `4ef8c5d054c6841b32871ca0e0a571fbf4df931ce6e46d85dbd732c48a90e2cf` |
| `/tmp/jsim/Jammers-simulator/jammers-simulator.exe` | 精简版解出的 exe，18,768,896 B |
| `/Users/flower/Downloads/JammersXfer/` | 宿主侧中转目录（见第 4 节） |

### 二进制事实（逆向 strings + `go version -m` 得到）

- PE32+ x86-64 GUI，**Go 1.27.1 + Wails v3.0.0-beta.18**
- 模块路径 `jammers/client`，`GOOS=windows GOARCH=amd64`，`CGO_ENABLED=1`，`-tags=desktop,production`
- `vcs.revision=4395ac09f16291cdae9b37d97aafb9e244e1e5c3`，`vcs.time=2026-09-09T14:45:58Z`，`vcs.modified=true`
- 依赖含 `modernc.org/sqlite`、`golang.org/x/crypto`、`go-ole`、`webview2/pkg/edge`
- 内嵌自检字符串 **`build manifest target must be windows/amd64`** —— 官方刻意锁定平台
- 官方服务器 **`https://cumcm2026b.shumo.net`**（纯 API 后端，所有网页路径均返回 404 text/plain）

### 完整版 vs 精简版（已验证）

完整版解开后是 **259 个文件 / 18 个目录 / 解压 711 MB**：
同样大小的 18,768,896 B exe（名为 `jammers-simulator-full.exe`，续验确认哈希与精简版不同）+ 一整套**固定版本 x64 WebView2 运行时**
（`WebView2Runtime/` 下有 `msedge.dll` 342 MB、`msedgewebview2.exe`、`prefs_enclave_x64.dll` 等）。

**在 ARM Windows 上建议优先用精简版**：它调用系统原生 ARM64 WebView2，
而完整版会把整个 x64 Chromium 也压进 Prism 模拟层，理论上更慢、内存更高。
完整版的价值是在没有 Evergreen WebView2 的机器上兜底。

---

## 3. 已验证事实（含证据）

1. **精简版能跑起来**。在 session 2 中启动后持续存活 75 秒以上无异常退出，常驻内存约 53 MB。
2. **跨架构 WebView2 可用**。x64 宿主进程成功使用系统 ARM64 WebView2 152.0.4191.66，
   拉起 12 个 `msedgewebview2.exe` 子进程，`startup.log` 只有
   `[WebView2] Environment created successfully`，无后续报错。
3. **GUI 完整渲染**。截图确认显示「无线电干扰源环境模拟器」标题栏、CUMCM 会徽、
   「参赛队身份认证 / 登录模拟器」卡片、登录/注册 Tab、参赛队号与密码输入框、右上角「未登录」。中文字体正常。
4. **HTTP 接口监听正常**。`127.0.0.1:2026` 与 `::1:2026` 均处于 Listen。
5. **未开测时的行为符合附件 2 文档**。此时 POST `/enter` 得到「连接被直接关闭、无 JSON 体」，
   与附件原文「接口尚未开放……连接可能被直接关闭，此时没有 JSON 体」完全吻合。
6. **数据目录自动生成**：`C:\Jammers\JammersSimulatorData\`，含
   `formal-statistics-queue.sqlite3`、`practice-statistics-queue.sqlite3`、`upload-queue.sqlite3`（均带 -shm/-wal）与 `startup.log`。

---

## 4. 关键坑（**这几条必须遵守，否则会得到假的失败结论**）

### 4.1 session 0 陷阱（最重要）

`prlctl exec` 以 **NT AUTHORITY\SYSTEM 在 session 0**（services，Disc，无桌面）运行。
在那里启动模拟器，WebView2 的 **controller 会因为没有可附着的桌面窗口而超时**，60 秒后进程崩溃，
`startup.log` 报：

```
[WebView2 Error] timed out after 1m0s waiting for the WebView2 controller;
                 the WebView2 runtime did not complete initialisation
```

**这是假阴性，不要据此判定架构不兼容。** 正确做法是用计划任务把进程丢进交互式 session 2：

```powershell
schtasks /delete /tn JammersRun /f 2>$null
schtasks /create /tn JammersRun /tr 'C:\Jammers\jammers-simulator.exe' /sc ONCE /st 23:59 /ru flower /it /f
schtasks /run /tn JammersRun
```

以 SYSTEM 身份创建 `/it`（interactive token）任务不需要密码。
验证落在正确会话：`(Get-CimInstance Win32_Process -Filter "ProcessId=<pid>").SessionId` 应为 **2**。

补充：从 session 0 查询 session 2 进程的 `MainWindowTitle` 永远是空字符串，
这也是正常的跨会话限制，**不能当作窗口没创建的证据**。要看界面请用 `prlctl capture`。

### 4.2 共享目录只暴露三个子目录

`\\Mac\Home` 只映射 `Desktop`、`Documents`、`Downloads` 三项，
放在家目录其它位置（如 `~/jammers-transfer`）的文件 **在 guest 里看不到**。
中转请用 `~/Downloads/JammersXfer/`，guest 侧路径为 `\\Mac\Home\Downloads\JammersXfer\`。

另外 `\\Mac\Home` 在 `--shared-profile on` / `--shf-host on` 生效前不可见，本机已开启。

### 4.3 宿主 HTTP 中转不通

在宿主起 `python3 -m http.server 8765 --bind 0.0.0.0`，guest 侧 `curl http://10.211.55.2:8765/...`
返回 `HTTP=000`。macOS 应用防火墙是关闭的，但 **pf 处于 Enabled**，推测被 pf 规则拦住。
**不要在这条路上浪费时间，直接用 4.2 的共享目录。**

### 4.4 引号转义

`prlctl exec ... powershell.exe -Command "<长脚本>"` 会被多层 shell 转义搞坏（报 `MissingArgument` 等）。
**一律改成：把 .ps1 写到宿主 `~/Downloads/JammersXfer/`，复制进 guest，再按文件路径执行。**
另外 `powershell -File` 直接吃 UNC 路径会报文件不存在，必须先 `copy` 到本地磁盘。

可用模板：

```bash
P="/Applications/Parallels Desktop.app/Contents/MacOS"; VM="Windows 11"
"$P/prlctl" exec "$VM" cmd.exe /c 'chcp 65001 >nul & copy /Y "\\Mac\Home\Downloads\JammersXfer\x.ps1" C:\Jammers\ >nul & powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Jammers\x.ps1'
```

`chcp 65001` 必须加，否则中文输出全是乱码。脚本首行建议加
`$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8`。

### 4.5 截图

`prlctl capture "Windows 11" --file /tmp/vm_shot.png` 可用，是确认 GUI 状态的唯一可靠手段。

---

## 5. 现有资产

guest `C:\Jammers\`：

| 文件 | 用途 |
|---|---|
| `jammers-simulator.exe` | 精简版模拟器 |
| `check.ps1` | 探测 WebView2 运行时版本与架构 |
| `run_test.ps1` | 在当前会话启动并观察（会踩 session 0 坑，仅作对照） |
| `run_interactive.ps1` | **正确的启动方式**，schtasks `/it` 丢进 session 2 并轮询状态 |
| `api_probe.ps1` | 探测进程、2026 端口、POST /enter、读 startup.log 与数据目录 |
| `JammersSimulatorData\` | 模拟器自建数据目录 |

宿主 `~/Downloads/JammersXfer/` 是以上 ps1 的源副本，改这里再 copy 进去。

---

## 6. 待验证任务（交接给你）

按优先级：

1. **完整版对照测试**。解开 `Jammers-simulator-full-win64.7z` 到 guest（**注意：解压后 711 MB，
   259 个文件，务必整个目录一起搬，`WebView2Runtime/` 与 exe 必须同级**），
   用 4.1 的 schtasks 方式启动 `jammers-simulator-full.exe`，对比：
   能否启动、启动耗时、常驻内存、`startup.log` 是否报
   `fixed WebView2 runtime version does not match the build manifest`。
   目标是确认「精简版更优」这个判断，并留一个兜底方案。

2. **Prism 模拟开销实测**（**最关键的剩余未知数**）。题目给的是 **20 分钟现实时间上限**，
   必须知道模拟器在 Prism 下每个 `/measure`、`/clear` 请求的往返延迟。
   需要登录后开一次演练测试才能测——**登录需要参赛队号、队员1姓名、手机号，只有用户能做**。
   在能测之前，先把压测脚本写好备用（串行发 N 次请求，统计 p50/p95 往返毫秒数）。

3. **guest 内安装 Python**。机器狗程序必须与模拟器同机运行（接口只监听回环，宿主访问不到），
   所以 Python 要装在 Windows 里。优先装 **ARM64 原生版**以避开模拟层。

4. **时间校验**。附件要求本机时间与服务器相差不超过 60 秒，否则无法开始测试。
   确认 guest 时间与宿主同步（Parallels 默认同步，截图里任务栏时间与宿主一致，但正式测试前应再核一次）。

5. **不要做的事**：模拟器有完整的防篡改设计（案例数据由服务器 RSA 加密下发、日志双密钥包裹、
   更新器验 ECDSA 签名、强制在线心跳、`test session requires a pristine simulator`）。
   **不要尝试逆向或绕过**。合法的调参途径只有官方演练测试 + 按附件 2 规则自建本地 mock。

---

## 7. 时间红线

- 北京时间 **2026-09-13 17:30** 之后不能启动新的演练测试或正式测试
- 官方建议 **15:30 之前**完成全部正式测试
- 问题 3、问题 4 **各只有 3 次**正式机会，中止测试同样占用机会
- 单次测试：25 分钟窗口 + `/enter` 之后 20 分钟程序运行上限，以先到者为准；
  窗口开始 5 分钟内 `/enter` 才能用足 20 分钟
