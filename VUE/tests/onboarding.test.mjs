/**
 * 新用户引导与免费模型提醒的回归测试
 *
 * 守住两条容易悄悄被改回去的产品规则：
 *   1. 没配置自己 API 的用户「每次进入都要被提醒一次」——
 *      因此提醒状态必须是内存态，绝不能写 sessionStorage/localStorage 被永久记住；
 *   2. 教程内容要与《新用户使用教程》一致：8 步、第 3 步区分电脑/手机端共 3 张图，
 *      且所有配图在仓库里真实存在（删图/改路径会在这里被抓住）。
 */
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const src = join(here, '..', 'src')

let passed = 0
let failed = 0
function ok(label, cond, extra = '') {
  if (cond) {
    passed++
    console.log(`  ok   ${label}`)
  } else {
    failed++
    console.log(`  FAIL ${label}${extra ? `  ${extra}` : ''}`)
  }
}

const home = readFileSync(join(src, 'views', 'Home.vue'), 'utf8')
const sidebar = readFileSync(join(src, 'components', 'Sidebar.vue'), 'utf8')
const dialog = readFileSync(join(src, 'components', 'FreeApiReminderDialog.vue'), 'utf8')
const stepsFile = readFileSync(join(src, 'utils', 'tutorialSteps.js'), 'utf8')
const tutorialDialog = readFileSync(join(src, 'components', 'NewUserTutorialDialog.vue'), 'utf8')

console.log('\n[1] 免费模型提醒：组件已接入')
ok('存在 FreeApiReminderDialog.vue', existsSync(join(src, 'components', 'FreeApiReminderDialog.vue')))
ok('Home.vue 导入并渲染了提醒弹窗',
  home.includes("import FreeApiReminderDialog from '../components/FreeApiReminderDialog.vue'")
  && home.includes('<FreeApiReminderDialog'))
ok('「去配置」直接打开模型配置面板', home.includes('@configure="providerPanelVisible = true"'))
ok('提醒只对未配置自有模型的用户显示',
  home.includes('chatStatus.value.is_free && !hasOwnChatProvider.value'))
ok('i18n 路径正确（../i18n，不是 ../utils/i18n）',
  dialog.includes("from '../i18n'") && !dialog.includes("from '../utils/i18n'"))

console.log('\n[2] 每次进入都要提醒（不能持久化「知道了」）')
ok('Home.vue 不再写 free_api_banner_dismissed',
  !home.includes('free_api_banner_dismissed'))
ok('Home.vue 不再读 sessionStorage 作为提醒开关',
  !/freeApiBannerDismissed\s*=\s*ref\(\s*sessionStorage/.test(home))
ok('提醒弹窗状态是内存 ref（不落存储）',
  /freeApiReminderVisible\s*=\s*ref\(false\)/.test(dialog) === false && /const freeApiReminderVisible = ref\(false\)/.test(home))
ok('进入时触发提醒（onMounted 与登录成功都调用）',
  (home.match(/maybeShowFreeApiReminder\(\)/g) || []).length >= 3)
ok('组件内不写 sessionStorage / localStorage',
  !/sessionStorage\.(set|get|remove)Item/.test(dialog) && !/localStorage\.(set|get|remove)Item/.test(dialog))

console.log('\n[3] 提醒文案要说清「免费模型限制多、很呆」')
const copy = dialog.replace(/\s+/g, '')
ok('提到频率/并发限制', copy.includes('频率') || copy.includes('排队'))
ok('提到能力弱 / 出戏 / 呆', copy.includes('能力较弱') || copy.includes('出戏') || copy.includes('比较呆'))
ok('给出解决方案（配置自己的 Key）', copy.includes('配置自己的APIKey') || copy.includes('自己的 API Key'))
ok('弹窗默认展开免费模型名称', dialog.includes('freeName ||'))

console.log('\n[4] 教程内容与文档一致')
const stepTitles = [...stepsFile.matchAll(/title:\s*'([^']+)'/g)].map(m => m[1])
ok('共 9 步', stepTitles.length === 9, `实际 ${stepTitles.length}`)
ok('第 1 步是配置 API', stepTitles[0].includes('API'))
ok('第 8 步讲生图与次数限制',
  stepTitles[7].includes('生图') && /未配置生图模型前有次数限制/.test(stepsFile), stepTitles[7])
ok('最后一步是反馈 / 更多玩法入口',
  /反馈|更多玩法/.test(stepTitles[stepTitles.length - 1]), stepTitles[stepTitles.length - 1])
ok('教程标题强调必须配置自己的 API',
  /首次使用请先配置自己的 API|一定要配置自己的 ?API/.test(tutorialDialog),
  (tutorialDialog.match(/tutorial-intro[\s\S]{0,120}/) || [''])[0].replace(/\s+/g, ' ').slice(0, 100))
const step3 = stepsFile.split("title: '创建并保存 Key'")[1]?.split('title:')[0] || ''
ok('第 3 步区分电脑端与手机端（3 张图）',
  step3.includes('电脑端获取方式') && step3.includes('手机端获取方式（一）') && step3.includes('手机端获取方式（二）'),
  step3.replace(/\s+/g, ' ').slice(0, 120))
ok('最后一步说明了反馈方式', /反馈/.test(stepsFile) && /管理员/.test(stepsFile))
ok('文案里没有真人姓名等隐私内容', !/廖祯斌/.test(stepsFile + tutorialDialog))

console.log('\n[5] 教程配图真实存在')
const assets = join(src, 'assets', 'tutorial')
for (const f of ['step1.png', 'step2.png', 'step3-pc.png', 'step3-phone1.png', 'step3-phone2.png',
  'step4.png', 'step5.png', 'step6.png', 'step7.png', 'step8.png', 'step9.png']) {
  ok(`assets/tutorial/${f}`, existsSync(join(assets, f)))
}
ok('教程弹窗支持一步多图', tutorialDialog.includes('v-for="(img, j) in step.images"'))
ok('预览大图带位置定位', tutorialDialog.includes('imageIndexOf(i, j)'))

console.log('\n[6] 侧边栏常驻入口')
ok('教程入口不再受 tutorialHint 控制', !sidebar.includes('v-if="tutorialHint"'))
ok('教程入口在「开启新对话」之上',
  sidebar.indexOf('sidebar-tutorial-banner') < sidebar.indexOf('new-chat-row'))
ok('免费提示条文案提到限制与出戏', sidebar.includes('免费模型限制多、回复容易出戏'))

console.log(`\n结果: ${passed} 通过, ${failed} 失败`)
process.exit(failed ? 1 : 0)
