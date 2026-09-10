<template>
  <div class="admin-login-page">
    <div class="login-card">
      <div class="brand">
        <img :src="brandIcon" class="brand-img" alt="Confide" />
        <span class="brand-text">{{ t('管理后台', 'Admin Panel') }}</span>
      </div>
      <p class="subtitle">{{ t('管理员专用登录入口（账号密码由服务端 .env 配置）', 'Admin-only login. Credentials come from the server .env') }}</p>

      <el-form @submit.prevent="doLogin" class="login-form">
        <el-form-item>
          <el-input
            v-model="username"
            :placeholder="t('管理员账号', 'Admin username')"
            size="large"
            autocomplete="username"
            :prefix-icon="User"
          />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="password"
            type="password"
            :placeholder="t('管理员密码', 'Admin password')"
            size="large"
            show-password
            autocomplete="current-password"
            :prefix-icon="Lock"
            @keyup.enter="doLogin"
          />
        </el-form-item>
        <el-button
          type="primary"
          class="login-btn"
          size="large"
          :loading="loading"
          :icon="Right"
          @click="doLogin"
        >
          {{ t('登 录', 'Login') }}
        </el-button>
      </el-form>

      <div class="back-link">
        <el-button link type="primary" @click="$router.push('/')">
          {{ t('返回 Confide 主界面', 'Back to Confide') }}
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock, Right } from '@element-plus/icons-vue'
import { adminApi } from '@/utils/resAi'
import { t } from '../i18n'
import brandIcon from '@/assets/icon/ChatBotIcon.png'

const router = useRouter()
const username = ref('')
const password = ref('')
const loading = ref(false)

async function doLogin() {
  if (!username.value.trim() || !password.value) {
    ElMessage.warning(t('请输入管理员账号和密码', 'Enter admin username and password'))
    return
  }
  loading.value = true
  try {
    const res = await adminApi.login(username.value.trim(), password.value)
    if (res.code === 200) {
      localStorage.setItem('admin_token', res.data.access_token)
      localStorage.setItem('admin_username', res.data.username)
      ElMessage.success(t('登录成功', 'Signed in'))
      router.replace('/chatbotAdmin')
    } else {
      ElMessage.error(res.message || t('登录失败', 'Login failed'))
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || e.message || t('登录失败', 'Login failed'))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.admin-login-page {
  width: 100%;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #fbf3ea 0%, #f3e3d0 100%);
  padding: 20px;
}

.login-card {
  width: 100%;
  max-width: 380px;
  background: var(--surface, #fff);
  border-radius: 16px;
  padding: 36px 32px 28px;
  box-shadow: 0 12px 40px rgba(90, 55, 25, 0.18);
  border: 1px solid rgba(180, 130, 80, 0.18);
}

.brand {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-bottom: 6px;
}

.brand-img {
  width: 34px;
  height: 34px;
  border-radius: 9px;
  object-fit: cover;
}

.brand-text {
  font-size: 22px;
  font-weight: 700;
  color: #7a4c24;
}

.subtitle {
  text-align: center;
  font-size: 12px;
  color: #a9815a;
  margin: 0 0 24px;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.login-btn {
  width: 100%;
  margin-top: 8px;
  background: linear-gradient(135deg, #d9a066, #c07c4a);
  border: none;
  font-weight: 600;
}

.login-btn:hover {
  opacity: 0.92;
  background: linear-gradient(135deg, #d9a066, #c07c4a);
}

.back-link {
  text-align: center;
  margin-top: 18px;
}
</style>