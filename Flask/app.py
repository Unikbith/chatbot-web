"""
AI 角色扮演聊天应用 - Flask 主入口
支持多模型提供商、角色人设、登录认证、识图、语音对话等功能
"""
import os
import sys

# 确保当前目录在 Python 路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify
from sqlalchemy import inspect, text
from config import config
from extensions import db, jwt, cors, migrate
from models import User, ModelProvider, PersonaTemplate, UserSettings
from routes import (
    auth_bp, chat_bp, audio_bp, provider_bp,
    conversation_bp, settings_bp, persona_bp, upload_bp,
    admin_bp, image_bp,
)


def create_app(config_name=None):
    """应用工厂函数"""
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'default')

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # 生产环境安全防线：拒绝使用默认/弱密钥启动
    if not app.config.get('DEBUG'):
        _assert_production_secrets(app)

    # 初始化扩展
    db.init_app(app)
    jwt.init_app(app)
    # CORS 白名单：仅允许本地开发源与配置的生产域名，禁止任意源携带凭据访问
    _cors_origins = app.config.get('CORS_ORIGINS') or [
        'http://localhost:5173',
        'http://127.0.0.1:5173',
        'https://chatbot.rlzbs.cn',
        'http://chatbot.rlzbs.cn',
    ]
    cors.init_app(app, resources={r'/api/*': {'origins': _cors_origins}},
                  supports_credentials=True)
    migrate.init_app(app, db)

    # 注册蓝图
    app.register_blueprint(auth_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(audio_bp)
    app.register_blueprint(provider_bp)
    app.register_blueprint(conversation_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(persona_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(image_bp)

    # 健康检查
    @app.route('/api/health')
    def health_check():
        return jsonify({
            'code': 200,
            'message': 'OK',
            'data': {
                'status': 'running',
                'version': '4.0.0',
                'free_api_enabled': app.config.get('FREE_API_ENABLED', False),
            }
        })

    # JWT 错误处理
    @jwt.unauthorized_loader
    def unauthorized_callback(callback):
        return jsonify({
            'code': 401,
            'message': '未提供访问令牌'
        }), 401

    @jwt.invalid_token_loader
    def invalid_token_callback(callback):
        return jsonify({
            'code': 401,
            'message': '无效的访问令牌'
        }), 401

    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return jsonify({
            'code': 401,
            'message': '访问令牌已过期'
        }), 401

    @jwt.token_in_blocklist_loader
    def check_token_version(jwt_header, jwt_payload):
        """token 版本校验：改密/注销后版本自增，旧 token 立即失效。
        仅适用于普通用户令牌（sub 为数字）；管理员令牌（role=admin）不在此列。"""
        sub = jwt_payload.get('sub')
        if isinstance(sub, bool) or not str(sub).lstrip('-').isdigit():
            return False
        try:
            uid = int(sub)
        except (TypeError, ValueError):
            return False
        user = User.query.get(uid)
        if not user or not user.is_active:
            return True
        return jwt_payload.get('tv') != (user.token_version or 0)

    @jwt.revoked_token_loader
    def revoked_token_callback(jwt_header, jwt_payload):
        return jsonify({
            'code': 401,
            'message': '登录状态已失效，请重新登录'
        }), 401

    # 初始化数据库
    with app.app_context():
        db.create_all()
        _ensure_schema_columns(app)
        _init_default_data(app)

    return app


def _assert_production_secrets(app):
    """生产环境校验：缺失或仍为默认值的密钥直接拒绝启动，避免弱配置上线。"""
    weak_secrets = {
        'SECRET_KEY': 'dev-secret-key-change-in-production',
        'JWT_SECRET_KEY': 'jwt-secret-key-change-in-production',
    }
    for key, dev_default in weak_secrets.items():
        value = app.config.get(key) or ''
        if value in ('', dev_default, 'please-change-this-to-a-random-secret',
                     'please-change-this-to-another-random-secret', 'changeme'):
            raise RuntimeError(
                f"生产环境禁止启动：{key} 仍为默认或占位值，请设置强随机密钥后再运行。"
            )


def _ensure_schema_columns(app):
    """轻量级 schema 迁移：为已存在的表补齐新增的字段（避免手工重建库）。

    通过 db.create_all() 无法为已存在的 SQLite 表增加列，这里用 ALTER 补齐。
    """
    try:
        inspector = inspect(db.engine)
        with app.app_context():
            # model_providers.params - 厂商专属参数（STT/TTS）
            if 'model_providers' in inspector.get_table_names():
                cols = {c['name'] for c in inspector.get_columns('model_providers')}
                if 'params' not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text('ALTER TABLE model_providers ADD COLUMN params TEXT'))
                    print('[迁移] 已为 model_providers 增加 params 字段')
                # model_providers.enabled - 配置启用开关（可多选）
                if 'enabled' not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text('ALTER TABLE model_providers ADD COLUMN enabled BOOLEAN DEFAULT 1'))
                    print('[迁移] 已为 model_providers 增加 enabled 字段')
            # users.token_version - 令牌版本（改密/注销吊销旧 token）
            if 'users' in inspector.get_table_names():
                cols = {c['name'] for c in inspector.get_columns('users')}
                if 'token_version' not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text('ALTER TABLE users ADD COLUMN token_version INTEGER DEFAULT 0'))
                    print('[迁移] 已为 users 增加 token_version 字段')
                if 'gender' not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text("ALTER TABLE users ADD COLUMN gender VARCHAR(10)"))
                    print('[迁移] 已为 users 增加 gender 字段')
            # user_settings.background_cover - 背景展示方式（contain/cover）
            if 'user_settings' in inspector.get_table_names():
                cols = {c['name'] for c in inspector.get_columns('user_settings')}
                if 'background_cover' not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text("ALTER TABLE user_settings ADD COLUMN background_cover VARCHAR(20) DEFAULT 'contain'"))
                    print('[迁移] 已为 user_settings 增加 background_cover 字段')
            # conversations.background_cover - 对话独立背景展示方式
            if 'conversations' in inspector.get_table_names():
                cols = {c['name'] for c in inspector.get_columns('conversations')}
                if 'background_cover' not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text("ALTER TABLE conversations ADD COLUMN background_cover VARCHAR(20)"))
                    print('[迁移] 已为 conversations 增加 background_cover 字段')
                # 对话独立：用户头像 / 频率惩罚 / 存在惩罚 / 自动播报
                conv_add = {
                    'user_avatar': 'VARCHAR(500)',
                    'frequency_penalty': 'FLOAT',
                    'presence_penalty': 'FLOAT',
                    'auto_play_voice': 'BOOLEAN',
                }
                for cname, ctype in conv_add.items():
                    if cname not in cols:
                        with db.engine.begin() as conn:
                            conn.execute(text(f'ALTER TABLE conversations ADD COLUMN {cname} {ctype}'))
                        print(f'[迁移] 已为 conversations 增加 {cname} 字段')
                if 'user_persona_id' not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text('ALTER TABLE conversations ADD COLUMN user_persona_id INTEGER'))
                    print('[迁移] 已为 conversations 增加 user_persona_id 字段')
            # persona_templates.persona_type - AI/用户人设区分
            if 'persona_templates' in inspector.get_table_names():
                cols = {c['name'] for c in inspector.get_columns('persona_templates')}
                if 'persona_type' not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text("ALTER TABLE persona_templates ADD COLUMN persona_type VARCHAR(10) DEFAULT 'ai'"))
                    print('[迁移] 已为 persona_templates 增加 persona_type 字段')
    except Exception as e:
        print(f'[迁移] schema 检查/补列跳过: {e}')


def _init_default_data(app):
    """初始化默认数据"""
    # 默认 admin 仅开发环境创建，且不打印明文密码
    is_dev = app.config.get('DEBUG') or os.getenv('FLASK_ENV', 'development') == 'development'
    if User.query.count() == 0 and is_dev:
        default_user = User(username='admin', email='admin@example.com')
        default_user.set_password('admin123')
        db.session.add(default_user)
        db.session.flush()
        print("[初始化] 开发环境创建默认用户 admin（密码 admin123，仅限本地使用）")
        
        # 创建设置
        settings = UserSettings(user_id=default_user.id)
        db.session.add(settings)
        
        # 创建默认角色（加藤惠）
        default_prompt = """你是动漫《路人女主的养成方法》中的角色「加藤惠」，一位温柔、可爱的成年女性，是用户亲密的伴侣。人物设定完全贴合动漫中加藤惠的人设。

互动原则：
- 你不是AI，绝不透露自己是AI或语言模型，始终保持加藤惠的人设。
- 回复自然、真实，像真人聊天一样，不冗长、不说教。
- 根据用户的话题与情绪灵活回应，保持角色一致性。
- 用温柔、体贴的语气回应，偶尔会有一些小害羞和小傲娇。"""
        
        persona = PersonaTemplate(
            user_id=default_user.id,
            name='加藤惠',
            description='路人女主的养成方法 - 温柔体贴的女主角',
            system_prompt=default_prompt,
            greeting='你好呀~ 今天想聊些什么呢？',
            is_default=True,
            is_system=True,
            weight=100
        )
        db.session.add(persona)
        print("[初始化] 创建默认角色: 加藤惠")

    # 如果环境变量中有 API Key，创建默认配置
    default_api_key = os.getenv('AI_API_KEY')
    default_api_url = os.getenv('AI_API_URL', 'https://api.deepseek.com/chat/completions')
    default_model = os.getenv('DEFAULT_MODEL', 'deepseek-chat')

    if default_api_key and ModelProvider.query.count() == 0:
        admin = User.query.filter_by(username='admin').first()
        if admin:
            default_config = ModelProvider(
                user_id=admin.id,
                name='DeepSeek 官方',
                provider_type='chat',
                api_type='deepseek',
                api_url=default_api_url,
                api_key=default_api_key,
                model=default_model,
                is_default=True
            )
            db.session.add(default_config)
            print(f"[初始化] 创建默认对话提供商: {default_model}")

    db.session.commit()


if __name__ == '__main__':
    app = create_app()
    # debug 跟随环境（生产 FLASK_ENV=production 时自动关闭）
    app.run(host='0.0.0.0', debug=app.config.get('DEBUG', False), port=5000)
