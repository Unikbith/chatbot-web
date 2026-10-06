"""线上升级：把已有数据迁移到新版本（幂等，可重复执行）。

为什么需要它
    老版本部署里没有「协议包」这个概念：
      · 人物卡的世界书是空的 → 新版本聊天拿不到输出结构 / 创作 / 剧情推进 / 玩法规范；
      · 老会话的 persona_id 多为空 → 协议条目按卡存，空值就查不到。
    应用启动时的 `_ensure_schema_columns` 只负责「表/列/索引」，不做这些业务数据迁移，
    所以线上需要执行一次本脚本。

    两层开关语义（谁控制谁）
      · 对话设置 = 总开关，管"所有人物卡"的世界书条目：
        – 提示词兜底 → 只控制「② 创作与内容协议」（= 后端 GLOBAL_APPEND_PROMPT 的破甲提示词），默认关；
        – 界面标记 + 丰富面板内容 → 只控制「① 输出结构协议」，默认开前两轮（之后 chat.py 自动关）；
      · 人物卡 → 世界书 = 只管"这一张卡"：每条自己的开关。
      · ③ 剧情推进与体验协议 = **常驻**（默认开、每轮注入，不受对话开关影响）；
        玩法包 = 默认开、关键词命中才注入。
    default_enabled：① 输出结构 = True、② 创作与内容 = False、③ 剧情体验 = True、玩法包 = True。

    一次性的破坏性步骤用 deploy_markers 表打标记，**重复执行不会覆盖用户后来的选择**
    （比如用户自己打开的开关，第二次跑脚本不会被再关掉）。

执行顺序（线上推荐）
    1) 备份数据库：  sqlite3 instance/chatbot.db ".backup 'backup_before_upgrade.db'"
    2) 启动一次新版本（会自动建表/加列/补索引，并把 rich_marker_enabled 的 NULL 回填）
    3) 跑本脚本：    venv/bin/python deploy_upgrade.py            # 先 --dry-run 看一眼
    4) 重启服务：    sudo systemctl restart chatbot

用法
    python deploy_upgrade.py                 # 执行（幂等）
    python deploy_upgrade.py --dry-run       # 只报告将要改什么，不写库
    python deploy_upgrade.py --diagnose      # 只读诊断：开关状态 + 每轮协议包注入多少字 + 重复文本
    python deploy_upgrade.py --dup-check     # 只读：找出「卡提示词里抄了世界书正文」的重复消耗
    python deploy_upgrade.py --fix-legacy    # 额外修老会话的「界面标记」开关（见下）
    python deploy_upgrade.py --fill-user-prompt   # 额外给「玩家设定」为空的卡补通用模板

关于 --fix-legacy
    老版本（升级前）**没有「界面标记」这个开关**，升级后所有老会话该字段为空，
    启动时会被一次性回填成 .env 里的 RICH_MESSAGE_ENABLED（默认 true）。
    若线上 .env 里曾经写过 RICH_MESSAGE_ENABLED=false，老会话就全变成「关」：
    此时结构协议不注入、前端也不渲染面板。--fix-legacy 会把这类老会话
    （判定依据：没有 reply_template，即升级前就存在）的「界面标记」重新打开；
    新版里用户自己关过的会话（有 reply_template）不动。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text

from app import create_app
from extensions import db
from models import (Conversation, PersonaTemplate, WorldBookEntry,
                    ConversationSummary, MarketplaceWorldbookEntry)
from services.protocol_seed import seed_protocol_entries

DRY = '--dry-run' in sys.argv
DIAGNOSE = '--diagnose' in sys.argv
FIX_LEGACY = '--fix-legacy' in sys.argv
FILL_USER_PROMPT = '--fill-user-prompt' in sys.argv
DUP_CHECK = '--dup-check' in sys.argv

# 一次性破坏性步骤的标记名（写进 deploy_markers 表；已打过就跳过）
MARK_SWITCHES_OFF = 'switches_default_off_v1'
MARK_ENTRIES_OFF = 'protocol_entries_default_off_v1'
MARK_STRUCTURE_ON = 'structure_entry_default_on_v1'
MARK_EXPERIENCE_ON = 'experience_entry_always_on_v1'

app = create_app()


def ensure_marker_table():
    """建标记表（脚本自己建，不依赖 app 启动迁移）。"""
    db.session.execute(text(
        'CREATE TABLE IF NOT EXISTS deploy_markers ('
        '  name VARCHAR(64) PRIMARY KEY,'
        '  applied_at DATETIME'
        ')'
    ))
    db.session.commit()


def marker_done(name):
    row = db.session.execute(
        text('SELECT name FROM deploy_markers WHERE name = :n'), {'n': name}
    ).first()
    return row is not None


def mark_done(name):
    db.session.execute(
        text('INSERT OR IGNORE INTO deploy_markers (name, applied_at) '
             'VALUES (:n, :t)'),
        {'n': name, 't': __import__('datetime').datetime.now()},
    )
    db.session.commit()
summary_rows = []


def report(label, value):
    print(f'  {label:<38} {value}')
    summary_rows.append((label, value))


def diagnose_conversations():
    """逐个会话报告「开关状态 + 每轮协议包注入多少字」—— 排查 token 消耗 / 没生效用。

    注意：新默认是关（提示词兜底、丰富面板内容都关），所以"注入 0 字"是正常状态；
    真正的问题是 ⚠ 标记的那些（没有人物卡、卡里没有启用的协议条目）。
    """
    from routes.chat import (_effective_persona_id, _protocol_block, template_prompt)
    from rich_marker import resolve_rich_marker_enabled, RICH_MESSAGE_ENABLED
    print(f'  环境变量 RICH_MESSAGE_ENABLED = {RICH_MESSAGE_ENABLED}')
    rows = Conversation.query.order_by(Conversation.id.desc()).limit(40).all()
    print(f'  最近 {len(rows)} 个会话（新默认：两个开关都是关）：')
    injecting = 0
    for conv in rows:
        problems = []
        pid = _effective_persona_id(conv, conv.user_id)
        if not pid:
            problems.append('无人物卡可回落')
        else:
            cnt = WorldBookEntry.query.filter_by(
                user_id=conv.user_id, persona_id=pid, category='protocol', enabled=True).count()
            if not cnt:
                problems.append(f'卡 #{pid} 没有启用的协议条目')
        opts = template_prompt(conv)
        switches = ' '.join([
            '兜底=' + ('开' if conv.append_prompt_enabled else '关'),
            '标记=' + ('开' if resolve_rich_marker_enabled(conv) else '关'),
            '面板=' + ('开' if opts.get('enhance') is True else '关'),
        ])
        # 卡片里条目自身的开关（控制"单独"）：统计已启用条数，帮用户定位"总开关开了还是没生效"
        entries = WorldBookEntry.query.filter(
            WorldBookEntry.user_id == conv.user_id,
            WorldBookEntry.category == 'protocol',
            db.or_(WorldBookEntry.persona_id == pid, WorldBookEntry.persona_id.is_(None)),
        ).all() if pid else []
        on_entries = sum(1 for e in entries if e.enabled)
        entry_info = f' 条目={on_entries}/{len(entries)}' if entries else ''
        block = _protocol_block(conv.user_id, pid, [], conv)
        if block:
            injecting += 1
        state = f'注入 {len(block):>5} 字' if block else '注入     0 字'
        flag = ('  ⚠ ' + '；'.join(problems)) if problems else ''
        print(f'    #{conv.id:<5} 用户{conv.user_id:<3} {state} [{switches}{entry_info}]{flag}')
    print(f'  当前每轮实际注入协议包的会话：{injecting} / {len(rows)} 个'
          f'（其余都是开关关着，省 token）')
    return injecting


def check_duplicate_injection():
    """只读检查：人物卡的提示词里是否**抄了**协议包 / 世界书的正文（每轮重复付费）。

    典型来源：用户把「提示词兜底」的那段全局提示词复制进了人物卡的提示词里。
    那段文字本来就会由协议包按开关注入，抄进卡里等于每轮付两次 token，
    而且**开关关掉也省不下来**（人物卡提示词是无条件注入的）。

    判定方式：把每条世界书条目按行切开，统计有多少行能在卡的提示词里原样找到。
    这是保守的近似（只认整行原样命中），避免把"意思相近"误报成重复。
    """
    cards = PersonaTemplate.query.filter_by(persona_type='ai').all()
    print(f'  扫描 {len(cards)} 张 AI 人物卡的提示词 …')
    hits = []
    for card in cards:
        prompt = card.system_prompt or ''
        if len(prompt) < 200:
            continue
        entries = WorldBookEntry.query.filter_by(
            user_id=card.user_id, persona_id=card.id).all()
        dup_chars = 0
        dup_titles = []
        for e in entries:
            body = (e.content or '').strip()
            if len(body) < 200:
                continue
            line_hit = 0
            for line in body.split('\n'):
                line = line.strip()
                if len(line) >= 12 and line in prompt:
                    line_hit += len(line)
            # 单条命中超过 300 字才算"抄了一段"，避免零星措辞撞车误报
            if line_hit >= 300:
                dup_chars += line_hit
                dup_titles.append(f'{e.title}({line_hit}字)')
        if dup_chars:
            hits.append((card, dup_chars, dup_titles))
    if not hits:
        print('  未发现「卡提示词里抄了世界书正文」的情况 ✔')
        return 0
    print(f'  发现 {len(hits)} 张卡存在重复文本（建议手动删掉卡里那段，改由协议条目控制）：')
    for card, chars, titles in sorted(hits, key=lambda x: -x[1]):
        print(f'    用户{card.user_id} 卡#{card.id}《{card.name or "未命名"}》'
              f' 提示词 {len(card.system_prompt or "")} 字，其中约 {chars} 字与世界书条目重复')
        print(f'        重复条目：{"、".join(titles)}')
    print('  处理建议：在「人物卡 → 提示词」里删掉与协议条目重复的那一段；'
          '协议包要不要注入交给「对话设置」的开关。')
    return len(hits)


with app.app_context():
    ensure_marker_table()
    print('=' * 68)
    print('线上升级' + ('（dry-run：不写库）' if DRY else '')
          + ('（诊断模式：只读）' if DIAGNOSE else ''))
    print('=' * 68)
    # 先把「用的是哪个解释器、哪个数据库文件」打出来：
    # 线上最常见的坑就是升级脚本跑在另一个 venv / 另一个库上，白忙一场。
    print(f'\n运行环境')
    print(f'  解释器   {sys.executable}')
    print(f'  数据库   {db.engine.url}')
    print(f'  工作目录 {os.getcwd()}')

    if DIAGNOSE:
        print('\n[诊断] 协议包为什么没生效')
        diagnose_conversations()
        print('\n[诊断] 重复文本检查（卡提示词里抄了世界书正文？）')
        check_duplicate_injection()
        print('\n诊断结束（未写入任何改动）')
        sys.exit(0)

    if DUP_CHECK:
        print('\n[检查] 人物卡提示词 vs 世界书：是否有重复文本')
        check_duplicate_injection()
        print('\n检查结束（未写入任何改动）')
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

    # 1b. 核心协议条目：默认改成「关」（一次性）
    # 两层开关里"卡片这一层"：三条核心条目种入即关，用户自己在卡片里逐条打开，
    # 或在「对话设置」点「一键开启该卡条目」。玩法包保持开（只有关键词命中才注入）。
    # 这一步会覆盖用户过去的开关状态，所以只在第一次执行时做（打标记），
    # 之后再跑脚本不会把用户自己打开的条目又关掉。
    already = marker_done(MARK_ENTRIES_OFF)
    if already:
        print('\n[1b] 核心协议条目默认关闭 —— 已执行过（跳过，不覆盖用户后来的选择）')
    else:
        print('\n[1b] 核心协议条目：默认关闭（用户按需在卡片里逐条打开）')
        rows = WorldBookEntry.query.filter(
            WorldBookEntry.category == 'protocol',
            WorldBookEntry.kind.in_(['structure', 'content', 'experience']),
        ).all()
        report('核心协议条目总数', len(rows))
        report('其中当前是开启的（将被关闭）', sum(1 for r in rows if r.enabled))
        report('核心协议条目取消「常驻」标记', sum(1 for r in rows if r.always_on))
        if not DRY:
            for row in rows:
                row.enabled = False
                row.always_on = False
            mark_done(MARK_ENTRIES_OFF)
        else:
            print('       （dry-run：未打标记，正式执行时才生效）')

    protocol_now = WorldBookEntry.query.filter_by(category='protocol').count()
    report('协议条目现有总数', protocol_now)
    report('协议条目中已启用的', WorldBookEntry.query.filter_by(
        category='protocol', enabled=True).count())

    # 1c. ① 输出结构协议：默认改成「开」（一次性）
    # 它的总开关「丰富面板内容」默认开前两轮，条目关着那两轮就白开了。
    if marker_done(MARK_STRUCTURE_ON):
        print('\n[1c] 输出结构协议默认开启 —— 已执行过（跳过）')
    else:
        print('\n[1c] 输出结构协议：默认开启（配合「丰富面板内容」默认开前两轮）')
        rows = WorldBookEntry.query.filter(
            WorldBookEntry.category == 'protocol',
            WorldBookEntry.kind == 'structure',
        ).all()
        report('结构协议条目总数', len(rows))
        report('其中当前是关闭的（将被开启）', sum(1 for r in rows if not r.enabled))
        if not DRY:
            for row in rows:
                row.enabled = True
            mark_done(MARK_STRUCTURE_ON)
        else:
            print('       （dry-run：未打标记，正式执行时才生效）')

    # 1d. ③ 剧情推进与体验协议：改成常驻（一次性）
    # 它是"每轮都在"的推进规范，不受对话设置里的开关控制，所以条目默认开。
    if marker_done(MARK_EXPERIENCE_ON):
        print('\n[1d] 剧情推进与体验协议（常驻）—— 已执行过（跳过）')
    else:
        print('\n[1d] 剧情推进与体验协议：改成常驻（默认开启、每轮注入）')
        rows = WorldBookEntry.query.filter(
            WorldBookEntry.category == 'protocol',
            WorldBookEntry.kind == 'experience',
        ).all()
        report('剧情推进条目总数', len(rows))
        report('其中当前是关闭的（将被开启）', sum(1 for r in rows if not r.enabled))
        if not DRY:
            for row in rows:
                row.enabled = True
                row.always_on = True
            mark_done(MARK_EXPERIENCE_ON)
        else:
            print('       （dry-run：未打标记，正式执行时才生效）')
        # 标题也换成「（常驻）」，避免界面上还写着由开关控制
        if not DRY:
            for row in rows:
                if row.title and '常驻' not in row.title:
                    row.title = '③ 剧情推进与体验协议（常驻）'

    # ---------- 2. 会话开关：一次性刷成新默认（历史会话都关，省 token） ----------
    print('\n[2] 一次性：历史会话的开关刷成默认关闭（提示词兜底 / 丰富面板内容）')
    # 上一版把老会话一律改成「开」，协议包每轮无条件注入 ~8k 字，token 消耗偏高。
    # 新默认改为「关」：由用户在「对话设置」里按需开；协议条目本身仍留在卡的
    # 世界书里，用户随时可以逐条编辑 / 启用，内容没有被删。
    # 同样只在第一次执行时改，避免二次运行把用户后来打开的开关又关掉。
    if marker_done(MARK_SWITCHES_OFF):
        print('  已执行过（跳过，不覆盖用户后来的开关选择）')
    else:
        flag_rows = Conversation.query.filter(
            db.or_(Conversation.append_prompt_enabled.is_(None),
                   Conversation.append_prompt_enabled.is_(True))
        ).all()
        report('提示词兜底需要改为关闭', len(flag_rows))
        if not DRY:
            for conv in flag_rows:
                conv.append_prompt_enabled = False

        enh_ids = []
        for conv in Conversation.query.filter(Conversation.reply_template.isnot(None)).all():
            try:
                tpl = json.loads(conv.reply_template)
            except (TypeError, ValueError):
                continue
            # 缺字段（None）也算「不是关」，一并补成 false —— 与前端默认一致
            if isinstance(tpl, dict) and tpl.get('enhance') is not False:
                tpl['enhance'] = False
                enh_ids.append(conv.id)
                if not DRY:
                    conv.reply_template = json.dumps(tpl, ensure_ascii=False)
        report('丰富面板内容需要改为关闭', len(enh_ids))
        if not DRY:
            mark_done(MARK_SWITCHES_OFF)
        else:
            print('       （dry-run：未打标记，正式执行时才生效）')

    # 2b. 还处在「前两轮」窗口里的会话：把「丰富面板内容」补开
    # 新默认是「开前两轮，之后自动关」。已经聊过两轮的老会话保持关闭（格式早已在上下文里），
    # 但刚建的新会话/只聊了一轮的会话如果被上面那步关了，就永远学不到面板格式 —— 补回来。
    # 这一步不需要标记：跑完第 2 轮后 chat.py 自己会关，收敛且幂等。
    print('\n[2b] 前两轮窗口内的会话补开「丰富面板内容」')
    from models import Message  # 局部导入：脚本其它地方用不到
    from routes.chat import ENHANCE_ROUNDS_BEFORE_OFF  # 与注入侧保持同一个阈值
    fixed_enh = 0
    for conv in Conversation.query.filter(Conversation.reply_template.isnot(None)).all():
        try:
            tpl = json.loads(conv.reply_template)
        except (TypeError, ValueError):
            continue
        if not isinstance(tpl, dict) or tpl.get('enhance') is True:
            continue
        rounds = Message.query.filter_by(conversation_id=conv.id, role='user').count()
        if rounds >= ENHANCE_ROUNDS_BEFORE_OFF:
            continue
        tpl['enhance'] = True
        fixed_enh += 1
        if not DRY:
            conv.reply_template = json.dumps(tpl, ensure_ascii=False)
    report(f'轮次 < {ENHANCE_ROUNDS_BEFORE_OFF} 的会话补开', fixed_enh)

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
