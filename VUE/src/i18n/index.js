// 轻量级国际化 - 无需额外依赖
import { ref, watch } from 'vue'

export const LOCALE_KEY = 'chatbot_locale'

// 当前语言：auto(跟随系统) / zh-CN / en
export const currentLocale = ref(localStorage.getItem(LOCALE_KEY) || 'auto')

// 计算实际生效的语言（解析 auto）并应用 document lang
function resolveLocale() {
  let l = currentLocale.value
  if (l === 'auto') {
    const sys = (navigator.language || 'zh-CN').toLowerCase()
    l = sys.startsWith('en') ? 'en' : 'zh-CN'
  }
  return l === 'en' ? 'en' : 'zh-CN'
}

function apply() {
  document.documentElement.setAttribute('lang', resolveLocale() === 'en' ? 'en' : 'zh-CN')
}

apply()
watch(currentLocale, apply)

// 切换语言
export function setLocale(locale) {
  currentLocale.value = locale
  localStorage.setItem(LOCALE_KEY, locale)
  apply()
}

let sysMedia = null
function detectSystem() {
  return (navigator.language || 'zh-CN').toLowerCase().startsWith('en') ? 'en' : 'zh-CN'
}

// 语言选择下拉选项
export const languageOptions = [
  { value: 'auto', label: '跟随系统' },
  { value: 'zh-CN', label: '简体中文' },
  { value: 'en', label: 'English' },
]

// 根据当前生效语言返回对应文案，t('中文', 'English')
export function t(zh, en) {
  return resolveLocale() === 'en' ? en : zh
}

export function isEn() {
  return resolveLocale() === 'en'
}

// 使用响应式切换（触发界面更新）
export function useLocale() {
  return { currentLocale, setLocale, t, isEn }
}