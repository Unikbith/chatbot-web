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
        <!-- 人物设定 -->
        <section class="cv-panel">
          <header class="cv-panel__head">
            <span class="cv-tick" aria-hidden="true"></span>
            <h3 class="cv-panel__title">{{ t('人物设定', 'Persona') }}</h3>
          </header>
          <p class="cv-panel__hint">{{ t('决定 AI 在本对话中的性格与口吻', 'Shapes how the AI behaves in this chat') }}</p>
          <el-select
            v-model="form.persona_id"
            clearable
            class="cv-field"
            :placeholder="t('使用默认AI人设', 'Use default AI persona')"
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
        </section>

        <!-- 提示词兜底：默认关闭，开启才会把后端写死的兜底词接在人物设定后面 -->
        <section class="cv-panel">
          <header class="cv-panel__head">
            <span class="cv-tick" aria-hidden="true"></span>
            <h3 class="cv-panel__title">{{ t('提示词兜底', 'Fallback Prompt') }}</h3>
          </header>
          <div class="cv-toggle">
            <div class="cv-toggle__text">
              <span class="cv-toggle__label">{{ t('开启后生成的内容（你懂的）', 'Enable fallback prompt') }}</span>
              <span class="cv-toggle__hint">
                {{ t('稳定生成内容后可关闭，减少token消耗', 'Enable only when the AI cannot produce what you want; turn it off once generation is stable to save tokens') }}
              </span>
            </div>
            <el-switch v-model="form.append_prompt_enabled" />
          </div>
        </section>

        <!-- 界面标记（富消息）：总开关。开启后 AI 才会输出标记，聊天页才会渲染成面板 -->
        <section class="cv-panel">
          <header class="cv-panel__head">
            <span class="cv-tick" aria-hidden="true"></span>
            <h3 class="cv-panel__title">{{ t('界面标记', 'Rich Markers') }}</h3>
          </header>
          <div class="cv-toggle">
            <div class="cv-toggle__text">
              <span class="cv-toggle__label">{{ t('让 AI 输出状态、内心与选项', 'Let the AI output status, inner voice and choices') }}</span>
              <span class="cv-toggle__hint">{{ t('关闭后回复只有正文', 'Off = plain text only') }}</span>
            </div>
            <el-switch v-model="form.rich_marker_enabled" />
          </div>

          <!-- 回复渲染模板：界面标记的子选项，关闭总开关时整块隐藏。
               用「按钮 + 预设面板」而不是下拉框：预设要靠预览才选得准 -->
          <div v-if="form.rich_marker_enabled" class="cv-sub">
            <div class="cv-toggle">
              <div class="cv-toggle__text">
                <span class="cv-toggle__label">{{ t('回复外观', 'Appearance') }}</span>
                <span class="cv-toggle__hint">{{ t('选配色与版式，可预览', 'Pick a theme, preview inside') }}</span>
              </div>
              <el-button size="small" class="tpl-open-btn" @click="openTemplatePanel">
                {{ currentTemplateName }}
              </el-button>
            </div>

            <!-- 提示词增强：把每轮该输出哪些构件的要求接进系统提示词 -->
            <div class="cv-toggle cv-toggle--sub">
              <div class="cv-toggle__text">
                <span class="cv-toggle__label">{{ t('提示词增强', 'Prompt Boost') }}</span>
                <span class="cv-toggle__hint">{{ t('每轮自动带上状态、面板、内心、选项', 'Adds panels every turn') }}</span>
              </div>
              <el-switch v-model="form.prompt_enhance" />
            </div>

            <!-- 回复长度：决定每轮正文写多长 -->
            <div class="cv-toggle cv-toggle--sub">
              <div class="cv-toggle__text">
                <span class="cv-toggle__label">{{ t('回复长度', 'Reply length') }}</span>
                <span class="cv-toggle__hint">{{ currentLengthDesc }}</span>
              </div>
              <el-select v-model="form.reply_length_id" size="small" class="tpl-select">
                <el-option
                  v-for="l in LENGTH_OPTIONS"
                  :key="l.id"
                  :value="l.id"
                  :label="t(l.name, l.nameEn)"
                />
              </el-select>
            </div>
          </div>
        </section>

        <!-- 渲染预设面板（实时预览 + 选择） -->
        <ReplyTemplatePanel
          ref="templatePanelRef"
          v-model="form.reply_template_id"
        />

        <!-- 记忆宫殿（滚动摘要）：沿用旧名，但不再提供查看入口 ——
             压缩结果现在直接显示在聊天框的「记忆回廊」里（长期记忆区） -->
        <section class="cv-panel">
          <header class="cv-panel__head">
            <span class="cv-tick" aria-hidden="true"></span>
            <h3 class="cv-panel__title">{{ t('记忆宫殿', 'Memory Palace') }}</h3>
          </header>
          <div class="cv-toggle">
            <div class="cv-toggle__text">
              <span class="cv-toggle__label">{{ t('每 N 轮压缩一次', 'Compress every N rounds') }}</span>
              <span class="cv-toggle__hint">{{ t('把较早对话压成一条摘要：既防止遗忘，又减少输入 token；压缩结果在聊天框的「记忆回廊」里查看', 'Condense older chat into one summary: keeps memory, cuts input tokens. View the result in the Memory Corridor inside the chat') }}</span>
            </div>
            <el-select v-model="form.summary_threshold" size="small" class="mp-select">
              <el-option v-for="n in 20" :key="n" :value="n" :label="`${n} ${t('轮', 'rounds')}`" />
            </el-select>
          </div>
        </section>

        <!-- 头像：AI / 用户可分别设置，仅当前对话生效 -->
        <section class="cv-panel">
          <header class="cv-panel__head">
            <span class="cv-tick" aria-hidden="true"></span>
            <h3 class="cv-panel__title">{{ t('头像', 'Avatars') }}</h3>
          </header>
          <div class="cv-avatar-grid">
            <div class="cv-avatar-block cv-avatar-block--ai">
              <span class="cv-avatar-label">
                <el-icon><MagicStick /></el-icon>
                {{ t('AI 头像', 'AI Avatar') }}
              </span>
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
              <span class="cv-avatar-label">
                <el-icon><User /></el-icon>
                {{ t('用户头像', 'User Avatar') }}
              </span>
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
        </section>

        <!-- 外观：背景图 + 消息框透明度 -->
        <section class="cv-panel">
          <header class="cv-panel__head">
            <span class="cv-tick" aria-hidden="true"></span>
            <h3 class="cv-panel__title">{{ t('外观', 'Appearance') }}</h3>
          </header>

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
                <el-button size="small">{{ t('背景图', 'Background') }}</el-button>
              </el-upload>
              <el-button size="small" plain :disabled="!form.background_image" @click="form.background_image = null">
                {{ t('清除', 'Clear') }}
              </el-button>
            </div>
          </div>

          <el-radio-group v-model="form.background_cover" class="cv-cover-group">
            <el-radio-button value="contain">{{ t('完整可见', 'Show Entire') }}</el-radio-button>
            <el-radio-button value="cover">{{ t('覆盖', 'Cover') }}</el-radio-button>
          </el-radio-group>

          <div class="cv-meter">
            <div class="cv-meter__head">
              <span class="cv-meter__label">{{ t('消息框透明度', 'Message opacity') }}</span>
              <span class="cv-meter__value">
                {{ Math.round((form.message_opacity == null ? generalOpacity : form.message_opacity) * 100) + '%' }}
              </span>
            </div>
            <el-slider
              :model-value="form.message_opacity == null ? generalOpacity : form.message_opacity"
              :min="0.1"
              :max="1"
              :step="0.05"
              class="cv-slider"
              @update:model-value="(v) => form.message_opacity = v"
            />
            <el-button
              v-if="form.message_opacity != null"
              size="small"
              text
              class="cv-reset"
              @click="form.message_opacity = null"
            >
              {{ t('恢复系统默认', 'Use system default') }}
            </el-button>
          </div>
        </section>

        <!-- 参数微调 -->
        <section class="cv-panel">
          <header class="cv-panel__head">
            <span class="cv-tick" aria-hidden="true"></span>
            <h3 class="cv-panel__title">{{ t('参数微调', 'Parameters') }}</h3>
            <span class="cv-panel__badge">{{ t('仅本对话', 'This chat only') }}</span>
          </header>

          <div v-for="p in paramDefs" :key="p.key" class="cv-meter">
            <div class="cv-meter__head">
              <span class="cv-meter__label">
                {{ p.label }}
                <el-tooltip :content="p.tip" placement="top">
                  <el-icon class="help-icon"><QuestionFilled /></el-icon>
                </el-tooltip>
              </span>
              <!-- 未单独设置时直接显示系统里那个值，而不是显示「系统默认」四个字 -->
              <span class="cv-meter__value">
                {{ Number(form[p.key] == null ? p.general : form[p.key]).toFixed(1) }}
              </span>
            </div>
            <div class="cv-meter__body">
              <el-slider
                :model-value="form[p.key] == null ? p.general : form[p.key]"
                :min="p.min"
                :max="p.max"
                :step="p.step"
                class="cv-slider"
                @update:model-value="(v) => form[p.key] = v"
              />
              <el-button
                size="small"
                text
                class="cv-reset"
                :disabled="form[p.key] == null"
                :aria-label="t('跟随系统', 'Follow system')"
                @click="form[p.key] = null"
              >
                {{ t('跟随系统', 'Follow system') }}
              </el-button>
            </div>
          </div>
        </section>

        <!-- 语音播报 -->
        <section class="cv-panel">
          <header class="cv-panel__head">
            <span class="cv-tick" aria-hidden="true"></span>
            <h3 class="cv-panel__title">{{ t('语音播报', 'Voice') }}</h3>
          </header>
          <div class="cv-toggle">
            <div class="cv-toggle__text">
              <span class="cv-toggle__label">{{ t('自动语音回复', 'Auto voice replies') }}</span>
              <span class="cv-toggle__hint">{{ t('AI 回复完成后自动朗读', 'Read AI replies aloud when they finish') }}</span>
            </div>
            <el-switch v-model="form.auto_play_voice" />
          </div>
        </section>

      </template>
    </div>

    <!-- 改动即时生效，不再需要点「保存」 -->
    <template #footer>
      <div class="cv-footer">
        <el-button type="primary" @click="emit('update:modelValue', false)">{{ t('完成', 'Done') }}</el-button>
      </div>
    </template>
  </el-drawer>

  <!-- 记忆宫殿的查看入口已移除：压缩结果直接显示在聊天框的「记忆回廊」里 -->
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, User, QuestionFilled } from '@element-plus/icons-vue'
import { uploadApi, conversationApi } from '../utils/resAi'
import {
  TEMPLATE_PRESETS, DEFAULT_PROTOCOL, DEFAULT_LENGTH, OUTPUT_LENGTH_LIST,
  DEFAULT_TEMPLATE_ID,
} from '../utils/replyTemplates'
import { t } from '../i18n'
import ReplyTemplatePanel from './ReplyTemplatePanel.vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  conversation: { type: Object, default: null },
  aiPersonas: { type: Array, default: () => [] },
  generalOpacity: { type: Number, default: 0.9 },
  userAvatar: { type: String, default: '' },
  generalTemperature: { type: Number, default: 0.8 },
  generalFrequencyPenalty: { type: Number, default: 0.0 },
  generalPresencePenalty: { type: Number, default: 0.0 },
})

const emit = defineEmits(['update:modelValue', 'save'])

// 渲染模板：用独立面板（带实时预览）选择，而不是下拉框
const templatePanelRef = ref(null)

/** 按钮上显示的当前预设名 */
const currentTemplateName = computed(() => {
  const p = TEMPLATE_PRESETS[form.reply_template_id] || TEMPLATE_PRESETS[DEFAULT_TEMPLATE_ID]
  return p ? t(p.name, p.nameEn) : t('档案风', 'Archive')
})

function openTemplatePanel() {
  templatePanelRef.value?.open()
}

// 回复长度三档
const LENGTH_OPTIONS = OUTPUT_LENGTH_LIST
const currentLengthDesc = computed(() => {
  const l = LENGTH_OPTIONS.find(x => x.id === form.reply_length_id)
    || LENGTH_OPTIONS.find(x => x.id === DEFAULT_LENGTH)
  return l ? t(l.desc, l.descEn) : ''
})

/** 从会话存的模板 JSON 里取出预设 id；没存过则用默认预设 */
function readTemplateId(raw) {
  if (!raw) return DEFAULT_TEMPLATE_ID
  try {
    const data = typeof raw === 'string' ? JSON.parse(raw) : raw
    const id = data && data.preset ? String(data.preset) : ''
    return TEMPLATE_PRESETS[id] ? id : DEFAULT_TEMPLATE_ID
  } catch (e) {
    return DEFAULT_TEMPLATE_ID
  }
}

/** 取回「提示词增强」开关：老数据没有该字段时默认开启 */
function readPromptEnhance(raw) {
  if (!raw) return true
  try {
    const data = typeof raw === 'string' ? JSON.parse(raw) : raw
    return data && data.enhance === false ? false : true
  } catch (e) {
    return true
  }
}

/** 取回回复长度；没存过则用默认档 */
function readLengthId(raw) {
  if (!raw) return DEFAULT_LENGTH
  try {
    const data = typeof raw === 'string' ? JSON.parse(raw) : raw
    const id = data && data.length ? String(data.length) : ''
    return OUTPUT_LENGTH_LIST.some(l => l.id === id) ? id : DEFAULT_LENGTH
  } catch (e) {
    return DEFAULT_LENGTH
  }
}

/**
 * 生成要落库的模板 JSON —— **只存选择项**，不存提示词正文。
 *
 * 提示词正文（标记词表 + 输出结构 + 篇幅要求）由后端 reply_spec 统一组合：
 * 之前正文存在会话里，新建对话还没有这份数据时就退回了旧提示词，
 * 表现为"开了增强却没内容、样式也没套上"。改由后端组合后，
 * 新建对话与历史对话的注入内容一致，也不会出现前后端两份文本漂移。
 */
function buildReplyTemplate() {
  const id = TEMPLATE_PRESETS[form.reply_template_id] ? form.reply_template_id : DEFAULT_TEMPLATE_ID
  const preset = TEMPLATE_PRESETS[id]
  if (!preset) return null
  return JSON.stringify({
    preset: preset.id,
    name: preset.name,
    protocol: DEFAULT_PROTOCOL,
    length: form.reply_length_id || DEFAULT_LENGTH,
    enhance: form.prompt_enhance !== false,
  })
}

// 仅列出已启用（enabled）的模型配置供当前对话选择
const form = reactive({
  persona_id: null, ai_avatar: null, user_avatar: null,
  background_image: null, background_cover: 'contain', message_opacity: null,
  temperature: null, frequency_penalty: null, presence_penalty: null,
  auto_play_voice: false,
  summary_threshold: 10,
  append_prompt_enabled: false,
  rich_marker_enabled: false,
  // 回复渲染模板：默认使用档案风（不再有"不使用"这一档）
  reply_template_id: 'archive',
  // 提示词增强：默认开启，把「每轮输出结构」接进系统提示词
  prompt_enhance: true,
  // 回复长度：short / medium / long
  reply_length_id: 'medium',
})

// 参数微调的量表定义：模板用 v-for 渲染，避免三段结构重复
const paramDefs = computed(() => ([
  {
    key: 'temperature', label: t('温度', 'Temperature'), min: 0, max: 2, step: 0.1,
    general: props.generalTemperature,
    tip: t('较高值使输出更随机创意，较低值更确定保守', 'Higher is more creative, lower is more focused'),
  },
  {
    key: 'frequency_penalty', label: t('频率惩罚', 'Frequency Penalty'), min: -2, max: 2, step: 0.1,
    general: props.generalFrequencyPenalty,
    tip: t('减少重复内容，值越高越倾向于使用新词', 'Reduce repetition'),
  },
  {
    key: 'presence_penalty', label: t('存在惩罚', 'Presence Penalty'), min: -2, max: 2, step: 0.1,
    general: props.generalPresencePenalty,
    tip: t('增加谈论新话题的可能性', 'Increase chance of new topics'),
  },
]))

function resetForm() {
  const conv = props.conversation || {}
  // 回填期间抑制自动保存，避免「打开抽屉」就被当成一次改动回写
  suppressAuto = true
  form.persona_id = conv.persona_id != null ? conv.persona_id : null
  form.ai_avatar = conv.ai_avatar || null
  form.user_avatar = conv.user_avatar || null
  form.background_image = conv.background_image || null
  form.background_cover = conv.background_cover || 'contain'
  form.message_opacity = (conv.message_opacity != null && conv.message_opacity !== '') ? conv.message_opacity : null
  form.temperature = (conv.temperature != null && conv.temperature !== '') ? conv.temperature : null
  form.frequency_penalty = (conv.frequency_penalty != null && conv.frequency_penalty !== '') ? conv.frequency_penalty : null
  form.presence_penalty = (conv.presence_penalty != null && conv.presence_penalty !== '') ? conv.presence_penalty : null
  form.auto_play_voice = !!conv.auto_play_voice
  form.summary_threshold = (conv.summary_threshold != null && conv.summary_threshold !== '') ? Number(conv.summary_threshold) : 10
  form.append_prompt_enabled = !!conv.append_prompt_enabled
  form.rich_marker_enabled = !!conv.rich_marker_enabled
  form.reply_template_id = readTemplateId(conv.reply_template)
  form.prompt_enhance = readPromptEnhance(conv.reply_template)
  form.reply_length_id = readLengthId(conv.reply_template)
  // 让本轮回填引起的 watch 在同一微任务里被忽略，下一轮才恢复自动保存
  nextTick(() => { suppressAuto = false })
}

watch(() => props.modelValue, (val) => {
  if (val) resetForm()
  else if (autoSaveTimer) { clearTimeout(autoSaveTimer); autoSaveTimer = null }
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

/* ---------- 自动保存：改动即存，无需再点「保存」 ---------- */
let autoSaveTimer = null
let suppressAuto = false

function buildPayload() {
  // 不再下发 provider_id / model_id：模型改由输入框左下角的模型选择器控制
  //（每轮消息实时生效）。后端 `if 'provider_id' in data` 语义下传 null
  // 会把对话的模型绑定清空，因此必须整项省略而不是置 null。
  return {
    persona_id: form.persona_id != null ? form.persona_id : null,
    ai_avatar: form.ai_avatar || null,
    user_avatar: form.user_avatar || null,
    background_image: form.background_image || null,
    background_cover: form.background_cover || 'contain',
    message_opacity: form.message_opacity != null ? Number(form.message_opacity) : null,
    temperature: form.temperature != null ? Number(form.temperature) : null,
    frequency_penalty: form.frequency_penalty != null ? Number(form.frequency_penalty) : null,
    presence_penalty: form.presence_penalty != null ? Number(form.presence_penalty) : null,
    auto_play_voice: !!form.auto_play_voice,
    summary_threshold: Number(form.summary_threshold) || 10,
    append_prompt_enabled: !!form.append_prompt_enabled,
    rich_marker_enabled: !!form.rich_marker_enabled,
    reply_template: buildReplyTemplate(),
  }
}

// _silent：自动保存不弹「已保存」提示，否则拖一下滑块就弹一次会很烦
watch(form, () => {
  if (suppressAuto) return
  clearTimeout(autoSaveTimer)
  autoSaveTimer = setTimeout(() => {
    emit('save', { ...buildPayload(), _silent: true })
  }, 400)
}, { deep: true })
</script>
<style scoped>
/* ============================================================
   对话设置 —— 工业实用（Industrial）调性
   分区用发丝边框的「面板」承载，每个面板左侧一道品牌色刻度作为锚点；
   数值区用等宽数字，读起来像仪表读数而不是表单。
   全部依赖项目既有主题变量，亮/暗自动适配。
   ============================================================ */

.conv-settings {
  --cv-hairline: var(--border-color);
  --cv-accent: var(--brand);
  padding: 0 0 4px;
}

/* 顶部说明：把「仅本对话生效」做成带竖线的注解，而非灰字 */
.drawer-desc {
  position: relative;
  margin: 0 0 20px;
  padding-left: 10px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary);
}
.drawer-desc::before {
  content: '';
  position: absolute;
  left: 0; top: 3px; bottom: 3px;
  width: 2px;
  border-radius: 1px;
  background: var(--cv-accent);
  opacity: 0.55;
}

.empty-tip { margin-top: 40px; }

/* ---------- 分区面板：发丝边框 + 极轻内阴影 ---------- */
.cv-panel {
  position: relative;
  margin-bottom: 14px;
  padding: 16px 16px 18px;
  border: 1px solid var(--cv-hairline);
  border-radius: 12px;
  background: var(--surface);
  box-shadow: 0 1px 0 rgba(0, 0, 0, 0.015);
  /* 顶部一道极细高光，制造面板的「金属边」而非纸片感 */
  overflow: hidden;
}
.cv-panel::before {
  content: '';
  position: absolute;
  inset: 0 0 auto;
  height: 1px;
  background: linear-gradient(
    90deg,
    transparent,
    color-mix(in srgb, var(--cv-accent) 22%, transparent),
    transparent
  );
}

/* 面板标题：刻度 + 标题 +（可选）作用域徽标 */
.cv-panel__head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.cv-tick {
  width: 3px;
  height: 13px;
  flex-shrink: 0;
  border-radius: 2px;
  background: var(--cv-accent);
}
.cv-panel__title {
  margin: 0;
  font-size: 13.5px;
  font-weight: 650;
  letter-spacing: 0.02em;
  color: var(--text-primary);
}
.cv-panel__badge {
  margin-left: auto;
  padding: 2px 7px;
  border-radius: 4px;
  border: 1px solid var(--cv-hairline);
  background: var(--surface-hover);
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.03em;
  color: var(--text-secondary);
  white-space: nowrap;
}
.cv-panel__hint {
  margin: 0 0 12px 11px;
  font-size: 11.5px;
  line-height: 1.55;
  color: var(--text-secondary);
}

.cv-field { width: 100%; }

.persona-opt {
  display: flex;
  align-items: center;
  gap: 8px;
}
.opt-avatar { flex-shrink: 0; }

/* ---------- 头像区 ---------- */
.cv-avatar-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.cv-avatar-block {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
  padding: 13px;
  border: 1px solid var(--cv-hairline);
  border-radius: 10px;
  /* 内层用极淡的暖色渐变，让卡片不是死白 */
  background:
    linear-gradient(160deg,
      color-mix(in srgb, var(--cv-accent) 5%, transparent),
      transparent 60%),
    var(--surface);
}
/* AI 侧用品牌色描边区分，用户侧保持中性 —— 不用图标以外的额外图示 */
.cv-avatar-block--ai {
  border-color: color-mix(in srgb, var(--cv-accent) 34%, var(--cv-hairline));
}
.cv-avatar-label {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}
.cv-avatar {
  flex-shrink: 0;
  border: 1.5px solid var(--cv-hairline);
  box-shadow: 0 2px 8px -4px rgba(0, 0, 0, 0.25);
}

.cv-image-row {
  display: flex;
  align-items: center;
  gap: 14px;
}
.bg-preview {
  width: 74px;
  height: 56px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  border: 1px dashed var(--cv-hairline);
  border-radius: 8px;
  background-color: var(--surface-hover);
  background-repeat: no-repeat;
  background-position: center;
  overflow: hidden;
}
.bg-placeholder {
  font-size: 12px;
  color: var(--text-secondary);
}
.cv-image-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.cv-cover-group { margin-top: 12px; }

/* ---------- 数值仪表：标签—数值—滑块 读作一条轴线 ---------- */
.cv-meter {
  padding: 11px 0 0;
  margin-top: 10px;
  border-top: 1px dashed var(--cv-hairline);
}
.cv-panel > .cv-meter:first-of-type {
  border-top: 0;
  margin-top: 0;
}
.cv-meter__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 2px;
}
.cv-meter__label {
  font-size: 12.5px;
  color: var(--text-secondary);
}
/* 等宽数字：数值变化时不跳动，读数也更像仪表 */
.cv-meter__value {
  font-size: 12.5px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.01em;
  color: var(--text-primary);
}
.cv-meter__body {
  display: flex;
  align-items: center;
  gap: 10px;
}
.cv-slider { flex: 1; min-width: 0; margin-right: 2px; }
.cv-reset {
  flex-shrink: 0;
  min-width: 44px;
  padding: 0 4px;
  font-size: 11.5px;
}
/* 滑块贴底时数值轴与轨道视觉对齐 */
.cv-slider :deep(.el-slider__runway) {
  margin: 8px 0;
  height: 3px;
  background-color: var(--surface-hover);
}
.cv-slider :deep(.el-slider__bar),
.cv-slider :deep(.el-slider__button) {
  background-color: var(--cv-accent);
  border-color: var(--cv-accent);
}
.cv-slider :deep(.el-slider__button) {
  width: 13px;
  height: 13px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.2);
}

/* ---------- 开关行 ---------- */
.cv-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 2px 0;
}
.cv-toggle__text { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.cv-toggle__label { font-size: 12.5px; color: var(--text-secondary); }
.cv-toggle__hint { font-size: 11px; color: var(--text-secondary); }

/* ---------- 入场序列：面板错峰淡入上浮（仅动 opacity/transform） ---------- */
@media (prefers-reduced-motion: no-preference) {
  .cv-panel {
    opacity: 0;
    transform: translateY(10px);
    animation: cv-rise 360ms cubic-bezier(0.16, 1, 0.3, 1) forwards;
  }
  .cv-panel:nth-child(1) { animation-delay: 0ms; }
  .cv-panel:nth-child(2) { animation-delay: 70ms; }
  .cv-panel:nth-child(3) { animation-delay: 140ms; }
  .cv-panel:nth-child(4) { animation-delay: 210ms; }
  .cv-panel:nth-child(5) { animation-delay: 280ms; }
}
@keyframes cv-rise {
  to { opacity: 1; transform: none; }
}

/* 焦点可见：键盘操作时给出明确描边 */
.conv-settings :focus-visible {
  outline: 2px solid var(--cv-accent);
  outline-offset: 2px;
  border-radius: 4px;
}

/* ---------- 移动端：单列堆叠，触摸目标放大到 44px ---------- */
@media (max-width: 520px) {
  .cv-avatar-grid { grid-template-columns: 1fr; }
  .cv-panel { padding: 14px 13px 16px; }
  .cv-meter__body { gap: 6px; }
  .cv-reset { min-width: 52px; min-height: 44px; }
  .cv-cover-group { display: flex; width: 100%; }
  .cv-cover-group :deep(.el-radio-button) { flex: 1; }
  .cv-cover-group :deep(.el-radio-button__inner) { width: 100%; min-height: 34px; }
}

/* ---------- 记忆宫殿（抽屉内） ---------- */
.mp-select { width: 108px; flex-shrink: 0; }
/* 渲染模板：按钮展示当前预设名，点开进入带预览的预设面板 */
.tpl-open-btn { flex-shrink: 0; max-width: 180px; }
/* 子选项：缩进 + 左侧刻度，表明它隶属于上面的开关 */
.cv-sub {
  margin-top: 10px;
  padding-left: 12px;
  border-left: 2px solid var(--border-color);
}
/* 二级子项：详略紧跟在模板选择下面，再多缩进一层表示从属关系 */
.cv-toggle--sub {
  margin-top: 10px;
  padding-left: 10px;
  border-left: 2px dashed var(--border-color);
}

/* 参数说明小问号：与系统设置保持一致 */
.help-icon {
  margin-left: 4px;
  color: var(--text-muted, #909399);
  cursor: help;
  vertical-align: -1px;
}

/* 底部：改动即存，只留一个「完成」 */
.cv-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  width: 100%;
}
</style>
