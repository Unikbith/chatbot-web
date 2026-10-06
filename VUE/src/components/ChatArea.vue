<script setup>
import { ref, reactive, computed, nextTick, watch, onMounted, onUnmounted } from 'vue';
import logger from '@/utils/logger';
import { ElMessage, ElInput } from 'element-plus';
import { 
  Setting, RefreshLeft, Lightning, 
  Bell, VideoPause, CircleClose, Upload, Edit, MagicStick, Picture, Notebook, Menu, Collection
} from '@element-plus/icons-vue';
import { readStream, chatApi, audioApi, imageApi, providersApi, conversationApi, uploadApi } from '@/utils/resAi';
import auth from '@/utils/auth';
import { sanitizeHtml } from '@/utils/sanitize';
import { hasRichMarkers, GENERIC_MARKERS } from '@/utils/richMessage';
import { templateMarkers } from '@/utils/replyTemplates';
import { renderProse } from '@/utils/proseRender';
import { t } from '../i18n';

import VoiceInput from '@/components/VoiceInput.vue';
import ImageUpload from '@/components/ImageUpload.vue';
import PromptToolPanel from '@/components/PromptToolPanel.vue';
import RichMessage from '@/components/RichMessage.vue';

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
  /** 会话选定的回复渲染模板（已解析的预设对象；为空则用内置基础渲染） */
  replyTemplate: { type: Object, default: null },
  /** 长期记忆（记忆宫殿摘要）：补进「记忆回廊」区块 */
  longTermMemory: { type: Array, default: () => [] },
  loggedIn: { type: Boolean, default: false },
  personaGreeting: { type: String, default: '' },
  backgroundImage: { type: String, default: '' },
  backgroundCover: { type: String, default: 'cover' },
  mobileMenu: { type: Boolean, default: false }
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
  'modelChange',
  // 本轮回复结束：父组件借此刷新长期记忆（记忆回廊）等派生数据
  'reply-done',
  // 后端在流中自动关闭了「提示词兜底」：通知父组件同步开关状态
  'fallback-disabled',
  // 后端在流中自动关闭了「丰富面板内容」：通知父组件同步开关状态
  'prompt-enhance-disabled',
  'toggleSidebar',
  'openMemoryTransfer'
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
  // richRaw：未渲染 Markdown 的原始纯文本，仅当含富标记时保留，供 RichMessage 解析
  id: null, role, content, raw: '', streamHtml: '', streaming: false, reasoning: '', showReasoning: false, imageUrl, tokens: null,
  richRaw: ''
});

/**
 * 富标记落位：仅当原始文本含可渲染标记时，把原文存入 richRaw 交给 RichMessage 渲染。
 *
 * 词表 = 当前模板的标记 + 内置通用标记。必须带上通用标记：
 * 模型偶尔会输出【进度】这类通用标记（尤其受历史消息影响），
 * 若只认模板词表，整条消息会被判定为"无标记"而走普通渲染，
 * 结果就是标记原文直接显示在气泡里（用户看到的"坏了"）。
 */
/**
 * 富渲染落位。
 *
 * 规则：**选了渲染模板时，所有 AI 消息都走模板渲染**（不只是含标记的）。
 * 这样整场对话的输出框风格统一 —— 否则没有标记的短回复会退回应用默认气泡，
 * 同一屏里两种风格混着出现（实测观感很割裂）。
 * 未选模板时才退化为「只有含标记的消息走富渲染」。
 *
 * 词表 = 当前模板的标记 + 内置通用标记。必须带上通用标记：
 * 模型偶尔会输出【进度】这类通用标记（尤其受历史消息影响），
 * 若只认模板词表，整条消息会被判定为"无标记"而走普通渲染，
 * 结果就是标记原文直接显示在气泡里（用户看到的"坏了"）。
 */
const applyRichRaw = (msg) => {
  if (!msg || msg.role !== 'assistant') return;
  if (props.replyTemplate) {
    // 有模板：无论有没有标记都用模板渲染
    msg.richRaw = msg.raw || '';
    return;
  }
  msg.richRaw = hasRichMarkers(msg.raw, null) ? msg.raw : '';
};

/** 当前生效的标记词表：模板词表 + 内置通用标记 */
const richMarkerNames = () => (props.replyTemplate
  ? [...templateMarkers(props.replyTemplate), ...GENERIC_MARKERS]
  : null);

/**
 * 流式期间的富渲染。
 *
 * 之前只在流结束后才判定富渲染，于是长回复会先以"普通气泡"的样子输出，
 * 结束时再整体换成模板样式 —— 视觉上明显的跳变/替换。
 * 这里在流式过程中就按累计文本实时判定，让模板从第一个字就开始渲染。
 *
 * 节流：长文（几千 token）逐字重解析代价高，故最多每 120ms 刷新一次；
 * 流结束时再无条件刷新一次，保证最终结果准确。
 */
const RICH_STREAM_INTERVAL = 120;
function applyRichRawStreaming(msg, force = false) {
  if (!msg) return;
  // 有模板时无需等待标记出现：从一开始就用模板渲染，避免"先生成完再整体换样式"
  if (props.replyTemplate) {
    const now = Date.now();
    if (!force && msg.richAt && now - msg.richAt < RICH_STREAM_INTERVAL) return;
    msg.richAt = now;
    msg.richRaw = msg.raw || '';
    return;
  }
  if (!hasRichMarkers(msg.raw, richMarkerNames())) {
    // 没有模板且尚未出现标记：先不启用富渲染，避免每条消息都白解析一遍
    if (msg.richRaw) msg.richRaw = '';
    return;
  }
  const now = Date.now();
  if (!force && msg.richAt && now - msg.richAt < RICH_STREAM_INTERVAL) return;
  msg.richAt = now;
  msg.richRaw = msg.raw;
}

// 选项点击：填入输入框但不自动发送（沿用项目「按钮默认填输入框」的既有习惯，
// 是否发送由用户自己决定，避免误触直接消耗额度）
const handlePickOption = (textValue) => {
  inputText.value = textValue;
  nextTick(() => {
    const el = document.querySelector('.chat-input textarea, .chat-input input');
    if (el && typeof el.focus === 'function') el.focus();
  });
};

// ── 按会话隔离的消息仓库 ─────────────────────────────────────────
// 旧实现：所有会话共用同一个 messages 数组，切换对话时整体替换。
// 后果有两个，正是本次要修的：
//   1) 切走时正在流式的那条消息被摘出数组 → 看起来「切走就打断回复」；
//   2) 切回来又从服务端重新拉取 → 还没落库的进行中回复彻底消失。
// 改为每个会话一份数组：切走只是不显示，流继续在后台跑完并落库，
// 切回来时若该会话仍在流式，就继续展示本地那份（不覆盖）。
const convStores = new Map();          // convKey -> ref([])
const storeKey = (id) => (id == null ? '__new__' : String(id));
function storeFor(id) {
  const k = storeKey(id);
  if (!convStores.has(k)) convStores.set(k, ref([]));
  return convStores.get(k);
}
// 当前展示的会话对应的数组（写操作请用各发送函数里捕获的 list，见下）
const messages = computed(() => storeFor(props.conversationId).value);

// 正在流式回复的会话（Set 里的元素是 convKey）
const activeStreams = ref(new Set());
// 每个会话一个中止控制器：A 在后台跑时 B 也能正常发送/中止，互不干扰
const abortControllers = new Map();
// 「正在回复」按会话判定：切到别的会话时，按钮不该显示成停止
const loading = computed(() => activeStreams.value.has(storeKey(props.conversationId)));

const inputText = ref('');
const messageListRef = ref(null);
const deepThink = ref(false);

// ── 草稿：按会话保存未发送的文字与图片 ───────────────────────────
// 切走时存起来、切回来时还回去，避免「打了一半切个对话就全没了」。
const drafts = new Map();              // convKey -> { text, image }
function saveDraft(key) {
  if (inputText.value || selectedImage.value) {
    drafts.set(key, { text: inputText.value, image: selectedImage.value });
  } else {
    drafts.delete(key);
  }
}
function restoreDraft(key) {
  const d = drafts.get(key);
  inputText.value = d?.text || '';
  if (d?.image) {
    selectedImage.value = d.image;
    imageUploadRef.value?.setImage(d.image);   // 同步上传组件的缩略图
  } else {
    selectedImage.value = null;
    imageUploadRef.value?.clearImage();
  }
}
// 会话切换：先把旧会话的输入存好，再恢复新会话的
watch(() => props.conversationId, (newId, oldId) => {
  if (storeKey(newId) === storeKey(oldId)) return;
  saveDraft(storeKey(oldId));
  restoreDraft(storeKey(newId));
});

/**
 * 渲染模板变化时，重新判定屏幕上已有消息的富渲染状态。
 *
 * 必要性：richRaw 是在消息流结束时按「当时的模板词表」判定并写下的。
 * 用户在会话设置里切换模板后，旧消息的 richRaw 仍是旧结果，
 * 于是新模板对它们不生效 —— 表现为"改了模板却看不出效果，必须重新发消息或刷新"。
 * 这里在模板变化时按新词表重算一遍。
 */
watch(() => props.replyTemplate, () => {
  for (const m of messages.value) {
    if (m.role === 'assistant' && m.raw) applyRichRaw(m);
  }
});

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
const isPaused = ref(false);     // 当前是否处于暂停（而非播放中）
const speakingIndex = ref(null); // 正在播报的消息索引（用于显示「播报中」）
let audioElement = null;

// ===== TTS 结果缓存 =====
// 同一段文本反复点「语音」会重复请求厂商（既慢又消耗额度），这里按
// 「音色 + 文本」缓存 blob URL；命中缓存直接播放，不再发请求。
const TTS_CACHE_MAX = 30; // 上限，超出按插入顺序淘汰最早的（简易 LRU）
const ttsCache = new Map();

function ttsCacheKey(voice, text) {
  // 文本可能很长，用「长度 + 首尾片段」做指纹，避免超长 key
  return `${voice || ''}|${text.length}|${text.slice(0, 40)}|${text.slice(-40)}`;
}

function ttsCacheGet(voice, text) {
  const key = ttsCacheKey(voice, text);
  if (!ttsCache.has(key)) return null;
  // 命中后挪到末尾，维持插入顺序（最近使用的排在最后）
  const url = ttsCache.get(key);
  ttsCache.delete(key);
  ttsCache.set(key, url);
  return url;
}

function ttsCacheSet(voice, text, url) {
  const key = ttsCacheKey(voice, text);
  if (ttsCache.has(key)) URL.revokeObjectURL(ttsCache.get(key));
  ttsCache.set(key, url);
  while (ttsCache.size > TTS_CACHE_MAX) {
    const oldest = ttsCache.keys().next().value;
    URL.revokeObjectURL(ttsCache.get(oldest));
    ttsCache.delete(oldest);
  }
}

// 移动端（Android/iOS）浏览器要求：音频元素的首次 play() 必须发生在用户手势的
// 「同步」上下文中。而合成语音要 await 几百毫秒~数秒，等拿到 blob 再 play()
// 手势上下文早已失效，浏览器会静默拒绝 -> 表现为「请求 200 但没声音」。
// 因此在点击的同步阶段先用一个静音片段解锁，之后异步播放才被允许。
let audioUnlocked = false;
const MUTED_UNLOCK_WAV = 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQQAAAD//w==';

function unlockAudio() {
  if (audioUnlocked) return;
  try {
    const el = new Audio(MUTED_UNLOCK_WAV);
    el.muted = true;
    const p = el.play();
    if (p && typeof p.catch === 'function') {
      p.then(() => { el.pause(); audioUnlocked = true; }).catch(() => {});
    } else {
      audioUnlocked = true;
    }
  } catch {
    // 解锁失败不阻断，后续播放会走正常报错路径
  }
}

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

// 请求中止：只中止当前这个会话的流（别的会话在后台跑的不受影响）
const abortRequest = () => {
  const key = storeKey(props.conversationId);
  abortControllers.get(key)?.abort();
  abortControllers.delete(key);
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
// preferId：由调用方传入「发起发送那一刻」的会话 id；缺省才回落到 props。
// 必须显式传 —— 若会话是在本次发送中新建的，创建请求往返期间用户可能已切走，
// 此时 props 已是别人的，再读就会把消息写进错误的会话。
const ensureConversation = async (preferId = null) => {
  const existing = preferId ?? props.conversationId;
  if (existing) return existing;
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

// 发送前把「本次请求要用的会话参数」一次性快照下来。
// 必须在任何 await 之前：发送过程中用户随时可能切到别的会话，props 会立刻变成对方的值，
// 若在 await 之后才读，本次请求就会带上别人的人设 / 模型 / 温度 —— 表现正是
//「A 还在思考时切到 B 再切回 A，A 的回复却按 B 的设定来」。
function snapshotRequestContext() {
  return {
    conversationId: props.conversationId,
    systemPrompt: props.systemPrompt,
    providerId: props.providerId,
    modelId: props.modelId,
    temperature: props.temperature,
    deepThink: deepThink.value,
  };
}

// 发送消息
const handleSend = async () => {
  if (loading.value) { abortRequest(); return; }
  if (!guardLogin()) return;

  const text = inputText.value.trim();
  if (!text && !selectedImage.value) return;

  const ctx = snapshotRequestContext();

  // 先拿到会话 id（已有会话时是同步返回，不会延迟上屏），
  // 之后所有消息都写进这个会话自己的数组 —— 中途切走也不会被顶掉。
  const convId = await ensureConversation(ctx.conversationId);
  if (!convId) { ElMessage.error(t('创建对话失败', 'Failed to create conversation')); return; }
  const list = storeFor(convId);

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

  // 如果有图片，走识图接口（传原始文本：空文本由函数内部区分「展示」与「发送」）
  if (selectedImage.value) {
    await handleVisionChat(text);
    return;
  }

  list.value.push(createMessage('user', text));
  inputText.value = '';
  // 用户发送消息后立即定位到底部（AI 生成过程中不强制滚动）
  scrollToBottom();

  const aiIndex = list.value.length;
  const aiMsg = reactive(createMessage('assistant'));
  list.value.push(aiMsg);

  const streamKey = storeKey(convId);
  activeStreams.value.add(streamKey);
  const ctrl = new AbortController();
  abortControllers.set(streamKey, ctrl);

  try {
    const requestBody = {
      messages: list.value.slice(0, -1).map(({ role, content }) => ({ role, content })),
      deep_think: ctx.deepThink,
      system_prompt: ctx.systemPrompt,
      temperature: ctx.temperature,
      provider_id: ctx.providerId,
      model_id: ctx.modelId || undefined,
      conversation_id: convId,
    };

    const response = await chatApi.stream(requestBody, { signal: ctrl.signal });
    await readStream(response, (data) => {
      const { reasoning_content: reasoning = '', content = '', html = '', tokens = null } = data.choices?.[0]?.delta || {};
      if (data.choices?.[0]?.delta?.append_prompt_enabled === false) emit('fallback-disabled', convId);
      if (data.choices?.[0]?.delta?.prompt_enhance_disabled === true) emit('prompt-enhance-disabled', convId);
      if (reasoning) aiMsg.reasoning += reasoning;
      if (content) { aiMsg.raw += content; aiMsg.streamHtml = sanitizeHtml(aiMsg.raw); aiMsg.streaming = true; applyRichRawStreaming(aiMsg); }
      if (tokens) aiMsg.tokens = tokens;
      if (data.choices?.[0]?.delta?.message_id) aiMsg.id = data.choices[0].delta.message_id;
      if (html) { aiMsg.content = sanitizeHtml(html); aiMsg.streaming = false; }
    });

    // 防御：流结束但未收到最终 html delta（异常/部分 provider 未下发）时，
    // 用已累积的原文兜底显示，并结束 streaming 态，避免消息空白或一直转圈。
    if (aiMsg.streaming) {
      aiMsg.streaming = false
      if (!aiMsg.content && aiMsg.raw) {
        aiMsg.content = sanitizeHtml(aiMsg.raw)
      }
    }

    // 流结束：无条件刷新一次富渲染（绕过节流），保证最终结果准确
    applyRichRawStreaming(aiMsg, true);
    // 通知父组件刷新长期记忆：本轮可能刚触发一次记忆宫殿压缩
    emit('reply-done', convId);

    // 自动播报 AI 回复（该对话开启时）
    if (props.autoPlayVoice && aiMsg.content && !aiMsg.imageUrl) {
      speakText(aiMsg.content, aiIndex);
    }

    // 更新对话标题（第一条用户消息）
    // 带上 convId：回复可能在后台跑完（用户已切到别的会话），
    // 父组件据此把标题写到正确的会话上，而不是写到当前显示的那个。
    if (list.value.filter(m => m.role === 'user').length === 1) {
      const title = text.length > 20 ? text.substring(0, 20) + '...' : text;
      emit('titleChange', { convId, title });
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
    abortControllers.delete(streamKey);
    activeStreams.value.delete(streamKey);
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

// 识图时判断用户是否真的想「改这张图」：只有出现明确的修改/生成类动词才算。
// 只发图（文本为空）、或问「这是什么 / 图里有几个人 / 帮我分析」都属识图，不能注入改图能力。
const IMAGE_EDIT_RE = /(改成|改一下|改一改|修改|换成|变成|做成|画成|画一张|重画|重新画|生成一张|加个|加上|加点|去掉|删掉|删除|调整|美化|优化一下|加个滤镜|换背景|改背景|变成.+色)/;

function wantsImageEdit(text) {
  const s = (text || '').trim();
  if (!s) return false;
  return IMAGE_EDIT_RE.test(s);
}

/**
 * 把本地图片换算成服务器 URL（用于消息落库）。
 * 支持传 File（上传框选的图）或 base64 data URL（改图参考图）。
 * 失败返回 null —— 调用方据此放弃「历史留图」，但不阻断生图本身。
 */
async function persistImageUrl(src) {
  if (!src) return null;
  try {
    let file = src;
    if (typeof src === 'string' && src.startsWith('data:')) {
      const blob = await (await fetch(src)).blob();
      const ext = (blob.type.split('/')[1] || 'png').replace('jpeg', 'jpg');
      file = new File([blob], `ref.${ext}`, { type: blob.type || 'image/png' });
    }
    const up = await uploadApi.uploadImage(file);
    if (up && up.code === 200 && up.data?.url) return up.data.url;
    return null;
  } catch (e) {
    logger.warn('参考图上传失败（不影响生图）', e);
    return null;
  }
}

// 从模型回复里提取「改图」标记，结合参考图代为调用图生图，结果附到该消息。
// 仅用于「识图 + 用户明确要求改图」的场景（见 handleVisionChat）：
// 用户主动上传图片并要求修改时，模型输出一行 `改图：<要求>`，前端据此调用图生图。
// 普通纯文字对话不再走这条链路（原「启用大模型原生工具」开关已下线），
// 避免模型随口输出标记就触发真实生图、白耗额度。
async function handleLlmImageMarkers(msg, reference = null, ownerConvId = null) {
  const src = msg.raw || msg.content || '';
  if (!src) return;
  // 只认「改图：」标记，且必须位于行首（m flag）：
  // 正文中间出现的「…可以改图：xxx」不应误触发真实生图
  const marker = src.match(/^[ \t]*改图[:：][ \t]*([^\n]+)/m);
  if (!marker) return;
  const prompt = marker[1].trim();
  // 移除标记行，保留可读文本；流式原文与最终 HTML 都去掉标记
  msg.raw = ((msg.raw || '').replace(marker[0], '') || '').trim();
  msg.content = ((msg.content || '').replace(marker[0], '') || '').trim();
  try {
    // 把用户上传的图作为参考图传入，实现「结合人设 + 参考图生成新图」
    const useRef = reference ? [reference] : [];
    // 带上会话与参考图 URL，让这次生图进入对话历史（否则切走对话就消失）
    // 用发起识图时定下的会话：用户可能已切走，此时 props 指向的是别的会话
    const convId = ownerConvId || await ensureConversation();
    const refUrl = await persistImageUrl(reference);
    const res = await imageApi.generate({
      prompt,
      references: useRef,
      conversation_id: convId,
      reference_url: refUrl,
    });
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
  const ctx = snapshotRequestContext();
  // 仅改图需要带上参考图；生图为文生图
  const prompt = text || t('生成一张图片', 'Generate an image');
  const convId = await ensureConversation(ctx.conversationId);
  if (!convId) { ElMessage.error(t('创建对话失败', 'Failed to create conversation')); return; }
  const list = storeFor(convId);

  list.value.push(createMessage('user', prompt, isEdit ? selectedImage.value?.dataUrl || null : null));
  const refDataUrl = isEdit ? selectedImage.value?.dataUrl : null;
  inputText.value = '';
  imageUploadRef.value?.clearImage();
  scrollToBottom();

  const aiMsg = reactive(createMessage('assistant'));
  list.value.push(aiMsg);

  const streamKey = storeKey(convId);
  activeStreams.value.add(streamKey);
  const ctrl = new AbortController();
  abortControllers.set(streamKey, ctrl);
  try {
    // 带上会话与参考图 URL：让这次生图写进对话历史（否则切走对话后整段消失）
    const refUrl = isEdit ? await persistImageUrl(refDataUrl) : null;
    const res = await imageApi.generate({
      prompt,
      references: refDataUrl ? [refDataUrl] : [],
      conversation_id: convId,
      reference_url: refUrl,
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
    abortControllers.delete(streamKey);
    activeStreams.value.delete(streamKey);
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
  // 展示与发送分离：聊天框只显示用户真写的字（空则纯图，不替用户说话）；
  // 发给模型时若为空则用一个自然占位，避免退化成「客观描述任务」
  const shownText = (text || '').trim()
  const visionText = shownText || t('（用户发来了一张图片，没说话，想让你看看）', '(The user sent an image without saying anything — just showing you)')
  // 关键：在任何 await 之前快照会话参数。图片上传是一次真实网络往返，
  // 期间用户完全可以切到别的会话，等下面再读 props.systemPrompt 就已经是对方的了。
  const ctx = snapshotRequestContext();

  const convId = await ensureConversation(ctx.conversationId);
  if (!convId) { ElMessage.error(t('创建对话失败', 'Failed to create conversation')); return; }
  const list = storeFor(convId);

  const userMsg = reactive(createMessage('user', shownText, refDataUrl))
  list.value.push(userMsg)
  inputText.value = '';
  imageUploadRef.value?.clearImage();
  // 用户发送消息后立即定位到底部
  scrollToBottom();

  const aiMsg = reactive(createMessage('assistant'));
  list.value.push(aiMsg);

  const streamKey = storeKey(convId);
  activeStreams.value.add(streamKey);
  const ctrl = new AbortController();
  abortControllers.set(streamKey, ctrl);

  // 上传图片换取服务器 URL 用于聊天记录留图：先 base64 立即上屏（不卡 UI），
  // 上传成功后换成 URL（reactive 才会触发视图更新）；失败只 warn 不阻断识图，
  // 后端还有落盘兜底，两条路保证图片能进历史。
  let imageUrl = null
  if (img?.file) {
    try {
      const up = await uploadApi.uploadImage(img.file)
      if (up && up.code === 200 && up.data?.url) {
        imageUrl = up.data.url
        userMsg.imageUrl = imageUrl
      }
    } catch (e) {
      logger.warn('识图图片上传失败（后端会兜底落盘）', e)
    }
  }

  try {
    const formData = new FormData();
    formData.append('text', visionText);
    formData.append('image', img?.file);
    if (ctx.providerId) {
      formData.append('provider_id', ctx.providerId);
    }
    // 必须带 model_id：否则后端落到厂商「默认 model」（通常非多模态），识图必然失败
    if (ctx.modelId) {
      formData.append('model_id', ctx.modelId);
    }
    // 深度思考跟随输入框按钮，不再恒开（后端缺省是关闭）
    formData.append('deep_think', ctx.deepThink ? '1' : '0');
    if (convId) {
      formData.append('conversation_id', convId);
    }
    if (imageUrl) {
      formData.append('image_url', imageUrl);
    }
    // 系统提示分两种：
    //  ① 用户明确要改这张图 → 给生图/改图能力（模型输出标记，前端代为生图）
    //  ② 其余情况（只发图、问「这是什么」）→ 给「角色化图片回应」指令：
    //     让模型以角色本人身份、用自己的口吻对图片作出反应，
    //     而不是退化成助手口吻的客观描述员。
    const personaPrompt = (ctx.systemPrompt || '').trim();
    const sysExtra = wantsImageEdit(shownText)
      ? '\n\n[系统能力-图片生成] 用户明确要求修改或重新生成这张图，此时只回复一行：`改图：<用中文描述修改要求>`，用户上传的图片会自动作为参考图使用，不要输出其它解释。'
      : '\n\n[图片回应] 用户发来了一张图片。你就是设定里的这个角色本人，请像用户当面给你看东西那样，用你自己的人设、语气和情绪自然回应（惊讶、好奇、评价、关心、调侃都可以），把它当成你们对话的延续。不要用「这是一张图片」「图中可以看到」这类客观描述的第三方口吻，也不要罗列图片内容清单，除非用户明确要求你描述或分析图片。';
    formData.append('system_prompt', (personaPrompt + sysExtra).trim());

    const response = await chatApi.vision(formData, { signal: ctrl.signal });
    await readStream(response, (data) => {
      const { reasoning_content: reasoning = '', content = '', html = '', tokens = null } = data.choices?.[0]?.delta || {};
      if (data.choices?.[0]?.delta?.append_prompt_enabled === false) emit('fallback-disabled', convId);
      if (data.choices?.[0]?.delta?.prompt_enhance_disabled === true) emit('prompt-enhance-disabled', convId);
      if (reasoning) aiMsg.reasoning += reasoning;
      if (content) { aiMsg.raw += content; aiMsg.streamHtml = sanitizeHtml(aiMsg.raw); aiMsg.streaming = true; applyRichRawStreaming(aiMsg); }
      if (tokens) aiMsg.tokens = tokens;
      if (data.choices?.[0]?.delta?.message_id) aiMsg.id = data.choices[0].delta.message_id;
      if (html) { aiMsg.content = sanitizeHtml(html); aiMsg.streaming = false; }
    });

    // 防御：流结束但未收到最终 html delta 时，用已累积的原文兜底显示，并结束 streaming 态。
    if (aiMsg.streaming) {
      aiMsg.streaming = false
      if (!aiMsg.content && aiMsg.raw) {
        aiMsg.content = sanitizeHtml(aiMsg.raw)
      }
    }

    // 模型若输出「改图」标记，则结合人设与用户上传的参考图自动生图并贴到本条回复
    await handleLlmImageMarkers(aiMsg, refDataUrl, convId);

    // 流结束：无条件刷新一次富渲染（用 raw 而非 content，后者已被渲染成 HTML）
    applyRichRawStreaming(aiMsg, true);

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
    abortControllers.delete(streamKey);
    activeStreams.value.delete(streamKey);
  }
};

// 语音播报
// 保存当前播放的 object URL，便于在停止/卸载时释放，避免 blob 常驻内存
let currentAudioUrl = null;
// 语音合成请求令牌：合成是异步的，用于丢弃过期响应（见 speakText）
let speakReqSeq = 0;

const speakText = async (text, index) => {
  // 必须在 await 之前、仍处于用户手势同步上下文时解锁音频（移动端硬性要求）
  unlockAudio();
  stopSpeaking();
  
  const plainText = text.replace(/<[^>]+>/g, '').trim();
  if (!plainText) return;

  // 播放请求令牌：合成是异步的，期间用户可能又点了别的语音按钮。
  // 没有令牌时后到的响应会覆盖当前播放对象、造成"点了没声音"。
  const reqId = ++speakReqSeq;

  try {
    // 音色使用 TTS 模型配置中的音色（不传 voice，由后端按提供商配置决定）
    const voice = '';
    // 命中缓存直接复用音频，不再向厂商发请求
    let url = ttsCacheGet(voice, plainText);
    if (!url) {
      const blob = await audioApi.textToSpeech(plainText, voice);
      // 合成期间已被更新的请求取代，丢弃本次结果
      if (reqId !== speakReqSeq) return;
      url = URL.createObjectURL(blob);
      ttsCacheSet(voice, plainText, url);
    }
    // 缓存中的 URL 由缓存自己管理生命周期，不随本次播放释放
    currentAudioUrl = null;

    audioElement = new Audio(url);
    // 移动端：游离的 <audio> 在部分浏览器不播放，需挂到 DOM；
    // playsinline 可避免 iOS 把音频交给全屏播放器接管。
    audioElement.setAttribute('playsinline', '');
    audioElement.preload = 'auto';
    audioElement.style.display = 'none';
    document.body.appendChild(audioElement);

    // 注意：这里的 URL 来自缓存，由缓存负责释放，不能在此 revoke，
    // 否则缓存里下一次命中会拿到已失效的 URL。
    const cleanup = () => {
      isSpeaking.value = false;
      isPaused.value = false;
      speakingIndex.value = null;
      try { audioElement?.pause(); } catch { /* 忽略 */ }
      if (audioElement?.parentNode) audioElement.parentNode.removeChild(audioElement);
      audioElement = null;
    };

    audioElement.onended = cleanup;
    audioElement.onerror = (e) => {
      logger.error('语音播放失败', e);
      cleanup();
    };
    isSpeaking.value = true;
    isPaused.value = false;
    speakingIndex.value = index;
    // play() 在部分浏览器/移动端会因自动播放策略返回 rejected Promise，
    // 不 catch 会变成 unhandled rejection，用户只看到"没声音"却没有提示。
    try {
      await audioElement.play();
    } catch (pe) {
      cleanup();
      // 移动端最常见的失败原因：仍被自动播放策略拦截
      throw new Error('浏览器阻止了自动播放，请再次点击语音按钮');
    }
  } catch (e) {
    logger.error('语音合成失败', e);
    ElMessage.warning(`语音播报失败：${e.message || '音频无法播放'}`);
  }
};

// 点击「语音」按钮的统一入口：同一条正在播放时暂停/继续，而不是重新合成。
function toggleSpeak(text, index) {
  const isCurrentTrack = speakingIndex.value === index && audioElement;
  if (isCurrentTrack) {
    if (audioElement.paused) {
      audioElement.play().then(() => {
        isPaused.value = false;
      }).catch(() => {
        ElMessage.warning('播放被浏览器阻止，请稍后重试');
      });
    } else {
      audioElement.pause();
      isPaused.value = true;
    }
    return;
  }
  // 另一条（或首次点击）：正常合成并播放
  speakText(text, index);
}

// 释放当前音频对象 URL（幂等）
const releaseAudioUrl = () => {
  if (currentAudioUrl) {
    try { URL.revokeObjectURL(currentAudioUrl); } catch { /* 忽略 */ }
    currentAudioUrl = null;
  }
};

const stopSpeaking = () => {
  // 递增令牌：作废仍在合成途中的旧请求，避免其响应回来后覆盖当前播放
  speakReqSeq++;
  if (audioElement) {
    audioElement.onended = null;
    audioElement.onerror = null;
    audioElement.pause();
    audioElement.src = '';
    // 播放时把元素挂到了 DOM 上（移动端需要），这里一并移除避免残留节点
    if (audioElement.parentNode) audioElement.parentNode.removeChild(audioElement);
    audioElement = null;
  }
  releaseAudioUrl();
  isSpeaking.value = false;
  isPaused.value = false;
  speakingIndex.value = null;
};

// 仅“最新一条”AI 消息允许重新生成
const isLatestAssistant = (index) => {
  if (!messages.value[index] || messages.value[index].role !== 'assistant') return false
  return index === messages.value.length - 1
};

// 重新生成
const regenerate = async (assistantIndex = null) => {
  const ctx = snapshotRequestContext();
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

  const convId = await ensureConversation(ctx.conversationId);
  if (!convId) return;
  const list = storeFor(convId);

  const oldAssistant = list.value[assistantIndex]
  if (oldAssistant?.id) {
    try {
      await conversationApi.deleteBranch(convId, oldAssistant.id)
    } catch (e) {
      ElMessage.error(t('旧回复删除失败，请刷新后重试', 'Could not replace the old reply. Refresh and try again.'))
      return
    }
  }
  // 服务端已删除旧分支后，再同步裁剪本地视图
  list.value = list.value.slice(0, userIndex + 1);
  
  // 重新发送
  const aiMsg = reactive(createMessage('assistant'));
  list.value.push(aiMsg);
  
  const streamKey = storeKey(convId);
  activeStreams.value.add(streamKey);
  const ctrl = new AbortController();
  abortControllers.set(streamKey, ctrl);

  try {
    const requestBody = {
      messages: list.value.slice(0, -1).map(({ role, content }) => ({ role, content })),
      deep_think: ctx.deepThink,
      system_prompt: ctx.systemPrompt,
      temperature: ctx.temperature,
      provider_id: ctx.providerId,
      model_id: ctx.modelId || undefined,
      conversation_id: convId,
    };

    const response = await chatApi.stream(requestBody, { signal: ctrl.signal });
    await readStream(response, (data) => {
      const { reasoning_content: reasoning = '', content = '', html = '', tokens = null } = data.choices?.[0]?.delta || {};
      if (data.choices?.[0]?.delta?.append_prompt_enabled === false) emit('fallback-disabled', convId);
      if (data.choices?.[0]?.delta?.prompt_enhance_disabled === true) emit('prompt-enhance-disabled', convId);
      if (reasoning) aiMsg.reasoning += reasoning;
      if (content) { aiMsg.raw += content; aiMsg.streamHtml = sanitizeHtml(aiMsg.raw); aiMsg.streaming = true; applyRichRawStreaming(aiMsg); }
      if (tokens) aiMsg.tokens = tokens;
      if (data.choices?.[0]?.delta?.message_id) aiMsg.id = data.choices[0].delta.message_id;
      if (html) { aiMsg.content = sanitizeHtml(html); aiMsg.streaming = false; }
    });

    // 防御：流结束但未收到最终 html delta 时，用已累积的原文兜底显示，并结束 streaming 态。
    if (aiMsg.streaming) {
      aiMsg.streaming = false
      if (!aiMsg.content && aiMsg.raw) {
        aiMsg.content = sanitizeHtml(aiMsg.raw)
      }
    }

    // 流结束：无条件刷新一次富渲染（绕过节流），保证最终结果准确
    applyRichRawStreaming(aiMsg, true);
    // 通知父组件刷新长期记忆：本轮可能刚触发一次记忆宫殿压缩
    emit('reply-done', convId);

  } catch (error) {
    if (error.name === 'AbortError') {
      aiMsg.streaming = false;
      aiMsg.raw += t('（已中止）', ' (aborted)');
    } else {
      aiMsg.streaming = false;
      aiMsg.content = `出错了：${error.message || '网络异常'}`;
    }
  } finally {
    abortControllers.delete(streamKey);
    activeStreams.value.delete(streamKey);
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
  // convId 显式传入：父组件切换会话时 props 还没更新完，用它定位仓库才不会写错格子
  setMessages: (convId, msgList) => {
    const list = storeFor(convId);
    // 该会话正在流式回复 → 保留本地正在写的这份，
    // 否则服务端数据（还没有这条回复）会把进行中的回复整个盖掉。
    if (activeStreams.value.has(storeKey(convId))) {
      // 保留本地视图的同时同步开场白状态，避免空/非空判断停留在上一次会话
      greetingActive.value = list.value.length === 0;
      scrollToBottom();
      return;
    }
    list.value = msgList.map(m => {
      // 优先用后端渲染好的 HTML（content_html），避免纯文本进 v-html 把段落压成一行；
      // 老数据或渲染失败时回退原 content
      const item = createMessage(m.role, m.content_html || m.content, m.image_url || m.imageUrl);
      item.id = m.id || null;
      // 历史消息：富标记按原始纯文本重建（content 已是 HTML，无法再解析标记）
      if (m.role === 'assistant' && m.content) {
        item.raw = m.content;
        applyRichRaw(item);
      }
      // 回填思考过程与 token 用量（历史消息才能显示"深度思考"展开与消耗）
      if (m.reasoning_content) { item.reasoning = m.reasoning_content; item.showReasoning = true; }
      const total = m.total_tokens
        ?? ((m.prompt_tokens || 0) + (m.completion_tokens || 0) || null);
      item.tokens = total;
      return item;
    });
    // 载入历史对话：仅空对话展示开场白
    greetingActive.value = list.value.length === 0;
    scrollToBottom();
  },
  resetMessages: (convId) => {
    storeFor(convId).value = [];
    greetingActive.value = true;
    scrollToBottom();
  },
  getMessages: () => messages.value,
  // 该会话是否正在流式回复：父组件据此判断能否安全重载
  isStreaming: (convId) => activeStreams.value.has(storeKey(convId)),
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
        <button v-if="mobileMenu" class="chat-menu-btn" type="button" @click="emit('toggleSidebar')">
          <el-icon><Menu /></el-icon>
        </button>
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
        <el-tooltip :content="t('聊天记忆', 'Chat Memory')">
          <el-button circle :icon="Collection" @click="emit('openMemoryTransfer')" />
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
              <!-- 开场白同样走模板渲染：否则新对话的第一条消息会是应用默认气泡样式，
                   与后续回复风格不一致（实测观感是"新对话没套上模板"） -->
              <RichMessage
                v-if="replyTemplate"
                :raw="props.personaGreeting || greetingText()"
                :render-text="renderProse"
                :template="replyTemplate"
                variant="greeting"
                @pick-option="handlePickOption"
              />
              <div v-else class="content-text">{{ props.personaGreeting || greetingText() }}</div>
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
              
              <!-- 消息内容渲染优先级：
                   1) 命中富标记 -> RichMessage。模板样式从第一个字就开始渲染，
                      避免"先按普通气泡输出、结束后再整体替换"的跳变
                   2) 流式中 -> 后端下发的 HTML 片段
                   3) 成稿 -> 后端渲染好的完整 HTML
                   4) 兜底 -> 原始文本 -->
              <RichMessage
                v-if="item.richRaw"
                :raw="item.richRaw"
                :render-text="renderProse"
                :template="replyTemplate"
                :long-term-memory="longTermMemory"
                @pick-option="handlePickOption"
              />
              <div v-else-if="item.streaming" class="content-text streaming-html" v-html="item.streamHtml"></div>
              <div v-else-if="item.content" class="content-text" v-html="item.content"></div>
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
                  :icon="speakingIndex === index && !isPaused ? VideoPause : Bell"
                  @click="toggleSpeak(item.content || item.raw, index)"
                  class="action-btn"
                >
                  <template v-if="speakingIndex === index">
                    {{ isPaused ? t('继续', 'Resume') : t('暂停', 'Pause') }}
                  </template>
                  <template v-else>{{ t('语音', 'Voice') }}</template>
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

.chat-menu-btn {
  display: none;
  width: 36px;
  height: 36px;
  margin-right: 4px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: #6b7280;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}

.chat-menu-btn:hover,
.chat-menu-btn:active {
  background: var(--surface-hover);
  color: var(--text-primary);
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
    padding: 10px 12px;
  }

  .chat-menu-btn {
    display: inline-flex;
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

  @supports (content-visibility: auto) {
    .message-item {
      content-visibility: auto;
      contain-intrinsic-size: 120px;
    }
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
    padding: 8px 10px;
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
