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
        <el-select
          v-model="genderFilter"
          :placeholder="t('性别', 'Gender')"
          clearable
          size="default"
          style="width: 110px"
          @change="applyGenderFilter"
        >
          <el-option :label="t('男', 'Male')" value="男" />
          <el-option :label="t('女', 'Female')" value="女" />
          <el-option :label="t('非二元', 'Non-binary')" value="非二元" />
        </el-select>
        <div class="toolbar-right">
          <!-- 排序方式（下拉框）：
            - hot：热门（赞比例）
            - new：最新
            - most_likes：点赞数最多
            - most_comments：评论数最多
            - most_disliked：最不受欢迎（踩远多于赞） -->
          <el-select
            v-model="sortMode"
            size="default"
            style="width: 150px"
            @change="loadList"
          >
            <el-option :label="t('热门', 'Hot')" value="hot" />
            <el-option :label="t('最新', 'Newest')" value="new" />
            <el-option :label="t('点赞最多', 'Most likes')" value="most_likes" />
            <el-option :label="t('评论最多', 'Most comments')" value="most_comments" />
            <el-option :label="t('最不受欢迎', 'Most disliked')" value="most_disliked" />
          </el-select>
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
            <img v-if="item.avatar" :src="item.avatar" :alt="item.name" loading="lazy" decoding="async" />
            <div v-else class="card-image-placeholder">
              <span>{{ item.name?.charAt(0) }}</span>
            </div>
            <span v-if="item.gender_tag" class="card-gender-tag" :class="{ nb: item.gender_tag === '非二元' }">
              {{ item.gender_tag }}
            </span>
          </div>
          <div class="card-body">
            <div class="card-name">{{ item.name }}</div>
            <p class="card-desc">{{ item.description }}</p>
            <div class="card-footer">
              <div class="card-stats">
                <span
                  class="card-stat like"
                  :class="{ active: item.user_vote === 'like' }"
                  :title="t('赞', 'Like')"
                  @click.stop="handleCardVote(item, 'like')"
                >
                  <ThumbIcon :size="14" /> {{ formatCount(item.likes) }}
                </span>
                <span
                  class="card-stat dislike"
                  :class="{ active: item.user_vote === 'dislike' }"
                  :title="t('踩', 'Dislike')"
                  @click.stop="handleCardVote(item, 'dislike')"
                >
                  <ThumbIcon :size="14" down /> {{ formatCount(item.dislikes) }}
                </span>
                <span
                  class="card-stat comments"
                  :title="t('评论数', 'Comments')"
                >
                  <el-icon><ChatLineRound /></el-icon> {{ formatCount(item.comment_count || 0) }}
                </span>
              </div>
              <span v-if="item.is_adopted" class="card-adopted-tag">{{ t('已添加', 'Added') }}</span>
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
          <div class="dl-avatar" @click="openImagePreview(detailData.avatar)" :class="{ 'is-clickable': !!detailData.avatar }">
            <img v-if="detailData.avatar" :src="detailData.avatar" :alt="detailData.name" decoding="async" />
            <div v-else class="dl-avatar-placeholder">{{ detailData.name?.charAt(0) }}</div>
            <div v-if="detailData.avatar" class="dl-avatar-zoom">
              <el-icon><ZoomIn /></el-icon>
            </div>
          </div>
          <div class="dl-votes">
            <button
              class="vote-btn like-btn"
              :class="{ active: detailData.user_vote === 'like' }"
              :title="t('赞', 'Like')"
              @click="handleVote('like')"
            >
              <ThumbIcon :size="18" />
              <span class="vote-count">{{ formatCount(detailData.likes) }}</span>
            </button>
            <button
              class="vote-btn dislike-btn"
              :class="{ active: detailData.user_vote === 'dislike' }"
              :title="t('踩', 'Dislike')"
              @click="handleVote('dislike')"
            >
              <ThumbIcon :size="18" down />
              <span class="vote-count">{{ formatCount(detailData.dislikes) }}</span>
            </button>
            <div class="vote-btn comments-btn" :title="t('评论数', 'Comments')">
              <el-icon><ChatLineRound /></el-icon>
              <span class="vote-count">{{ formatCount(detailData.comment_count || 0) }}</span>
            </div>
          </div>
          <p class="dl-desc">{{ detailData.description }}</p>
          <div class="dl-creator-info">
            <img
              :src="identiconDataUrl(detailData.creator_identicon_seed, 24)"
              class="dl-creator-icon"
              alt=""
              decoding="async"
            />
            <span class="dl-creator-name">{{ detailData.creator_pseudonym }}</span>
          </div>
          <div v-if="isCreator" class="dl-creator-actions">
            <el-button size="small" type="danger" plain @click="handleDeleteCard">
              {{ t('删除卡片', 'Delete Card') }}
            </el-button>
          </div>
        </div>

        <!-- 右半区：上方内容可滚动，底部添加按钮固定 -->
        <div class="detail-right">
          <div class="dr-scroll">
          <h2 class="dr-name">{{ detailData.name }}</h2>
          <div class="dr-meta">
            <span>{{ t('创建时间', 'Created') }}: {{ formatDate(detailData.created_at) }}</span>
            <span class="dr-meta-stats">
              <ThumbIcon :size="13" /> {{ detailData.likes }}
              ·
              <ThumbIcon :size="13" down /> {{ detailData.dislikes }}
            </span>
          </div>

          <div class="dr-section">
            <div class="dr-label dr-label-row">
              <span>{{ t('人设提示词', 'Character Prompt') }}</span>
              <button
                type="button"
                class="dr-prompt-toggle"
                @click="promptExpanded = !promptExpanded"
              >
                {{ promptExpanded
                    ? t('收起', 'Collapse')
                    : t('展开全文', 'Expand all') }}
              </button>
            </div>
            <div
              class="dr-box dr-prompt-box"
              :class="{ collapsed: !promptExpanded }"
              @click="!promptExpanded && (promptExpanded = true)"
            >
              {{ detailData.system_prompt }}
            </div>
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
              <div v-if="replyTarget" class="reply-hint">
                <span>{{ t('回复', 'Replying to') }} <b>{{ replyTarget.label }}</b></span>
                <el-button text size="small" @click="cancelReply">{{ t('取消', 'Cancel') }}</el-button>
              </div>
              <el-input
                v-model="newComment"
                :placeholder="replyPlaceholder"
                maxlength="500"
                show-word-limit
                type="textarea"
                :rows="2"
                :autosize="false"
                resize="none"
                class="fixed-textarea"
              />
              <el-button type="primary" size="small" :disabled="!newComment.trim()" @click="submitComment" :loading="commentSubmitting">
                {{ replyTarget ? t('回复', 'Reply') : t('发表', 'Post') }}
              </el-button>
            </div>

            <div v-loading="commentsLoading" class="comments-list">
              <div v-for="c in comments" :key="c.id" class="comment-item comment-top">
                <div class="comment-user">
                  <img
                    :src="identiconDataUrl(c.identicon_seed, 28)"
                    class="comment-identicon"
                    alt=""
                    loading="lazy"
                    decoding="async"
                  />
                  <span class="comment-pseudonym">{{ c.pseudonym }}</span>
                </div>
                <p class="comment-text">{{ c.content }}</p>
                <div class="comment-footer">
                  <span class="comment-time">{{ formatTime(c.created_at) }}</span>
                  <el-button
                    text
                    size="small"
                    :class="{ 'is-liked': c.liked }"
                    @click="handleLikeComment(c)"
                  >
                    <el-icon><Sunny /></el-icon> {{ c.likes }}
                  </el-button>
                  <el-button text size="small" @click="startReply(c, null)">
                    {{ t('回复', 'Reply') }}
                  </el-button>
                </div>

                <!-- 子回复：最多嵌套一层，默认只展示 3 条，其余折叠 -->
                <div v-if="c.replies && c.replies.length" class="reply-list">
                  <div v-for="r in visibleReplies(c)" :key="r.id" class="reply-item">
                    <img
                      :src="identiconDataUrl(r.identicon_seed, 22)"
                      class="comment-identicon reply-identicon"
                      alt=""
                      loading="lazy"
                      decoding="async"
                    />
                    <div class="reply-main">
                      <div class="reply-head">
                        <span class="comment-pseudonym">{{ r.pseudonym }}</span>
                        <span class="reply-to">
                          {{ t('回复', 'reply to') }}
                          {{ r.reply_to_name || t('该评论', 'this comment') }}
                        </span>
                      </div>
                      <p class="comment-text">{{ r.content }}</p>
                      <div class="comment-footer">
                        <span class="comment-time">{{ formatTime(r.created_at) }}</span>
                        <el-button
                          text
                          size="small"
                          :class="{ 'is-liked': r.liked }"
                          @click="handleLikeComment(r)"
                        >
                          <el-icon><Sunny /></el-icon> {{ r.likes }}
                        </el-button>
                        <el-button text size="small" @click="startReply(c, r)">
                          {{ t('回复', 'Reply') }}
                        </el-button>
                      </div>
                    </div>
                  </div>

                  <button
                    v-if="c.replies.length > REPLY_PREVIEW"
                    type="button"
                    class="reply-toggle"
                    @click.stop="toggleReplies(c)"
                  >
                    {{ isExpanded(c.id)
                      ? t('收起回复', 'Collapse replies')
                      : `${t('展开其余', 'Show')} ${c.replies.length - REPLY_PREVIEW} ${t('条回复', 'more replies')}` }}
                  </button>
                </div>
              </div>
              <div v-if="!commentsLoading && comments.length === 0" class="no-comments">
                {{ t('暂无评论', 'No comments yet') }}
              </div>
            </div>
          </div>

          </div>

          <!-- 添加按钮：固定在详情底部，不随内容滚动 -->
          <div class="dr-bottom">
            <el-button
              v-if="!detailData.is_adopted"
              type="primary"
              size="large"
              class="adopt-btn"
              @click="handleAdopt"
            >
              {{ t('添加', 'Add') }}
            </el-button>
            <el-button v-else size="large" disabled class="adopt-btn">
              {{ t('已添加', 'Added') }}
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
          <el-input v-model="publishForm.description" type="textarea" :rows="2" :maxlength="100" show-word-limit resize="none" />
        </el-form-item>
        <el-form-item :label="t('人物卡性别', 'Gender')" required>
          <div class="gender-picker">
            <el-radio-group v-model="publishForm.gender">
              <el-radio-button value="男">{{ t('男', 'Male') }}</el-radio-button>
              <el-radio-button value="女">{{ t('女', 'Female') }}</el-radio-button>
              <el-radio-button value="神秘">{{ t('神秘', 'Mystery') }}</el-radio-button>
              <el-radio-button value="自定义">{{ t('自定义', 'Custom') }}</el-radio-button>
            </el-radio-group>
            <el-input
              v-if="publishForm.gender === '自定义'"
              v-model="publishForm.genderCustom"
              :placeholder="t('输入自定义性别（筛选时归入非二元）', 'Custom gender (grouped as non-binary)')"
              maxlength="20"
              class="gender-custom-input"
            />
          </div>
        </el-form-item>
        <el-form-item :label="t('人设提示词 (100-800字)', 'Character Prompt (100-800 chars)')" required>
          <el-input v-model="publishForm.system_prompt" type="textarea" :rows="5" :maxlength="800" show-word-limit resize="none" />
        </el-form-item>
        <el-form-item :label="t('开场白 (最多50字)', 'Greeting (max 50 chars)')" required>
          <el-input v-model="publishForm.greeting" type="textarea" :rows="2" :maxlength="50" show-word-limit resize="none" />
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

    <!-- 头像大图预览：点击详情页的头像后弹出，与聊天大图预览体验一致 -->
    <el-image-viewer
      v-if="previewImageVisible && previewImageUrl"
      :url-list="[previewImageUrl]"
      :zoom-rate="1.2"
      hide-on-click-modal
      @close="previewImageVisible = false"
    />
  </el-drawer>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Sunny, Search, ZoomIn, ChatLineRound } from '@element-plus/icons-vue'
import { marketplaceApi, uploadApi } from '../utils/resAi'
import { t } from '../i18n'
import ThumbIcon from './ThumbIcon.vue'
import { identiconDataUrl } from '../utils/identicon'

// 千位 k 计数：>= 1000 显示为 1k / 1.5k / 12k / 123k / 1.2m（百万）
// 例如 1000 -> 1k，1500 -> 1.5k，10000 -> 10k，1500000 -> 1.5m
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

const props = defineProps({
  modelValue: Boolean,
  currentUserId: { type: Number, default: null },
  // 人物卡列表版本号：人物卡增删改后由主页面自增，用于实时刷新「已添加」状态
  personaVersion: { type: Number, default: 0 },
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
// 性别筛选：'' 全部 / 男 / 女 / 非二元（自定义及未设置统一归入非二元）
const genderFilter = ref('')
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

function applyGenderFilter() {
  currentPage.value = 1
  loadList()
}

// 详情状态
const detailVisible = ref(false)
const detailData = ref(null)
// 人设提示词默认收起：长文一进来就铺满整个右半区体验差，
// 默认只露一行 + 渐变，点击「展开全文」才显示完整内容
const promptExpanded = ref(false)
// 打开详情时重置 promptExpanded，避免上一次会话的状态残留
watch(detailVisible, (val) => {
  if (val) promptExpanded.value = false
})
const isCreator = computed(() =>
  detailData.value && props.currentUserId && detailData.value.author_id === props.currentUserId
)

// 大图预览：点击详情页头像后打开 el-image-viewer 全屏预览
const previewImageVisible = ref(false)
const previewImageUrl = ref('')
function openImagePreview(url) {
  if (!url) return
  previewImageUrl.value = url
  previewImageVisible.value = true
}

// 评论状态
const comments = ref([])
const commentsLoading = ref(false)
const commentSort = ref('hot')
const commentTotal = ref(0)
const newComment = ref('')
const commentSubmitting = ref(false)

// 评论最多嵌套一层；顶层评论下的回复默认只展示 3 条，其余折叠可展开
const REPLY_PREVIEW = 3
const expandedReplyIds = ref([])
const replyTarget = ref(null) // { topId, replyToId, label }

const replyPlaceholder = computed(() => {
  if (replyTarget.value) {
    return `${t('回复', 'Reply to')} ${replyTarget.value.label}：${t('写下你的评论...', 'Write a comment...')}`
  }
  return t('写下你的评论...', 'Write a comment...')
})

function isExpanded(id) {
  return expandedReplyIds.value.includes(id)
}

function toggleReplies(c) {
  if (isExpanded(c.id)) {
    expandedReplyIds.value = expandedReplyIds.value.filter(x => x !== c.id)
  } else {
    expandedReplyIds.value = [...expandedReplyIds.value, c.id]
  }
}

function visibleReplies(c) {
  if (!c.replies) return []
  return isExpanded(c.id) ? c.replies : c.replies.slice(0, REPLY_PREVIEW)
}

// 回复顶层评论 -> 显示「回复该评论」；回复子评论 -> 显示「回复 <那个人>」
function startReply(top, reply) {
  replyTarget.value = {
    topId: top.id,
    replyToId: reply ? reply.id : top.id,
    label: reply ? reply.pseudonym : t('该评论', 'this comment'),
  }
}

function cancelReply() {
  replyTarget.value = null
}

// 发布状态
const showPublishDialog = ref(false)
const publishing = ref(false)
const publishForm = reactive({
  name: '',
  description: '',
  system_prompt: '',
  greeting: '',
  avatar: '',
  gender: '',        // 男 / 女 / 自定义
  genderCustom: '',  // 自定义性别文本（非男非女，筛选归入非二元）
})

// 实际提交的性别值：自定义模式下取文本（留空则由后端归入非二元）
const effectiveGender = () =>
  publishForm.gender === '自定义' ? publishForm.genderCustom.trim() : (publishForm.gender || '')

watch(() => props.modelValue, (val) => {
  if (val) loadList()
})

// 人物卡列表变化（如删除已添加的人物卡）后，实时刷新卡片的「已添加」状态
watch(() => props.personaVersion, () => {
  if (visible.value) loadList()
  if (detailData.value) refreshDetailAdoptState()
})

// 重新拉取当前详情的添加状态，避免详情页停留在旧的「已添加」
async function refreshDetailAdoptState() {
  if (!detailData.value) return
  try {
    const res = await marketplaceApi.get(detailData.value.id)
    if (res.code === 200 && detailData.value?.id === res.data.id) {
      detailData.value.is_adopted = res.data.is_adopted
    }
  } catch (e) { /* silent */ }
}

async function loadList() {
  loading.value = true
  try {
    const res = await marketplaceApi.list(sortMode.value, currentPage.value, searchKeyword.value.trim(), genderFilter.value)
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
    if (res.code === 200 && res.data) {
      // 后端支持「再次点击即取消」，user_vote 直接以接口返回为准
      const { likes, dislikes, user_vote } = res.data
      detailData.value.likes = likes
      detailData.value.dislikes = dislikes
      detailData.value.user_vote = user_vote || null
      const idx = items.value.findIndex(i => i.id === detailData.value.id)
      if (idx >= 0) {
        items.value[idx].likes = likes
        items.value[idx].dislikes = dislikes
        items.value[idx].user_vote = user_vote || null
      }
    }
  } catch (e) {
    ElMessage.error(t('投票失败', 'Vote failed'))
  }
}

async function handleCardVote(item, voteType) {
  try {
    const res = await marketplaceApi.vote(item.id, voteType)
    if (res.code === 200 && res.data) {
      const { likes, dislikes, user_vote } = res.data
      item.likes = likes
      item.dislikes = dislikes
      item.user_vote = user_vote || null
    }
  } catch (e) { /* silent */ }
}

async function handleAdopt() {
  if (!detailData.value) return
  try {
    const res = await marketplaceApi.adopt(detailData.value.id)
    if (res.code === 200) {
      if (res.data?.already) {
        ElMessage.info(t('已添加过该卡片', 'Already added'))
      } else {
        ElMessage.success(t('已添加到人物卡管理', 'Added to your persona cards'))
      }
      detailData.value.is_adopted = true
      const idx = items.value.findIndex(i => i.id === detailData.value.id)
      if (idx >= 0) items.value[idx].is_adopted = true
      emit('adopted')
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || t('添加失败', 'Add failed'))
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
  const target = replyTarget.value
  commentSubmitting.value = true
  try {
    const res = await marketplaceApi.addComment(
      detailData.value.id,
      newComment.value.trim(),
      target ? target.topId : null,
      target ? target.replyToId : null
    )
    if (res.code === 200) {
      ElMessage.success(target ? t('回复已发表', 'Reply posted') : t('评论已发表', 'Comment posted'))
      newComment.value = ''
      // 新回复发布后自动展开该条评论，避免回复被折叠看不到
      if (target && !isExpanded(target.topId)) {
        expandedReplyIds.value = [...expandedReplyIds.value, target.topId]
      }
      replyTarget.value = null
      loadComments()
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || t('评论失败', 'Comment failed'))
  } finally {
    commentSubmitting.value = false
  }
}

// 再次点击即取消点赞
async function handleLikeComment(comment) {
  try {
    const res = await marketplaceApi.toggleCommentLike(comment.id)
    if (res.code === 200) {
      comment.likes = res.data.likes
      comment.liked = res.data.liked
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
  if (!publishForm.gender) {
    ElMessage.warning(t('请选择人物卡性别', 'Please choose a gender'))
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
      gender: effectiveGender(),
    })
    if (res.code === 200) {
      ElMessage.success(t('发布成功', 'Published'))
      showPublishDialog.value = false
      Object.assign(publishForm, { name: '', description: '', system_prompt: '', greeting: '', avatar: '', gender: '', genderCustom: '' })
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
  /* 更窄的最小列宽 + 更小间距 => 同屏展示更多卡片，以图片为主 */
  grid-template-columns: repeat(auto-fill, minmax(158px, 1fr));
  /* 行高按最高卡片自适应，但卡片本身不拉伸：body 不再使用 flex:1，
     卡片高度 = 图片高度 + body 内容高度，避免点赞下方出现大片内部空白。 */
  grid-auto-rows: max-content;
  align-items: start;
  gap: 10px;
  overflow-y: auto;
  flex: 1;
  padding: 4px;
}

.mp-card {
  /* width:0 + min-width:0 是 grid 内让子项正确收缩的关键，
     否则长文本会把卡片撑宽并溢出网格 */
  width: 0;
  min-width: 100%;
  background: var(--surface);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s;
  overflow: hidden;
  display: flex;
  flex-direction: column;
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

/* 卡片左上角性别标签 */
.card-gender-tag {
  position: absolute;
  top: 6px;
  left: 6px;
  z-index: 1;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 11px;
  line-height: 1.6;
  color: #fff;
  background: rgba(76, 130, 201, 0.85);
  backdrop-filter: blur(2px);
  pointer-events: none;
}

.card-gender-tag.nb {
  background: rgba(154, 106, 187, 0.85);
}

.gender-picker {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  flex-wrap: wrap;
}

.gender-custom-input {
  flex: 1;
  min-width: 160px;
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

/* 信息区：名称 / 描述(占 2 行) / 统计，天然流式排列，
   配合卡片在网格中自动等高拉伸，所有卡片信息区高度完全一致。
   整体收紧内边距与行距，减少图片下方的空白占位 */
.card-body {
  padding: 7px 9px 8px;
  /* 不拉伸 body：body 由内容撑高，避免点赞下方空出一大片内部空白 */
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
}

.card-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.25;
  margin-bottom: 3px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 固定占 2 行高度：描述短也不会让卡片塌陷，高度与长描述卡片一致 */
.card-desc {
  font-size: 11.5px;
  color: var(--text-secondary);
  line-height: 1.35;
  margin: 0;
  display: -webkit-box;
  /* 描述最多展示 2 行，超出截断，完整内容进入卡片详情查看 */
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
  /* 固定占 2 行高度：描述短也不会让卡片塌陷，高度与长描述卡片一致 */
  min-height: calc(1.35em * 2);
  margin-bottom: 4px;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 18px;
}

.card-stats {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.card-stat {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  color: var(--text-muted);
  cursor: pointer;
}

.card-stat:hover {
  color: var(--brand);
}

.card-stat.like.active {
  color: #f59e0b;
  font-weight: 600;
}

.card-stat.dislike.active {
  color: #ef4444;
  font-weight: 600;
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
  /* 左侧信息（头像/赞踩/描述/创作者）固定不动，内容过多时自身滚动 */
  overflow-y: auto;
}

.dl-avatar {
  width: 200px;
  height: 260px;
  border-radius: 12px;
  overflow: hidden;
  background: var(--surface-hover);
  position: relative;
  cursor: zoom-in;
  transition: transform 0.2s;
}

.dl-avatar.is-clickable:hover {
  transform: scale(1.02);
}

.dl-avatar-zoom {
  position: absolute;
  bottom: 8px;
  right: 8px;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  pointer-events: none;
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
  gap: 6px;
  padding: 6px 16px;
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

.vote-btn .vote-emoji {
  font-size: 17px;
  line-height: 1;
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

.dl-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
  text-align: center;
  margin: 0;
}

.dl-creator-info {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 12px;
}

.dl-creator-icon {
  width: 24px;
  height: 24px;
  border-radius: 50%;
}

.dl-creator-name {
  font-size: 12px;
  color: var(--text-secondary);
}

.dl-creator-actions {
  margin-top: auto;
}

.detail-right {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 右半区滚动内容：人设提示词/开场白/评论区，添加按钮固定在其下方 */
.dr-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 20px 24px;
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

/* 人物提示词折叠样式：
   - 收起态：限高 + 渐变遮罩，提示「还有更多内容」
   - 展开态：完整展示，不限高 */
.dr-prompt-box.collapsed {
  max-height: 96px;
  overflow: hidden;
  position: relative;
  cursor: pointer;
  -webkit-mask-image: linear-gradient(to bottom, #000 60%, rgba(0, 0, 0, 0) 100%);
  mask-image: linear-gradient(to bottom, #000 60%, rgba(0, 0, 0, 0) 100%);
}

.dr-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.dr-prompt-toggle {
  background: none;
  border: none;
  padding: 0;
  font-size: 12px;
  color: var(--brand);
  cursor: pointer;
  font-weight: 500;
}

.dr-prompt-toggle:hover {
  text-decoration: underline;
}

/* 评论数显示（卡片列表 + 详情页共用，与点赞/踩风格一致） */
.comments-btn {
  cursor: default;
  pointer-events: none;
  color: var(--text-muted);
}

.card-stat.comments {
  cursor: default;
  pointer-events: none;
  color: var(--text-muted);
}

.greeting-box {
  border-left: 3px solid var(--brand);
}

.dr-bottom {
  flex-shrink: 0;
  padding: 12px 24px 16px;
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
  position: relative;
  display: flex;
  gap: 8px;
  align-items: flex-start;
  margin-bottom: 12px;
}

.comment-input .el-input {
  flex: 1;
}

/* 评论输入框：固定行数不可拉伸，超出后滚动 */
.comment-input :deep(textarea.el-textarea__inner) {
  resize: none;
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
  gap: 10px;
  margin-top: 6px;
}

.comment-time {
  font-size: 11px;
  color: var(--text-muted);
  margin-right: auto;
}

/* 已点赞状态：高亮 + 实心感，再次点击可取消 */
.comment-footer :deep(.el-button.is-liked) {
  color: var(--brand, #b06a2e);
  font-weight: 600;
}

.comment-footer :deep(.el-button) {
  padding: 0;
  height: auto;
}

.reply-hint {
  position: absolute;
  top: -22px;
  left: 0;
  right: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-muted, #8a6a48);
}

.reply-list {
  margin-top: 8px;
  padding-left: 10px;
  border-left: 2px solid var(--border-color);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.reply-item {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.reply-identicon {
  width: 20px;
  height: 20px;
  flex: none;
  margin-top: 2px;
}

.reply-main {
  flex: 1;
  min-width: 0;
}

.reply-head {
  display: flex;
  align-items: baseline;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 2px;
}

.reply-to {
  font-size: 11px;
  color: var(--text-muted);
}

.reply-toggle {
  align-self: flex-start;
  background: none;
  border: none;
  padding: 2px 0;
  font-size: 12px;
  color: var(--brand, #b06a2e);
  cursor: pointer;
}

.reply-toggle:hover {
  text-decoration: underline;
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
    grid-template-columns: repeat(auto-fill, minmax(132px, 1fr));
    gap: 8px;
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
    overflow-y: visible;
  }
  .dl-avatar {
    width: 140px;
    height: 180px;
  }
  .dr-scroll {
    padding: 16px;
  }
  .dr-bottom {
    padding: 12px 16px 16px;
  }
}
</style>
