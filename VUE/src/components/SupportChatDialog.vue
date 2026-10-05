<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ChatDotRound, Promotion, Picture } from '@element-plus/icons-vue'
import { supportApi, uploadApi } from '@/utils/resAi'
import { identiconDataUrl } from '@/utils/identicon'
import { t } from '../i18n'

const props = defineProps({ modelValue: { type: Boolean, default: false }, user: { type: Object, default: null } })
const emit = defineEmits(['update:modelValue'])
const visible = computed({ get: () => props.modelValue, set: (v) => emit('update:modelValue', v) })
const loading = ref(false)
const sending = ref(false)
const imageUploading = ref(false)
const content = ref('')
const imageUrl = ref('')
const thread = ref(null)
const messages = ref([])
const supportMessagesRef = ref(null)
const anonymousId = computed(() => thread.value?.anonymous_id || t('匿名用户', 'Anonymous'))
const anonymousAvatar = computed(() => identiconDataUrl(thread.value?.avatar_seed || 'anonymous'))
const canSend = computed(() => !sending.value && !imageUploading.value && (!!content.value.trim() || !!imageUrl.value))

function formatTime(value) {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(d)
}

function isNearBottom(el) {
  if (!el) return true
  return el.scrollHeight - el.scrollTop - el.clientHeight < 96
}

async function scrollToLatest(force = false) {
  await nextTick()
  const el = supportMessagesRef.value
  if (!el) return
  // 弹窗有过渡动画；等两帧后再按实际高度定位，避免在内容尚未撑开时滚到半途。
  await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
  if (force || isNearBottom(el)) el.scrollTop = el.scrollHeight
}

async function loadThread(silent = false, forceScroll = false) {
  if (!silent) loading.value = true
  try {
    const res = await supportApi.getThread()
    if (res.code === 200) {
      const shouldStick = forceScroll || !silent || isNearBottom(supportMessagesRef.value)
      thread.value = res.data
      messages.value = res.data.messages || []
      await scrollToLatest(shouldStick)
    }
  } catch (e) {
    if (!silent) ElMessage.error(t('加载反馈会话失败', 'Failed to load support chat'))
  } finally {
    if (!silent) loading.value = false
  }
}

async function send() {
  const text = content.value.trim()
  if ((!text && !imageUrl.value) || sending.value || imageUploading.value) return
  sending.value = true
  try {
    const res = await supportApi.send(text, imageUrl.value)
    if (res.code === 200) {
      content.value = ''
      imageUrl.value = ''
      await loadThread(true, true)
      await scrollToLatest(true)
    } else {
      ElMessage.warning(res.message || t('发送失败', 'Failed to send'))
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || t('发送失败', 'Failed to send'))
  } finally {
    sending.value = false
  }
}

function handleKeydown(event) {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return
  event.preventDefault()
  send()
}

async function handleImageUpload(file) {
  imageUploading.value = true
  try {
    const res = await uploadApi.uploadImage(file)
    if (res.code === 200) imageUrl.value = res.data.url
    else ElMessage.warning(res.message || t('图片上传失败', 'Image upload failed'))
  } catch (e) {
    ElMessage.error(e.response?.data?.message || t('图片上传失败', 'Image upload failed'))
  } finally {
    imageUploading.value = false
  }
  return false
}

watch(() => props.modelValue, (open) => {
  if (open) loadThread(false, true)
})

watch(() => messages.value.length, () => {
  if (props.modelValue) scrollToLatest(false)
})
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="t('与管理员对话并提出建议', 'Chat with Admin')"
    width="min(560px, 94vw)"
    align-center
    class="support-chat-dialog"
    @opened="scrollToLatest(true)"
  >
    <div v-loading="loading" class="support-chat">
      <div class="support-chat-head">
        <el-avatar :size="38" :src="anonymousAvatar" />
        <div class="support-chat-head__meta">
          <strong>{{ anonymousId }}</strong>
          <p>{{ t('双方均以匿名身份显示，内容仅用于处理你的建议。', 'Both sides appear anonymous. Messages are only used to handle your feedback.') }}</p>
        </div>
        <span class="support-chat-head__badge">{{ t('匿名', 'Anonymous') }}</span>
      </div>

      <div ref="supportMessagesRef" class="support-messages">
        <div v-if="!messages.length" class="support-empty">
          <el-icon><ChatDotRound /></el-icon>
          <strong>{{ t('还没有消息', 'No messages yet') }}</strong>
          <span>{{ t('可以直接告诉管理员你的建议或遇到的问题。', 'Send the admin a suggestion or report an issue.') }}</span>
        </div>
        <div v-for="m in messages" :key="m.id" class="support-message" :class="m.sender">
          <el-avatar :size="28" :src="m.sender === 'admin' ? identiconDataUrl('admin-support') : anonymousAvatar" />
          <div class="support-bubble">
            <div v-if="m.content" class="support-text">{{ m.content }}</div>
            <el-image
              v-if="m.image_url"
              :src="m.image_url"
              fit="contain"
              class="support-image"
              @load="scrollToLatest(true)"
            />
            <time>{{ formatTime(m.created_at) }}</time>
          </div>
        </div>
      </div>

      <div class="support-composer">
        <div class="support-input">
          <el-upload
            class="support-upload"
            :show-file-list="false"
            :before-upload="handleImageUpload"
            accept="image/*"
          >
            <el-tooltip :content="t('添加图片', 'Attach image')" placement="top">
              <el-button circle plain :icon="Picture" :loading="imageUploading" />
            </el-tooltip>
          </el-upload>
          <el-input
            v-model="content"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
            resize="none"
            maxlength="2000"
            :placeholder="t('输入建议或问题，Enter 发送，Shift+Enter 换行', 'Write your feedback. Enter to send, Shift+Enter for a new line')"
            @keydown="handleKeydown"
          />
          <el-button
            class="support-send"
            type="primary"
            :icon="Promotion"
            :loading="sending"
            :disabled="!canSend"
            @click="send"
          >{{ t('发送', 'Send') }}</el-button>
        </div>

        <div v-if="imageUrl" class="support-image-preview">
          <el-image :src="imageUrl" fit="contain" />
          <span>{{ t('图片已准备发送', 'Image ready to send') }}</span>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<style scoped>
.support-chat { display: flex; flex-direction: column; gap: 14px; min-height: 470px; }
.support-chat-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 13px 14px;
  border-radius: 17px;
  background: linear-gradient(135deg, rgba(217, 108, 78, .14), rgba(217, 108, 78, .035));
  border: 1px solid rgba(217, 108, 78, .16);
}
.support-chat-head__meta { min-width: 0; flex: 1; }
.support-chat-head strong { display: block; font-size: 14px; color: var(--text-primary); }
.support-chat-head p { margin: 3px 0 0; font-size: 11.5px; line-height: 1.45; color: var(--text-muted); }
.support-chat-head__badge {
  flex: none;
  padding: 3px 8px;
  border-radius: 999px;
  color: var(--brand);
  background: var(--brand-soft, rgba(217, 108, 78, .12));
  font-size: 11px;
  font-weight: 600;
}
.support-messages {
  min-height: 260px;
  height: min(48vh, 390px);
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
  display: flex;
  flex-direction: column;
  gap: 15px;
  padding: 6px 7px 8px 3px;
}
.support-empty {
  margin: auto;
  color: var(--text-muted);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 7px;
  text-align: center;
  font-size: 12.5px;
}
.support-empty .el-icon { font-size: 28px; color: var(--brand); opacity: .72; }
.support-empty strong { color: var(--text-secondary); font-size: 13px; }
.support-message { display: flex; align-items: flex-end; gap: 10px; }
.support-message.user { flex-direction: row-reverse; }
.support-bubble {
  max-width: min(78%, 390px);
  padding: 10px 13px;
  border-radius: 15px 15px 15px 5px;
  background: var(--surface-hover);
  box-shadow: 0 5px 18px rgba(44, 31, 22, .055);
  border: 1px solid var(--border-color);
}
.support-message.user .support-bubble {
  border-radius: 15px 15px 5px 15px;
  background: var(--brand-soft, rgba(217, 108, 78, .14));
  border-color: rgba(217, 108, 78, .14);
}
.support-text { white-space: pre-wrap; word-break: break-word; font-size: 13.5px; line-height: 1.6; color: var(--text-primary); }
.support-bubble time { display: block; margin-top: 5px; font-size: 10.5px; color: var(--text-muted); }
.support-image { display: block; max-width: 240px; max-height: 240px; margin-top: 7px; border-radius: 10px; }
.support-composer { display: flex; flex-direction: column; gap: 8px; }
.support-input {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 9px;
  padding: 10px;
  border-radius: 18px;
  background: var(--surface);
  border: 1px solid var(--border-color);
  box-shadow: 0 8px 28px -18px rgba(44, 31, 22, .48);
  transition: border-color .18s ease, box-shadow .18s ease;
}
.support-input:focus-within {
  border-color: var(--brand);
  box-shadow: 0 8px 28px -16px rgba(217, 108, 78, .5);
}
.support-upload, .support-upload :deep(.el-upload) { display: flex; }
.support-upload :deep(.el-button) { width: 40px; height: 40px; border-radius: 12px; }
.support-input :deep(.el-textarea__inner) {
  min-height: 64px !important;
  padding: 10px 12px;
  border-radius: 12px;
  background: var(--input-bg);
  box-shadow: 0 0 0 1px var(--border-color) inset;
  font-size: 13.5px;
  line-height: 1.55;
  color: var(--text-primary);
}
.support-input :deep(.el-textarea__inner:focus) { box-shadow: 0 0 0 1px var(--brand) inset; }
.support-send { min-width: 82px; height: 40px; border-radius: 12px; }
.support-image-preview {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 8px 10px;
  border-radius: 12px;
  background: var(--brand-soft, rgba(217, 108, 78, .1));
  color: var(--text-secondary);
  font-size: 11.5px;
}
.support-image-preview :deep(.el-image) { width: 52px; height: 52px; border-radius: 8px; flex: none; }

@media (max-width: 560px) {
  .support-chat { min-height: 0; }
  .support-messages { height: min(46vh, 330px); }
  .support-input { grid-template-columns: auto minmax(0, 1fr); }
  .support-send { grid-column: 2; width: 100%; }
  .support-bubble { max-width: 82%; }
  .support-chat-head__badge { display: none; }
}
</style>

<style>
.support-chat-dialog .el-dialog__body { padding: 0 20px 20px; }
@media (max-width: 560px) {
  .support-chat-dialog .el-dialog__body { padding: 0 14px 14px; }
}
</style>
