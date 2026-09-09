"""用户设置路由 - 通用设置、AI 参数等"""
import math

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models import UserSettings, User

settings_bp = Blueprint('settings', __name__, url_prefix='/api/settings')

# 数值型设置字段: (请求键, 模型属性, 下限, 上限)；非法值一律返回 400 而非 500
_NUMERIC_FIELDS = [
    ('message_opacity', 'message_opacity', 0.1, 1.0),
    ('temperature', 'temperature', 0.0, 2.0),
    ('frequency_penalty', 'frequency_penalty', -2.0, 2.0),
    ('presence_penalty', 'presence_penalty', -2.0, 2.0),
    ('top_p', 'top_p', 0.0, 1.0),
]


def _parse_float_clamped(raw, lo, hi):
    """安全解析浮点并钳制到 [lo, hi]；空/非数值/NaN/Inf 返回 None。"""
    try:
        f = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return max(lo, min(hi, f))


@settings_bp.route('', methods=['GET'])
@jwt_required()
def get_settings():
    """获取用户设置"""
    user_id = int(get_jwt_identity())
    settings = UserSettings.query.filter_by(user_id=user_id).first()
    
    if not settings:
        # 创建设置
        settings = UserSettings(user_id=user_id)
        db.session.add(settings)
        db.session.commit()
    
    return jsonify({
        'code': 200,
        'data': settings.to_dict()
    })


@settings_bp.route('', methods=['PUT'])
@jwt_required()
def update_settings():
    """更新用户设置"""
    user_id = int(get_jwt_identity())
    settings = UserSettings.query.filter_by(user_id=user_id).first()
    
    if not settings:
        settings = UserSettings(user_id=user_id)
        db.session.add(settings)
    
    data = request.get_json() or {}

    # 通用设置
    if 'theme' in data:
        settings.theme = data['theme']
    if 'language' in data:
        settings.language = data['language']
    if 'background_image' in data:
        settings.background_image = data['background_image'] or None
    if 'background_cover' in data:
        settings.background_cover = data['background_cover'] or 'contain'
    if 'sidebar_collapsed' in data:
        settings.sidebar_collapsed = bool(data['sidebar_collapsed'])

    # 数值型设置：交给统一校验（非数值/NaN/Inf → 400）
    for key, attr, lo, hi in _NUMERIC_FIELDS:
        if key in data:
            val = _parse_float_clamped(data[key], lo, hi)
            if val is None:
                return jsonify({'code': 400, 'message': f'无效的参数: {key}'}), 400
            setattr(settings, attr, val)
    
    # 语音设置
    if 'default_voice' in data:
        settings.default_voice = data['default_voice']
    if 'auto_play_voice' in data:
        settings.auto_play_voice = bool(data['auto_play_voice'])
    
    db.session.commit()
    
    return jsonify({
        'code': 200,
        'message': '设置已更新',
        'data': settings.to_dict()
    })


@settings_bp.route('/profile', methods=['PUT'])
@jwt_required()
def update_profile():
    """更新用户资料（用户名、头像等）"""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({'code': 404, 'message': '用户不存在'}), 404
    
    data = request.get_json() or {}
    
    # 用户名与邮箱均为唯一且不可修改（注册后锁定）
    if 'username' in data:
        return jsonify({'code': 400, 'message': '用户名注册后不可修改'}), 400
    if 'email' in data:
        return jsonify({'code': 400, 'message': '邮箱注册后不可修改'}), 400
    
    if 'avatar' in data:
        user.avatar = data['avatar'] or None
    
    if 'ai_avatar' in data:
        user.ai_avatar = data['ai_avatar'] or None
    
    db.session.commit()
    
    return jsonify({
        'code': 200,
        'message': '资料已更新',
        'data': user.to_dict()
    })
