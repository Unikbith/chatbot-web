import { createRouter, createWebHistory } from 'vue-router'

const SITE_NAME = '心语'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/Home.vue'),
    meta: { title: 'Confide' }
  },
  {
    // 管理后台唯一入口：登录页内嵌在 AdminBackend 组件内，登录态由组件自管
    path: '/chatbotadmin',
    name: 'AdminBackend',
    component: () => import('@/views/AdminBackend.vue'),
    meta: { title: 'Confide 管理后台' }
  },
  {
    path: '/user-agreement',
    name: 'UserAgreement',
    component: () => import('@/views/UserAgreement.vue'),
    meta: { title: '用户须知与免责声明' }
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/'
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 路由守卫 - 设置页面标题（管理后台登录校验由 AdminBackend 组件自管，无需前端跳转）
router.beforeEach((to, from, next) => {
  document.title = to.meta.title ? `${to.meta.title} | ${SITE_NAME}` : SITE_NAME
  next()
})

export default router
