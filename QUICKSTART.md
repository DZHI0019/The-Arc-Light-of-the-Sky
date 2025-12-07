# 快速启动指南

本文档提供了在 Windows Server 2025 上最快速部署此项目的步骤，以及日常运维常用命令。

## 目录
- [一分钟快速启动](#一分钟快速启动)
- [Windows 部署方案对比](#windows-部署方案对比)
- [环境变量配置](#环境变量配置)
- [常见问题](#常见问题)
- [开发与测试](#开发与测试)

---

## 一分钟快速启动

假设已在 `D:\project\` 克隆/放置项目。

### 步骤 1: 创建虚拟环境并安装依赖
```powershell
cd D:\project\
python -m venv .venv
& .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 步骤 2: 配置 config.yaml
编辑 `config.yaml`，至少填入：
- `targets`: 目标账户（QQ号、B站UID、名称）
- `email`: SMTP 服务器、发送者、接收者（参考 README 获取授权码）
- `database.path`: 数据库文件路径（可保持默认 `monitor.db`）

示例：
```yaml
targets:
  - qq_number: "123456789"
    bilibili_uid: "987654321"
    name: "监控对象"

email:
  smtp_server: "smtp.qq.com"
  smtp_port: 587
  sender_email: "your_email@qq.com"
  sender_password: "your_auth_code"  # 授权码（非QQ密码）
  receiver_email: "alert@example.com"
  subject_prefix: "[监控]"
```

### 步骤 3: 启动程序（选择一种方式）

#### 方案 A：直接运行（前台）
```powershell
& .\.venv\Scripts\Activate.ps1
python main.py
```

#### 方案 B：后台运行（自动重启，推荐）
```powershell
powershell -ExecutionPolicy Bypass -File .\run_on_windows.ps1
```
程序会在 5 秒内退出时自动重启。

#### 方案 C：注册系统计划任务（系统启动时自动运行）
以**管理员**身份运行 PowerShell：
```powershell
powershell -ExecutionPolicy Bypass -File .\register_task_on_windows.ps1
```
然后可在 `任务计划程序` 中查看任务 `BiliMonitor_AutoStart`，手动启动或等待系统启动时自动运行。

---

## Windows 部署方案对比

| 方案 | 优点 | 缺点 | 适用场景 |
|------|------|------|--------|
| **直接运行** | 简单，易调试 | 需保持窗口/CMD 打开 | 测试、短期运行 |
| **自动重启脚本** (`run_on_windows.ps1`) | 进程退出自动重启，无窗口（pythonw） | 需保持 PS 窗口或后台任务 | 中期运行，内网环境 |
| **计划任务** (`register_task_on_windows.ps1`) | 随系统启动，集成度高，易管理 | 需要管理员权限，计划任务配置有学习成本 | 长期部署，生产环境 |
| **nssm 服务** | 企业级守护，细粒度重启策略，日志管理完善 | 需单独安装 nssm，配置稍复杂 | 企业级服务，SLA 要求高 |

### 推荐用于 Windows Server 2025 的方案：
- 小型/内网环境 → **计划任务** + `register_task_on_windows.ps1`
- 生产/SLA 要求 → **nssm 服务**（参考 `README.md` 中 nssm 章节）

---

## 环境变量配置

若希望通过环境变量而不是配置文件传递敏感信息，可设置以下环境变量（优先级高于 config.yaml）：

| 环境变量 | 对应配置项 | 示例 |
|---------|---------|-----|
| `EMAIL_SMTP_SERVER` | `email.smtp_server` | `smtp.qq.com` |
| `EMAIL_SMTP_PORT` | `email.smtp_port` | `587` |
| `EMAIL_SENDER` | `email.sender_email` | `alert@qq.com` |
| `EMAIL_PASSWORD` | `email.sender_password` | `abcd1234efgh5678` |
| `EMAIL_RECEIVER` | `email.receiver_email` | `notify@example.com` |
| `EMAIL_SUBJECT_PREFIX` | `email.subject_prefix` | `[告警]` |
| `EMAIL_USE_SSL` | `email.use_ssl` | `1` 或 `true` |
| `EMAIL_TIMEOUT` | `email.timeout` | `30` |
| `MONITOR_DB_PATH` | `database.path` | `D:\data\monitor.db` |

### 在计划任务中使用环境变量
编辑任务 → 操作 → 编辑 → 参数：
```
-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command "
$env:EMAIL_PASSWORD='your_auth_code'; 
& 'D:\project\.venv\Scripts\python.exe' 'D:\project\main.py'
"
```

或在 `.bat` 脚本中：
```batch
@echo off
set EMAIL_PASSWORD=your_auth_code
set EMAIL_SMTP_SERVER=smtp.qq.com
D:\project\.venv\Scripts\pythonw.exe D:\project\main.py
```

---

## 常见问题

### Q: 程序启动后立即退出，如何调试？
A: 改为前台运行并查看错误：
```powershell
& .\.venv\Scripts\Activate.ps1
python main.py
```
或查看日志文件（默认 `monitor.log`）。

### Q: 邮件发送失败，显示"认证失败"
A: 
1. 确认是否使用了授权码而非 QQ 密码（参考 `README.md`）
2. 检查 SMTP 服务器地址与端口（QQ 邮箱：`smtp.qq.com:587` 或 `smtp.qq.com:465` 用 SSL）
3. 若使用端口 465，需在 config.yaml 中设置 `email.use_ssl: true`

### Q: 数据库文件很大，如何清理历史记录？
A: SQLite 数据库路径在 `config.yaml` 的 `database.path`。可用 SQLite 工具删除旧数据：
```sql
DELETE FROM check_records WHERE created_at < datetime('now', '-90 days');
DELETE FROM notification_records WHERE created_at < datetime('now', '-90 days');
VACUUM;  -- 回收磁盘空间
```

### Q: 如何查看监控状态？
A: 
1. 查看日志：`monitor.log`
2. 若启用了控制面板，访问 `http://127.0.0.1:8080/status`（需要 Bearer Token）
3. 查看数据库：`monitor.db`（SQLite）

### Q: Windows Server 2025 防火墙阻止了 SMTP？
A: 
1. 允许出站连接到 SMTP 服务器端口（587、465 等）
2. 或在 PowerShell 中临时允许：
   ```powershell
   New-NetFirewallRule -DisplayName "Python SMTP" -Direction Outbound -Protocol TCP -RemotePort 587,465 -Action Allow
   ```

---

## 开发与测试

### 运行单元测试
```powershell
& .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt  # 若需要最新测试依赖
pytest -q
```

### 运行特定测试
```powershell
pytest tests/test_email_sender.py::test_send_email_starttls -v
```

### 代码质量检查（开发环境）
```powershell
# 安装开发依赖
pip install ruff mypy

# Lint
ruff check .

# Type check
mypy . --ignore-missing-imports
```

### 手动测试 B 站检测模块
```powershell
python test_check.py --no-input --uid 1
```

### 手动测试邮件发送
```powershell
python test_check.py --no-input
# 选项 3：测试邮件发送模块
```

---

## 日志与监控

### 查看日志
日志文件位置：`config.yaml` 中 `logging.file`（默认 `monitor.log`）

启用调试日志：编辑 `config.yaml`，设置：
```yaml
logging:
  level: "DEBUG"  # 改为 DEBUG
```

### 日志轮转
日志自动轮转：
- `max_bytes`: 单个文件最大大小（默认 10MB）
- `backup_count`: 保留备份数（默认 5 个）

### 监控服务状态
若启用了控制面板（config.yaml 中 `control_panel.enabled: true`），可访问：
- `/health`：健康检查（无需认证）
- `/status`：运行状态（需要 `auth_token`）
- `/config`：配置信息（需要 `auth_token`）

示例：
```powershell
Invoke-WebRequest -Uri http://127.0.0.1:8080/health
```

---

## 更新与维护

### 升级依赖包
```powershell
& .\.venv\Scripts\Activate.ps1
pip install --upgrade -r requirements.txt
```

### 备份数据库
```powershell
Copy-Item monitor.db "backup\monitor_$(Get-Date -Format 'yyyyMMdd_HHmmss').db"
```

---

## 获取帮助

- 查看完整文档：`README.md`
- 查看源代码注释：各模块（`main.py`、`bilibili_checker.py` 等）
- 运行测试：`pytest -q` 或 `pytest -v`

祝部署顺利！
