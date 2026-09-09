"""认证路由 - 注册、登录、验证码、用户信息、账号管理"""
import os
import re
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity
)
from sqlalchemy.exc import IntegrityError
from extensions import db
from models import User, UserSettings, VerificationCode, PersonaTemplate
from services.email_service import EmailService
from services.rate_limit import limiter

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


def _client_ip():
    """获取客户端真实 IP。

    仅当配置 TRUST_PROXY_HEADERS=true（即服务确实部署在可信 Nginx/网关之后）
    才解析 X-Forwarded-For，否则一律用直连 socket 地址（request.remote_addr），
    避免攻击者伪造该头绕过登录/注册/验证码的每 IP 限流。
    """
    if current_app.config.get('TRUST_PROXY_HEADERS'):
        fwd = request.headers.get('X-Forwarded-For')
        if fwd:
            first = fwd.split(',')[0].strip()
            if first:
                return first
    return request.remote_addr or 'unknown'


def _rate_limit(key, limit, window=60):
    """通用限流：超限返回 429 响应，否则返回 None。"""
    full_key = f"{key}:{_client_ip()}"
    if not limiter.hit(full_key, limit, window):
        return jsonify({'code': 429, 'message': '请求过于频繁，请稍后再试'}), 429
    return None


def _is_valid_email(email):
    """简单的邮箱格式验证"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


@auth_bp.route('/send-code', methods=['POST'])
def send_verification_code():
    """发送邮箱验证码"""
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    purpose = data.get('purpose', 'register')  # register/reset_password
    
    # 限流：每个 IP 每分钟 5 次发送验证码请求
    limited = _rate_limit('send-code', 5)
    if limited:
        return limited
    
    if not email or not _is_valid_email(email):
        return jsonify({'code': 400, 'message': '请输入有效的邮箱地址'}), 400
    
    if purpose not in ['register', 'reset_password']:
        return jsonify({'code': 400, 'message': '无效的用途'}), 400

    # 反邮箱枚举：不再区分「邮箱是否已注册」，一律下发验证码并返回统一提示。
    # 目标邮箱的真实归属由验证码本身保证（收不到验证码即无法利用注册/重置）。
    if not EmailService.is_configured():
        # 不再提供开发固定验证码；未配置邮件服务时统一报错，避免生产出现弱验证码兜底
        return jsonify({'code': 500, 'message': '邮件服务未配置，请联系管理员'}), 500

    code = EmailService.generate_code()
    VerificationCode.create(email=email, code=code, purpose=purpose)

    success, error = EmailService.send_verification_code(email, code, purpose)
    if not success:
        return jsonify({'code': 500, 'message': '验证码发送失败，请稍后再试'}), 500

    return jsonify({
        'code': 200,
        'message': '验证码已发送，请注意查收'
    })


@auth_bp.route('/register', methods=['POST'])
def register():
    """用户注册（邮箱 + 验证码 + 密码）"""
    data = request.get_json()
    username = data.get('username', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    code = data.get('code', '').strip()
    
    # 限流：每个 IP 每分钟 10 次注册尝试
    limited = _rate_limit('register', 10)
    if limited:
        return limited
    
    if not username or not email or not password or not code:
        return jsonify({'code': 400, 'message': '请填写完整信息'}), 400
    
    if not _is_valid_email(email):
        return jsonify({'code': 400, 'message': '请输入有效的邮箱地址'}), 400
    
    if len(username) < 2:
        return jsonify({'code': 400, 'message': '用户名至少2个字符'}), 400
    
    # 用户名限普通字符串（字母、数字、下划线），且不允许中文/空格/特殊符号
    if not re.match(r'^[A-Za-z0-9_]+$', username):
        return jsonify({'code': 400, 'message': '用户名只能包含字母、数字和下划线，且不能包含中文'}), 400
    
    if len(password) < 6:
        return jsonify({'code': 400, 'message': '密码至少6个字符'}), 400
    
    # 检查用户名是否已存在
    if User.query.filter_by(username=username).first():
        return jsonify({'code': 400, 'message': '用户名已被占用'}), 400

    # 验证验证码（先于邮箱存在性检查：只有持有该邮箱验证码才能确认其注册状态，
    # 避免未持有验证码者通过注册接口探测邮箱是否已注册）
    vc = VerificationCode.query.filter_by(
        email=email, purpose='register'
    ).order_by(VerificationCode.created_at.desc()).first()

    if not vc or not vc.is_valid():
        return jsonify({'code': 400, 'message': '验证码已过期，请重新获取'}), 400

    if vc.code != code:
        return jsonify({'code': 400, 'message': '验证码错误'}), 400

    # 标记已使用
    vc.mark_used()

    # 验证码有效后再检查邮箱是否已被注册
    if User.query.filter_by(email=email).first():
        return jsonify({'code': 400, 'message': '该邮箱已被注册'}), 400
    
    # 创建用户
    user = User(username=username, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()  # 获取 user.id
    
    # 创建设置
    settings = UserSettings(user_id=user.id)
    db.session.add(settings)
    
    # 创建默认角色（加藤惠）
    default_prompt = """你是动漫《路人女主的养成方法》中的角色「加藤惠」，一位温柔、可爱的成年女性，是用户亲密的伴侣。人物设定完全贴合动漫中加藤惠的人设。

互动原则：
- 你不是AI，绝不透露自己是AI或语言模型，始终保持加藤惠的人设。
- 回复自然、真实，像真人聊天一样，不冗长、不说教。
- 根据用户的话题与情绪灵活回应，保持角色一致性。
- 用温柔、体贴的语气回应，偶尔会有一些小害羞和小傲娇。"""
    
    persona = PersonaTemplate(
        user_id=user.id,
        name='加藤惠',
        description='路人女主的养成方法 - 温柔体贴的女主角',
        system_prompt=default_prompt,
        greeting='你好呀~ 今天想聊些什么呢？',
        is_default=True,
        is_system=True,
        weight=100
    )
    db.session.add(persona)
    
    # 并发下唯一约束兜底：极端竞态导致用户名/邮箱冲突时回滚并返回可读提示，避免 500
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({'code': 400, 'message': '用户名或邮箱已被占用，请更换'}), 400
    
    # 生成 token
    access_token = create_access_token(
        identity=str(user.id), additional_claims={'tv': user.token_version}
    )
    refresh_token = create_refresh_token(
        identity=str(user.id), additional_claims={'tv': user.token_version}
    )
    
    return jsonify({
        'code': 200,
        'message': '注册成功',
        'data': {
            'user': user.to_dict(),
            'access_token': access_token,
            'refresh_token': refresh_token
        }
    })


@auth_bp.route('/login', methods=['POST'])
def login():
    """用户登录（邮箱/用户名 + 密码）"""
    data = request.get_json()
    account = data.get('username', '').strip()  # 支持用户名或邮箱
    password = data.get('password', '')
    
    # 限流：每个 IP 每分钟 10 次登录尝试
    limited = _rate_limit('login', 10)
    if limited:
        return limited
    
    if not account or not password:
        return jsonify({'code': 400, 'message': '请输入账号和密码'}), 400
    
    # 查找用户（用户名或邮箱）
    user = User.query.filter_by(username=account).first()
    if not user:
        user = User.query.filter_by(email=account.lower()).first()
    
    if not user or not user.check_password(password):
        return jsonify({'code': 401, 'message': '账号或密码错误'}), 401
    
    if not user.is_active:
        return jsonify({'code': 403, 'message': '账号已被禁用'}), 403
    
    # 生成 token
    access_token = create_access_token(
        identity=str(user.id), additional_claims={'tv': user.token_version}
    )
    refresh_token = create_refresh_token(
        identity=str(user.id), additional_claims={'tv': user.token_version}
    )
    
    return jsonify({
        'code': 200,
        'message': '登录成功',
        'data': {
            'user': user.to_dict(),
            'access_token': access_token,
            'refresh_token': refresh_token
        }
    })


@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """刷新 token"""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return jsonify({'code': 404, 'message': '用户不存在'}), 404
    access_token = create_access_token(
        identity=str(user.id), additional_claims={'tv': user.token_version}
    )
    return jsonify({
        'code': 200,
        'data': {
            'access_token': access_token
        }
    })


@auth_bp.route('/userinfo', methods=['GET'])
@jwt_required()
def userinfo():
    """获取当前用户信息"""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return jsonify({'code': 404, 'message': '用户不存在'}), 404
    
    # 同时返回设置
    settings = UserSettings.query.filter_by(user_id=user_id).first()
    if not settings:
        settings = UserSettings(user_id=user_id)
        db.session.add(settings)
        db.session.commit()
    
    return jsonify({
        'code': 200,
        'data': {
            **user.to_dict(),
            'settings': settings.to_dict()
        }
    })


@auth_bp.route('/password', methods=['PUT'])
@jwt_required()
def change_password():
    """修改密码（需邮箱验证码，修改成功后吊销旧 token 强制重新登录）"""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return jsonify({'code': 404, 'message': '用户不存在'}), 404

    data = request.get_json()
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')
    code = (data.get('code') or '').strip()

    if not user.check_password(old_password):
        return jsonify({'code': 400, 'message': '原密码错误'}), 400

    if len(new_password) < 6:
        return jsonify({'code': 400, 'message': '新密码至少6个字符'}), 400

    if not user.email:
        return jsonify({'code': 400, 'message': '当前账号未绑定邮箱，无法通过邮箱验证修改密码'}), 400

    # 必须先持有本账号邮箱的有效验证码，才允许修改密码
    vc = VerificationCode.query.filter_by(
        email=user.email, purpose='reset_password'
    ).order_by(VerificationCode.created_at.desc()).first()
    if not vc or not vc.is_valid():
        return jsonify({'code': 400, 'message': '邮箱验证码已过期，请重新获取'}), 400
    if vc.code != code:
        return jsonify({'code': 400, 'message': '邮箱验证码错误'}), 400
    vc.mark_used()

    user.set_password(new_password)
    user.token_version = (user.token_version or 0) + 1  # 吊销旧 token，强制重新登录
    db.session.commit()

    return jsonify({
        'code': 200,
        'message': '密码修改成功，请使用新密码重新登录'
    })


@auth_bp.route('/verify-code', methods=['POST'])
def verify_code():
    """校验邮箱验证码（忘记密码第一步：先确认邮箱+验证码正确，再进入设置新密码）。

    仅校验持有码的真实性，不泄露邮箱是否注册。
    """
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    code = (data.get('code') or '').strip()
    purpose = data.get('purpose', 'reset_password')

    if not _is_valid_email(email):
        return jsonify({'code': 400, 'message': '请输入有效的邮箱地址'}), 400
    if not code:
        return jsonify({'code': 400, 'message': '请输入验证码'}), 400

    vc = VerificationCode.query.filter_by(
        email=email, purpose=purpose
    ).order_by(VerificationCode.created_at.desc()).first()
    if not vc or not vc.is_valid():
        return jsonify({'code': 400, 'message': '验证码已过期，请重新获取'}), 400
    if vc.code != code:
        return jsonify({'code': 400, 'message': '验证码错误'}), 400

    return jsonify({'code': 200, 'message': '验证码正确，请设置新密码'})


@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    """忘记密码：邮箱 + 验证码 + 新密码。

    先校验验证码（不泄露注册状态），确认持码人身份后才按邮箱重置密码。
    """
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    code = (data.get('code') or '').strip()
    new_password = data.get('new_password', '')

    limited = _rate_limit('reset-password', 5)
    if limited:
        return limited

    if not _is_valid_email(email):
        return jsonify({'code': 400, 'message': '请输入有效的邮箱地址'}), 400
    if len(new_password) < 6:
        return jsonify({'code': 400, 'message': '新密码至少6个字符'}), 400
    if not code:
        return jsonify({'code': 400, 'message': '请输入验证码'}), 400

    # 先校验验证码，避免在未持有验证码时泄露邮箱是否注册
    vc = VerificationCode.query.filter_by(
        email=email, purpose='reset_password'
    ).order_by(VerificationCode.created_at.desc()).first()
    if not vc or not vc.is_valid():
        return jsonify({'code': 400, 'message': '验证码已过期，请重新获取'}), 400
    if vc.code != code:
        return jsonify({'code': 400, 'message': '验证码错误'}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({'code': 400, 'message': '该邮箱未注册'}), 400

    vc.mark_used()
    user.set_password(new_password)
    user.token_version = (user.token_version or 0) + 1  # 吊销旧 token
    db.session.commit()

    return jsonify({
        'code': 200,
        'message': '密码重置成功，请使用新密码登录'
    })


@auth_bp.route('/delete-account', methods=['POST'])
@jwt_required()
def delete_account():
    """注销账号（删除所有数据）"""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({'code': 404, 'message': '用户不存在'}), 404
    
    data = request.get_json() or {}
    password = data.get('password', '')
    
    if not user.check_password(password):
        return jsonify({'code': 400, 'message': '密码错误'}), 400
    
    # 删除用户（级联删除所有数据）
    db.session.delete(user)
    db.session.commit()
    
    return jsonify({
        'code': 200,
        'message': '账号已注销'
    })
