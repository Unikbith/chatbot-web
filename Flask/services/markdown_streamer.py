"""流式 Markdown 转 HTML 转换器"""
import markdown
import re
import html as html_lib
from services.html_sanitize import sanitize_html


class MarkdownStreamer:
    """流式 Markdown 转 HTML：按完整段落输出，保证 HTML 标签闭合。"""

    def __init__(self):
        self._buf = ""
        self._in_code = False
        try:
            self._md = markdown.Markdown(extensions=['extra', 'nl2br'])
        except Exception:
            # nl2br 扩展不可用时降级（不引入 print，生产环境不产生控制台噪声）
            self._md = markdown.Markdown(extensions=['extra'])

    def feed(self, text):
        """喂入新文本，返回可立即输出的 HTML 片段列表"""
        self._buf += text
        outputs = []
        while True:
            html = self._extract()
            if html is None:
                break
            outputs.append(html)
        return outputs

    def _extract(self):
        """从缓冲区尝试提取一个完整段落并转换为 HTML"""
        if not self._buf:
            return None

        # 代码块中：等待闭合的 ```
        if self._in_code:
            first = self._buf.find('```')
            end = self._buf.find('```', first + 3) if first != -1 else -1
            if end == -1:
                return None
            nl = self._buf.find('\n', end)
            if nl == -1:
                return None
            segment = self._buf[:nl + 1]
            self._buf = self._buf[nl + 1:]
            self._in_code = False
            return self._convert(segment)

        # 普通模式：检查是否以 ``` 开头
        stripped = self._buf.lstrip()
        if stripped.startswith('```'):
            if '\n' not in self._buf:
                return None
            self._in_code = True
            return None

        # 普通模式：找空行（段落结束标志）
        para_end = self._buf.find('\n\n')
        if para_end != -1:
            segment = self._buf[:para_end + 2]
            self._buf = self._buf[para_end + 2:]
            return self._convert(segment)

        return None

    def _convert(self, text):
        self._md.reset()
        return sanitize_html(self._md.convert(text))

    def flush(self):
        """流结束，输出缓冲区中剩余的所有内容"""
        if self._buf.strip():
            html = self._convert(self._buf)
            self._buf = ""
            return html
        return ""


def _highlight(text):
    """把 ==高亮== 转成 <mark>。

    这是很多模型习惯用的强调写法（部分也用 **加粗**，两者互不冲突）。
    只处理成对出现的标记，且转义在前、先转义后替换，避免破坏 HTML 转义结果。
    """
    # 先切分避免跨标签误替换：仅对纯文本片段做处理
    parts = re.split(r'(<[^>]+>)', text)
    for i, part in enumerate(parts):
        if part.startswith('<'):
            continue
        # 避免把 == 内部的 <br> 等标签拆开：此处 parts 已按标签切分，天然安全
        parts[i] = re.sub(r'==(.+?)==', r'<mark>\1</mark>', part, flags=re.DOTALL)
    return ''.join(parts)


def render_markdown(text):
    """将一段 Markdown 渲染为经过白名单过滤的 HTML（流结束后一次性渲染）"""
    if not text:
        return ''
    try:
        md = markdown.Markdown(extensions=['extra', 'nl2br'])
    except Exception:
        md = markdown.Markdown(extensions=['extra'])
    return sanitize_html(_highlight(md.convert(text)))


def render_stream_delta(text):
    """把流式增量转成与成稿渲染一致的 HTML 片段。

    成稿走 markdown 的 nl2br（单换行 → <br>），所以流式阶段采用同样规则：
    先把整个片段转义，再把换行还原成 <br>。因为文本已完全转义，片段内
    不会出现任何未闭合标签，前端可安全地边收边 v-html 拼接。

    效果：生成中与生成完看到的都是同一套 HTML 排版，段落/换行节奏一致，
    不会出现「回复结束后空行被抹掉、内容猛地一缩」的跳变。
    """
    if not text:
        return ''
    escaped = html_lib.escape(text, quote=False).replace('\n', '<br>')
    return sanitize_html(_highlight(escaped))


def strip_html_to_text(html_text):
    """将 HTML 还原为纯文本，供模型续写/后续对话使用"""
    if not html_text:
        return ''
    text = html_text
    # 换行类标签先转成换行
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</(p|div|li|h[1-6]|blockquote|pre|tr)>', '\n', text, flags=re.IGNORECASE)
    # 去掉剩余所有标签
    text = re.sub(r'<[^>]+>', '', text)
    # 还原 HTML 实体
    text = html_lib.unescape(text)
    return text.strip()


def estimate_word_count(text):
    """估算文本字数：中文字符 + 英文单词数 + 连续数字组数。"""
    if not text:
        return 0
    text = strip_html_to_text(text)
    chinese = len(re.findall(r'[\u4e00-\u9fff]', text))
    english_words = len(re.findall(r'[a-zA-Z]+', text))
    numbers = len(re.findall(r'\d+', text))
    return chinese + english_words + numbers


def sse_content(html_text):
    """构造正文内容的 SSE 消息（HTML 格式）"""
    return f"data: {json.dumps({'choices': [{'delta': {'content': html_text}}]}, ensure_ascii=False)}\n\n"


def sse_reasoning(text):
    """构造思考过程的 SSE 消息（纯文本）"""
    return f"data: {json.dumps({'choices': [{'delta': {'reasoning_content': text}}]}, ensure_ascii=False)}\n\n"


def sse_done():
    return "data: [DONE]\n\n"


def sse_html(html_text):
    """构造最终渲染结果的 SSE 消息（HTML，前端据此替换流式原文）"""
    return f"data: {json.dumps({'choices': [{'delta': {'html': html_text}}]}, ensure_ascii=False)}\n\n"


def sse_tokens(total_tokens):
    """构造 token 用量的 SSE 消息（前端据此在消息下方显示消耗）"""
    return f"data: {json.dumps({'choices': [{'delta': {'tokens': total_tokens}}]}, ensure_ascii=False)}\n\n"


import json
