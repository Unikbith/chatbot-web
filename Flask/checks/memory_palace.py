"""校验「记忆宫殿」是否真的生效，以及 token 是否被有效约束。

回答三个问题：
  A. 导入的长期记忆是否**完整**注入（不再被 200 字截断）—— 标记放在第 700 字附近
  B. 自动滚动摘要（长记忆）是否真的生效 —— 压缩后原文被丢弃、摘要进入 system 提示词
  C. token 是否随对话无限增长 —— 上下文窗口是否真的在裁剪

为避免真实调用大模型，把 AIService.chat_completions 打桩并捕获**真正发往模型的 messages**。
最后清理全部测试数据（含 ai_usage_logs 外键子表）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from extensions import db
from models import (User, Conversation, Message, ConversationSummary, AiUsageLog)

UID = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 1

MARK_TAIL = f'__mk_tail_{os.getpid()}__'      # 放在导入记忆靠后位置（>200 字）
MARK_OLD = f'__mk_old_{os.getpid()}__'        # 早期原文里的标记（压缩后应被丢弃）
MARK_SUM = f'__mk_sum_{os.getpid()}__'        # 压缩器产出的摘要里的标记

app = create_app()
ok = True
CAPTURED = []


def check(label, cond, extra=''):
    global ok
    print(('  [OK]   ' if cond else '  [FAIL] ') + label + (f'  {extra}' if extra else ''))
    if not cond:
        ok = False


class FakeResp:
    status_code = 200
    text = ''

    def __init__(self, content):
        self._content = content

    def json(self):
        return {'choices': [{'message': {'content': self._content}}]}

    def iter_lines(self, decode_unicode=True):
        import json as _json
        yield 'data: ' + _json.dumps(
            {'choices': [{'delta': {'content': self._content}}]}, ensure_ascii=False)
        yield 'data: [DONE]'


def fake_chat_completions(provider=None, messages=None, stream=False, **kw):
    sys_text = ''
    for m in (messages or []):
        if m.get('role') == 'system':
            sys_text = m.get('content') or ''
            break
    is_compressor = '对话记忆压缩器' in sys_text
    if is_compressor:
        CAPTURED.append({'kind': 'compress', 'messages': messages})
        # 压缩器按设计只输出 50-200 字：这里给一条短摘要（含 MARK_SUM）
        return FakeResp(f'- 用户提到过一个重要的旧约定（{MARK_SUM}）。'), None
    CAPTURED.append({'kind': 'chat', 'messages': messages})
    return FakeResp('好的。'), None


def build_history(msgs):
    return [{'role': m['role'], 'content': m['content']}
            for m in msgs if m['role'] in ('user', 'assistant')]


def last_chat_messages():
    for item in reversed(CAPTURED):
        if item['kind'] == 'chat':
            return item['messages']
    return []


def make_conv(client, H, title):
    r = client.post('/api/conversations', headers=H, json={
        'title': title, 'system_prompt': '你是一个温柔体贴的朋友，说话简短自然。'})
    return ((r.get_json() or {}).get('data') or {}).get('id')


conv_a = conv_b = None
try:
    with app.app_context():
        from flask_jwt_extended import create_access_token
        import routes.chat as chat_mod

        user = User.query.filter_by(id=UID).first()
        if not user:
            print(f'用户 {UID} 不存在')
            sys.exit(1)
        token = create_access_token(identity=str(UID), additional_claims={'tv': user.token_version})
        H = {'Authorization': f'Bearer {token}'}
        chat_mod.AIService.chat_completions = staticmethod(fake_chat_completions)
        client = app.test_client()

        # ── A. 导入记忆是否完整注入 ───────────────────────────────────
        print('== A. 导入长期记忆：是否完整注入（不再被 200 字截断）==')
        conv_a = make_conv(client, H, f'[自动校验] 导入记忆 {MARK_TAIL}')
        padding = '这是一段用于占位的往事细节，描述季节、街道与心情。' * 30   # 约 750 字
        memory = padding + f'我们之间的暗号是「{MARK_TAIL}」。'
        tail_pos = memory.index(MARK_TAIL)
        print(f'   导入记忆 {len(memory)} 字，标记位于第 {tail_pos} 字')

        client.post('/api/chat/memory-import', headers=H,
                    json={'conversation_id': conv_a, 'memory_text': memory})
        detail = (client.get(f'/api/conversations/{conv_a}', headers=H).get_json() or {}).get('data') or {}
        check('导入记忆已存入 imported_memory',
              MARK_TAIL in (detail.get('imported_memory') or ''),
              f'{len(detail.get("imported_memory") or "")} 字')

        CAPTURED.clear()
        history = build_history(detail.get('messages') or [])
        history.append({'role': 'user', 'content': '我们之间的暗号是什么？'})
        client.post('/api/chat', headers=H, json={
            'conversation_id': conv_a, 'messages': history, 'temperature': 0.6}).get_data()
        sent = last_chat_messages()
        sys_text = next((m['content'] for m in sent if m['role'] == 'system'), '')
        check('超出 200 字的标记也出现在 system 提示词里（未被截断）',
              MARK_TAIL in sys_text,
              f'标记位于第 {tail_pos} 字')
        check('导入原文没有在上下文里重复出现（避免双份 token）',
              not any(MARK_TAIL in (m.get('content') or '') for m in sent if m['role'] != 'system'))

        # ── B. 自动滚动摘要是否生效 ──────────────────────────────────
        print('== B. 自动滚动摘要：压缩后原文丢弃、摘要进入 system ==')
        conv_b = make_conv(client, H, f'[自动校验] 滚动摘要 {MARK_SUM}')
        with app.app_context():
            conv = db.session.get(Conversation, conv_b)
            conv.summary_threshold = 7
            db.session.commit()
            rows = []
            for i in range(8):
                c = (f'第{i+1}轮：' + (f'早期细节 {MARK_OLD} ' if i == 0 else '') +
                     '我们聊了很多日常，天气、工作、还有晚饭吃什么。' * 2)
                rows.append(Message(conversation_id=conv_b, role='user', content=c))
                rows.append(Message(conversation_id=conv_b, role='assistant', content='嗯，我懂你的意思。'))
            db.session.add_all(rows)
            db.session.commit()
            print(f'   预置 {len(rows)} 条消息（阈值 7 轮 = 14 条，应触发压缩）')

        all_msgs = (client.get(f'/api/conversations/{conv_b}', headers=H).get_json() or {}).get('data', {}).get('messages') or []
        CAPTURED.clear()
        client.post('/api/chat', headers=H, json={
            'conversation_id': conv_b,
            'messages': build_history(all_msgs) + [{'role': 'user', 'content': '我们接着聊吧。'}],
            'temperature': 0.6}).get_data()

        detail_b = (client.get(f'/api/conversations/{conv_b}', headers=H).get_json() or {}).get('data') or {}
        summary = detail_b.get('summary') or ''
        check('压缩已触发并写入 conv.summary', bool(summary), repr(summary[:60]))
        check('摘要长度在注入上限内（≤600 字）', 0 < len(summary) <= 600, f'{len(summary)} 字')
        check('summary_upto_id 已推进', (detail_b.get('summary_upto_id') or 0) > 0,
              f'summary_upto_id={detail_b.get("summary_upto_id")}')

        CAPTURED.clear()
        client.post('/api/chat', headers=H, json={
            'conversation_id': conv_b,
            'messages': build_history(detail_b.get('messages') or []) + [{'role': 'user', 'content': '我们接着聊吧。'}],
            'temperature': 0.6}).get_data()
        sent_b = last_chat_messages()
        sys_b = next((m['content'] for m in sent_b if m['role'] == 'system'), '')
        check('摘要已注入 system 提示词', MARK_SUM in sys_b)
        check('被摘要覆盖的旧原文不再送入模型（省 token 的关键）',
              not any(MARK_OLD in (m.get('content') or '') for m in sent_b))

        # ── C. 上下文窗口是否真的在裁剪 ──────────────────────────────
        print('== C. token 约束：上下文窗口裁剪 ==')
        with app.app_context():
            rows = []
            for i in range(40):
                rows.append(Message(conversation_id=conv_b, role='user',
                                    content=f'第{i+1}条补充：' + '一些无关紧要的闲聊内容。' * 6))
                rows.append(Message(conversation_id=conv_b, role='assistant', content='嗯嗯，我听着呢。'))
            db.session.add_all(rows)
            db.session.commit()

        big = (client.get(f'/api/conversations/{conv_b}', headers=H).get_json() or {}).get('data', {}).get('messages') or []
        history_big = build_history(big)
        CAPTURED.clear()
        client.post('/api/chat', headers=H, json={
            'conversation_id': conv_b, 'messages': history_big + [{'role': 'user', 'content': '继续。'}],
            'temperature': 0.6}).get_data()
        sent_c = last_chat_messages()
        ctx = [m for m in sent_c if m['role'] != 'system']
        ctx_chars = sum(len(m.get('content') or '') for m in ctx)
        print(f'   前端上送 {len(history_big)} 条 → 模型实收 {len(ctx)} 条上下文 / {ctx_chars} 字')
        check('上下文条数被限制在 16 条以内', len(ctx) <= 16, f'{len(ctx)} 条')
        check('上下文正文被限制在 5000 字量级', ctx_chars <= 5000 + 400, f'{ctx_chars} 字')
        check('系统提示词始终只注入一份', sum(1 for m in sent_c if m['role'] == 'system') == 1)

finally:
    print('== 清理测试数据 ==')
    with app.app_context():
        for cid in [c for c in (conv_a, conv_b) if c]:
            msg_ids = [m.id for m in Message.query.filter_by(conversation_id=cid).all()]
            AiUsageLog.query.filter_by(conversation_id=cid).delete(synchronize_session=False)
            if msg_ids:
                AiUsageLog.query.filter(AiUsageLog.message_id.in_(msg_ids)).delete(
                    synchronize_session=False)
            Message.query.filter_by(conversation_id=cid).delete(synchronize_session=False)
            ConversationSummary.query.filter_by(conversation_id=cid).delete(synchronize_session=False)
            c = db.session.get(Conversation, cid)
            if c:
                db.session.delete(c)
        db.session.commit()
        left = sum(Message.query.filter_by(conversation_id=cid).count()
                   for cid in [c for c in (conv_a, conv_b) if c])
    check('测试数据已清理', left == 0, f'残留 {left}')

print()
print('结果：' + ('全部通过 ✅' if ok else '存在失败项 ❌'))
sys.exit(0 if ok else 1)
