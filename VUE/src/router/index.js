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
    path: '/admin',
    name: 'AdminLogin',
    component: () => import('@/views/AdminLogin.vue'),
    meta: { title: '管理后台登录' }
  },
  {
    path: '/chatbotAdmin',
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

// 管理员令牌有效性缓存：避免每次路由跳转都请求 /api/admin/me
let adminCheckCache = { token: null, ok: false, at: 0 }
const ADMIN_CHECK_TTL = 60 * 1000

async function verifyAdminToken(token) {
  const now = Date.now()
  if (adminCheckCache.token === token && now - adminCheckCache.at < ADMIN_CHECK_TTL) {
    return adminCheckCache.ok
  }
  try {
    const baseURL = import.meta.env.VITE_API_BASE_URL || ''
    const res = await fetch(`${baseURL}/api/admin/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    const ok = res.ok
    if (!ok) localStorage.removeItem('admin_token')
    adminCheckCache = { token, ok, at: now }
    return ok
  } catch {
    // 网络异常时保守放行由后端接口二次鉴权，避免误踢出正常管理员
    return true
  }
}

// 路由守卫 - 设置页面标题；管理后台需登录（管理员令牌在 admin_token），未登录跳 /admin 登录页
router.beforeEach(async (to, from, next) => {
  document.title = to.meta.title ? `${to.meta.title} | ${SITE_NAME}` : SITE_NAME

  if (to.name === 'AdminBackend') {
    const token = localStorage.getItem('admin_token')
    if (!token) return next({ path: '/admin' })
    // 前端守卫仅检查 token 是否存在不够：向服务端校验令牌有效性与 admin 身份
    const ok = await verifyAdminToken(token)
    if (!ok) return next({ path: '/admin' })
  }
  next()
})

export default router
