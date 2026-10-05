<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, Upload, Document } from '@element-plus/icons-vue'
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

function downloadText() {
  if (!exportText.value) return
  const blob = new Blob([exportText.value], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `chat-memory-${props.conversationId || 'current'}.txt`
  a.click()
  URL.revokeObjectURL(url)
}

async function exportMemory() {
  if (!props.conversationId) return ElMessage.warning(t('请先打开一个对话', 'Open a conversation first'))
  loading.value = true
  try {
    const res = await chatApi.exportMemory({ conversation_id: props.conversationId, provider_id: props.providerId, model_id: props.modelId })
    if (res.code === 200) {
      exportText.value = res.data.content
      downloadText()
      ElMessage.success(t('记忆文本已生成并下载', 'Memory text generated and downloaded'))
    } else ElMessage.warning(res.message || t('导出失败', 'Export failed'))
  } catch (e) { ElMessage.error(t('导出失败', 'Export failed')) }
  finally { loading.value = false }
}

function readFile(file) {
  const reader = new FileReader()
  reader.onload = () => { importText.value = String(reader.result || '') }
  reader.onerror = () => ElMessage.error(t('文件读取失败', 'Failed to read file'))
  reader.readAsText(file)
  return false
}

async function importMemory() {
  const text = importText.value.trim()
  if (text.length < 10) return ElMessage.warning(t('请选择包含记忆内容的文本文件', 'Choose a valid memory text file'))
  loading.value = true
  try {
    const res = await conversationApi.replaceMemory(props.conversationId, text)
    if (res.code === 200) {
      ElMessage.success(t('记忆已导入当前对话', 'Memory imported into this chat'))
      emit('imported')
      visible.value = false
    }
  } catch (e) { ElMessage.error(t('导入失败', 'Import failed')) }
  finally { loading.value = false }
}
</script>

<template>
  <el-drawer
    v-model="visible"
    :title="t('聊天记忆管理', 'Chat Memory')"
    size="420px"
    direction="rtl"
    append-to-body
    destroy-on-close
    class="memory-transfer-drawer"
  >
    <div class="memory-drawer">
      <div class="memory-choice">
        <button type="button" :class="{ active: mode === 'export' }" @click="mode = 'export'">
          <el-icon><Download /></el-icon>
          <span>{{ t('导出聊天记忆', 'Export memory') }}</span>
        </button>
        <button type="button" :class="{ active: mode === 'import' }" @click="mode = 'import'">
          <el-icon><Upload /></el-icon>
          <span>{{ t('导入聊天记忆', 'Import memory') }}</span>
        </button>
      </div>

      <div v-if="mode === 'export'" class="memory-pane">
        <p>{{ t('把当前记忆宫殿整理成文本并下载。导出内容不会包含全部聊天原文。', 'Generate a downloadable memory text from the memory palace only.') }}</p>
        <el-button type="primary" :icon="Download" :loading="loading" @click="exportMemory">{{ t('生成并下载文本', 'Generate and download') }}</el-button>
        <el-input v-if="exportText" v-model="exportText" type="textarea" :rows="14" readonly />
      </div>

      <div v-else class="memory-pane">
        <p>{{ t('选择一个记忆文本文件，导入后会写入当前对话的记忆回廊。', 'Choose a memory text file; it will be saved into this chat memory.') }}</p>
        <el-upload :show-file-list="false" :before-upload="readFile" accept=".txt,text/plain">
          <el-button :icon="Document">{{ t('选择文本文件', 'Choose text file') }}</el-button>
        </el-upload>
        <el-input v-if="importText" v-model="importText" type="textarea" :rows="12" readonly />
        <el-button v-if="importText" type="primary" :icon="Upload" :loading="loading" @click="importMemory">{{ t('导入到当前对话记忆', 'Import into this chat') }}</el-button>
      </div>
    </div>
  </el-drawer>
</template>

<style scoped>
.memory-drawer { display: flex; flex-direction: column; gap: 18px; }
.memory-choice { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.memory-choice button { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 14px 10px; border: 1px solid var(--border-color); border-radius: 12px; background: var(--surface); color: var(--text-secondary); cursor: pointer; }
.memory-choice button.active { border-color: var(--brand); color: var(--brand); background: var(--brand-soft, rgba(176, 106, 46, .1)); }
.memory-pane { display: flex; flex-direction: column; gap: 12px; }
.memory-pane p { margin: 0; color: var(--text-secondary); line-height: 1.6; }
</style>

<style>
.memory-transfer-drawer { max-width: 94vw; }
.memory-transfer-drawer .el-drawer__body { padding-top: 8px; }
</style>
