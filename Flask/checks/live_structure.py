"""实测「结构规范」是否真的让模型按固定结构输出。

做法：取一个已启用的对话配置，把**和线上完全一样的注入文本**
（人设 + reply_spec.compose_reply_spec）发一次真实请求，核对回复的构件结构。

不碰任何对话数据、不写库 —— 只是拿同一份提示词问一次模型。

用法：python checks/live_structure.py [用户ID] [篇幅]
      篇幅 = short / medium / long（默认 short，省 token）
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import User, ModelProvider
from reply_spec import compose_reply_spec
from services.ai_service import AIService

UID = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 7
LENGTH = sys.argv[2] if len(sys.argv) > 2 else 'short'

SYSTEM_PROMPT = (
    '你是「沈昭」，25 岁，独立书店店员，说话慢、有点冷淡但细心。\n'
    '玩家是常来店里的熟客，两人认识三个月，关系处于互相试探的阶段。'
)

app = create_app()
ok = True


def check(label, cond, extra=''):
    global ok
    print(('  [OK]   ' if cond else '  [FAIL] ') + label + (f'  {extra}' if extra else ''))
    if not cond:
        ok = False


with app.app_context():
    user = User.query.filter_by(id=UID).first()
    if not user:
        print(f'用户 {UID} 不存在')
        sys.exit(1)
    chat_prov = ModelProvider.query.filter_by(
        user_id=UID, provider_type='chat', enabled=True).order_by(ModelProvider.id).first()
    if not chat_prov:
        print(f'用户 {UID} 没有启用的对话配置，无法实测')
        sys.exit(1)

    spec = compose_reply_spec('full', LENGTH, True)
    system = SYSTEM_PROMPT + '\n\n' + spec
    # 模型名与线上一致地从配置的模型列表里取（provider.model 常常为空）
    model = chat_prov.model or next(
        (m.model_id for m in (chat_prov.models or []) if m.enabled), None)
    if not model:
        print(f'配置 #{chat_prov.id} 没有可用模型，无法实测')
        sys.exit(1)
    # 思考开关关闭：与普通聊天默认一致（不带思考过程，结构看得更清楚）
    print(f'用户 {UID}，对话配置 #{chat_prov.id} {chat_prov.name}，模型={model}，'
          f'篇幅={LENGTH}，注入规范 {len(spec)} 字')

    messages = [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': '（我在书架前站了很久，最后只问了一句："这本，你读过吗？"）'},
    ]
    print('  → 发起一次真实请求（会消耗少量额度）…')
    resp, err = AIService.chat_completions(
        chat_prov, messages, stream=False, model=model, deep_think=False,
    )
    if err:
        print(f'  请求失败：{err}')
        sys.exit(1)
    data = resp if isinstance(resp, dict) else resp.json()
    content = ''
    try:
        content = data['choices'][0]['message']['content'] or ''
    except Exception:
        print('  响应结构异常：' + json.dumps(data, ensure_ascii=False)[:300])
        sys.exit(1)
    print(f'  收到回复 {len(content)} 字')

    check('模型产出了回复', bool(content.strip()))

    names = []
    for line in content.split('\n'):
        ls = line.strip()
        if ls.startswith('【') and '】' in ls:
            names.append(ls[1:ls.index('】')])
    print('  构件顺序：' + ' → '.join(names))

    need = {
        '场景条': ('场景' in names) or ('状态条' in names),
        '玩家信息': '玩家信息' in content,
        '角色信息': '角色信息' in content,
        '身体状态': '身体状态' in content,
        '精神心理': '精神心理' in content,
        '状态': '状态' in names,
        '内心': '内心' in names,
        '记忆': '记忆' in names,
        '推演': '推演' in names,
    }
    for k, v in need.items():
        check(f'包含 {k}', v)
    check('场景条只写一个', not ('场景' in names and '状态条' in names),
          '同时出现【场景】与【状态条】')
    check('没有一行挤两个标记',
          not any(sum(1 for n in ('场景', '状态条', '面板', '状态', '内心', '记忆', '推演')
                      if f'【{n}】' in line) >= 2
                  for line in content.split('\n') if line.strip().startswith('【')))
    if '推演' in names and ('场景' in names or '状态条' in names):
        first_scene = min([names.index(n) for n in ('场景', '状态条') if n in names])
        check('场景条在推演之前', first_scene < names.index('推演'))
    for line in content.split('\n'):
        if line.strip().startswith('【场景】') or line.strip().startswith('【状态条】'):
            check('场景条字段写了名字（地点:/时间:）',
                  ('地点' in line or '时间' in line), line.strip()[:90])
            break

    print()
    print('  ---- 回复结构预览 ----')
    for line in content.split('\n'):
        ls = line.strip()
        if ls.startswith('【'):
            print('   ' + (ls[:100] + ('…' if len(ls) > 100 else '')))

print()
print('结果：' + ('结构符合规范 ✅' if ok else '有不符合项 ❌（可把对应例句补进 reply_spec.py）'))
sys.exit(0 if ok else 1)
