import { createApp } from 'vue'
// 只引入必要的基础样式；组件样式由 unplugin-vue-components 按需注入，
// 函数式 API（ElMessage/ElMessageBox/ElLoading）与指令的样式需手动补，
// 否则消息提示 / v-loading 会没有样式。
import 'element-plus/theme-chalk/base.css'
import 'element-plus/theme-chalk/el-message.css'
import 'element-plus/theme-chalk/el-message-box.css'
import 'element-plus/theme-chalk/el-loading.css'
// v-loading 指令不经过模板组件扫描，显式全局注册（样式已在上行引入）
import { ElLoading } from 'element-plus'
import App from './App.vue'
import router from './router'

// Element Plus 深色变量按需异步加载：仅当用户处于深色模式时才注入，
// 避免浅色用户白白下载一份深色主题 CSS，缩短首屏渲染阻塞时间。
let darkCssLoaded = false
function ensureDarkThemeCss() {
  if (darkCssLoaded) return
  if (!document.documentElement.classList.contains('dark')) return
  darkCssLoaded = true
  import('element-plus/theme-chalk/dark/css-vars.css')
}
ensureDarkThemeCss()
// 切换主题时补加载（首次切到深色时生效）
window.addEventListener('chatbot:theme-change', ensureDarkThemeCss)

// 说明：项目内使用图标的组件均已各自按需 import（形如
// `import { Setting } from '@element-plus/icons-vue'`），无需在入口全局注册。
// 原「全量注册 @element-plus/icons-vue」会把 1000+ 图标打进首屏包（约 170KB），
// 现已移除，首屏仅包含组件真正用到的图标。

const app = createApp(App)

// v-loading 指令显式全局注册（已在上方引入 el-loading.css）
app.directive('loading', ElLoading.directive)
app.use(router)
app.mount('#app')

// 移除 index.html 中的首屏骨架（Vue 挂载后通常已清空，这里兜底防止残留遮挡）
const bootEl = document.querySelector('.app-boot')
if (bootEl) bootEl.remove()
