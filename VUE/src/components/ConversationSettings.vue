<template>
  <el-drawer
    :model-value="modelValue"
    @update:model-value="(v) => emit('update:modelValue', v)"
    :title="t('对话设置', 'Conversation Settings')"
    size="min(420px, 100vw)"
  >
    <div class="conv-settings">
      <p class="drawer-desc">
        {{ t('以下设置仅作用于当前对话；未设置的项目将使用通用设置。', 'These only apply to the current conversation. Items left unset use the general settings.') }}
      </p>
      <div v-if="!conversation" class="empty-tip">
        <el-empty :description="t('请先新建或选择一个对话', 'Create or select a conversation first')" :image-size="70" />
      </div>

      <template v-else>
        <!-- 人设（独立） -->
        <div class="cv-section">
          <div class="cv-title">{{ t('独立人设', 'Per-chat Persona') }}</div>
          <div class="cv-row">
            <el-select
              v-model="form.persona_id"
              clearable
              :placeholder="t('使用默认人设', 'Use default persona')"
              style="width: 100%"
            >
              <el-option
                v-for="p in personas"
                :key="p.id"
                :label="p.is_default ? t('默认人设') + ' · ' + p.name : p.name"
                :value="p.id"
              >
                <div class="persona-opt">
                  <el-avatar :size="24" :src="p.avatar" class="opt-avatar">
                    <el-icon><MagicStick /></el-icon>
                  </el-avatar>
                  <span>{{ p.name }}</span>
                </div>
              </el-option>
            </el-select>
            <div class="cv-hint">{{ t('留空则使用通用默认人设', 'Leave empty to use the default persona') }}</div>
          </div>
        </div>

        <!-- 独立 AI 头像 -->
        <div class="cv-section">
          <div class="cv-title">{{ t('独立 AI 头像', 'Per-chat AI Avatar') }}</div>
          <div class="cv-image-row">
            <el-avatar :size="56" :src="form.ai_avatar || ''" class="cv-avatar">
              <el-icon><MagicStick /></el-icon>
            </el-avatar>
            <div class="cv-image-actions">
              <el-upload
                :show-file-list="false"
                :before-upload="handleAvatarUpload"
                accept="image/*"
              >
                <el-button size="small">{{ t('上传', 'Upload') }}</el-button>
              </el-upload>
              <el-button size="small" plain :disabled="!form.ai_avatar" @click="form.ai_avatar = null">
                {{ t('清除', 'Clear') }}
              </el-button>
            </div>
          </div>
        </div>

        <!-- 独立背景图片 -->
        <div class="cv-section">
          <div class="cv-title">{{ t('独立背景图片', 'Per-chat Background') }}</div>
          <div class="cv-image-row">
            <div class="bg-preview" :style="bgPreviewStyle">
              <span v-if="!form.background_image" class="bg-placeholder">{{ t('无', 'None') }}</span>
            </div>
            <div class="cv-image-actions">
              <el-upload
                :show-file-list="false"
                :before-upload="handleBgUpload"
                accept="image/*"
              >
                <el-button size="small">{{ t('上传', 'Upload') }}</el-button>
              </el-upload>
              <el-button size="small" plain :disabled="!form.background_image" @click="form.background_image = null">
                {{ t('清除', 'Clear') }}
              </el-button>
            </div>
          </div>
        </div>

        <!-- 独立消息框透明度 -->
        <div class="cv-section">
          <div class="cv-title">{{ t('独立消息框透明度', 'Per-chat Transparency') }}</div>
          <div class="slider-control">
            <el-slider
              :model-value="form.message_opacity == null ? generalOpacity : form.message_opacity"
              :min="0.1"
              :max="1"
              :step="0.05"
              @update:model-value="(v) => form.message_opacity = v"
              style="flex: 1; margin-right: 16px"
            />
            <span class="slider-value">
              {{ form.message_opacity == null ? t('通用', 'Default') : Math.round(form.message_opacity * 100) + '%' }}
            </span>
          </div>
          <el-button v-if="form.message_opacity != null" size="small" plain @click="form.message_opacity = null" style="margin-top: 8px">
            {{ t('恢复通用', 'Use default') }}
          </el-button>
        </div>
      </template>
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">{{ t('取消', 'Cancel') }}</el-button>
      <el-button type="primary" :disabled="!conversation" :loading="saving" @click="save">
        {{ t('保存', 'Save') }}
      </el-button>
    </template>
  </el-drawer>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { uploadApi } from '../utils/resAi'
import { t } from '../i18n'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  conversation: { type: Object, default: null },
  personas: { type: Array, default: () => [] },
  generalOpacity: { type: Number, default: 0.9 },
})

const emit = defineEmits(['update:modelValue', 'save'])

const saving = ref(false)
const form = reactive({ persona_id: null, ai_avatar: null, background_image: null, message_opacity: null })

function resetForm() {
  const conv = props.conversation || {}
  form.persona_id = conv.persona_id != null ? conv.persona_id : null
  form.ai_avatar = conv.ai_avatar || null
  form.background_image = conv.background_image || null
  form.message_opacity = (conv.message_opacity != null && conv.message_opacity !== '') ? conv.message_opacity : null
}

watch(() => props.modelValue, (val) => {
  if (val) resetForm()
})

const bgPreviewStyle = computed(() => {
  if (form.background_image) {
    return { backgroundImage: `url(${form.background_image})`, backgroundSize: 'cover', backgroundPosition: 'center' }
  }
  return {}
})

async function handleAvatarUpload(file) {
  try {
    const res = await uploadApi.uploadImage(file)
    if (res.code === 200) {
      form.ai_avatar = res.data.url
      ElMessage.success(t('上传成功', 'Uploaded'))
    }
  } catch (e) {
    ElMessage.error(t('上传失败', 'Upload failed'))
  }
  return false
}

async function handleBgUpload(file) {
  try {
    const res = await uploadApi.uploadImage(file)
    if (res.code === 200) {
      form.background_image = res.data.url
      ElMessage.success(t('上传成功', 'Uploaded'))
    }
  } catch (e) {
    ElMessage.error(t('上传失败', 'Upload failed'))
  }
  return false
}

function save() {
  saving.value = true
  emit('save', {
    persona_id: form.persona_id != null ? form.persona_id : null,
    ai_avatar: form.ai_avatar || null,
    background_image: form.background_image || null,
    message_opacity: form.message_opacity != null ? Number(form.message_opacity) : null,
  })
  setTimeout(() => { saving.value = false }, 500)
}
</script>

<style scoped>
.conv-settings { padding: 4px 0; }
.drawer-desc { font-size: 12px; color: var(--text-muted); margin-bottom: 16px; }
.empty-tip { margin-top: 40px; }

.cv-section { margin-bottom: 24px; }
.cv-title {
  font-size: 13px; font-weight: 600; color: var(--text-primary);
  margin-bottom: 12px; padding-bottom: 6px; border-bottom: 1px solid var(--border-color);
}
.cv-row { display: flex; flex-direction: column; gap: 6px; }

.persona-opt { display: flex; align-items: center; gap: 8px; }
.opt-avatar { flex-shrink: 0; }

.cv-image-row { display: flex; align-items: center; gap: 14px; }
.cv-avatar { flex-shrink: 0; border: 2px solid var(--border-color); }
.cv-image-actions { display: flex; flex-direction: column; gap: 8px; }

.bg-preview {
  width: 88px; height: 60px; border-radius: 8px;
  border: 1px solid var(--border-color);
  display: flex; align-items: center; justify-content: center;
  background: var(--surface-hover);
  background-size: cover; background-position: center;
  flex-shrink: 0;
}
.bg-placeholder { font-size: 12px; color: var(--text-muted); }
.cv-hint { font-size: 11px; color: var(--text-muted); }

.slider-control { display: flex; align-items: center; }
.slider-value {
  min-width: 60px; text-align: right; font-size: 13px;
  color: var(--text-muted); font-variant-numeric: tabular-nums;
}
</style>