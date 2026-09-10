<template>
  <el-drawer
    v-model="visible"
    title="角色人设管理"
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
          @click="selectPersona(persona)"
        >
          <el-avatar :size="44" :src="persona.avatar" class="persona-avatar">
            <el-icon><MagicStick /></el-icon>
          </el-avatar>
          <div class="persona-info">
            <div class="persona-name">
              {{ persona.name }}
              <el-tag v-if="persona.is_default" size="small" type="success" effect="light" class="default-tag">默认</el-tag>
              <el-tag v-if="persona.is_system" size="small" type="info" effect="light" class="system-tag">系统</el-tag>
              <el-tag v-if="persona.persona_type === 'user'" size="small" type="warning" effect="light" class="system-tag">用户</el-tag>
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
              v-if="!persona.is_system"
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
          <el-empty description="暂无角色，点击下方按钮创建" :image-size="80" />
        </div>
      </div>

      <div class="panel-footer">
        <el-button type="primary" icon="Plus" @click="openCreateDialog">
          新建角色
        </el-button>
      </div>
    </div>

    <!-- 编辑/创建对话框 -->
    <el-dialog 
      v-model="editDialogVisible" 
      :title="editingPersona ? '编辑角色' : '新建角色'"
      width="min(560px, 94vw)"
      @close="resetForm"
    >
      <el-form :model="form" label-width="80px" label-position="top">
        <el-form-item label="角色头像">
          <div class="avatar-upload">
            <el-avatar :size="64" :src="form.avatar" class="form-avatar">
              <el-icon><MagicStick /></el-icon>
            </el-avatar>
            <el-upload
              :show-file-list="false"
              :before-upload="handleAvatarUpload"
              accept="image/*"
            >
              <el-button size="small">上传头像</el-button>
            </el-upload>
          </div>
        </el-form-item>
        <el-form-item label="角色名称">
          <el-input v-model="form.name" placeholder="如：加藤惠" />
        </el-form-item>
        <el-form-item label="角色简介">
          <el-input v-model="form.description" placeholder="简短描述角色特点" />
        </el-form-item>
        <el-form-item label="系统提示词">
          <el-input 
            v-model="form.system_prompt" 
            type="textarea" 
            :rows="8"
            placeholder="详细的角色设定，指导 AI 如何扮演这个角色..."
          />
        </el-form-item>
        <el-form-item label="开场问候语">
          <el-input 
            v-model="form.greeting" 
            type="textarea" 
            :rows="2"
            placeholder="角色第一次打招呼时说的话（可选）"
          />
        </el-form-item>
        <el-form-item v-if="!editingPersona || !editingPersona.is_system">
          <el-checkbox v-model="form.is_default">设为默认角色</el-checkbox>
        </el-form-item>
        <el-form-item label="人设类型">
          <el-radio-group v-model="form.persona_type">
            <el-radio-button value="ai">AI 人设</el-radio-button>
            <el-radio-button value="user">用户人设</el-radio-button>
          </el-radio-group>
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
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { personaApi, uploadApi } from '../utils/resAi'

const props = defineProps({
  modelValue: Boolean,
  selectedId: [String, Number],
})

const emit = defineEmits(['update:modelValue', 'update:selectedId', 'persona-changed'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

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
    console.error('加载角色失败', e)
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
    }
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

function confirmDelete(id) {
  ElMessageBox.confirm('确定删除这个角色吗？', '确认删除', {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消',
  }).then(async () => {
    const res = await personaApi.remove(id)
    if (res.code === 200) {
      ElMessage.success('已删除')
      loadPersonas()
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

.system-tag {
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
}

.avatar-upload {
  display: flex;
  align-items: center;
  gap: 12px;
}

.form-avatar {
  border: 2px solid #ebeef5;
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
</style>
