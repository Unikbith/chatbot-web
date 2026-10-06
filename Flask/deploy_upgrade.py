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
    python deploy_upgrade.py --diagnose      # 只读诊断：逐个会话说明「为什么协议包没生效」
    python deploy_upgrade.py --fix-legacy    # 额外修老会话的「界面标记」开关（见下）
    python deploy_upgrade.py --fill-user-prompt   # 额外给「玩家设定」为空的卡补通用模板

关于 --fix-legacy
    老版本（升级前）**没有「界面标记」这个开关**，升级后所有老会话该字段为空，
    启动时会被一次性回填成 .env 里的 RICH_MESSAGE_ENABLED（默认 true）。
    若线上 .env 里曾经写过 RICH_MESSAGE_ENABLED=false，老会话就全变成「关」：
    此时结构协议不注入、前端也不渲染面板 —— 表现就是"世界书里有内容，但对话里没生效"。
    --fix-legacy 会把这类老会话（判定依据：没有 reply_template，即升级前就存在）的
    「界面标记」重新打开；新版里用户自己关过的会话（有 reply_template）不动。
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
DIAGNOSE = '--diagnose' in sys.argv
FIX_LEGACY = '--fix-legacy' in sys.argv
FILL_USER_PROMPT = '--fill-user-prompt' in sys.argv

app = create_app()
summary_rows = []


def report(label, value):
    print(f'  {label:<38} {value}')
    summary_rows.append((label, value))


def diagnose_conversations():
    """逐个会话说明协议包为什么（没）生效 —— 排查"世界书有内容但对话里没生效"用。"""
    from routes.chat import (_effective_persona_id, _protocol_block, template_prompt)
    from rich_marker import resolve_rich_marker_enabled, RICH_MESSAGE_ENABLED
    print(f'  环境变量 RICH_MESSAGE_ENABLED = {RICH_MESSAGE_ENABLED}')
    rows = Conversation.query.order_by(Conversation.id.desc()).limit(40).all()
    print(f'  最近 {len(rows)} 个会话：')
    blocked = 0
    for conv in rows:
        reasons = []
        if conv.append_prompt_enabled is False:
            reasons.append('提示词兜底=关')
        pid = _effective_persona_id(conv, conv.user_id)
        if not pid:
            reasons.append('无人物卡可回落')
        else:
            cnt = WorldBookEntry.query.filter_by(
                user_id=conv.user_id, persona_id=pid, category='protocol', enabled=True).count()
            if not cnt:
                reasons.append(f'卡 #{pid} 没有启用的协议条目')
        if not resolve_rich_marker_enabled(conv):
            reasons.append('界面标记=关（结构不注入、前端也不渲染）')
        opts = template_prompt(conv)
        if opts.get('enhance') is False:
            reasons.append('提示词增强=关（结构不注入）')
        block = _protocol_block(conv.user_id, pid, [], conv)
        if not block:
            blocked += 1
        state = f'注入 {len(block)} 字' if block else '注入 0 字 ← 没生效'
        flag = ('  ⚠ ' + '；'.join(reasons)) if reasons else ''
        print(f'    #{conv.id:<5} 用户{conv.user_id:<3} {state}{flag}')
    print(f'  未生效的会话：{blocked} 个（有 ⚠ 的就是原因）')
    return blocked


with app.app_context():
    print('=' * 68)
    print('线上升级' + ('（dry-run：不写库）' if DRY else '')
          + ('（诊断模式：只读）' if DIAGNOSE else ''))
    print('=' * 68)

    if DIAGNOSE:
        print('\n[诊断] 协议包为什么没生效')
        diagnose_conversations()
        print('\n诊断结束（未写入任何改动）')
        sys.exit(0)

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

    # ---------- 3b. 老会话的「界面标记」开关（--fix-legacy） ----------
    if FIX_LEGACY:
        print('\n[3b] 老会话的「界面标记」开关（旧版本没有这个开关）')
        # 判定「老会话」：没有 reply_template —— 该字段同样是升级后才有的，
        # 因此新版里被用户自己关掉的会话（有模板）不会被误改。
        legacy_off = [c for c in Conversation.query.filter(
            Conversation.rich_marker_enabled.is_(False)).all()
            if not (c.reply_template or '').strip()]
        report('老会话里界面标记为关的', len(legacy_off))
        if not DRY:
            for conv in legacy_off:
                conv.rich_marker_enabled = True
        print('       （说明：界面标记关掉时，结构协议不注入、前端也不渲染面板）')
    else:
        off_cnt = Conversation.query.filter(Conversation.rich_marker_enabled.is_(False)).count()
        if off_cnt:
            print(f'\n[3b] 提示：有 {off_cnt} 个会话的「界面标记」是关的；'
                  f'若是老版本升级上来的，用 --fix-legacy 一并打开')

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
