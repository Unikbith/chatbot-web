"""用户反馈路由 - 帮助与反馈"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models import Feedback, SupportThread, SupportMessage, User, local_now
from functools import wraps
from flask_jwt_extended import get_jwt

feedback_bp = Blueprint('feedback', __name__, url_prefix='/api/feedback')


def admin_required(fn):
    """要求携带 role=admin 的管理员令牌。"""
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        if get_jwt().get('role') != 'admin':
            return jsonify({'code': 403, 'message': '无权限访问'}), 403
        return fn(*args, **kwargs)
    return wrapper


@feedback_bp.route('', methods=['POST'])
@jwt_required()
def submit_feedback():
    """提交用户反馈（需登录）"""
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    content = (data.get('content') or '').strip()
    allow_email_contact = bool(data.get('allow_email_contact'))
    contact_email = (data.get('contact_email') or '').strip()

    if not content:
        return jsonify({'code': 400, 'message': '请填写反馈内容'}), 400
    if len(content) > 2000:
        return jsonify({'code': 400, 'message': '反馈内容最多 2000 字'}), 400
    if allow_email_contact and not contact_email:
        return jsonify({'code': 400, 'message': '请选择允许邮件联系后填写联系邮箱'}), 400
    if contact_email and len(contact_email) > 120:
        return jsonify({'code': 400, 'message': '邮箱长度超出限制'}), 400

    feedback = Feedback(
        user_id=user_id,
        content=content,
        allow_email_contact=allow_email_contact,
        contact_email=contact_email or None,
    )
    db.session.add(feedback)
    db.session.commit()
    return jsonify({'code': 200, 'message': '反馈已提交，感谢你的建议', 'data': feedback.to_dict()})


@feedback_bp.route('', methods=['GET'])
@admin_required
def list_feedback():
    """管理员查看反馈列表"""
    page = int(request.args.get('page', 1))
    per_page = min(int(request.args.get('per_page', 20)), 100)

    pagination = Feedback.query.order_by(Feedback.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    items = [f.to_dict(include_user=True) for f in pagination.items]

    return jsonify({
        'code': 200,
        'data': {
            'items': items,
            'total': pagination.total,
            'page': page,
            'pages': pagination.pages,
        }
    })


def _get_or_create_support_thread(user_id):
    thread = SupportThread.query.filter_by(user_id=user_id).first()
    if thread:
        return thread
    thread = SupportThread(user_id=user_id)
    db.session.add(thread)
    db.session.commit()
    return thread


def _anonymous_identity(user_id):
    from routes.marketplace import _pseudonym_for, _identicon_seed_for
    return {
        'anonymous_id': _pseudonym_for(int(user_id), 0),
        'avatar_seed': _identicon_seed_for(int(user_id), 0),
    }


@feedback_bp.route('/support', methods=['GET'])
@jwt_required()
def support_thread():
    """用户侧匿名反馈会话；只显示匿名身份和回复时间。"""
    user_id = int(get_jwt_identity())
    thread = _get_or_create_support_thread(user_id)
    messages = SupportMessage.query.filter_by(thread_id=thread.id).order_by(
        SupportMessage.created_at.asc(), SupportMessage.id.asc()
    ).all()
    changed = False
    for msg in messages:
        if msg.sender == 'admin' and not msg.read_by_user:
            msg.read_by_user = True
            changed = True
    if thread.user_unread:
        thread.user_unread = 0
        changed = True
    if changed:
        db.session.commit()
    return jsonify({'code': 200, 'data': {
        **_anonymous_identity(user_id),
        'thread_id': thread.id,
        'messages': [m.to_dict() for m in messages],
    }})


@feedback_bp.route('/support/status', methods=['GET'])
@jwt_required()
def support_status():
    user_id = int(get_jwt_identity())
    thread = _get_or_create_support_thread(user_id)
    return jsonify({'code': 200, 'data': {'unread': thread.user_unread or 0}})


@feedback_bp.route('/support', methods=['POST'])
@jwt_required()
def send_support_message():
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    content = (data.get('content') or '').strip()
    image_url = (data.get('image_url') or '').strip() or None
    if not content and not image_url:
        return jsonify({'code': 400, 'message': '请输入内容或发送图片'}), 400
    if len(content) > 2000:
        return jsonify({'code': 400, 'message': '单条消息最多 2000 字'}), 400
    thread = _get_or_create_support_thread(user_id)
    msg = SupportMessage(
        thread_id=thread.id, sender='user', content=content,
        image_url=image_url, read_by_admin=False, read_by_user=True,
    )
    thread.admin_unread = (thread.admin_unread or 0) + 1
    thread.last_message_at = local_now()
    db.session.add(msg)
    db.session.commit()
    return jsonify({'code': 200, 'message': '已发送', 'data': msg.to_dict()})


@feedback_bp.route('/admin/support-chats', methods=['GET'])
@admin_required
def admin_support_chats():
    page = max(1, int(request.args.get('page', 1)))
    per_page = min(100, max(1, int(request.args.get('per_page', 30))))
    pagination = SupportThread.query.order_by(
        SupportThread.last_message_at.desc(),
        SupportThread.updated_at.desc(),
    ).paginate(page=page, per_page=per_page, error_out=False)
    items = []
    for t in pagination.items:
        user = User.query.get(t.user_id)
        last = SupportMessage.query.filter_by(thread_id=t.id).order_by(SupportMessage.id.desc()).first()
        identity = _anonymous_identity(t.user_id)
        items.append({
            'id': t.id,
            'user': user.to_dict() if user else None,
            'anonymous_id': identity['anonymous_id'],
            'avatar_seed': identity['avatar_seed'],
            'status': t.status,
            'admin_unread': t.admin_unread or 0,
            'last_message': last.to_dict() if last else None,
            'last_message_at': last.to_dict()['created_at'] if last else None,
        })
    return jsonify({'code': 200, 'data': {
        'items': items,
        'total': pagination.total,
        'page': page,
        'pages': pagination.pages,
    }})


@feedback_bp.route('/admin/support-chats/<int:thread_id>', methods=['GET', 'POST'])
@admin_required
def admin_support_thread(thread_id):
    thread = SupportThread.query.get(thread_id)
    if not thread:
        return jsonify({'code': 404, 'message': '会话不存在'}), 404
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        content = (data.get('content') or '').strip()
        image_url = (data.get('image_url') or '').strip() or None
        if not content and not image_url:
            return jsonify({'code': 400, 'message': '请输入回复内容或发送图片'}), 400
        if len(content) > 2000:
            return jsonify({'code': 400, 'message': '单条消息最多 2000 字'}), 400
        msg = SupportMessage(
            thread_id=thread.id, sender='admin', content=content,
            image_url=image_url, read_by_user=False, read_by_admin=True,
        )
        thread.user_unread = (thread.user_unread or 0) + 1
        thread.last_message_at = local_now()
        db.session.add(msg)
        db.session.commit()
        return jsonify({'code': 200, 'message': '已回复', 'data': msg.to_dict()})

    messages = SupportMessage.query.filter_by(thread_id=thread.id).order_by(
        SupportMessage.created_at.asc(), SupportMessage.id.asc()
    ).all()
    for msg in messages:
        if msg.sender == 'user':
            msg.read_by_admin = True
    thread.admin_unread = 0
    db.session.commit()
    user = User.query.get(thread.user_id)
    return jsonify({'code': 200, 'data': {
        'thread': {'id': thread.id, 'anonymous_id': _anonymous_identity(thread.user_id)['anonymous_id']},
        'user': user.to_dict() if user else None,
        'messages': [m.to_dict() for m in messages],
        'user_unread': thread.user_unread or 0,
        'admin_unread': thread.admin_unread or 0,
    }})
