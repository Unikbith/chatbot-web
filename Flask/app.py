"""
AI 角色扮演聊天应用 - Flask 主入口
支持多模型提供商、角色人设、登录认证、识图、语音对话等功能
"""
import os
import sys

# 确保当前目录在 Python 路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify, request
from sqlalchemy import event, inspect, text
from config import config
from extensions import db, jwt, cors, migrate
from models import (User, ModelProvider, PersonaTemplate, UserSettings, Conversation,
                    ConversationMediaLog)
from routes import (
    auth_bp, chat_bp, audio_bp, provider_bp,
    conversation_bp, settings_bp, persona_bp, upload_bp,
    admin_bp, image_bp, marketplace_bp, feedback_bp,
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
    with app.app_context():
        _configure_sqlite_engine(db.engine)
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
    app.register_blueprint(marketplace_bp)
    app.register_blueprint(feedback_bp)

    # 安全响应头：兜底 XSS / 点击劫持 / MIME 嗅探等常见攻击
    @app.after_request
    def _set_security_headers(resp):
        resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
        resp.headers.setdefault('X-Frame-Options', 'DENY')
        resp.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        # 仅对 API 响应设置 CSP；静态页面由前端 index.html 的 meta CSP 覆盖
        if request.path.startswith('/api/'):
            resp.headers.setdefault('Content-Security-Policy',
                                    "default-src 'none'; frame-ancestors 'none'")
        return resp

    # 健康检查
    @app.route('/api/health')
    def health_check():
        # rich_message_enabled：全局默认开关（.env 的 RICH_MESSAGE_ENABLED）。
        # 单个对话以自身的 rich_marker_enabled 为准（可在「会话设置 → 界面标记」里改）。
        try:
            from rich_marker import RICH_MESSAGE_ENABLED as rich_global
            rich_enabled = bool(rich_global)
        except Exception:
            rich_enabled = False
        return jsonify({
            'code': 200,
            'message': 'OK',
            'data': {
                'status': 'running',
                'version': '4.0.0',
                'free_api_enabled': app.config.get('FREE_API_ENABLED', False),
                'rich_message_enabled': rich_enabled,
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
        _ensure_runtime_indexes(app)
        _init_default_data(app)

    return app


def _configure_sqlite_engine(engine):
    """为 SQLite 连接设置并发与完整性相关的 PRAGMA。"""
    if engine.url.get_backend_name() != 'sqlite':
        return
    if getattr(engine, '_confide_sqlite_configured', False):
        return

    @event.listens_for(engine, 'connect')
    def _set_sqlite_pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute('PRAGMA foreign_keys=ON')
            cursor.execute('PRAGMA busy_timeout=15000')
            cursor.execute('PRAGMA journal_mode=WAL')
            cursor.execute('PRAGMA synchronous=NORMAL')
        finally:
            cursor.close()

    engine._confide_sqlite_configured = True


def _ensure_runtime_indexes(app):
    """为已有数据库补齐 SQLAlchemy 模型中声明的复合索引。"""
    wanted = {
        'idx_conversations_user_deleted_updated',
        'idx_messages_conversation_created_id',
        'idx_messages_conversation_id',
        'idx_ai_usage_user_created',
        'idx_ai_usage_model_created',
        'idx_ai_usage_conversation_created',
    }
    try:
        for table in db.metadata.tables.values():
            for index in table.indexes:
                if index.name in wanted:
                    index.create(bind=db.engine, checkfirst=True)
    except Exception as e:
        app.logger.info(f'[迁移] 运行索引检查/创建跳过: {e}')


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


def _migrate_media_log_conversation_id_nullable(app):
    """把 conversation_media_logs.conversation_id 从 NOT NULL 改为可空。

    素材记录现在还要承载系统设置的头像/背景、聊天时上传的图片，
    这些都没有归属对话。SQLite 不支持直接修改列约束，用「建新表→搬数据→换名」完成，
    整体放在一个事务里，任何一步失败都会回滚，不会丢审计数据。
    """
    try:
        cols = inspect(db.engine).get_columns('conversation_media_logs')
        cid = next((c for c in cols if c['name'] == 'conversation_id'), None)
        if cid is None or cid.get('nullable', True):
            return
        # 索引名在 SQLite 里是库级唯一的：表改名后旧索引仍占着原名字，
        # 必须显式删掉，否则新表建索引时会报 "index ... already exists"
        index_names = [ix['name'] for ix in inspect(db.engine).get_indexes('conversation_media_logs')
                       if ix.get('name')]
        with db.engine.begin() as conn:
            conn.execute(text('ALTER TABLE conversation_media_logs RENAME TO conversation_media_logs_old'))
            for name in index_names:
                conn.execute(text(f'DROP INDEX IF EXISTS "{name}"'))
            ConversationMediaLog.__table__.create(conn)
            conn.execute(text(
                'INSERT INTO conversation_media_logs (id, user_id, conversation_id, media_type, value, created_at) '
                'SELECT id, user_id, conversation_id, media_type, value, created_at FROM conversation_media_logs_old'
            ))
            conn.execute(text('DROP TABLE conversation_media_logs_old'))
        app.logger.info('[迁移] conversation_media_logs.conversation_id 已允许为空')
    except Exception as e:
        app.logger.warning('[迁移] conversation_media_logs 结构调整跳过: %s', e)


def _ensure_schema_columns(app):
    """轻量级 schema 迁移：为已存在的表补齐新增的字段（避免手工重建库）。

    通过 db.create_all() 无法为已存在的 SQLite 表增加列，这里用 ALTER 补齐。
    """
    try:
        inspector = inspect(db.engine)
        with app.app_context():
            # prompt_tool_logs — 提示词工具使用审计（较新表，旧库可能缺失）
            if 'prompt_tool_logs' not in inspector.get_table_names():
                db.create_all()
                app.logger.info('[迁移] 已创建 prompt_tool_logs 表')
            # conversation_media_logs — 对话素材（背景图/头像）设置历史
            if 'conversation_media_logs' not in inspector.get_table_names():
                db.create_all()
                app.logger.info('[迁移] 已创建 conversation_media_logs 表')
            else:
                # 素材记录扩展为「全部图片素材」后，系统设置的头像/背景、聊天时上传的图片
                # 都不属于任何对话，conversation_id 必须允许为空。
                # SQLite 无法用 ALTER 去掉 NOT NULL，只能重建表并搬移数据（DDL 在事务内，失败会整体回滚）。
                _migrate_media_log_conversation_id_nullable(app)
            # conversation_summaries — 记忆宫殿：对话滚动摘要的每次压缩记录
            if 'conversation_summaries' not in inspector.get_table_names():
                db.create_all()
                app.logger.info('[迁移] 已创建 conversation_summaries 表')
            # worldbook_entries — 世界书：按需注入的设定条目
            if 'worldbook_entries' not in inspector.get_table_names():
                db.create_all()
                app.logger.info('[迁移] 已创建 worldbook_entries 表')
            # marketplace_worldbook_entries — 广场卡片随卡分享的世界书条目
            if 'marketplace_worldbook_entries' not in inspector.get_table_names():
                db.create_all()
                app.logger.info('[迁移] 已创建 marketplace_worldbook_entries 表')
            # ai_usage_logs — 模型调用用量与缓存命中审计
            if 'ai_usage_logs' not in inspector.get_table_names():
                db.create_all()
                app.logger.info('[迁移] 已创建 ai_usage_logs 表')
            # messages.prompt_tokens / completion_tokens - 单条回复的 token 用量
            if 'messages' in inspector.get_table_names():
                cols = {c['name'] for c in inspector.get_columns('messages')}
                if 'prompt_tokens' not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text('ALTER TABLE messages ADD COLUMN prompt_tokens INTEGER'))
                    app.logger.info('[迁移] 已为 messages 增加 prompt_tokens 字段')
                if 'completion_tokens' not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text('ALTER TABLE messages ADD COLUMN completion_tokens INTEGER'))
                    app.logger.info('[迁移] 已为 messages 增加 completion_tokens 字段')
                if 'cached_tokens' not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text('ALTER TABLE messages ADD COLUMN cached_tokens INTEGER'))
                    app.logger.info('[迁移] 已为 messages 增加 cached_tokens 字段')
            # model_providers.params - 厂商专属参数（STT/TTS）
            if 'model_providers' in inspector.get_table_names():
                cols = {c['name'] for c in inspector.get_columns('model_providers')}
                if 'params' not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text('ALTER TABLE model_providers ADD COLUMN params TEXT'))
                    app.logger.info('[迁移] 已为 model_providers 增加 params 字段')
                # model_providers.enabled - 配置启用开关（可多选）
                if 'enabled' not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text('ALTER TABLE model_providers ADD COLUMN enabled BOOLEAN DEFAULT 1'))
                    app.logger.info('[迁移] 已为 model_providers 增加 enabled 字段')
            # users.token_version - 令牌版本（改密/注销吊销旧 token）
            if 'users' in inspector.get_table_names():
                cols = {c['name'] for c in inspector.get_columns('users')}
                if 'token_version' not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text('ALTER TABLE users ADD COLUMN token_version INTEGER DEFAULT 0'))
                    app.logger.info('[迁移] 已为 users 增加 token_version 字段')
                if 'gender' not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text("ALTER TABLE users ADD COLUMN gender VARCHAR(10)"))
                    app.logger.info('[迁移] 已为 users 增加 gender 字段')
                if 'deleted_at' not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text("ALTER TABLE users ADD COLUMN deleted_at DATETIME"))
                    app.logger.info('[迁移] 已为 users 增加 deleted_at 字段')
                if 'last_login_at' not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text("ALTER TABLE users ADD COLUMN last_login_at DATETIME"))
                    app.logger.info('[迁移] 已为 users 增加 last_login_at 字段')
                if 'last_chat_at' not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text("ALTER TABLE users ADD COLUMN last_chat_at DATETIME"))
                    app.logger.info('[迁移] 已为 users 增加 last_chat_at 字段')
            # user_settings.background_cover - 背景展示方式（contain/cover）
            if 'user_settings' in inspector.get_table_names():
                cols = {c['name'] for c in inspector.get_columns('user_settings')}
                if 'background_cover' not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text("ALTER TABLE user_settings ADD COLUMN background_cover VARCHAR(20) DEFAULT 'contain'"))
                    app.logger.info('[迁移] 已为 user_settings 增加 background_cover 字段')
                # 新用户教程引导标记：老库补列时按「已完成」写入（默认 1），
                # 使教程只对补列之后注册的新用户生效
                for cname in ('tutorial_seen', 'tutorial_hint_dismissed'):
                    if cname not in cols:
                        with db.engine.begin() as conn:
                            conn.execute(text(f'ALTER TABLE user_settings ADD COLUMN {cname} BOOLEAN DEFAULT 1'))
                        app.logger.info(f'[迁移] 已为 user_settings 增加 {cname} 字段')
            # conversations.background_cover - 对话独立背景展示方式
            if 'conversations' in inspector.get_table_names():
                cols = {c['name'] for c in inspector.get_columns('conversations')}
                if 'background_cover' not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text("ALTER TABLE conversations ADD COLUMN background_cover VARCHAR(20)"))
                    app.logger.info('[迁移] 已为 conversations 增加 background_cover 字段')
                # 对话独立：用户头像 / 频率惩罚 / 存在惩罚 / 自动播报
                conv_add = {
                    'user_avatar': 'VARCHAR(500)',
                    'frequency_penalty': 'FLOAT',
                    'presence_penalty': 'FLOAT',
                    'auto_play_voice': 'BOOLEAN',
                    # 记忆宫殿（滚动摘要）
                    'summary_threshold': 'INTEGER',
                    'summary': 'TEXT',
                    'summary_upto_id': 'INTEGER',
                    # 提示词兜底开关
                    'append_prompt_enabled': 'BOOLEAN',
                    # 界面标记（富消息）开关
                    'rich_marker_enabled': 'BOOLEAN',
                    # 回复渲染模板（JSON 文本）
                    'reply_template': 'TEXT',
                }
                for cname, ctype in conv_add.items():
                    if cname not in cols:
                        with db.engine.begin() as conn:
                            conn.execute(text(f'ALTER TABLE conversations ADD COLUMN {cname} {ctype}'))
                        app.logger.info(f'[迁移] 已为 conversations 增加 {cname} 字段')
                if 'user_persona_id' not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text('ALTER TABLE conversations ADD COLUMN user_persona_id INTEGER'))
                    app.logger.info('[迁移] 已为 conversations 增加 user_persona_id 字段')
                if 'deleted_at' not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text("ALTER TABLE conversations ADD COLUMN deleted_at DATETIME"))
                    app.logger.info('[迁移] 已为 conversations 增加 deleted_at 字段')
            # daily_checkins.checkin_time - 签到时间（24小时冷却制）
            if 'daily_checkins' in inspector.get_table_names():
                cols = {c['name'] for c in inspector.get_columns('daily_checkins')}
                if 'checkin_time' not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text("ALTER TABLE daily_checkins ADD COLUMN checkin_time DATETIME"))
                    app.logger.info('[迁移] 已为 daily_checkins 增加 checkin_time 字段')
                # 历史遗留：checkin_date 字段仍存在但模型已不依赖；保留原列，
                # 由模型 default 自动填充，避免破坏旧表结构。
            # persona_marketplace.gender - 人物卡性别（男/女/自定义，非男非女筛选归入非二元）
            if 'persona_marketplace' in inspector.get_table_names():
                cols = {c['name'] for c in inspector.get_columns('persona_marketplace')}
                if 'gender' not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text('ALTER TABLE persona_marketplace ADD COLUMN gender VARCHAR(20)'))
                    app.logger.info('[迁移] 已为 persona_marketplace 增加 gender 字段')
                # user_prompt - 玩家侧设定：随卡片一起发布，采用后即知道「自己是谁」
                if 'user_prompt' not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text('ALTER TABLE persona_marketplace ADD COLUMN user_prompt TEXT'))
                    app.logger.info('[迁移] 已为 persona_marketplace 增加 user_prompt 字段')
            # image_usage.is_remaining_semantics - 免费生图次数语义迁移标记
            if 'image_usage' in inspector.get_table_names():
                cols = {c['name'] for c in inspector.get_columns('image_usage')}
                if 'is_remaining_semantics' not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text("ALTER TABLE image_usage ADD COLUMN is_remaining_semantics BOOLEAN DEFAULT 0"))
                    app.logger.info('[迁移] 已为 image_usage 增加 is_remaining_semantics 字段')
            # persona_templates.persona_type - AI/用户人设区分
            if 'persona_templates' in inspector.get_table_names():
                cols = {c['name'] for c in inspector.get_columns('persona_templates')}
                if 'persona_type' not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text("ALTER TABLE persona_templates ADD COLUMN persona_type VARCHAR(10) DEFAULT 'ai'"))
                    app.logger.info('[迁移] 已为 persona_templates 增加 persona_type 字段')
                # persona_templates.user_prompt - 玩家侧人物设定（与 AI 提示词同卡绑定）
                if 'user_prompt' not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text('ALTER TABLE persona_templates ADD COLUMN user_prompt TEXT'))
                    app.logger.info('[迁移] 已为 persona_templates 增加 user_prompt 字段')
                # 系统内置人物卡已改为「普通人物卡」，不再区分系统/用户，移除废弃字段
                if 'is_system' in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text("ALTER TABLE persona_templates DROP COLUMN is_system"))
                    app.logger.info('[迁移] 已移除 persona_templates.is_system 废弃字段')
    except Exception as e:
        app.logger.info(f'[迁移] schema 检查/补列跳过: {e}')


def _init_default_data(app):
    """初始化默认数据"""
    # 一次性回填：界面标记开关为 NULL 的历史会话，按当时的全局默认值固定下来。
    # 目的：让「会话设置 → 界面标记」显示的开关状态与实际注入行为一致 ——
    # 否则 NULL 会在界面上显示成「关闭」，实际却按全局值在注入（显示与行为不符），
    # 且用户在该面板里改任何其它设置都会被一并写成 False，静默把标记关掉。
    try:
        from rich_marker import RICH_MESSAGE_ENABLED as rich_default
        updated = db.session.query(Conversation).filter(
            Conversation.rich_marker_enabled.is_(None)
        ).update({Conversation.rich_marker_enabled: rich_default},
                 synchronize_session=False)
        if updated:
            db.session.commit()
            app.logger.info(f'[迁移] 已按全局开关初始化 {updated} 个会话的界面标记状态')
    except Exception as e:
        db.session.rollback()
        app.logger.info(f'[迁移] 界面标记状态回填跳过: {e}')

    # 一次性迁移：image_usage.free_count 从「已用次数」转为「剩余次数」语义
    try:
        from models import ImageUsage
        limit = int(app.config.get('IMAGE_FREE_LIMIT') or 5)
        rows = ImageUsage.query.filter_by(is_remaining_semantics=False).all()
        if rows:
            converted = 0
            for row in rows:
                used = row.free_count or 0
                row.free_count = max(0, min(limit - used, limit))
                row.is_remaining_semantics = True
                converted += 1
            db.session.commit()
            app.logger.info(f'[迁移] 已转换 {converted} 条 image_usage 记录为剩余次数语义')
    except Exception as e:
        app.logger.info(f'[迁移] image_usage 语义转换跳过: {e}')

    # 默认 admin 仅开发环境创建，且不打印明文密码
    is_dev = app.config.get('DEBUG') or os.getenv('FLASK_ENV', 'development') == 'development'
    if User.query.count() == 0 and is_dev:
        default_user = User(username='admin', email='admin@example.com')
        default_user.set_password('admin123')
        db.session.add(default_user)
        db.session.flush()
        app.logger.info("[初始化] 开发环境创建默认用户 admin（仅限本地使用）")
        
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
            weight=100
        )
        db.session.add(persona)
        app.logger.info("[初始化] 创建默认角色: 加藤惠")

    # 旧版默认人物卡提示词一次性升级（幂等：新版含【与用户的关系】章节即跳过）
    try:
        from routes.auth import _upgrade_legacy_default_personas
        _upgrade_legacy_default_personas()
    except Exception as e:
        app.logger.info(f'[初始化] 默认人物卡升级跳过: {e}')

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
            app.logger.info("[初始化] 创建默认对话提供商: %s", default_model)

    db.session.commit()


if __name__ == '__main__':
    app = create_app()
    # debug 跟随环境（生产 FLASK_ENV=production 时自动关闭）
    app.run(host='0.0.0.0', debug=app.config.get('DEBUG', False), port=5000)
