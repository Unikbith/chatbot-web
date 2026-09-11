<template>
  <svg
    class="thumb-icon"
    :class="{ down: down }"
    viewBox="0 0 24 24"
    :width="size"
    :height="size"
    aria-hidden="true"
    focusable="false"
  >
    <path
      fill="currentColor"
      d="M1 21h4V9H1v12zm22-11c0-1.1-.9-2-2-2h-6.31l.95-4.57.03-.32c0-.41-.17-.79-.44-1.06L14.17 1 7.59 7.59C7.22 7.95 7 8.45 7 9v10c0 1.1.9 2 2 2h9c.83 0 1.54-.5 1.84-1.22l3.02-7.05c.09-.23.14-.47.14-.73v-1z"
    />
  </svg>
</template>

<script setup>
defineProps({
  /** 是否显示为「倒大拇指」（踩） */
  down: { type: Boolean, default: false },
  size: { type: [Number, String], default: 16 },
})
</script>

<style scoped>
.thumb-icon {
  display: block;
  flex-shrink: 0;
  transition: transform 0.15s ease;
}

/* 倒大拇指：整体旋转 180°，视觉上拇指向下 */
.thumb-icon.down {
  transform: rotate(180deg);
}
</style>
