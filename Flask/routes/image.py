"""图像生成路由 - 生成图像（支持 Agnes 厂商）

支持文生图 / 图生图：
  POST /api/image/generate
    body:
      prompt            必填，图片描述
      provider_id       可选，指定使用的图片配置；留空则用第一个启用的图片配置
      model             可选，指定配置内模型；留空用第一个启用模型
      references        [可选]，参考图列表（公网 URL 或 Data URI Base64），用于图生图
      resolution        可选，1K/2K/4K，覆盖配置默认
      aspect_ratio      可选，如 16:9，覆盖配置默认
      quality           可选，auto/low/medium/high，覆盖配置默认

未配置任何图片生成时，会回退使用 .env 中的共享免费 Key（IMAGE_FREE_*）生图/改图，
并每人限制 IMAGE_FREE_LIMIT 次（默认 10），超出后需用户自行配置 API Key。
"""
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from models import ModelProvider, ImageUsage
from extensions import db
from services.agnes_image import (
    generate_image, IMAGE_RESOLUTIONS, IMAGE_ASPECT_RATIOS, IMAGE_QUALITIES,
)

image_bp = Blueprint('image', __name__, url_prefix='/api/image')


def _get_image_provider(user_id, provider_id=None):
    """获取用户自定义的图片生成配置：优先指定 id（校验归属），否则取第一个启用的配置"""
    if provider_id:
        p = ModelProvider.query.filter_by(
            id=provider_id, user_id=user_id, provider_type='image'
        ).first()
        if p:
            return p
    return ModelProvider.query.filter_by(
        user_id=user_id, provider_type='image', enabled=True
    ).first()


class _FreeImageProvider:
    """由 .env 共享 Key 构造的免费图片服务对象（与 generate_image 兼容，简化版）。"""

    def __init__(self):
        self.api_url = current_app.config.get('IMAGE_FREE_API_URL') or 'https://apihub.agnes-ai.cn/v1'
        self.api_key = current_app.config.get('IMAGE_FREE_API_KEY') or ''
        self.model = current_app.config.get('IMAGE_FREE_MODEL') or 'agnes-image-2.1-flash'
        self.models = []  # generate_image 通过 pick_enabled_model 取模型时返回 None

    def get_params(self):
        return {}


def _free_limit():
    return int(current_app.config.get('IMAGE_FREE_LIMIT') or 10)


def _usage_row(user_id):
    return ImageUsage.query.filter_by(user_id=user_id).first()


def _free_remaining(user_id):
    row = _usage_row(user_id)
    return max(_free_limit() - (row.free_count if row else 0), 0)


def _increment_free_usage(user_id):
    row = _usage_row(user_id)
    if row:
        row.free_count += 1
        row.updated_at = datetime.utcnow()
    else:
        db.session.add(ImageUsage(user_id=user_id, free_count=1))
    db.session.commit()


@image_bp.route('/generate', methods=['POST'])
@jwt_required()
def generate():
    """生成一张图像（文生图 / 图生图）"""
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}

    prompt = (data.get('prompt') or '').strip()
    if not prompt:
        return jsonify({'code': 400, 'message': '请填写图片描述'}), 400

    provider = _get_image_provider(user_id, data.get('provider_id'))
    is_free = False

    # 用户未配置图片生成时，回退到 .env 共享免费 Key
    if not provider:
        free_key = current_app.config.get('IMAGE_FREE_API_KEY') or ''
        if free_key:
            provider = _FreeImageProvider()
            is_free = True
        else:
            return jsonify({'code': 400, 'message': '请先在「模型配置-图片生成」中添加图片生成配置'}), 400

    # 免费额度校验：超限则拦截
    if is_free:
        limit = _free_limit()
        row = _usage_row(user_id)
        used = row.free_count if row else 0
        if used >= limit:
            return jsonify({
                'code': 403,
                'message': f'免费图片生成已达上限（{used}/{limit}），请前往「模型配置-图片生成」配置你自己的 API Key。',
                'data': {'free': True, 'used': used, 'limit': limit, 'remaining': 0},
            }), 403

    model = (data.get('model') or '').strip() or (provider.model if is_free else None)
    references = data.get('references') or []

    resolution = data.get('resolution')
    if resolution and resolution not in IMAGE_RESOLUTIONS:
        return jsonify({'code': 400, 'message': f'不支持的分辨率: {resolution}'}), 400
    aspect_ratio = data.get('aspect_ratio')
    # 使用共享免费 Key 生图/改图时默认 2:3（竖版，未单独指定比例）
    if aspect_ratio is None and is_free:
        aspect_ratio = '2:3'
    if aspect_ratio and aspect_ratio not in IMAGE_ASPECT_RATIOS:
        return jsonify({'code': 400, 'message': f'不支持的长宽比: {aspect_ratio}'}), 400
    quality = data.get('quality')
    if quality and quality not in IMAGE_QUALITIES:
        return jsonify({'code': 400, 'message': f'不支持的质量档: {quality}'}), 400

    image, err = generate_image(
        provider,
        prompt,
        model=model,
        reference_images=references if isinstance(references, list) else [],
        resolution=resolution,
        aspect_ratio=aspect_ratio,
        quality=quality,
    )
    if err:
        return jsonify({'code': 500, 'message': f'生成失败: {err}'}), 500

    used, limit = None, None
    if is_free:
        _increment_free_usage(user_id)
        used = _usage_row(user_id).free_count
        limit = _free_limit()

    payload = {
        'url': image,
        'provider_id': provider.id if not is_free else None,
        'model': model or provider.model,
        'provider_name': provider.name if not is_free else current_app.config.get('FREE_API_NAME', '免费 API'),
    }
    if is_free:
        payload['free'] = True
        payload['used'] = used
        payload['limit'] = limit
        payload['remaining'] = max(limit - used, 0)

    return jsonify({'code': 200, 'message': '生成成功', 'data': payload})