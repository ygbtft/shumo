param([Parameter(Mandatory=$true)][ValidatePattern('^[0-9]+$')][string]$RobotId,[switch]$CheckOnly,[string]$ExpectedCase)
$ErrorActionPreference='Stop'
$env:PYTHONUTF8='1'
$python='C:\Python314-arm64\python.exe'
Set-Location $PSScriptRoot
& $python -B "$PSScriptRoot\verify_package.py" $PSScriptRoot
if($LASTEXITCODE -ne 0){throw 'Frozen package verification failed'}
& $python -B "$PSScriptRoot\B\run_q3_fused_formal.py" --check-config
if($LASTEXITCODE -ne 0){throw 'Nearest-task configuration check failed'}
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
function One($items,$label){$a=@($items);if($a.Count -ne 1){throw "Expected one $label, found $($a.Count)"};return $a[0]}
function ReadFormalCase {
 $session=[System.Diagnostics.Process]::GetCurrentProcess().SessionId
 $process=One @(Get-Process -Name jammers-simulator|Where-Object {$_.SessionId -eq $session}) 'interactive simulator'
 $root=[System.Windows.Automation.AutomationElement]::FromHandle($process.MainWindowHandle)
 $all=@($root.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition))
 if(@($all|Where-Object {$_.Current.IsPassword -or $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::Edit}).Count){throw 'Login/input screen is not an open formal case'}
 $active=One @($all|Where-Object {$_.Current.ClassName -match '(^|\s)nav-item\s' -and $_.Current.ClassName -match '(^|\s)active($|\s)'}) 'active navigation'
 if($active.Current.Name -notmatch '^问题\s*3\s*正式测试$'){throw 'Open the Q3 FORMAL session first; no robot request sent'}
 if(-not @($all|Where-Object {$_.Current.Name -eq "队号 $RobotId"}).Count){throw 'Logged-in team does not match RobotId'}
 if(-not @($all|Where-Object {$_.Current.Name -eq '服务器已连接'}).Count){throw 'Official simulator is not connected'}
 $main=One @($all|Where-Object {$_.Current.ClassName -match '(^|\s)workspace-main($|\s)'}) 'main content'
 $elements=@($main.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition))
 $names=@($elements|ForEach-Object {$_.Current.Name});$text=$names -join ' '
 if($text -notmatch '问题\s*3\s*正式\s*测试' -or $text -notmatch '等待机器狗进入' -or $text -notmatch '尚未进入' -or $text -match '测试已结束'){throw 'Q3 formal case must be waiting, not already entered or ended'}
 $case=One @($names|Where-Object {$_ -match '^[A-Z0-9]{4}(-[A-Z0-9]{4}){3}$'}|Select-Object -Unique) 'case code'
 return $case
}
$case=ReadFormalCase
if($ExpectedCase -and $case -ne $ExpectedCase){throw 'Formal case does not match the explicitly selected case'}
if($CheckOnly){Write-Output "READY: Q3 formal case $case; nearest task order; gate 65 m, primary budget 2; no requests sent";return}
$mutex=New-Object System.Threading.Mutex($false,'Global\BRobotAutoPractice')
$held=$false
try {
 try{$held=$mutex.WaitOne(0)}catch [System.Threading.AbandonedMutexException]{$held=$true}
 if(-not $held){throw 'Another robot automation is running'}
 if((ReadFormalCase) -ne $case){throw 'Formal case changed during preflight'}
 $marker=[System.IO.File]::Open("$PSScriptRoot\ONE_FORMAL_ATTEMPT.json",[System.IO.FileMode]::CreateNew,[System.IO.FileAccess]::Write,[System.IO.FileShare]::None)
 try{
  $record=@{case_code=$case;problem=3;variant='range_area7_nearest65_a2';robot_id=$RobotId;started_utc=[DateTime]::UtcNow.ToString('o')}
  $bytes=[System.Text.Encoding]::UTF8.GetBytes(($record|ConvertTo-Json -Compress));$marker.Write($bytes,0,$bytes.Length)
 }finally{$marker.Dispose()}
 Set-Location "$PSScriptRoot\B"
 $before=@(Get-ChildItem robot_runs -Directory|ForEach-Object Name)
 & $python -B run_q3_fused_formal.py --robot-id $RobotId --case-code $case --confirm-formal
 $code=$LASTEXITCODE
 $archive="\\Mac\Home\Downloads\Q3FusedFormal-20260913\results\$case"
 New-Item -ItemType Directory -Force -Path $archive|Out-Null
 Copy-Item "$PSScriptRoot\ONE_FORMAL_ATTEMPT.json" $archive
 $new=@(Get-ChildItem robot_runs -Directory|Where-Object {$_.Name -notin $before -and $_.Name -like '*-bounded-formal'})
 foreach($run in $new){Copy-Item -Recurse $run.FullName $archive}
 $official=@(Get-ChildItem 'C:\Jammers\JammersSimulatorData\behavior-logs' -File|Where-Object {$_.Name -like "formal-p3-*-$case*"})
 foreach($file in $official){Copy-Item $file.FullName $archive}
 if($code -ne 0){throw "Robot stopped with an error. Inspect $archive; do not launch it again in this case."}
 Write-Output "Robot finished. Evidence: $archive"
 Write-Output 'Keep the official simulator open until its formal log status is UPLOADED.'
}finally{if($held){$mutex.ReleaseMutex()};$mutex.Dispose()}
