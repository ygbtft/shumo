param([Parameter(Mandatory=$true)][string]$JobDir)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes,WindowsBase,System.Drawing,System.Windows.Forms
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class APNative {
 [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
}
'@
[void][APNative]::SetProcessDPIAware()
$cfg=Get-Content -Raw -Encoding UTF8 "$JobDir\job.json" | ConvertFrom-Json
$script:seq=0
$script:clicks=0
$script:robot=$null
$script:mutex=$null
$script:mutexHeld=$false
$script:deny='正式|formal|production|real\s*test|official\s*test'
$script:outcome=@{ok=$false;clicks=0;robot_started=$false}
function Log($event,$data) {
 @{time=[DateTime]::UtcNow.ToString('o');event=$event;data=$data} | ConvertTo-Json -Depth 9 -Compress | Add-Content -Encoding UTF8 "$JobDir\decisions.jsonl"
}
function CheckSwitch {
 $runDir=Split-Path -Parent $JobDir
 $transferDir=Split-Path -Parent $runDir
 if($cfg.policy -ne 'practice-only' -or (Test-Path "$JobDir\STOP") -or (Test-Path "$runDir\STOP") -or (Test-Path "$transferDir\STOP")){throw 'MASTER_SWITCH_BLOCKED'}
}
function Deny($text,$scope) {
 if($text -match $script:deny){Log 'DENY_FORMAL' @{scope=$scope;text=$text}; throw "DENY_FORMAL: $scope : $text"}
}
function PracticeText($text,$scope) {
 Deny $text $scope
 if($text -notmatch '演练'){throw "NO_PRACTICE_TEXT: $scope"}
}
function One($items,$label) {
 $a=@($items); if($a.Count -ne 1){throw "AMBIGUOUS_OR_MISSING: $label ($($a.Count))"}; return $a[0]
}
function Elements($root) { return @($root.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)) }
function Snapshot($label) {
 CheckSwitch
 $script:seq++
 $prefix=('{0:D3}-{1}' -f $script:seq,$label)
 $process=One @(Get-Process -Name jammers-simulator | Where-Object {$_.SessionId -eq [System.Diagnostics.Process]::GetCurrentProcess().SessionId}) 'simulator process'
 if($process.MainWindowHandle -eq 0){throw 'NO_INTERACTIVE_WINDOW'}
 $script:root=[System.Windows.Automation.AutomationElement]::FromHandle($process.MainWindowHandle)
 $all=Elements $script:root
 # Never read ValuePattern/TextPattern or input contents. Refuse login before capturing.
 if(@($all | Where-Object {$_.Current.IsPassword -or $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::Edit}).Count){throw 'INPUT_OR_LOGIN_PRESENT: no capture of credentials'}
 $b=$script:root.Current.BoundingRectangle
 if($b.Width -le 0 -or $b.Height -le 0){throw 'INVALID_WINDOW_RECT'}
 $bmp=New-Object System.Drawing.Bitmap ([int]$b.Width),([int]$b.Height)
 $g=[System.Drawing.Graphics]::FromImage($bmp)
 try {$g.CopyFromScreen([int]$b.X,[int]$b.Y,0,0,$bmp.Size);$bmp.Save("$JobDir\$prefix.png")} finally {$g.Dispose();$bmp.Dispose()}
 $script:els=Elements $script:root
 $rows=@(); try { foreach($e in $script:els){$c=$e.Current;if($c.IsPassword -or $c.ControlType -eq [System.Windows.Automation.ControlType]::Edit){throw 'INPUT_APPEARED'};$r=$c.BoundingRectangle
 $rows+=@{text=$c.Name;class=$c.ClassName;id=$c.AutomationId;type=$(if($null -eq $c.ControlType){'Unavailable-during-render'}else{$c.ControlType.ProgrammaticName});offscreen=$c.IsOffscreen;enabled=$c.IsEnabled;rect=@($r.X,$r.Y,$r.Width,$r.Height)}}
 } finally {
 $rows|ConvertTo-Json -Depth 6|Set-Content -Encoding UTF8 "$JobDir\$prefix.uia.json"
 Log 'SNAPSHOT' @{label=$label;file="$prefix.png";text_file="$prefix.uia.json";session=[System.Diagnostics.Process]::GetCurrentProcess().SessionId}
 }
 if([APNative]::GetForegroundWindow() -ne $process.MainWindowHandle){throw 'SIMULATOR_NOT_FOREGROUND'}
 $script:main=One @($script:els|Where-Object {$_.Current.ClassName -match '(^|\s)workspace-main($|\s)'}) 'workspace-main'
 $script:mainEls=Elements $script:main
 $active=One @($script:els|Where-Object {$_.Current.ClassName -match '(^|\s)nav-item\s' -and $_.Current.ClassName -match '(^|\s)active($|\s)'}) 'active navigation'
 Deny $active.Current.Name 'active navigation'
 foreach($e in $script:mainEls){Deny ($e.Current.Name+' '+$e.Current.ClassName) 'main content'}
 foreach($e in $script:els){if($e.Current.ControlType -eq [System.Windows.Automation.ControlType]::Window -or $e.Current.ClassName -match 'modal|dialog'){Deny (($e.Current.Name)+ ' '+ ((Elements $e|ForEach-Object {$_.Current.Name}) -join ' ')) 'dialog'}}
 if($active.Current.Name -ne '演练测试'){throw 'NOT_PRACTICE_NAVIGATION'}
 if(-not @($script:els|Where-Object {$_.Current.Name -eq '服务器已连接'}).Count){throw 'NOT_CONNECTED'}
 if(-not @($script:els|Where-Object {$_.Current.Name -eq "队号 $($cfg.robot_id)"}).Count){throw 'TEAM_MISMATCH_OR_NOT_LOGGED_IN'}
}
function Button($name) {
 return One @($script:els|Where-Object {$_.Current.Name -eq $name -and $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::Button}) $name
}
function GuardButton($e,$expected) {
 $c=$e.Current
 PracticeText $c.Name 'candidate'
 if($c.Name -ne $expected -or $expected -notin @("开始问题$($cfg.problem)演练测试",'返回演练测试')){throw 'NOT_EXACT_ALLOWLIST'}
 if(-not $c.IsEnabled -or $c.IsOffscreen){throw 'BUTTON_NOT_VISIBLE_ENABLED'}
 $p=$e.GetClickablePoint()
 $hit=[System.Windows.Automation.AutomationElement]::FromPoint($p)
 if(-not [System.Windows.Automation.Automation]::Compare($e,$hit)){throw 'BUTTON_OCCLUDED_OR_HIT_MISMATCH'}
 Log 'ALLOW_CANDIDATE' @{text=$c.Name;expected=$expected;point=@($p.X,$p.Y)}
}
function ClickPractice($name) {
 if($cfg.action -notin @('run','return') -or $cfg.policy -ne 'practice-only' -or (Test-Path "$JobDir\STOP")){throw 'MASTER_SWITCH_BLOCKED'}
 Snapshot 'before-click'
 $e=Button $name
 GuardButton $e $name
 # Invoke only the visible UIA button; no coordinates, bindings, DOM, or simulator internals.
 $pattern=$e.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
 PracticeText $e.Current.Name 'immediate candidate'
 if($e.Current.Name -ne $name){throw 'CANDIDATE_CHANGED'}
 CheckSwitch
 $pattern.Invoke();$script:clicks++;Log 'UIA_INVOKE' @{text=$name;clicks=$script:clicks}
 Start-Sleep -Milliseconds 600
 Snapshot 'after-click'
 PracticeText (($script:mainEls|ForEach-Object {$_.Current.Name}) -join ' ') 'post-click content'
}
function ActiveCase {
 $text=($script:mainEls|ForEach-Object {$_.Current.Name}) -join ' '
 if($text -notmatch "问题\s*$($cfg.problem)\s*演练\s*测试" -or $text -notmatch '等待机器狗进入' -or $text -notmatch '尚未进入'){throw 'NOT_NEW_WAITING_PRACTICE_SESSION'}
 $codes=@($script:mainEls|Where-Object {$_.Current.Name -match '^[A-Z0-9]{4}(-[A-Z0-9]{4}){3}$'}|ForEach-Object {$_.Current.Name}|Select-Object -Unique)
 $code=One $codes 'active case code'
 if($code -eq 'XXXX-XXXX-XXXX-XXXX'){throw 'PLACEHOLDER_CASE_CODE'}
 return $code
}
function ReturnToPractice {
 Snapshot 'before-completion-close'
 $text=($script:mainEls|ForEach-Object {$_.Current.Name}) -join ' '
 if($cfg.expected_case -notmatch '^[A-Z0-9]{4}(-[A-Z0-9]{4}){3}$' -or $text -notmatch [regex]::Escape($cfg.expected_case) -or $text -notmatch '测试已结束'){throw 'COMPLETION_CASE_OR_STATE_MISMATCH'}
 $dialogs=@($script:els|Where-Object {$_.Current.ClassName -eq 'action-dialog-panel'})
 if($dialogs.Count){
  $dialog=One $dialogs 'completion dialog'
  $title="问题$($cfg.problem)演练测试完成"
  $parts=Elements $dialog
  $dialogText=$dialog.Current.Name+' '+(($parts|ForEach-Object {$_.Current.Name}) -join ' ')
  PracticeText $dialogText 'completion dialog composite target'
  if($dialog.Current.Name -ne $title){throw 'NOT_EXACT_COMPLETION_DIALOG'}
  if($dialogText -notmatch '测试正常结束' -or $dialogText -notmatch '行为日志已保存'){throw 'NOT_NORMAL_SAVED_COMPLETION'}
  $button=One @($parts|Where-Object {$_.Current.ControlType -eq [System.Windows.Automation.ControlType]::Button}) 'only completion button'
  Deny $button.Current.Name 'completion button'
  if($button.Current.Name -ne '确认' -or -not $button.Current.IsEnabled -or $button.Current.IsOffscreen){throw 'NOT_COMPLETION_CONFIRM'}
  $point=$button.GetClickablePoint()
  if(-not [System.Windows.Automation.Automation]::Compare($button,[System.Windows.Automation.AutomationElement]::FromPoint($point))){throw 'COMPLETION_BUTTON_OCCLUDED'}
  if($cfg.action -ne 'return' -or $cfg.policy -ne 'practice-only' -or (Test-Path "$JobDir\STOP")){throw 'MASTER_SWITCH_BLOCKED'}
  # Sole user-authorized exception: exact practice COMPLETION dialog + its Confirm button.
  Log 'ALLOW_COMPLETION_COMPOSITE' @{title=$title;button=$button.Current.Name;text=$dialogText;case_code=$cfg.expected_case}
  PracticeText ($dialog.Current.Name+' '+$button.Current.Name) 'immediate completion target'
  if($dialog.Current.Name -ne $title -or $button.Current.Name -ne '确认'){throw 'COMPLETION_TARGET_CHANGED'}
  CheckSwitch
  $button.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
  $script:clicks++;Log 'UIA_INVOKE_COMPLETION' @{text=$title+' / 确认';clicks=$script:clicks}
  Start-Sleep -Milliseconds 400
  Snapshot 'after-completion-close'
  PracticeText (($script:mainEls|ForEach-Object {$_.Current.Name}) -join ' ') 'post-completion-close'
 }
 ClickPractice '返回演练测试'
 $page=One @($script:mainEls|Where-Object {$_.Current.ClassName -eq 'page practice-page' -and $_.Current.Name -eq '演练测试'}) 'returned practice landing page'
 $script:outcome.ok=$true;$script:outcome.status='returned-to-practice'
}
try {
 if([System.Diagnostics.Process]::GetCurrentProcess().SessionId -ne 2){throw 'REQUIRE_SESSION_2'}
 CheckSwitch
 $script:mutex=New-Object System.Threading.Mutex($false,'Global\BRobotAutoPractice')
 try {$script:mutexHeld=$script:mutex.WaitOne(0)} catch [System.Threading.AbandonedMutexException] {$script:mutexHeld=$true}
 if(-not $script:mutexHeld){throw 'ANOTHER_AUTOMATION_RUNNING'}
 if($cfg.policy -ne 'practice-only' -or (Test-Path "$JobDir\STOP")){throw 'MASTER_SWITCH_BLOCKED'}
 $singleUse=[System.IO.File]::Open("$JobDir\started.once",[System.IO.FileMode]::CreateNew,[System.IO.FileAccess]::Write,[System.IO.FileShare]::None)
 $singleUse.Dispose()
 if($cfg.problem -notin @(3,4) -or $cfg.action -notin @('dry-run','reject-formal','run','return')){throw 'INVALID_JOB'}
 Snapshot 'initial'
 if($cfg.action -eq 'reject-formal'){
  $candidate=Button "问题$($cfg.problem)正式测试"
  Log 'NEGATIVE_REAL_UI_CANDIDATE' @{text=$candidate.Current.Name;no_click=$true}
  GuardButton $candidate "开始问题$($cfg.problem)演练测试"
  throw 'NEGATIVE_TEST_FAILED_TO_REJECT'
 }
 if($cfg.action -eq 'return'){
  ReturnToPractice
 } else {
 $start="开始问题$($cfg.problem)演练测试"
 $page=One @($script:mainEls|Where-Object {$_.Current.ClassName -eq 'page practice-page' -and $_.Current.Name -eq '演练测试'}) 'practice landing page'
 GuardButton (Button $start) $start
 if($cfg.action -eq 'dry-run'){$script:outcome.ok=$true;$script:outcome.status='dry-run-ready'}
 else {
  ClickPractice $start
  $readyDeadline=[DateTime]::UtcNow.AddSeconds(30)
  while((($script:mainEls|ForEach-Object {$_.Current.Name}) -join ' ') -notmatch '等待机器狗进入'){
   if([DateTime]::UtcNow -gt $readyDeadline){throw 'PRACTICE_PREPARATION_TIMEOUT'}
   Start-Sleep -Milliseconds 600
   Snapshot 'waiting-practice-ready'
   PracticeText (($script:mainEls|ForEach-Object {$_.Current.Name}) -join ' ') 'preparing practice'
  }
  $case=ActiveCase
  $script:outcome.case_code=$case
  Log 'POST_CLICK_VERIFIED' @{case_code=$case;problem=$cfg.problem}
  Snapshot 'before-robot'
  if((ActiveCase) -ne $case -or (Test-Path "$JobDir\STOP")){throw 'SESSION_CHANGED_OR_STOP'}
  $method=if($cfg.problem -eq 3){'range_area7'}else{'range_grid21_29'}
  $arguments=@('-B','official_ablation_robot.py','--variant','scan_then_service__g35','--problem',[string]$cfg.problem,'--method',$method,'--mode','practice','--base-url','http://127.0.0.1:2026','--robot-id',[string]$cfg.robot_id,'--confirm-practice')
  Log 'ROBOT_START' @{cwd='C:\BAblation-20260913\B';args=$arguments;case_code=$case}
  $env:PYTHONUTF8='1'
  $beforeRuns=@(Get-ChildItem 'C:\BAblation-20260913\B\robot_runs' -Directory | ForEach-Object Name)
  CheckSwitch
  $script:robot=Start-Process 'C:\Python314-arm64\python.exe' -ArgumentList $arguments -WorkingDirectory 'C:\BAblation-20260913\B' -RedirectStandardOutput "$JobDir\robot.stdout.log" -RedirectStandardError "$JobDir\robot.stderr.log" -WindowStyle Hidden -PassThru
  $robotHandle=$script:robot.Handle # Cache the process handle so ExitCode survives fast exit.
  $script:outcome.robot_started=$true
  $deadline=[DateTime]::UtcNow.AddMinutes(21)
  while(-not $script:robot.HasExited){
   Start-Sleep -Milliseconds 750
   CheckSwitch
   if([DateTime]::UtcNow -gt $deadline){throw 'ROBOT_TIMEOUT'}
   Snapshot 'robot-watch'
   $script:robot.Refresh()
  }
  $script:robot.WaitForExit();$script:outcome.robot_exit=$script:robot.ExitCode
  $newRuns=@(Get-ChildItem 'C:\BAblation-20260913\B\robot_runs' -Directory|Where-Object {$_.Name -notin $beforeRuns -and $_.Name -like '*-bounded-practice'})
  foreach($r in $newRuns){Copy-Item -Recurse $r.FullName "$JobDir\robot-run"}
  Snapshot 'completed'
  $completedText=($script:mainEls|ForEach-Object {$_.Current.Name}) -join ' '
  PracticeText $completedText 'completed practice page'
  if($completedText -notmatch [regex]::Escape($case) -or $completedText -notmatch '测试已结束'){throw 'COMPLETED_CASE_OR_STATE_MISMATCH'}
  if($script:robot.ExitCode -ne 0){throw 'ROBOT_NONZERO_EXIT'}
  $script:outcome.ok=$true;$script:outcome.status='robot-completed'
 }
 }
} catch {
 if($null -ne $script:robot -and -not $script:robot.HasExited){Stop-Process -Id $script:robot.Id -Force}
 $script:outcome.error=$_.Exception.Message
 Log 'ABORT' @{error=$_.Exception.Message;stack=$_.ScriptStackTrace;clicks=$script:clicks;robot_started=$script:outcome.robot_started}
} finally {
 if($script:mutexHeld){$script:mutex.ReleaseMutex()}
 if($null -ne $script:mutex){$script:mutex.Dispose()}
 $script:outcome.clicks=$script:clicks
 $script:outcome|ConvertTo-Json -Depth 6|Set-Content -Encoding UTF8 "$JobDir\result.tmp"
 Move-Item -Force "$JobDir\result.tmp" "$JobDir\result.json"
}
if(-not $script:outcome.ok){exit 20}
