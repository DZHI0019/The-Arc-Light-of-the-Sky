# B站账号生命状态监控系统

## 项目简介

这是一个用于监控B站账号活动状态的自动化系统。通过定期检测目标QQ号对应的B站账号登录情况，判断账号持有者的生命状态。当检测到账号超过设定天数未活动时，系统会自动发送邮件通知。

## 功能特点

- ✅ **自动化监控**: 定期自动检查B站账号活动状态
- ✅ **智能判断**: 通过账号动态和活动时间判断生命状态
- ✅ **邮件通知**: 发现异常情况自动发送详细邮件通知
- ✅ **数据持久化**: 使用SQLite数据库存储检查历史记录
- ✅ **高可靠性**: 完善的错误处理和重试机制
- ✅ **日志记录**: 详细的日志记录，便于问题排查
- ✅ **配置灵活**: 通过YAML配置文件轻松管理

## 系统要求

- Python 3.7 或更高版本
- 网络连接（用于访问B站API和发送邮件）

## 安装步骤

### 1. 克隆或下载项目

```bash
# 如果使用git
git clone <repository_url>
cd 远点弧光计划

# 或直接下载解压到项目目录
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置系统

编辑 `config.yaml` 文件，配置以下内容：

#### 目标用户配置
```yaml
targets:
  - qq_number: "123456789"      # 目标QQ号
    bilibili_uid: "12345678"    # 对应的B站UID
    name: "用户1"                # 备注名称（可选）
```

**如何获取B站UID？**
- 访问目标用户的B站主页，URL中的数字就是UID
- 例如：`https://space.bilibili.com/12345678` 中的 `12345678` 就是UID

#### 检查配置
```yaml
check_config:
  check_interval_hours: 6              # 检查间隔（小时）
  inactive_days_threshold: 7          # 无活动天数阈值
```

#### 邮件配置
```yaml
email:
  smtp_server: "smtp.qq.com"          # SMTP服务器（QQ邮箱）
  smtp_port: 587                      # SMTP端口
  sender_email: "your_email@qq.com"   # 发送者邮箱
  sender_password: "your_app_password" # 邮箱授权码（重要！）
  receiver_email: "receiver@example.com" # 接收者邮箱
  subject_prefix: "[生命状态监控]"     # 邮件主题前缀
```

**如何获取QQ邮箱授权码？**
1. 登录QQ邮箱网页版
2. 进入"设置" -> "账户"
3. 找到"POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV服务"
4. 开启"POP3/SMTP服务"或"IMAP/SMTP服务"
5. 点击"生成授权码"，按照提示获取授权码
6. **注意**: 授权码不是QQ密码，需要单独生成

#### 其他配置
```yaml
database:
  path: "monitor.db"                  # 数据库文件路径

logging:
  level: "INFO"                       # 日志级别
  file: "monitor.log"                 # 日志文件路径
  max_bytes: 10485760                 # 日志文件最大大小（10MB）
  backup_count: 5                     # 日志文件备份数量
```

## 使用方法

### 运行程序

```bash
python main.py
```

程序会：
1. 立即执行一次检查
2. 然后按照配置的间隔时间定期检查
3. 发现异常情况时自动发送邮件

### 后台运行（Linux/Mac）

```bash
# 使用nohup
nohup python main.py > output.log 2>&1 &

# 或使用screen
screen -S monitor
python main.py
# 按 Ctrl+A 然后按 D 退出screen，程序继续运行
```

### Windows后台运行

可以使用任务计划程序或创建一个批处理文件：

```batch
@echo off
pythonw main.py
```

### Windows Server 2025 — 开箱即用部署（推荐）

下面给出一个开箱即用的部署流程，适用于 Windows Server 2025。该流程保证：自动启动、进程退出自动重启、使用虚拟环境运行，便于长期稳定运行。

1. 在项目根目录创建并激活虚拟环境（如果尚未创建）：

```powershell
python -m venv .venv
& .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. 确保 `config.yaml` 已正确配置（包括 `database.path`、`email` 等）。如果使用 SMTPS（端口 465），请将 `email.use_ssl` 设置为 `true`。

3. 使用随仓库提供的 `run_on_windows.ps1` 脚本来启动程序并保证自动重启：

```powershell
# 在管理员权限或服务账号下运行（或用计划任务在系统启动时运行此脚本）
powershell -ExecutionPolicy Bypass -File .\run_on_windows.ps1
```

该脚本会优先使用虚拟环境内的 `pythonw.exe`（无窗口），如果不存在则使用 `python.exe`，并在程序退出后 5 秒自动重启，适合长期稳定运行。

4. 可选：将脚本注册为计划任务以便随系统启动自动运行（示例）：

```powershell
#$action = New-ScheduledTaskAction -Execute 'PowerShell.exe' -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"C:\path\to\project\run_on_windows.ps1`""
#$trigger = New-ScheduledTaskTrigger -AtStartup
#Register-ScheduledTask -TaskName 'BiliMonitor' -Action $action -Trigger $trigger -RunLevel Highest
```

提示：若需更严格的守护和失败重试策略，可使用 `nssm`（非官方服务管理器）或将程序容器化后在容器平台上运行。

### 使用 nssm 将程序作为服务运行（可选）

nssm（Non-Sucking Service Manager）能把任意可执行程序包装为 Windows 服务，便于系统管理与自动重启。示例流程：

1. 下载并解压 nssm（https://nssm.cc/），例如放到 `C:\tools\nssm\nssm.exe`。
2. 以管理员运行以下命令安装服务（注意修改路径）：

```powershell
# 示例：
&C:\tools\nssm\nssm.exe install BiliMonitor "C:\path\to\project\.venv\Scripts\pythonw.exe" "C:\path\to\project\main.py"
C:\tools\nssm\nssm.exe set BiliMonitor AppDirectory "C:\path\to\project"
C:\tools\nssm\nssm.exe set BiliMonitor AppStdout "C:\path\to\project\bili_out.log"
C:\tools\nssm\nssm.exe set BiliMonitor AppStderr "C:\path\to\project\bili_err.log"
C:\tools\nssm\nssm.exe start BiliMonitor
```

#### 使用自动化脚本安装服务（推荐）

项目提供了 `install_as_service.ps1` 脚本来自动化 nssm 安装与服务配置。以管理员身份运行：

```powershell
# 方案1：自动下载并安装 nssm（需网络连接）
& .\install_as_service.ps1 -DownloadNssm

# 方案2：指定本地 nssm 路径
& .\install_as_service.ps1 -NssmPath "C:\tools\nssm\nssm.exe"
```

脚本会自动：
- 检查管理员权限
- 配置 Python 路径与应用目录
- 设置日志输出与轮转
- 配置自动启动与重启策略

之后可使用 `net start BiliMonitor` 启动服务，`net stop BiliMonitor` 停止服务。

nssm 提供更细粒度的重启策略和日志管理，适合企业级长期运行场景。

## 项目结构

```
远点弧光计划/
├── main.py                      # 主程序入口
├── config.yaml                  # 配置文件（需编辑）
├── database.py                  # 数据库模块
├── bilibili_checker.py          # B站检测模块
├── email_sender.py              # 邮件发送模块
├── logger_config.py             # 日志配置模块
├── control_panel.py             # Web 控制面板
├── time_sync.py                 # NTP 时间同步模块
├── test_check.py                # 交互式测试脚本
├── requirements.txt             # 依赖包列表
├── run_on_windows.ps1           # Windows 自动重启脚本
├── register_task_on_windows.ps1 # 计划任务注册脚本
├── install_as_service.ps1       # nssm 服务安装脚本（企业级）
├── README.md                    # 项目说明文档
├── QUICKSTART.md                # 快速启动指南与常见问题
├── OPTIMIZATION_NOTES.md        # 优化记录
├── .github/workflows/ci.yml     # GitHub Actions CI 工作流
├── tests/                       # 单元测试目录
│   ├── test_email_sender.py
│   ├── test_database.py
│   └── test_bilibili_checker.py
├── monitor.db                   # SQLite 数据库（运行后自动生成）
├── monitor.log                  # 日志文件（运行后自动生成）
└── .venv/                       # Python 虚拟环境（运行后自动生成）
```

## 快速开始

完整的快速启动指南、环境变量配置、部署方案对比与常见问题已整理在 **`QUICKSTART.md`**，建议**先阅读**。

常用命令快速参考：
```powershell
# 创建虚拟环境与安装依赖
python -m venv .venv
& .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 运行程序（选一种方式）
python main.py                                    # 前台运行
powershell -ExecutionPolicy Bypass -File .\run_on_windows.ps1  # 自动重启
.\register_task_on_windows.ps1                    # 注册计划任务（需管理员）
.\install_as_service.ps1 -DownloadNssm           # 安装 Windows 服务（企业级）

# 运行测试
pytest -q
pytest tests/test_email_sender.py -v

# 代码质量检查（开发环境）
ruff check .
mypy . --ignore-missing-imports
```

## 注意事项

1. **账号检测**: 通过B站公开API获取用户信息和最新动态
2. **活动判断**: 根据最新动态时间计算不活跃天数
3. **阈值判断**: 当不活跃天数超过设定阈值时触发通知
4. **邮件通知**: 发送包含详细信息的邮件通知
5. **数据记录**: 所有检查记录和通知记录都保存在数据库中

## 注意事项

⚠️ **重要提示**:
- 本系统仅用于监控公开的B站账号信息
- 请确保遵守B站服务条款和相关法律法规
- 建议合理设置检查间隔，避免对B站服务器造成压力
- 邮件授权码请妥善保管，不要泄露

⚠️ **限制说明**:
- B站API可能不提供最后登录时间，系统主要通过动态时间判断
- 如果用户设置了隐私保护或没有动态，可能无法准确判断
- 网络问题可能导致检查失败，系统会自动重试

## 故障排查

### 问题1: 无法获取用户信息
- 检查B站UID是否正确
- 检查网络连接是否正常
- 查看日志文件了解详细错误信息

### 问题2: 邮件发送失败
- 确认SMTP服务器和端口配置正确
- 确认邮箱授权码正确（不是QQ密码）
- 确认发送者邮箱已开启SMTP服务
- 检查防火墙是否阻止了SMTP连接

### 问题3: 程序运行异常
- 查看 `monitor.log` 日志文件
- 确认所有依赖包已正确安装
- 确认配置文件格式正确（YAML格式）

## 维护建议

1. **定期检查日志**: 查看 `monitor.log` 了解系统运行状态
2. **数据库备份**: 定期备份 `monitor.db` 数据库文件
3. **配置更新**: 根据实际需求调整检查间隔和阈值
4. **依赖更新**: 定期更新依赖包以获得安全补丁

## 许可证

本项目仅供学习和个人使用，请遵守相关法律法规。

## 技术支持

如遇到问题，请查看日志文件或检查配置文件。建议在GitHub Issues中反馈问题。

