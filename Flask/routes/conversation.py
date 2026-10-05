"""对话路由 - 对话列表、消息管理、置顶等"""
import json
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models import (Conversation, Message, ModelProvider, PersonaTemplate,
                    local_now, ConversationMediaLog, ConversationSummary)
from services.media_log import log_media


def _log_media_if_changed(user_id, conv_id, data, old_bg, old_ai, old_user):
    """若背景图/AI头像/用户头像本次设置非空且与已存值不同，写入素材记录。"""
    pairs = [
        ('background', 'background_image', old_bg),
        ('ai_avatar', 'ai_avatar', old_ai),
        ('user_avatar', 'user_avatar', old_user),
    ]
    for media_type, key, old_val in pairs:
        new_val = data.get(key)
        if not isinstance(new_val, str):
            continue
        if old_val and old_val.strip() == new_val.strip():
            continue
        log_media(user_id, media_type, new_val, conversation_id=conv_id)
from services.markdown_streamer import render_markdown
from datetime import datetime, timedelta

conversation_bp = Blueprint('conversation', __name__, url_prefix='/api/conversations')

DEFAULT_REPLY_TEMPLATE = json.dumps({
    'preset': 'blush',
    'name': '脸红',
    'protocol': 'full',
    'length': 'long',
    'enhance': True,
}, ensure_ascii=False)


@conversation_bp.route('', methods=['GET'])
@jwt_required()
def list_conversations():
    """获取对话列表（带按日期分组的数据）"""
    user_id = int(get_jwt_identity())
    
    conversations = Conversation.query.filter_by(user_id=user_id).filter(
        Conversation.deleted_at.is_(None)
    ).order_by(
        Conversation.is_pinned.desc(),
        Conversation.updated_at.desc()
    ).all()
    
    # 按日期分组
    now = local_now()
    today_start = datetime(now.year, now.month, now.day)
    yesterday_start = today_start - timedelta(days=1)
    week_ago_start = today_start - timedelta(days=7)
    month_ago_start = today_start - timedelta(days=30)
    
    groups = {
        'pinned': [],     # 置顶
        'today': [],      # 今天
        'yesterday': [],  # 昨天
        'week': [],       # 7天内
        'month': [],      # 30天内
        'older': []       # 更早
    }
    
    for conv in conversations:
        conv_dict = conv.to_dict()
        updated = conv.updated_at or conv.created_at
        
        if conv.is_pinned:
            groups['pinned'].append(conv_dict)
        elif updated >= today_start:
            groups['today'].append(conv_dict)
        elif updated >= yesterday_start:
            groups['yesterday'].append(conv_dict)
        elif updated >= week_ago_start:
            groups['week'].append(conv_dict)
        elif updated >= month_ago_start:
            groups['month'].append(conv_dict)
        else:
            groups['older'].append(conv_dict)
    
    return jsonify({
        'code': 200,
        'data': {
            'items': [c.to_dict() for c in conversations],
            'groups': groups
        }
    })


@conversation_bp.route('', methods=['POST'])
@jwt_required()
def create_conversation():
    """创建新对话"""
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    
    title = data.get('title', '新对话').strip() or '新对话'
    provider_id = data.get('provider_id')
    model_id = data.get('model_id')
    persona_id = data.get('persona_id')
    system_prompt = data.get('system_prompt')
    temperature = data.get('temperature')

    # 校验提供商归属；失效 id（已删除/残留）降级为 None，不阻断建会话
    if provider_id:
        provider = ModelProvider.query.filter_by(id=provider_id, user_id=user_id).first()
        if not provider:
            provider_id = None

    # 校验角色模板归属；失效 id 同样降级
    if persona_id:
        persona = PersonaTemplate.query.filter_by(id=persona_id, user_id=user_id).first()
        if not persona:
            persona_id = None

    # 对话上限10条：超出时返回提示，前端确认后带 force_delete=true 重新请求
    MAX_CONVERSATIONS = 10
    existing_count = Conversation.query.filter_by(user_id=user_id).filter(
        Conversation.deleted_at.is_(None)
    ).count()
    if existing_count >= MAX_CONVERSATIONS:
        force = data.get('force_delete', False)
        if not force:
            return jsonify({
                'code': 409,
                'message': f'已达对话保存上限（{MAX_CONVERSATIONS} 个），继续新建将删除最早创建的对话',
                'data': {'count': existing_count, 'max': MAX_CONVERSATIONS}
            }), 200
        oldest = Conversation.query.filter_by(user_id=user_id).filter(
            Conversation.deleted_at.is_(None)
        ).order_by(
            Conversation.created_at.asc()
        ).first()
        if oldest:
            oldest.deleted_at = local_now()
            db.session.flush()

    conv = Conversation(
        user_id=user_id,
        title=title,
        provider_id=provider_id,
        model_id=model_id,
        persona_id=persona_id,
        system_prompt=system_prompt,
        temperature=temperature,
        rich_marker_enabled=bool(data.get('rich_marker_enabled', True)),
        reply_template=data.get('reply_template') or DEFAULT_REPLY_TEMPLATE,
    )
    db.session.add(conv)
    db.session.commit()
    
    return jsonify({
        'code': 200,
        'message': '创建成功',
        'data': conv.to_dict()
    })


@conversation_bp.route('/<int:conv_id>', methods=['GET'])
@jwt_required()
def get_conversation(conv_id):
    """获取对话详情及消息"""
    user_id = int(get_jwt_identity())
    conv = Conversation.query.filter_by(id=conv_id, user_id=user_id).filter(
        Conversation.deleted_at.is_(None)
    ).first()
    if not conv:
        return jsonify({'code': 404, 'message': '对话不存在'}), 404

    messages = Message.query.filter_by(conversation_id=conv_id).order_by(
        Message.created_at.asc()
    ).all()

    # 历史消息的 content 存的是纯文本（落库时 strip_html_to_text 剥掉了 HTML），
    # 前端渲染走的是 v-html，直接塞纯文本会把所有段落压成一行——与刚生成完
    # 走 sse_html(render_markdown()) 的效果不一致，表现为「切页面后文字折叠」。
    # 这里额外给 assistant 消息补一个渲染好的 HTML 字段，前端优先用它。
    payload = []
    for m in messages:
        d = m.to_dict()
        if m.role == 'assistant' and m.content:
            try:
                d['content_html'] = render_markdown(m.content)
            except Exception:
                # 渲染失败不阻断历史消息加载
                d['content_html'] = ''
        payload.append(d)

    return jsonify({
        'code': 200,
        'data': {
            **conv.to_dict(),
            'messages': payload
        }
    })


@conversation_bp.route('/<int:conv_id>', methods=['PUT'])
@jwt_required()
def update_conversation(conv_id):
    """更新对话信息（标题、置顶等）"""
    user_id = int(get_jwt_identity())
    conv = Conversation.query.filter_by(id=conv_id, user_id=user_id).filter(
        Conversation.deleted_at.is_(None)
    ).first()
    if not conv:
        return jsonify({'code': 404, 'message': '对话不存在'}), 404
    
    data = request.get_json() or {}
    
    if 'title' in data:
        raw_title = data['title']
        conv.title = (raw_title.strip() if isinstance(raw_title, str)
                      else ('' if raw_title is None else str(raw_title))).strip() or '新对话'
    if 'is_pinned' in data:
        conv.is_pinned = bool(data['is_pinned'])
    if 'provider_id' in data:
        pid = data['provider_id']
        if pid is not None and not ModelProvider.query.filter_by(id=pid, user_id=user_id).first():
            return jsonify({'code': 400, 'message': '无效的模型提供商'}), 400
        conv.provider_id = pid
    if 'model_id' in data:
        conv.model_id = data.get('model_id') or None
    if 'persona_id' in data:
        perid = data['persona_id']
        if perid is not None and not PersonaTemplate.query.filter_by(id=perid, user_id=user_id).first():
            return jsonify({'code': 400, 'message': '无效的角色模板'}), 400
        conv.persona_id = perid
    if 'user_persona_id' in data:
        upid = data['user_persona_id']
        if upid is not None and not PersonaTemplate.query.filter_by(id=upid, user_id=user_id).first():
            return jsonify({'code': 400, 'message': '无效的用户人设'}), 400
        conv.user_persona_id = upid
    if 'system_prompt' in data:
        conv.system_prompt = data['system_prompt']
    if 'temperature' in data:
        conv.temperature = data['temperature']
    # 先记录素材旧值，供「设置历史」比较是否发生变化（下列赋值会覆盖 conv 上的字段）
    _old_bg = conv.background_image
    _old_ai = conv.ai_avatar
    _old_user = conv.user_avatar
    # 背景图/头像：用户「清除」时前端传 null（或空串），后端置 None 真正清除；
    # 历史记录由 _log_media_if_changed 在「设置/变更」时单独落库，与当前值是否清除解耦。
    if 'background_image' in data:
        conv.background_image = data['background_image'] or None
    if 'background_cover' in data:
        conv.background_cover = data['background_cover'] or None
    if 'ai_avatar' in data:
        conv.ai_avatar = data['ai_avatar'] or None
    if 'user_avatar' in data:
        conv.user_avatar = data['user_avatar'] or None
    # 记录对话素材设置历史：每次「设置/变更」非空值且较上次有变化时落库，
    # 供管理员在后台追溯（前端清除不真正置空，故历史始终保留最后设置）。
    try:
        _log_media_if_changed(user_id, conv.id, data, _old_bg, _old_ai, _old_user)
    except Exception:
        current_app.logger.warning('[对话素材] 历史记录写入失败', exc_info=True)
    if 'message_opacity' in data:
        conv.message_opacity = data['message_opacity']
    if 'frequency_penalty' in data:
        conv.frequency_penalty = data['frequency_penalty']
    if 'presence_penalty' in data:
        conv.presence_penalty = data['presence_penalty']
    if 'auto_play_voice' in data:
        conv.auto_play_voice = bool(data['auto_play_voice'])
    # 记忆宫殿：压缩触发阈值（1-20 轮），越界直接拒绝，避免非法值入库
    if 'summary_threshold' in data:
        raw = data['summary_threshold']
        try:
            thr = int(raw)
        except (TypeError, ValueError):
            return jsonify({'code': 400, 'message': '压缩轮数必须是 1-20 的整数'}), 400
        if thr < 1 or thr > 20:
            return jsonify({'code': 400, 'message': '压缩轮数必须在 1-20 之间'}), 400
        conv.summary_threshold = thr
    # 提示词兜底：默认关闭，开启后才会把后端写死的追加提示词接在人物设定之后
    if 'append_prompt_enabled' in data:
        conv.append_prompt_enabled = bool(data['append_prompt_enabled'])
    # 界面标记（富消息）：默认关闭，开启后把标记约定接在系统提示词后
    if 'rich_marker_enabled' in data:
        conv.rich_marker_enabled = bool(data['rich_marker_enabled'])
    # 回复渲染模板：JSON 文本（前端按 preset 解析版式，后端只取 prompt 注入）
    if 'reply_template' in data:
        raw_tpl = data['reply_template']
        if raw_tpl in (None, ''):
            conv.reply_template = None
        elif isinstance(raw_tpl, str):
            if len(raw_tpl) > 20000:
                return jsonify({'code': 400, 'message': '渲染模板过长（上限 20000 字符）'}), 400
            # 必须是合法 JSON 对象，避免脏数据在读取时反复解析失败
            try:
                parsed = json.loads(raw_tpl)
            except (TypeError, ValueError):
                return jsonify({'code': 400, 'message': '渲染模板不是合法 JSON'}), 400
            if not isinstance(parsed, dict):
                return jsonify({'code': 400, 'message': '渲染模板必须是 JSON 对象'}), 400
            conv.reply_template = raw_tpl
        else:
            return jsonify({'code': 400, 'message': '渲染模板格式不正确'}), 400

    conv.updated_at = local_now()
    db.session.commit()
    
    return jsonify({
        'code': 200,
        'message': '更新成功',
        'data': conv.to_dict()
    })


@conversation_bp.route('/<int:conv_id>/summaries', methods=['GET'])
@jwt_required()
def list_summaries(conv_id):
    """记忆宫殿：列出该对话历次压缩产生的摘要（按压缩次数倒序）。"""
    user_id = int(get_jwt_identity())
    conv = Conversation.query.filter_by(id=conv_id, user_id=user_id).filter(
        Conversation.deleted_at.is_(None)
    ).first()
    if not conv:
        return jsonify({'code': 404, 'message': '对话不存在'}), 404

    rows = ConversationSummary.query.filter_by(
        conversation_id=conv.id, user_id=user_id
    ).order_by(ConversationSummary.seq.desc()).all()

    return jsonify({
        'code': 200,
        'data': {
            'conversation_id': conv.id,
            'threshold': conv.summary_threshold or 10,
            'compress_count': len(rows),
            'current_summary': conv.summary,
            'summary_upto_id': conv.summary_upto_id,
            'items': [r.to_dict() for r in rows],
        }
    })


@conversation_bp.route('/<int:conv_id>/pin', methods=['PUT'])
@jwt_required()
def toggle_pin(conv_id):
    """切换置顶状态"""
    user_id = int(get_jwt_identity())
    conv = Conversation.query.filter_by(id=conv_id, user_id=user_id).filter(
        Conversation.deleted_at.is_(None)
    ).first()
    if not conv:
        return jsonify({'code': 404, 'message': '对话不存在'}), 404
    
    conv.is_pinned = not conv.is_pinned
    conv.updated_at = local_now()
    db.session.commit()
    
    return jsonify({
        'code': 200,
        'message': '操作成功',
        'data': {'is_pinned': conv.is_pinned}
    })


@conversation_bp.route('/<int:conv_id>', methods=['DELETE'])
@jwt_required()
def delete_conversation(conv_id):
    """删除对话（软删除）"""
    user_id = int(get_jwt_identity())
    conv = Conversation.query.filter_by(id=conv_id, user_id=user_id).filter(
        Conversation.deleted_at.is_(None)
    ).first()
    if not conv:
        return jsonify({'code': 404, 'message': '对话不存在'}), 404

    conv.deleted_at = local_now()
    db.session.commit()

    return jsonify({
        'code': 200,
        'message': '删除成功'
    })


@conversation_bp.route('/<int:conv_id>/messages', methods=['DELETE'])
@jwt_required()
def clear_messages(conv_id):
    """清空对话消息"""
    user_id = int(get_jwt_identity())
    conv = Conversation.query.filter_by(id=conv_id, user_id=user_id).filter(
        Conversation.deleted_at.is_(None)
    ).first()
    if not conv:
        return jsonify({'code': 404, 'message': '对话不存在'}), 404
    
    Message.query.filter_by(conversation_id=conv_id).delete()
    conv.updated_at = local_now()
    db.session.commit()
    
    return jsonify({
        'code': 200,
        'message': '已清空'
    })
