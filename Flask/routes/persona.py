"""角色模板路由 - 人设提示词管理"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models import PersonaTemplate, MarketplaceAdopt

persona_bp = Blueprint('persona', __name__, url_prefix='/api/personas')

# 人物卡（AI 人设）数量上限
PERSONA_CARD_LIMIT = 10

# 字段长度上限（与前端 PersonaPanel 保持一致，服务端兜底校验）
MAX_NAME_LEN = 1000
MAX_DESCRIPTION_LEN = 1000
MAX_PROMPT_LEN = 10000
MAX_GREETING_LEN = 1000


def _validate_lengths(name, description, system_prompt, greeting):
    """人物卡字段长度校验，超限返回错误信息字符串，否则返回 None"""
    if name is not None and len(name) > MAX_NAME_LEN:
        return f'角色名称过长（最多 {MAX_NAME_LEN} 字）'
    if description is not None and len(description) > MAX_DESCRIPTION_LEN:
        return f'角色简介过长（最多 {MAX_DESCRIPTION_LEN} 字）'
    if system_prompt is not None and len(system_prompt) > MAX_PROMPT_LEN:
        return f'系统提示词过长（最多 {MAX_PROMPT_LEN} 字）'
    if greeting is not None and len(greeting) > MAX_GREETING_LEN:
        return f'开场问候语过长（最多 {MAX_GREETING_LEN} 字）'
    return None


def _card_source(persona, user_id):
    """人物卡来源：卡片广场（通过 adopt 记录判断）或 None"""
    adopt = MarketplaceAdopt.query.filter_by(
        template_id=persona.id, user_id=user_id
    ).first()
    return 'marketplace' if adopt else None


@persona_bp.route('', methods=['GET'])
@jwt_required()
def list_personas():
    """获取角色模板列表"""
    user_id = int(get_jwt_identity())

    # 系统自带人物卡与卡片广场系统卡的关联补齐（幂等），保证「卡片广场」来源标签可用
    try:
        from routes.marketplace import ensure_system_adopts
        ensure_system_adopts(user_id)
    except Exception:
        db.session.rollback()

    personas = PersonaTemplate.query.filter_by(user_id=user_id).order_by(
        PersonaTemplate.is_default.desc(),
        PersonaTemplate.weight.desc(),
        PersonaTemplate.created_at.desc()
    ).all()
    
    data = []
    for p in personas:
        d = p.to_dict()
        d['source'] = _card_source(p, user_id)
        data.append(d)

    return jsonify({
        'code': 200,
        'data': data
    })


@persona_bp.route('/<int:persona_id>', methods=['GET'])
@jwt_required()
def get_persona(persona_id):
    """获取角色详情"""
    user_id = int(get_jwt_identity())
    persona = PersonaTemplate.query.filter_by(id=persona_id, user_id=user_id).first()
    
    if not persona:
        return jsonify({'code': 404, 'message': '角色不存在'}), 404

    d = persona.to_dict()
    d['source'] = _card_source(persona, user_id)
    return jsonify({
        'code': 200,
        'data': d
    })


@persona_bp.route('', methods=['POST'])
@jwt_required()
def create_persona():
    """创建角色模板"""
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    
    name = data.get('name', '').strip()
    system_prompt = data.get('system_prompt', '').strip()
    description = data.get('description', '').strip() or None
    avatar = data.get('avatar', '').strip() or None
    greeting = data.get('greeting', '').strip() or None
    is_default = data.get('is_default', False)
    
    if not name or not system_prompt:
        return jsonify({'code': 400, 'message': '角色名和系统提示词不能为空'}), 400

    length_err = _validate_lengths(name, description, system_prompt, greeting)
    if length_err:
        return jsonify({'code': 400, 'message': length_err}), 400

    persona_type = data.get('persona_type', 'ai') or 'ai'

    # 人物卡（AI 人设）数量上限
    if persona_type == 'ai':
        ai_count = PersonaTemplate.query.filter_by(user_id=user_id, persona_type='ai').count()
        if ai_count >= PERSONA_CARD_LIMIT:
            return jsonify({
                'code': 400,
                'message': f'人物卡数量已达上限（{PERSONA_CARD_LIMIT} 个）'
            }), 400

    # 如果设为默认，取消其他默认
    if is_default:
        PersonaTemplate.query.filter_by(
            user_id=user_id, is_default=True
        ).update({'is_default': False})

    persona = PersonaTemplate(
        user_id=user_id,
        name=name,
        description=description,
        avatar=avatar,
        system_prompt=system_prompt,
        greeting=greeting,
        is_default=is_default,
        persona_type=persona_type,
    )
    db.session.add(persona)
    
    # 如果是第一个角色，自动设为默认
    if PersonaTemplate.query.filter_by(user_id=user_id).count() == 1:
        persona.is_default = True
    
    db.session.commit()
    
    return jsonify({
        'code': 200,
        'message': '创建成功',
        'data': persona.to_dict()
    })


@persona_bp.route('/<int:persona_id>', methods=['PUT'])
@jwt_required()
def update_persona(persona_id):
    """更新角色模板"""
    user_id = int(get_jwt_identity())
    persona = PersonaTemplate.query.filter_by(id=persona_id, user_id=user_id).first()
    
    if not persona:
        return jsonify({'code': 404, 'message': '角色不存在'}), 404

    data = request.get_json() or {}

    # 更新前对待写字段做长度校验（仅校验请求中携带的字段）
    def _field(key, current):
        if key not in data:
            return None
        v = data[key]
        return v.strip() if isinstance(v, str) else current

    length_err = _validate_lengths(
        _field('name', persona.name),
        _field('description', persona.description),
        _field('system_prompt', persona.system_prompt),
        _field('greeting', persona.greeting),
    )
    if length_err:
        return jsonify({'code': 400, 'message': length_err}), 400

    if 'name' in data:
        persona.name = data['name'].strip() or persona.name
    if 'description' in data:
        persona.description = data['description'].strip() or None
    if 'avatar' in data:
        persona.avatar = data['avatar'] or None
    if 'system_prompt' in data:
        persona.system_prompt = data['system_prompt'].strip() or persona.system_prompt
    if 'greeting' in data:
        persona.greeting = data['greeting'].strip() or None
    if 'weight' in data:
        try:
            weight = int(data['weight'])
        except (TypeError, ValueError):
            return jsonify({'code': 400, 'message': '无效的权重'}), 400
        persona.weight = max(0, min(100, weight))
    if 'is_default' in data and data['is_default']:
        PersonaTemplate.query.filter_by(
            user_id=user_id, is_default=True
        ).update({'is_default': False})
        persona.is_default = True
    if 'persona_type' in data:
        pt = (data['persona_type'] or '').strip()
        if pt in ('ai', 'user'):
            persona.persona_type = pt
    
    db.session.commit()
    
    return jsonify({
        'code': 200,
        'message': '更新成功',
        'data': persona.to_dict()
    })


@persona_bp.route('/<int:persona_id>', methods=['DELETE'])
@jwt_required()
def delete_persona(persona_id):
    """删除角色模板"""
    user_id = int(get_jwt_identity())
    persona = PersonaTemplate.query.filter_by(id=persona_id, user_id=user_id).first()
    
    if not persona:
        return jsonify({'code': 404, 'message': '角色不存在'}), 404

    was_default = persona.is_default

    # 清理该人物卡对应的卡片广场 adopt 记录，
    # 保证卡片广场的「已添加」状态与人物卡列表实时同步
    MarketplaceAdopt.query.filter_by(
        template_id=persona.id, user_id=user_id
    ).delete()

    db.session.delete(persona)
    db.session.commit()
    
    # 如果删的是默认角色，将第一个设为默认
    if was_default:
        first = PersonaTemplate.query.filter_by(user_id=user_id).first()
        if first:
            first.is_default = True
            db.session.commit()
    
    return jsonify({
        'code': 200,
        'message': '删除成功'
    })


@persona_bp.route('/<int:persona_id>/default', methods=['PUT'])
@jwt_required()
def set_default(persona_id):
    """设为默认角色"""
    user_id = int(get_jwt_identity())
    persona = PersonaTemplate.query.filter_by(id=persona_id, user_id=user_id).first()
    
    if not persona:
        return jsonify({'code': 404, 'message': '角色不存在'}), 404
    
    PersonaTemplate.query.filter_by(
        user_id=user_id, is_default=True
    ).update({'is_default': False})
    persona.is_default = True
    db.session.commit()
    
    return jsonify({
        'code': 200,
        'message': '已设为默认',
        'data': persona.to_dict()
    })
