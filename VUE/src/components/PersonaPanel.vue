<template>
  <el-drawer
    v-model="visible"
    title="人物卡管理"
    size="min(500px, 100vw)"
    class="persona-drawer"
    @close="handleClose"
  >
    <div class="persona-panel">
      <div class="persona-list">
        <div 
          v-for="persona in personas" 
          :key="persona.id"
          class="persona-card"
          :class="{ active: selectedId === persona.id, 'is-default': persona.is_default }"
          @click="editPersona(persona)"
        >
          <el-avatar :size="44" :src="persona.avatar" class="persona-avatar">
            <el-icon><MagicStick /></el-icon>
          </el-avatar>
          <div class="persona-info">
            <div class="persona-name">
              {{ persona.name }}
              <el-tag v-if="persona.is_default" size="small" type="success" effect="light" class="default-tag">默认</el-tag>
              <el-tag v-if="persona.source === 'marketplace'" size="small" type="warning" effect="light" class="source-tag">卡片广场</el-tag>
            </div>
            <div class="persona-desc">{{ persona.description || '暂无描述' }}</div>
          </div>
          <div class="persona-actions" @click.stop>
            <el-button 
              v-if="!persona.is_default" 
              size="small" 
              text 
              @click="setDefault(persona.id)"
            >
              设为默认
            </el-button>
            <el-button 
              size="small" 
              text 
              type="primary"
              @click="editPersona(persona)"
            >
              编辑
            </el-button>
            <el-button
              size="small"
              text
              type="danger"
              @click="confirmDelete(persona.id)"
            >
              删除
            </el-button>
          </div>
        </div>

        <div v-if="personas.length === 0" class="empty-tip">
          <el-empty description="暂无人物卡，点击下方按钮创建" :image-size="80" />
        </div>
      </div>

      <div class="panel-footer">
        <span class="footer-count">人物卡 {{ personas.length }}/{{ PERSONA_CARD_LIMIT }}</span>
        <el-button
          type="primary"
          icon="Plus"
          :disabled="personas.length >= PERSONA_CARD_LIMIT"
          @click="openCreateDialog"
        >
          新建人物卡
        </el-button>
      </div>
    </div>

    <!-- 编辑/创建对话框 -->
    <el-dialog
      v-model="editDialogVisible"
      :title="editingPersona ? '编辑人物卡' : '新建人物卡'"
      width="min(560px, 94vw)"
      @close="resetForm"
    >
      <el-form :model="form" label-position="top" class="persona-form">
        <!-- 头像上传：居中大图预览，与系统卡片风格一致 -->
        <el-form-item>
          <div class="form-avatar-section">
            <div class="form-avatar-preview">
              <img v-if="form.avatar" :src="form.avatar" alt="" />
              <el-icon v-else class="form-avatar-placeholder"><MagicStick /></el-icon>
            </div>
            <el-upload
              :show-file-list="false"
              :before-upload="handleAvatarUpload"
              accept="image/*"
            >
              <el-button size="small" type="primary" plain>
                <el-icon><Upload /></el-icon> 上传头像
              </el-button>
            </el-upload>
          </div>
        </el-form-item>

        <div class="form-card">
          <el-form-item label="角色名称">
            <el-input v-model="form.name" placeholder="如：加藤惠" maxlength="1000" />
          </el-form-item>
          <el-form-item label="角色简介">
            <el-input
              v-model="form.description"
              type="textarea"
              :rows="2"
              :autosize="false"
              resize="none"
              placeholder="简短描述角色特点"
              maxlength="1000"
            />
          </el-form-item>
        </div>

        <div class="form-card">
          <el-form-item label="系统提示词">
            <el-input
              v-model="form.system_prompt"
              type="textarea"
              :rows="8"
              :autosize="false"
              resize="none"
              placeholder="详细的角色设定，指导 AI 如何扮演这个角色..."
              maxlength="10000"
            />
          </el-form-item>
          <el-form-item label="开场问候语">
            <el-input
              v-model="form.greeting"
              type="textarea"
              :rows="2"
              :autosize="false"
              resize="none"
              placeholder="角色第一次打招呼时说的话（可选）"
              maxlength="1000"
            />
          </el-form-item>
        </div>

        <el-form-item>
          <el-checkbox v-model="form.is_default">设为默认角色</el-checkbox>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="savePersona" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </el-drawer>
</template>

<script setup>
import logger from '@/utils/logger';
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, Upload } from '@element-plus/icons-vue'
import { personaApi, uploadApi } from '../utils/resAi'

const props = defineProps({
  modelValue: Boolean,
  selectedId: [String, Number],
})

const emit = defineEmits(['update:modelValue', 'update:selectedId', 'persona-changed', 'persona-deleted'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

// 人物卡（AI 人设）数量上限，与后端 PERSONA_CARD_LIMIT 保持一致
const PERSONA_CARD_LIMIT = 10

const personas = ref([])
const editDialogVisible = ref(false)
const editingPersona = ref(null)
const saving = ref(false)

const defaultForm = {
  name: '',
  description: '',
  avatar: '',
  system_prompt: '',
  greeting: '',
  is_default: false,
  persona_type: 'ai',
}

const form = reactive({ ...defaultForm })

watch(() => props.modelValue, (val) => {
  if (val) {
    loadPersonas()
  }
})

async function loadPersonas() {
  try {
    const res = await personaApi.list()
    if (res.code === 200) {
      personas.value = res.data
    }
  } catch (e) {
    logger.error('加载角色失败', e)
  }
}

function handleClose() {
  visible.value = false
}

function selectPersona(persona) {
  emit('update:selectedId', persona.id)
  emit('persona-changed', persona)
}

function setDefault(id) {
  personaApi.setDefault(id).then(res => {
    if (res.code === 200) {
      ElMessage.success('已设为默认')
      loadPersonas()
      emit('persona-changed', res.data)
    }
  })
}

function editPersona(persona) {
  editingPersona.value = persona
  Object.assign(form, {
    name: persona.name,
    description: persona.description || '',
    avatar: persona.avatar || '',
    system_prompt: persona.system_prompt,
    greeting: persona.greeting || '',
    is_default: persona.is_default,
    persona_type: persona.persona_type || 'ai',
  })
  editDialogVisible.value = true
}

/**
 * 供侧边栏「人物卡」列表点击后直接打开对应人物卡的编辑详情。
 * 打开抽屉 → 拉取最新列表 → 弹出编辑对话框。
 */
async function openEdit(persona) {
  visible.value = true
  await loadPersonas()
  const fresh = personas.value.find(p => p.id === persona.id) || persona
  editPersona(fresh)
}

defineExpose({ openEdit })

function openCreateDialog() {
  editingPersona.value = null
  resetForm()
  editDialogVisible.value = true
}

function resetForm() {
  Object.assign(form, defaultForm)
}

async function handleAvatarUpload(file) {
  try {
    const res = await uploadApi.uploadImage(file)
    if (res.code === 200) {
      form.avatar = res.data.url
      ElMessage.success('上传成功')
    }
  } catch (e) {
    ElMessage.error('上传失败')
  }
  return false
}

async function savePersona() {
  if (!form.name.trim()) {
    ElMessage.warning('请输入角色名称')
    return
  }
  if (!form.system_prompt.trim()) {
    ElMessage.warning('请输入系统提示词')
    return
  }

  // 新建时前端先拦截上限，避免无谓请求
  if (!editingPersona.value && personas.value.length >= PERSONA_CARD_LIMIT) {
    ElMessage.warning(`人物卡数量已达上限（${PERSONA_CARD_LIMIT} 个），请先删除部分人物卡`)
    return
  }

  saving.value = true
  try {
    let res
    if (editingPersona.value) {
      res = await personaApi.update(editingPersona.value.id, form)
    } else {
      res = await personaApi.create(form)
    }
    if (res.code === 200) {
      ElMessage.success(editingPersona.value ? '更新成功' : '创建成功')
      editDialogVisible.value = false
      loadPersonas()
      emit('persona-changed', res.data)
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

function confirmDelete(id) {
  ElMessageBox.confirm('确定删除这个人物卡吗？', '确认删除', {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消',
  }).then(async () => {
    const res = await personaApi.remove(id)
    if (res.code === 200) {
      ElMessage.success('已删除')
      loadPersonas()
      // 通知主页面同步侧边栏人物卡列表（删除后卡片广场恢复为「添加」状态）
      emit('persona-deleted', id)
    }
  }).catch(() => {})
}
</script>

<style scoped>
.persona-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.persona-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
}

.persona-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: 8px;
  border: 1px solid #ebeef5;
  margin-bottom: 10px;
  cursor: pointer;
  transition: all 0.2s;
}

.persona-card:hover {
  border-color: #dcdfe6;
  background: #fafafa;
}

.persona-card.active {
  border-color: var(--brand);
  background: var(--brand-soft);
}

.persona-avatar {
  flex-shrink: 0;
}

.persona-info {
  flex: 1;
  min-width: 0;
}

.persona-name {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  display: flex;
  align-items: center;
  gap: 6px;
}

.default-tag {
  font-size: 11px;
}

.persona-desc {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.persona-actions {
  display: none;
  flex-shrink: 0;
}

.persona-card:hover .persona-actions {
  display: flex;
  gap: 4px;
}

.empty-tip {
  padding: 40px 0;
}

.panel-footer {
  padding-top: 16px;
  border-top: 1px solid #ebeef5;
  margin-top: 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.footer-count {
  font-size: 12px;
  color: var(--text-muted, #909399);
  white-space: nowrap;
}

/* 来源标签：与「默认 / 系统」同款小方框 */
.source-tag {
  font-size: 11px;
}

.persona-name :deep(.el-tag) {
  margin-right: 0;
  padding: 0 5px;
  height: 18px;
  line-height: 17px;
}

/* 编辑/新建对话框：与系统整体风格一致的卡片式表单 */
.persona-form {
  padding: 4px 8px;
}

.persona-form :deep(.el-form-item__label) {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #303133);
  padding-bottom: 6px;
}

.form-avatar-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 16px 0 8px;
}

.form-avatar-preview {
  width: 96px;
  height: 96px;
  border-radius: 50%;
  overflow: hidden;
  background: linear-gradient(135deg, #eef3fc, #e6edfa);
  border: 2px solid var(--border-color, #e4e7ed);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
}

.form-avatar-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.form-avatar-placeholder {
  font-size: 32px;
  color: #bfc9dc;
}

.form-card {
  background: var(--surface, #f5f7fa);
  border: 1px solid var(--border-color, #e4e7ed);
  border-radius: 14px;
  padding: 16px;
  margin-bottom: 16px;
}

.form-card :deep(.el-textarea__inner) {
  background: var(--bg, #ffffff);
  border-radius: 10px;
  resize: none;
}

.form-card :deep(.el-input__wrapper) {
  background: var(--bg, #ffffff);
  border-radius: 10px;
}

/* ===== 移动端响应式 ===== */
@media (max-width: 768px) {
  .persona-card {
    flex-wrap: wrap;
    align-items: flex-start;
  }
  /* 移动端无 hover，操作按钮常驻显示 */
  .persona-actions,
  .persona-card:hover .persona-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    width: 100%;
    margin-left: 56px;
  }
  .avatar-upload {
    width: 100%;
  }
  .persona-desc {
    white-space: normal;
  }
}

/* 超窄屏（iPhone SE 一类）：取消操作按钮的头像缩进，把宽度让给按钮本身 */
@media (max-width: 420px) {
  .persona-actions,
  .persona-card:hover .persona-actions {
    margin-left: 0;
  }
}
</style>
