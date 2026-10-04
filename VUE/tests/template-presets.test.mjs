/**
 * 交叉核对：每套渲染预设都要覆盖骨架用到的全部样式钩子。
 *
 * 防的是「新加一个预设，但只写了一半变量 → 某些区块没样式、看起来像坏了」。
 * 做法：把 _base.css 里用到的所有 CSS 变量收集起来，
 * 再检查每个预设文件是否都给出了取值（或可继承自默认值）。
 */
import { readFileSync, readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { TEMPLATE_PRESET_LIST } from '../src/utils/replyTemplates.js'
import { renderReplyTemplate } from '../src/utils/renderReplyTemplate.js'

const here = dirname(fileURLToPath(import.meta.url))
const DIR = join(here, '..', 'src', 'assets', 'reply-templates')
const base = readFileSync(join(DIR, '_base.css'), 'utf8')

let pass = 0, fail = 0
const check = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`  ok   ${name}`) }
  else { fail++; console.log(`  FAIL ${name} ${extra}`) }
}

console.log('\n[1] 骨架与预设文件齐备')
const files = readdirSync(DIR).filter(f => f.endsWith('.css'))
check('存在 _base.css', files.includes('_base.css'), files.join(','))
for (const p of TEMPLATE_PRESET_LIST) {
  check(`预设 ${p.id} 有 CSS 文件`, files.includes(`${p.id}.css`), files.join(','))
}

console.log('\n[2] 骨架里用到的变量，每套预设都要有取值')
// 收集 _base.css 中使用到的 --rtpl-* 变量
const usedVars = new Set()
for (const m of base.matchAll(/var\((--rtpl-[\w-]+)\)/g)) usedVars.add(m[1])
// 以及骨架自带默认值（写在 .rtpl { } 里的），这些可以被子预设继承
const definedInBase = new Set()
for (const m of base.matchAll(/(--rtpl-[\w-]+)\s*:/g)) definedInBase.add(m[1])

console.log(`    骨架使用变量 ${usedVars.size} 个，默认定义 ${definedInBase.size} 个`)
const noDefault = [...usedVars].filter(v => !definedInBase.has(v))
check('所有使用到的变量都有默认值', noDefault.length === 0, noDefault.join(', '))

for (const p of TEMPLATE_PRESET_LIST) {
  const css = readFileSync(join(DIR, `${p.id}.css`), 'utf8')
  const scopeOk = css.includes(`.rtpl.rtpl-${p.id}`)
  check(`${p.id}: 根选择器为 .rtpl.rtpl-${p.id}`, scopeOk)
  // 主题至少要给出配色类变量，否则等于没换风格
  const themed = ['--rtpl-bg', '--rtpl-fg', '--rtpl-accent'].filter(v => css.includes(v))
  check(`${p.id}: 覆盖核心配色变量`, themed.length === 3, themed.join(','))
  // 选择器不得泄漏到全站
  const selectors = [...css.matchAll(/(^|\})\s*([^{}@]+)\{/g)].map(m => m[2].trim()).filter(Boolean)
  const leak = selectors.filter(s => !s.includes('.rtpl'))
  check(`${p.id}: 无泄漏到全站的选择器`, leak.length === 0, leak.slice(0, 3).join(' | '))
  // 暗色适配：本身就是深色设计的预设（darkNative）无需额外覆盖
  if (p.darkNative) {
    check(`${p.id}: 深色原生，无需暗色覆盖`, true)
  } else {
    check(`${p.id}: 有暗色适配`, css.includes(`html.dark .rtpl.rtpl-${p.id}`))
  }
}

console.log('\n[3] 引擎产出的 class 在骨架里都有规则')
const SAMPLE = [
  '【场景】23:42|客厅', '【摘要】摘要内容',
  '【面板】用户信息|姓名:甲|年龄:22', '【面板】想法|整行正文',
  '【状态】状态|好感度:99/100【注释】',
  '【记忆】短期记忆|条目一', '【推演】A.【标题】描述',
  '【物品】药:3', '【提醒】注意', '正文。',
].join('\n')
const { parts } = renderReplyTemplate(SAMPLE, TEMPLATE_PRESET_LIST[0])
const html = parts.filter(p => p.type === 'html').map(p => p.html).join('')
const used = new Set(['rtpl', 'rtpl-prose', 'rtpl-block'])
for (const m of html.matchAll(/class="([^"]+)"/g)) {
  for (const c of m[1].split(/\s+/)) if (c) used.add(c)
}
const inBase = new Set()
for (const m of base.matchAll(/\.([a-zA-Z][\w-]*)/g)) inBase.add(m[1])
const missing = [...used].filter(c => !inBase.has(c))
check('无未覆盖的 class', missing.length === 0, missing.join(', '))

console.log(`\n结果: ${pass} 通过, ${fail} 失败\n`)
process.exit(fail ? 1 : 0)
