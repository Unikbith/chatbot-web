<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import { fetchStream, readStream } from '@/utils/resAi';
// 图标需要手动导入
import { Menu, Delete, Plus, ChatDotSquare } from '@element-plus/icons-vue';

import katoImage from '@/assets/images/加藤惠.jpg';
import natsumeImage from '@/assets/images/夏目贵志.jpg';

const GREETING = '你好呀~';
const TOKEN_OPTIONS = [150, 300, 500, 1000];

//聊天消息 
const createMessage = (role, content = '') => ({ role, content, reasoning: '', showReasoning: false });

const messages = ref([
  createMessage('assistant', GREETING)
]);
const inputText = ref('');
const loading = ref(false);
const messageList = ref(null);
const deepThink = ref(false);
let abortController = null;

//头像与背景
const aiAvatar = ref(katoImage);
const userAvatar = ref(natsumeImage);
const wrapperBg = ref('');

const coverStyle = (bg, repeat = false) =>
  bg
    ? {
      backgroundImage: `url(${bg})`,
      backgroundSize: 'cover',
      backgroundPosition: 'center',
      ...(repeat ? { backgroundRepeat: 'no-repeat' } : {}),
    }
    : {};

const bubbleOpacityStyle = computed(() => ({
  '--bubble-opacity': (settings.value.bubbleOpacity ?? 90) / 100,
}));

//设置抽屉
const drawerVisible = ref(false);
const openDrawer = () => { drawerVisible.value = true; };

const settings = ref({
  apiKey: '',
  model: '',
  maxTokens: 150,
  aiAvatarData: null,
  userAvatarData: null,
  backgroundData: null,
  bubbleOpacity: 90,
  promptMode: 'default',
  customPrompt: '',
  frequencyPenalty: 0.1, 
  presencePenalty: 0.1,  
});

// 多人物对话存档管理
const STORAGE_KEY_INDEX = 'chat_conversations_index';

const conversations = ref([]);   // [{ id, title, timestamp }]
const currentConvId = ref(null);

// 生成唯一ID（时间戳+随机数）
const generateId = () => {
  return Date.now().toString(36) + '-' + Math.random().toString(36).substring(2, 8);
};

// 获取对话的标题（取第一条用户消息或第一条assistant消息）
const getConversationTitle = (msgs) => {
  if (!msgs || msgs.length === 0) return '新对话';
  const userMsg = msgs.find(m => m.role === 'user');
  if (userMsg) {
    const text = userMsg.content.replace(/<[^>]+>/g, '').trim();
    return text.length > 20 ? text.substring(0, 20) + '...' : text;
  }
  return '新对话';
};

// 加载对话索引列表
const loadConversationList = () => {
  try {
    const data = localStorage.getItem(STORAGE_KEY_INDEX);
    if (data) {
      conversations.value = JSON.parse(data);
    }
  } catch (e) {
    console.warn('加载对话列表失败', e);
    conversations.value = [];
  }
};

// 保存对话索引列表
const saveConversationList = () => {
  try {
    localStorage.setItem(STORAGE_KEY_INDEX, JSON.stringify(conversations.value));
  } catch (e) {
    console.warn('保存对话列表失败', e);
  }
};

// 保存当前对话到 localStorage
const saveMessages = () => {
  if (!currentConvId.value) return;
  const key = 'chat_history_' + currentConvId.value;
  try {
    localStorage.setItem(key, JSON.stringify(messages.value));
    // 更新对话标题
    const conv = conversations.value.find(c => c.id === currentConvId.value);
    if (conv) {
      conv.title = getConversationTitle(messages.value);
      conv.timestamp = Date.now();
      saveConversationList();
    }
  } catch (e) {
    console.warn('保存对话失败', e);
  }
};

// 加载指定对话
const loadMessages = (convId) => {
  if (!convId) return;
  const key = 'chat_history_' + convId;
  try {
    const saved = localStorage.getItem(key);
    if (saved) {
      messages.value = JSON.parse(saved).map((msg) => ({
        ...msg,
        reasoning: msg.reasoning || '',
        showReasoning: false,
      }));
      return;
    }
  } catch (e) {
    console.warn('历史记录解析失败', e);
  }
  // 没有存档则使用欢迎消息
  messages.value = [createMessage('assistant', GREETING)];
};

// 切换对话
const switchConversation = (convId) => {
  if (convId === currentConvId.value) return;
  // 先保存当前对话
  saveMessages();
  currentConvId.value = convId;
  loadMessages(convId);
  scrollToBottom();
};

// 新建对话
const newConversation = () => {
  // 保存当前对话
  saveMessages();
  const id = generateId();
  const conv = {
    id,
    title: '新对话',
    timestamp: Date.now(),
  };
  conversations.value.unshift(conv);
  saveConversationList();
  currentConvId.value = id;
  messages.value = [createMessage('assistant', GREETING)];
  scrollToBottom();
};

// 删除对话存档
const deleteConversation = (convId, event) => {
  if (event) event.stopPropagation();
  // 从 localStorage 删除数据
  const key = 'chat_history_' + convId;
  try {
    localStorage.removeItem(key);
  } catch (e) {
    console.warn('删除对话数据失败', e);
  }
  // 从列表中移除
  const idx = conversations.value.findIndex(c => c.id === convId);
  if (idx !== -1) {
    conversations.value.splice(idx, 1);
    saveConversationList();
  }
  // 如果删除的是当前对话，切换到第一个剩余对话
  if (convId === currentConvId.value) {
    if (conversations.value.length > 0) {
      switchConversation(conversations.value[0].id);
    } else {
      currentConvId.value = null;
      messages.value = [createMessage('assistant', GREETING)];
    }
  }
};

// 清空当前聊天（保留在存档中）
const handleClearChat = () => {
  if (loading.value) abortRequest();
  messages.value = [createMessage('assistant', GREETING)];
  inputText.value = '';
  // 不删除存档，只清空消息并保存
  saveMessages();
  scrollToBottom();
};

const loadSettings = () => {
  try {
    const parsed = JSON.parse(localStorage.getItem('ai_chat_settings'));
    if (!parsed) return;
    settings.value = { ...settings.value, ...parsed };
    aiAvatar.value = parsed.aiAvatarData || katoImage;
    userAvatar.value = parsed.userAvatarData || natsumeImage;
    wrapperBg.value = parsed.backgroundData || '';
  } catch (e) {
    console.warn('加载设置失败', e);
  }
};

const saveSettings = () => {
  try {
    localStorage.setItem('ai_chat_settings', JSON.stringify(settings.value));
  } catch (e) {
    console.warn('保存设置失败', e);
  }
};
watch(settings, saveSettings, { deep: true });

//图片上传
const aiFileInput = ref(null);
const userFileInput = ref(null);
const bgFileInput = ref(null);

const UPLOAD_CONFIG = {
  aiAvatar: { input: aiFileInput, settingKey: 'aiAvatarData', preview: aiAvatar, fallback: katoImage },
  userAvatar: { input: userFileInput, settingKey: 'userAvatarData', preview: userAvatar, fallback: natsumeImage },
  bg: { input: bgFileInput, settingKey: 'backgroundData', preview: wrapperBg, fallback: '' },
};

const triggerUpload = (key) => UPLOAD_CONFIG[key].input.value?.click();

const handleImageUpload = (event, key) => {
  const { input, settingKey, preview } = UPLOAD_CONFIG[key];
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    const dataUrl = e.target.result;
    settings.value[settingKey] = dataUrl;
    preview.value = dataUrl;
    input.value.value = '';
  };
  reader.readAsDataURL(file);
};

const resetImage = (key) => {
  const { settingKey, preview, fallback } = UPLOAD_CONFIG[key];
  settings.value[settingKey] = null;
  preview.value = fallback;
  saveSettings();
};

//大图预览
const showBigAvatar = ref(false);
const bigAvatarSrc = ref('');
const openBigAvatar = (src) => { bigAvatarSrc.value = src; showBigAvatar.value = true; };
const closeBigAvatar = () => { showBigAvatar.value = false; };

//滚动到底部
const scrollToBottom = async () => {
  await nextTick();
  if (!messageList.value) return;
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      const wrap = messageList.value.wrapRef;
      if (wrap) messageList.value.setScrollTop(wrap.scrollHeight);
    });
  });
};

//请求中止
const abortRequest = () => {
  abortController?.abort();
  abortController = null;
  loading.value = false;
};

//发送消息
const handleSend = async () => {
  if (loading.value) { abortRequest(); return; }

  const text = inputText.value.trim();
  if (!text) return;

  messages.value.push(createMessage('user', text));
  inputText.value = '';
  /* await scrollToBottom(); */

  const aiIndex = messages.value.length;
  messages.value.push(createMessage('assistant'));
  /*   await scrollToBottom(); */

  loading.value = true;
  abortController = new AbortController();

  try {
    const s = settings.value;
    const requestBody = {
      messages: messages.value.slice(0, -1).map(({ role, content }) => ({ role, content })),
      deep_think: deepThink.value,
      prompt_mode: s.promptMode,
      custom_prompt: s.promptMode === 'custom' ? s.customPrompt : '',
      max_tokens: s.maxTokens,
      frequency_penalty: s.frequencyPenalty,   // 新增
      presence_penalty: s.presencePenalty,     // 新增
    };
    if (s.apiKey.trim()) requestBody.api_key = s.apiKey.trim();
    if (s.model.trim()) requestBody.model = s.model.trim();

    const response = await fetchStream('/api/chat', requestBody, { signal: abortController.signal });
    await readStream(response, (data) => {
      const { reasoning_content: reasoning = '', content = '' } = data.choices?.[0]?.delta || {};
      if (reasoning) messages.value[aiIndex].reasoning += reasoning;
      if (content) messages.value[aiIndex].content += content;
      /* if (reasoning || content) scrollToBottom(); */
    });
  } catch (error) {
    if (error.name === 'AbortError') {
      messages.value[aiIndex].content += '（已中止）';
    } else {
      console.error('发送失败', error);
      messages.value[aiIndex].content = `出错了：${error.message || '网络异常'}`;
    }
  } finally {
    abortController = null;
    loading.value = false;
    /* await scrollToBottom(); */
  }
};

//回车发送
const handleKeydown = (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    handleSend();
  }
};

let saveTimer = null;
watch(messages, () => {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveMessages, 500);
}, { deep: true });


onMounted(async () => {
  loadSettings();
  loadConversationList();
  // 如果有存档，加载第一个；否则新建一个
  if (conversations.value.length > 0) {
    // 按时间戳倒序，取最新的
    conversations.value.sort((a, b) => b.timestamp - a.timestamp);
    currentConvId.value = conversations.value[0].id;
    loadMessages(currentConvId.value);
  } else {
    newConversation();
  }
  await scrollToBottom();
});

onUnmounted(abortRequest);
</script>

<template>
  <div class="wrapper" :style="[coverStyle(wrapperBg, true), bubbleOpacityStyle]">
    <!-- 头部 -->
    <div class="wrapper-head">
      <div class="head-left">
        <el-button class="menu-btn" circle aria-label="打开设置" @click="openDrawer">
          <el-icon>
            <Menu />
          </el-icon>
        </el-button>
        <div class="name">贤妻加藤惠</div>
      </div>
      <div class="header-actions">
        <el-button class="new-btn" circle title="新建对话" @click="newConversation">
          <el-icon>
            <Plus />
          </el-icon>
        </el-button>
        <el-button class="clear-btn" circle title="清空当前对话" @click="handleClearChat">
          <el-icon>
            <Delete />
          </el-icon>
        </el-button>
        <el-avatar :size="60" :src="aiAvatar" alt="加藤惠" class="avatar-ai" @click="openBigAvatar(aiAvatar)" />
      </div>
    </div>

    <!-- 设置抽屉 -->
    <el-drawer v-model="drawerVisible" title="设置" direction="ltr" size="360px" class="settings-drawer">
      <!-- 对话历史列表 -->
      <div class="conv-section">
        <div class="conv-section-header">
          <span class="conv-section-title">人物对话</span>
          <el-button class="conv-new-btn" size="small" @click="newConversation(); drawerVisible = false;">
            <el-icon>
              <Plus />
            </el-icon> 新建
          </el-button>
        </div>
        <div class="conv-list" v-if="conversations.length > 0">
          <div v-for="conv in conversations" :key="conv.id" class="conv-item"
            :class="{ active: conv.id === currentConvId }" @click="switchConversation(conv.id); drawerVisible = false;">
            <el-icon class="conv-icon">
              <ChatDotSquare />
            </el-icon>
            <span class="conv-title">{{ conv.title }}</span>
            <el-button class="conv-del-btn" size="small" circle @click="deleteConversation(conv.id, $event)">
              <el-icon>
                <Delete />
              </el-icon>
            </el-button>
          </div>
        </div>
        <div class="conv-empty" v-else>
          暂无对话存档
        </div>
        <div class="conv-divider"></div>
      </div>

      <div class="prompt-section">
        <div class="setting-group">
          <label>人物设定</label>
          <el-select v-model="settings.promptMode" class="setting-select">
            <el-option label="默认（加藤惠）" value="default" />
            <el-option label="自定义" value="custom" />
          </el-select>
          <small class="hint">"自定义"可在下方输入你自己的提示词</small>
        </div>
        <div v-if="settings.promptMode === 'custom'" class="setting-group">
          <label>自定义人物设定提示词</label>
          <el-input v-model="settings.customPrompt" type="textarea" :autosize="{ minRows: 4, maxRows: 12 }"
            class="setting-input" placeholder="在此输入你的人物设定提示词..." />
        </div>
      </div>

      <div class="setting-divider">基础设置</div>

      <div class="setting-group">
        <label>API Key</label>
        <el-input v-model="settings.apiKey" type="password" show-password class="setting-input"
          placeholder="请填入你的API key" />
      </div>
      <div class="setting-group">
        <label>模型</label>
        <el-input v-model="settings.model" class="setting-input" placeholder="例如 deepseek-chat" />
        <small class="hint">请填入你选择的模型</small>
      </div>
      <div class="setting-group">
        <label>回复长度（挡位）</label>
        <el-select v-model="settings.maxTokens" class="setting-select">
          <el-option v-for="val in TOKEN_OPTIONS" :key="val" :label="`${val} 字`" :value="val" />
        </el-select>
        <small class="hint">当前选择：{{ settings.maxTokens }} 字 </small>
      </div>
      <div class="setting-group">
        <label>消息框透明度</label>
        <el-slider v-model="settings.bubbleOpacity" :min="20" :max="100" :show-tooltip="false" class="setting-slider" />
        <small class="hint">调低透明度可透出背景图（当前 {{ settings.bubbleOpacity }}%）</small>
      </div>
      <div class="setting-group">
        <label>频率惩罚（减少重复词）</label>
        <el-slider v-model="settings.frequencyPenalty" :min="0" :max="1" :step="0.1" :show-tooltip="false"
          class="setting-slider" />
        <small class="hint">当前：{{ settings.frequencyPenalty }}（值越高越避免重复）</small>
      </div>
      <div class="setting-group">
        <label>存在惩罚（鼓励新话题）</label>
        <el-slider v-model="settings.presencePenalty" :min="0" :max="1" :step="0.1" :show-tooltip="false"
          class="setting-slider" />
        <small class="hint">当前：{{ settings.presencePenalty }}（值越高越倾向新内容）</small>
      </div>

      <div class="setting-divider">头像设置</div>

      <div class="setting-group">
        <label>AI 头像</label>
        <div class="avatar-upload-row">
          <el-avatar :size="56" :src="aiAvatar" class="avatar-preview" />
          <div class="avatar-actions">
            <input ref="aiFileInput" type="file" accept="image/*" style="display:none"
              @change="(e) => handleImageUpload(e, 'aiAvatar')" />
            <el-button class="avatar-btn" @click="triggerUpload('aiAvatar')">上传</el-button>
            <el-button class="avatar-btn reset" @click="resetImage('aiAvatar')">重置</el-button>
          </div>
        </div>
      </div>

      <div class="setting-group">
        <label>用户头像</label>
        <div class="avatar-upload-row">
          <el-avatar :size="56" :src="userAvatar" class="avatar-preview" />
          <div class="avatar-actions">
            <input ref="userFileInput" type="file" accept="image/*" style="display:none"
              @change="(e) => handleImageUpload(e, 'userAvatar')" />
            <el-button class="avatar-btn" @click="triggerUpload('userAvatar')">上传</el-button>
            <el-button class="avatar-btn reset" @click="resetImage('userAvatar')">重置</el-button>
          </div>
        </div>
      </div>

      <div class="setting-divider">背景设置</div>

      <div class="setting-group">
        <label>聊天背景图片</label>
        <div class="avatar-upload-row">
          <div class="bg-preview" :style="coverStyle(wrapperBg)">{{ wrapperBg ? '' : '无背景' }}</div>
          <div class="avatar-actions">
            <input ref="bgFileInput" type="file" accept="image/*" style="display:none"
              @change="(e) => handleImageUpload(e, 'bg')" />
            <el-button class="avatar-btn" @click="triggerUpload('bg')">上传</el-button>
            <el-button class="avatar-btn reset" @click="resetImage('bg')">✕ 移除</el-button>
          </div>
        </div>
        <small class="hint">上传图片将作为聊天区域背景</small>
      </div>
    </el-drawer>

    <!-- 消息列表 -->
    <div class="wrapper-body">
      <el-scrollbar ref="messageList" class="message-scrollbar">
        <ul class="message-list">
          <li v-for="(item, index) in messages" :key="index"
            :class="item.role === 'assistant' ? 'message-ai' : 'message-user'">
            <el-avatar :size="42" :src="item.role === 'assistant' ? aiAvatar : userAvatar" class="avatar"
              @click="openBigAvatar(item.role === 'assistant' ? aiAvatar : userAvatar)" />
            <div class="message-content">
              <div v-if="item.role === 'assistant' && item.reasoning" class="reasoning-wrapper">
                <div class="reasoning-toggle" @click="item.showReasoning = !item.showReasoning">
                  <span>{{ item.showReasoning ? '收起思考' : '查看思考' }}</span>
                  <span class="arrow">{{ item.showReasoning ? '▲' : '▼' }}</span>
                </div>
                <div v-show="item.showReasoning" class="reasoning-block">
                  <div class="reasoning-label">思考过程</div>
                  <div class="reasoning-text">{{ item.reasoning }}</div>
                </div>
              </div>
              <div v-if="item.content" class="content-text" v-html="item.content"></div>
              <div v-if="item.role === 'assistant' && !item.content && !item.reasoning" class="loading-text">
                正在输入...
              </div>
            </div>
          </li>
        </ul>
      </el-scrollbar>
    </div>

    <!-- 底部输入 -->
    <div class="wrapper-foot">
      <el-switch v-model="deepThink" active-text="深度思考" class="deep-think-switch" />
      <el-input v-model="inputText" type="textarea" class="input" placeholder="说些什么吧..." resize="none"
        :autosize="{ minRows: 1, maxRows: 5 }" @keydown="handleKeydown" />
      <el-button class="btn" @click="handleSend">{{ loading ? '停止' : '发送' }}</el-button>
    </div>

    <!-- 大图模态框 -->
    <el-dialog v-model="showBigAvatar" class="big-avatar-dialog" modal-class="big-avatar-overlay" :show-close="false"
      width="auto" align-center @close="closeBigAvatar">
      <img :src="bigAvatarSrc" alt="大图" class="big-avatar-img" @click="closeBigAvatar" />
    </el-dialog>
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

.wrapper-head .menu-btn,
.wrapper-head .clear-btn {
  width: 40px;
  height: 40px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
  color: #fff;
  font-size: 20px;
  flex-shrink: 0;
}

.wrapper-head .menu-btn:hover,
.wrapper-head .clear-btn:hover {
  background: rgba(255, 255, 255, 0.35);
  color: #fff;
}

.wrapper-head .menu-btn:active,
.wrapper-head .clear-btn:active {
  transform: scale(0.95);
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

.wrapper-head .new-btn {
  width: 40px;
  height: 40px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
  color: #fff;
  font-size: 20px;
  flex-shrink: 0;
}

.wrapper-head .new-btn:hover {
  background: rgba(255, 255, 255, 0.35);
  color: #fff;
}

.wrapper-head .new-btn:active {
  transform: scale(0.95);
}

.avatar-ai {
  cursor: pointer;
  transition: transform 0.2s;
  flex-shrink: 0;
}

.avatar-ai:hover {
  transform: scale(1.05);
}

.conv-section {
  margin-bottom: 16px;
}

.conv-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.conv-section-title {
  font-size: 14px;
  font-weight: 600;
  color: #764ba2;
}

.conv-new-btn {
  --el-button-bg-color: #764ba2;
  --el-button-border-color: #764ba2;
  --el-button-text-color: #fff;
  --el-button-hover-bg-color: #8b5cf6;
  --el-button-hover-border-color: #8b5cf6;
  --el-button-hover-text-color: #fff;
  height: 28px;
  font-size: 12px;
}

.conv-list {
  max-height: 240px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.conv-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  cursor: pointer;
  background: #f8f8f8;
  transition: background 0.2s;
  border: 1px solid transparent;
}

.conv-item:hover {
  background: #f0e6ff;
  border-color: #e0d0f0;
}

.conv-item.active {
  background: #f0e6ff;
  border-color: #be5cee;
}

.conv-icon {
  color: #764ba2;
  font-size: 16px;
  flex-shrink: 0;
}

.conv-title {
  flex: 1;
  font-size: 13px;
  color: #444;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.conv-del-btn {
  width: 24px;
  height: 24px;
  flex-shrink: 0;
  --el-button-bg-color: transparent;
  --el-button-border-color: transparent;
  --el-button-text-color: #ccc;
  --el-button-hover-bg-color: #ffe0e0;
  --el-button-hover-border-color: #ff6b6b;
  --el-button-hover-text-color: #ff6b6b;
  opacity: 0;
  transition: opacity 0.2s;
}

.conv-item:hover .conv-del-btn {
  opacity: 1;
}

.conv-empty {
  text-align: center;
  color: #bbb;
  font-size: 13px;
  padding: 16px 0;
}

.conv-divider {
  height: 1px;
  background: #f0e6ff;
  margin: 16px 0;
}

.prompt-section {
  background: #f8f8f8;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 16px;
  border: 1px solid #eee;
}

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



.setting-input,
.setting-select,
.setting-slider {
  width: 100%;
}

.avatar-upload-row {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 4px;
}

.avatar-preview {
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
  height: 28px;
  padding: 0 12px;
  font-size: 13px;
  --el-button-bg-color: #f5f5f5;
  --el-button-border-color: #ddd;
  --el-button-text-color: #606266;
  --el-button-hover-bg-color: #e8e8e8;
  --el-button-hover-border-color: #ddd;
  --el-button-hover-text-color: #606266;
}

.avatar-btn.reset {
  --el-button-border-color: #ff6b6b;
  --el-button-text-color: #ff6b6b;
  --el-button-hover-border-color: #ff6b6b;
  --el-button-hover-text-color: #ff6b6b;
  --el-button-hover-bg-color: #ffe0e0;
  --el-button-active-border-color: #ff6b6b;
  --el-button-active-text-color: #ff6b6b;
}

.wrapper-body {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
  position: relative;
  z-index: 1;
}

.message-scrollbar {
  height: 100%;
  width: 100%;
}

.message-scrollbar :deep(.el-scrollbar__bar) {
  display: none;
}

.message-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 10px;
  margin: 0;
  list-style: none;
}

.avatar {
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
  background: rgba(240, 240, 240, var(--bubble-opacity, 0.92));
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
  background: rgba(240, 240, 240, var(--bubble-opacity, 0.92));
  padding: 10px 16px;
  border-radius: 16px;
  border-bottom-left-radius: 4px;
  color: #333;
  font-size: 15px;
  line-height: 1.6;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.message-user .content-text {
  background: linear-gradient(135deg, rgba(102, 126, 234, var(--bubble-opacity, 0.92)) 0%, rgba(118, 75, 162, var(--bubble-opacity, 0.92)) 100%);
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

.content-text :deep(img) {
  max-width: 100%;
  border-radius: 6px;
}

.content-text :deep(pre) {
  background: rgba(0, 0, 0, 0.06);
  padding: 10px 14px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 8px 0;
}

.content-text :deep(code) {
  background: rgba(0, 0, 0, 0.06);
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 0.9em;
}

.content-text :deep(pre code) {
  background: none;
  padding: 0;
}

.content-text :deep(a) {
  color: #764ba2;
}

.message-user .content-text :deep(a) {
  color: #fff;
  text-decoration: underline;
}

.wrapper-foot {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 12px 30px;
  margin: 10px auto;
  min-height: 80px;
  width: 700px;
  border-radius: 12px;
  background: rgba(255, 255, 255, var(--bubble-opacity, 0.92));
  backdrop-filter: blur(4px);
  gap: 12px;
  flex-shrink: 0;
  position: relative;
  z-index: 2;
}

.deep-think-switch {
  --el-switch-on-color: #F678B4;
  margin-top: 8px;
  flex-shrink: 0;
}

.wrapper-foot .input {
  flex: 1;
  min-width: 0;
}

.wrapper-foot :deep(.el-textarea__inner) {
  min-height: 44px;
  padding: 10px 16px;
  font-size: 16px;
  font-family: 'PingFang SC', 'Microsoft YaHei', -apple-system, BlinkMacSystemFont, sans-serif;
  line-height: 1.6;
  border: none;
  border-radius: 12px;
  background-color: rgba(245, 245, 245, 0.9);
  outline: none;
  box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.04);
  transition: background 0.2s, box-shadow 0.2s;
}

.wrapper-foot :deep(.el-textarea__inner:focus) {
  background-color: rgba(240, 240, 240, 0.95);
  box-shadow: inset 0 1px 4px rgba(0, 0, 0, 0.08);
}

.wrapper-foot :deep(.el-textarea__inner::placeholder) {
  color: #aaa;
  font-size: 15px;
  letter-spacing: 0.3px;
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
  color: #fff;
}

.wrapper-foot .btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.big-avatar-dialog {
  background: #fff;
  border-radius: 16px;
  padding: 12px;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.5);
  overflow: hidden;
}

.big-avatar-dialog :deep(.el-dialog__header) {
  display: none;
}

.big-avatar-dialog :deep(.el-dialog__body) {
  padding: 0;
}

.big-avatar-img {
  display: block;
  max-width: 80vw;
  max-height: 80vh;
  width: auto;
  height: auto;
  border-radius: 12px;
  object-fit: contain;
  cursor: zoom-out;
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

  .wrapper-head .menu-btn,
  .wrapper-head .clear-btn,
  .wrapper-head .new-btn {
    width: 34px;
    height: 34px;
    font-size: 17px;
  }

  .avatar-ai {
    --el-avatar-size: 40px !important;
  }

  .conv-section-title {
    font-size: 13px;
  }

  .conv-list {
    max-height: 180px;
  }

  .conv-item {
    padding: 6px 10px;
  }

  .conv-title {
    font-size: 12px;
  }

  .conv-del-btn {
    opacity: 1;
  }

  .wrapper-body {
    flex: 1;
    overflow: hidden;
  }

  .message-list {
    gap: 12px;
    padding: 8px 12px;
  }

  .avatar {
    --el-avatar-size: 32px !important;
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

  .deep-think-switch {
    margin-top: 0;
  }

  .wrapper-foot :deep(.el-textarea__inner) {
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

  .prompt-section {
    padding: 12px;
  }

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

  .setting-group .hint {
    font-size: 11px;
  }

  .avatar-upload-row {
    flex-wrap: wrap;
    gap: 10px;
  }

  .avatar-preview {
    --el-avatar-size: 44px !important;
  }

  .bg-preview {
    width: 60px;
    height: 44px;
  }

  .avatar-btn {
    font-size: 12px;
    padding: 0 10px;
  }

  .big-avatar-img {
    max-width: 92vw;
    max-height: 85vh;
  }
}
</style>

<style>
.settings-drawer .el-drawer__header {
  margin: 0;
  padding: 20px 24px;
  font-size: 18px;
  font-weight: bold;
  color: #333;
  border-bottom: 1px solid #eee;
}

.settings-drawer .el-drawer__body {
  padding: 24px;
}

@media screen and (max-width: 768px) {
  .settings-drawer.el-drawer {
    width: 85vw !important;
    max-width: 300px;
  }

  .settings-drawer .el-drawer__header {
    padding: 16px 18px;
    font-size: 16px;
  }

  .settings-drawer .el-drawer__body {
    padding: 16px 18px;
  }
}

.big-avatar-overlay {
  background: rgba(0, 0, 0, 0.7);
}
</style>
