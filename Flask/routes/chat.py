"""聊天路由 - 流式对话、识图对话"""
import json
import base64
from flask import Blueprint, request, Response, stream_with_context, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models import ModelProvider, Conversation, Message, PersonaTemplate, UserSettings
from services.ai_service import AIService, FreeAPIProvider
from services.markdown_streamer import (
    MarkdownStreamer, strip_html_to_text,
    sse_content, sse_reasoning, sse_done
)
from services.upload_guard import check_upload, detect_image_type, MAX_IMAGE_SIZE

chat_bp = Blueprint('chat', __name__, url_prefix='/api/chat')


def iter_sse_content(response, full_content_holder, streamer, reasoning_holder, model_holder=None):
    """遍历 API 流式响应，提取正文和思考过程。"""
    new_content = ""
    finish_reason = None

    try:
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            if line.startswith("data: "):
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    if model_holder is not None and chunk.get('model'):
                        model_holder[0] = chunk['model']
                    
                    choice = chunk.get("choices", [{}])[0]
                    delta = choice.get("delta", {})

                    if "finish_reason" in choice and choice["finish_reason"] is not None:
                        finish_reason = choice["finish_reason"]

                    content = delta.get("content", "")
                    reasoning = delta.get("reasoning_content", "")

                    if reasoning:
                        reasoning_holder[0] += reasoning
                        yield sse_reasoning(reasoning)

                    if content:
                        new_content += content
                        full_content_holder[0] += content
                        for html_frag in streamer.feed(content):
                            yield sse_content(html_frag)
                except (json.JSONDecodeError, KeyError, IndexError):
                    pass
    except GeneratorExit:
        print("[客户端断开] 停止生成")
        raise

    remaining = streamer.flush()
    if remaining:
        yield sse_content(remaining)

    return new_content, finish_reason


def _get_free_provider():
    """获取免费 API 提供者（如果配置了）"""
    if not current_app.config.get('FREE_API_ENABLED'):
        return None
    api_url = current_app.config.get('FREE_API_URL', '')
    api_key = current_app.config.get('FREE_API_KEY', '')
    model = current_app.config.get('FREE_API_MODEL', '')
    if not api_url or not api_key or not model:
        return None
    return FreeAPIProvider(
        api_url=api_url,
        api_key=api_key,
        model=model,
        name=current_app.config.get('FREE_API_NAME', '免费 API')
    )


def _get_chat_provider(user_id, provider_id=None):
    """获取对话用的提供商（优先用户配置，其次免费API）"""
    if provider_id:
        return ModelProvider.query.filter_by(
            id=provider_id, user_id=user_id, provider_type='chat'
        ).first()
    else:
        provider = ModelProvider.query.filter_by(
            user_id=user_id, provider_type='chat', is_default=True
        ).first()
        if provider:
            return provider
        # 用户没有配置，尝试免费 API
        return _get_free_provider()


def _get_vision_provider(user_id, provider_id=None):
    """获取识图用的提供商（图像理解复用对话模型，无需单独配置）"""
    return _get_chat_provider(user_id, provider_id)


def _resolve_chat_model(provider, conversation=None, model_id=None):
    """解析本次对话使用的具体模型 ID

    优先级：请求明确指定 > 对话记忆的模型 > 提供商下第一个启用的模型 > 提供商默认 model
    """
    if model_id:
        return model_id
    if conversation and conversation.model_id:
        return conversation.model_id
    if provider is not None and not isinstance(provider, FreeAPIProvider):
        enabled = [m for m in provider.models if m.enabled]
        if enabled:
            return enabled[0].model_id
        if provider.model:
            return provider.model
    return None


def _get_user_settings(user_id):
    """获取用户设置"""
    settings = UserSettings.query.filter_by(user_id=user_id).first()
    if not settings:
        settings = UserSettings(user_id=user_id)
        db.session.add(settings)
        db.session.commit()
    return settings


CONTEXT_MAX_MESSAGES = 20  # 送入模型的历史消息滑动窗口上限（不含系统提示词）


def _apply_context_window(formatted_messages):
    """滑动窗口截断：始终保留系统提示词与最新消息，丢弃过旧上下文以控制 token 成本。"""
    if len(formatted_messages) <= CONTEXT_MAX_MESSAGES + 1:
        return formatted_messages
    # 拆分系统提示词（位于首位）与其余消息
    if formatted_messages and formatted_messages[0].get('role') == 'system':
        system = [formatted_messages[0]]
        rest = formatted_messages[1:]
    else:
        system = []
        rest = formatted_messages
    return system + rest[-(CONTEXT_MAX_MESSAGES):]


def _get_system_prompt(conv, persona_id=None, custom_prompt=None):
    """获取系统提示词（优先级：自定义 > 角色模板 > 默认角色）"""
    if custom_prompt:
        return custom_prompt
    if conv and conv.system_prompt:
        return conv.system_prompt
    # 从对话的角色模板获取
    if conv and conv.persona:
        return conv.persona.system_prompt
    # 从指定角色获取
    if persona_id:
        persona = PersonaTemplate.query.get(persona_id)
        if persona:
            return persona.system_prompt
    # 使用默认角色
    default_persona = PersonaTemplate.query.filter_by(
        user_id=conv.user_id if conv else None, is_default=True
    ).first()
    if default_persona:
        return default_persona.system_prompt
    return ''


@chat_bp.route('/status', methods=['GET'])
@jwt_required()
def chat_status():
    """获取聊天状态（是否使用免费API等）"""
    user_id = int(get_jwt_identity())
    provider = _get_chat_provider(user_id)
    
    is_free = provider and isinstance(provider, FreeAPIProvider)
    free_name = current_app.config.get('FREE_API_NAME', '免费 API') if is_free else None
    
    return jsonify({
        'code': 200,
        'data': {
            'has_provider': provider is not None,
            'is_free': is_free,
            'free_name': free_name,
            'provider_name': provider.name if provider else None,
        }
    })


@chat_bp.route('', methods=['POST'])
@jwt_required()
def chat():
    """流式聊天接口"""
    user_id = int(get_jwt_identity())
    data = request.get_json()
    if not isinstance(data, dict):
        return jsonify({'code': 400, 'message': '无效的请求体'}), 400

    messages = data.get('messages', [])
    if not isinstance(messages, list):
        return jsonify({'code': 400, 'message': '消息列表格式不正确'}), 400

    deep_think = bool(data.get('deep_think', False))
    raw_sys = data.get('system_prompt')
    system_prompt = (raw_sys.strip() if isinstance(raw_sys, str) else '').strip()
    provider_id = data.get('provider_id')
    conversation_id = data.get('conversation_id')
    persona_id = data.get('persona_id')
    model_id = data.get('model_id')

    # 获取用户设置
    settings = _get_user_settings(user_id)
    temperature = data.get('temperature', settings.temperature)
    frequency_penalty = data.get('frequency_penalty', settings.frequency_penalty)
    presence_penalty = data.get('presence_penalty', settings.presence_penalty)
    top_p = data.get('top_p', settings.top_p)

    # 获取提供商
    provider = _get_chat_provider(user_id, provider_id)
    if not provider:
        return jsonify({'code': 400, 'message': '请先配置对话模型提供商，或使用免费 API'}), 400

    if not messages or len(messages) == 0:
        return jsonify({'code': 400, 'message': '消息列表不能为空'}), 400

    # 获取对话
    conv = None
    if conversation_id:
        conv = Conversation.query.filter_by(id=conversation_id, user_id=user_id).first()

    # 构建消息列表
    formatted_messages = []
    for msg in messages:
        role = msg.get('role')
        content = msg.get('content', '')
        if role == 'assistant' and content:
            content = strip_html_to_text(content)
        formatted_messages.append({
            'role': role,
            'content': content
        })

    # 插入系统提示词
    final_prompt = _get_system_prompt(conv, user_id, persona_id, system_prompt)
    if final_prompt and (not formatted_messages or formatted_messages[0].get('role') != 'system'):
        formatted_messages.insert(0, {
            'role': 'system',
            'content': final_prompt
        })

    # 滑动窗口截断，控制上下文长度
    formatted_messages = _apply_context_window(formatted_messages)

    is_free_api = isinstance(provider, FreeAPIProvider)

    # 解析本次对话使用的模型
    effective_model = None
    if not is_free_api:
        effective_model = _resolve_chat_model(provider, conv, model_id)

    def generate():
        full_content_holder = [""]
        reasoning_holder = [""]
        model_holder = [""]
        streamer = MarkdownStreamer()

        try:
            model_name = effective_model or (
                (provider.model if hasattr(provider, 'model') else None) or '')
            if not model_name:
                model_name = 'glm-4.5-flash'
            if deep_think:
                model_name = effective_model or 'deepseek-reasoner'

            response, error = AIService.chat_completions(
                provider=provider,
                messages=formatted_messages,
                stream=True,
                temperature=temperature,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
                top_p=top_p,
                deep_think=deep_think,
                model=effective_model or None,
            )

            if response is None:
                yield sse_content(f'出错了：AI 服务请求失败 - {error}')
                yield sse_done()
                return

            if response.status_code != 200:
                error_text = response.text[:200] if response.text else "无响应体"
                yield sse_content(f'出错了：API 返回错误 - HTTP {response.status_code}: {error_text}')
                yield sse_done()
                return

            new_content, finish_reason = yield from iter_sse_content(
                response, full_content_holder, streamer, reasoning_holder, model_holder
            )
            full_content = full_content_holder[0]
            yield sse_done()

            # 保存到对话
            if conversation_id:
                try:
                    conv = Conversation.query.filter_by(id=conversation_id, user_id=user_id).first()
                    if conv:
                        last_user_msg = None
                        for msg in reversed(messages):
                            if msg.get('role') == 'user':
                                last_user_msg = msg
                                break
                        if last_user_msg:
                            user_msg = Message(
                                conversation_id=conv.id,
                                role='user',
                                content=strip_html_to_text(last_user_msg.get('content', ''))
                            )
                            db.session.add(user_msg)

                        ai_msg = Message(
                            conversation_id=conv.id,
                            role='assistant',
                            content=strip_html_to_text(full_content),
                            reasoning_content=reasoning_holder[0] if reasoning_holder[0] else None,
                            model=model_holder[0] or model_name
                        )
                        db.session.add(ai_msg)

                        if conv.title == '新对话' and last_user_msg:
                            text = strip_html_to_text(last_user_msg.get('content', ''))
                            conv.title = text[:20] + '...' if len(text) > 20 else text

                        if effective_model and not conv.model_id:
                            conv.model_id = effective_model

                        conv.updated_at = db.func.now()
                        db.session.commit()
                except Exception as e:
                    print(f"[保存消息失败] {e}")

        except GeneratorExit:
            print("[用户停止] 生成被中断")
        except Exception as e:
            print(f"[错误] {str(e)}")
            yield sse_content(f'出错了：服务端错误 - {str(e)}')
            yield sse_done()

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
            'X-Is-Free-Api': str(is_free_api).lower()
        }
    )


@chat_bp.route('/vision', methods=['POST'])
@jwt_required()
def vision_chat():
    """识图聊天接口"""
    user_id = int(get_jwt_identity())

    text = request.form.get('text', '请描述这张图片')
    provider_id = request.form.get('provider_id')
    conversation_id = request.form.get('conversation_id')

    image_file = request.files.get('image')
    if not image_file:
        return jsonify({'code': 400, 'message': '请上传图片'}), 400

    provider = _get_vision_provider(user_id, provider_id)
    if not provider:
        return jsonify({'code': 400, 'message': '请先配置图像理解模型提供商'}), 400

    settings = _get_user_settings(user_id)

    # 识图输入前置校验：空 / 超 5MB / 非真实图片一律 400
    image_data, guard_err = check_upload(image_file, MAX_IMAGE_SIZE)
    if guard_err:
        return jsonify({'code': 400, 'message': guard_err}), 400
    if detect_image_type(image_data) is None:
        return jsonify({'code': 400, 'message': '文件不是有效的图片'}), 400
    image_base64 = base64.b64encode(image_data).decode('utf-8')

    messages = [
        {'role': 'user', 'content': text}
    ]

    def generate():
        full_content_holder = [""]
        reasoning_holder = [""]
        model_holder = [""]
        streamer = MarkdownStreamer()

        try:
            response, error = AIService.vision_chat(
                provider=provider,
                messages=messages,
                image_base64=image_base64,
                stream=True,
                temperature=settings.temperature,
                frequency_penalty=settings.frequency_penalty,
                presence_penalty=settings.presence_penalty,
                top_p=settings.top_p,
            )

            if response is None:
                yield sse_content(f'出错了：识图服务请求失败 - {error}')
                yield sse_done()
                return

            if response.status_code != 200:
                error_text = response.text[:200] if response.text else "无响应体"
                yield sse_content(f'出错了：API 返回错误 - HTTP {response.status_code}: {error_text}')
                yield sse_done()
                return

            yield from iter_sse_content(
                response, full_content_holder, streamer, reasoning_holder, model_holder
            )
            yield sse_done()

            # 落库：识图对话同样保存到会话记录（与普通聊天保持一致）
            if conversation_id:
                try:
                    conv = Conversation.query.filter_by(id=conversation_id, user_id=user_id).first()
                    if conv:
                        user_msg = Message(
                            conversation_id=conv.id,
                            role='user',
                            content=strip_html_to_text(text)
                        )
                        db.session.add(user_msg)

                        ai_msg = Message(
                            conversation_id=conv.id,
                            role='assistant',
                            content=strip_html_to_text(full_content_holder[0]),
                            reasoning_content=reasoning_holder[0] if reasoning_holder[0] else None,
                            model=model_holder[0]
                        )
                        db.session.add(ai_msg)

                        if conv.title == '新对话':
                            t = strip_html_to_text(text)
                            conv.title = t[:20] + '...' if len(t) > 20 else t

                        conv.updated_at = db.func.now()
                        db.session.commit()
                except Exception as e:
                    print(f"[识图保存失败] {str(e)}")

        except GeneratorExit:
            print("[用户停止] 识图生成被中断")
        except Exception as e:
            print(f"[识图错误] {str(e)}")
            yield sse_content(f'出错了：服务端错误 - {str(e)}')
            yield sse_done()

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )


@chat_bp.route('/models', methods=['GET'])
@jwt_required()
def list_models():
    """获取模型列表"""
    user_id = int(get_jwt_identity())
    provider_id = request.args.get('provider_id')
    provider_type = request.args.get('type', 'chat')

    if provider_id:
        provider = ModelProvider.query.filter_by(id=provider_id, user_id=user_id).first()
    else:
        provider = ModelProvider.query.filter_by(
            user_id=user_id, provider_type=provider_type, is_default=True
        ).first()
        if not provider:
            provider = _get_free_provider()

    if not provider:
        return jsonify({'code': 400, 'message': '请先配置模型提供商'}), 400

    models, error = AIService.list_models(provider)
    if error:
        return jsonify({'code': 500, 'message': f'获取模型列表失败: {error}'}), 500

    return jsonify({
        'code': 200,
        'data': [{'id': m.get('id'), 'name': m.get('id')} for m in (models or [])]
    })
