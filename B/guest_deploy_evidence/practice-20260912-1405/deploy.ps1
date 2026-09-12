$ErrorActionPreference = 'Stop'
$dest = 'C:\BRobot-practice-20260912-1405'
if (Test-Path $dest) { throw 'Destination exists' }
Expand-Archive -LiteralPath '\\Mac\Home\Downloads\BRobot-practice-20260912-1405\runtime.zip' -DestinationPath $dest
Set-Location $dest
$env:PYTHONUTF8 = '1'
& 'C:\Python314-arm64\python.exe' -B '\\Mac\Home\Downloads\BRobot-practice-20260912-1405\verify.py'
if ($LASTEXITCODE -ne 0) { throw 'Hash mismatch' }
& 'C:\Python314-arm64\python.exe' -B run_bounded_robot.py --problem 3 --method range_area7 --mode mock-http > guest-q3-mock.log
if ($LASTEXITCODE -ne 0) { throw 'Q3 smoke failed' }
& 'C:\Python314-arm64\python.exe' -B run_bounded_robot.py --problem 4 --method range_grid21_29 --mode mock-http > guest-q4-mock.log
if ($LASTEXITCODE -ne 0) { throw 'Q4 smoke failed' }
Get-ChildItem robot_runs -Directory | ForEach-Object {
$s = Get-Content (Join-Path $_.FullName 'summary.json') -Raw | ConvertFrom-Json
if (-not $s.all_cleared -or $s.official_calls -ne 0) { throw 'Invalid smoke result' }
$s | Select-Object problem,all_cleared,cleared,transport_failures,exited | ConvertTo-Json -Compress
}
