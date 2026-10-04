<template>
  <!-- 世界书编辑器（卡片广场发布 / 编辑用）
       与人物卡里的世界书同构，但为「一张卡随卡分享」简化：
       条目全可选 —— 一条都不填也能发布，只是没有按需注入的设定。
       常驻=每次都注入；非常驻=对话里出现关键词才注入。 -->
  <div class="mk-wb">
    <div v-for="(entry, i) in list" :key="i" class="mk-wb-item">
      <div class="mk-wb-head">
        <el-input
          v-model="entry.title"
          size="small"
          maxlength="200"
          :placeholder="t('条目名（仅管理界面显示，如：世界观 / 称呼习惯）', 'Entry name (admin display only)')"
          class="mk-wb-title"
        />
        <el-switch
          v-model="entry.always_on"
          size="small"
          inline-prompt
          :active-text="t('常驻', 'Always')"
          :inactive-text="t('按需', 'On demand')"
          :title="entry.always_on
            ? t('每次都注入（核心设定）', 'Injected every turn (core lore)')
            : t('对话里出现关键词时才注入', 'Injected only when a keyword appears')"
        />
        <el-button
          size="small"
          text
          type="danger"
          :icon="Delete"
          :title="t('删除该条目', 'Delete entry')"
          @click="remove(i)"
        />
      </div>
      <el-input
        v-model="entry.keywords"
        size="small"
        maxlength="500"
        :placeholder="t('触发关键词，逗号分隔（常驻可留空）', 'Trigger keywords, comma separated (empty when always-on)')"
      />
      <el-input
        v-model="entry.content"
        type="textarea"
        :rows="3"
        resize="none"
        maxlength="4000"
        :placeholder="t('命中后注入给模型的设定正文（这一段是必填的，只有标题的条目会被忽略）', 'Lore text injected when triggered (required for an entry to count)')"
      />
    </div>

    <div class="mk-wb-foot">
      <el-button size="small" :icon="Plus" @click="add">{{ t('添加条目', 'Add entry') }}</el-button>
      <span class="mk-wb-tip">
        {{ t('可不填。世界书只在与剧情相关时才占用上下文，适合写世界观、称呼、习惯等设定。',
          'Optional. Lorebook entries only consume context when relevant.') }}
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Plus, Delete } from '@element-plus/icons-vue'
import { t } from '../i18n'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue'])

// 最多 20 条（与后端 PUB_WORLDBOOK_MAX 一致），避免发布时报错才发现
const MAX_ENTRIES = 20

const list = computed(() => props.modelValue || [])

function add() {
  if (list.value.length >= MAX_ENTRIES) return
  emit('update:modelValue', [
    ...list.value,
    { title: '', keywords: '', content: '', always_on: false },
  ])
}

function remove(i) {
  const next = list.value.slice()
  next.splice(i, 1)
  emit('update:modelValue', next)
}
</script>

<style scoped>
.mk-wb {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.mk-wb-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--surface);
}

.mk-wb-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.mk-wb-title {
  flex: 1 1 auto;
  min-width: 0;
}

.mk-wb-foot {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.mk-wb-tip {
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-muted);
  flex: 1 1 180px;
}
</style>
