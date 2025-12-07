# Register scheduled task to run run_on_windows.ps1 at startup
# Usage: Run as Administrator

param(
    [string]$TaskName = "BiliMonitor_AutoStart",
    [string]$ScriptPath = "$(Split-Path -Parent $MyInvocation.MyCommand.Definition)\\run_on_windows.ps1",
    [string]$User = "SYSTEM"
)

Write-Output "Registering scheduled task $TaskName for script: $ScriptPath"

$action = New-ScheduledTaskAction -Execute 'PowerShell.exe' -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$ScriptPath`""
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId $User -RunLevel Highest

try {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Force
    Write-Output "Task registered: $TaskName"
} catch {
    Write-Error "Failed to register task: $_"
}
