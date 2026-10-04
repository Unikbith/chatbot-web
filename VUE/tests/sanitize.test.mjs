// 临时验证：富渲染消毒通道（安全关键）
// DOMPurify 需要 DOM，用 jsdom 或浏览器环境都不便，这里直接用 Node 起一个最小 DOM 存根。
import { JSDOM } from 'jsdom'

const dom = new JSDOM('<!doctype html><html><body></body></html>')
global.window = dom.window
global.document = dom.window.document

const { sanitizeRichHtml, sanitizeHtml } = await import('../src/utils/sanitize.js')

let pass = 0, fail = 0
const check = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`  ok   ${name}`) }
  else { fail++; console.log(`  FAIL ${name} ${extra}`) }
}

console.log('\n[1] 脚本与事件必须被清掉')
check('<script> 被移除', !sanitizeRichHtml('<div>a</div><script>alert(1)</script>').includes('<script'))
check('onerror 被移除', !sanitizeRichHtml('<img src=x onerror=alert(1)>').includes('onerror'))
check('onclick 被移除', !sanitizeRichHtml('<div onclick="x()">a</div>').includes('onclick'))
check('iframe 被移除', !sanitizeRichHtml('<iframe src="//evil.com"></iframe>').includes('iframe'))
check('form/input 被移除', !sanitizeRichHtml('<form><input value="x"></form>').includes('<input'))
check('javascript: 链接被移除', !sanitizeRichHtml('<a href="javascript:alert(1)">x</a>').includes('javascript:'))

console.log('\n[2] 允许的排版能力（模板需要）')
check('class 保留', sanitizeRichHtml('<div class="t-panel">a</div>').includes('t-panel'))
check('id 保留', sanitizeRichHtml('<div id="x">a</div>').includes('id="x"'))
check('button 保留', sanitizeRichHtml('<button class="t-opt" data-opt-idx="0">a</button>').includes('<button'))
check('data-opt-idx 保留', sanitizeRichHtml('<button data-opt-idx="0">a</button>').includes('data-opt-idx="0"'))
// 注意：过滤后会把声明规范化成 `width: 70%`（冒号后补空格），断言按规范化结果写
check('安全内联样式保留', /width:\s*70%/.test(sanitizeRichHtml('<i style="width:70%"></i>')))
check('多属性样式过滤', /width:\s*70%/.test(sanitizeRichHtml('<i style="width:70%;color:red"></i>')))
check('颜色声明保留', /color:\s*red/.test(sanitizeRichHtml('<i style="width:70%;color:red"></i>')))
check('section/ol/li 保留', sanitizeRichHtml('<section><ol><li>a</li></ol></section>').includes('<li>'))

console.log('\n[3] 危险样式必须被丢弃')
{
  const out = sanitizeRichHtml('<div style="position:fixed;top:0">a</div>')
  check('position 被丢弃', !out.includes('position'), out)
}
{
  const out = sanitizeRichHtml('<div style="background-image:url(//evil.com/a.png)">a</div>')
  check('url() 被丢弃', !out.includes('url('), out)
}
{
  const out = sanitizeRichHtml('<div style="background-image:linear-gradient(red,blue)">a</div>')
  check('渐变图片保留', out.includes('linear-gradient'), out)
}
{
  const out = sanitizeRichHtml('<div style="width:expression(alert(1))">a</div>')
  check('expression 被丢弃', !out.includes('expression'), out)
}
{
  const out = sanitizeRichHtml('<div style="width:calc(1px);behavior:url(x)">a</div>')
  check('behavior 被丢弃', !out.includes('behavior'), out)
}
{
  const out = sanitizeRichHtml('<div data-x="1">a</div>')
  check('自定义 data-* 被丢弃', !out.includes('data-x'), out)
}

console.log('\n[4] 普通通道不受影响（回归）')
check('普通通道仍禁 style', !sanitizeHtml('<i style="width:70%"></i>').includes('style'))
check('普通通道仍保留 class', sanitizeHtml('<div class="x">a</div>').includes('class="x"'))
check('普通通道清除脚本', !sanitizeHtml('<script>alert(1)</script>').includes('<script'))

console.log(`\n结果: ${pass} 通过, ${fail} 失败\n`)
process.exit(fail ? 1 : 0)
