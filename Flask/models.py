import os
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db
from rich_marker import RICH_MESSAGE_ENABLED
import json


APP_TIMEZONE = ZoneInfo(os.getenv('APP_TIMEZONE', 'Asia/Shanghai'))


def local_now():
    """返回应用统一时区的当前时间（naive datetime，落库格式）。

    应用不依赖部署机器的系统时区，默认固定为 Asia/Shanghai。
    API 输出一律通过 iso_time() 附带时区偏移，避免浏览器把无时区字符串
    误按本地时间解析。
    """
    return datetime.now(APP_TIMEZONE).replace(tzinfo=None)


def iso_time(value):
    """把数据库中的 naive 时间按应用时区序列化为带偏移的 ISO 字符串。"""
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=APP_TIMEZONE)
    return value.isoformat()


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
    deleted_at = db.Column(db.DateTime, nullable=True)
    token_version = db.Column(db.Integer, default=0)  # 令牌版本：改密/注销时自增以吊销旧 token
    last_login_at = db.Column(db.DateTime, nullable=True)
    last_chat_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)

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
            'last_login_at': iso_time(self.last_login_at),
            'last_chat_at': iso_time(self.last_chat_at),
            'created_at': iso_time(self.created_at)
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
    created_at = db.Column(db.DateTime, default=local_now)

    @classmethod
    def create(cls, email, code, purpose='register', minutes=5):
        """创建验证码"""
        vc = cls(
            email=email,
            code=code,
            purpose=purpose,
            expires_at=local_now() + timedelta(minutes=minutes)
        )
        db.session.add(vc)
        db.session.commit()
        return vc

    def is_valid(self):
        """检查是否有效"""
        return not self.used and self.expires_at > local_now()

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

    # 新用户使用教程引导：注册时由注册接口置为「未看过 / 未点开」，
    # 看过弹窗、点开侧栏入口后分别置位。默认值为 True，
    # 保证功能上线前已存在的老账号不会突然被弹出教程。
    tutorial_seen = db.Column(db.Boolean, default=True)  # False=新用户，登录后自动弹一次教程
    tutorial_hint_dismissed = db.Column(db.Boolean, default=True)  # False=侧栏教程入口仍显示

    # AI 参数（通用微调）
    temperature = db.Column(db.Float, default=0.8)  # 温度
    frequency_penalty = db.Column(db.Float, default=0.0)  # 频率惩罚 -2.0~2.0
    presence_penalty = db.Column(db.Float, default=0.0)  # 存在惩罚 -2.0~2.0
    top_p = db.Column(db.Float, default=0.95)  # 核采样

    # 语音设置
    default_voice = db.Column(db.String(100), default='alloy')
    auto_play_voice = db.Column(db.Boolean, default=False)  # 自动播报

    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)

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
            'tutorial_seen': bool(self.tutorial_seen),
            'tutorial_hint_dismissed': bool(self.tutorial_hint_dismissed),
        }


class PersonaTemplate(db.Model):
    """角色提示词模板"""
    __tablename__ = 'persona_templates'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    name = db.Column(db.String(1000), nullable=False)  # 角色名，如 "加藤惠"
    description = db.Column(db.String(1000), nullable=True)  # 简介
    avatar = db.Column(db.String(500), nullable=True)  # 角色头像
    system_prompt = db.Column(db.Text, nullable=False)  # 系统提示词（界面称「AI 提示词」）
    # 玩家（用户）侧的人物设定，界面称「人物提示词」。
    # 与 AI 提示词同属一张卡：写卡时把「玩家是谁」和「AI 是谁」一起定好，
    # 换卡即换整场戏的角色关系，不需要再去别处单独配一遍用户人设。
    user_prompt = db.Column(db.Text, nullable=True)
    greeting = db.Column(db.Text, nullable=True)  # 开场问候语
    is_default = db.Column(db.Boolean, default=False)  # 是否为默认角色
    persona_type = db.Column(db.String(10), default='ai')  # ai / user
    weight = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)
    deleted_at = db.Column(db.DateTime, nullable=True)  # 软删除时间戳

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'avatar': self.avatar,
            'system_prompt': self.system_prompt,
            'user_prompt': self.user_prompt,
            'greeting': self.greeting,
            'is_default': self.is_default,
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
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)

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
    created_at = db.Column(db.DateTime, default=local_now)

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
    # 记忆宫殿（滚动摘要）：每 N 轮触发一次压缩，压缩后旧消息被替换为一条摘要
    summary_threshold = db.Column(db.Integer, default=7, nullable=True)  # 触发阈值，1-20 轮，默认 7
    summary = db.Column(db.Text, nullable=True)             # 当前滚动摘要正文（最新一次压缩结果）
    summary_upto_id = db.Column(db.Integer, nullable=True)  # 已摘要到的最后一条 message id
    # 提示词兜底：开启后，后端写死的 GLOBAL_APPEND_PROMPT 才会接在人物设定之后。
    # 默认关闭 —— 那段兜底词有几千 token，默认带上会显著抬高每轮输入成本，
    # 只有在「AI 生成不出想要的内容」时才由用户自行打开。
    append_prompt_enabled = db.Column(db.Boolean, default=False, nullable=True)
    # 界面标记（富消息）：开启后把「【状态】【进度】【选项】」等标记约定接在系统提示词后，
    # 模型输出的标记由前端 RichMessage.vue 渲染成状态栏/进展条/可点选项。
    # 默认值跟随全局开关 RICH_MESSAGE_ENABLED（见 rich_marker.py）：
    # 这样新建对话的初始状态与 .env 一致，且「会话设置」里显示的开关不会与实际行为不符。
    # 用户可在会话设置里单独覆盖（写入显式 True/False）。
    rich_marker_enabled = db.Column(
        db.Boolean, default=True, nullable=True
    )
    # 回复渲染模板（JSON 文本）：决定这个话题的回复"长什么样"。
    # 形如 {"preset":"archive","name":"档案风","prompt":"…标记说明…"}：
    #   · prompt 由后端拼进系统提示词，保证「模板词表」与「前端渲染」天然对齐；
    #   · 版式（CSS/骨架）由前端按 preset 解析，换模板即换风格。
    # 为空表示不使用模板，走内置的基础标注渲染。
    reply_template = db.Column(db.Text, nullable=True)
    deleted_at = db.Column(db.DateTime, nullable=True)
    settings = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)

    __table_args__ = (
        db.Index('idx_conversations_user_deleted_updated',
                 'user_id', 'deleted_at', 'updated_at', 'id'),
    )

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
            'summary_threshold': self.summary_threshold,
            'summary': self.summary,
            'summary_upto_id': self.summary_upto_id,
            'append_prompt_enabled': bool(self.append_prompt_enabled),
            # NULL 与「未存过」同义：回落到全局默认值，
            # 与 rich_marker.resolve_rich_marker_enabled 的判定保持一致，
            # 避免前端显示成关闭、实际却按全局开关在注入。
            'rich_marker_enabled': (
                bool(self.rich_marker_enabled)
                if self.rich_marker_enabled is not None
                else RICH_MESSAGE_ENABLED
            ),
            'reply_template': self.reply_template,
            'persona_name': self.persona.name if self.persona else None,
            'persona_avatar': self.persona.avatar if self.persona else None,
            'created_at': iso_time(self.created_at),
            'updated_at': iso_time(self.updated_at)
        }


class ConversationSummary(db.Model):
    """对话压缩记录（记忆宫殿）。

    每次触发滚动摘要时落一条，记录「第几次压缩」与压缩后的完整摘要正文，
    供前端记忆宫殿展示压缩次数与每一次压缩的结果。
    """
    __tablename__ = 'conversation_summaries'

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    seq = db.Column(db.Integer, nullable=False, default=1)           # 第几次压缩（从 1 开始）
    content = db.Column(db.Text, nullable=False)                      # 本次压缩后的完整摘要正文
    msg_from = db.Column(db.Integer, nullable=True)                   # 本次被压缩的首条 message id
    msg_to = db.Column(db.Integer, nullable=True)                     # 本次被压缩的末条 message id
    message_count = db.Column(db.Integer, nullable=False, default=0)  # 本次压缩涉及的消息条数
    created_at = db.Column(db.DateTime, default=local_now, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'seq': self.seq,
            'content': self.content,
            'msg_from': self.msg_from,
            'msg_to': self.msg_to,
            'message_count': self.message_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class WorldBookEntry(db.Model):
    """世界书条目（设定条目 / Lorebook Entry）。

    设计目标：把一大块「永远全量重发」的角色设定，拆成若干**按需注入**的小条目，
    只有当最近对话里出现关键词时才把该条目送进模型 —— 既省 token，又能写更多设定。

    对用户是「零配置」的：不填任何条目时行为与以前完全一致（整块设定常驻）。

    字段说明：
      persona_id  —— 归属角色；为 None 表示「全局条目」（对当前用户所有角色生效）
      keywords    —— 触发关键词，逗号/换行分隔；中文无空格分词，用子串匹配最稳
      content     —— 命中后注入的设定正文
      always_on   —— True 表示常驻（每次都注入，用于核心人设）；False 表示按需
      enabled     —— 停用开关（保留条目但不注入）
      weight      —— 命中过多、超出预算时的优先级，越大越优先
    """
    __tablename__ = 'worldbook_entries'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    persona_id = db.Column(db.Integer, db.ForeignKey('persona_templates.id'), nullable=True, index=True)
    title = db.Column(db.String(200), nullable=False, default='')      # 条目名，仅用于管理界面展示
    keywords = db.Column(db.Text, nullable=False, default='')          # 触发关键词，逗号/换行分隔
    content = db.Column(db.Text, nullable=False, default='')           # 命中后注入的设定正文
    always_on = db.Column(db.Boolean, default=False)                   # 常驻（每次都注入）
    enabled = db.Column(db.Boolean, default=True)                      # 是否启用
    weight = db.Column(db.Integer, default=0)                          # 预算不足时的优先级
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)

    def to_dict(self):
        return {
            'id': self.id,
            'persona_id': self.persona_id,
            'title': self.title,
            'keywords': self.keywords,
            'content': self.content,
            'always_on': bool(self.always_on),
            'enabled': bool(self.enabled),
            'weight': self.weight or 0,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class ImageUsage(db.Model):
    """免费图片生成用量（每账号共享 Key 免费次数）。

    free_count 语义：自 2026-09-11 起改为「剩余免费次数」。
    历史数据通过 is_remaining_semantics 标记完成一次性迁移。
    """
    __tablename__ = 'image_usage'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True, index=True)
    free_count = db.Column(db.Integer, default=0, nullable=False)  # 剩余免费次数
    is_remaining_semantics = db.Column(db.Boolean, default=True, nullable=False)  # True=剩余次数语义
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)

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
    # 本次回复的 token 消耗（厂商 usage 缺失时为 None，前端不展示）
    prompt_tokens = db.Column(db.Integer, nullable=True)
    completion_tokens = db.Column(db.Integer, nullable=True)
    cached_tokens = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=local_now)

    __table_args__ = (
        db.Index('idx_messages_conversation_created_id',
                 'conversation_id', 'created_at', 'id'),
        db.Index('idx_messages_conversation_id', 'conversation_id', 'id'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'role': self.role,
            'content': self.content,
            'reasoning_content': self.reasoning_content,
            'image_url': self.image_url,
            'model': self.model,
            'prompt_tokens': self.prompt_tokens,
            'completion_tokens': self.completion_tokens,
            'cached_tokens': self.cached_tokens,
            'total_tokens': ((self.prompt_tokens or 0) + (self.completion_tokens or 0)
                             or None),
            'created_at': iso_time(self.created_at)
        }


class PersonaMarketplace(db.Model):
    """人设广场 - 用户分享的AI人设"""
    __tablename__ = 'persona_marketplace'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    name = db.Column(db.String(1000), nullable=False)
    description = db.Column(db.String(1000), nullable=True)
    avatar = db.Column(db.String(500), nullable=True)
    # 上限 50000 字（软上限 10000，超出部分兜底）；SQLite 的 TEXT 不限长度，
    # 若将来迁 MySQL 需改为 LONGTEXT（VARCHAR/TEXT 上限 65535 字节存不下 5 万汉字）
    system_prompt = db.Column(db.Text, nullable=False)
    greeting = db.Column(db.Text, nullable=True)
    # 玩家侧设定（与人物卡上的「人物提示词」同一含义）：
    # 发布卡片时一并带上，别人采用后就知道了「自己是谁」，不必再手动补。
    user_prompt = db.Column(db.Text, nullable=True)
    # 人物卡性别：男 / 女 / 自定义文本（非男非女在筛选里统一归入「非二元」）
    gender = db.Column(db.String(20), nullable=True)
    likes = db.Column(db.Integer, default=0)
    dislikes = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)

    # 性别归一化标签：男 / 女 / 非二元（自定义及未填写均归入非二元筛选桶）
    GENDER_TAGS = ('男', '女', '非二元')

    @staticmethod
    def gender_tag_of(gender):
        """卡片上显示的性别标签。

        保留用户填写的具体值（神秘/双性/无性别…），只有未填写时才回落为
        「非二元」—— 否则用户发布「双性」却显示成「非二元」，与预期不符。
        """
        g = (gender or '').strip()
        return g or '非二元'

    author = db.relationship('User', backref='marketplace_personas')
    comments = db.relationship('MarketplaceComment', backref='persona_card', lazy='dynamic',
                               cascade='all, delete-orphan', order_by='MarketplaceComment.created_at.desc()')
    # 随卡片一起分享的世界书条目（可选）；删卡时一并删除
    worldbook = db.relationship('MarketplaceWorldbookEntry', backref='marketplace_card',
                                lazy='select', cascade='all, delete-orphan',
                                order_by='MarketplaceWorldbookEntry.id')

    def to_dict(self, include_prompt=False, comment_count=None, worldbook_count=None):
        """序列化。comment_count / worldbook_count 可由调用方预先批量聚合传入，
        避免逐卡片执行 count() 造成 N+1 查询。

        can_edit 需调用方传入当前请求者是否为管理员（或卡片作者），
        由接口层判定后回填 —— 前端不自行判断权限，一律以此字段为准。"""
        data = {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'avatar': self.avatar,
            'greeting': self.greeting,
            'gender': self.gender,
            'gender_tag': self.gender_tag_of(self.gender),
            'likes': self.likes,
            'dislikes': self.dislikes,
            'score': self.likes - self.dislikes,
            'author_id': self.user_id,
            'author_name': self.author.username if self.author else None,
            'comment_count': (
                comment_count if comment_count is not None
                else (self.comments.count() if self.comments else 0)
            ),
            # 列表页只要条数（卡片上打个小标记），详情页才带完整条目
            'worldbook_count': (
                worldbook_count if worldbook_count is not None
                else (len(self.worldbook) if include_prompt else 0)
            ),
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        if include_prompt:
            data['system_prompt'] = self.system_prompt
            data['user_prompt'] = self.user_prompt
            # 世界书只在详情/编辑场景下发（列表页带上会让响应体积翻好几倍）
            data['worldbook'] = [e.to_dict() for e in (self.worldbook or [])]
        return data


class MarketplaceWorldbookEntry(db.Model):
    """人设广场卡片的世界书条目（发布卡片时随卡分享）。

    为什么不直接复用 WorldBookEntry：
        那张表是「用户自己的角色设定」，其中 persona_id 为空代表**全局条目**
        （注入到该用户的所有角色）。广场条目混进去会被当成全局设定，
        污染采用者自己的所有对话 —— 因此单独建表，
        采用（adopt）时再复制成对方自己名下的 WorldBookEntry。
    """
    __tablename__ = 'marketplace_worldbook_entries'

    id = db.Column(db.Integer, primary_key=True)
    persona_id = db.Column(db.Integer, db.ForeignKey('persona_marketplace.id'),
                           nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False, default='')
    keywords = db.Column(db.Text, nullable=False, default='')
    content = db.Column(db.Text, nullable=False, default='')
    always_on = db.Column(db.Boolean, default=False)
    enabled = db.Column(db.Boolean, default=True)
    weight = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=local_now)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title or '',
            'keywords': self.keywords or '',
            'content': self.content or '',
            'always_on': bool(self.always_on),
            'enabled': bool(self.enabled),
            'weight': self.weight or 0,
        }


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
    """人设广场评论（扁平结构：只评论人物卡，不支持对评论的回复）"""
    __tablename__ = 'marketplace_comments'

    id = db.Column(db.Integer, primary_key=True)
    persona_id = db.Column(db.Integer, db.ForeignKey('persona_marketplace.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    likes = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=local_now)

    commenter = db.relationship('User', backref='marketplace_comments')

    def to_dict(self, pseudonym=None, identicon_seed=None, liked=False):
        return {
            'id': self.id,
            'content': self.content,
            'likes': self.likes,
            'pseudonym': pseudonym,
            'identicon_seed': identicon_seed,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'liked': bool(liked),
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


class MarketplaceAdopt(db.Model):
    """记录用户采用了哪些广场卡片，避免重复采用"""
    __tablename__ = 'marketplace_adopts'

    id = db.Column(db.Integer, primary_key=True)
    persona_id = db.Column(db.Integer, db.ForeignKey('persona_marketplace.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    template_id = db.Column(db.Integer, db.ForeignKey('persona_templates.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=local_now)

    __table_args__ = (
        db.UniqueConstraint('persona_id', 'user_id', name='uq_marketplace_adopt'),
    )


class DailyCheckIn(db.Model):
    """每日签到"""
    __tablename__ = 'daily_checkins'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    checkin_time = db.Column(db.DateTime, default=local_now)
    checkin_date = db.Column(db.Date, default=date.today)  # 兼容历史表：保留日期字段
    bonus_images = db.Column(db.Integer, default=5)
    created_at = db.Column(db.DateTime, default=local_now)


class Feedback(db.Model):
    """用户反馈（系统设置-帮助与反馈）"""
    __tablename__ = 'feedbacks'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)  # 反馈内容
    allow_email_contact = db.Column(db.Boolean, default=False)  # 是否允许以邮件联系
    contact_email = db.Column(db.String(120), nullable=True)  # 联系邮箱（允许邮件联系时填写）
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)

    user = db.relationship('User', backref='feedbacks')

    def to_dict(self, include_user=False):
        data = {
            'id': self.id,
            'user_id': self.user_id,
            'content': self.content,
            'allow_email_contact': self.allow_email_contact,
            'contact_email': self.contact_email,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        if include_user and self.user:
            data['user'] = {
                'id': self.user.id,
                'username': self.user.username,
                'email': self.user.email,
                'avatar': self.user.avatar,
                'gender': self.user.gender,
            }
        return data


class PromptToolLog(db.Model):
    """提示词工具使用审计记录。

    记录谁在何时用了提示词工具、输入了什么、产出什么，供运营在管理后台
    排查与追溯。只在生成成功时落库（失败请求不污染记录）。
    字段刻意保留原始文本而非摘要：排查「生成了什么」时需要看到原文。
    """
    __tablename__ = 'prompt_tool_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    # character=人物设定 / image=生图改图
    category = db.Column(db.String(20), nullable=False, index=True)
    provider_id = db.Column(db.Integer)
    model = db.Column(db.String(200))
    custom_prompt = db.Column(db.Text)      # 用户自定义系统提示词（为空表示用默认）
    base_info = db.Column(db.Text)          # 用户填写的基础信息
    result = db.Column(db.Text)             # 模型生成结果
    created_at = db.Column(db.DateTime, default=local_now, index=True)

    user = db.relationship('User', backref='prompt_tool_logs')

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.user.username if self.user else None,
            'email': self.user.email if self.user else None,
            'category': self.category,
            'category_label': '人物设定' if self.category == 'character' else '生图/改图',
            'provider_id': self.provider_id,
            'model': self.model,
            'custom_prompt': self.custom_prompt,
            'has_custom_prompt': bool(self.custom_prompt),
            'base_info': self.base_info,
            'result': self.result,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class ConversationMediaLog(db.Model):
    """对话素材（背景图 / 头像 / 上传图片）使用记录。

    两类来源：
      · 对话级：每个对话可独立设置背景图、AI 头像、用户头像（conversation_id 有值）；
      · 全局级：系统设置里的头像与背景、聊天时上传的图片（conversation_id 为空）。
    管理员在后台「对话素材记录」里追溯与清理。

    只在设置非空值且较上次有变化时落库，避免重复保存刷屏。
    """
    __tablename__ = 'conversation_media_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    # 允许为空：系统设置里的头像/背景、聊天上传的图片不属于某个具体对话
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id'), nullable=True, index=True)
    # background=背景图 / ai_avatar=AI头像 / user_avatar=用户头像
    # profile_avatar=资料头像 / profile_ai_avatar=通用AI头像 / profile_background=通用背景图
    # upload=上传图片（聊天发送的图片等）
    media_type = db.Column(db.String(20), nullable=False, index=True)
    value = db.Column(db.Text)                 # data-URI 或 URL
    created_at = db.Column(db.DateTime, default=local_now, index=True)

    user = db.relationship('User', backref='conversation_media_logs')
    # 系统级/上传级记录不挂对话，因此这里是可选关系（conversation 可能为 None）
    conversation = db.relationship('Conversation', backref='media_logs')

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.user.username if self.user else None,
            'email': self.user.email if self.user else None,
            'conversation_id': self.conversation_id,
            'conversation_title': self.conversation.title if self.conversation else None,
            'media_type': self.media_type,
            'media_type_label': {
                'background': '对话背景图',
                'ai_avatar': '对话AI头像',
                'user_avatar': '对话用户头像',
                'profile_background': '系统背景图',
                'profile_avatar': '系统用户头像',
                'profile_ai_avatar': '系统AI头像',
                'upload': '上传图片',
            }.get(self.media_type, self.media_type),
            'value': self.value,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class AiUsageLog(db.Model):
    """模型调用用量审计。

    与最终消息解耦，保留模型、供应商、Token、缓存命中和耗时等信息，
    便于后台按用户、模型、对话和时间聚合。
    """
    __tablename__ = 'ai_usage_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id'), nullable=True, index=True)
    message_id = db.Column(db.Integer, db.ForeignKey('messages.id'), nullable=True, index=True)
    provider_id = db.Column(db.Integer, nullable=True, index=True)
    model = db.Column(db.String(200), nullable=True)
    is_free_api = db.Column(db.Boolean, default=False, nullable=False)
    prompt_tokens = db.Column(db.Integer, nullable=True)
    completion_tokens = db.Column(db.Integer, nullable=True)
    cached_tokens = db.Column(db.Integer, nullable=True)
    total_tokens = db.Column(db.Integer, nullable=True)
    latency_ms = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), default='success', nullable=False, index=True)
    error_type = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=local_now, index=True)

    __table_args__ = (
        db.Index('idx_ai_usage_user_created', 'user_id', 'created_at'),
        db.Index('idx_ai_usage_model_created', 'model', 'created_at'),
        db.Index('idx_ai_usage_conversation_created', 'conversation_id', 'created_at'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'conversation_id': self.conversation_id,
            'message_id': self.message_id,
            'provider_id': self.provider_id,
            'model': self.model,
            'is_free_api': bool(self.is_free_api),
            'prompt_tokens': self.prompt_tokens,
            'completion_tokens': self.completion_tokens,
            'cached_tokens': self.cached_tokens,
            'total_tokens': self.total_tokens,
            'latency_ms': self.latency_ms,
            'status': self.status,
            'error_type': self.error_type,
            'created_at': iso_time(self.created_at),
        }


class SupportThread(db.Model):
    """用户与管理员之间的匿名反馈会话（每个用户一个线程）。"""
    __tablename__ = 'support_threads'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True, index=True)
    status = db.Column(db.String(20), default='open', nullable=False)
    user_unread = db.Column(db.Integer, default=0, nullable=False)
    admin_unread = db.Column(db.Integer, default=0, nullable=False)
    last_message_at = db.Column(db.DateTime, nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)

    user = db.relationship('User', backref='support_thread')


class SupportMessage(db.Model):
    """匿名反馈会话消息，sender=user/admin。"""
    __tablename__ = 'support_messages'

    id = db.Column(db.Integer, primary_key=True)
    thread_id = db.Column(db.Integer, db.ForeignKey('support_threads.id'), nullable=False, index=True)
    sender = db.Column(db.String(10), nullable=False)
    content = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(500), nullable=True)
    read_by_user = db.Column(db.Boolean, default=False, nullable=False)
    read_by_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=local_now, index=True)

    __table_args__ = (
        db.Index('idx_support_messages_thread_created', 'thread_id', 'created_at', 'id'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'thread_id': self.thread_id,
            'sender': self.sender,
            'content': self.content,
            'image_url': self.image_url,
            'read_by_user': bool(self.read_by_user),
            'read_by_admin': bool(self.read_by_admin),
            'created_at': iso_time(self.created_at),
        }
