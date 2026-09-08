"""音频路由 - 语音转文字(STT)、文字转语音(TTS)、音色列表"""
from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from io import BytesIO
from models import ModelProvider
from services.ai_service import AIService
from services.upload_guard import check_upload, MAX_AUDIO_SIZE

audio_bp = Blueprint('audio', __name__, url_prefix='/api/audio')


def _get_stt_provider(user_id, provider_id=None):
    """获取 STT 提供商（优先 stt 类型，没有则用 chat 类型）"""
    if provider_id:
        return ModelProvider.query.filter_by(id=provider_id, user_id=user_id).first()
    stt = ModelProvider.query.filter_by(
        user_id=user_id, provider_type='stt', is_default=True
    ).first()
    if stt:
        return stt
    # 回退到 chat 类型默认配置
    return ModelProvider.query.filter_by(
        user_id=user_id, provider_type='chat', is_default=True
    ).first()


def _get_tts_provider(user_id, provider_id=None):
    """获取 TTS 提供商"""
    if provider_id:
        return ModelProvider.query.filter_by(id=provider_id, user_id=user_id).first()
    tts = ModelProvider.query.filter_by(
        user_id=user_id, provider_type='tts', is_default=True
    ).first()
    if tts:
        return tts
    # 回退到 chat 类型默认配置
    return ModelProvider.query.filter_by(
        user_id=user_id, provider_type='chat', is_default=True
    ).first()


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
    voice = data.get('voice', 'alloy')
    provider_id = data.get('provider_id')
    
    if not text:
        return jsonify({'code': 400, 'message': '文本不能为空'}), 400
    
    provider = _get_tts_provider(user_id, provider_id)
    if not provider:
        return jsonify({'code': 400, 'message': '请先配置语音合成模型提供商'}), 400
    
    try:
        audio_data, error = AIService.text_to_speech(provider, text, voice)
        if error:
            return jsonify({'code': 500, 'message': f'合成失败: {error}'}), 500
        
        # 返回音频流
        return send_file(
            BytesIO(audio_data),
            mimetype='audio/mpeg',
            as_attachment=False,
            download_name='speech.mp3'
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
