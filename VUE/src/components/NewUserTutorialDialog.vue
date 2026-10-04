<template>
  <el-dialog
    v-model="visible"
    :title="t('新用户使用教程', 'Getting Started')"
    width="min(760px, 94vw)"
    class="tutorial-dialog"
    align-center
    append-to-body
    @close="handleClose"
  >
    <p class="tutorial-intro">
      {{ t('跟着 7 步配置好自己的模型，就能开始畅聊；点图片可放大查看。', 'Follow these 7 steps to set up your own model and start chatting. Click an image to zoom in.') }}
    </p>

    <div class="tutorial-steps">
      <div v-for="(step, i) in steps" :key="i" class="tutorial-step">
        <div class="ts-head">
          <span class="ts-index">{{ i + 1 }}</span>
          <div class="ts-texts">
            <div class="ts-title">{{ t(step.title, step.titleEn) }}</div>
            <div class="ts-desc">{{ t(step.desc, step.descEn) }}</div>
          </div>
        </div>
        <el-image
          class="ts-image"
          :src="step.image"
          :preview-src-list="imageList"
          :initial-index="i"
          :alt="t(step.title, step.titleEn)"
          fit="contain"
          preview-teleported
          hide-on-click-modal
        />
      </div>
    </div>

    <template #footer>
      <el-button type="primary" @click="visible = false">
        {{ t('知道了', 'Got it') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed } from 'vue'
import { t } from '../i18n'
import { TUTORIAL_STEPS } from '../utils/tutorialSteps'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'read'])

const steps = TUTORIAL_STEPS
// 大图预览：把 7 张配图交给同一个 viewer，点任意一张即可左右翻看
const imageList = TUTORIAL_STEPS.map(s => s.image)

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

// 关闭（任意见了教程）即视为已阅读：由父组件落库，保证「只弹这一次」
function handleClose() {
  emit('read')
}
</script>

<style scoped>
.tutorial-intro {
  margin: 0 0 14px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.tutorial-steps {
  display: flex;
  flex-direction: column;
  gap: 18px;
  /* 教程较长：限高并内部滚动，避免弹窗超出屏幕 */
  max-height: min(62vh, 560px);
  overflow-y: auto;
  padding-right: 6px;
}

.tutorial-step {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ts-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.ts-index {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--brand-gradient);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-top: 1px;
}

.ts-texts {
  flex: 1;
  min-width: 0;
}

.ts-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.5;
}

.ts-desc {
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
  margin-top: 2px;
}

.ts-image {
  display: flex;
  justify-content: center;
  width: 100%;
  cursor: zoom-in;
}

/* 原文档配图尺寸差异大（横图约 2.3:1、竖图约 0.6:1）：
   边框贴在图本身而不是固定框上，小图不放大（保持清晰）、
   大图按最大高度缩放，点击可用 el-image 预览放大。 */
.ts-image :deep(img) {
  width: auto;
  max-width: 100%;
  max-height: 440px;
  object-fit: contain;
  display: block;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--surface-hover);
}

/* 弹窗内边距收紧，让配图占更宽的可视区域 */
.tutorial-dialog :deep(.el-dialog__body) {
  padding-top: 8px;
}
</style>
