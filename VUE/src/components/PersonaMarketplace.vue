<template>
  <el-drawer
    v-model="visible"
    :title="t('卡片广场', 'Card Marketplace')"
    size="min(720px, 100vw)"
    direction="rtl"
    @close="handleClose"
  >
    <div class="marketplace">
      <!-- 顶部操作栏 -->
      <div class="mp-toolbar">
        <el-input
          v-model="searchKeyword"
          :placeholder="t('搜索卡片名称或描述...', 'Search cards...')"
          clearable
          size="default"
          style="width: 240px"
          @input="debouncedSearch"
          @clear="loadList"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <div class="toolbar-right">
          <el-radio-group v-model="sortMode" size="default" @change="loadList">
            <el-radio-button value="hot">{{ t('热门', 'Hot') }}</el-radio-button>
            <el-radio-button value="new">{{ t('最新', 'New') }}</el-radio-button>
          </el-radio-group>
          <el-button type="primary" size="small" @click="showPublishDialog = true">
            <el-icon><Plus /></el-icon> {{ t('发布卡片', 'Publish Card') }}
          </el-button>
        </div>
      </div>

      <!-- 卡片网格 -->
      <div v-loading="loading" class="mp-grid">
        <div
          v-for="item in items"
          :key="item.id"
          class="mp-card"
          @click="openDetail(item)"
        >
          <div class="card-image">
            <img v-if="item.avatar" :src="item.avatar" :alt="item.name" />
            <div v-else class="card-image-placeholder">
              <span>{{ item.name?.charAt(0) }}</span>
            </div>
            <div class="card-like-badge" @click.stop="handleCardVote(item, 'like')">
              <el-icon :class="{ active: item.user_vote === 'like' }"><Sunny /></el-icon>
              <span>{{ item.likes }}</span>
            </div>
          </div>
          <div class="card-body">
            <div class="card-name">{{ item.name }}</div>
            <p class="card-desc">{{ item.description }}</p>
            <div class="card-footer">
              <span class="card-stat">
                <el-icon><Sunny /></el-icon> {{ item.likes }}
              </span>
              <span v-if="item.is_adopted" class="card-adopted-tag">{{ t('已采用', 'Adopted') }}</span>
            </div>
          </div>
        </div>

        <div v-if="!loading && items.length === 0" class="mp-empty">
          {{ t('暂无卡片', 'No cards yet') }}
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

    <!-- 详情对话框：左右分栏 -->
    <el-dialog
      v-model="detailVisible"
      width="min(800px, 96vw)"
      align-center
      destroy-on-close
      class="detail-dialog"
      :show-close="true"
    >
      <template #header><span></span></template>
      <div v-if="detailData" class="detail-split">
        <!-- 左半区：固定 -->
        <div class="detail-left">
          <div class="dl-avatar">
            <img v-if="detailData.avatar" :src="detailData.avatar" :alt="detailData.name" />
            <div v-else class="dl-avatar-placeholder">{{ detailData.name?.charAt(0) }}</div>
          </div>
          <div class="dl-votes">
            <button
              class="vote-btn like-btn"
              :class="{ active: detailData.user_vote === 'like' }"
              @click="handleVote('like')"
            >
              <el-icon><Sunny /></el-icon>
              <span>{{ detailData.likes }}</span>
            </button>
            <button
              class="vote-btn dislike-btn"
              :class="{ active: detailData.user_vote === 'dislike' }"
              @click="handleVote('dislike')"
            >
              <el-icon class="thumb-down"><Sunny /></el-icon>
            </button>
          </div>
          <p class="dl-desc">{{ detailData.description }}</p>
          <div v-if="isCreator" class="dl-creator-actions">
            <el-button size="small" type="danger" plain @click="handleDeleteCard">
              {{ t('删除卡片', 'Delete Card') }}
            </el-button>
          </div>
        </div>

        <!-- 右半区：可滚动 -->
        <div class="detail-right">
          <h2 class="dr-name">{{ detailData.name }}</h2>
          <div class="dr-meta">
            <span>{{ t('创建时间', 'Created') }}: {{ formatDate(detailData.created_at) }}</span>
            <span><el-icon><Sunny /></el-icon> {{ detailData.likes }}</span>
          </div>

          <div class="dr-section">
            <div class="dr-label">{{ t('人设提示词', 'Character Prompt') }}</div>
            <div class="dr-box">{{ detailData.system_prompt }}</div>
          </div>

          <div v-if="detailData.greeting" class="dr-section">
            <div class="dr-label">{{ t('开场白', 'Greeting') }}</div>
            <div class="dr-box greeting-box">{{ detailData.greeting }}</div>
          </div>

          <!-- 评论区 -->
          <div class="dr-section comments-section">
            <div class="comments-header">
              <span>{{ t('评论', 'Comments') }} ({{ commentTotal }})</span>
              <el-radio-group v-model="commentSort" size="small" @change="loadComments">
                <el-radio-button value="hot">{{ t('热门', 'Hot') }}</el-radio-button>
                <el-radio-button value="new">{{ t('最新', 'New') }}</el-radio-button>
              </el-radio-group>
            </div>

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

            <div v-loading="commentsLoading" class="comments-list">
              <div v-for="c in comments" :key="c.id" class="comment-item">
                <div class="comment-user">
                  <img
                    :src="`https://api.dicebear.com/7.x/identicon/svg?seed=${c.identicon_seed}`"
                    class="comment-identicon"
                    alt=""
                  />
                  <span class="comment-pseudonym">{{ c.pseudonym }}</span>
                </div>
                <p class="comment-text">{{ c.content }}</p>
                <div class="comment-footer">
                  <span class="comment-time">{{ formatTime(c.created_at) }}</span>
                  <el-button text size="small" @click="handleLikeComment(c)">
                    <el-icon><Sunny /></el-icon> {{ c.likes }}
                  </el-button>
                </div>
              </div>
              <div v-if="!commentsLoading && comments.length === 0" class="no-comments">
                {{ t('暂无评论', 'No comments yet') }}
              </div>
            </div>
          </div>

          <!-- 采用按钮（底部固定） -->
          <div class="dr-bottom">
            <el-button
              v-if="!detailData.is_adopted"
              type="primary"
              size="large"
              class="adopt-btn"
              @click="handleAdopt"
            >
              {{ t('采用', 'Adopt') }}
            </el-button>
            <el-button v-else size="large" disabled class="adopt-btn">
              {{ t('已采用', 'Adopted') }}
            </el-button>
          </div>
        </div>
      </div>
    </el-dialog>

    <!-- 发布卡片对话框 -->
    <el-dialog
      v-model="showPublishDialog"
      :title="t('发布卡片', 'Publish Card')"
      width="min(500px, 95vw)"
      align-center
      destroy-on-close
    >
      <el-form :model="publishForm" label-position="top">
        <el-form-item :label="t('名称', 'Name')" required>
          <el-input v-model="publishForm.name" maxlength="30" show-word-limit />
        </el-form-item>
        <el-form-item :label="t('描述 (30-100字)', 'Description (30-100 chars)')" required>
          <el-input v-model="publishForm.description" type="textarea" :rows="2" :maxlength="100" show-word-limit />
        </el-form-item>
        <el-form-item :label="t('人设提示词 (100-800字)', 'Character Prompt (100-800 chars)')" required>
          <el-input v-model="publishForm.system_prompt" type="textarea" :rows="5" :maxlength="800" show-word-limit />
        </el-form-item>
        <el-form-item :label="t('开场白 (最多50字)', 'Greeting (max 50 chars)')" required>
          <el-input v-model="publishForm.greeting" type="textarea" :rows="2" :maxlength="50" show-word-limit />
        </el-form-item>
        <el-form-item :label="t('头像', 'Avatar')" required>
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
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Sunny, Search } from '@element-plus/icons-vue'
import { marketplaceApi, uploadApi } from '../utils/resAi'
import { t } from '../i18n'

const props = defineProps({
  modelValue: Boolean,
  currentUserId: { type: Number, default: null },
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
const searchKeyword = ref('')
const currentPage = ref(1)
const pageSize = 12
const total = ref(0)
const totalPages = computed(() => Math.ceil(total.value / pageSize))

let _searchTimer = null
function debouncedSearch() {
  clearTimeout(_searchTimer)
  _searchTimer = setTimeout(() => {
    currentPage.value = 1
    loadList()
  }, 300)
}

// 详情状态
const detailVisible = ref(false)
const detailData = ref(null)
const isCreator = computed(() =>
  detailData.value && props.currentUserId && detailData.value.author_id === props.currentUserId
)

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
    const res = await marketplaceApi.list(sortMode.value, currentPage.value, searchKeyword.value.trim())
    if (res.code === 200) {
      items.value = res.data.items || []
      total.value = res.data.total || 0
    }
  } catch (e) {
    console.error('加载卡片广场失败', e)
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
      const idx = items.value.findIndex(i => i.id === detailData.value.id)
      if (idx >= 0) {
        items.value[idx].likes = res.data.likes
        items.value[idx].user_vote = res.data.user_vote
      }
    }
  } catch (e) {
    ElMessage.error(t('投票失败', 'Vote failed'))
  }
}

async function handleCardVote(item, voteType) {
  try {
    const res = await marketplaceApi.vote(item.id, voteType)
    if (res.code === 200) {
      item.likes = res.data.likes
      item.user_vote = res.data.user_vote
    }
  } catch (e) { /* silent */ }
}

async function handleAdopt() {
  if (!detailData.value) return
  try {
    const res = await marketplaceApi.adopt(detailData.value.id)
    if (res.code === 200) {
      if (res.data?.already) {
        ElMessage.info(t('已经采用过该卡片', 'Already adopted'))
      } else {
        ElMessage.success(t('已采用到人设列表', 'Adopted to your personas'))
      }
      detailData.value.is_adopted = true
      const idx = items.value.findIndex(i => i.id === detailData.value.id)
      if (idx >= 0) items.value[idx].is_adopted = true
      emit('adopted')
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || t('采用失败', 'Adopt failed'))
  }
}

async function handleDeleteCard() {
  if (!detailData.value) return
  try {
    await ElMessageBox.confirm(t('确定删除这张卡片吗？', 'Delete this card?'), t('确认', 'Confirm'), {
      type: 'warning',
    })
    const res = await marketplaceApi.delete(detailData.value.id)
    if (res.code === 200) {
      ElMessage.success(t('已删除', 'Deleted'))
      detailVisible.value = false
      loadList()
    }
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error(e.response?.data?.message || t('删除失败', 'Delete failed'))
    }
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

function formatDate(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
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
  gap: 12px;
  flex-wrap: wrap;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
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
  cursor: pointer;
  transition: all 0.2s;
  overflow: hidden;
}

.mp-card:hover {
  border-color: var(--brand);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
  transform: translateY(-2px);
}

.card-image {
  position: relative;
  width: 100%;
  aspect-ratio: 3/4;
  overflow: hidden;
  background: var(--surface-hover);
}

.card-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.card-image-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 32px;
  color: var(--text-muted);
  background: var(--surface-hover);
}

.card-like-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  display: flex;
  align-items: center;
  gap: 3px;
  background: rgba(0, 0, 0, 0.5);
  color: white;
  padding: 3px 8px;
  border-radius: 12px;
  font-size: 12px;
  cursor: pointer;
  backdrop-filter: blur(4px);
}

.card-like-badge .el-icon.active {
  color: #fbbf24;
}

.card-body {
  padding: 10px 12px 12px;
}

.card-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-desc {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.4;
  margin: 0 0 8px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-stat {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  color: var(--text-muted);
}

.card-adopted-tag {
  font-size: 11px;
  color: var(--brand);
  font-weight: 500;
}

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

/* ===== 详情对话框：左右分栏 ===== */
.detail-split {
  display: flex;
  min-height: 500px;
  max-height: 75vh;
}

.detail-left {
  width: 280px;
  flex-shrink: 0;
  padding: 20px;
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.dl-avatar {
  width: 200px;
  height: 260px;
  border-radius: 12px;
  overflow: hidden;
  background: var(--surface-hover);
}

.dl-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.dl-avatar-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 48px;
  color: var(--text-muted);
}

.dl-votes {
  display: flex;
  gap: 10px;
}

.vote-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 14px;
  border-radius: 20px;
  border: 1px solid var(--border-color);
  background: var(--surface);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.vote-btn:hover {
  border-color: var(--brand);
}

.like-btn.active {
  background: #fef3c7;
  border-color: #f59e0b;
  color: #f59e0b;
}

.dislike-btn.active {
  background: #fee2e2;
  border-color: #ef4444;
  color: #ef4444;
}

.thumb-down {
  transform: rotate(180deg);
}

.dl-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
  text-align: center;
  margin: 0;
}

.dl-creator-actions {
  margin-top: auto;
}

.detail-right {
  flex: 1;
  padding: 20px 24px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.dr-name {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
}

.dr-meta {
  display: flex;
  gap: 16px;
  font-size: 13px;
  color: var(--text-muted);
}

.dr-meta span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.dr-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.dr-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.dr-box {
  background: var(--surface-hover);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 12px;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.greeting-box {
  border-left: 3px solid var(--brand);
}

.dr-bottom {
  margin-top: auto;
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
}

.adopt-btn {
  width: 100%;
}

/* 评论区 */
.comments-section {
  border-top: 1px solid var(--border-color);
  padding-top: 16px;
}

.comments-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 12px;
}

.comment-input {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  margin-bottom: 12px;
}

.comment-input .el-input {
  flex: 1;
}

.comments-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
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
  margin-bottom: 4px;
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

.comment-text {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin: 0;
}

.comment-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
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
  .detail-split {
    flex-direction: column;
    max-height: none;
  }
  .detail-left {
    width: 100%;
    border-right: none;
    border-bottom: 1px solid var(--border-color);
    padding: 16px;
  }
  .dl-avatar {
    width: 140px;
    height: 180px;
  }
}
</style>
