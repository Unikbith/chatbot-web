<template>
  <template v-for="(node, i) in nodes" :key="i">
    <!-- 状态栏：数值项自带进度条 -->
    <div v-if="node.type === '状态'" class="rm-card rm-status">
      <div v-for="(s, j) in node.stats" :key="j" class="rm-stat">
        <div class="rm-stat-head">
          <span class="rm-stat-label">{{ s.label }}</span>
          <span class="rm-stat-value">{{ s.value }}</span>
        </div>
        <div v-if="s.percent !== null" class="rm-bar">
          <div class="rm-bar-fill" :style="{ width: s.percent + '%' }"></div>
        </div>
      </div>
    </div>

    <!-- 进度条 -->
    <div v-else-if="node.type === '进度'" class="rm-card rm-progress">
      <div class="rm-stat-head">
        <span class="rm-stat-label">{{ node.label || t('进度', 'Progress') }}</span>
        <span class="rm-stat-value">{{ node.percent }}%</span>
      </div>
      <div class="rm-bar">
        <div class="rm-bar-fill" :style="{ width: node.percent + '%' }"></div>
      </div>
    </div>

    <!-- 选项：可点击填入输入框 -->
    <div v-else-if="node.type === '选项'" class="rm-options">
      <button
        v-for="(o, j) in node.options"
        :key="j"
        type="button"
        class="rm-option"
        @click="emit('pick-option', o.text)"
      >
        <span v-if="o.key" class="rm-option-key">{{ o.key }}</span>
        <span class="rm-option-text">{{ o.text }}</span>
      </button>
    </div>

    <!-- 提醒 -->
    <div v-else-if="node.type === '提醒'" class="rm-alert">
      <el-icon class="rm-alert-icon"><WarningFilled /></el-icon>
      <span>{{ node.text }}</span>
    </div>

    <!-- 面板 -->
    <div v-else-if="node.type === '面板'" class="rm-card rm-panel">
      <div v-if="node.title" class="rm-panel-title">{{ node.title }}</div>
      <div v-for="(l, j) in node.lines" :key="j" class="rm-panel-line">{{ l }}</div>
    </div>

    <!-- 物品 -->
    <div v-else-if="node.type === '物品'" class="rm-items">
      <span v-for="(it, j) in node.items" :key="j" class="rm-item">
        {{ it.label }}<em v-if="it.count" class="rm-item-count">×{{ it.count }}</em>
      </span>
    </div>
  </template>
</template>

<script setup>
/**
 * 内置基础标注块
 *
 * 抽成独立组件的原因：这套块有两种使用场景 ——
 *   1. 未选渲染模板时，整条消息都用它（RichMessage 的通用分支）；
 *   2. 已选模板时，用于兜住模板词表之外的通用标记
 *      （例如模板是档案风、模型却输出了【进度】，不能把标记原文丢给用户）。
 */
import { WarningFilled } from '@element-plus/icons-vue'
import { t } from '../i18n'

defineProps({
  /** richMessage.buildNode 产出的节点数组 */
  nodes: { type: Array, default: () => [] },
})
const emit = defineEmits(['pick-option'])
</script>

<style scoped>
/* 卡片基底：跟随主题变量，明暗自动适配 */
.rm-card {
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--surface-hover);
  border: 1px solid var(--border-color);
}

.rm-status {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 18px;
}

.rm-stat {
  flex: 1 1 120px;
  min-width: 0;
}

.rm-stat-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}

.rm-stat-label {
  font-size: 12px;
  color: var(--text-muted);
}

.rm-stat-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.rm-bar {
  height: 6px;
  border-radius: 3px;
  background: var(--border-color);
  overflow: hidden;
}

.rm-bar-fill {
  height: 100%;
  border-radius: 3px;
  background: var(--brand-gradient);
  transition: width 0.35s ease;
}

.rm-progress .rm-bar {
  height: 8px;
  border-radius: 4px;
}

.rm-options {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.rm-option {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  text-align: left;
  font: inherit;
  font-size: 13px;
  color: var(--text-secondary);
  background: var(--surface);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}

.rm-option:hover {
  background: var(--brand-soft);
  border-color: var(--brand);
  color: var(--text-primary);
}

.rm-option-key {
  flex-shrink: 0;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 5px;
  background: var(--brand-soft);
  color: var(--brand);
  font-size: 11px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.rm-option:hover .rm-option-key {
  background: var(--brand);
  color: #fff;
}

.rm-option-text {
  flex: 1;
  min-width: 0;
}

.rm-alert {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  padding: 9px 12px;
  border-radius: 8px;
  background: rgba(217, 108, 78, 0.1);
  border: 1px solid rgba(217, 108, 78, 0.28);
  font-size: 13px;
  line-height: 1.55;
  color: var(--text-secondary);
}

.rm-alert-icon {
  flex-shrink: 0;
  margin-top: 2px;
  color: var(--brand);
  font-size: 14px;
}

.rm-panel-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 6px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border-color);
}

.rm-panel-line {
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.rm-items {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.rm-item {
  display: inline-flex;
  align-items: baseline;
  gap: 3px;
  padding: 4px 10px;
  border-radius: 999px;
  background: var(--surface-hover);
  border: 1px solid var(--border-color);
  font-size: 12px;
  color: var(--text-secondary);
}

.rm-item-count {
  font-style: normal;
  font-weight: 700;
  color: var(--brand);
}
</style>
