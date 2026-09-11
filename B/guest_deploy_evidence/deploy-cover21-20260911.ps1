$ErrorActionPreference = 'Stop'
$dest = 'C:\BRobot'
if (Test-Path $dest) { throw 'C:\BRobot already exists; preserving it' }
Expand-Archive -LiteralPath '\\Mac\Home\Downloads\BRobot-cover21-20260911.zip' -DestinationPath $dest
& 'C:\Python314-arm64\python.exe' -m pip install --no-index --no-deps '\\Mac\Home\Downloads\BRobot-cover21-wheels\scipy-1.18.1-cp314-cp314-win_arm64.whl'
if ($LASTEXITCODE -ne 0) { throw 'SciPy installation failed' }
Set-Location $dest
& 'C:\Python314-arm64\python.exe' -B -c "import sys,numpy,scipy; print(sys.version); print(numpy.__version__,scipy.__version__)"
if ($LASTEXITCODE -ne 0) { throw 'Dependency check failed' }
