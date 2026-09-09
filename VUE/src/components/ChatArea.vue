<script setup>
import { ref, computed, nextTick, watch, onMounted, onUnmounted } from 'vue';
import { ElMessage, ElInput } from 'element-plus';
import { 
  Setting, RefreshLeft, Lightning, 
  Bell, CircleClose, Upload, Edit, MagicStick, Picture, Notebook
} from '@element-plus/icons-vue';
import { readStream, chatApi, audioApi, imageApi, providersApi, conversationApi } from '@/utils/resAi';
import auth from '@/utils/auth';
import { t } from '../i18n';

import VoiceInput from '@/components/VoiceInput.vue';
import ImageUpload from '@/components/ImageUpload.vue';
import PromptToolPanel from '@/components/PromptToolPanel.vue';

const props = defineProps({
  conversationId: {
    type: [Number, String],
    default: null
  },
  conversationTitle: {
    type: String,
    default: '新对话'
  },
  providerId: {
    type: [Number, String],
    default: null
  },
  systemPrompt: {
    type: String,
    default: ''
  },
  temperature: {
    type: Number,
    default: 0.7
  },
  user: { type: Object, default: null },
  userAvatar: { type: String, default: '' },
  aiAvatar: { type: String, default: '' },
  messageOpacity: { type: Number, default: 0.9 },
  settings: { type: Object, default: null },
  isFreeApi: { type: Boolean, default: false },
  autoPlayVoice: { type: Boolean, default: false }
});

const emit = defineEmits([
  'openSettings', 
  'openProvider',
  'openConversationSettings',
  'titleChange', 
  'newChat',
  'updateConversation',
  'conversationCreated'
]);

const opacityVal = computed(() => {
  const v = Number(props.messageOpacity)
  return isNaN(v) ? 0.9 : Math.min(1, Math.max(0.05, v))
});

const greetingText = () => t('你好！有什么可以帮你的吗？', 'Hello! How can I help you?');

// 消息
const createMessage = (role, content = '', imageUrl = null) => ({ 
  role, content, reasoning: '', showReasoning: false, imageUrl 
});

const messages = ref([]);
const inputText = ref('');
const loading = ref(false);
const messageListRef = ref(null);
const deepThink = ref(false);
let abortController = null;

// 图片上传
const imageUploadRef = ref(null);
const selectedImage = ref(null);
// 生图模式开关：'' 普通聊天 / 'text2img' 生图 / 'img2img' 改图（需附参考图）
const genMode = ref('');

// 语音播报
const isSpeaking = ref(false);
const speakingIndex = ref(null); // 正在播报的消息索引（用于显示「播报中」）
let audioElement = null;

// 编辑标题
const editingTitle = ref(false);
const editTitleInput = ref(null);
const tempTitle = ref('');

// 滚动到底部
const scrollToBottom = async () => {
  await nextTick();
  const wrap = messageListRef.value?.wrapRef;
  if (wrap) wrap.scrollTop = wrap.scrollHeight;
};

// 请求中止
const abortRequest = () => {
  abortController?.abort();
  abortController = null;
  loading.value = false;
  stopSpeaking();
};

// 图片选择处理
const handleImageSelected = (imageData) => {
  selectedImage.value = imageData;
};

const handleImageCleared = () => {
  selectedImage.value = null;
};

// 语音文字输入
const handleVoiceText = (text) => {
  inputText.value = text;
};

// 发送前确保存在会话：无 conversationId 时先创建，保证聊天记录落库
const ensureConversation = async () => {
  if (props.conversationId) return props.conversationId;
  try {
    const res = await conversationApi.create({
      title: t('新对话', 'New Chat'),
      provider_id: props.providerId,
      system_prompt: props.systemPrompt,
      temperature: props.temperature,
    });
    if (res.code === 200) {
      emit('conversationCreated', res.data);
      return res.data.id;
    }
  } catch (e) {
    console.error('创建对话失败', e);
  }
  return null;
};

// 发送消息
const handleSend = async () => {
  if (loading.value) { abortRequest(); return; }

  const text = inputText.value.trim();
  if (!text && !selectedImage.value) return;

  // 关键词触发：生图=文生图 / 改图=图生图（无需手动开启生图模式）
  const imgCmd = matchImageCommand(text);
  if (imgCmd) {
    if (imgCmd.mode === 'img2img' && !selectedImage.value) {
      ElMessage.warning(t('改图需要先上传/选择一张参考图片', 'Attach a reference image first to edit it'));
    }
    await handleImageGenerate(imgCmd.prompt, imgCmd.mode);
    return;
  }

  // 图片生成模式（明确选择 生图/改图）
  if (genMode.value === 'text2img') {
    await handleImageGenerate(text, 'text2img');
    return;
  }
  if (genMode.value === 'img2img') {
    if (!selectedImage.value) {
      ElMessage.warning(t('改图需要先上传/选择一张参考图片', 'Attach a reference image first to edit it'));
      return;
    }
    await handleImageGenerate(text, 'img2img');
    return;
  }

  // 如果有图片，走识图接口
  if (selectedImage.value) {
    await handleVisionChat(text || '请描述这张图片');
    return;
  }

  messages.value.push(createMessage('user', text));
  inputText.value = '';
  // 用户发送消息后立即定位到底部（AI 生成过程中不强制滚动）
  scrollToBottom();

  const aiIndex = messages.value.length;
  const aiMsg = createMessage('assistant');
  messages.value.push(aiMsg);

  loading.value = true;
  abortController = new AbortController();

  const convId = await ensureConversation();

  // 若打通了「大模型原生工具」，在系统提示中加一句图片生成约定，让模型可输出标记由前端代劳
  const llmTools = await imageLlmToolsEnabled();
  const sysPrompt = llmTools
    ? (props.systemPrompt || '') + '\n\n[系统能力-图片生成] 当用户要求生成图片时只回复一行：`生图：<英文提示词>`；要求修改/结合参考图时只回复一行：`改图：<中文修改要求>`。不要输出其它解释。'
    : props.systemPrompt;

  try {
    const requestBody = {
      messages: messages.value.slice(0, -1).map(({ role, content }) => ({ role, content })),
      deep_think: deepThink.value,
      system_prompt: sysPrompt,
      temperature: props.temperature,
      provider_id: props.providerId,
      conversation_id: convId,
    };

    const response = await chatApi.stream(requestBody, { signal: abortController.signal });
    await readStream(response, (data) => {
      const { reasoning_content: reasoning = '', content = '' } = data.choices?.[0]?.delta || {};
      if (reasoning) aiMsg.reasoning += reasoning;
      if (content) aiMsg.content += content;
    });

    // 大模型输出带生图/改图标记时，自动代为调用图片生成
    await handleLlmImageMarkers(aiMsg);

    // 自动播报 AI 回复（该对话开启时）
    if (props.autoPlayVoice && aiMsg.content && !aiMsg.imageUrl) {
      speakText(aiMsg.content, aiIndex);
    }

    // 更新对话标题（第一条用户消息）
    if (messages.value.filter(m => m.role === 'user').length === 1) {
      const title = text.length > 20 ? text.substring(0, 20) + '...' : text;
      emit('titleChange', title);
    }

  } catch (error) {
    if (error.name === 'AbortError') {
      aiMsg.content += '（已中止）';
    } else {
      console.error('发送失败', error);
      aiMsg.content = `出错了：${error.message || '网络异常'}`;
    }
  } finally {
    abortController = null;
    loading.value = false;
  }
};

// 关键词识别：返回 {mode:'text2img'|'img2img', prompt} 或 null
function matchImageCommand(raw) {
  const s = (raw || '').trim();
  if (!s) return null;
  // 文生图：生图 / 生成图片 / 画一张 ...
  const t2i = s.match(/^(?:请|帮我|给我|帮我)?\s*(生图|生成图片|直接生图|画一张|画图)\s*[：:，,.\s]*/);
  if (t2i) {
    return { mode: 'text2img', prompt: s.slice(t2i[0].length).trim() || t('生成一张图片', 'Generate an image') };
  }
  // 图生图：改图 / 图生图 / 修改图片（word 级别，仅在开头才能命中，避免误伤正文）
  const i2i = s.match(/^(?:请|帮我|给我)?\s*(改图|图生图|修改这张图|修改图片)\s*[：:，,.\s]*/);
  if (i2i) {
    return { mode: 'img2img', prompt: s.slice(i2i[0].length).trim() || t('请修改这张图', 'Edit this image') };
  }
  return null;
}

// 大模型原生工具：探测图片配置是否开启 llm_tools（缓存结果）
let llmToolsCache = null;
async function imageLlmToolsEnabled() {
  if (llmToolsCache !== null) return llmToolsCache;
  try {
    const res = await providersApi.list('image');
    const enabled = (res.data || []).find(p => p.enabled !== false);
    llmToolsCache = !!(enabled && enabled.params && enabled.params.llm_tools);
  } catch (e) {
    llmToolsCache = false;
  }
  return llmToolsCache;
}

// 从模型回复里提取「生图/改图」标记并代为调用图片生成，结果以图片形式附到该消息
async function handleLlmImageMarkers(msg) {
  if (!msg || !msg.content) return;
  const m2i = msg.content.match(/生图[:：]\s*([^\n]+)/);
  const mImg = msg.content.match(/改图[:：]\s*([^\n]+)/);
  const marker = m2i || mImg;
  if (!marker) return;
  const prompt = marker[1].trim();
  // 移除标记行，保留可读文本；且仅当第一条标记满足
  msg.content = msg.content.replace(marker[0], '');
  try {
    const res = await imageApi.generate({ prompt, references: [] });
    if (res.code === 200 && res.data?.url) {
      msg.imageUrl = res.data.url;
      if (res.data?.free) {
        ElMessage.info(t(`共享免费生图（剩余 ${res.data.remaining}/${res.data.limit} 次）`, `Shared free gen (${res.data.remaining}/${res.data.limit} left)`));
      }
      scrollToBottom();
    } else if (res.message) {
      msg.content = (msg.content + '\n' + t('图片生成失败', 'Image failed') + '：' + res.message).trim();
    }
  } catch (e) {
    msg.content = (msg.content + '\n' + t('图片生成失败', 'Image failed') + '：' + (e.message || '')).trim();
  }
}

// 图片生成（mode: 'text2img' 生图 / 'img2img' 改图）
const handleImageGenerate = async (text, mode = 'text2img') => {
  const isEdit = mode === 'img2img';
  // 仅改图需要带上参考图；生图为文生图
  const prompt = text || t('生成一张图片', 'Generate an image');
  messages.value.push(createMessage('user', prompt, isEdit ? selectedImage.value?.dataUrl || null : null));
  const refDataUrl = isEdit ? selectedImage.value?.dataUrl : null;
  inputText.value = '';
  imageUploadRef.value?.clearImage();
  scrollToBottom();

  const aiMsg = createMessage('assistant');
  messages.value.push(aiMsg);

  loading.value = true;
  abortController = new AbortController();
  try {
    const res = await imageApi.generate({
      prompt,
      references: refDataUrl ? [refDataUrl] : [],
    });
    if (res.code === 200 && res.data?.url) {
      aiMsg.imageUrl = res.data.url;
      if (res.data?.free) {
        ElMessage.info(t(`共享免费生图（剩余 ${res.data.remaining}/${res.data.limit} 次）`, `Shared free gen (${res.data.remaining}/${res.data.limit} left)`));
      }
    } else {
      aiMsg.content = `出错了：${res.message || '生成失败'}`;
    }
  } catch (error) {
    if (error.name === 'AbortError') {
      aiMsg.content += '（已中止）';
    } else {
      aiMsg.content = `出错了：${error.message || '网络异常'}`;
    }
  } finally {
    abortController = null;
    loading.value = false;
    scrollToBottom();
  }
};

// 图片大图预览（发出图片 / 生成图片均支持）
const previewVisible = ref(false);
const previewUrl = ref('');
const previewImage = (url) => {
  if (!url) return;
  previewUrl.value = url;
  previewVisible.value = true;
};

// 识图对话
const handleVisionChat = async (text) => {
  messages.value.push(createMessage('user', text, selectedImage.value.dataUrl));
  inputText.value = '';
  imageUploadRef.value?.clearImage();
  // 用户发送消息后立即定位到底部
  scrollToBottom();

  const aiMsg = createMessage('assistant');
  messages.value.push(aiMsg);

  loading.value = true;
  abortController = new AbortController();

  const convId = await ensureConversation();

  try {
    const formData = new FormData();
    formData.append('text', text);
    formData.append('image', selectedImage.value.file);
    if (props.providerId) {
      formData.append('provider_id', props.providerId);
    }
    if (convId) {
      formData.append('conversation_id', convId);
    }

    const response = await chatApi.vision(formData, { signal: abortController.signal });
    await readStream(response, (data) => {
      const { reasoning_content: reasoning = '', content = '' } = data.choices?.[0]?.delta || {};
      if (reasoning) aiMsg.reasoning += reasoning;
      if (content) aiMsg.content += content;
    });

  } catch (error) {
    if (error.name === 'AbortError') {
      aiMsg.content += '（已中止）';
    } else {
      console.error('识图失败', error);
      aiMsg.content = `出错了：${error.message || '网络异常'}`;
    }
  } finally {
    selectedImage.value = null;
    abortController = null;
    loading.value = false;
  }
};

// 语音播报
const speakText = async (text, index) => {
  stopSpeaking();
  
  const plainText = text.replace(/<[^>]+>/g, '').trim();
  if (!plainText) return;

  try {
    // 音色使用 TTS 模型配置中的音色（不传 voice，由后端按提供商配置决定）
    const blob = await audioApi.textToSpeech(plainText, '');
    const url = URL.createObjectURL(blob);
    
    audioElement = new Audio(url);
    audioElement.onended = () => {
      isSpeaking.value = false;
      speakingIndex.value = null;
      URL.revokeObjectURL(url);
    };
    audioElement.onerror = () => {
      isSpeaking.value = false;
      speakingIndex.value = null;
      console.error('语音播放失败');
    };
    isSpeaking.value = true;
    speakingIndex.value = index;
    audioElement.play();
  } catch (e) {
    console.error('语音合成失败', e);
    ElMessage.warning(`语音播报失败：${e.message || ''}`);
  }
};

const stopSpeaking = () => {
  if (audioElement) {
    audioElement.pause();
    audioElement = null;
  }
  isSpeaking.value = false;
  speakingIndex.value = null;
};

// 仅“最新一条”AI 消息允许重新生成
const isLatestAssistant = (index) => {
  if (!messages.value[index] || messages.value[index].role !== 'assistant') return false
  for (let i = messages.value.length - 1; i > index; i--) {
    if (messages.value[i].role === 'assistant') return false
  }
  return true
};

// 重新生成
const regenerate = async (assistantIndex = null) => {
  // 若点击的是某条 AI 消息的「重新生成」，定位到它对应的用户消息所在轮次；
  // 否则（兜底）取最后一条用户消息。
  let userIndex;
  if (typeof assistantIndex === 'number' && assistantIndex > 0) {
    userIndex = assistantIndex - 1;
    while (userIndex >= 0 && messages.value[userIndex].role !== 'user') userIndex--;
    if (userIndex < 0) return;
  } else {
    const lastUserIndex = [...messages.value].reverse().findIndex(m => m.role === 'user');
    if (lastUserIndex === -1) return;
    userIndex = messages.value.length - 1 - lastUserIndex;
  }

  // 删除该轮之后的 AI 回复（含该轮）
  messages.value = messages.value.slice(0, userIndex + 1);
  
  // 重新发送
  const aiMsg = createMessage('assistant');
  messages.value.push(aiMsg);
  
  loading.value = true;
  abortController = new AbortController();

  const convId = await ensureConversation();

  try {
    const requestBody = {
      messages: messages.value.slice(0, -1).map(({ role, content }) => ({ role, content })),
      deep_think: deepThink.value,
      system_prompt: props.systemPrompt,
      temperature: props.temperature,
      provider_id: props.providerId,
      conversation_id: convId,
    };

    const response = await chatApi.stream(requestBody, { signal: abortController.signal });
    await readStream(response, (data) => {
      const { reasoning_content: reasoning = '', content = '' } = data.choices?.[0]?.delta || {};
      if (reasoning) aiMsg.reasoning += reasoning;
      if (content) aiMsg.content += content;
    });
  } catch (error) {
    if (error.name === 'AbortError') {
      aiMsg.content += '（已中止）';
    } else {
      aiMsg.content = `出错了：${error.message || '网络异常'}`;
    }
  } finally {
    abortController = null;
    loading.value = false;
  }
};

// 回车发送
const handleKeydown = (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    handleSend();
  }
};

// 编辑标题
const startEditTitle = () => {
  tempTitle.value = props.conversationTitle;
  editingTitle.value = true;
  setTimeout(() => {
    editTitleInput.value?.focus();
    editTitleInput.value?.select();
  }, 0);
};

const confirmEditTitle = () => {
  const newTitle = tempTitle.value.trim() || '新对话';
  if (newTitle !== props.conversationTitle) {
    emit('titleChange', newTitle);
  }
  editingTitle.value = false;
};

const cancelEditTitle = () => {
  editingTitle.value = false;
};

// 提示词工具面板
const promptToolOpen = ref(false);
// 将生成结果插入输入框
const handlePromptInsert = (text) => {
  inputText.value = text;
  scrollToBottom();
};

// 暴露方法
defineExpose({
  setMessages: (msgList) => {
    messages.value = msgList.map(m => createMessage(m.role, m.content, m.image_url || m.imageUrl));
    scrollToBottom();
  },
  resetMessages: () => {
    messages.value = [];
    scrollToBottom();
  },
  getMessages: () => messages.value,
  scrollToBottom
});

onMounted(() => {
  scrollToBottom();
});

onUnmounted(() => {
  abortRequest();
});
</script>

<template>
  <div class="chat-area" :style="{ '--message-opacity': opacityVal }">
    <!-- 顶部栏 -->
    <div class="chat-header">
      <div class="header-left">
        <div class="chat-title" @click="startEditTitle" v-if="!editingTitle">
          <span class="title-text">{{ conversationTitle || '新对话' }}</span>
          <el-icon class="edit-icon"><Edit /></el-icon>
        </div>
        <el-input
          v-else
          ref="editTitleInput"
          v-model="tempTitle"
          class="title-input"
          size="small"
          @blur="confirmEditTitle"
          @keyup.enter="confirmEditTitle"
          @keyup.esc="cancelEditTitle"
        />
      </div>

      <div class="header-actions">
        <el-tooltip :content="t('对话设置', 'Conversation Settings')">
          <el-button circle :icon="MagicStick" @click="emit('openConversationSettings')" />
        </el-tooltip>
        <el-tooltip :content="t('提示词工具', 'Prompt Tool')">
          <el-button circle :icon="Notebook" @click="promptToolOpen = true" />
        </el-tooltip>
        <el-tooltip :content="t('模型设置', 'Model Settings')">
          <el-button circle :icon="Setting" @click="emit('openProvider')" />
        </el-tooltip>
      </div>
    </div>

    <!-- 消息列表 -->
    <div class="chat-body">
      <!-- 空对话开场白：任何对话无消息时始终展示，切换对话也不会消失 -->
      <div v-if="messages.length === 0" class="chat-welcome">
        <div class="welcome-avatar">
          <img v-if="aiAvatar" :src="aiAvatar" class="avatar-img" alt="AI" />
          <span v-else>AI</span>
        </div>
        <div class="welcome-text">{{ greetingText() }}</div>
      </div>

      <el-scrollbar ref="messageListRef" class="message-scrollbar">
        <div class="message-container">
          <div
            v-for="(item, index) in messages"
            :key="index"
            class="message-item"
            :class="item.role === 'assistant' ? 'message-ai' : 'message-user'"
          >
            <div class="message-avatar">
              <div class="avatar-circle" :class="item.role">
                <img
                  v-if="item.role === 'assistant' && aiAvatar"
                  :src="aiAvatar"
                  class="avatar-img"
                  alt="AI"
                />
                <img
                  v-else-if="item.role === 'user' && userAvatar"
                  :src="userAvatar"
                  class="avatar-img"
                  alt="我"
                />
                <span v-else>{{ item.role === 'assistant' ? 'AI' : t('我', 'Me') }}</span>
              </div>
            </div>
            
            <div class="message-content">
              <!-- 用户消息中的图片 -->
              <div v-if="item.role === 'user' && item.imageUrl" class="message-image">
                <img :src="item.imageUrl" alt="图片" @click="previewImage(item.imageUrl)" />
              </div>
              
              <!-- 思考过程 -->
              <div v-if="item.role === 'assistant' && item.reasoning" class="reasoning-wrapper">
                <div class="reasoning-toggle" @click="item.showReasoning = !item.showReasoning">
                  <el-icon class="thunder-icon"><Lightning /></el-icon>
                  <span>{{ item.showReasoning ? t('收起思考过程', 'Collapse') : t('深度思考中', 'Deep thinking') }}</span>
                  <span class="arrow">{{ item.showReasoning ? '▲' : '▼' }}</span>
                </div>
                <div v-show="item.showReasoning" class="reasoning-block">
                  <div class="reasoning-text">{{ item.reasoning }}</div>
                </div>
              </div>
              
              <!-- 图片生成结果（文生图 / 图生图） -->
              <div v-if="item.role === 'assistant' && item.imageUrl" class="message-image generated">
                <img :src="item.imageUrl" alt="生成图片" @click="previewImage(item.imageUrl)" />
              </div>
              
              <!-- 消息内容 -->
              <div v-if="item.content" class="content-text" v-html="item.content"></div>
              
              <!-- 加载状态 -->
              <div v-if="item.role === 'assistant' && !item.content && !item.reasoning && !item.imageUrl" class="loading-dots">
                <span></span><span></span><span></span>
              </div>

              <!-- 消息操作 -->
              <div v-if="item.role === 'assistant' && item.content" class="message-actions">
                <el-button 
                  size="small" 
                  text 
                  :icon="RefreshLeft" 
                  @click="regenerate(index)"
                  class="action-btn"
                  :disabled="loading || !isLatestAssistant(index)"
                >
                  {{ t('重新生成', 'Regenerate') }}
                </el-button>
                <el-button 
                  size="small" 
                  text 
                  :icon="Bell" 
                  @click="speakText(item.content, index)"
                  class="action-btn"
                >
                  {{ speakingIndex === index ? t('播报中', 'Speaking') : t('语音播报', 'Speak') }}
                </el-button>
              </div>
            </div>
          </div>
        </div>
      </el-scrollbar>
    </div>

    <!-- 底部输入区 -->
    <div class="chat-footer">
      <div class="input-wrapper">
        <!-- 图片预览条 -->
        <div v-if="selectedImage" class="image-preview-bar">
          <img :src="selectedImage.dataUrl" class="preview-thumb" />
          <span class="image-hint">{{ t('识图模式', 'Vision mode') }}</span>
        </div>
        
        <div class="input-area">
          <el-input 
            v-model="inputText" 
            type="textarea" 
            class="chat-input" 
            :placeholder="selectedImage ? t('输入关于图片的问题...', 'Ask about the image...') : t('发送消息给 AI...', 'Message the AI...')" 
            resize="none"
            :autosize="{ minRows: 1, maxRows: 6 }" 
            @keydown="handleKeydown" 
          />
        </div>
        
        <div class="input-actions">
          <div class="action-left">
            <ImageUpload 
              ref="imageUploadRef"
              @image-selected="handleImageSelected"
              @clear="handleImageCleared"
            />
            <VoiceInput 
              :provider-id="providerId"
              @text-ready="handleVoiceText"
            />
            <div class="deep-think-wrapper">
              <el-switch 
                v-model="deepThink" 
                :active-text="t('深思', 'Deep')"
                inline-prompt
                size="small"
              />
            </div>
            <div
              class="gen-mode-group"
              :title="t('选择图片生成方式：生图=文字生成图片；改图=修改参考图（需先上传图片）。需先在模型配置中添加图片生成配置', 'Generate: text to image. Edit: modify a reference image (attach one first). Add an image config in Model Settings first.')"
            >
              <button
                class="gen-mode-btn"
                :class="{ active: genMode === 'text2img' }"
                @click="genMode = genMode === 'text2img' ? '' : 'text2img'"
              >
                <el-icon><Picture /></el-icon>
                <span>{{ t('生图', 'Image') }}</span>
              </button>
              <button
                class="gen-mode-btn"
                :class="{ active: genMode === 'img2img' }"
                @click="genMode = genMode === 'img2img' ? '' : 'img2img'"
              >
                <el-icon><Edit /></el-icon>
                <span>{{ t('改图', 'Edit') }}</span>
              </button>
            </div>
          </div>
          
          <div class="action-right">
            <el-button 
              class="send-btn" 
              type="primary"
              circle
              :icon="loading ? CircleClose : Upload"
              @click="handleSend"
            />
          </div>
        </div>
      </div>
      
    </div>

    <!-- 提示词工具 -->
    <PromptToolPanel v-model="promptToolOpen" @insert="handlePromptInsert" />

    <!-- 图片大图预览：直接全屏展示单张大图，无额外标题/边框 -->
    <el-image-viewer
      v-if="previewVisible && previewUrl"
      :url-list="[previewUrl]"
      :zoom-rate="1.2"
      hide-on-click-modal
      @close="previewVisible = false"
    />
  </div>
</template>

<style scoped>
.chat-area {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: transparent;
  flex: 1;
  min-width: 0;
}

/* 顶部栏 */
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 24px;
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
  background: transparent;
}

.header-left {
  display: flex;
  align-items: center;
}

.chat-title {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  transition: background 0.2s;
}

.chat-title:hover {
  background: var(--surface-hover);
}

.title-text {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.edit-icon {
  font-size: 14px;
  color: #9ca3af;
  opacity: 0;
  transition: opacity 0.2s;
}

.chat-title:hover .edit-icon {
  opacity: 1;
}

.title-input {
  width: 280px;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.header-actions :deep(.el-button) {
  width: 36px;
  height: 36px;
  border: none;
  background: transparent;
  color: #6b7280;
}

.header-actions :deep(.el-button:hover) {
  background: #f3f4f6;
  color: #1f2937;
}

/* 消息区 */
.chat-body {
  flex: 1;
  overflow: hidden;
}

.message-scrollbar {
  height: 100%;
}

.message-container {
  max-width: 768px;
  margin: 0 auto;
  padding: 24px 20px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* 空对话开场白 */
.chat-welcome {
  max-width: 768px;
  margin: 0 auto;
  padding: 48px 20px;
  display: flex;
  align-items: center;
  gap: 14px;
}

.welcome-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: var(--brand-gradient);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
  overflow: hidden;
  flex-shrink: 0;
}

.welcome-avatar .avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.welcome-text {
  font-size: 15px;
  line-height: 1.7;
  color: var(--text-primary);
  background: rgba(163, 172, 190, var(--message-opacity, 0.9));
  padding: 10px 16px;
  border-radius: 14px;
  border-top-left-radius: 4px;
}

.message-item {
  display: flex;
  gap: 16px;
}

.message-item.message-user {
  flex-direction: row-reverse;
}

.message-avatar {
  flex-shrink: 0;
}

.avatar-circle {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  overflow: hidden;
}

.avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.avatar-circle.assistant {
  background: var(--brand-gradient);
  color: #fff;
}

.avatar-circle.user {
  background: #e5e7eb;
  color: #374151;
  overflow: hidden;
}

.message-content {
  max-width: calc(100% - 52px);
  min-width: 0;
}

.message-image {
  margin-bottom: 8px;
}

.message-image img {
  max-width: 300px;
  max-height: 300px;
  border-radius: 12px;
  display: block;
  cursor: zoom-in;
}

/* 生成的图片支持更大展示 */
.message-image.generated img {
  max-width: 480px;
  max-height: 480px;
  cursor: zoom-in;
  box-shadow: 0 4px 16px rgba(0,0,0,0.12);
}

/* 图片大图预览使用 el-image-viewer 全屏展示，无需额外样式 */

/* 思考过程 */
.reasoning-wrapper {
  margin-bottom: 12px;
}

.reasoning-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  user-select: none;
  padding: 6px 12px;
  background: #f3f4f6;
  border-radius: 20px;
  font-size: 13px;
  color: #6b7280;
  transition: background 0.2s;
}

.reasoning-toggle:hover {
  background: #e5e7eb;
}

.thunder-icon {
  color: #f59e0b;
  font-size: 14px;
}

.arrow {
  font-size: 10px;
  color: #9ca3af;
}

.reasoning-block {
  background: #fafafa;
  padding: 12px 16px;
  border-radius: 12px;
  border-left: 3px solid #f59e0b;
  margin-top: 8px;
  font-size: 14px;
  color: #6b7280;
}

.reasoning-text {
  white-space: pre-wrap;
  word-wrap: break-word;
  line-height: 1.6;
}

/* 消息内容 */
.content-text {
  font-size: 15px;
  line-height: 1.7;
  color: var(--text-primary);
  word-wrap: break-word;
}

.message-user .content-text {
  background: rgba(79, 70, 229, var(--message-opacity, 0.92));
  color: #fff;
  padding: 10px 16px;
  border-radius: 16px;
  border-top-right-radius: 4px;
}

.message-ai .content-text {
  color: var(--text-primary);
  background: rgba(163, 172, 190, var(--message-opacity, 0.9));
  padding: 10px 16px;
  border-radius: 14px;
  border-top-left-radius: 4px;
}

/* 加载动画 */
.loading-dots {
  display: flex;
  gap: 4px;
  padding: 12px 0;
}

.loading-dots span {
  width: 8px;
  height: 8px;
  background: #d1d5db;
  border-radius: 50%;
  animation: bounce 1.4s infinite ease-in-out both;
}

.loading-dots span:nth-child(1) { animation-delay: -0.32s; }
.loading-dots span:nth-child(2) { animation-delay: -0.16s; }

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0.8); opacity: 0.5; }
  40% { transform: scale(1); opacity: 1; }
}

/* 消息操作 */
.message-actions {
  display: flex;
  gap: 4px;
  margin-top: 8px;
  opacity: 0;
  transition: opacity 0.2s;
}

.message-item:hover .message-actions {
  opacity: 1;
}

.action-btn {
  font-size: 12px;
  color: #9ca3af;
  padding: 2px 8px;
  height: 24px;
}

/* 有背景图片时也仅改变字体颜色，不出现白色/浅色背景，避免突兀 */
.action-btn,
.action-btn:active,
.action-btn:focus,
.action-btn.is-text,
.action-btn.is-text:active,
.action-btn.is-text:focus {
  background: transparent !important;
}

.action-btn:hover,
.action-btn.is-text:hover {
  color: var(--brand);
  background: transparent !important;
}

/* 底部输入区 */
.chat-footer {
  padding: 12px 20px 16px;
  flex-shrink: 0;
  background: transparent;
}

.input-wrapper {
  max-width: 768px;
  margin: 0 auto;
  background: rgba(120, 130, 145, calc(var(--message-opacity, 1) * 0.12));
  border-radius: 16px;
  padding: 8px 8px 4px;
  border: 1px solid var(--border-color);
  backdrop-filter: blur(6px);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.input-wrapper:focus-within {
  border-color: #d1d5db;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.image-preview-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  padding: 6px 10px;
  background: #eef2ff;
  border-radius: 8px;
}

.preview-thumb {
  width: 32px;
  height: 32px;
  border-radius: 6px;
  object-fit: cover;
}

.image-hint {
  font-size: 12px;
  color: var(--brand);
  font-weight: 500;
}

.input-area {
  margin-bottom: 4px;
}

.chat-input :deep(.el-textarea__inner) {
  background: transparent;
  border: none;
  padding: 8px 12px;
  font-size: 15px;
  line-height: 1.6;
  resize: none;
  box-shadow: none;
}

.chat-input :deep(.el-textarea__inner:focus) {
  box-shadow: none;
}

.input-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 4px;
}

.action-left {
  display: flex;
  align-items: center;
  gap: 4px;
}

.action-right {
  display: flex;
  align-items: center;
}

.send-btn {
  width: 36px;
  height: 36px;
  background: var(--brand-gradient);
  border: none;
  color: #fff;
}

.send-btn:hover {
  opacity: 0.92;
  background: var(--brand-gradient);
}

.deep-think-wrapper {
  margin-left: 8px;
}

.gen-mode-group {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  margin-left: 8px;
  padding: 2px;
  height: 24px;
  border-radius: 999px;
  border: 1px solid rgba(120, 130, 145, 0.18);
  background: transparent;
}

.gen-mode-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 20px;
  padding: 0 10px;
  border: none;
  border-radius: 999px;
  font-size: 12px;
  color: #6b7280;
  background: transparent;
  cursor: pointer;
  transition: all 0.2s;
  user-select: none;
}

.gen-mode-btn:hover {
  color: var(--brand);
}

.gen-mode-btn.active {
  color: var(--brand);
  background: rgba(120, 130, 145, calc(var(--message-opacity, 1) * 0.14));
}

/* Markdown 样式补充 */
.content-text :deep(img) { max-width: 100%; border-radius: 6px; }
.content-text :deep(pre) {
  background: #1f2937;
  padding: 12px 16px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 12px 0;
}
.content-text :deep(code) {
  background: rgba(0, 0, 0, 0.06);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.9em;
  font-family: 'SF Mono', Consolas, monospace;
}
.content-text :deep(pre code) { background: none; padding: 0; color: #e5e7eb; }
.content-text :deep(a) { color: var(--brand); }

.message-user .content-text :deep(a) { color: #fff; text-decoration: underline; }
.message-user .content-text :deep(code) { background: rgba(255,255,255,0.2); }

/* 响应式 */
@media (max-width: 768px) {
  .chat-header {
    padding: 10px 16px 10px 58px;
  }
  .chat-header .header-actions {
    gap: 2px;
  }
  
  .message-container {
    padding: 16px 12px;
    gap: 16px;
  }
  
  .message-item {
    gap: 10px;
  }
  
  .avatar-circle {
    width: 32px;
    height: 32px;
    font-size: 12px;
  }
  
  .message-content {
    max-width: calc(100% - 42px);
  }
  
  .content-text {
    font-size: 14px;
    line-height: 1.6;
  }
  
  .chat-footer {
    padding: 8px 12px 12px;
  }
  
  .message-actions {
    opacity: 1;
  }
}
</style>
