"""线上升级：把已有数据迁移到新版本（幂等，可重复执行）。

为什么需要它
    老版本部署里没有「协议包」这个概念：
      · 人物卡的世界书是空的 → 新版本聊天拿不到输出结构 / 创作 / 剧情推进 / 玩法规范；
      · 会话的「提示词兜底」是旧默认（关）→ 协议包整套不注入；
      · 会话里存过模板的 enhance 是 false（旧版会在聊满两轮后自动关掉）→ 结构规范不注入；
      · 老会话的 persona_id 多为空 → 协议条目按卡存，空值就查不到。
    应用启动时的 `_ensure_schema_columns` 只负责「表/列/索引」，不做这些业务数据迁移，
    所以线上需要执行一次本脚本。

执行顺序（线上推荐）
    1) 备份数据库：  sqlite3 instance/chatbot.db ".backup 'backup_before_upgrade.db'"
    2) 启动一次新版本（会自动建表/加列/补索引，并把 rich_marker_enabled 的 NULL 回填）
    3) 跑本脚本：    venv/bin/python deploy_upgrade.py            # 先 --dry-run 看一眼
    4) 重启服务：    sudo systemctl restart chatbot

用法
    python deploy_upgrade.py                 # 执行（幂等）
    python deploy_upgrade.py --dry-run       # 只报告将要改什么，不写库
    python deploy_upgrade.py --fill-user-prompt   # 额外给「玩家设定」为空的卡补通用模板
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from extensions import db
from models import (Conversation, PersonaTemplate, WorldBookEntry,
                    ConversationSummary, MarketplaceWorldbookEntry)
from services.protocol_seed import seed_protocol_entries

DRY = '--dry-run' in sys.argv
FILL_USER_PROMPT = '--fill-user-prompt' in sys.argv

app = create_app()
summary_rows = []


def report(label, value):
    print(f'  {label:<38} {value}')
    summary_rows.append((label, value))


with app.app_context():
    print('=' * 68)
    print('线上升级' + ('（dry-run：不写库）' if DRY else ''))
    print('=' * 68)

    # ---------- 0. 结构自检（启动迁移应已建好新表/列） ----------
    print('\n[0] 结构自检')
    from sqlalchemy import inspect
    insp = inspect(db.engine)
    tables = set(insp.get_table_names())
    need_tables = ['worldbook_entries', 'conversation_summaries', 'conversation_media_logs',
                   'marketplace_worldbook_entries', 'prompt_tool_logs']
    missing_tables = [t for t in need_tables if t not in tables]
    report('缺失的表', missing_tables or '无')
    if 'worldbook_entries' in tables:
        cols = {c['name'] for c in insp.get_columns('worldbook_entries')}
        report('worldbook_entries 新字段',
               '齐全' if {'category', 'kind', 'source_key'} <= cols
               else f"缺 {sorted({'category', 'kind', 'source_key'} - cols)}")
    if 'conversations' in tables:
        ccols = {c['name'] for c in insp.get_columns('conversations')}
        report('conversations 新字段',
               '齐全' if {'rich_marker_enabled', 'reply_template', 'summary_threshold',
                          'imported_memory'} <= ccols
               else f"缺 {sorted({'rich_marker_enabled', 'reply_template', 'summary_threshold', 'imported_memory'} - ccols)}")
    if 'persona_templates' in tables:
        pcols = {c['name'] for c in insp.get_columns('persona_templates')}
        report('persona_templates.user_prompt', '有' if 'user_prompt' in pcols else '缺')

    # ---------- 1. 人物卡：种入协议包 ----------
    print('\n[1] 给所有人物卡种入协议包（输出结构 / 创作与内容 / 剧情推进 + 玩法包）')
    cards = PersonaTemplate.query.filter_by(persona_type='ai').all()
    created_total = updated_total = 0
    for card in cards:
        have = WorldBookEntry.query.filter_by(
            user_id=card.user_id, persona_id=card.id, category='protocol').count()
        if DRY:
            created_total += max(0, len(__import__('protocol_pack').protocol_entries()) - have)
            continue
        created, updated = seed_protocol_entries(card.user_id, card.id)
        created_total += created
        updated_total += updated
    report('AI 人物卡总数', len(cards))
    report('新增协议条目', created_total)
    report('刷新协议条目正文', updated_total)
    protocol_now = WorldBookEntry.query.filter_by(category='protocol').count()
    report('协议条目现有总数', protocol_now)

    # ---------- 2. 会话：提示词兜底 / 提示词增强 跟着新默认走 ----------
    print('\n[2] 会话开关：提示词兜底（新默认开）、提示词增强（新默认开）')
    flag_rows = Conversation.query.filter(
        db.or_(Conversation.append_prompt_enabled.is_(None),
               Conversation.append_prompt_enabled.is_(False))
    ).all()
    report('提示词兜底需要改为开启', len(flag_rows))
    if not DRY:
        for conv in flag_rows:
            conv.append_prompt_enabled = True

    enh_ids = []
    for conv in Conversation.query.filter(Conversation.reply_template.isnot(None)).all():
        try:
            tpl = json.loads(conv.reply_template)
        except (TypeError, ValueError):
            continue
        if isinstance(tpl, dict) and tpl.get('enhance') is False:
            tpl['enhance'] = True
            enh_ids.append(conv.id)
            if not DRY:
                conv.reply_template = json.dumps(tpl, ensure_ascii=False)
    report('提示词增强需要改为开启', len(enh_ids))

    # ---------- 3. 会话：补绑人物卡（协议条目按卡存） ----------
    print('\n[3] 给没绑定人物卡的会话补绑默认卡')
    unbound = Conversation.query.filter(Conversation.persona_id.is_(None)).all()
    bound = no_card = 0
    for conv in unbound:
        card = PersonaTemplate.query.filter_by(
            user_id=conv.user_id, persona_type='ai', is_default=True
        ).filter(PersonaTemplate.deleted_at.is_(None)).first() or \
            PersonaTemplate.query.filter_by(
                user_id=conv.user_id, persona_type='ai'
            ).filter(PersonaTemplate.deleted_at.is_(None)).order_by(PersonaTemplate.id).first()
        if not card:
            no_card += 1
            continue
        bound += 1
        if not DRY:
            conv.persona_id = card.id
    report('persona_id 为空的会话', len(unbound))
    report('可补绑', bound)
    report('所属用户没有人物卡（无法补绑）', no_card)

    # ---------- 4. 可选：补玩家设定 ----------
    if FILL_USER_PROMPT:
        print('\n[4] 给「玩家设定」为空的人物卡补通用模板')
        from routes.auth import DEFAULT_USER_PROMPT
        empty_cards = [c for c in PersonaTemplate.query.filter_by(persona_type='ai').all()
                       if not (c.user_prompt or '').strip()]
        report('需要补的卡', len(empty_cards))
        if not DRY:
            for c in empty_cards:
                c.user_prompt = DEFAULT_USER_PROMPT

    # ---------- 5. 数据健康度 ----------
    print('\n[5] 数据健康度')
    report('AI 人物卡', PersonaTemplate.query.filter_by(persona_type='ai').count())
    report('普通设定条目（lore）', WorldBookEntry.query.filter_by(category='lore').count())
    report('压缩摘要记录', ConversationSummary.query.count())
    report('广场卡片世界书条目', MarketplaceWorldbookEntry.query.count())
    report('会话总数', Conversation.query.count())
    report('仍无人物卡的会话', Conversation.query.filter(Conversation.persona_id.is_(None)).count())

    if DRY:
        db.session.rollback()
        print('\n[dry-run] 未写入任何改动')
    else:
        db.session.commit()
        print('\n已提交')

print('\n' + '=' * 68)
print('升级完成。下一步：')
print('  sudo systemctl restart chatbot        # 让新代码生效')
print('  curl http://127.0.0.1:5000/api/health # 期望 {"code":200,...}')
print('=' * 68)
