/**
 * 回复渲染模板（Reply Template）
 *
 * 设计要点：把「长什么样」与「写什么内容」彻底分开。
 *
 *   模板（属于会话/卡片，可换）= CSS 皮肤 + 标记词表 + 给 AI 的标记说明
 *   内容（AI 每轮输出）        = 一行一个标记，例如 【状态】好感度:99/100
 *
 * 引擎负责把标记翻译成**固定骨架的 DOM**（class 名稳定，见下方 t-* 约定），
 * 模板只提供 CSS。这样做的好处：
 *   1. AI 永远不需要写 HTML —— 它只填数据，版式不可能被写飞；
 *   2. 换风格 = 换一段 CSS，不涉及任何组件改动，所以"每张卡一套风格"成本极低；
 *   3. 不引入模板语言，没有表达式求值，天然不可注入。
 *
 * 可用的 DOM 骨架（模板 CSS 按这些 class 写即可）：
 *   .rtpl                       根容器（模板作用域）
 *   .t-scene / .t-scene-row     场景条（时间、地点）
 *   .t-ico                      行首图标
 *   .t-sum                      剧情摘要行
 *   .t-panel / .t-panel-h / .t-panel-b   卡片与标题栏
 *   .t-row / .t-k / .t-v        键值行、标签胶囊、值
 *   .t-stat / .t-num / .t-note  数值行、数值、注释
 *   .t-bar / .t-bar-fill        进度条
 *   .t-mem / .t-mem-h / .t-mem-list   记忆档案块
 *   .t-opts / .t-opt / .t-opt-k / .t-opt-t / .t-opt-d   推演选项
 *   .t-items / .t-item          物品标签
 *   .t-alert                    提醒
 */

/*
 * 注意：本文件里的提示词文本（ARCHIVE_PROMPT / PROTOCOL_* / LENGTH_PROMPTS）
 * **不再用于注入** —— 注入内容由后端 Flask/reply_spec.py 统一组合并作为唯一事实来源。
 * 原因：文本若随会话保存，新建对话（还没存过模板）就会退回旧提示词，
 * 表现为"开了提示词增强却没有内容"。
 * 这里保留这些文本仅用于前端文案与测试参照，修改注入内容请改后端 reply_spec.py。
 */

/** 转义：模板骨架由引擎生成，所有来自 AI 的文本都必须转义 */
function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/** 按 | 切分条目 */
function splitItems(body) {
  return String(body || '')
    .split(/[|｜]/)
    .map(s => s.trim())
    .filter(Boolean)
}

/** 解析 `键:值`，无冒号时键为空（视为整段文本） */
function splitKV(item) {
  const sep = item.search(/[:：]/)
  if (sep === -1) return { k: '', v: item }
  return { k: item.slice(0, sep).trim(), v: item.slice(sep + 1).trim() }
}

/** 拆出条目尾部的注释（【…】或((…))） */
function splitNote(value) {
  const m = String(value || '').match(/^(.*?)\s*(?:【([^】]*)】|\(\(([^)]*)\)\))\s*$/)
  if (!m) return { v: String(value || '').trim(), note: '' }
  return { v: (m[1] || '').trim(), note: (m[2] || m[3] || '').trim() }
}

/** 拆出条目尾部的强度徽标（`[微涨]` / `［骤升］`），返回 { v, badge } */
function splitBadge(value) {
  const m = String(value || '').match(/^(.*?)\s*[\[［]([^\]］]{1,12})[\]］]\s*$/)
  if (!m) return { v: String(value || '').trim(), badge: '' }
  return { v: (m[1] || '').trim(), badge: (m[2] || '').trim() }
}

/** 解析 `0/100` 形式：返回 { cur, max, percent } */
function parseRatio(v) {
  const m = String(v || '').trim().match(/^(-?\d+(?:\.\d+)?)\s*\/\s*(\d+(?:\.\d+)?)$/)
  if (!m) return null
  const cur = parseFloat(m[1])
  const max = parseFloat(m[2])
  if (!Number.isFinite(cur) || !Number.isFinite(max) || max <= 0) return null
  return { cur: m[1], max: m[2], percent: Math.max(0, Math.min(100, Math.round(cur / max * 100))) }
}

/**
 * 解析变化量写法：`100→100`、`78→40`、`0 -> 5`。
 * 常见于状态卡（前后对比），带方向便于样式区分涨/跌。
 */
function parseDelta(v) {
  const m = String(v || '').trim().match(/^(-?\d+(?:\.\d+)?)\s*(?:→|->|⇒|➔|>)\s*(-?\d+(?:\.\d+)?)(\s*\/\s*\d+(?:\.\d+)?)?$/)
  if (!m) return null
  const from = parseFloat(m[1])
  const to = parseFloat(m[2])
  if (!Number.isFinite(from) || !Number.isFinite(to)) return null
  return {
    from: m[1],
    to: m[2],
    max: m[3] ? m[3].trim() : '',
    dir: to > from ? 'up' : (to < from ? 'down' : 'flat'),
  }
}

/**
 * 标签自动配色：按出现顺序轮换 c1..c6。
 * 目的是让「每项标签一个颜色」这种观感**自动出现**，
 * 不需要模型去指定颜色（模型指定颜色既不稳定也不安全）。
 */
function toneClass(i) {
  return `c${(i % 6) + 1}`
}

/** 图标：按标记语义给默认图标，模板可覆盖（这里用 emoji，零依赖） */
const ICONS = {
  场景: '🕐', 地点: '📍', 摘要: '🗒️', 面板: '📄', 状态: '💗',
  记忆: '🧠', 推演: '🎬', 物品: '🎒', 提醒: '⚠️',
  状态条: '📡', 模块: '🧩', 内心: '💭',
}

/**
 * 档案风预设 —— 贴近「场景条 + 标签胶囊 + 数值注释 + 记忆档案 + 推演卡片」的版式。
 */

const ARCHIVE_PROMPT = [
  '',
  '',
  '【界面标记（务必遵守）】',
  '为了让界面好看，请在需要时**单独占一行**输出下列标记（标记必须位于行首、一行只写一个标记、前后不要写别的文字，否则会被当普通文字显示）：',
  '· 场景（时间与地点，两个字段用 | 分隔）：`【场景】08:15 (Day 1, 清晨)|咖啡馆靠窗座位`',
  '· 状态条（顶部信息条：标题 | 时间 | 一句当前状态）：`【状态条】星火网咖2F-双人包间|02:55|屏幕还亮着，桌上放着两杯冷掉的咖啡`',
  '· 模块（终端式模块清单，可带徽标）：`【模块】USER.DAT|角色状态.EXE|观察线索 (3)|环境变量|推荐行动|记忆回廊 (L:2 S:11)`',
  '· 摘要（一句话概括本轮剧情）：`【摘要】两人第一次把话说开`',
  '· 面板（一个信息卡片，首项是标题，其余是「标签:内容」，不写冒号则整行作为正文）：`【面板】角色资料|姓名:陈默|性别:男|年龄:24|职业:插画师`',
  '· 状态（数值卡片，值可写「当前/上限」或「旧值→新值」，行尾可用【】附一句注释）：`【状态】角色状态|好感度:72/100【她开始主动找话题】|信任度:45→52【你替她解了围】`',
  '· 内心（突出显示的心理独白）：`【内心】我完了……他怎么什么都记得。`',
  '· 记忆（长期/短期记忆，首项是标题，其余是条目）：`【记忆】短期记忆 (3/7)|你替她挡了一次雨|她记住了你喜欢的口味`',
  '· 推演（给玩家的选项，可写「A.」编号，标题用【】包裹）：`【推演】A.【直接告白】把话说清楚|B.【维持现状】先不打破现在的距离`',
  '· 物品：`【物品】雨伞:1|车票:2`',
  '· 提醒：`【提醒】今晚约好一起看电影`',
  '要求：数值与你叙述的剧情一致，不要每轮重置；不需要的标记不要硬凑。',
].join('\n')

/**
 * 场景类字段归位：把「地点 / 时间 / 氛围」按**语义**放对位置。
 *
 * 为什么不能按位置硬取：
 *   模型在【场景】里被要求写「时间|地点」，在【状态条】里被要求写「地点|时间|氛围」，
 *   两个标记的字段顺序本来就是相反的；实测模型经常混着写（有时还两个标记都输出），
 *   于是同一个位置一会儿是时间、一会儿是地点 —— 界面上就表现为「地点显示错了」。
 *
 * 归位规则（先看名字，再看内容，最后才退回声明顺序）：
 *   1. 形如 `地点:客厅` / `时间:周六 14:20` 的具名字段直接按名字归位；
 *   2. 剩下没名字的字段按内容猜：像时间的给时间，像地点的给地点，其余算氛围说明；
 *   3. 都猜不出来时按 fieldOrder 声明的顺序填，保证至少有内容、不丢字。
 */
const TIME_HINT = /(\d{1,2}\s*[:：]\s*\d{2}|凌晨|清晨|早上|早晨|上午|中午|午后|下午|傍晚|黄昏|晚上|夜里|深夜|午夜|半夜|Day\s*\d|第[一二三四五六七八九十百\d]+天|周[一二三四五六日天]|星期[一二三四五六日天])/
const PLACE_HINT = /(楼|层|室|房|厅|馆|店|院|街|路|巷|城|村|岛|山|河|湖|海|港|公园|广场|学校|教室|走廊|楼道|客厅|卧室|厨房|浴室|洗手间|阳台|沙发|床上|床边|车里|车内|门口|窗外|天台|吧台|包厢|营地|车站|机场|咖啡|酒吧|餐厅|食堂|办公室|宿舍|医院|地下|地面|电梯|玄关|地毯)/

const SCENE_KEYS = {
  place: ['地点', '位置', '所在', '场景'],
  time: ['时间', '时刻'],
  note: ['氛围', '环境', '状态', '说明', '光线'],
}

function sceneKindOf(key) {
  for (const [kind, keys] of Object.entries(SCENE_KEYS)) {
    if (keys.includes(key)) return kind
  }
  return null
}

function classifySceneFields(fields, fieldOrder = ['place', 'time', 'note']) {
  const out = { place: '', time: '', note: '' }
  const bare = []
  for (const raw of fields || []) {
    const s = String(raw == null ? '' : raw).trim()
    if (!s) continue
    const m = s.match(/^([^:：]{1,6})[:：]\s*(.*)$/)
    const kind = m ? sceneKindOf(m[1].trim()) : null
    if (kind) {
      if (!out[kind]) out[kind] = m[2].trim()
      continue
    }
    bare.push(s)
  }

  // 无名值：按内容判类型；同类型已有值就退化成氛围说明，绝不覆盖已有的地点/时间
  const notes = []
  for (const s of bare) {
    const isTime = TIME_HINT.test(s)
    const isPlace = !isTime && PLACE_HINT.test(s)
    if (isTime && !out.time) { out.time = s; continue }
    if (isPlace && !out.place) { out.place = s; continue }
    notes.push(s)
  }

  // 兜底：一个都认不出来（生僻写法）时按声明顺序落位，保证内容不丢、位置固定
  if (!out.place && !out.time && notes.length) {
    const order = fieldOrder.filter(k => k === 'place' || k === 'time')
    order.forEach((kind, i) => { if (notes[i]) out[kind] = notes[i] })
    notes.splice(0, order.length)
  }

  if (notes.length) out.note = [out.note, ...notes].filter(Boolean).join(' ')
  return out
}

/**
 * 把一条记忆宫殿摘要整理成可读的多行 HTML。
 *
 * 摘要正文是分条写的长文（`- 人物身份与关系：…` / `- 关键事件时间线：\n 1. …`），
 * 直接丢进一个 <li> 会连成一大坨、上下文字段还会串味。这里：
 *   · 按行拆开，去掉 markdown 的 - * 与列表编号前缀；
 *   · 第一行当小标题，其余作为正文行；
 *   · 单行过长时截断（摘要本身在库里保留全文，界面只需要能扫读）。
 */
const MEMORY_LINE_MAX = 240
function formatMemoryEntry(text) {
  const lines = String(text || '')
    .split(/\r?\n/)
    .map(l => l.replace(/^\s*[-*•·]\s*/, '').replace(/^\s*\d+[.、)]\s*/, '').trim())
    .filter(Boolean)
  if (!lines.length) return ''
  const clip = (s) => (s.length > MEMORY_LINE_MAX ? `${s.slice(0, MEMORY_LINE_MAX)}…` : s)
  const [head, ...body] = lines
  return `<span class="t-mem-item-h">${esc(clip(head))}</span>`
    + (body.length
      ? `<span class="t-mem-item-b">${body.map(l => `<span class="t-mem-line">${esc(clip(l))}</span>`).join('')}</span>`
      : '')
}

/** 各标记的渲染器：输入 body，输出 { html, options } */
const ARCHIVE_BLOCKS = {
  场景(fields) {
    // 声明顺序：地点 | 时间 | 氛围（两个字段时也按语义自动归位）
    const { place, time, note } = classifySceneFields(fields, ['place', 'time', 'note'])
    const rows = []
    if (place) rows.push(`<div class="t-scene-row is-place"><span class="t-ico">${ICONS.地点}</span><span>${esc(place)}</span></div>`)
    if (time) rows.push(`<div class="t-scene-row"><span class="t-ico">${ICONS.场景}</span><span>${esc(time)}</span></div>`)
    if (note) rows.push(`<div class="t-scene-row is-note"><span>${esc(note)}</span></div>`)
    return { html: rows.length ? `<div class="t-scene">${rows.join('')}</div>` : '' }
  },

  摘要(fields) {
    const text = fields.join(' ')
    return { html: text ? `<div class="t-sum"><span class="t-ico">${ICONS.摘要}</span><span>${esc(text)}</span></div>` : '' }
  },

  面板(fields, ctx) {
    if (!fields.length) return { html: '' }
    const title = fields[0]
    const items = fields.slice(1)
    const rows = items.map((item, i) => {
      const { k, v } = splitKV(item)
      if (!k) return `<div class="t-row t-row-text"><span class="t-v">${esc(v)}</span></div>`
      return `<div class="t-row"><span class="t-k ${toneClass(i)}">${esc(k)}</span><span class="t-v">${esc(v)}</span></div>`
    }).join('')
    const body = `<div class="t-panel-b">${rows}</div>`
    // 信息面板一律默认折叠：玩家信息、角色信息、身体状态、精神心理都是"要时再看"的
    // 查阅型内容，默认展开会把正文淹没。想常开可在渲染上下文里传 expandPanels。
    const open = !!(ctx && ctx.expandPanels)
    return {
      html: `<details class="t-fold t-fold--panel"${open ? ' open' : ''}>`
        + `<summary class="t-fold-h"><span class="t-ico">${ICONS.面板}</span>`
        + `<span class="t-fold-t">${esc(title)}</span>`
        + `<span class="t-fold-count">${items.length}</span>`
        + `<span class="t-fold-arrow"></span></summary>`
        + body + `</details>`,
    }
  },

  状态(fields) {
    if (!fields.length) return { html: '' }
    // 首项无冒号时视为卡片标题（如「角色状态」）
    let title = ''
    let items = fields
    if (fields[0] && !/[:：]/.test(fields[0])) {
      title = fields[0]
      items = fields.slice(1)
    } else if (fields[0]) {
      // 容错：模型常把标题与第一项数值挤在一格（用空格而非 | 分隔），
      // 形如「林小雨 好感度:76→78」。此时把最后一处空格当作标题分界。
      const m = fields[0].match(/^(.*\S)\s+(\S+[:：].*)$/)
      if (m) {
        title = m[1]
        items = [m[2], ...fields.slice(1)]
      }
    }
    const rows = items.map((item, i) => {
      const { k, v } = splitKV(item)
      const { v: valueNoNote, note } = splitNote(v)
      const { v: rawValue, badge } = splitBadge(valueNoNote)
      const delta = parseDelta(rawValue)
      const ratio = delta ? null : parseRatio(rawValue)
      let numHtml
      if (delta) {
        // 变化量：旧值 → 新值，新值加粗并按涨跌着色
        numHtml = `<span class="t-num t-delta is-${delta.dir}">`
          + `<span class="t-delta-from">${esc(delta.from)}</span>`
          + `<span class="t-delta-arrow">→</span>`
          + `<span class="t-delta-to">${esc(delta.to)}</span>`
          + `${delta.max ? `<i>${esc(delta.max)}</i>` : ''}</span>`
      } else if (ratio) {
        numHtml = `<span class="t-num">${esc(ratio.cur)}<i>/${esc(ratio.max)}</i></span>`
      } else {
        numHtml = `<span class="t-num">${esc(rawValue)}</span>`
      }
      const bar = ratio ? `<span class="t-bar"><span class="t-bar-fill" style="width:${ratio.percent}%"></span></span>` : ''
      // 强度徽标：一眼看出这一项是本轮是涨是跌、幅度多大
      const badgeDir = delta ? delta.dir : 'flat'
      const badgeHtml = badge
        ? `<span class="t-badge is-${badgeDir}">${esc(badge)}</span>`
        : ''
      const noteHtml = note ? `<span class="t-note">${esc(note)}</span>` : ''
      // 顺序：标签 + 数值 + 迷你条 + 强度徽标 同行，注释换行 —— 与 _base.css 的排布一致
      return `<div class="t-stat"><span class="t-k ${toneClass(i)}">${esc(k || '数值')}</span>${numHtml}${bar}${badgeHtml}${noteHtml}</div>`
    }).join('')
    const head = title
      ? `<header class="t-panel-h"><span class="t-ico">${ICONS.状态}</span><span>${esc(title)}</span></header>`
      : ''
    return { html: `<section class="t-panel${title ? '' : ' t-stats-flat'}">${head}<div class="t-panel-b">${rows}</div></section>` }
  },

  /** 顶部状态条：地点 | 时间 | 一句氛围（与【场景】同一套语义归位，写反了也不会错位） */
  状态条(fields) {
    if (!fields.length) return { html: '' }
    const { place, time, note } = classifySceneFields(fields, ['place', 'time', 'note'])
    const parts = []
    if (place) parts.push(`<span class="t-topbar-place"><span class="t-ico">${ICONS.地点}</span>${esc(place)}</span>`)
    if (time) parts.push(`<span class="t-topbar-time">${esc(time)}</span>`)
    if (note) parts.push(`<span class="t-topbar-note">${esc(note)}</span>`)
    return { html: parts.length ? `<div class="t-topbar">${parts.join('<span class="t-topbar-sep">|</span>')}</div>` : '' }
  },

  /**
   * 终端式模块表：一行一个模块名，可带徽标，如
   * `【模块】USER.DAT|江小满.EXE|星记忆回廊 (L:1 S:23)`
   */
  模块(fields) {
    if (!fields.length) return { html: '' }
    const rows = fields.map((raw) => {
      const m = String(raw).match(/^(.+?)\s*[（(]([^）)]*)[）)]\s*$/)
      const name = m ? m[1].trim() : String(raw).trim()
      const badge = m ? m[2].trim() : ''
      const lead = name.match(/^([^\w\u4e00-\u9fa5]+)\s*(.*)$/)
      const icon = lead ? lead[1].trim() : ''
      const label = lead ? lead[2].trim() : name
      return `<div class="t-module">`
        + `<span class="t-module-caret">»</span>`
        + `<span class="t-module-name">${esc(label)}</span>`
        + `${icon ? `<span class="t-module-ico">${esc(icon)}</span>` : ''}`
        + `${badge ? `<span class="t-module-badge">${esc(badge)}</span>` : ''}`
        + `</div>`
    }).join('')
    return { html: `<div class="t-modules">${rows}</div>` }
  },

  /** 内心独白：突出显示的心理活动块 */
  内心(fields) {
    const text = fields.join(' ')
    return { html: text ? `<div class="t-inner"><span class="t-inner-text">${esc(text)}</span></div>` : '' }
  },

  /**
   * 记忆回廊：一个总区块，里面分「短期记忆」（AI 输出的条目）
   * 与「长期记忆」（= 应用自己的记忆宫殿摘要，由系统数据补上，AI 不需要写）。
   *
   * 关键点：**长期记忆来自系统数据，不依赖模型是否写了【记忆】**。
   * 之前只有模型写了【记忆】才渲染整块，模型一轮偷懒没写，界面上就完全看不到
   * 记忆宫殿（而摘要其实一直在库里）—— 现在 fields 为空也能渲染出长期记忆。
   */
  记忆(fields, ctx) {
    let title = '记忆回廊'
    let items = []
    // 首项是标题（模型按规范写「记忆回廊」），其余是短期记忆条目；没有标题时全部当条目
    if (fields.length) {
      const first = String(fields[0] || '').trim()
      if (/^记忆|回廊|宫殿|短期|长期/.test(first) && fields.length > 1) {
        title = /短期/.test(first) ? '记忆回廊' : first
        items = fields.slice(1)
      } else if (/^记忆|回廊|宫殿/.test(first)) {
        title = first || '记忆回廊'
        items = fields.slice(1)
      } else {
        items = fields.slice()
      }
    }
    const longTerm = (ctx && ctx.longTerm) || []
    if (!items.length && !longTerm.length) return { html: '' }

    const shortBlock = items.length
      ? `<div class="t-mem-sub">`
        + `<div class="t-mem-sub-h">短期记忆 <em>${items.length}</em></div>`
        + `<ol class="t-mem-list">${items.map(it => `<li>${esc(it)}</li>`).join('')}</ol>`
        + `</div>`
      : ''
    // 长期记忆 = 记忆宫殿摘要。摘要本身是分条写的长文，直接塞进 <li> 会变成一坨，
    // 这里拆成行渲染，并默认折叠（要看再展开），避免淹没正文。
    const longBlock = longTerm.length
      ? `<details class="t-mem-sub t-mem-sub--long">`
        + `<summary class="t-mem-sub-h">长期记忆（记忆宫殿） <em>${longTerm.length}</em></summary>`
        + `<ol class="t-mem-list t-mem-list--long">`
        + longTerm.map(it => `<li>${formatMemoryEntry(it)}</li>`).join('')
        + `</ol></details>`
      : ''

    return {
      html: `<details class="t-fold t-fold--mem" open>`
        + `<summary class="t-fold-h t-mem-h"><span class="t-ico">${ICONS.记忆}</span>`
        + `<span class="t-fold-t">${esc(title || '记忆回廊')}</span>`
        + `<span class="t-fold-arrow"></span></summary>`
        + `<div class="t-mem-body">${shortBlock}${longBlock}</div></details>`,
    }
  },

  推演(fields) {
    const options = []
    const rows = fields.map((item, idx) => {
      // `A.【标题】描述` / `A. 描述` / 纯描述
      let rest = item
      let key = ''
      const km = rest.match(/^\s*([A-Za-z]|\d+)\s*[.、:：)）]\s*(.*)$/)
      if (km) { key = km[1].toUpperCase(); rest = km[2].trim() }
      let title = ''
      const tm = rest.match(/^【([^】]*)】\s*(.*)$/)
      if (tm) { title = tm[1]; rest = tm[2].trim() }
      const plain = (title ? `【${title}】` : '') + rest
      options.push(plain)
      const titleHtml = title ? `<b class="t-opt-t">【${esc(title)}】</b>` : ''
      const keyHtml = key ? `<span class="t-opt-k">${esc(key)}.</span>` : ''
      return `<button type="button" class="t-opt" data-opt-idx="${idx}">${keyHtml}<span class="t-opt-body">${titleHtml}<span class="t-opt-d">${esc(rest)}</span></span></button>`
    }).join('')
    if (!options.length) return { html: '' }
    // 用原生 <details> 做成可折叠：默认展开，玩家可收起去看正文，不需要任何 JS
    return {
      html: `<details class="t-fold" open>`
        + `<summary class="t-fold-h"><span class="t-ico">${ICONS.推演}</span>`
        + `<span class="t-fold-t">推荐行动</span><span class="t-fold-arrow"></span></summary>`
        + `<div class="t-opts">${rows}</div></details>`,
      options,
    }
  },

  物品(fields) {
    const chips = fields.map((item) => {
      const { k, v } = splitKV(item)
      return `<span class="t-item">${esc(k || v)}${k && v ? `<b>×${esc(v)}</b>` : ''}</span>`
    }).join('')
    return { html: chips ? `<div class="t-items">${chips}</div>` : '' }
  },

  提醒(fields) {
    const text = fields.join(' ')
    return { html: text ? `<div class="t-alert"><span class="t-ico">${ICONS.提醒}</span><span>${esc(text)}</span></div>` : '' }
  },
}

/**
 * 渲染预设登记表。
 *
 * 新增一个预设只需两步（无需改动任何组件）：
 *   1. 在 assets/reply-templates/ 下加一个 CSS 文件，按 _base.css 的变量名
 *      覆盖一组值（根选择器写成 .rtpl.rtpl-<id>），并在 main.js 里静态引入；
 *   2. 在下面登记一条：id / 名称 / 说明 / 给 AI 的标记说明。
 * blocks 目前各预设共用同一套骨架（见 ARCHIVE_BLOCKS），
 * 因此换预设只换外观、不改标记词表 —— AI 侧行为保持一致。
 */
export const TEMPLATE_PRESETS = {
  archive: {
    id: 'archive',
    name: '档案风',
    nameEn: 'Archive',
    desc: '玫粉调 · 圆角卡片 · 柔和阴影 · 正文首行缩进',
    descEn: 'Rose palette, rounded cards, soft shadows, indented prose',
    css: '',   // 样式在 assets/reply-templates/archive.css（静态导入，保证加载）
    prompt: ARCHIVE_PROMPT,
    blocks: ARCHIVE_BLOCKS,
  },
  minimal: {
    id: 'minimal',
    name: '极简',
    nameEn: 'Minimal',
    desc: '无彩色 · 细线 · 无阴影 · 宽行距，适合正剧与长篇阅读',
    descEn: 'Monochrome, hairline borders, no shadows, roomy line height',
    css: '',
    prompt: ARCHIVE_PROMPT,
    blocks: ARCHIVE_BLOCKS,
  },
  neon: {
    id: 'neon',
    name: '霓虹',
    nameEn: 'Neon',
    desc: '深底 · 青紫辉光 · 硬直角，赛博科幻向',
    descEn: 'Dark base, cyan-violet glow, sharp corners — cyberpunk',
    css: '',
    prompt: ARCHIVE_PROMPT,
    blocks: ARCHIVE_BLOCKS,
    // 本身就是深色设计：明暗两种环境下观感一致，无需额外写暗色变量覆盖
    darkNative: true,
  },
  ink: {
    id: 'ink',
    name: '和纸',
    nameEn: 'Ink',
    desc: '米纸底 · 墨色衬线 · 印章式标签，古风与年代向',
    descEn: 'Paper tone, ink serif, seal-style tags — classical',
    css: '',
    prompt: ARCHIVE_PROMPT,
    blocks: ARCHIVE_BLOCKS,
  },
  terminal: {
    id: 'terminal',
    name: '终端',
    nameEn: 'Terminal',
    desc: '暗色终端 · 青色描边 · 多色标签胶囊 · 数值增减一目了然',
    descEn: 'Dark terminal, cyan outlines, multi-color stat pills, clear deltas',
    css: '',
    prompt: ARCHIVE_PROMPT,
    blocks: ARCHIVE_BLOCKS,
    darkNative: true,
  },
  // ── 氛围向：三套「叙事隐喻」预设 ──
  // 共同点：不只是换配色，而是给一轮回复一个可读的隐喻，
  // 版式（栏宽、居中、装饰边、纸张纹理）跟着隐喻一起变。
  script: {
    id: 'script',
    name: '银幕',
    nameEn: 'Screenplay',
    desc: '剧本页 · 打字机等宽 · 台词收窄居中，像在读这一场戏的分镜稿',
    descEn: 'Typewriter screenplay page — centered dialogue, slugged scene headings',
    css: '',
    prompt: ARCHIVE_PROMPT,
    blocks: ARCHIVE_BLOCKS,
  },
  letter: {
    id: 'letter',
    name: '信笺',
    nameEn: 'Letter',
    desc: '信纸横纹 · 楷体手书 · 航空信封边与邮戳，像收到角色写来的一封信',
    descEn: 'Ruled writing paper in kai script — airmail edge, postmark, fold creases',
    css: '',
    prompt: ARCHIVE_PROMPT,
    blocks: ARCHIVE_BLOCKS,
  },
  oracle: {
    id: 'oracle',
    name: '启示',
    nameEn: 'Oracle',
    desc: '深靛夜空 · 金发丝双框 · 四角括号与牌卡式选项，像摊开一张牌',
    descEn: 'Indigo night with gold hairlines — corner brackets, card-like choices',
    css: '',
    prompt: ARCHIVE_PROMPT,
    blocks: ARCHIVE_BLOCKS,
    // 本身就是深色设计：明暗两种环境下观感一致，无需额外写暗色变量覆盖
    darkNative: true,
  },

  // ── 暧昧向 · 五套新预设（男女受众各有侧重）──
  blush: {
    id: 'blush',
    name: '脸红',
    nameEn: 'Blush',
    desc: '奶油蜜桃底 · 腮红粉 · 圆润气泡卡片与心跳细线，甜而不腻的心动',
    descEn: 'Cream-peach with blush pink — bubbly cards and a heartbeat edge',
    css: '',
    prompt: ARCHIVE_PROMPT,
    blocks: ARCHIVE_BLOCKS,
  },
  moonlight: {
    id: 'moonlight',
    name: '月色',
    nameEn: 'Moonlight',
    desc: '银蓝夜色 · 淡紫月光 · 月牙与星点，静谧梦幻的月下私语',
    descEn: 'Silver-blue night with a crescent moon — hushed, dreamy confessions',
    css: '',
    prompt: ARCHIVE_PROMPT,
    blocks: ARCHIVE_BLOCKS,
  },
  smoke: {
    id: 'smoke',
    name: '余温',
    nameEn: 'Afterglow',
    desc: '炭蓝灰底 · 烟橙余火 · 细发丝边框，事后的片刻、不必说破的克制暧昧',
    descEn: 'Charcoal with an ember glow — the muted afterglow that needs no words',
    css: '',
    prompt: ARCHIVE_PROMPT,
    blocks: ARCHIVE_BLOCKS,
    darkNative: true,
  },
  whiskey: {
    id: 'whiskey',
    name: '微醺',
    nameEn: 'Tipsy',
    desc: '深棕木质 · 琥珀金 · 吊灯暖光与衬线字，深夜酒吧里上头的情调',
    descEn: 'Warm walnut and amber — a late-night bar, pleasantly over the line',
    css: '',
    prompt: ARCHIVE_PROMPT,
    blocks: ARCHIVE_BLOCKS,
    darkNative: true,
  },
  fate: {
    id: 'fate',
    name: '红线',
    nameEn: 'Red String',
    desc: '暖米纸底 · 玄朱与流金 · 双细线婚书框，一纸誓约与系在指上的红线',
    descEn: 'Ivory with vermilion and gold — a vow on paper, tied by a red string',
    css: '',
    prompt: ARCHIVE_PROMPT,
    blocks: ARCHIVE_BLOCKS,
  },
}

/** 供渲染预设面板按顺序展示 */
export const TEMPLATE_PRESET_LIST = Object.values(TEMPLATE_PRESETS)

/** 默认渲染预设：不指定时用它（而不是"不使用"），保证开箱就有版式 */
export const DEFAULT_TEMPLATE_ID = 'blush'

/**
 * 通用标记 → 模板区块的映射。
 *
 * 为什么需要它：模型有时会输出通用标记（如【进度】好感度|83），
 * 若直接交给 RichBlocks 兜底，会出现"两套样式"——通用组件自带的进度条
 * 撑满整行、配色与模板不搭，观感很违和。
 * 这里把通用标记**翻译成模板自己的字段**，让它用模板的样式渲染，
 * 整个输出框的风格因此始终统一。
 */
const GENERIC_TO_BLOCK = {
  状态: (node) => ({ block: '状态', fields: node.stats.map(s => `${s.label}:${s.value}`) }),
  // 进度只有「名称 + 百分比」，转成「当前/上限」让模板画出同款迷你条
  进度: (node) => ({ block: '状态', fields: [`${node.label || '进度'}:${node.percent}/100`] }),
  选项: (node) => ({ block: '推演', fields: node.options.map(o => (o.key ? `${o.key}. ${o.text}` : o.text)) }),
  提醒: (node) => ({ block: '提醒', fields: [node.text] }),
  面板: (node) => ({ block: '面板', fields: [node.title || '信息', ...node.lines] }),
  物品: (node) => ({ block: '物品', fields: node.items.map(i => (i.count ? `${i.label}:${i.count}` : i.label)) }),
}

/** 把通用节点翻译成模板可渲染的 { block, fields }；无法翻译时返回 null */
export function genericNodeToBlock(node) {
  const mapper = node && GENERIC_TO_BLOCK[node.type]
  if (!mapper) return null
  try {
    const out = mapper(node)
    if (!out || !out.fields || !out.fields.length) return null
    return out
  } catch (e) {
    return null
  }
}

// ---------------------------------------------------------------------------
// 输出详略（输出协议）
//
// 解决的核心问题：预设只决定「长什么样」，不决定「每轮输出多少内容」。
// 模型默认只会偶尔用几个标记，于是界面看起来很空。
// 这里把「每轮该输出哪些构件」写成三档协议，拼进系统提示词，
// 让「每轮都有完整信息」变成明确要求而不是碰运气。
// 与视觉风格正交：可以「终端风 + 详尽」，也可以「和纸 + 简明」。
// ---------------------------------------------------------------------------

const PROTOCOL_BRIEF = [
  '',
  '【界面标记（按需使用）】',
  '只在剧情确实需要时使用标记，标记必须独占一行、位于行首，不要为了凑格式而硬输出。',
  '可用：`【状态条】地点|时间|一句状态`、`【状态】角色名|数值:当前/上限`、`【内心】心里话`、`【推演】A.【选项】说明|B.【选项】说明`。',
].join('\n')

const PROTOCOL_STANDARD = [
  '',
  '【每轮输出结构（务必遵守）】',
  '每次回复都要有下面的构件，各自独占一行、写在正文之后：',
  '1. `【状态条】地点|时间|一句环境或当前状态`',
  '2. `【状态】角色名.EXE|数值:当前/上限【一句说明】|…` —— 至少 3 项，数值要与剧情一致并逐轮累积',
  '3. `【内心】角色此刻没说出口的心里话`（1-2 句）',
  '4. `【推演】A.【选项名】具体说明|B.【选项名】说明|C.【自由输入】按你的想法行动`（至少 2 项）',
  '不需要的构件可省略，但状态条与推演每轮都要有。',
].join('\n')

/**
 * 通用输出结构（详尽档，也是唯一使用的档）。
 *
 * 「通用」的含义：不绑定任何一张具体的卡 ——
 * 构件名、字段名都用通用叫法；数值项则以「这张卡的 AI 提示词里定义了什么」为准，
 * 卡里没定义时回落到一组通用数值。因此同一段提示词对所有卡都成立。
 */
const PROTOCOL_FULL = [
  '',
  '【每轮输出结构（通用规范 · 务必完整执行）】',
  '无论剧情长短，每次回复都要在正文之后按顺序给齐下面的构件；',
  '每个标记独占一行、位于行首，标记之间不要夹其它文字。',
  '',
  '一、正文',
  '对白用「」，心理或动作放（）里；对白与叙述分开成段，不要混在同一段里。',
  '',
  '二、信息构件',
  '1. `【状态条】地点|时间|一句环境或当前氛围`',
  '   例：`【状态条】二楼包厢|凌晨 02:14|屏幕的蓝光映在墙面上`',
  '',
  '2. `【面板】玩家信息|姓名:…|性别:…|年龄:…|外貌:…|穿着:…|当前姿态:…|携带物:…`',
  '   玩家（{{user}}）的当前信息，按剧情推进更新；没有变化时也要照常输出。',
  '',
  '3. `【状态】角色名|数值:旧值→新值[强度]【变化原因】|数值:当前/上限[强度]【一句说明】|…`',
  '   · 数值项以这张卡的 AI 提示词里定义的为准，**定义了哪些就全部输出，一项都不许省略**；',
  '     卡里没有定义数值项时，用这组通用项：好感度、信任度、情绪、身体状态',
  '   · 有变化的写成「旧值→新值」，没有变化的写成「值→值」',
  '   · 每一项都要用 `[强度]` 标出本轮的变化幅度或当前程度，例如 `[微涨]`、`[骤升]`、`[骤降]`、',
  '     `[持平]`、`[紧绷]`、`[临界]` —— 让人一眼看出这一项现在是什么状态、动得多快',
  '   · 数值必须承接上一轮，只能按剧情合理增减，绝不允许每轮重置',
  '   · 每一项的【】里再补一句具体说明，不要写"无变化"这类废话',
  '',
  '4. `【内心】角色此刻没说出口的心里话`（1-3 句，要具体、有情绪）',
  '',
  '5. `【推演】A.【选项名】具体做法|B.【选项名】具体做法|C.【选项名】具体做法|D.【自由输入】按你的想法行动`',
  '   · 至少 3 个具体选项，每个都要写清"做什么、可能怎样"，不要写"随便看看"',
  '',
  '6. 按需补充（需要时才写）：',
  '   `【记忆】短期记忆 (n/m)|条目|条目` —— 出现重要转折或每 3-5 轮更新一次',
  '   `【物品】名称:数量`、`【提醒】需要玩家留意的事`',
  '',
  '三、叙事要求（代入感）',
  '· 用第二人称「你」称呼玩家，紧扣玩家的设定：称呼、关系、身体特征都要对上。',
  '· 描写要有感官层次：动作、呼吸、体温、声音、气味，不要只写"她说了什么"。',
  '· 情绪要有起伏与克制感，留白比直白更动人；避免流水账式的动作罗列。',
  '· 角色要有自己的意志与迟疑，不要一味顺从；她的犹豫、口是心非、松口的过程本身就是戏。',
  '· 构件内容必须与正文剧情一致，不要为了凑格式编造与剧情无关的信息。',
].join('\n')

export const OUTPUT_PROTOCOLS = {
  brief: {
    id: 'brief',
    name: '按需',
    nameEn: 'On demand',
    desc: '只在需要时用标记，最省 token',
    descEn: 'Only when needed — fewest tokens',
    prompt: PROTOCOL_BRIEF,
  },
  standard: {
    id: 'standard',
    name: '标准',
    nameEn: 'Standard',
    desc: '每轮都有状态条 / 状态表 / 内心 / 推演',
    descEn: 'Status bar, stats, inner voice and choices every turn',
    prompt: PROTOCOL_STANDARD,
  },
  full: {
    id: 'full',
    name: '详尽',
    nameEn: 'Full',
    desc: '每轮输出全部信息：模块表 + 玩家资料 + 全部数值变化 + 内心 + 推演',
    descEn: 'Everything every turn: modules, profile, all stat deltas, inner voice, choices',
    prompt: PROTOCOL_FULL,
  },
}

export const OUTPUT_PROTOCOL_LIST = Object.values(OUTPUT_PROTOCOLS)
// 默认「详尽」：用户要的是每轮都能看到完整信息，默认就该是最全的那档
export const DEFAULT_PROTOCOL = 'full'

// ---------------------------------------------------------------------------
// 回复长度
//
// 有人喜欢长文细读，有人只想快速推进，所以做成一个明确选项。
// 它同时影响两件事：正文篇幅 + 构件里说明文字的详略。
// ---------------------------------------------------------------------------
export const OUTPUT_LENGTHS = {
  short: {
    id: 'short',
    name: '短文',
    nameEn: 'Short',
    desc: '正文 400-700 字，节奏偏快但仍写满状态信息',
    descEn: '400-700 chars — quicker pace, still fills all panels',
    prompt: '',
  },
  medium: {
    id: 'medium',
    name: '适中',
    nameEn: 'Medium',
    desc: '正文 700-1200 字，描写与推进兼顾',
    descEn: '700-1200 chars — balanced description and progression',
    prompt: '',
  },
  long: {
    id: 'long',
    name: '长文',
    nameEn: 'Long',
    desc: '正文 1200-2000 字，充分展开感官与心理细节',
    descEn: '1200-2000 chars — rich sensory and emotional detail',
    prompt: '',
  },
}

export const OUTPUT_LENGTH_LIST = Object.values(OUTPUT_LENGTHS)
// 默认「适中」：与后端 reply_spec.DEFAULT_LENGTH 及 chat.py 的默认回复模板保持一致。
// 前端新建会话时会把这个值写进 reply_template，两边不一致会导致"前端显示短文、
// 实际按适中生成"这类默认值漂移。
export const DEFAULT_LENGTH = 'medium'

/**
 * 取篇幅要求文本；未知 id 回落默认。
 *
 * ⚠️ 已**不用于注入提示词**：注入文本的唯一事实来源是后端 `Flask/reply_spec.py`
 * （否则新建对话拿不到这份文本，两边还会各写一份逐渐漂移）。
 * 这里的文本只作为前端侧的对照参考，改注入内容请改后端。
 */
export function lengthPrompt(id) {
  const l = OUTPUT_LENGTHS[id] || OUTPUT_LENGTHS[DEFAULT_LENGTH]
  return l ? l.prompt : ''
}

/** 取协议文本；未知 id 回落到默认（同样不再用于注入，见上） */
export function protocolPrompt(id) {
  const p = OUTPUT_PROTOCOLS[id] || OUTPUT_PROTOCOLS[DEFAULT_PROTOCOL]
  return p ? p.prompt : ''
}

/**
 * 组合注入文本（历史接口，保留仅为兼容旧调用）。
 *
 * 🚫 不要用它生成注入内容 —— 会与后端规范形成两份互相冲突的文本。
 * 需要改模型看到的结构规范，请改 `Flask/reply_spec.py`。
 */
export function composeTemplatePrompt(preset, protocolId, lengthId) {
  const vocab = preset?.prompt || ''
  return vocab + protocolPrompt(protocolId) + lengthPrompt(lengthId)
}

/** 取某个预设支持的标记名列表（用于解析与提示词对齐） */
export function templateMarkers(preset) {
  return Object.keys(preset?.blocks || {})
}

/** 新对话默认模板：脸红 + 长文 + 丰富面板内容开启两轮（后端第 2 轮后自动关闭）。 */
export function buildDefaultReplyTemplateJson(overrides = {}) {
  const preset = TEMPLATE_PRESETS[DEFAULT_TEMPLATE_ID] || TEMPLATE_PRESET_LIST[0] || {}
  return JSON.stringify({
    preset: preset.id || DEFAULT_TEMPLATE_ID,
    name: preset.name || '脸红',
    protocol: DEFAULT_PROTOCOL,
    length: DEFAULT_LENGTH,
    enhance: true,
    ...overrides,
  })
}

/**
 * 解析会话保存的模板字段，返回可用预设对象。
 *
 * 没有保存过模板时返回**默认预设**（而不是 null）：
 * 这样新对话开箱就有一套完整版式，不需要用户先去设置里挑一遍。
 */
export function resolveTemplate(raw) {
  const fallback = TEMPLATE_PRESETS[DEFAULT_TEMPLATE_ID] || null
  if (!raw) return fallback
  let data = raw
  if (typeof raw === 'string') {
    try { data = JSON.parse(raw) } catch { return fallback }
  }
  if (!data || typeof data !== 'object') return fallback
  const preset = data.preset ? TEMPLATE_PRESETS[data.preset] : null
  return preset || fallback
}

export default TEMPLATE_PRESETS
