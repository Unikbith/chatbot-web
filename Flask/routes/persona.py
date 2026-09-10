"""角色模板路由 - 人设提示词管理"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models import PersonaTemplate

persona_bp = Blueprint('persona', __name__, url_prefix='/api/personas')


@persona_bp.route('', methods=['GET'])
@jwt_required()
def list_personas():
    """获取角色模板列表"""
    user_id = int(get_jwt_identity())
    
    personas = PersonaTemplate.query.filter_by(user_id=user_id).order_by(
        PersonaTemplate.is_default.desc(),
        PersonaTemplate.weight.desc(),
        PersonaTemplate.created_at.desc()
    ).all()
    
    return jsonify({
        'code': 200,
        'data': [p.to_dict() for p in personas]
    })


@persona_bp.route('/<int:persona_id>', methods=['GET'])
@jwt_required()
def get_persona(persona_id):
    """获取角色详情"""
    user_id = int(get_jwt_identity())
    persona = PersonaTemplate.query.filter_by(id=persona_id, user_id=user_id).first()
    
    if not persona:
        return jsonify({'code': 404, 'message': '角色不存在'}), 404
    
    return jsonify({
        'code': 200,
        'data': persona.to_dict()
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
        is_system=False,
        persona_type=data.get('persona_type', 'ai'),
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
    
    # 系统内置角色不可修改
    if persona.is_system:
        return jsonify({'code': 400, 'message': '系统内置角色不可修改'}), 400
    
    data = request.get_json() or {}
    
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
    
    if persona.is_system:
        return jsonify({'code': 400, 'message': '系统内置角色不可删除'}), 400
    
    was_default = persona.is_default
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
