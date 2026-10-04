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
      conversation_id   可选，所在对话；传入后本轮生图会写入对话历史
      reference_url     可选，改图参考图的服务器 URL，用于聊天记录留档

未配置任何图片生成时，会回退使用 .env 中的共享免费 Key（IMAGE_FREE_*）生图/改图，
并每人限制 IMAGE_FREE_LIMIT 次（默认 10），超出后需用户自行配置 API Key。
注意：免费额度只约束「共享免费 Key」，用户自己的 Key 生图不受次数限制。
"""
import base64 as _b64

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from sqlalchemy import update
from models import ModelProvider, ImageUsage, Conversation, Message, local_now
from extensions import db
from services.agnes_image import (
    generate_image, IMAGE_RESOLUTIONS, IMAGE_ASPECT_RATIOS, IMAGE_QUALITIES,
)
from services.ssrf import validate_reference_images
from services.rate_limit import rate_limit
from services.upload_guard import detect_image_type
from routes.upload import save_image_bytes

image_bp = Blueprint('image', __name__, url_prefix='/api/image')

# 图片描述长度上限，避免超长 prompt 撑爆上游请求体 / 超出模型上下文
MAX_PROMPT_LEN = 1500


def _get_image_provider(user_id, provider_id=None):
    """挑选本次生图使用的图片配置。

    优先级按用户直觉来（「我配好了就应该用我配的」）：
      1. 显式指定的 provider_id（校验归属）
      2. 第一个「已启用」的图片配置
      3. 有配置但一个都没启用时，仍然用配置本身（默认配置优先，其次最近新增的）
      4. 一条配置都没有 → 返回 None，由上层回退到共享免费 Key

    第 3 条是踩过坑之后加的：图片配置的「启用」开关藏在配置列表里的小开关上，
    很容易配好 Key、测试连接也成功，却因为没拨开关而静默落到共享免费通道，
    最终表现成「配好了却生不了图」。有配置就优先用配置，比默默用免费通道更有用。
    """
    if provider_id:
        p = ModelProvider.query.filter_by(
            id=provider_id, user_id=user_id, provider_type='image'
        ).first()
        if p:
            return p

    enabled = ModelProvider.query.filter_by(
        user_id=user_id, provider_type='image', enabled=True
    ).order_by(ModelProvider.is_default.desc(), ModelProvider.id.desc()).first()
    if enabled:
        return enabled

    return ModelProvider.query.filter_by(
        user_id=user_id, provider_type='image'
    ).order_by(ModelProvider.is_default.desc(), ModelProvider.id.desc()).first()


class _FreeImageProvider:
    """由 .env 共享 Key 构造的免费图片服务对象（与 generate_image 兼容，简化版）。"""

    def __init__(self):
        self.api_url = current_app.config.get('IMAGE_FREE_API_URL') or 'https://api.agnes-ai.cn/v1'
        self.api_key = current_app.config.get('IMAGE_FREE_API_KEY') or ''
        self.model = current_app.config.get('IMAGE_FREE_MODEL') or 'agnes-image-2.1-flash'
        self.models = []  # generate_image 通过 pick_enabled_model 取模型时返回 None

    def get_params(self):
        return {}


def _free_limit():
    return int(current_app.config.get('IMAGE_FREE_LIMIT') or 5)


def _no_provider_hint():
    """一条图片配置都没有时的提示（走共享免费通道或提示去配置）。"""
    return '请先在「模型配置-图片生成」中添加图片生成配置'


def _provider_name(provider):
    """配置名（免费通道没有名字，统一叫「共享免费通道」）。"""
    return getattr(provider, 'name', None) or '共享免费通道'


def _usage_row(user_id):
    return ImageUsage.query.filter_by(user_id=user_id).first()


def _free_remaining(user_id):
    """返回剩余免费生图次数。free_count 为剩余次数语义。"""
    row = _usage_row(user_id)
    return max(row.free_count if row else _free_limit(), 0)


def _ensure_usage_row(user_id):
    """获取或初始化 ImageUsage 行；新用户默认拥有完整免费额度（5 次）。"""
    row = _usage_row(user_id)
    if not row:
        row = ImageUsage(user_id=user_id, free_count=_free_limit(), is_remaining_semantics=True)
        db.session.add(row)
        try:
            db.session.commit()
        except Exception:
            # 并发下另一请求可能已插入同一 user_id 的行，回滚后重新读取即可
            db.session.rollback()
            row = _usage_row(user_id)
    return row


def _consume_free_usage(user_id):
    """原子消耗一次免费额度：``free_count = free_count - 1 WHERE free_count > 0``。

    返回消耗后的剩余次数；额度已耗尽（并发下被其他请求抢先扣完）返回 None。
    使用 ``UPDATE ... WHERE free_count > 0`` 保证并发安全，避免先读后写的超额消耗。
    """
    _ensure_usage_row(user_id)
    result = db.session.execute(
        update(ImageUsage)
        .where(ImageUsage.user_id == user_id, ImageUsage.free_count > 0)
        .values(free_count=ImageUsage.free_count - 1, updated_at=local_now())
    )
    db.session.commit()
    if not result.rowcount:
        return None
    remaining = _free_remaining(user_id)
    return remaining


def _persist_reference(ref, user_id):
    """把参考图转成可长期访问的服务器 URL。

    - data URI：解出字节后落盘（后端兜底，防止前端未上传导致参考图丢失）；
    - http(s) 公网地址：直接沿用（本来就是可访问 URL）；
    - 其他：返回 None。

    落盘失败返回 None —— 调用方据此放弃「参考图留档」，但不影响生图本身。
    """
    if not ref or not isinstance(ref, str):
        return None
    if ref.startswith('data:'):
        try:
            _header, _, payload = ref.partition(',')
            raw = _b64.b64decode(payload, validate=False)
        except Exception:
            return None
        if not raw:
            return None
        ext = detect_image_type(raw) or 'jpg'
        return save_image_bytes(raw, ext, user_id)
    if ref.startswith('http://') or ref.startswith('https://'):
        return ref
    return None


def _persist_image_messages(user_id, conversation_id, prompt, image_url, reference_url=None):
    """把生图/改图这一轮（用户 prompt + 生成结果）写进对话历史。

    此前 generate() 只扣额度、完全不落 Message，导致生图/改图整段对话
    切走后全部消失。这里补齐落库：

    - 写两条：user（prompt + 参考图 URL）与 assistant（生成图 URL）；
    - assistant 的 content 列 NOT NULL，用空串占位，前端按 image_url 渲染；
    - 幂等：按「最后一条同角色消息」比对，前端重试不会插重复；
    - 越权防护：只写当前用户自己的对话，他人对话直接返回 False。

    返回 True 表示已写入对话历史。
    """
    if not conversation_id:
        return False
    conv = Conversation.query.filter_by(id=conversation_id, user_id=user_id).first()
    if not conv:
        return False

    last_user = Message.query.filter_by(
        conversation_id=conv.id, role='user'
    ).order_by(Message.created_at.desc(), Message.id.desc()).first()
    if not (last_user is not None
            and last_user.content == prompt
            and (last_user.image_url or None) == (reference_url or None)):
        db.session.add(Message(
            conversation_id=conv.id, role='user',
            content=prompt, image_url=reference_url or None,
        ))

    last_ai = Message.query.filter_by(
        conversation_id=conv.id, role='assistant'
    ).order_by(Message.created_at.desc(), Message.id.desc()).first()
    if not (last_ai is not None and (last_ai.image_url or None) == (image_url or None)):
        db.session.add(Message(
            conversation_id=conv.id, role='assistant',
            content='', image_url=image_url,
        ))

    # 首条生图时把「新对话」标题更新为 prompt 摘要（与普通聊天一致）
    if conv.title in (None, '', '新对话'):
        conv.title = (prompt[:20] + '...') if len(prompt) > 20 else prompt

    return True


@image_bp.route('/generate', methods=['POST'])
@jwt_required()
def generate():
    """生成一张图像（文生图 / 图生图）"""
    user_id = int(get_jwt_identity())
    # 图片生成成本高：按用户限流，每分钟最多 10 次
    limited = rate_limit('image_generate', 10, 60, scope='user')
    if limited:
        return limited

    data = request.get_json() or {}

    prompt = (data.get('prompt') or '').strip()
    if not prompt:
        return jsonify({'code': 400, 'message': '请填写图片描述'}), 400
    if len(prompt) > MAX_PROMPT_LEN:
        return jsonify({'code': 400, 'message': f'图片描述过长（最多 {MAX_PROMPT_LEN} 字）'}), 400

    own_provider = _get_image_provider(user_id, data.get('provider_id'))

    # 没有可用配置时才回退共享免费 Key；用户自己的配置一律优先（哪怕它的启用开关是关着的，
    # 见 _get_image_provider 的优先级说明），否则就会出现「配好了却被免费通道拖垮」的假故障。
    if own_provider is not None and own_provider.enabled is False:
        current_app.logger.info(
            '[生图] 用户 %s 的图片配置「%s」未启用，仍按该配置生图（有配置优先于共享免费通道）',
            user_id, own_provider.name,
        )

    if not own_provider:
        free_key = current_app.config.get('IMAGE_FREE_API_KEY') or ''
        if not free_key:
            return jsonify({'code': 400, 'message': _no_provider_hint()}), 400
        provider = _FreeImageProvider()
    else:
        provider = own_provider

    is_free = own_provider is None

    # 免费额度校验只作用于「共享免费 Key」：
    # 用户配置了自己的 Key 生图，不该被每日免费次数拦住。
    remaining = _free_remaining(user_id)
    if is_free and remaining <= 0:
        return jsonify({
            'code': 403,
            'message': '今日免费生图次数已用完，请先签到或明日再试；也可配置自己的 Agnes API Key。',
            'data': {'free': is_free, 'remaining': 0},
        }), 403

    model = (data.get('model') or '').strip() or (provider.model if is_free else None)

    # 参考图校验：限制数量 / 体积，URL 必须是 http(s) 且通过 SSRF 校验，
    # 防止诱导第三方平台请求内网地址或用作外带数据通道
    try:
        references = validate_reference_images(
            data.get('references'),
            enabled=current_app.config.get('SSRF_PROTECTION', True),
        )
    except ValueError as e:
        return jsonify({'code': 400, 'message': str(e)}), 400

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
        reference_images=references,
        resolution=resolution,
        aspect_ratio=aspect_ratio,
        quality=quality,
    )
    if err:
        # 对外统一脱敏，避免透传上游厂商内部地址 / 配额 / 堆栈等敏感信息，
        # 但必须给出「接下来该做什么」：带上用的是哪条配置，用户才知道去改哪里。
        current_app.logger.error('图片生成失败 user=%s provider=%s: %s', user_id, _provider_name(provider), err)
        if is_free:
            message = (
                '图片生成失败：本次使用的是共享免费通道，但它当前不可用。'
                '请在「模型配置 → 图片生成」里填入自己的 API Key 后再试。'
            )
        else:
            message = (
                f'图片生成失败（使用的是配置「{_provider_name(provider)}」）：'
                '请检查该配置的 API Key、接口地址与模型名是否正确。'
            )
        return jsonify({'code': 500, 'message': message}), 500

    if is_free:
        remaining = _consume_free_usage(user_id)
        if remaining is None:
            # 并发下额度已耗尽：生成结果不回传，提示用户
            return jsonify({
                'code': 403,
                'message': '今日免费生图次数已用完，请先签到或明日再试；也可配置自己的 Agnes API Key。',
                'data': {'free': is_free, 'remaining': 0},
            }), 403
    else:
        # 自有 Key 不占用免费次数，仅读一次剩余用于日志
        remaining = _free_remaining(user_id)
        current_app.logger.info(
            '[生图] 用户 %s 使用自有配置「%s」生图，不占用免费次数（剩余 %s）',
            user_id, provider.name, remaining,
        )

    # 落库：把这一轮生图写进对话历史（参考图 data URI 在此兜底落盘）。
    # 失败只 warning 不影响返回 —— 图已生成、额度已消耗，不能让用户白等。
    conversation_id = data.get('conversation_id')
    if conversation_id:
        reference_url = _persist_reference(data.get('reference_url'), user_id)
        try:
            _persist_image_messages(user_id, conversation_id, prompt, image, reference_url)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.warning(
                '生图消息落库失败 user=%s conv=%s: %s', user_id, conversation_id, e,
            )

    payload = {
        'url': image,
        'provider_id': provider.id if not is_free else None,
        'model': model or provider.model,
        'provider_name': provider.name if not is_free else current_app.config.get('FREE_API_NAME', '免费 API'),
        'remaining': remaining,
        'free': is_free,
    }

    return jsonify({'code': 200, 'message': '生成成功', 'data': payload})
