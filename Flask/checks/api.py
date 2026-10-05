"""接口健康巡检：把所有主要 API 都真实打一遍，看是否有 5xx / 异常返回。

用法：python checks/api.py            （用 Flask 测试客户端，不依赖已启动的服务）

覆盖：健康检查、认证、用户设置、模型配置、对话与消息、人设卡、卡片广场、
      记忆（摘要/记忆宫殿）、世界书、提示词工具、反馈、签到、上传、
      图片生成（只读探测，不真正生图）、管理员后台主要列表。
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from extensions import db
from models import User, Conversation

app = create_app()

results = []


def call(client, method, path, headers=None, label=None, json_body=None, expect=(200,), **kw):
    """发一个请求并记录结果。expect 为可接受的状态码集合。"""
    fn = getattr(client, method)
    if json_body is not None:
        resp = fn(path, json=json_body, headers=headers, **kw)
    else:
        resp = fn(path, headers=headers, **kw)
    code = resp.status_code
    body = None
    try:
        body = resp.get_json()
    except Exception:
        pass
    msg = (body or {}).get('message') if isinstance(body, dict) else None
    ok = code in expect
    results.append((ok, method.upper(), path, code, msg or ''))
    print(('  [OK]   ' if ok else '  [FAIL] ') + f'{method.upper():6} {path:52} -> {code}' +
          (f'  {msg}' if msg else ''))
    return resp


with app.app_context():
    from flask_jwt_extended import create_access_token

    user = User.query.order_by(User.id).first()
    token = create_access_token(identity=str(user.id), additional_claims={'tv': user.token_version})
    H = {'Authorization': f'Bearer {token}'}
    conv = Conversation.query.filter_by(user_id=user.id).order_by(Conversation.id).first()
    conv_id = conv.id if conv else None
    print(f'测试用户 id={user.id} 对话 id={conv_id}\n')

    c = app.test_client()

    print('== 公开 / 健康检查 ==')
    r = call(c, 'get', '/api/health', label='健康检查')
    if r.status_code == 200:
        print('        ', r.get_json())

    print('== 认证（未登录应 401，不崩）==')
    call(c, 'get', '/api/conversations', expect=(401,))
    call(c, 'get', '/api/settings', expect=(401,))
    call(c, 'get', '/api/auth/userinfo', expect=(401,))
    call(c, 'get', '/api/marketplace/public')
    call(c, 'get', '/api/marketplace/genders', expect=(200, 401))

    print('== 用户 / 设置 ==')
    call(c, 'get', '/api/auth/userinfo', headers=H)
    call(c, 'get', '/api/settings', headers=H)
    call(c, 'get', '/api/marketplace/checkin/status', headers=H)

    print('== 模型配置 ==')
    call(c, 'get', '/api/providers', headers=H)
    call(c, 'get', '/api/providers?type=chat', headers=H)
    call(c, 'get', '/api/providers?type=image', headers=H)
    call(c, 'get', '/api/providers/all', headers=H)
    call(c, 'get', '/api/providers/vendors', headers=H)
    call(c, 'get', '/api/providers/config-schema', headers=H)
    # 模型列表依赖用户自己的 Key：Key 失效是数据问题而非接口故障，
    # 这里接受 200（正常）与 400（已翻译成可执行提示）
    call(c, 'get', '/api/chat/models', headers=H, expect=(200, 400))

    print('== 对话与消息 ==')
    call(c, 'get', '/api/conversations', headers=H)
    if conv_id:
        r = call(c, 'get', f'/api/conversations/{conv_id}', headers=H)
        d = (r.get_json() or {}).get('data') or {}
        print(f'        详情字段：{sorted(d.keys())[:12]}')
        # 消息随对话详情一起返回（没有独立的 GET 消息路由）
        msgs = d.get('messages')
        print(f'        含消息：{len(msgs) if isinstance(msgs, list) else "无"}')
        call(c, 'get', f'/api/conversations/{conv_id}/summaries', headers=H)
    call(c, 'get', '/api/chat/status', headers=H)
    call(c, 'get', '/api/chat/prompt-tool', headers=H)

    print('== 人设 / 卡片广场 ==')
    call(c, 'get', '/api/personas', headers=H)
    call(c, 'get', '/api/marketplace?page=1&per_page=5', headers=H)
    call(c, 'get', '/api/marketplace/public?page=1&per_page=5')

    print('== 世界书 / 人设详情 ==')
    r = call(c, 'get', '/api/personas', headers=H)
    plist = (r.get_json() or {}).get('data') or []
    if plist:
        pid = plist[0].get('id')
        call(c, 'get', f'/api/personas/{pid}', headers=H)
        call(c, 'get', f'/api/personas/{pid}/worldbook', headers=H)

    print('== 其他 ==')
    call(c, 'get', '/api/audio/voices', headers=H)
    call(c, 'post', '/api/marketplace/checkin', headers=H, expect=(200, 400, 403))

    print('== 上传 ==')
    png = bytes.fromhex(
        '89504e470d0a1a0a0000000d494844520000000100000001080600000'
        '01f15c4890000000d4944415478da63f8cfc0f01f0005fe01ffabce3689'
        '0000000049454e44ae426082')
    call(c, 'post', '/api/upload/image', headers=H,
         data={'file': (io.BytesIO(png), 'probe.png')},
         content_type='multipart/form-data')

    print('== 生图（只读探测：缺参应 400，不该 500）==')
    call(c, 'post', '/api/image/generate', headers=H, json_body={}, expect=(400,))

    print('== 管理员后台 ==')
    admin_token = create_access_token(identity='admin', additional_claims={'role': 'admin'})
    AH = {'Authorization': f'Bearer {admin_token}'}
    for path in ('/api/admin/me',
                 '/api/admin/users?page=1&per_page=5',
                 '/api/admin/stats',
                 '/api/admin/conversation-media-logs?page=1&per_page=5',
                 '/api/admin/prompt-tool-logs?page=1&per_page=5',
                 '/api/admin/marketplace?page=1&per_page=5',
                 '/api/feedback?page=1&per_page=5'):
        call(c, 'get', path, headers=AH, expect=(200, 404))
    if conv_id:
        call(c, 'get', f'/api/admin/conversations/{conv_id}/messages', headers=AH)
        call(c, 'get', f'/api/admin/conversations/{conv_id}/export', headers=AH)

    print('== 权限边界（普通用户不该进后台）==')
    call(c, 'get', '/api/admin/users?page=1&per_page=5', headers=H, expect=(401, 403))
    call(c, 'get', '/api/feedback', headers=H, expect=(401, 403))

failed = [r for r in results if not r[0]]
print()
print(f'共 {len(results)} 个接口，失败 {len(failed)} 个')
for ok, method, path, code, msg in failed:
    print(f'  ❌ {method} {path} -> {code} {msg}')
print('结果：' + ('全部正常 ✅' if not failed else '存在异常 ❌'))
sys.exit(0 if not failed else 1)
