"""
邮件发送模块 - 负责发送通知邮件

本模块提供高可靠性的邮件发送功能，包括：
- SMTP邮件发送
- 完善的错误处理和重试机制
- HTML和纯文本格式支持
- 邮件模板生成
"""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from datetime import datetime
from typing import Dict, List, Optional
import json
import time
import os

logger = logging.getLogger(__name__)


class EmailSender:
    """
    邮件发送类
    
    提供高可靠性的SMTP邮件发送功能，包括：
    - 自动重试机制
    - 完善的错误处理
    - HTML和纯文本格式支持
    """
    
    def __init__(self, smtp_server: str, smtp_port: int, 
                 sender_email: str, sender_password: str,
                 receiver_email: str, subject_prefix: str = "",
                 timeout: int = 30, max_retries: int = 3,
                 use_ssl: bool = False):
        """
        初始化邮件发送器
        
        Args:
            smtp_server: SMTP服务器地址（如 smtp.qq.com）
            smtp_port: SMTP端口（如 587）
            sender_email: 发送者邮箱地址
            sender_password: 发送者密码/授权码（注意：QQ邮箱需要使用授权码）
            receiver_email: 接收者邮箱地址
            subject_prefix: 邮件主题前缀（默认空字符串）
            timeout: SMTP连接超时时间（秒），默认30秒
            max_retries: 最大重试次数，默认3次
            
        Raises:
            ValueError: 当参数验证失败时
        """
        # 参数验证
        if not smtp_server or not isinstance(smtp_server, str):
            raise ValueError(f"无效的SMTP服务器地址: {smtp_server}")
        if not isinstance(smtp_port, int) or smtp_port <= 0 or smtp_port > 65535:
            raise ValueError(f"无效的SMTP端口: {smtp_port}")
        if not sender_email or '@' not in sender_email:
            raise ValueError(f"无效的发送者邮箱: {sender_email}")
        if not sender_password:
            raise ValueError("发送者密码/授权码不能为空")
        if not receiver_email or '@' not in receiver_email:
            raise ValueError(f"无效的接收者邮箱: {receiver_email}")
        
        self.smtp_server = smtp_server.strip()
        self.smtp_port = smtp_port
        self.sender_email = sender_email.strip()
        self.sender_password = sender_password
        self.receiver_email = receiver_email.strip()
        self.subject_prefix = str(subject_prefix) if subject_prefix else ""
        self.timeout = timeout
        self.max_retries = max_retries
        # 是否使用 SSL 直连（如端口465）
        self.use_ssl = bool(use_ssl)
        
        logger.debug(f"邮件发送器初始化完成: SMTP={smtp_server}:{smtp_port}, 发送者={sender_email}, 接收者={receiver_email}")
    
    def _create_message(self, subject: str, body: str, 
                       html_body: Optional[str] = None) -> MIMEMultipart:
        """
        创建邮件消息
        
        Args:
            subject: 邮件主题
            body: 纯文本正文
            html_body: HTML正文（可选）
            
        Returns:
            MIMEMultipart消息对象
        """
        msg = MIMEMultipart('alternative')
        msg['From'] = Header(self.sender_email, 'utf-8')
        msg['To'] = Header(self.receiver_email, 'utf-8')
        msg['Subject'] = Header(subject, 'utf-8')
        
        # 添加纯文本部分
        text_part = MIMEText(body, 'plain', 'utf-8')
        msg.attach(text_part)
        
        # 添加HTML部分（如果提供）
        if html_body:
            html_part = MIMEText(html_body, 'html', 'utf-8')
            msg.attach(html_part)
        
        return msg
    
    def send_email(self, subject: str, body: str, 
                   html_body: Optional[str] = None) -> bool:
        """
        发送邮件（带重试机制）
        
        Args:
            subject: 邮件主题（字符串）
            body: 纯文本正文（字符串）
            html_body: HTML正文（可选，字符串）
            
        Returns:
            bool: 发送是否成功
            
        Note:
            - 如果提供html_body，邮件客户端会优先显示HTML版本
            - 如果HTML显示失败，会回退到纯文本版本
        """
        # 参数验证
        if not subject or not isinstance(subject, str):
            logger.error(f"无效的邮件主题: {subject}")
            return False
        if not body or not isinstance(body, str):
            logger.error(f"无效的邮件正文: {body}")
            return False
        
        for attempt in range(self.max_retries):
            try:
                # 创建邮件消息
                msg = self._create_message(subject, body, html_body)
                
                # 连接SMTP服务器并发送
                logger.debug(f"尝试发送邮件 (尝试 {attempt + 1}/{self.max_retries}): 主题={subject}")
                
                # 支持通过环境变量设置 SMTP 超时时间覆盖
                env_timeout = os.environ.get('EMAIL_TIMEOUT')
                if env_timeout:
                    try:
                        self.timeout = int(env_timeout)
                    except Exception:
                        pass

                server = None
                try:
                    # 如果配置为 SSL（常见端口465），使用 SMTP_SSL 直接建立加密连接
                    if self.use_ssl or self.smtp_port == 465:
                        server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, timeout=self.timeout)
                    else:
                        server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=self.timeout)
                        # 启用 STARTTLS
                        try:
                            server.starttls()
                        except Exception:
                            # 有些服务器不支持 starttls，忽略失败并继续尝试登录
                            logger.debug("STARTTLS 不可用或失败，继续尝试登录（如果服务器允许）")

                    server.login(self.sender_email, self.sender_password)
                    server.sendmail(self.sender_email, [self.receiver_email], msg.as_string())
                    logger.info(f"邮件发送成功: 主题={subject}, 接收者={self.receiver_email}")
                    return True
                finally:
                    if server:
                        try:
                            server.quit()
                        except:
                            pass
                
            except smtplib.SMTPAuthenticationError as e:
                logger.error(f"SMTP认证失败: {e}")
                # 认证失败不重试
                return False
            except smtplib.SMTPRecipientsRefused as e:
                logger.error(f"收件人地址被拒绝: {e}")
                # 收件人错误不重试
                return False
            except smtplib.SMTPServerDisconnected as e:
                logger.warning(f"SMTP服务器断开连接 (尝试 {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)  # 指数退避
                    continue
                else:
                    logger.error(f"SMTP服务器断开连接，已达到最大重试次数")
                    return False
            except smtplib.SMTPException as e:
                logger.error(f"SMTP错误 (尝试 {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                else:
                    logger.error(f"SMTP错误，已达到最大重试次数")
                    return False
            except Exception as e:
                logger.error(f"发送邮件时发生未知错误 (尝试 {attempt + 1}/{self.max_retries}): {e}", exc_info=True)
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                else:
                    return False
        
        return False
    
    def send_notification_email(self, qq_number: str, bilibili_uid: str,
                               name: str, days_inactive: int, 
                               last_active_time: Optional[datetime],
                               status_info: str, check_data: Dict) -> bool:
        """
        发送通知邮件
        
        Args:
            qq_number: QQ号
            bilibili_uid: B站UID
            name: 用户名称
            days_inactive: 不活跃天数
            last_active_time: 最后活动时间
            status_info: 状态信息
            check_data: 检查数据字典
            
        Returns:
            发送是否成功
        """
        # 构建邮件主题
        subject = f"{self.subject_prefix} 检测到异常 - {name} (QQ: {qq_number})"
        
        # 构建纯文本正文
        body_lines = [
            f"检测到目标用户出现异常情况：",
            "",
            f"用户信息：",
            f"  - 名称: {name}",
            f"  - QQ号: {qq_number}",
            f"  - B站UID: {bilibili_uid}",
            "",
            f"检测结果：",
            f"  - 不活跃天数: {days_inactive} 天",
        ]
        
        if last_active_time:
            body_lines.append(f"  - 最后活动时间: {last_active_time.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            body_lines.append(f"  - 最后活动时间: 无法确定")
        
        body_lines.extend([
            f"  - 状态信息: {status_info}",
            "",
            f"检测时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "详细数据：",
            json.dumps(check_data, ensure_ascii=False, indent=2)
        ])
        
        body = "\n".join(body_lines)
        
        # 构建HTML正文
        html_body = f"""
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                .header {{ background-color: #f4f4f4; padding: 20px; border-radius: 5px; }}
                .content {{ padding: 20px; }}
                .info-item {{ margin: 10px 0; }}
                .warning {{ color: #d9534f; font-weight: bold; }}
                .data {{ background-color: #f9f9f9; padding: 15px; border-radius: 5px; font-family: monospace; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>⚠️ 生命状态监控警报</h2>
            </div>
            <div class="content">
                <h3>用户信息</h3>
                <div class="info-item"><strong>名称:</strong> {name}</div>
                <div class="info-item"><strong>QQ号:</strong> {qq_number}</div>
                <div class="info-item"><strong>B站UID:</strong> {bilibili_uid}</div>
                
                <h3>检测结果</h3>
                <div class="info-item warning">
                    <strong>不活跃天数:</strong> {days_inactive} 天
                </div>
                <div class="info-item">
                    <strong>最后活动时间:</strong> {last_active_time.strftime('%Y-%m-%d %H:%M:%S') if last_active_time else '无法确定'}
                </div>
                <div class="info-item">
                    <strong>状态信息:</strong> {status_info}
                </div>
                
                <div class="info-item">
                    <strong>检测时间:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                </div>
                
                <h3>详细数据</h3>
                <div class="data">
                    <pre>{json.dumps(check_data, ensure_ascii=False, indent=2)}</pre>
                </div>
            </div>
        </body>
        </html>
        """
        
        return self.send_email(subject, body, html_body)

