<template>
  <!-- 免费模型使用提醒：没有配置自己 API Key 的用户，每次进入应用都会看到一次。
       不写入 sessionStorage / localStorage —— 刷新或下次进入照样提醒，
       因为「免费 GLM-4-Flash 能力有限」这件事不会因为点过一次就改变。 -->
  <el-dialog
    v-model="visible"
    :title="t('建议配置自己的 API Key', 'Configure your own API Key')"
    width="520px"
    align-center
    class="free-api-reminder-dialog"
    append-to-body
    :close-on-click-modal="false"
  >
    <div class="far-body">
      <p class="far-lead">
        {{ t('你当前正在使用共享的免费模型', 'You are currently using the shared free model') }}
        <strong class="far-model">{{ freeName || t('免费模型', 'Free model') }}</strong>。
      </p>

      <ul class="far-list">
        <li>
          <el-icon class="far-ico"><WarningFilled /></el-icon>
          <span>{{ t('免费通道有频率与并发限制，人多时需要排队，长对话容易被截断。', 'The free channel is rate-limited and shared, so replies can queue up or get cut off in long chats.') }}</span>
        </li>
        <li>
          <el-icon class="far-ico"><WarningFilled /></el-icon>
          <span>{{ t('免费模型本身能力较弱，角色扮演容易出戏、回复偏短、记不住设定，也就是常说的「比较呆」。', 'The free model is weak at roleplay: it breaks character, writes short replies and forgets your settings.') }}</span>
        </li>
        <li>
          <el-icon class="far-ico"><MagicStick /></el-icon>
          <span>{{ t('配置自己的 API Key 后，可自由选择更强的模型，长文回复、状态面板、生图等功能才能完整发挥。', 'With your own API Key you can pick stronger models, and long replies, status panels and image generation all work fully.') }}</span>
        </li>
      </ul>

      <p class="far-tip">
        {{ t('填上你自己的 Key 就行，配置只保存在你的账号里。', 'Just paste your own key — it is stored only in your account.') }}
      </p>
    </div>

    <template #footer>
      <div class="far-footer">
        <!-- 新用户首次登录时，这个弹窗会代替教程弹窗出现（两个弹窗叠在一起会互相遮挡），
             所以教程入口必须在这里也能进，不能只靠侧边栏 -->
        <el-button text :icon="Reading" @click="openTutorial">
          {{ t('查看使用教程', 'View the guide') }}
        </el-button>
        <div class="far-footer-right">
          <el-button text @click="visible = false">
            {{ t('先用免费的', 'Keep using free') }}
          </el-button>
          <el-button type="primary" :icon="Setting" @click="goConfigure">
            {{ t('去配置 API Key', 'Configure API Key') }}
          </el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed } from 'vue'
import { WarningFilled, MagicStick, Setting, Reading } from '@element-plus/icons-vue'
import { t } from '../i18n'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  // 当前免费模型名称（后端 FREE_API_NAME，如「免费 GLM-4-flash」）
  freeName: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue', 'configure', 'open-tutorial'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

function goConfigure() {
  visible.value = false
  emit('configure')
}

// 从这个弹窗进教程：先关掉自己，避免两层弹窗叠在一起
function openTutorial() {
  visible.value = false
  emit('open-tutorial')
}
</script>

<style scoped>
.far-lead {
  margin: 0 0 14px;
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-primary, #e8e0d5);
}
.far-model {
  color: var(--accent, #d8a06a);
}
.far-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.far-list li {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  font-size: 13px;
  line-height: 1.65;
  color: var(--text-secondary, #b9a98f);
}
.far-ico {
  flex: none;
  margin-top: 3px;
  color: var(--accent, #d8a06a);
}
.far-tip {
  margin: 14px 0 0;
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-muted, #9c8f7c);
  background: rgba(216, 160, 106, .08);
}
.far-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.far-footer-right {
  display: flex;
  gap: 8px;
}
</style>
