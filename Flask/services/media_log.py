"""对话素材记录（ConversationMediaLog）统一写入口。

用户上传/设置的图片分散在多个入口，管理员后台「对话素材记录」需要一处汇总：
  · 对话级：对话设置里的背景图、AI 头像、用户头像（带 conversation_id）
  · 系统级：系统设置里的用户头像、AI 头像、背景图（不带 conversation_id）
  · 上传级：聊天时发送的图片等一切 /api/upload/image 上传（不带 conversation_id）

写入是「尽力而为」的：审计记录失败绝不能影响用户真正要做的事（发图、改设置），
因此调用方不需要 try/except，本模块内部已经吞掉异常并回滚到可用状态。
"""
from extensions import db
from models import ConversationMediaLog


def log_media(user_id, media_type, value, conversation_id=None, dedupe=True):
    """记录一条图片素材使用。

    :param user_id: 所属用户
    :param media_type: 见 models.ConversationMediaLog 的取值说明
    :param value: data-URI 或 URL；空值直接忽略（清除操作不产生记录）
    :param conversation_id: 对话级素材传对话 ID，系统级/上传级传 None
    :param dedupe: 同用户+同类型+同对话下，与上一条完全相同的值不再重复记录
    :return: 新建的记录对象，被跳过或失败时返回 None
    """
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None

    try:
        if dedupe:
            last = (
                ConversationMediaLog.query
                .filter_by(user_id=user_id, media_type=media_type, conversation_id=conversation_id)
                .order_by(ConversationMediaLog.id.desc())
                .first()
            )
            if last is not None and last.value == value:
                return None

        rec = ConversationMediaLog(
            user_id=user_id,
            conversation_id=conversation_id,
            media_type=media_type,
            value=value,
        )
        # SAVEPOINT：审计写入失败时只回滚这一条，
        # 不会连带丢掉调用方同一请求里已改好的设置/资料。
        with db.session.begin_nested():
            db.session.add(rec)
        return rec
    except Exception:
        # 审计是附带功能，绝不能连带用户的正常操作一起失败
        return None
