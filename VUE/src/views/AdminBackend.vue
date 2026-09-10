<template>
  <div class="admin-page">
    <!-- 顶部导航 -->
    <header class="admin-header">
      <div class="header-brand">
        <img :src="brandIcon" class="brand-img" alt="Confide" />
        <span class="brand-text">{{ t('Confide 管理后台', 'Confide Admin') }}</span>
      </div>
      <div class="header-right">
        <span v-if="adminName" class="admin-name">
          <el-icon><Monitor /></el-icon> {{ t('管理员', 'Admin') }}：{{ adminName }}
        </span>
        <el-button size="small" :icon="Back" @click="$router.push('/')">
          {{ t('返回主界面', 'Back to app') }}
        </el-button>
        <el-button size="small" type="danger" plain :icon="SwitchButton" @click="doLogout">
          {{ t('退出', 'Log out') }}
        </el-button>
      </div>
    </header>

    <main class="admin-main">
      <!-- 平台统计 -->
      <div class="admin-stats" v-loading="statsLoading">
        <div class="stat-card"><div class="stat-num">{{ stats.user_count ?? '-' }}</div><div class="stat-label">{{ t('用户', 'Users') }}</div></div>
        <div class="stat-card"><div class="stat-num">{{ stats.conversation_count ?? '-' }}</div><div class="stat-label">{{ t('对话', 'Conversations') }}</div></div>
        <div class="stat-card"><div class="stat-num">{{ stats.message_count ?? '-' }}</div><div class="stat-label">{{ t('消息', 'Messages') }}</div></div>
        <div class="stat-card"><div class="stat-num">{{ stats.provider_count ?? '-' }}</div><div class="stat-label">{{ t('模型配置', 'Providers') }}</div></div>
        <div class="stat-card"><div class="stat-num">{{ stats.persona_count ?? '-' }}</div><div class="stat-label">{{ t('角色', 'Personas') }}</div></div>
        <div class="stat-card stat-today">
          <div class="stat-num">{{ (stats.today?.users ?? 0) }}<span class="sub">/{{ stats.today?.messages ?? 0 }}</span></div>
          <div class="stat-label">{{ t('今日新增用户/消息', 'New today') }}</div>
        </div>
      </div>

      <el-tabs v-model="activeTab" class="admin-tabs">
        <!-- 用户数据 Tab -->
        <el-tab-pane :label="t('用户数据', 'User Data')" name="users">
          <div class="admin-toolbar">
            <span class="admin-title">{{ t('用户数据', 'User Data') }}</span>
            <div class="toolbar-actions">
              <el-select v-model="genderFilter" placeholder="性别筛选" size="small" style="width: 120px" @change="applyGenderFilter">
                <el-option label="全部" value="" />
                <el-option label="男" value="男" />
                <el-option label="女" value="女" />
                <el-option label="神秘" value="神秘" />
              </el-select>
              <el-button size="small" :icon="Refresh" @click="loadAll">{{ t('刷新', 'Refresh') }}</el-button>
            </div>
          </div>

          <el-table
            :data="users"
            v-loading="usersLoading"
            class="admin-table"
            :default-expand-all="false"
            row-key="id"
            @expand-change="onUserExpand"
          >
            <el-table-column type="expand">
              <template #default="{ row }">
                <el-table
                  :data="row._conversations || []"
                  class="inner-table"
                  row-key="id"
                  v-loading="row._loading"
                >
                  <el-table-column prop="title" :label="t('对话标题', 'Conversation')" min-width="160" show-overflow-tooltip />
                  <el-table-column prop="message_count" :label="t('消息数', 'Msgs')" width="80" align="center" />
                  <el-table-column :label="t('AI人设', 'Persona')" width="130" show-overflow-tooltip>
                    <template #default="{ row: conv }">
                      <span v-if="conv.persona_name" class="persona-link" @click.stop="showPersonaDetail(conv)">{{ conv.persona_name }}</span>
                      <span v-else>-</span>
                    </template>
                  </el-table-column>
                  <el-table-column :label="t('背景图', 'Background')" width="90" align="center">
                    <template #default="{ row: conv }">
                      <img v-if="conv.background_image" :src="conv.background_image" class="bg-thumb" alt="" />
                      <span v-else>-</span>
                    </template>
                  </el-table-column>
                  <el-table-column :label="t('更新时间', 'Updated')" width="150">
                    <template #default="{ row: conv }">{{ formatTime(conv.updated_at) }}</template>
                  </el-table-column>
                  <el-table-column :label="t('消息', 'Messages')" width="90" align="center">
                    <template #default="{ row: conv }">
                      <el-button size="small" type="primary" plain @click.stop="exportConversation(conv)">
                        {{ t('导出', 'Export') }}
                      </el-button>
                    </template>
                  </el-table-column>
                </el-table>
                <div v-if="!row._conversations || row._conversations.length === 0" class="col-empty-inner">{{ t('该用户暂无对话', 'No conversations') }}</div>
              </template>
            </el-table-column>

            <el-table-column prop="username" :label="t('用户名', 'Username')" min-width="110" show-overflow-tooltip />
            <el-table-column prop="email" :label="t('邮箱', 'Email')" min-width="160" show-overflow-tooltip />
            <el-table-column prop="gender" :label="t('性别', 'Gender')" width="80" align="center">
              <template #default="{ row }">{{ row.gender || '-' }}</template>
            </el-table-column>
            <el-table-column :label="t('状态', 'Status')" width="80" align="center">
              <template #default="{ row }">
                <el-tag :type="row.is_active && !row.deleted_at ? 'success' : 'danger'" size="small">
                  {{ row.deleted_at ? t('已注销', 'Deleted') : (row.is_active ? t('正常', 'Active') : t('停用', 'Disabled')) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="conversation_count" :label="t('对话', 'Chats')" width="80" align="center" />
            <el-table-column prop="message_count" :label="t('消息', 'Msgs')" width="80" align="center" />
            <el-table-column prop="provider_count" :label="t('模型配置', 'Cfgs')" width="90" align="center" />
            <el-table-column prop="persona_count" :label="t('角色', 'Personas')" width="80" align="center" />
            <el-table-column :label="t('最近活跃', 'Last Active')" width="150">
              <template #default="{ row }">{{ row.last_active ? formatTime(row.last_active) : '-' }}</template>
            </el-table-column>
            <el-table-column :label="t('注册时间', 'Registered')" width="150">
              <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- 卡片广场 Tab -->
        <el-tab-pane :label="t('卡片广场', 'Card Marketplace')" name="marketplace">
          <div class="admin-toolbar">
            <span class="admin-title">{{ t('卡片广场管理', 'Marketplace Management') }}</span>
            <el-button size="small" :icon="Refresh" @click="loadMarketplaceCards">{{ t('刷新', 'Refresh') }}</el-button>
          </div>
          <el-table :data="mpCards" v-loading="mpLoading" class="admin-table">
            <el-table-column :label="t('头像', 'Avatar')" width="70" align="center">
              <template #default="{ row }">
                <el-avatar :size="36" :src="row.avatar">{{ row.name?.charAt(0) }}</el-avatar>
              </template>
            </el-table-column>
            <el-table-column prop="name" :label="t('名称', 'Name')" min-width="120" show-overflow-tooltip />
            <el-table-column prop="description" :label="t('描述', 'Description')" min-width="180" show-overflow-tooltip />
            <el-table-column prop="author_username" :label="t('创建者', 'Creator')" width="120" show-overflow-tooltip />
            <el-table-column prop="author_email" :label="t('邮箱', 'Email')" width="180" show-overflow-tooltip />
            <el-table-column :label="t('点赞/踩', 'Likes')" width="100" align="center">
              <template #default="{ row }">{{ row.likes }} / {{ row.dislikes }}</template>
            </el-table-column>
            <el-table-column :label="t('评论数', 'Comments')" width="80" align="center">
              <template #default="{ row }">{{ row.comment_count }}</template>
            </el-table-column>
            <el-table-column :label="t('发布时间', 'Created')" width="150">
              <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column :label="t('操作', 'Actions')" width="90" align="center">
              <template #default="{ row }">
                <el-button size="small" type="danger" plain @click="deleteMpCard(row)">{{ t('删除', 'Delete') }}</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </main>

    <!-- 人设详情模态框 -->
    <el-dialog v-model="personaDetailVisible" :title="personaDetailData?.persona_name" width="min(500px, 90vw)" align-center>
      <div v-if="personaDetailData" class="persona-detail-modal">
        <div class="pdm-row">
          <el-avatar v-if="personaDetailData.persona_avatar" :size="64" :src="personaDetailData.persona_avatar" />
          <div class="pdm-info">
            <h3>{{ personaDetailData.persona_name }}</h3>
            <p>{{ personaDetailData.persona_description }}</p>
          </div>
        </div>
        <div v-if="personaDetailData.persona_system_prompt" class="pdm-section">
          <div class="pdm-label">{{ t('人设提示词', 'System Prompt') }}</div>
          <div class="pdm-box">{{ personaDetailData.persona_system_prompt }}</div>
        </div>
        <div v-if="personaDetailData.persona_greeting" class="pdm-section">
          <div class="pdm-label">{{ t('开场白', 'Greeting') }}</div>
          <div class="pdm-box">{{ personaDetailData.persona_greeting }}</div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Back, SwitchButton, Monitor } from '@element-plus/icons-vue'
import { adminApi } from '@/utils/resAi'
import { t } from '../i18n'
import brandIcon from '@/assets/icon/ChatBotIcon.png'

const router = useRouter()
const adminName = ref(localStorage.getItem('admin_username') || '')

const stats = ref({})
const users = ref([])
const statsLoading = ref(false)
const usersLoading = ref(false)
const genderFilter = ref('')
const allUsers = ref([])
const activeTab = ref('users')

// 卡片广场
const mpCards = ref([])
const mpLoading = ref(false)

// 人设详情模态框
const personaDetailVisible = ref(false)
const personaDetailData = ref(null)

function formatTime(iso) {
  if (!iso) return '-'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

async function loadStats() {
  statsLoading.value = true
  try {
    const res = await adminApi.stats()
    if (res.code === 200) stats.value = res.data
  } catch (e) {
    ElMessage.error(t('加载统计失败', 'Failed to load stats'))
  } finally {
    statsLoading.value = false
  }
}

async function loadUsers() {
  usersLoading.value = true
  try {
    const res = await adminApi.users()
    if (res.code === 200) {
      allUsers.value = (res.data || []).map(u => ({ ...u, _conversations: null, _loading: false }))
      applyGenderFilter()
    } else if (res.code === 403) {
      ElMessage.warning(t('无管理员权限', 'No admin permission'))
    }
  } catch (e) {
    ElMessage.error(t('加载用户失败', 'Failed to load users'))
  } finally {
    usersLoading.value = false
  }
}

function applyGenderFilter() {
  if (!genderFilter.value) {
    users.value = [...allUsers.value]
  } else {
    users.value = allUsers.value.filter(u => u.gender === genderFilter.value)
  }
}

async function loadConversations(user) {
  if (user._conversations) return
  user._loading = true
  try {
    const res = await adminApi.userConversations(user.id)
    if (res.code === 200) {
      user._conversations = (res.data || []).map(c => ({ ...c }))
    }
  } catch (e) {
    ElMessage.error(t('加载对话失败', 'Failed to load conversations'))
  } finally {
    user._loading = false
  }
}

// 外层用户表展开时加载该用户对话（修复展开无数据 bug）
function onUserExpand(row, expandedRows) {
  if (expandedRows && expandedRows.includes(row)) {
    loadConversations(row)
  }
}

async function exportConversation(conv) {
  try {
    await adminApi.exportConversation(conv.id)
    ElMessage.success(t(`已导出「${conv.title}」`, `Exported "${conv.title}"`))
  } catch (e) {
    ElMessage.error(t('导出失败', 'Export failed') + `：${e.message || ''}`)
  }
}

async function loadMarketplaceCards() {
  mpLoading.value = true
  try {
    const res = await adminApi.marketplaceCards()
    if (res.code === 200) {
      mpCards.value = res.data.items || []
    }
  } catch (e) {
    ElMessage.error(t('加载卡片失败', 'Failed to load cards'))
  } finally {
    mpLoading.value = false
  }
}

async function deleteMpCard(card) {
  try {
    await ElMessageBox.confirm(t(`确定删除卡片「${card.name}」吗？`, `Delete card "${card.name}"?`), t('确认', 'Confirm'), { type: 'warning' })
    const res = await adminApi.deleteMarketplaceCard(card.id)
    if (res.code === 200) {
      ElMessage.success(t('已删除', 'Deleted'))
      loadMarketplaceCards()
    }
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(t('删除失败', 'Delete failed'))
  }
}

function showPersonaDetail(conv) {
  personaDetailData.value = conv
  personaDetailVisible.value = true
}

async function loadAll() {
  await Promise.all([loadStats(), loadUsers()])
}

function doLogout() {
  ElMessageBox.confirm(
    t('确定要退出管理后台吗？', 'Log out of admin panel?'),
    t('确认', 'Confirm'),
    { type: 'warning' }
  ).then(() => {
    adminApi.logout()
    router.replace('/admin')
  }).catch(() => {})
}

onMounted(async () => {
  // 校验令牌是否仍有效，失效则回登录页
  try {
    const res = await adminApi.status()
    if (res.code !== 200) router.replace('/admin')
  } catch (e) {
    router.replace('/admin')
  }
  await loadAll()
})
</script>

<style scoped>
.admin-page {
  height: 100vh;
  height: 100dvh;
  display: flex;
  flex-direction: column;
  background: var(--app-bg, #faf6f1);
  overflow-x: hidden;
  overflow-y: auto;
}

.admin-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 24px;
  background: var(--surface, #fff);
  border-bottom: 1px solid var(--border-color, #e9e0d4);
  flex-wrap: wrap;
}

.header-brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand-img {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  object-fit: cover;
}

.brand-text {
  font-size: 18px;
  font-weight: 700;
  color: #7a4c24;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.admin-name {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: #a9815a;
  margin-right: 6px;
}

.admin-main {
  flex: 1;
  min-height: 0;
  padding: 24px;
  max-width: 1280px;
  width: 100%;
  margin: 0 auto;
  box-sizing: border-box;
}

.admin-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}

.stat-card {
  background: var(--surface, #fff);
  border: 1px solid var(--border-color, #e9e0d4);
  border-radius: 10px;
  padding: 16px 12px;
  text-align: center;
}

.stat-num {
  font-size: 22px;
  font-weight: 700;
  color: #4a3520;
}

.stat-num .sub {
  font-size: 13px;
  color: #a9815a;
}

.stat-label {
  font-size: 12px;
  color: #8a6a48;
  margin-top: 4px;
}

.stat-today {
  background: linear-gradient(135deg, #fbead6, #fff);
}

.admin-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.admin-title {
  font-size: 15px;
  font-weight: 600;
  color: #4a3520;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.admin-table {
  width: 100%;
  background: var(--surface, #fff);
  border-radius: 10px;
}

.inner-table {
  width: calc(100% - 24px);
  margin: 8px 12px;
  border: 1px solid var(--border-color, #e9e0d4);
  border-radius: 8px;
}

.msg-panel {
  padding: 10px 16px;
  background: var(--surface-hover, #faf3ea);
  border-radius: 8px;
  margin: 8px 24px;
}

.msg-block {
  padding: 4px 0;
  font-size: 13px;
  line-height: 1.5;
  border-bottom: 1px dashed rgba(0,0,0,0.05);
}

.msg-block:last-child {
  border-bottom: none;
}

.msg-role {
  font-weight: 600;
  color: #b06a2e;
  margin-right: 8px;
}

.msg-content {
  color: #4a3520;
  word-break: break-word;
}

.col-empty-inner {
  font-size: 12px;
  color: #a9815a;
  padding: 8px 0;
  text-align: center;
}

.admin-tabs {
  margin-top: 8px;
}

.persona-link {
  color: var(--brand, #b06a2e);
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.persona-link:hover {
  opacity: 0.8;
}

.bg-thumb {
  width: 40px;
  height: 28px;
  border-radius: 4px;
  object-fit: cover;
  border: 1px solid var(--border-color, #e9e0d4);
}

.persona-detail-modal {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.pdm-row {
  display: flex;
  align-items: center;
  gap: 14px;
}

.pdm-info h3 {
  margin: 0 0 4px;
  font-size: 16px;
  color: var(--text-primary, #4a3520);
}

.pdm-info p {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary, #8a6a48);
  line-height: 1.5;
}

.pdm-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.pdm-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #4a3520);
}

.pdm-box {
  background: var(--surface-hover, #faf3ea);
  border: 1px solid var(--border-color, #e9e0d4);
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 13px;
  color: var(--text-secondary, #8a6a48);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow-y: auto;
}

/* 移动端 */
@media (max-width: 768px) {
  .admin-main {
    padding: 14px;
  }
  .admin-stats {
    grid-template-columns: repeat(2, 1fr);
  }
  .admin-header {
    padding: 12px 14px;
  }
  .admin-table :deep(.el-table__cell),
  .admin-table :deep(th.el-table__cell) {
    padding: 6px 4px;
  }
}
</style>