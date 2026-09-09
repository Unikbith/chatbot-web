<template>
  <el-drawer
    v-model="visible"
    :title="t('管理后台', 'Admin Panel')"
    size="min(860px, 100vw)"
    direction="rtl"
    class="admin-drawer"
  >
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

    <div class="admin-toolbar">
      <span class="admin-title">{{ t('用户数据', 'User Data') }}</span>
      <el-button size="small" :icon="Refresh" @click="loadAll">{{ t('刷新', 'Refresh') }}</el-button>
    </div>

    <el-table
      :data="users"
      v-loading="usersLoading"
      class="admin-table"
      :default-expand-all="false"
      row-key="id"
    >
      <el-table-column type="expand">
        <template #default="{ row }">
          <!-- 用户的对话列表 -->
          <el-table
            :data="row._conversations || []"
            class="inner-table"
            row-key="id"
            v-loading="row._loading"
          >
            <el-table-column type="expand">
              <template #default="{ row: conv }">
                <div class="msg-panel" v-if="conv._messages">
                  <div class="msg-block" v-for="m in conv._messages" :key="m.id" :class="'msg-' + m.role">
                    <span class="msg-role">{{ m.role === 'user' ? t('用户', 'User') : t('AI', 'AI') }}</span>
                    <span class="msg-content">{{ m.content }}</span>
                  </div>
                  <div v-if="!conv._messages || conv._messages.length === 0" class="col-empty-inner">{{ t('暂无消息', 'No messages') }}</div>
                </div>
                <div v-else class="col-empty-inner">{{ t('点击展开查看消息', 'Expand to view messages') }}</div>
              </template>
            </el-table-column>
            <el-table-column prop="title" :label="t('对话标题', 'Conversation')" min-width="160" show-overflow-tooltip />
            <el-table-column prop="message_count" :label="t('消息数', 'Msgs')" width="80" align="center" />
            <el-table-column prop="persona_name" :label="t('角色', 'Persona')" width="110" show-overflow-tooltip>
              <template #default="{ row: conv }">{{ conv.persona_name || '-' }}</template>
            </el-table-column>
            <el-table-column :label="t('更新时间', 'Updated')" width="150">
              <template #default="{ row: conv }">{{ formatTime(conv.updated_at) }}</template>
            </el-table-column>
            <el-table-column :label="t('消息', 'Messages')" width="60" align="center">
              <template #default="{ row: conv }">
                <el-button size="small" text @click.stop="loadMessages(row, conv)">{{ t('查看', 'View') }}</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="!row._conversations" class="col-empty-inner">{{ t('点击加载该用户对话', 'Click to load conversations') }}</div>
        </template>
      </el-table-column>

      <el-table-column prop="username" :label="t('用户名', 'Username')" min-width="110" show-overflow-tooltip />
      <el-table-column prop="email" :label="t('邮箱', 'Email')" min-width="160" show-overflow-tooltip />
      <el-table-column :label="t('状态', 'Status')" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">{{ row.is_active ? t('正常', 'Active') : t('停用', 'Disabled') }}</el-tag>
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
  </el-drawer>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { adminApi } from '@/utils/resAi'
import { t } from '../i18n'

const props = defineProps({ modelValue: { type: Boolean, default: false } })
const emit = defineEmits(['update:modelValue'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const stats = ref({})
const users = ref([])
const statsLoading = ref(false)
const usersLoading = ref(false)

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
      users.value = (res.data || []).map(u => ({ ...u, _conversations: null, _loading: false }))
    } else if (res.code === 403) {
      ElMessage.warning(t('无管理员权限', 'No admin permission'))
    }
  } catch (e) {
    ElMessage.error(t('加载用户失败', 'Failed to load users'))
  } finally {
    usersLoading.value = false
  }
}

async function loadConversations(user) {
  if (user._conversations) return
  user._loading = true
  try {
    const res = await adminApi.userConversations(user.id)
    if (res.code === 200) {
      user._conversations = (res.data || []).map(c => ({ ...c, _messages: null }))
    }
  } catch (e) {
    ElMessage.error(t('加载对话失败', 'Failed to load conversations'))
  } finally {
    user._loading = false
  }
}

async function loadMessages(user, conv) {
  if (conv._messages) { conv._messages = null; return }
  try {
    const res = await adminApi.conversationMessages(conv.id)
    if (res.code === 200) {
      conv._messages = (res.data?.messages || [])
    }
  } catch (e) {
    ElMessage.error(t('加载消息失败', 'Failed to load messages'))
  }
}

async function loadAll() {
  await Promise.all([loadStats(), loadUsers()])
}

watch(() => props.modelValue, (val) => {
  if (val) loadAll()
})
</script>

<style scoped>
.admin-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.stat-card {
  background: var(--surface);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  padding: 14px 12px;
  text-align: center;
}
.stat-num {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
}
.stat-num .sub {
  font-size: 13px;
  color: var(--text-muted);
}
.stat-label {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 4px;
}
.stat-today {
  background: linear-gradient(135deg, var(--brand-soft, #fdf3e7), var(--surface));
}

.admin-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.admin-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.admin-table {
  width: 100%;
}
.inner-table {
  width: calc(100% - 24px);
  margin: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
}
.msg-panel {
  padding: 10px 16px;
  background: var(--surface-hover);
  border-radius: 8px;
  margin: 8px 24px;
}
.msg-block {
  padding: 4px 0;
  font-size: 13px;
  line-height: 1.5;
}
.msg-role {
  font-weight: 600;
  color: var(--brand);
  margin-right: 8px;
}
.msg-content {
  color: var(--text-primary);
  word-break: break-word;
}
.col-empty-inner {
  font-size: 12px;
  color: var(--text-muted);
  padding: 8px 0;
  text-align: center;
}

/* 移动端优化 */
@media (max-width: 768px) {
  .admin-stats {
    grid-template-columns: repeat(2, 1fr);
  }
  .admin-table :deep(.el-table__cell),
  .admin-table :deep(th.el-table__cell) {
    padding: 6px 4px;
  }
}
</style>