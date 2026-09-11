$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
$python = 'C:\Python314-arm64\python.exe'
New-Item -ItemType Directory -Path 'C:\JammersBench' -Force | Out-Null
Copy-Item '\\Mac\Home\Downloads\JammersXfer\benchmark_api.py' 'C:\JammersBench\benchmark_api.py'
Copy-Item '\\Mac\Home\Downloads\JammersXfer\python_inventory.py' 'C:\JammersBench\python_inventory.py'
Copy-Item '\\Mac\Home\Downloads\JammersXfer\jammers_benchmark_smoke.py' 'C:\JammersBench\jammers_benchmark_smoke.py'
& $python 'C:\JammersBench\python_inventory.py' | Tee-Object 'C:\JammersEvidence\python-inventory.json'
if ($LASTEXITCODE -ne 0) { throw 'Native ARM64 verification failed' }
& $python 'C:\JammersBench\jammers_benchmark_smoke.py' 'C:\JammersBench\benchmark_api.py' | Tee-Object 'C:\JammersEvidence\benchmark-smoke.json'
if ($LASTEXITCODE -ne 0) { throw 'Benchmark smoke verification failed' }
& $python -m pip --version | Set-Content 'C:\JammersEvidence\pip-version.txt'
$signature = Get-AuthenticodeSignature 'C:\Jammers\python-3.14.7-arm64.exe'
[pscustomobject]@{ sha256 = (Get-FileHash 'C:\Jammers\python-3.14.7-arm64.exe').Hash; signature = [string]$signature.Status; signer = $signature.SignerCertificate.Subject } | ConvertTo-Json | Set-Content 'C:\JammersEvidence\python-installer.json'
