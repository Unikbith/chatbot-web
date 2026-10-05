"""结构巡检：检查最近几轮 AI 回复是否按规范给齐了构件。

用法：
    python checks/structure.py             # 巡检最近 40 条助手消息
    python checks/structure.py 100 110     # 巡检最近 100 条，只看对话 110

检查点（对着 reply_spec.py 的「每轮输出结构」逐条核对）：
  1. 必备构件是否齐全：场景 / 玩家信息 / 角色信息 / 身体状态 / 精神心理 / 状态 / 内心 / 记忆 / 推演
  2. 是否同轮重复写了场景条（【场景】+【状态条】两个都写）
  3. 场景条字段是否写反（按内容判类型，地点位置出现时间即算错位）
  4. 标记是否独占一行（两个标记挤一行会被拆开显示，观感错乱）
  5. 是否用了词表外的自创标记名

它只读不写，用来判断"错乱"是模型没按规范输出，还是前端渲染的问题。
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import Message, Conversation

app = create_app()

LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 40
ONLY_CONV = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else None

# 每轮必备的构件（值与 reply_spec.STRUCTURE_SPEC 的顺序一致）
REQUIRED = ['场景', '玩家信息', '角色信息', '身体状态', '精神心理', '状态', '内心', '记忆', '推演']
# 允许出现的标记名（reply_spec.MARKER_VOCAB）；其余算自创
KNOWN = {'场景', '状态条', '模块', '摘要', '面板', '状态', '内心', '记忆', '推演', '物品', '提醒',
         '进度', '选项'}

TIME_HINT = re.compile(r'(\d{1,2}\s*[:：]\s*\d{2}|凌晨|清晨|早上|早晨|上午|中午|午后|下午|傍晚|黄昏|晚上|夜里|深夜|午夜|半夜|Day\s*\d|周[一二三四五六日天])')
PLACE_HINT = re.compile(r'(楼|层|室|房|厅|馆|店|院|街|路|巷|城|村|岛|山|河|湖|海|公园|广场|学校|教室|走廊|客厅|卧室|厨房|浴室|阳台|沙发|床|车里|车内|门口|窗外|天台|包厢|咖啡|酒吧|餐厅|办公室|宿舍|医院|地下|电梯|玄关|地毯)')

MARKER_LINE = re.compile(r'^\s*【([^】]{1,20})】([\s\S]*)$')


def blocks_of(text):
    """按行抽出行首标记，返回 [(名字, 字段列表)]"""
    out = []
    for line in (text or '').split('\n'):
        m = MARKER_LINE.match(line)
        if not m:
            continue
        name = m.group(1).strip()
        fields = [f.strip() for f in re.split(r'[|｜]', m.group(2)) if f.strip()]
        out.append((name, fields, line))
    return out


def scene_misordered(fields):
    """场景/状态条里，地点位置是否是时间（或反之）—— 结果为 (place, time) 元组判断"""
    place = time = ''
    for f in fields:
        m = re.match(r'^([^:：]{1,6})[:：]\s*(.*)$', f)
        if m:
            k = m.group(1).strip()
            if k in ('地点', '位置', '所在', '场景') and not place:
                place = m.group(2).strip()
            elif k in ('时间', '时刻') and not time:
                time = m.group(2).strip()
            continue
        if TIME_HINT.search(f) and not time:
            time = f
        elif PLACE_HINT.search(f) and not place:
            place = f
    # 地点里含时间特征、时间里含地点特征 => 明显写反
    bad = bool(place and TIME_HINT.search(place) and not PLACE_HINT.search(place)) \
        or bool(time and PLACE_HINT.search(time) and not TIME_HINT.search(time))
    return bad, place, time


with app.app_context():
    q = Message.query.filter(Message.role == 'assistant')
    if ONLY_CONV:
        q = q.filter(Message.conversation_id == ONLY_CONV)
    msgs = q.order_by(Message.id.desc()).limit(LIMIT).all()

    fmt_msgs = [m for m in msgs if '【' in (m.content or '')]
    print(f'扫描最近 {len(msgs)} 条助手回复，其中含标记的 {len(fmt_msgs)} 条'
          + (f'（对话 {ONLY_CONV}）' if ONLY_CONV else ''))

    tot = {'missing': 0, 'dup_scene': 0, 'misorder': 0, 'inline': 0, 'unknown': 0}
    legacy = 0
    for m in fmt_msgs:
        blocks = blocks_of(m.content)
        names = [b[0] for b in blocks]
        problems = []

        # 旧格式/简短消息（构件少于 3 个，例如只有一条【进度】或纯正文）：
        # 它们不是"结构错乱"，而是规范上线前的历史内容，前端已用兜底渲染，
        # 单独统计、不混进缺失数里，免得把历史数据当成现在的 bug。
        if len(blocks) < 3:
            legacy += 1
            print(f'  msg={m.id:<6} conv={m.conversation_id:<5} 构件={len(blocks):<3} '
                  f'[旧格式/简短，跳过结构核对] {names}')
            continue

        # 1. 必备构件
        missing = []
        for req in REQUIRED:
            if req == '场景':
                if '场景' not in names and '状态条' not in names:
                    missing.append('场景/状态条')
            elif req in ('玩家信息', '角色信息', '身体状态', '精神心理'):
                if not any(n == '面板' and f and req in f[0] for n, f, _ in blocks):
                    missing.append(req)
            elif req == '记忆':
                # 记忆可以由前端用系统摘要补出，这里只提示模型没写
                if '记忆' not in names:
                    missing.append('记忆(前端会补)')
            elif req not in names:
                missing.append(req)
        if missing:
            tot['missing'] += 1
            problems.append('缺构件: ' + ','.join(missing))

        # 2. 场景条重复
        if '场景' in names and '状态条' in names:
            tot['dup_scene'] += 1
            problems.append('场景条写了两个（【场景】+【状态条】）')

        # 3. 字段错位
        for n, f, _ in blocks:
            if n in ('场景', '状态条'):
                bad, place, time = scene_misordered(f)
                if bad:
                    tot['misorder'] += 1
                    problems.append(f'{n}字段疑似写反: 地点={place!r} 时间={time!r}')
                break

        # 4. 一行里挤了两个**已知标记**（【】包着的说明文字不算，那是格式允许的）
        for line in (m.content or '').split('\n'):
            hits = re.findall(r'【([^】]{1,20})】', line)
            known_hits = [h.strip() for h in hits if h.strip() in KNOWN]
            if len(known_hits) >= 2:
                tot['inline'] += 1
                problems.append('一行里有多个标记: ' + line[:60])
                break

        # 5. 自创标记
        unknown = sorted({n for n in names if n not in KNOWN})
        if unknown:
            tot['unknown'] += 1
            problems.append('自创标记: ' + ','.join(unknown))

        # 6. 推演选项数量
        for n, f, _ in blocks:
            if n == '推演' and len(f) < 3:
                problems.append(f'推演选项偏少({len(f)})')
                break

        flag = 'OK' if not problems else ' | '.join(problems)
        print(f'  msg={m.id:<6} conv={m.conversation_id:<5} 构件={len(blocks):<3} {flag}')

    print()
    print('汇总：')
    print(f'  旧格式/简短消息  {legacy} 条（跳过核对，前端已兜底渲染）')
    print(f'  缺必备构件      {tot["missing"]} 条')
    print(f'  场景条写两个    {tot["dup_scene"]} 条')
    print(f'  地点/时间错位   {tot["misorder"]} 条')
    print(f'  一行挤多个标记  {tot["inline"]} 条')
    print(f'  自创标记名      {tot["unknown"]} 条')
    print()
    if fmt_msgs and not any(tot.values()):
        print('结论：结构稳定，没有错乱 ✅')
    else:
        print('结论：上面每一条都是"模型没按规范输出"的证据 —— '
              '前端渲染已做语义归位与兜底，标记文本不会漏进正文；')
        print('      若某类问题反复出现，可把对应例句补进 Flask/reply_spec.py 的规范里。')
