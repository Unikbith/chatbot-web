"""校验「卡片广场」与「人物卡」字段对齐：玩家设定 + 世界书，且都可选。

走真实 HTTP 接口（Flask 测试客户端），最后把测试数据全部清理干净。

检查点：
  1. 玩家设定 / 世界书都不填 → 仍能发布（可选）
  2. 填了就存下来，详情接口能读回
  3. 编辑：可以改玩家设定、整表替换世界书、用空数组清空世界书
  4. 采用（adopt）：玩家设定与世界书条目一并复制成采用者自己的数据
  5. 边界：正文为空的世界书条目被忽略；超过 20 条被截断
  6. 清理：发布/采用产生的数据全部删除
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from extensions import db
from models import (User, PersonaMarketplace, MarketplaceAdopt, PersonaTemplate,
                    WorldBookEntry, MarketplaceWorldbookEntry)

UID = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 1

app = create_app()
ok = True


def check(label, cond, extra=''):
    global ok
    print(('  [OK]   ' if cond else '  [FAIL] ') + label + (f'  {extra}' if extra else ''))
    if not cond:
        ok = False


PNG = ('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8'
       'z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==')
MARK = f'__mk_probe_{os.getpid()}__'


def card_payload(**over):
    data = {
        'name': MARK,
        'description': '这是一张用于自动校验的测试卡片，描述需要至少三十个字，所以这里补足长度凑数。',
        'system_prompt': '你是一位安静的图书管理员。' * 12,
        'greeting': '你来了。',
        'avatar': PNG,
        'gender': '女',
    }
    data.update(over)
    return data


with app.app_context():
    from flask_jwt_extended import create_access_token

    user = User.query.filter_by(id=UID).first()
    if not user:
        print(f'用户 {UID} 不存在')
        sys.exit(1)
    token = create_access_token(identity=str(UID), additional_claims={'tv': user.token_version})
    H = {'Authorization': f'Bearer {token}'}
    before = PersonaMarketplace.query.filter(PersonaMarketplace.name.like(f'%{MARK}%')).count()
    print(f'用户 {UID}，开始校验（测试卡前缀 {MARK}）')

    client = app.test_client()
    created_ids = []
    adopted_tpl_ids = []
    try:
        print('== 1. 玩家设定 / 世界书都不填（可选）==')
        r = client.post('/api/marketplace', headers=H, json=card_payload())
        body = r.get_json() or {}
        pid = (body.get('data') or {}).get('id')
        if pid:
            created_ids.append(pid)
        check('不填这两项也能发布', r.status_code == 200 and body.get('code') == 200,
              f'HTTP {r.status_code} {body.get("message")}')
        check('详情里玩家设定为空、世界书为空数组',
              (body.get('data') or {}).get('user_prompt') in (None, '')
              and (body.get('data') or {}).get('worldbook') == [],
              str({k: (body.get('data') or {}).get(k) for k in ('user_prompt', 'worldbook')}))

        print('== 2. 填了就存下来 ==')
        r = client.post('/api/marketplace', headers=H, json=card_payload(
            name=MARK + '_full',
            user_prompt='你是 32 岁的编辑，与她是多年笔友。',
            worldbook=[
                {'title': '世界观', 'keywords': '', 'content': '故事发生在一座多雨的南方小城。', 'always_on': True},
                {'title': '称呼', 'keywords': '称呼,名字', 'content': '她只在你叫她小名时才答应。'},
                {'title': '空壳', 'keywords': 'x', 'content': '   '},   # 应被忽略
            ],
        ))
        body = r.get_json() or {}
        pid2 = (body.get('data') or {}).get('id')
        if pid2:
            created_ids.append(pid2)
        d = body.get('data') or {}
        check('带玩家设定 + 世界书发布成功', r.status_code == 200 and body.get('code') == 200,
              f'HTTP {r.status_code} {body.get("message")}')
        check('玩家设定已保存', d.get('user_prompt') == '你是 32 岁的编辑，与她是多年笔友。', str(d.get('user_prompt')))
        check('世界书 2 条（空正文的条目被忽略）', len(d.get('worldbook') or []) == 2,
              str([e.get('title') for e in (d.get('worldbook') or [])]))
        check('常驻标记保留',
              (d.get('worldbook') or [{}])[0].get('always_on') is True)

        print('== 3. 详情接口读回 ==')
        r = client.get(f'/api/marketplace/{pid2}', headers=H)
        d = (r.get_json() or {}).get('data') or {}
        check('详情包含玩家设定与世界书',
              d.get('user_prompt') and len(d.get('worldbook') or []) == 2,
              f'user_prompt={bool(d.get("user_prompt"))} wb={len(d.get("worldbook") or [])}')

        print('== 4. 编辑：改玩家设定 / 替换世界书 / 清空 ==')
        r = client.put(f'/api/marketplace/{pid2}', headers=H, json={
            'user_prompt': '你是刚从外地调来的记者。',
            'worldbook': [{'title': '新条目', 'keywords': '雨', 'content': '下雨天她总会想起那通电话。'}],
        })
        d = (r.get_json() or {}).get('data') or {}
        check('编辑后玩家设定已更新', d.get('user_prompt') == '你是刚从外地调来的记者。', str(d.get('user_prompt')))
        check('世界书被整表替换为 1 条', len(d.get('worldbook') or []) == 1,
              str([e.get('title') for e in (d.get('worldbook') or [])]))
        r = client.put(f'/api/marketplace/{pid2}', headers=H, json={'worldbook': []})
        d = (r.get_json() or {}).get('data') or {}
        check('提交空数组可清空世界书', (d.get('worldbook') or []) == [], str(d.get('worldbook')))
        r = client.put(f'/api/marketplace/{pid2}', headers=H, json={'worldbook': [{'title': 'a', 'content': '回来一条'}]})
        d = (r.get_json() or {}).get('data') or {}
        check('清空后还能再加回来', len(d.get('worldbook') or []) == 1)

        print('== 5. 采用：玩家设定 + 世界书一起带过来 ==')
        with app.app_context():
            ai_count = PersonaTemplate.query.filter_by(user_id=UID, persona_type='ai').count()
        if ai_count >= 10:
            print(f'  (人物卡已满 {ai_count}/10，跳过采用校验)')
        else:
            r = client.post(f'/api/marketplace/{pid2}/adopt', headers=H)
            body = r.get_json() or {}
            tpl = body.get('data') or {}
            tpl_id = tpl.get('id')
            if tpl_id:
                adopted_tpl_ids.append(tpl_id)
            check('采用成功', r.status_code == 200 and body.get('code') == 200,
                  f'HTTP {r.status_code} {body.get("message")}')
            check('玩家设定已复制到人物卡', tpl.get('user_prompt') == '你是刚从外地调来的记者。',
                  str(tpl.get('user_prompt')))
            check('世界书条目已复制', tpl.get('worldbook_count') == 1, str(tpl.get('worldbook_count')))
            if tpl_id:
                r = client.get(f'/api/personas/{tpl_id}/worldbook', headers=H)
                items = (r.get_json() or {}).get('data') or []
                check('复制出来的世界书挂在该人物卡下',
                      len(items) == 1 and items[0].get('content') == '回来一条',
                      str(items)[:160])

        print('== 6. 边界：条目数量上限 ==')
        many = [{'title': f'条目{i}', 'keywords': 'k', 'content': f'内容{i}'} for i in range(30)]
        r = client.post('/api/marketplace', headers=H, json=card_payload(name=MARK + '_many', worldbook=many))
        body = r.get_json() or {}
        pid3 = (body.get('data') or {}).get('id')
        if pid3:
            created_ids.append(pid3)
        got = len((body.get('data') or {}).get('worldbook') or [])
        check('超过 20 条被截断到 20', got == 20, f'got={got}')

    finally:
        print('== 7. 清理测试数据 ==')
        with app.app_context():
            for pid in created_ids:
                MarketplaceWorldbookEntry.query.filter_by(persona_id=pid).delete(synchronize_session=False)
                MarketplaceAdopt.query.filter_by(persona_id=pid).delete(synchronize_session=False)
                PersonaMarketplace.query.filter_by(id=pid).delete(synchronize_session=False)
            for tid in adopted_tpl_ids:
                WorldBookEntry.query.filter_by(persona_id=tid).delete(synchronize_session=False)
                PersonaTemplate.query.filter_by(id=tid).delete(synchronize_session=False)
            # 兜底：名字带前缀的残留卡片
            leftovers = PersonaMarketplace.query.filter(PersonaMarketplace.name.like(f'%{MARK}%')).all()
            for p in leftovers:
                MarketplaceWorldbookEntry.query.filter_by(persona_id=p.id).delete(synchronize_session=False)
                MarketplaceAdopt.query.filter_by(persona_id=p.id).delete(synchronize_session=False)
                db.session.delete(p)
            db.session.commit()
            after = PersonaMarketplace.query.filter(PersonaMarketplace.name.like(f'%{MARK}%')).count()
            orphan = MarketplaceWorldbookEntry.query.filter(
                MarketplaceWorldbookEntry.persona_id.notin_(
                    db.session.query(PersonaMarketplace.id))).count()
        check('测试卡片已清理', after == before, f'{after} vs {before}')
        check('没有留下孤儿世界书条目', orphan == 0, f'orphan={orphan}')

print()
print('结果：' + ('全部通过 ✅' if ok else '存在失败项 ❌'))
sys.exit(0 if ok else 1)
