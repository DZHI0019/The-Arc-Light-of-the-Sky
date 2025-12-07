"""
数据库模块 - 负责数据存储和查询

本模块提供高可靠性的数据持久化功能，包括：
- 检查记录存储和查询
- 通知记录存储和查询
- 完善的错误处理和事务管理
- 数据库连接池管理
"""
import sqlite3
import logging
from datetime import datetime
from typing import Optional, List, Dict
from contextlib import contextmanager
import os
import threading

logger = logging.getLogger(__name__)


class Database:
    """
    数据库管理类
    
    提供高可靠性的SQLite数据库操作，包括：
    - 自动初始化表结构
    - 线程安全的连接管理
    - 完善的错误处理和事务管理
    - 数据验证
    """
    
    # 数据库版本，用于未来迁移
    DB_VERSION = 1
    
    def __init__(self, db_path: str, timeout: float = 10.0):
        """
        初始化数据库连接
        
        Args:
            db_path: 数据库文件路径
            timeout: 数据库连接超时时间（秒），默认10秒
            
        Raises:
            sqlite3.Error: 当数据库初始化失败时
        """
        if not db_path:
            raise ValueError("数据库路径不能为空")
        
        self.db_path = db_path
        self.timeout = timeout
        self._lock = threading.Lock()  # 用于线程安全
        
        # 确保数据库目录存在
        db_dir = os.path.dirname(os.path.abspath(db_path))
        if db_dir and not os.path.exists(db_dir):
            try:
                os.makedirs(db_dir, exist_ok=True)
                logger.info(f"创建数据库目录: {db_dir}")
            except OSError as e:
                logger.error(f"创建数据库目录失败: {e}")
                raise
        
        self._init_database()
        logger.info(f"数据库初始化完成: {db_path}")
    
    def _init_database(self):
        """
        初始化数据库表结构
        
        创建必要的表和索引，如果表已存在则跳过。
        
        Raises:
            sqlite3.Error: 当数据库操作失败时
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 创建版本表（用于未来数据库迁移）
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS db_version (
                        version INTEGER PRIMARY KEY,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 检查当前版本
                cursor.execute("SELECT version FROM db_version ORDER BY version DESC LIMIT 1")
                version_row = cursor.fetchone()
                current_version = version_row[0] if version_row else 0
                
                # 创建检查记录表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS check_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        qq_number TEXT NOT NULL,
                        bilibili_uid TEXT NOT NULL,
                        check_time TIMESTAMP NOT NULL,
                        last_active_time TIMESTAMP,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        days_inactive INTEGER DEFAULT 0,
                        status_info TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        CHECK (days_inactive >= 0 OR days_inactive = -1)
                    )
                """)
                
                # 创建通知记录表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS notification_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        qq_number TEXT NOT NULL,
                        bilibili_uid TEXT NOT NULL,
                        notification_time TIMESTAMP NOT NULL,
                        days_inactive INTEGER NOT NULL,
                        status_info TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        CHECK (days_inactive >= 0)
                    )
                """)
                
                # 创建索引以提高查询性能
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_check_records_qq_uid 
                    ON check_records(qq_number, bilibili_uid)
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_check_records_time 
                    ON check_records(check_time DESC)
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_notification_records_qq_uid 
                    ON notification_records(qq_number, bilibili_uid)
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_notification_records_time 
                    ON notification_records(notification_time DESC)
                """)
                
                # 更新数据库版本
                if current_version < self.DB_VERSION:
                    cursor.execute("""
                        INSERT OR REPLACE INTO db_version (version, updated_at)
                        VALUES (?, CURRENT_TIMESTAMP)
                    """, (self.DB_VERSION,))
                
                conn.commit()
                logger.debug(f"数据库表结构初始化完成: version={self.DB_VERSION}")
                
        except sqlite3.Error as e:
            logger.error(f"数据库初始化失败: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"数据库初始化时发生未知错误: {e}", exc_info=True)
            raise
    
    @contextmanager
    def _get_connection(self):
        """
        获取数据库连接的上下文管理器
        
        提供线程安全的数据库连接管理，自动处理事务和错误。
        
        Yields:
            sqlite3.Connection: 数据库连接对象
            
        Raises:
            sqlite3.Error: 当数据库操作失败时
        """
        conn = None
        try:
            # 使用线程锁确保线程安全
            with self._lock:
                conn = sqlite3.connect(
                    self.db_path,
                    timeout=self.timeout,
                    check_same_thread=False  # 允许多线程访问
                )
                conn.row_factory = sqlite3.Row
                # 启用外键约束（虽然当前没有外键，但为未来做准备）
                conn.execute("PRAGMA foreign_keys = ON")
                # 设置WAL模式以提高并发性能
                conn.execute("PRAGMA journal_mode = WAL")
                yield conn
        except sqlite3.Error as e:
            if conn:
                try:
                    conn.rollback()
                except:
                    pass
            logger.error(f"数据库连接错误: {e}", exc_info=True)
            raise
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except:
                    pass
            logger.error(f"数据库操作时发生未知错误: {e}", exc_info=True)
            raise
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass
    
    def save_check_record(self, qq_number: str, bilibili_uid: str, 
                         check_time: datetime, last_active_time: Optional[datetime],
                         is_active: bool, days_inactive: int, status_info: str = ""):
        """
        保存检查记录
        
        Args:
            qq_number: QQ号（字符串格式）
            bilibili_uid: B站UID（字符串格式）
            check_time: 检查时间（datetime对象）
            last_active_time: 最后活动时间（datetime对象，可为None）
            is_active: 是否活跃（布尔值）
            days_inactive: 不活跃天数（整数，-1表示无法确定）
            status_info: 状态信息（字符串，默认空字符串）
            
        Raises:
            ValueError: 当参数验证失败时
            sqlite3.Error: 当数据库操作失败时
        """
        # 参数验证
        if not qq_number or not isinstance(qq_number, str):
            raise ValueError(f"无效的QQ号: {qq_number}")
        if not bilibili_uid or not isinstance(bilibili_uid, str):
            raise ValueError(f"无效的B站UID: {bilibili_uid}")
        if not isinstance(check_time, datetime):
            raise ValueError(f"无效的检查时间类型: {type(check_time)}")
        if not isinstance(is_active, bool):
            raise ValueError(f"无效的is_active类型: {type(is_active)}")
        if not isinstance(days_inactive, int):
            raise ValueError(f"无效的days_inactive类型: {type(days_inactive)}")
        
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO check_records 
                    (qq_number, bilibili_uid, check_time, last_active_time, 
                     is_active, days_inactive, status_info)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(qq_number).strip(),
                    str(bilibili_uid).strip(),
                    check_time.isoformat(),
                    last_active_time.isoformat() if last_active_time else None,
                    1 if is_active else 0,
                    days_inactive,
                    str(status_info) if status_info else ""
                ))
                conn.commit()
                record_id = cursor.lastrowid
                logger.debug(f"保存检查记录成功: ID={record_id}, QQ={qq_number}, UID={bilibili_uid}, 不活跃天数={days_inactive}")
        except sqlite3.IntegrityError as e:
            logger.error(f"保存检查记录失败（完整性错误）: QQ={qq_number}, UID={bilibili_uid}, error={e}")
            raise
        except sqlite3.Error as e:
            logger.error(f"保存检查记录失败（数据库错误）: QQ={qq_number}, UID={bilibili_uid}, error={e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"保存检查记录失败（未知错误）: QQ={qq_number}, UID={bilibili_uid}, error={e}", exc_info=True)
            raise
    
    def save_notification_record(self, qq_number: str, bilibili_uid: str,
                                notification_time: datetime, days_inactive: int,
                                status_info: str = ""):
        """
        保存通知记录
        
        Args:
            qq_number: QQ号（字符串格式）
            bilibili_uid: B站UID（字符串格式）
            notification_time: 通知时间（datetime对象）
            days_inactive: 不活跃天数（非负整数）
            status_info: 状态信息（字符串，默认空字符串）
            
        Raises:
            ValueError: 当参数验证失败时
            sqlite3.Error: 当数据库操作失败时
        """
        # 参数验证
        if not qq_number or not isinstance(qq_number, str):
            raise ValueError(f"无效的QQ号: {qq_number}")
        if not bilibili_uid or not isinstance(bilibili_uid, str):
            raise ValueError(f"无效的B站UID: {bilibili_uid}")
        if not isinstance(notification_time, datetime):
            raise ValueError(f"无效的通知时间类型: {type(notification_time)}")
        if not isinstance(days_inactive, int) or days_inactive < 0:
            raise ValueError(f"无效的不活跃天数: {days_inactive}（必须为非负整数）")
        
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO notification_records 
                    (qq_number, bilibili_uid, notification_time, days_inactive, status_info)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    str(qq_number).strip(),
                    str(bilibili_uid).strip(),
                    notification_time.isoformat(),
                    days_inactive,
                    str(status_info) if status_info else ""
                ))
                conn.commit()
                record_id = cursor.lastrowid
                logger.info(f"保存通知记录成功: ID={record_id}, QQ={qq_number}, UID={bilibili_uid}, 不活跃天数={days_inactive}")
        except sqlite3.IntegrityError as e:
            logger.error(f"保存通知记录失败（完整性错误）: QQ={qq_number}, UID={bilibili_uid}, error={e}")
            raise
        except sqlite3.Error as e:
            logger.error(f"保存通知记录失败（数据库错误）: QQ={qq_number}, UID={bilibili_uid}, error={e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"保存通知记录失败（未知错误）: QQ={qq_number}, UID={bilibili_uid}, error={e}", exc_info=True)
            raise
    
    def get_latest_check_record(self, qq_number: str, bilibili_uid: str) -> Optional[Dict]:
        """
        获取最新的检查记录
        
        Args:
            qq_number: QQ号（字符串格式）
            bilibili_uid: B站UID（字符串格式）
            
        Returns:
            Optional[Dict]: 最新检查记录字典，如果不存在则返回None
                字典包含：id, qq_number, bilibili_uid, check_time, last_active_time,
                         is_active, days_inactive, status_info, created_at
        """
        # 参数验证
        if not qq_number or not isinstance(qq_number, str):
            logger.warning(f"无效的QQ号: {qq_number}")
            return None
        if not bilibili_uid or not isinstance(bilibili_uid, str):
            logger.warning(f"无效的B站UID: {bilibili_uid}")
            return None
        
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM check_records
                    WHERE qq_number = ? AND bilibili_uid = ?
                    ORDER BY check_time DESC
                    LIMIT 1
                """, (str(qq_number).strip(), str(bilibili_uid).strip()))
                
                row = cursor.fetchone()
                if row:
                    record = dict(row)
                    logger.debug(f"获取最新检查记录成功: QQ={qq_number}, UID={bilibili_uid}")
                    return record
                else:
                    logger.debug(f"未找到检查记录: QQ={qq_number}, UID={bilibili_uid}")
                    return None
        except sqlite3.Error as e:
            logger.error(f"获取最新检查记录失败（数据库错误）: QQ={qq_number}, UID={bilibili_uid}, error={e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"获取最新检查记录失败（未知错误）: QQ={qq_number}, UID={bilibili_uid}, error={e}", exc_info=True)
            return None
    
    def get_recent_notifications(self, qq_number: str, bilibili_uid: str,
                                hours: int = 24) -> List[Dict]:
        """
        获取最近的通知记录
        
        Args:
            qq_number: QQ号（字符串格式）
            bilibili_uid: B站UID（字符串格式）
            hours: 最近多少小时内的通知（正整数，默认24小时）
            
        Returns:
            List[Dict]: 通知记录列表，每个字典包含：
                id, qq_number, bilibili_uid, notification_time, days_inactive,
                status_info, created_at
        """
        # 参数验证
        if not qq_number or not isinstance(qq_number, str):
            logger.warning(f"无效的QQ号: {qq_number}")
            return []
        if not bilibili_uid or not isinstance(bilibili_uid, str):
            logger.warning(f"无效的B站UID: {bilibili_uid}")
            return []
        if not isinstance(hours, int) or hours < 0:
            logger.warning(f"无效的小时数: {hours}，使用默认值24")
            hours = 24
        
        try:
            from datetime import timedelta
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM notification_records
                    WHERE qq_number = ? AND bilibili_uid = ?
                    AND notification_time >= ?
                    ORDER BY notification_time DESC
                """, (
                    str(qq_number).strip(),
                    str(bilibili_uid).strip(),
                    cutoff_time.isoformat()
                ))
                
                rows = cursor.fetchall()
                records = [dict(row) for row in rows]
                logger.debug(f"获取最近通知记录成功: QQ={qq_number}, UID={bilibili_uid}, 记录数={len(records)}, 时间范围={hours}小时")
                return records
        except sqlite3.Error as e:
            logger.error(f"获取最近通知记录失败（数据库错误）: QQ={qq_number}, UID={bilibili_uid}, error={e}", exc_info=True)
            return []
        except Exception as e:
            logger.error(f"获取最近通知记录失败（未知错误）: QQ={qq_number}, UID={bilibili_uid}, error={e}", exc_info=True)
            return []

