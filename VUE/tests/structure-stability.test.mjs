/**
 * 结构稳定性回归测试：模型怎么写，界面都不能错乱。
 *
 * 真实踩过的两个坑（都来自线上对话记录）：
 *   1. 模型一轮写【场景】(时间|地点)，下一轮写【状态条】(地点|时间|氛围)，
 *      甚至同轮两个都写 —— 按位置硬取会让「地点」出现在「时间」的位置上；
 *   2. 模型偷懒不写【记忆】时，界面上完全看不到记忆宫殿（而摘要在库里一直有）。
 */
import { resolveTemplate } from '../src/utils/replyTemplates.js'
import { renderReplyTemplate } from '../src/utils/renderReplyTemplate.js'

let pass = 0, fail = 0
const check = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`  ok   ${name}`) }
  else { fail++; console.log(`  FAIL ${name} ${extra}`) }
}
const T = resolveTemplate(null)
const htmlOf = (raw, ctx) => renderReplyTemplate(raw, T, ctx || {})
  .parts.filter(p => p.type === 'html').map(p => p.html).join('')
// 取出场景/顶栏里的地点与时间，用于断言"谁在谁的位置上"
const sceneText = (raw) => {
  const h = htmlOf(raw)
  const place = (h.match(/is-place[^>]*>.*?<span>([^<]*)<\/span>/) || [])[1] || ''
  const time = (h.match(/t-scene-row">.*?<span>([^<]*)<\/span>/) || [])[1] || ''
  return { place, time }
}
const topbarText = (raw) => {
  const h = htmlOf(raw)
  // 顶栏地点是「图标 span + 紧跟的文本节点」，这里把图标那层吃掉再取文本
  const place = (h.match(/t-topbar-place[^>]*>(?:<span class="t-ico">[^<]*<\/span>)?([^<]*)/) || [])[1] || ''
  const time = (h.match(/t-topbar-time">([^<]*)</) || [])[1] || ''
  return { place: place.trim(), time: time.trim() }
}

console.log('\n[1] 场景/状态条：字段写反了也不能错位')
{
  const a = sceneText('【场景】周六 14:20|家里客厅，沙发')
  check('时间在前时：地点=家里客厅，时间=周六 14:20',
    a.place === '家里客厅，沙发' && a.time === '周六 14:20', JSON.stringify(a))

  const b = sceneText('【场景】家里客厅，沙发|周六 14:20')
  check('地点在前时同样归位正确',
    b.place === '家里客厅，沙发' && b.time === '周六 14:20', JSON.stringify(b))

  const c = sceneText('【场景】地点:二楼包厢|时间:凌晨 02:14|氛围:屏幕的蓝光映在墙面上')
  check('写了字段名时按名字归位',
    c.place === '二楼包厢' && c.time === '凌晨 02:14', JSON.stringify(c))

  const d = sceneText('【场景】时间:凌晨 02:14|地点:二楼包厢')
  check('具名字段顺序颠倒也不受影响',
    d.place === '二楼包厢' && d.time === '凌晨 02:14', JSON.stringify(d))

  const e = sceneText('【场景】Day 1|咖啡馆靠窗座位|雨声很密')
  check('英文时间写法也认得（Day 1）',
    e.place === '咖啡馆靠窗座位' && e.time === 'Day 1', JSON.stringify(e))
}

console.log('\n[2] 状态条（别名）与场景条语义一致')
{
  const t = topbarText('【状态条】家里客厅|周六 14:28|午后的光里，她坐在你腿上')
  check('顶栏地点/时间各自就位',
    t.place === '家里客厅' && t.time === '周六 14:28', JSON.stringify(t))

  const t2 = topbarText('【状态条】周六 14:28|家里客厅')
  check('顶栏写成时间在前也能纠正',
    t2.place === '家里客厅' && t2.time === '周六 14:28', JSON.stringify(t2))

  const h = htmlOf('【状态条】家里客厅|周六 14:28|午后的光|')
  check('结尾空字段不影响渲染', h.includes('t-topbar') && !h.includes('||'), h.slice(0, 120))
}

console.log('\n[3] 记忆宫殿：模型不写【记忆】也要显示长期记忆')
{
  const longTerm = ['- 人物：两人是兄妹关系，互动暧昧\n- 场景设定：客厅沙发上\n- 关键事件时间线：\n 1. 她主动凑过来']
  const h = htmlOf('正文一段。\n【推演】A.【继续】压上去|B.【停手】看反应', { longTerm })
  check('无【记忆】标记时补出记忆回廊', h.includes('t-fold--mem'))
  check('长期记忆标题写明记忆宫殿', h.includes('长期记忆（记忆宫殿）'))
  check('摘要拆成行而不是坨在一起',
    h.includes('t-mem-item-h') && h.includes('t-mem-line'))
  check('记忆块插在推荐行动之前',
    h.indexOf('t-fold--mem') < h.indexOf('t-opts'), `${h.indexOf('t-fold--mem')} vs ${h.indexOf('t-opts')}`)

  const out = renderReplyTemplate('正文。\n【推演】A.【继续】压上去', T, { longTerm })
  check('补出的块被标记为 synthesized', out.parts.some(p => p.synthesized))
  check('选项数不受补块影响', out.options.length === 1, JSON.stringify(out.options))

  const none = htmlOf('正文一段，没有推演。', { longTerm })
  check('没有推演时补在末尾', none.includes('t-fold--mem'))

  const empty = htmlOf('正文一段。')
  check('既没有标记也没有长期记忆时不凭空造块', !empty.includes('t-fold--mem'))
}

console.log('\n[4] 模型写了【记忆】时不能被重复补一份')
{
  const longTerm = ['- 摘要一']
  const h = htmlOf('【记忆】记忆回廊|她开始习惯靠着你\n【推演】A.【继续】', { longTerm })
  check('只有一块记忆回廊', (h.match(/t-fold--mem/g) || []).length === 1,
    String((h.match(/t-fold--mem/g) || []).length))
  check('短期与长期都在', h.includes('短期记忆') && h.includes('长期记忆（记忆宫殿）'))

  const h2 = htmlOf('【记忆】记忆回廊|她开始习惯靠着你')
  check('只有短期记忆时也能渲染', h2.includes('t-fold--mem') && h2.includes('短期记忆'))

  const h3 = htmlOf('【记忆】短期记忆 (3/7)|条目一|条目二')
  check('模型仍写旧标题「短期记忆 (n/m)」时标题归一为记忆回廊',
    h3.includes('记忆回廊') && !h3.includes('短期记忆 (3/7)'), h3.slice(0, 160))
}

console.log('\n[5] 每个预设的行为一致（换皮不换骨架）')
{
  const { TEMPLATE_PRESETS } = await import('../src/utils/replyTemplates.js')
  const raw = '【场景】周六 14:20|家里客厅\n【记忆】记忆回廊|条目一\n【推演】A.【继续】'
  const ctx = { longTerm: ['- 摘要一'] }
  let allOk = true
  const detail = []
  for (const id of Object.keys(TEMPLATE_PRESETS)) {
    const p = TEMPLATE_PRESETS[id]
    const out = renderReplyTemplate(raw, p, ctx)
    const html = out.parts.filter(x => x.type === 'html').map(x => x.html).join('')
    const okScene = html.includes('t-scene-row') && html.includes('家里客厅')
    const okMem = html.includes('t-fold--mem')
    const okOpt = out.options.length === 1
    if (!(okScene && okMem && okOpt)) { allOk = false; detail.push(`${id}:${okScene}/${okMem}/${okOpt}`) }
  }
  check('8 个预设都能正确处理同一段输入', allOk, detail.join(' '))
}

console.log('\n[6] 场景（时间/地点）必须置顶 —— 模型先写正文再补场景也不能错序')
{
  // 线上实测：模型先输出一句括号动作，再补【场景】，界面上地点/时间跑到正文后面
  const raw = '（说完就转头看窗外，耳朵那块在夕阳里透着红）\n【场景】16:07 (Day 1, 傍晚)|训练场外车内\n夕阳斜照，她汗湿的鬓角贴着脸侧'
  const parts = renderReplyTemplate(raw, T, {}).parts
  const firstHtmlIdx = parts.findIndex(p => p.type === 'html')
  const sceneIdx = parts.findIndex(p => p.type === 'html' && p.scene)
  check('场景块被提到了所有正文之前', sceneIdx === 0 && firstHtmlIdx === 0,
    `parts 顺序: ${parts.map(p => p.type + (p.scene ? '(scene)' : '')).join(' -> ')}`)

  // 正文里出现多个区块时，场景依然在最前、且各区块相对顺序保持稳定
  const raw2 = '【摘要】两人在车里聊开了\n【场景】16:07 (Day 1, 傍晚)|训练场外车内\n【面板】角色资料|姓名:陈默'
  const parts2 = renderReplyTemplate(raw2, T, {}).parts
  const order = parts2.map(p => p.scene ? 'S' : '.').join('')
  check('场景块排第一，其余区块相对顺序不变',
    order.startsWith('S') && parts2.filter(p => p.scene).length === 1, order)
}

console.log(`\n结果: ${pass} 通过, ${fail} 失败`)
process.exit(fail ? 1 : 0)
