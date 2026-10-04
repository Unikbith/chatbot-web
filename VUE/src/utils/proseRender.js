/**
 * 正文渲染与「按内容类型区分样式」
 *
 * AI 的回复通常混着几类内容，全都用同一种字体样式会显得很平：
 *   · 对白（说的话）——「你来了。」/ “你来了。”
 *   · 心理或动作（常写在括号里）——（心跳快了半拍）
 *   · 其余为叙述描写
 * 这里在渲染后给它们分别打上 class，让模板 CSS 能分别设计：
 *   .rtpl-say      对白
 *   .rtpl-bracket  括号内容（心理/动作，具体语义由模板决定怎么表现）
 *   .rtpl-narr     段落级：叙述描写
 *
 * 实现要点：
 *   1. 先用 markdown-it 渲染成真正的 HTML（段落、加粗、引用等），
 *      此前正文只过消毒、没有渲染，导致段落被压成一行；
 *   2. 消毒后再用 DOMParser 只对**文本节点**做包裹，
 *      不碰标签、不碰代码块，因此不会破坏结构也无法注入。
 */
import MarkdownIt from 'markdown-it'
import { sanitizeHtml } from './sanitize.js'
import { normalizeModelText } from './normalizeText.js'

const md = new MarkdownIt({
  html: false,      // 模型输出的原始 HTML 一律当纯文本，安全第一
  linkify: true,
  breaks: true,     // 单个换行即换行，贴合聊天式排版
})

// 成对引号：覆盖中英文常见写法
const SAY_PAIRS = [
  ['「', '」'],
  ['『', '』'],
  ['“', '”'],
  ['"', '"'],
  ['‘', '’'],
]

// 括号：心理活动 / 动作描写
const BRACKET_PAIRS = [
  ['（', '）'],
  ['(', ')'],
]

/** 把文本节点按引号/括号切分并包裹，返回文档片段 */
function decorateTextNode(doc, node) {
  const text = node.nodeValue || ''
  if (!text.trim()) return

  // 收集所有可包裹区间：{ start, end, cls }
  const ranges = []
  for (const [open, close] of SAY_PAIRS) {
    const re = new RegExp(`${open}([^${open}${close}]{1,300})${close}`, 'g')
    let m
    while ((m = re.exec(text))) ranges.push({ start: m.index, end: m.index + m[0].length, cls: 'rtpl-say' })
  }
  for (const [open, close] of BRACKET_PAIRS) {
    const re = new RegExp(`\\${open}([^${open}${close}]{1,300})\\${close}`, 'g')
    let m
    while ((m = re.exec(text))) ranges.push({ start: m.index, end: m.index + m[0].length, cls: 'rtpl-bracket' })
  }
  if (!ranges.length) return

  // 按起点排序，去掉互相重叠的区间（保留先出现的）
  ranges.sort((a, b) => a.start - b.start)
  const picked = []
  let lastEnd = -1
  for (const r of ranges) {
    if (r.start < lastEnd) continue
    picked.push(r)
    lastEnd = r.end
  }

  const frag = doc.createDocumentFragment()
  let cursor = 0
  for (const r of picked) {
    if (r.start > cursor) frag.appendChild(doc.createTextNode(text.slice(cursor, r.start)))
    const span = doc.createElement('span')
    span.className = r.cls
    span.textContent = text.slice(r.start, r.end)
    frag.appendChild(span)
    cursor = r.end
  }
  if (cursor < text.length) frag.appendChild(doc.createTextNode(text.slice(cursor)))

  node.parentNode.replaceChild(frag, node)
}

/**
 * 给已消毒的 HTML 打内容类型标记。
 * 只在浏览器环境可用（依赖 DOMParser）；不可用时原样返回，不影响渲染。
 */
export function decorateProse(html) {
  if (!html || typeof DOMParser === 'undefined') return html
  try {
    const doc = new DOMParser().parseFromString(`<div id="rtpl-root">${html}</div>`, 'text/html')
    const root = doc.getElementById('rtpl-root')
    if (!root) return html

    // 段落级：叙述描写（对白 span 会继承，但可在 CSS 里单独覆盖）
    root.querySelectorAll('p').forEach((p) => {
      p.classList.add('rtpl-narr')
      // 以对白开头的段落单独标记：模板可据此取消首行缩进
      const first = (p.textContent || '').trimStart().charAt(0)
      if (SAY_PAIRS.some(([open]) => open === first)) p.classList.add('rtpl-say-line')
    })

    // 文本节点级：对白与括号
    const walker = doc.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        // 代码块/行内代码内的内容不动
        let el = node.parentNode
        while (el && el !== root) {
          const tag = el.nodeName
          if (tag === 'CODE' || tag === 'PRE') return NodeFilter.FILTER_REJECT
          el = el.parentNode
        }
        return NodeFilter.FILTER_ACCEPT
      },
    })
    const targets = []
    while (walker.nextNode()) targets.push(walker.currentNode)
    targets.forEach(node => decorateTextNode(doc, node))

    return root.innerHTML
  } catch (e) {
    return html
  }
}

/**
 * 把一段 Markdown 原文渲染成 HTML，并打好内容类型标记。
 * 流程：Markdown → 消毒 → 装饰（装饰只包裹文本，故放在消毒之后仍安全）。
 */
export function renderProse(text) {
  // 规范化：把模型写的 <br> 还原成真实换行，避免它以文字形式显示
  const raw = normalizeModelText(text)
  if (!raw.trim()) return ''
  let html
  try {
    html = md.render(raw)
  } catch (e) {
    html = `<p>${raw.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</p>`
  }
  return decorateProse(sanitizeHtml(html))
}

export default renderProse
