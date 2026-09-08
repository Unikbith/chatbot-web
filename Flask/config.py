import os
from pathlib import Path

from dotenv import load_dotenv

# 固定加载本文件同级目录的 .env，避免依赖进程启动目录导致配置读不到
load_dotenv(Path(__file__).resolve().parent / '.env')


class Config:
    """基础配置"""
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'jwt-secret-key-change-in-production')
    JWT_ACCESS_TOKEN_EXPIRES = 86400  # 24小时
    JWT_REFRESH_TOKEN_EXPIRES = 2592000  # 30天

    # 数据库
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///chatbot.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 免费 API 配置（用户未配置时使用）
    FREE_API_ENABLED = os.getenv('FREE_API_ENABLED', 'true').lower() == 'true'
    FREE_API_NAME = os.getenv('FREE_API_NAME', '免费 GLM-4.7-flash')
    FREE_API_URL = os.getenv('FREE_API_URL', '')
    FREE_API_KEY = os.getenv('FREE_API_KEY', '')
    FREE_API_MODEL = os.getenv('FREE_API_MODEL', 'glm-4.7-flash')

    # 邮箱配置（QQ邮箱 SMTP）
    SMTP_HOST = os.getenv('SMTP_HOST', 'smtp.qq.com')
    SMTP_PORT = int(os.getenv('SMTP_PORT', '465'))
    SMTP_USER = os.getenv('SMTP_USER', '')
    SMTP_PASS = os.getenv('SMTP_PASS', '')
    SENDER_NAME = os.getenv('SENDER_NAME', 'AI 聊天助手')

    # 支持的 API 类型
    SUPPORTED_API_TYPES = ['openai', 'deepseek', 'zhipu', 'qwen', 'custom']

    # 文件上传限制
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB

    # SSRF 防护：拦截外发请求指向内网/云元数据等敏感地址（可关闭）
    SSRF_PROTECTION = os.getenv('SSRF_PROTECTION', 'true').lower() == 'true'

    # 是否处于受信反向代理（Nginx/网关）之后：仅此时才信任 X-Forwarded-For；
    # 直连场景保持 false，避免伪造该头绕过登录/注册/验证码的每 IP 限流
    TRUST_PROXY_HEADERS = os.getenv('TRUST_PROXY_HEADERS', 'false').lower() == 'true'

    # CORS 允许的来源（逗号分隔）。默认仅本地开发 + 生产域名，可用环境变量覆盖，禁止任意源携带凭据
    CORS_ORIGINS = [o.strip() for o in os.getenv(
        'CORS_ORIGINS',
        'http://localhost:5173,http://127.0.0.1:5173,'
        'https://chatbot.rlzbs.cn,http://chatbot.rlzbs.cn'
    ).split(',') if o.strip()]

    # 上传目录
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    # 未显式设置 FLASK_ENV 时走生产安全配置（DEBUG=False），
    # 漏配环境变量也不会以默认/占位密钥上线；本地开发请显式 export FLASK_ENV=development
    'default': ProductionConfig
}
