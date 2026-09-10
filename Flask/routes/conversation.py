"""对话路由 - 对话列表、消息管理、置顶等"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models import Conversation, Message, ModelProvider, PersonaTemplate
from datetime import datetime, timedelta

conversation_bp = Blueprint('conversation', __name__, url_prefix='/api/conversations')


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
    now = datetime.utcnow()
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

    # 对话上限10条：超出时自动软删除最早创建的对话（仅统计未删除的）
    MAX_CONVERSATIONS = 10
    existing_count = Conversation.query.filter_by(user_id=user_id).filter(
        Conversation.deleted_at.is_(None)
    ).count()
    if existing_count >= MAX_CONVERSATIONS:
        oldest = Conversation.query.filter_by(user_id=user_id).filter(
            Conversation.deleted_at.is_(None)
        ).order_by(
            Conversation.created_at.asc()
        ).first()
        if oldest:
            oldest.deleted_at = datetime.utcnow()
            db.session.flush()

    conv = Conversation(
        user_id=user_id,
        title=title,
        provider_id=provider_id,
        persona_id=persona_id,
        system_prompt=system_prompt,
        temperature=temperature
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

    return jsonify({
        'code': 200,
        'data': {
            **conv.to_dict(),
            'messages': [m.to_dict() for m in messages]
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
    if 'background_image' in data:
        conv.background_image = data['background_image'] or None
    if 'background_cover' in data:
        conv.background_cover = data['background_cover'] or None
    if 'ai_avatar' in data:
        conv.ai_avatar = data['ai_avatar'] or None
    if 'user_avatar' in data:
        conv.user_avatar = data['user_avatar'] or None
    if 'message_opacity' in data:
        conv.message_opacity = data['message_opacity']
    if 'frequency_penalty' in data:
        conv.frequency_penalty = data['frequency_penalty']
    if 'presence_penalty' in data:
        conv.presence_penalty = data['presence_penalty']
    if 'auto_play_voice' in data:
        conv.auto_play_voice = bool(data['auto_play_voice'])
    
    conv.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'code': 200,
        'message': '更新成功',
        'data': conv.to_dict()
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
    conv.updated_at = datetime.utcnow()
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

    conv.deleted_at = datetime.utcnow()
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
    conv.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'code': 200,
        'message': '已清空'
    })
