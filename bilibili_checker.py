"""
B站账号检测模块 - 负责检测B站账号的活动状态

本模块提供高可靠性的B站账号活动状态检测功能，包括：
- 用户信息获取
- 动态信息获取
- 活动状态判断
- 完善的错误处理和重试机制
"""
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
import time

logger = logging.getLogger(__name__)


class BilibiliChecker:
    """
    B站账号检测类
    
    提供高可靠性的B站账号活动状态检测功能，包括：
    - 自动重试机制
    - 连接池管理
    - 完善的错误处理
    - 超时控制
    """
    
    # B站API端点
    API_USER_INFO = "https://api.bilibili.com/x/space/acc/info"
    API_USER_DYNAMICS = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space"
    
    def __init__(self, timeout: int = 10, retry_times: int = 3, 
                 max_retries: int = 3, backoff_factor: float = 0.5):
        """
        初始化B站检测器
        
        Args:
            timeout: 请求超时时间（秒），默认10秒
            retry_times: 重试次数，默认3次
            max_retries: HTTP适配器最大重试次数，默认3次
            backoff_factor: 重试退避因子，默认0.5秒
        """
        self.timeout = timeout
        self.retry_times = retry_times
        
        # 创建带重试策略的会话
        self.session = requests.Session()
        
        # 配置重试策略
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        
        # 配置HTTP适配器
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=20
        )
        
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # 设置请求头
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.bilibili.com/',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive'
        })
        
        logger.debug(f"B站检测器初始化完成: timeout={timeout}s, retry_times={retry_times}")
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口，确保资源清理"""
        self.close()
    
    def close(self):
        """关闭会话，释放资源"""
        if hasattr(self, 'session') and self.session:
            self.session.close()
            logger.debug("B站检测器会话已关闭")
    
    def get_user_info(self, uid: str) -> Optional[Dict]:
        """
        获取用户基本信息
        
        Args:
            uid: B站UID（字符串格式）
            
        Returns:
            用户信息字典，如果获取失败返回None
            
        Raises:
            ValueError: 当UID格式无效时
        """
        # 验证UID格式
        if not uid or not str(uid).strip().isdigit():
            logger.error(f"无效的UID格式: {uid}")
            raise ValueError(f"无效的UID格式: {uid}")
        
        uid = str(uid).strip()
        url = f"{self.API_USER_INFO}?mid={uid}"
        
        for attempt in range(self.retry_times):
            try:
                logger.debug(f"获取用户信息 (尝试 {attempt + 1}/{self.retry_times}): UID={uid}")
                response = self.session.get(url, timeout=self.timeout)
                response.raise_for_status()
                
                # 验证响应内容类型
                if 'application/json' not in response.headers.get('Content-Type', ''):
                    logger.warning(f"响应内容类型异常: UID={uid}, Content-Type={response.headers.get('Content-Type')}")
                
                data = response.json()
                
                # 验证响应数据结构
                if not isinstance(data, dict):
                    logger.error(f"响应数据格式异常: UID={uid}, 数据类型={type(data)}")
                    if attempt < self.retry_times - 1:
                        time.sleep(2 ** attempt)
                        continue
                    return None
                
                code = data.get('code')
                if code == 0:
                    user_info = data.get('data', {})
                    if user_info:
                        logger.debug(f"成功获取用户信息: UID={uid}, 用户名={user_info.get('name', '未知')}")
                        return user_info
                    else:
                        logger.warning(f"用户信息为空: UID={uid}")
                        return None
                else:
                    error_msg = data.get('message', '未知错误')
                    logger.warning(f"获取用户信息失败: UID={uid}, code={code}, message={error_msg}")
                    # 如果是用户不存在或已注销，不重试
                    if code in [-404, -400]:
                        return None
                    if attempt < self.retry_times - 1:
                        time.sleep(2 ** attempt)
                        continue
                    return None
                    
            except requests.exceptions.Timeout:
                logger.warning(f"请求超时 (尝试 {attempt + 1}/{self.retry_times}): UID={uid}")
                if attempt < self.retry_times - 1:
                    time.sleep(2 ** attempt)  # 指数退避
                else:
                    logger.error(f"请求超时，已达到最大重试次数: UID={uid}")
                    return None
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"请求异常 (尝试 {attempt + 1}/{self.retry_times}): UID={uid}, error={e}")
                if attempt < self.retry_times - 1:
                    time.sleep(2 ** attempt)
                else:
                    logger.error(f"请求异常，已达到最大重试次数: UID={uid}")
                    return None
                    
            except json.JSONDecodeError as e:
                logger.error(f"JSON解析失败: UID={uid}, error={e}")
                if attempt < self.retry_times - 1:
                    time.sleep(2 ** attempt)
                else:
                    return None
                    
            except Exception as e:
                logger.error(f"获取用户信息时发生未知错误: UID={uid}, error={e}", exc_info=True)
                if attempt < self.retry_times - 1:
                    time.sleep(2 ** attempt)
                else:
                    return None
        
        return None
    
    def get_user_dynamics(self, uid: str, page_size: int = 5) -> Optional[Dict]:
        """
        获取用户最新动态
        
        Args:
            uid: B站UID（字符串格式）
            page_size: 获取动态数量，默认5条（用于提高准确性）
            
        Returns:
            动态信息字典 {'dynamics': [...], 'count': int}，如果获取失败返回None
            
        Raises:
            ValueError: 当UID格式无效或page_size无效时
        """
        # 验证参数
        if not uid or not str(uid).strip().isdigit():
            logger.error(f"无效的UID格式: {uid}")
            raise ValueError(f"无效的UID格式: {uid}")
        
        if not isinstance(page_size, int) or page_size < 1 or page_size > 20:
            logger.warning(f"无效的page_size: {page_size}，使用默认值5")
            page_size = 5
        
        uid = str(uid).strip()
        url = self.API_USER_DYNAMICS
        params = {
            'host_mid': uid,
            'page_size': page_size,
            'offset': ''
        }
        
        for attempt in range(self.retry_times):
            try:
                logger.debug(f"获取用户动态 (尝试 {attempt + 1}/{self.retry_times}): UID={uid}, page_size={page_size}")
                response = self.session.get(url, params=params, timeout=self.timeout)
                response.raise_for_status()
                
                # 验证响应内容类型
                if 'application/json' not in response.headers.get('Content-Type', ''):
                    logger.warning(f"响应内容类型异常: UID={uid}, Content-Type={response.headers.get('Content-Type')}")
                
                data = response.json()
                
                # 验证响应数据结构
                if not isinstance(data, dict):
                    logger.error(f"响应数据格式异常: UID={uid}, 数据类型={type(data)}")
                    if attempt < self.retry_times - 1:
                        time.sleep(2 ** attempt)
                        continue
                    return None
                
                code = data.get('code')
                if code == 0:
                    data_dict = data.get('data', {})
                    dynamics = data_dict.get('items', [])
                    count = len(dynamics)
                    logger.debug(f"成功获取用户动态: UID={uid}, 动态数量={count}")
                    return {'dynamics': dynamics, 'count': count}
                else:
                    error_msg = data.get('message', '未知错误')
                    logger.warning(f"获取用户动态失败: UID={uid}, code={code}, message={error_msg}")
                    # 如果是用户不存在或已注销，不重试
                    if code in [-404, -400]:
                        return None
                    if attempt < self.retry_times - 1:
                        time.sleep(2 ** attempt)
                        continue
                    return None
                    
            except requests.exceptions.Timeout:
                logger.warning(f"请求超时 (尝试 {attempt + 1}/{self.retry_times}): UID={uid}")
                if attempt < self.retry_times - 1:
                    time.sleep(2 ** attempt)
                else:
                    logger.error(f"请求超时，已达到最大重试次数: UID={uid}")
                    return None
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"请求异常 (尝试 {attempt + 1}/{self.retry_times}): UID={uid}, error={e}")
                if attempt < self.retry_times - 1:
                    time.sleep(2 ** attempt)
                else:
                    logger.error(f"请求异常，已达到最大重试次数: UID={uid}")
                    return None
                    
            except json.JSONDecodeError as e:
                logger.error(f"JSON解析失败: UID={uid}, error={e}")
                if attempt < self.retry_times - 1:
                    time.sleep(2 ** attempt)
                else:
                    return None
                    
            except Exception as e:
                logger.error(f"获取用户动态时发生未知错误: UID={uid}, error={e}", exc_info=True)
                if attempt < self.retry_times - 1:
                    time.sleep(2 ** attempt)
                else:
                    return None
        
        return None
    
    def check_user_activity(self, uid: str) -> Tuple[bool, Optional[datetime], str]:
        """
        检查用户活动状态
        
        通过获取用户信息和最新动态来判断用户的活动状态。
        优先使用动态时间作为最后活动时间，如果无法获取动态则返回None。
        
        Args:
            uid: B站UID（字符串格式）
            
        Returns:
            Tuple[bool, Optional[datetime], str]:
                - bool: 是否活跃（账号是否存在且可访问）
                - Optional[datetime]: 最后活动时间（如果无法确定则为None）
                - str: 状态信息描述
                
        Raises:
            ValueError: 当UID格式无效时
        """
        try:
            # 验证UID格式
            if not uid or not str(uid).strip().isdigit():
                raise ValueError(f"无效的UID格式: {uid}")
            
            uid = str(uid).strip()
            logger.info(f"开始检查用户活动状态: UID={uid}")
            
            # 获取用户信息
            user_info = self.get_user_info(uid)
            if not user_info:
                logger.warning(f"无法获取用户信息: UID={uid}")
                return False, None, "无法获取用户信息，可能账号不存在或已注销"
            
            # 检查账号状态
            if user_info.get('face') is None:
                logger.warning(f"账号可能已注销: UID={uid}")
                return False, None, "账号可能已注销"
            
            # 获取用户名
            username = user_info.get('name', '未知')
            logger.debug(f"用户信息获取成功: UID={uid}, 用户名={username}")
            
            # 获取最新动态
            dynamics_info = self.get_user_dynamics(uid, page_size=5)
            
            last_active_time = None
            status_info = f"用户名: {username}"
            
            if dynamics_info and dynamics_info.get('dynamics'):
                dynamics_list = dynamics_info['dynamics']
                logger.debug(f"获取到 {len(dynamics_list)} 条动态: UID={uid}")
                
                # 遍历动态列表，找到最新的有效时间戳
                for dynamic in dynamics_list:
                    if not isinstance(dynamic, dict):
                        continue
                    
                    timestamp = None
                    
                    # 方式1: 从 module_author 获取 pub_ts
                    modules = dynamic.get('modules', {})
                    if isinstance(modules, dict):
                        module_author = modules.get('module_author', {})
                        if isinstance(module_author, dict):
                            timestamp = module_author.get('pub_ts')
                    
                    # 方式2: 从动态根节点获取 pub_ts
                    if not timestamp:
                        timestamp = dynamic.get('pub_ts')
                    
                    # 方式3: 从 extend_json 获取
                    if not timestamp:
                        extend_json = dynamic.get('extend_json')
                        if isinstance(extend_json, str):
                            try:
                                extend_data = json.loads(extend_json)
                                if isinstance(extend_data, dict):
                                    timestamp = extend_data.get('pub_ts') or extend_data.get('timestamp')
                            except (json.JSONDecodeError, TypeError) as e:
                                logger.debug(f"解析extend_json失败: {e}")
                    
                    # 如果找到时间戳，转换为datetime
                    if timestamp:
                        try:
                            # 处理时间戳（可能是秒或毫秒）
                            if isinstance(timestamp, (int, float)):
                                if timestamp > 1e10:  # 毫秒时间戳
                                    timestamp = timestamp / 1000
                                last_active_time = datetime.fromtimestamp(timestamp)
                                logger.debug(f"解析到活动时间: UID={uid}, 时间={last_active_time}")
                                break  # 找到第一个有效时间戳即可
                        except (ValueError, OSError) as e:
                            logger.warning(f"时间戳转换失败: UID={uid}, timestamp={timestamp}, error={e}")
                            continue
                
                if last_active_time:
                    status_info += f", 最新动态时间: {last_active_time.strftime('%Y-%m-%d %H:%M:%S')}"
                else:
                    status_info += ", 无法解析动态时间"
            else:
                logger.debug(f"无法获取动态信息: UID={uid}")
                status_info += ", 无法获取动态信息（可能用户未发布动态或动态被隐藏）"
            
            # 如果无法确定最后活动时间
            if last_active_time is None:
                status_info += ", 无法确定最后活动时间"
                logger.warning(f"无法确定最后活动时间: UID={uid}")
            
            logger.info(f"用户活动状态检查完成: UID={uid}, 活跃={True}, 最后活动时间={last_active_time}")
            return True, last_active_time, status_info
            
        except ValueError as e:
            logger.error(f"参数验证失败: {e}")
            raise
        except Exception as e:
            logger.error(f"检查用户活动状态时发生错误: UID={uid}, error={e}", exc_info=True)
            return False, None, f"检查过程发生错误: {str(e)}"
    
    def calculate_inactive_days(self, last_active_time: Optional[datetime]) -> int:
        """
        计算不活跃天数
        
        计算从最后活动时间到当前时间的天数差。
        
        Args:
            last_active_time: 最后活动时间（datetime对象）
            
        Returns:
            int: 不活跃天数（非负整数），如果无法确定则返回-1
            
        Note:
            - 如果最后活动时间在未来，返回0
            - 如果最后活动时间为None，返回-1
        """
        if last_active_time is None:
            logger.debug("最后活动时间为None，返回-1")
            return -1
        
        if not isinstance(last_active_time, datetime):
            logger.error(f"无效的时间类型: {type(last_active_time)}")
            return -1
        
        try:
            now = datetime.now()
            delta = now - last_active_time
            
            # 如果最后活动时间在未来（不应该发生，但做保护）
            if delta.total_seconds() < 0:
                logger.warning(f"最后活动时间在未来: {last_active_time}, 当前时间: {now}")
                return 0
            
            days = delta.days
            logger.debug(f"计算不活跃天数: 最后活动时间={last_active_time}, 当前时间={now}, 天数={days}")
            return days
            
        except Exception as e:
            logger.error(f"计算不活跃天数时发生错误: error={e}", exc_info=True)
            return -1

