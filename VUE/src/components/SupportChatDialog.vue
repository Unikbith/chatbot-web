<script setup>
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ChatDotRound, Promotion, Picture } from '@element-plus/icons-vue'
import { supportApi, uploadApi } from '@/utils/resAi'
import { identiconDataUrl } from '@/utils/identicon'
import { t } from '../i18n'

const props = defineProps({ modelValue: { type: Boolean, default: false }, user: { type: Object, default: null } })
const emit = defineEmits(['update:modelValue'])
const visible = computed({ get: () => props.modelValue, set: (v) => emit('update:modelValue', v) })
const loading = ref(false); const sending = ref(false); const content = ref(''); const imageUrl = ref('')
const thread = ref(null); const messages = ref([]); let pollTimer = null
const anonymousId = computed(() => thread.value?.anonymous_id || t('匿名用户', 'Anonymous'))
const anonymousAvatar = computed(() => identiconDataUrl(thread.value?.avatar_seed || 'anonymous'))

function formatTime(value) {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(d)
}
async function loadThread(silent = false) {
  if (!silent) loading.value = true
  try {
    const res = await supportApi.getThread()
    if (res.code === 200) { thread.value = res.data; messages.value = res.data.messages || []; await nextTick(); const body = document.querySelector('.support-chat-dialog .el-dialog__body'); if (body) body.scrollTop = body.scrollHeight }
  } catch (e) { if (!silent) ElMessage.error(t('加载反馈会话失败', 'Failed to load support chat')) }
  finally { if (!silent) loading.value = false }
}
async function send() {
  const text = content.value.trim(); if ((!text && !imageUrl.value) || sending.value) return
  sending.value = true
  try { const res = await supportApi.send(text, imageUrl.value); if (res.code === 200) { content.value = ''; imageUrl.value = ''; await loadThread(true) } }
  catch (e) { ElMessage.error(t('发送失败', 'Failed to send')) }
  finally { sending.value = false }
}
async function handleImageUpload(file) {
  try {
    const res = await uploadApi.uploadImage(file)
    if (res.code === 200) imageUrl.value = res.data.url
  } catch (e) { ElMessage.error(t('图片上传失败', 'Image upload failed')) }
  return false
}
function startPolling() { stopPolling(); pollTimer = setInterval(() => loadThread(true), 8000) }
function stopPolling() { if (pollTimer) clearInterval(pollTimer); pollTimer = null }
watch(() => props.modelValue, (open) => { if (open) { loadThread(); startPolling() } else stopPolling() })
onUnmounted(stopPolling)
</script>

<template>
  <el-dialog v-model="visible" :title="t('与管理员对话并提出建议', 'Chat with Admin')" width="min(520px, 94vw)" align-center class="support-chat-dialog">
    <div v-loading="loading" class="support-chat">
      <div class="support-chat-head">
        <el-avatar :size="36" :src="anonymousAvatar" />
        <div><strong>{{ anonymousId }}</strong><p>{{ t('双方均以匿名身份显示。', 'Both sides appear anonymous.') }}</p></div>
      </div>
      <div class="support-messages">
        <div v-if="!messages.length" class="support-empty"><el-icon><ChatDotRound /></el-icon><span>{{ t('可以直接告诉管理员你的建议或遇到的问题。', 'Send the admin a suggestion or report an issue.') }}</span></div>
        <div v-for="m in messages" :key="m.id" class="support-message" :class="m.sender">
          <el-avatar :size="26" :src="m.sender === 'admin' ? identiconDataUrl('admin-support') : anonymousAvatar" />
          <div class="support-bubble"><div class="support-text">{{ m.content }}</div><el-image v-if="m.image_url" :src="m.image_url" fit="contain" class="support-image" /><time>{{ formatTime(m.created_at) }}</time></div>
        </div>
      </div>
      <div class="support-input">
        <el-upload :show-file-list="false" :before-upload="handleImageUpload" accept="image/*"><el-button :icon="Picture" /></el-upload>
        <el-input v-model="content" type="textarea" :rows="2" resize="none" maxlength="2000" :placeholder="t('输入建议或问题，按发送', 'Write your feedback and send')" />
        <el-button type="primary" :icon="Promotion" :loading="sending" @click="send">{{ t('发送', 'Send') }}</el-button>
      </div>
      <div v-if="imageUrl" class="support-image-preview"><el-image :src="imageUrl" fit="contain" /></div>
    </div>
  </el-dialog>
</template>

<style scoped>
.support-chat { display: flex; flex-direction: column; gap: 12px; }
.support-chat-head { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 12px; background: var(--surface-hover); }
.support-chat-head strong { font-size: 14px; }
.support-chat-head p { margin: 2px 0 0; font-size: 11.5px; color: var(--text-muted); }
.support-messages { min-height: 260px; max-height: 48vh; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; padding: 4px 2px; }
.support-empty { margin: auto; color: var(--text-muted); display: flex; flex-direction: column; align-items: center; gap: 8px; font-size: 13px; }
.support-message { display: flex; align-items: flex-end; gap: 8px; }
.support-message.user { flex-direction: row-reverse; }
.support-bubble { max-width: 76%; padding: 9px 11px; border-radius: 12px; background: var(--surface-hover); }
.support-message.user .support-bubble { background: var(--brand-soft, rgba(176, 106, 46, .12)); }
.support-text { white-space: pre-wrap; word-break: break-word; font-size: 13.5px; line-height: 1.55; }
.support-bubble time { display: block; margin-top: 4px; font-size: 10.5px; color: var(--text-muted); }
.support-image { display: block; max-width: 220px; max-height: 220px; margin-top: 6px; border-radius: 8px; }
.support-image-preview :deep(.el-image) { max-height: 120px; }
.support-input { display: flex; gap: 8px; align-items: flex-end; }
.support-input :deep(.el-textarea) { flex: 1; }
</style>
