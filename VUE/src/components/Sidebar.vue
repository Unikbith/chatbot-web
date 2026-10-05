<template>
  <div class="sidebar" :class="{ collapsed }">
    <!-- 收起时的迷你模式 -->
    <div v-if="collapsed" class="sidebar-mini">
      <div class="mini-logo" @click="toggleCollapse">
        <img :src="brandIcon" class="brand-img" alt="Confide" />
      </div>
      <div class="mini-new-chat" @click="createConversation">
        <el-icon><Plus /></el-icon>
      </div>
      <div class="mini-icon" @click="toggleCollapse" :title="t('展开对话列表', 'Expand chat list')">
        <el-icon><Menu /></el-icon>
      </div>
      <div class="mini-spacer"></div>
      <!-- 左下角个人头像：点击展开侧边栏（与左上角 logo/菜单一致） -->
      <div class="mini-user" :title="t('展开侧边栏', 'Expand sidebar')" @click="toggleCollapse">
        <el-avatar :size="32" :src="userAvatar || user?.avatar">
          {{ user?.username?.charAt(0)?.toUpperCase() }}
        </el-avatar>
      </div>
    </div>

    <!-- 展开模式 -->
    <template v-else>
      <div class="sidebar-header">
        <div class="logo">
          <img :src="brandIcon" class="logo-img" alt="Confide" />
          <span class="logo-text">Confide</span>
        </div>
        <el-button 
          class="collapse-btn" 
          circle 
          size="small" 
          @click="toggleCollapse"
          :title="t('收起侧边栏', 'Collapse sidebar')"
        >
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
      </div>

      <!-- 免费 API 提示条：仅在侧边栏展开（拉出）时显示。
           「知道了」只对本次访问有效，没配自己 Key 的用户下次进入仍会看到。 -->
      <div v-if="freeApiBanner" class="sidebar-free-banner">
        <span class="sfb-icon"><el-icon><Present /></el-icon></span>
        <span class="sfb-text">{{ t('当前使用', 'Now using') }} <strong>{{ freeApiName }}</strong>，{{ t('免费模型限制多、回复容易出戏，建议配置自己的 API Key', 'the free model is rate-limited and weak at roleplay — configure your own API Key') }}</span>
        <div class="sfb-actions">
          <el-button size="small" type="primary" link @click="openProvider">
            {{ t('去配置', 'Configure') }}
          </el-button>
          <el-button size="small" text @click="emit('dismiss-free-api')">
            {{ t('知道了', 'Got it') }}
          </el-button>
        </div>
      </div>

      <!-- 使用教程：常驻入口，固定在「开启新对话」之上。
           原来只在「新用户尚未点开」时出现，老用户与看过的用户就再也找不到；
           教程本就是要随时回看的东西，因此改为常驻。 -->
      <div class="sidebar-tutorial-banner">
        <span class="stb-icon"><el-icon><Reading /></el-icon></span>
        <span class="stb-text" @click="emit('open-tutorial')">
          {{ t('使用教程', 'Getting Started') }}
        </span>
        <div class="stb-actions">
          <el-button size="small" type="primary" link @click="emit('open-tutorial')">
            {{ t('查看', 'View') }}
          </el-button>
        </div>
      </div>
      
      <div class="new-chat-row">
        <el-button
          class="new-chat-btn"
          type="primary"
          @click="createConversation"
        >
          <el-icon class="btn-icon"><Plus /></el-icon>
          {{ t('开启新对话', 'New Chat') }}
        </el-button>
      </div>

      <!-- 人设列表 -->
      <div class="persona-list-section">
        <div class="persona-group">
          <div class="persona-group-header">
            <span class="persona-group-title">
              {{ t('人物卡', 'Persona Cards') }}
              <span class="persona-count">{{ aiPersonas.length }}/10</span>
            </span>
            <el-button text size="small" circle @click.stop="emit('open-persona')">
              <el-icon><Plus /></el-icon>
            </el-button>
          </div>
          <div
            v-for="p in aiPersonas"
            :key="p.id"
            class="persona-list-item"
            :class="{ active: currentPersona?.id === p.id }"
            @click="openPersonaEdit(p)"
          >
            <el-avatar :size="24" :src="p.avatar" class="pl-avatar">
              {{ p.name?.charAt(0) }}
            </el-avatar>
            <span class="pl-name">{{ p.name }}</span>
          </div>
          <div v-if="aiPersonas.length === 0" class="pl-empty">{{ t('暂无', 'None') }}</div>
        </div>

      </div>
      
      <div class="conversation-list">
        <!-- 对话列表标题 + 上限计数：固定在列表上方，不随列表滚动 -->
        <div class="conv-list-header">
          <span class="group-title">{{ t('对话列表', 'Conversations') }}</span>
          <span class="conv-count">{{ conversations.length }}/10</span>
        </div>
        <div class="conv-list-scroll">
        <template v-if="groups.pinned.length > 0">
          <!-- 置顶就是一个普通分组：标题与「今天 / 昨天」完全同款（无底色、无图标），
               只是排序上排在它们前面 -->
          <div class="group-title">{{ t('置顶', 'Pinned') }}</div>
          <div 
            v-for="conv in groups.pinned" 
            :key="conv.id"
            class="conv-item"
            :class="{ active: currentConvId == conv.id }"
            @click="selectConversation(conv.id)"
          >
            <span class="conv-title" :title="conv.title">{{ conv.title }}</span>
            <div class="conv-actions">
              <el-button size="small" text @click.stop="togglePin(conv.id)">
                <el-icon><Top /></el-icon>
              </el-button>
              <el-button size="small" text type="danger" @click.stop="confirmDelete(conv.id)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
          </div>
        </template>

        <!-- 有置顶对话时补上「今天」标题，让第二个分区有明确起点 -->
        <div
          v-if="groups.pinned.length > 0 && groups.today.length > 0"
          class="group-title"
        >{{ t('今天', 'Today') }}</div>

        <div
          v-for="conv in groups.today"
          :key="conv.id"
          class="conv-item"
          :class="{ active: currentConvId == conv.id }"
          @click="selectConversation(conv.id)"
        >
          <span class="conv-title" :title="conv.title">{{ conv.title }}</span>
          <div class="conv-actions">
            <el-button size="small" text @click.stop="togglePin(conv.id)">
              <el-icon><Top /></el-icon>
            </el-button>
            <el-button size="small" text type="danger" @click.stop="confirmDelete(conv.id)">
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>
        </div>
        
        <div v-if="groups.yesterday.length > 0" class="group-title">{{ t('昨天', 'Yesterday') }}</div>
        <div 
          v-for="conv in groups.yesterday" 
          :key="conv.id"
          class="conv-item"
          :class="{ active: currentConvId == conv.id }"
          @click="selectConversation(conv.id)"
        >
          <span class="conv-title" :title="conv.title">{{ conv.title }}</span>
          <div class="conv-actions">
            <el-button size="small" text @click.stop="togglePin(conv.id)">
              <el-icon><Top /></el-icon>
            </el-button>
            <el-button size="small" text type="danger" @click.stop="confirmDelete(conv.id)">
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>
        </div>
        
        <div v-if="groups.week.length > 0" class="group-title">{{ t('7天内', 'Past 7 days') }}</div>
        <div 
          v-for="conv in groups.week" 
          :key="conv.id"
          class="conv-item"
          :class="{ active: currentConvId == conv.id }"
          @click="selectConversation(conv.id)"
        >
          <span class="conv-title" :title="conv.title">{{ conv.title }}</span>
          <div class="conv-actions">
            <el-button size="small" text @click.stop="togglePin(conv.id)">
              <el-icon><Top /></el-icon>
            </el-button>
            <el-button size="small" text type="danger" @click.stop="confirmDelete(conv.id)">
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>
        </div>

        <div v-if="groups.month.length > 0" class="group-title">{{ t('30天内', 'Past 30 days') }}</div>
        <div 
          v-for="conv in groups.month" 
          :key="conv.id"
          class="conv-item"
          :class="{ active: currentConvId == conv.id }"
          @click="selectConversation(conv.id)"
        >
          <span class="conv-title" :title="conv.title">{{ conv.title }}</span>
          <div class="conv-actions">
            <el-button size="small" text @click.stop="togglePin(conv.id)">
              <el-icon><Top /></el-icon>
            </el-button>
            <el-button size="small" text type="danger" @click.stop="confirmDelete(conv.id)">
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>
        </div>

        <div v-if="groups.older.length > 0" class="group-title">{{ t('更早', 'Earlier') }}</div>
        <div 
          v-for="conv in groups.older" 
          :key="conv.id"
          class="conv-item"
          :class="{ active: currentConvId == conv.id }"
          @click="selectConversation(conv.id)"
        >
          <span class="conv-title" :title="conv.title">{{ conv.title }}</span>
          <div class="conv-actions">
            <el-button size="small" text @click.stop="togglePin(conv.id)">
              <el-icon><Top /></el-icon>
            </el-button>
            <el-button size="small" text type="danger" @click.stop="confirmDelete(conv.id)">
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>
        </div>

        <div v-if="conversations.length === 0" class="empty-tip">
          {{ t('暂无对话，点击上方按钮开始', 'No conversations yet. Click the button to start.') }}
        </div>
        </div>
      </div>
      
      <div class="sidebar-footer">
        <el-dropdown trigger="click" @command="handleCommand">
          <div class="user-info">
            <el-avatar :size="36" :src="userAvatar || user?.avatar" class="user-avatar">
              {{ user?.username?.charAt(0)?.toUpperCase() }}
            </el-avatar>
            <div class="user-meta">
              <span class="user-name">{{ user?.username || t('未登录', 'Not logged in') }}</span>
              <span class="user-email" v-if="user?.email">{{ user.email }}</span>
            </div>
            <el-icon class="user-arrow"><ArrowUp /></el-icon>
          </div>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item disabled v-if="user" class="user-info-item">
                {{ user?.username }}
              </el-dropdown-item>
              <el-dropdown-item v-if="user" command="marketplace">
                <el-icon><ShoppingBag /></el-icon> {{ t('卡片广场', 'Card Marketplace') }}
              </el-dropdown-item>
              <el-dropdown-item v-if="user" command="provider">
                <el-icon><Setting /></el-icon> {{ t('模型设置', 'Model Settings') }}
              </el-dropdown-item>
              <el-dropdown-item v-if="user" command="settings">
                <el-icon><Tools /></el-icon> {{ t('系统设置', 'Settings') }}
              </el-dropdown-item>
              <el-dropdown-item v-if="user" command="logout" divided>
                <el-icon><SwitchButton /></el-icon> {{ t('退出登录', 'Log out') }}
              </el-dropdown-item>
              <el-dropdown-item v-else command="login">
                <el-icon><User /></el-icon> {{ t('登录', 'Log in') }}
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, ArrowLeft, ArrowRight, ArrowUp, Top, Delete,
  User, Setting, Tools, SwitchButton, MagicStick, Menu, Present, ShoppingBag, Reading
} from '@element-plus/icons-vue'
import { t } from '../i18n'

import brandIcon from '../assets/icon/ChatBotIcon.png'

const props = defineProps({
  conversations: { type: Array, default: () => [] },
  groups: { type: Object, default: () => ({ pinned: [], today: [], yesterday: [], week: [], month: [], older: [] }) },
  currentConvId: { type: [String, Number], default: null },
  user: { type: Object, default: null },
  userAvatar: { type: String, default: null },
  collapsed: { type: Boolean, default: false },
  currentPersona: { type: Object, default: null },
  freeApiBanner: { type: Boolean, default: false },
  freeApiName: { type: String, default: '' },
  // 新用户教程入口：看过引导弹窗但尚未点开教程时显示在免费提示条下方
  tutorialHint: { type: Boolean, default: false },
  aiPersonas: { type: Array, default: () => [] },
})

const emit = defineEmits([
  'create', 'select', 'toggle-pin', 'delete',
  'toggle-collapse', 'open-provider', 'open-settings',
  'open-persona', 'open-marketplace', 'edit-persona',
  'login', 'logout',
  'dismiss-free-api',
  'open-tutorial', 'dismiss-tutorial'
])

function createConversation() {
  emit('create')
}

function selectConversation(id) {
  emit('select', id)
}

function togglePin(id) {
  emit('toggle-pin', id)
}

function confirmDelete(id) {
  ElMessageBox.confirm(t('确定删除这个对话吗？', 'Delete this conversation?'), t('确认删除', 'Confirm Delete'), {
    type: 'warning',
    confirmButtonText: t('删除', 'Delete'),
    cancelButtonText: t('取消', 'Cancel'),
  }).then(() => {
    emit('delete', id)
  }).catch(() => {})
}

function toggleCollapse() {
  emit('toggle-collapse')
}

function openProvider() {
  emit('open-provider')
}

function openPersonaPanel() {
  emit('open-persona')
}

/**
 * 点击人物卡：打开该人物卡的详细信息进行编辑
 * （不再切换当前对话人设；对话人设只能通过「对话设置」修改）
 */
function openPersonaEdit(persona) {
  emit('edit-persona', persona)
}

function handleCommand(cmd) {
  switch (cmd) {
    case 'marketplace':
      emit('open-marketplace')
      break
    case 'provider':
      emit('open-provider')
      break
    case 'settings':
      emit('open-settings')
      break
    case 'logout':
      emit('logout')
      break
    case 'login':
      emit('login')
      break
  }
}
</script>

<style scoped>
.sidebar {
  width: 280px;
  height: 100%;
  background: var(--sidebar-bg);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  transition: width 0.3s ease;
  flex-shrink: 0;
}

.sidebar.collapsed {
  width: 60px;
}

/* Mini 模式 */
.sidebar-mini {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px 0;
  height: 100%;
  gap: 8px;
}

.mini-logo {
  width: 32px;
  height: 32px;
  cursor: pointer;
  padding: 4px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.mini-logo .brand-img {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  object-fit: cover;
}

.mini-logo:hover {
  background: #e5e5e5;
}

.mini-new-chat {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--brand-gradient);
  color: white;
  border-radius: 10px;
  cursor: pointer;
  font-size: 18px;
  margin-top: 4px;
}

.mini-new-chat:hover {
  opacity: 0.9;
}

.mini-icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #6b7280;
  border-radius: 8px;
  cursor: pointer;
}

.mini-icon:hover {
  background: #e5e5e5;
}

.mini-spacer {
  flex: 1;
}

.mini-user {
  cursor: pointer;
  padding: 4px;
  border-radius: 50%;
}

.mini-user:hover {
  background: #e5e5e5;
}

/* 展开模式 */
.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 16px 8px;
}

.logo {
  display: flex;
  align-items: center;
  gap: 8px;
}

.logo-img {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  object-fit: cover;
  flex-shrink: 0;
}

.logo-text {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}

.collapse-btn {
  opacity: 0.6;
}

.collapse-btn:hover {
  opacity: 1;
}

.new-chat-btn {
  margin: 8px 0 12px;
  height: 40px;
  border-radius: 8px;
  font-size: 14px;
  background: var(--brand-gradient);
  border: none;
  flex: 1;
}

.new-chat-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 16px;
}

.conv-count {
  font-size: 12px;
  color: var(--text-muted);
  white-space: nowrap;
  flex-shrink: 0;
}

/* 侧边栏内的免费 API 提示条（土陶暖色，适配明暗主题） */
.sidebar-free-banner {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0 16px 12px;
  padding: 10px 12px;
  background: linear-gradient(135deg, rgba(222, 128, 84, 0.14) 0%, rgba(214, 103, 66, 0.12) 100%);
  border: 1px solid rgba(214, 103, 66, 0.28);
  border-radius: 10px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.sfb-icon {
  display: inline-flex;
  color: var(--brand);
  font-size: 15px;
}

.sfb-text strong {
  color: var(--brand);
}

.sfb-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.sfb-actions .el-button {
  font-size: 12px;
}

/* 新用户教程入口：与免费提示条同宽同位置，色调更低调以免抢走免费提示的注意力 */
.sidebar-tutorial-banner {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 16px 12px;
  padding: 8px 12px;
  background: var(--surface-hover);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.stb-icon {
  display: inline-flex;
  flex-shrink: 0;
  color: var(--brand);
  font-size: 15px;
}

.stb-text {
  flex: 1;
  min-width: 0;
  font-weight: 600;
  color: var(--text-primary);
  cursor: pointer;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stb-text:hover {
  color: var(--brand);
}

.stb-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

.stb-actions .el-button {
  font-size: 12px;
}

.btn-icon {
  color: var(--brand);
  margin-right: 6px;
}

/* 人设列表 */
.persona-list-section {
  margin: 0 12px 8px;
  max-height: 180px;
  overflow-y: auto;
}

.persona-group {
  margin-bottom: 6px;
}

.persona-group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 4px 2px;
}

.persona-group-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

/* 人物卡列表上限计数 */
.persona-count {
  font-size: 10px;
  font-weight: 500;
  color: var(--text-muted);
  background: var(--surface-hover);
  border-radius: 8px;
  padding: 1px 6px;
}

.persona-list-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
}

.persona-list-item:hover {
  background: var(--surface-hover);
}

.persona-list-item.active {
  background: var(--surface-hover);
}

.pl-avatar {
  flex-shrink: 0;
}

.pl-name {
  flex: 1;
  font-size: 13px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pl-empty {
  font-size: 12px;
  color: var(--text-muted);
  padding: 4px 8px;
}

.conversation-list {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 0 8px;
  overflow: hidden;
}

/* 列表标题 + 上限计数：固定在滚动区上方 */
.conv-list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  padding-right: 8px;
}

.conv-list-header .group-title {
  padding: 12px 8px 6px;
}

.conv-list-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.group-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  padding: 12px 8px 6px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* 置顶不再单独美化：标题用 .group-title 通用样式，列表项用 .conv-item 通用样式，
   与「今天 / 昨天 / 7天内」等分组完全一致的观感，只靠排序区分先后。 */

.conv-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  margin-bottom: 2px;
  transition: background 0.15s;
}

.conv-item:hover {
  background: var(--surface-hover);
}

.conv-item.active {
  background: var(--surface-hover);
}

.conv-title {
  flex: 1;
  font-size: 13px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding-right: 8px;
}

.conv-actions {
  display: none;
  gap: 2px;
  flex-shrink: 0;
}

.conv-item:hover .conv-actions {
  display: flex;
}

.empty-tip {
  text-align: center;
  color: #9ca3af;
  font-size: 13px;
  padding: 40px 16px;
}

.sidebar-footer {
  border-top: 1px solid var(--border-color);
  padding: 12px 16px;
  background: var(--surface-hover);
}

.user-info {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  padding: 6px;
  border-radius: 8px;
  transition: background 0.15s;
}

.user-info:hover {
  background: var(--border-color);
}

.user-avatar {
  flex-shrink: 0;
}

.user-meta {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.user-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-email {
  font-size: 11px;
  color: #9ca3af;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-arrow {
  color: #9ca3af;
  font-size: 12px;
}

.user-info-item {
  font-weight: 600;
  color: #1f2937;
}

/* 移动端：底部用户卡片避开底部安全区（Home Indicator），避免“贴底”错位 */
@media (max-width: 768px) {
  .sidebar-header {
    padding-top: calc(16px + env(safe-area-inset-top, 0px));
  }
  .sidebar-footer {
    padding-left: 16px;
    padding-right: 16px;
    padding-bottom: calc(12px + env(safe-area-inset-bottom, 0px));
  }
}
</style>
