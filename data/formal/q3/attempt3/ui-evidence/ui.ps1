param([Parameter(Mandatory=$true)][string]$JobDir)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes,WindowsBase,System.Drawing,System.Windows.Forms
Add-Type @'
using System;using System.Runtime.InteropServices;
public static class FormalNative {[DllImport("user32.dll")]public static extern IntPtr GetForegroundWindow();[DllImport("user32.dll")]public static extern bool SetProcessDPIAware();}
'@
[void][FormalNative]::SetProcessDPIAware()
$cfg=Get-Content -Raw -Encoding UTF8 "$JobDir\job.json"|ConvertFrom-Json
$script:seq=0;$script:clicks=0;$held=$false;$mutex=$null
$result=@{ok=$false;robot_started=$false;clicks=0}
function One($items,$label){$a=@($items);if($a.Count -ne 1){throw "Expected one $label; found $($a.Count)"};return $a[0]}
function Elements($root){return @($root.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition))}
function Snapshot($label){
 $script:seq++;$prefix=('{0:D3}-{1}' -f $script:seq,$label)
 $proc=One @(Get-Process -Name jammers-simulator|Where-Object {$_.SessionId -eq [System.Diagnostics.Process]::GetCurrentProcess().SessionId}) 'interactive simulator'
 $script:root=[System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)
 $script:els=Elements $script:root
 if(@($script:els|Where-Object {$_.Current.IsPassword -or $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::Edit}).Count){throw 'Input/login present; no credential capture'}
 if([FormalNative]::GetForegroundWindow() -ne $proc.MainWindowHandle){throw 'Simulator is not foreground'}
 $rows=New-Object 'System.Collections.Generic.List[object]'
 foreach($e in $script:els){$c=$e.Current;$b=$c.BoundingRectangle;$rows.Add(@{text=$c.Name;class=$c.ClassName;id=$c.AutomationId;type=$c.ControlType.ProgrammaticName;enabled=$c.IsEnabled;offscreen=$c.IsOffscreen;rect=@($b.X,$b.Y,$b.Width,$b.Height)})}
 $rows|ConvertTo-Json -Depth 6|Set-Content -Encoding UTF8 "$JobDir\$prefix.uia.json"
 $b=$script:root.Current.BoundingRectangle;$bmp=New-Object System.Drawing.Bitmap ([int]$b.Width),([int]$b.Height);$g=[System.Drawing.Graphics]::FromImage($bmp)
 try{$g.CopyFromScreen([int]$b.X,[int]$b.Y,0,0,$bmp.Size);$bmp.Save("$JobDir\$prefix.png")}finally{$g.Dispose();$bmp.Dispose()}
 $script:active=One @($script:els|Where-Object {$_.Current.ClassName -match '(^|\s)nav-item\s' -and $_.Current.ClassName -match '(^|\s)active($|\s)'}) 'active navigation'
 if(-not @($script:els|Where-Object {$_.Current.Name -eq "队号 $($cfg.robot_id)"}).Count){throw 'Team mismatch'}
 if(-not @($script:els|Where-Object {$_.Current.Name -eq '服务器已连接'}).Count){throw 'Simulator not connected'}
 $script:main=One @($script:els|Where-Object {$_.Current.ClassName -match '(^|\s)workspace-main($|\s)'}) 'main content'
 $script:names=@((Elements $script:main)|ForEach-Object {$_.Current.Name})
 $result.active_navigation=$script:active.Current.Name
}
function InvokeExact($name){
 $e=One @($script:els|Where-Object {$_.Current.Name -eq $name -and $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::Button}) $name
 if(-not $e.Current.IsEnabled -or $e.Current.IsOffscreen){throw 'Target not visible/enabled'}
 $point=$e.GetClickablePoint();if(-not [System.Windows.Automation.Automation]::Compare($e,[System.Windows.Automation.AutomationElement]::FromPoint($point))){throw 'Target occluded'}
 if($e.Current.Name -ne $name -or (Test-Path "$JobDir\STOP")){throw 'Target changed or stop requested'}
 $e.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke();$script:clicks++
 Start-Sleep -Milliseconds 600
}
try{
 if($cfg.policy -ne 'formal-q3-once' -or $cfg.problem -ne 3 -or [System.Diagnostics.Process]::GetCurrentProcess().SessionId -ne 2){throw 'Formal Q3 authorization scope mismatch'}
 $mutex=New-Object System.Threading.Mutex($false,'Global\BRobotAutoPractice')
 try{$held=$mutex.WaitOne(0)}catch [System.Threading.AbandonedMutexException]{$held=$true}
 if(-not $held){throw 'Another automation is running'}
 Snapshot 'initial'
 if($cfg.action -eq 'inspect'){$result.status='inspected'}
 elseif($cfg.action -eq 'navigate'){
  if($script:active.Current.Name -notin @('演练测试','概览','问题3正式测试','问题4正式测试')){throw 'Unexpected current navigation'}
  if($script:active.Current.Name -ne '问题3正式测试'){InvokeExact '问题3正式测试'}
  Snapshot 'q3-formal-page'
  if($script:active.Current.Name -ne '问题3正式测试'){throw 'Failed to reach Q3 formal page'}
  $result.status='q3-formal-page'
 }elseif($cfg.action -eq 'start'){
  if($script:active.Current.Name -ne '问题3正式测试' -or '已用2次，剩余1次（共3次）' -notin $script:names -or '可以开始' -notin $script:names){throw 'Formal page/quota changed'}
  if(Test-Path 'C:\Q3FusedFormalRepeat-20260913\ONE_FORMAL_ATTEMPT.json'){throw 'Robot attempt already exists'}
  if(Test-Path 'C:\Q3FusedFormalRepeat-20260913\FORMAL_CLIENT_STARTED.json'){throw 'Robot already started'}
  & 'C:\Python314-arm64\python.exe' -B 'C:\Q3FusedFormalRepeat-20260913\verify_package.py' 'C:\Q3FusedFormalRepeat-20260913' | Out-File -Encoding UTF8 "$JobDir\package-verification.txt"
  if($LASTEXITCODE -ne 0){throw 'Package validation failed'}
  $marker=[System.IO.File]::Open('C:\Q3FusedFormalRepeat-20260913\GUI_FORMAL_START_ONCE.json',[System.IO.FileMode]::CreateNew,[System.IO.FileAccess]::Write,[System.IO.FileShare]::None)
  try{$bytes=[System.Text.Encoding]::UTF8.GetBytes((@{problem=3;prior_used=2;at=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json));$marker.Write($bytes,0,$bytes.Length)}finally{$marker.Dispose()}
  InvokeExact '开始问题3正式测试'
  Snapshot 'after-single-start-click'
  $result.status='single-start-clicked'
 }elseif($cfg.action -eq 'confirm-start'){
  if($script:active.Current.Name -ne '问题3正式测试' -or -not @($script:els|Where-Object {$_.Current.Name -eq '即将开始问题3正式测试。当前剩余1次机会，是否继续？'}).Count){throw 'Wrong formal confirmation'}
  if(-not (Test-Path 'C:\Q3FusedFormalRepeat-20260913\GUI_FORMAL_START_ONCE.json')){throw 'Missing authorized start marker'}
  $marker=[System.IO.File]::Open('C:\Q3FusedFormalRepeat-20260913\GUI_FORMAL_CONFIRM_ONCE.json',[System.IO.FileMode]::CreateNew,[System.IO.FileAccess]::Write,[System.IO.FileShare]::None)
  try{$bytes=[System.Text.Encoding]::UTF8.GetBytes((@{problem=3;formal_index=3;at=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json));$marker.Write($bytes,0,$bytes.Length)}finally{$marker.Dispose()}
  InvokeExact '继续'
  Start-Sleep -Seconds 2
  Snapshot 'after-single-confirmation'
  $result.status='single-start-confirmed'
 }elseif($cfg.action -eq 'confirm-final'){
  if($script:active.Current.Name -ne '问题3正式测试' -or -not @($script:els|Where-Object {$_.Current.Name -eq '启动成功后将占用问题3的一次正式测试机会。确定开始吗？'}).Count){throw 'Wrong final confirmation'}
  if(-not (Test-Path 'C:\Q3FusedFormalRepeat-20260913\GUI_FORMAL_CONFIRM_ONCE.json')){throw 'Missing prior confirmation marker'}
  $marker=[System.IO.File]::Open('C:\Q3FusedFormalRepeat-20260913\GUI_FORMAL_FINAL_ONCE.json',[System.IO.FileMode]::CreateNew,[System.IO.FileAccess]::Write,[System.IO.FileShare]::None)
  try{$bytes=[System.Text.Encoding]::UTF8.GetBytes((@{problem=3;formal_index=3;at=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json));$marker.Write($bytes,0,$bytes.Length)}finally{$marker.Dispose()}
  InvokeExact '确认开始'
  Start-Sleep -Seconds 2
  Snapshot 'after-final-confirmation'
  $result.status='formal-start-confirmed'
 }elseif($cfg.action -eq 'run'){
  if($script:active.Current.Name -ne '问题3正式测试' -or -not $cfg.expected_case -or $cfg.expected_case -notin $script:names){throw 'Formal case mismatch'}
  if(-not (Test-Path 'C:\Q3FusedFormalRepeat-20260913\GUI_FORMAL_FINAL_ONCE.json')){throw 'Missing authorized final confirmation'}
  & 'C:\Q3FusedFormalRepeat-20260913\start_q3_fused_formal.ps1' -RobotId $cfg.robot_id -ExpectedCase $cfg.expected_case -CheckOnly | Out-File -Encoding UTF8 "$JobDir\ready.txt"
  $result.robot_started=$true
  & 'C:\Q3FusedFormalRepeat-20260913\start_q3_fused_formal.ps1' -RobotId $cfg.robot_id -ExpectedCase $cfg.expected_case | Out-File -Encoding UTF8 "$JobDir\robot.txt"
  Start-Sleep -Seconds 2
  Snapshot 'after-robot'
  $result.status='formal-robot-returned';$result.case_code=$cfg.expected_case
 }elseif($cfg.action -eq 'view-upload'){
  if($script:active.Current.Name -ne '问题3正式测试' -or $cfg.expected_case -ne 'G4MK-ZVXM-A682-MVBS' -or $cfg.expected_case -notin $script:names -or '测试已结束' -notin $script:names){throw 'Wrong completed formal case'}
  if(-not @($script:els|Where-Object {$_.Current.Name -eq '问题3正式测试完成'}).Count){throw 'Missing completion dialog'}
  InvokeExact '确认'
  Snapshot 'completion-dismissed'
  InvokeExact '返回问题3正式测试'
  Snapshot 'formal-upload-history'
  $result.status='formal-upload-history'
 }else{throw 'Action not enabled in this controller'}
 $result.ok=$true
}catch{$result.error=$_.Exception.Message;$result.stack=$_.ScriptStackTrace}
finally{
 if($held){$mutex.ReleaseMutex()};if($null -ne $mutex){$mutex.Dispose()}
 $result.clicks=$script:clicks
 $result|ConvertTo-Json -Depth 6|Set-Content -Encoding UTF8 "$JobDir\result.json"
}
if(-not $result.ok){exit 20}
