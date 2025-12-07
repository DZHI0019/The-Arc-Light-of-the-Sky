"""
主程序 - B站账号生命状态监控系统

本程序提供高可靠性的B站账号生命状态监控服务，包括：
- 定期检查目标账号活动状态
- 自动发送邮件通知
- 完善的错误处理和恢复机制
- 优雅的启动和关闭流程
"""
import yaml
import time
import signal
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging

from logger_config import setup_logger
from database import Database
from bilibili_checker import BilibiliChecker
from email_sender import EmailSender
from control_panel import ControlPanel
from time_sync import get_trusted_time, TimeSyncError

logger = logging.getLogger(__name__)


class MonitorService:
    """
    监控服务主类
    
    提供高可靠性的B站账号生命状态监控服务，包括：
    - 配置管理和验证
    - 定期检查任务调度
    - 邮件通知管理
    - 优雅的启动和关闭
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        初始化监控服务
        
        Args:
            config_path: 配置文件路径（默认 config.yaml）
            
        Raises:
            ValueError: 当配置验证失败时
            FileNotFoundError: 当配置文件不存在时
            yaml.YAMLError: 当配置文件格式错误时
        """
        self.config_path = config_path
        self.config = self._load_config()
        self._validate_config()
        self.running = True
        self.start_time = datetime.now()
        self.last_cycle_started: Optional[datetime] = None
        self.last_cycle_finished: Optional[datetime] = None
        self.control_panel: Optional[ControlPanel] = None
        
        # 初始化各个模块
        try:
            # 支持使用环境变量覆盖配置，便于在 Windows 服务/计划任务中安全传递敏感信息
            db_path = os.environ.get('MONITOR_DB_PATH') or self.config['database']['path']
            self.db = Database(db_path)
            self.checker = BilibiliChecker()

            # 邮件配置：允许用环境变量覆盖
            email_cfg = self.config.get('email', {})
            smtp_server = os.environ.get('EMAIL_SMTP_SERVER') or email_cfg.get('smtp_server')
            smtp_port = int(os.environ.get('EMAIL_SMTP_PORT') or email_cfg.get('smtp_port'))
            sender_email = os.environ.get('EMAIL_SENDER') or email_cfg.get('sender_email')
            sender_password = os.environ.get('EMAIL_PASSWORD') or email_cfg.get('sender_password')
            receiver_email = os.environ.get('EMAIL_RECEIVER') or email_cfg.get('receiver_email')
            subject_prefix = os.environ.get('EMAIL_SUBJECT_PREFIX') or email_cfg.get('subject_prefix', '')
            use_ssl = os.environ.get('EMAIL_USE_SSL') in ('1', 'true', 'True') if os.environ.get('EMAIL_USE_SSL') is not None else email_cfg.get('use_ssl', False)

            self.email_sender = EmailSender(
                smtp_server=smtp_server,
                smtp_port=smtp_port,
                sender_email=sender_email,
                sender_password=sender_password,
                receiver_email=receiver_email,
                subject_prefix=subject_prefix,
                use_ssl=use_ssl,
            )
        except Exception as e:
            logger.error(f"模块初始化失败: {e}", exc_info=True)
            raise
        
        # 注册信号处理器（仅Unix系统）
        if hasattr(signal, 'SIGINT'):
            signal.signal(signal.SIGINT, self._signal_handler)
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, self._signal_handler)
        
        # 初始化控制面板（如启用）
        self._start_control_panel()
        
        logger.info("监控服务初始化完成")
    
    def _load_config(self) -> Dict:
        """
        加载配置文件
        
        Returns:
            Dict: 配置字典
            
        Raises:
            FileNotFoundError: 当配置文件不存在时
            yaml.YAMLError: 当配置文件格式错误时
        """
        if not os.path.exists(self.config_path):
            logger.error(f"配置文件不存在: {self.config_path}")
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            if config is None:
                raise ValueError("配置文件为空")
            
            logger.info(f"配置文件加载成功: {self.config_path}")
            return config
            
        except yaml.YAMLError as e:
            logger.error(f"配置文件解析错误: {e}")
            raise
        except Exception as e:
            logger.error(f"加载配置文件时发生错误: {e}", exc_info=True)
            raise
    
    def _validate_config(self):
        """
        验证配置文件的有效性
        
        Raises:
            ValueError: 当配置验证失败时
        """
        # 验证必要的配置项
        required_keys = ['targets', 'check_config', 'email', 'database', 'logging']
        for key in required_keys:
            if key not in self.config:
                raise ValueError(f"配置文件缺少必要的配置项: {key}")
        
        # 验证targets配置
        targets = self.config.get('targets', [])
        if not isinstance(targets, list) or len(targets) == 0:
            raise ValueError("配置文件中必须至少包含一个目标用户")
        
        for i, target in enumerate(targets):
            if not isinstance(target, dict):
                raise ValueError(f"目标配置 {i+1} 格式错误：必须是字典")
            if 'qq_number' not in target or 'bilibili_uid' not in target:
                raise ValueError(f"目标配置 {i+1} 缺少必要字段：qq_number 或 bilibili_uid")
            if not str(target['qq_number']).strip() or not str(target['bilibili_uid']).strip():
                raise ValueError(f"目标配置 {i+1} 的 qq_number 或 bilibili_uid 不能为空")
        
        # 验证check_config配置
        check_config = self.config.get('check_config', {})
        if 'check_interval_hours' not in check_config:
            raise ValueError("check_config 中缺少 check_interval_hours")
        if not isinstance(check_config['check_interval_hours'], (int, float)) or check_config['check_interval_hours'] <= 0:
            raise ValueError("check_interval_hours 必须是正数")
        if 'inactive_days_threshold' not in check_config:
            raise ValueError("check_config 中缺少 inactive_days_threshold")
        if not isinstance(check_config['inactive_days_threshold'], int) or check_config['inactive_days_threshold'] < 0:
            raise ValueError("inactive_days_threshold 必须是非负整数")
        
        # 验证email配置
        email_config = self.config.get('email', {})
        required_email_keys = ['smtp_server', 'smtp_port', 'sender_email', 'sender_password', 'receiver_email']
        for key in required_email_keys:
            if key not in email_config:
                raise ValueError(f"email 配置中缺少必要字段: {key}")
        if not isinstance(email_config['smtp_port'], int) or email_config['smtp_port'] <= 0:
            raise ValueError("smtp_port 必须是正整数")
        
        # 验证database配置
        database_config = self.config.get('database', {})
        if 'path' not in database_config:
            raise ValueError("database 配置中缺少 path 字段")

        # 验证 control_panel 配置
        panel_cfg = self.config.get('control_panel', {})
        if panel_cfg:
            if 'enabled' in panel_cfg and not isinstance(panel_cfg.get('enabled'), bool):
                raise ValueError("control_panel.enabled 必须为布尔值")
            if panel_cfg.get('enable_https'):
                if not panel_cfg.get('certfile') or not panel_cfg.get('keyfile'):
                    raise ValueError("启用 HTTPS 时必须提供 certfile 和 keyfile")

        # 验证 time_sync 配置
        ts_cfg = self.config.get('time_sync', {})
        if ts_cfg:
            servers = ts_cfg.get('servers', [])
            if servers and (not isinstance(servers, list) or not all(isinstance(s, str) for s in servers)):
                raise ValueError("time_sync.servers 必须是字符串列表")
            if 'max_skew_sec' in ts_cfg and ts_cfg['max_skew_sec'] <= 0:
                raise ValueError("time_sync.max_skew_sec 必须大于0")
            if 'min_success' in ts_cfg and ts_cfg['min_success'] <= 0:
                raise ValueError("time_sync.min_success 必须大于0")

        logger.debug("配置文件验证通过")

    def _start_control_panel(self):
        """启动控制面板（如配置启用）"""
        panel_cfg = self.config.get('control_panel', {})
        enabled = panel_cfg.get('enabled', False)
        if not enabled:
            return
        host = panel_cfg.get('host', '127.0.0.1')
        port = int(panel_cfg.get('port', 8080))
        auth_token = panel_cfg.get('auth_token', '')
        enable_https = bool(panel_cfg.get('enable_https', False))
        certfile = panel_cfg.get('certfile', '')
        keyfile = panel_cfg.get('keyfile', '')

        try:
            self.control_panel = ControlPanel(
                monitor_service=self,
                host=host,
                port=port,
                auth_token=auth_token,
                enable_https=enable_https,
                certfile=certfile,
                keyfile=keyfile,
            )
            self.control_panel.start()
            logger.info(f"控制面板已启动: {'https' if enable_https else 'http'}://{host}:{port}")
        except Exception as e:
            logger.error(f"控制面板启动失败: {e}", exc_info=True)
    
    def _signal_handler(self, signum, frame):
        """
        信号处理器，用于优雅退出
        
        Args:
            signum: 信号编号
            frame: 当前堆栈帧
        """
        signal_name = signal.Signals(signum).name if hasattr(signal, 'Signals') else str(signum)
        logger.info(f"接收到信号 {signal_name} ({signum})，准备优雅退出...")
        self.running = False
    
    def health_check(self) -> bool:
        """
        执行健康检查
        
        检查各个模块是否正常工作。
        
        Returns:
            bool: 健康检查是否通过
        """
        try:
            # 检查数据库连接
            test_record = self.db.get_latest_check_record("health_check", "health_check")
            logger.debug("数据库健康检查通过")
            
            # 检查B站检测器（简单测试）
            if not hasattr(self.checker, 'session'):
                logger.warning("B站检测器会话不存在")
                return False
            
            # 检查邮件发送器配置
            if not self.email_sender.sender_email or not self.email_sender.receiver_email:
                logger.warning("邮件发送器配置不完整")
                return False
            
            logger.debug("健康检查通过")
            return True
            
        except Exception as e:
            logger.error(f"健康检查失败: {e}", exc_info=True)
            return False
    
    def check_target(self, target: Dict) -> bool:
        """
        检查单个目标
        
        执行完整的检查流程：
        1. 获取用户活动状态
        2. 计算不活跃天数
        3. 保存检查记录
        4. 判断是否需要发送通知
        
        Args:
            target: 目标配置字典，必须包含：
                - qq_number: QQ号
                - bilibili_uid: B站UID
                - name: 用户名称（可选）
            
        Returns:
            bool: 检查是否成功
        """
        # 参数验证
        if not isinstance(target, dict):
            logger.error(f"无效的目标配置类型: {type(target)}")
            return False
        
        qq_number = str(target.get('qq_number', '')).strip()
        bilibili_uid = str(target.get('bilibili_uid', '')).strip()
        name = target.get('name', f"QQ_{qq_number}")
        
        if not qq_number or not bilibili_uid:
            logger.error(f"目标配置缺少必要字段: {target}")
            return False
        
        logger.info(f"开始检查目标: {name} (QQ: {qq_number}, UID: {bilibili_uid})")
        
        try:
            # 检查用户活动状态
            is_active, last_active_time, status_info = self.checker.check_user_activity(bilibili_uid)
            
            # 计算不活跃天数
            days_inactive = -1
            if last_active_time:
                days_inactive = self.checker.calculate_inactive_days(last_active_time)
            else:
                # 如果无法确定最后活动时间，检查历史记录
                latest_record = self.db.get_latest_check_record(qq_number, bilibili_uid)
                if latest_record and latest_record.get('last_active_time'):
                    try:
                        last_time_str = latest_record['last_active_time']
                        if last_time_str:
                            last_time = datetime.fromisoformat(last_time_str)
                            days_inactive = self.checker.calculate_inactive_days(last_time)
                            # 更新状态信息，说明使用了历史记录
                            status_info += f" (使用历史记录: {last_time.strftime('%Y-%m-%d %H:%M:%S')})"
                            logger.debug(f"使用历史记录计算不活跃天数: {days_inactive} 天")
                        else:
                            days_inactive = -1
                    except (ValueError, TypeError) as e:
                        logger.warning(f"解析历史记录时间失败: {e}")
                        days_inactive = -1
                else:
                    days_inactive = -1
                    status_info += " (无历史记录)"
            
            # 保存检查记录
            check_time = datetime.now()
            try:
                self.db.save_check_record(
                    qq_number=qq_number,
                    bilibili_uid=bilibili_uid,
                    check_time=check_time,
                    last_active_time=last_active_time,
                    is_active=is_active,
                    days_inactive=days_inactive if days_inactive >= 0 else 0,
                    status_info=status_info
                )
            except Exception as e:
                logger.error(f"保存检查记录失败: {name}, error={e}", exc_info=True)
                # 即使保存失败，也继续后续流程
            
            # 检查是否需要发送通知
            threshold_days = self.config['check_config']['inactive_days_threshold']
            
            if days_inactive >= threshold_days and days_inactive >= 0:
                # 检查最近是否已发送过通知（避免重复通知）
                recent_notifications = self.db.get_recent_notifications(
                    qq_number, bilibili_uid, hours=24
                )
                
                if not recent_notifications:
                    # 发送前进行时间校验（使用多源 NTP）
                    ts_cfg = self.config.get('time_sync', {})
                    servers = ts_cfg.get('servers', []) or ["ntp.aliyun.com", "ntp.tencent.com", "pool.ntp.org"]
                    max_skew_sec = ts_cfg.get('max_skew_sec', 2.0)
                    min_success = ts_cfg.get('min_success', 2)
                    try:
                        trusted_time = get_trusted_time(
                            servers,
                            timeout=ts_cfg.get('timeout', 3.0),
                            max_skew_sec=max_skew_sec,
                            min_success=min_success,
                        )
                        logger.debug(f"时间校验通过，可信时间: {datetime.fromtimestamp(trusted_time)}")
                    except TimeSyncError as e:
                        logger.error(f"时间校验失败，跳过告警发送: {e}")
                        return True

                    # 准备通知数据
                    check_data = {
                        'qq_number': qq_number,
                        'bilibili_uid': bilibili_uid,
                        'name': name,
                        'check_time': check_time.isoformat(),
                        'last_active_time': last_active_time.isoformat() if last_active_time else None,
                        'days_inactive': days_inactive,
                        'is_active': is_active,
                        'status_info': status_info
                    }
                    
                    # 发送邮件通知（多次重试）
                    try:
                        max_notify_retries = self.config.get('email', {}).get('notify_retries', 3)
                        notify_sent = False
                        for attempt in range(max_notify_retries):
                            email_sent = self.email_sender.send_notification_email(
                                qq_number=qq_number,
                                bilibili_uid=bilibili_uid,
                                name=name,
                                days_inactive=days_inactive,
                                last_active_time=last_active_time,
                                status_info=status_info,
                                check_data=check_data
                            )
                            if email_sent:
                                notify_sent = True
                                break
                            time.sleep(min(30, 2 ** attempt))
                        
                        if notify_sent:
                            # 保存通知记录
                            try:
                                self.db.save_notification_record(
                                    qq_number=qq_number,
                                    bilibili_uid=bilibili_uid,
                                    notification_time=check_time,
                                    days_inactive=days_inactive,
                                    status_info=status_info
                                )
                            except Exception as e:
                                logger.error(f"保存通知记录失败: {name}, error={e}", exc_info=True)
                            
                            logger.warning(f"已发送通知邮件: {name} (不活跃 {days_inactive} 天，阈值 {threshold_days} 天)")
                        else:
                            logger.error(f"发送通知邮件失败（重试 {max_notify_retries} 次后放弃）: {name}")
                    except Exception as e:
                        logger.error(f"发送通知邮件时发生异常: {name}, error={e}", exc_info=True)
                else:
                    logger.info(f"24小时内已发送过通知，跳过: {name} (上次通知时间: {recent_notifications[0].get('notification_time')})")
            else:
                if days_inactive >= 0:
                    logger.info(f"目标状态正常: {name} (不活跃 {days_inactive} 天，阈值 {threshold_days} 天)")
                else:
                    logger.info(f"目标状态检查完成但无法确定不活跃天数: {name}")
            
            return True
            
        except ValueError as e:
            logger.error(f"检查目标时参数错误: {name}, error={e}")
            return False
        except Exception as e:
            logger.error(f"检查目标时发生错误: {name}, error={e}", exc_info=True)
            return False
    
    def run_check_cycle(self):
        """
        执行一次检查周期
        
        遍历所有配置的目标，依次进行检查。
        在检查之间添加延迟以避免请求过快。
        """
        targets = self.config['targets']
        if not targets:
            logger.warning("没有配置目标用户，跳过检查周期")
            return
        
        logger.info(f"开始执行检查周期，目标数量: {len(targets)}")
        self.last_cycle_started = datetime.now()
        
        success_count = 0
        failed_count = 0
        
        for i, target in enumerate(targets, 1):
            if not self.running:
                logger.info("收到退出信号，中断检查周期")
                break
            
            try:
                logger.debug(f"检查目标 {i}/{len(targets)}: {target.get('name', target.get('qq_number', '未知'))}")
                if self.check_target(target):
                    success_count += 1
                else:
                    failed_count += 1
                
                # 在检查之间添加短暂延迟，避免请求过快
                if i < len(targets):  # 最后一个目标不需要延迟
                    time.sleep(2)
                    
            except KeyboardInterrupt:
                logger.info("收到键盘中断信号，中断检查周期")
                self.running = False
                break
            except Exception as e:
                failed_count += 1
                logger.error(f"检查目标时发生未捕获的异常: {e}", exc_info=True)
        
        self.last_cycle_finished = datetime.now()
        elapsed_time = (self.last_cycle_finished - self.last_cycle_started).total_seconds()
        logger.info(f"检查周期完成，成功: {success_count}/{len(targets)}, 失败: {failed_count}, 耗时: {elapsed_time:.2f}秒")
    
    def run(self):
        """
        运行监控服务
        
        启动主循环，定期执行检查任务。
        支持优雅退出和错误恢复。
        """
        check_interval_hours = self.config['check_config']['check_interval_hours']
        check_interval_seconds = check_interval_hours * 3600
        
        logger.info(f"监控服务启动，检查间隔: {check_interval_hours} 小时")
        logger.info(f"不活跃天数阈值: {self.config['check_config']['inactive_days_threshold']} 天")
        logger.info(f"目标用户数量: {len(self.config['targets'])}")
        
        # 执行健康检查
        if not self.health_check():
            logger.warning("健康检查未通过，但继续运行")
        
        # 立即执行一次检查
        try:
            self.run_check_cycle()
        except Exception as e:
            logger.error(f"初始检查周期失败: {e}", exc_info=True)
        
        # 循环执行检查
        cycle_count = 0
        while self.running:
            try:
                cycle_count += 1
                logger.info(f"等待 {check_interval_hours} 小时后进行下次检查 (周期 #{cycle_count})...")
                
                # 分段等待，以便能够响应退出信号
                wait_time = 0
                sleep_interval = 60  # 每次睡眠60秒
                
                while wait_time < check_interval_seconds and self.running:
                    sleep_duration = min(sleep_interval, check_interval_seconds - wait_time)
                    time.sleep(sleep_duration)
                    wait_time += sleep_duration
                    
                    # 每10分钟记录一次状态
                    if wait_time % 600 == 0:
                        uptime = datetime.now() - self.start_time
                        logger.debug(f"服务运行中，已运行: {uptime}, 等待时间: {wait_time}/{check_interval_seconds}秒")
                
                if self.running:
                    logger.info(f"开始执行检查周期 #{cycle_count}")
                    self.run_check_cycle()
                    
            except KeyboardInterrupt:
                logger.info("接收到键盘中断信号")
                self.running = False
                break
            except Exception as e:
                logger.error(f"运行监控服务时发生错误: {e}", exc_info=True)
                # 发生错误后等待一段时间再继续
                if self.running:
                    error_wait_time = 300  # 等待5分钟后重试
                    logger.info(f"等待 {error_wait_time} 秒后重试...")
                    time.sleep(error_wait_time)
        
        # 清理资源
        self._cleanup()
        
        uptime = datetime.now() - self.start_time
        logger.info(f"监控服务已停止，总运行时间: {uptime}")
    
    def _cleanup(self):
        """
        清理资源
        
        在服务停止时调用，确保所有资源被正确释放。
        """
        try:
            logger.debug("开始清理资源...")
            
            # 关闭B站检测器会话
            if hasattr(self, 'checker') and hasattr(self.checker, 'close'):
                self.checker.close()

            # 关闭控制面板
            if self.control_panel:
                self.control_panel.stop()
                self.control_panel = None
            
            # 数据库连接会在上下文管理器中自动关闭
            
            logger.debug("资源清理完成")
            
        except Exception as e:
            logger.warning(f"清理资源时发生错误: {e}", exc_info=True)


def main():
    """
    主函数
    
    程序的入口点，负责：
    1. 加载和配置日志系统
    2. 创建监控服务实例
    3. 启动监控服务
    4. 处理异常和退出
    """
    config_path = "config.yaml"
    
    # 先加载基本配置以设置日志
    try:
        if not os.path.exists(config_path):
            print(f"错误: 配置文件不存在: {config_path}")
            print("请确保配置文件存在并正确配置")
            sys.exit(1)
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        if config is None:
            print("错误: 配置文件为空或格式错误")
            sys.exit(1)
        
        logger_config = config.get('logging', {})
        setup_logger(
            log_level=logger_config.get('level', 'INFO'),
            log_file=logger_config.get('file', 'monitor.log'),
            max_bytes=logger_config.get('max_bytes', 10485760),
            backup_count=logger_config.get('backup_count', 5)
        )
        
    except FileNotFoundError:
        print(f"错误: 配置文件不存在: {config_path}")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"错误: 配置文件格式错误: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"错误: 加载配置文件失败: {e}")
        sys.exit(1)
    
    try:
        logger.info("=" * 60)
        logger.info("B站账号生命状态监控系统启动")
        logger.info("=" * 60)
        
        # 创建并运行监控服务
        service = MonitorService(config_path)
        service.run()
        
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
        sys.exit(0)
    except ValueError as e:
        logger.error(f"配置错误: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"程序启动失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

