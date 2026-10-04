<template>
  <el-dialog
    v-model="visible"
    :title="t('渲染预设', 'Render Presets')"
    width="min(920px, 94vw)"
    class="rtp-dialog"
    align-center
    append-to-body
  >
    <p class="rtp-intro">
      {{ t('预设决定 AI 回复长什么样——整个输出框的配色、字体、卡片版式。下面是实时预览，用的是真正的渲染引擎与示例数据。', 'Presets decide how replies look — the whole output box: colors, fonts, cards. Previews below use the real render engine with sample data.') }}
    </p>

    <div class="rtp-grid">
      <div
        v-for="p in presets"
        :key="p.id"
        class="rtp-card"
        :class="{ 'is-active': modelValue === p.id }"
        @click="choose(p.id)"
      >
        <div class="rtp-head">
          <span class="rtp-name">{{ t(p.name, p.nameEn) }}</span>
          <span v-if="modelValue === p.id" class="rtp-badge">{{ t('使用中', 'Active') }}</span>
        </div>
        <div class="rtp-desc">{{ t(p.desc, p.descEn) }}</div>
        <!-- 预览区不可交互：既避免误点选中选项按钮，也避免按钮嵌套。
             预览走真实渲染（含 Markdown 与对白/描写区分），与聊天页一致 -->
        <div class="rtp-preview">
          <RichMessage :raw="SAMPLE" :render-text="renderProse" :template="p" />
        </div>
      </div>
    </div>

    <template #footer>
      <span class="rtp-foot-hint">
        {{ t('选择后立即生效，并自动应用到这条对话的历史消息', 'Applies immediately, including the existing messages in this chat') }}
      </span>
      <el-button type="primary" @click="visible = false">{{ t('完成', 'Done') }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
/**
 * 渲染预设面板
 *
 * 每个预设卡片里渲染的是**真实组件 + 真实示例数据**，
 * 因此预览与聊天页的效果完全一致（同一套引擎、同一份 CSS）。
 * 这样"选预设"不再需要靠文字猜效果。
 */
import { computed, ref } from 'vue'
import { t } from '../i18n'
import RichMessage from './RichMessage.vue'
import { TEMPLATE_PRESET_LIST } from '../utils/replyTemplates'
import { renderProse } from '../utils/proseRender'

const props = defineProps({
  /** 当前选中的预设 id */
  modelValue: { type: String, default: 'archive' },
})
const emit = defineEmits(['update:modelValue', 'change'])

// 面板开关：由父组件通过 ref 调用 open() / close()
const openFlag = ref(false)
const visible = computed({
  get: () => openFlag.value,
  set: (v) => { openFlag.value = v },
})

const presets = TEMPLATE_PRESET_LIST

// 预览示例：一律使用中性虚构数据。
// 不要把真实姓名或作者的私人创作内容写进示例 —— 它们会随产物发布，
// 模板提示词里的示例还会随请求发往模型厂商。
const SAMPLE = [
  '【场景】08:15 (Day 1, 清晨)|咖啡馆靠窗座位',
  '【摘要】两人第一次把话说开',
  '【面板】角色资料|姓名:陈默|性别:男|年龄:24',
  '【状态】角色状态|好感度:72/100【她开始主动找话题】|信任度:45/100',
  '【记忆】短期记忆 (3/7)|你替她挡了一次雨|她记住了你喜欢的口味',
  '【推演】A.【直接告白】把话说清楚|B.【维持现状】先不打破现在的距离',
  '她把杯子推到一边，侧过头看你。',
  '「你今天来得比平时早。」',
  '语气很平常。（其实她提前半小时就到了，只是不肯承认。）',
].join('\n')

function choose(id) {
  emit('update:modelValue', id)
  emit('change', id)
}

defineExpose({
  open: () => { openFlag.value = true },
  close: () => { openFlag.value = false },
})
</script>

<style scoped>
.rtp-intro {
  margin: 0 0 14px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.rtp-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 14px;
  max-height: min(64vh, 620px);
  overflow-y: auto;
  padding: 2px;
}

.rtp-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  background: var(--surface);
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s;
}

.rtp-card:hover {
  border-color: var(--brand);
  box-shadow: var(--shadow-soft);
}

.rtp-card.is-active {
  border-color: var(--brand);
  box-shadow: 0 0 0 2px var(--brand-soft);
}

.rtp-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.rtp-name {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
}

.rtp-badge {
  flex: none;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--brand);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
}

.rtp-desc {
  font-size: 12px;
  line-height: 1.55;
  color: var(--text-muted);
}

/* 预览区：固定高度裁切，让卡片高度整齐；不可交互，避免误点选项按钮 */
.rtp-preview {
  margin-top: 4px;
  max-height: 260px;
  overflow: hidden;
  border-radius: 10px;
  pointer-events: none;
  /* 淡出，暗示内容被裁切 */
  -webkit-mask-image: linear-gradient(180deg, #000 78%, transparent 100%);
  mask-image: linear-gradient(180deg, #000 78%, transparent 100%);
}

.rtp-preview--none {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 90px;
  padding: 16px;
  background: var(--surface-hover);
  border: 1px dashed var(--border-color);
}

.rtp-none-note {
  font-size: 12px;
  color: var(--text-muted);
  text-align: center;
}

.rtp-foot-hint {
  margin-right: auto;
  font-size: 12px;
  color: var(--text-muted);
}
</style>
