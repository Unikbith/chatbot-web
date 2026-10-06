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

console.log('\n[5] 会话设置：「角色阵容」已下线，两个开关默认开启')
{
  const vue = read('components/ConversationSettings.vue')
  // 注释里会提到"角色阵容已下线"，所以只断言界面上不再有这个面板标题
  ok('不再有「角色阵容」面板',
    !vue.includes("t('角色阵容'") && !vue.includes("'Character Cast'"))
  ok('不再有单角色/多角色选择', !vue.includes('role_mode') && !vue.includes('ensemble'))
  ok('不再有阵容与回应焦点输入', !vue.includes('role_cast') && !vue.includes('role_focus_rule'))
  ok('不再提交 conversation_directives（只留一条说明性注释）',
    !/conversation_directives:\s*\{/.test(vue))
  ok('提示词兜底表单默认 true', /append_prompt_enabled:\s*true/.test(vue))
  ok('提示词兜底回填时 NULL 视为开启',
    /form\.append_prompt_enabled = conv\.append_prompt_enabled == null \? true/.test(vue))
  ok('提示词增强回填时默认开启', /function readPromptEnhance[\s\S]{0,200}?return true/.test(vue))
  ok('提示词增强表单默认 true', /prompt_enhance:\s*true/.test(vue))
  ok('文案改成「默认开启」而不是「生成失败后才开启」',
    vue.includes('默认开启') && !vue.includes('生成失败后才开启'))
}

console.log('\n[6] 后端：开关默认值与自动关闭逻辑')
{
  const models = readFileSync(join(here, '..', '..', 'Flask', 'models.py'), 'utf8')
  const chat = readFileSync(join(here, '..', '..', 'Flask', 'routes', 'chat.py'), 'utf8')
  const rich = readFileSync(join(here, '..', '..', 'Flask', 'rich_marker.py'), 'utf8')
  const pack = readFileSync(join(here, '..', '..', 'Flask', 'protocol_pack.py'), 'utf8')
  ok('模型默认 append_prompt_enabled=True',
    /append_prompt_enabled = db\.Column\(db\.Boolean, default=True/.test(models))
  ok('协议包：只有显式关闭才不注入（NULL 视为开启）',
    /getattr\(conv, 'append_prompt_enabled', None\) is False/.test(chat))
  ok('协议包：硬注入已移除（_get_system_prompt 不再拼兜底词）',
    !/_append_global_prompt\(body/.test(chat))
  ok('协议包：结构与内容协议都是常驻条目',
    /'source_key': 'protocol:structure'[\s\S]{0,200}?'always_on': True/.test(pack)
    && /'source_key': 'protocol:content'[\s\S]{0,200}?'always_on': True/.test(pack))
  ok('协议包：玩法扩展包是按需触发（不常驻）',
    /'kind': 'play',\s*\n\s*'always_on': False/.test(pack))
  ok('协议包含双男主与色情玩法包',
    pack.includes('protocol:play:multi') && pack.includes('protocol:play:sex'))
  ok('enhance 未设置时按开启处理',
    /enhance = opts\.get\('enhance'\) is not False/.test(rich))
  ok('不再有「聊满三轮自动关闭提示词兜底」', !chat.includes('提示词兜底已自动关闭'))
  ok('不再有「聊满两轮自动关闭丰富面板内容」', !chat.includes('已自动关闭，以减少后续 Token 消耗'))
  ok('多角色注入函数已移除',
    !chat.includes('_multi_character_block') && !chat.includes('【角色阵容】'))
}

console.log('\n[7] 协议包 UI：卡片里能看见、能恢复、排版分组')
{
  const panel = readFileSync(join(src, 'components', 'PersonaPanel.vue'), 'utf8')
  const api = readFileSync(join(src, 'utils', 'resAi.js'), 'utf8')
  const conv = readFileSync(join(src, 'components', 'ConversationSettings.vue'), 'utf8')
  ok('协议条目标记按 category 渲染', panel.includes("e.category === 'protocol'"))
  ok('协议条目有专属样式（左侧刻度 + 描边标记）',
    /\.wb-item\.is-protocol\s*\{/.test(panel) && /\.wb-tag\.is-proto\s*\{/.test(panel))
  ok('有「恢复默认协议包」按钮与确认框',
    panel.includes('restoreProtocolPack') && panel.includes("t('恢复默认协议包', 'Restore protocol pack')"))
  ok('恢复接口已定义且路径正确',
    /restoreProtocol\(personaId, sourceKeys = null\)[\s\S]{0,200}?restore-protocol/.test(api))
  ok('删除条目失败会提示（不再静默）',
    /personaApi\.removeWorldBook[\s\S]{0,300}?ElMessage\.error/.test(panel))
  ok('世界书表头有窄屏适配', /@media \(max-width: 768px\) \{[\s\S]{0,200}?\.wb-head/.test(panel))
  ok('缺失的 .form-hint 已补样式', /\.form-hint\s*\{/.test(panel))
  ok('对话设置里说明协议条目位置',
    conv.includes('协议条目在「人物卡 → 世界书」里') || conv.includes('Protocol entries live in Persona'))
  // 世界书排版：分组 + 默认收起 + 展开看全文
  ok('世界书按「协议包 / 我的设定条目」分组',
    panel.includes('wbGroups') && panel.includes("t('协议包', 'Protocol pack')")
    && panel.includes("t('我的设定条目', 'My lore entries')"))
  ok('条目默认收起，点击展开（不再是一屏文字墙）',
    /isWbExpanded/.test(panel) && /toggleWbExpand/.test(panel) && /v-if="isWbExpanded\(e\)"/.test(panel))
  ok('收起态显示摘要与字数', /function wbPreview/.test(panel) && /e\.content\.length/.test(panel))
  ok('触发词渲染为标签', /wbKeywordList/.test(panel) && /wb-kw-chip/.test(panel))
  ok('展开正文可滚动（长规范不撑爆面板）', /\.wb-content\s*\{[\s\S]{0,200}?max-height/.test(panel))
  ok('列表不再有 34vh 硬限制（改为分组滚动）', !/max-height: 34vh/.test(panel))
}

console.log('\n[8] 广场世界书编辑器：上限与键稳定性')
{
  const editor = readFileSync(join(src, 'components', 'MarketplaceWorldbookEditor.vue'), 'utf8')
  ok('达到上限时按钮禁用（不再静默无反应）',
    /:disabled="list\.length >= MAX_ENTRIES"/.test(editor))
  ok('达到上限有文字提示', editor.includes('已达上限'))
  ok('新增条目带稳定 uid（避免索引 key 串行）',
    /uid: `wb_/.test(editor) && /:key="entry\.uid \|\| i"/.test(editor))
  ok('广场卡片的 weight/enabled 往返不丢',
    readFileSync(join(src, 'components', 'PersonaMarketplace.vue'), 'utf8')
      .match(/weight: Number\(e\.weight\) \|\| 0/g)?.length >= 2)
  ok('打开发布对话框会重置草稿', /function openPublishDialog\(\)/.test(
    readFileSync(join(src, 'components', 'PersonaMarketplace.vue'), 'utf8')))
}

console.log('\n[9] 长期免登录：启动时用 refresh token 静默续期')
{
  const api = readFileSync(join(src, 'utils', 'resAi.js'), 'utf8')
  const home = readFileSync(join(src, 'views', 'Home.vue'), 'utf8')
  const store = readFileSync(join(src, 'utils', 'tokenStore.js'), 'utf8')
  ok('导出 ensureSession / hasStoredSession（且不重复导出）',
    /export async function ensureSession/.test(api) && /export function hasStoredSession/.test(api)
    && !/\n  ensureSession,/.test(api))
  ok('启动时：没有 access 但有 refresh 就静默续期',
    /if \(!token && tokenStore\.getRefresh\(\)\)[\s\S]{0,200}?await ensureSession\(\)/.test(home))
  ok('续期失败只按未登录处理，不清掉 refresh token（网络抖动不该踢人）',
    /catch \(e\) \{\s*\n\s*logger\.warn\('启动续期失败/.test(home))
  ok('只有服务端说 token 无效（401/403/422）才清 refresh',
    /status === 401 \|\| status === 403 \|\| status === 422/.test(api)
    && !/if \(status === 401\) \{\s*\n\s*\/\/[^\n]*\n\s*const hadToken[\s\S]{0,120}?tokenStore\.clear\(\)/.test(api))
  ok('access token 仍在 sessionStorage、refresh 在 localStorage（安全策略不变）',
    /safeSet\(sessionStorage, ACCESS_KEY, token\)/.test(store)
    && /return safeGet\(localStorage, REFRESH_KEY\)/.test(store))
  ok('接近过期（5 分钟内）也提前续期',
    /5 \* 60 \* 1000/.test(api))
}

console.log(`\n结果: ${pass} 通过, ${fail} 失败`)
process.exit(fail ? 1 : 0)
