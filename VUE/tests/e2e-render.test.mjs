// 端到端渲染验证：折叠默认值 + 恶劣换行 + 记忆回廊
import { resolveTemplate } from '../src/utils/replyTemplates.js'
import { renderReplyTemplate } from '../src/utils/renderReplyTemplate.js'

let pass = 0, fail = 0
const check = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`  ok   ${name}`) }
  else { fail++; console.log(`  FAIL ${name} ${extra}`) }
}

const T = resolveTemplate(null)

console.log('\n[1] 最恶劣情况：整轮回复没有换行，标记用空格/标点相连')
{
  const raw = '她说你就这点本事啊。【面板】玩家信息|姓名:小林|性别:男 '
    + '【面板】身体状态|胸部:涨痛|私处:湿透 '
    + '【状态】林小雨|好感度:76→78[微涨]【她嘴上嫌弃】|欲望:40→62[骤升] '
    + '【内心】我完了。 【推演】A.【继续】压上去|B.【停手】看她反应'
  const out = renderReplyTemplate(raw, T, { longTerm: ['（较早对话摘要一）'] })
  const html = out.parts.filter(p => p.type === 'html').map(p => p.html).join('')
  const textLeft = out.parts.filter(p => p.type === 'text').map(p => p.text).join('')

  // 5 个构件来自标记；另有 1 个是系统补出的记忆回廊（模型没写【记忆】，
  // 但 ctx.longTerm 有摘要 —— 这正是"记忆宫殿必须显示"的兜底行为）
  check('识别出 5 个标记构件 + 1 个补出的记忆回廊',
    out.parts.filter(p => p.type === 'html').length === 6,
    JSON.stringify(out.parts.map(p => p.type)))
  check('补出的记忆块带 synthesized 标记',
    out.parts.filter(p => p.synthesized).length === 1)
  check('长期记忆来自 ctx', html.includes('t-mem-list--long') && html.includes('较早对话摘要一'))
  check('无标记原文残留', !/【(面板|状态|内心|推演)】/.test(textLeft), JSON.stringify(textLeft))
  check('状态含强度徽标', html.includes('t-badge') && html.includes('微涨'))
  check('状态含涨跌方向', html.includes('is-up'))
  check('两个面板都渲染', (html.match(/t-fold--panel/g) || []).length === 2, html.slice(0, 200))
  check('推演渲染为折叠块', html.includes('t-fold') && html.includes('t-opt'))
  check('选项可点击回传', out.options.length === 2, JSON.stringify(out.options))
}

console.log('\n[2] 信息面板默认折叠（玩家信息与角色信息都是）')
{
  const out = renderReplyTemplate('【面板】玩家信息|姓名:小林\n【面板】身体状态|胸部:涨痛', T)
  const html = out.parts.map(p => p.html).join('')
  const panels = html.match(/<details class="t-fold t-fold--panel"[^>]*>/g) || []
  check('两个面板都不带 open', panels.length === 2 && panels.every(p => !p.includes('open')),
    JSON.stringify(panels))
  check('带条数徽标', (html.match(/t-fold-count/g) || []).length === 2)
}
{
  // ctx.expandPanels 时默认展开（留给"想常开"的用法）
  const out = renderReplyTemplate('【面板】玩家信息|姓名:小林', T, { expandPanels: true })
  check('expandPanels 时展开', /t-fold--panel" open/.test(out.parts[0].html), out.parts[0].html.slice(0, 160))
}

console.log('\n[3] 记忆回廊：短期 + 长期两层')
{
  const out = renderReplyTemplate('【记忆】记忆回廊|你替她挡了一次雨|她记住你喜欢的口味', T,
    { longTerm: ['（长期一）', '（长期二）'] })
  const h = out.parts[0].html
  check('标题为记忆回廊', h.includes('记忆回廊'))
  check('短期记忆子块', h.includes('t-mem-sub-h') && h.includes('短期记忆'))
  check('长期记忆子块', h.includes('长期记忆'))
  check('长期记忆内容来自应用数据', h.includes('（长期一）') && h.includes('（长期二）'))
  check('短期 2 条 + 长期 2 条 = 4 条', (h.match(/<li>/g) || []).length === 4,
    String((h.match(/<li>/g) || []).length))
}
{
  // 模型仍写旧标题「短期记忆」时，统一显示为记忆回廊
  const out = renderReplyTemplate('【记忆】短期记忆 (3/7)|条目一', T)
  check('旧标题被归一为记忆回廊', out.parts[0].html.includes('>记忆回廊<'), out.parts[0].html.slice(0, 120))
}

console.log('\n[4] 开场白变体')
{
  const out = renderReplyTemplate('你好呀，今天想聊些什么呢？', T, {})
  check('正文可渲染', out.parts.length >= 1 && out.parts[0].type === 'text')
}

console.log(`\n结果: ${pass} 通过, ${fail} 失败\n`)
process.exit(fail ? 1 : 0)
