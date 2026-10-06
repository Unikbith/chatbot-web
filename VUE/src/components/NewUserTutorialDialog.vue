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
      {{ t('首次使用请先配置自己的 API：默认免费模型仅适合体验，对话能力受限、无法畅聊。跟着下面几步走完就能畅聊；点图片可放大查看。', 'Configure your own API first: the default free model is only for a quick try, limited and unable to chat freely. Follow the steps below; click an image to zoom in.') }}
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
        <!-- 一步可以有多张图（如第 3 步区分电脑端 / 手机端） -->
        <div v-for="(img, j) in step.images" :key="j" class="ts-figure">
          <div v-if="img.caption" class="ts-caption">{{ img.caption }}</div>
          <el-image
            class="ts-image"
            :src="img.src"
            :preview-src-list="imageList"
            :initial-index="imageIndexOf(i, j)"
            :alt="t(step.title, step.titleEn)"
            fit="contain"
            preview-teleported
            hide-on-click-modal
          />
        </div>
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

// 大图预览：把所有配图摊平给同一个 viewer（一步多图时也能左右翻看）；
// 同时记下每张图在摊平数组里的下标，供 initial-index 定位。
const flatImages = []
const indexMap = new Map()
TUTORIAL_STEPS.forEach((s, i) => {
  (s.images || []).forEach((img, j) => {
    indexMap.set(`${i}-${j}`, flatImages.length)
    flatImages.push(img.src)
  })
})
const imageList = flatImages
const imageIndexOf = (i, j) => indexMap.get(`${i}-${j}`) ?? 0

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

/* 一步多图时的分组与说明文字 */
.ts-figure {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ts-caption {
  font-size: 12px;
  font-weight: 600;
  color: var(--brand);
  padding-left: 2px;
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
