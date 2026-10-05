<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, Upload, Document, CopyDocument } from '@element-plus/icons-vue'
import { conversationApi, chatApi } from '@/utils/resAi'
import { t } from '../i18n'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  conversationId: { type: [Number, String], default: null },
  providerId: { type: [Number, String], default: null },
  modelId: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'imported'])
const visible = computed({ get: () => props.modelValue, set: v => emit('update:modelValue', v) })
const mode = ref('export')
const loading = ref(false)
const exportText = ref('')
const importText = ref('')
const importFileName = ref('')
const MAX_IMPORT_CHARS = 8000
const hasConversation = computed(() => props.conversationId !== null && props.conversationId !== undefined && props.conversationId !== '')
const importTooLong = computed(() => importText.value.length > MAX_IMPORT_CHARS)

watch(() => props.modelValue, (open) => {
  if (open && !hasConversation.value) mode.value = 'export'
})

function errorMessage(error, fallback) {
  return error?.response?.data?.message || error?.message || fallback
}

function downloadText() {
  const text = exportText.value.trim()
  if (!text) return ElMessage.warning(t('请先生成记忆档', 'Generate a memory file first'))
  try {
    const blob = new Blob(['\ufeff' + text], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `chat-memory-${props.conversationId || 'current'}.txt`
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (e) {
    ElMessage.error(t('下载失败', 'Download failed'))
  }
}

async function copyText() {
  const text = exportText.value.trim()
  if (!text) return
  try {
    if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(text)
    else {
      const input = document.createElement('textarea')
      input.value = text
      document.body.appendChild(input)
      input.select()
      document.execCommand('copy')
      input.remove()
    }
    ElMessage.success(t('已复制', 'Copied'))
  } catch (e) {
    ElMessage.error(t('复制失败', 'Copy failed'))
  }
}

async function exportMemory() {
  if (!hasConversation.value) return ElMessage.warning(t('请先打开一个对话', 'Open a conversation first'))
  loading.value = true
  try {
    const res = await chatApi.exportMemory({
      conversation_id: props.conversationId,
      provider_id: props.providerId,
      model_id: props.modelId,
    })
    if (res.code === 200 && res.data?.content) {
      exportText.value = res.data.content
      downloadText()
      ElMessage.success(t('记忆文本已生成并下载', 'Memory text generated and downloaded'))
    } else {
      ElMessage.warning(res.message || t('导出失败', 'Export failed'))
    }
  } catch (e) {
    ElMessage.error(errorMessage(e, t('导出失败', 'Export failed')))
  } finally {
    loading.value = false
  }
}

function readFile(file) {
  if (file.size > 1024 * 1024) {
    ElMessage.warning(t('文本文件不能超过 1MB', 'Text file must be under 1 MB'))
    return false
  }
  const reader = new FileReader()
  reader.onload = () => {
    importText.value = String(reader.result || '').replace(/^\ufeff/, '')
    importFileName.value = file.name || ''
    if (importTooLong.value) {
      ElMessage.warning(t('记忆文本最多 8000 字，请先精简后再导入', 'Memory text is limited to 8,000 characters'))
      return
    }
    importMemory()
  }
  reader.onerror = () => ElMessage.error(t('文件读取失败', 'Failed to read file'))
  reader.readAsText(file)
  return false
}

function clearImport() {
  importText.value = ''
  importFileName.value = ''
}

async function importMemory() {
  if (!hasConversation.value) return ElMessage.warning(t('请先打开一个对话', 'Open a conversation first'))
  const text = importText.value.trim()
  if (text.length < 10) return ElMessage.warning(t('请选择或输入包含记忆内容的文本', 'Choose or enter valid memory text'))
  if (text.length > MAX_IMPORT_CHARS) return ElMessage.warning(t('记忆文本最多 8000 字', 'Memory text is limited to 8,000 characters'))

  loading.value = true
  try {
    const res = await conversationApi.replaceMemory(props.conversationId, text)
    if (res.code === 200) {
      ElMessage.success(t('记忆已导入当前对话', 'Memory imported into this chat'))
      emit('imported')
      visible.value = false
    } else {
      ElMessage.warning(res.message || t('导入失败', 'Import failed'))
    }
  } catch (e) {
    ElMessage.error(errorMessage(e, t('导入失败', 'Import failed')))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <el-drawer
    v-model="visible"
    direction="rtl"
    size="460px"
    append-to-body
    destroy-on-close
    class="memory-transfer-drawer"
  >
    <template #header>
      <div class="memory-drawer-head">
        <span class="memory-drawer-head__icon"><el-icon><Document /></el-icon></span>
        <div>
          <strong>{{ t('聊天记忆管理', 'Chat Memory') }}</strong>
          <small>{{ hasConversation ? `${t('当前对话', 'Current chat')} #${conversationId}` : t('尚未打开对话', 'No chat selected') }}</small>
        </div>
      </div>
    </template>

    <div class="memory-drawer">
      <div class="memory-choice" role="tablist">
        <button type="button" :class="{ active: mode === 'export' }" @click="mode = 'export'">
          <el-icon><Download /></el-icon>
          <span>{{ t('导出聊天记忆', 'Export memory') }}</span>
        </button>
        <button type="button" :class="{ active: mode === 'import' }" @click="mode = 'import'">
          <el-icon><Upload /></el-icon>
          <span>{{ t('导入聊天记忆', 'Import memory') }}</span>
        </button>
      </div>

      <section v-if="mode === 'export'" class="memory-pane">
        <div class="memory-pane__intro">
          <h4>{{ t('生成记忆档案', 'Generate Memory Archive') }}</h4>
          <p>{{ t('调用当前 AI 汇总记忆宫殿中的长记忆与短记忆，生成可移植的长期记忆档案（会消耗少量 token）。', 'AI will merge long/short-term memory from the memory palace into a portable archive (uses some tokens).') }}</p>
        </div>
        <div v-if="!hasConversation" class="memory-notice">
          {{ t('请先从聊天列表打开一个对话，再导出记忆。', 'Open a conversation before exporting memory.') }}
        </div>
        <div class="memory-actions">
          <el-button type="primary" :icon="Download" :loading="loading" :disabled="!hasConversation" @click="exportMemory">
            {{ t('生成记忆档', 'Generate memory file') }}
          </el-button>
          <el-button :icon="CopyDocument" :disabled="!exportText" @click="copyText">{{ t('复制', 'Copy') }}</el-button>
          <el-button :icon="Download" :disabled="!exportText" @click="downloadText">{{ t('下载 .txt', 'Download .txt') }}</el-button>
        </div>
        <div v-if="exportText" class="memory-preview">
          <div class="memory-preview__bar">
            <span>{{ t('导出预览', 'Preview') }}</span>
            <span>{{ exportText.length }} / 8000</span>
          </div>
          <el-input v-model="exportText" type="textarea" :rows="15" readonly />
        </div>
        <div v-else class="memory-empty">
          <el-icon><Document /></el-icon>
          <span>{{ t('生成后会在这里显示内容，确认无误再下载。', 'The generated text will appear here before download.') }}</span>
        </div>
      </section>

      <section v-else class="memory-pane">
        <div class="memory-pane__intro">
          <h4>{{ t('导入记忆文本', 'Import memory text') }}</h4>
          <p>{{ t('支持 .txt / text 文件。导入后会替换当前对话的长期记忆，不会删除聊天记录。', 'Supports .txt / text files. Import replaces this chat’s long-term memory without deleting messages.') }}</p>
        </div>
        <div v-if="!hasConversation" class="memory-notice">
          {{ t('请先从聊天列表打开一个对话，再导入记忆。', 'Open a conversation before importing memory.') }}
        </div>
        <el-upload
          drag
          class="memory-upload"
          :show-file-list="false"
          :before-upload="readFile"
          accept=".txt,text/plain"
          :disabled="!hasConversation"
        >
          <el-icon class="memory-upload__icon"><Upload /></el-icon>
          <div class="memory-upload__title">{{ t('拖入文本文件，或点击选择', 'Drop a text file here, or click to choose') }}</div>
          <div class="memory-upload__hint">{{ t('最多 1MB，正文上限 8000 字', 'Up to 1 MB, 8,000 characters') }}</div>
        </el-upload>
        <div v-if="importFileName" class="memory-file">
          <span>{{ importFileName }}</span>
          <el-button text size="small" @click="clearImport">{{ t('清除', 'Clear') }}</el-button>
        </div>
        <div v-if="importText" class="memory-preview">
          <div class="memory-preview__bar">
            <span>{{ t('导入预览（可编辑）', 'Preview (editable)') }}</span>
            <span :class="{ 'is-over': importTooLong }">{{ importText.length }} / {{ MAX_IMPORT_CHARS }}</span>
          </div>
          <el-input v-model="importText" type="textarea" :rows="13" maxlength="9000" />
        </div>
        <el-button
          class="memory-import-btn"
          type="primary"
          :icon="Upload"
          :loading="loading"
          :disabled="!hasConversation || !importText.trim() || importTooLong"
          @click="importMemory"
        >{{ t('导入到当前对话记忆', 'Import into this chat') }}</el-button>
      </section>
    </div>
  </el-drawer>
</template>

<style scoped>
.memory-drawer-head { display: flex; align-items: center; gap: 11px; min-width: 0; }
.memory-drawer-head__icon {
  width: 34px;
  height: 34px;
  border-radius: 11px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  color: var(--brand);
  background: var(--brand-soft, rgba(217, 108, 78, .12));
}
.memory-drawer-head strong { display: block; color: var(--text-primary); font-size: 15px; }
.memory-drawer-head small { display: block; margin-top: 2px; color: var(--text-muted); font-size: 11.5px; }
.memory-drawer { height: 100%; display: flex; flex-direction: column; gap: 18px; }
.memory-choice { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.memory-choice button {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 48px;
  padding: 10px;
  border: 1px solid var(--border-color);
  border-radius: 14px;
  background: var(--surface);
  color: var(--text-secondary);
  cursor: pointer;
  transition: .18s ease;
}
.memory-choice button:hover { border-color: var(--brand); color: var(--brand); }
.memory-choice button.active {
  border-color: var(--brand);
  color: var(--brand);
  background: var(--brand-soft, rgba(217, 108, 78, .1));
  box-shadow: 0 7px 20px -16px rgba(217, 108, 78, .8);
}
.memory-pane { display: flex; flex-direction: column; gap: 13px; min-height: 0; }
.memory-pane__intro h4 { margin: 0 0 5px; font-size: 14px; color: var(--text-primary); }
.memory-pane__intro p { margin: 0; color: var(--text-secondary); line-height: 1.65; font-size: 12.5px; }
.memory-notice { padding: 10px 12px; border-radius: 10px; color: #b36a16; background: rgba(217, 151, 59, .12); font-size: 12.5px; }
.memory-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.memory-actions .el-button { margin-left: 0; }
.memory-preview { min-height: 0; display: flex; flex-direction: column; gap: 6px; }
.memory-preview__bar { display: flex; justify-content: space-between; color: var(--text-muted); font-size: 11.5px; }
.memory-preview__bar .is-over { color: #d94e4e; font-weight: 600; }
.memory-preview :deep(.el-textarea__inner) {
  background: var(--input-bg);
  border-radius: 12px;
  font-family: ui-monospace, SFMono-Regular, Consolas, 'Liberation Mono', monospace;
  font-size: 12px;
  line-height: 1.65;
  color: var(--text-primary);
}
.memory-empty {
  min-height: 180px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 9px;
  text-align: center;
  border: 1px dashed var(--border-color);
  border-radius: 14px;
  color: var(--text-muted);
  font-size: 12.5px;
}
.memory-empty .el-icon { font-size: 30px; color: var(--brand); opacity: .6; }
.memory-upload { display: block; }
.memory-upload :deep(.el-upload) { width: 100%; }
.memory-upload :deep(.el-upload-dragger) {
  width: 100%;
  padding: 24px 16px;
  border-radius: 14px;
  border-color: var(--border-color);
  background: var(--surface);
  transition: .18s ease;
}
.memory-upload :deep(.el-upload-dragger:hover) { border-color: var(--brand); background: var(--brand-soft, rgba(217, 108, 78, .06)); }
.memory-upload__icon { font-size: 28px; color: var(--brand); }
.memory-upload__title { margin-top: 7px; color: var(--text-primary); font-size: 13px; font-weight: 600; }
.memory-upload__hint { margin-top: 4px; color: var(--text-muted); font-size: 11.5px; }
.memory-file { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 8px 10px; border-radius: 10px; background: var(--surface-hover); color: var(--text-secondary); font-size: 12px; }
.memory-file span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.memory-import-btn { width: 100%; height: 40px; }

@media (max-width: 560px) {
  .memory-drawer { gap: 12px; }
  .memory-drawer-head__icon { width: 30px; height: 30px; border-radius: 9px; }
  .memory-drawer-head__icon .el-icon { font-size: 16px; }
  .memory-drawer-head strong { font-size: 14px; }
  .memory-drawer-head small { font-size: 11px; }
  .memory-choice { grid-template-columns: 1fr; gap: 8px; }
  .memory-choice button { min-height: 42px; padding: 8px 10px; font-size: 12.5px; }
  .memory-pane__intro h4 { font-size: 13px; }
  .memory-pane__intro p { font-size: 12px; line-height: 1.55; }
  .memory-actions { display: flex; flex-direction: column; gap: 8px; }
  .memory-actions .el-button { width: 100%; min-height: 38px; }
  .memory-preview :deep(.el-textarea__inner) { font-size: 11.5px; }
  .memory-empty { min-height: 140px; font-size: 12px; }
  .memory-empty .el-icon { font-size: 26px; }
  .memory-upload :deep(.el-upload-dragger) { padding: 18px 12px; }
  .memory-upload__icon { font-size: 24px; }
  .memory-upload__title { font-size: 12.5px; }
  .memory-upload__hint { font-size: 11px; }
  .memory-import-btn { height: 38px; font-size: 13px; }
}
</style>

<style>
.memory-transfer-drawer {
  width: min(460px, 100vw) !important;
  max-width: 100vw;
}
.memory-transfer-drawer .el-drawer__header {
  margin-bottom: 0;
  padding: 20px 20px 12px;
  color: var(--text-primary);
  border-bottom: 1px solid var(--border-color, rgba(0,0,0,.06));
}
.memory-transfer-drawer .el-drawer__body {
  height: calc(100% - 76px);
  padding: 0 20px 20px;
  overflow-y: auto;
  overscroll-behavior: contain;
}
.memory-transfer-drawer .el-drawer__body::-webkit-scrollbar { width: 6px; }
.memory-transfer-drawer .el-drawer__body::-webkit-scrollbar-thumb {
  background: rgba(0,0,0,.12);
  border-radius: 3px;
}
.memory-transfer-drawer .el-drawer__body::-webkit-scrollbar-thumb:hover { background: rgba(0,0,0,.2); }
@media (max-width: 560px) {
  .memory-transfer-drawer { width: 100vw !important; }
  .memory-transfer-drawer .el-drawer__header { padding: 14px 14px 10px; }
  .memory-transfer-drawer .el-drawer__body { height: calc(100% - 64px); padding: 0 14px 14px; }
}
</style>
