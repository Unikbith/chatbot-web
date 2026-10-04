"""界面标记（富消息）配置与判定 —— 单一事实来源。

被三处共用，避免各家自己读环境变量导致语义漂移：
  - routes/chat.py   把标记约定拼进系统提示词
  - models.py        新会话的默认开关值
  - app.py           启动时回填历史会话 + 健康检查自报

为什么不放在 services/ 下：services/__init__.py 会 import AIService 等重依赖，
models.py 若经由包导入会引入循环风险；本模块保持零依赖（只用 os），
放顶层最安全。

开关语义（务必与前端 ConversationSettings.vue 的显示保持一致）：
  - 每个会话的 rich_marker_enabled 是**权威值**，由「会话设置 → 界面标记」控制；
  - 该值为 NULL（历史数据）时回落到环境变量 RICH_MESSAGE_ENABLED；
  - 启动时会做一次性回填，把 NULL 写成当时的全局值，
    因此 UI 显示的开关状态与实际注入行为始终一致，不会「显示关但实际在注入」。
"""
import json
import os

import reply_spec

# 全局默认开关：新会话的初始值，也是历史 NULL 数据的回落值。
RICH_MESSAGE_ENABLED = os.getenv('RICH_MESSAGE_ENABLED', 'false').lower() == 'true'

# 兼容保留：旧代码曾用这个常量做「未选模板」时的兜底说明。
# 现在注入内容统一由 reply_spec 组合（含完整结构与篇幅要求），此常量不再参与注入。
RICH_MESSAGE_PROMPT = ''


def resolve_rich_marker_enabled(conv=None):
    """解析某个会话是否启用界面标记。conv=None 时返回全局默认值。"""
    if conv is None:
        return RICH_MESSAGE_ENABLED
    flag = getattr(conv, 'rich_marker_enabled', None)
    return RICH_MESSAGE_ENABLED if flag is None else bool(flag)


def template_prompt(conv=None):
    """取出会话模板里的**选择项**（预设 / 结构档 / 篇幅 / 增强开关）。

    注意：不再使用会话里存的 prompt 正文 —— 规范文本统一由 reply_spec 给出。
    原因：新建对话还没有存过模板，若依赖会话里的正文就会退回旧提示词，
    表现为"开了提示词增强也没内容"。改为后端统一组合后，
    新建对话与历史对话的注入内容完全一致。
    """
    raw = getattr(conv, 'reply_template', None) if conv is not None else None
    if not raw:
        return {}
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def rich_marker_rule(conv=None):
    """返回要追加到系统提示词的标记规范；未启用时返回空串（行为与未接入前一致）。

    优先级：会话的「界面标记」总开关 > 会话模板的选择项 > 默认选择项。
    无论会话有没有存过模板，注入内容都由 reply_spec 统一组合。
    """
    if not resolve_rich_marker_enabled(conv):
        return ''
    opts = template_prompt(conv)
    # enhance 未设置时默认开启（与前端开关默认值一致）
    enhance = opts.get('enhance', True) is not False
    protocol = opts.get('protocol') or reply_spec.DEFAULT_PROTOCOL
    length = opts.get('length') or reply_spec.DEFAULT_LENGTH
    return reply_spec.compose_reply_spec(protocol=protocol, length=length, enhance=enhance)
