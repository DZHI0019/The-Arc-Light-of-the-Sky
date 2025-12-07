# 自动安装 nssm 并注册为 Windows 服务（仅限 Windows Server 2025）
# 用法：以管理员身份运行
# .\install_as_service.ps1 -DownloadNssm
# 或手动下载 nssm 后：
# .\install_as_service.ps1 -NssmPath "C:\tools\nssm.exe"

param(
    [switch]$DownloadNssm,
    [string]$NssmPath = "C:\tools\nssm\nssm.exe",
    [string]$ServiceName = "BiliMonitor",
    [string]$ProjectPath = (Split-Path -Parent $MyInvocation.MyCommand.Definition),
    [string]$LogPath = "$ProjectPath\logs"
)

function Download-Nssm {
    param([string]$TargetPath)
    Write-Output "下载 nssm..."
    $nssm_url = "https://nssm.cc/download/nssm-2.24-101-g897c7f7.zip"
    $zip_path = "$env:TEMP\nssm.zip"
    
    try {
        Invoke-WebRequest -Uri $nssm_url -OutFile $zip_path -ErrorAction Stop
        Expand-Archive -Path $zip_path -DestinationPath $env:TEMP -Force
        $nssm_src = Get-ChildItem $env:TEMP -Filter "nssm-*" -Directory | Select-Object -First 1
        if ($nssm_src) {
            $nssm_exe = Join-Path $nssm_src.FullName "win64\nssm.exe"
            if (Test-Path $nssm_exe) {
                New-Item -ItemType Directory -Force -Path (Split-Path $TargetPath)
                Copy-Item $nssm_exe $TargetPath -Force
                Write-Output "nssm 已下载到: $TargetPath"
                return $true
            }
        }
    } catch {
        Write-Error "下载失败: $_"
        return $false
    }
    return $false
}

# 检查是否以管理员运行
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")
if (-not $isAdmin) {
    Write-Error "此脚本需要管理员权限！请以管理员身份运行。"
    exit 1
}

# 如果需要下载 nssm
if ($DownloadNssm) {
    if (-not (Download-Nssm -TargetPath $NssmPath)) {
        Write-Error "nssm 下载失败，请手动下载并指定 -NssmPath"
        exit 1
    }
}

# 检查 nssm 是否存在
if (-not (Test-Path $NssmPath)) {
    Write-Error "nssm 未找到: $NssmPath"
    Write-Output "请先下载 nssm（https://nssm.cc/），或运行: .\install_as_service.ps1 -DownloadNssm"
    exit 1
}

# 创建日志目录
New-Item -ItemType Directory -Force -Path $LogPath | Out-Null

# 获取虚拟环境 Python 路径
$python_exe = Join-Path $ProjectPath ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $python_exe)) {
    Write-Error "虚拟环境未找到: $python_exe"
    Write-Output "请先创建虚拟环境并安装依赖。"
    exit 1
}

Write-Output "正在安装 Windows 服务: $ServiceName"
Write-Output "项目路径: $ProjectPath"
Write-Output "Python: $python_exe"
Write-Output "日志路径: $LogPath"

# 安装服务
& $NssmPath install $ServiceName $python_exe "main.py"
if ($LASTEXITCODE -ne 0) {
    Write-Error "服务安装失败！"
    exit 1
}

# 配置服务
& $NssmPath set $ServiceName AppDirectory $ProjectPath
& $NssmPath set $ServiceName AppStdout "$LogPath\out.log"
& $NssmPath set $ServiceName AppStderr "$LogPath\err.log"
& $NssmPath set $ServiceName AppRotateFiles 1
& $NssmPath set $ServiceName AppRotateBytes 10485760  # 10MB
& $NssmPath set $ServiceName AppRotateDelay 0

# 设置重启策略
& $NssmPath set $ServiceName AppRestartDelay 5000  # 5 秒
& $NssmPath set $ServiceName Start SERVICE_AUTO_START

Write-Output "`n服务安装完成！"
Write-Output ""
Write-Output "启动服务："
Write-Output "  net start $ServiceName"
Write-Output ""
Write-Output "停止服务："
Write-Output "  net stop $ServiceName"
Write-Output ""
Write-Output "卸载服务："
Write-Output "  & $NssmPath remove $ServiceName confirm"
Write-Output ""
Write-Output "查看日志："
Write-Output "  Get-Content '$LogPath\out.log' -Tail 50"
