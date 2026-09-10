param(
    [ValidateSet('slim', 'full')][string]$Variant,
    [string]$RunLabel,
    [int]$ObserveSeconds = 90
)
$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
$directory = if ($Variant -eq 'full') { 'C:\JammersFull' } else { 'C:\Jammers' }
$executable = if ($Variant -eq 'full') { 'jammers-simulator-full.exe' } else { 'jammers-simulator.exe' }
$evidence = "C:\JammersEvidence\$RunLabel"
New-Item -ItemType Directory -Path $evidence -Force | Out-Null
$logPath = Join-Path $directory 'JammersSimulatorData\startup.log'
if (Test-Path $logPath) { Copy-Item $logPath "$evidence\startup-before.log" }
$existing = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('jammers-simulator.exe', 'jammers-simulator-full.exe') })
foreach ($process in $existing) {
    & taskkill.exe /PID $process.ProcessId /T /F | Out-Null
}
Start-Sleep -Seconds 2
$taskName = "JammersCompare-$Variant"
& schtasks.exe /create /tn $taskName /tr (Join-Path $directory $executable) /sc ONCE /st 23:59 /ru flower /it /f
if ($LASTEXITCODE -ne 0) { throw 'Task creation failed' }
$startedUtc = [DateTimeOffset]::UtcNow.ToString('o')
$timer = [Diagnostics.Stopwatch]::StartNew()
& schtasks.exe /run /tn $taskName
if ($LASTEXITCODE -ne 0) { throw 'Task launch failed' }
$samples = [Collections.Generic.List[object]]::new()
$firstProcess = $null
$firstListener = $null
$firstWebView = $null
$inventorySaved = $false
while ($timer.Elapsed.TotalSeconds -lt $ObserveSeconds) {
    $allProcesses = @(Get-CimInstance Win32_Process)
    $root = $allProcesses | Where-Object { $_.ExecutablePath -eq (Join-Path $directory $executable) } | Select-Object -First 1
    $members = @()
    if ($root) {
        if ($null -eq $firstProcess) { $firstProcess = $timer.Elapsed.TotalSeconds }
        $identifiers = [Collections.Generic.HashSet[uint32]]::new()
        [void]$identifiers.Add($root.ProcessId)
        do {
            $previousCount = $identifiers.Count
            foreach ($process in $allProcesses) {
                if ($identifiers.Contains($process.ParentProcessId)) { [void]$identifiers.Add($process.ProcessId) }
            }
        } while ($identifiers.Count -gt $previousCount)
        $members = @($allProcesses | Where-Object { $identifiers.Contains($_.ProcessId) })
    }
    $webviews = @($members | Where-Object { $_.Name -eq 'msedgewebview2.exe' })
    if ($webviews.Count -gt 0 -and $null -eq $firstWebView) { $firstWebView = $timer.Elapsed.TotalSeconds }
    $listeners = @([Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() | Where-Object { $_.Port -eq 2026 })
    if ($listeners.Count -gt 0 -and $null -eq $firstListener) { $firstListener = $timer.Elapsed.TotalSeconds }
    $sample = [pscustomobject]@{
        elapsed_s = [Math]::Round($timer.Elapsed.TotalSeconds, 3)
        root_pid = $root.ProcessId
        session_id = $root.SessionId
        root_working_set_bytes = $root.WorkingSetSize
        tree_working_set_bytes = ($members | Measure-Object WorkingSetSize -Sum).Sum
        tree_private_bytes = ($members | Measure-Object PrivatePageCount -Sum).Sum
        webview_count = $webviews.Count
        listener_count = $listeners.Count
    }
    $samples.Add($sample)
    if ($timer.Elapsed.TotalSeconds -ge 15 -and -not $inventorySaved) {
        $members | Select-Object Name,ProcessId,ParentProcessId,SessionId,ExecutablePath,CommandLine,WorkingSetSize,PrivatePageCount | ConvertTo-Json -Depth 5 | Set-Content "$evidence\processes-15s.json" -Encoding UTF8
        $inventorySaved = $true
        Write-Output ($sample | ConvertTo-Json -Compress)
    }
    Start-Sleep -Milliseconds 500
}
$samples | Export-Csv "$evidence\samples.csv" -NoTypeInformation -Encoding UTF8
$members | Select-Object Name,ProcessId,ParentProcessId,SessionId,ExecutablePath,CommandLine,WorkingSetSize,PrivatePageCount | ConvertTo-Json -Depth 5 | Set-Content "$evidence\processes-final.json" -Encoding UTF8
if (Test-Path $logPath) { Copy-Item $logPath "$evidence\startup-after.log" }
$runtimeVersions = @($webviews.ExecutablePath | Sort-Object -Unique | ForEach-Object { $runtimeFile = Get-Item $_; [pscustomobject]@{ path = $_; version = $runtimeFile.VersionInfo.FileVersion } })
$summary = [pscustomobject]@{
    variant = $Variant
    run_label = $RunLabel
    launch_utc = $startedUtc
    first_process_s = $firstProcess
    first_listener_s = $firstListener
    first_webview_process_s = $firstWebView
    observed_seconds = $timer.Elapsed.TotalSeconds
    final_sample = $samples[$samples.Count - 1]
    runtimes = $runtimeVersions
    executable_sha256 = (Get-FileHash (Join-Path $directory $executable) -Algorithm SHA256).Hash
}
$summary | ConvertTo-Json -Depth 6 | Set-Content "$evidence\summary.json" -Encoding UTF8
$summary | ConvertTo-Json -Depth 6
if (Test-Path $logPath) { Get-Content $logPath -Tail 30 }
& schtasks.exe /delete /tn $taskName /f | Out-Null
