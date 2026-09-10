"""后台管理路由 - 监控所有用户与数据信息（管理员专用）

管理员账号独立于普通用户体系，由环境变量 ADMIN_USERNAME / ADMIN_PASSWORD 配置
（见 .env），通过 POST /api/admin/login 登录换取带 role=admin 声明的 JWT。
所有数据接口均要求该管理员令牌，避免越权访问。
"""
from flask import Blueprint, request, jsonify, current_app, Response
from flask_jwt_extended import jwt_required, get_jwt, create_access_token
from sqlalchemy import func
from functools import wraps
from extensions import db
from services.rate_limit import limiter
from models import (
    User, Conversation, Message, ModelProvider, PersonaTemplate,
)

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')


def _client_ip():
    # 仅信任反向代理头（减少伪造限流）；直连场景取对端地址
    if current_app.config.get('TRUST_PROXY_HEADERS'):
        return request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown').split(',')[0].strip()
    return request.remote_addr or 'unknown'


@admin_bp.route('/login', methods=['POST'])
def admin_login():
    """管理员登录：校验 .env 中的 ADMIN_USERNAME / ADMIN_PASSWORD。"""
    # 登录限流：每 IP 每分钟最多 10 次
    if not limiter.hit(f'admin_login:{_client_ip()}', 10, 60):
        return jsonify({'code': 429, 'message': '尝试过于频繁，请稍后再试'}), 429

    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    expected_user = current_app.config.get('ADMIN_USERNAME', 'admin')
    expected_pass = current_app.config.get('ADMIN_PASSWORD', '')

    if not expected_pass:
        return jsonify({'code': 500, 'message': '未配置管理员密码，请在 .env 中设置 ADMIN_PASSWORD'}), 500

    if username != expected_user or password != expected_pass:
        return jsonify({'code': 401, 'message': '管理员账号或密码错误'}), 401

    token = create_access_token(identity='admin', additional_claims={'role': 'admin'})
    return jsonify({
        'code': 200,
        'message': '登录成功',
        'data': {'access_token': token, 'username': username}
    })


def admin_required(fn):
    """要求携带 role=admin 的管理员令牌。"""
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        if get_jwt().get('role') != 'admin':
            return jsonify({'code': 403, 'message': '无权限访问'}), 403
        return fn(*args, **kwargs)
    return wrapper


@admin_bp.route('/me', methods=['GET'])
@jwt_required()
def admin_me():
    """校验管理员令牌是否有效（登录态检测）。"""
    if get_jwt().get('role') != 'admin':
        return jsonify({'code': 403, 'message': '无权限访问'}), 403
    return jsonify({'code': 200, 'data': {'is_admin': True}})


@admin_bp.route('/stats', methods=['GET'])
@admin_required
def platform_stats():
    """平台整体数据统计。"""
    user_count = User.query.filter_by(is_active=True).filter(User.deleted_at.is_(None)).count()
    conversation_count = db.session.query(func.count(Conversation.id)).filter(
        Conversation.deleted_at.is_(None)
    ).scalar() or 0
    message_count = db.session.query(func.count(Message.id)).scalar() or 0
    provider_count = ModelProvider.query.count()
    persona_count = PersonaTemplate.query.count()

    # 今日新增
    from datetime import datetime
    today_start = datetime(datetime.utcnow().year, datetime.utcnow().month, datetime.utcnow().day)
    recent_users = User.query.filter(User.created_at >= today_start).filter(
        User.deleted_at.is_(None)
    ).count()
    recent_convs = Conversation.query.filter(Conversation.created_at >= today_start).filter(
        Conversation.deleted_at.is_(None)
    ).count()
    recent_msgs = Message.query.filter(Message.created_at >= today_start).count()

    return jsonify({
        'code': 200,
        'data': {
            'user_count': user_count,
            'conversation_count': conversation_count,
            'message_count': message_count,
            'provider_count': provider_count,
            'persona_count': persona_count,
            'today': {
                'users': recent_users,
                'conversations': recent_convs,
                'messages': recent_msgs,
            }
        }
    })


@admin_bp.route('/users', methods=['GET'])
@admin_required
def list_users():
    """用户列表及各用户的数据量汇总。"""
    users = User.query.order_by(User.created_at.desc()).all()

    conv_counts = dict(
        db.session.query(Conversation.user_id, func.count(Conversation.id))
        .filter(Conversation.deleted_at.is_(None))
        .group_by(Conversation.user_id).all()
    )
    msg_counts = dict(
        db.session.query(Message.conversation_id, func.count(Message.id))
        .group_by(Message.conversation_id).all()
    )
    prov_counts = dict(
        db.session.query(ModelProvider.user_id, func.count(ModelProvider.id))
        .group_by(ModelProvider.user_id).all()
    )
    persona_counts = dict(
        db.session.query(PersonaTemplate.user_id, func.count(PersonaTemplate.id))
        .group_by(PersonaTemplate.user_id).all()
    )

    # 每个用户最新一条消息时间 = 最近活跃（排除已软删除的对话）
    latest_msg_by_user = {}
    latest_rows = (
        db.session.query(Conversation.user_id, func.max(Message.created_at))
        .join(Message, Message.conversation_id == Conversation.id)
        .filter(Conversation.deleted_at.is_(None))
        .group_by(Conversation.user_id).all()
    )
    for uid, ts in latest_rows:
        latest_msg_by_user[uid] = ts.isoformat() if ts else None

    result = []
    for u in users:
        conv_ids = [c.id for c in u.conversations if c.deleted_at is None]
        msg_count = sum(msg_counts.get(cid, 0) for cid in conv_ids)
        result.append({
            'id': u.id,
            'username': u.username,
            'email': u.email,
            'avatar': u.avatar,
            'gender': u.gender,
            'is_active': u.is_active,
            'deleted_at': u.deleted_at.isoformat() if u.deleted_at else None,
            'created_at': u.created_at.isoformat() if u.created_at else None,
            'conversation_count': len(conv_ids),
            'message_count': msg_count,
            'provider_count': prov_counts.get(u.id, 0),
            'persona_count': persona_counts.get(u.id, 0),
            'last_active': latest_msg_by_user.get(u.id),
        })

    return jsonify({'code': 200, 'data': result})


@admin_bp.route('/users/<int:user_id>/conversations', methods=['GET'])
@admin_required
def user_conversations(user_id):
    """某用户的对话列表及消息数。"""
    convs = Conversation.query.filter_by(user_id=user_id).order_by(
        Conversation.updated_at.desc()
    ).all()
    msg_counts = {}
    if convs:
        ids = [c.id for c in convs]
        msg_counts = dict(
            db.session.query(Message.conversation_id, func.count(Message.id))
            .filter(Message.conversation_id.in_(ids))
            .group_by(Message.conversation_id).all()
        )

    return jsonify({
        'code': 200,
        'data': [{
            'id': c.id,
            'title': c.title,
            'is_pinned': c.is_pinned,
            'message_count': msg_counts.get(c.id, 0),
            'persona_name': c.persona.name if c.persona else None,
            'persona_system_prompt': c.persona.system_prompt if c.persona else None,
            'persona_avatar': c.persona.avatar if c.persona else None,
            'persona_description': c.persona.description if c.persona else None,
            'persona_greeting': c.persona.greeting if c.persona else None,
            'background_image': c.background_image,
            'provider_id': c.provider_id,
            'created_at': c.created_at.isoformat() if c.created_at else None,
            'updated_at': c.updated_at.isoformat() if c.updated_at else None,
        } for c in convs]
    })


@admin_bp.route('/conversations/<int:conv_id>/messages', methods=['GET'])
@admin_required
def conversation_messages(conv_id):
    """某对话的消息记录（管理员监控用，正文截断避免过于冗长）。"""
    conv = Conversation.query.get(conv_id)
    if not conv:
        return jsonify({'code': 404, 'message': '对话不存在'}), 404

    msgs = Message.query.filter_by(conversation_id=conv_id).order_by(
        Message.created_at.asc()
    ).all()

    def _short(txt):
        if not txt:
            return ''
        txt = str(txt)
        return txt if len(txt) <= 200 else txt[:200] + '…'

    return jsonify({
        'code': 200,
        'data': {
            'conversation': {
                'id': conv.id,
                'title': conv.title,
                'user_id': conv.user_id,
                'username': conv.user.username if conv.user else None,
            },
            'messages': [{
                'id': m.id,
                'role': m.role,
                'content': _short(m.content),
                'image_url': m.image_url,
                'created_at': m.created_at.isoformat() if m.created_at else None,
            } for m in msgs]
        }
    })


@admin_bp.route('/conversations/<int:conv_id>/export', methods=['GET'])
@admin_required
def export_conversation(conv_id):
    """导出某对话全部消息（Markdown），每条标注发送者角色。"""
    conv = Conversation.query.get(conv_id)
    if not conv:
        return jsonify({'code': 404, 'message': '对话不存在'}), 404

    msgs = Message.query.filter_by(conversation_id=conv_id).order_by(
        Message.created_at.asc()
    ).all()

    role_labels = {'user': '用户', 'assistant': 'AI 助手', 'system': '系统'}
    lines = []
    lines.append(f'# 对话标题：{conv.title}')
    lines.append(f'# 角色：{conv.persona.name if conv.persona else "默认"}')
    lines.append(f'# 更新时间：{conv.updated_at.isoformat() if conv.updated_at else ""}')
    lines.append(f'# 消息数：{len(msgs)}')
    lines.append('')
    for m in msgs:
        label = role_labels.get(m.role, m.role)
        ts = m.created_at.strftime('%Y-%m-%d %H:%M:%S') if m.created_at else ''
        lines.append(f'## [{label}] {ts}')
        lines.append(m.content or '')
        if m.image_url:
            lines.append(f'[图片] {m.image_url}')
        lines.append('')

    filename = f'conversation_{conv_id}.md'
    resp = Response('\n'.join(lines), mimetype='text/markdown; charset=utf-8')
    resp.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return resp


@admin_bp.route('/marketplace', methods=['GET'])
@admin_required
def list_marketplace_cards():
    """管理员查看广场卡片列表（含真实创建者信息）"""
    from models import PersonaMarketplace
    page = int(request.args.get('page', 1))
    per_page = min(int(request.args.get('per_page', 20)), 50)

    pagination = PersonaMarketplace.query.order_by(PersonaMarketplace.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    items = []
    for p in pagination.items:
        d = p.to_dict(include_prompt=True)
        d['author_username'] = p.author.username if p.author else None
        d['author_email'] = p.author.email if p.author else None
        items.append(d)

    return jsonify({
        'code': 200,
        'data': {
            'items': items,
            'total': pagination.total,
            'page': page,
            'pages': pagination.pages,
        }
    })


@admin_bp.route('/marketplace/<int:pid>', methods=['DELETE'])
@admin_required
def delete_marketplace_card(pid):
    """管理员删除广场卡片"""
    from models import PersonaMarketplace
    persona = PersonaMarketplace.query.get(pid)
    if not persona:
        return jsonify({'code': 404, 'message': '卡片不存在'}), 404
    db.session.delete(persona)
    db.session.commit()
    return jsonify({'code': 200, 'message': '已删除'})