"""校验「记忆导入」的真实行为：导入后 AI 是**基于长记忆**回复，而非仅靠上下文。

走真实 HTTP 接口（Flask 测试客户端）。为避免真实调用大模型，
把 AIService.chat_completions 打桩，捕获**真正发往模型的 messages** 后断言。
最后把测试数据全部清理干净（含 ai_usage_logs 外键子表）。

检查点：
  1. 导入成功，且记忆以「用户消息」写入对话（界面可见）
  2. 导入同时写入独立的「导入记忆」字段 conv.imported_memory（原样保留、每轮注入，
     不会被滚动摘要压缩器改写成 200 字短摘要），summary_upto_id 指向该导入消息
  3. AI 以角色口吻确认记住（回复作为 assistant 消息落库）
  4. 后续对话时，前端上送的完整历史里虽然仍带导入原文，
     但模型实际收到的上下文中该原文已被摘要切片丢弃
  5. 记忆标记只出现在 system 消息（长记忆注入），不出现在任何上下文消息
  6. 负向对照：清空长记忆后，标记应从 system 消息中彻底消失（证明因果）
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from extensions import db
from models import (User, Conversation, Message, ConversationSummary, AiUsageLog)

UID = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 1

MARK = f'__mk_mem_{os.getpid()}__'
MEMORY = (f'我有一件很特别的信物，是一枚刻着「{MARK}」的银戒指，是外婆留给我的。'
          '我一直随身带着，从没给别人看过。')
QUESTION = '我的那件信物上，刻着什么花纹？'
CANNED = '好的，我记住了。'      # 故意不含 MARK，避免回复本身泄漏标记

app = create_app()
ok = True
CAPTURED = []


def check(label, cond, extra=''):
    global ok
    print(('  [OK]   ' if cond else '  [FAIL] ') + label + (f'  {extra}' if extra else ''))
    if not cond:
        ok = False


class FakeResp:
    """伪造上游流式/非流式响应，仅提供被测代码用到的接口。"""
    status_code = 200
    text = ''

    def json(self):
        return {'choices': [{'message': {'content': CANNED}}]}

    def iter_lines(self, decode_unicode=True):
        yield 'data: ' + json.dumps(
            {'choices': [{'delta': {'content': CANNED}}]}, ensure_ascii=False)
        yield 'data: [DONE]'


def fake_chat_completions(provider=None, messages=None, stream=False, **kw):
    CAPTURED.append(messages)
    return FakeResp(), None


conv_id = None
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

        print(f'用户 {UID}，开始校验（标记 {MARK}）')

        print('== 1. 新建对话并导入记忆 ==')
        r = client.post('/api/conversations', headers=H, json={
            'title': f'[自动校验] {MARK}',
            'system_prompt': '你是一个温柔体贴的朋友，说话简短自然。',
        })
        conv_id = ((r.get_json() or {}).get('data') or {}).get('id')
        check('新建对话', bool(conv_id), f'HTTP {r.status_code}')

        r = client.post('/api/chat/memory-import', headers=H,
                        json={'conversation_id': conv_id, 'memory_text': MEMORY})
        body = r.get_json() or {}
        check('导入接口返回成功', r.status_code == 200 and body.get('code') == 200,
              f'HTTP {r.status_code} {body.get("message")}')

        detail = (client.get(f'/api/conversations/{conv_id}', headers=H).get_json() or {}).get('data') or {}
        msgs = detail.get('messages') or []
        user_msgs = [m for m in msgs if m['role'] == 'user']
        ai_msgs = [m for m in msgs if m['role'] == 'assistant']
        check('记忆已作为「用户消息」写入对话',
              any(MARK in (m.get('content') or '') for m in user_msgs),
              f'user 消息 {len(user_msgs)} 条')
        check('AI 已以角色口吻回复并落库', len(ai_msgs) >= 1,
              repr((ai_msgs[-1].get('content') or '')[:40]) if ai_msgs else '无')

        print('== 2. 导入记忆写入记忆宫殿 ==')
        check('conv.imported_memory 含记忆全文', MARK in (detail.get('imported_memory') or ''))
        check('导入记忆不被滚动摘要字段混用（summary 未被写入）',
              MARK not in (detail.get('summary') or ''))
        imported_user = [m for m in user_msgs if MARK in (m.get('content') or '')]
        check('summary_upto_id 指向导入的那条用户消息',
              bool(imported_user) and detail.get('summary_upto_id') == imported_user[-1]['id'],
              f'summary_upto_id={detail.get("summary_upto_id")} '
              f'导入消息 id={imported_user[-1]["id"] if imported_user else None}')

        print('== 3. 后续对话：模型实际收到什么 ==')
        history = [{'role': m['role'], 'content': m['content']}
                   for m in msgs if m['role'] in ('user', 'assistant')]
        history.append({'role': 'user', 'content': QUESTION})
        CAPTURED.clear()
        client.post('/api/chat', headers=H, json={
            'conversation_id': conv_id, 'messages': history, 'temperature': 0.6,
        }).get_data()

        check('捕获到模型调用', len(CAPTURED) >= 1, f'{len(CAPTURED)} 次')
        if CAPTURED:
            sent = CAPTURED[0] or []
            sys_msgs = [m for m in sent if m['role'] == 'system']
            ctx_msgs = [m for m in sent if m['role'] != 'system']
            token_in_sys = any(MARK in (m.get('content') or '') for m in sys_msgs)
            token_in_ctx = [m['role'] for m in ctx_msgs if MARK in (m.get('content') or '')]

            uploaded_has_token = any(
                m['role'] == 'user' and MARK in (m.get('content') or '') for m in history)
            print(f'   前端上送历史 {len(history)} 条 / 模型实收 {len(sent)} 条')
            check('前端上送的历史里确实带着导入原文（前提成立）', uploaded_has_token)
            check('模型实收上下文中已无该原文（被摘要切片丢弃）', not token_in_ctx,
                  f'出现在 {token_in_ctx}' if token_in_ctx else '')
            check('记忆标记出现在 system 消息（导入记忆注入）', token_in_sys)

            print('== 4. 负向对照：清空导入记忆后标记应消失 ==')
            with app.app_context():
                c = db.session.get(Conversation, conv_id)
                saved = c.imported_memory
                c.imported_memory = None
                db.session.commit()
            CAPTURED.clear()
            client.post('/api/chat', headers=H, json={
                'conversation_id': conv_id, 'messages': history, 'temperature': 0.6,
            }).get_data()
            still = bool(CAPTURED) and any(
                MARK in (m.get('content') or '') for m in CAPTURED[0] if m['role'] == 'system')
            with app.app_context():
                c = db.session.get(Conversation, conv_id)
                c.imported_memory = saved
                db.session.commit()
            check('清空导入记忆后标记不再出现（证明来自记忆而非上下文）', not still)
finally:
    print('== 5. 清理测试数据 ==')
    if conv_id:
        with app.app_context():
            msg_ids = [m.id for m in Message.query.filter_by(conversation_id=conv_id).all()]
            AiUsageLog.query.filter_by(conversation_id=conv_id).delete(synchronize_session=False)
            if msg_ids:
                AiUsageLog.query.filter(AiUsageLog.message_id.in_(msg_ids)).delete(
                    synchronize_session=False)
            Message.query.filter_by(conversation_id=conv_id).delete(synchronize_session=False)
            ConversationSummary.query.filter_by(conversation_id=conv_id).delete(synchronize_session=False)
            c = db.session.get(Conversation, conv_id)
            if c:
                db.session.delete(c)
            db.session.commit()
            left = (Message.query.filter_by(conversation_id=conv_id).count()
                    + Conversation.query.filter_by(id=conv_id).count())
        check('测试对话与消息已清理', left == 0, f'残留 {left}')

print()
print('结果：' + ('全部通过 ✅' if ok else '存在失败项 ❌'))
sys.exit(0 if ok else 1)
