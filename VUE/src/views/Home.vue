<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Present, Menu } from '@element-plus/icons-vue'
import {
  authApi, providersApi, personaApi, settingsApi, conversationApi, chatApi
} from '../utils/resAi'
import { applyTheme, bindSystemThemeListener } from '../utils/theme'
import { t, setLocale } from '../i18n'

import Sidebar from '../components/Sidebar.vue'
import ChatArea from '../components/ChatArea.vue'
import AuthModal from '../components/AuthModal.vue'
import ProviderPanel from '../components/ProviderPanel.vue'
import SystemSettings from '../components/SystemSettings.vue'
import PersonaPanel from '../components/PersonaPanel.vue'
import ConversationSettings from '../components/ConversationSettings.vue'

import defaultUserAvatar from '../assets/images/avatar-takashi.jpg'
import defaultAiAvatar from '../assets/images/avatar-megumi.jpg'

const sidebarRef = ref(null)
const chatAreaRef = ref(null)

// 用户状态
const user = ref(null)
const isLoggedIn = ref(false)

// 弹窗
const authModalVisible = ref(false)
const providerPanelVisible = ref(false)
const settingsVisible = ref(false)
const personaPanelVisible = ref(false)
const convoSettingsVisible = ref(false)

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

// 免费 API 提示条：每次打开网页展示一次、可点“知道了”消除；已配置自有模型的用户不展示
const freeApiBannerDismissed = ref(false)
// 是否已配置自有对话模型（任一启用的 chat 配置都视为已配置）
const hasOwnChatProvider = computed(() =>
  chatConfigs.value.some(p => p.provider_type === 'chat' && p.enabled !== false)
)
const showFreeApiBanner = computed(() =>
  isLoggedIn.value && chatStatus.value.is_free && !hasOwnChatProvider.value && !freeApiBannerDismissed.value
)
function dismissFreeApiBanner() {
  freeApiBannerDismissed.value = true
}

// 对话列表
const conversations = ref([])
const convGroups = ref({ pinned: [], today: [], yesterday: [], week: [], month: [], older: [] })

// 侧边栏折叠
const sidebarCollapsed = computed(() => userSettings.sidebar_collapsed)

// 移动端适配：窄屏时侧边栏改为浮层
const isMobile = ref(false)
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

// 背景层样式：仅覆盖聊天区域（红线标注区），随侧边栏收起自动铺满；
// 展示方式由用户设置决定：contain=完整可见（完整展示原貌，不裁剪）/ cover=覆盖背景（铺满填充）
const backgroundCover = computed(() =>
  currentConv.value?.background_cover || userSettings.background_cover || 'contain'
)

const bgStyle = computed(() => {
  const url = effectiveBackground.value
  if (!url) return {}
  return {
    backgroundImage: `url(${url})`,
    backgroundSize: backgroundCover.value,
    backgroundPosition: 'center',
    backgroundRepeat: 'no-repeat',
  }
})

// ========== 初始化 ==========
let unbindSystemTheme = null

onMounted(async () => {
  unbindSystemTheme = bindSystemThemeListener(() => userSettings.theme)
  updateViewport()
  window.addEventListener('resize', updateViewport)

  const token = localStorage.getItem('chatbot_token')
  if (token) {
    try {
      await loadUserInfo()
      await loadAllData()
      await ensureInitialConversation()
    } catch (e) {
      authModalVisible.value = true
    }
  } else {
    authModalVisible.value = true
  }

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
  action()
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
    console.warn('加载对话失败', e)
  }
}

async function loadPersonas() {
  try {
    const res = await personaApi.list()
    if (res.code === 200) {
      personas.value = res.data
      if (!currentPersona.value) {
        const defaultPersona = res.data.find(p => p.is_default) || res.data[0] || null
        currentPersona.value = defaultPersona
      }
    }
  } catch (e) {
    console.warn('加载角色失败', e)
  }
}

async function loadChatStatus() {
  try {
    const res = await chatApi.status()
    if (res.code === 200) {
      chatStatus.value = res.data
    }
  } catch (e) {
    console.warn('加载聊天状态失败', e)
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
    console.warn('加载提供商失败', e)
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
  const personaId = ( personas.value.find(p => p.is_default) || personas.value[0] || currentPersona.value )?.id || null
  currentProviderId.value = pickEnabledChatProviderId()
  try {
    const res = await conversationApi.create({
      title: t('新对话', 'New Chat'),
      provider_id: currentProviderId.value,
      persona_id: personaId,
      system_prompt: systemPrompt.value,
      temperature: userSettings.temperature,
    })

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
  await loadAllData()
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
  authModalVisible.value = true
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
function handlePersonaChanged(persona) {
  // 应用到当前对话（若存在则保存）
  if (persona) {
    currentPersona.value = persona
    if (currentConvId.value) {
      conversationApi.update(currentConvId.value, { persona_id: persona.id }).then(() => {
        loadConversations()
      }).catch(() => {})
    }
  }
  loadPersonas()
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

// ========== 对话独立设置 ==========
function openConversationSettings() {
  convoSettingsVisible.value = true
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
    :style="{ '--sidebar-width': sidebarCollapsed ? (isMobile ? '0px' : '60px') : (isMobile ? '0px' : '280px') }"
  >
    <!-- 背景层：仅覆盖聊天区域（红线标注区），侧边栏收起时自动铺满 -->
    <div class="bg-layer" :style="bgStyle"></div>

    <!-- 免费 API 提示条 -->
    <div v-if="showFreeApiBanner" class="free-api-banner">
      <span class="free-icon"><el-icon><Present /></el-icon></span>
      <span>{{ t('当前使用', 'Now using') }} <strong>{{ chatStatus.free_name }}</strong>，{{ t('为获得更好体验建议配置自己的 API Key', 'configure your own API Key for a better experience') }}</span>
      <el-button size="small" type="primary" link @click="providerPanelVisible = true">
        {{ t('去配置', 'Configure') }}
      </el-button>
      <el-button size="small" text @click="dismissFreeApiBanner">
        {{ t('知道了', 'Got it') }}
      </el-button>
    </div>

    <!-- 侧边栏 -->
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
      @create="handleNewChat"
      @select="handleSelectConversation"
      @toggle-pin="handleTogglePin"
      @delete="handleDeleteConversation"
      @toggle-collapse="toggleSidebar"
      @open-provider="requireLogin(() => providerPanelVisible = true)"
      @open-settings="requireLogin(() => settingsVisible = true)"
      @open-persona="requireLogin(() => personaPanelVisible = true)"
      @login="authModalVisible = true"
      @logout="handleLogout"
    />

    <!-- 聊天主区域 -->
    <ChatArea
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
      @open-settings="requireLogin(() => settingsVisible = true)"
      @open-provider="requireLogin(() => providerPanelVisible = true)"
      @open-conversation-settings="openConversationSettings"
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
    />

    <!-- 系统设置面板 -->
    <SystemSettings
      v-model="settingsVisible"
      :user="user"
      @settings-updated="handleSettingsUpdated"
      @user-updated="handleUserUpdated"
      @logout="handleLogout"
    />

    <!-- 角色人设面板 -->
    <PersonaPanel
      v-model="personaPanelVisible"
      :selected-id="currentPersona?.id"
      @persona-changed="handlePersonaChanged"
    />

    <!-- 对话独立设置 -->
    <ConversationSettings
      v-model="convoSettingsVisible"
      :conversation="currentConv"
      :personas="personas"
      :configs="chatConfigs"
      :user-avatar="effectiveUserAvatar"
      :general-opacity="userSettings.message_opacity"
      :general-temperature="userSettings.temperature"
      :general-frequency-penalty="userSettings.frequency_penalty"
      :general-presence-penalty="userSettings.presence_penalty"
      @save="handleConvoSettingsSaved"
    />
  </div>
</template>

<style scoped>
.home-container {
  display: flex;
  width: 100%;
  height: 100vh;
  overflow: hidden;
  background: var(--app-bg);
  position: relative;
}

/* 背景层：仅覆盖聊天区域（从侧边栏右侧开始），侧边栏收起时自动铺满 */
.bg-layer {
  position: absolute;
  inset: 0 0 0 var(--sidebar-width, 0);
  z-index: 0;
  pointer-events: none;
  background-color: var(--app-bg);
  transition: background-image 0.3s;
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

.free-api-banner {
  position: fixed;
  top: 0;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1000;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 20px;
  background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
  color: #92400e;
  font-size: 13px;
  border-radius: 0 0 12px 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.free-icon {
  font-size: 16px;
}

.free-api-banner strong {
  color: #78350f;
}

/* ===== 移动端响应式 ===== */
.mobile-menu-btn {
  position: fixed;
  top: 14px;
  left: 14px;
  z-index: 60;
  width: 42px;
  height: 42px;
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
  transition: transform 0.15s ease;
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