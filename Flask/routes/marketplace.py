"""人设广场路由 - 分享、投票、评论"""
import hashlib
from datetime import date, datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models import (
    PersonaMarketplace, MarketplaceVote, MarketplaceComment,
    CommentLike, DailyCheckIn, ImageUsage, User, Conversation,
)

marketplace_bp = Blueprint('marketplace', __name__, url_prefix='/api/marketplace')


# ── 确定性假名生成 ──────────────────────────────────────────────
ADJECTIVES = [
    "温柔的", "安静的", "明亮的", "慵懒的", "清澈的", "柔软的", "沉静的", "温暖的",
    "飘逸的", "朦胧的", "恬淡的", "悠然的", "细腻的", "淡雅的", "宁静的", "从容的",
    "洒脱的", "纯粹的", "含蓄的", "自在的", "通透的", "轻盈的", "温润的", "素雅的",
    "空灵的", "清冽的", "和煦的", "微醺的", "散漫的", "疏朗的", "澄澈的", "恬静的",
    "旷达的", "隽永的", "灵动的", "朴素的", "萧然的", "静谧的", "朗润的", "闲适的",
    "淡泊的", "雅致的", "简净的", "舒展的", "清欢的", "默然的", "淡然的", "舒缓的",
    "幽远的", "平和的",
]

NOUNS = [
    "月亮", "旅人", "星辰", "晚风", "云朵", "山岚", "溪流", "落叶",
    "暮色", "晨光", "细雨", "薄雾", "飞鸟", "花影", "潮汐", "烟火",
    "树影", "钟声", "渡口", "归舟", "远山", "白露", "青苔", "竹笛",
    "纸鸢", "灯火", "长亭", "古道", "清泉", "孤帆", "残雪", "新芽",
    "晚霞", "星河", "浮云", "落花", "流水", "寒梅", "幽兰", "翠竹",
    "松涛", "鹤鸣", "蝉声", "萤火", "朝露", "夕照", "春风", "秋月",
    "夏雨", "冬雪", "晓星", "夜莺",
]


def _pseudonym_for(user_id, persona_id):
    """根据 user_id + persona_id 生成确定性假名（同一用户在同人设卡下始终相同）"""
    seed = hashlib.sha256(f"{user_id}:{persona_id}:name".encode()).hexdigest()
    adj_idx = int(seed[:8], 16) % len(ADJECTIVES)
    noun_idx = int(seed[8:16], 16) % len(NOUNS)
    return f"{ADJECTIVES[adj_idx]}{NOUNS[noun_idx]}"


def _identicon_seed_for(user_id, persona_id):
    """生成确定性 identicon seed"""
    return hashlib.sha256(f"{user_id}:{persona_id}:icon".encode()).hexdigest()[:16]


# ── 列表 ────────────────────────────────────────────────────────
@marketplace_bp.route('', methods=['GET'])
@jwt_required()
def list_marketplace():
    """获取人设广场列表，按 score 排序"""
    sort = request.args.get('sort', 'hot')  # hot / new
    page = int(request.args.get('page', 1))
    per_page = min(int(request.args.get('per_page', 20)), 50)

    query = PersonaMarketplace.query
    if sort == 'new':
        query = query.order_by(PersonaMarketplace.created_at.desc())
    else:
        query = query.order_by(
            (PersonaMarketplace.likes - PersonaMarketplace.dislikes).desc(),
            PersonaMarketplace.created_at.desc(),
        )

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        'code': 200,
        'data': {
            'items': [p.to_dict() for p in pagination.items],
            'total': pagination.total,
            'page': page,
            'pages': pagination.pages,
        }
    })


# ── 详情 ────────────────────────────────────────────────────────
@marketplace_bp.route('/<int:pid>', methods=['GET'])
@jwt_required()
def get_marketplace_persona(pid):
    persona = PersonaMarketplace.query.get(pid)
    if not persona:
        return jsonify({'code': 404, 'message': '人设不存在'}), 404
    return jsonify({'code': 200, 'data': persona.to_dict(include_prompt=True)})


# ── 发布 ────────────────────────────────────────────────────────
@marketplace_bp.route('', methods=['POST'])
@jwt_required()
def publish_persona():
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    system_prompt = (data.get('system_prompt') or '').strip()
    if not name or not system_prompt:
        return jsonify({'code': 400, 'message': '名称和提示词不能为空'}), 400

    persona = PersonaMarketplace(
        user_id=user_id,
        name=name,
        description=(data.get('description') or '').strip() or None,
        avatar=data.get('avatar'),
        system_prompt=system_prompt,
        greeting=(data.get('greeting') or '').strip() or None,
    )
    db.session.add(persona)
    db.session.commit()
    return jsonify({'code': 200, 'message': '发布成功', 'data': persona.to_dict()})


# ── 投票 ────────────────────────────────────────────────────────
@marketplace_bp.route('/<int:pid>/vote', methods=['POST'])
@jwt_required()
def vote_persona(pid):
    user_id = int(get_jwt_identity())
    persona = PersonaMarketplace.query.get(pid)
    if not persona:
        return jsonify({'code': 404, 'message': '人设不存在'}), 404

    data = request.get_json() or {}
    vote_type = data.get('vote_type')
    if vote_type not in ('like', 'dislike'):
        return jsonify({'code': 400, 'message': '无效的投票类型'}), 400

    existing = MarketplaceVote.query.filter_by(persona_id=pid, user_id=user_id).first()
    if existing:
        if existing.vote_type == vote_type:
            return jsonify({'code': 200, 'message': '已投过', 'data': persona.to_dict()})
        old = existing.vote_type
        existing.vote_type = vote_type
        if old == 'like':
            persona.likes = max(0, persona.likes - 1)
        else:
            persona.dislikes = max(0, persona.dislikes - 1)
    else:
        db.session.add(MarketplaceVote(persona_id=pid, user_id=user_id, vote_type=vote_type))

    if vote_type == 'like':
        persona.likes += 1
    else:
        persona.dislikes += 1

    db.session.commit()
    return jsonify({'code': 200, 'data': persona.to_dict()})


# ── 添加到我的角色 ──────────────────────────────────────────────
@marketplace_bp.route('/<int:pid>/adopt', methods=['POST'])
@jwt_required()
def adopt_persona(pid):
    from models import PersonaTemplate
    user_id = int(get_jwt_identity())
    persona = PersonaMarketplace.query.get(pid)
    if not persona:
        return jsonify({'code': 404, 'message': '人设不存在'}), 404

    tp = PersonaTemplate(
        user_id=user_id,
        name=persona.name,
        description=f"[来自人设广场] {persona.description or ''}",
        avatar=persona.avatar,
        system_prompt=persona.system_prompt,
        greeting=persona.greeting,
        is_default=False,
        is_system=False,
        persona_type='ai',
    )
    db.session.add(tp)
    db.session.commit()
    return jsonify({'code': 200, 'message': '已添加到我的角色', 'data': tp.to_dict()})


# ── 评论列表 ────────────────────────────────────────────────────
@marketplace_bp.route('/<int:pid>/comments', methods=['GET'])
@jwt_required()
def list_comments(pid):
    sort = request.args.get('sort', 'hot')  # hot / new
    page = int(request.args.get('page', 1))
    per_page = min(int(request.args.get('per_page', 30)), 100)

    query = MarketplaceComment.query.filter_by(persona_id=pid)
    if sort == 'new':
        query = query.order_by(MarketplaceComment.created_at.desc())
    else:
        query = query.order_by(MarketplaceComment.likes.desc(), MarketplaceComment.created_at.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    items = []
    for c in pagination.items:
        items.append(c.to_dict(
            pseudonym=_pseudonym_for(c.user_id, pid),
            identicon_seed=_identicon_seed_for(c.user_id, pid),
        ))
    return jsonify({
        'code': 200,
        'data': {'items': items, 'total': pagination.total, 'page': page}
    })


# ── 发表评论 ────────────────────────────────────────────────────
@marketplace_bp.route('/<int:pid>/comments', methods=['POST'])
@jwt_required()
def add_comment(pid):
    user_id = int(get_jwt_identity())
    persona = PersonaMarketplace.query.get(pid)
    if not persona:
        return jsonify({'code': 404, 'message': '人设不存在'}), 404

    data = request.get_json() or {}
    content = (data.get('content') or '').strip()
    if not content:
        return jsonify({'code': 400, 'message': '评论内容不能为空'}), 400
    if len(content) > 500:
        return jsonify({'code': 400, 'message': '评论最多500字'}), 400

    comment = MarketplaceComment(persona_id=pid, user_id=user_id, content=content)
    db.session.add(comment)
    db.session.commit()
    return jsonify({
        'code': 200,
        'message': '评论成功',
        'data': comment.to_dict(
            pseudonym=_pseudonym_for(user_id, pid),
            identicon_seed=_identicon_seed_for(user_id, pid),
        )
    })


# ── 评论点赞 ────────────────────────────────────────────────────
@marketplace_bp.route('/comments/<int:cid>/like', methods=['POST'])
@jwt_required()
def like_comment(cid):
    user_id = int(get_jwt_identity())
    comment = MarketplaceComment.query.get(cid)
    if not comment:
        return jsonify({'code': 404, 'message': '评论不存在'}), 404

    existing = CommentLike.query.filter_by(comment_id=cid, user_id=user_id).first()
    if existing:
        return jsonify({'code': 200, 'message': '已点赞过'})

    db.session.add(CommentLike(comment_id=cid, user_id=user_id))
    comment.likes += 1
    db.session.commit()
    return jsonify({'code': 200, 'data': {'likes': comment.likes}})


# ── 每日签到 ────────────────────────────────────────────────────
@marketplace_bp.route('/checkin', methods=['POST'])
@jwt_required()
def daily_checkin():
    user_id = int(get_jwt_identity())
    today = date.today()

    existing = DailyCheckIn.query.filter_by(user_id=user_id, checkin_date=today).first()
    if existing:
        return jsonify({'code': 200, 'message': '今日已签到', 'data': {'already': True}})

    checkin = DailyCheckIn(user_id=user_id, checkin_date=today, bonus_images=5)
    db.session.add(checkin)

    usage = ImageUsage.query.filter_by(user_id=user_id).first()
    if not usage:
        usage = ImageUsage(user_id=user_id, free_count=0)
        db.session.add(usage)
    usage.free_count = (usage.free_count or 0) + 5

    db.session.commit()
    return jsonify({
        'code': 200,
        'message': '签到成功，获得5次免费生图机会',
        'data': {'already': False, 'bonus': 5, 'remaining': usage.free_count}
    })


@marketplace_bp.route('/checkin/status', methods=['GET'])
@jwt_required()
def checkin_status():
    user_id = int(get_jwt_identity())
    today = date.today()
    checked = DailyCheckIn.query.filter_by(user_id=user_id, checkin_date=today).first() is not None
    usage = ImageUsage.query.filter_by(user_id=user_id).first()
    return jsonify({
        'code': 200,
        'data': {
            'checked_today': checked,
            'remaining_images': usage.free_count if usage else 0,
        }
    })
