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
            print("[警告] nl2br 扩展不可用，降级为 extra")
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


def render_markdown(text):
    """将一段 Markdown 渲染为经过白名单过滤的 HTML（流结束后一次性渲染）"""
    if not text:
        return ''
    try:
        md = markdown.Markdown(extensions=['extra', 'nl2br'])
    except Exception:
        md = markdown.Markdown(extensions=['extra'])
    return sanitize_html(md.convert(text))


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


import json
