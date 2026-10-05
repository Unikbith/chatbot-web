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
          class="mp-search"
          @input="debouncedSearch"
          @clear="loadList"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-select
          v-model="genderFilter"
          :placeholder="t('类型', 'Type')"
          clearable
          size="default"
          class="mp-gender"
          @change="applyGenderFilter"
        >
          <!-- 只渲染实际存在卡片的性别：没有对应卡片的选项不显示，
               避免用户点了得到空列表。顺序：男 → 女 → 其他具体类型 -->
          <el-option
            v-for="opt in genderOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          >
            <span class="gender-opt-label">{{ opt.label }}</span>
            <span class="gender-opt-count">{{ opt.count }}</span>
          </el-option>
        </el-select>
        <div class="toolbar-right">
          <!-- 排序方式（下拉框）：
            - hot：热门（赞比例）
            - new：最新
            - most_likes：点赞数最多
            - most_comments：评论数最多 -->
          <el-select
            v-model="sortMode"
            size="default"
            class="mp-sort"
            @change="loadList"
          >
            <el-option :label="t('热门', 'Hot')" value="hot" />
            <el-option :label="t('最新', 'Newest')" value="new" />
            <el-option :label="t('点赞最多', 'Most likes')" value="most_likes" />
            <el-option :label="t('评论最多', 'Most comments')" value="most_comments" />
          </el-select>
          <el-button type="primary" size="small" @click="showPublishDialog = true">
            <el-icon><Plus /></el-icon> {{ t('发布卡片', 'Publish Card') }}
          </el-button>
        </div>
      </div>

      <!-- 卡片网格：滚动到底部自动加载下一页 -->
      <div ref="gridRef" v-loading="loading" class="mp-grid">
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
                <!-- 带世界书的卡片打个标记：一眼看出这张卡随卡分享了设定 -->
                <span
                  v-if="item.worldbook_count > 0"
                  class="card-stat wb"
                  :title="t(`随卡带 ${item.worldbook_count} 条世界书设定`, `Ships with ${item.worldbook_count} worldbook entries`)"
                >
                  <el-icon><Notebook /></el-icon> {{ item.worldbook_count }}
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
          <div v-if="detailData.can_edit" class="dl-creator-actions">
            <el-button size="small" plain @click="openEditDialog">
              {{ t('编辑', 'Edit') }}
            </el-button>
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

          <!-- 与人物卡对齐：玩家设定（你是谁）与世界书（按需注入的设定） -->
          <div v-if="detailData.user_prompt" class="dr-section">
            <div class="dr-label">{{ t('玩家设定', 'Player Setup') }}</div>
            <div class="dr-box">{{ detailData.user_prompt }}</div>
          </div>

          <div v-if="detailData.worldbook && detailData.worldbook.length" class="dr-section">
            <div class="dr-label">
              {{ t('世界书', 'Worldbook') }} ({{ detailData.worldbook.length }})
            </div>
            <div class="dr-wb-list">
              <div v-for="(e, i) in detailData.worldbook" :key="i" class="dr-wb-item">
                <div class="dr-wb-head">
                  <span class="dr-wb-title">{{ e.title || t('未命名条目', 'Untitled') }}</span>
                  <span class="dr-wb-tag">{{ e.always_on ? t('常驻', 'Always') : t('按需', 'On demand') }}</span>
                </div>
                <div v-if="e.keywords" class="dr-wb-kw">
                  {{ t('触发词', 'Keywords') }}：{{ e.keywords }}
                </div>
                <div class="dr-box dr-wb-content">{{ e.content }}</div>
              </div>
            </div>
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
                :placeholder="t('写下你对这张人物卡的评论...', 'Write a comment on this persona...')"
                maxlength="500"
                show-word-limit
                type="textarea"
                :rows="2"
                :autosize="false"
                resize="none"
                class="fixed-textarea"
              />
              <el-button type="primary" size="small" :disabled="!newComment.trim()" @click="submitComment" :loading="commentSubmitting">
                {{ t('发表', 'Post') }}
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
                </div>
              </div>
              <div v-if="!commentsLoading && comments.length === 0" class="no-comments">
                {{ t('暂无评论', 'No comments yet') }}
              </div>
              <div v-if="!commentsLoading && commentsHasMore" class="comments-load-more">
                <button type="button" @click="loadMoreComments">
                  {{ t('加载更多评论', 'Load more comments') }}
                </button>
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
          <el-input
            v-model="publishForm.name"
            maxlength="100"
            :placeholder="t('给这位角色起个名字', 'Name this character')"
          />
        </el-form-item>
        <el-form-item :label="t('描述', 'Description')" required>
          <el-input
            v-model="publishForm.description"
            type="textarea"
            :rows="2"
            maxlength="100"
            resize="none"
            :placeholder="t('至少 30 字，介绍一下这位角色', 'At least 30 characters — describe this character')"
          />
        </el-form-item>
        <el-form-item :label="t('类型', 'Type')" required>
          <div class="gender-picker">
            <!-- 预设具体类型：男 / 女 / 神秘 / 双性 / 无性别；再提供「其他」自由输入兜底。
                 选择结果直接存入 gender，并作为具体值出现在筛选下拉里
                 （见 /marketplace/genders，只显示有卡片的类型）。 -->
            <el-radio-group v-model="publishForm.gender">
              <el-radio-button value="男">{{ t('男', 'Male') }}</el-radio-button>
              <el-radio-button value="女">{{ t('女', 'Female') }}</el-radio-button>
              <el-radio-button value="神秘">{{ t('神秘', 'Mystery') }}</el-radio-button>
              <el-radio-button value="双性">{{ t('双性', 'Intersex') }}</el-radio-button>
              <el-radio-button value="无性别">{{ t('无性别', 'Genderless') }}</el-radio-button>
              <el-radio-button value="其他">{{ t('其他', 'Other') }}</el-radio-button>
            </el-radio-group>
            <el-input
              v-if="publishForm.gender === '其他'"
              v-model="publishForm.genderCustom"
              :placeholder="t('输入自定义性别', 'Enter a custom gender')"
              maxlength="20"
              show-word-limit
              class="gender-custom-input"
            />
          </div>
        </el-form-item>
        <el-form-item :label="t('人设提示词', 'Character Prompt')" required>
          <el-input
            v-model="publishForm.system_prompt"
            type="textarea"
            :rows="5"
            maxlength="50000"
            resize="none"
            :placeholder="t('至少 100 字，描述性格、说话方式、背景设定等', 'At least 100 characters — personality, speech style, background…')"
          />
        </el-form-item>
        <!-- 玩家设定（可选）：与人物卡上的同名项一致，别人采用后就知道「自己是谁」 -->
        <el-form-item :label="t('玩家设定（可选）', 'Player Setup (optional)')">
          <el-input
            v-model="publishForm.user_prompt"
            type="textarea"
            :rows="4"
            maxlength="4000"
            resize="none"
            :placeholder="t('这张卡里「你是谁」：姓名、年龄、身份、与角色的关系、性格外貌等。留空则采用者自己补。', 'Who you are in this card. Leave empty and the adopter fills it in.')"
          />
          <div class="mk-field-hint">
            {{ t('不填也能发布 —— 采用这张卡的人可以自己补上自己的身份。', 'Optional — adopters can fill in their own identity later.') }}
          </div>
        </el-form-item>
        <!-- 世界书（可选）：随卡片分享的按需注入设定 -->
        <el-form-item :label="t('世界书（可选）', 'Worldbook (optional)')">
          <MarketplaceWorldbookEditor v-model="publishForm.worldbook" />
        </el-form-item>
        <el-form-item :label="t('开场白', 'Greeting')" required>
          <el-input
            v-model="publishForm.greeting"
            type="textarea"
            :rows="2"
            maxlength="100"
            resize="none"
            :placeholder="t('角色见到你时的第一句话', 'The character’s first line on meeting you')"
          />
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

    <!-- 编辑卡片对话框：创建者与管理员共用 -->
    <el-dialog
      v-model="showEditDialog"
      :title="t('编辑卡片', 'Edit Card')"
      width="min(520px, 94vw)"
      append-to-body
      destroy-on-close
    >
      <el-form :model="editForm" label-position="top">
        <el-form-item :label="t('名称', 'Name')" required>
          <el-input v-model="editForm.name" maxlength="100" />
        </el-form-item>
        <el-form-item :label="t('描述', 'Description')" required>
          <el-input v-model="editForm.description" type="textarea" :rows="2" maxlength="100" resize="none" />
        </el-form-item>
        <el-form-item :label="t('类型', 'Type')" required>
          <el-radio-group v-model="editForm.gender">
            <el-radio-button value="男">{{ t('男', 'Male') }}</el-radio-button>
            <el-radio-button value="女">{{ t('女', 'Female') }}</el-radio-button>
            <el-radio-button value="神秘">{{ t('神秘', 'Mystery') }}</el-radio-button>
            <el-radio-button value="双性">{{ t('双性', 'Intersex') }}</el-radio-button>
            <el-radio-button value="无性别">{{ t('无性别', 'Genderless') }}</el-radio-button>
            <el-radio-button value="其他">{{ t('其他', 'Other') }}</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="editForm.gender === '其他'" :label="t('自定义类型', 'Custom Type')">
          <el-input v-model="editForm.genderCustom" maxlength="20" :placeholder="t('输入自定义类型', 'Enter a custom type')" />
        </el-form-item>
        <el-form-item :label="t('人设提示词', 'Character Prompt')" required>
          <el-input v-model="editForm.system_prompt" type="textarea" :rows="6" maxlength="50000" resize="none" />
        </el-form-item>
        <!-- 与人物卡对齐：玩家设定 + 世界书，均为可选 -->
        <el-form-item :label="t('玩家设定（可选）', 'Player Setup (optional)')">
          <el-input v-model="editForm.user_prompt" type="textarea" :rows="4" maxlength="4000" resize="none"
            :placeholder="t('这张卡里「你是谁」。留空则采用者自己补。', 'Who you are in this card. Optional.')" />
        </el-form-item>
        <el-form-item :label="t('世界书（可选）', 'Worldbook (optional)')">
          <MarketplaceWorldbookEditor v-model="editForm.worldbook" />
        </el-form-item>
        <el-form-item :label="t('开场白', 'Greeting')" required>
          <el-input v-model="editForm.greeting" type="textarea" :rows="3" maxlength="100" resize="none" />
        </el-form-item>
        <el-form-item :label="t('头像', 'Avatar')" required>
          <div class="edit-avatar-row">
            <el-avatar :size="56" :src="editForm.avatar" />
            <el-upload :show-file-list="false" :before-upload="handleEditAvatarUpload" accept="image/*">
              <el-button size="small">{{ t('更换头像', 'Change') }}</el-button>
            </el-upload>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">{{ t('取消', 'Cancel') }}</el-button>
        <el-button type="primary" :loading="editSaving" @click="handleSaveEdit">
          {{ t('保存', 'Save') }}
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
import logger from '@/utils/logger';
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Sunny, Search, ZoomIn, ChatLineRound, Notebook } from '@element-plus/icons-vue'
import { marketplaceApi, uploadApi } from '../utils/resAi'
import { t } from '../i18n'
import ThumbIcon from './ThumbIcon.vue'
import MarketplaceWorldbookEditor from './MarketplaceWorldbookEditor.vue'
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
// 类型筛选：'' 全部 / 具体类型（男、女或用户自定义值）
const genderFilter = ref('')
// 广场中各性别标签 -> 卡片数量（仅数量 > 0 的才会出现在下拉里）
const genderCounts = ref({})

// 筛选下拉选项：只保留有卡片的类型，顺序为 男 → 女 → 其他具体值。
// 不提供「非二元」总览项——用户选择具体类型即可，逐项选择更明确。
const genderOptions = computed(() => {
  const counts = genderCounts.value || {}
  const preset = ['男', '女']
  const extras = Object.keys(counts).filter(
    g => !preset.includes(g) && g !== '非二元'
  )
  return [
    ...preset.filter(g => counts[g] > 0).map(g => ({ value: g, label: g, count: counts[g] })),
    ...extras.filter(g => counts[g] > 0).map(g => ({ value: g, label: g, count: counts[g] })),
  ]
})
const currentPage = ref(1)
const pageSize = 12
const total = ref(0)
// 列表请求令牌：排序/筛选切换时作废在途请求，防止旧响应污染新列表
let listReqSeq = 0
const hasMore = computed(() => items.value.length < total.value)
const gridRef = ref(null)

let _searchTimer = null
function debouncedSearch() {
  clearTimeout(_searchTimer)
  _searchTimer = setTimeout(() => {
    currentPage.value = 1
    loadList()
  }, 300)
}

function applyGenderFilter() {
  // 当前选中的性别若已没有对应卡片（例如删了最后一张），选项会消失，
  // 此时清空筛选回到「全部」，避免停留在一个无效条件上
  if (genderFilter.value && !genderOptions.value.some(o => o.value === genderFilter.value)) {
    genderFilter.value = ''
  }
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
// 编辑/删除按钮的显隐统一由后端下发的 can_edit 决定（管理员由后端放行）

// ========== 编辑卡片 ==========
const showEditDialog = ref(false)
const editSaving = ref(false)
const editForm = reactive({
  name: '', description: '', gender: '', genderCustom: '',
  system_prompt: '', greeting: '', avatar: '',
  // 与人物卡对齐：玩家设定与世界书都是可选
  user_prompt: '', worldbook: [],
})

// 从详情打开编辑：把当前值填入表单。原「其他」类型需还原成"其他 + 文本"，
// 否则直接填入具体值会与单选组选项不匹配，导致回显丢失。
function openEditDialog() {
  const d = detailData.value
  if (!d) return
  const raw = (d.gender || '').trim()
  const isPreset = ['男', '女', '神秘', '双性', '无性别'].includes(raw)
  Object.assign(editForm, {
    name: d.name || '',
    description: d.description || '',
    gender: !raw ? '男' : (isPreset ? raw : '其他'),
    genderCustom: isPreset || !raw ? '' : raw,
    system_prompt: d.system_prompt || '',
    greeting: d.greeting || '',
    avatar: d.avatar || '',
    user_prompt: d.user_prompt || '',
    // 深拷贝：编辑时改条目不能直接改到详情数据上（取消编辑应保持原样）
    worldbook: (d.worldbook || []).map(e => ({
      title: e.title || '',
      keywords: e.keywords || '',
      content: e.content || '',
      always_on: !!e.always_on,
    })),
  })
  showEditDialog.value = true
}

const editEffectiveGender = () =>
  editForm.gender === '其他' ? (editForm.genderCustom.trim() || '其他') : editForm.gender

async function handleEditAvatarUpload(file) {
  try {
    const res = await uploadApi.uploadImage(file)
    if (res.code === 200) editForm.avatar = res.data.url
    else ElMessage.error(t('上传失败', 'Upload failed'))
  } catch {
    ElMessage.error(t('上传失败', 'Upload failed'))
  }
  return false
}

async function handleSaveEdit() {
  if (!detailData.value) return
  editSaving.value = true
  try {
    const res = await marketplaceApi.update(detailData.value.id, {
      name: editForm.name.trim(),
      description: editForm.description.trim(),
      gender: editEffectiveGender(),
      system_prompt: editForm.system_prompt.trim(),
      greeting: editForm.greeting.trim(),
      avatar: editForm.avatar,
      // 玩家设定与世界书可选：空值照常提交（提交即代表"用当前内容覆盖"）
      user_prompt: editForm.user_prompt.trim(),
      worldbook: cleanWorldbook(editForm.worldbook),
    })
    if (res.code === 200) {
      ElMessage.success(t('已保存', 'Saved'))
      showEditDialog.value = false
      // 用最新数据覆盖详情，避免关闭编辑后仍显示旧值
      if (res.data) detailData.value = { ...detailData.value, ...res.data }
      loadList()
    } else {
      ElMessage.warning(res.message || t('保存失败', 'Save failed'))
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || t('保存失败', 'Save failed'))
  } finally {
    editSaving.value = false
  }
}

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
const commentsPage = ref(1)
const COMMENTS_PAGE_SIZE = 5
const commentsHasMore = computed(() => comments.value.length < commentTotal.value)

// 评论为扁平结构：只评论人物卡，不支持对评论的回复

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
  genderCustom: '',  // 「其他」模式下用户填写的类型文本
  // 玩家设定与世界书：与人物卡一致，都可留空
  user_prompt: '',
  worldbook: [],
})

// 提交前把世界书条目洗一遍：正文为空的整条丢掉（后端也会丢，这里先过滤少一次往返）
function cleanWorldbook(entries) {
  return (entries || [])
    .filter(e => (e.content || '').trim())
    .map(e => ({
      title: (e.title || '').trim(),
      keywords: (e.keywords || '').trim(),
      content: (e.content || '').trim(),
      always_on: !!e.always_on,
    }))
}

// 实际提交的类型值：「其他」模式下取用户输入（留空则回落到「其他」）
// 提交给后端的性别值：选「其他」时取自由输入，其余取预设值。
// 「其他」本身不是有效性别，必须替换为用户填的内容（空则回落到预设值）。
const effectiveGender = () => {
  if (publishForm.gender === '其他') return publishForm.genderCustom.trim() || '其他'
  return publishForm.gender || ''
}

watch(() => props.modelValue, (val) => {
  if (val) {
    loadList()
    loadCustomGenders()
  }
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

// 拉取广场中各性别的卡片数量；没有对应卡片的性别不显示在下拉里
async function loadCustomGenders() {
  try {
    const res = await marketplaceApi.genders()
    if (res.code === 200) {
      genderCounts.value = res.data?.genders || {}
    }
  } catch (e) { /* 静默失败：下拉退化为空，用户仍可用「全部」 */ }
}

async function loadList(append = false) {
  if (!append) {
    currentPage.value = 1
    items.value = []
    total.value = 0
  }
  // 排序/筛选切换时若有请求在途，递增令牌使其作废：
  // 否则旧排序的响应回来后会 push 进已重置的列表，导致同一批卡片重复出现
  const reqToken = ++listReqSeq
  loading.value = true
  try {
    const page = append ? currentPage.value : 1
    const res = await marketplaceApi.list(sortMode.value, page, searchKeyword.value.trim(), genderFilter.value, pageSize)
    if (reqToken !== listReqSeq) return   // 已被更新的请求取代
    if (res.code === 200) {
      const newItems = res.data.items || []
      total.value = res.data.total || 0
      if (append) {
        // 按 id 去重：分页边界可能因排序变动而重叠
        const seen = new Set(items.value.map(i => i.id))
        items.value = items.value.concat(newItems.filter(i => !seen.has(i.id)))
      } else {
        items.value = newItems
      }
    }
  } catch (e) {
    if (reqToken === listReqSeq) logger.error('加载卡片广场失败', e)
  } finally {
    if (reqToken === listReqSeq) loading.value = false
  }
}

function onGridScroll() {
  const el = gridRef.value
  if (!el || loading.value || !hasMore.value) return
  if (el.scrollHeight - el.scrollTop - el.clientHeight < 120) {
    currentPage.value += 1
    loadList(true)
  }
}

// 排序 / 性别筛选变化：重置到第一页并重新加载。
// 缺了这个监听，切换排序后列表不刷新且页码沿用旧值，
// 继续滚动会把同一页重复追加（表现为卡片重复且越来越多）。
watch(sortMode, () => {
  currentPage.value = 1
  loadList(false)
})
watch(genderFilter, () => {
  currentPage.value = 1
  loadList(false)
})

onMounted(() => {
  if (gridRef.value) gridRef.value.addEventListener('scroll', onGridScroll)
})

onUnmounted(() => {
  if (gridRef.value) gridRef.value.removeEventListener('scroll', onGridScroll)
})

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

async function loadComments(append = false) {
  if (!detailData.value) return
  if (!append) {
    commentsPage.value = 1
    comments.value = []
    commentTotal.value = 0
  }
  commentsLoading.value = true
  try {
    const res = await marketplaceApi.comments(
      detailData.value.id,
      commentSort.value,
      commentsPage.value,
      COMMENTS_PAGE_SIZE
    )
    if (res.code === 200) {
      const items = res.data.items || []
      commentTotal.value = res.data.total || 0
      if (append) {
        comments.value.push(...items)
      } else {
        comments.value = items
      }
    }
  } catch (e) {
    logger.error('加载评论失败', e)
  } finally {
    commentsLoading.value = false
  }
}

async function loadMoreComments() {
  if (commentsLoading.value || !commentsHasMore.value) return
  commentsPage.value += 1
  await loadComments(true)
}

async function submitComment() {
  if (!newComment.value.trim() || !detailData.value) return
  commentSubmitting.value = true
  try {
    const res = await marketplaceApi.addComment(
      detailData.value.id,
      newComment.value.trim()
    )
    if (res.code === 200) {
      ElMessage.success(t('评论已发表', 'Comment posted'))
      newComment.value = ''
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
    ElMessage.warning(t('请选择类型', 'Please choose a type'))
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
      // 可选字段：留空就是不带（采用者之后可自行补）
      user_prompt: publishForm.user_prompt.trim(),
      worldbook: cleanWorldbook(publishForm.worldbook),
    })
    if (res.code === 200) {
      ElMessage.success(t('发布成功', 'Published'))
      showPublishDialog.value = false
      Object.assign(publishForm, {
        name: '', description: '', system_prompt: '', greeting: '', avatar: '',
        gender: '', genderCustom: '', user_prompt: '', worldbook: [],
      })
      loadList()
      // 新卡片可能带来新的自定义性别，刷新下拉选项
      loadCustomGenders()
    } else {
      // 后端校验失败（如描述/提示词字数不足）会返回 200 + code 4xx，
      // 原实现只处理 HTTP 异常，这里必须显式提示，否则表现为「点了没反应」
      ElMessage.warning(res.message || t('发布失败，请检查填写内容', 'Publish failed, please check the fields'))
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

/* 工具栏控件宽度（原内联样式，改类名以便响应式覆盖） */
.mp-search { width: 240px; }
.mp-gender { width: 110px; }
.mp-sort { width: 150px; }

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

/* 性别下拉选项：左侧名称、右侧数量（等宽数字） */
.gender-opt-label { flex: 1; }
.gender-opt-count {
  margin-left: 14px;
  font-size: 11.5px;
  font-variant-numeric: tabular-nums;
  color: var(--text-muted);
}

/* 编辑对话框头像行 */
.edit-avatar-row {
  display: flex;
  align-items: center;
  gap: 14px;
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
  /* 关键：flex 子项默认 min-height:auto 会拒绝收缩，导致 .dr-scroll 的
     overflow-y:auto 失效、内容顶出容器（移动端表现为只有底部一小块可操作）。 */
  min-height: 0;
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

/* ===== 详情里的世界书条目 ===== */
.dr-wb-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.dr-wb-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.dr-wb-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dr-wb-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.dr-wb-tag {
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 9px;
  color: var(--text-muted);
  background: var(--surface-hover);
  border: 1px solid var(--border-color);
}

.dr-wb-kw {
  font-size: 12px;
  color: var(--text-muted);
  word-break: break-word;
}

/* 条目正文比人设提示词次要，收紧内边距与字号 */
.dr-wb-content {
  padding: 9px 11px;
  font-size: 12.5px;
}

/* 表单里的辅助说明（玩家设定 / 世界书都是可选字段） */
.mk-field-hint {
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-muted);
  margin-top: 4px;
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

/* 带世界书的卡片标记：用品牌色描边，与点赞/评论的静默样式区分开 */
.card-stat.wb {
  cursor: default;
  pointer-events: none;
  color: var(--brand, var(--text-secondary));
  border: 1px solid var(--border-color);
  border-radius: 9px;
  padding: 0 6px;
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

.no-comments {
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
  padding: 20px;
}

.comments-load-more {
  display: flex;
  justify-content: center;
  padding: 8px 0;
}

.comments-load-more button {
  background: none;
  border: none;
  font-size: 13px;
  color: var(--brand);
  cursor: pointer;
  padding: 6px 12px;
  border-radius: 6px;
  transition: background 0.15s;
}

.comments-load-more button:hover {
  background: var(--surface-hover);
  text-decoration: underline;
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
  /* 弹窗本体限高并转为纵向 flex：header / body / footer 三段，
     body 作为唯一的滚动承载（内部由 .dr-scroll 负责），
     避免整窗超出视口后 align-center 把顶部顶出屏幕。 */
  .detail-dialog {
    display: flex;
    flex-direction: column;
    max-height: calc(100vh - 24px);
    max-height: calc(100dvh - 24px);
    margin: 0 auto;
  }
  .detail-dialog :deep(.el-dialog__body) {
    flex: 1;
    min-height: 0;
    overflow: hidden;
    padding: 0;
  }
  .mp-grid {
    grid-template-columns: repeat(auto-fill, minmax(132px, 1fr));
    gap: 8px;
  }
  .detail-split {
    flex-direction: column;
    /* 关键：原先是 max-height:none，内容按自然高度无限撑开，
       配合 dialog 的 align-center 居中，弹窗高度超过视口后
       顶部被顶到视口之上，于是只有底部一小块能点（移动端反馈的 bug）。
       改为限制在视口内并由内部区域滚动。100dvh 会随地址栏收起而变化，
       比 vh 更贴近移动端实际可视高度。 */
    height: calc(100vh - 148px);
    height: calc(100dvh - 148px);
    max-height: calc(100dvh - 148px);
  }
  /* 移动端：左上角信息区改为「头像 + 右侧信息」横向紧凑排布。
     原先是纵向堆叠且 flex-shrink:0 不参与滚动，140×180 的头像加上
     赞踩/描述/创作者把首屏几乎占满，内容区只剩很小一条，
     用户第一眼看不到人设提示词与开场白，交互感很差。
     改成横向后纵向空间让给内容，头像也相应缩小。 */
  .detail-left {
    width: 100%;
    flex-shrink: 0;
    display: grid;
    grid-template-columns: 96px 1fr;
    grid-template-areas:
      'avatar votes'
      'avatar desc'
      'creator creator';
    align-items: start;
    column-gap: 14px;
    row-gap: 10px;
    border-right: none;
    border-bottom: 1px solid var(--border-color);
    padding: 14px 16px;
    overflow-y: visible;
  }
  .dl-avatar {
    grid-area: avatar;
    width: 96px;
    height: 124px;
  }
  .dl-votes {
    grid-area: votes;
    align-self: center;
    /* 桌面端三个按钮竖排（父容器 column），横向布局下改为横排更省高度 */
    flex-direction: row;
    gap: 8px;
  }
  .dl-desc {
    grid-area: desc;
    /* 桌面端为居中排版，横向布局下改左对齐更易读 */
    text-align: left;
    /* 限制行数：过长会把创作者行挤到折叠线以下 */
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
    font-size: 12.5px;
    line-height: 1.6;
  }
  .dl-creator-info,
  .dl-creator-actions { grid-area: creator; }
  .dl-creator-info {
    justify-content: flex-start;
    margin-top: 0;   /* 桌面端靠 margin-top 拉开与描述的距离，网格已负责行距 */
  }
  .dr-scroll {
    padding: 16px;
    /* 移动端适当加大行距与段间距：内容区宽度有限，行高太小会挤成一片，
       读长提示词时体验差 */
    line-height: 1.75;
  }
  /* dr-section 自身是 flex + gap 布局，用 gap 拉开段间距而非 margin */
  .dr-section { gap: 10px; }
  .dr-bottom {
    padding: 12px 16px 16px;
  }
  /* 添加按钮在移动端加大点击区域（≥44px） */
  .adopt-btn { min-height: 44px; }

  /* 顶部工具栏：搜索框整行独占，性别/排序弹性收缩，
     避免三个固定宽度控件在窄屏挤成多行碎片 */
  .mp-toolbar {
    gap: 8px;
  }
  .mp-search {
    flex: 1 1 100%;
    width: 100%;
  }
  .mp-gender,
  .mp-sort {
    width: auto;
    flex: 1 1 96px;
    min-width: 92px;
  }
  .toolbar-right {
    flex: 1 1 auto;
    gap: 8px;
  }

  /* 详情弹窗：内容过长时内部滚动，而不是撑出可视区 */
  .detail-split {
    max-height: 70vh;
    overflow-y: auto;
  }
}
</style>
