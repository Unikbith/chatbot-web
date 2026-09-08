<script setup>
import { ref, computed, nextTick, watch, onMounted, onUnmounted } from 'vue';
import { ElMessage, ElMessageBox, ElInput } from 'element-plus';
import { 
  Setting, CopyDocument, RefreshLeft, Lightning, 
  Bell, CircleClose, Upload, Edit, MagicStick
} from '@element-plus/icons-vue';
import { readStream, chatApi, audioApi, providersApi } from '@/utils/resAi';
import auth from '@/utils/auth';
import { t } from '../i18n';

import VoiceInput from '@/components/VoiceInput.vue';
import ImageUpload from '@/components/ImageUpload.vue';

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
  isFreeApi: { type: Boolean, default: false }
});

const emit = defineEmits([
  'openSettings', 
  'openProvider',
  'openConversationSettings',
  'titleChange', 
  'newChat',
  'updateConversation'
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

const messages = ref([createMessage('assistant', greetingText())]);
const inputText = ref('');
const loading = ref(false);
const messageListRef = ref(null);
const deepThink = ref(false);
let abortController = null;

// 图片上传
const imageUploadRef = ref(null);
const selectedImage = ref(null);

// 语音播报
const isSpeaking = ref(false);
let audioElement = null;

// 编辑标题
const editingTitle = ref(false);
const editTitleInput = ref(null);
const tempTitle = ref('');

// 复制反馈
const copiedIndex = ref(null);

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

// 发送消息
const handleSend = async () => {
  if (loading.value) { abortRequest(); return; }

  const text = inputText.value.trim();
  if (!text && !selectedImage.value) return;

  // 如果有图片，走识图接口
  if (selectedImage.value) {
    await handleVisionChat(text || '请描述这张图片');
    return;
  }

  messages.value.push(createMessage('user', text));
  inputText.value = '';

  const aiIndex = messages.value.length;
  messages.value.push(createMessage('assistant'));

  loading.value = true;
  abortController = new AbortController();

  try {
    const requestBody = {
      messages: messages.value.slice(0, -1).map(({ role, content }) => ({ role, content })),
      deep_think: deepThink.value,
      system_prompt: props.systemPrompt,
      temperature: props.temperature,
      provider_id: props.providerId,
      conversation_id: props.conversationId,
    };

    const response = await chatApi.stream(requestBody, { signal: abortController.signal });
    await readStream(response, (data) => {
      const { reasoning_content: reasoning = '', content = '' } = data.choices?.[0]?.delta || {};
      if (reasoning) messages.value[aiIndex].reasoning += reasoning;
      if (content) messages.value[aiIndex].content += content;
    });

    // 更新对话标题（第一条用户消息）
    if (messages.value.filter(m => m.role === 'user').length === 1) {
      const title = text.length > 20 ? text.substring(0, 20) + '...' : text;
      emit('titleChange', title);
    }

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
    scrollToBottom();
  }
};

// 识图对话
const handleVisionChat = async (text) => {
  messages.value.push(createMessage('user', text, selectedImage.value.dataUrl));
  inputText.value = '';
  imageUploadRef.value?.clearImage();

  const aiIndex = messages.value.length;
  messages.value.push(createMessage('assistant'));

  loading.value = true;
  abortController = new AbortController();

  try {
    const formData = new FormData();
    formData.append('text', text);
    formData.append('image', selectedImage.value.file);
    if (props.providerId) {
      formData.append('provider_id', props.providerId);
    }
    if (props.conversationId) {
      formData.append('conversation_id', props.conversationId);
    }

    const response = await chatApi.vision(formData, { signal: abortController.signal });
    await readStream(response, (data) => {
      const { reasoning_content: reasoning = '', content = '' } = data.choices?.[0]?.delta || {};
      if (reasoning) messages.value[aiIndex].reasoning += reasoning;
      if (content) messages.value[aiIndex].content += content;
    });

  } catch (error) {
    if (error.name === 'AbortError') {
      messages.value[aiIndex].content += '（已中止）';
    } else {
      console.error('识图失败', error);
      messages.value[aiIndex].content = `出错了：${error.message || '网络异常'}`;
    }
  } finally {
    selectedImage.value = null;
    abortController = null;
    loading.value = false;
    scrollToBottom();
  }
};

// 语音播报
const speakText = async (text) => {
  stopSpeaking();
  
  const plainText = text.replace(/<[^>]+>/g, '').trim();
  if (!plainText) return;

  try {
    const blob = await audioApi.textToSpeech(plainText, 'alloy', props.providerId);
    const url = URL.createObjectURL(blob);
    
    audioElement = new Audio(url);
    audioElement.onended = () => {
      isSpeaking.value = false;
      URL.revokeObjectURL(url);
    };
    audioElement.onerror = () => {
      isSpeaking.value = false;
      console.error('语音播放失败');
    };
    isSpeaking.value = true;
    audioElement.play();
  } catch (e) {
    console.error('语音合成失败', e);
    ElMessage.warning('语音播报失败');
  }
};

const stopSpeaking = () => {
  if (audioElement) {
    audioElement.pause();
    audioElement = null;
  }
  isSpeaking.value = false;
};

// 复制消息
const copyMessage = async (content, index) => {
  try {
    const plainText = content.replace(/<[^>]+>/g, '').trim();
    await navigator.clipboard.writeText(plainText);
    copiedIndex.value = index;
    setTimeout(() => { copiedIndex.value = null; }, 2000);
  } catch (e) {
    ElMessage.warning('复制失败');
  }
};

// 重新生成
const regenerate = async () => {
  // 找到最后一条用户消息
  const lastUserIndex = [...messages.value].reverse().findIndex(m => m.role === 'user');
  if (lastUserIndex === -1) return;
  
  const actualIndex = messages.value.length - 1 - lastUserIndex;
  const userMessage = messages.value[actualIndex];
  
  // 删除 AI 回复
  messages.value = messages.value.slice(0, actualIndex + 1);
  
  // 重新发送
  const aiIndex = messages.value.length;
  messages.value.push(createMessage('assistant'));
  
  loading.value = true;
  abortController = new AbortController();
  
  try {
    const requestBody = {
      messages: messages.value.slice(0, -1).map(({ role, content }) => ({ role, content })),
      deep_think: deepThink.value,
      system_prompt: props.systemPrompt,
      temperature: props.temperature,
      provider_id: props.providerId,
      conversation_id: props.conversationId,
    };

    const response = await chatApi.stream(requestBody, { signal: abortController.signal });
    await readStream(response, (data) => {
      const { reasoning_content: reasoning = '', content = '' } = data.choices?.[0]?.delta || {};
      if (reasoning) messages.value[aiIndex].reasoning += reasoning;
      if (content) messages.value[aiIndex].content += content;
    });
  } catch (error) {
    if (error.name === 'AbortError') {
      messages.value[aiIndex].content += '（已中止）';
    } else {
      messages.value[aiIndex].content = `出错了：${error.message || '网络异常'}`;
    }
  } finally {
    abortController = null;
    loading.value = false;
    scrollToBottom();
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

// 清空当前对话
const handleClearChat = async () => {
  if (loading.value) abortRequest();
  
  try {
    await ElMessageBox.confirm('确定要清空当前对话吗？', '确认', { type: 'warning' });
  } catch {
    return;
  }

  messages.value = [createMessage('assistant', greetingText())];
  inputText.value = '';
  scrollToBottom();
};

// 暴露方法
defineExpose({
  setMessages: (msgList) => {
    messages.value = msgList.map(m => createMessage(m.role, m.content, m.image_url || m.imageUrl));
    scrollToBottom();
  },
  resetMessages: () => {
    messages.value = [createMessage('assistant', greetingText())];
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
        <el-tooltip :content="t('清空对话', 'Clear Chat')">
          <el-button circle :icon="RefreshLeft" @click="handleClearChat" />
        </el-tooltip>
        <el-tooltip :content="t('模型设置', 'Model Settings')">
          <el-button circle :icon="Setting" @click="emit('openProvider')" />
        </el-tooltip>
      </div>
    </div>

    <!-- 消息列表 -->
    <div class="chat-body">
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
                <img :src="item.imageUrl" alt="图片" />
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
              
              <!-- 消息内容 -->
              <div v-if="item.content" class="content-text" v-html="item.content"></div>
              
              <!-- 加载状态 -->
              <div v-if="item.role === 'assistant' && !item.content && !item.reasoning" class="loading-dots">
                <span></span><span></span><span></span>
              </div>

              <!-- 消息操作 -->
              <div v-if="item.role === 'assistant' && item.content" class="message-actions">
                <el-button 
                  size="small" 
                  text 
                  :icon="CopyDocument" 
                  @click="copyMessage(item.content, index)"
                  class="action-btn"
                >
                  {{ copiedIndex === index ? t('已复制', 'Copied') : t('复制', 'Copy') }}
                </el-button>
                <el-button 
                  size="small" 
                  text 
                  :icon="RefreshLeft" 
                  @click="regenerate"
                  class="action-btn"
                  :disabled="loading"
                >
                  {{ t('重新生成', 'Regenerate') }}
                </el-button>
                <el-button 
                  size="small" 
                  text 
                  :icon="Bell" 
                  @click="speakText(item.content)"
                  class="action-btn"
                >
                  {{ t('语音播报', 'Speak') }}
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
      
      <div class="footer-hint">
        {{ t('AI 可能会产生不准确的信息，请核实重要内容', 'AI may produce inaccurate information. Please verify important facts.') }}
      </div>
    </div>
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
}

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
  background: rgba(148, 163, 184, calc(var(--message-opacity, 0.9) * 0.16));
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

.action-btn:hover {
  color: var(--brand);
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

.footer-hint {
  text-align: center;
  font-size: 12px;
  color: #9ca3af;
  margin-top: 8px;
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
