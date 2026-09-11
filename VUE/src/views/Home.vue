<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import logger from '@/utils/logger';
import { ElMessage, ElMessageBox } from 'element-plus'
import { Menu, ZoomIn, ChatLineRound } from '@element-plus/icons-vue'
import {
  authApi, providersApi, personaApi, settingsApi, conversationApi, chatApi, marketplaceApi
} from '../utils/resAi'
import { applyTheme, bindSystemThemeListener } from '../utils/theme'
import { tokenStore } from '../utils/tokenStore'
import { t, setLocale } from '../i18n'

import Sidebar from '../components/Sidebar.vue'
import ChatArea from '../components/ChatArea.vue'
import AuthModal from '../components/AuthModal.vue'
import ProviderPanel from '../components/ProviderPanel.vue'
import SystemSettings from '../components/SystemSettings.vue'
import PersonaPanel from '../components/PersonaPanel.vue'
import ConversationSettings from '../components/ConversationSettings.vue'
import PersonaMarketplace from '../components/PersonaMarketplace.vue'
import ThumbIcon from '../components/ThumbIcon.vue'
import { identiconDataUrl } from '../utils/identicon'

import defaultUserAvatar from '../assets/images/avatar-user.jpg'
import defaultAiAvatar from '../assets/images/avatar-megumi.jpg'

const sidebarRef = ref(null)
const chatAreaRef = ref(null)
const personaPanelRef = ref(null)

// 用户状态
const user = ref(null)
const isLoggedIn = ref(false)

// 弹窗
const authModalVisible = ref(false)
const providerPanelVisible = ref(false)
const settingsVisible = ref(false)
// 系统设置打开时定位到的标签页（如从模型配置的帮助引导跳转到「帮助和反馈」）
const settingsInitialTab = ref('profile')
const personaPanelVisible = ref(false)
const convoSettingsVisible = ref(false)
const marketplaceVisible = ref(false)

// 对话状态
const currentConv = ref(null)
const currentConvId = ref(null)
const currentConvTitle = ref('新对话')
const currentProviderId = ref(null)
const systemPrompt = ref('')
const temperature = ref(0.8)

// 角色
const personas = ref([])
const currentPersona = ref(null)
const aiPersonas = computed(() => personas.value.filter(p => (p.persona_type || 'ai') === 'ai'))

// 对话模型配置列表（用于对话内选择模型、判定已启用配置）
const chatConfigs = ref([])

// 用户设置
const userSettings = reactive({
  theme: 'auto',
  language: 'auto',
  background_image: null,
  background_cover: 'contain',
  message_opacity: 0.9,
  sidebar_collapsed: false,
  temperature: 0.8,
  frequency_penalty: 0.0,
  presence_penalty: 0.0,
  top_p: 0.95,
})

// 聊天状态
const chatStatus = ref({ has_provider: false, is_free: false, free_name: '', provider_name: '' })

// 免费 API 提示条：每次浏览器会话只展示一次、可点“知道了”消除；已配置自有模型的用户不展示。
// 仅在侧边栏拉出（展开）时渲染在侧边栏内，移动端收起/桌面端折叠时不可见。
const freeApiBannerDismissed = ref(sessionStorage.getItem('free_api_banner_dismissed') === '1')
// 是否已配置自有对话模型（任一启用的 chat 配置都视为已配置）
const hasOwnChatProvider = computed(() =>
  chatConfigs.value.some(p => p.provider_type === 'chat' && p.enabled !== false)
)
const showFreeApiBanner = computed(() =>
  isLoggedIn.value && chatStatus.value.is_free && !hasOwnChatProvider.value && !freeApiBannerDismissed.value
)
function dismissFreeApiBanner() {
  freeApiBannerDismissed.value = true
  sessionStorage.setItem('free_api_banner_dismissed', '1')
}

// 对话列表
const conversations = ref([])
const convGroups = ref({ pinned: [], today: [], yesterday: [], week: [], month: [], older: [] })

// 侧边栏折叠
const sidebarCollapsed = computed(() => userSettings.sidebar_collapsed)

// 移动端适配：窄屏时侧边栏改为浮层
const isMobile = ref(false)
// 视口尺寸（背景智能适配需要按容器比例实时计算）
const viewportW = ref(typeof window !== 'undefined' ? window.innerWidth : 1280)
const viewportH = ref(typeof window !== 'undefined' ? window.innerHeight : 800)
let prevMobile = false
function updateViewport() {
  const mobile = window.innerWidth <= 768
  // 从桌面切换到移动端时，自动收起侧边栏，避免遮挡对话区
  if (mobile && !prevMobile && !userSettings.sidebar_collapsed) {
    userSettings.sidebar_collapsed = true
    settingsApi.update({ sidebar_collapsed: true }).catch(() => {})
  }
  prevMobile = mobile
  isMobile.value = mobile
  viewportW.value = window.innerWidth
  viewportH.value = window.innerHeight
}

// 默认头像回退
const effectiveUserAvatar = computed(() => currentConv.value?.user_avatar || user.value?.avatar || defaultUserAvatar)
// AI 头像优先级：对话独立 > 通用AI头像 > 角色头像 > 默认图
const effectiveAiAvatar = computed(() => {
  const c = currentConv.value
  return c?.ai_avatar || user.value?.ai_avatar || currentPersona.value?.avatar || defaultAiAvatar
})
// 对话独立：AI 回复自动播报
const autoPlayVoice = computed(() => !!currentConv.value?.auto_play_voice)

// 对话独立背景 > 通用背景
const effectiveBackground = computed(() => currentConv.value?.background_image || userSettings.background_image || null)

// 对话独立透明度 > 通用透明度
const effectiveOpacity = computed(() => {
  if (currentConv.value && currentConv.value.message_opacity != null && currentConv.value.message_opacity !== '') {
    return Number(currentConv.value.message_opacity)
  }
  return userSettings.message_opacity
})

// 展示方式由用户设置决定：contain=完整可见 / cover=铺满填充
const backgroundCover = computed(() =>
  currentConv.value?.background_cover || userSettings.background_cover || 'contain'
)

// 未登录首屏没有用户设置，用默认形象图兜底，保证一进网站就有氛围背景
const ambientBackground = computed(() => effectiveBackground.value || defaultAiAvatar)

// 全屏氛围底图：contain 完整可见 + 平铺铺满 + 重度模糊，作为整站背景；
// 聊天区上方的 .bg-layer 仍按用户设置原样显示（不模糊）
const ambientStyle = computed(() => {
  const url = ambientBackground.value
  if (!url) return {}
  return {
    backgroundImage: `url(${url})`,
    backgroundSize: 'cover',
    backgroundPosition: 'center',
    backgroundRepeat: 'no-repeat',
  }
})

// 首屏未登录引导层（一进网站展示的图示状态）
const guestHeroVisible = computed(() => !isLoggedIn.value)

// ========== 入口页（未登录）的卡片广场数据 ==========
// 公开接口，无需登录；保持与原 marketplaceApi 同构
async function fetchLandingCardsPublic(sort, page, keyword, gender, perPage = 60) {
  const params = new URLSearchParams()
  params.set('sort', sort)
  params.set('page', String(page))
  params.set('per_page', String(perPage))
  if (keyword) params.set('q', keyword)
  if (gender) params.set('gender', gender)
  const res = await fetch(`${import.meta.env.VITE_API_BASE_URL || ''}/api/marketplace/public?${params}`)
  if (!res.ok) return { items: [], total: 0 }
  const data = await res.json()
  return data.code === 200 ? data.data : { items: [], total: 0 }
}
async function fetchLandingDetailPublic(id) {
  const res = await fetch(`${import.meta.env.VITE_API_BASE_URL || ''}/api/marketplace/public/${id}`)
  if (!res.ok) return null
  const data = await res.json()
  return data.code === 200 ? data.data : null
}

// 入口页展示的卡片：固定 4 张，加权随机抽样（高赞+高评论数更易被抽中）
// 用 hot 排序拉一大份候选池，前端按权重抽样；命中不可预测 + 高热内容优先。
const LANDING_SHOW_COUNT = 4
const LANDING_POOL_SIZE = 60

const landingLoading = ref(false)
const landingCards = ref([])

function weightedRandomPick(pool, n) {
  // 权重公式 = 1 + likes + 2 * sqrt(comment_count)
  //   - +1 保证所有卡片都有最低被抽中的概率（避免冷启动被完全埋没）
  //   - likes 越多越易被抽中
  //   - 评论数多的卡片额外加权，强化「人气内容优先」
  const weighted = pool.map(c => {
    const w = 1 + (c.likes || 0) + 2 * Math.sqrt(c.comment_count || 0)
    return { card: c, weight: Math.max(w, 0.01) }
  })
  const result = []
  const used = new Set()
  for (let i = 0; i < n && weighted.length > used.size; i++) {
    const totalWeight = weighted.reduce((sum, w) => used.has(w.card.id) ? sum : sum + w.weight, 0)
    if (totalWeight <= 0) break
    let r = Math.random() * totalWeight
    let chosen = weighted[weighted.length - 1].card
    for (const w of weighted) {
      if (used.has(w.card.id)) continue
      r -= w.weight
      if (r <= 0) { chosen = w.card; break }
    }
    result.push(chosen)
    used.add(chosen.id)
  }
  return result
}

async function loadLandingCards() {
  landingLoading.value = true
  try {
    // 取一个较大的候选池（hot 排序），按权重随机抽 4 张
    const data = await fetchLandingCardsPublic('hot', 1, '', '', LANDING_POOL_SIZE)
    const pool = data.items || []
    landingCards.value = weightedRandomPick(pool, LANDING_SHOW_COUNT)
  } catch (e) {
    logger.warn('加载入口页卡片失败', e)
    landingCards.value = []
  } finally {
    landingLoading.value = false
  }
}

async function openLandingDetail(card) {
  landingCommentsPage.value = 1
  const [detail, commentsRes] = await Promise.all([
    fetchLandingDetailPublic(card.id),
    marketplaceApi.publicComments(card.id, 'hot', 1, LANDING_COMMENTS_PAGE_SIZE).catch(() => null),
  ])
  if (detail) {
    landingDetail.value = {
      ...detail,
      comments: commentsRes?.data?.items || [],
      comment_total: commentsRes?.data?.total || 0,
    }
    landingDetailVisible.value = true
  }
}

async function loadMoreLandingComments() {
  if (!landingDetail.value || !landingCommentsHasMore.value) return
  landingCommentsPage.value += 1
  try {
    const res = await marketplaceApi.publicComments(
      landingDetail.value.id,
      'hot',
      landingCommentsPage.value,
      LANDING_COMMENTS_PAGE_SIZE
    )
    if (res.code === 200) {
      landingDetail.value.comments.push(...(res.data.items || []))
      landingDetail.value.comment_total = res.data.total || landingDetail.value.comment_total
    }
  } catch (e) {
    logger.warn('加载更多评论失败', e)
  }
}

function openLandingPreview(url) {
  if (!url) return
  landingPreviewUrl.value = url
  landingPreviewVisible.value = true
}

// 千位 k 计数：1000 -> 1k，1500 -> 1.5k，10000 -> 10k，百万及以上用 m
function formatCount(n) {
  const v = Number(n) || 0
  if (v < 1000) return String(v)
  if (v < 1000000) {
    const k = v / 1000
    return (k >= 100 ? Math.round(k) : Math.round(k * 10) / 10) + 'k'
  }
  const m = v / 1000000
  return (m >= 100 ? Math.round(m) : Math.round(m * 10) / 10) + 'm'
}

// 入口页详情弹窗状态
const landingDetailVisible = ref(false)
const landingDetail = ref(null)
const landingPreviewVisible = ref(false)
const landingPreviewUrl = ref('')
// 入口页详情：人物提示词默认收起，避免长文一进来就占满整个右半区
const landingPromptExpanded = ref(false)
const landingCommentsPage = ref(1)
const LANDING_COMMENTS_PAGE_SIZE = 5
const landingCommentsHasMore = computed(() =>
  landingDetail.value && landingDetail.value.comments.length < landingDetail.value.comment_total
)
watch(landingDetailVisible, (val) => {
  if (val) landingPromptExpanded.value = false
})

// 从入口页选择卡片后登录：记录待采用的卡片 ID，登录后用它创建默认对话
const pendingLandingPersonaId = ref(null)
const savedPendingId = localStorage.getItem('pending_landing_persona_id')
if (savedPendingId) {
  pendingLandingPersonaId.value = Number(savedPendingId)
}

function onLandingLoginClick() {
  if (landingDetail.value?.id) {
    pendingLandingPersonaId.value = landingDetail.value.id
    localStorage.setItem('pending_landing_persona_id', String(landingDetail.value.id))
  }
  landingDetailVisible.value = false
  authModalVisible.value = true
}

function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  if (isNaN(d.getTime())) return ts
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function formatDate(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  if (isNaN(d.getTime())) return ts
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// ========== 初始化 ==========
let unbindSystemTheme = null

onMounted(async () => {
  unbindSystemTheme = bindSystemThemeListener(() => userSettings.theme)
  updateViewport()
  window.addEventListener('resize', updateViewport)

  const token = tokenStore.getAccess()
  if (token) {
    try {
      await loadUserInfo()
      await loadAllData()
      await ensureInitialConversation()
    } catch (e) {
      authModalVisible.value = true
    }
  } else {
    // 未登录：立刻拉一次入口页卡片，刷新即可看到最新内容
    loadLandingCards()
  }
  // 未登录时首屏不弹登录框：仅在用户进行需要登录的操作（发消息/新对话/角色/设置等）时才提示，避免一进来就打扰

  window.addEventListener('auth:expired', handleAuthExpired)
})

// 打开/关闭模型配置面板后刷新对话配置列表，保证对话内模型选择为最新
watch(providerPanelVisible, (val) => {
  if (!val) loadDefaultProvider()
})

onUnmounted(() => {
  window.removeEventListener('resize', updateViewport)
  window.removeEventListener('auth:expired', handleAuthExpired)
  if (unbindSystemTheme) unbindSystemTheme()
})

function handleAuthExpired() {
  ElMessage.warning(t('登录已过期，请重新登录', 'Session expired, please log in again'))
  authApi.logout()
  isLoggedIn.value = false
  user.value = null
  authModalVisible.value = true
}

// 需要登录的操作：未登录时直接弹登录框，避免请求 401 连环触发“登录已过期”toast
function requireLogin(action) {
  if (!isLoggedIn.value) {
    ElMessage.info(t('请先登录', 'Please log in first'))
    authModalVisible.value = true
    return
  }
  if (typeof action === 'function') action()
}

// ========== 用户数据加载 ==========
async function loadUserInfo() {
  const res = await authApi.userinfo()
  if (res.code === 200) {
    user.value = res.data
    isLoggedIn.value = true
    if (res.data.settings) {
      Object.assign(userSettings, res.data.settings)
      applyTheme(userSettings.theme)
      setLocale(userSettings.language)
    }
  }
}

async function loadAllData() {
  await Promise.all([
    loadConversations(),
    loadPersonas(),
    loadChatStatus(),
    loadDefaultProvider(),
  ])
}

async function loadConversations() {
  try {
    const res = await conversationApi.list()
    if (res.code === 200) {
      conversations.value = res.data.items || []
      convGroups.value = res.data.groups || convGroups.value
    }
  } catch (e) {
    logger.warn('加载对话失败', e)
  }
}

async function loadPersonas() {
  try {
    const res = await personaApi.list()
    if (res.code === 200) {
      personas.value = res.data
      if (!currentPersona.value) {
        // 注册时按性别生成的默认 AI 人物卡优先（is_default），避免误取到用户人设
        const list = res.data || []
        currentPersona.value =
          aiPersonas.value.find(p => p.is_default) ||
          list.find(p => p.is_default) ||
          aiPersonas.value[0] ||
          list[0] ||
          null
      }
    }
  } catch (e) {
    logger.warn('加载角色失败', e)
  }
}

async function loadChatStatus() {
  try {
    const res = await chatApi.status()
    if (res.code === 200) {
      chatStatus.value = res.data
    }
  } catch (e) {
    logger.warn('加载聊天状态失败', e)
  }
}

async function loadDefaultProvider() {
  try {
    const res = await providersApi.list('chat')
    chatConfigs.value = (res.data || []).filter(p => p.provider_type === 'chat')
    if (res.code === 200 && res.data?.length > 0) {
      const savedId = providersApi.getCurrentId('chat')
      let provider = res.data.find(p => p.id == savedId)
      if (!provider) provider = res.data.find(p => p.is_default) || res.data[0]
      currentProviderId.value = provider.id
      providersApi.setCurrentId(provider.id, 'chat')
    }
  } catch (e) {
    logger.warn('加载提供商失败', e)
  }
}

// 取「应使用的默认对话配置」ID：本地保存的已启用配置 > 首个已启用配置 > null
function pickEnabledChatProviderId() {
  const list = chatConfigs.value
  if (!list.length) return null
  const enabled = list.filter(p => p.enabled !== false)
  if (!enabled.length) return null
  const saved = enabled.find(p => p.id == providersApi.getCurrentId('chat'))
  return saved ? saved.id : enabled[0].id
}

// 根据对话 id 找到对应 persona（无则使用通用默认）
function personaOf(conv) {
  if (!conv || !conv.persona_id) {
    const def = personas.value.find(p => p.is_default) || personas.value[0] || null
    return def
  }
  return personas.value.find(p => p.id == conv.persona_id) || personas.value.find(p => p.is_default) || null
}

// ========== 对话操作 ==========
// 登录后确保存在一个可用对话：有对话则选中最近一条；无对话则自动新建首条，保证对话设置立即可用
async function ensureInitialConversation() {
  if (!chatAreaRef.value) return
  if (conversations.value.length > 0) {
    await handleSelectConversation(conversations.value[0].id)
    return
  }
  await handleNewChat()
}

async function handleNewChat() {
  // 默认人物卡来自注册时选择的性别（后端按性别把对应人物卡标记为 is_default）
  const personaId = (
    aiPersonas.value.find(p => p.is_default) ||
    personas.value.find(p => p.is_default) ||
    aiPersonas.value[0] ||
    personas.value[0] ||
    currentPersona.value
  )?.id || null
  await _doCreateConversation(personaId)
}

async function createConversationWithPersona(personaId) {
  if (!personaId) {
    await ensureInitialConversation()
    return
  }
  await _doCreateConversation(personaId)
}

async function _doCreateConversation(personaId, forceDelete = false) {
  currentProviderId.value = pickEnabledChatProviderId()
  const payload = {
    title: t('新对话', 'New Chat'),
    provider_id: currentProviderId.value,
    persona_id: personaId,
    system_prompt: systemPrompt.value,
    temperature: userSettings.temperature,
  }
  if (forceDelete) payload.force_delete = true

  try {
    const res = await conversationApi.create(payload)

    if (res.code === 409 && !forceDelete) {
      try {
        await ElMessageBox.confirm(
          res.message || t('已达对话保存上限（10 个），继续将删除最早创建的对话', 'Conversation limit reached (10). Continue to delete the oldest one.'),
          t('已达保存的上限', 'Conversation Limit'),
          { confirmButtonText: t('继续', 'Continue'), cancelButtonText: t('取消', 'Cancel'), type: 'warning' }
        )
        await _doCreateConversation(personaId, true)
      } catch (e) { /* cancelled */ }
      return
    }

    if (res.code === 200) {
      currentConv.value = res.data
      currentConvId.value = res.data.id
      currentConvTitle.value = res.data.title || '新对话'
      currentPersona.value = personaOf(res.data)
      systemPrompt.value = res.data.system_prompt || ''
      currentProviderId.value = res.data.provider_id || pickEnabledChatProviderId()
      chatAreaRef.value?.resetMessages()
      loadConversations()
    }
  } catch (e) {
    ElMessage.error(t('创建对话失败', 'Failed to create conversation'))
  }
}

async function handleSelectConversation(convId) {
  if (!convId || convId === currentConvId.value) return
  try {
    const res = await conversationApi.get(convId)
    if (res.code === 200) {
      const data = res.data
      currentConv.value = data
      currentConvId.value = convId
      currentConvTitle.value = data.title || '新对话'
      systemPrompt.value = data.system_prompt || ''
      currentPersona.value = personaOf(data)
      // 对话独立模型配置优先；未指定则回退到已启用的默认配置
      currentProviderId.value = data.provider_id || pickEnabledChatProviderId()

      const msgList = data.messages || []
      chatAreaRef.value?.setMessages(msgList)
    }
  } catch (e) {
    ElMessage.error(t('加载对话失败', 'Failed to load conversation'))
  }
}

async function handleTogglePin(convId) {
  try {
    await conversationApi.togglePin(convId)
    loadConversations()
  } catch (e) {
    ElMessage.error(t('操作失败', 'Operation failed'))
  }
}

async function handleDeleteConversation(convId) {
  try {
    const res = await conversationApi.remove(convId)
    if (currentConvId.value == convId) {
      currentConv.value = null
      currentConvId.value = null
      currentConvTitle.value = '新对话'
      currentPersona.value = personas.value.find(p => p.is_default) || personas.value[0] || null
      chatAreaRef.value?.resetMessages()
    }
    await loadConversations()
    ElMessage.success(t('已删除', 'Deleted'))
    // 删除的是当前对话时，自动选中最近一条或新建首条，保持始终有可用对话
    if (!currentConvId.value) await ensureInitialConversation()
  } catch (e) {
    ElMessage.error(t('删除失败', 'Delete failed'))
  }
}

function handleTitleChange(newTitle) {
  currentConvTitle.value = newTitle
  if (currentConv.value) {
    currentConv.value.title = newTitle
  }
  if (currentConvId.value) {
    conversationApi.update(currentConvId.value, { title: newTitle }).then(() => {
      loadConversations()
    }).catch(() => {})
  }
}

// 首次发送消息时前端自动创建会话（ChatArea 触发），同步到侧边栏
function handleConversationCreated(conv) {
  if (!conv || !conv.id) return
  if (!currentConvId.value) {
    currentConv.value = conv
    currentConvId.value = conv.id
    currentConvTitle.value = conv.title || '新对话'
    currentPersona.value = personaOf(conv)
    systemPrompt.value = conv.system_prompt || ''
    currentProviderId.value = conv.provider_id || pickEnabledChatProviderId()
  }
  loadConversations()
}

// ========== 侧边栏 ==========
function toggleSidebar() {
  userSettings.sidebar_collapsed = !userSettings.sidebar_collapsed
  settingsApi.update({ sidebar_collapsed: userSettings.sidebar_collapsed }).catch(() => {})
}

// ========== 登录/登出 ==========
async function handleLoginSuccess(userData) {
  user.value = userData
  isLoggedIn.value = true
  authModalVisible.value = false
  // 清空旧人设，让 loadPersonas 按新登录用户的性别重新挑默认人物卡
  currentPersona.value = null
  await loadAllData()

  // 若用户从入口页选择某张卡片后登录，优先以该卡片作为默认对话对象
  const pendingId = pendingLandingPersonaId.value
  if (pendingId) {
    pendingLandingPersonaId.value = null
    localStorage.removeItem('pending_landing_persona_id')
    try {
      const res = await marketplaceApi.adopt(pendingId)
      if (res.code === 200) {
        const templateId = res.data?.template_id || res.data?.id
        // 刷新人物卡列表，让新采用的人物卡出现在侧边栏
        await loadPersonas()
        if (templateId) {
          await createConversationWithPersona(templateId)
          return
        }
      }
    } catch (e) {
      logger.warn('采用入口页卡片失败', e)
    }
  }

  await ensureInitialConversation()
}

function handleLogout() {
  authApi.logout()
  isLoggedIn.value = false
  user.value = null
  currentConv.value = null
  currentConvId.value = null
  currentConvTitle.value = '新对话'
  currentPersona.value = null
  conversations.value = []
  convGroups.value = { pinned: [], today: [], yesterday: [], week: [], month: [], older: [] }
  chatAreaRef.value?.resetMessages()
  // 退出登录后页面刷新重定向到入口页（路由 / 即入口页）：
  // 使用 reload 让 Vue 完全重新挂载，避免旧对话/旧状态闪一下；同时保证内存中的
  // 用户态、对话态彻底清空，避免下一次直接复用旧组件导致脏读。
  authModalVisible.value = false
  setTimeout(() => { window.location.reload() }, 50)
}

// ========== 设置更新 ==========
function handleSettingsUpdated(settings) {
  Object.assign(userSettings, settings)
  applyTheme(userSettings.theme)
}

function handleUserUpdated(userData) {
  user.value = userData
  if (authApi.setUser) {
    try { localStorage.setItem('chatbot_user', JSON.stringify(userData)) } catch (e) {}
  }
}

// ========== 角色变更 ==========
// 人物卡列表版本号：任何增删改都会自增，用于通知卡片广场刷新「已添加」状态
const personaVersion = ref(0)

function handlePersonaChanged(persona) {
  // 对话中的独立人设只能通过「对话设置」修改：
  // 这里不改写当前对话的 persona_id，只刷新列表与内存中的当前人物卡（同步头像/开场白）
  if (persona) {
    if (!currentPersona.value || currentPersona.value.id === persona.id) {
      currentPersona.value = persona
    }
  }
  personaVersion.value++
  loadPersonas()
}

// 侧边栏人物卡点击：打开人物卡管理并弹出编辑，不再直接切换对话人设
function handleSidebarEditPersona(persona) {
  personaPanelRef.value?.openEdit(persona)
}

// 从卡片广场添加人物卡后：刷新侧边栏人物卡列表 + 同步卡片广场状态
function handleCardAdopted() {
  personaVersion.value++
  loadPersonas()
}

// 人物卡删除后同步侧边栏与当前对话人设
function handlePersonaDeleted(personaId) {
  personas.value = personas.value.filter(p => p.id !== personaId)
  // 删除后立刻同步卡片广场的「已添加 / 添加」状态
  personaVersion.value++
  if (currentPersona.value && currentPersona.value.id === personaId) {
    const defaultPersona = personas.value.find(p => p.is_default) || personas.value[0] || null
    currentPersona.value = defaultPersona
    if (currentConvId.value && defaultPersona) {
      conversationApi.update(currentConvId.value, { persona_id: defaultPersona.id }).catch(() => {})
    } else if (currentConvId.value) {
      conversationApi.update(currentConvId.value, { persona_id: null }).catch(() => {})
    }
  }
}

// ========== 提供商变更 ==========
function handleProviderSelect({ provider, type }) {
  if (type === 'chat') {
    currentProviderId.value = provider.id
    providersApi.setCurrentId(provider.id, 'chat')
    ElMessage.success(t('已切换到', 'Switched to') + `「${provider.name}」`)
    loadChatStatus()
  }
}

// 从模型配置的帮助引导跳到「设置 - 帮助和反馈」
function openSettingsHelp() {
  settingsInitialTab.value = 'feedback'
  providerPanelVisible.value = false
  settingsVisible.value = true
}

// ========== 对话独立设置 ==========
function openConversationSettings() {
  // 对话设置需登录（未登录点到时直接弹登录框）
  requireLogin(() => { convoSettingsVisible.value = true })
}
async function handleConvoSettingsSaved(payload) {
  if (!currentConvId.value) {
    ElMessage.warning(t('请先创建或选择一个对话', 'Create or select a conversation first'))
    return
  }
  try {
    const update = {
      provider_id: payload.provider_id,
      model_id: payload.model_id,
      persona_id: payload.persona_id,
      ai_avatar: payload.ai_avatar,
      user_avatar: payload.user_avatar,
      background_image: payload.background_image,
      background_cover: payload.background_cover,
      message_opacity: payload.message_opacity,
      temperature: payload.temperature,
      frequency_penalty: payload.frequency_penalty,
      presence_penalty: payload.presence_penalty,
      auto_play_voice: payload.auto_play_voice,
    }
    const res = await conversationApi.update(currentConvId.value, update)
    if (res.code === 200) {
      const prevMessages = currentConv.value?.messages || []
      currentConv.value = { ...res.data, messages: prevMessages }
      systemPrompt.value = res.data.system_prompt || ''
      // 更新当前对话使用的模型配置
      currentProviderId.value = payload.provider_id != null
        ? payload.provider_id
        : pickEnabledChatProviderId()
      if (payload.persona_id) {
        currentPersona.value = personas.value.find(p => p.id == payload.persona_id) || currentPersona.value
      }
      loadConversations()
      ElMessage.success(t('已保存', 'Saved'))
    }
  } catch (e) {
    ElMessage.error(t('保存失败', 'Save failed'))
  }
}
</script>

<template>
  <div
    class="home-container"
    :style="isLoggedIn ? { '--sidebar-width': sidebarCollapsed ? (isMobile ? '0px' : '60px') : (isMobile ? '0px' : '280px') } : { '--sidebar-width': '0px' }"
  >
    <!-- 全屏氛围底图：contain 平铺 + 模糊覆盖整个页面 -->
    <div class="bg-ambient" :style="ambientStyle"></div>

    <!-- 侧边栏（仅登录后展示；入口页隐藏） -->
    <template v-if="isLoggedIn">
    <!-- 移动端：收起时显示的菜单按钮 -->
    <button v-if="isMobile && sidebarCollapsed" class="mobile-menu-btn" @click="toggleSidebar">
      <el-icon><Menu /></el-icon>
    </button>
    <!-- 移动端：侧边栏展开时的遮罩 -->
    <div v-if="isMobile && !sidebarCollapsed" class="sidebar-backdrop" @click="toggleSidebar"></div>
    <Sidebar
      ref="sidebarRef"
      class="sidebar-wrap"
      :conversations="conversations"
      :groups="convGroups"
      :current-conv-id="currentConvId"
      :user="user"
      :user-avatar="effectiveUserAvatar"
      :collapsed="sidebarCollapsed"
      :current-persona="currentPersona"
      :free-api-banner="showFreeApiBanner"
      :free-api-name="chatStatus.free_name"
      :ai-personas="aiPersonas"
      @dismiss-free-api="dismissFreeApiBanner"
      @create="requireLogin(handleNewChat)"
      @select="handleSelectConversation"
      @toggle-pin="handleTogglePin"
      @delete="handleDeleteConversation"
      @toggle-collapse="toggleSidebar"
      @open-provider="requireLogin(() => providerPanelVisible = true)"
      @open-settings="requireLogin(() => settingsVisible = true)"
      @open-persona="requireLogin(() => personaPanelVisible = true)"
      @open-marketplace="requireLogin(() => marketplaceVisible = true)"
      @edit-persona="handleSidebarEditPersona"
      @login="authModalVisible = true"
      @logout="handleLogout"
    />
    </template>

    <!-- 首屏未登录态：图示欢迎层 -->
    <div v-if="guestHeroVisible" class="landing-page">
      <!-- 顶部导航 -->
      <header class="lp-header">
        <div class="lp-brand">
          <img :src="defaultAiAvatar" class="lp-brand-icon" alt="Confide" />
          <span class="lp-brand-text">Confide<span class="lp-divider">·</span>心语</span>
        </div>
        <div class="lp-header-right">
          <el-button class="lp-pill-btn" round @click="authModalVisible = true">
            {{ t('登录 / 注册', 'Sign in / Sign up') }}
          </el-button>
        </div>
      </header>

      <!-- 主体 -->
      <main class="lp-main">
        <!-- Hero 区：标题 + 登录引导（入口页极简：去掉搜索/筛选/排序，4 张卡片才是主舞台） -->
        <section class="lp-hero">
          <div class="lp-tagline">
            <span class="lp-dot">◆</span>
            <span>{{ t('心语 v1.0 · 多人设 AI 角色陪伴 · 多种对话风格 · 对话永久保存', 'Confide · many personas · endless conversations · saved forever') }}</span>
          </div>
          <h1 class="lp-title">{{ t('与心语，开始你的对话', 'Start a conversation with Confide') }}</h1>
          <p class="lp-sub">{{ t('选择一张人物卡，开启属于你的私人对话。', 'Pick a persona card and start a private chat of your own.') }}</p>
        </section>

        <!-- 卡片广场：固定展示 4 张人气卡片 + 首位 CTA 登录卡 -->
        <section class="lp-market">
          <div v-loading="landingLoading" class="lp-grid lp-grid-fixed">
            <!-- 登录引导卡（始终首位；点击进入登录） -->
            <div class="lp-card lp-card-cta" @click="authModalVisible = true">
              <div class="lp-cta-avatar">
                <img :src="defaultAiAvatar" :alt="t('心语', 'Confide')" />
              </div>
              <h3 class="lp-cta-title">Confide · 心语</h3>
              <p class="lp-cta-sub">{{ t('选择一个人物卡，开启一段只属于你的对话', 'Pick a persona and start a chat of your own') }}</p>
              <el-button type="primary" round class="lp-cta-btn">
                {{ t('登录 / 注册', 'Sign in / Sign up') }}
              </el-button>
              <div class="lp-cta-tips">
                <span>{{ t('多种人物卡', 'Many personas') }}</span>
                <i>·</i>
                <span>{{ t('自定义背景', 'Custom background') }}</span>
                <i>·</i>
                <span>{{ t('对话永久保存', 'Chats saved') }}</span>
              </div>
            </div>

            <!-- 卡片列表：固定 4 张加权随机卡片 -->
            <div
              v-for="card in landingCards"
              :key="card.id"
              class="lp-card"
              @click="openLandingDetail(card)"
            >
              <div class="lp-card-image">
                <img v-if="card.avatar" :src="card.avatar" :alt="card.name" loading="lazy" decoding="async" />
                <div v-else class="lp-card-placeholder">{{ card.name?.charAt(0) }}</div>
              </div>
              <div class="lp-card-body">
                <div class="lp-card-name">{{ card.name }}</div>
                <p class="lp-card-desc">{{ card.description }}</p>
                <div class="lp-card-meta">
                  <!-- 入口页只展示点赞数 + 评论数，k 单位（1k = 1000，10k = 10000） -->
                  <span class="lp-card-stat" :title="t('点赞数', 'Likes')">
                    <ThumbIcon :size="13" /> {{ formatCount(card.likes) }}
                  </span>
                  <span class="lp-card-stat" :title="t('评论数', 'Comments')">
                    <el-icon><ChatLineRound /></el-icon> {{ formatCount(card.comment_count || 0) }}
                  </span>
                </div>
              </div>
            </div>

            <div v-if="!landingLoading && landingCards.length === 0" class="lp-empty">
              {{ t('暂无卡片', 'No cards yet') }}
            </div>
          </div>
        </section>
      </main>

      <!-- 底部声明 -->
      <footer class="lp-footer">
        <span>© {{ new Date().getFullYear() }} Confide · 心语</span>
        <span class="lp-footer-sep">·</span>
        <span>{{ t('每一个人物卡，都是一颗等你的心', 'Every persona is a heart waiting for you') }}</span>
      </footer>
    </div>

    <!-- 卡片详情弹窗（在未登录入口页使用） -->
    <el-dialog
      v-model="landingDetailVisible"
      width="min(720px, 96vw)"
      align-center
      destroy-on-close
      class="lp-detail-dialog"
    >
      <template #header><span></span></template>
      <div v-if="landingDetail" class="lp-detail">
        <div class="lp-detail-left">
          <div
            class="lp-detail-avatar-box"
            @click="openLandingPreview(landingDetail.avatar)"
            :class="{ 'is-clickable': !!landingDetail.avatar }"
          >
            <img v-if="landingDetail.avatar" :src="landingDetail.avatar" :alt="landingDetail.name" />
            <div v-else class="lp-detail-placeholder">{{ landingDetail.name?.charAt(0) }}</div>
            <div v-if="landingDetail.avatar" class="lp-detail-zoom"><el-icon><ZoomIn /></el-icon></div>
          </div>

          <!-- 图片下方：点赞 / 评论 / 创作者（与卡片广场一致的统计展示） -->
          <div class="lp-detail-stats">
            <div class="lp-detail-stat like">
              <ThumbIcon :size="16" />
              <span class="lp-detail-stat-num">{{ formatCount(landingDetail.likes || 0) }}</span>
              <span class="lp-detail-stat-label">{{ t('点赞', 'Likes') }}</span>
            </div>
            <div class="lp-detail-stat comment">
              <el-icon :size="15"><ChatLineRound /></el-icon>
              <span class="lp-detail-stat-num">{{ formatCount(landingDetail.comment_total || landingDetail.comment_count || 0) }}</span>
              <span class="lp-detail-stat-label">{{ t('评论', 'Comments') }}</span>
            </div>
          </div>

          <div class="lp-detail-creator-card">
            <img
              v-if="landingDetail.creator_identicon_seed"
              :src="identiconDataUrl(landingDetail.creator_identicon_seed, 34)"
              class="lp-detail-creator-avatar"
              alt=""
            />
            <div class="lp-detail-creator-info">
              <span class="lp-detail-creator-label">{{ t('创作者', 'Creator') }}</span>
              <span class="lp-detail-creator-name">{{ landingDetail.creator_pseudonym || t('匿名', 'Anonymous') }}</span>
            </div>
          </div>
        </div>
        <div class="lp-detail-right">
          <h2 class="lp-detail-name">{{ landingDetail.name }}</h2>
          <div class="lp-detail-meta">
            <span>{{ t('创建时间', 'Created') }}: {{ formatDate(landingDetail.created_at) }}</span>
            <span class="lp-detail-meta-stats">
              <ThumbIcon :size="13" /> {{ formatCount(landingDetail.likes || 0) }}
              <el-icon :size="13"><ChatLineRound /></el-icon> {{ formatCount(landingDetail.comment_total || landingDetail.comment_count || 0) }}
            </span>
          </div>
          <p class="lp-detail-desc">{{ landingDetail.description }}</p>
          <div class="lp-detail-section" v-if="landingDetail.greeting">
            <div class="lp-detail-label">{{ t('开场白', 'Greeting') }}</div>
            <div class="lp-detail-box lp-greeting-box">{{ landingDetail.greeting }}</div>
          </div>
          <div class="lp-detail-section">
            <div class="lp-detail-label lp-detail-label-row">
              <span>{{ t('人设提示词', 'Character Prompt') }}</span>
              <button
                type="button"
                class="lp-detail-toggle"
                @click="landingPromptExpanded = !landingPromptExpanded"
              >
                {{ landingPromptExpanded
                    ? t('收起', 'Collapse')
                    : t('展开全文', 'Expand all') }}
              </button>
            </div>
            <div
              class="lp-detail-box"
              :class="{ 'lp-prompt-collapsed': !landingPromptExpanded }"
              @click="!landingPromptExpanded && (landingPromptExpanded = true)"
            >
              {{ landingDetail.system_prompt }}
            </div>
          </div>

          <!-- 评论区：未登录只读，展示假名 -->
          <div class="lp-detail-section lp-comments-section">
            <div class="lp-detail-label">{{ t('评论', 'Comments') }} ({{ landingDetail.comment_total || 0 }})</div>
            <div v-if="!(landingDetail.comments || []).length" class="lp-no-comments">{{ t('暂无评论', 'No comments yet') }}</div>
            <div v-else class="lp-comments-list">
              <div v-for="c in landingDetail.comments" :key="c.id" class="lp-comment">
                <div class="lp-comment-head">
                  <img :src="identiconDataUrl(c.identicon_seed, 24)" class="lp-comment-avatar" alt="" />
                  <span class="lp-comment-pseudonym">{{ c.pseudonym }}</span>
                  <span class="lp-comment-time">{{ formatTime(c.created_at) }}</span>
                </div>
                <p class="lp-comment-text">{{ c.content }}</p>
              </div>
            </div>
            <div v-if="landingCommentsHasMore" class="lp-comments-load-more">
              <button type="button" @click="loadMoreLandingComments">
                {{ t('加载更多评论', 'Load more comments') }}
              </button>
            </div>
          </div>

          <div class="lp-detail-bottom">
            <el-button type="primary" size="large" round class="lp-detail-btn" @click="onLandingLoginClick">
              {{ t('登录后开始对话', 'Sign in to chat') }}
            </el-button>
          </div>
        </div>
      </div>
    </el-dialog>

    <!-- 大图预览（与详情页头像共用） -->
    <el-image-viewer
      v-if="landingPreviewVisible && landingPreviewUrl"
      :url-list="[landingPreviewUrl]"
      :zoom-rate="1.2"
      hide-on-click-modal
      @close="landingPreviewVisible = false"
    />

    <!-- 聊天主区域（仅登录后展示） -->
    <ChatArea
      v-if="isLoggedIn"
      ref="chatAreaRef"
      class="chat-wrap"
      :conversation-id="currentConvId"
      :conversation-title="currentConvTitle"
      :provider-id="currentProviderId"
      :system-prompt="systemPrompt"
      :temperature="userSettings.temperature"
      :settings="userSettings"
      :user="user"
      :user-avatar="effectiveUserAvatar"
      :ai-avatar="effectiveAiAvatar"
      :message-opacity="effectiveOpacity"
      :auto-play-voice="autoPlayVoice"
      :is-free-api="chatStatus.is_free"
      :logged-in="isLoggedIn"
      :persona-greeting="currentPersona?.greeting || ''"
      :background-image="effectiveBackground"
      :background-cover="backgroundCover"
      @open-settings="requireLogin(() => settingsVisible = true)"
      @open-provider="requireLogin(() => providerPanelVisible = true)"
      @open-conversation-settings="openConversationSettings"
      @require-login="requireLogin"
      @title-change="handleTitleChange"
      @new-chat="handleNewChat"
      @conversation-created="handleConversationCreated"
    />

    <!-- 登录注册弹窗 -->
    <AuthModal v-model="authModalVisible" @success="handleLoginSuccess" />

    <!-- 模型提供商配置面板 -->
    <ProviderPanel
      v-model="providerPanelVisible"
      :current-provider-id="currentProviderId"
      @select="handleProviderSelect"
      @open-settings-help="openSettingsHelp"
    />

    <!-- 系统设置面板 -->
    <SystemSettings
      v-model="settingsVisible"
      :user="user"
      :initial-tab="settingsInitialTab"
      @settings-updated="handleSettingsUpdated"
      @user-updated="handleUserUpdated"
      @logout="handleLogout"
    />

    <!-- 人物卡管理面板 -->
    <PersonaPanel
      ref="personaPanelRef"
      v-model="personaPanelVisible"
      :selected-id="currentPersona?.id"
      @persona-changed="handlePersonaChanged"
      @persona-deleted="handlePersonaDeleted"
    />

    <!-- 对话独立设置 -->
    <ConversationSettings
      v-model="convoSettingsVisible"
      :conversation="currentConv"
      :ai-personas="aiPersonas"
      :configs="chatConfigs"
      :user-avatar="effectiveUserAvatar"
      :general-opacity="userSettings.message_opacity"
      :general-temperature="userSettings.temperature"
      :general-frequency-penalty="userSettings.frequency_penalty"
      :general-presence-penalty="userSettings.presence_penalty"
      @save="handleConvoSettingsSaved"
    />

    <!-- 卡片广场 -->
    <PersonaMarketplace
      v-model="marketplaceVisible"
      :current-user-id="user?.id"
      :persona-version="personaVersion"
      @adopted="handleCardAdopted"
    />
  </div>
</template>

<style scoped>
.home-container {
  display: flex;
  width: 100%;
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
  background: var(--app-bg);
  position: relative;
}

/* 全屏氛围底图：cover 铺满 + 重度模糊，作为整站背景 */
.bg-ambient {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  /* contain 平铺保证原图完整不被裁切，放大后模糊消除平铺接缝并覆盖整屏 */
  transform: scale(1.6);
  filter: blur(28px) saturate(1.15);
  opacity: 0.35;
  background-color: var(--app-bg);
}

.bg-ambient::after {
  content: '';
  position: absolute;
  inset: 0;
  background: var(--app-bg);
  opacity: 0.55;
}

/* ======================================================
 * DeepSeek 风格入口页（未登录态）
 *  - 顶部品牌区
 *  - 中央 hero：标语 + 标题 + 副标题 + 搜索 + 模式胶囊
 *  - 下方市场区：网格排布卡片，首位为「Confide · 心语」登录引导卡
 *  - 全屏氛围底图复用 .bg-ambient
 * ====================================================== */

.landing-page {
  position: absolute;
  inset: 0 0 0 var(--sidebar-width, 0);
  z-index: 2;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  color: #2a3a55;
  background:
    radial-gradient(circle at 50% 14%, rgba(220, 232, 250, 0.55), transparent 55%),
    radial-gradient(circle at 80% 18%, rgba(228, 240, 255, 0.45), transparent 50%),
    radial-gradient(circle at 20% 18%, rgba(238, 232, 252, 0.4), transparent 55%),
    linear-gradient(180deg, #f4f8ff 0%, #eef3fc 100%);
}

.lp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 28px;
  flex-shrink: 0;
}

.lp-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 700;
  font-size: 18px;
  letter-spacing: 0.4px;
  color: #2c3e6e;
}

.lp-brand-icon {
  width: 32px;
  height: 32px;
  border-radius: 9px;
  object-fit: cover;
  box-shadow: 0 4px 12px rgba(60, 100, 180, 0.18);
}

.lp-divider {
  margin: 0 6px;
  opacity: 0.45;
  font-weight: 400;
}

.lp-pill-btn {
  border-radius: 999px !important;
  padding: 8px 20px !important;
  font-weight: 500;
}

.lp-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 36px;
  padding: 8px 24px 24px;
}

.lp-hero {
  text-align: center;
  padding: 24px 16px 8px;
}

.lp-tagline {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.65);
  border: 1px solid rgba(120, 145, 195, 0.25);
  color: #5e7baf;
  font-size: 12px;
  margin-bottom: 22px;
  backdrop-filter: blur(6px);
}

.lp-dot {
  color: #6e8fdf;
  font-size: 10px;
}

.lp-title {
  margin: 0;
  font-size: 42px;
  font-weight: 700;
  letter-spacing: 0.02em;
  background: linear-gradient(135deg, #2c3e6e 0%, #5e7baf 60%, #6e8fdf 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.lp-sub {
  margin: 12px 0 22px;
  color: #6e7fa3;
  font-size: 15px;
}

.lp-searchbar {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 12px;
  max-width: 720px;
  margin: 0 auto;
  flex-wrap: wrap;
}

.lp-search-input {
  flex: 1;
  min-width: 280px;
  max-width: 520px;
}

.lp-search-input :deep(.el-input__wrapper) {
  background: rgba(255, 255, 255, 0.78);
  border-radius: 14px;
  padding: 6px 14px;
  box-shadow: 0 6px 24px rgba(80, 110, 170, 0.12);
  border: 1px solid rgba(120, 145, 195, 0.22);
}

.lp-gender-select {
  width: 140px;
}

.lp-gender-select :deep(.el-select__wrapper) {
  background: rgba(255, 255, 255, 0.78);
  border-radius: 14px;
  box-shadow: 0 6px 24px rgba(80, 110, 170, 0.12);
  border: 1px solid rgba(120, 145, 195, 0.22);
  height: 42px;
}

.lp-pills {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  margin-top: 18px;
  flex-wrap: wrap;
  justify-content: center;
}

.lp-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 16px;
  border-radius: 999px;
  border: 1px solid rgba(120, 145, 195, 0.3);
  background: rgba(255, 255, 255, 0.6);
  color: #5e7baf;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.18s;
}

.lp-pill:hover {
  border-color: rgba(120, 145, 195, 0.6);
  color: #2c3e6e;
}

.lp-pill.active {
  background: linear-gradient(135deg, #5e7baf, #6e8fdf);
  color: #fff;
  border-color: transparent;
  box-shadow: 0 6px 14px rgba(80, 110, 170, 0.25);
}

.lp-market {
  max-width: 1180px;
  width: 100%;
  margin: 0 auto;
  padding: 8px 4px;
}

.lp-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
  gap: 16px;
}

/* 入口页固定 5 列（1 个 CTA + 4 张卡片），更紧凑、对齐更整齐 */
.lp-grid-fixed {
  grid-template-columns: repeat(5, minmax(0, 1fr));
  max-width: 1100px;
  margin: 0 auto;
}

@media (max-width: 980px) {
  .lp-grid-fixed {
    grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
  }
}

.lp-card {
  width: 0;
  min-width: 100%;
  background: rgba(255, 255, 255, 0.85);
  border: 1px solid rgba(120, 145, 195, 0.18);
  border-radius: 14px;
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s, border-color 0.2s;
  display: flex;
  flex-direction: column;
  backdrop-filter: blur(6px);
}

.lp-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 12px 28px rgba(80, 110, 170, 0.18);
  border-color: rgba(120, 145, 195, 0.45);
}

.lp-card-cta {
  background: linear-gradient(160deg, #ffffff, #f6f8ff);
  border: 1px dashed rgba(120, 145, 195, 0.45);
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 22px 18px;
  gap: 8px;
}

.lp-card-cta:hover {
  border-color: #5e7baf;
  background: linear-gradient(160deg, #ffffff, #eef3fc);
}

.lp-cta-avatar img {
  width: 72px;
  height: 72px;
  border-radius: 16px;
  object-fit: cover;
  box-shadow: 0 6px 16px rgba(80, 110, 170, 0.18);
}

.lp-cta-title {
  margin: 8px 0 0;
  font-size: 18px;
  font-weight: 700;
  color: #2c3e6e;
}

.lp-cta-sub {
  margin: 0;
  font-size: 12px;
  color: #6e7fa3;
  line-height: 1.5;
}

.lp-cta-btn {
  margin-top: 8px;
  min-width: 140px;
  border-radius: 999px;
  background: linear-gradient(135deg, #5e7baf, #6e8fdf);
  border: none;
}

.lp-cta-tips {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  font-size: 11px;
  color: #8aa0c4;
  flex-wrap: wrap;
  justify-content: center;
}

.lp-cta-tips i {
  font-style: normal;
  opacity: 0.6;
}

.lp-card-image {
  width: 100%;
  aspect-ratio: 3 / 4;
  overflow: hidden;
  background: linear-gradient(135deg, #e8efff, #d6e4ff);
}

.lp-card-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.lp-card-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 36px;
  color: rgba(94, 123, 175, 0.5);
  background: linear-gradient(135deg, #e8efff, #d6e4ff);
}

.lp-card-body {
  padding: 8px 10px 10px;
  display: flex;
  flex-direction: column;
}

.lp-card-name {
  font-size: 13px;
  font-weight: 600;
  color: #2c3e6e;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.lp-card-desc {
  font-size: 11.5px;
  color: #6e7fa3;
  line-height: 1.4;
  margin: 3px 0 4px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
  min-height: calc(1.4em * 2);
}

.lp-card-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: auto;
  font-size: 11px;
  color: #8aa0c4;
}

.lp-card-stat {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.lp-empty {
  grid-column: 1 / -1;
  text-align: center;
  padding: 40px 20px;
  color: #8aa0c4;
  font-size: 14px;
}

.lp-pagination {
  display: flex;
  justify-content: center;
  margin-top: 18px;
}

.lp-footer {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 18px 16px 28px;
  font-size: 12px;
  color: #8aa0c4;
}

.lp-footer-sep {
  opacity: 0.5;
}

/* 详情弹窗：左右分栏 */
.lp-detail {
  display: flex;
  gap: 24px;
  min-height: 460px;
}

/* 左栏：头像 + 图片下方统计 + 创作者 */
.lp-detail-left {
  width: 240px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.lp-detail-avatar-box {
  position: relative;
  width: 100%;
  height: 260px;
  border-radius: 14px;
  overflow: hidden;
  background: linear-gradient(135deg, #e8efff, #d6e4ff);
  cursor: zoom-in;
}

.lp-detail-avatar-box.is-clickable:hover img {
  transform: scale(1.02);
}

.lp-detail-avatar-box img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.2s;
}

.lp-detail-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 48px;
  color: rgba(94, 123, 175, 0.5);
}

.lp-detail-zoom {
  position: absolute;
  bottom: 10px;
  right: 10px;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
}

/* 图片下方统计：点赞 / 评论 */
.lp-detail-stats {
  display: flex;
  gap: 8px;
}

.lp-detail-stat {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 8px 4px;
  border-radius: 10px;
  background: rgba(110, 143, 223, 0.07);
  border: 1px solid rgba(110, 143, 223, 0.14);
}

.lp-detail-stat.like {
  color: #e0603f;
}

.lp-detail-stat.comment {
  color: #5e7baf;
}

.lp-detail-stat-num {
  font-size: 15px;
  font-weight: 700;
  line-height: 1.1;
}

.lp-detail-stat-label {
  font-size: 11px;
  color: #8796b5;
}

/* 创作者卡片 */
.lp-detail-creator-card {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.65);
  border: 1px solid rgba(110, 143, 223, 0.14);
}

.lp-detail-creator-avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  flex: none;
}

.lp-detail-creator-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.lp-detail-creator-label {
  font-size: 10px;
  color: #8796b5;
  line-height: 1.2;
}

.lp-detail-creator-name {
  font-size: 13px;
  font-weight: 600;
  color: #2c3e6e;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.lp-detail-right {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.lp-detail-name {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: #2c3e6e;
}

.lp-detail-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
  color: #8aa0c4;
}

.lp-detail-meta-stats {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.lp-detail-desc {
  margin: 0;
  font-size: 13px;
  color: #4f6393;
  line-height: 1.5;
}

.lp-detail-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.lp-detail-label {
  font-size: 13px;
  font-weight: 600;
  color: #2c3e6e;
}

.lp-detail-box {
  background: rgba(238, 243, 252, 0.7);
  border: 1px solid rgba(120, 145, 195, 0.18);
  border-radius: 10px;
  padding: 12px 14px;
  font-size: 13px;
  color: #4f6393;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 220px;
  overflow-y: auto;
}

.lp-greeting-box {
  border-left: 3px solid #6e8fdf;
}

/* 入口页详情：人物提示词折叠样式 */
.lp-detail-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.lp-detail-toggle {
  background: none;
  border: none;
  padding: 0;
  font-size: 12px;
  color: #6e8fdf;
  cursor: pointer;
  font-weight: 500;
}

.lp-detail-toggle:hover {
  text-decoration: underline;
}

/* 收起态：限高 + 渐变遮罩；展开态：内容自然撑开 */
.lp-prompt-collapsed {
  max-height: 96px;
  overflow: hidden;
  position: relative;
  cursor: pointer;
  -webkit-mask-image: linear-gradient(to bottom, #000 60%, rgba(0, 0, 0, 0) 100%);
  mask-image: linear-gradient(to bottom, #000 60%, rgba(0, 0, 0, 0) 100%);
}

.lp-detail-bottom {
  margin-top: auto;
  padding-top: 12px;
}

.lp-detail-btn {
  width: 100%;
  background: linear-gradient(135deg, #5e7baf, #6e8fdf);
  border: none;
}

/* 入口页详情评论区 */
.lp-comments-section {
  border-top: 1px solid rgba(120, 145, 195, 0.22);
  padding-top: 12px;
}

.lp-comments-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 240px;
  overflow-y: auto;
}

.lp-no-comments {
  font-size: 13px;
  color: #8aa0c4;
  padding: 12px 0;
}

.lp-comment {
  background: rgba(255, 255, 255, 0.6);
  border: 1px solid rgba(120, 145, 195, 0.18);
  border-radius: 10px;
  padding: 10px 12px;
}

.lp-comment-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.lp-comment-avatar {
  width: 24px;
  height: 24px;
  border-radius: 50%;
}

.lp-comment-pseudonym {
  font-size: 13px;
  font-weight: 600;
  color: #2c3e6e;
}

.lp-comment-time {
  font-size: 11px;
  color: #8aa0c4;
  margin-left: auto;
}

.lp-comment-text {
  font-size: 13px;
  color: #4f6393;
  line-height: 1.5;
  margin: 0;
  word-break: break-word;
}

.lp-comments-load-more {
  display: flex;
  justify-content: center;
  padding: 8px 0;
}

.lp-comments-load-more button {
  background: none;
  border: none;
  font-size: 13px;
  color: #6e8fdf;
  cursor: pointer;
  padding: 6px 12px;
  border-radius: 6px;
  transition: background 0.15s;
}

.lp-comments-load-more button:hover {
  background: rgba(110, 143, 223, 0.08);
  text-decoration: underline;
}

@media (max-width: 768px) {
  .lp-title { font-size: 28px; }
  .lp-grid { grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 12px; }
  .lp-detail { flex-direction: column; }
  .lp-detail-left { width: 100%; height: auto; }
  .lp-detail-avatar-box { height: 220px; }
}

.sidebar-wrap,
.chat-wrap {
  position: relative;
  z-index: 1;
}

.chat-wrap {
  flex: 1;
  min-width: 0;
}

/* ===== 移动端响应式 ===== */
.mobile-menu-btn {
  position: fixed;
  top: 12px;
  left: 14px;
  z-index: 60;
  width: 40px;
  height: 40px;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  background: var(--surface);
  color: var(--text-primary);
  box-shadow: var(--shadow-soft);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 20px;
  transition: transform 0.15s ease, background 0.2s;
}

.mobile-menu-btn:active { transform: scale(0.92); }

.sidebar-backdrop {
  position: fixed;
  inset: 0;
  z-index: 55;
  background: rgba(20, 12, 5, 0.4);
  backdrop-filter: blur(2px);
}

@media (max-width: 768px) {
  .sidebar-wrap {
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    width: 280px;
    max-width: 86vw;
    height: 100vh;
    height: 100dvh;
    z-index: 60;
    border-right: none;
    box-shadow: 0 0 60px rgba(15, 8, 3, 0.3);
    transition: transform 0.3s cubic-bezier(0.2, 0.8, 0.2, 1);
  }

  /* 移动端收起 = 隐藏（避免迷你栏遮挡对话区） */
  .sidebar-wrap.collapsed {
    transform: translateX(-100%);
  }

  /* 移动端输入区更紧凑 */
  .chat-wrap {
    padding-bottom: 0;
  }
}
</style>