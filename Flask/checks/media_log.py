"""校对：对话素材记录（conversation_media_logs）全链路是否真的记全了。

覆盖场景：
  1. 系统设置的用户头像 / AI 头像 / 背景图  → profile_*
  2. 对话设置的背景图 / AI 头像 / 用户头像  → background / ai_avatar / user_avatar（带 conversation_id）
  3. 聊天时上传的图片（/api/upload/image）  → upload
  4. conversation_id 已允许为空（系统级素材）
  5. 同值重复设置不产生重复记录
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from extensions import db
from models import ConversationMediaLog, User, UserSettings, Conversation

app = create_app()

PNG = ('data:image/png;base64,'
       'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==')

ok = True


def check(label, cond, extra=''):
    global ok
    print(('  [OK]   ' if cond else '  [FAIL] ') + label + (f'  {extra}' if extra else ''))
    if not cond:
        ok = False


with app.app_context():
    print('== 1. 表结构 ==')
    from sqlalchemy import inspect
    cols = {c['name']: c for c in inspect(db.engine).get_columns('conversation_media_logs')}
    check('conversation_id 存在', 'conversation_id' in cols)
    check('conversation_id 允许为空', cols.get('conversation_id', {}).get('nullable') is True,
          f"nullable={cols.get('conversation_id', {}).get('nullable')}")
    check('media_type / value / created_at 齐全',
          {'media_type', 'value', 'created_at'} <= set(cols))

    user = User.query.order_by(User.id).first()
    if not user:
        print('!! 库里没有用户，跳过写读校验')
        sys.exit(0)
    uid = user.id
    settings = UserSettings.query.filter_by(user_id=uid).first()
    conv = Conversation.query.filter_by(user_id=uid).order_by(Conversation.id).first()
    print(f'  使用用户 id={uid}，对话 id={conv.id if conv else None}')

    before = ConversationMediaLog.query.count()
    print(f'  记录数(前)={before}')

    print('== 2. 系统设置头像/背景（settings.update_profile / update_settings 的写入口）==')
    from services.media_log import log_media
    stamp = f'{PNG}#profile-{os.getpid()}'
    log_media(uid, 'profile_avatar', stamp)
    log_media(uid, 'profile_ai_avatar', stamp + '-ai')
    log_media(uid, 'profile_background', stamp + '-bg')
    db.session.commit()
    check('系统级记录已写入',
          ConversationMediaLog.query.filter(
              ConversationMediaLog.user_id == uid,
              ConversationMediaLog.media_type.in_(['profile_avatar', 'profile_ai_avatar', 'profile_background']),
              ConversationMediaLog.value.like(f'%profile-{os.getpid()}%'),
          ).count() == 3)
    rec = ConversationMediaLog.query.filter_by(user_id=uid, media_type='profile_background').order_by(
        ConversationMediaLog.id.desc()).first()
    check('系统级记录 conversation_id 为空', rec.conversation_id is None, f'conversation_id={rec.conversation_id}')
    check('系统级记录有中文标签', rec.to_dict()['media_type_label'] == '系统背景图',
          rec.to_dict()['media_type_label'])

    print('== 3. 对话设置素材 ==')
    if conv:
        log_media(uid, 'background', stamp + '-convbg', conversation_id=conv.id)
        log_media(uid, 'ai_avatar', stamp + '-convai', conversation_id=conv.id)
        log_media(uid, 'user_avatar', stamp + '-convuser', conversation_id=conv.id)
        db.session.commit()
        rows = ConversationMediaLog.query.filter(
            ConversationMediaLog.conversation_id == conv.id,
            ConversationMediaLog.value.like(f'%profile-{os.getpid()}%'),
        ).all()
        check('对话级记录带 conversation_id', len(rows) == 3, f'got={len(rows)}')
        check('对话级记录带对话标题字段', rows and rows[0].to_dict().get('conversation_title') is not None,
              str(rows[0].to_dict().get('conversation_title')) if rows else '')

    print('== 4. 聊天上传图片 ==')
    log_media(uid, 'upload', f'/api/upload/image/test_{os.getpid()}.png')
    db.session.commit()
    up = ConversationMediaLog.query.filter_by(user_id=uid, media_type='upload').order_by(
        ConversationMediaLog.id.desc()).first()
    check('上传记录已写入', up is not None and str(os.getpid()) in (up.value or ''))
    check('上传标签正确', up and up.to_dict()['media_type_label'] == '上传图片',
          up.to_dict()['media_type_label'] if up else '')

    print('== 5. 去重 ==')
    n1 = ConversationMediaLog.query.count()
    log_media(uid, 'upload', f'/api/upload/image/test_{os.getpid()}.png')
    db.session.commit()
    n2 = ConversationMediaLog.query.count()
    check('同值重复上传不再记录', n1 == n2, f'{n1} -> {n2}')

    print('== 6. 后台筛选可用 ==')
    from routes.admin import MEDIA_LOG_TYPES
    check('7 种类型都在筛选白名单里', set(MEDIA_LOG_TYPES) == {
        'background', 'ai_avatar', 'user_avatar',
        'profile_background', 'profile_avatar', 'profile_ai_avatar', 'upload'})

    print('== 7. 真实接口串联（走 HTTP，验证接线而不只是函数）==')
    from flask_jwt_extended import create_access_token
    from models import ConversationMediaLog as ML
    client = app.test_client()
    tok = create_access_token(identity=str(uid), additional_claims={'tv': user.token_version})
    HD = {'Authorization': f'Bearer {tok}'}

    def rows_of(mtype, like=None):
        q = ML.query.filter(ML.user_id == uid, ML.media_type == mtype)
        if like:
            q = q.filter(ML.value.like(like))
        return q.all()

    # 备份原始素材，测完原样还原，避免污染账号
    orig_settings = UserSettings.query.filter_by(user_id=uid).first()
    orig_avatar, orig_bg = user.avatar, (orig_settings.background_image if orig_settings else None)
    orig_conv_bg = conv.background_image if conv else None
    mark = f'http-{os.getpid()}'

    try:
        # 7.1 上传接口 → upload
        # 注意：上传接口会用 uuid 重命名文件，URL 里不含原文件名，
        # 所以这里用「记录数增量」判断，而不是拿文件名去 LIKE 匹配
        import io
        uploads_before = ML.query.filter_by(user_id=uid, media_type='upload').count()
        png_bytes = __import__('base64').b64decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==')
        r = client.post('/api/upload/image', headers=HD,
                        data={'file': (io.BytesIO(png_bytes), f'{mark}.png')},
                        content_type='multipart/form-data')
        up_url = ((r.get_json() or {}).get('data') or {}).get('url') or ''
        uploads_after = ML.query.filter_by(user_id=uid, media_type='upload').count()
        check('上传图片后自动记录 upload', r.status_code == 200 and uploads_after == uploads_before + 1,
              f'HTTP {r.status_code} {uploads_before} -> {uploads_after} url={up_url}')
        newest = ML.query.filter_by(user_id=uid, media_type='upload').order_by(ML.id.desc()).first()
        check('上传记录不挂对话', newest is not None and newest.conversation_id is None,
              f'conversation_id={newest.conversation_id if newest else None}')
        if newest:
            newest_id = newest.id

        # 7.2 系统设置资料头像 → profile_avatar
        r = client.put('/api/settings/profile', headers=HD,
                       json={'avatar': f'/api/upload/image/{mark}-avatar.png'})
        check('系统设置改头像后记录 profile_avatar',
              r.status_code == 200 and len(rows_of('profile_avatar', f'%{mark}%')) == 1,
              f'HTTP {r.status_code}')

        # 7.3 系统设置背景图 → profile_background
        r = client.put('/api/settings', headers=HD,
                       json={'background_image': f'/api/upload/image/{mark}-bg.png'})
        check('系统设置改背景后记录 profile_background',
              r.status_code == 200 and len(rows_of('profile_background', f'%{mark}%')) == 1,
              f'HTTP {r.status_code}')

        # 7.4 对话设置背景图 → background（带 conversation_id）
        if conv:
            r = client.put(f'/api/conversations/{conv.id}', headers=HD,
                           json={'background_image': f'/api/upload/image/{mark}-convbg.png'})
            got = rows_of('background', f'%{mark}%')
            check('对话设置改背景后记录 background 且带 conversation_id',
                  r.status_code == 200 and len(got) == 1 and got[0].conversation_id == conv.id,
                  f'HTTP {r.status_code} rows={len(got)}')

        # 7.5 后台接口能查到这些记录（管理员视角）
        admin_tok = create_access_token(identity='admin', additional_claims={'role': 'admin'})
        r = client.get(f'/api/admin/conversation-media-logs?user_id={uid}&per_page=50',
                       headers={'Authorization': f'Bearer {admin_tok}'})
        items = ((r.get_json() or {}).get('data') or {}).get('items') or []
        ids = {i['id'] for i in items}
        labels = {i['media_type_label'] for i in items if i['id'] in ids and (
            mark in (i.get('value') or '') or i['id'] == newest_id)}
        check('后台「对话素材记录」能看到这几类新记录', len(labels) >= 4, str(sorted(labels)))
        check('后台返回归属字段（系统/对话标题）',
              all(('conversation_title' in i) for i in items[:1]))
    finally:
        # 还原被改动的素材，并清掉本次产生的记录
        client.put('/api/settings/profile', headers=HD, json={'avatar': orig_avatar or ''})
        client.put('/api/settings', headers=HD, json={'background_image': orig_bg or ''})
        if conv:
            client.put(f'/api/conversations/{conv.id}', headers=HD,
                       json={'background_image': orig_conv_bg or ''})
        ML.query.filter(ML.value.like(f'%{mark}%')).delete(synchronize_session=False)
        ML.query.filter(ML.value.like(f'%profile-{os.getpid()}%')).delete(synchronize_session=False)
        ML.query.filter(ML.value.like(f'%test_{os.getpid()}%')).delete(synchronize_session=False)
        if 'newest_id' in dir() and newest_id:
            ML.query.filter(ML.id == newest_id).delete(synchronize_session=False)
        db.session.commit()
        print('  已还原头像/背景并清理测试记录')

    print('== 8. 清理校验 ==')
    check('测试记录已清空', ML.query.filter(ML.value.like(f'%{mark}%')).count() == 0)
    print(f'  记录数(后)={ML.query.count()}')

print()
print('结果：' + ('全部通过 ✅' if ok else '存在失败项 ❌'))
sys.exit(0 if ok else 1)
