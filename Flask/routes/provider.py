"""模型提供商路由 - 按「提供商 -> 模型」两级结构管理

对话模型仅支持预设厂商（小米/DeepSeek/智谱/Kimi/MiniMax），用户只需配置
ID（name）、API Key、API Base URL。每个提供商下可管理多个模型：
  - 已配置模型：可启用/停用、测试、删除
  - 可用模型：从厂商 /models 接口拉取，点击加入已配置
  - 自定义模型：手动输入模型 ID（列表拉取不到的模型）
"""
import requests
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.exc import IntegrityError
from extensions import db
from models import ModelProvider, ProviderModel
from services.vendor_presets import get_vendor, get_vendors, get_config_schema, CHAT_VENDORS
from services.ai_service import AIService

provider_bp = Blueprint('provider', __name__, url_prefix='/api/providers')

VALID_TYPES = ['chat', 'stt', 'tts', 'image']


def _get_own_provider(provider_id, user_id):
    """获取属于当前用户的提供商"""
    return ModelProvider.query.filter_by(id=provider_id, user_id=user_id).first()


def _get_own_model(model_id, user_id):
    """获取属于当前用户的已配置模型"""
    m = ProviderModel.query.get(model_id)
    if not m:
        return None
    p = _get_own_provider(m.provider_id, user_id)
    if not p:
        return None
    return m


@provider_bp.route('/vendors', methods=['GET'])
@jwt_required()
def list_vendors():
    """获取某一类型的厂商预设（前端用于选择厂商）"""
    provider_type = request.args.get('type', 'chat')
    if provider_type not in VALID_TYPES:
        return jsonify({'code': 400, 'message': '无效的提供商类型'}), 400
    return jsonify({
        'code': 200,
        'data': get_vendors(provider_type)
    })


@provider_bp.route('/config-schema', methods=['GET'])
@jwt_required()
def config_schema():
    """获取某类型 + 厂商的额外配置字段（STT/TTS 专用，不含公共 ID/API Key/Base URL）"""
    provider_type = request.args.get('type', 'chat')
    brand = request.args.get('brand', '')
    if provider_type not in VALID_TYPES:
        return jsonify({'code': 400, 'message': '无效的提供商类型'}), 400
    return jsonify({
        'code': 200,
        'data': get_config_schema(provider_type, brand)
    })


@provider_bp.route('', methods=['GET'])
@jwt_required()
def list_providers():
    """获取用户的所有模型提供商，可按类型筛选"""
    user_id = int(get_jwt_identity())
    provider_type = request.args.get('type', None)

    query = ModelProvider.query.filter_by(user_id=user_id)
    if provider_type:
        if provider_type not in VALID_TYPES:
            return jsonify({'code': 400, 'message': '无效的提供商类型'}), 400
        query = query.filter_by(provider_type=provider_type)

    providers = query.order_by(
        ModelProvider.is_default.desc(),
        ModelProvider.weight.desc(),
        ModelProvider.created_at.desc()
    ).all()

    return jsonify({
        'code': 200,
        'data': [p.to_dict(include_models=True) for p in providers]
    })


@provider_bp.route('/all', methods=['GET'])
@jwt_required()
def list_all_grouped():
    """获取所有类型的提供商，按类型分组返回"""
    user_id = int(get_jwt_identity())

    result = {}
    for ptype in VALID_TYPES:
        providers = ModelProvider.query.filter_by(
            user_id=user_id, provider_type=ptype
        ).order_by(
            ModelProvider.is_default.desc(),
            ModelProvider.weight.desc(),
            ModelProvider.created_at.desc()
        ).all()
        result[ptype] = [p.to_dict(include_models=True) for p in providers]

    return jsonify({
        'code': 200,
        'data': result
    })


@provider_bp.route('/<int:provider_id>', methods=['GET'])
@jwt_required()
def get_provider(provider_id):
    """获取单个提供商详情（含已配置模型）"""
    user_id = int(get_jwt_identity())
    provider = _get_own_provider(provider_id, user_id)
    if not provider:
        return jsonify({'code': 404, 'message': '提供商不存在'}), 404

    return jsonify({
        'code': 200,
        'data': provider.to_dict(include_key=True, include_models=True)
    })


@provider_bp.route('', methods=['POST'])
@jwt_required()
def create_provider():
    """创建模型提供商（仅需 ID、API Key、API Base URL）"""
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}

    name = (data.get('name') or '').strip()
    provider_type = data.get('provider_type', 'chat')
    brand = data.get('brand', 'deepseek')
    api_url = (data.get('api_url') or '').rstrip('/')
    api_key = (data.get('api_key') or '').strip()
    model = (data.get('model') or '').strip()
    params = data.get('params') or {}

    if provider_type not in VALID_TYPES:
        return jsonify({'code': 400, 'message': '无效的提供商类型'}), 400

    if not name:
        return jsonify({'code': 400, 'message': '请填写配置 ID（名称）'}), 400

    if not api_key:
        return jsonify({'code': 400, 'message': '请填写 API Key'}), 400

    # STT/TTS 厂商接口差异较大，暂不做强校验；对话模型给出默认地址提示
    if not api_url:
        vendor = get_vendor(brand, provider_type)
        api_url = (vendor or {}).get('default_api_url', '')

    # 重复创建判断（同类型下名称唯一）
    exists = ModelProvider.query.filter_by(
        user_id=user_id, provider_type=provider_type, name=name
    ).first()
    if exists:
        return jsonify({'code': 400, 'message': '已存在同名配置，请更换 ID'}), 400

    provider = ModelProvider(
        user_id=user_id,
        name=name,
        provider_type=provider_type,
        brand=brand,
        api_type='openai',
        api_url=api_url,
        api_key=api_key,
        model=model or None,
    )
    provider.set_params(params)
    db.session.add(provider)

    # 如果是该类型第一个配置，自动设为默认
    if ModelProvider.query.filter_by(user_id=user_id, provider_type=provider_type).count() == 0:
        provider.is_default = True

    # 图片生成配置：自动预置厂商默认模型（Agnes），无需用户手动拉取
    if provider_type == 'image':
        vendor = get_vendor(brand, provider_type)
        default_models = (vendor or {}).get('models', [])
        for mid in default_models:
            provider.models.append(ProviderModel(model_id=mid, name=mid, enabled=True))

    # 并发下唯一约束兜底：极端竞态导致同名冲突时回滚并返回可读提示，避免 500
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({'code': 400, 'message': '已存在同名配置，请更换 ID'}), 400

    return jsonify({
        'code': 200,
        'message': '创建成功',
        'data': provider.to_dict(include_key=True, include_models=True)
    })


@provider_bp.route('/<int:provider_id>', methods=['PUT'])
@jwt_required()
def update_provider(provider_id):
    """更新模型提供商"""
    user_id = int(get_jwt_identity())
    provider = _get_own_provider(provider_id, user_id)
    if not provider:
        return jsonify({'code': 404, 'message': '提供商不存在'}), 404

    data = request.get_json() or {}

    if 'name' in data:
        new_name = (data.get('name') or '').strip()
        if new_name:
            provider.name = new_name
    if 'brand' in data:
        provider.brand = data['brand']
    if 'api_url' in data:
        provider.api_url = (data['api_url'] or '').rstrip('/')
    if 'api_key' in data and data.get('api_key'):
        incoming = data['api_key'].strip()
        masked_current = ModelProvider.mask_api_key(provider.api_key)
        # 若提交的是掩码回显值或与现有明文相同，视为未修改，避免误覆写
        if incoming and incoming != masked_current and incoming != (provider.api_key or ''):
            provider.api_key = incoming
    if 'model' in data:
        provider.model = (data.get('model') or '').strip() or None
    if 'params' in data:
        provider.set_params(data.get('params') or {})
    if 'enabled' in data:
        provider.enabled = bool(data['enabled'])

    db.session.commit()

    return jsonify({
        'code': 200,
        'message': '更新成功',
        'data': provider.to_dict(include_key=True, include_models=True)
    })


@provider_bp.route('/<int:provider_id>', methods=['DELETE'])
@jwt_required()
def delete_provider(provider_id):
    """删除模型提供商"""
    user_id = int(get_jwt_identity())
    provider = _get_own_provider(provider_id, user_id)
    if not provider:
        return jsonify({'code': 404, 'message': '提供商不存在'}), 404

    provider_type = provider.provider_type
    was_default = provider.is_default
    db.session.delete(provider)
    db.session.commit()

    # 如果删除的是默认配置，将第一个配置设为默认
    if was_default:
        first_provider = ModelProvider.query.filter_by(
            user_id=user_id, provider_type=provider_type
        ).first()
        if first_provider:
            first_provider.is_default = True
            db.session.commit()

    return jsonify({'code': 200, 'message': '删除成功'})


@provider_bp.route('/<int:provider_id>/default', methods=['PUT'])
@jwt_required()
def set_default(provider_id):
    """设置为该类型的默认提供商"""
    user_id = int(get_jwt_identity())
    provider = _get_own_provider(provider_id, user_id)
    if not provider:
        return jsonify({'code': 404, 'message': '提供商不存在'}), 404

    ModelProvider.query.filter_by(
        user_id=user_id, provider_type=provider.provider_type, is_default=True
    ).update({'is_default': False})
    provider.is_default = True
    db.session.commit()

    return jsonify({'code': 200, 'message': '已设为默认', 'data': provider.to_dict()})


# ---------------------------------------------------------------------------
# 提供商连接与模型测试
# ---------------------------------------------------------------------------

def _chat_request_ok(provider, model_id, timeout=15):
    """向厂商发起一次最小化 chat 请求，验证配置与模型是否可用"""
    # SSRF 防护：测试路径同样纳入拦截，防止利用连接测试探测内网/云元数据
    err = AIService._ssrf_error(provider.api_url)
    if err:
        return False, err
    url = AIService._build_chat_url(provider.api_url)
    payload = {
        'model': model_id or provider.model or 'gpt-3.5-turbo',
        'messages': [{'role': 'user', 'content': 'hi'}],
        'max_tokens': 1,
        'stream': False,
    }
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {provider.api_key}',
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if resp.status_code in (200, 201):
        return True, ''
    try:
        msg = resp.json().get('error', {}).get('message', resp.text[:200])
    except Exception:
        msg = resp.text[:200]
    return False, f'HTTP {resp.status_code}: {msg}'


def _generic_request_ok(provider, timeout=15):
    """STT/TTS 等其它类型的连通性测试。

    多家 STT/TTS 接口（尤其火山引擎 openspeech 自定义接口）并不提供 /models，
    因此这里只做基础连通检查：能到达并返回任意 HTTP 状态，即视为「地址可达」；
    真正的识别/合成是否成功以实际使用接口为准。
    """
    params = provider.get_params() or {}
    # SSRF 防护：基础连通检查同样纳入拦截
    err = AIService._ssrf_error(provider.api_url)
    if err:
        return False, err
    base = AIService._resolve_base(provider.api_url)
    url = f"{base}/models"
    proxies = None
    if params.get('proxy'):
        proxies = {'http': params['proxy'], 'https': params['proxy']}
    headers = {'Authorization': f'Bearer {provider.api_key}'}

    def readable(resp):
        try:
            msg = resp.json().get('error', {}).get('message', resp.text[:150])
        except Exception:
            msg = resp.text[:150]
        return f'HTTP {resp.status_code}: {msg}'

    try:
        resp = requests.get(url, headers=headers, timeout=timeout, proxies=proxies)
        if resp.status_code in (200, 201):
            return True, ''
        return False, f'接口不可用（/models 未提供）: {readable(resp)}'
    except requests.RequestException:
        # 无法拉取 /models —— 属于接口不支持或地址为自定义端点，
        # 改做纯连通检查：能建立 TCP/收到响应即认为基础可达。
        pass

    try:
        ping_url = provider.api_url.rstrip('/')
        resp = requests.get(ping_url, headers=headers, timeout=timeout, proxies=proxies)
        return True, '基础地址可达（请以实际语音接口验证准确性）'
    except requests.RequestException as e:
        return False, f'无法连接 API: {str(e)}'


def _tts_request_ok(provider, timeout=30):
    """TTS 真实合成测试：用短文本实际合成一段音频，成功才算可用。

    仅做连通性检查会误导用户（地址可达但协议/额度不对导致无法合成）。
    """
    params = provider.get_params() or {}
    err = AIService._ssrf_error(provider.api_url)
    if err:
        return False, err
    try:
        audio, err = AIService.text_to_speech(provider, '你好')
    except Exception as e:
        return False, f'合成异常: {str(e)}'
    if err:
        return False, err
    if not audio:
        return False, '未返回音频数据'
    return True, ''


@provider_bp.route('/<int:provider_id>/test', methods=['POST'])
@jwt_required()
def test_provider(provider_id):
    """测试提供商基础配置是否可用（不带具体模型）"""
    user_id = int(get_jwt_identity())
    provider = _get_own_provider(provider_id, user_id)
    if not provider:
        return jsonify({'code': 404, 'message': '提供商不存在'}), 404

    try:
        if provider.provider_type == 'chat':
            ok, err = _chat_request_ok(provider, provider.model)
        elif provider.provider_type == 'tts':
            ok, err = _tts_request_ok(provider)
        else:
            ok, err = _generic_request_ok(provider)
        if ok:
            return jsonify({'code': 200, 'message': '连接成功', 'data': {'ok': True}})
        return jsonify({'code': 500, 'message': f'连接失败: {err}'})
    except Exception as e:
        return jsonify({'code': 500, 'message': f'测试失败: {str(e)}'})


# ---------------------------------------------------------------------------
# 已配置模型管理
# ---------------------------------------------------------------------------

@provider_bp.route('/<int:provider_id>/models', methods=['GET'])
@jwt_required()
def list_models(provider_id):
    """获取该提供商下已配置的模型"""
    user_id = int(get_jwt_identity())
    provider = _get_own_provider(provider_id, user_id)
    if not provider:
        return jsonify({'code': 404, 'message': '提供商不存在'}), 404
    return jsonify({
        'code': 200,
        'data': [m.to_dict() for m in provider.models]
    })


@provider_bp.route('/<int:provider_id>/models', methods=['POST'])
@jwt_required()
def add_model(provider_id):
    """添加已配置模型（可用模型加入 / 自定义模型输入）"""
    user_id = int(get_jwt_identity())
    provider = _get_own_provider(provider_id, user_id)
    if not provider:
        return jsonify({'code': 404, 'message': '提供商不存在'}), 404

    data = request.get_json() or {}
    model_id = (data.get('model_id') or '').strip()
    is_custom = bool(data.get('is_custom', False))
    name = (data.get('name') or '').strip()

    if not model_id:
        return jsonify({'code': 400, 'message': '模型 ID 不能为空'}), 400

    # 避免重复
    exists = ProviderModel.query.filter_by(provider_id=provider.id, model_id=model_id).first()
    if exists:
        return jsonify({'code': 400, 'message': '该模型已配置过'}), 400

    pm = ProviderModel(
        provider_id=provider.id,
        model_id=model_id,
        name=name or model_id,
        enabled=True,
        is_custom=is_custom,
    )
    db.session.add(pm)
    db.session.commit()

    return jsonify({'code': 200, 'message': '已添加', 'data': pm.to_dict()})


@provider_bp.route('/<int:provider_id>/models/fetch', methods=['POST'])
@jwt_required()
def fetch_models(provider_id):
    """从厂商 /models 接口拉取可用模型列表（供用户勾选加入）"""
    user_id = int(get_jwt_identity())
    provider = _get_own_provider(provider_id, user_id)
    if not provider:
        return jsonify({'code': 404, 'message': '提供商不存在'}), 404

    # SSRF 防护：拉取模型同样纳入拦截
    err = AIService._ssrf_error(provider.api_url)
    if err:
        return jsonify({'code': 500, 'message': f'获取模型列表失败: {err}'}), 500

    base = AIService._resolve_base(provider.api_url)
    models_url = f"{base}/models"
    headers = {'Authorization': f'Bearer {provider.api_key}'}

    try:
        resp = requests.get(models_url, headers=headers, timeout=20)
        if resp.status_code not in (200, 201):
            return jsonify({
                'code': 500,
                'message': f'获取模型列表失败: HTTP {resp.status_code}'
            }), 500
        data = resp.json().get('data', [])
    except requests.RequestException as e:
        return jsonify({'code': 500, 'message': f'获取模型列表失败: {str(e)}'}), 500

    # 标记已配置的模型
    configured = {
        m.model_id for m in ProviderModel.query.filter_by(provider_id=provider.id).all()
    }
    result = []
    for m in data or []:
        mid = m.get('id') or m.get('model_id')
        if not mid:
            continue
        result.append({
            'model_id': mid,
            'name': mid,
            'configured': mid in configured,
        })

    return jsonify({'code': 200, 'data': result})


@provider_bp.route('/<int:provider_id>/models/<int:model_id>', methods=['PUT'])
@jwt_required()
def update_model(provider_id, model_id):
    """更新已配置模型（启用/停用等）"""
    user_id = int(get_jwt_identity())
    pm = _get_own_model(model_id, user_id)
    if not pm or pm.provider_id != provider_id:
        return jsonify({'code': 404, 'message': '模型不存在'}), 404

    data = request.get_json() or {}
    if 'enabled' in data:
        pm.enabled = bool(data['enabled'])
    if 'name' in data and data.get('name'):
        pm.name = data['name'].strip()
    if 'vision' in data:
        pm.vision = bool(data['vision'])

    db.session.commit()
    return jsonify({'code': 200, 'message': '已更新', 'data': pm.to_dict()})


@provider_bp.route('/<int:provider_id>/models/<int:model_id>/test', methods=['POST'])
@jwt_required()
def test_model(provider_id, model_id):
    """测试已配置的某个模型连接是否正常"""
    user_id = int(get_jwt_identity())
    pm = _get_own_model(model_id, user_id)
    if not pm or pm.provider_id != provider_id:
        return jsonify({'code': 404, 'message': '模型不存在'}), 404

    provider = _get_own_provider(provider_id, user_id)
    try:
        ok, err = _chat_request_ok(provider, pm.model_id)
        if ok:
            return jsonify({'code': 200, 'message': '连接正常', 'data': {'ok': True}})
        return jsonify({'code': 500, 'message': f'连接失败: {err}'})
    except Exception as e:
        return jsonify({'code': 500, 'message': f'测试失败: {str(e)}'})


@provider_bp.route('/<int:provider_id>/models/<int:model_id>', methods=['DELETE'])
@jwt_required()
def delete_model(provider_id, model_id):
    """删除已配置模型"""
    user_id = int(get_jwt_identity())
    pm = _get_own_model(model_id, user_id)
    if not pm or pm.provider_id != provider_id:
        return jsonify({'code': 404, 'message': '模型不存在'}), 404

    db.session.delete(pm)
    db.session.commit()
    return jsonify({'code': 200, 'message': '已删除'})