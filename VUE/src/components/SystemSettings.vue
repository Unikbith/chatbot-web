<template>
  <el-drawer
    v-model="visible"
    :title="t('系统设置', 'Settings')"
    size="min(500px, 100vw)"
    @close="handleClose"
  >
    <div class="system-settings">
      <el-tabs v-model="activeTab" class="settings-tabs">
        <!-- 通用设置 -->
        <el-tab-pane :label="t('通用设置', 'General')" name="general">
          <div class="settings-section">
            <div class="section-title">{{ t('外观', 'Appearance') }}</div>

            <div class="setting-item">
              <div class="setting-label">{{ t('主题模式', 'Theme Mode') }}</div>
              <el-radio-group v-model="localSettings.theme" size="default">
                <el-radio-button value="light">{{ t('浅色', 'Light') }}</el-radio-button>
                <el-radio-button value="dark">{{ t('深色', 'Dark') }}</el-radio-button>
                <el-radio-button value="auto">{{ t('跟随系统', 'System') }}</el-radio-button>
              </el-radio-group>
            </div>

            <div class="setting-item">
              <div class="setting-label">{{ t('语言', 'Language') }}</div>
              <el-select v-model="localSettings.language" style="width: 200px" @change="handleLanguageChange">
                <el-option label="跟随系统" value="auto" />
                <el-option label="简体中文" value="zh-CN" />
                <el-option label="English" value="en" />
              </el-select>
            </div>
          </div>

          <div class="settings-section avatar-section">
            <div class="section-title">{{ t('头像', 'Avatars') }}</div>
            <p class="section-desc">{{ t('通用头像用于所有未单独设置头像的角色对话，可分别在聊天框与角色设置中覆盖。', 'General avatars apply to conversations that have no per-chat avatar. They can be overridden per chat.') }}</p>

            <div class="avatar-row">
              <div class="avatar-block">
                <el-avatar :size="60" :src="userAvatarUrl" class="avatar-preview">
                  <el-icon><User /></el-icon>
                </el-avatar>
                <div class="avatar-meta">
                  <span class="avatar-label">{{ t('用户头像', 'User Avatar') }}</span>
                  <el-upload
                    :show-file-list="false"
                    :before-upload="handleUserAvatarUpload"
                    accept="image/*"
                  >
                    <el-button size="small">{{ t('更换', 'Change') }}</el-button>
                  </el-upload>
                </div>
              </div>

              <div class="avatar-block">
                <el-avatar :size="60" :src="aiAvatarUrl" class="avatar-preview ai-avatar">
                  <el-icon><MagicStick /></el-icon>
                </el-avatar>
                <div class="avatar-meta">
                  <span class="avatar-label">{{ t('AI 头像', 'AI Avatar') }}</span>
                  <el-upload
                    :show-file-list="false"
                    :before-upload="handleAiAvatarUpload"
                    accept="image/*"
                  >
                    <el-button size="small">{{ t('更换', 'Change') }}</el-button>
                  </el-upload>
                </div>
              </div>
            </div>
          </div>

          <div class="settings-section">
            <div class="section-title">{{ t('界面', 'Interface') }}</div>

            <div class="setting-item">
              <div class="setting-label">{{ t('背景图片', 'Background Image') }}</div>
              <div class="bg-image-control">
                <div class="bg-preview" :style="bgPreviewStyle">
                  <span v-if="!localSettings.background_image" class="bg-placeholder">{{ t('无背景', 'None') }}</span>
                </div>
                <div class="bg-actions">
                  <el-upload
                    :show-file-list="false"
                    :before-upload="handleBgUpload"
                    accept="image/*"
                  >
                    <el-button size="small">{{ t('上传图片', 'Upload') }}</el-button>
                  </el-upload>
                  <el-button
                    size="small"
                    type="danger"
                    plain
                    @click="clearBgImage"
                    :disabled="!localSettings.background_image"
                  >
                    {{ t('清除', 'Clear') }}
                  </el-button>
                </div>
              </div>
            </div>

            <div class="setting-item">
              <div class="setting-label">{{ t('消息框透明度', 'Message Transparency') }}</div>
              <div class="slider-control">
                <el-slider
                  v-model="localSettings.message_opacity"
                  :min="0.1"
                  :max="1"
                  :step="0.05"
                  style="flex: 1; margin-right: 16px"
                />
                <span class="slider-value">{{ Math.round(localSettings.message_opacity * 100) }}%</span>
              </div>
            </div>
          </div>

          <div class="settings-section">
            <div class="section-title">{{ t('AI 参数微调', 'AI Parameters') }}</div>
            <p class="section-desc">{{ t('以下为各模型通用参数，小众参数未包含以保持简洁。', 'Common parameters across models; niche ones omitted for clarity.') }}</p>

            <div class="setting-item">
              <div class="setting-label">
                {{ t('温度 (Temperature)', 'Temperature') }}
                <el-tooltip :content="t('较高值使输出更随机创意，较低值更确定保守', 'Higher is more creative, lower is more focused')" placement="top">
                  <el-icon class="help-icon"><QuestionFilled /></el-icon>
                </el-tooltip>
              </div>
              <div class="slider-control">
                <el-slider v-model="localSettings.temperature" :min="0" :max="2" :step="0.1" style="flex: 1; margin-right: 16px" />
                <span class="slider-value">{{ localSettings.temperature.toFixed(1) }}</span>
              </div>
            </div>

            <div class="setting-item">
              <div class="setting-label">
                {{ t('频率惩罚 (Frequency Penalty)', 'Frequency Penalty') }}
                <el-tooltip :content="t('减少重复内容，值越高越倾向于使用新词', 'Reduce repetition')" placement="top">
                  <el-icon class="help-icon"><QuestionFilled /></el-icon>
                </el-tooltip>
              </div>
              <div class="slider-control">
                <el-slider v-model="localSettings.frequency_penalty" :min="-2" :max="2" :step="0.1" style="flex: 1; margin-right: 16px" />
                <span class="slider-value">{{ localSettings.frequency_penalty.toFixed(1) }}</span>
              </div>
            </div>

            <div class="setting-item">
              <div class="setting-label">
                {{ t('存在惩罚 (Presence Penalty)', 'Presence Penalty') }}
                <el-tooltip :content="t('增加谈论新话题的可能性', 'Increase chance of new topics')" placement="top">
                  <el-icon class="help-icon"><QuestionFilled /></el-icon>
                </el-tooltip>
              </div>
              <div class="slider-control">
                <el-slider v-model="localSettings.presence_penalty" :min="-2" :max="2" :step="0.1" style="flex: 1; margin-right: 16px" />
                <span class="slider-value">{{ localSettings.presence_penalty.toFixed(1) }}</span>
              </div>
            </div>

            <div class="setting-item">
              <div class="setting-label">
                {{ t('核采样 (Top P)', 'Top P') }}
                <el-tooltip :content="t('从概率质量前 P% 的 token 中采样', 'Sample from top P% of tokens')" placement="top">
                  <el-icon class="help-icon"><QuestionFilled /></el-icon>
                </el-tooltip>
              </div>
              <div class="slider-control">
                <el-slider v-model="localSettings.top_p" :min="0" :max="1" :step="0.05" style="flex: 1; margin-right: 16px" />
                <span class="slider-value">{{ localSettings.top_p.toFixed(2) }}</span>
              </div>
            </div>
          </div>

          <div class="settings-section">
            <div class="section-title">{{ t('语音', 'Voice') }}</div>

            <div class="setting-item">
              <div class="setting-label">{{ t('自动播报 AI 回复', 'Auto-play replies') }}</div>
              <el-switch v-model="localSettings.auto_play_voice" />
            </div>

            <div class="setting-item">
              <div class="setting-label">{{ t('默认音色', 'Default Voice') }}</div>
              <el-select v-model="localSettings.default_voice" style="width: 200px">
                <el-option label="Alloy (合金)" value="alloy" />
                <el-option label="Echo (回响)" value="echo" />
                <el-option label="Fable (寓言)" value="fable" />
                <el-option label="Onyx (缟玛瑙)" value="onyx" />
                <el-option label="Nova (新星)" value="nova" />
                <el-option label="Shimmer (微光)" value="shimmer" />
              </el-select>
            </div>
          </div>
        </el-tab-pane>

        <!-- 账号管理 -->
        <el-tab-pane :label="t('账号管理', 'Account')" name="account">
          <div class="settings-section">
            <div class="section-title">{{ t('基本信息', 'Basic Info') }}</div>

            <div class="setting-item">
              <div class="setting-label">{{ t('用户名', 'Username') }}</div>
              <div class="inline-edit">
                <span v-if="!editingUsername" class="edit-value">{{ user?.username }}</span>
                <el-input
                  v-else
                  v-model="newUsername"
                  size="small"
                  style="width: 200px"
                  @keyup.enter="saveUsername"
                />
                <el-button
                  size="small"
                  type="primary"
                  link
                  @click="editingUsername ? saveUsername() : (editingUsername = true, newUsername = user?.username || '')"
                >
                  {{ editingUsername ? t('保存', 'Save') : t('修改', 'Edit') }}
                </el-button>
              </div>
            </div>

            <div class="setting-item">
              <div class="setting-label">{{ t('邮箱', 'Email') }}</div>
              <span class="static-value">{{ user?.email }}</span>
            </div>
          </div>

          <div class="settings-section">
            <div class="section-title">{{ t('安全', 'Security') }}</div>
            <div class="setting-item">
              <div class="setting-label">{{ t('修改密码', 'Change Password') }}</div>
              <el-button size="small" @click="showPwdDialog = true">{{ t('修改密码', 'Change Password') }}</el-button>
            </div>
          </div>

          <div class="settings-section danger-section">
            <div class="section-title">{{ t('危险操作', 'Danger Zone') }}</div>
            <div class="setting-item">
              <div class="setting-label">{{ t('登出所有设备', 'Logout All Devices') }}</div>
              <el-button size="small" type="warning" @click="logoutAllDevices">{{ t('登出所有设备', 'Logout') }}</el-button>
            </div>
            <div class="setting-item">
              <div class="setting-label">{{ t('注销账号', 'Delete Account') }}</div>
              <el-button size="small" type="danger" @click="showDeleteDialog = true">{{ t('注销账号', 'Delete') }}</el-button>
              <p class="danger-tip">{{ t('注销后所有数据将被永久删除，无法恢复', 'All data will be permanently deleted.') }}</p>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>

      <div class="settings-footer">
        <el-button @click="resetSettings">{{ t('恢复默认', 'Reset') }}</el-button>
        <el-button type="primary" @click="saveSettings" :loading="saving">{{ t('保存设置', 'Save') }}</el-button>
      </div>
    </div>

    <!-- 修改密码对话框 -->
    <el-dialog v-model="showPwdDialog" :title="t('修改密码', 'Change Password')" width="400px">
      <el-form :model="pwdForm" :label-width="t('原密码','Old').length * 14 + 20 + 'px'">
        <el-form-item :label="t('原密码', 'Old password')">
          <el-input v-model="pwdForm.old_password" type="password" show-password />
        </el-form-item>
        <el-form-item :label="t('新密码', 'New password')">
          <el-input v-model="pwdForm.new_password" type="password" show-password />
        </el-form-item>
        <el-form-item :label="t('确认密码', 'Confirm')">
          <el-input v-model="pwdForm.confirm_password" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showPwdDialog = false">{{ t('取消', 'Cancel') }}</el-button>
        <el-button type="primary" @click="changePassword" :loading="pwdLoading">{{ t('确认', 'Confirm') }}</el-button>
      </template>
    </el-dialog>

    <!-- 注销账号对话框 -->
    <el-dialog v-model="showDeleteDialog" :title="t('确认注销账号', 'Delete Account')" width="400px">
      <p style="color: #f56c6c; margin-bottom: 16px;">
        {{ t('警告：注销账号后，您的所有数据将被永久删除，无法恢复！', 'Warning: all your data will be permanently deleted!') }}
      </p>
      <el-form :model="deleteForm" label-width="60px">
        <el-form-item :label="t('密码', 'Password')">
          <el-input v-model="deleteForm.password" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDeleteDialog = false">{{ t('取消', 'Cancel') }}</el-button>
        <el-button type="danger" @click="confirmDelete" :loading="deleteLoading">{{ t('确认注销', 'Delete') }}</el-button>
      </template>
    </el-dialog>
  </el-drawer>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { User, MagicStick, QuestionFilled } from '@element-plus/icons-vue'
import { settingsApi, uploadApi, authApi } from '../utils/resAi'
import { setLocale } from '../i18n'
import { t } from '../i18n'
import { applyTheme } from '../utils/theme'

const props = defineProps({
  modelValue: Boolean,
  user: Object,
})

const emit = defineEmits(['update:modelValue', 'settings-updated', 'user-updated', 'logout'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const activeTab = ref('general')
const saving = ref(false)
const editingUsername = ref(false)
const newUsername = ref('')

const showPwdDialog = ref(false)
const pwdLoading = ref(false)
const pwdForm = reactive({ old_password: '', new_password: '', confirm_password: '' })

const showDeleteDialog = ref(false)
const deleteLoading = ref(false)
const deleteForm = reactive({ password: '' })

const defaultSettings = {
  theme: 'auto',
  language: 'auto',
  background_image: null,
  message_opacity: 0.9,
  sidebar_collapsed: false,
  temperature: 0.8,
  frequency_penalty: 0.0,
  presence_penalty: 0.0,
  top_p: 0.95,
  default_voice: 'alloy',
  auto_play_voice: false,
}

const localSettings = reactive({ ...defaultSettings })

const userAvatarUrl = computed(() => props.user?.avatar || '')
const aiAvatarUrl = computed(() => props.user?.ai_avatar || '')

const bgPreviewStyle = computed(() => {
  if (localSettings.background_image) {
    return { backgroundImage: `url(${localSettings.background_image})`, backgroundSize: 'cover', backgroundPosition: 'center' }
  }
  return {}
})

// 应用主题 - 由 utils/theme 提供

// 主题、语言变更即时预览
watch(() => localSettings.theme, (v) => applyTheme(v))
function handleLanguageChange() {
  setLocale(localSettings.language === 'en' ? 'en' : (localSettings.language === 'zh-CN' ? 'zh-CN' : 'auto'))
}

watch(() => props.modelValue, (val) => {
  if (val) {
    loadSettings()
  }
})

async function loadSettings() {
  try {
    const res = await settingsApi.get()
    if (res.code === 200 && res.data) {
      Object.assign(localSettings, res.data)
      applyTheme(localSettings.theme)
      handleLanguageChange()
    }
  } catch (e) {
    console.error('加载设置失败', e)
  }
}

function handleClose() {
  visible.value = false
}

async function saveSettings() {
  saving.value = true
  try {
    const payload = { ...localSettings }
    const res = await settingsApi.update(payload)
    if (res.code === 200) {
      ElMessage.success(t('设置已保存', 'Settings saved'))
      emit('settings-updated', { ...localSettings })
      applyTheme(localSettings.theme)
      handleLanguageChange()
    }
  } catch (e) {
    ElMessage.error(t('保存失败', 'Save failed'))
  } finally {
    saving.value = false
  }
}

function resetSettings() {
  Object.assign(localSettings, defaultSettings)
  applyTheme(localSettings.theme)
}

// 背景图片上传
async function handleBgUpload(file) {
  try {
    const res = await uploadApi.uploadImage(file)
    if (res.code === 200) {
      localSettings.background_image = res.data.url
      ElMessage.success(t('上传成功', 'Uploaded'))
    }
  } catch (e) {
    ElMessage.error(t('上传失败', 'Upload failed'))
  }
  return false
}

function clearBgImage() {
  localSettings.background_image = null
}

// 头像上传
async function handleUserAvatarUpload(file) {
  try {
    const res = await uploadApi.uploadImage(file)
    if (res.code === 200) {
      await settingsApi.updateProfile({ avatar: res.data.url })
      emit('user-updated', { ...props.user, avatar: res.data.url })
      ElMessage.success(t('头像已更新', 'Avatar updated'))
    }
  } catch (e) {
    ElMessage.error(t('上传失败', 'Upload failed'))
  }
  return false
}

async function handleAiAvatarUpload(file) {
  try {
    const res = await uploadApi.uploadImage(file)
    if (res.code === 200) {
      await settingsApi.updateProfile({ ai_avatar: res.data.url })
      emit('user-updated', { ...props.user, ai_avatar: res.data.url })
      ElMessage.success(t('AI 头像已更新', 'AI avatar updated'))
    }
  } catch (e) {
    ElMessage.error(t('上传失败', 'Upload failed'))
  }
  return false
}

// 用户名修改
function saveUsername() {
  if (!newUsername.value.trim()) {
    ElMessage.warning(t('用户名不能为空', 'Username cannot be empty'))
    return
  }
  settingsApi.updateProfile({ username: newUsername.value.trim() }).then(res => {
    if (res.code === 200) {
      ElMessage.success(t('用户名已更新', 'Username updated'))
      emit('user-updated', res.data)
      editingUsername.value = false
    }
  }).catch(() => {
    ElMessage.error(t('修改失败', 'Failed'))
  })
}

// 修改密码
async function changePassword() {
  if (!pwdForm.old_password || !pwdForm.new_password) {
    ElMessage.warning(t('请填写完整', 'Please fill in all fields'))
    return
  }
  if (pwdForm.new_password.length < 6) {
    ElMessage.warning(t('新密码至少6位', 'Password must be at least 6 chars'))
    return
  }
  if (pwdForm.new_password !== pwdForm.confirm_password) {
    ElMessage.warning(t('两次密码不一致', 'Passwords do not match'))
    return
  }
  pwdLoading.value = true
  try {
    const res = await authApi.changePassword(pwdForm.old_password, pwdForm.new_password)
    if (res.code === 200) {
      ElMessage.success(t('密码修改成功', 'Password changed'))
      showPwdDialog.value = false
      pwdForm.old_password = ''
      pwdForm.new_password = ''
      pwdForm.confirm_password = ''
    }
  } catch (e) {
    ElMessage.error(t('修改失败', 'Failed'))
  } finally {
    pwdLoading.value = false
  }
}

// 登出所有设备
function logoutAllDevices() {
  ElMessageBox.confirm(
    t('确定要登出所有设备吗？登出后需要重新登录。', 'Log out from all devices?'),
    t('确认', 'Confirm'),
    { type: 'warning' }
  ).then(() => {
    authApi.logout()
    emit('logout')
    ElMessage.success(t('已登出所有设备', 'Logged out'))
  }).catch(() => {})
}

// 注销账号
async function confirmDelete() {
  if (!deleteForm.password) {
    ElMessage.warning(t('请输入密码', 'Enter your password'))
    return
  }
  deleteLoading.value = true
  try {
    const res = await authApi.deleteAccount(deleteForm.password)
    if (res.code === 200) {
      ElMessage.success(t('账号已注销', 'Account deleted'))
      showDeleteDialog.value = false
      authApi.logout()
      emit('logout')
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || t('注销失败', 'Delete failed'))
  } finally {
    deleteLoading.value = false
  }
}
</script>

<style scoped>
.system-settings {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.settings-tabs {
  flex: 1;
  overflow-y: auto;
  padding-right: 8px;
}

.settings-section {
  margin-bottom: 28px;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-color);
}

.section-desc {
  font-size: 12px;
  color: var(--text-muted);
  margin: -8px 0 16px 0;
}

.setting-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
  min-height: 48px;
}

.setting-label {
  display: flex;
  align-items: center;
  font-size: 14px;
  color: var(--text-secondary);
}

.help-icon {
  margin-left: 4px;
  color: #c0c4cc;
  cursor: help;
}

.slider-control {
  display: flex;
  align-items: center;
  width: 280px;
}

.slider-value {
  min-width: 48px;
  text-align: right;
  font-size: 13px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

/* 头像区域（明显位置，用户/AI 单独设置） */
.avatar-section .avatar-row {
  display: flex;
  gap: 24px;
}

.avatar-block {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  background: var(--surface);
}

.avatar-meta {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.avatar-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.avatar-preview {
  border: 2px solid var(--border-color);
  flex-shrink: 0;
}

.ai-avatar {
  border-color: #a7f3d0;
}

.bg-image-control {
  display: flex;
  gap: 12px;
  align-items: center;
}

.bg-preview {
  width: 80px;
  height: 56px;
  border-radius: 6px;
  border: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--surface-hover);
}

.bg-placeholder {
  font-size: 12px;
  color: var(--text-muted);
}

.bg-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.inline-edit {
  display: flex;
  align-items: center;
  gap: 8px;
}

.edit-value {
  font-size: 14px;
  color: var(--text-primary);
}

.static-value {
  font-size: 14px;
  color: var(--text-muted);
}

.danger-section .section-title {
  color: #f56c6c;
}

.danger-tip {
  font-size: 12px;
  color: #f56c6c;
  margin: 8px 0 0 0;
}

.settings-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
  margin-top: auto;
}
</style>