"""
时间同步模块 - 使用多个 NTP 服务器校验时间

设计目标：
- 使用多个时间源取中位数，降低单点异常风险
- 校验本地时钟与可信时间的偏差，超限则抛出异常
- 仅使用标准库，避免额外依赖
"""
import socket
import struct
import time
from statistics import median
from typing import Iterable, List


class TimeSyncError(Exception):
    """时间同步异常"""


def _query_ntp(host: str, timeout: float) -> float:
    """向指定 NTP 服务器发起请求，返回 Unix 时间戳（秒）"""
    ntp_packet = b"\x1b" + 47 * b"\0"
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(ntp_packet, (host, 123))
        data, _ = sock.recvfrom(48)
    if len(data) < 48:
        raise TimeSyncError(f"NTP 响应长度异常: {host}")
    # 取 transmit timestamp 高 32 位（秒）
    transmit_ts = struct.unpack("!12I", data)[10]
    ntp_epoch = 2208988800  # 1900 to 1970
    return float(transmit_ts - ntp_epoch)


def get_trusted_time(
    servers: Iterable[str],
    *,
    timeout: float = 3.0,
    max_skew_sec: float = 2.0,
    min_success: int = 2,
) -> float:
    """
    获取可信时间戳（秒），使用多个 NTP 服务器取中位数并校验本地偏差。

    Args:
        servers: NTP 服务器列表
        timeout: 单个请求超时（秒）
        max_skew_sec: 允许的本地时钟偏差（秒）
        min_success: 最少成功的服务器数量

    Returns:
        可信 Unix 时间戳（秒）

    Raises:
        TimeSyncError: 当可用服务器不足或偏差超限
    """
    successes: List[float] = []
    for host in servers:
        try:
            ts = _query_ntp(host, timeout=timeout)
            successes.append(ts)
        except Exception:
            continue

    if len(successes) < min_success:
        raise TimeSyncError(f"NTP 可用响应不足，成功 {len(successes)}/{min_success}")

    trusted_ts = median(successes)
    skew = abs(trusted_ts - time.time())
    if skew > max_skew_sec:
        raise TimeSyncError(f"本地时间偏差过大: {skew:.3f}s (> {max_skew_sec}s)")

    return trusted_ts

