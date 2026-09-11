param([string]$Label)
$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class ProcessArchitecture {
    [StructLayout(LayoutKind.Sequential)]
    public struct MachineInformation { public ushort Machine; public ushort Reserved; public uint Attributes; }
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern IntPtr OpenProcess(uint access, bool inherit, uint processId);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool IsWow64Process2(IntPtr process, out ushort processMachine, out ushort nativeMachine);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool GetProcessInformation(IntPtr process, int informationClass, out MachineInformation information, uint size);
    [DllImport("kernel32.dll")]
    public static extern bool CloseHandle(IntPtr handle);
}
'@
$results = foreach ($process in Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('jammers-simulator.exe','jammers-simulator-full.exe','msedgewebview2.exe') }) {
    $handle = [ProcessArchitecture]::OpenProcess(0x1000, $false, $process.ProcessId)
    if ($handle -eq [IntPtr]::Zero) { continue }
    try {
        [uint16]$processMachine = 0
        [uint16]$nativeMachine = 0
        $success = [ProcessArchitecture]::IsWow64Process2($handle, [ref]$processMachine, [ref]$nativeMachine)
        $information = New-Object ProcessArchitecture+MachineInformation
        $machineSuccess = [ProcessArchitecture]::GetProcessInformation($handle, 9, [ref]$information, 8)
        [pscustomobject]@{ name = $process.Name; pid = $process.ProcessId; path = $process.ExecutablePath; session = $process.SessionId; success = $success; wow64_process_machine = ('0x{0:X4}' -f $processMachine); native_machine = ('0x{0:X4}' -f $nativeMachine); machine_query_success = $machineSuccess; process_machine = ('0x{0:X4}' -f $information.Machine) }
    } finally { [void][ProcessArchitecture]::CloseHandle($handle) }
}
$results | ConvertTo-Json -Depth 3 | Set-Content "C:\JammersEvidence\$Label-architecture.json" -Encoding UTF8
$results | ConvertTo-Json -Depth 3
