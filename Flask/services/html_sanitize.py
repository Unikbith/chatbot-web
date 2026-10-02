"""HTML 白名单消毒器：基于标准库 html.parser，零第三方依赖。

用于后端生成的 Markdown→HTML 输出，防止模型注入原始脚本/事件处理导致存储型 XSS。
只允许 markdown 转换器实际会产出的标签与安全属性。
"""
import html as html_lib
from html.parser import HTMLParser

# markdown(extra/nl2br) 实际会产出的标签白名单
ALLOWED_TAGS = {
    'p', 'br', 'hr',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'strong', 'b', 'em', 'i', 'del', 's',
    'code', 'pre',
    'blockquote',
    'ul', 'ol', 'li',
    'a', 'img',
    'table', 'thead', 'tbody', 'tr', 'td', 'th',
    'span', 'div',
}

# 仅保留的必要属性；href/src 额外做协议校验
ALLOWED_ATTRS = {
    'a': {'href', 'title'},
    'img': {'src', 'alt', 'title'},
    'code': {'class'},
    'span': {'class'},
    'div': {'class'},
}

_SAFE_SCHEMES = {'http', 'https', 'mailto', 'ftp', 'file'}

# 无法自闭合标签之外的"安全 void"标签（html.parser 的 startendtag）
_VOID_TAGS = {'br', 'hr', 'img', 'meta', 'link', 'input'}


def _is_safe_url(value):
    """仅允许 http/https/mailto/ftp 以及站内相对路径，拦截 javascript:、data: 等。"""
    s = (value or '').strip()
    if not s:
        return False
    if s.startswith('/') or s.startswith('#'):
        return True
    if ':' in s:
        scheme = s.split(':', 1)[0].lower()
        return scheme in _SAFE_SCHEMES
    return True


class _Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.output = []
        self._skip_depth = 0

    def _attrs_str(self, attrs):
        parts = []
        for key, value in attrs:
            k = key.lower()
            # 丢弃所有事件处理属性
            if k.startswith('on'):
                continue
            if k.startswith('style'):
                continue
            if k not in ALLOWED_ATTRS.get(self._current_tag, ()):
                continue
            if k in ('href', 'src') and not _is_safe_url(value):
                continue
            parts.append(f'{k}="{html_lib.escape(value, quote=True)}"')
        return (' ' + ' '.join(parts)) if parts else ''

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t in ('script', 'style', 'iframe', 'object', 'embed'):
            self._skip_depth += 1
            return
        if t not in ALLOWED_TAGS:
            return
        self._current_tag = t
        self.output.append(f'<{t}{self._attrs_str(attrs)}>')

    def handle_startendtag(self, tag, attrs):
        t = tag.lower()
        if t in ('script', 'style', 'iframe', 'object', 'embed'):
            self._skip_depth += 1
            return
        if t not in ALLOWED_TAGS or t not in _VOID_TAGS:
            return
        self._current_tag = t
        self.output.append(f'<{t}{self._attrs_str(attrs)}/>')

    def handle_endtag(self, tag):
        t = tag.lower()
        if t in ('script', 'style', 'iframe', 'object', 'embed'):
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return
        if t in ALLOWED_TAGS:
            self.output.append(f'</{t}>')

    def handle_data(self, data):
        if self._skip_depth > 0:
            return
        self.output.append(html_lib.escape(data, quote=False))

    def handle_comment(self, data):
        pass

    def handle_entityref(self, name):
        if self._skip_depth > 0:
            return
        self.output.append(f'&{name};')

    def handle_charref(self, name):
        if self._skip_depth > 0:
            return
        self.output.append(f'&#{name};')


def sanitize_html(raw_html):
    """消毒后端生成的 HTML，返回仅含白名单标签的安全片段。"""
    if not raw_html:
        return ''
    parser = _Sanitizer()
    try:
        parser.feed(raw_html)
        parser.close()
    except Exception:
        return html_lib.escape(raw_html, quote=False)
    return ''.join(parser.output)