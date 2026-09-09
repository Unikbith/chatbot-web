<script setup>
import { ref, watch, onUnmounted } from 'vue';
import { ElMessage } from 'element-plus';
import { User, Lock, Message, Close } from '@element-plus/icons-vue';
import { authApi } from '../utils/resAi';

import brandIcon from '../assets/icon/ChatBotIcon.png'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  }
});

const emit = defineEmits(['update:modelValue', 'success']);

const isLogin = ref(true);
const inForgot = ref(false);
const forgotStep = ref(1); // 1=邮箱+验证码，2=设置新密码
const loading = ref(false);
const codeLoading = ref(false);
const forgotCodeLoading = ref(false);
const forgotLoading = ref(false);
const countdown = ref(0);
const forgotCountdown = ref(0);
let countdownTimer = null;
let forgotCountdownTimer = null;

const form = ref({
  username: '',
  email: '',
  password: '',
  confirmPassword: '',
  code: '',
});

const forgotForm = ref({
  email: '',
  code: '',
  new_password: '',
  confirm_password: '',
});

watch(() => props.modelValue, (val) => {
  if (!val) {
    form.value = { username: '', email: '', password: '', confirmPassword: '', code: '' };
    isLogin.value = true;
    inForgot.value = false;
    forgotStep.value = 1;
    forgotForm.value = { email: '', code: '', new_password: '', confirm_password: '' };
    clearCountdown();
  }
});

onUnmounted(() => {
  clearCountdown();
});

function clearCountdown() {
  if (countdownTimer) {
    clearInterval(countdownTimer);
    countdownTimer = null;
  }
  countdown.value = 0;
  if (forgotCountdownTimer) {
    clearInterval(forgotCountdownTimer);
    forgotCountdownTimer = null;
  }
  forgotCountdown.value = 0;
}

const handleClose = () => {
  emit('update:modelValue', false);
};

const toggleMode = () => {
  isLogin.value = !isLogin.value;
  form.value.confirmPassword = '';
  form.value.code = '';
  inForgot.value = false;
  forgotStep.value = 1;
  clearCountdown();
};

const goForgot = () => {
  inForgot.value = true;
  forgotStep.value = 1;
  clearCountdown();
};

const backToLogin = () => {
  inForgot.value = false;
  isLogin.value = true;
  forgotStep.value = 1;
  forgotForm.value = { email: '', code: '', new_password: '', confirm_password: '' };
  clearCountdown();
};

async function sendForgotCode() {
  const email = forgotForm.value.email.trim();
  if (!email) {
    ElMessage.warning('请输入邮箱');
    return;
  }
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(email)) {
    ElMessage.warning('请输入有效的邮箱地址');
    return;
  }
  forgotCodeLoading.value = true;
  try {
    const res = await authApi.sendCode(email, 'reset_password');
    if (res.code === 200) {
      ElMessage.success(res.message || '验证码已发送');
      forgotCountdown.value = 60;
      if (forgotCountdownTimer) clearInterval(forgotCountdownTimer);
      forgotCountdownTimer = setInterval(() => {
        forgotCountdown.value--;
        if (forgotCountdown.value <= 0) {
          clearInterval(forgotCountdownTimer);
          forgotCountdownTimer = null;
        }
      }, 1000);
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || e.message || '发送失败');
  } finally {
    forgotCodeLoading.value = false;
  }
}

async function submitForgotStep1() {
  const email = forgotForm.value.email.trim();
  if (!email) {
    ElMessage.warning('请输入邮箱');
    return;
  }
  if (!forgotForm.value.code) {
    ElMessage.warning('请输入验证码');
    return;
  }
  forgotLoading.value = true;
  try {
    const res = await authApi.verifyCode(email, forgotForm.value.code, 'reset_password');
    if (res.code === 200) {
      ElMessage.success(res.message || '验证通过');
      forgotStep.value = 2;
    } else {
      ElMessage.error(res.message || '验证失败');
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || e.message || '验证失败');
  } finally {
    forgotLoading.value = false;
  }
}

async function submitForgot() {
  const newPwd = forgotForm.value.new_password;
  if (newPwd.length < 6) {
    ElMessage.warning('新密码至少6个字符');
    return;
  }
  if (newPwd !== forgotForm.value.confirm_password) {
    ElMessage.warning('两次密码输入不一致');
    return;
  }
  forgotLoading.value = true;
  try {
    const res = await authApi.resetPassword(
      forgotForm.value.email.trim(),
      forgotForm.value.code,
      newPwd,
    );
    if (res.code === 200) {
      ElMessage.success(res.message || '密码重置成功');
      backToLogin();
      emit('update:modelValue', false);
    } else {
      ElMessage.error(res.message || '重置失败');
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || e.message || '重置失败');
  } finally {
    forgotLoading.value = false;
  }
}

async function sendCode() {
  if (!form.value.email) {
    ElMessage.warning('请输入邮箱');
    return;
  }
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(form.value.email)) {
    ElMessage.warning('请输入有效的邮箱地址');
    return;
  }

  codeLoading.value = true;
  try {
    const res = await authApi.sendCode(form.value.email, 'register');
    if (res.code === 200) {
      ElMessage.success(res.message || '验证码已发送');
      // 开始倒计时
      countdown.value = 60;
      countdownTimer = setInterval(() => {
        countdown.value--;
        if (countdown.value <= 0) {
          clearCountdown();
        }
      }, 1000);
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '发送失败');
  } finally {
    codeLoading.value = false;
  }
}

const handleSubmit = async () => {
  if (isLogin.value) {
    // 登录
    if (!form.value.username || !form.value.password) {
      ElMessage.warning('请输入账号和密码');
      return;
    }
  } else {
    // 注册
    if (!form.value.username) {
      ElMessage.warning('请输入用户名');
      return;
    }
    if (form.value.username.length < 2) {
      ElMessage.warning('用户名至少2个字符');
      return;
    }
    if (!/^[A-Za-z0-9_]+$/.test(form.value.username)) {
      ElMessage.warning('用户名只能包含字母、数字和下划线，且不能包含中文');
      return;
    }
    if (!form.value.email) {
      ElMessage.warning('请输入邮箱');
      return;
    }
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(form.value.email)) {
      ElMessage.warning('请输入有效的邮箱地址');
      return;
    }
    if (!form.value.code) {
      ElMessage.warning('请输入验证码');
      return;
    }
    if (!form.value.password) {
      ElMessage.warning('请输入密码');
      return;
    }
    if (form.value.password.length < 6) {
      ElMessage.warning('密码至少6个字符');
      return;
    }
    if (form.value.password !== form.value.confirmPassword) {
      ElMessage.warning('两次密码输入不一致');
      return;
    }
  }

  loading.value = true;
  try {
    let res;
    if (isLogin.value) {
      res = await authApi.login(form.value.username, form.value.password);
    } else {
      res = await authApi.register({
        username: form.value.username,
        email: form.value.email,
        password: form.value.password,
        code: form.value.code,
      });
    }

    if (res.code === 200) {
      // 保存 token
      localStorage.setItem('chatbot_token', res.data.access_token);
      localStorage.setItem('chatbot_refresh_token', res.data.refresh_token);
      localStorage.setItem('chatbot_user', JSON.stringify(res.data.user));
      
      ElMessage.success(isLogin.value ? '登录成功' : '注册成功');
      emit('update:modelValue', false);
      emit('success', res.data.user);
    } else {
      ElMessage.error(res.message || '操作失败');
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || e.message || '网络错误');
  } finally {
    loading.value = false;
  }
};
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="(val) => emit('update:modelValue', val)"
    width="420px"
    :close-on-click-modal="false"
    :show-close="false"
    class="auth-modal"
    align-center
  >
    <template #header>
      <div class="auth-header">
        <div class="auth-logo">
          <img :src="brandIcon" class="logo-img" alt="ChatBot" />
          <span class="logo-text">ChatBot</span>
        </div>
        <el-button class="close-btn" circle :icon="Close" @click="handleClose" />
      </div>
    </template>

    <div class="auth-body">
      <div v-if="!inForgot" class="auth-tabs">
        <div class="auth-tab" :class="{ active: isLogin }" @click="isLogin = true">
          登录
        </div>
        <div class="auth-tab" :class="{ active: !isLogin }" @click="isLogin = false">
          注册
        </div>
      </div>
      <div v-else class="auth-forgot-title">
        <el-icon><Lock /></el-icon>
        <span>找回密码</span>
      </div>

      <p v-if="!inForgot" class="auth-subtitle">
        {{ isLogin ? '欢迎回来，登录以继续聊天' : '创建账号，开启角色对话之旅' }}
      </p>
      <p v-else class="auth-subtitle">
        输入邮箱与验证码，找回你的账号密码
      </p>

      <!-- 登录 / 注册 -->
      <el-form v-if="!inForgot" @submit.prevent="handleSubmit" class="auth-form">
        <!-- 登录：用户名/邮箱 -->
        <el-form-item v-if="isLogin">
          <el-input
            v-model="form.username"
            placeholder="用户名或邮箱"
            size="large"
            :prefix-icon="User"
            autocomplete="username"
            class="auth-input"
          />
        </el-form-item>

        <!-- 注册：用户名 -->
        <el-form-item v-if="!isLogin">
          <el-input
            v-model="form.username"
            placeholder="用户名"
            size="large"
            :prefix-icon="User"
            class="auth-input"
          />
        </el-form-item>

        <!-- 注册：邮箱 + 验证码 -->
        <template v-if="!isLogin">
          <el-form-item>
            <el-input
              v-model="form.email"
              placeholder="邮箱"
              size="large"
              :prefix-icon="Message"
              type="email"
              class="auth-input"
            />
          </el-form-item>
          <el-form-item>
            <div class="code-input-group">
              <el-input
                v-model="form.code"
                placeholder="验证码"
                size="large"
                class="auth-input code-input"
                maxlength="6"
              />
              <el-button
                size="large"
                :disabled="countdown > 0"
                :loading="codeLoading"
                @click="sendCode"
                class="code-btn"
              >
                {{ countdown > 0 ? `${countdown}s 后重发` : '获取验证码' }}
              </el-button>
            </div>
          </el-form-item>
        </template>

        <el-form-item>
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码"
            size="large"
            :prefix-icon="Lock"
            show-password
            :autocomplete="isLogin ? 'current-password' : 'new-password'"
            @keyup.enter="handleSubmit"
            class="auth-input"
          />
        </el-form-item>

        <el-form-item v-if="!isLogin">
          <el-input
            v-model="form.confirmPassword"
            type="password"
            placeholder="确认密码"
            size="large"
            :prefix-icon="Lock"
            show-password
            @keyup.enter="handleSubmit"
            class="auth-input"
          />
        </el-form-item>

        <el-button
          type="primary"
          size="large"
          class="submit-btn"
          :loading="loading"
          @click="handleSubmit"
        >
          {{ isLogin ? '登录' : '注册' }}
        </el-button>
      </el-form>

      <div class="toggle-text">
        {{ isLogin ? '还没有账号？' : '已有账号？' }}
        <span class="toggle-link" @click="toggleMode">
          {{ isLogin ? '立即注册' : '去登录' }}
        </span>
        <span v-if="isLogin" class="forgot-link" @click="goForgot">忘记密码？</span>
      </div>

      <div v-if="!isLogin" class="register-tip">
        <el-icon><InfoFilled /></el-icon>
        <span>注册需要验证邮箱，未配置邮件服务时验证码为 123456</span>
      </div>

      <!-- 忘记密码：第一步 邮箱+验证码 -->
      <div v-if="inForgot && forgotStep === 1" class="forgot-step">
        <el-form-item>
          <el-input
            v-model="forgotForm.email"
            placeholder="邮箱"
            size="large"
            :prefix-icon="Message"
            type="email"
            class="auth-input"
          />
        </el-form-item>
        <el-form-item>
          <div class="code-input-group">
            <el-input
              v-model="forgotForm.code"
              placeholder="验证码"
              size="large"
              class="auth-input code-input"
              maxlength="6"
            />
            <el-button
              size="large"
              :disabled="forgotCountdown > 0"
              :loading="forgotCodeLoading"
              @click="sendForgotCode"
              class="code-btn"
            >
              {{ forgotCountdown > 0 ? `${forgotCountdown}s 后重发` : '获取验证码' }}
            </el-button>
          </div>
        </el-form-item>
        <el-button
          type="primary"
          size="large"
          class="submit-btn"
          :loading="forgotLoading"
          @click="submitForgotStep1"
        >
          下一步
        </el-button>
      </div>

      <!-- 忘记密码：第二步 设置新密码 -->
      <div v-if="inForgot && forgotStep === 2" class="forgot-step">
        <el-form-item>
          <el-input
            v-model="forgotForm.new_password"
            type="password"
            placeholder="新密码（至少6位）"
            size="large"
            :prefix-icon="Lock"
            show-password
            class="auth-input"
          />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="forgotForm.confirm_password"
            type="password"
            placeholder="确认新密码"
            size="large"
            :prefix-icon="Lock"
            show-password
            @keyup.enter="submitForgot"
            class="auth-input"
          />
        </el-form-item>
        <el-button
          type="primary"
          size="large"
          class="submit-btn"
          :loading="forgotLoading"
          @click="submitForgot"
        >
          重置密码
        </el-button>
        <div class="forgot-back">
          <span class="toggle-link" @click="backToLogin">返回登录</span>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<style scoped>
.auth-modal :deep(.el-dialog) {
  border-radius: 16px;
  overflow: hidden;
}

.auth-modal :deep(.el-dialog__header) {
  padding: 0;
  margin: 0;
}

.auth-modal :deep(.el-dialog__body) {
  padding: 0;
}

.auth-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px 0;
}

.auth-logo {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-img {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  object-fit: cover;
}

.logo-text {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
}

.close-btn {
  border: none;
  background: transparent;
  color: #9ca3af;
}

.close-btn:hover {
  background: #f3f4f6;
  color: #4b5563;
}

.auth-body {
  padding: 16px 32px 32px;
}

.auth-tabs {
  display: flex;
  gap: 24px;
  margin-bottom: 8px;
}

.auth-tab {
  font-size: 20px;
  font-weight: 600;
  color: #9ca3af;
  cursor: pointer;
  padding-bottom: 8px;
  border-bottom: 2px solid transparent;
  transition: all 0.2s;
}

.auth-tab.active {
  color: var(--text-primary);
  border-bottom-color: var(--brand);
}

.auth-subtitle {
  color: var(--text-secondary);
  font-size: 14px;
  margin: 0 0 24px 0;
}

.auth-form {
  margin-bottom: 20px;
}

.auth-input :deep(.el-input__wrapper) {
  border-radius: 10px;
  padding: 4px 12px;
}

.code-input-group {
  display: flex;
  gap: 10px;
}

.code-input {
  flex: 1;
}

.code-btn {
  width: 120px;
  white-space: nowrap;
  border-radius: 10px;
}

.submit-btn {
  width: 100%;
  height: 44px;
  font-size: 15px;
  border-radius: 10px;
  margin-top: 8px;
  background: var(--brand-gradient);
  border: none;
  font-weight: 500;
}

.submit-btn:hover {
  opacity: 0.9;
}

.toggle-text {
  text-align: center;
  color: #6b7280;
  font-size: 14px;
}

.toggle-link {
  color: var(--brand);
  cursor: pointer;
  font-weight: 500;
  margin-left: 4px;
}

.toggle-link:hover {
  text-decoration: underline;
}

.register-tip {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #909399;
  margin-top: 16px;
  padding: 8px 12px;
  background: #f4f4f5;
  border-radius: 6px;
}

.forgot-link {
  float: right;
  font-size: 13px;
  color: var(--brand);
  cursor: pointer;
}

.forgot-link:hover {
  text-decoration: underline;
}

.auth-forgot-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.forgot-step {
  display: flex;
  flex-direction: column;
}

.forgot-back {
  text-align: center;
  margin-top: 16px;
  font-size: 14px;
}
</style>
