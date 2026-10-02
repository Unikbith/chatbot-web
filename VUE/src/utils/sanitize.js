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

export default sanitizeHtml;
