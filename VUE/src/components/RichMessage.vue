<template>
  <!-- 模板渲染分支：会话/卡片选定了渲染模板时走这里。
       版式完全由模板 CSS 决定，AI 只提供数据；
       模板词表之外的通用标记由 RichBlocks 兜底渲染，不会露出标记原文。 -->
  <div
    v-if="template"
    class="rich-message rtpl"
    :class="['rtpl-' + template.id, variant ? 'rtpl--' + variant : '']"
    @click="handleTemplateClick"
  >
    <template v-for="(part, i) in tpl.parts" :key="'p' + i">
      <!-- 正文段落不套用应用默认的 .content-text 样式：
           模板要负责整个输出框的排版（字体、缩进、行距），
           两套样式叠加会互相打架、出现"模板没生效"的错觉 -->
      <div v-if="part.type === 'text'" class="rtpl-prose" v-html="part.html"></div>
      <!-- 兜底：模板没定义的通用标记（如【进度】） -->
      <RichBlocks
        v-else-if="part.type === 'generic'"
        :nodes="[part.node]"
        @pick-option="emit('pick-option', $event)"
      />
      <div v-else class="rtpl-block" v-html="part.html"></div>
    </template>
  </div>

  <!-- 通用分支：未选模板时用内置的基础标注 -->
  <div v-else class="rich-message">
    <template v-for="(part, i) in genericParts" :key="'g' + i">
      <div v-if="part.type === 'text'" class="content-text rm-text" v-html="part.html"></div>
      <RichBlocks
        v-else
        :nodes="[part.node]"
        @pick-option="emit('pick-option', $event)"
      />
    </template>
  </div>
</template>

<script setup>
/**
 * 富消息渲染器
 *
 * 两条渲染路径：
 *   1. 模板路径（template 非空）：按会话/卡片选定的渲染模板输出 DOM 骨架，
 *      版式由模板 CSS 决定 —— 换模板即换风格。
 *      模板词表之外的通用标记由 RichBlocks 兜底，避免露出标记原文。
 *   2. 通用路径（template 为空）：使用内置的基础标注块。
 *
 * 两条路径都不把 AI 文本当 HTML 使用：模板骨架由引擎生成（文本已转义），
 * 普通文本交由 renderText（Markdown + 消毒 + 对白/描写标记）处理。
 */
import { computed } from 'vue'
import { t } from '../i18n'
import RichBlocks from './RichBlocks.vue'
import { parseRichMessage } from '../utils/richMessage'
import { renderReplyTemplate } from '../utils/renderReplyTemplate'
import { renderProse } from '../utils/proseRender'
import { sanitizeRichHtml } from '../utils/sanitize'

const props = defineProps({
  /** 消息纯文本（未渲染的 markdown 原文） */
  raw: { type: String, default: '' },
  /** 把纯文本转成安全 HTML 的函数（聊天页传 renderProse，保证排版一致） */
  renderText: { type: Function, default: null },
  /** 会话/卡片选定的渲染模板（已解析的预设对象，null 表示用通用分支） */
  template: { type: Object, default: null },
  /** 长期记忆（记忆宫殿摘要）：由应用数据补进「记忆回廊」，AI 不需要输出它 */
  longTermMemory: { type: Array, default: () => [] },
  /** 呈现变体：'greeting' 用于开场白（更克制的样式） */
  variant: { type: String, default: '' },
})

const emit = defineEmits(['pick-option'])

const escapeHtml = (s) => String(s)
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')

/**
 * 文本段渲染策略：
 *   · 优先用父组件传入的 renderText（聊天页传 renderProse，保持一致）；
 *   · 未传时用内置的 renderProse —— Markdown 渲染并给对白/心理/叙述打标记。
 */
const toHtml = (text) => (props.renderText ? props.renderText(text) : renderProse(text))

// ---- 模板路径 ----
const tpl = computed(() => {
  if (!props.template) return { parts: [], options: [] }
  const { parts, options } = renderReplyTemplate(props.raw, props.template, {
    // 长期记忆由应用数据（记忆宫殿摘要）补入，AI 只写短期记忆
    longTerm: props.longTermMemory,
  })
  return {
    options,
    parts: parts.map((p) => {
      if (p.type === 'text') return { type: 'text', html: toHtml(p.text) }
      if (p.type === 'generic') return p
      return { type: 'html', html: sanitizeRichHtml(p.html) }
    }),
  }
})

// 选项点击：v-html 内容无法挂 Vue 事件，用容器委托 + 索引回查文案
function handleTemplateClick(e) {
  const btn = e.target && e.target.closest ? e.target.closest('[data-opt-idx]') : null
  if (!btn) return
  const idx = Number(btn.getAttribute('data-opt-idx'))
  const text = tpl.value.options[idx]
  if (text) emit('pick-option', text)
}

// ---- 通用路径 ----
const genericParts = computed(() => {
  if (props.template) return []
  return parseRichMessage(props.raw).map((seg) => {
    if (seg.kind === 'text') return { type: 'text', html: toHtml(seg.text) }
    return { type: 'block', node: seg.node }
  })
})
</script>

<style scoped>
.rich-message {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.rm-text {
  margin: 0;
}

.rm-text :deep(p:first-child) { margin-top: 0; }
.rm-text :deep(p:last-child) { margin-bottom: 0; }

/* 模板分支：骨架样式全部来自模板 CSS（全局注入），这里只保证块级排布 */
.rtpl-block {
  min-width: 0;
}

.rtpl .rm-text {
  color: inherit;
}
</style>
