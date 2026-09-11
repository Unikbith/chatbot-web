"""用户反馈路由 - 帮助与反馈"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models import Feedback
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
