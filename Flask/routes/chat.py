"""聊天路由 - 流式对话、识图对话"""
import json
import base64
from flask import Blueprint, request, Response, stream_with_context, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models import ModelProvider, Conversation, Message, PersonaTemplate, UserSettings
from services.ai_service import AIService, FreeAPIProvider
from services.markdown_streamer import (
    strip_html_to_text,
    render_markdown,
    sse_content, sse_reasoning, sse_done, sse_html
)
from services.upload_guard import check_upload, detect_image_type, MAX_IMAGE_SIZE

chat_bp = Blueprint('chat', __name__, url_prefix='/api/chat')


def iter_sse_content(response, full_content_holder, reasoning_holder, model_holder=None):
    """遍历 API 流式响应，原文逐块透传（增量展示），思考过程单独下发。"""
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
                        # 输出原文增量而非整段 Markdown，真正实现逐 token 流式
                        yield sse_content(content)
                except (json.JSONDecodeError, KeyError, IndexError):
                    pass
    except GeneratorExit:
        print("[客户端断开] 停止生成")
        raise

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
    """获取对话用的提供商（优先指定已启用配置，其次已启用配置，最后免费API）

    指定 provider_id 失效（已删除/不存在/总开关关闭）时自动降级，避免前端残留 id 导致 400。
    即：只要「总开关」（provider.enabled）关闭，即使里面的模型是开启的，也不会被使用，
    会回落到其他已启用配置，最后回落到我方配置的免费 API。
    未指定时，从「已启用」的配置中选取（优先默认配置，否则按权重/创建时间取最先启用的）。
    """
    if provider_id:
        provider = ModelProvider.query.filter_by(
            id=provider_id, user_id=user_id, provider_type='chat', enabled=True
        ).first()
        if provider:
            return provider
    provider = ModelProvider.query.filter_by(
        user_id=user_id, provider_type='chat', enabled=True
    ).order_by(
        ModelProvider.is_default.desc(),
        ModelProvider.weight.desc(),
        ModelProvider.created_at.desc()
    ).first()
    if provider:
        return provider
    # 用户没有启用任何配置，使用我方配置的免费 API
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


def _get_system_prompt(conv, user_id, persona_id=None, custom_prompt=None):
    """获取系统提示词（优先级：自定义 > 角色模板 > 指定角色(仅限本人) > 默认角色）"""
    if custom_prompt:
        return custom_prompt
    if conv and conv.system_prompt:
        return conv.system_prompt
    # 从对话的角色模板获取
    if conv and conv.persona:
        return conv.persona.system_prompt
    # 从指定角色获取：必须属于当前用户，防止越权读取他人设定
    if persona_id:
        persona = PersonaTemplate.query.filter_by(
            id=persona_id, user_id=user_id
        ).first()
        if persona:
            return persona.system_prompt
    # 使用默认角色
    default_persona = PersonaTemplate.query.filter_by(
        user_id=user_id, is_default=True
    ).first()
    if default_persona:
        return default_persona.system_prompt
    return ''


def _save_ai_message(conversation_id, user_id, content, reasoning=None,
                     model_name=None, title_source=None, model_id=None):
    """将 AI 回复落库（普通聊天与识图共用）。

    独立于流式生成器之外可复用：正常流结束调用一次；
    客户端断开（GeneratorExit）时内容已收集完整也调用一次，
    保证回复不会因连接关闭而丢失。
    """
    if not conversation_id or not content:
        return
    try:
        conv = Conversation.query.filter_by(id=conversation_id, user_id=user_id).first()
        if not conv:
            return
        ai_msg = Message(
            conversation_id=conv.id,
            role='assistant',
            content=strip_html_to_text(content),
            reasoning_content=reasoning or None,
            model=model_name
        )
        db.session.add(ai_msg)

        if conv.title == '新对话' and title_source:
            t = strip_html_to_text(title_source)
            conv.title = t[:20] + '...' if len(t) > 20 else t

        if model_id and not conv.model_id:
            conv.model_id = model_id

        conv.updated_at = db.func.now()
        db.session.commit()
    except Exception as e:
        print(f"[保存消息失败] {type(e).__name__}: {e}", flush=True)

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

    # 设置行异常（历史数据/直插库导致 NULL）时回退默认值，避免下方数值钳制崩溃
    if temperature is None:
        temperature = 0.8
    if frequency_penalty is None:
        frequency_penalty = 0.0
    if presence_penalty is None:
        presence_penalty = 0.0
    if top_p is None:
        top_p = 0.95

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

    # 对话独立参数覆盖通用设置（未单独设置时沿用通用值）
    if conv:
        if conv.temperature is not None:
            temperature = conv.temperature
        if conv.frequency_penalty is not None:
            frequency_penalty = conv.frequency_penalty
        if conv.presence_penalty is not None:
            presence_penalty = conv.presence_penalty

    # 未指定对话时自动创建，保证聊天记录落库（前端漏建时兜底）
    if not conv:
        conv = Conversation(
            user_id=user_id,
            title='新对话',
            provider_id=provider.id if not isinstance(provider, FreeAPIProvider) else None,
            persona_id=persona_id,
            system_prompt=system_prompt or None,
            temperature=temperature,
        )
        db.session.add(conv)
        db.session.commit()
        conversation_id = conv.id

    # 持久化开场白：对话无 AI 消息时，将角色开场白作为首条 assistant 消息写入
    if conv:
        has_ai_msg = Message.query.filter_by(conversation_id=conv.id, role='assistant').first()
        if not has_ai_msg:
            greeting_persona = conv.persona or (
                PersonaTemplate.query.filter_by(id=persona_id, user_id=user_id).first() if persona_id else None
            ) or PersonaTemplate.query.filter_by(user_id=user_id, is_default=True).first()
            if greeting_persona and greeting_persona.greeting:
                db.session.add(Message(
                    conversation_id=conv.id, role='assistant', content=greeting_persona.greeting
                ))
                db.session.commit()

    # 立即持久化最新用户消息：AI 仍在生成时切换对话也不丢消息。
    # 通过与已存的最末用户消息比对去重，重试/重新生成时不会重复入库。
    if conv:
        last_user_content = ''
        for msg in reversed(messages):
            if msg.get('role') == 'user':
                last_user_content = str(msg.get('content', '')) or ''
                break
        if last_user_content:
            last_stored_user = Message.query.filter_by(
                conversation_id=conv.id, role='user'
            ).order_by(Message.created_at.desc(), Message.id.desc()).first()
            plain = strip_html_to_text(last_user_content)
            if not last_stored_user or last_stored_user.content != plain:
                db.session.add(Message(
                    conversation_id=conv.id, role='user', content=plain
                ))
                db.session.commit()

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

    # 注入用户人设：如果对话设置了用户人设，将其拼接到系统提示词最前面
    if conv and conv.user_persona_id:
        user_persona = PersonaTemplate.query.filter_by(
            id=conv.user_persona_id, user_id=user_id
        ).first()
        if user_persona and user_persona.system_prompt:
            final_prompt = user_persona.system_prompt + '\n\n' + (final_prompt or '')

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
        # 用户提供商没有可用模型时降级到免费 API，
        # 避免把默认模型名发往错误厂商导致 400
        if effective_model is None:
            free = _get_free_provider()
            if free:
                provider = free
                is_free_api = True
                effective_model = free.model

    def generate():
        full_content_holder = [""]
        reasoning_holder = [""]
        model_holder = [""]
        saved = False

        # 本次请求最后一条用户消息（用于自动命名标题）
        last_user_text = ''
        for msg in reversed(messages):
            if msg.get('role') == 'user':
                last_user_text = str(msg.get('content', '')) or ''
                break

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
                response, full_content_holder, reasoning_holder, model_holder
            )
            full_content = full_content_holder[0]

            # 先落库再下发最终事件：客户端收到 [DONE] 即断开连接，
            # 若在最后一个 yield 之后才写库，生成器不再被推进，AI 回复会丢失（并发实测出现）
            if conversation_id:
                _save_ai_message(
                    conversation_id, user_id, full_content,
                    reasoning=reasoning_holder[0],
                    model_name=model_holder[0] or model_name,
                    title_source=last_user_text,
                    model_id=effective_model,
                )
                saved = True

            # 流结束后一次性下发渲染好的（含白名单过滤）完整 HTML，前端替换流式原文
            yield sse_html(render_markdown(full_content))
            yield sse_done()
        except GeneratorExit:
            # 客户端断开：内容已收集完整时尽力落库，避免回复丢失
            if not saved and conversation_id and full_content_holder[0]:
                _save_ai_message(
                    conversation_id, user_id, full_content_holder[0],
                    reasoning=reasoning_holder[0],
                    model_name=model_holder[0] or model_name,
                    title_source=last_user_text,
                    model_id=effective_model,
                )
            print("[用户停止] 生成被中断")
            raise
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
    raw_sys = request.form.get('system_prompt')

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
    # 识图同样注入人设/图片生成能力约定（前端按能力拼好）；system 消息会被原样转发给模型
    system_prompt = (raw_sys.strip() if isinstance(raw_sys, str) else '').strip()
    if system_prompt:
        messages.insert(0, {'role': 'system', 'content': system_prompt})

    # 立即持久化识图的用户消息，避免生成过程中切换对话丢失（与普通聊天一致）
    if conversation_id:
        conv = Conversation.query.filter_by(id=conversation_id, user_id=user_id).first()
        if conv:
            last_stored_user = Message.query.filter_by(
                conversation_id=conv.id, role='user'
            ).order_by(Message.created_at.desc(), Message.id.desc()).first()
            plain = strip_html_to_text(text)
            if not last_stored_user or last_stored_user.content != plain:
                db.session.add(Message(conversation_id=conv.id, role='user', content=plain))
                db.session.commit()

    def generate():
        full_content_holder = [""]
        reasoning_holder = [""]
        model_holder = [""]
        saved = False

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
                response, full_content_holder, reasoning_holder, model_holder
            )
            # 先落库再下发最终事件（与普通聊天一致，避免客户端断开后生成器不推进导致丢失）
            if conversation_id:
                _save_ai_message(
                    conversation_id, user_id, full_content_holder[0],
                    reasoning=reasoning_holder[0],
                    model_name=model_holder[0],
                    title_source=text,
                )
                saved = True

            yield sse_html(render_markdown(full_content_holder[0]))
            yield sse_done()
        except GeneratorExit:
            # 客户端断开：内容已收集完整时尽力落库
            if not saved and conversation_id and full_content_holder[0]:
                _save_ai_message(
                    conversation_id, user_id, full_content_holder[0],
                    reasoning=reasoning_holder[0],
                    model_name=model_holder[0],
                    title_source=text,
                )
            print("[用户停止] 识图生成被中断")
            raise
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


# ---------------------------------------------------------------------------
# 提示词工具（替代「清空对话」）：一键生成人物设定 / 生图改图提示词
# ---------------------------------------------------------------------------
# 默认系统提示词（未填写自定义提示词时使用）
DEFAULT_CHARACTER_PROMPT = (
    '你是一位资深的人物设定策划师。请根据用户的需求，产出一份可直接用于角色扮演、'
    '小说或剧本创作的人物设定。要求覆盖：姓名、年龄、身份与职业、性格（含优点与缺点）、'
    '背景经历、外貌特征、说话风格与口头禅、能力与特长、目标与动机、人际关系与潜在冲突。'
    '内容要具体、有层次，避免空洞套话，用分点或分段呈现。只输出设定正文，不要任何额外解释。'
)
DEFAULT_IMAGE_PROMPT = (
    '你是一位专业的 Prompt 提示词工程师。请根据用户的需求，产出一条可直接复制到'
    '文生图 / 图生图模型的高质量提示词。要求包含：主体描述、环境场景、视觉风格'
    '（如写实 / 动漫 / 油画 / 赛博朋克等）、光线与氛围、构图与镜头视角、材质细节，'
    '并附带常用画质关键词（如 high detail, 8k, sharp focus）。建议中英文对照。'
    '若涉及修改图片，请额外补充针对原图的具体修改要求。只输出提示词内容本身。'
)


@chat_bp.route('/prompt-tool', methods=['GET'])
@jwt_required()
def prompt_tool_info():
    """提示词工具的候选模型与默认提示词。"""
    user_id = int(get_jwt_identity())
    free = _get_free_provider()

    providers = ModelProvider.query.filter_by(
        user_id=user_id, provider_type='chat', enabled=True
    ).order_by(ModelProvider.is_default.desc(), ModelProvider.created_at.desc()).all()

    prov_list = []
    for p in providers:
        models = []
        if hasattr(p, 'models'):
            for m in p.models or []:
                if m.enabled:
                    models.append({'id': m.model_id, 'name': m.model_id})
        if not models and p.model:
            models.append({'id': p.model, 'name': p.model})
        prov_list.append({'id': p.id, 'name': p.name, 'models': models})

    return jsonify({'code': 200, 'data': {
        'free_model': (free.model if free else current_app.config.get('FREE_API_MODEL') or 'glm-4-flash'),
        'free_name': free.name if free else current_app.config.get('FREE_API_NAME', '免费 API'),
        'providers': prov_list,
        'default_prompts': {
            'character': DEFAULT_CHARACTER_PROMPT,
            'image': DEFAULT_IMAGE_PROMPT,
        }
    }})


@chat_bp.route('/prompt-tool', methods=['POST'])
@jwt_required()
def prompt_tool_generate():
    """根据分类生成人物设定或生图/改图提示词。

    请求体：{category:'character'|'image', provider_id?, model?, custom_prompt?, base_info?}
    - 不传 provider_id 时默认使用 .env 里的免费 API（glm-4-flash）
    - 传了 model 则覆盖默认模型名（支持自定义模型）
    - 传了 custom_prompt 则替代默认系统提示词；否则用默认系统提示词
    - 传了 base_info 则基于该基础信息扩写；未传则随机生成一个主题
    """
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    category = data.get('category')
    if category not in ('character', 'image'):
        return jsonify({'code': 400, 'message': '无效的分类'}), 400

    provider_id = data.get('provider_id')
    custom_model = (data.get('model') or '').strip()
    custom_prompt = (data.get('custom_prompt') or '').strip()
    base_info = (data.get('base_info') or '').strip()

    provider = None
    if provider_id:
        provider = ModelProvider.query.filter_by(
            id=provider_id, user_id=user_id, provider_type='chat'
        ).first()
    if not provider:
        provider = _get_free_provider()
    if not provider:
        return jsonify({'code': 400, 'message': '未配置可用的模型（可配置聊天模型或在 .env 中启用 FREE_API）'}), 400

    is_free = isinstance(provider, FreeAPIProvider)
    if is_free:
        model = custom_model or provider.model or current_app.config.get('FREE_API_MODEL') or 'glm-4-flash'
    else:
        model = custom_model or (_resolve_chat_model(provider) or provider.model or '')

    system_prompt = custom_prompt or (
        DEFAULT_IMAGE_PROMPT if category == 'image' else DEFAULT_CHARACTER_PROMPT
    )
    if category == 'image':
        base_task = (
            f'用户的基础信息如下，请据此扩写成一张图片的创作提示词：\n{base_info}'
            if base_info
            else '用户未提供任何基础信息，请随机生成一个创意十足、主题鲜明的图片创作提示词。'
        )
    else:
        base_task = (
            f'用户的基础信息如下，请据此扩写一份人物设定：\n{base_info}'
            if base_info
            else '用户未提供任何基础信息，请随机生成一个特点鲜明、有血有肉的人物设定。'
        )

    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': base_task},
    ]

    try:
        response, error = AIService.chat_completions(
            provider=provider, messages=messages, stream=False,
            temperature=0.7, model=model,
        )
    except Exception as e:
        return jsonify({'code': 500, 'message': f'生成失败：{str(e)}'}), 500

    if response is None:
        return jsonify({'code': 500, 'message': f'AI 服务请求失败：{error}'}), 500
    if response.status_code != 200:
        return jsonify({'code': 500, 'message': f'API 返回错误 HTTP {response.status_code}: {response.text[:200]}'}), 500

    try:
        content = response.json()['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError, ValueError):
        return jsonify({'code': 500, 'message': '响应格式异常'}), 500

    return jsonify({'code': 200, 'data': {'content': content, 'model': model}})
