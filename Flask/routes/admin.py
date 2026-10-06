"""后台管理路由 - 监控所有用户与数据信息（管理员专用）

管理员账号独立于普通用户体系，由环境变量 ADMIN_USERNAME / ADMIN_PASSWORD 配置
（见 .env），通过 POST /api/admin/login 登录换取带 role=admin 声明的 JWT。
所有数据接口均要求该管理员令牌，避免越权访问。
"""
from flask import Blueprint, request, jsonify, current_app, Response
from flask_jwt_extended import (
    jwt_required, get_jwt, create_access_token, create_refresh_token,
)
from sqlalchemy import case, func, or_ as _or
from sqlalchemy.orm import joinedload, selectinload
from functools import wraps
from datetime import datetime, time, timedelta
from extensions import db
from services.rate_limit import limiter
from models import (
    AiUsageLog, Conversation, ConversationMediaLog, DailyCheckIn, ImageUsage,
    Message, ModelProvider, PersonaTemplate, PromptToolLog, User, UserSettings,
    WorldBookEntry, iso_time, local_now,
)

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')

# 管理员令牌有效期：和普通用户一个思路 —— 短期 access + 长期 refresh，
# 前端在 access 过期时静默续期，所以「打开后台不用重新登录」。
# 后台不常开，access 直接给 7 天，refresh 给 30 天（与用户 refresh 一致）。
ADMIN_TOKEN_DAYS = 7
ADMIN_REFRESH_DAYS = 30


def _arg_int(name, default, *, minimum=None, maximum=None):
    """读取并限制整数 query 参数，非法值回落到默认值。"""
    try:
        value = int(request.args.get(name, default))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(value, minimum)
    if maximum is not None:
        value = min(value, maximum)
    return value


def _arg_values(name):
    return [v.strip() for v in (request.args.get(name) or '').split(',') if v.strip()]


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

    # 管理员后台不常开：access 给 7 天，另外发一个 30 天的 refresh，
    # 前端在 access 过期/临近过期时静默换新 —— 与普通用户的长期免登录一致。
    token = create_access_token(
        identity='admin',
        additional_claims={'role': 'admin'},
        expires_delta=timedelta(days=ADMIN_TOKEN_DAYS),
    )
    refresh = create_refresh_token(
        identity='admin',
        additional_claims={'role': 'admin'},
        expires_delta=timedelta(days=ADMIN_REFRESH_DAYS),
    )
    return jsonify({
        'code': 200,
        'message': '登录成功',
        'data': {
            'access_token': token,
            'refresh_token': refresh,
            'expires_in_days': ADMIN_TOKEN_DAYS,
            'username': username,
        }
    })


@admin_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def admin_refresh():
    """用 30 天的 refresh 换新的 access（管理员长期免登录）。"""
    if get_jwt().get('role') != 'admin':
        return jsonify({'code': 403, 'message': '无权限访问'}), 403
    token = create_access_token(
        identity='admin',
        additional_claims={'role': 'admin'},
        expires_delta=timedelta(days=ADMIN_TOKEN_DAYS),
    )
    return jsonify({
        'code': 200,
        'message': '已续期',
        'data': {'access_token': token, 'expires_in_days': ADMIN_TOKEN_DAYS},
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
    """用户列表：服务端筛选、排序、分页和用量汇总。"""
    page = _arg_int('page', 1, minimum=1)
    per_page = _arg_int('per_page', 50, minimum=1, maximum=100)
    keyword = (request.args.get('q') or '').strip()
    genders = _arg_values('gender')
    statuses = _arg_values('status')
    has_config = _arg_values('has_config')
    activity = (request.args.get('activity') or '').strip()
    sort = (request.args.get('sort') or 'created_at').strip()
    order = (request.args.get('order') or 'desc').strip().lower()

    conv_count_sq = (
        db.session.query(func.count(Conversation.id))
        .filter(Conversation.user_id == User.id,
                Conversation.deleted_at.is_(None))
        .correlate(User)
        .scalar_subquery()
    )
    msg_count_sq = (
        db.session.query(func.count(Message.id))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .filter(Conversation.user_id == User.id,
                Conversation.deleted_at.is_(None))
        .correlate(User)
        .scalar_subquery()
    )
    provider_count_sq = (
        db.session.query(func.count(ModelProvider.id))
        .filter(ModelProvider.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )
    persona_count_sq = (
        db.session.query(func.count(PersonaTemplate.id))
        .filter(PersonaTemplate.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )
    token_sum_sq = (
        db.session.query(func.coalesce(func.sum(
            func.coalesce(Message.prompt_tokens, 0)
            + func.coalesce(Message.completion_tokens, 0)
        ), 0))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .filter(Conversation.user_id == User.id,
                Conversation.deleted_at.is_(None))
        .correlate(User)
        .scalar_subquery()
    )
    latest_msg_sq = (
        db.session.query(func.max(Message.created_at))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .filter(Conversation.user_id == User.id,
                Conversation.deleted_at.is_(None))
        .correlate(User)
        .scalar_subquery()
    )
    latest_conv_sq = (
        db.session.query(func.max(Conversation.updated_at))
        .filter(Conversation.user_id == User.id,
                Conversation.deleted_at.is_(None))
        .correlate(User)
        .scalar_subquery()
    )
    last_active_expr = func.coalesce(
        User.last_chat_at, latest_msg_sq, latest_conv_sq,
        User.last_login_at, User.created_at,
    )

    query = User.query
    if keyword:
        like = f'%{keyword}%'
        query = query.filter(_or(User.username.ilike(like), User.email.ilike(like)))
    if genders:
        query = query.filter(User.gender.in_(genders))
    if statuses:
        status_conditions = []
        if 'active' in statuses:
            status_conditions.append((User.deleted_at.is_(None)) & User.is_active.is_(True))
        if 'disabled' in statuses:
            status_conditions.append((User.deleted_at.is_(None)) & User.is_active.is_(False))
        if 'deleted' in statuses:
            status_conditions.append(User.deleted_at.is_not(None))
        if status_conditions:
            query = query.filter(_or(*status_conditions))
    if 'provider' in has_config:
        query = query.filter(provider_count_sq > 0)
    if 'persona' in has_config:
        query = query.filter(persona_count_sq > 0)
    if 'avatar' in has_config:
        query = query.filter(User.avatar.is_not(None), User.avatar != '')

    now = local_now()
    today_start = datetime.combine(now.date(), time.min)
    if activity == 'has_conversation':
        query = query.filter(conv_count_sq > 0)
    elif activity == 'has_message':
        query = query.filter(msg_count_sq > 0)
    elif activity == 'no_conversation':
        query = query.filter(conv_count_sq == 0)
    elif activity == 'today':
        query = query.filter(last_active_expr >= today_start)
    elif activity == 'week':
        query = query.filter(last_active_expr >= today_start - timedelta(days=7))

    sort_columns = {
        'created_at': User.created_at,
        'last_active': last_active_expr,
        'message_count': msg_count_sq,
        'conversation_count': conv_count_sq,
        'total_tokens': token_sum_sq,
        'username': User.username,
    }
    sort_column = sort_columns.get(sort, User.created_at)
    if order == 'asc':
        query = query.order_by(sort_column.asc(), User.id.asc())
    else:
        query = query.order_by(sort_column.desc(), User.id.desc())

    pagination = query.add_columns(
        conv_count_sq.label('conversation_count'),
        msg_count_sq.label('message_count'),
        provider_count_sq.label('provider_count'),
        persona_count_sq.label('persona_count'),
        last_active_expr.label('last_active'),
        token_sum_sq.label('total_tokens'),
    ).paginate(page=page, per_page=per_page, error_out=False)

    result = []
    for row in pagination.items:
        u = row[0]
        result.append({
            'id': u.id,
            'username': u.username,
            'email': u.email,
            'avatar': u.avatar,
            'ai_avatar': u.ai_avatar,
            'gender': u.gender,
            'is_active': u.is_active,
            'deleted_at': iso_time(u.deleted_at),
            'created_at': iso_time(u.created_at),
            'last_login_at': iso_time(u.last_login_at),
            'last_chat_at': iso_time(u.last_chat_at),
            'conversation_count': row.conversation_count or 0,
            'message_count': row.message_count or 0,
            'provider_count': row.provider_count or 0,
            'persona_count': row.persona_count or 0,
            'total_tokens': int(row.total_tokens or 0),
            'last_active': iso_time(row.last_active),
        })

    return jsonify({
        'code': 200,
        'data': {
            'items': result,
            'total': pagination.total,
            'page': page,
            'pages': pagination.pages,
            'sort': sort,
            'order': order,
        }
    })


@admin_bp.route('/users/<int:user_id>/conversations', methods=['GET'])
@admin_required
def user_conversations(user_id):
    """某用户的对话列表：服务端分页、筛选和排序。"""
    if not User.query.get(user_id):
        return jsonify({'code': 404, 'message': '用户不存在'}), 404

    page = _arg_int('page', 1, minimum=1)
    per_page = _arg_int('per_page', 20, minimum=1, maximum=100)
    keyword = (request.args.get('q') or '').strip()
    status = (request.args.get('status') or 'all').strip()
    sort = (request.args.get('sort') or 'updated_at').strip()
    order = (request.args.get('order') or 'desc').strip().lower()

    msg_count_sq = (
        db.session.query(func.count(Message.id))
        .filter(Message.conversation_id == Conversation.id)
        .correlate(Conversation)
        .scalar_subquery()
    )
    token_sum_sq = (
        db.session.query(func.coalesce(func.sum(
            func.coalesce(Message.prompt_tokens, 0)
            + func.coalesce(Message.completion_tokens, 0)
        ), 0))
        .filter(Message.conversation_id == Conversation.id)
        .correlate(Conversation)
        .scalar_subquery()
    )

    query = Conversation.query.options(
        joinedload(Conversation.persona),
        joinedload(Conversation.user_persona),
    ).filter(Conversation.user_id == user_id)
    if keyword:
        query = query.filter(Conversation.title.ilike(f'%{keyword}%'))
    if status == 'active':
        query = query.filter(Conversation.deleted_at.is_(None))
    elif status == 'removed':
        query = query.filter(Conversation.deleted_at.is_not(None))

    sort_columns = {
        'updated_at': Conversation.updated_at,
        'created_at': Conversation.created_at,
        'message_count': msg_count_sq,
        'total_tokens': token_sum_sq,
        'title': Conversation.title,
    }
    sort_column = sort_columns.get(sort, Conversation.updated_at)
    if order == 'asc':
        query = query.order_by(sort_column.asc(), Conversation.id.asc())
    else:
        query = query.order_by(sort_column.desc(), Conversation.id.desc())

    pagination = query.add_columns(
        msg_count_sq.label('message_count'),
        token_sum_sq.label('total_tokens'),
    ).paginate(page=page, per_page=per_page, error_out=False)

    def _persona_block(p):
        """抽取人设展示字段，玩家设定单独返回 user_prompt。"""
        if not p:
            return {
                'persona_name': None, 'persona_avatar': None,
                'persona_description': None, 'persona_system_prompt': None,
                'persona_user_prompt': None, 'persona_greeting': None,
                'persona_type': None,
            }
        return {
            'persona_name': p.name,
            'persona_avatar': p.avatar,
            'persona_description': p.description,
            'persona_system_prompt': p.system_prompt,
            'persona_user_prompt': p.user_prompt,
            'persona_greeting': p.greeting,
            'persona_type': p.persona_type or 'ai',
        }

    data = []
    for row in pagination.items:
        c = row[0]
        item = {
            'id': c.id,
            'title': c.title,
            'is_pinned': c.is_pinned,
            'message_count': row.message_count or 0,
            'total_tokens': int(row.total_tokens or 0),
            'background_image': c.background_image,
            'background_cover': c.background_cover,
            'ai_avatar': c.ai_avatar,
            'user_avatar': c.user_avatar,
            'provider_id': c.provider_id,
            'deleted_at': iso_time(c.deleted_at),
            'exists': c.deleted_at is None,
            'created_at': iso_time(c.created_at),
            'updated_at': iso_time(c.updated_at),
        }
        item.update(_persona_block(c.persona))
        legacy = _persona_block(c.user_persona)
        item.update({
            'user_persona_name': legacy['persona_name'],
            'user_persona_avatar': legacy['persona_avatar'],
            'user_persona_description': legacy['persona_description'],
            'user_persona_system_prompt': legacy['persona_system_prompt'],
            'user_persona_user_prompt': legacy['persona_user_prompt'],
            'user_persona_greeting': legacy['persona_greeting'],
        })
        data.append(item)

    return jsonify({
        'code': 200,
        'data': {
            'items': data,
            'total': pagination.total,
            'page': page,
            'pages': pagination.pages,
            'sort': sort,
            'order': order,
        }
    })


@admin_bp.route('/users/<int:user_id>/summary', methods=['GET'])
@admin_required
def user_summary(user_id):
    """用户详情概览，包含账号、人设、模型和 Token 汇总。"""
    user = User.query.get(user_id)
    if not user:
        return jsonify({'code': 404, 'message': '用户不存在'}), 404

    conv_count, msg_count, prompt_total, completion_total, cached_total = (
        db.session.query(
            func.count(func.distinct(Conversation.id)),
            func.count(Message.id),
            func.coalesce(func.sum(Message.prompt_tokens), 0),
            func.coalesce(func.sum(Message.completion_tokens), 0),
            func.coalesce(func.sum(Message.cached_tokens), 0),
        )
        .select_from(Conversation)
        .outerjoin(Message, Message.conversation_id == Conversation.id)
        .filter(Conversation.user_id == user_id)
        .one()
    )
    last_message_at = (
        db.session.query(func.max(Message.created_at))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .filter(Conversation.user_id == user_id)
        .scalar()
    )
    image_usage = ImageUsage.query.filter_by(user_id=user_id).first()
    last_checkin = DailyCheckIn.query.filter_by(user_id=user_id).order_by(
        DailyCheckIn.checkin_time.desc()
    ).first()

    return jsonify({
        'code': 200,
        'data': {
            **user.to_dict(),
            'deleted_at': iso_time(user.deleted_at),
            'conversation_count': int(conv_count or 0),
            'message_count': int(msg_count or 0),
            'provider_count': ModelProvider.query.filter_by(user_id=user_id).count(),
            'persona_count': PersonaTemplate.query.filter_by(user_id=user_id).count(),
            'prompt_tokens': int(prompt_total or 0),
            'completion_tokens': int(completion_total or 0),
            'cached_tokens': int(cached_total or 0),
            'total_tokens': int((prompt_total or 0) + (completion_total or 0)),
            'last_message_at': iso_time(last_message_at),
            'free_images_remaining': image_usage.free_count if image_usage else None,
            'last_checkin_at': iso_time(last_checkin.checkin_time) if last_checkin else None,
        }
    })


@admin_bp.route('/users/<int:user_id>/personas', methods=['GET'])
@admin_required
def user_personas(user_id):
    """用户的人物卡完整列表，包含 AI 提示词与玩家设定。"""
    if not User.query.get(user_id):
        return jsonify({'code': 404, 'message': '用户不存在'}), 404
    worldbook_counts = dict(
        db.session.query(WorldBookEntry.persona_id, func.count(WorldBookEntry.id))
        .filter(WorldBookEntry.user_id == user_id)
        .group_by(WorldBookEntry.persona_id).all()
    )
    rows = PersonaTemplate.query.filter_by(user_id=user_id).order_by(
        PersonaTemplate.is_default.desc(),
        PersonaTemplate.updated_at.desc(),
        PersonaTemplate.id.desc(),
    ).all()
    return jsonify({
        'code': 200,
        'data': {
            'items': [{
                **p.to_dict(),
                'created_at': iso_time(p.created_at),
                'updated_at': iso_time(p.updated_at),
                'worldbook_count': worldbook_counts.get(p.id, 0),
            } for p in rows]
        }
    })


@admin_bp.route('/users/<int:user_id>/providers', methods=['GET'])
@admin_required
def user_providers(user_id):
    """用户模型配置列表；API Key 仅返回掩码。"""
    if not User.query.get(user_id):
        return jsonify({'code': 404, 'message': '用户不存在'}), 404
    rows = ModelProvider.query.options(
        selectinload(ModelProvider.models)
    ).filter_by(user_id=user_id).order_by(
        ModelProvider.is_default.desc(),
        ModelProvider.created_at.desc(),
        ModelProvider.id.desc(),
    ).all()
    return jsonify({
        'code': 200,
        'data': {'items': [p.to_dict(include_models=True) for p in rows]}
    })


@admin_bp.route('/users/<int:user_id>/settings', methods=['GET'])
@admin_required
def user_settings(user_id):
    """用户设置只读视图。"""
    user = User.query.get(user_id)
    if not user:
        return jsonify({'code': 404, 'message': '用户不存在'}), 404
    settings = UserSettings.query.filter_by(user_id=user_id).first()
    return jsonify({
        'code': 200,
        'data': settings.to_dict() if settings else UserSettings().to_dict()
    })


@admin_bp.route('/users/<int:user_id>/usage', methods=['GET'])
@admin_required
def user_usage(user_id):
    """按天、模型和对话聚合用户 Token 用量。"""
    if not User.query.get(user_id):
        return jsonify({'code': 404, 'message': '用户不存在'}), 404
    days = _arg_int('days', 30, minimum=1, maximum=3650)
    cutoff = local_now() - timedelta(days=days)
    prompt_total, completion_total, cached_total, message_count = (
        db.session.query(
            func.coalesce(func.sum(Message.prompt_tokens), 0),
            func.coalesce(func.sum(Message.completion_tokens), 0),
            func.coalesce(func.sum(Message.cached_tokens), 0),
            func.count(Message.id),
        )
        .join(Conversation, Conversation.id == Message.conversation_id)
        .filter(Conversation.user_id == user_id, Message.created_at >= cutoff)
        .one()
    )
    daily_rows = (
        db.session.query(
            func.date(Message.created_at).label('usage_date'),
            func.coalesce(func.sum(Message.prompt_tokens), 0),
            func.coalesce(func.sum(Message.completion_tokens), 0),
            func.coalesce(func.sum(Message.cached_tokens), 0),
            func.count(Message.id),
        )
        .join(Conversation, Conversation.id == Message.conversation_id)
        .filter(Conversation.user_id == user_id, Message.created_at >= cutoff)
        .group_by(func.date(Message.created_at))
        .order_by(func.date(Message.created_at).desc())
        .all()
    )
    model_rows = (
        db.session.query(
            Message.model,
            func.coalesce(func.sum(Message.prompt_tokens), 0),
            func.coalesce(func.sum(Message.completion_tokens), 0),
            func.coalesce(func.sum(Message.cached_tokens), 0),
            func.count(Message.id),
        )
        .join(Conversation, Conversation.id == Message.conversation_id)
        .filter(Conversation.user_id == user_id, Message.created_at >= cutoff)
        .group_by(Message.model)
        .order_by(func.coalesce(func.sum(Message.prompt_tokens), 0).desc())
        .all()
    )
    conversation_rows = (
        db.session.query(
            Conversation.id,
            Conversation.title,
            func.coalesce(func.sum(Message.prompt_tokens), 0),
            func.coalesce(func.sum(Message.completion_tokens), 0),
            func.coalesce(func.sum(Message.cached_tokens), 0),
            func.count(Message.id),
        )
        .join(Message, Message.conversation_id == Conversation.id)
        .filter(Conversation.user_id == user_id, Message.created_at >= cutoff)
        .group_by(Conversation.id, Conversation.title)
        .order_by(func.coalesce(func.sum(Message.prompt_tokens), 0).desc())
        .limit(50)
        .all()
    )
    usage_request_count, free_tokens = (
        db.session.query(
            func.count(AiUsageLog.id),
            func.coalesce(func.sum(case(
                (AiUsageLog.is_free_api.is_(True), AiUsageLog.total_tokens),
                else_=0,
            )), 0),
        )
        .filter(AiUsageLog.user_id == user_id, AiUsageLog.created_at >= cutoff)
        .one()
    )
    return jsonify({
        'code': 200,
        'data': {
            'days': days,
            'totals': {
                'message_count': int(message_count or 0),
                'prompt_tokens': int(prompt_total or 0),
                'completion_tokens': int(completion_total or 0),
                'cached_tokens': int(cached_total or 0),
                'total_tokens': int((prompt_total or 0) + (completion_total or 0)),
                'request_count': int(usage_request_count or 0),
                'free_api_tokens': int(free_tokens or 0),
            },
            'daily': [{
                'date': row[0],
                'prompt_tokens': int(row[1] or 0),
                'completion_tokens': int(row[2] or 0),
                'cached_tokens': int(row[3] or 0),
                'total_tokens': int((row[1] or 0) + (row[2] or 0)),
                'message_count': int(row[4] or 0),
            } for row in daily_rows],
            'by_model': [{
                'model': row[0] or 'unknown',
                'prompt_tokens': int(row[1] or 0),
                'completion_tokens': int(row[2] or 0),
                'cached_tokens': int(row[3] or 0),
                'total_tokens': int((row[1] or 0) + (row[2] or 0)),
                'message_count': int(row[4] or 0),
            } for row in model_rows],
            'by_conversation': [{
                'conversation_id': row[0],
                'title': row[1],
                'prompt_tokens': int(row[2] or 0),
                'completion_tokens': int(row[3] or 0),
                'cached_tokens': int(row[4] or 0),
                'total_tokens': int((row[2] or 0) + (row[3] or 0)),
                'message_count': int(row[5] or 0),
            } for row in conversation_rows],
        }
    })


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


@admin_bp.route('/personas/batch-delete', methods=['POST'])
@admin_required
def batch_delete_personas():
    """管理员批量彻底删除人物卡。

    用于后台清理用户软删除后残留的人物卡。
    逐条真删并返回成功/跳过的明细。
    """
    data = request.get_json() or {}
    ids = data.get('ids') or []
    if not isinstance(ids, list) or not ids:
        return jsonify({'code': 400, 'message': '请选择要删除的人物卡'}), 400
    if len(ids) > 200:
        return jsonify({'code': 400, 'message': '单次最多删除 200 个'}), 400
    try:
        ids = [int(i) for i in ids]
    except (TypeError, ValueError):
        return jsonify({'code': 400, 'message': '参数不合法'}), 400

    deleted = []
    skipped = []
    for persona_id in ids:
        persona = PersonaTemplate.query.get(persona_id)
        if not persona:
            skipped.append({'id': persona_id, 'reason': '不存在'})
            continue
        # 解除对话对该人物卡的引用，避免外键残留
        Conversation.query.filter_by(persona_id=persona_id).update(
            {Conversation.persona_id: None}, synchronize_session=False
        )
        Conversation.query.filter_by(user_persona_id=persona_id).update(
            {Conversation.user_persona_id: None}, synchronize_session=False
        )
        # 同时删除关联的世界书条目
        WorldBookEntry.query.filter_by(persona_id=persona_id).delete(synchronize_session=False)
        db.session.delete(persona)
        deleted.append({'id': persona_id, 'name': persona.name, 'user_id': persona.user_id})

    if deleted:
        db.session.commit()
    else:
        db.session.rollback()

    return jsonify({
        'code': 200,
        'message': f'已删除 {len(deleted)} 个' + (f'，跳过 {len(skipped)} 个' if skipped else ''),
        'data': {'deleted': deleted, 'skipped': skipped},
    })


@admin_bp.route('/conversations/<int:conv_id>/messages', methods=['GET'])
@admin_required
def conversation_messages(conv_id):
    """某对话的消息记录：游标分页，默认返回最新的 N 条。"""
    conv = Conversation.query.options(
        joinedload(Conversation.user), joinedload(Conversation.persona)
    ).filter(Conversation.id == conv_id).first()
    if not conv:
        return jsonify({'code': 404, 'message': '对话不存在'}), 404

    limit = _arg_int('limit', 100, minimum=1, maximum=500)
    before_id = request.args.get('before_id', type=int)
    role = (request.args.get('role') or '').strip()
    keyword = (request.args.get('q') or '').strip()

    base_query = Message.query.filter(Message.conversation_id == conv_id)
    if role in ('user', 'assistant', 'system'):
        base_query = base_query.filter(Message.role == role)
    if keyword:
        base_query = base_query.filter(Message.content.ilike(f'%{keyword}%'))

    total = base_query.count()
    query = base_query
    if before_id:
        query = query.filter(Message.id < before_id)
    rows = query.order_by(Message.id.desc()).limit(limit + 1).all()
    has_more = len(rows) > limit
    rows = list(reversed(rows[:limit]))

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
                'persona_user_prompt': conv.persona.user_prompt if conv.persona else None,
                'deleted_at': iso_time(conv.deleted_at),
            },
            'messages': [{
                'id': m.id,
                'role': m.role,
                'content': _short(m.content),
                'reasoning_content': _short(m.reasoning_content),
                'image_url': m.image_url,
                'model': m.model,
                'prompt_tokens': m.prompt_tokens,
                'completion_tokens': m.completion_tokens,
                'cached_tokens': m.cached_tokens,
                'total_tokens': ((m.prompt_tokens or 0) + (m.completion_tokens or 0)
                                 or None),
                'created_at': iso_time(m.created_at),
            } for m in rows],
            'total': total,
            'has_more': has_more,
            'next_before_id': rows[0].id if rows and has_more else None,
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
    lines.append(f'# 更新时间：{iso_time(conv.updated_at) or ""}')
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
            'created_at': iso_time(c.created_at),
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
