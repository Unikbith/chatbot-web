import { createRouter, createWebHistory } from 'vue-router'

const SITE_NAME = 'ChatBot'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/Home.vue'),
    meta: { title: 'ChatBot' }
  },
  {
    path: '/admin',
    name: 'AdminLogin',
    component: () => import('@/views/AdminLogin.vue'),
    meta: { title: '管理后台登录' }
  },
  {
    path: '/chatbotAdmin',
    name: 'AdminBackend',
    component: () => import('@/views/AdminBackend.vue'),
    meta: { title: 'ChatBot 管理后台' }
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

// 路由守卫 - 设置页面标题；管理后台需登录（管理员令牌在 admin_token），未登录跳 /admin 登录页
router.beforeEach((to, from, next) => {
  document.title = to.meta.title ? `${to.meta.title} - ${SITE_NAME}` : SITE_NAME

  if (to.name === 'AdminBackend' && !localStorage.getItem('admin_token')) {
    return next({ path: '/admin' })
  }
  next()
})

export default router
