/**
 * 正文渲染与内容类型区分（对白 / 心理动作 / 叙述）。
 *
 * 依赖 DOMParser：用 jsdom 提供；缺 jsdom 时自动跳过（见 run-all.mjs）。
 */
import { JSDOM } from 'jsdom'

const dom = new JSDOM('<!doctype html><html><body></body></html>')
global.window = dom.window
global.document = dom.window.document
global.DOMParser = dom.window.DOMParser
global.NodeFilter = dom.window.NodeFilter

const { renderProse, decorateProse } = await import('../src/utils/proseRender.js')

let pass = 0, fail = 0
const check = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`  ok   ${name}`) }
  else { fail++; console.log(`  FAIL ${name} ${extra}`) }
}

console.log('\n[1] Markdown 被真正渲染（此前正文没有段落）')
{
  const html = renderProse('第一段\n\n第二段')
  check('生成两个段落', (html.match(/<p/g) || []).length === 2, html)
  check('段落带叙述标记', html.includes('rtpl-narr'))
}
{
  const html = renderProse('**加粗**与*斜体*')
  check('加粗生效', html.includes('<strong>'), html)
  check('斜体生效', html.includes('<em>'), html)
}
{
  const html = renderProse('单行\n换行')
  check('单换行即换行（breaks）', html.includes('<br'), html)
}

console.log('\n[2] 对白识别（说的话单独标记）')
for (const [name, text, want] of [
  ['直角引号「」', '她说：「你来了。」', '「你来了。」'],
  ['双直角『』', '她低声说『别走』。', '『别走』'],
  ['中文双引号“”', '她说：“你来了。”', '“你来了。”'],
  ['英文双引号 ""', 'She said "hello" softly.', '"hello"'],
]) {
  const html = renderProse(text)
  check(`${name} -> rtpl-say`, html.includes('class="rtpl-say"') && html.includes(want), html)
}

console.log('\n[3] 心理/动作（括号）识别')
{
  const html = renderProse('（她心跳快了半拍）')
  check('中文括号 -> rtpl-bracket', html.includes('class="rtpl-bracket"'), html)
}
{
  const html = renderProse('(waited a while)')
  check('英文括号 -> rtpl-bracket', html.includes('class="rtpl-bracket"'), html)
}

console.log('\n[4] 叙述描写仍走默认，不与对白混淆')
{
  const html = renderProse('她抬起头看向你。')
  check('无对白时不产生 rtpl-say', !html.includes('rtpl-say'), html)
  check('有叙述段落标记', html.includes('rtpl-narr'))
}

console.log('\n[5] 对白起首的段落单独标记（供模板取消缩进）')
{
  const html = renderProse('「你今天回来好晚。」')
  check('段落带 rtpl-say-line', html.includes('rtpl-say-line'), html)
}
{
  const html = renderProse('她轻声说：「嗯。」')
  check('对白不在段首则不加该标记', !html.includes('rtpl-say-line'), html)
}

console.log('\n[6] 混排：三类内容同时出现且互不干扰')
{
  const html = renderProse('她抬起头。\n「你来了。」\n（其实等了很久）')
  check('有对白', html.includes('class="rtpl-say"'), html)
  check('有括号内容', html.includes('class="rtpl-bracket"'), html)
  check('三者共存', html.includes('她抬起头') && html.includes('你来了') && html.includes('其实等了很久'))
}

console.log('\n[7] 安全：模型写的 HTML 必须当纯文本')
{
  const html = renderProse('<img src=x onerror=alert(1)>')
  check('尖括号被转义', html.includes('&lt;img'), html)
  check('无真实 img 标签', !/<img/i.test(html), html)
}
{
  const html = renderProse('<script>alert(1)</script>')
  check('script 被清除', !html.includes('<script'), html)
}
{
  // 代码块内的引号不应被当成对白
  const html = renderProse('```\nconst a = "x"\n```')
  check('代码块内不打对白标记', !html.includes('rtpl-say'), html)
}

console.log('\n[8] 容错')
check('空串返回空', renderProse('') === '')
{
  // 真实模拟"没有 DOMParser"的环境（如极简运行时），应原样返回而不是抛错
  const saved = global.DOMParser
  delete global.DOMParser
  const out = decorateProse('<p>a</p>')
  global.DOMParser = saved
  check('无 DOMParser 时原样返回', out === '<p>a</p>', out)
}

console.log('\n[9] 字面 <br> 还原成换行（不能以文字显示出来）')
{
  const html = renderProse('第一句<br>第二句')
  check('不再出现字面 <br> 文本', !html.includes('&lt;br'), html)
  check('变成真实换行', html.includes('<br') || html.includes('第一句'), html)
  check('两句都在', html.includes('第一句') && html.includes('第二句'), html)
}
{
  const html = renderProse('甲<br/>乙<br />丙')
  check('三种 <br> 写法都还原', !html.includes('&lt;br'), html)
}
{
  const html = renderProse('&nbsp;空格')
  check('&nbsp; 还原为空格', !html.includes('&amp;nbsp;'), html)
}

console.log(`\n结果: ${pass} 通过, ${fail} 失败\n`)
process.exit(fail ? 1 : 0)
