/**
 * 结构契约测试：骨架 _base.css + 主题文件的职责划分。
 *
 * 架构：
 *   _base.css      → 结构、排版与默认变量（不带具体配色）
 *   <preset>.css   → 只覆盖一组 --rtpl-* 变量（换风格）
 * 本文件守住「骨架侧」的契约；各预设的完整性由 template-presets.test.mjs 负责。
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { TEMPLATE_PRESETS } from '../src/utils/replyTemplates.js'
import { renderReplyTemplate } from '../src/utils/renderReplyTemplate.js'

const here = dirname(fileURLToPath(import.meta.url))
const DIR = join(here, '..', 'src', 'assets', 'reply-templates')
const base = readFileSync(join(DIR, '_base.css'), 'utf8')

let pass = 0, fail = 0
const check = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`  ok   ${name}`) }
  else { fail++; console.log(`  FAIL ${name} ${extra}`) }
}

const T = TEMPLATE_PRESETS.archive

console.log('\n[1] 整框容器（"渲染整个输出框"的关键）')
check('有 .rtpl 容器规则', /\.rtpl\s*\{/.test(base))
check('容器有内边距', /\.rtpl\s*\{[^}]*padding:/.test(base))
check('容器有圆角', /\.rtpl\s*\{[^}]*border-radius:\s*var\(--rtpl-radius\)/.test(base))
check('容器背景走变量', /\.rtpl\s*\{[^}]*background:\s*var\(--rtpl-bg\)/.test(base))
check('容器边框走变量', /\.rtpl\s*\{[^}]*border:\s*1px solid var\(--rtpl-border\)/.test(base))
check('容器字体走变量', /\.rtpl\s*\{[^}]*font-family:\s*var\(--rtpl-font\)/.test(base))
check('容器字号走变量', /\.rtpl\s*\{[^}]*font-size:\s*var\(--rtpl-font-size\)/.test(base))

console.log('\n[2] 正文排版')
check('有正文段落规则', base.includes('.rtpl .rtpl-prose p'))
check('首行缩进可配置', /\.rtpl \.rtpl-prose p\s*\{[^}]*text-indent:\s*var\(--rtpl-indent\)/.test(base))
check('标题不缩进', /\.rtpl \.rtpl-prose h1[\s\S]{0,400}?text-indent:\s*0/.test(base))
check('强调色走变量', /\.rtpl \.rtpl-prose strong[\s\S]{0,120}?var\(--rtpl-accent-strong\)/.test(base))
check('列表/引用/代码/表格都有规则', ['blockquote', 'code', 'table', 'ul'].every(k => base.includes(`.rtpl .rtpl-prose ${k}`)))

console.log('\n[3] 骨架默认变量齐备（预设可只覆盖一部分）')
const used = new Set([...base.matchAll(/var\((--rtpl-[\w-]+)\)/g)].map(m => m[1]))
const defined = new Set([...base.matchAll(/(--rtpl-[\w-]+)\s*:/g)].map(m => m[1]))
const missing = [...used].filter(v => !defined.has(v))
check('使用到的变量都有默认值', missing.length === 0, missing.join(', '))
check('变量数量合理（>20）', defined.size > 20, String(defined.size))

console.log('\n[4] 引擎产出的 class 在骨架里都有规则')
const SAMPLE = [
  '【场景】23:42|客厅', '【摘要】摘要内容',
  '【面板】用户信息|姓名:甲|年龄:22', '【面板】想法|整行正文',
  '【状态】状态|好感度:99/100【注释】',
  '【记忆】短期记忆|条目一', '【推演】A.【标题】描述',
  '【物品】药:3', '【提醒】注意', '正文。',
].join('\n')
const { parts, options } = renderReplyTemplate(SAMPLE, T)
check('样例覆盖全部标记', parts.filter(p => p.type === 'html').length >= 8)
check('推演选项被识别', options.length === 1, JSON.stringify(options))

const html = parts.filter(p => p.type === 'html').map(p => p.html).join('')
const usedClasses = new Set(['rtpl', 'rtpl-prose', 'rtpl-block'])
for (const m of html.matchAll(/class="([^"]+)"/g)) {
  for (const c of m[1].split(/\s+/)) if (c) usedClasses.add(c)
}
const inBase = new Set([...base.matchAll(/\.([a-zA-Z][\w-]*)/g)].map(m => m[1]))
const noStyle = [...usedClasses].filter(c => !inBase.has(c))
check('无未覆盖的 class', noStyle.length === 0, noStyle.join(', '))

console.log('\n[5] 骨架不得泄漏到全站')
{
  const body = base.replace(/\/\*[\s\S]*?\*\//g, '')
  const selectors = [...body.matchAll(/(^|\})\s*([^{}@]+)\{/g)].map(m => m[2].trim()).filter(Boolean)
  const leak = selectors.filter(s => !s.includes('.rtpl'))
  check('所有选择器都限定在 .rtpl 下', leak.length === 0, leak.slice(0, 5).join(' | '))
}

console.log(`\n结果: ${pass} 通过, ${fail} 失败\n`)
process.exit(fail ? 1 : 0)
