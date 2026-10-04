"""后台管理路由 - 监控所有用户与数据信息（管理员专用）

管理员账号独立于普通用户体系，由环境变量 ADMIN_USERNAME / ADMIN_PASSWORD 配置
（见 .env），通过 POST /api/admin/login 登录换取带 role=admin 声明的 JWT。
所有数据接口均要求该管理员令牌，避免越权访问。
"""
from flask import Blueprint, request, jsonify, current_app, Response
from flask_jwt_extended import jwt_required, get_jwt, create_access_token
from sqlalchemy import func, or_ as _or
from functools import wraps
from extensions import db
from services.rate_limit import limiter
from models import (
    User, Conversation, Message, ModelProvider, PersonaTemplate, local_now,
    PromptToolLog, ConversationMediaLog,
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

    # 今日新增（按服务器本地「现实世界」时间的零点切分）
    now = local_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
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
    """用户列表及各用户的数据量汇总（支持关键词搜索 + 后端分页）。

    query 参数：
      page     页码（默认 1）
      per_page 每页条数（默认 50，上限 200）
      q        关键词（匹配用户名 / 邮箱）
    """
    page = max(int(request.args.get('page', 1) or 1), 1)
    per_page = min(max(int(request.args.get('per_page', 50) or 50), 1), 200)
    keyword = (request.args.get('q') or '').strip()

    query = User.query
    if keyword:
        like = f'%{keyword}%'
        query = query.filter(_or(User.username.ilike(like), User.email.ilike(like)))
    query = query.order_by(User.created_at.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    users = pagination.items
    user_ids = [u.id for u in users]

    # 仅聚合当前页用户的数据量，避免全表扫描 + 逐用户触发 N+1
    conv_counts = {}
    msg_counts_by_user = {}
    prov_counts = {}
    persona_counts = {}
    if user_ids:
        conv_counts = dict(
            db.session.query(Conversation.user_id, func.count(Conversation.id))
            .filter(Conversation.deleted_at.is_(None), Conversation.user_id.in_(user_ids))
            .group_by(Conversation.user_id).all()
        )
        # 消息数：一次 JOIN 聚合到 user_id，避免逐用户/逐对话查询
        msg_counts_by_user = dict(
            db.session.query(Conversation.user_id, func.count(Message.id))
            .join(Message, Message.conversation_id == Conversation.id)
            .filter(Conversation.deleted_at.is_(None), Conversation.user_id.in_(user_ids))
            .group_by(Conversation.user_id).all()
        )
        prov_counts = dict(
            db.session.query(ModelProvider.user_id, func.count(ModelProvider.id))
            .filter(ModelProvider.user_id.in_(user_ids))
            .group_by(ModelProvider.user_id).all()
        )
        persona_counts = dict(
            db.session.query(PersonaTemplate.user_id, func.count(PersonaTemplate.id))
            .filter(PersonaTemplate.user_id.in_(user_ids))
            .group_by(PersonaTemplate.user_id).all()
        )

    # 每个用户最新一条消息时间 = 最近活跃（排除已软删除的对话）
    latest_msg_by_user = {}
    latest_conv_by_user = {}
    if user_ids:
        latest_rows = (
            db.session.query(Conversation.user_id, func.max(Message.created_at))
            .join(Message, Message.conversation_id == Conversation.id)
            .filter(Conversation.deleted_at.is_(None),
                    Conversation.user_id.in_(user_ids))
            .group_by(Conversation.user_id).all()
        )
        for uid, ts in latest_rows:
            latest_msg_by_user[uid] = ts

        # 没有消息但有对话（如刚建对话就离开）的用户，退化为对话更新时间
        latest_conv_by_user = dict(
            db.session.query(Conversation.user_id, func.max(Conversation.updated_at))
            .filter(Conversation.deleted_at.is_(None),
                    Conversation.user_id.in_(user_ids))
            .group_by(Conversation.user_id).all()
        )

    def _pick(u):
        ts = latest_msg_by_user.get(u.id)
        alt = latest_conv_by_user.get(u.id)
        for candidate in (ts, alt, u.created_at):
            if candidate:
                return candidate
        return None

    result = []
    for u in users:
        conv_count = conv_counts.get(u.id, 0)
        last = _pick(u)
        result.append({
            'id': u.id,
            'username': u.username,
            'email': u.email,
            'avatar': u.avatar,
            'ai_avatar': u.ai_avatar,
            'gender': u.gender,
            'is_active': u.is_active,
            'deleted_at': u.deleted_at.isoformat() if u.deleted_at else None,
            'created_at': u.created_at.isoformat() if u.created_at else None,
            'conversation_count': conv_count,
            'message_count': msg_counts_by_user.get(u.id, 0),
            'provider_count': prov_counts.get(u.id, 0),
            'persona_count': persona_counts.get(u.id, 0),
            'last_active': last.isoformat() if last else None,
        })

    return jsonify({
        'code': 200,
        'data': {
            'items': result,
            'total': pagination.total,
            'page': page,
            'pages': pagination.pages,
        }
    })


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

    def _persona_block(p):
        """抽取人设展示字段（AI 人设 / 用户人设共用）"""
        if not p:
            return {
                'persona_name': None, 'persona_avatar': None,
                'persona_description': None, 'persona_system_prompt': None,
                'persona_greeting': None,
            }
        return {
            'persona_name': p.name,
            'persona_avatar': p.avatar,
            'persona_description': p.description,
            'persona_system_prompt': p.system_prompt,
            'persona_greeting': p.greeting,
        }

    data = []
    for c in convs:
        row = {
            'id': c.id,
            'title': c.title,
            'is_pinned': c.is_pinned,
            'message_count': msg_counts.get(c.id, 0),
            'background_image': c.background_image,
            'background_cover': c.background_cover,
            'ai_avatar': c.ai_avatar,
            'user_avatar': c.user_avatar,
            'provider_id': c.provider_id,
            # 用户是否在自己的对话面板里删掉了这条对话（软删除即视为「已移除」）
            'deleted_at': c.deleted_at.isoformat() if c.deleted_at else None,
            'exists': c.deleted_at is None,
            'created_at': c.created_at.isoformat() if c.created_at else None,
            'updated_at': c.updated_at.isoformat() if c.updated_at else None,
        }
        row.update(_persona_block(c.persona))
        up = _persona_block(c.user_persona)
        row.update({
            'user_persona_name': up['persona_name'],
            'user_persona_avatar': up['persona_avatar'],
            'user_persona_description': up['persona_description'],
            'user_persona_system_prompt': up['persona_system_prompt'],
            'user_persona_greeting': up['persona_greeting'],
        })
        data.append(row)

    return jsonify({'code': 200, 'data': data})


@admin_bp.route('/conversations/<int:conv_id>', methods=['DELETE'])
@admin_required
def delete_conversation(conv_id):
    """管理员彻底删除对话（连同消息一起从数据库移除）。

    用户侧删除是软删除（写入 deleted_at，仍可在后台看到）；管理员删除为真删，
    确保数据库内不再残留，避免后台统计与用户面板不一致。
    """
    conv = Conversation.query.get(conv_id)
    if not conv:
        return jsonify({'code': 404, 'message': '对话不存在'}), 404

    title = conv.title
    owner_id = conv.user_id
    Message.query.filter_by(conversation_id=conv_id).delete(synchronize_session=False)
    db.session.delete(conv)
    db.session.commit()
    return jsonify({
        'code': 200,
        'message': '已删除',
        'data': {'id': conv_id, 'title': title, 'user_id': owner_id},
    })


@admin_bp.route('/conversations/batch-delete', methods=['POST'])
@admin_required
def batch_delete_conversations():
    """管理员批量彻底删除对话（连同消息）。

    用于后台清理「已移除」（用户软删除、消息已不存在）的对话残留。
    逐条真删并返回成功/跳过的明细，便于前端提示与刷新。
    """
    data = request.get_json() or {}
    ids = data.get('ids') or []
    if not isinstance(ids, list) or not ids:
        return jsonify({'code': 400, 'message': '请选择要删除的对话'}), 400
    # 上限保护：单次最多 200 条，避免超大请求拖垮数据库
    if len(ids) > 200:
        return jsonify({'code': 400, 'message': '单次最多删除 200 条'}), 400
    try:
        ids = [int(i) for i in ids]
    except (TypeError, ValueError):
        return jsonify({'code': 400, 'message': '参数不合法'}), 400

    deleted = []
    skipped = []
    for conv_id in ids:
        conv = Conversation.query.get(conv_id)
        if not conv:
            skipped.append({'id': conv_id, 'reason': '不存在'})
            continue
        Message.query.filter_by(conversation_id=conv_id).delete(synchronize_session=False)
        db.session.delete(conv)
        deleted.append({'id': conv_id, 'title': conv.title, 'user_id': conv.user_id})

    if deleted:
        db.session.commit()
    else:
        db.session.rollback()

    return jsonify({
        'code': 200,
        'message': f'已删除 {len(deleted)} 条' + (f'，跳过 {len(skipped)} 条' if skipped else ''),
        'data': {'deleted': deleted, 'skipped': skipped},
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

    # 管理员需要看到接近完整的对话记录，仅对超长单条做保护性截断
    MAX_LEN = 4000

    def _short(txt):
        if not txt:
            return ''
        txt = str(txt)
        return txt if len(txt) <= MAX_LEN else txt[:MAX_LEN] + '…（已截断）'

    return jsonify({
        'code': 200,
        'data': {
            'conversation': {
                'id': conv.id,
                'title': conv.title,
                'user_id': conv.user_id,
                'username': conv.user.username if conv.user else None,
                'persona_name': conv.persona.name if conv.persona else None,
                'deleted_at': conv.deleted_at.isoformat() if conv.deleted_at else None,
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
    """管理员查看广场卡片列表（含真实创建者信息）

    支持筛选：
      - keyword：按创建者用户名 / 邮箱模糊匹配
      - gender：人物卡自身性别（男 / 女 / 非二元）。
                「人物卡」字段在创建时可填「男 / 女 / 神秘 / 自定义」，
                由于「神秘」与「自定义 / 未填写」在内容上更接近「非二元」，
                「神秘」也归入「非二元」桶；传空或「神秘」则视为不过滤。
      - creator_gender：创建者（发布该卡片的用户）的性别，
                取值 男 / 女 / 神秘 / 空（不过滤）。
                注意：用户注册时的性别枚举是 男 / 女 / 神秘 三选一。
      - page / per_page：分页
    """
    from models import PersonaMarketplace
    from sqlalchemy import or_

    page = int(request.args.get('page', 1))
    per_page = min(int(request.args.get('per_page', 50)), 100)
    keyword = (request.args.get('keyword') or '').strip()
    gender = (request.args.get('gender') or '').strip()
    creator_gender = (request.args.get('creator_gender') or '').strip()

    query = PersonaMarketplace.query.join(User, User.id == PersonaMarketplace.user_id)

    if keyword:
        query = query.filter(
            _or(
                User.username.ilike(f'%{keyword}%'),
                User.email.ilike(f'%{keyword}%'),
            )
        )

    if gender:
        if gender in ('男', '女'):
            query = query.filter(PersonaMarketplace.gender == gender)
        elif gender == '非二元':
            # 自定义或未填写（含「神秘」）都归入非二元
            query = query.filter(
                or_(
                    PersonaMarketplace.gender.is_(None),
                    PersonaMarketplace.gender.notin_(['男', '女']),
                )
            )
        # gender == '神秘' / 空：不过滤

    if creator_gender in ('男', '女', '神秘'):
        query = query.filter(User.gender == creator_gender)
    # creator_gender == '' 视为不过滤

    pagination = query.order_by(PersonaMarketplace.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    items = []
    for p in pagination.items:
        d = p.to_dict(include_prompt=True)
        d['author_username'] = p.author.username if p.author else None
        d['author_email'] = p.author.email if p.author else None
        d['author_gender'] = p.author.gender if p.author else None
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


@admin_bp.route('/marketplace/<int:pid>', methods=['GET'])
@admin_required
def get_marketplace_card(pid):
    """管理员查看广场卡片完整详情（含 system_prompt、评论区真实用户名）。"""
    from models import PersonaMarketplace, MarketplaceComment

    persona = PersonaMarketplace.query.get(pid)
    if not persona:
        return jsonify({'code': 404, 'message': '卡片不存在'}), 404

    d = persona.to_dict(include_prompt=True)
    d['author_username'] = persona.author.username if persona.author else None
    d['author_email'] = persona.author.email if persona.author else None
    d['author_gender'] = persona.author.gender if persona.author else None

    # 评论（扁平结构，使用真实用户名）
    rows = MarketplaceComment.query.filter_by(persona_id=pid).order_by(
        MarketplaceComment.created_at.desc()
    ).all()

    def _pack(c):
        user = c.commenter
        return {
            'id': c.id,
            'content': c.content,
            'likes': c.likes,
            'username': user.username if user else None,
            'user_id': user.id if user else None,
            'created_at': c.created_at.isoformat() if c.created_at else None,
        }

    d['comments'] = [_pack(c) for c in rows]
    return jsonify({'code': 200, 'data': d})


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

@admin_bp.route('/prompt-tool-logs', methods=['GET'])
@admin_required
def list_prompt_tool_logs():
    """提示词工具使用记录：谁在何时用了、输入了什么、生成结果。

    支持按用户、分类筛选，便于定向排查某个用户或某类生成内容。
    """
    page = max(1, int(request.args.get('page', 1)))
    per_page = min(50, max(1, int(request.args.get('per_page', 20))))
    user_id = request.args.get('user_id', type=int)
    category = (request.args.get('category') or '').strip()

    q = PromptToolLog.query
    if user_id:
        q = q.filter(PromptToolLog.user_id == user_id)
    if category in ('character', 'image'):
        q = q.filter(PromptToolLog.category == category)

    pagination = q.order_by(PromptToolLog.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return jsonify({
        'code': 200,
        'data': {
            'items': [r.to_dict() for r in pagination.items],
            'total': pagination.total,
            'page': pagination.page,
            'pages': pagination.pages,
        }
    })


@admin_bp.route('/prompt-tool-logs/<int:log_id>', methods=['DELETE'])
@admin_required
def delete_prompt_tool_log(log_id):
    """管理员删除单条提示词工具使用记录。"""
    rec = PromptToolLog.query.get(log_id)
    if not rec:
        return jsonify({'code': 404, 'message': '记录不存在'}), 404
    db.session.delete(rec)
    db.session.commit()
    return jsonify({'code': 200, 'message': '已删除 1 条', 'deleted': 1})


@admin_bp.route('/prompt-tool-logs/batch-delete', methods=['POST'])
@admin_required
def batch_delete_prompt_tool_logs():
    """管理员批量删除提示词工具使用记录。"""
    data = request.get_json() or {}
    ids = data.get('ids') or []
    if not isinstance(ids, list) or not ids:
        return jsonify({'code': 400, 'message': '请选择要删除的记录'}), 400
    if len(ids) > 200:
        return jsonify({'code': 400, 'message': '单次最多删除 200 条'}), 400
    try:
        ids = [int(i) for i in ids]
    except (TypeError, ValueError):
        return jsonify({'code': 400, 'message': '参数不合法'}), 400

    deleted, skipped = [], []
    for log_id in ids:
        rec = PromptToolLog.query.get(log_id)
        if not rec:
            skipped.append({'id': log_id, 'reason': '不存在'})
            continue
        db.session.delete(rec)
        deleted.append({'id': log_id})

    if deleted:
        db.session.commit()
    else:
        db.session.rollback()

    return jsonify({
        'code': 200,
        'message': f'已删除 {len(deleted)} 条，跳过 {len(skipped)} 条',
        'deleted': len(deleted),
        'skipped': len(skipped),
    })


MEDIA_LOG_TYPES = (
    'background', 'ai_avatar', 'user_avatar',           # 对话级设置
    'profile_background', 'profile_avatar', 'profile_ai_avatar',  # 系统设置
    'upload',                                            # 聊天发送的图片等上传
)


@admin_bp.route('/conversation-media-logs', methods=['GET'])
@admin_required
def list_conversation_media_logs():
    """对话素材记录：背景图 / 头像（对话级 + 系统级）/ 上传图片，按用户、类型筛选。"""
    page = max(1, int(request.args.get('page', 1)))
    per_page = min(50, max(1, int(request.args.get('per_page', 20))))
    user_id = request.args.get('user_id', type=int)
    media_type = (request.args.get('media_type') or '').strip()

    q = ConversationMediaLog.query
    if user_id:
        q = q.filter(ConversationMediaLog.user_id == user_id)
    if media_type in MEDIA_LOG_TYPES:
        q = q.filter(ConversationMediaLog.media_type == media_type)

    pagination = q.order_by(ConversationMediaLog.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return jsonify({
        'code': 200,
        'data': {
            'items': [r.to_dict() for r in pagination.items],
            'total': pagination.total,
            'page': pagination.page,
            'pages': pagination.pages,
        }
    })


@admin_bp.route('/conversation-media-logs/<int:log_id>', methods=['DELETE'])
@admin_required
def delete_conversation_media_log(log_id):
    """管理员删除单条对话素材历史记录。

    只删审计记录本身，不动会话上仍在生效的素材（背景图/头像）——
    那是另一套数据，误删会让用户界面上的设置凭空消失。
    """
    rec = ConversationMediaLog.query.get(log_id)
    if not rec:
        return jsonify({'code': 404, 'message': '记录不存在'}), 404
    db.session.delete(rec)
    db.session.commit()
    return jsonify({'code': 200, 'message': '已删除 1 条', 'deleted': 1})


@admin_bp.route('/conversation-media-logs/batch-delete', methods=['POST'])
@admin_required
def batch_delete_media_logs():
    """管理员批量删除对话素材历史记录（由管理员决定是否清理）。"""
    data = request.get_json() or {}
    ids = data.get('ids') or []
    if not isinstance(ids, list) or not ids:
        return jsonify({'code': 400, 'message': '请选择要删除的记录'}), 400
    if len(ids) > 200:
        return jsonify({'code': 400, 'message': '单次最多删除 200 条'}), 400
    try:
        ids = [int(i) for i in ids]
    except (TypeError, ValueError):
        return jsonify({'code': 400, 'message': '参数不合法'}), 400

    deleted = []
    skipped = []
    for log_id in ids:
        rec = ConversationMediaLog.query.get(log_id)
        if not rec:
            skipped.append({'id': log_id, 'reason': '不存在'})
            continue
        db.session.delete(rec)
        deleted.append({'id': log_id})

    if deleted:
        db.session.commit()
    else:
        db.session.rollback()

    return jsonify({
        'code': 200,
        'message': f'已删除 {len(deleted)} 条，跳过 {len(skipped)} 条',
        'deleted': len(deleted),
        'skipped': len(skipped),
    })


@admin_bp.route('/marketplace/<int:pid>', methods=['PUT'])
@admin_required
def update_marketplace_card_admin(pid):
    """管理员编辑任意广场卡片（不受作者归属限制）。"""
    from models import PersonaMarketplace
    from routes.marketplace import (
        PUB_NAME_MAX, PUB_DESC_MIN, PUB_DESC_MAX,
        PUB_PROMPT_MIN, PUB_PROMPT_MAX, PUB_GREETING_MAX,
    )
    persona = PersonaMarketplace.query.get(pid)
    if not persona:
        return jsonify({'code': 404, 'message': '卡片不存在'}), 404

    data = request.get_json() or {}
    name = data.get('name')
    description = data.get('description')
    system_prompt = data.get('system_prompt')
    greeting = data.get('greeting')
    avatar = data.get('avatar')
    gender = data.get('gender')

    if name is not None:
        name = name.strip()
        if not name or len(name) > PUB_NAME_MAX:
            return jsonify({'code': 400, 'message': f'名称需 1-{PUB_NAME_MAX} 字'}), 400
        persona.name = name
    if description is not None:
        description = description.strip()
        if len(description) < PUB_DESC_MIN or len(description) > PUB_DESC_MAX:
            return jsonify({'code': 400, 'message': f'描述需 {PUB_DESC_MIN}-{PUB_DESC_MAX} 字'}), 400
        persona.description = description
    if system_prompt is not None:
        system_prompt = system_prompt.strip()
        if len(system_prompt) < PUB_PROMPT_MIN or len(system_prompt) > PUB_PROMPT_MAX:
            return jsonify({'code': 400, 'message': f'人设提示词需 {PUB_PROMPT_MIN}-{PUB_PROMPT_MAX} 字'}), 400
        persona.system_prompt = system_prompt
    if greeting is not None:
        greeting = greeting.strip()
        if not greeting or len(greeting) > PUB_GREETING_MAX:
            return jsonify({'code': 400, 'message': f'开场白需 1-{PUB_GREETING_MAX} 字'}), 400
        persona.greeting = greeting
    if avatar is not None and avatar.strip():
        persona.avatar = avatar.strip()
    if gender is not None:
        gender = gender.strip()
        if len(gender) > 20:
            return jsonify({'code': 400, 'message': '性别内容过长（最多20字）'}), 400
        persona.gender = gender or None

    db.session.commit()
    return jsonify({'code': 200, 'message': '已保存', 'data': persona.to_dict()})
