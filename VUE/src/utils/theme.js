// utils/theme.js - 主题切换（浅色/深色/跟随系统）
const THEME_KEY = 'chatbot_theme'

export function applyTheme(theme) {
  const html = document.documentElement
  const dark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)')
  let isDark = false
  if (theme === 'dark') isDark = true
  else if (theme === 'light') isDark = false
  else isDark = !!(dark && dark.matches)
  html.classList.toggle('dark', isDark)
  try { localStorage.setItem(THEME_KEY, theme) } catch (e) {}
}

// 在应用启动早期应用本地缓存的主题，避免首次渲染时闪白/闪黑
export function initThemeFromStorage() {
  let saved = 'auto'
  try { saved = localStorage.getItem(THEME_KEY) || 'auto' } catch (e) {}
  applyTheme(saved)
  return saved
}

// 绑定系统主题变化监听（auto 模式时自动切换）
export function bindSystemThemeListener(themeGetter) {
  const dark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)')
  if (!dark) return () => {}
  const listener = () => {
    if (themeGetter && themeGetter() === 'auto') applyTheme('auto')
  }
  dark.addEventListener('change', listener)
  return () => dark.removeEventListener('change', listener)
}

// 将 Element Plus 主题与自定义主题对齐
export function initTheme(settings) {
  applyTheme(settings?.theme || 'auto')
}