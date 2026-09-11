$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
$processes = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('jammers-simulator.exe','jammers-simulator-full.exe') } | Select-Object Name,ProcessId,SessionId,ExecutablePath)
$listeners = @(Get-NetTCPConnection -State Listen -LocalPort 2026 | Select-Object LocalAddress,LocalPort,OwningProcess)
$operatingSystem = Get-CimInstance Win32_OperatingSystem
$result = [pscustomobject]@{
    utc = [DateTimeOffset]::UtcNow.ToString('o')
    os = $operatingSystem.Caption
    version = $operatingSystem.Version
    build = $operatingSystem.BuildNumber
    processes = $processes
    listeners = $listeners
    slim_sha256 = (Get-FileHash 'C:\Jammers\jammers-simulator.exe').Hash
    full_sha256 = (Get-FileHash 'C:\JammersFull\jammers-simulator-full.exe').Hash
}
$result | ConvertTo-Json -Depth 5 | Set-Content 'C:\JammersEvidence\final-state.json' -Encoding UTF8
$result | ConvertTo-Json -Depth 5
Copy-Item '\\Mac\Home\Downloads\JammersXfer\BENCH-README.md' 'C:\JammersBench\README.md'
