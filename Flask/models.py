from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db
import json


class User(db.Model):
    """用户表"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)  # 邮箱必填
    avatar = db.Column(db.String(500), nullable=True)  # 用户头像
    ai_avatar = db.Column(db.String(500), nullable=True)  # AI 头像
    gender = db.Column(db.String(10), nullable=True)  # 性别：男/女/神秘
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    token_version = db.Column(db.Integer, default=0)  # 令牌版本：改密/注销时自增以吊销旧 token
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联
    providers = db.relationship('ModelProvider', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    conversations = db.relationship('Conversation', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    settings = db.relationship('UserSettings', backref='user', uselist=False, cascade='all, delete-orphan')
    personas = db.relationship('PersonaTemplate', backref='user', lazy='dynamic', cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'avatar': self.avatar,
            'ai_avatar': self.ai_avatar,
            'gender': self.gender,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class VerificationCode(db.Model):
    """邮箱验证码表"""
    __tablename__ = 'verification_codes'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False, index=True)
    code = db.Column(db.String(6), nullable=False)
    purpose = db.Column(db.String(20), nullable=False, default='register')  # register/reset_password
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @classmethod
    def create(cls, email, code, purpose='register', minutes=5):
        """创建验证码"""
        vc = cls(
            email=email,
            code=code,
            purpose=purpose,
            expires_at=datetime.utcnow() + timedelta(minutes=minutes)
        )
        db.session.add(vc)
        db.session.commit()
        return vc

    def is_valid(self):
        """检查是否有效"""
        return not self.used and self.expires_at > datetime.utcnow()

    def mark_used(self):
        """标记为已使用"""
        self.used = True
        db.session.commit()


class UserSettings(db.Model):
    """用户设置表"""
    __tablename__ = 'user_settings'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True, index=True)

    # 通用设置
    theme = db.Column(db.String(20), default='auto')  # light/dark/auto
    language = db.Column(db.String(20), default='auto')  # zh-CN/en/auto
    background_image = db.Column(db.String(500), nullable=True)  # 背景图片
    background_cover = db.Column(db.String(20), default='contain')  # 背景展示方式 contain=完整可见 / cover=覆盖背景
    message_opacity = db.Column(db.Float, default=0.9)  # 消息框透明度 0-1
    sidebar_collapsed = db.Column(db.Boolean, default=False)  # 侧边栏是否收起

    # AI 参数（通用微调）
    temperature = db.Column(db.Float, default=0.8)  # 温度
    frequency_penalty = db.Column(db.Float, default=0.0)  # 频率惩罚 -2.0~2.0
    presence_penalty = db.Column(db.Float, default=0.0)  # 存在惩罚 -2.0~2.0
    top_p = db.Column(db.Float, default=0.95)  # 核采样

    # 语音设置
    default_voice = db.Column(db.String(100), default='alloy')
    auto_play_voice = db.Column(db.Boolean, default=False)  # 自动播报

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'theme': self.theme,
            'language': self.language,
            'background_image': self.background_image,
            'background_cover': self.background_cover or 'contain',
            'message_opacity': self.message_opacity,
            'sidebar_collapsed': self.sidebar_collapsed,
            'temperature': self.temperature,
            'frequency_penalty': self.frequency_penalty,
            'presence_penalty': self.presence_penalty,
            'top_p': self.top_p,
            'default_voice': self.default_voice,
            'auto_play_voice': self.auto_play_voice,
        }


class PersonaTemplate(db.Model):
    """角色提示词模板"""
    __tablename__ = 'persona_templates'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)  # 角色名，如 "加藤惠"
    description = db.Column(db.String(500), nullable=True)  # 简介
    avatar = db.Column(db.String(500), nullable=True)  # 角色头像
    system_prompt = db.Column(db.Text, nullable=False)  # 系统提示词
    greeting = db.Column(db.Text, nullable=True)  # 开场问候语
    is_default = db.Column(db.Boolean, default=False)  # 是否为默认角色
    is_system = db.Column(db.Boolean, default=False)  # 是否系统内置（不可删除）
    persona_type = db.Column(db.String(10), default='ai')  # ai / user
    weight = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'avatar': self.avatar,
            'system_prompt': self.system_prompt,
            'greeting': self.greeting,
            'is_default': self.is_default,
            'is_system': self.is_system,
            'persona_type': self.persona_type or 'ai',
            'weight': self.weight,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class ModelProvider(db.Model):
    """模型提供商表 - 支持多种类型：对话/语音转文字/文字转语音
    
    provider_type:
      - chat: 对话模型
      - stt: 语音转文字 (Speech-to-Text)
      - tts: 文字转语音 (Text-to-Speech)

    每个提供商（ModelProvider）可配置多个具体模型（ProviderModel），
    形成「提供商 -> 模型」两级结构，与前端配置面板一致。
    """
    __tablename__ = 'model_providers'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    provider_type = db.Column(db.String(30), nullable=False, default='chat')
    brand = db.Column(db.String(50), default='deepseek')  # 厂商预设：deepseek/zhipu/kimi/minimax/xiaomi...
    api_type = db.Column(db.String(50), nullable=False, default='openai')
    api_url = db.Column(db.String(500), nullable=False)
    api_key = db.Column(db.String(500), nullable=False)
    model = db.Column(db.String(100), nullable=True)  # STT/TTS 模型 ID（qwen3-asr-flash / mimo-v2.5-tts 等）
    params = db.Column(db.Text, nullable=True)  # 厂商专属参数 JSON：timeout/proxy/appid/cluster/voice_type/speed/output_format/style_prompt/dialect/seed_text 等
    voice = db.Column(db.String(100), nullable=True)
    is_default = db.Column(db.Boolean, default=False)
    enabled = db.Column(db.Boolean, default=True)  # 是否启用（未指定时作为候选配置，可多个同时启用）
    weight = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联：该提供商下配置的模型
    models = db.relationship(
        'ProviderModel', backref='provider', lazy='select',
        cascade='all, delete-orphan', order_by='ProviderModel.created_at'
    )

    __table_args__ = (
        db.Index('idx_user_type', 'user_id', 'provider_type'),
    )

    def get_params(self):
        """解析 PARAMS 字段（厂商专属参数）为字典"""
        if not self.params:
            return {}
        try:
            return json.loads(self.params) if isinstance(self.params, str) else dict(self.params)
        except (ValueError, TypeError):
            return {}

    def set_params(self, params):
        """存储厂商专属参数（仅保留非空值）"""
        if not params:
            self.params = None
            return
        cleaned = {k: v for k, v in params.items() if v is not None and v != ''}
        self.params = json.dumps(cleaned, ensure_ascii=False)

    @staticmethod
    def mask_api_key(api_key):
        """掩码 API Key：仅保留首尾，中间打码，避免明文回传到前端。"""
        if not api_key:
            return ''
        s = api_key.strip()
        if len(s) <= 8:
            return '*' * len(s)
        return s[:4] + '*' * 8 + s[-4:]

    def to_dict(self, include_key=False, include_models=False):
        data = {
            'id': self.id,
            'name': self.name,
            'provider_type': self.provider_type,
            'brand': self.brand,
            'api_type': self.api_type,
            'api_url': self.api_url,
            'model': self.model,
            'params': self.get_params(),
            'voice': self.voice,
            'api_key_masked': self.mask_api_key(self.api_key) if self.api_key else '',
            'is_default': self.is_default,
            'enabled': self.enabled,
            'weight': self.weight,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        if include_key:
            # 仅回传掩码，前端用其做回显/比对，绝不泄露明文
            data['api_key'] = data['api_key_masked']
        if include_models:
            data['models'] = [m.to_dict() for m in self.models]
        return data


class ProviderModel(db.Model):
    """提供商下的具体模型（已配置模型）

    对应前端「已配置的模型」列表，每个模型可独立启用/停用。
    """
    __tablename__ = 'provider_models'

    id = db.Column(db.Integer, primary_key=True)
    provider_id = db.Column(db.Integer, db.ForeignKey('model_providers.id'),
                            nullable=False, index=True)
    model_id = db.Column(db.String(200), nullable=False)  # API 模型 ID，如 deepseek-chat
    name = db.Column(db.String(200), nullable=True)  # 展示名
    enabled = db.Column(db.Boolean, default=True)  # 是否启用
    is_custom = db.Column(db.Boolean, default=False)  # 是否为手动添加的自定义模型
    vision = db.Column(db.Boolean, default=False)  # 是否支持视觉
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.Index('idx_provider_model', 'provider_id', 'model_id', unique=False),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'provider_id': self.provider_id,
            'model_id': self.model_id,
            'name': self.name or self.model_id,
            'enabled': self.enabled,
            'is_custom': self.is_custom,
            'vision': self.vision,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Conversation(db.Model):
    """对话存档表"""
    __tablename__ = 'conversations'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    title = db.Column(db.String(200), default='新对话')
    provider_id = db.Column(db.Integer, db.ForeignKey('model_providers.id'), nullable=True)
    model_id = db.Column(db.String(200), nullable=True)  # 对话使用的模型 ID
    persona_id = db.Column(db.Integer, db.ForeignKey('persona_templates.id'), nullable=True)  # 使用的角色模板（AI人设）
    user_persona_id = db.Column(db.Integer, db.ForeignKey('persona_templates.id'), nullable=True)  # 用户人设
    is_pinned = db.Column(db.Boolean, default=False)
    system_prompt = db.Column(db.Text, nullable=True)  # 单对话自定义提示词（覆盖模板）
    background_image = db.Column(db.String(500), nullable=True)  # 对话独立背景（覆盖通用）
    background_cover = db.Column(db.String(20), nullable=True)  # 对话独立背景展示方式 contain/cover
    ai_avatar = db.Column(db.String(500), nullable=True)  # 对话独立 AI 头像（覆盖通用/角色）
    user_avatar = db.Column(db.String(500), nullable=True)  # 对话独立用户头像（覆盖通用）
    message_opacity = db.Column(db.Float, nullable=True)  # 对话独立消息框透明度
    temperature = db.Column(db.Float, nullable=True)
    frequency_penalty = db.Column(db.Float, nullable=True)
    presence_penalty = db.Column(db.Float, nullable=True)
    auto_play_voice = db.Column(db.Boolean, nullable=True)  # 对话独立：AI 回复自动播报
    settings = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = db.relationship('Message', backref='conversation', lazy='dynamic',
                               cascade='all, delete-orphan', order_by='Message.created_at')
    persona = db.relationship('PersonaTemplate', backref='conversations', foreign_keys=[persona_id])
    user_persona = db.relationship('PersonaTemplate', foreign_keys=[user_persona_id])

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'provider_id': self.provider_id,
            'model_id': self.model_id,
            'persona_id': self.persona_id,
            'user_persona_id': self.user_persona_id,
            'is_pinned': self.is_pinned,
            'system_prompt': self.system_prompt,
            'background_image': self.background_image,
            'background_cover': self.background_cover,
            'ai_avatar': self.ai_avatar,
            'user_avatar': self.user_avatar,
            'message_opacity': self.message_opacity,
            'temperature': self.temperature,
            'frequency_penalty': self.frequency_penalty,
            'presence_penalty': self.presence_penalty,
            'auto_play_voice': self.auto_play_voice,
            'persona_name': self.persona.name if self.persona else None,
            'persona_avatar': self.persona.avatar if self.persona else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class ImageUsage(db.Model):
    """免费图片生成用量（每账号共享 Key 免费次数）"""
    __tablename__ = 'image_usage'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True, index=True)
    free_count = db.Column(db.Integer, default=0, nullable=False)  # 免费生成累计次数
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'user_id': self.user_id,
            'free_count': self.free_count,
        }


class Message(db.Model):
    """消息表"""
    __tablename__ = 'messages'

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id'), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    reasoning_content = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(500), nullable=True)
    model = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'role': self.role,
            'content': self.content,
            'reasoning_content': self.reasoning_content,
            'image_url': self.image_url,
            'model': self.model,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class PersonaMarketplace(db.Model):
    """人设广场 - 用户分享的AI人设"""
    __tablename__ = 'persona_marketplace'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(500), nullable=True)
    avatar = db.Column(db.String(500), nullable=True)
    system_prompt = db.Column(db.Text, nullable=False)
    greeting = db.Column(db.Text, nullable=True)
    likes = db.Column(db.Integer, default=0)
    dislikes = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    author = db.relationship('User', backref='marketplace_personas')
    comments = db.relationship('MarketplaceComment', backref='persona_card', lazy='dynamic',
                               cascade='all, delete-orphan', order_by='MarketplaceComment.created_at.desc()')

    def to_dict(self, include_prompt=False):
        data = {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'avatar': self.avatar,
            'greeting': self.greeting,
            'likes': self.likes,
            'dislikes': self.dislikes,
            'score': self.likes - self.dislikes,
            'author_name': self.author.username if self.author else None,
            'comment_count': self.comments.count() if self.comments else 0,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        if include_prompt:
            data['system_prompt'] = self.system_prompt
        return data


class MarketplaceVote(db.Model):
    """人设广场投票记录（每人每卡只投一次）"""
    __tablename__ = 'marketplace_votes'

    id = db.Column(db.Integer, primary_key=True)
    persona_id = db.Column(db.Integer, db.ForeignKey('persona_marketplace.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    vote_type = db.Column(db.String(4), nullable=False)  # like / dislike

    __table_args__ = (
        db.UniqueConstraint('persona_id', 'user_id', name='uq_marketplace_vote'),
    )


class MarketplaceComment(db.Model):
    """人设广场评论"""
    __tablename__ = 'marketplace_comments'

    id = db.Column(db.Integer, primary_key=True)
    persona_id = db.Column(db.Integer, db.ForeignKey('persona_marketplace.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    likes = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    commenter = db.relationship('User', backref='marketplace_comments')

    def to_dict(self, pseudonym=None, identicon_seed=None):
        return {
            'id': self.id,
            'content': self.content,
            'likes': self.likes,
            'pseudonym': pseudonym,
            'identicon_seed': identicon_seed,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class CommentLike(db.Model):
    """评论点赞记录"""
    __tablename__ = 'comment_likes'

    id = db.Column(db.Integer, primary_key=True)
    comment_id = db.Column(db.Integer, db.ForeignKey('marketplace_comments.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    __table_args__ = (
        db.UniqueConstraint('comment_id', 'user_id', name='uq_comment_like'),
    )


class DailyCheckIn(db.Model):
    """每日签到"""
    __tablename__ = 'daily_checkins'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    checkin_date = db.Column(db.Date, nullable=False)
    bonus_images = db.Column(db.Integer, default=5)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'checkin_date', name='uq_daily_checkin'),
    )
