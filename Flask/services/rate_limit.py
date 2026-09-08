"""轻量级滑动窗口限流器（内存实现，进程内有效）。

用于登录/注册/验证码等敏感接口防止暴力破解与刷接口。
生产多 worker（gunicorn）场景下为进程级限制，仍能起到基础防护作用。
如需要跨进程一致限流，可替换为 Redis 存储。
"""
import time
from collections import deque, defaultdict


class SlidingWindowLimiter:
    def __init__(self):
        self._hits = defaultdict(deque)

    def hit(self, key: str, limit: int, window_seconds: int) -> bool:
        """记录一次访问。返回 True 表示允许，False 表示已触发限流。"""
        now = time.time()
        q = self._hits[key]
        cutoff = now - window_seconds
        while q and q[0] <= cutoff:
            q.popleft()

        if len(q) >= limit:
            return False

        q.append(now)
        return True


limiter = SlidingWindowLimiter()