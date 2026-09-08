<script setup>
import { RouterView } from 'vue-router'
import { initThemeFromStorage } from './utils/theme'

// 启动早期应用缓存的主题（浅色/深色/跟随系统），避免闪白/闪黑
initThemeFromStorage()
</script>

<template>
  <router-view />
</template>

<style>
:root {
  --app-bg: #faf7f4;
  --sidebar-bg: #f2ede8;
  --surface: #ffffff;
  --surface-hover: #ebe4de;
  --text-primary: #2a2522;
  --text-secondary: #6a5d53;
  --text-muted: #a89b8f;
  --border-color: #e7ded6;
  --brand: #d96c4e;
  --brand-dark: #c05a3f;
  --brand-gradient: linear-gradient(135deg, #e07c5a 0%, #cf5a47 100%);
  --brand-soft: #f8e9e2;
  --chat-user-bubble: rgba(217, 108, 78, 0.92);
  --chat-ai-bubble: rgba(255, 255, 255, 0.86);
  --input-bg: rgba(250, 247, 244, 0.96);
  --shadow-soft: 0 1px 2px rgba(60, 40, 25, 0.04), 0 6px 24px -12px rgba(60, 40, 25, 0.12);
  --radius: 14px;
  color-scheme: light;
}

html.dark {
  --app-bg: #191613;
  --sidebar-bg: #211c18;
  --surface: #2a2520;
  --surface-hover: #37302a;
  --text-primary: #f2ebe4;
  --text-secondary: #c6b8ac;
  --text-muted: #8e8175;
  --border-color: #3a332b;
  --brand: #e88b6f;
  --brand-dark: #f0a184;
  --brand-gradient: linear-gradient(135deg, #ef926f 0%, #da6a4d 100%);
  --brand-soft: rgba(232, 139, 111, 0.16);
  --chat-user-bubble: rgba(224, 124, 90, 0.9);
  --chat-ai-bubble: rgba(42, 37, 32, 0.8);
  --input-bg: rgba(42, 37, 32, 0.92);
  --shadow-soft: 0 1px 2px rgba(0, 0, 0, 0.3), 0 8px 28px -14px rgba(0, 0, 0, 0.5);
  --radius: 14px;
  color-scheme: dark;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html, body {
  height: 100%;
  width: 100%;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', Roboto, 'Helvetica Neue', Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  background: var(--app-bg);
  color: var(--text-primary);
  line-height: 1.5;
}

#app {
  width: 100%;
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
}

/* 滚动条全局样式 */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: #d8c8bb;
  border-radius: 3px;
}

html.dark ::-webkit-scrollbar-thumb {
  background: #4a413a;
}

::-webkit-scrollbar-thumb:hover {
  background: #c2ad9c;
}

html.dark ::-webkit-scrollbar-thumb:hover {
  background: #61564c;
}

/* 选中文本样式 */
::selection {
  background: #f3d6c9;
  color: #3a2418;
}

html.dark ::selection {
  background: #d96c4e;
  color: #fff;
}

/* Element Plus 暗色侧边栏/弹窗背景覆盖（配合 var 主题） */
html.dark .el-drawer,
html.dark .el-dialog,
html.dark .el-message-box,
html.dark .el-popper,
html.dark .el-dropdown-menu {
  background: var(--surface);
  color: var(--text-primary);
}
html.dark .el-drawer__header,
html.dark .el-dialog__title {
  color: var(--text-primary);
}
</style>
