$ErrorActionPreference='Stop'
$tokens=$null;$parseErrors=$null
[System.Management.Automation.Language.Parser]::ParseFile('C:\BRobot\auto-practice\20260913-151423-0c4eb4ba\ui.ps1',[ref]$tokens,[ref]$parseErrors)|Out-Null
if($parseErrors.Count){throw ($parseErrors|Out-String)}
$tr='powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "C:\BRobot\auto-practice\20260913-151423-0c4eb4ba\ui.ps1" -JobDir "\\Mac\Home\Downloads\AutoPractice\20260913-151423-0c4eb4ba\007-6-view-upload"'
& schtasks.exe /create /tn 'AutoPractice-20260913-151423-0c4eb4ba' /tr $tr /sc ONCE /st 23:59 /ru flower /it /f | Out-Null
if($LASTEXITCODE -ne 0){throw 'CREATE_TASK_FAILED'}
$s=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 23)
$t=Get-ScheduledTask -TaskName 'AutoPractice-20260913-151423-0c4eb4ba'
$t.Triggers=@()
$t.Settings=$s
Set-ScheduledTask -InputObject $t | Out-Null
& schtasks.exe /run /tn 'AutoPractice-20260913-151423-0c4eb4ba' | Out-Null
if($LASTEXITCODE -ne 0){throw 'RUN_TASK_FAILED'}
