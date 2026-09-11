$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
$source = '\\Mac\Home\Downloads\JammersXfer\full-package\Jammers-simulator-full'
$target = 'C:\JammersFull'
New-Item -ItemType Directory -Path $target -Force | Out-Null
& robocopy.exe $source $target /E /R:1 /W:1 /NFL /NDL /NJH /NJS
if ($LASTEXITCODE -ge 8) { throw "robocopy failed: $LASTEXITCODE" }
$files = @(Get-ChildItem $source -File -Recurse)
$mismatches = @()
foreach ($file in $files) {
    $relative = $file.FullName.Substring($source.Length + 1)
    $destination = Join-Path $target $relative
    if ((Get-FileHash $file.FullName -Algorithm SHA256).Hash -ne (Get-FileHash $destination -Algorithm SHA256).Hash) { $mismatches += $relative }
}
$result = [pscustomobject]@{ files = $files.Count; bytes = ($files | Measure-Object Length -Sum).Sum; sha256_mismatches = $mismatches }
New-Item -ItemType Directory -Path 'C:\JammersEvidence' -Force | Out-Null
$result | ConvertTo-Json -Depth 4 | Set-Content 'C:\JammersEvidence\full-copy.json' -Encoding UTF8
$result | ConvertTo-Json -Depth 4
if ($mismatches.Count -gt 0) { throw 'Copy verification failed' }
