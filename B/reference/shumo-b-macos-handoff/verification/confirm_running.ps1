$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
$samples = @()
for ($sampleIndex = 0; $sampleIndex -le 6; $sampleIndex++) {
    if ($sampleIndex -gt 0) { Start-Sleep -Seconds 5 }
    $process = Get-Process -Id 4320
    $session = (Get-CimInstance Win32_Process -Filter 'ProcessId=4320').SessionId
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort 2026 | Where-Object { $_.OwningProcess -eq $process.Id })
    $sample = [pscustomobject]@{
        utc = [DateTimeOffset]::UtcNow.ToString('o')
        pid = $process.Id
        session = $session
        uptime_seconds = [Math]::Round(((Get-Date) - $process.StartTime).TotalSeconds, 1)
        working_set_mib = [Math]::Round($process.WorkingSet64 / 1MB, 2)
        addresses = @($listeners.LocalAddress)
    }
    $samples += $sample
    $sample | ConvertTo-Json -Compress
    if ($session -ne 2 -or '127.0.0.1' -notin $listeners.LocalAddress -or '::1' -notin $listeners.LocalAddress) { throw 'Session or listener check failed' }
}
$samples | ConvertTo-Json -Depth 4 | Set-Content 'C:\JammersEvidence\running-confirmation.json' -Encoding UTF8
Get-Content 'C:\Jammers\JammersSimulatorData\startup.log'
