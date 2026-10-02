"""音频路由 - 语音转文字(STT)、文字转语音(TTS)、音色列表"""
from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from io import BytesIO
from models import ModelProvider
from services.ai_service import AIService
from services.upload_guard import check_upload, MAX_AUDIO_SIZE

audio_bp = Blueprint('audio', __name__, url_prefix='/api/audio')


# 厂商英文错误对用户很难判断是「配置错了」还是「账号没权限」，
# 这里把百炼常见错误映射成可行动的说明。
_TTS_ERROR_HINTS = (
    ('does not support http call', '当前 API Key 未开通该模型的 HTTP 调用权限（换用已开通的模型，或到百炼控制台开通）'),
    ('AllocationQuota', '配额不足或免费额度已用完（百炼控制台查看该模型的额度与计费）'),
    ('FreeTierOnly', '该模型仅免费额度可用且已耗尽（百炼控制台查看额度）'),
    ('InvalidApiKey', 'API Key 无效或地域不匹配（语音合成需使用北京地域的 API Key）'),
    ('Unsupported model', '模型 ID 不被支持（核对模型名，注意模型与音色必须配套）'),
    ('TTS speak operation failed', '音色与模型不匹配（例如把 CosyVoice 音色用于 qwen-audio 会失败，请改配对音色）'),
    ('Arrearage', '账号欠费，请充值后重试'),
    ('Throttling', '请求过于频繁，请稍后重试'),
)


def _friendly_tts_error(error):
    raw = str(error or '')
    for key, hint in _TTS_ERROR_HINTS:
        if key.lower() in raw.lower():
            return f'{hint}（{raw[:120]}）'
    return raw


def _resolve_provider(user_id, provider_type, provider_id=None):
    """按类型解析音频（STT/TTS）提供商。

    解析顺序：显式 provider_id → 该类型的默认配置 → 该类型的任意一条
    → chat 类型默认配置 → chat 类型任意一条。

    倒数第二步很重要：用户往往只配了一个 TTS/STT 却没勾「设为默认」，
    只认 is_default 会导致 provider_id 为空时直接 400，表现为
    「点语音没反应」。有且仅有一条配置时应当直接用它。
    """
    if provider_id:
        p = ModelProvider.query.filter_by(id=provider_id, user_id=user_id).first()
        # 只接受该类型的提供商；前端误传聊天提供商 id 时忽略，回落到默认配置
        if p and p.provider_type == provider_type:
            return p

    q = ModelProvider.query.filter_by(user_id=user_id, provider_type=provider_type)
    return (q.filter_by(is_default=True).first()
            or q.order_by(ModelProvider.id.asc()).first()
            or ModelProvider.query.filter_by(
                user_id=user_id, provider_type='chat', is_default=True).first()
            or ModelProvider.query.filter_by(
                user_id=user_id, provider_type='chat').order_by(
                ModelProvider.id.asc()).first())


def _get_stt_provider(user_id, provider_id=None):
    """获取 STT 提供商"""
    return _resolve_provider(user_id, 'stt', provider_id)


def _get_tts_provider(user_id, provider_id=None):
    """获取 TTS 提供商"""
    return _resolve_provider(user_id, 'tts', provider_id)


@audio_bp.route('/transcriptions', methods=['POST'])
@jwt_required()
def speech_to_text():
    """语音转文字 (STT)"""
    user_id = int(get_jwt_identity())
    
    audio_file = request.files.get('file')
    if not audio_file:
        return jsonify({'code': 400, 'message': '请上传音频文件'}), 400

    provider_id = request.form.get('provider_id')
    provider = _get_stt_provider(user_id, provider_id)

    if not provider:
        return jsonify({'code': 400, 'message': '请先配置语音识别模型提供商'}), 400

    # 音频前置校验：空 / 超 10MB 一律 400
    audio_data, guard_err = check_upload(audio_file, MAX_AUDIO_SIZE)
    if guard_err:
        return jsonify({'code': 400, 'message': guard_err}), 400

    try:
        result, error = AIService.speech_to_text(provider, audio_data)
        if error:
            return jsonify({'code': 500, 'message': f'识别失败: {error}'}), 500
        
        return jsonify({
            'code': 200,
            'data': {
                'text': result
            }
        })
    except Exception as e:
        return jsonify({'code': 500, 'message': f'识别失败: {str(e)}'}), 500


@audio_bp.route('/speech', methods=['POST'])
@jwt_required()
def text_to_speech():
    """文字转语音 (TTS)"""
    user_id = int(get_jwt_identity())
    data = request.get_json()
    
    text = data.get('text', '').strip()
    provider_id = data.get('provider_id')

    if not text:
        return jsonify({'code': 400, 'message': '文本不能为空'}), 400

    # 长度保护：AI 的长回复可能上千字，而厂商对单次合成有字符上限
    # （百炼 HTTP 非流式单次 20000 字符，按权重计数）。超限时截断，
    # 否则会表现为「点了读语音没反应」。
    max_chars = 18000
    if len(text) > max_chars:
        text = text[:max_chars]

    provider = _get_tts_provider(user_id, provider_id)
    if not provider:
        return jsonify({'code': 400, 'message': '请先配置语音合成模型提供商'}), 400

    # 未显式指定音色时，优先使用 TTS 提供商自带配置的音色。
    # 不再回落到 'alloy'：那是 OpenAI 占位音，百炼等厂商不认，会导致空音色被拒。
    voice = data.get('voice') or getattr(provider, 'voice', None) or ''

    try:
        audio_data, fmt, error = AIService.text_to_speech_with_format(provider, text, voice)
        if error:
            return jsonify({'code': 500, 'message': f'合成失败: {_friendly_tts_error(error)}'}), 500
        if not audio_data:
            return jsonify({'code': 500, 'message': '合成失败: 未返回音频数据'}), 500

        # 容器类型必须与厂商实际输出格式一致：百炼 Qwen-Audio/CosyVoice 默认
        # 输出 wav，若一律标成 audio/mpeg，部分浏览器/音频库会拒播或播不出声。
        # 格式由 TTS 层按实际使用的参数返回，不靠猜。
        ext, mimetype = {
            'mp3': ('mp3', 'audio/mpeg'),
            'wav': ('wav', 'audio/wav'),
            'pcm': ('pcm', 'audio/L16'),
            'ogg': ('ogg', 'audio/ogg'),
            'opus': ('opus', 'audio/opus'),
            'flac': ('flac', 'audio/flac'),
            'aac': ('m4a', 'audio/mp4'),
        }.get((fmt or '').lower(), ('mp3', 'audio/mpeg'))

        return send_file(
            BytesIO(audio_data),
            mimetype=mimetype,
            as_attachment=False,
            download_name=f'speech.{ext}'
        )
    except Exception as e:
        return jsonify({'code': 500, 'message': f'合成失败: {str(e)}'}), 500


@audio_bp.route('/voices', methods=['GET'])
@jwt_required()
def list_voices():
    """获取可用音色列表（通用默认值 + 提供商自定义）"""
    user_id = int(get_jwt_identity())
    provider_id = request.args.get('provider_id')
    
    provider = _get_tts_provider(user_id, provider_id)
    
    # 默认音色列表（OpenAI 兼容格式）
    default_voices = [
        {'id': 'alloy', 'name': '合金', 'language': 'multi'},
        {'id': 'echo', 'name': '回响', 'language': 'multi'},
        {'id': 'fable', 'name': '寓言', 'language': 'multi'},
        {'id': 'onyx', 'name': '缟玛瑙', 'language': 'multi'},
        {'id': 'nova', 'name': '新星', 'language': 'multi'},
        {'id': 'shimmer', 'name': '微光', 'language': 'multi'},
    ]
    
    # 如果提供商有配置音色，也加入
    custom_voices = []
    if provider and provider.voice:
        custom_voices = [
            {'id': provider.voice, 'name': provider.voice, 'language': 'custom'}
        ]
    
    return jsonify({
        'code': 200,
        'data': {
            'voices': default_voices + custom_voices,
            'default_voice': (provider and provider.voice) or 'alloy'
        }
    })
