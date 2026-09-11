$ErrorActionPreference = 'Stop'
Set-Location 'C:\BRobot'
$env:PYTHONUTF8 = '1'
& 'C:\Python314-arm64\python.exe' -B '\\Mac\Home\Downloads\verify-cover21-manifest.py'
if ($LASTEXITCODE -ne 0) { throw 'Manifest mismatch' }
& 'C:\Python314-arm64\python.exe' -B run_bounded_robot.py --series cover21 --problem 3 --method range_area7 --mode offline > guest-q3-offline.log
if ($LASTEXITCODE -ne 0) { throw 'Q3 failed' }
& 'C:\Python314-arm64\python.exe' -B run_bounded_robot.py --series cover21 --problem 4 --method range_grid21_29 --mode offline > guest-q4-offline.log
if ($LASTEXITCODE -ne 0) { throw 'Q4 failed' }
$rows = @()
Get-ChildItem 'C:\BRobot\robot_runs' -Directory | ForEach-Object {
  $s = Get-Content (Join-Path $_.FullName 'summary.json') -Raw | ConvertFrom-Json
  if (-not $s.all_cleared -or $s.official_calls -ne 0) { throw 'Smoke assertions failed' }
  $s | Add-Member -NotePropertyName guest_result_dir -NotePropertyValue $_.FullName
  $rows += $s
}
if ($rows.Count -ne 2) { throw 'Expected exactly two smoke runs' }
$rows | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 '\\Mac\Home\Downloads\BRobot-cover21-guest-results.json'
Compress-Archive -Path 'C:\BRobot\robot_runs','C:\BRobot\guest-q3-offline.log','C:\BRobot\guest-q4-offline.log' -DestinationPath '\\Mac\Home\Downloads\BRobot-cover21-guest-evidence.zip'
$rows | Select-Object problem,method,all_cleared,cleared,source_count_scoring_only,commands,official_calls,guest_result_dir | Format-List
