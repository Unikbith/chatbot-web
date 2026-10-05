<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Delete, Download, Upload, Refresh } from '@element-plus/icons-vue'
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
const loading = ref(false)
const data = ref(null)
const daily = ref(null)
const editing = ref(false)
const form = ref({ id: null, card_type: 'fact', title: '', content: '', importance: 1 })
const exportVisible = ref(false)
const exportText = ref('')
const exportLoading = ref(false)
const importVisible = ref(false)
const importText = ref('')
const importLoading = ref(false)
const stageText = computed(() => `${data.value?.stage || '陌生'} · ${data.value?.score ?? 0}/100`)

async function load() {
  if (!props.conversationId) return
  loading.value = true
  try {
    const [m, d] = await Promise.all([conversationApi.memoryCenter(props.conversationId), conversationApi.dailyEvent(props.conversationId)])
    if (m.code === 200) data.value = m.data
    if (d.code === 200) daily.value = d.data
  } catch (e) { ElMessage.error(t('加载记忆失败', 'Failed to load memory')) }
  finally { loading.value = false }
}
function resetForm() { form.value = { id: null, card_type: 'fact', title: '', content: '', importance: 1 }; editing.value = false }
function editCard(card) { form.value = { ...card }; editing.value = true }
async function saveCard() {
  if (!form.value.title.trim() || !form.value.content.trim()) return ElMessage.warning(t('请填写标题和内容', 'Title and content required'))
  try {
    const res = form.value.id ? await conversationApi.updateMemory(props.conversationId, form.value.id, form.value) : await conversationApi.createMemory(props.conversationId, form.value)
    if (res.code === 200) { ElMessage.success(res.message || t('已保存', 'Saved')); resetForm(); await load() }
  } catch (e) { ElMessage.error(t('保存失败', 'Save failed')) }
}
async function removeCard(card) {
  try { await ElMessageBox.confirm(t('确定让角色忘记这条记忆吗？', 'Forget this memory?'), t('确认', 'Confirm'), { type: 'warning' }); await conversationApi.removeMemory(props.conversationId, card.id); await load() }
  catch (e) { if (e !== 'cancel') ElMessage.error(t('删除失败', 'Delete failed')) }
}
async function exportMemory() {
  exportLoading.value = true
  try {
    const res = await chatApi.exportMemory({ conversation_id: props.conversationId, provider_id: props.providerId, model_id: props.modelId })
    if (res.code === 200) { exportText.value = res.data.content; exportVisible.value = true }
    else ElMessage.warning(res.message || t('导出失败', 'Export failed'))
  } catch (e) { ElMessage.error(t('导出失败', 'Export failed')) }
  finally { exportLoading.value = false }
}
async function doImport() {
  if (importText.value.trim().length < 10) return
  importLoading.value = true
  try {
    const res = await conversationApi.importMemory({ memory_text: importText.value.trim(), provider_id: props.providerId, model_id: props.modelId, persona_id: props.personaId, title: t('记忆存档', 'Memory Save') })
    if (res.code === 200) { ElMessage.success(t('已创建带记忆的新对话', 'Memory save created')); importVisible.value = false; importText.value = ''; emit('imported', res.data); visible.value = false }
  } catch (e) { ElMessage.error(t('导入失败', 'Import failed')) }
  finally { importLoading.value = false }
}
watch(() => props.modelValue, open => { if (open) load() })
</script>

<template>
  <el-dialog v-model="visible" :title="t('记忆中心', 'Memory Center')" width="min(720px, 96vw)" align-center>
    <div v-loading="loading" class="memory-center">
      <div v-if="daily" class="memory-daily"><div><strong>{{ t('今日角色事件', 'Today') }}</strong><span>{{ daily.mood }}</span></div><p>{{ daily.message }}</p><small>{{ t('连续互动', 'Streak') }} {{ daily.streak }} {{ t('天', 'days') }}</small></div>
      <div class="memory-stage"><span>{{ t('关系阶段', 'Relationship') }}</span><strong>{{ stageText }}</strong><div class="memory-progress"><i :style="{ width: `${data?.score || 0}%` }" /></div><small>{{ (data?.unlocked || []).join(' · ') }}</small></div>
      <div class="memory-toolbar"><strong>{{ t('长期记忆卡', 'Memory Cards') }}</strong><div><el-button size="small" :icon="Download" :loading="exportLoading" @click="exportMemory">{{ t('导出记忆', 'Export') }}</el-button><el-button size="small" :icon="Upload" @click="importVisible = true">{{ t('导入记忆', 'Import') }}</el-button><el-button size="small" :icon="Refresh" @click="load">{{ t('刷新', 'Refresh') }}</el-button></div></div>
      <div class="memory-cards"><div v-for="c in (data?.cards || [])" :key="c.id" class="memory-card"><div class="memory-card-head"><strong>{{ c.title }}</strong><span>{{ c.card_type }} · {{ c.importance }}</span></div><p>{{ c.content }}</p><div class="memory-card-actions"><el-button size="small" text @click="editCard(c)">{{ t('编辑', 'Edit') }}</el-button><el-button size="small" text type="danger" :icon="Delete" @click="removeCard(c)" /></div></div><el-empty v-if="!data?.cards?.length" :description="t('还没有手动记忆卡', 'No memory cards yet')" /></div>
      <div class="memory-editor"><el-select v-model="form.card_type" size="small" style="width: 110px"><el-option :label="t('事实', 'Fact')" value="fact" /><el-option :label="t('时间线', 'Timeline')" value="timeline" /><el-option :label="t('偏好', 'Preference')" value="preference" /><el-option :label="t('雷点', 'Dislike')" value="dislike" /></el-select><el-input v-model="form.title" size="small" :placeholder="t('标题', 'Title')" /><el-input v-model="form.content" size="small" :placeholder="t('内容，例如：她不喜欢被突然触碰', 'Content')" /><el-button size="small" type="primary" :icon="Plus" @click="saveCard">{{ editing ? t('保存', 'Save') : t('添加', 'Add') }}</el-button><el-button v-if="editing" size="small" text @click="resetForm">{{ t('取消', 'Cancel') }}</el-button></div>
    </div>
    <el-dialog v-model="exportVisible" :title="t('可移植记忆档', 'Portable Memory')" width="min(620px, 94vw)" append-to-body><el-input v-model="exportText" type="textarea" :rows="12" readonly /><template #footer><el-button @click="exportVisible = false">{{ t('关闭', 'Close') }}</el-button></template></el-dialog>
    <el-dialog v-model="importVisible" :title="t('导入记忆档', 'Import Memory')" width="min(620px, 94vw)" append-to-body><el-input v-model="importText" type="textarea" :rows="12" :placeholder="t('粘贴导出的记忆档', 'Paste exported memory')" /><template #footer><el-button @click="importVisible = false">{{ t('取消', 'Cancel') }}</el-button><el-button type="primary" :loading="importLoading" @click="doImport">{{ t('创建记忆存档', 'Create Save') }}</el-button></template></el-dialog>
  </el-dialog>
</template>

<style scoped>
.memory-center { display: flex; flex-direction: column; gap: 14px; }
.memory-daily, .memory-stage { padding: 12px 14px; border: 1px solid var(--border-color); border-radius: 12px; background: var(--surface-hover); }
.memory-daily > div { display: flex; justify-content: space-between; gap: 12px; }
.memory-daily p { margin: 6px 0; color: var(--text-secondary); }
.memory-daily small, .memory-stage small { color: var(--text-muted); }
.memory-stage { display: flex; flex-direction: column; gap: 6px; }
.memory-progress { height: 8px; border-radius: 99px; background: var(--border-color); overflow: hidden; }
.memory-progress i { display: block; height: 100%; background: var(--brand); transition: width .3s ease; }
.memory-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.memory-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; max-height: 280px; overflow-y: auto; }
.memory-card { padding: 10px 12px; border: 1px solid var(--border-color); border-radius: 10px; background: var(--surface); }
.memory-card-head { display: flex; justify-content: space-between; gap: 8px; }
.memory-card-head span { color: var(--text-muted); font-size: 11px; }
.memory-card p { margin: 6px 0; font-size: 12.5px; line-height: 1.5; color: var(--text-secondary); white-space: pre-wrap; }
.memory-card-actions { display: flex; justify-content: flex-end; }
.memory-editor { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.memory-editor :deep(.el-input) { flex: 1; min-width: 140px; }
@media (max-width: 560px) { .memory-toolbar { align-items: flex-start; flex-direction: column; } }
</style>
