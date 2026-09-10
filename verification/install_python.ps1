$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
$installer = 'C:\Jammers\python-3.14.7-arm64.exe'
Copy-Item '\\Mac\Home\Downloads\JammersXfer\python-3.14.7-arm64.exe' $installer
$hash = (Get-FileHash $installer -Algorithm SHA256).Hash
if ($hash -ne '9a3fe120cc81bc2cb099550f794d8356811f96a86c7f438519243c3485db928d') { throw 'Installer SHA256 mismatch' }
$signature = Get-AuthenticodeSignature $installer
$signature | Select-Object Status,@{Name='Signer';Expression={$_.SignerCertificate.Subject}} | ConvertTo-Json
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') { throw 'Installer signature invalid' }
$installed = Start-Process $installer -ArgumentList @('/quiet', '/norestart', 'InstallAllUsers=1', 'TargetDir=C:\Python314-arm64', 'PrependPath=1', 'Include_launcher=0', 'Include_test=0', '/log', 'C:\JammersEvidence\python-install.log') -Wait -PassThru
Write-Output "Installer exit code: $($installed.ExitCode)"
if ($installed.ExitCode -notin @(0,3010)) { throw 'Python installation failed' }
& 'C:\Python314-arm64\python.exe' --version
& 'C:\Python314-arm64\python.exe' -m pip --version
if ($LASTEXITCODE -ne 0) { throw 'pip verification failed' }
