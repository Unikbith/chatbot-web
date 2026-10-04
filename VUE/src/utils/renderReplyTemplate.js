/**
 * 渲染模板引擎
 *
 * 把 AI 输出的标记文本翻译成「标记 → DOM 骨架」的序列。
 *
 * 解析规则（与通用富标记保持一致，避免两套行为漂移）：
 *   1. 标记必须位于**行首**（允许前导空白），整行内容都属于该标记；
 *   2. 标记名必须是当前模板声明过的名字，否则整行按普通文本输出；
 *   3. 解析失败/字段为空的标记一律回退为普通文本 —— 宁可少渲染，绝不吞正文。
 */
import { templateMarkers, genericNodeToBlock } from './replyTemplates.js'
import { GENERIC_MARKERS, parseRichMessage } from './richMessage.js'
import { normalizeModelText } from './normalizeText.js'

/**
 * 把「写在句中」的标记拆到行首。
 *
 * 实测问题：模型常把多个标记连在一行输出
 *（`……受用】<br><br>【内心】你要是敢说……【推演】A.…`），
 * 甚至整轮回复一个换行都没有；而标记解析依赖行边界，
 * 于是除第一个之外的标记全部漏成原文。
 *
 * 拆分条件：标记前面是这些"边界字符"之一才拆，
 * 避免在句子中间误拆、把正文切断：
 *   · 句末标点（。！？…；）
 *   · 成对符号的收尾（」』”"）)]】）
 *   · 空白（空格/制表符）
 */
const BOUNDARY_CHARS = '。！？…；!?;」』”"’\'）)]】》>'
function splitInlineMarkers(text, names) {
  if (!text || !names.length) return text
  const escaped = names
    .map(n => String(n).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
    .join('|')
  const boundary = BOUNDARY_CHARS.replace(/[\\\]^-]/g, '\\$&')
  // 边界字符（可带空白）后紧跟已知标记 -> 插一个换行
  const re = new RegExp(`([${boundary}]|\\s)\\s*(?=【(?:${escaped})】)`, 'g')
  return text.replace(re, '$1\n')
}

/**
 * @param {string} raw     AI 输出的原始文本
 * @param {object} preset  模板预设（含 blocks）
 * @param {object} [ctx]   渲染上下文：长期记忆等由应用数据补入的内容
 * @returns {{ parts: Array<{type:'text'|'html'|'generic', text?:string, html?:string, node?:object}>, options: string[], hasBlock: boolean }}
 */
export function renderReplyTemplate(raw, preset, ctx = {}) {
  const tplNames = templateMarkers(preset)
  // 规范化：模型写的 <br> 还原成真实换行。
  // 这一步对标记解析是**必需**的 —— 否则整段是一行，行首标记识别不到，
  // 标记原文会直接漏到气泡里（实测出现过）。
  const allNames = [...tplNames, ...GENERIC_MARKERS]
  const text = splitInlineMarkers(normalizeModelText(raw), allNames)
  let parts = []
  const options = []
  let hasBlock = false
  // 是否已经渲染过记忆回廊；以及「推荐行动」在第几个 part（补记忆块时要插在它前面）
  let memoryRendered = false
  let firstOptionsIdx = -1

  if (!text || !tplNames.length) {
    return { parts: text ? [{ type: 'text', text }] : [], options, hasBlock: false }
  }
  // 词表 = 模板自带 + 内置通用：模板没定义的通用标记走兜底渲染，
  // 绝不能把【进度】这类标记原文原样丢给用户（那是明显的"坏了"观感）。
  const tplSet = new Set(tplNames)
  const nameSet = new Set(allNames)
  // 场景类区块（时间 / 地点 / 顶部信息条）：无论模型把它写在回复的哪个位置，
  // 渲染时一律提到最前面 —— 「在哪儿 / 什么时间」应该先于正文交代。
  // 实测模型经常先写一句动作、再补【场景】，观感就是"地点时间跑到中间去了"。
  const SCENE_BLOCK_NAMES = new Set(['场景', '状态条'])

  // 行首标记：`【名字】…`
  const LINE_RE = /^\s*【([^】]{1,20})】([\s\S]*)$/

  let buffer = []
  const flushText = () => {
    if (!buffer.length) return
    const joined = buffer.join('\n')
    if (joined.trim() !== '') parts.push({ type: 'text', text: joined })
    buffer = []
  }

  for (const line of text.split('\n')) {
    const m = line.match(LINE_RE)
    const name = m ? m[1].trim() : ''
    if (!m || !nameSet.has(name)) {
      buffer.push(line)
      continue
    }
    // 字段：按 | 切分；文本类标记若只有一个字段则整体作为正文
    const fields = m[2]
      .split(/[|｜]/)
      .map(s => s.trim())
      .filter(Boolean)
    if (!fields.length) {
      buffer.push(line)   // 空标记：按原文输出
      continue
    }

    // 模板未定义该标记 -> 优先翻译成模板自己的区块，
    // 让通用标记也用模板样式渲染（避免出现两套观感）
    if (!tplSet.has(name)) {
      const parsed = parseRichMessage(line)
      const node = parsed.find(p => p.kind === 'rich')?.node
      if (!node) {
        buffer.push(line)
        continue
      }
      const mapped = genericNodeToBlock(node)
      const targetBlock = mapped ? preset.blocks[mapped.block] : null
      if (mapped && targetBlock) {
        let out = null
        try {
          out = targetBlock(mapped.fields, ctx)
        } catch (e) {
          out = null
        }
        if (out && out.html) {
          flushText()
          parts.push({ type: 'html', html: out.html, scene: SCENE_BLOCK_NAMES.has(mapped.block) })
          if (out.options && out.options.length) options.push(...out.options)
          hasBlock = true
          continue
        }
      }
      // 模板确实没有对应区块时，才退回通用组件渲染
      flushText()
      parts.push({ type: 'generic', node })
      hasBlock = true
      continue
    }

    const block = preset.blocks[name]
    let rendered
    try {
      rendered = block ? block(fields, ctx) : null
    } catch (e) {
      rendered = null        // 渲染器异常不影响正文
    }
    if (!rendered || !rendered.html) {
      buffer.push(line)
      continue
    }
    flushText()
    parts.push({ type: 'html', html: rendered.html, scene: SCENE_BLOCK_NAMES.has(name) })
    if (name === '记忆') memoryRendered = true
    if (rendered.options && rendered.options.length) {
      // 选项文本按出现顺序收集，点击时按索引取回（避免把文案塞进 DOM 属性）
      if (firstOptionsIdx < 0) firstOptionsIdx = parts.length - 1
      options.push(...rendered.options)
    }
    hasBlock = true
  }
  flushText()

  // 记忆宫殿兜底：长期记忆来自系统数据（对话摘要），不依赖模型写没写【记忆】。
  // 模型漏写时这里补一块，否则界面上会完全看不到记忆回廊。
  const longTerm = (ctx && ctx.longTerm) || []
  if (!memoryRendered && longTerm.length && tplSet.has('记忆') && preset.blocks['记忆']) {
    let out = null
    try {
      out = preset.blocks['记忆']([], ctx)
    } catch (e) {
      out = null
    }
    if (out && out.html) {
      // 插在「推荐行动」之前：记忆是回顾，选项是下一步，顺序更符合阅读习惯
      const at = firstOptionsIdx >= 0 ? firstOptionsIdx : parts.length
      parts.splice(at, 0, { type: 'html', html: out.html, synthesized: true })
      hasBlock = true
    }
  }

  // 场景区块置顶：稳定分区（保持各自内部相对顺序），把场景类挪到最前面。
  // 记忆兜底块不受影响（它不是 scene），仍在原位。
  if (hasBlock && parts.some(p => p.scene)) {
    const sceneParts = parts.filter(p => p.scene)
    const rest = parts.filter(p => !p.scene)
    parts = [...sceneParts, ...rest]
  }

  return { parts, options, hasBlock }
}

export default renderReplyTemplate
