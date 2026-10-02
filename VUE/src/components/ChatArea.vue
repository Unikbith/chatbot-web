<script setup>
import { ref, reactive, computed, nextTick, watch, onMounted, onUnmounted } from 'vue';
import logger from '@/utils/logger';
import { ElMessage, ElInput } from 'element-plus';
import { 
  Setting, RefreshLeft, Lightning, 
  Bell, CircleClose, Upload, Edit, MagicStick, Picture, Notebook
} from '@element-plus/icons-vue';
import { readStream, chatApi, audioApi, imageApi, providersApi, conversationApi } from '@/utils/resAi';
import auth from '@/utils/auth';
import { sanitizeHtml } from '@/utils/sanitize';
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
  modelId: {
    type: String,
    default: ''
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
  autoPlayVoice: { type: Boolean, default: false },
  loggedIn: { type: Boolean, default: false },
  personaGreeting: { type: String, default: '' },
  backgroundImage: { type: String, default: '' },
  backgroundCover: { type: String, default: 'cover' }
});

const emit = defineEmits([
  'openSettings', 
  'openProvider',
  'openConversationSettings',
  'titleChange', 
  'newChat',
  'updateConversation',
  'conversationCreated',
  'requireLogin',
  'modelChange'
]);

const opacityVal = computed(() => {
  const v = Number(props.messageOpacity)
  return isNaN(v) ? 0.9 : Math.min(1, Math.max(0.05, v))
});

const bgStyle = computed(() => {
  if (!props.backgroundImage) return {}
  return {
    backgroundImage: `url(${props.backgroundImage})`,
    backgroundSize: props.backgroundCover === 'contain' ? 'contain' : 'cover',
    backgroundPosition: 'center',
    backgroundRepeat: 'no-repeat',
  }
});

const greetingText = () => t('你好！有什么可以帮你的吗？', 'Hello! How can I help you?');

// 开场白：作为会话首条消息常驻展示，发送消息/收到回复后不会消失；
// 仅当载入已有历史消息的对话时隐藏（历史中没有开场白，避免重复）。
// 初始为 false：页面刷新/首次挂载时还不知道对话是否为空，
// 先不渲染开场白，等 setMessages/resetMessages 明确后再显示，
// 避免刷新瞬间闪现默认招呼语再消失的错误画面。
const greetingActive = ref(false);
const showWelcome = computed(() => greetingActive.value);

// 消息
let _msgSeq = 0;
const createMessage = (role, content = '', imageUrl = null) => ({ 
  _key: `m${++_msgSeq}`,  // 稳定唯一 key，避免用 index 作 key 导致重排时 DOM 复用错乱
  // raw：Markdown 原文（落库/语音朗读用）；streamHtml：后端下发的已转义 HTML 片段
  // （生成中直接渲染，与成稿排版一致，避免回复结束后空行被抹掉造成跳变）
  // tokens：本次回复的 token 消耗（厂商未返回时为 null，不展示）
  // hasAiStyle：本条回复是否带模型自绘样式（决定是否加作用域类）
  role, content, raw: '', streamHtml: '', streaming: false, reasoning: '', showReasoning: false, imageUrl, tokens: null, hasAiStyle: false
});

const messages = ref([]);
const inputText = ref('');
const loading = ref(false);
const messageListRef = ref(null);
const deepThink = ref(false);
let abortController = null;

// ===== 模型自绘样式（AI 自助 CSS）=====
// 后端已把模型写的 CSS 过滤到「视觉属性白名单 + 仅 class 选择器」，
// 这里以 CSSOM 注入到消息容器的作用域内：既不经过 v-html（无 XSS 风险），
// 也不会污染全局（选择器被限定在 .ai-style-scope 下）。
const AI_SCOPE_CLASS = 'ai-style-scope';

let aiStyleSheet = null;
let aiStyleText = '';

function ensureAiStyleSheet() {
  if (aiStyleSheet) return aiStyleSheet;
  if (typeof document === 'undefined') return null;
  const style = document.createElement('style');
  style.setAttribute('data-ai-style', '1');
  style.textContent = '';
  document.head.appendChild(style);
  aiStyleSheet = style;
  return aiStyleSheet;
}

function applyAiStyle(cssText) {
  if (!cssText) return;
  const sheet = ensureAiStyleSheet();
  if (!sheet) return;
  // 作用域前缀：把 .card 改写成 .ai-style-scope .card，
  // 配合消息容器的 ai-style-scope 类实现「只在本条消息内生效」
  const scoped = `.${AI_SCOPE_CLASS} {\n${cssText}\n}`;
  // 累积而非覆盖：模型可能在多条消息里分别给样式
  if (!aiStyleText.includes(scoped)) {
    aiStyleText += scoped;
    sheet.textContent = aiStyleText;
  }
}

// ========== 对话模型选择器（输入框左下角） ==========
// 数据来源：当前用户全部已启用的对话模型配置（含配置内启用的模型），
// 选择后以「配置ID::模型ID」组合值驱动，随消息请求带 provider_id + model_id。
const chatProviders = ref([]);
const modelSelectValue = ref(''); // `${providerId}::${modelId}`，模型为空时仅 providerId

const modelOptions = computed(() => {
  const groups = [];
  for (const p of chatProviders.value) {
    if (p.enabled === false) continue;
    const models = (p.models || []).filter(m => m.enabled !== false);
    if (models.length) {
      groups.push({
        provider: p,
        options: models.map(m => ({
          value: `${p.id}::${m.model_id}`,
          label: m.name || m.model_id,
        })),
      });
    } else if (p.model) {
      // 配置未维护模型列表时，用配置自身的默认模型兜底
      groups.push({
        provider: p,
        options: [{ value: `${p.id}::${p.model}`, label: p.model }],
      });
    }
  }
  return groups;
});

// 未显式选模型时，解析该配置实际会使用的默认模型：
// 第一个启用的模型 → 配置默认模型（与后端解析顺序保持一致）。
// 否则把裸 providerId（如 "1"）塞给 el-select，没有匹配项就会显示成 "1"。
const resolveDefaultModelValue = () => {
  const p = chatProviders.value.find(x => x.id == props.providerId);
  if (!p) return '';
  const models = (p.models || []).filter(m => m.enabled !== false);
  if (models.length) return `${p.id}::${models[0].model_id}`;
  if (p.model) return `${p.id}::${p.model}`;
  return '';
};

// 选择器当前显示值：与父组件传入的 providerId / modelId 保持同步
const syncModelSelectValue = () => {
  if (!props.providerId) { modelSelectValue.value = ''; return; }
  if (props.modelId) {
    modelSelectValue.value = `${props.providerId}::${props.modelId}`;
    return;
  }
  modelSelectValue.value = resolveDefaultModelValue() || String(props.providerId);
};
watch(() => [props.providerId, props.modelId], syncModelSelectValue, { immediate: true });
// 配置列表是异步加载/刷新的（模型配置面板关闭会 reload），默认模型解析依赖它，需重算
watch(chatProviders, syncModelSelectValue);

// 当前选中的展示文案（配置名 · 模型名）
const currentModelLabel = computed(() => {
  const p = chatProviders.value.find(x => x.id == props.providerId);
  if (!p) return t('选择模型', 'Select model');
  let m = (p.models || []).find(x => x.model_id === props.modelId);
  if (!m && !props.modelId) {
    // 未显式选模型时展示实际会用的默认模型
    const models = (p.models || []).filter(x => x.enabled !== false);
    m = models[0] || (p.model ? { model_id: p.model, name: p.model } : null);
  }
  return m ? `${p.name} · ${m.name || m.model_id}` : p.name;
});

const loadChatProviders = async () => {
  try {
    const res = await providersApi.list('chat');
    if (res.code === 200) chatProviders.value = res.data || [];
  } catch (e) {
    logger.warn('加载模型配置失败', e);
  }
  // 模型配置面板关闭后会触发本函数：同时让「大模型原生生图」探测缓存失效，
  // 避免改了图片配置 llm_tools 开关后仍沿用旧结果
  llmToolsCache = null;
};

const handleModelSelect = (val) => {
  if (!val) return;
  const sep = val.indexOf('::');
  const providerId = sep >= 0 ? Number(val.slice(0, sep)) : Number(val);
  const modelId = sep >= 0 ? val.slice(sep + 2) : '';
  emit('modelChange', { providerId, modelId });
};

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
      model_id: props.modelId || undefined,
      system_prompt: props.systemPrompt,
      temperature: props.temperature,
    });
    if (res.code === 200) {
      emit('conversationCreated', res.data);
      return res.data.id;
    }
  } catch (e) {
    logger.error('创建对话失败', e);
  }
  return null;
};

// 发送消息前先确认已登录；未登录直接弹登录框且不发请求（需求：输入框未登录不可发送）
const guardLogin = () => {
  if (!props.loggedIn) {
    emit('requireLogin')
    return false
  }
  return true
}

// 发送消息
const handleSend = async () => {
  if (loading.value) { abortRequest(); return; }
  if (!guardLogin()) return;

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
  const aiMsg = reactive(createMessage('assistant'));
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
      model_id: props.modelId || undefined,
      conversation_id: convId,
    };

    const response = await chatApi.stream(requestBody, { signal: abortController.signal });
    await readStream(response, (data) => {
      const { reasoning_content: reasoning = '', content = '', html = '', tokens = null, style: aiCss = '' } = data.choices?.[0]?.delta || {};
      if (reasoning) aiMsg.reasoning += reasoning;
      if (content) { aiMsg.raw += content; aiMsg.streamHtml += content; aiMsg.streaming = true; }
      if (tokens) aiMsg.tokens = tokens;
      if (aiCss) { applyAiStyle(aiCss); aiMsg.hasAiStyle = true; }
      if (html) { aiMsg.content = sanitizeHtml(html); aiMsg.streaming = false; }
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
      aiMsg.streaming = false;
      aiMsg.raw += t('（已中止）', ' (aborted)');
    } else {
      logger.error('发送失败', error);
      aiMsg.streaming = false;
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

// 从模型回复里提取「生图/改图」标记并代为调用图片生成，结果以图片形式附到该消息。
// reference 供「改图（图生图）」使用：识图对话中用户附带的参考图 / 结合人设生成新图
async function handleLlmImageMarkers(msg, reference = null) {
  const src = msg.raw || msg.content || '';
  if (!src) return;
  const m2i = src.match(/生图[:：]\s*([^\n]+)/);
  const mImg = src.match(/改图[:：]\s*([^\n]+)/);
  const marker = m2i || mImg;
  if (!marker) return;
  const prompt = marker[1].trim();
  // 移除标记行，保留可读文本；流式原文与最终 HTML 都去掉标记
  msg.raw = ((msg.raw || '').replace(marker[0], '') || '').trim();
  msg.content = ((msg.content || '').replace(marker[0], '') || '').trim();
  try {
    // 改图时把用户/参考图作为 references 传入，实现「结合人设 + 参考图生成新图」
    const useRef = mImg ? (reference ? [reference] : []) : [];
    const res = await imageApi.generate({ prompt, references: useRef });
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

  const aiMsg = reactive(createMessage('assistant'));
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
  // 先快照用户上传的图片，后续 clearImage 不会影响它（既是消息图，也作改图参考图）
  const img = selectedImage.value
  const refDataUrl = img?.dataUrl || null

  messages.value.push(createMessage('user', text, refDataUrl));
  inputText.value = '';
  imageUploadRef.value?.clearImage();
  // 用户发送消息后立即定位到底部
  scrollToBottom();

  const aiMsg = reactive(createMessage('assistant'));
  messages.value.push(aiMsg);

  loading.value = true;
  abortController = new AbortController();

  const convId = await ensureConversation();

  try {
    const formData = new FormData();
    formData.append('text', text);
    formData.append('image', img?.file);
    if (props.providerId) {
      formData.append('provider_id', props.providerId);
    }
    if (convId) {
      formData.append('conversation_id', convId);
    }
    // 识图同样注入人设 + 图片生成能力约定：模型输出「改图」标记后，前端结合用户参考图自动生图
    const personaPrompt = (props.systemPrompt || '').trim();
    formData.append('system_prompt', (
      personaPrompt + '\n\n[系统能力-图片生成] 当用户提供图片并希望在保留图片元素的同时生成/修改图片（例如想看"你的样子"、把图中的元素融入人设风格制作新图）时，只回复一行：`改图：<用中文描述修改要求>`，用户上传的图片会自动作为参考图使用，不要输出其它解释。'
    ).trim());

    const response = await chatApi.vision(formData, { signal: abortController.signal });
    await readStream(response, (data) => {
      const { reasoning_content: reasoning = '', content = '', html = '', tokens = null, style: aiCss = '' } = data.choices?.[0]?.delta || {};
      if (reasoning) aiMsg.reasoning += reasoning;
      if (content) { aiMsg.raw += content; aiMsg.streamHtml += content; aiMsg.streaming = true; }
      if (tokens) aiMsg.tokens = tokens;
      if (aiCss) { applyAiStyle(aiCss); aiMsg.hasAiStyle = true; }
      if (html) { aiMsg.content = sanitizeHtml(html); aiMsg.streaming = false; }
    });

    // 模型若输出「改图」标记，则结合人设与用户上传的参考图自动生图并贴到本条回复
    await handleLlmImageMarkers(aiMsg, refDataUrl);

  } catch (error) {
    if (error.name === 'AbortError') {
      aiMsg.streaming = false;
      aiMsg.raw += t('（已中止）', ' (aborted)');
    } else {
      logger.error('识图失败', error);
      aiMsg.streaming = false;
      aiMsg.content = `出错了：${error.message || '网络异常'}`;
    }
  } finally {
    selectedImage.value = null;
    abortController = null;
    loading.value = false;
  }
};

// 语音播报
// 保存当前播放的 object URL，便于在停止/卸载时释放，避免 blob 常驻内存
let currentAudioUrl = null;

const speakText = async (text, index) => {
  stopSpeaking();
  
  const plainText = text.replace(/<[^>]+>/g, '').trim();
  if (!plainText) return;

  try {
    // 音色使用 TTS 模型配置中的音色（不传 voice，由后端按提供商配置决定）
    const blob = await audioApi.textToSpeech(plainText, '');
    const url = URL.createObjectURL(blob);
    currentAudioUrl = url;

    audioElement = new Audio(url);
    audioElement.onended = () => {
      isSpeaking.value = false;
      speakingIndex.value = null;
      releaseAudioUrl();
    };
    audioElement.onerror = () => {
      isSpeaking.value = false;
      speakingIndex.value = null;
      releaseAudioUrl();
      logger.error('语音播放失败');
    };
    isSpeaking.value = true;
    speakingIndex.value = index;
    audioElement.play();
  } catch (e) {
    logger.error('语音合成失败', e);
    ElMessage.warning(`语音播报失败：${e.message || ''}`);
  }
};

// 释放当前音频对象 URL（幂等）
const releaseAudioUrl = () => {
  if (currentAudioUrl) {
    try { URL.revokeObjectURL(currentAudioUrl); } catch { /* 忽略 */ }
    currentAudioUrl = null;
  }
};

const stopSpeaking = () => {
  if (audioElement) {
    audioElement.onended = null;
    audioElement.onerror = null;
    audioElement.pause();
    audioElement.src = '';
    audioElement = null;
  }
  releaseAudioUrl();
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
  const aiMsg = reactive(createMessage('assistant'));
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
      model_id: props.modelId || undefined,
      conversation_id: convId,
    };

    const response = await chatApi.stream(requestBody, { signal: abortController.signal });
    await readStream(response, (data) => {
      const { reasoning_content: reasoning = '', content = '', html = '', tokens = null, style: aiCss = '' } = data.choices?.[0]?.delta || {};
      if (reasoning) aiMsg.reasoning += reasoning;
      if (content) { aiMsg.raw += content; aiMsg.streamHtml += content; aiMsg.streaming = true; }
      if (tokens) aiMsg.tokens = tokens;
      if (aiCss) { applyAiStyle(aiCss); aiMsg.hasAiStyle = true; }
      if (html) { aiMsg.content = sanitizeHtml(html); aiMsg.streaming = false; }
    });
  } catch (error) {
    if (error.name === 'AbortError') {
      aiMsg.streaming = false;
      aiMsg.raw += t('（已中止）', ' (aborted)');
    } else {
      aiMsg.streaming = false;
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
    // 长按回车会连续触发 keydown；生成中按 Enter 不再打断当前流（避免误中止）
    if (e.repeat) return;
    if (loading.value) return;
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
// 未登录时打开提示词工具需先登录
function openPromptTool() {
  if (!guardLogin()) return
  promptToolOpen.value = true
}
// 将生成结果插入输入框
const handlePromptInsert = (text) => {
  inputText.value = text;
  scrollToBottom();
};

// 暴露方法
defineExpose({
  setMessages: (msgList) => {
    messages.value = msgList.map(m => {
      const item = createMessage(m.role, m.content, m.image_url || m.imageUrl);
      // 回填思考过程与 token 用量（历史消息才能显示"深度思考"展开与消耗）
      if (m.reasoning_content) { item.reasoning = m.reasoning_content; item.showReasoning = true; }
      const total = m.total_tokens
        ?? ((m.prompt_tokens || 0) + (m.completion_tokens || 0) || null);
      item.tokens = total;
      return item;
    });
    // 载入历史对话：仅空对话展示开场白
    greetingActive.value = messages.value.length === 0;
    scrollToBottom();
  },
  resetMessages: () => {
    messages.value = [];
    greetingActive.value = true;
    scrollToBottom();
  },
  getMessages: () => messages.value,
  scrollToBottom,
  // 模型配置面板关闭后由父组件调用，刷新输入框模型选择器数据
  reloadProviders: loadChatProviders
});

onMounted(() => {
  scrollToBottom();
  loadChatProviders();
});

onUnmounted(() => {
  abortRequest();
  stopSpeaking();
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
          <el-button circle :icon="Notebook" @click="openPromptTool" />
        </el-tooltip>
        <el-tooltip :content="t('模型设置', 'Model Settings')">
          <el-button circle :icon="Setting" @click="emit('openProvider')" />
        </el-tooltip>
      </div>
    </div>

    <!-- 聊天背景：仅覆盖消息列表 + 输入区，不覆盖顶部栏 -->
    <div class="chat-conversation">
      <div class="chat-bg" :style="bgStyle"></div>

      <!-- 消息列表 -->
      <div class="chat-body">
      <el-scrollbar ref="messageListRef" class="message-scrollbar">
        <div class="message-container">
          <!-- 人设开场白：作为首条消息展示，发送消息/收到回复后不会消失 -->
          <div v-if="showWelcome" class="message-item message-ai greeting-item">
            <div class="message-avatar">
              <div class="avatar-circle assistant">
                <img v-if="aiAvatar" :src="aiAvatar" class="avatar-img" alt="AI" style="cursor: pointer" @click="previewImage(aiAvatar)" />
                <span v-else>AI</span>
              </div>
            </div>
            <div class="message-content">
              <div class="content-text">{{ props.personaGreeting || greetingText() }}</div>
            </div>
          </div>
          <div
            v-for="(item, index) in messages"
            :key="item._key || index"
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
                  style="cursor: pointer"
                  @click="previewImage(aiAvatar)"
                />
                <img
                  v-else-if="item.role === 'user' && userAvatar"
                  :src="userAvatar"
                  class="avatar-img"
                  alt="我"
                  style="cursor: pointer"
                  @click="previewImage(userAvatar)"
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
              
              <!-- 消息内容：生成中渲染后端下发的 HTML 片段（已转义，与成稿一致），
                   流结束后由 sse_html 的完整渲染结果替换。
                   hasAiStyle 的消息加上作用域类，让模型自绘的 CSS 只在本条内生效 -->
              <div v-if="item.streaming" class="content-text streaming-html" :class="{ 'ai-style-scope': item.hasAiStyle }" v-html="item.streamHtml"></div>
              <div v-else-if="item.content" class="content-text" :class="{ 'ai-style-scope': item.hasAiStyle }" v-html="item.content"></div>
              <div v-else-if="item.raw" class="content-text raw-streaming">{{ item.raw }}</div>

              <!-- 加载状态 -->
              <div v-if="item.role === 'assistant' && !item.content && !item.raw && !item.reasoning && !item.imageUrl" class="loading-dots">
                <span></span><span></span><span></span>
              </div>

              <!-- 消息操作 -->
              <div v-if="item.role === 'assistant' && (item.content || item.imageUrl)" class="message-actions">
                <!-- 仅最新一条 AI 回复显示「重新生成」；历史记录只保留语音 -->
                <el-button 
                  v-if="isLatestAssistant(index)"
                  size="small" 
                  text 
                  :icon="RefreshLeft" 
                  @click="regenerate(index)"
                  class="action-btn"
                  :disabled="loading"
                >
                  {{ t('重新生成', 'Regenerate') }}
                </el-button>
                <el-button 
                  v-if="(item.content || item.raw) && !item.imageUrl"
                  size="small" 
                  text 
                  :icon="Bell" 
                  @click="speakText(item.content || item.raw, index)"
                  class="action-btn"
                >
                  {{ speakingIndex === index ? t('播放中', 'Playing') : t('语音', 'Voice') }}
                </el-button>
                <!-- token 消耗：厂商未返回 usage 时不展示 -->
                <span v-if="item.tokens" class="token-usage" :title="t('本次回复消耗的 token 数', 'Tokens used by this reply')">
                  {{ t('消耗', 'Used') }} {{ item.tokens.toLocaleString() }} {{ t('tokens', 'tokens') }}
                </span>
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
            <!-- 当前对话使用的模型（多厂商配置时可在会话内随时切换） -->
            <el-select
              v-if="modelOptions.length"
              v-model="modelSelectValue"
              class="model-select"
              size="small"
              :title="t('选择当前对话使用的模型', 'Choose the model for this chat')"
              @change="handleModelSelect"
            >
              <template #prefix>
                <el-icon><MagicStick /></el-icon>
              </template>
              <el-option-group
                v-for="group in modelOptions"
                :key="group.provider.id"
                :label="group.provider.name"
              >
                <el-option
                  v-for="opt in group.options"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-option-group>
            </el-select>
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
                :aria-label="t('生图', 'Generate image')"
                @click="genMode = genMode === 'text2img' ? '' : 'text2img'"
              >
                <el-icon><Picture /></el-icon>
                <span>{{ t('生图', 'Image') }}</span>
              </button>
              <button
                class="gen-mode-btn"
                :class="{ active: genMode === 'img2img' }"
                :aria-label="t('改图', 'Edit image')"
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
  height: 100dvh;
  background: transparent;
  flex: 1;
  min-width: 0;
  position: relative;
}

/* 聊天背景：仅覆盖消息区 + 输入区，顶部栏保持透明 */
.chat-conversation {
  position: relative;
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.chat-bg {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background-color: transparent;
  background-position: center;
  background-repeat: no-repeat;
}

.chat-body,
.chat-footer {
  position: relative;
  z-index: 1;
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
  flex: 1 1 auto;
  min-width: 0;
}

.chat-title {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
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
  /* 长标题截断，避免把右侧按钮挤出可视区 */
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  max-width: 100%;
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

/* 内容框宽度收窄到 720：配合 Home 的背景智能适配，
   让大多数比例的背景图在 contain 完整显示时也能横向盖住整个聊天框 */
.message-container {
  max-width: 720px;
  margin: 0 auto;
  padding: 24px 20px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* 空对话开场白 */
.chat-welcome {
  max-width: 720px;
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

/* 开场白消息：与普通消息同构，作为首条常驻 */
.greeting-item {
  opacity: 0.95;
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

/* 流式期间展示原文（仅在未收到渲染结果时兜底）：保留换行与 Markdown 语法 */
.content-text.raw-streaming {
  white-space: pre-wrap;
  word-break: break-word;
}

/* 生成中的 HTML 片段：后端已转义并把换行转成 <br>，排版与成稿一致，
   因此不需要 pre-wrap（否则会与成稿的段落间距产生错位） */
.content-text.streaming-html {
  word-break: break-word;
}

/* 段落间距：与流式阶段「空行」的高度（约 1.6em 行高）对齐，
   避免回复结束切换成成稿时段落被挤在一起、看起来很乱 */
.content-text :deep(p) {
  margin: 0 0 1.4em;
}

.content-text :deep(p:last-child) {
  margin-bottom: 0;
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
  align-items: center;
  gap: 4px;
  margin-top: 8px;
  opacity: 0;
  transition: opacity 0.2s;
}

.message-item:hover .message-actions {
  opacity: 1;
}

/* token 消耗：放在操作按钮末尾的轻量文字，hover 时随操作区一起出现 */
.token-usage {
  margin-left: 4px;
  font-size: 11px;
  color: #9ca3af;
  white-space: nowrap;
  user-select: text;
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
  max-width: 720px;
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

/* 输入框模型选择器：紧凑展示当前模型，完整配置名在下拉分组里 */
.model-select {
  width: 168px;
  margin-right: 4px;
}

.model-select :deep(.el-select__wrapper) {
  min-height: 26px;
  border-radius: 999px;
  box-shadow: none;
  background: rgba(120, 130, 145, 0.08);
}

.model-select :deep(.el-select__wrapper:hover),
.model-select :deep(.el-select__wrapper.is-focused) {
  box-shadow: 0 0 0 1px var(--brand) inset;
}

.gen-mode-group {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  margin-left: 8px;
  padding: 2px;
  height: 26px;
  border-radius: 999px;
  border: 1px solid rgba(120, 130, 145, 0.18);
  background: transparent;
}

.gen-mode-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 22px;
  padding: 0 10px;
  border: none;
  border-radius: 999px;
  font-size: 12px;
  color: #6b7280;
  background: transparent;
  cursor: pointer;
  transition: background 0.18s, color 0.18s, box-shadow 0.18s;
  user-select: none;
}

/* 未选中态：纯文字提示，hover 时只做轻微变化以避免误以为已选中 */
.gen-mode-btn:hover {
  color: var(--brand);
  background: rgba(120, 130, 145, 0.06);
}

/* 选中态：明确的色块 + 阴影；
   注：rgba 不支持 calc(...) 嵌套，因此使用静态 0.16 透明度保持稳定。 */
.gen-mode-btn.active {
  color: #fff;
  background: var(--brand);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.12);
}

/* 选中态再 hover 时略提亮，提示「再点一下取消选中」 */
.gen-mode-btn.active:hover {
  filter: brightness(1.08);
}

/* ===== Markdown 渲染排版 =====
   模型输出以标准 Markdown 为主，这里把标题、列表、引用、表格等结构做成
   统一的视觉层级：靠前的留白小、靠后的留白大，避免全篇都是同一种段落。 */
.content-text :deep(h1),
.content-text :deep(h2),
.content-text :deep(h3),
.content-text :deep(h4) {
  margin: 1.4em 0 0.6em;
  font-weight: 650;
  line-height: 1.4;
  color: var(--text-primary);
}
.content-text :deep(h1) { font-size: 1.4em; }
.content-text :deep(h2) {
  font-size: 1.25em;
  padding-bottom: 0.3em;
  border-bottom: 1px solid var(--border-color, rgba(120, 130, 145, 0.18));
}
.content-text :deep(h3) { font-size: 1.1em; }
.content-text :deep(h4) { font-size: 1em; color: var(--text-secondary); }
/* 标题紧跟上一个元素时收紧上间距，避免出现大段空白 */
.content-text :deep(h1:first-child),
.content-text :deep(h2:first-child),
.content-text :deep(h3:first-child),
.content-text :deep(h4:first-child) { margin-top: 0; }

/* 列表：去掉浏览器默认的实心圆点，换成更轻的品牌色标记 */
.content-text :deep(ul),
.content-text :deep(ol) {
  margin: 0 0 1em;
  padding-left: 1.5em;
}
.content-text :deep(li) { margin: 0.3em 0; }
.content-text :deep(ul > li) { list-style: none; position: relative; }
.content-text :deep(ul > li)::before {
  content: '';
  position: absolute;
  left: -0.9em;
  top: 0.72em;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--brand);
  opacity: 0.55;
}
.content-text :deep(ol > li)::marker { color: var(--brand); font-weight: 600; }
/* 嵌套列表略微缩进，层级更清楚 */
.content-text :deep(ul ul),
.content-text :deep(ol ol),
.content-text :deep(ul ol),
.content-text :deep(ol ul) {
  margin: 0.3em 0 0.2em;
}

/* 引用块：左侧竖线 + 浅底，用于强调原文 */
.content-text :deep(blockquote) {
  margin: 0 0 1em;
  padding: 0.6em 1em;
  border-left: 3px solid var(--brand);
  background: rgba(120, 130, 145, 0.07);
  border-radius: 0 8px 8px 0;
  color: var(--text-secondary);
}
.content-text :deep(blockquote > :last-child) { margin-bottom: 0; }

/* 分割线：细一点，两侧留出呼吸感 */
.content-text :deep(hr) {
  margin: 1.6em 0;
  border: none;
  border-top: 1px solid var(--border-color, rgba(120, 130, 145, 0.18));
}

/* 表格：横向可滚动，不撑破消息气泡 */
.content-text :deep(table) {
  width: 100%;
  margin: 0 0 1em;
  border-collapse: collapse;
  font-size: 0.94em;
  display: block;
  overflow-x: auto;
}
.content-text :deep(th),
.content-text :deep(td) {
  padding: 8px 12px;
  border: 1px solid var(--border-color, rgba(120, 130, 145, 0.2));
  text-align: left;
}
.content-text :deep(th) {
  background: rgba(120, 130, 145, 0.09);
  font-weight: 600;
  white-space: nowrap;
}
.content-text :deep(tbody tr:nth-child(even)) {
  background: rgba(120, 130, 145, 0.04);
}

/* 加粗与斜体的强调色，便于扫读 */
.content-text :deep(strong) { font-weight: 650; color: var(--text-primary); }
.content-text :deep(em) { font-style: italic; }

.content-text :deep(img) {
  max-width: 100%;
  border-radius: 8px;
  display: block;
  margin: 0.4em 0;
}
.content-text :deep(pre) {
  background: #1f2937;
  padding: 12px 16px;
  border-radius: 10px;
  overflow-x: auto;
  margin: 0 0 1em;
  line-height: 1.55;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.06);
}
.content-text :deep(code) {
  background: rgba(120, 130, 145, 0.12);
  padding: 2px 6px;
  border-radius: 5px;
  font-size: 0.88em;
  font-family: 'SF Mono', Consolas, monospace;
}
.content-text :deep(pre code) {
  background: none;
  padding: 0;
  color: #e5e7eb;
  font-size: 0.88em;
}
.content-text :deep(a) {
  color: var(--brand);
  text-decoration: none;
  border-bottom: 1px solid rgba(110, 143, 223, 0.4);
  transition: border-color 0.15s ease;
}
.content-text :deep(a:hover) { border-bottom-color: var(--brand); }

/* 高亮标记：==高亮== 是很多模型爱用的强调写法，转成带底色的胶囊标签 */
.content-text mark {
  background: linear-gradient(180deg, transparent 58%, rgba(255, 214, 102, 0.55) 58%);
  color: inherit;
  padding: 0 2px;
  border-radius: 3px;
  font-weight: 600;
}

/* 代码块语言标签：块右上角小字，视觉上更像 IDE */
.content-text :deep(pre) {
  position: relative;
}
.content-text :deep(pre)::before {
  content: 'CODE';
  position: absolute;
  top: 6px;
  right: 10px;
  font-size: 10px;
  letter-spacing: 0.08em;
  color: #6b7280;
  font-family: 'SF Mono', Consolas, monospace;
  pointer-events: none;
}

/* 提示块：把「提示 / 注意 / 警告」这类引用块做成带色边的卡片 */
.content-text :deep(blockquote) {
  position: relative;
  font-size: 0.97em;
}

/* 列表项内的多行内容：第二行起与首行文字对齐 */
.content-text :deep(li > p) { margin: 0 0 0.4em; }
.content-text :deep(li > p:last-child) { margin-bottom: 0; }

/* 有序列表当作「步骤」呈现：序号用圆形浅底，视觉上区分于普通有序列表。
   用 CSS counter 而非 ::marker（兼容性更好），序号由 ol 的计数器驱动。 */
.content-text :deep(ol) {
  counter-reset: step;
}
.content-text :deep(ol > li) {
  position: relative;
  padding-left: 0.2em;
  list-style: none;
}
.content-text :deep(ol > li)::before {
  content: counter(step);
  counter-increment: step;
  position: absolute;
  left: -1.5em;
  top: 0.15em;
  width: 1.5em;
  height: 1.5em;
  border-radius: 50%;
  background: rgba(110, 143, 223, 0.16);
  color: var(--brand);
  font-size: 0.78em;
  font-weight: 700;
  line-height: 1.5em;
  text-align: center;
}

/* ============================================================
   RP 卡片组件库
   模型输出的 HTML 只能使用这里定义的类名来表达结构与视觉，
   由本组件库提供样式（亮/暗双主题），无需模型现写 CSS。
   命名约定：rp- 前缀 = roleplay card
   ============================================================ */

/* 主卡片：圆角 + 描边 + 柔和投影，内层留白舒适 */
:deep(.rp-card) {
  margin: 0.6em 0 1em;
  padding: 16px 18px;
  border-radius: 16px;
  background: var(--surface);
  border: 1px solid var(--border-color);
  box-shadow: var(--shadow-soft);
}
:deep(.rp-card) > :first-child { margin-top: 0; }
:deep(.rp-card) > :last-child { margin-bottom: 0; }

/* 卡片标题：居中大标题 + 可选副标题（对应截图的「🏡 庄园家教日记」） */
:deep(.rp-title) {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin: 0 0 6px;
  font-size: 1.24em;
  font-weight: 700;
  letter-spacing: 0.01em;
  color: var(--text-primary);
  text-align: center;
}
:deep(.rp-sub) {
  margin: 0 0 14px;
  text-align: center;
  font-size: 0.86em;
  color: var(--text-secondary);
}

/* 区块：左侧竖线 + 浅色底，对应截图的「📜 背景」 */
:deep(.rp-section) {
  margin: 0.8em 0;
  padding: 12px 14px;
  border-left: 3px solid var(--brand);
  border-radius: 0 10px 10px 0;
  background: var(--brand-soft);
}
:deep(.rp-section) > :first-child { margin-top: 0; }
:deep(.rp-section) > :last-child { margin-bottom: 0; }
:deep(.rp-section-title) {
  display: block;
  margin: 0 0 6px;
  font-weight: 650;
  color: var(--brand-dark);
}

/* 徽章 / 标签：用于属性、状态等短标记 */
:deep(.rp-badge) {
  display: inline-block;
  margin: 0.2em 0.4em 0.2em 0;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 0.8em;
  font-weight: 600;
  color: var(--brand-dark);
  background: var(--brand-soft);
  border: 1px solid transparent;
}
:deep(.rp-badge-alt) {
  color: #4a6fa5;
  background: rgba(110, 143, 223, 0.14);
}

/* 信息网格：卡片式键值对，比裸表格更适合展示属性 */
:deep(.rp-grid) {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 8px;
  margin: 0.8em 0;
}
:deep(.rp-cell) {
  padding: 8px 10px;
  border-radius: 10px;
  background: var(--surface-hover);
  font-size: 0.9em;
}
:deep(.rp-cell-label) {
  display: block;
  font-size: 0.82em;
  color: var(--text-secondary);
  margin-bottom: 2px;
}

/* 表格：表头带品牌色底 + 斑马纹，横向可滚动 */
:deep(.rp-table-wrap) {
  margin: 0.8em 0;
  overflow-x: auto;
  border-radius: 10px;
  border: 1px solid var(--border-color);
}
:deep(.rp-table) {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9em;
}
:deep(.rp-table) th {
  padding: 8px 10px;
  background: var(--brand);
  color: #fff;
  font-weight: 600;
  text-align: left;
  white-space: nowrap;
}
:deep(.rp-table) td {
  padding: 8px 10px;
  border-top: 1px solid var(--border-color);
  vertical-align: top;
}
:deep(.rp-table) tbody tr:nth-child(even) { background: rgba(120, 130, 145, 0.05); }

/* 折叠分组：对应截图的「▸ 周围其他角色」 */
:deep(.rp-collapse) {
  margin: 0.6em 0;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  background: var(--surface);
  overflow: hidden;
}
:deep(.rp-collapse) > summary {
  padding: 9px 13px;
  cursor: pointer;
  font-weight: 600;
  font-size: 0.94em;
  color: var(--text-primary);
  background: var(--surface-hover);
  list-style: none;
  user-select: none;
}
:deep(.rp-collapse) > summary::-webkit-details-marker { display: none; }
:deep(.rp-collapse) > summary::before {
  content: '▸';
  display: inline-block;
  margin-right: 7px;
  color: var(--brand);
  transition: transform 0.18s ease;
}
:deep(.rp-collapse)[open] > summary::before { transform: rotate(90deg); }
:deep(.rp-collapse-body) {
  padding: 11px 13px;
  border-top: 1px solid var(--border-color);
}
:deep(.rp-collapse-body) > :first-child { margin-top: 0; }
:deep(.rp-collapse-body) > :last-child { margin-bottom: 0; }

/* 引用台词：左侧双竖线 + 斜体，用于角色说话 */
:deep(.rp-quote) {
  margin: 0.7em 0;
  padding: 8px 12px;
  border-left: 3px double var(--brand);
  color: var(--text-secondary);
  font-style: italic;
}

/* 分隔标题：带文字的横向分割线 */
:deep(.rp-divider) {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 1.3em 0 0.7em;
  color: var(--text-secondary);
  font-size: 0.88em;
  font-weight: 600;
}
:deep(.rp-divider)::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border-color);
}

/* 暗色主题下微调：卡片描边与表头更柔和 */
:global(html.dark) .rp-card,
:global(html.dark) .rp-collapse {
  background: rgba(255, 255, 255, 0.04);
}
:global(html.dark) .rp-collapse > summary { background: rgba(255, 255, 255, 0.06); }
:global(html.dark) .rp-table th { background: var(--brand-dark); }

/* 移动端：卡片内边距收紧，网格降为单列 */
@media (max-width: 768px) {
  :deep(.rp-card) { padding: 13px 14px; border-radius: 14px; }
  :deep(.rp-title) { font-size: 1.12em; }
  :deep(.rp-grid) { grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); }
  :deep(.rp-table) { font-size: 0.85em; }
  :deep(.rp-table) th,
  :deep(.rp-table) td { padding: 6px 8px; }
}

/* 移动端：表格与代码块在窄屏更容易溢出，统一压一档字号 */
@media (max-width: 768px) {
  .content-text :deep(table) { font-size: 0.88em; }
  .content-text :deep(th),
  .content-text :deep(td) { padding: 6px 8px; }
  .content-text :deep(pre) { padding: 10px 12px; }
  .content-text :deep(blockquote) { padding: 0.5em 0.8em; }
}

/* 用户气泡是深色底，Markdown 元素需反色，否则标题/表格/引用会看不清 */
.message-user .content-text :deep(a) { color: #fff; border-bottom-color: rgba(255, 255, 255, 0.5); }
.message-user .content-text :deep(code) { background: rgba(255, 255, 255, 0.2); color: #fff; }
.message-user .content-text :deep(strong) { color: #fff; }
.message-user .content-text :deep(h1),
.message-user .content-text :deep(h2),
.message-user .content-text :deep(h3),
.message-user .content-text :deep(h4) { color: #fff; }
.message-user .content-text :deep(h2) { border-bottom-color: rgba(255, 255, 255, 0.3); }
.message-user .content-text :deep(hr) { border-top-color: rgba(255, 255, 255, 0.3); }
.message-user .content-text :deep(blockquote) {
  background: rgba(255, 255, 255, 0.14);
  border-left-color: rgba(255, 255, 255, 0.7);
  color: rgba(255, 255, 255, 0.92);
}
.message-user .content-text :deep(th) {
  background: rgba(255, 255, 255, 0.18);
  color: #fff;
}
.message-user .content-text :deep(td),
.message-user .content-text :deep(th) { border-color: rgba(255, 255, 255, 0.28); }
.message-user .content-text :deep(tbody tr:nth-child(even)) { background: rgba(255, 255, 255, 0.08); }
.message-user .content-text :deep(ul > li)::before { background: #fff; opacity: 0.85; }
.message-user .content-text :deep(ol > li)::marker { color: #fff; }

/* 响应式 */
@media (max-width: 768px) {
  .chat-header {
    padding: 10px 16px 10px 58px;
  }
  .chat-header .header-actions {
    gap: 2px;
  }

  /* 触屏没有 hover：改标题的笔形图标常显（否则用户发现不了可改标题） */
  .edit-icon {
    opacity: 0.6;
  }

  .title-input {
    width: 100%;
    max-width: 200px;
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
    padding-bottom: calc(12px + env(safe-area-inset-bottom));
  }
  
  .message-actions {
    opacity: 1;
  }

  /* ===== 输入区移动端重排 =====
     窄屏工具栏有 7 个控件（模型选择 / 识图 / 语音 / 深思 / 生图 / 改图 / 发送），
     单行必然溢出被挤压。这里改成确定性的两行布局：
       第一行：模型选择器整行独占（完整显示当前模型名，不会被挤成省略号）
       第二行：图标组 + 深思开关 + 生图/改图，发送按钮右下角对齐
     同时放开换行兜底，任何宽度下都不会撑破输入区。 */
  .input-wrapper {
    padding: 6px 8px 2px;
    border-radius: 14px;
  }

  .input-actions {
    align-items: flex-end;
    gap: 8px;
  }

  .action-left {
    flex: 1 1 auto;
    min-width: 0;
    flex-wrap: wrap;
    row-gap: 6px;
  }

  .action-right {
    flex-shrink: 0;
  }

  .model-select {
    flex: 1 1 100%;
    width: auto;
    max-width: 100%;
    margin-right: 0;
  }

  .model-select :deep(.el-select__wrapper) {
    min-height: 28px;
  }

  /* 超长模型名截断而非撑破 */
  .model-select :deep(.el-select__selected-item),
  .model-select :deep(.el-select__placeholder) {
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* 生图/改图：窄屏只留图标（文字语义已由 aria-label 保留） */
  .gen-mode-group {
    margin-left: 4px;
  }

  .gen-mode-btn {
    padding: 0 7px;
  }

  .gen-mode-btn span {
    display: none;
  }

  .deep-think-wrapper {
    margin-left: 4px;
  }

  .deep-think-wrapper :deep(.el-switch__label) {
    font-size: 11px;
  }

  /* iOS Safari 对 font-size < 16px 的输入框聚焦时会自动放大页面，
     破坏 100dvh 全屏布局 —— 移动端统一提到 16px */
  .chat-input :deep(.el-textarea__inner) {
    font-size: 16px;
    padding: 6px 10px;
  }

  /* 触控目标放大到 40px（原 36px 偏小） */
  .send-btn {
    width: 40px;
    height: 40px;
  }
}

/* 超窄屏（iPhone SE 等）再收紧一档 */
@media (max-width: 420px) {
  .chat-header {
    padding: 8px 12px 8px 54px;
  }

  .message-container {
    padding: 12px 10px;
    gap: 12px;
  }

  .avatar-circle {
    width: 28px;
    height: 28px;
    font-size: 11px;
  }

  .message-content {
    max-width: calc(100% - 36px);
  }

  .chat-footer {
    padding: 6px 8px 10px;
    padding-bottom: calc(10px + env(safe-area-inset-bottom));
  }

  .input-wrapper {
    border-radius: 12px;
  }
}
</style>
