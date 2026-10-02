# -*- coding: utf-8 -*-
"""模型自绘样式（AI 自助 CSS）提取与安全化。

参考风月AI 的体验：模型可以根据自己输出的内容，附带一段 CSS 来美化排版
（如卡片、配色、间距）。本模块负责把这段 CSS 变成**受控**的样式通道：

安全边界（重要）
- 只接受「属性白名单」内的样式属性，其余一律丢弃（如 position/behavior/
  transform 之类可用于覆盖层攻击的属性）。
- 属性值中出现 url()、expression()、javascript:、@import 等一律拒绝该条声明。
- 选择器只接受单一 class 选择器（.foo），且类名统一加前缀由前端加作用域，
  避免模型用 `body{}`、`* {}` 之类选择器污染整页。
- 选择器内的元素/后代选择器会被丢弃（只保留 .class 与 .class.class 形式）。
- 最终产物是一段「作用域受限」的 CSS 文本，随 SSE 下发给前端注入，
  **不会**经过 v-html，因此不引入存储型 XSS。
"""
import re

# 允许的 CSS 属性（纯视觉属性，不含可执行/可覆盖层的能力）
ALLOWED_PROPS = {
    # 盒模型
    'margin', 'margin-top', 'margin-right', 'margin-bottom', 'margin-left',
    'padding', 'padding-top', 'padding-right', 'padding-bottom', 'padding-left',
    'width', 'height', 'max-width', 'min-width', 'max-height', 'min-height',
    'box-sizing', 'display',
    # 排版
    'font-size', 'font-weight', 'font-style', 'font-family', 'line-height',
    'letter-spacing', 'word-break', 'word-wrap', 'overflow-wrap', 'white-space',
    'text-align', 'text-decoration', 'text-indent', 'text-transform',
    'text-overflow', 'vertical-align',
    # 颜色与背景
    'color', 'background', 'background-color', 'background-image',
    'background-size', 'background-position', 'background-repeat',
    'opacity',
    # 边框
    'border', 'border-top', 'border-right', 'border-bottom', 'border-left',
    'border-color', 'border-style', 'border-width', 'border-radius',
    'border-collapse', 'border-spacing',
    # 表格
    'table-layout',
    # 弹性与网格布局
    'flex', 'flex-direction', 'flex-wrap', 'flex-grow', 'flex-shrink',
    'flex-basis', 'justify-content', 'align-items', 'align-self',
    'align-content', 'order', 'gap', 'row-gap', 'column-gap',
    'grid', 'grid-template-columns', 'grid-template-rows',
    'grid-column', 'grid-row', 'grid-gap', 'grid-auto-flow',
    # 溢出与可见性
    'overflow', 'overflow-x', 'overflow-y', 'overflow-wrap',
    'list-style', 'list-style-type', 'list-style-position',
    # 动效（仅过渡，不含 keyframes/animation 以免资源与性能问题）
    'transition', 'box-shadow', 'filter', 'aspect-ratio', 'object-fit',
}

# 属性值里出现即拒绝整条声明
_FORBIDDEN_VALUE_RE = re.compile(
    r'(expression\s*\(|javascript\s*:|vbscript\s*:|@import|behavior\s*:|-moz-binding|'
    r'url\s*\()',
    re.IGNORECASE,
)

# CSS 注释
_COMMENT_RE = re.compile(r'/\*.*?\*/', re.DOTALL)

# 一条规则：选择器 + 声明块
_RULE_RE = re.compile(r'([^{}]+)\{([^{}]*)\}', re.DOTALL)

# 合法选择器：仅 .class 或 .class.class（可带 :hover/:first-child 等伪类后缀）
_CLASS_SELECTOR_RE = re.compile(
    r'^\.[A-Za-z_][\w-]*(\.[A-Za-z_][\w-]*)*'
    r'(:hover|:active|:focus|:first-child|:last-child|:nth-child\(\s*\d+\s*\))*$'
)

# 前端注入时统一使用的作用域类名
SCOPE_CLASS = 'ai-style-scope'


def _clean_selector(raw):
    """清洗选择器：只保留单一 class 选择器（可带伪类），其余返回 None。"""
    sel = (raw or '').strip()
    # 去掉注释残留与换行
    sel = re.sub(r'\s+', ' ', sel)
    if not sel or len(sel) > 120:
        return None
    # 不允许逗号分组（一次只处理一个选择器，避免歧义）
    if ',' in sel or '{' in sel or '}' in sel:
        return None
    # 禁止全局/元素/ID/属性选择器
    if sel.startswith(('*', '#', '[', ':root', 'html', 'body')):
        return None
    if not _CLASS_SELECTOR_RE.match(sel):
        return None
    return sel


def _clean_declarations(block):
    """过滤声明块：仅保留白名单属性且值不含危险内容。"""
    kept = []
    for decl in (block or '').split(';'):
        decl = decl.strip()
        if not decl or ':' not in decl:
            continue
        prop, _, value = decl.partition(':')
        prop = prop.strip().lower()
        value = value.strip()
        if prop not in ALLOWED_PROPS:
            continue
        if not value or len(value) > 200:
            continue
        if _FORBIDDEN_VALUE_RE.search(value):
            continue
        # 禁止 position 类的覆盖层能力（虽然已在白名单外，这里做二次保险）
        if prop in ('position', 'z-index'):
            continue
        kept.append(f'{prop}: {value}')
        if len(kept) >= 60:  # 单条规则上限，防止模型输出超大样式
            break
    return '; '.join(kept)


def extract_ai_css(markdown_text):
    """从模型输出中提取 CSS。

    支持两种写法：
    1) ```css ... ``` 代码块
    2) 正文里的 <style>...</style> 片段（会被当成代码展示，这里抽出来）

    返回 (清理后的 markdown_text, css_text)
    """
    if not markdown_text:
        return markdown_text, ''

    collected = []

    # 1) 提取 ```css 代码块
    def _take_css_block(m):
        collected.append(m.group(1))
        # 原样保留为普通代码块，交给常规渲染（读者能看到模型写的样式）
        return m.group(0)

    text = re.sub(r'```css\s*\n(.*?)```', _take_css_block, markdown_text,
                  flags=re.DOTALL | re.IGNORECASE)
    # 也兼容 ```html 里内嵌的 <style>（部分模型这么输出）
    text = re.sub(r'<style[^>]*>(.*?)</style>',
                  lambda m: (collected.append(m.group(1)), '')[1],
                  text, flags=re.DOTALL | re.IGNORECASE)

    if not collected:
        return text, ''

    raw_css = '\n'.join(collected)
    raw_css = _COMMENT_RE.sub('', raw_css)
    # 只取最外层规则，嵌套的 @media 直接丢弃（保持实现简单可控）
    rules = []
    for sel_raw, decl in _RULE_RE.findall(raw_css):
        sel = _clean_selector(sel_raw)
        if not sel:
            continue
        decls = _clean_declarations(decl)
        if not decls:
            continue
        rules.append(f'{sel} {{ {decls} }}')
        if len(rules) >= 40:  # 规则数上限
            break

    css_text = '\n'.join(rules)
    # 总体积上限（防止超大 CSS 撑爆消息体）
    if len(css_text) > 8000:
        css_text = css_text[:8000]
    return text, css_text
