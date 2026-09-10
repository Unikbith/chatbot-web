<template>
  <el-drawer
    v-model="visible"
    :title="t('人设广场', 'Persona Marketplace')"
    size="min(680px, 100vw)"
    direction="rtl"
    @close="handleClose"
  >
    <div class="marketplace">
      <!-- 顶部操作栏 -->
      <div class="mp-toolbar">
        <el-radio-group v-model="sortMode" size="default" @change="loadList">
          <el-radio-button value="hot">{{ t('热门', 'Hot') }}</el-radio-button>
          <el-radio-button value="new">{{ t('最新', 'New') }}</el-radio-button>
        </el-radio-group>
        <el-button type="primary" size="small" @click="showPublishDialog = true">
          <el-icon><Plus /></el-icon> {{ t('发布人设', 'Publish') }}
        </el-button>
      </div>

      <!-- 卡片网格 -->
      <div v-loading="loading" class="mp-grid">
        <div
          v-for="item in items"
          :key="item.id"
          class="mp-card"
          @click="openDetail(item)"
        >
          <div class="card-header">
            <el-avatar :size="48" :src="item.avatar" class="card-avatar">
              {{ item.name?.charAt(0) }}
            </el-avatar>
            <div class="card-info">
              <div class="card-name">{{ item.name }}</div>
              <div class="card-author">{{ item.author_name }}</div>
            </div>
          </div>
          <p class="card-desc">{{ item.description || t('暂无描述', 'No description') }}</p>
          <div class="card-footer">
            <span class="card-stat like"><el-icon><Star /></el-icon> {{ item.likes }}</span>
            <span class="card-stat dislike"><el-icon><StarFilled /></el-icon> {{ item.dislikes }}</span>
            <span class="card-stat comment"><el-icon><ChatDotRound /></el-icon> {{ item.comment_count || 0 }}</span>
          </div>
        </div>

        <div v-if="!loading && items.length === 0" class="mp-empty">
          {{ t('暂无人设，快来发布第一个吧', 'No personas yet. Be the first to publish!') }}
        </div>
      </div>

      <!-- 分页 -->
      <div v-if="totalPages > 1" class="mp-pagination">
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="pageSize"
          :total="total"
          layout="prev, pager, next"
          small
          @current-change="loadList"
        />
      </div>
    </div>

    <!-- 详情对话框 -->
    <el-dialog
      v-model="detailVisible"
      :title="detailData?.name"
      width="min(600px, 95vw)"
      align-center
      destroy-on-close
    >
      <div v-if="detailData" class="detail-content">
        <div class="detail-header">
          <el-avatar :size="64" :src="detailData.avatar" class="detail-avatar">
            {{ detailData.name?.charAt(0) }}
          </el-avatar>
          <div class="detail-meta">
            <h3>{{ detailData.name }}</h3>
            <span class="detail-author">{{ t('作者', 'Author') }}: {{ detailData.author_name }}</span>
          </div>
        </div>

        <p class="detail-desc">{{ detailData.description }}</p>

        <div class="detail-prompt-section">
          <div class="prompt-label">{{ t('系统提示词', 'System Prompt') }}</div>
          <div class="prompt-box">{{ detailData.system_prompt }}</div>
        </div>

        <div v-if="detailData.greeting" class="detail-prompt-section">
          <div class="prompt-label">{{ t('开场白', 'Greeting') }}</div>
          <div class="prompt-box greeting-box">{{ detailData.greeting }}</div>
        </div>

        <!-- 操作按钮 -->
        <div class="detail-actions">
          <el-button
            :type="detailData.user_vote === 'like' ? 'primary' : 'default'"
            @click="handleVote('like')"
          >
            <el-icon><Star /></el-icon> {{ detailData.likes }}
          </el-button>
          <el-button
            :type="detailData.user_vote === 'dislike' ? 'danger' : 'default'"
            @click="handleVote('dislike')"
          >
            <el-icon><StarFilled /></el-icon> {{ detailData.dislikes }}
          </el-button>
          <el-button type="success" @click="handleAdopt">
            <el-icon><Download /></el-icon> {{ t('采用', 'Adopt') }}
          </el-button>
        </div>

        <!-- 评论区 -->
        <div class="comments-section">
          <div class="comments-header">
            <span>{{ t('评论', 'Comments') }} ({{ commentTotal }})</span>
            <el-radio-group v-model="commentSort" size="small" @change="loadComments">
              <el-radio-button value="hot">{{ t('热门', 'Hot') }}</el-radio-button>
              <el-radio-button value="new">{{ t('最新', 'New') }}</el-radio-button>
            </el-radio-group>
          </div>

          <!-- 发表评论 -->
          <div class="comment-input">
            <el-input
              v-model="newComment"
              :placeholder="t('写下你的评论...', 'Write a comment...')"
              maxlength="500"
              show-word-limit
              type="textarea"
              :rows="2"
            />
            <el-button type="primary" size="small" :disabled="!newComment.trim()" @click="submitComment" :loading="commentSubmitting">
              {{ t('发表', 'Post') }}
            </el-button>
          </div>

          <!-- 评论列表 -->
          <div v-loading="commentsLoading" class="comments-list">
            <div v-for="c in comments" :key="c.id" class="comment-item">
              <div class="comment-user">
                <img
                  :src="`https://api.dicebear.com/7.x/identicon/svg?seed=${c.identicon_seed}`"
                  class="comment-identicon"
                  alt=""
                />
                <span class="comment-pseudonym">{{ c.pseudonym }}</span>
                <span v-if="c.is_author" class="comment-badge">{{ t('作者', 'Author') }}</span>
              </div>
              <p class="comment-text">{{ c.content }}</p>
              <div class="comment-footer">
                <el-button text size="small" @click="handleLikeComment(c)">
                  <el-icon><Star /></el-icon> {{ c.likes }}
                </el-button>
                <span class="comment-time">{{ formatTime(c.created_at) }}</span>
              </div>
            </div>
            <div v-if="!commentsLoading && comments.length === 0" class="no-comments">
              {{ t('暂无评论', 'No comments yet') }}
            </div>
          </div>
        </div>
      </div>
    </el-dialog>

    <!-- 发布人设对话框 -->
    <el-dialog
      v-model="showPublishDialog"
      :title="t('发布人设', 'Publish Persona')"
      width="min(500px, 95vw)"
      align-center
      destroy-on-close
    >
      <el-form :model="publishForm" label-position="top">
        <el-form-item :label="t('名称', 'Name')" required>
          <el-input v-model="publishForm.name" maxlength="30" show-word-limit />
        </el-form-item>
        <el-form-item :label="t('描述', 'Description')">
          <el-input v-model="publishForm.description" type="textarea" :rows="2" maxlength="200" show-word-limit />
        </el-form-item>
        <el-form-item :label="t('系统提示词', 'System Prompt')" required>
          <el-input v-model="publishForm.system_prompt" type="textarea" :rows="5" maxlength="4000" show-word-limit />
        </el-form-item>
        <el-form-item :label="t('开场白', 'Greeting')">
          <el-input v-model="publishForm.greeting" type="textarea" :rows="2" maxlength="500" show-word-limit />
        </el-form-item>
        <el-form-item :label="t('头像', 'Avatar')">
          <el-upload
            :show-file-list="false"
            :before-upload="handleAvatarUpload"
            accept="image/*"
          >
            <div class="publish-avatar-preview">
              <el-avatar v-if="publishForm.avatar" :size="64" :src="publishForm.avatar" />
              <el-avatar v-else :size="64"><el-icon><Plus /></el-icon></el-avatar>
              <span class="upload-hint">{{ t('点击上传', 'Click to upload') }}</span>
            </div>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showPublishDialog = false">{{ t('取消', 'Cancel') }}</el-button>
        <el-button type="primary" @click="handlePublish" :loading="publishing">
          {{ t('发布', 'Publish') }}
        </el-button>
      </template>
    </el-dialog>
  </el-drawer>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Star, StarFilled, ChatDotRound, Download } from '@element-plus/icons-vue'
import { marketplaceApi, uploadApi } from '../utils/resAi'
import { t } from '../i18n'

const props = defineProps({
  modelValue: Boolean,
})

const emit = defineEmits(['update:modelValue', 'adopted'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

// 列表状态
const loading = ref(false)
const items = ref([])
const sortMode = ref('hot')
const currentPage = ref(1)
const pageSize = 12
const total = ref(0)
const totalPages = computed(() => Math.ceil(total.value / pageSize))

// 详情状态
const detailVisible = ref(false)
const detailData = ref(null)

// 评论状态
const comments = ref([])
const commentsLoading = ref(false)
const commentSort = ref('hot')
const commentTotal = ref(0)
const newComment = ref('')
const commentSubmitting = ref(false)

// 发布状态
const showPublishDialog = ref(false)
const publishing = ref(false)
const publishForm = reactive({
  name: '',
  description: '',
  system_prompt: '',
  greeting: '',
  avatar: '',
})

watch(() => props.modelValue, (val) => {
  if (val) loadList()
})

async function loadList() {
  loading.value = true
  try {
    const res = await marketplaceApi.list(sortMode.value, currentPage.value)
    if (res.code === 200) {
      items.value = res.data.items || []
      total.value = res.data.total || 0
    }
  } catch (e) {
    console.error('加载人设广场失败', e)
  } finally {
    loading.value = false
  }
}

async function openDetail(item) {
  try {
    const res = await marketplaceApi.get(item.id)
    if (res.code === 200) {
      detailData.value = res.data
      detailVisible.value = true
      loadComments()
    }
  } catch (e) {
    ElMessage.error(t('加载详情失败', 'Failed to load details'))
  }
}

async function handleVote(voteType) {
  if (!detailData.value) return
  try {
    const res = await marketplaceApi.vote(detailData.value.id, voteType)
    if (res.code === 200) {
      detailData.value.likes = res.data.likes
      detailData.value.dislikes = res.data.dislikes
      detailData.value.user_vote = res.data.user_vote
      // 同步列表中的卡片数据
      const idx = items.value.findIndex(i => i.id === detailData.value.id)
      if (idx >= 0) {
        items.value[idx].likes = res.data.likes
        items.value[idx].dislikes = res.data.dislikes
      }
    }
  } catch (e) {
    ElMessage.error(t('投票失败', 'Vote failed'))
  }
}

async function handleAdopt() {
  if (!detailData.value) return
  try {
    const res = await marketplaceApi.adopt(detailData.value.id)
    if (res.code === 200) {
      ElMessage.success(t('已采用到人设列表', 'Adopted to your personas'))
      emit('adopted')
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || t('采用失败', 'Adopt failed'))
  }
}

async function loadComments() {
  if (!detailData.value) return
  commentsLoading.value = true
  try {
    const res = await marketplaceApi.comments(detailData.value.id, commentSort.value, 1)
    if (res.code === 200) {
      comments.value = res.data.items || []
      commentTotal.value = res.data.total || 0
    }
  } catch (e) {
    console.error('加载评论失败', e)
  } finally {
    commentsLoading.value = false
  }
}

async function submitComment() {
  if (!newComment.value.trim() || !detailData.value) return
  commentSubmitting.value = true
  try {
    const res = await marketplaceApi.addComment(detailData.value.id, newComment.value.trim())
    if (res.code === 200) {
      ElMessage.success(t('评论已发表', 'Comment posted'))
      newComment.value = ''
      loadComments()
    }
  } catch (e) {
    ElMessage.error(t('评论失败', 'Comment failed'))
  } finally {
    commentSubmitting.value = false
  }
}

async function handleLikeComment(comment) {
  try {
    const res = await marketplaceApi.likeComment(comment.id)
    if (res.code === 200) {
      comment.likes = res.data.likes
    }
  } catch (e) {
    ElMessage.error(t('点赞失败', 'Like failed'))
  }
}

async function handleAvatarUpload(file) {
  try {
    const res = await uploadApi.uploadImage(file)
    if (res.code === 200) {
      publishForm.avatar = res.data.url
    }
  } catch (e) {
    ElMessage.error(t('上传失败', 'Upload failed'))
  }
  return false
}

async function handlePublish() {
  if (!publishForm.name.trim() || !publishForm.system_prompt.trim()) {
    ElMessage.warning(t('请填写名称和系统提示词', 'Name and system prompt are required'))
    return
  }
  publishing.value = true
  try {
    const res = await marketplaceApi.publish({
      name: publishForm.name.trim(),
      description: publishForm.description.trim(),
      system_prompt: publishForm.system_prompt.trim(),
      greeting: publishForm.greeting.trim(),
      avatar: publishForm.avatar,
    })
    if (res.code === 200) {
      ElMessage.success(t('发布成功', 'Published'))
      showPublishDialog.value = false
      Object.assign(publishForm, { name: '', description: '', system_prompt: '', greeting: '', avatar: '' })
      loadList()
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || t('发布失败', 'Publish failed'))
  } finally {
    publishing.value = false
  }
}

function handleClose() {
  detailVisible.value = false
}

function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  const now = new Date()
  const diff = now - d
  if (diff < 60000) return t('刚刚', 'Just now')
  if (diff < 3600000) return `${Math.floor(diff / 60000)}${t('分钟前', 'm ago')}`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}${t('小时前', 'h ago')}`
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
</script>

<style scoped>
.marketplace {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 16px;
}

.mp-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;
}

.mp-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 14px;
  overflow-y: auto;
  flex: 1;
  padding: 4px;
}

.mp-card {
  background: var(--surface);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.mp-card:hover {
  border-color: var(--brand);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
  transform: translateY(-2px);
}

.card-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.card-info {
  min-width: 0;
  flex: 1;
}

.card-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-author {
  font-size: 11px;
  color: var(--text-muted);
}

.card-desc {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-footer {
  display: flex;
  gap: 12px;
  margin-top: auto;
}

.card-stat {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  color: var(--text-muted);
}

.card-stat.like .el-icon { color: #f59e0b; }
.card-stat.dislike .el-icon { color: #ef4444; }

.mp-empty {
  grid-column: 1 / -1;
  text-align: center;
  color: var(--text-muted);
  padding: 60px 20px;
  font-size: 14px;
}

.mp-pagination {
  display: flex;
  justify-content: center;
  flex-shrink: 0;
  padding-top: 8px;
}

/* 详情 */
.detail-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 14px;
}

.detail-meta h3 {
  margin: 0;
  font-size: 18px;
  color: var(--text-primary);
}

.detail-author {
  font-size: 13px;
  color: var(--text-muted);
}

.detail-desc {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin: 0;
}

.detail-prompt-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.prompt-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.prompt-box {
  background: var(--surface-hover);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 12px;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  max-height: 200px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.greeting-box {
  border-left: 3px solid var(--brand);
}

.detail-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

/* 评论区 */
.comments-section {
  border-top: 1px solid var(--border-color);
  padding-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.comments-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.comment-input {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.comment-input .el-input {
  flex: 1;
}

.comments-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 300px;
  overflow-y: auto;
}

.comment-item {
  padding: 10px 12px;
  background: var(--surface);
  border-radius: 8px;
  border: 1px solid var(--border-color);
}

.comment-user {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.comment-identicon {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--surface-hover);
}

.comment-pseudonym {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.comment-badge {
  font-size: 10px;
  background: var(--brand);
  color: white;
  padding: 1px 6px;
  border-radius: 8px;
}

.comment-text {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin: 0;
}

.comment-footer {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 6px;
}

.comment-time {
  font-size: 11px;
  color: var(--text-muted);
}

.no-comments {
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
  padding: 20px;
}

/* 发布表单头像预览 */
.publish-avatar-preview {
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
}

.upload-hint {
  font-size: 13px;
  color: var(--text-muted);
}

@media (max-width: 768px) {
  .mp-grid {
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 10px;
  }
  .detail-actions {
    flex-direction: column;
  }
}
</style>
