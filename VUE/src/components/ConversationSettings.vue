<template>
  <el-drawer
    :model-value="modelValue"
    @update:model-value="(v) => emit('update:modelValue', v)"
    :title="t('对话设置', 'Conversation Settings')"
    size="min(420px, 100vw)"
  >
    <div class="conv-settings">
      <p class="drawer-desc">
        {{ t('以下设置仅在当前对话生效', 'These settings only apply to the current conversation.') }}
      </p>
      <div v-if="!conversation" class="empty-tip">
        <el-empty :description="t('请先新建或选择一个对话', 'Create or select a conversation first')" :image-size="70" />
      </div>

      <template v-else>
        <!-- 对话使用的模型（当前对话生效） -->
        <div class="cv-section">
          <div class="cv-title">{{ t('使用模型配置', 'Model Config') }}</div>
          <div class="cv-row">
            <el-select
              v-model="form.provider_id"
              clearable
              :placeholder="t('选择模型配置', 'Select a config')"
              style="width: 100%"
              @change="onProviderChange"
            >
              <el-option
                v-for="p in enabledConfigs"
                :key="p.id"
                :label="p.name"
                :value="p.id"
              />
            </el-select>
            <el-select
              v-if="selectedProvider"
              v-model="form.model_id"
              clearable
              :placeholder="t('选择该配置内的模型', 'Select a model in this config')"
              style="width: 100%"
            >
              <el-option
                v-for="m in providerModels(selectedProvider)"
                :key="m.id"
                :label="m.name || m.model_id"
                :value="m.model_id"
              />
            </el-select>
          </div>
        </div>

        <!-- AI 人设 -->
        <div class="cv-section">
          <div class="cv-title">{{ t('AI 人设', 'AI Persona') }}</div>
          <div class="cv-row">
            <el-select
              v-model="form.persona_id"
              clearable
              :placeholder="t('使用默认AI人设', 'Use default AI persona')"
              style="width: 100%"
            >
              <el-option
                v-for="p in aiPersonas"
                :key="p.id"
                :label="p.is_default ? t('默认') + ' · ' + p.name : p.name"
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
          </div>
        </div>

        <!-- 用户人设 -->
        <div class="cv-section">
          <div class="cv-title">{{ t('用户人设', 'User Persona') }}</div>
          <p class="cv-hint-text">{{ t('用户人设会在每次对话开始时注入到消息最前端', 'User persona is injected at the start of each conversation') }}</p>
          <div class="cv-row">
            <el-select
              v-model="form.user_persona_id"
              clearable
              :placeholder="t('不使用用户人设', 'No user persona')"
              style="width: 100%"
            >
              <el-option
                v-for="p in userPersonas"
                :key="p.id"
                :label="p.name"
                :value="p.id"
              >
                <div class="persona-opt">
                  <el-avatar :size="24" :src="p.avatar" class="opt-avatar">
                    <el-icon><User /></el-icon>
                  </el-avatar>
                  <span>{{ p.name }}</span>
                </div>
              </el-option>
            </el-select>
          </div>
        </div>

        <!-- 头像：AI / 用户可分别设置，仅当前对话生效 -->
        <div class="cv-section">
          <div class="cv-title">{{ t('头像', 'Avatars') }}</div>
          <div class="cv-avatar-grid">
            <div class="cv-avatar-block">
              <span class="cv-avatar-label">{{ t('AI 头像', 'AI Avatar') }}</span>
              <el-avatar :size="52" :src="form.ai_avatar || ''" class="cv-avatar">
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
            <div class="cv-avatar-block">
              <span class="cv-avatar-label">{{ t('用户头像', 'User Avatar') }}</span>
              <el-avatar :size="52" :src="form.user_avatar || props.userAvatar || ''" class="cv-avatar">
                <el-icon><User /></el-icon>
              </el-avatar>
              <div class="cv-image-actions">
                <el-upload
                  :show-file-list="false"
                  :before-upload="handleUserAvatarUpload"
                  accept="image/*"
                >
                  <el-button size="small">{{ t('上传', 'Upload') }}</el-button>
                </el-upload>
                <el-button size="small" plain :disabled="!form.user_avatar" @click="form.user_avatar = null">
                  {{ t('清除', 'Clear') }}
                </el-button>
              </div>
            </div>
          </div>
        </div>

        <!-- 背景图片 -->
        <div class="cv-section">
          <div class="cv-title">{{ t('背景图片', 'Background') }}</div>
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
          <el-radio-group v-model="form.background_cover" style="margin-top: 6px">
            <el-radio-button value="contain">{{ t('完整可见', 'Show Entire Image') }}</el-radio-button>
            <el-radio-button value="cover">{{ t('覆盖背景', 'Cover Background') }}</el-radio-button>
          </el-radio-group>
        </div>

        <!-- AI 参数（当前对话模型单独设置） -->
        <div class="cv-section">
          <div class="cv-title">{{ t('AI 参数', 'AI Parameters') }}</div>

          <div class="param-row">
            <div class="slider-label">{{ t('温度', 'Temperature') }}</div>
            <div class="slider-control">
              <el-slider
                :model-value="form.temperature == null ? generalTemperature : form.temperature"
                :min="0" :max="2" :step="0.1"
                @update:model-value="(v) => form.temperature = v"
                style="flex: 1; margin-right: 16px"
              />
              <span class="slider-value">{{ form.temperature == null ? t('系统默认', 'System default') : form.temperature.toFixed(1) }}</span>
            </div>
            <el-button v-if="form.temperature != null" size="small" text plain @click="form.temperature = null">
              {{ t('恢复系统默认', 'Use system default') }}
            </el-button>
          </div>

          <div class="param-row">
            <div class="slider-label">{{ t('频率惩罚', 'Frequency Penalty') }}</div>
            <div class="slider-control">
              <el-slider
                :model-value="form.frequency_penalty == null ? generalFrequencyPenalty : form.frequency_penalty"
                :min="-2" :max="2" :step="0.1"
                @update:model-value="(v) => form.frequency_penalty = v"
                style="flex: 1; margin-right: 16px"
              />
              <span class="slider-value">{{ form.frequency_penalty == null ? t('系统默认', 'System default') : form.frequency_penalty.toFixed(1) }}</span>
            </div>
            <el-button v-if="form.frequency_penalty != null" size="small" text plain @click="form.frequency_penalty = null">
              {{ t('恢复系统默认', 'Use system default') }}
            </el-button>
          </div>

          <div class="param-row">
            <div class="slider-label">{{ t('存在惩罚', 'Presence Penalty') }}</div>
            <div class="slider-control">
              <el-slider
                :model-value="form.presence_penalty == null ? generalPresencePenalty : form.presence_penalty"
                :min="-2" :max="2" :step="0.1"
                @update:model-value="(v) => form.presence_penalty = v"
                style="flex: 1; margin-right: 16px"
              />
              <span class="slider-value">{{ form.presence_penalty == null ? t('系统默认', 'System default') : form.presence_penalty.toFixed(1) }}</span>
            </div>
            <el-button v-if="form.presence_penalty != null" size="small" text plain @click="form.presence_penalty = null">
              {{ t('恢复系统默认', 'Use system default') }}
            </el-button>
          </div>
        </div>

        <!-- 语音播报 -->
        <div class="cv-section">
          <div class="cv-title">{{ t('语音播报', 'Voice') }}</div>
          <div class="cv-row voice-row">
            <div class="voice-item">
              <span class="slider-label">{{ t('自动播报 AI 回复', 'Auto-play AI replies') }}</span>
              <el-switch v-model="form.auto_play_voice" />
            </div>
          </div>
        </div>

        <!-- 消息框透明度 -->
        <div class="cv-section">
          <div class="cv-title">{{ t('消息框透明度', 'Transparency') }}</div>
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
              {{ form.message_opacity == null ? t('系统默认', 'System default') : Math.round(form.message_opacity * 100) + '%' }}
            </span>
          </div>
          <el-button v-if="form.message_opacity != null" size="small" plain @click="form.message_opacity = null" style="margin-top: 8px">
            {{ t('恢复系统默认', 'Use system default') }}
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
import { MagicStick, User } from '@element-plus/icons-vue'
import { uploadApi } from '../utils/resAi'
import { t } from '../i18n'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  conversation: { type: Object, default: null },
  aiPersonas: { type: Array, default: () => [] },
  userPersonas: { type: Array, default: () => [] },
  configs: { type: Array, default: () => [] },
  generalOpacity: { type: Number, default: 0.9 },
  userAvatar: { type: String, default: '' },
  generalTemperature: { type: Number, default: 0.8 },
  generalFrequencyPenalty: { type: Number, default: 0.0 },
  generalPresencePenalty: { type: Number, default: 0.0 },
})

const emit = defineEmits(['update:modelValue', 'save'])

const saving = ref(false)
// 仅列出已启用（enabled）的模型配置供当前对话选择
const enabledConfigs = computed(() => (props.configs || []).filter(p => p.enabled !== false))
const selectedProvider = computed(() =>
  enabledConfigs.value.find(p => p.id == form.provider_id) || null
)
// 取某配置内已启用的模型
function providerModels(p) {
  return (p?.models || []).filter(m => m.enabled !== false)
}
const form = reactive({ provider_id: null, model_id: null, persona_id: null, user_persona_id: null, ai_avatar: null, user_avatar: null, background_image: null, background_cover: 'contain', message_opacity: null, temperature: null, frequency_penalty: null, presence_penalty: null, auto_play_voice: false })

function resetForm() {
  const conv = props.conversation || {}
  form.provider_id = conv.provider_id != null ? conv.provider_id : null
  form.model_id = conv.model_id || null
  form.persona_id = conv.persona_id != null ? conv.persona_id : null
  form.user_persona_id = conv.user_persona_id != null ? conv.user_persona_id : null
  form.ai_avatar = conv.ai_avatar || null
  form.user_avatar = conv.user_avatar || null
  form.background_image = conv.background_image || null
  form.background_cover = conv.background_cover || 'contain'
  form.message_opacity = (conv.message_opacity != null && conv.message_opacity !== '') ? conv.message_opacity : null
  form.temperature = (conv.temperature != null && conv.temperature !== '') ? conv.temperature : null
  form.frequency_penalty = (conv.frequency_penalty != null && conv.frequency_penalty !== '') ? conv.frequency_penalty : null
  form.presence_penalty = (conv.presence_penalty != null && conv.presence_penalty !== '') ? conv.presence_penalty : null
  form.auto_play_voice = !!conv.auto_play_voice
}

function onProviderChange() {
  // 切换配置后，若原模型不属于新配置则清空
  const models = providerModels(selectedProvider.value)
  if (!models.some(m => m.model_id === form.model_id)) {
    form.model_id = null
  }
}

watch(() => props.modelValue, (val) => {
  if (val) resetForm()
})

const bgPreviewStyle = computed(() => {
  if (form.background_image) {
    return { backgroundImage: `url(${form.background_image})`, backgroundSize: 'contain', backgroundPosition: 'center', backgroundRepeat: 'no-repeat' }
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

async function handleUserAvatarUpload(file) {
  try {
    const res = await uploadApi.uploadImage(file)
    if (res.code === 200) {
      form.user_avatar = res.data.url
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
    provider_id: form.provider_id != null ? form.provider_id : null,
    model_id: form.model_id || null,
    persona_id: form.persona_id != null ? form.persona_id : null,
    user_persona_id: form.user_persona_id != null ? form.user_persona_id : null,
    ai_avatar: form.ai_avatar || null,
    user_avatar: form.user_avatar || null,
    background_image: form.background_image || null,
    background_cover: form.background_cover || 'contain',
    message_opacity: form.message_opacity != null ? Number(form.message_opacity) : null,
    temperature: form.temperature != null ? Number(form.temperature) : null,
    frequency_penalty: form.frequency_penalty != null ? Number(form.frequency_penalty) : null,
    presence_penalty: form.presence_penalty != null ? Number(form.presence_penalty) : null,
    auto_play_voice: !!form.auto_play_voice,
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

/* 头像区：AI / 用户并排 */
.cv-avatar-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.cv-avatar-block {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
  padding: 14px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  background: var(--surface);
}
.cv-avatar-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

/* AI 参数行：标签 + 滑块 + 恢复通用 */
.param-row {
  display: grid;
  grid-template-columns: 88px 1fr auto;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}
.slider-label {
  font-size: 13px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.voice-row {
  gap: 10px;
}
.voice-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

@media (max-width: 520px) {
  .cv-avatar-grid {
    grid-template-columns: 1fr;
  }
  .param-row {
    grid-template-columns: 1fr;
    gap: 8px;
    padding-bottom: 10px;
    border-bottom: 1px dashed var(--border-color);
  }
}

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
.cv-hint-text { font-size: 11px; color: var(--text-muted); margin-bottom: 8px; }

.slider-control { display: flex; align-items: center; }
.slider-value {
  min-width: 60px; text-align: right; font-size: 13px;
  color: var(--text-muted); font-variant-numeric: tabular-nums;
}
</style>