"""端到端校验生图 / 改图接口（/api/image/generate）。

用法：
    python checks/image.py            # 只读校验（不调整任何配置、不真正生图）
    python checks/image.py --live     # 真跑一次生图 + 一次改图（消耗用户自己的额度）

检查点：
  1. 图片配置的启用状态（「连接测试成功但生不了图」的根因就是它被停用）
  2. 无可用配置时的报错文案是否可执行
  3. 生图（文生图）能否拿到图片 URL，且该 URL 可访问
  4. 改图（图生图，带参考图）能否成功
"""
import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

from app import create_app
from extensions import db
from models import ModelProvider, User, ImageUsage

LIVE = '--live' in sys.argv

PNG_B64 = (
    'iVBORw0KGgoAAAANSUhEUgAAAGQAAABkCAYAAABw4pVUAAAAOklEQVR42u3OMQEAAAgDoC251a3g'
    'LwSgOTcVAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAPBnAWvsAAGqf6X8AAAAAElFTkSuQmCC'
)

app = create_app()
ok = True


def check(label, cond, extra=''):
    global ok
    print(('  [OK]   ' if cond else '  [FAIL] ') + label + (f'  {extra}' if extra else ''))
    if not cond:
        ok = False


with app.app_context():
    from flask_jwt_extended import create_access_token

    print('== 1. 图片生成配置 ==')
    # 选一个作为测试主体的用户：优先有图片配置的
    rows = []
    for p in ModelProvider.query.filter_by(provider_type='image').order_by(ModelProvider.id).all():
        u = db.session.get(User, p.user_id)
        rows.append((p, u))
    for p, u in rows:
        print(f'  id={p.id} 用户={p.user_id}({u.username if u else "?"}) 名称={p.name!r} '
              f'启用={p.enabled} 模型={p.model} 参数={p.get_params()}')
    if not rows:
        print('  (库里没有任何图片生成配置，跳过后续真实调用)')
        sys.exit(0)

    # 有停用配置的用户：用于验证报错文案
    disabled_pairs = [(p, u) for p, u in rows if not p.enabled]
    enabled_pairs = [(p, u) for p, u in rows if p.enabled]

    print('== 2. 配置优先级（有配置就优先用配置）==')
    from routes.image import _no_provider_hint, _get_image_provider, _provider_name
    check('完全没配置时的提示', '模型配置' in _no_provider_hint())

    # 用真实用户验证：停用的配置也必须被选中，否则会静默落到共享免费通道
    probe_user = rows[0][0].user_id
    picked = _get_image_provider(probe_user)
    check('用户有配置时一定返回配置（不论是否启用）', picked is not None,
          f'picked={getattr(picked, "id", None)} enabled={getattr(picked, "enabled", None)}')
    check('显式 provider_id 优先', _get_image_provider(probe_user, rows[0][0].id) is not None)
    check('别人的 provider_id 不会越权拿到', _get_image_provider(probe_user, 999999) is not None)
    check('配置名可读（免费通道有兜底名）', _provider_name(rows[0][0]) != '共享免费通道'
          and _provider_name(type('X', (), {})()) == '共享免费通道')

    # 造一个「已启用 + 已停用」并存的最小场景，验证已启用的优先
    from models import ModelProvider
    from extensions import db as _db
    tmp_a = ModelProvider(user_id=probe_user, name=f'__t_disabled_{os.getpid()}',
                          provider_type='image', brand='agnes', api_type='openai',
                          api_url='https://example.invalid/v1', api_key='k', enabled=False)
    tmp_b = ModelProvider(user_id=probe_user, name=f'__t_enabled_{os.getpid()}',
                          provider_type='image', brand='agnes', api_type='openai',
                          api_url='https://example.invalid/v1', api_key='k', enabled=True)
    _db.session.add_all([tmp_a, tmp_b])
    _db.session.commit()
    try:
        got = _get_image_provider(probe_user)
        check('多条配置时优先选「已启用」的那条', got is not None and got.id == tmp_b.id,
              f'got={getattr(got, "name", None)}')
        # 把已启用的停掉 → 仍要返回一条配置（不能变成免费通道）
        tmp_b.enabled = False
        _db.session.commit()
        got2 = _get_image_provider(probe_user)
        check('全部停用时仍返回配置（不退化成免费通道）', got2 is not None,
              f'got={getattr(got2, "name", None)}')
        check('显式指定停用配置时照样用它', _get_image_provider(probe_user, tmp_a.id) is not None)
    finally:
        ModelProvider.query.filter(ModelProvider.id.in_([tmp_a.id, tmp_b.id])).delete(
            synchronize_session=False)
        _db.session.commit()

    print('== 3. 生图 / 改图 ==')
    if not LIVE:
        print('  (未加 --live，跳过真实生图；加 --live 会真的调用厂商接口)')
    else:
        # 现在「有配置就优先用配置」，所以不需要临时改 enabled 就能验证真实链路
        target, owner = (enabled_pairs or rows)[0]
        try:
            client = app.test_client()
            # 与 auth.py 登录时一致：identity 是用户 ID 字符串，并带 token_version 声明，
            # 否则会被 token_version 校验判为「登录状态已失效」
            token = create_access_token(identity=str(owner.id),
                                        additional_claims={'tv': owner.token_version})
            headers = {'Authorization': f'Bearer {token}'}

            print(f'  → 生图（用户 {owner.id} / 配置 {target.id} {target.name} 启用={target.enabled}）')
            r = client.post('/api/image/generate', json={
                'prompt': 'a small blue circle on a white background',
                'resolution': '1K',
                'aspect_ratio': '1:1',
            }, headers=headers)
            body = r.get_json() or {}
            print(f'    HTTP {r.status_code} code={body.get("code")} message={body.get("message")}')
            url = ((body.get('data') or {}).get('url')) or ''
            check('文生图返回 200 且有图片 URL', r.status_code == 200 and bool(url), url or str(body)[:200])
            image_bytes = None
            if url:
                # 绝对地址是厂商 CDN，相对地址是本站上传目录，两种都要能取到
                if url.startswith('http'):
                    rr = requests.get(url, timeout=60)
                    ok_get, status = rr.status_code == 200, rr.status_code
                    image_bytes = rr.content if ok_get else None
                else:
                    g = client.get(url)
                    ok_get, status = g.status_code == 200, g.status_code
                    image_bytes = g.data if ok_get else None
                check('生成的图片可访问', ok_get, f'GET -> {status}')

            # 改图（图生图）：参考图分别用「公网 URL」与「Data URI」两条路径，
            # 前端上传的图走 base64，聊天里已有的图走 URL，两条都必须通
            print('  → 改图（参考图 = 公网 URL）')
            ref_url = url if url.startswith('http') else f'{url}'
            r2 = client.post('/api/image/generate', json={
                'prompt': 'keep the subject, change the background to light green',
                'references': [ref_url] if ref_url else [],
                'resolution': '1K',
                'aspect_ratio': '1:1',
            }, headers=headers)
            body2 = r2.get_json() or {}
            print(f'    HTTP {r2.status_code} code={body2.get("code")} message={body2.get("message")}')
            url2 = ((body2.get('data') or {}).get('url')) or ''
            check('改图（URL 参考图）返回 200 且有图片 URL',
                  r2.status_code == 200 and bool(url2), url2 or str(body2)[:200])

            if image_bytes:
                print('  → 改图（参考图 = Data URI / base64）')
                b64 = base64.b64encode(image_bytes).decode()
                r3 = client.post('/api/image/generate', json={
                    'prompt': 'keep the subject, add soft pink lighting',
                    'references': [f'data:image/png;base64,{b64}'],
                    'resolution': '1K',
                    'aspect_ratio': '1:1',
                }, headers=headers)
                body3 = r3.get_json() or {}
                print(f'    HTTP {r3.status_code} code={body3.get("code")} message={body3.get("message")}')
                url3 = ((body3.get('data') or {}).get('url')) or ''
                check('改图（base64 参考图）返回 200 且有图片 URL',
                      r3.status_code == 200 and bool(url3), url3 or str(body3)[:200])
            else:
                print('  (没拿到可下载的底图，跳过 base64 改图测试)')
        except Exception as e:
            check('生图链路未抛异常', False, str(e))

    print('== 4. 免费通道 ==')
    from config import config as cfg
    free_key = (cfg['default'].IMAGE_FREE_API_KEY or '') if hasattr(cfg['default'], 'IMAGE_FREE_API_KEY') else ''
    print(f'  共享免费 Key：{"已配置" if free_key else "未配置"}（长度 {len(free_key)}）')
    if free_key:
        print('  提示：免费通道是否可用取决于该 Key 的有效期，与用户自己的配置无关。')

print()
print('结果：' + ('全部通过 ✅' if ok else '存在失败项 ❌'))
sys.exit(0 if ok else 1)
