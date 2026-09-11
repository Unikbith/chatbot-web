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


def client_ip():
    """获取客户端真实 IP（仅可信代理后才解析 X-Forwarded-For）。"""
    from flask import request, current_app
    if current_app.config.get('TRUST_PROXY_HEADERS'):
        fwd = request.headers.get('X-Forwarded-For')
        if fwd:
            first = fwd.split(',')[0].strip()
            if first:
                return first
    return request.remote_addr or 'unknown'


def rate_limit(key, limit, window=60, scope=None):
    """通用限流：超限返回 429 响应，否则返回 None。

    key  限流维度（如端点名），实际 key 会拼接用户身份或客户端 IP；
    scope 为 'user' 时按登录用户限流，否则按 IP 限流。
    """
    from flask import jsonify
    from flask_jwt_extended import get_jwt_identity
    if scope == 'user':
        try:
            ident = get_jwt_identity() or client_ip()
        except Exception:
            ident = client_ip()
    else:
        ident = client_ip()
    if not limiter.hit(f'{key}:{ident}', limit, window):
        return jsonify({'code': 429, 'message': '请求过于频繁，请稍后再试'}), 429
    return None