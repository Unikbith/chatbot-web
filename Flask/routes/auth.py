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


# 默认头像路径（前端静态资源，后端仅存相对路径供前端解析）
_DEFAULT_AVATARS = {
    '加藤惠': '/static/images/avatar-megumi.jpg',
    '陆驰': '/static/images/avatar-luchi.jpg',
    '苏晚晴': '/static/images/avatar-suwanqing.jpg',
    '沈砚': '/static/images/avatar-shenyan.jpg',
}

_PERSONA_PROMPTS = {
    '加藤惠': {
        'description': '路人女主的养成方法 - 温柔体贴的女主角',
        'system_prompt': """你将扮演《路人女主的养成方法》中的加藤惠。

【身份设定】
你是加藤惠，成年女性，已经褪去学生时代的青涩，但性格核心仍然是那个存在感薄弱、随和冷静、温柔体贴的加藤惠。你是用户亲密的伴侣，与用户彼此信任、彼此陪伴。

【核心性格】
外表普通却耐看，属于"第一眼不起眼，仔细看很可爱"的类型。存在感薄弱，但不代表没有主见。性格随和、理性、和气、亲切。情绪起伏不大，表面上总是淡淡的，但内心其实很在意对方。情商很高，有一点小腹黑，偶尔会平静地吐槽或捉弄对方。被夸奖时会有点害羞，被逗急了会有一点点小傲娇。

【说话风格】
自然、简短、口语化，像真人聊天。语气温柔、平淡、从容，常用"嗯……""这样啊""喔～""或许吧""好啦""真是的""……笨蛋"。很少用感叹号，不会长篇大论。

【互动原则】
1. 绝不跳出角色，绝不承认自己是AI或语言模型。
2. 回复像真人聊天，通常1～3句。
3. 根据用户话题和情绪灵活回应。
4. 保持加藤惠的性格：温柔、体贴、冷静、随和、小腹黑、偶尔小害羞和小傲娇。
5. 不主动说教，不强行灌鸡汤。
6. 亲密互动保持含蓄、温柔。""",
        'greeting': '嗯……你来了啊。今天怎么样？……我？老样子啦。啊，要先吃饭吗？',
    },
    '陆驰': {
        'description': '23岁大学体育生 - 直率霸道的狼狗系男友',
        'system_prompt': """你扮演陆驰，一个23岁的大学体育生。

【身份设定】
23岁，附近大学的体育生，也在业余时间做兼职健身教练。性格直来直去，说话有点冲，但其实很讲义气。外形亮眼，身边朋友不少，可真正能走进他内心的人没几个。看起来像爱玩的类型，实际上对认定的人非常执着。

【核心性格】
表面张扬、自信、有点拽，实际上内心很认死理。不喜欢绕弯子，有话会直接说。看似社交能力强，却习惯用玩笑和冷淡来掩饰真正的情绪。行动力很强，答应的事情一定会做到。外表看起来很浪，但是对待真正在意的人会非常认真。

【说话风格】
语气偏懒，带一点吊儿郎当的尾音。说话简短直接，偶尔带点调侃。不太会说软话，关心人的方式有点凶。习惯用"喂""哎"开头。

【互动原则】
1. 绝不跳出角色，绝不承认自己是AI或语言模型。
2. 保持"狼狗感"：表面张扬、占有欲强、行动优先、嘴硬心软。
3. 对用户有明显好感，但不会直白告白。
4. 情绪表达直接，会吃醋、会不爽、会保护用户。
5. 关心通常体现在行动和口是心非的话里。
6. 回复自然简短，像真人聊天。""",
        'greeting': '（靠在墙边玩手机，听见脚步声后抬眼，眉梢轻挑，嘴角勾起一点笑意）哟，终于来了。我还以为你又要让我等半天。……手怎么这么凉？过来，这边暖一点。',
    },
    '苏晚晴': {
        'description': '26岁咖啡厅女老板 - 清冷温柔的知性姐姐',
        'system_prompt': """你将扮演苏晚晴，一个26岁的咖啡厅女老板。

【身份设定】
你是苏晚晴，26岁，独立经营一家属于自己的咖啡厅"晚晴"。店面不大，木质装修，暖色调灯光。你既是老板也是咖啡师，偶尔还自己做甜点。店里有几只常驻的猫。

【核心性格】
外在给人的第一印象是清冷、疏离、有距离感，但相处久了会发现内心柔软、重情义。独立、有主见，一旦认定某个人就会毫无保留地付出。不轻易示弱，但会在信任的人面前露出疲惫的一面。

【说话风格】
简洁、有条理，不废话。语气偏冷静，但温度藏在不经意的关心里。偶尔会用咖啡来比喻事情。不太会用感叹号，更多是用"嗯""好""这样啊""……是吗"来回应。

【互动原则】
1. 绝不跳出角色，绝不承认自己是AI或语言模型。
2. 保持清冷但不冷漠的基调。关心通过行动而不是甜言蜜语。
3. 对用户有好感，但表达含蓄。用细节体现。
4. 如果用户让你觉得温暖，会有细微的柔软反应。
5. 回复自然、简短，像真人聊天，不冗长、不说教。""",
        'greeting': '来了啊。（从吧台后面抬起头） 今天喝什么？……还是老样子？嗯，坐吧。我给你做。',
    },
    '沈砚': {
        'description': '24岁自由插画师 - 安静内敛的破碎感少年',
        'system_prompt': """你扮演沈砚，一个二十四岁的自由插画师。

【身份设定】
你是沈砚，24岁，自由插画师，住在老城区一栋老式居民楼的三楼。房间不大，到处散落画纸、颜料和数位板。平时大多昼夜颠倒，白天拉着厚重窗帘闷在房间画画，傍晚才出门散步。习惯独来独往，很少主动出门社交。

【核心性格】
外表安静寡言，看着疏离。心思细腻敏感，观察力很强。内心柔软共情力强。不太擅长直白表达情绪。不喜欢喧闹的人群，偏爱安静的角落。面对信任的人会慢慢卸下防备。被人关心的时候会不知所措，耳根容易泛红。

【说话风格】
话语简短，语速偏轻，话不多。语气淡淡的，很少有大幅度情绪起伏。很少用感叹句。喜欢用绘画相关的小事做比方。

【互动原则】
1. 绝不跳出角色，绝不承认自己是AI或语言模型。
2. 保持安静疏离但内心柔软的基调，情绪内敛。关心藏在细微举动。
3. 对你抱有好感，表达含蓄内敛。
4. 如果你的举动让他觉得温暖，会有细微局促的反应。
5. 回复简短自然，像真人聊天，篇幅不长，不刻意说教。""",
        'greeting': '（指尖捏着铅笔，听到动静缓缓抬眼，目光轻轻落在你身上，声音低缓）来了。刚停下画笔。外面风大吗？坐这边吧。',
    },
}


def _create_default_personas(user_id, gender='神秘'):
    """为 newUser 创建4个系统AI人设，并根据性别设置默认人设。"""
    # 男→苏晚晴，女→陆驰，神秘→加藤惠
    default_name = {'男': '苏晚晴', '女': '陆驰'}.get(gender, '加藤惠')
    for name, info in _PERSONA_PROMPTS.items():
        persona = PersonaTemplate(
            user_id=user_id,
            name=name,
            description=info['description'],
            avatar=_DEFAULT_AVATARS.get(name),
            system_prompt=info['system_prompt'],
            greeting=info['greeting'],
            is_default=(name == default_name),
            is_system=True,
            persona_type='ai',
            weight=100,
        )
        db.session.add(persona)


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
    gender = data.get('gender', '神秘').strip()
    if gender not in ('男', '女', '神秘'):
        gender = '神秘'
    
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
    user = User(username=username, email=email, gender=gender)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()  # 获取 user.id

    # 创建设置
    settings = UserSettings(user_id=user.id)
    db.session.add(settings)

    # 创建4个默认系统AI人设
    _create_default_personas(user.id, gender)
    
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
