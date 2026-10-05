// 临时验证：渲染模板引擎 + 消毒通道
import { TEMPLATE_PRESETS, DEFAULT_TEMPLATE_ID, resolveTemplate, templateMarkers, DEFAULT_PROTOCOL, protocolPrompt, composeTemplatePrompt, OUTPUT_LENGTH_LIST, DEFAULT_LENGTH } from '../src/utils/replyTemplates.js'
import { renderReplyTemplate } from '../src/utils/renderReplyTemplate.js'
import { hasRichMarkers, GENERIC_MARKERS } from '../src/utils/richMessage.js'

let pass = 0, fail = 0
const check = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`  ok   ${name}`) }
  else { fail++; console.log(`  FAIL ${name} ${extra}`) }
}

const T = TEMPLATE_PRESETS.archive
const DEFAULT_T = TEMPLATE_PRESETS[DEFAULT_TEMPLATE_ID]

console.log('\n[1] 预设结构')
check('预设存在', !!T)
// 预设样式已改为独立 CSS 文件静态引入（assets/reply-templates/archive.css），
// 不再内联在 JS 里，所以这里断言「登记信息完整」与「有给 AI 的提示词」
check('预设 id 正确', T.id === 'archive', T.id)
check('预设名与说明齐全', !!T.name && !!T.desc)
check('有提示词', typeof T.prompt === 'string' && T.prompt.includes('【场景】'))
check('不含内联 CSS（改由静态文件提供）', !T.css, JSON.stringify(T.css))
check('标记词表', templateMarkers(T).length >= 6, JSON.stringify(templateMarkers(T)))
check('resolveTemplate 认 preset', resolveTemplate(JSON.stringify({ preset: 'archive' })) === T)
check('未保存过模板时返回默认预设', resolveTemplate(null) === DEFAULT_T && resolveTemplate('') === DEFAULT_T,
  String(resolveTemplate(null)))
check('坏 JSON 时也回落默认预设', resolveTemplate('不是json') === DEFAULT_T)
check('未知 preset 回落默认预设', resolveTemplate(JSON.stringify({ preset: '不存在' })) === DEFAULT_T)
check('新用户默认外观为脸红', DEFAULT_TEMPLATE_ID === 'blush', DEFAULT_TEMPLATE_ID)

console.log('\n[2] 场景 / 摘要')
{
  const r = renderReplyTemplate('【场景】23:42 (Day 1, 晚上)|公寓客厅沙发', T)
  check('产出 1 块', r.hasBlock && r.parts.length === 1)
  check('含时间', r.parts[0].html.includes('23:42'))
  check('含地点', r.parts[0].html.includes('公寓客厅沙发'))
  check('地点行有区分类', r.parts[0].html.includes('is-place'))
}
{
  const r = renderReplyTemplate('【摘要】她第一次主动主导了节奏', T)
  check('摘要渲染', r.hasBlock && r.parts[0].html.includes('t-sum'))
}

console.log('\n[3] 面板（键值 + 标签胶囊）')
{
  const r = renderReplyTemplate('【面板】角色资料|姓名:陈默|性别:男|性格:话少但细心', T)
  const h = r.parts[0].html
  check('标题', h.includes('角色资料'))
  check('三个标签', (h.match(/class="t-k(?: c\d)?"/g) || []).length === 3, h)
  check('值渲染', h.includes('陈默') && h.includes('话少但细心'))
  check('面板容器（折叠栏结构）', h.includes('t-fold-h') && h.includes('<details'))
}
{
  const r = renderReplyTemplate('【面板】内心想法|我他妈真的自己动了。', T)
  check('无冒号整行作正文', r.parts[0].html.includes('t-row-text'), r.parts[0].html)
}

console.log('\n[4] 状态（数值/上限 + 注释 + 进度条）')
{
  const r = renderReplyTemplate('【状态】角色状态|好感度:72/100【她开始主动找话题】|信任度:45/100', T)
  const h = r.parts[0].html
  check('卡片标题', h.includes('角色状态'))
  check('分子分母', h.includes('>72<') && h.includes('>/100<'), h.slice(0, 400))
  check('注释渲染', h.includes('她开始主动找话题'))
  check('进度条', h.includes('t-bar-fill') && h.includes('width:72%'))
}
{
  // 0/100 应得到宽度 0 的条
  const r = renderReplyTemplate('【状态】角色状态|干劲:0/100', T)
  check('0/100 条宽为 0', r.parts[0].html.includes('width:0%'), r.parts[0].html)
}
{
  const r = renderReplyTemplate('【状态】好感度:很高', T)
  check('非数值也能渲染', r.hasBlock && r.parts[0].html.includes('很高'))
}

console.log('\n[5] 记忆 / 推演 / 物品 / 提醒')
{
  const r = renderReplyTemplate('【记忆】短期记忆 (3/7)|你替她挡了一次雨|她记住了你喜欢的口味', T)
  const h = r.parts[0].html
  check('标题统一显示为记忆回廊', h.includes('记忆回廊'))
  check('两条条目', (h.match(/<li>/g) || []).length === 2)
  check('渐变标题类', h.includes('t-mem-h'))
  check('短期记忆子块', h.includes('t-mem-sub-h') && h.includes('短期记忆'))
}
{
  const r = renderReplyTemplate('【推演】A.【直接告白】把话说清楚|B.【维持现状】先不打破现在的距离', T)
  const h = r.parts[0].html
  check('两个选项', r.options.length === 2, JSON.stringify(r.options))
  check('选项按钮', (h.match(/data-opt-idx=/g) || []).length === 2)
  check('标题加粗', h.includes('t-opt-t') && h.includes('直接告白'))
  check('文案回传给点击用', r.options[0].includes('直接告白') && r.options[0].includes('把话说清楚'), r.options[0])
}
{
  const r = renderReplyTemplate('【物品】金创药:3|火折子:1', T)
  check('物品渲染', r.parts[0].html.includes('金创药') && r.parts[0].html.includes('×3'))
}
{
  const r = renderReplyTemplate('【提醒】今晚要去后山', T)
  check('提醒渲染', r.parts[0].html.includes('t-alert'))
}

console.log('\n[6] 正文与标记混排 + 容错')
{
  const raw = '她抬起头看向你。\n【状态】好感度:45\n「你来了。」'
  const r = renderReplyTemplate(raw, T)
  check('三段（文/块/文）', r.parts.length === 3, JSON.stringify(r.parts.map(p => p.type)))
  check('首段是文本', r.parts[0].type === 'text' && r.parts[0].text.includes('抬起头'))
  check('中段是 HTML', r.parts[1].type === 'html')
  check('末段是文本', r.parts[2].type === 'text' && r.parts[2].text.includes('你来了'))
}
{
  const r = renderReplyTemplate('开头【状态】好感度:45结尾', T)
  check('标记不在行首 -> 不解析', !r.hasBlock && r.parts[0].type === 'text', JSON.stringify(r.parts))
  check('原文完整保留', r.parts[0].text === '开头【状态】好感度:45结尾')
}
{
  const r = renderReplyTemplate('【不存在的标记】内容', T)
  check('未知标记按文本', !r.hasBlock)
}
{
  const r = renderReplyTemplate('【状态】', T)
  check('空标记按文本', !r.hasBlock)
}
{
  const r = renderReplyTemplate('', T)
  check('空串返回空', r.parts.length === 0)
}

console.log('\n[7] 转义（防注入）')
{
  const r = renderReplyTemplate('【摘要】<img src=x onerror=alert(1)>', T)
  check('尖括号被转义', r.parts[0].html.includes('&lt;img'), r.parts[0].html)
  check('无原始标签', !r.parts[0].html.includes('<img'))
}
{
  const r = renderReplyTemplate('【面板】标题|姓名:"onmouseover="alert(1)', T)
  check('引号被转义', r.parts[0].html.includes('&quot;'), r.parts[0].html)
}

console.log('\n[8] hasRichMarkers 支持模板词表')
{
  const names = templateMarkers(T)
  check('识别模板标记', hasRichMarkers('【场景】x|y', names) === true)
  check('识别记忆', hasRichMarkers('【记忆】长期记忆|a', names) === true)
  check('只给模板词表时不认通用标记（调用方需自行并入通用词表）',
    hasRichMarkers('【进度】x|1', names) === false)
  const many = names.map(n => hasRichMarkers(`【${n}】a`, names))
  check('连续调用不丢判', many.every(Boolean), JSON.stringify(many))
}

console.log('\n[9] 模板未定义的通用标记必须兜底渲染（不得露出原文）')
{
  // 场景：选了档案风（词表无「进度」），模型却输出了【进度】
  // —— 这正是实测中"气泡里出现【进度】好感度|83 原文"的那条 bug
  const r = renderReplyTemplate('【进度】好感度|83', T)
  check('判定为可渲染', r.hasBlock === true, JSON.stringify(r.parts))
  check('翻译成模板区块（不是通用组件，避免两套风格）',
    r.parts.length === 1 && r.parts[0].type === 'html', JSON.stringify(r.parts.map(p => p.type)))
  check('用模板的状态行渲染', r.parts[0].html.includes('t-stat'), r.parts[0].html)
  check('画出模板的迷你进度条', r.parts[0].html.includes('t-bar-fill') && r.parts[0].html.includes('width:83%'),
    r.parts[0].html)
  check('不残留标记原文', !r.parts.some(p => p.type === 'text' && String(p.text).includes('【进度】')),
    JSON.stringify(r.parts))
}
{
  // 通用【选项】应翻译成模板的推演卡片
  const r = renderReplyTemplate('【选项】A. 上前询问|B. 静静观察', T)
  check('选项翻译成推演区块', r.parts[0].type === 'html' && r.parts[0].html.includes('t-opt'),
    JSON.stringify(r.parts.map(p => p.type)))
  check('选项文案可点击回传', r.options.length === 2, JSON.stringify(r.options))
}
{
  // 通用标记与模板标记混排，两者都要出块
  const r = renderReplyTemplate('【场景】08:15|咖啡馆\n【进度】好感度|60\n【选项】A. 上前|B. 离开', T)
  check('两种词表混排都渲染成模板区块',
    r.parts.every(p => p.type === 'html') && r.parts.length === 3,
    JSON.stringify(r.parts.map(p => p.type)))
}
{
  // 完全未知的标记仍按原文显示（而不是被吞掉）
  const r = renderReplyTemplate('【某个不存在的标记】内容', T)
  check('未知标记保留原文',
    r.parts[0].type === 'text' && r.parts[0].text.includes('【某个不存在的标记】'), JSON.stringify(r.parts))
}

console.log('\n[10] 通用词表导出给检测层使用（ChatArea 需要它）')
{
  check('导出 GENERIC_MARKERS', Array.isArray(GENERIC_MARKERS) && GENERIC_MARKERS.includes('进度'),
    JSON.stringify(GENERIC_MARKERS))
  const names = [...templateMarkers(T), ...GENERIC_MARKERS]
  check('合并词表能识别通用标记', hasRichMarkers('【进度】x|1', names) === true)
  check('合并词表仍识别模板标记', hasRichMarkers('【场景】a|b', names) === true)
}

console.log('\n[11] 新增构件：状态条 / 模块 / 内心 / 数值差值 / 自动配色')
{
  const r = renderReplyTemplate('【状态条】星火网咖2F-双人包间|02:55|屏幕还亮着', T)
  const h = r.parts[0].html
  check('状态条渲染', r.hasBlock && h.includes('t-topbar'), h)
  check('含标题', h.includes('星火网咖2F-双人包间'))
  check('含时间', h.includes('02:55'))
  check('含状态句', h.includes('屏幕还亮着'))
}
{
  const r = renderReplyTemplate('【模块】USER.DAT|角色状态.EXE|记忆回廊 (L:2 S:11)|💾 存档', T)
  const h = r.parts[0].html
  check('模块表渲染', r.hasBlock && h.includes('t-modules'), h)
  check('四项模块', (h.match(/class="t-module"/g) || []).length === 4, h)
  check('徽标被解析成 badge', h.includes('t-module-badge') && h.includes('L:2 S:11'), h)
  check('带表情前缀的模块名拆分', h.includes('t-module-ico') && h.includes('存档'), h)
}
{
  const r = renderReplyTemplate('【内心】我完了……他怎么什么都记得。', T)
  const h = r.parts[0].html
  check('内心独白渲染', r.hasBlock && h.includes('t-inner'), h)
  check('内容保留', h.includes('他怎么什么都记得'))
}
{
  const r = renderReplyTemplate('【状态】角色状态|好感度:100→100|信任度:45→52【你替她解了围】', T)
  const h = r.parts[0].html
  check('差值渲染', h.includes('t-delta'), h)
  check('标记为 flat', h.includes('is-flat'), h)
  check('标记为 up', h.includes('is-up'), h)
  check('旧新值都在', h.includes('t-delta-from') && h.includes('t-delta-to'))
  check('注释不带方括号残留', h.includes('你替她解了围') && !h.includes('【你替她解了围】'), h)
}
{
  // 自动配色：每个标签拿到 c1..c6 中的一个
  const r = renderReplyTemplate('【状态】状态|A:1|B:2|C:3|D:4|E:5|F:6|G:7', T)
  const h = r.parts[0].html
  const tones = [...h.matchAll(/t-k (c\d)/g)].map(m => m[1])
  check('标签带配色类', tones.length === 7, JSON.stringify(tones))
  check('第 7 项回到 c1（循环）', tones[6] === 'c1', JSON.stringify(tones))
}

console.log('\n[14] 字面 <br> 必须还原成换行（否则标记识别失败 + 显示成文字）')
{
  // 复现实测：模型把换行写成 <br>，整段变成一行 → 【进度】不在行首 → 漏成原文
  const raw = '（睫毛颤了一下）<br> <br>（你低头靠近）<br> <br>【进度】好感度|88'
  const r = renderReplyTemplate(raw, T)
  check('标记被正确识别', r.hasBlock === true, JSON.stringify(r.parts.map(p => p.type)))
  check('渲染成模板状态行', r.parts.some(p => p.type === 'html' && p.html.includes('t-bar-fill')),
    JSON.stringify(r.parts.map(p => p.type)))
  check('标记原文不再残留', !r.parts.some(p => p.type === 'text' && String(p.text).includes('【进度】')),
    JSON.stringify(r.parts))
  check('正文里不再有字面 <br>', !r.parts.some(p => p.type === 'text' && /<br/i.test(String(p.text))),
    JSON.stringify(r.parts))
  const textPart = r.parts.find(p => p.type === 'text')
  check('正文保留了两段描写', textPart && textPart.text.includes('睫毛颤了一下') && textPart.text.includes('你低头靠近'),
    JSON.stringify(textPart))
}
{
  // 各种 <br> 写法都要认
  for (const br of ['<br>', '<br/>', '<br />', '<BR>', '</br>']) {
    const r = renderReplyTemplate(`前面${br}【进度】好感度|50`, T)
    check(`识别 ${br}`, r.parts.some(p => p.type === 'html' && p.html.includes('t-bar-fill')), br)
  }
}
{
  // 连续多个空行折叠，不至于把输出框撑得很难看
  const r = renderReplyTemplate('第一段\n\n\n\n\n第二段', T)
  const t = r.parts.find(p => p.type === 'text')
  check('多余空行被折叠', t && !/\n{3,}/.test(t.text), JSON.stringify(t && t.text))
}

console.log('\n[15] 句中标记必须被拆出来（否则整段标记漏成原文）')
{
  // 复现实测：模型把多个标记挤在一行、用字面 <br> 或句末标点相连
  const raw = '叫什么叫，就叫林小雨啊。<br><br>【面板】玩家信息|姓名:小林|性别:男'
    + '<br><br>【状态】林小雨|好感度:76→78[微涨]|信任度:52→52[持平]'
    + '<br><br>【内心】你要是敢说个正经的，我就骂你。'
    + '<br><br>【推演】A.【顺着逗她】说个暖昧的称呼|B.【装傻】故意晾她'
  const r = renderReplyTemplate(raw, T)
  const html = r.parts.filter(p => p.type === 'html').map(p => p.html).join('')
  check('面板被识别', html.includes('t-panel-h'), html.slice(0, 200))
  check('状态被识别', html.includes('t-stat'), html.slice(0, 200))
  check('内心被识别', html.includes('t-inner'))
  check('推演被识别', html.includes('t-opt'))
  check('正文里不含任何标记原文',
    !r.parts.some(p => p.type === 'text' && /【(面板|状态|内心|推演)】/.test(String(p.text))),
    JSON.stringify(r.parts.filter(p => p.type === 'text').map(p => p.text)))
  check('正文不含字面 <br>', !r.parts.some(p => p.type === 'text' && /<br/i.test(String(p.text))))
  check('选项可点击回传', r.options.length === 2, JSON.stringify(r.options))
}
{
  // 句子中间的标记不该被硬拆（避免把正文切断）
  const r = renderReplyTemplate('她说【提醒】记得带伞这句话', T) 
  check('句中标点前的标记保持原样', !r.hasBlock || r.parts.some(p => p.type === 'text'), JSON.stringify(r.parts.map(p => p.type)))
}

console.log('\n[16] 状态强度徽标与标题容错')
{
  const r = renderReplyTemplate('【状态】林小雨|好感度:76→78[微涨]|信任度:52→52[持平]', T)
  const h = r.parts[0].html
  check('标题被拆出', h.includes('林小雨') && h.includes('t-panel-h'), h.slice(0, 200))
  check('强度徽标渲染', h.includes('t-badge') && h.includes('微涨'))
  check('涨跌方向类', h.includes('is-up') && h.includes('is-flat'))
}
{
  // 标题与首项挤在一格（空格分隔）也要能拆
  const r = renderReplyTemplate('【状态】林小雨 好感度:76→78[微涨]', T)
  const h = r.parts[0].html
  check('空格分隔的标题被拆出', h.includes('t-panel-h') && h.includes('林小雨'), h.slice(0, 260))
  check('首项数值正常', h.includes('t-delta') && h.includes('76') && h.includes('78'))
}

console.log('\n[17] 回复长度选项（前端只拥有选项与文案；篇幅正文由后端 reply_spec 负责）')
{
  check('三档长度齐备', OUTPUT_LENGTH_LIST.length === 3, JSON.stringify(OUTPUT_LENGTH_LIST.map(l => l.id)))
  check('默认长度为 medium（默认「适中」，与后端 reply_spec.DEFAULT_LENGTH 一致）',
    DEFAULT_LENGTH === 'medium', DEFAULT_LENGTH)
  check('三档都有名称与说明', OUTPUT_LENGTH_LIST.every(l => l.name && l.nameEn && l.desc && l.descEn))
  check('id 稳定（与后端 LENGTH_PROMPTS 对应）',
    OUTPUT_LENGTH_LIST.map(l => l.id).join(',') === 'short,medium,long',
    OUTPUT_LENGTH_LIST.map(l => l.id).join(','))
  // 文案应体现"已经拉长"，避免 UI 与实际注入不符
  check('短文说明已更新为 400-700', /400-700/.test(OUTPUT_LENGTH_LIST[0].desc), OUTPUT_LENGTH_LIST[0].desc)
  check('长文说明已更新为 1200-2000', /1200-2000/.test(OUTPUT_LENGTH_LIST[2].desc), OUTPUT_LENGTH_LIST[2].desc)
}

console.log(`\n结果: ${pass} 通过, ${fail} 失败\n`)
process.exit(fail ? 1 : 0)
