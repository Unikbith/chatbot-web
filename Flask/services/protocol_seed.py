"""协议包种入：把 protocol_pack 里的条目挂到人物卡名下（幂等）。

为什么做成"种入到卡"而不是"全局注入"：
    用户要的是「默认在每张卡里都有、也能选择打开和删除」——
    所以条目必须真实存在于该卡的世界书里，用户在自己的卡片面板就能编辑 / 启用 / 删除。

两层开关（**都要开才注入**）：
    · 对话设置里的总开关：提示词兜底（内容类）/ 界面标记 + 丰富面板内容（结构类）；
    · 卡片里条目自己的开关（WorldBookEntry.enabled）。
    所以三条核心条目种入时是**关**的（`default_enabled=False`），用户在卡片里单独打开；
    玩法包种入即开（只有关键词命中才会真的注入，平时不花 token）。

幂等规则：以 (user_id, persona_id, source_key) 为唯一键。
    已存在 → 只更新标题 / 正文 / 权重等系统维护字段，**不动用户的 enabled 与 always_on**，
    避免用户刚关掉的条目又被下一次种入打开。
"""
from extensions import db
from models import WorldBookEntry
import protocol_pack


def seed_protocol_entries(user_id, persona_id, only_missing=False):
    """给某张人物卡种入协议包条目。

    :param only_missing: True 时只补缺失的条目（不覆盖已有条目的正文），
                         用于"补种"场景；False 时同时刷新系统维护字段的正文。
    :return: (新增数, 更新数)
    """
    if not user_id or not persona_id:
        return 0, 0

    existing = {
        e.source_key: e
        for e in WorldBookEntry.query.filter_by(
            user_id=user_id, persona_id=persona_id, category='protocol'
        ).filter(WorldBookEntry.source_key.isnot(None)).all()
    }

    created = updated = 0
    for spec in protocol_pack.protocol_entries():
        row = existing.get(spec['source_key'])
        if row is None:
            db.session.add(WorldBookEntry(
                user_id=user_id,
                persona_id=persona_id,
                title=spec['title'],
                keywords=spec['keywords'],
                content=spec['content'],
                always_on=bool(spec['always_on']),
                # 新条目按 spec 的默认开关：核心条目=关，玩法包=开
                enabled=bool(spec.get('default_enabled', True)),
                weight=spec['weight'],
                category='protocol',
                kind=spec['kind'],
                source_key=spec['source_key'],
            ))
            created += 1
            continue
        if only_missing:
            continue
        # 只刷新系统维护的字段；enabled / always_on 尊重用户当前选择
        changed = False
        if row.title != spec['title']:
            row.title = spec['title']; changed = True
        if (row.content or '') != spec['content']:
            row.content = spec['content']; changed = True
        if (row.keywords or '') != spec['keywords']:
            row.keywords = spec['keywords']; changed = True
        if row.kind != spec['kind']:
            row.kind = spec['kind']; changed = True
        if (row.weight or 0) != spec['weight']:
            row.weight = spec['weight']; changed = True
        if changed:
            updated += 1
    return created, updated


def restore_protocol_entry(user_id, persona_id, source_key):
    """把某条协议条目恢复成默认正文并启用（用户删掉/改坏后的救援入口）。

    「恢复默认协议包」是用户主动点的救援动作 —— 恢复内容的同时把条目**打开**，
    否则点了按钮还是没反应（是否真的注入仍由「对话设置」的总开关决定）。
    """
    content = protocol_pack.entry_content_of(source_key)
    if not content:
        return None
    spec = next((e for e in protocol_pack.protocol_entries()
                 if e['source_key'] == source_key), None)
    if spec is None:
        return None
    row = WorldBookEntry.query.filter_by(
        user_id=user_id, persona_id=persona_id, source_key=source_key
    ).first()
    if row is None:
        row = WorldBookEntry(
            user_id=user_id, persona_id=persona_id, source_key=source_key,
            title=spec['title'], keywords=spec['keywords'], content=content,
            always_on=bool(spec['always_on']), enabled=True, weight=spec['weight'],
            category='protocol', kind=spec['kind'],
        )
        db.session.add(row)
    else:
        row.title = spec['title']
        row.content = content
        row.keywords = spec['keywords']
        row.kind = spec['kind']
        row.weight = spec['weight']
        row.always_on = bool(spec['always_on'])
        row.enabled = True
    return row
