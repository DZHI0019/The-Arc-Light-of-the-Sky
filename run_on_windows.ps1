# Windows 启动脚本：自动重启并以后台方式运行 main.py
# 适用于 Windows Server 2025 开箱即用部署示例
# 使用方法：以管理员或服务账号运行此脚本，或通过计划任务在系统启动时运行

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

# 首选使用虚拟环境内的 pythonw/python
$venvPython = Join-Path $scriptDir ".venv\Scripts\pythonw.exe"
$venvPythonConsole = Join-Path $scriptDir ".venv\Scripts\python.exe"

if (Test-Path $venvPython) {
    $python = $venvPython
} elseif (Test-Path $venvPythonConsole) {
    # 如果没有 pythonw，使用 python 控制台版
    $python = $venvPythonConsole
} else {
    # 回退到系统安装的 python
    $python = "pythonw.exe"
}

Write-Output "使用 Python: $python"

# 持续循环：程序退出后等待并重启，保证长期稳定性
while ($true) {
    try {
        Write-Output "[run_on_windows] 启动监控 $(Get-Date)"
        $proc = Start-Process -FilePath $python -ArgumentList "main.py" -WorkingDirectory $scriptDir -PassThru
        $proc.WaitForExit()
        $exitCode = $proc.ExitCode
        Write-Output "[run_on_windows] 监控进程已退出，代码: $exitCode ($(Get-Date))。5秒后重启..."
    } catch {
        Write-Output "[run_on_windows] 启动失败: $_"
    }
    Start-Sleep -Seconds 5
}
