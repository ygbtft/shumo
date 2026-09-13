param([Parameter(Mandatory=$true)][string]$Source,[Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$tokens=$null;$errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($Source,[ref]$tokens,[ref]$errors)
if($errors.Count){throw ($errors|Out-String)}
# Load ONLY pure guard definitions. Never execute the UI runner or simulator code.
$wanted=@('Deny','PracticeText','One','GuardButton')
foreach($f in $ast.FindAll({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst]},$true)){
 if($f.Name -in $wanted){. ([scriptblock]::Create($f.Extent.Text))}
}
$assignment=$ast.FindAll({param($n) $n -is [System.Management.Automation.Language.AssignmentStatementAst] -and $n.Left.Extent.Text -eq '$script:deny'},$true)
if(@($assignment).Count -ne 1){throw 'DENY_ASSIGNMENT_MISSING'}
. ([scriptblock]::Create($assignment[0].Extent.Text))
$script:rows=@()
function Log($event,$data) { $script:rows+=@{event=$event;data=$data} }
$cfg=[pscustomobject]@{problem=3}
$checks=@()
foreach($scope in @('active navigation','main content','dialog','candidate')){
 foreach($name in @('问题3正式测试','问题3演练测试 正式','FORMAL practice','演练 production','演练 real test','演练 official test')){
  $caught=$false
  try {Deny $name $scope} catch {if($_.Exception.Message -notmatch '^DENY_FORMAL:'){throw};$caught=$true}
  if(-not $caught){throw "FAILED_TO_REJECT: $scope $name"}
  $checks+=@{scope=$scope;text=$name;rejected=$true}
 }
}
foreach($name in @('问题3正式测试','开始问题3演练测试 FORMAL','开始问题4演练测试','确认','开始问题3测试')){
 $candidate=[pscustomobject]@{Current=[pscustomobject]@{Name=$name;IsEnabled=$true;IsOffscreen=$false}}
 # No UI object is supplied. A failure to stop before hit testing fails this test.
 $caught=$false
 try {GuardButton $candidate '开始问题3演练测试'} catch {
  if($_.Exception.Message -notmatch '^(DENY_FORMAL|NOT_EXACT_ALLOWLIST|NO_PRACTICE_TEXT):?'){throw}
  $caught=$true
 }
 if(-not $caught){throw "FAILED_CANDIDATE: $name"}
 $checks+=@{scope='candidate gate';text=$name;rejected=$true}
}
PracticeText '开始问题3演练测试' 'positive'
@{passed=($checks.Count+1);gui_calls=0;http_calls=0;checks=$checks;decisions=$script:rows}|ConvertTo-Json -Depth 8|Set-Content -Encoding UTF8 $OutputPath
