"""厂商预设 - 统一管理各类型（对话/STT/TTS）支持的厂商与默认配置。

对话模型仅支持以下五家（接口兼容 OpenAI chat/completions 格式，用户只需
提供 api_key 与 api_base_url）：
    小米 (xiaomi / MiMo)、DeepSeek、智谱 (zhipu)、Kimi (moonshot)、MiniMax

语音转文字（stt）：仅支持 阿里云百炼(Paraformer) 与 火山引擎(豆包 ASR)。
文字转语音（tts）：仅支持 MiniMax TTS、阿里云百炼(CosyVoice)、火山引擎(豆包 TTS)。
均采用 OpenAI 兼容接口格式。
"""

# ---------------------------------------------------------------------------
# 对话模型厂商
# ---------------------------------------------------------------------------
CHAT_VENDORS = [
    {
        'brand': 'deepseek',
        'name': 'DeepSeek',
        'desc': '深度求索 AI',
        'default_api_url': 'https://api.deepseek.com',
        'models': ['deepseek-chat', 'deepseek-reasoner'],
    },
    {
        'brand': 'zhipu',
        'name': '智谱 AI',
        'desc': '智谱清言 / GLM',
        'default_api_url': 'https://open.bigmodel.cn/api/paas/v4',
        'models': ['glm-4.5-flash', 'glm-4.5', 'glm-4-flash', 'glm-4v-plus'],
    },
    {
        'brand': 'kimi',
        'name': 'Kimi',
        'desc': '月之暗面 Moonshot',
        'default_api_url': 'https://api.moonshot.cn/v1',
        'models': ['moonshot-v1-8k', 'moonshot-v1-32k', 'moonshot-v1-128k'],
    },
    {
        'brand': 'minimax',
        'name': 'MiniMax',
        'desc': 'MiniMax 大模型',
        'default_api_url': 'https://api.minimax.chat/v1',
        'models': ['MiniMax-Text-01', 'abab6.5s-chat'],
    },
    {
        'brand': 'xiaomi',
        'name': '小米',
        'desc': '小米 MiMo（DeepSeek 兼容）',
        'default_api_url': 'https://api.xiaomimimo.com/v1',
        'models': ['mimo-55b-v2', 'mimo-78b-v2-250616'],
    },
]

# ---------------------------------------------------------------------------
# 语音转文字厂商
# ---------------------------------------------------------------------------
STT_VENDORS = [
    {
        'brand': 'bailian',
        'name': '阿里云百炼',
        'desc': 'DashScope Paraformer',
        'default_api_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        'models': ['paraformer-realtime-v2', 'paraformer-v2'],
    },
    {
        'brand': 'volcengine',
        'name': '火山引擎',
        'desc': '豆包语音识别',
        'default_api_url': 'https://ark.cn-beijing.volces.com/api/v3',
        'models': ['doubao-asr'],
    },
]

# ---------------------------------------------------------------------------
# 文字转语音厂商
# ---------------------------------------------------------------------------
TTS_VENDORS = [
    {
        'brand': 'mimotts',
        'name': 'MiniMax TTS',
        'desc': 'MiniMax 语音合成',
        'default_api_url': 'https://api.minimax.chat/v1',
        'models': ['speech-01'],
        'voices': ['male-qn-qingse', 'female-shaonv', 'female-chengshu', 'female-tianmei'],
    },
    {
        'brand': 'bailian',
        'name': '阿里云百炼',
        'desc': 'DashScope CosyVoice',
        'default_api_url': 'https://dashscope.aliyuncs.com/api/v1',
        'models': ['cosyvoice-v2'],
        'voices': ['longxiaochun', 'longhua', 'longlz', 'longshuo'],
    },
    {
        'brand': 'volcengine',
        'name': '火山引擎',
        'desc': '豆包语音合成',
        'default_api_url': 'https://ark.cn-beijing.volces.com/api/v3',
        'models': ['doubao-tts'],
        'voices': ['zh_female_wanwanxiaohe_moon_bigtts', 'zh_male_qingkuang_moon_bigtts'],
    },
]


# ---------------------------------------------------------------------------
# 图片生成厂商（仅支持 Agnes AI，国内官方主页 agnes-ai.cn 注册获取免费 Key）
# ---------------------------------------------------------------------------
IMAGE_VENDORS = [
    {
        'brand': 'agnes',
        'name': 'Agnes AI',
        'desc': '免费图像生成（文生图 / 图生图）· 前往 agnes-ai.cn 注册获取免费 Key',
        'default_api_url': 'https://apihub.agnes-ai.cn/v1',
        'models': ['agnes-image-2.1-flash', 'agnes-image-2.0-flash'],
    },
]

# 生图参数预设
IMAGE_RESOLUTIONS = ('1K', '2K', '4K')
# 仅保留 Agnes 官方 2.1 长宽比列出的 8 种；4:5 / 5:4 官方不支持（会按 3:4 / 4:3 截取，比例失真）故移除
IMAGE_ASPECT_RATIOS = (
    '1:1', '16:9', '4:3', '3:2', '3:4', '2:3', '9:16', '21:9',
)
IMAGE_QUALITIES = ('auto', 'low', 'medium', 'high')


def get_vendor(brand, provider_type='chat'):
    """按类型 + 厂商名查找厂商预设"""
    table = {
        'chat': CHAT_VENDORS,
        'stt': STT_VENDORS,
        'tts': TTS_VENDORS,
        'image': IMAGE_VENDORS,
    }.get(provider_type, CHAT_VENDORS)
    for v in table:
        if v['brand'] == brand:
            return v
    return None


def get_vendors(provider_type='chat'):
    """返回某一类型的全部厂商预设（供前端渲染根据厂商选择）"""
    table = {
        'chat': CHAT_VENDORS,
        'stt': STT_VENDORS,
        'tts': TTS_VENDORS,
        'image': IMAGE_VENDORS,
    }.get(provider_type, CHAT_VENDORS)
    # 去掉内部模型/音色列表，仅返回供选择的基础信息
    return [
        {k: v for k, v in item.items() if k not in ('models', 'voices')}
        for item in table
    ]


# ---------------------------------------------------------------------------
# 厂商专属配置字段 schema（STT/TTS）
# 公共字段（ID / API Key / API Base URL）由前端固定渲染，此处仅为「额外参数」。
# target: 'model' -> 存 provider.model；其它 -> 存 provider.params（JSON）
# ---------------------------------------------------------------------------
def _text(key, label, label_en='', default='', help='', help_en='', required=False,
          placeholder='', target='params'):
    return {
        'key': key, 'label': label, 'label_en': label_en or label,
        'type': 'text', 'default': default,
        'help': help, 'help_en': help_en, 'required': required,
        'placeholder': placeholder, 'target': target,
    }


def _number(key, label, label_en='', default=None, min=None, max=None,
            step=None, unit='秒', help='', help_en=''):
    return {
        'key': key, 'label': label, 'label_en': label_en or label,
        'type': 'number', 'default': default, 'min': min, 'max': max,
        'step': step, 'unit': unit, 'help': help, 'help_en': help_en,
        'target': 'params',
    }


def _select(key, label, label_en='', default='', options=(), options_en=None,
            help='', help_en=''):
    return {
        'key': key, 'label': label, 'label_en': label_en or label,
        'type': 'select', 'default': default,
        'options': [{'label': o, 'value': o} for o in options],
        'options_en': options_en or [],
        'help': help, 'help_en': help_en, 'target': 'params',
    }


def _boolean(key, label, label_en='', default=False, help='', help_en=''):
    return {
        'key': key, 'label': label, 'label_en': label_en or label,
        'type': 'boolean', 'default': default,
        'help': help, 'help_en': help_en, 'target': 'params',
    }


def _asr_common():
    """STT 通用字段（阿里百炼 / 火山引擎 ASR）"""
    return [
        _text('model', '模型 ID', 'Model ID', default='',
              placeholder='qwen3-asr-flash, doubao-asr...',
              help='语音识别模型名称', help_en='ASR model ID', required=True,
              target='model',
              ),
        _number('timeout', '超时时间', 'Timeout', default=20, min=5, max=120,
                unit='秒', help='识别超时时间，单位秒', help_en='Timeout in seconds'),
        _text('proxy', '代理地址', 'Proxy', default='',
              placeholder='http://127.0.0.1:7890',
              help='HTTP/HTTPS 代理，仅对该提供商请求生效',
              help_en='HTTP/HTTPS proxy for this provider only'),
    ]


# 文字转语音 - 火山引擎（openspeech 自定义接口）
def _volcengine_tts_schema():
    return [
        _text('model', '模型 ID', 'Model ID', default='',
              placeholder='doubao-tts...', required=False,
              help='语音合成模型', help_en='TTS model ID', target='model'),
        _text('appid', 'App ID', 'App ID', default='', required=True,
              help='火山引擎应用 ID', help_en='Volcano Engine App ID'),
        _text('cluster', '火山引擎集群', 'Cluster', default='volcano_tts',
              help='volcano_tts / volcano_icl / volcano_icl_concurr',
              help_en='Service cluster'),
        _text('voice_type', '火山引擎音色', 'Voice', default='', required=True,
              placeholder='输入声音 id（Voice_type）', help='声音 id',
              help_en='Voice Type id'),
        _number('speed_ratio', '语速设置', 'Speed', default=1.0, min=0.2, max=3.0,
                step=0.1, unit='倍', help='语速倍率（0.2-3.0，默认 1.0）',
                help_en='Speed ratio (0.2-3.0)'),
        _number('timeout', '超时时间', 'Timeout', default=20, min=5, max=120,
                unit='秒', help='合成超时时间，单位秒', help_en='Timeout in seconds'),
        _text('proxy', '代理地址', 'Proxy', default='',
              placeholder='http://127.0.0.1:7890',
              help='HTTP/HTTPS 代理，仅对该提供商请求生效',
              help_en='HTTP/HTTPS proxy for this provider only'),
    ]


# 文字转语音 - 阿里云百炼（DashScope / OpenAI 兼容）
def _bailian_tts_schema():
    return [
        _text('model', '模型 ID', 'Model ID', default='',
              placeholder='cosyvoice-v2...', required=True,
              help='语音合成模型', help_en='TTS model ID', target='model'),
        _text('voice', '音色', 'Voice', default='',
              placeholder='输入自定义音色 ID，如 longxiaochun',
              help='CosyVoice 音色 ID，可自定义输入',
              help_en='CosyVoice voice ID, custom input'),
        _select('output_format', '输出格式', 'Format', default='mp3',
                options=['mp3', 'wav', 'pcm'], help='音频输出格式',
                help_en='Audio output format'),
        _number('timeout', '超时时间', 'Timeout', default=20, min=5, max=120,
                unit='秒', help='合成超时时间，单位秒', help_en='Timeout in seconds'),
        _text('proxy', '代理地址', 'Proxy', default='',
              placeholder='http://127.0.0.1:7890',
              help='HTTP/HTTPS 代理，仅对该提供商请求生效',
              help_en='HTTP/HTTPS proxy for this provider only'),
    ]


def _mimotts_schema():
    return [
        _text('model', '模型 ID', 'Model ID', default='',
              placeholder='mimo-v2.5-tts...', required=True,
              help='语音合成模型', help_en='TTS model ID', target='model'),
        _text('voice', '音色', 'Voice', default='',
              placeholder='输入自定义音色 ID，如 female-shaonv',
              help='声音角色 ID，可自定义输入',
              help_en='Voice / timbre ID, custom input'),
        _select('output_format', '输出格式', 'Format', default='mp3',
                options=['wav', 'mp3', 'pcm'], help='音频输出格式',
                help_en='Audio output format'),
        _text('style_prompt', '风格提示词', 'Style', default='',
              placeholder='如：开心、悄悄话...',
              help='情感/风格提示词', help_en='Emotional style prompt'),
        _select('dialect', '方言', 'Dialect', default='',
                options=['', '东北话', '四川话', '河南话', '粤语'],
                help='地区方言', help_en='Regional dialect'),
        _text('seed_text', '种子文本', 'Seed', default='',
              placeholder='参考文本，用于校准音色',
              help='参考文本，稳定音色', help_en='Seed text for voice calibration'),
        _number('timeout', '超时时间', 'Timeout', default=20, min=5, max=120,
                unit='秒', help='合成超时时间，单位秒', help_en='Timeout in seconds'),
        _text('proxy', '代理地址', 'Proxy', default='',
              placeholder='http://127.0.0.1:7890',
              help='HTTP/HTTPS 代理，仅对该提供商请求生效',
              help_en='HTTP/HTTPS proxy for this provider only'),
    ]


# 图片生成 - Agnes AI 生图参数（文生图 / 图生图公用）
# 参考 astrbot_plugin_agnes_image 的「生图设置」配置项
def _agnes_image_schema():
    return [
        _text('proxy', '代理地址', 'Proxy', default='',
              placeholder='留空不使用，支持 http/https/socks5，如 http://127.0.0.1:7890',
              help='仅对该提供商生图请求生效，留空不走代理',
              help_en='HTTP/HTTPS/SOCKS5 proxy for this provider only'),
        _boolean('llm_tools', '启用大模型原生工具', 'Enable LLM Tools',
                 default=False,
                 help='开启后，可用自然语言让大模型调用图片/视频生成工具（对话中遇到「生图/改图」指令自动转图片生成）',
                 help_en='Let the LLM call the image-generation tool via natural language'),
        _select('resolution', '默认分辨率', 'Default Resolution',
                default='2K', options=IMAGE_RESOLUTIONS,
                help='1K / 2K / 4K（4K 仅 agnes-image-2.1-flash 支持，且尺寸较大不推荐）',
                help_en='1K / 2K / 4K'),
        _select('image_model', '默认生图模型', 'Default Model',
                default='agnes-image-2.1-flash',
                options=['agnes-image-2.1-flash', 'agnes-image-2.0-flash'],
                help='文生图 / 图生图使用的图像模型',
                help_en='Text / image-to-image generation model'),
        _select('aspect_ratio', '默认长宽比', 'Default Aspect Ratio',
                default='1:1', options=IMAGE_ASPECT_RATIOS,
                help='生成图片的长宽比（10 种预设可选）',
                help_en='Aspect ratio of the image'),
        _select('quality', '默认质量档', 'Default Quality',
                default='auto', options=IMAGE_QUALITIES,
                help='为当前模型附加质量参数，auto=不附加',
                help_en='auto / low / medium / high'),
        _select('send_mode', '图片发送方式', 'Send Mode',
                default='url', options=['url', 'file', 'base64'],
                help='url=发送图片链接；base64=内嵌发送；file=作为文件上传',
                help_en='How the generated image is delivered'),
        _number('switch_threshold', '智能切换阈值 (MB)', 'Switch Threshold (MB)',
                default=2, min=0.5, max=50, step=0.5, unit='MB',
                help='send_mode 为 auto/智能切换时：文件小于该值走 base64，否则走 file',
                help_en='File size threshold for base64/file auto switch'),
        _boolean('ref_aspect_ratio', '改图按参考图原比例', 'Follow Reference Ratio',
                 default=False,
                 help='开启后，改图指令自动按第一张参考图的原始宽高比生图（匹配最接近的预设比例）',
                 help_en='Generate at the reference image aspect ratio'),
        _number('timeout', '请求超时', 'Timeout', default=120, min=10, max=300,
                unit='秒', help='图像生成的最大超时时间，单位秒',
                help_en='Timeout in seconds'),
    ]


CONFIG_SCHEMA = {
    'chat': {},
    'stt': {
        'bailian': _asr_common,
        'volcengine': _asr_common,
    },
    'tts': {
        'mimotts': _mimotts_schema,
        'bailian': _bailian_tts_schema,
        'volcengine': _volcengine_tts_schema,
    },
    'image': {
        'agnes': _agnes_image_schema,
    },
}


def get_config_schema(provider_type='chat', brand=''):
    """返回某类型 + 厂商的额外配置字段列表（不含公共字段 ID/API Key/Base URL）"""
    if provider_type not in CONFIG_SCHEMA:
        return []
    builder = CONFIG_SCHEMA[provider_type].get(brand)
    if not builder:
        return []
    return builder()