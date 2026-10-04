// utils/sanitize.js - 前端 HTML 消毒（DOMPurify 二次防线）
//
// 后端已对 AI 回复做白名单消毒，前端再经 DOMPurify 过滤一次，
// 即使上游过滤被绕过，也不会执行恶意脚本（防御存储型 XSS）。
import DOMPurify from 'dompurify';

// 允许的标签与后端白名单保持一致：仅保留安全的排版类标签
const ALLOWED_TAGS = [
  'p', 'br', 'hr', 'strong', 'b', 'em', 'i', 'u', 's', 'del', 'ins',
  'blockquote', 'code', 'pre', 'span', 'div',
  'ul', 'ol', 'li',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'table', 'thead', 'tbody', 'tr', 'th', 'td',
  'a', 'img',
];

const ALLOWED_ATTR = [
  'href', 'title', 'target', 'rel',
  'src', 'alt', 'width', 'height', 'class',
];

// 用于校验 URL 是否安全：仅允许 http/https/mailto 与站内相对路径
function safeUri(value) {
  if (!value) return false;
  const v = String(value).trim();
  if (/^(https?:|mailto:|\/|\.\/|\.\.\/|#)/i.test(v)) {
    // 排除 //evil.com 形式的协议相对地址被误判
    if (v.startsWith('//')) return false;
    return true;
  }
  return false;
}

let hooksRegistered = false;

function registerHooks() {
  if (hooksRegistered) return;
  hooksRegistered = true;
  // 强制外链 a 标签使用安全属性，禁止 javascript: 等危险协议
  DOMPurify.addHook('afterSanitizeAttributes', (node) => {
    if (node.tagName === 'A') {
      const href = node.getAttribute('href');
      if (href && !safeUri(href)) {
        node.removeAttribute('href');
      } else if (href) {
        node.setAttribute('target', '_blank');
        node.setAttribute('rel', 'noopener noreferrer nofollow');
      }
    }
    if (node.tagName === 'IMG') {
      const src = node.getAttribute('src');
      // 允许站内相对路径、http(s) 与 data:image（头像/上传图/生成图）
      const isData = /^data:image\/(png|jpe?g|gif|webp|bmp);base64,/i.test(src || '');
      if (src && !safeUri(src) && !isData) {
        node.removeAttribute('src');
      }
    }
  });
}

/**
 * 消毒 HTML 字符串，返回可安全用于 v-html 的内容。
 * @param {string} html 原始 HTML
 * @returns {string} 消毒后的 HTML
 */
export function sanitizeHtml(html) {
  if (!html || typeof html !== 'string') return '';
  registerHooks();
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
    ALLOW_DATA_ATTR: false,
    FORBID_TAGS: ['script', 'style', 'iframe', 'object', 'embed', 'form', 'input', 'link'],
    FORBID_ATTR: ['onerror', 'onload', 'onclick', 'style'],
  });
}

// ---------------------------------------------------------------------------
// 富渲染模板专用通道
//
// 卡片模板需要 class 与少量内联样式（进度条宽度、间距）才能做出好看版式，
// 上面那条普通通道把 class 之外的属性几乎全禁了。这里开一条独立的、受控的通道：
//   · 仍然禁止 <script> / <iframe> / <form> / <input> 与所有 on* 事件；
//   · 内联 style 只放行一份安全属性白名单，且拒绝 url()/expression/position 等；
//   · 允许 class/id 与 data-opt-idx（引擎自己生成，用于选项点击回传）。
// 模板骨架由 renderReplyTemplate 生成（文本均已转义），这条通道只做二次兜底，
// 因此即使模板来自 AI/作者，也无法借此执行脚本或读取外部资源。
// ---------------------------------------------------------------------------

const RICH_ALLOWED_TAGS = [
  ...ALLOWED_TAGS,
  'section', 'header', 'footer', 'button', 'ol', 'ul', 'li',
  'small', 'mark', 'figure', 'figcaption', 'sub', 'sup', 'abbr', 'b', 'i',
  // 可折叠区块：原生 details/summary，用于「推荐行动」「记忆」等长块的展开收起
  'details', 'summary',
];

const RICH_ALLOWED_ATTR = [
  'class', 'id', 'title', 'style', 'colspan', 'rowspan',
  // details 默认展开需要 open 属性（用于「推荐行动」「记忆」折叠块）
  'open',
  'href', 'src', 'alt', 'width', 'height', 'target', 'rel',
  'data-opt-idx',
];

// 允许的内联样式属性（模板只做排版配色，不需要定位/行为类属性）
const SAFE_STYLE_PROPS = new Set([
  'color', 'background', 'background-color', 'background-image', 'background-size',
  'background-position', 'background-repeat', 'background-clip', 'background-origin',
  'border', 'border-color', 'border-width', 'border-style', 'border-radius',
  'border-top', 'border-right', 'border-bottom', 'border-left',
  'border-top-color', 'border-bottom-color', 'border-left-color', 'border-right-color',
  'border-top-width', 'border-bottom-width', 'border-left-width', 'border-right-width',
  'border-top-style', 'border-bottom-style', 'border-left-style', 'border-right-style',
  'border-top-left-radius', 'border-top-right-radius',
  'border-bottom-left-radius', 'border-bottom-right-radius',
  'padding', 'padding-top', 'padding-right', 'padding-bottom', 'padding-left',
  'margin', 'margin-top', 'margin-right', 'margin-bottom', 'margin-left',
  'font', 'font-size', 'font-weight', 'font-style', 'font-family', 'font-variant',
  'line-height', 'letter-spacing', 'word-spacing', 'text-align', 'text-indent',
  'text-decoration', 'text-transform', 'text-shadow', 'text-overflow', 'white-space',
  'word-break', 'overflow-wrap',
  'display', 'flex', 'flex-direction', 'flex-wrap', 'flex-grow', 'flex-shrink',
  'flex-basis', 'align-items', 'align-self', 'align-content', 'justify-content',
  'justify-items', 'justify-self', 'gap', 'row-gap', 'column-gap',
  'grid', 'grid-template-columns', 'grid-template-rows', 'grid-column', 'grid-row',
  'order', 'width', 'min-width', 'max-width', 'height', 'min-height', 'max-height',
  'opacity', 'overflow', 'overflow-x', 'overflow-y',
  'box-shadow', 'box-sizing', 'vertical-align', 'object-fit', 'list-style',
  'list-style-type', 'list-style-position', 'caption-side', 'border-collapse',
]);

// 值里出现这些一律丢弃：外链、脚本、表达式、或可能闭合声明块的字符
const UNSAFE_STYLE_VALUE = /url\s*\(|expression\s*\(|javascript:|@import|behavior\s*:|\\|[\u0000-\u001f]|[{}]/i;

function filterStyleValue(styleText) {
  const kept = [];
  for (const decl of String(styleText).split(';')) {
    const idx = decl.indexOf(':');
    if (idx === -1) continue;
    const prop = decl.slice(0, idx).trim().toLowerCase();
    const value = decl.slice(idx + 1).trim();
    if (!prop || !value) continue;
    if (!SAFE_STYLE_PROPS.has(prop)) continue;
    if (UNSAFE_STYLE_VALUE.test(value)) continue;
    // background-image 只允许渐变，避免外链图片绕过 safeUri
    if (prop === 'background-image' && !/^\s*(linear|radial|conic)-gradient\s*\(/i.test(value)) continue;
    kept.push(`${prop}: ${value}`);
  }
  return kept.join('; ');
}

let richHooksRegistered = false;

function registerRichHooks() {
  if (richHooksRegistered) return;
  richHooksRegistered = true;
  DOMPurify.addHook('afterSanitizeAttributes', (node) => {
    // 内联样式逐条过滤，只留白名单属性
    const style = node.getAttribute && node.getAttribute('style');
    if (style) {
      const safe = filterStyleValue(style);
      if (safe) node.setAttribute('style', safe);
      else node.removeAttribute('style');
    }
    if (node.tagName === 'A') {
      const href = node.getAttribute('href');
      if (href && !safeUri(href)) node.removeAttribute('href');
      else if (href) {
        node.setAttribute('target', '_blank');
        node.setAttribute('rel', 'noopener noreferrer nofollow');
      }
    }
    if (node.tagName === 'IMG') {
      const src = node.getAttribute('src');
      const isData = /^data:image\/(png|jpe?g|gif|webp|bmp);base64,/i.test(src || '');
      if (src && !safeUri(src) && !isData) node.removeAttribute('src');
    }
    // 选项按钮：只允许纯数字索引，防止被塞入其它语义
    const optIdx = node.getAttribute && node.getAttribute('data-opt-idx');
    if (optIdx !== null && optIdx !== undefined && !/^\d+$/.test(String(optIdx))) {
      node.removeAttribute('data-opt-idx');
    }
  });
}

/**
 * 消毒「模板渲染」产生的 HTML。
 * 与 sanitizeHtml 的区别：允许 class/id 与受控的内联样式，
 * 以便卡片模板能画出真实版式；脚本与事件依旧被完全禁止。
 */
export function sanitizeRichHtml(html) {
  if (!html || typeof html !== 'string') return '';
  registerRichHooks();
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: RICH_ALLOWED_TAGS,
    ALLOWED_ATTR: RICH_ALLOWED_ATTR,
    ALLOW_DATA_ATTR: false,
    FORBID_TAGS: ['script', 'style', 'iframe', 'object', 'embed', 'form', 'input', 'textarea', 'select', 'link', 'meta', 'base'],
    // 事件属性一律禁止（on* 也由 DOMPurify 默认拦截，这里显式列出常见的）
    FORBID_ATTR: ['onerror', 'onload', 'onclick', 'onmouseover', 'onfocus', 'onblur', 'srcdoc', 'formaction'],
  });
}

export default sanitizeHtml;
