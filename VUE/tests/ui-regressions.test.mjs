/**
 * UI 回归测试（静态源码断言）
 *
 * 守住三处容易改回去的地方：
 *   1. 系统设置「头像」区：抽屉内容区只有 ~420px，两块并排必然挤变形 ——
 *      必须是「自动换行网格 + 最小宽度」，且头像图片要 object-fit: cover（不变形）
 *   2. 「图片生成」里不得再出现「它没有启用，但有配置就会优先用配置」这段文案
 *      （有配置就用配置是内部规则，摆在界面上只会让人以为出了问题）
 *   3. 卡片广场要与人物卡字段对齐：玩家设定 + 世界书都要有，且**都不是必填**
 */
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const src = join(here, '..', 'src')

let pass = 0, fail = 0
const ok = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`  ok   ${name}`) }
  else { fail++; console.log(`  FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}
const read = (rel) => readFileSync(join(src, rel), 'utf8')

console.log('\n[1] 系统设置：头像区不再被挤压')
{
  const vue = read('components/SystemSettings.vue')
  ok('头像行用网格自动换行（不是死板的两列 flex）',
    /\.avatar-section \.avatar-row\s*\{[^}]*display:\s*grid/.test(vue))
  ok('块有最小宽度，装不下就独占一行',
    /grid-template-columns:\s*repeat\(auto-fit,\s*minmax\(2\d\dpx/.test(vue))
  ok('块允许内容收缩（min-width: 0），不会把边框撑破',
    /\.avatar-block\s*\{[^}]*min-width:\s*0/.test(vue))
  ok('按钮容器可换行，不会溢出',
    /\.avatar-actions\s*\{[^}]*flex-wrap:\s*wrap/.test(vue))
  ok('el-upload 改成 inline-flex（否则按钮基线错位）',
    /\.avatar-actions :deep\(\.el-upload\)\s*\{[^}]*display:\s*inline-flex/.test(vue))
  ok('头像图片按 cover 裁切、正圆（长图也不会被拉变形）',
    /\.avatar-preview :deep\(img\)\s*\{[^}]*object-fit:\s*cover[^}]*border-radius:\s*50%/.test(vue))
  ok('窄屏媒体查询同步改成单列网格',
    /@media[\s\S]*?\.avatar-section \.avatar-row\s*\{\s*grid-template-columns:\s*1fr/.test(vue))
}

console.log('\n[2] 图片生成：去掉「没有启用」那段提示')
{
  const vue = read('components/ProviderPanel.vue')
  ok('不再出现「它没有启用，但有配置就会优先用配置」',
    !vue.includes('它没有启用，但有配置就会优先用配置'))
  ok('不再出现 is-warn 状态', !vue.includes('is-warn'))
  ok('没有文案时整行不渲染',
    /v-if="activeType === 'image' && imageUsage\.text"/.test(vue))
  ok('正常情况仍显示「生图使用配置「X」」', vue.includes('生图使用配置「${pick.name}」'))
  ok('无配置时提示走共享免费通道', vue.includes('未配置图片 API：生图将使用共享免费通道'))
}

console.log('\n[3] 卡片广场：与人物卡字段对齐（玩家设定 + 世界书，都可选）')
{
  const vue = read('components/PersonaMarketplace.vue')
  ok('存在世界书编辑器组件', existsSync(join(src, 'components', 'MarketplaceWorldbookEditor.vue')))
  ok('显式引入世界书编辑器',
    vue.includes("import MarketplaceWorldbookEditor from './MarketplaceWorldbookEditor.vue'"))
  ok('发布表单有玩家设定', /publishForm\.user_prompt/.test(vue))
  ok('发布表单有世界书', /publishForm\.worldbook/.test(vue))
  ok('编辑表单有玩家设定', /editForm\.user_prompt/.test(vue))
  ok('编辑表单有世界书', /editForm\.worldbook/.test(vue))
  // 「必填」在模板里是 el-form-item 的 required 属性：这两项绝不能带
  const requiredItems = [...vue.matchAll(/<el-form-item[^>]*required[^>]*>\s*<[^>]*(?:Player Setup|Worldbook)/g)]
  ok('玩家设定/世界书没有标成必填', requiredItems.length === 0,
    String(requiredItems.length))
  ok('两个表单都用同一个世界书编辑器',
    (vue.match(/<MarketplaceWorldbookEditor/g) || []).length === 2,
    String((vue.match(/<MarketplaceWorldbookEditor/g) || []).length))
  ok('提交前过滤空正文条目', vue.includes('function cleanWorldbook'))
  ok('详情里展示玩家设定与世界书',
    vue.includes('detailData.user_prompt') && vue.includes('detailData.worldbook'))
  ok('卡片列表显示世界书条数标记', vue.includes('item.worldbook_count > 0'))
  ok('编辑时深拷贝世界书（取消编辑不污染详情）',
    /worldbook:\s*\(d\.worldbook \|\| \[\]\)\.map\(/.test(vue))
}

console.log('\n[4] 世界书编辑器自身：条目可选、有上限')
{
  const wb = read('components/MarketplaceWorldbookEditor.vue')
  ok('最多 20 条（与后端一致）', wb.includes('MAX_ENTRIES = 20'))
  ok('支持常驻/按需切换', wb.includes('always_on'))
  ok('说明可不填', wb.includes('可不填'))
}

console.log(`\n结果: ${pass} 通过, ${fail} 失败`)
process.exit(fail ? 1 : 0)
