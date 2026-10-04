/**
 * 富消息标记解析器
 *
 * 设计目标：让 AI 用「轻量文本标记」表达状态栏、进度条、选项卡等结构化内容，
 * 前端解析成原生 Vue 组件渲染。相比让模型直接吐 HTML，这样做的好处：
 *
 * 1. 安全 —— 标记本身是纯文本，不经过 v-html，模型无法借此注入脚本；
 *    后端白名单消毒（html_sanitize.py）与前端 DOMPurify 两道防线都无需放宽。
 * 2. 可控 —— 每个标记对应一个固定组件与固定样式，模型只能填数据，
 *    不能决定长什么样，因此不会出现「模型写飞了把界面搞乱」。
 * 3. 好看 —— 组件用项目自身的 CSS 变量（--brand / --surface / --text-primary），
 *    自动适配明暗主题，不像第三方方案需要手写两套色值。
 *
 * 标记语法（刻意做得像自然文本，方便模型稳定输出、也方便容错）：
 *
 *   【状态】血量:70|金币:3|体力:45
 *   【进度】好感度|72
 *   【选项】A. 跟她打招呼|B. 转身离开|C. 保持沉默
 *   【提醒】今晚要去后山
 *   【面板】标题|第一行|第二行
 *   【物品】金创药:3|火折子:1
 *
 * 解析规则：
 * - 每个标记独占一行（行首可有空白，行尾可有空白），行内 `|` 分隔条目，`:` 分隔名值。
 * - 一行里允许出现多个标记，按出现顺序解析；标记之间的普通文字原样保留。
 * - 未闭合或格式不对的标记，一律按普通文本输出（宁可不渲染，也不能吃掉正文）。
 */

import { normalizeModelText } from './normalizeText.js'

// 标记名 -> 解析器。键名需与 TAIL 中的正则保持一致。
const MARKER_NAMES = ['状态', '进度', '选项', '提醒', '面板', '物品']

/**
 * 内置通用标记词表（对外暴露）。
 * 作用：选了渲染模板后，模型仍可能输出通用标记（例如【进度】），
 * 渲染层必须认识它们并兜底渲染，否则标记原文会直接显示给用户。
 */
export const GENERIC_MARKERS = [...MARKER_NAMES]
/**
 * 标记的通用约束：**一律独占一行**。
 *
 * 之所以不允许多余文字与标记同行：标记内容是「从 `】` 到下一个 `【`/行尾」，
 * 若允许行内混排，`开头【进度】好感度|30结尾` 会把「结尾」并进数值里、
 * `开头【提醒】别忘了带伞结尾` 会把「结尾」并进提醒内容里 —— 正文被静默吞掉，
 * 这是比「少渲染一个组件」严重得多的错误。
 *
 * 独占一行时，行的边界就是内容的边界，规则简单且不会吃掉正文。
 * 需要正文与状态并存时，让模型分多行输出即可（模型很容易做到）。
 */

// 标记名探测：刻意**不带 `g` 标志**。
// 带 g 的正则在 .test() 时会保留 lastIndex，连续调用会交替返回 true/false
// （第 1 个标记命中、第 2 个漏判），导致部分消息静默不走富渲染。
const MARKER_RE = new RegExp(`【(${MARKER_NAMES.join('|')})】`)

/**
 * 找出所有「成对且有名」的标记片段。
 * 只认 `【名字】内容` 形式；`【` 后面不是已知标记名的，整段当普通文本。
 *
 * @param {string} line 单行文本
 * @returns {Array<{type: string, body: string, start: number, end: number}>}
 */
function findMarkers(line) {
  const found = []
  // 逐字符扫描而不是直接 exec：需要保证「名 + 内容」成对，
  // 且遇到未知名标记时跳过该 `【` 继续往后找，避免整行丢弃。
  let i = 0
  while (i < line.length) {
    const open = line.indexOf('【', i)
    if (open === -1) break
    const close = line.indexOf('】', open + 1)
    if (close === -1) break
    const name = line.slice(open + 1, close)
    if (!MARKER_NAMES.includes(name)) {
      // 未知名标记：从 `【` 后一位继续找，保证后续合法标记仍能被识别
      i = open + 1
      continue
    }
    // 内容 = `】` 之后直到下一个 `【`（或行尾）
    const nextOpen = line.indexOf('【', close + 1)
    const end = nextOpen === -1 ? line.length : nextOpen
    found.push({
      type: name,
      body: line.slice(close + 1, end).trim(),
      start: open,
      end,
    })
    i = end
  }
  return found
}

/** 解析 `名:值|名:值` 形式的键值对，缺冒号时整体作为名称、值为空 */
function parsePairs(body) {
  return splitItems(body).map((item) => {
    const sep = item.search(/[:：]/)
    if (sep === -1) return { label: item.trim(), value: '' }
    return {
      label: item.slice(0, sep).trim(),
      value: item.slice(sep + 1).trim(),
    }
  }).filter(p => p.label)
}

/** 按 `|` 或 `｜` 切分条目，过滤空项 */
function splitItems(body) {
  return String(body || '')
    .split(/[|｜]/)
    .map(s => s.trim())
    .filter(Boolean)
}

/**
 * 进度值归一化：支持 `72`、`72%`、`0.72`。
 * 返回 0-100 的整数；无法解析时返回 null（调用方按普通文本处理）。
 */
function parsePercent(value) {
  if (value === '' || value == null) return null
  const raw = String(value).trim()
  // 带百分号直接取数；纯小数（含小数点）按 0-1 比例换算
  if (raw.endsWith('%')) {
    const n = parseFloat(raw)
    return Number.isFinite(n) ? clampPercent(Math.round(n)) : null
  }
  const n = parseFloat(raw)
  if (!Number.isFinite(n)) return null
  if (raw.includes('.') && n >= 0 && n <= 1) {
    return clampPercent(Math.round(n * 100))
  }
  return clampPercent(Math.round(n))
}

function clampPercent(n) {
  return Math.max(0, Math.min(100, n))
}

/**
 * 数值化：用于状态栏里识别「血量:70」这种可直接画条的项。
 * 返回数字或 null。
 */
function parseNumber(value) {
  if (value === '' || value == null) return null
  const raw = String(value).trim()
  const m = raw.match(/^-?\d+(\.\d+)?/)
  if (!m) return null
  const n = parseFloat(m[0])
  return Number.isFinite(n) ? n : null
}

/**
 * 把单个标记转成结构化节点。
 * 内容不足以渲染时返回 null，调用方回退为普通文本。
 */
function buildNode(type, body) {
  if (!body) return null
  switch (type) {
    case '状态': {
      const stats = parsePairs(body).map(p => {
        const num = parseNumber(p.value)
        // 数值项可画条：识别 `70/100` 形式取分子做百分比
        let percent = null
        if (num !== null) {
          const frac = String(p.value).match(/^\s*(-?\d+(?:\.\d+)?)\s*\/\s*(\d+(?:\.\d+)?)\s*$/)
          if (frac) {
            const total = parseFloat(frac[2])
            const cur = parseFloat(frac[1])
            if (total > 0) percent = clampPercent(Math.round((cur / total) * 100))
          } else if (num >= 0 && num <= 100) {
            percent = clampPercent(Math.round(num))
          }
        }
        return { label: p.label, value: p.value, percent }
      })
      return stats.length ? { type: '状态', stats } : null
    }

    case '进度': {
      // 支持两种写法：`标签|数值`（推荐）与 `标签:数值`
      const items = splitItems(body)
      if (!items.length) return null
      let label, rawValue
      const first = items[0]
      const sep = first.search(/[:：]/)
      if (sep !== -1) {
        label = first.slice(0, sep).trim()
        rawValue = first.slice(sep + 1).trim()
      } else {
        label = first
        // `好感度|72`：数值在第二项；只有一项时数值取标签自身（如 `【进度】72`）
        rawValue = items.length > 1 ? items[1] : first
        if (items.length === 1) label = ''
      }
      const percent = parsePercent(rawValue)
      if (percent === null) return null
      return { type: '进度', label, percent }
    }

    case '选项': {
      // 选项支持 `A. 文本` / `A、文本` / `1. 文本` / 纯文本
      const options = splitItems(body).map((item) => {
        const m = item.match(/^\s*([A-Za-z]|\d+)\s*[.、:：)）]\s*(.+)$/)
        if (m) return { key: m[1].toUpperCase(), text: m[2].trim() }
        return { key: '', text: item }
      }).filter(o => o.text)
      return options.length ? { type: '选项', options } : null
    }

    case '提醒':
      return { type: '提醒', text: body }

    case '面板': {
      const items = splitItems(body)
      if (!items.length) return null
      const title = items.length > 1 ? items[0] : ''
      const lines = items.length > 1 ? items.slice(1) : items
      return { type: '面板', title, lines }
    }

    case '物品': {
      const items = parsePairs(body).map(p => ({ label: p.label, count: p.value }))
      return items.length ? { type: '物品', items } : null
    }

    default:
      return null
  }
}

/**
 * 解析整段文本，返回「文本段 / 富节点」的线性序列。
 *
 * 返回值元素形态：
 *   { kind: 'text', text: string }
 *   { kind: 'rich', node: {...} }
 *
 * @param {string} input 消息纯文本（未经过 Markdown/HTML 处理）
 * @returns {Array<object>}
 */
export function parseRichMessage(input) {
  // 先规范化：模型写的 <br> 还原成真实换行，否则整段会变成一行、
  // 行首标记识别不到（标记原文就会漏到气泡里）
  const text = normalizeModelText(input)
  if (!text) return []

  const out = []
  const lines = text.split('\n')
  let buffer = []

  const flushText = () => {
    if (!buffer.length) return
    const joined = buffer.join('\n')
    if (joined.trim() !== '' || joined.includes('\n')) {
      out.push({ kind: 'text', text: joined })
    }
    buffer = []
  }

  for (const line of lines) {
    const markers = findMarkers(line)
    if (!markers.length) {
      buffer.push(line)
      continue
    }

    // 标记必须独占一行：`【名】内容`，其前后不允许再有其它文字。
    // 不满足就整行按普通文本输出（宁可少渲染，也不吞正文）。
    const trimmed = line.trim()
    const solo = markers.length === 1
      && trimmed.startsWith('【')
      && markers[0].start === line.indexOf('【')
      && line.slice(markers[0].end).trim() === ''

    if (!solo) {
      buffer.push(line)
      continue
    }

    const node = buildNode(markers[0].type, markers[0].body)
    if (node) {
      flushText()
      out.push({ kind: 'rich', node })
    } else {
      // 解析失败（数值非法等）：原样保留，绝不吞掉用户可见内容
      buffer.push(line)
    }
  }
  flushText()

  return out.filter((seg) => seg.kind !== 'text' || seg.text.trim() !== '')
}

/**
 * 文本中是否含可渲染的富标记：用于决定是否走富渲染分支。
 *
 * @param {string} input 待检测文本
 * @param {string[]} [names] 自定义标记词表（渲染模板自带的标记名）。
 *        不传则用内置的通用词表 —— 模板的标记名（如【场景】【记忆】）
 *        不在通用词表里，必须显式传入，否则整条消息会被判定为"无标记"而不渲染。
 */
export function hasRichMarkers(input, names) {
  const text = String(input || '')
  if (!text) return false
  if (!names || !names.length) return MARKER_RE.test(text)
  const escaped = names
    .map(n => String(n).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
    .join('|')
  // 刻意不带 g 标志：带 g 的正则 .test() 会保留 lastIndex，连续调用会交替返回真假
  return new RegExp(`【(?:${escaped})】`).test(text)
}

export default parseRichMessage
