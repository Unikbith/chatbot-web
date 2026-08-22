<script setup>
import { nextTick, onMounted, onUnmounted, ref, watch, computed } from 'vue';
import { fetchStream, readStream } from '@/utils/resAi';

import katoImage from '@/assets/images/加藤惠.jpg';
import natsumeImage from '@/assets/images/夏目贵志.jpg';

const messages = ref([
  { role: 'assistant', content: '你好呀,我是加藤惠~', reasoning: '', showReasoning: false }
]);
const inputText = ref('');
const loading = ref(false);
const messageList = ref(null);
const deepThink = ref(false);
let abortController = null;

const aiAvatar = ref(katoImage);
const userAvatar = ref(natsumeImage);
const wrapperBg = ref('');

//  抽屉菜单状态 
const drawerVisible = ref(false);
const toggleDrawer = () => { drawerVisible.value = !drawerVisible.value; };
const closeDrawer = () => { drawerVisible.value = false; };

// 设置项
const settings = ref({
  apiKey: '',
  model: '',
  maxTokens: 30,
  aiAvatarData: null,
  userAvatarData: null,
  backgroundData: null,
  nsfwEnabled: false,
  nsfwMode: 'default',        // 'default' 或 'custom'
  nsfwCustomPrompt: '',       // 自定义提示词
});

// 加载存储的设置
const loadSettings = () => {
  try {
    const saved = localStorage.getItem('ai_chat_settings');
    if (saved) {
      const parsed = JSON.parse(saved);
      settings.value = { ...settings.value, ...parsed };
      if (parsed.aiAvatarData) {
        aiAvatar.value = parsed.aiAvatarData;
      } else {
        aiAvatar.value = katoImage;
      }
      if (parsed.userAvatarData) {
        userAvatar.value = parsed.userAvatarData;
      } else {
        userAvatar.value = natsumeImage;
      }
      if (parsed.backgroundData) {
        wrapperBg.value = parsed.backgroundData;
      } else {
        wrapperBg.value = '';
      }
    }
  } catch (e) {
    console.warn('加载设置失败', e);
  }
};

// 保存设置
const saveSettings = () => {
  try {
    localStorage.setItem('ai_chat_settings', JSON.stringify(settings.value));
  } catch (e) {
    console.warn('保存设置失败', e);
  }
};

// 监听设置变化自动保存
watch(settings, () => {
  saveSettings();
}, { deep: true });

// 头像上传 
const aiFileInputRef = ref(null);
const userFileInputRef = ref(null);

const handleAiAvatarUpload = (event) => {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    const dataUrl = e.target.result;
    settings.value.aiAvatarData = dataUrl;
    aiAvatar.value = dataUrl;
    aiFileInputRef.value.value = '';
  };
  reader.readAsDataURL(file);
};

const handleUserAvatarUpload = (event) => {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    const dataUrl = e.target.result;
    settings.value.userAvatarData = dataUrl;
    userAvatar.value = dataUrl;
    userFileInputRef.value.value = '';
  };
  reader.readAsDataURL(file);
};

const resetAiAvatar = () => {
  settings.value.aiAvatarData = null;
  aiAvatar.value = katoImage;
  saveSettings();
};

const resetUserAvatar = () => {
  settings.value.userAvatarData = null;
  userAvatar.value = natsumeImage;
  saveSettings();
};

//  背景图片上传 
const bgFileInputRef = ref(null);

const handleBgUpload = (event) => {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    const dataUrl = e.target.result;
    settings.value.backgroundData = dataUrl;
    wrapperBg.value = dataUrl;
    bgFileInputRef.value.value = '';
  };
  reader.readAsDataURL(file);
};

const resetBg = () => {
  settings.value.backgroundData = null;
  wrapperBg.value = '';
  saveSettings();
};

// 大图显示 
const showBigAvatar = ref(false);
const bigAvatarSrc = ref('');
const openBigAvatar = (src) => {
  bigAvatarSrc.value = src;
  showBigAvatar.value = true;
};
const closeBigAvatar = () => {
  showBigAvatar.value = false;
};

//  输入框自动增高 
const textareaRef = ref(null);
const autoResize = () => {
  const el = textareaRef.value;
  if (!el) return;
  el.style.height = 'auto';
  const maxHeight = 160;
  const newHeight = Math.min(el.scrollHeight, maxHeight);
  el.style.height = newHeight + 'px';
  el.style.overflowY = el.scrollHeight > maxHeight ? 'auto' : 'hidden';
};

// 滚动到底部 
const scrollToBottom = async () => {
  await nextTick();
  if (!messageList.value) return;
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      messageList.value.scrollTop = messageList.value.scrollHeight;
    });
  });
};

// 发送消息 
const handleSend = async () => {
  if (loading.value) {
    abortController?.abort();
    abortController = null;
    loading.value = false;
    return;
  }

  const text = inputText.value.trim();
  if (!text) return;

  messages.value.push({ role: 'user', content: text, reasoning: '', showReasoning: false });
  inputText.value = '';
  nextTick(() => autoResize());
  await scrollToBottom();

  const aiIndex = messages.value.length;
  messages.value.push({ role: 'assistant', content: '', reasoning: '', showReasoning: false });
  await scrollToBottom();

  loading.value = true;
  abortController = new AbortController();

  try {
    const requestBody = {
      messages: messages.value.slice(0, -1).map(({ role, content }) => ({ role, content })),
      deep_think: deepThink.value,
      nsfw_enabled: settings.value.nsfwEnabled,
      nsfw_mode: settings.value.nsfwMode,
      nsfw_custom_prompt: settings.value.nsfwCustomPrompt,
    };
    if (settings.value.apiKey.trim()) {
      requestBody.api_key = settings.value.apiKey.trim();
    }
    if (settings.value.model.trim()) {
      requestBody.model = settings.value.model.trim();
    }
    requestBody.max_tokens = settings.value.maxTokens;

    const response = await fetchStream(
      '/api/chat',
      requestBody,
      { signal: abortController.signal }
    );

    await readStream(response, (data) => {
      const delta = data.choices?.[0]?.delta || {};
      const reasoning = delta.reasoning_content || '';
      const content = delta.content || '';
      if (reasoning) {
        messages.value[aiIndex].reasoning += reasoning;
      }
      if (content) {
        messages.value[aiIndex].content += content;
      }
      if (reasoning || content) {
        scrollToBottom();
      }
    });

  } catch (error) {
    if (error.name === 'AbortError') {
      messages.value[aiIndex].content += '（已中止）';
    } else {
      console.error('发送失败', error);
      messages.value[aiIndex].content = `出错了：${error.message || '网络异常'}`;
    }
  } finally {
    loading.value = false;
    abortController = null;
    await scrollToBottom();
  }
};

// 键盘事件 
const handleKeydown = (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    handleSend();
  }
};

// 清除聊天 
const handleClearChat = () => {
  if (loading.value) {
    abortController?.abort();
    abortController = null;
    loading.value = false;
  }
  messages.value = [
    { role: 'assistant', content: '你好呀,我是加藤惠~', reasoning: '', showReasoning: false }
  ];
  inputText.value = '';
  localStorage.removeItem('chat_history');
  scrollToBottom();
};

// 消息持久化 
const saveMessages = () => {
  localStorage.setItem('chat_history', JSON.stringify(messages.value));
};
const loadMessages = () => {
  const saved = localStorage.getItem('chat_history');
  if (saved) {
    try {
      const parsed = JSON.parse(saved);
      messages.value = parsed.map(msg => ({
        ...msg,
        reasoning: msg.reasoning || '',
        showReasoning: false
      }));
    } catch (e) {
      console.warn('历史记录解析失败');
    }
  }
};

let saveTimer = null;
watch(messages, () => {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveMessages, 500);
}, { deep: true });

//  挂载 
onMounted(async () => {
  loadSettings();
  loadMessages();
  await scrollToBottom();
});

onUnmounted(() => {
  abortController?.abort();
  abortController = null;
});
</script>

<template>
  <!-- wrapper 绑定动态背景 -->
  <div class="wrapper"
    :style="wrapperBg ? { backgroundImage: `url(${wrapperBg})`, backgroundSize: 'cover', backgroundPosition: 'center', backgroundRepeat: 'no-repeat' } : {}">
    <!-- 头部  -->
    <div class="wrapper-head">
      <div class="head-left">
        <button class="menu-btn" @click="toggleDrawer" aria-label="打开设置">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round">
            <line x1="3" y1="6" x2="21" y2="6" />
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </svg>
        </button>
        <div class="name">
          <span>贤妻加藤惠</span>
        </div>
      </div>
      <div class="header-actions">
        <button class="clear-btn" @click="handleClearChat" title="重新开始聊天">
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 6h18" />
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
            <line x1="10" y1="11" x2="10" y2="17" />
            <line x1="14" y1="11" x2="14" y2="17" />
          </svg>
        </button>
        <img :src="aiAvatar" alt="加藤惠" class="avatar-ai" @click="openBigAvatar(aiAvatar)" style="cursor:pointer;">
      </div>
    </div>

    <!-- 抽屉菜单 -->
    <div class="drawer-overlay" v-if="drawerVisible" @click="closeDrawer"></div>
    <div class="drawer" :class="{ open: drawerVisible }">
      <div class="drawer-header">
        <span>设置</span>
        <button class="drawer-close" @click="closeDrawer">✕</button>
      </div>
      <div class="drawer-body">
        <!-- NSFW 开关 -->
        <div class="nsfw-toggle-row">
          <label class="nsfw-toggle">
            <input type="checkbox" v-model="settings.nsfwEnabled" />
            <span class="toggle-slider"></span>
            <span class="toggle-label">🔞 NSFW</span>
          </label>
          <span class="nsfw-hint">{{ settings.nsfwEnabled ? '已开启（启用续写）' : '已关闭（不续写）' }}</span>
        </div>

        <!-- 人物设定选择（仅 NSFW 开启时显示） -->
        <div v-if="settings.nsfwEnabled" class="nsfw-prompt-section">
          <div class="setting-group">
            <label>人物设定</label>
            <select v-model="settings.nsfwMode">
              <option value="default">默认</option>
              <option value="custom">自定义</option>
            </select>
            <small class="hint">选择 "自定义" 可在下方输入框填写人物设定提示词</small>
          </div>

          <!-- 自定义提示词输入框 -->
          <div v-if="settings.nsfwMode === 'custom'" class="setting-group">
            <label>自定义提示词</label>
            <textarea v-model="settings.nsfwCustomPrompt" class="custom-prompt-textarea" placeholder="请输入自定义的人物设定提示词..."
              rows="4"></textarea>
            <small class="hint">输入后将替换默认的 NSFW 人物设定</small>
          </div>
        </div>

        <div class="setting-divider">基础设置</div>

        <!-- API Key -->
        <div class="setting-group">
          <label>API Key</label>
          <input type="password" v-model="settings.apiKey" placeholder="留空则使用默认" />
        </div>
        <!-- 模型 -->
        <div class="setting-group">
          <label>模型</label>
          <input type="text" v-model="settings.model" placeholder="例如 glm-4.5-flash" />
          <small class="hint">留空使用默认（glm-4.5-flash）</small>
        </div>
        <!-- 回复长度 -->
        <div class="setting-group">
          <label>回复长度（挡位）</label>
          <select v-model="settings.maxTokens">
            <option v-for="val in [30, 50, 100, 150]" :key="val" :value="val">
              {{ val }} 字
            </option>
          </select>
          <small class="hint">当前选择：{{ settings.maxTokens }} 字（NSFW 开启时生效）</small>
        </div>

        <!-- 头像区域 -->
        <div class="setting-divider">头像设置</div>

        <!-- AI 头像 -->
        <div class="setting-group">
          <label>AI 头像</label>
          <div class="avatar-upload-row">
            <img :src="aiAvatar" class="avatar-preview" alt="AI头像" />
            <div class="avatar-actions">
              <input type="file" ref="aiFileInputRef" accept="image/*" @change="handleAiAvatarUpload"
                style="display:none" />
              <button class="avatar-btn" @click="aiFileInputRef.click()">上传</button>
              <button class="avatar-btn reset" @click="resetAiAvatar">重置</button>
            </div>
          </div>
        </div>

        <!-- 用户头像 -->
        <div class="setting-group">
          <label>用户头像</label>
          <div class="avatar-upload-row">
            <img :src="userAvatar" class="avatar-preview" alt="用户头像" />
            <div class="avatar-actions">
              <input type="file" ref="userFileInputRef" accept="image/*" @change="handleUserAvatarUpload"
                style="display:none" />
              <button class="avatar-btn" @click="userFileInputRef.click()">上传</button>
              <button class="avatar-btn reset" @click="resetUserAvatar">重置</button>
            </div>
          </div>
        </div>

        <!--  背景图片 -->
        <div class="setting-divider">背景设置</div>

        <div class="setting-group">
          <label>聊天背景图片</label>
          <div class="avatar-upload-row">
            <div class="bg-preview"
              :style="wrapperBg ? { backgroundImage: `url(${wrapperBg})`, backgroundSize: 'cover', backgroundPosition: 'center' } : { background: '#f5f5f5', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#aaa', fontSize: '12px' }">
              {{ wrapperBg ? '' : '无背景' }}
            </div>
            <div class="avatar-actions">
              <input type="file" ref="bgFileInputRef" accept="image/*" @change="handleBgUpload" style="display:none" />
              <button class="avatar-btn" @click="bgFileInputRef.click()">上传</button>
              <button class="avatar-btn reset" @click="resetBg">✕ 移除</button>
            </div>
          </div>
          <small class="hint">上传图片将作为聊天区域背景</small>
        </div>
      </div>
    </div>

    <!-- 消息列表  -->
    <div class="wrapper-body">
      <ul class="message-list" ref="messageList">
        <li v-for="(item, index) in messages" :key="index"
          :class="item.role === 'assistant' ? 'message-ai' : 'message-user'">
          <img :src="item.role === 'assistant' ? aiAvatar : userAvatar" alt="avatar" class="avatar"
            @click="openBigAvatar(item.role === 'assistant' ? aiAvatar : userAvatar)" style="cursor:pointer;">
          <div class="message-content">
            <!-- 思考过程 -->
            <div v-if="item.role === 'assistant' && item.reasoning" class="reasoning-wrapper">
              <div class="reasoning-toggle" @click="item.showReasoning = !item.showReasoning">
                <span>{{ item.showReasoning ? '收起思考' : '查看思考' }}</span>
                <span class="arrow">{{ item.showReasoning ? '▲' : '▼' }}</span>
              </div>
              <div v-show="item.showReasoning" class="reasoning-block">
                <div class="reasoning-label"> 思考过程</div>
                <div class="reasoning-text">{{ item.reasoning }}</div>
              </div>
            </div>
            <!-- 正文 -->
            <div v-if="item.content" class="content-text">{{ item.content }}</div>
            <div v-if="item.role === 'assistant' && !item.content && !item.reasoning" class="loading-text">
              正在输入...
            </div>
          </div>
        </li>
      </ul>
    </div>

    <!--  底部输入  -->
    <div class="wrapper-foot">
      <label class="deep-think-capsule">
        <input type="checkbox" v-model="deepThink" />
        <span>深度思考</span>
      </label>
      <textarea ref="textareaRef" class="input" placeholder="说些什么吧..." v-model="inputText" @keydown="handleKeydown"
        @input="autoResize" rows="1"></textarea>
      <button class="btn" @click="handleSend">
        {{ loading ? '停止' : '发送' }}
      </button>
    </div>

    <!--  大图模态框  -->
    <div v-if="showBigAvatar" class="big-avatar-overlay" @click="closeBigAvatar">
      <div class="big-avatar-container" @click.stop>
        <img :src="bigAvatarSrc" alt="大图" class="big-avatar-img" />
        <button class="close-big-avatar" @click="closeBigAvatar">✕</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

.wrapper {
  display: flex;
  flex-direction: column;
  margin: 30px auto;
  height: 650px;
  width: 800px;
  border-radius: 12px;
  overflow: hidden;
  background-color: #f5f5f5;
  box-shadow: 0 2px 12px 12px rgba(0, 0, 0, 0.1);
  position: relative;
  transition: background-image 0.3s ease;
}

/*  头部 */
.wrapper-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  height: 80px;
  background: linear-gradient(to right, #fd72e5, #be5cee);
  flex-shrink: 0;
  position: relative;
  z-index: 2;
}

.head-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.menu-btn {
  background: rgba(255, 255, 255, 0.2);
  border: none;
  color: white;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.2s;
}

.menu-btn:hover {
  background: rgba(255, 255, 255, 0.35);
}

.wrapper-head .name {
  color: white;
  font-size: 20px;
  font-weight: bold;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}

.clear-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: none;
  background: rgba(255, 255, 255, 0.2);
  color: white;
  cursor: pointer;
  transition: all 0.3s ease;
}

.clear-btn:hover {
  background: rgba(255, 255, 255, 0.35);
  transform: scale(1.05);
}

.clear-btn:active {
  transform: scale(0.95);
}

.clear-btn svg {
  width: 20px;
  height: 20px;
}

.avatar-ai {
  width: 60px;
  height: 60px;
  border-radius: 50%;
  object-fit: cover;
  cursor: pointer;
  transition: transform 0.2s;
}

.avatar-ai:hover {
  transform: scale(1.05);
}

/*  抽屉 */
.drawer-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.4);
  z-index: 9998;
}

.drawer {
  position: fixed;
  top: 0;
  left: -360px;
  width: 360px;
  height: 100%;
  background: #fff;
  box-shadow: 2px 0 12px rgba(0, 0, 0, 0.15);
  transition: left 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  z-index: 9999;
  display: flex;
  flex-direction: column;
}

.drawer.open {
  left: 0;
}

.drawer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid #eee;
  font-size: 18px;
  font-weight: bold;
  color: #333;
  flex-shrink: 0;
}

.drawer-close {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #888;
  padding: 0 4px;
}

.drawer-close:hover {
  color: #333;
}

.drawer-body {
  padding: 24px;
  flex: 1;
  overflow-y: auto;
}

/* NSFW 开关 */
.nsfw-toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: #faf5ff;
  border-radius: 12px;
  border: 1px solid #f0e6ff;
  margin-bottom: 16px;
}

.nsfw-toggle {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  user-select: none;
}

.nsfw-toggle input {
  display: none;
}

.nsfw-toggle .toggle-slider {
  width: 44px;
  height: 24px;
  background: #ccc;
  border-radius: 12px;
  transition: background 0.3s;
  position: relative;
  flex-shrink: 0;
}

.nsfw-toggle .toggle-slider::after {
  content: '';
  position: absolute;
  top: 3px;
  left: 3px;
  width: 18px;
  height: 18px;
  background: white;
  border-radius: 50%;
  transition: transform 0.3s;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

.nsfw-toggle input:checked+.toggle-slider {
  background: linear-gradient(to right, #ff6b6b, #ee5a24);
}

.nsfw-toggle input:checked+.toggle-slider::after {
  transform: translateX(20px);
}

.nsfw-toggle .toggle-label {
  font-size: 15px;
  font-weight: 600;
  color: #333;
}

.nsfw-hint {
  font-size: 12px;
  color: #999;
}

/*  NSFW 人物设定区域  */
.nsfw-prompt-section {
  background: #f8f8f8;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 16px;
  border: 1px solid #eee;
}

.custom-prompt-textarea {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 8px;
  font-size: 13px;
  background: #fafafa;
  transition: border 0.2s;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
  resize: vertical;
  min-height: 80px;
  line-height: 1.6;
}

.custom-prompt-textarea:focus {
  border-color: #be5cee;
  outline: none;
  background: #fff;
}

/*  设置分组  */
.setting-divider {
  font-size: 14px;
  font-weight: 600;
  color: #764ba2;
  margin: 20px 0 12px 0;
  padding-bottom: 6px;
  border-bottom: 2px solid #f0e6ff;
}

.setting-divider:first-of-type {
  margin-top: 0;
}

.setting-group {
  margin-bottom: 16px;
}

.setting-group label {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: #444;
  margin-bottom: 4px;
}

.setting-group input,
.setting-group select {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 8px;
  font-size: 14px;
  background: #fafafa;
  transition: border 0.2s;
}

.setting-group input:focus,
.setting-group select:focus {
  border-color: #be5cee;
  outline: none;
  background: #fff;
}

.setting-group .hint {
  font-size: 12px;
  color: #999;
  margin-top: 2px;
}

/* 头像上传 */
.avatar-upload-row {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 4px;
}

.avatar-preview {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  object-fit: cover;
  border: 2px solid #e0e0e0;
  flex-shrink: 0;
}

.bg-preview {
  width: 80px;
  height: 56px;
  border-radius: 8px;
  border: 2px solid #e0e0e0;
  flex-shrink: 0;
  overflow: hidden;
  background: #f5f5f5;
  font-size: 12px;
  color: #aaa;
  display: flex;
  align-items: center;
  justify-content: center;
}

.avatar-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.avatar-btn {
  padding: 4px 12px;
  border: 1px solid #ddd;
  border-radius: 6px;
  background: #f5f5f5;
  cursor: pointer;
  font-size: 13px;
  transition: background 0.2s;
}

.avatar-btn:hover {
  background: #e8e8e8;
}

.avatar-btn.reset {
  border-color: #ff6b6b;
  color: #ff6b6b;
}

.avatar-btn.reset:hover {
  background: #ffe0e0;
}

/*  消息列表  */
.wrapper-body {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
  position: relative;
  z-index: 1;
}

.message-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 0;
  margin: 10px;
  list-style: none;
  flex: 1;
  overflow-y: auto;
}

.message-list::-webkit-scrollbar {
  width: 0;
  height: 0;
  background: transparent;
  display: none;
}

.avatar {
  width: 42px;
  height: 42px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
  margin-top: 2px;
  cursor: pointer;
  transition: transform 0.2s;
}

.avatar:hover {
  transform: scale(1.05);
}

.message-ai {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.message-user {
  display: flex;
  flex-direction: row-reverse;
  gap: 10px;
}

.message-content {
  max-width: 70%;
  display: flex;
  flex-direction: column;
  gap: 0;
}

.reasoning-wrapper {
  margin-bottom: 16px;
}

.reasoning-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  user-select: none;
  padding: 4px 12px;
  background: #e8e8e8;
  border-radius: 20px;
  font-size: 13px;
  color: #555;
  transition: background 0.2s;
}

.reasoning-toggle:hover {
  background: #d0d0d0;
}

.reasoning-toggle .arrow {
  font-size: 12px;
  transition: transform 0.2s;
}

.reasoning-block {
  background: rgba(240, 240, 240, 0.92);
  padding: 10px 14px;
  border-radius: 12px;
  border-left: 4px solid #be5cee;
  margin-top: 8px;
  font-size: 14px;
  color: #555;
}

.reasoning-label {
  font-weight: bold;
  color: #764ba2;
  margin-bottom: 4px;
  font-size: 13px;
}

.reasoning-text {
  white-space: pre-wrap;
  word-wrap: break-word;
  line-height: 1.6;
}

.message-ai .content-text {
  background: rgba(240, 240, 240, 0.92);
  padding: 10px 16px;
  border-radius: 16px;
  border-bottom-left-radius: 4px;
  color: #333;
  font-size: 15px;
  line-height: 1.6;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.message-user .content-text {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border-bottom-right-radius: 4px;
  padding: 10px 16px;
  border-radius: 16px;
  font-size: 15px;
  line-height: 1.6;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.loading-text {
  color: #999;
  font-style: italic;
  padding: 10px 0;
}

/* 底部  */
.wrapper-foot {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 12px 30px;
  margin: 10px auto;
  min-height: 80px;
  width: 700px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(4px);
  gap: 12px;
  flex-shrink: 0;
  position: relative;
  z-index: 2;
}

.deep-think-capsule {
  cursor: pointer;
  user-select: none;
  padding: 7px 14px;
  border-radius: 999px;
  background-color: #e8e8e8;
  font-size: 14px;
  color: #555;
  transition: all 0.24s ease;
  margin-top: 8px;
}

.deep-think-capsule input {
  display: none;
}

.deep-think-capsule:hover {
  opacity: 0.84;
}

.deep-think-capsule:has(input:checked) {
  background: linear-gradient(to right, #FABAF6, #F678B4);
  color: #fff;
}

.wrapper-foot .input {
  flex: 1;
  min-height: 44px;
  padding: 10px 16px;
  font-size: 16px;
  font-family: 'PingFang SC', 'Microsoft YaHei', -apple-system, BlinkMacSystemFont, sans-serif;
  line-height: 1.6;
  border: none;
  border-radius: 12px;
  background-color: rgba(245, 245, 245, 0.9);
  outline: none;
  resize: none;
  overflow-y: hidden;
  transition: background 0.2s, box-shadow 0.2s;
  box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.04);
}

.wrapper-foot .input:focus {
  background-color: rgba(240, 240, 240, 0.95);
  box-shadow: inset 0 1px 4px rgba(0, 0, 0, 0.08);
}

.wrapper-foot .input::placeholder {
  color: #aaa;
  font-size: 15px;
  letter-spacing: 0.3px;
}

.wrapper-foot .input::-webkit-scrollbar {
  width: 4px;
}

.wrapper-foot .input::-webkit-scrollbar-thumb {
  background: #ccc;
  border-radius: 4px;
}

.wrapper-foot .btn {
  height: 45px;
  width: 80px;
  border-radius: 10px;
  border: none;
  outline: none;
  color: white;
  font-size: 14px;
  letter-spacing: 3px;
  background: linear-gradient(to right, #FABAF6, #F678B4);
  transition: opacity 0.2s;
  flex-shrink: 0;
  margin-top: 4px;
}

.wrapper-foot .btn:hover:not(:disabled) {
  opacity: 0.85;
}

.wrapper-foot .btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

/*  大图模态框  */
.big-avatar-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 9999;
  animation: fadeIn 0.2s ease;
}

.big-avatar-container {
  position: relative;
  max-width: 80%;
  max-height: 80%;
  background: white;
  border-radius: 16px;
  padding: 12px;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.5);
}

.big-avatar-img {
  display: block;
  max-width: 100%;
  max-height: 80vh;
  width: auto;
  height: auto;
  border-radius: 12px;
  object-fit: contain;
}

.close-big-avatar {
  position: absolute;
  top: -12px;
  right: -12px;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: #333;
  color: white;
  font-size: 20px;
  cursor: pointer;
  line-height: 36px;
  text-align: center;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  transition: background 0.2s;
}

.close-big-avatar:hover {
  background: #555;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: scale(0.9);
  }

  to {
    opacity: 1;
    transform: scale(1);
  }
}

@media screen and (max-width: 768px) {
  .wrapper {
    width: 100%;
    height: 100vh;
    height: 100dvh;
    margin: 0;
    border-radius: 0;
    box-shadow: none;
  }

  .wrapper-head {
    padding: 0 12px;
    height: 56px;
  }

  .head-left .name {
    font-size: 16px;
  }

  .menu-btn {
    width: 34px;
    height: 34px;
  }

  .menu-btn svg {
    width: 20px;
    height: 20px;
  }

  .clear-btn {
    width: 34px;
    height: 34px;
  }

  .clear-btn svg {
    width: 17px;
    height: 17px;
  }

  .avatar-ai {
    width: 40px;
    height: 40px;
  }

  .wrapper-body {
    flex: 1;
    overflow: hidden;
  }

  .message-list {
    gap: 12px;
    margin: 8px 12px;
  }

  .avatar {
    width: 32px;
    height: 32px;
  }

  .message-content {
    max-width: 80%;
  }

  .reasoning-block {
    font-size: 13px;
    padding: 8px 12px;
  }

  .message-ai .content-text,
  .message-user .content-text {
    font-size: 14px;
    padding: 8px 12px;
    line-height: 1.5;
  }

  /*  底部  */
  .wrapper-foot {
    width: 100%;
    padding: 8px 12px;
    margin: 0;
    min-height: 56px;
    border-radius: 0;
    background: rgba(255, 255, 255, 0.92);
    gap: 8px;
    border-top: 1px solid rgba(0, 0, 0, 0.06);
    align-items: center;
  }

  .deep-think-capsule {
    padding: 5px 10px;
    font-size: 12px;
    margin-top: 0;
  }

  .wrapper-foot .input {
    min-height: 36px;
    padding: 6px 12px;
    font-size: 15px;
    border-radius: 16px;
  }

  .wrapper-foot .btn {
    height: 36px;
    width: 56px;
    font-size: 13px;
    letter-spacing: 2px;
    border-radius: 16px;
    margin-top: 0;
  }

  /*  抽屉  */
  .drawer {
    width: 85vw;
    max-width: 300px;
    left: -85vw;
    border-radius: 0 12px 12px 0;
  }

  .drawer.open {
    left: 0;
  }

  .drawer-header {
    padding: 16px 18px;
    font-size: 16px;
  }

  .drawer-close {
    font-size: 22px;
    padding: 0 4px;
  }

  .drawer-body {
    padding: 16px 18px;
  }

  /* NSFW 开关 - 手机版 */
  .nsfw-toggle-row {
    padding: 10px 14px;
    flex-wrap: wrap;
    gap: 6px;
  }

  .nsfw-toggle .toggle-slider {
    width: 38px;
    height: 20px;
  }

  .nsfw-toggle .toggle-slider::after {
    width: 14px;
    height: 14px;
    top: 3px;
    left: 3px;
  }

  .nsfw-toggle input:checked+.toggle-slider::after {
    transform: translateX(18px);
  }

  .nsfw-toggle .toggle-label {
    font-size: 13px;
  }

  .nsfw-hint {
    font-size: 11px;
  }

  /* NSFW 人物设定 - 手机版 */
  .nsfw-prompt-section {
    padding: 12px;
  }

  .custom-prompt-textarea {
    font-size: 12px;
    min-height: 60px;
  }

  /* 设置分组 - 手机版 */
  .setting-divider {
    font-size: 13px;
    margin: 16px 0 10px 0;
  }

  .setting-group {
    margin-bottom: 12px;
  }

  .setting-group label {
    font-size: 13px;
  }

  .setting-group input,
  .setting-group select {
    padding: 6px 10px;
    font-size: 13px;
    border-radius: 6px;
  }

  .setting-group .hint {
    font-size: 11px;
  }

  /* 头像上传 - 手机版 */
  .avatar-upload-row {
    flex-wrap: wrap;
    gap: 10px;
  }

  .avatar-preview {
    width: 44px;
    height: 44px;
  }

  .bg-preview {
    width: 60px;
    height: 44px;
  }

  .avatar-btn {
    font-size: 12px;
    padding: 3px 10px;
  }

  /* 大图模态框 - 手机版 */
  .big-avatar-container {
    max-width: 92%;
    max-height: 85%;
    padding: 8px;
  }

  .big-avatar-img {
    max-height: 70vh;
  }

  .close-big-avatar {
    width: 30px;
    height: 30px;
    font-size: 16px;
    line-height: 30px;
    top: -10px;
    right: -10px;
  }
}
</style>
