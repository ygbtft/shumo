$ErrorActionPreference = 'Stop'
Set-Location 'C:\BRobot-practice-20260912-1405'
$env:PYTHONUTF8 = '1'
& 'C:\Python314-arm64\python.exe' -B '\\Mac\Home\Downloads\BRobot-practice-20260912-1405\verify.py'
if ($LASTEXITCODE -ne 0) { throw 'Hash mismatch' }
& 'C:\Python314-arm64\python.exe' -B run_bounded_robot.py --problem 4 --method range_grid21_29 --mode practice --base-url http://127.0.0.1:2026 --robot-id 202623001141 --confirm-practice
$runCode = $LASTEXITCODE
$latest = Get-ChildItem robot_runs -Directory -Filter '*-bounded-practice' | Sort-Object Name -Descending | Select-Object -First 1
if ($latest) { Copy-Item -Recurse $latest.FullName '\\Mac\Home\Downloads\BRobot-practice-20260912-1405\' }
if ($runCode -ne 0) { throw 'Practice failed; inspect copied evidence, do not restart in same session' }
