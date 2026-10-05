<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, Upload } from '@element-plus/icons-vue'
import { conversationApi, chatApi } from '@/utils/resAi'
import { t } from '../i18n'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  conversationId: { type: [Number, String], default: null },
  providerId: { type: [Number, String], default: null },
  modelId: { type: String, default: '' },
  personaId: { type: [Number, String], default: null },
})
const emit = defineEmits(['update:modelValue', 'imported'])
const visible = computed({ get: () => props.modelValue, set: v => emit('update:modelValue', v) })
const mode = ref('export')
const loading = ref(false)
const exportText = ref('')
const importText = ref('')

async function exportMemory() {
  if (!props.conversationId) return ElMessage.warning(t('请先打开一个对话', 'Open a conversation first'))
  loading.value = true
  try {
    const res = await chatApi.exportMemory({ conversation_id: props.conversationId, provider_id: props.providerId, model_id: props.modelId })
    if (res.code === 200) exportText.value = res.data.content
    else ElMessage.warning(res.message || t('导出失败', 'Export failed'))
  } catch (e) { ElMessage.error(t('导出失败', 'Export failed')) }
  finally { loading.value = false }
}

async function importMemory() {
  const text = importText.value.trim()
  if (text.length < 10) return ElMessage.warning(t('请粘贴有效的记忆文本', 'Paste valid memory text'))
  loading.value = true
  try {
    const res = await conversationApi.importMemory({
      memory_text: text,
      provider_id: props.providerId,
      model_id: props.modelId,
      persona_id: props.personaId,
      title: t('记忆存档', 'Memory Save'),
    })
    if (res.code === 200) {
      ElMessage.success(t('已创建带记忆的新对话', 'Memory save created'))
      emit('imported', res.data)
      visible.value = false
    }
  } catch (e) { ElMessage.error(t('导入失败', 'Import failed')) }
  finally { loading.value = false }
}
</script>

<template>
  <el-dialog v-model="visible" :title="t('导出 / 导入聊天记忆', 'Export / Import Chat Memory')" width="min(620px, 94vw)" align-center>
    <el-radio-group v-model="mode" class="memory-mode">
      <el-radio-button value="export">{{ t('导出聊天记忆', 'Export memory') }}</el-radio-button>
      <el-radio-button value="import">{{ t('导入聊天记忆', 'Import memory') }}</el-radio-button>
    </el-radio-group>

    <div v-if="mode === 'export'" class="memory-transfer-pane">
      <p>{{ t('只读取长期记忆和压缩记录，让 AI 整理成较短的记忆档，不会导出全部聊天正文。', 'Uses only long-term memory and summaries to create a portable memory file.') }}</p>
      <el-button type="primary" :icon="Download" :loading="loading" @click="exportMemory">{{ t('生成记忆档', 'Generate memory') }}</el-button>
      <el-input v-if="exportText" v-model="exportText" type="textarea" :rows="12" readonly />
      <el-button v-if="exportText" size="small" @click="navigator.clipboard.writeText(exportText)">{{ t('复制', 'Copy') }}</el-button>
    </div>

    <div v-else class="memory-transfer-pane">
      <p>{{ t('粘贴记忆档后创建新对话。新对话只携带记忆摘要，可以继续剧情并减少 Token。', 'Paste a memory file to start a new conversation with only the memory summary.') }}</p>
      <el-input v-model="importText" type="textarea" :rows="12" :placeholder="t('粘贴之前导出的记忆档', 'Paste exported memory here')" />
      <el-button type="primary" :icon="Upload" :loading="loading" @click="importMemory">{{ t('创建记忆存档', 'Create memory save') }}</el-button>
    </div>
  </el-dialog>
</template>

<style scoped>
.memory-mode { margin-bottom: 14px; }
.memory-transfer-pane { display: flex; flex-direction: column; gap: 12px; }
.memory-transfer-pane p { margin: 0; color: var(--text-secondary); line-height: 1.6; }
</style>
