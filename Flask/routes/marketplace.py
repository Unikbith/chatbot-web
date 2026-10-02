"""人设广场路由 - 分享、投票、评论"""
import hashlib
from datetime import date, datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models import (
    PersonaMarketplace, MarketplaceVote, MarketplaceComment,
    CommentLike, DailyCheckIn, ImageUsage, User,
    MarketplaceAdopt, local_now,
)
from sqlalchemy import func
from sqlalchemy.orm import joinedload

marketplace_bp = Blueprint('marketplace', __name__, url_prefix='/api/marketplace')


# ── 发布卡片字数限制 ──────────────────────────────────────────────
# 与「人物卡」（PersonaTemplate）保持一致，避免出现「人物卡能写 1000 字、
# 发布到广场却被拦下」的情况。系统提示词另设软上限：常规建议 10000 字，
# 确有需要时超出部分兜底到 50000 字。
PUB_NAME_MAX = 100
PUB_DESC_MIN = 30
PUB_DESC_MAX = 100
PUB_PROMPT_MIN = 100
PUB_PROMPT_SOFT_MAX = 10000
PUB_PROMPT_MAX = 50000
PUB_GREETING_MAX = 100


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


def _is_adopted(marketplace_id, user_id):
    """该卡片是否已被用户添加（ adopt 记录存在且对应人物卡未被删除）"""
    adopt = MarketplaceAdopt.query.filter_by(
        persona_id=marketplace_id, user_id=user_id
    ).first()
    if not adopt:
        return False
    # 人物卡已被删除时视为未添加，前端可重新添加
    from models import PersonaTemplate
    return PersonaTemplate.query.get(adopt.template_id) is not None


def _adjust_persona_counters(pid, like_delta=0, dislike_delta=0):
    """原子调整卡片点赞/点踩计数（``UPDATE ... SET x = MAX(0, x + delta)``）。

    并发下多个请求同时投票时，先读后写会产生计数漂移；这里直接用 SQL 表达式
    在数据库端完成自增/自减，保证一致性。
    """
    from sqlalchemy import case, func as _func
    values = {}
    if like_delta:
        values['likes'] = case(
            (PersonaMarketplace.likes + like_delta < 0, 0),
            else_=PersonaMarketplace.likes + like_delta,
        )
    if dislike_delta:
        values['dislikes'] = case(
            (PersonaMarketplace.dislikes + dislike_delta < 0, 0),
            else_=PersonaMarketplace.dislikes + dislike_delta,
        )
    if not values:
        return
    db.session.execute(
        db.update(PersonaMarketplace)
        .where(PersonaMarketplace.id == pid)
        .values(**values)
    )


# ── 系统默认卡片：保证默认人设始终存在于卡片广场 ────────────────
# 进程级一次性标记：系统卡补录是全局数据维护，每个请求都跑会白白多出
# 多次 SELECT（甚至 UPDATE），列表接口首当其冲变慢。进程内跑过一次即可。
_system_cards_ensured = False


def ensure_system_cards():
    """幂等：把系统默认人设（加藤惠、陆驰、苏晚晴、沈砚）补录进卡片广场。
    作者挂到最早注册的管理员（或最早的注册用户）名下，仅创建缺失项。
    已存在的同名系统卡若仍是旧版提示词（缺少【与用户的关系】章节），一并升级。"""
    global _system_cards_ensured
    if _system_cards_ensured:
        return

    from models import PersonaTemplate  # noqa: F401  (保持依赖显式)
    from routes.auth import _PERSONA_PROMPTS, _DEFAULT_AVATARS, _PRESET_GENDERS

    names = list(_PERSONA_PROMPTS.keys())
    cards = {
        c.name: c
        for c in PersonaMarketplace.query.filter(PersonaMarketplace.name.in_(names)).all()
    }

    author = User.query.order_by(User.id.asc()).first()
    if author is None:
        return

    dirty = False
    for name, info in _PERSONA_PROMPTS.items():
        card = cards.get(name)
        if card is None:
            db.session.add(
                PersonaMarketplace(
                    user_id=author.id,
                    name=name,
                    description=info.get('description') or '',
                    avatar=_DEFAULT_AVATARS.get(name),
                    system_prompt=info.get('system_prompt') or '',
                    greeting=info.get('greeting') or '',
                    gender=_PRESET_GENDERS.get(name),
                )
            )
            dirty = True
        elif '【与用户的关系】' not in (card.system_prompt or ''):
            # 旧版提示词且未被用户改动过（新版统一含该章节），升级到新版
            card.system_prompt = info.get('system_prompt') or card.system_prompt
            card.greeting = info.get('greeting') or card.greeting
            card.description = info.get('description') or card.description
            if not card.gender:
                card.gender = _PRESET_GENDERS.get(name)
            dirty = True
    if dirty:
        db.session.commit()
    # 成功跑完才置标记：首次执行失败（如数据库暂不可用）时下次请求仍可重试
    _system_cards_ensured = True


def ensure_system_adopts(user_id):
    """把默认人物卡（加藤惠 / 陆驰 / 苏晚晴 / 沈砚）与卡片广场中的同名卡片关联。

    效果：这些人物卡既出现在卡片广场，又默认处于「已添加」状态，
    并在人物卡管理中带上「卡片广场」来源标签。仅补齐缺失记录，幂等。
    注意：只处理用户自己的默认人物卡（is_default），用户自行创建的同名卡片不参与。
    """
    from models import PersonaTemplate
    from routes.auth import _PERSONA_PROMPTS, _DEFAULT_AVATARS

    names = list(_PERSONA_PROMPTS.keys())
    cards = {
        c.name: c
        for c in PersonaMarketplace.query.filter(PersonaMarketplace.name.in_(names)).all()
    }
    if not cards:
        return

    # 只认「默认人物卡」：注册时创建的 4 张默认卡之一（性别决定其中一张为默认）
    templates = PersonaTemplate.query.filter(
        PersonaTemplate.user_id == user_id,
        PersonaTemplate.name.in_(list(cards.keys())),
    ).all()

    changed = False
    for tp in templates:
        card = cards.get(tp.name)
        if not card:
            continue

        # 该用户是否拥有同名「默认卡」：默认卡自身，或它是 4 张预设之一
        # （预设卡注册即生成，删掉后不再补，因此以 is_default 或历史无 adopt 的方式判定）
        if not tp.is_default and MarketplaceAdopt.query.filter_by(
            template_id=tp.id, user_id=user_id
        ).first() is None:
            # 用户自建的同名卡片，不参与默认关联
            if tp.created_at and card.created_at and tp.created_at > card.created_at:
                continue

        # 补齐默认人物卡的头像 / 开场白（历史数据可能为空）
        info = _PERSONA_PROMPTS.get(tp.name) or {}
        if not tp.avatar and _DEFAULT_AVATARS.get(tp.name):
            tp.avatar = _DEFAULT_AVATARS.get(tp.name)
            changed = True
        if not tp.greeting and info.get('greeting'):
            tp.greeting = info.get('greeting')
            changed = True

        adopt = MarketplaceAdopt.query.filter_by(persona_id=card.id, user_id=user_id).first()
        if adopt:
            # 人物卡被删除后重新生成时，修正 adopt 指向
            if adopt.template_id != tp.id:
                adopt.template_id = tp.id
                changed = True
            continue
        db.session.add(MarketplaceAdopt(persona_id=card.id, user_id=user_id, template_id=tp.id))
        changed = True

    if changed:
        db.session.commit()


def _apply_gender_filter(query, gender_tag):
    """按性别标签筛选人物卡。

    - 「男」/「女」：精确匹配
    - 「非二元」：所有非男/女的值（含未填写），用于总览
    - 其他值：当作自定义性别精确匹配（如「神秘」「双性」「无性别」）

    自定义性别单独可选后，用户能在广场里筛出自己填的具体值，
    而不是只能看到一个笼统的「非二元」。
    """
    if not gender_tag:
        return query
    if gender_tag in ('男', '女'):
        return query.filter(PersonaMarketplace.gender == gender_tag)
    if gender_tag == '非二元':
        return query.filter(
            db.or_(
                PersonaMarketplace.gender.is_(None),
                PersonaMarketplace.gender.notin_(['男', '女']),
            )
        )
    return query.filter(PersonaMarketplace.gender == gender_tag)


@marketplace_bp.route('/genders', methods=['GET'])
def list_marketplace_genders():
    """返回广场中各性别标签的卡片数量，供筛选下拉只渲染有数据的选项。

    为什么不固定返回男/女/非二元：
    - 用户可发布任意自定义性别（「双性」「无性别」「神秘」…），只给固定三项
      这些卡片永远筛不出来；
    - 反过来，没有对应卡片的性别也不该出现在下拉里（点了就是空列表）。

    返回 {标签: 数量}，含「男」「女」与自定义值；「非二元」为总览项
    （所有非男/女的卡片，含未填写），数量为 0 时前端不渲染。
    """
    try:
        ensure_system_cards()
    except Exception:
        db.session.rollback()
    rows = (
        db.session.query(PersonaMarketplace.gender, func.count())
        .group_by(PersonaMarketplace.gender)
        .all()
    )
    counts = {}
    non_binary = 0
    for gender, cnt in rows:
        g = (gender or '').strip()
        if g in ('男', '女'):
            counts[g] = counts.get(g, 0) + cnt
        else:
            # 非男/女（含未填写）计入非二元总览；若填了具体值也单独记一份，
            # 这样「双性」既能单独筛选，也能出现在非二元总览里
            non_binary += cnt
            if g:
                counts[g] = counts.get(g, 0) + cnt
    counts['非二元'] = non_binary
    return jsonify({'code': 200, 'data': {'genders': counts}})


# ── 公开卡片列表（用于未登录入口页） ──────────────────────────────
@marketplace_bp.route('/public', methods=['GET'])
def list_marketplace_public():
    """未登录用户浏览卡片广场的公开接口：不依赖 JWT，不暴露「是否已采用」「我的投票」。

    入口页 / 落地页拉取该接口即可在登录前展示卡片网格；点击卡片进入详情后，
    详情接口走公开版本（/public/<id>），采纳等操作仍要求登录。

    排序 sort：
      - hot：赞比例 + 总赞数 + 时间（最热）
      - new：按发布时间倒序
      - most_likes：点赞数最多
      - most_comments：评论数最多
      - most_disliked：「最不受欢迎」= 踩数明显多于赞数的卡片优先；
        计算 dislike_ratio = dislikes / (likes + dislikes + 1)，
        按 ratio desc + dislikes desc 排序，让踩远多于赞的卡片排在前面
    """
    from models import PersonaMarketplace  # noqa: F401

    sort = request.args.get('sort', 'hot')
    page = int(request.args.get('page', 1))
    per_page = min(int(request.args.get('per_page', 50)), 100)
    keyword = request.args.get('q', '').strip()
    gender_tag = request.args.get('gender', '').strip()

    # joinedload author：to_dict 读 author.username，避免逐卡片懒加载（N+1）
    query = PersonaMarketplace.query.options(joinedload(PersonaMarketplace.author))
    if keyword:
        query = query.filter(
            db.or_(
                PersonaMarketplace.name.ilike(f'%{keyword}%'),
                PersonaMarketplace.description.ilike(f'%{keyword}%'),
            )
        )
    query = _apply_gender_filter(query, gender_tag)

    query = _apply_marketplace_sort(query, sort)

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    items = [p.to_dict() for p in pagination.items]

    return jsonify({
        'code': 200,
        'data': {
            'items': items,
            'total': pagination.total,
            'page': page,
            'pages': pagination.pages,
        }
    })


@marketplace_bp.route('/public/<int:pid>', methods=['GET'])
def get_marketplace_persona_public(pid):
    """未登录用户查看卡片详情：不暴露 user_vote / is_adopted，但保留创作者假名信息。"""
    persona = PersonaMarketplace.query.get(pid)
    if not persona:
        return jsonify({'code': 404, 'message': '人设不存在'}), 404
    d = persona.to_dict(include_prompt=True)
    d['creator_pseudonym'] = _pseudonym_for(persona.user_id, pid)
    d['creator_identicon_seed'] = _identicon_seed_for(persona.user_id, pid)
    return jsonify({'code': 200, 'data': d})


@marketplace_bp.route('/public/<int:pid>/comments', methods=['GET'])
def list_comments_public(pid):
    """未登录用户查看卡片评论：只读，不暴露点赞状态，使用假名。"""
    sort = request.args.get('sort', 'hot')  # hot / new
    page = int(request.args.get('page', 1))
    per_page = min(int(request.args.get('per_page', 30)), 100)

    persona = PersonaMarketplace.query.get(pid)
    if not persona:
        return jsonify({'code': 404, 'message': '人设不存在'}), 404

    query = MarketplaceComment.query.filter_by(persona_id=pid)
    if sort == 'new':
        query = query.order_by(MarketplaceComment.created_at.desc())
    else:
        query = query.order_by(MarketplaceComment.likes.desc(), MarketplaceComment.created_at.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    def _pack(c):
        return {
            'id': c.id,
            'content': c.content,
            'likes': c.likes,
            'pseudonym': _pseudonym_for(c.user_id, pid),
            'identicon_seed': _identicon_seed_for(c.user_id, pid),
            'created_at': c.created_at.isoformat() if c.created_at else None,
        }

    items = [_pack(c) for c in pagination.items]
    return jsonify({
        'code': 200,
        'data': {'items': items, 'total': pagination.total, 'page': page}
    })


def _apply_marketplace_sort(query, sort):
    """按 sort 取值给 query 套 order_by。

    支持排序：
      - new：created_at 倒序
      - hot：赞比例（likes / (likes+dislikes+1)）降序、总赞数兜底
      - most_likes：likes 倒序
      - most_comments：评论数倒序（用子查询聚合，避免 N+1）
      - most_disliked：踩赞比例倒序（dislikes 远多于 likes），ratio = dislikes / (likes+dislikes+1)
    """
    from models import PersonaMarketplace, MarketplaceComment

    if sort == 'new':
        return query.order_by(PersonaMarketplace.created_at.desc())

    if sort == 'most_likes':
        return query.order_by(
            PersonaMarketplace.likes.desc(),
            PersonaMarketplace.created_at.desc(),
        )

    if sort == 'most_comments':
        # 子查询：每张卡片的评论数（顶层，不含已删除场景）
        cmt_count = (
            db.session.query(
                MarketplaceComment.persona_id,
                func.count(MarketplaceComment.id),
            )
            .group_by(MarketplaceComment.persona_id)
            .subquery()
        )
        return (
            query.outerjoin(cmt_count, cmt_count.c.persona_id == PersonaMarketplace.id)
            .order_by(
                cmt_count.c.count.desc().nulls_last(),
                PersonaMarketplace.likes.desc(),
                PersonaMarketplace.created_at.desc(),
            )
        )

    if sort == 'most_disliked':
        # 优先把「踩远多于赞」的卡片顶到前面；
        # ratio = dislikes / (likes+dislikes+1)，值越大越不受欢迎
        d_ratio = PersonaMarketplace.dislikes * 1.0 / (
            PersonaMarketplace.likes + PersonaMarketplace.dislikes + 1.0
        )
        return query.order_by(
            d_ratio.desc(),
            PersonaMarketplace.dislikes.desc(),
            PersonaMarketplace.created_at.desc(),
        )

    # 默认 hot：赞比例 + 总赞数 + 时间
    ratio = PersonaMarketplace.likes * 1.0 / (
        PersonaMarketplace.likes + PersonaMarketplace.dislikes + 1.0
    )
    return query.order_by(
        ratio.desc(),
        PersonaMarketplace.likes.desc(),
        PersonaMarketplace.created_at.desc(),
    )


# ── 列表 ────────────────────────────────────────────────────────
@marketplace_bp.route('', methods=['GET'])
@jwt_required()
def list_marketplace():
    """获取人设广场列表，支持多种排序（详见 _apply_marketplace_sort）。

    sort: hot / new / most_likes / most_comments / most_disliked
    """
    user_id = int(get_jwt_identity())
    sort = request.args.get('sort', 'hot')
    page = int(request.args.get('page', 1))
    per_page = min(int(request.args.get('per_page', 20)), 50)
    keyword = request.args.get('q', '').strip()
    # 性别筛选：男 / 女 / 非二元（自定义及未填写统一归入非二元）
    gender_tag = request.args.get('gender', '').strip()

    # 系统默认人物卡补录进卡片广场（幂等）
    try:
        ensure_system_cards()
        ensure_system_adopts(user_id)
    except Exception:
        db.session.rollback()

    # joinedload author：to_dict 序列化会读 author.username，
    # 不预取则每张卡片一次懒加载查询（N+1，一页 12 卡多出 12 次查询）
    query = PersonaMarketplace.query.options(joinedload(PersonaMarketplace.author))
    if keyword:
        query = query.filter(
            db.or_(
                PersonaMarketplace.name.ilike(f'%{keyword}%'),
                PersonaMarketplace.description.ilike(f'%{keyword}%'),
            )
        )
    query = _apply_gender_filter(query, gender_tag)

    query = _apply_marketplace_sort(query, sort)

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    page_items = pagination.items
    page_ids = [p.id for p in page_items]

    # 批量预取：避免逐卡片查询造成的 N+1（原实现每卡 3 次查询 → 3N+1）
    comment_counts = {}
    user_votes = {}
    adopted_ids = set()
    if page_ids:
        # 1) 评论数一次性聚合
        rows = (
            db.session.query(
                MarketplaceComment.persona_id, func.count(MarketplaceComment.id)
            )
            .filter(MarketplaceComment.persona_id.in_(page_ids))
            .group_by(MarketplaceComment.persona_id)
            .all()
        )
        comment_counts = {pid: cnt for pid, cnt in rows}

        # 2) 当前用户在本页卡片的投票一次性取回
        votes = MarketplaceVote.query.filter(
            MarketplaceVote.user_id == user_id,
            MarketplaceVote.persona_id.in_(page_ids),
        ).all()
        user_votes = {v.persona_id: v.vote_type for v in votes}

        # 3) 当前用户已采用（且对应人物卡仍存在）的卡片一次性取回
        adopts = MarketplaceAdopt.query.filter(
            MarketplaceAdopt.user_id == user_id,
            MarketplaceAdopt.persona_id.in_(page_ids),
        ).all()
        from models import PersonaTemplate
        template_ids = [a.template_id for a in adopts if a.template_id]
        alive_tpl_ids = set()
        if template_ids:
            alive_tpl_ids = {
                tid for (tid,) in db.session.query(PersonaTemplate.id)
                .filter(PersonaTemplate.id.in_(template_ids)).all()
            }
        adopted_ids = {
            a.persona_id for a in adopts if a.template_id in alive_tpl_ids
        }

    items = []
    for p in page_items:
        d = p.to_dict(comment_count=comment_counts.get(p.id, 0))
        d['comment_count'] = comment_counts.get(p.id, 0)
        d['user_vote'] = user_votes.get(p.id)
        d['is_adopted'] = p.id in adopted_ids
        items.append(d)

    return jsonify({
        'code': 200,
        'data': {
            'items': items,
            'total': pagination.total,
            'page': page,
            'pages': pagination.pages,
        }
    })


# ── 详情 ────────────────────────────────────────────────────────
@marketplace_bp.route('/<int:pid>', methods=['GET'])
@jwt_required()
def get_marketplace_persona(pid):
    user_id = int(get_jwt_identity())
    persona = PersonaMarketplace.query.get(pid)
    if not persona:
        return jsonify({'code': 404, 'message': '人设不存在'}), 404
    d = persona.to_dict(include_prompt=True)
    vote = MarketplaceVote.query.filter_by(persona_id=pid, user_id=user_id).first()
    d['user_vote'] = vote.vote_type if vote else None
    d['is_adopted'] = _is_adopted(pid, user_id)
    d['creator_pseudonym'] = _pseudonym_for(persona.user_id, pid)
    d['creator_identicon_seed'] = _identicon_seed_for(persona.user_id, pid)
    return jsonify({'code': 200, 'data': d})


# ── 发布 ────────────────────────────────────────────────────────
@marketplace_bp.route('', methods=['POST'])
@jwt_required()
def publish_persona():
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    description = (data.get('description') or '').strip()
    system_prompt = (data.get('system_prompt') or '').strip()
    greeting = (data.get('greeting') or '').strip()
    avatar = data.get('avatar')
    gender = (data.get('gender') or '').strip()
    if gender and len(gender) > 20:
        return jsonify({'code': 400, 'message': '性别自定义内容过长（最多20字）'}), 400

    if not name or not description or not system_prompt or not greeting or not avatar:
        return jsonify({'code': 400, 'message': '请按规范填写'}), 400
    # 字数上限与「人物卡」保持一致：名称/描述/开场白 1000，
    # 系统提示词软上限 10000，超出部分兜底到硬上限 50000
    if len(name) > PUB_NAME_MAX:
        return jsonify({'code': 400, 'message': f'名称最多 {PUB_NAME_MAX} 字'}), 400
    if len(description) < PUB_DESC_MIN or len(description) > PUB_DESC_MAX:
        return jsonify({
            'code': 400,
            'message': f'描述需 {PUB_DESC_MIN}-{PUB_DESC_MAX} 字（当前 {len(description)} 字）'
        }), 400
    if len(system_prompt) < PUB_PROMPT_MIN or len(system_prompt) > PUB_PROMPT_MAX:
        return jsonify({
            'code': 400,
            'message': (f'人设提示词至少 {PUB_PROMPT_MIN} 字'
                        f'（最多 {PUB_PROMPT_SOFT_MAX} 字，超出可到 {PUB_PROMPT_MAX} 字）')
        }), 400
    if len(greeting) > PUB_GREETING_MAX:
        return jsonify({'code': 400, 'message': f'开场白最多 {PUB_GREETING_MAX} 字'}), 400

    persona = PersonaMarketplace(
        user_id=user_id,
        name=name,
        description=description,
        avatar=avatar,
        system_prompt=system_prompt,
        greeting=greeting,
        gender=gender or None,
    )
    db.session.add(persona)
    db.session.commit()
    return jsonify({'code': 200, 'message': '发布成功', 'data': persona.to_dict()})


# ── 投票 ────────────────────────────────────────────────────────
@marketplace_bp.route('/<int:pid>/vote', methods=['POST'])
@jwt_required()
def vote_persona(pid):
    """人设卡片投票（支持「再次点击取消」）。

    行为：
      - 同类型再投：直接拒绝（返回 code=200 但 user_vote 不变，避免双重计票）
      - 不同类型切换：撤销旧投票 + 新增新投票（likes/dislikes 计数同步变化）
      - 未投过：直接 +1
      - 再次点击同一类型 -> 取消投票：likes/dislikes -1，user_vote 置 None
        前端需要在切换「目标投票类型」与「取消」时根据 user_vote 决定如何 POST。
        为简化前端交互，这里同时支持通过可选参数 ``toggle=true``：
        同一类型再次点击会自动撤销并返回最新状态。
    """
    user_id = int(get_jwt_identity())
    persona = PersonaMarketplace.query.get(pid)
    if not persona:
        return jsonify({'code': 404, 'message': '人设不存在'}), 404

    data = request.get_json() or {}
    vote_type = data.get('vote_type')
    if vote_type not in ('like', 'dislike'):
        return jsonify({'code': 400, 'message': '无效的投票类型'}), 400
    # 是否开启「再次点击即取消」语义；默认开启，与前端交互对齐
    toggle = bool(data.get('toggle', True))

    existing = MarketplaceVote.query.filter_by(persona_id=pid, user_id=user_id).first()

    if existing and toggle and existing.vote_type == vote_type:
        # 同一类型再次点击 → 取消投票（原子自减，避免并发下的计数漂移）
        db.session.delete(existing)
        _adjust_persona_counters(pid, like_delta=-1 if vote_type == 'like' else 0,
                                 dislike_delta=-1 if vote_type == 'dislike' else 0)
        db.session.commit()
        persona = PersonaMarketplace.query.get(pid)
        return jsonify({
            'code': 200,
            'message': '已取消投票',
            'data': {
                'likes': persona.likes,
                'dislikes': persona.dislikes,
                'user_vote': None,
            },
        })

    if existing:
        # 不同类型 → 旧 -1，新 +1
        old = existing.vote_type
        existing.vote_type = vote_type
        like_delta = (1 if vote_type == 'like' else 0) - (1 if old == 'like' else 0)
        dislike_delta = (1 if vote_type == 'dislike' else 0) - (1 if old == 'dislike' else 0)
        _adjust_persona_counters(pid, like_delta=like_delta, dislike_delta=dislike_delta)
    else:
        db.session.add(MarketplaceVote(persona_id=pid, user_id=user_id, vote_type=vote_type))
        _adjust_persona_counters(pid, like_delta=1 if vote_type == 'like' else 0,
                                 dislike_delta=1 if vote_type == 'dislike' else 0)

    db.session.commit()
    persona = PersonaMarketplace.query.get(pid)
    return jsonify({
        'code': 200,
        'message': '投票成功',
        'data': {
            'likes': persona.likes,
            'dislikes': persona.dislikes,
            'user_vote': vote_type,
        },
    })


# ── 添加到我的角色 ──────────────────────────────────────────────
@marketplace_bp.route('/<int:pid>/adopt', methods=['POST'])
@jwt_required()
def adopt_persona(pid):
    from models import PersonaTemplate
    user_id = int(get_jwt_identity())
    persona = PersonaMarketplace.query.get(pid)
    if not persona:
        return jsonify({'code': 404, 'message': '人设不存在'}), 404

    existing_adopt = MarketplaceAdopt.query.filter_by(persona_id=pid, user_id=user_id).first()
    if existing_adopt:
        # adopt 记录存在但对应人物卡已被删除 → 清理失效记录，允许重新添加
        existing_tp = PersonaTemplate.query.get(existing_adopt.template_id)
        if existing_tp is None:
            db.session.delete(existing_adopt)
            db.session.commit()
        else:
            return jsonify({
                'code': 200,
                'message': '已添加过该卡片',
                'data': {'already': True, 'template_id': existing_tp.id}
            })

    # 人物卡（AI 人设）数量上限
    ai_count = PersonaTemplate.query.filter_by(user_id=user_id, persona_type='ai').count()
    if ai_count >= 10:
        return jsonify({
            'code': 400,
            'message': '人物卡数量已达上限（10 个），请先删除部分人物卡'
        }), 400

    tp = PersonaTemplate(
        user_id=user_id,
        name=persona.name,
        description=persona.description or '',
        avatar=persona.avatar,
        system_prompt=persona.system_prompt,
        greeting=persona.greeting,
        is_default=False,
        persona_type='ai',
    )
    db.session.add(tp)
    db.session.flush()

    adopt = MarketplaceAdopt(persona_id=pid, user_id=user_id, template_id=tp.id)
    db.session.add(adopt)

    db.session.commit()
    return jsonify({'code': 200, 'message': '已添加到我的角色', 'data': tp.to_dict()})


# ── 删除（仅创建者） ────────────────────────────────────────────
@marketplace_bp.route('/<int:pid>', methods=['DELETE'])
@jwt_required()
def delete_persona(pid):
    user_id = int(get_jwt_identity())
    persona = PersonaMarketplace.query.get(pid)
    if not persona:
        return jsonify({'code': 404, 'message': '人设不存在'}), 404
    if persona.user_id != user_id:
        return jsonify({'code': 403, 'message': '只能删除自己发布的卡片'}), 403
    db.session.delete(persona)
    db.session.commit()
    return jsonify({'code': 200, 'message': '已删除'})


# ── 取消采用 ────────────────────────────────────────────────────
@marketplace_bp.route('/<int:pid>/unadopt', methods=['POST'])
@jwt_required()
def unadopt_persona(pid):
    user_id = int(get_jwt_identity())
    adopt = MarketplaceAdopt.query.filter_by(persona_id=pid, user_id=user_id).first()
    if adopt:
        db.session.delete(adopt)
        db.session.commit()
    return jsonify({'code': 200, 'message': '已取消采用'})


# ── 评论列表 ────────────────────────────────────────────────────
@marketplace_bp.route('/<int:pid>/comments', methods=['GET'])
@jwt_required()
def list_comments(pid):
    sort = request.args.get('sort', 'hot')  # hot / new
    page = int(request.args.get('page', 1))
    per_page = min(int(request.args.get('per_page', 30)), 100)

    user_id = int(get_jwt_identity())

    query = MarketplaceComment.query.filter_by(persona_id=pid)
    if sort == 'new':
        query = query.order_by(MarketplaceComment.created_at.desc())
    else:
        query = query.order_by(MarketplaceComment.likes.desc(), MarketplaceComment.created_at.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    rows = list(pagination.items)

    # 当前用户已点赞的评论
    liked_ids = set()
    if rows:
        liked_ids = {
            r[0] for r in db.session.query(CommentLike.comment_id).filter(
                CommentLike.user_id == user_id,
                CommentLike.comment_id.in_([c.id for c in rows]),
            ).all()
        }

    def _pack(c):
        return c.to_dict(
            pseudonym=_pseudonym_for(c.user_id, pid),
            identicon_seed=_identicon_seed_for(c.user_id, pid),
            liked=c.id in liked_ids,
        )

    items = [_pack(c) for c in rows]
    return jsonify({
        'code': 200,
        'data': {'items': items, 'total': pagination.total, 'page': page}
    })


# ── 发表评论 ────────────────────────────────────────────────────
@marketplace_bp.route('/<int:pid>/comments', methods=['POST'])
@jwt_required()
def add_comment(pid):
    """对人物卡发表评论（扁平，不支持回复评论）。"""
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

    comment = MarketplaceComment(
        persona_id=pid,
        user_id=user_id,
        content=content,
    )
    db.session.add(comment)
    db.session.commit()
    return jsonify({
        'code': 200,
        'message': '评论成功',
        'data': comment.to_dict(
            pseudonym=_pseudonym_for(user_id, pid),
            identicon_seed=_identicon_seed_for(user_id, pid),
            liked=False,
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

    # 点赞 / 取消点赞（同一条评论再次点击即取消）；计数用原子 UPDATE 避免并发漂移
    existing = CommentLike.query.filter_by(comment_id=cid, user_id=user_id).first()
    if existing:
        db.session.delete(existing)
        db.session.execute(
            db.update(MarketplaceComment)
            .where(MarketplaceComment.id == cid)
            .values(likes=func.max(0, MarketplaceComment.likes - 1))
        )
        db.session.commit()
        comment = MarketplaceComment.query.get(cid)
        return jsonify({
            'code': 200,
            'message': '已取消点赞',
            'data': {'likes': comment.likes, 'liked': False},
        })

    db.session.add(CommentLike(comment_id=cid, user_id=user_id))
    db.session.execute(
        db.update(MarketplaceComment)
        .where(MarketplaceComment.id == cid)
        .values(likes=MarketplaceComment.likes + 1)
    )
    db.session.commit()
    comment = MarketplaceComment.query.get(cid)
    return jsonify({
        'code': 200,
        'message': '已点赞',
        'data': {'likes': comment.likes, 'liked': True},
    })


# ── 每日签到 ────────────────────────────────────────────────────
@marketplace_bp.route('/checkin', methods=['POST'])
@jwt_required()
def daily_checkin():
    """每日签到：冷却 24h；签到后向 ImageUsage.free_count 增加 5 次剩余免费生图次数。

    设计：签到奖励直接累加「剩余免费生图次数」，不设上限；
    生图时优先使用用户自有的 Agnes 图片配置，未配置则回退到系统共享免费 Key，
    每次生图均消耗 1 次剩余次数。
    """
    user_id = int(get_jwt_identity())
    now = local_now()

    # 并发安全：先原子「抢占」签到窗口——仅当不存在近 24h 的签到记录时才插入。
    # 用带 EXISTS 条件的 INSERT ... SELECT 保证同一用户并发签到只有一个请求成功。
    from sqlalchemy import text as _text
    cutoff = now - timedelta(seconds=86400)
    existing = (
        db.session.query(DailyCheckIn.id)
        .filter(DailyCheckIn.user_id == user_id,
                DailyCheckIn.checkin_time > cutoff)
        .first()
    )
    if existing:
        last = DailyCheckIn.query.filter_by(user_id=user_id).order_by(
            DailyCheckIn.checkin_time.desc()).first()
        remaining = 86400 - (now - last.checkin_time).total_seconds()
        hours = int(remaining // 3600)
        minutes = int((remaining % 3600) // 60)
        return jsonify({'code': 400, 'message': f'签到冷却中，还需等待{hours}小时{minutes}分钟'}), 400

    bonus = 5

    usage = ImageUsage.query.filter_by(user_id=user_id).first()
    if not usage:
        usage = ImageUsage(user_id=user_id, free_count=0, is_remaining_semantics=True)
        db.session.add(usage)
        try:
            db.session.flush()
        except Exception:
            db.session.rollback()
            usage = ImageUsage.query.filter_by(user_id=user_id).first()

    # 原子累加签到奖励，避免并发下的先读后写
    db.session.execute(
        db.update(ImageUsage)
        .where(ImageUsage.user_id == user_id)
        .values(free_count=ImageUsage.free_count + bonus, updated_at=now)
    )

    checkin = DailyCheckIn(user_id=user_id, checkin_time=now, bonus_images=bonus)
    db.session.add(checkin)

    db.session.commit()
    usage = ImageUsage.query.filter_by(user_id=user_id).first()
    return jsonify({
        'code': 200,
        'message': f'签到成功，获得{bonus}次免费生图机会',
        'data': {'bonus': bonus, 'free_images': usage.free_count if usage else bonus}
    })


@marketplace_bp.route('/checkin/status', methods=['GET'])
@jwt_required()
def checkin_status():
    """返回当前用户的签到状态、剩余免费生图额度与上限。
    上限来自 IMAGE_FREE_LIMIT，与图片生成共享同一上限。
    """
    from flask import current_app
    user_id = int(get_jwt_identity())
    now = local_now()
    free_limit = int(current_app.config.get('IMAGE_FREE_LIMIT') or 5)

    last = DailyCheckIn.query.filter_by(user_id=user_id).order_by(DailyCheckIn.checkin_time.desc()).first()
    can_checkin = True
    next_checkin = None
    if last and last.checkin_time:
        elapsed = (now - last.checkin_time).total_seconds()
        if elapsed < 86400:
            can_checkin = False
            next_checkin = (last.checkin_time + timedelta(seconds=86400)).isoformat()

    usage = ImageUsage.query.filter_by(user_id=user_id).first()
    # free_count 语义为「剩余次数」；未创建记录时视为拥有完整额度
    free_images = usage.free_count if usage else free_limit
    return jsonify({
        'code': 200,
        'data': {
            'can_checkin': can_checkin,
            'next_checkin': next_checkin,
            'free_images': free_images,
            'free_limit': free_limit,
        }
    })
