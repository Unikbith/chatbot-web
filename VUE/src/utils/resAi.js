import logger from './logger';
// utils/resAi.js - API 请求封装
import axios from "axios";
import { tokenStore } from './tokenStore';

const baseURL = import.meta.env.VITE_API_BASE_URL || "";

const resAi = axios.create({
  baseURL,
  timeout: 30000,
  headers: { "Content-Type": "application/json" },
});

// 登录态失效通知去重：多个并发 401 只触发一次「登录过期」
let authExpiredCooldown = 0;
function notifyAuthExpired() {
  const now = Date.now();
  if (now - authExpiredCooldown < 1500) return;
  authExpiredCooldown = now;
  window.dispatchEvent(new CustomEvent("auth:expired"));
}

// 静默续期：access token 过期时用 refresh token 换新，避免打断用户操作。
// 并发 401 共享同一个刷新 Promise，防止刷新风暴。
let refreshPromise = null;
async function tryRefreshToken() {
  const refreshToken = tokenStore.getRefresh();
  if (!refreshToken) return null;
  if (!refreshPromise) {
    refreshPromise = axios
      .post(`${baseURL}/api/auth/refresh`, {}, {
        headers: { Authorization: `Bearer ${refreshToken}` },
      })
      .then((res) => {
        const newToken = res.data?.data?.access_token;
        if (newToken) tokenStore.setAccess(newToken);
        return newToken || null;
      })
      .catch(() => null)
      .finally(() => { refreshPromise = null; });
  }
  return refreshPromise;
}

resAi.interceptors.request.use(
  (config) => {
    const token = tokenStore.getAccess();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error),
);

resAi.interceptors.response.use(
  (response) => response.data,
  async (error) => {
    const status = error.response?.status;
    const original = error.config || {};
    // 401 且未重试过、且存在 refresh token → 静默续期后重放一次原请求
    if (status === 401 && !original._retried && tokenStore.getRefresh()) {
      original._retried = true;
      const newToken = await tryRefreshToken();
      if (newToken) {
        original.headers = original.headers || {};
        original.headers.Authorization = `Bearer ${newToken}`;
        return resAi(original);
      }
    }
    if (status === 401) {
      // 仅当发请求时确实持有 token 才视为「登录过期」；未登录(无 token)的 401 不弹误导提示
      const hadToken = !!tokenStore.getAccess();
      tokenStore.clear();
      if (hadToken) notifyAuthExpired();
    } else {
      logger.error("请求错误", error);
    }
    return Promise.reject(error);
  },
);

// 流式请求
const fetchStream = async (url, data, options = {}) => {
  const token = tokenStore.getAccess();
  const response = await fetch(`${baseURL}${url}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token && { Authorization: `Bearer ${token}` }),
      ...options.headers,
    },
    body: JSON.stringify(data),
    ...options,
  });
  if (!response.ok) {
    if (response.status === 401) {
      const hadToken = !!tokenStore.getAccess();
      tokenStore.setAccess(null);
      if (hadToken) notifyAuthExpired();
    }
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  return response;
};

// 流式表单请求
const fetchStreamFormData = async (url, formData, options = {}) => {
  const token = tokenStore.getAccess();
  const headers = {
    ...(token && { Authorization: `Bearer ${token}` }),
    ...options.headers,
  };
  const response = await fetch(`${baseURL}${url}`, {
    method: "POST",
    headers,
    body: formData,
    ...options,
  });
  if (!response.ok) {
    if (response.status === 401) {
      const hadToken = !!tokenStore.getAccess();
      tokenStore.setAccess(null);
      if (hadToken) notifyAuthExpired();
    }
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  return response;
};

// 流式数据读取
const readStream = async (response, onChunk) => {
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || !trimmed.startsWith("data: ")) continue;
      const jsonStr = trimmed.slice(6);
      if (jsonStr === "[DONE]") continue;
      try {
        const data = JSON.parse(jsonStr);
        if (data.error) throw new Error(data.error);
        onChunk(data);
      } catch (e) {
        logger.warn("解析失败", e);
      }
    }
  }
};

// ========== 认证 API ==========
const authApi = {
  // 发送验证码
  async sendCode(email, purpose = 'register') {
    return resAi.post('/api/auth/send-code', { email, purpose });
  },

  // 注册
  async register(data) {
    return resAi.post('/api/auth/register', data);
  },

  // 登录
  async login(username, password) {
    return resAi.post('/api/auth/login', { username, password });
  },

  // 刷新 token
  async refresh() {
    const refreshToken = tokenStore.getRefresh();
    const res = await axios.post(`${baseURL}/api/auth/refresh`, {}, {
      headers: { Authorization: `Bearer ${refreshToken}` }
    });
    return res.data;
  },

  // 获取用户信息
  async userinfo() {
    return resAi.get('/api/auth/userinfo');
  },

  // 修改密码（需邮箱验证码）
  async changePassword(old_password, new_password, code) {
    return resAi.put('/api/auth/password', { old_password, new_password, code });
  },

  // 忘记密码：邮箱 + 验证码 + 新密码
  async resetPassword(email, code, new_password) {
    return resAi.post('/api/auth/reset-password', { email, code, new_password });
  },

  // 校验邮箱验证码（忘记密码第一步）
  async verifyCode(email, code, purpose = 'reset_password') {
    return resAi.post('/api/auth/verify-code', { email, code, purpose });
  },

  // 注销账号
  async deleteAccount(password) {
    return resAi.post('/api/auth/delete-account', { password });
  },

  // 登出（清除本地 token）
  logout() {
    tokenStore.clear();
  },
};

// ========== 模型提供商 API ==========
const providersApi = {
  async all() {
    return resAi.get('/api/providers/all');
  },
  async list(type = 'chat') {
    return resAi.get(`/api/providers?type=${type}`);
  },
  async vendors(type = 'chat') {
    return resAi.get(`/api/providers/vendors?type=${type}`);
  },
  async configSchema(type = 'chat', brand = '') {
    return resAi.get(`/api/providers/config-schema?type=${type}&brand=${brand}`);
  },
  async get(id) {
    return resAi.get(`/api/providers/${id}`);
  },
  async create(data) {
    return resAi.post('/api/providers', data);
  },
  async update(id, data) {
    return resAi.put(`/api/providers/${id}`, data);
  },
  async remove(id) {
    return resAi.delete(`/api/providers/${id}`);
  },
  async setDefault(id) {
    return resAi.put(`/api/providers/${id}/default`);
  },
  // 图片生成连接测试：后端会发起一次真实生图请求（可能 10~90s），
  // 必须单独放宽超时，否则前端会先于后端超时并误报「测试失败」
  async test(id) {
    return resAi.post(`/api/providers/${id}/test`, null, { timeout: 150000 });
  },
  // 已配置模型管理
  async listModels(providerId) {
    return resAi.get(`/api/providers/${providerId}/models`);
  },
  async addModel(providerId, data) {
    return resAi.post(`/api/providers/${providerId}/models`, data);
  },
  async fetchAvailable(providerId) {
    return resAi.post(`/api/providers/${providerId}/models/fetch`);
  },
  async updateModel(providerId, modelId, data) {
    return resAi.put(`/api/providers/${providerId}/models/${modelId}`, data);
  },
  async testModel(providerId, modelId) {
    return resAi.post(`/api/providers/${providerId}/models/${modelId}/test`);
  },
  async deleteModel(providerId, modelId) {
    return resAi.delete(`/api/providers/${providerId}/models/${modelId}`);
  },
  async models(providerId, type = 'chat') {
    return resAi.get(`/api/chat/models?provider_id=${providerId}&type=${type}`);
  },
  getCurrentId(type = 'chat') {
    return localStorage.getItem(`current_provider_id_${type}`);
  },
  setCurrentId(id, type = 'chat') {
    localStorage.setItem(`current_provider_id_${type}`, id);
  },
  // 上一次使用的模型（`providerId::modelId`），跨登录保留在浏览器本地。
  // 作用：配置了多个模型时，退出再登录仍接着上次用的那个，而不是总回到第一个。
  getLastModel(type = 'chat') {
    try { return localStorage.getItem(`last_model_${type}`) || ''; } catch (e) { return ''; }
  },
  setLastModel(providerId, modelId, type = 'chat') {
    try { localStorage.setItem(`last_model_${type}`, `${providerId}::${modelId || ''}`); } catch (e) { /* 忽略隐私模式 */ }
  },
};

// ========== 角色模板 API ==========
const personaApi = {
  async list() {
    return resAi.get('/api/personas');
  },
  async get(id) {
    return resAi.get(`/api/personas/${id}`);
  },
  async create(data) {
    return resAi.post('/api/personas', data);
  },
  async update(id, data) {
    return resAi.put(`/api/personas/${id}`, data);
  },
  async remove(id) {
    return resAi.delete(`/api/personas/${id}`);
  },
  async setDefault(id) {
    return resAi.put(`/api/personas/${id}/default`);
  },
  // 世界书（设定条目）：按需注入的设定，命中关键词才送进模型，省 token
  async listWorldBook(personaId) {
    return resAi.get(`/api/personas/${personaId}/worldbook`);
  },
  async createWorldBook(personaId, data) {
    return resAi.post(`/api/personas/${personaId}/worldbook`, data);
  },
  async updateWorldBook(personaId, entryId, data) {
    return resAi.put(`/api/personas/${personaId}/worldbook/${entryId}`, data);
  },
  async removeWorldBook(personaId, entryId) {
    return resAi.delete(`/api/personas/${personaId}/worldbook/${entryId}`);
  },
  getDefaultId() {
    return localStorage.getItem('default_persona_id');
  },
  setDefaultId(id) {
    localStorage.setItem('default_persona_id', id);
  },
};

// ========== 用户设置 API ==========
const settingsApi = {
  async get() {
    return resAi.get('/api/settings');
  },
  async update(data) {
    return resAi.put('/api/settings', data);
  },
  async updateProfile(data) {
    return resAi.put('/api/settings/profile', data);
  },
};

// ========== 文件上传 API ==========
const uploadApi = {
  // 走 resAi(axios) 而非裸 fetch：只有 axios 实例挂了 401 自动续期拦截器，
  // 裸 fetch 在 token 过期时会直接失败（无提示、无续期）→ 上传静默失败 → 图片丢失
  async uploadImage(file) {
    const formData = new FormData();
    formData.append('file', file);
    // Content-Type 交给 axios 自动补 multipart 边界，手写会导致后端解析失败
    return resAi.post('/api/upload/image', formData, {
      headers: { 'Content-Type': undefined },
    });
  },
  getImageUrl(filename) {
    return `${baseURL}/api/upload/image/${filename}`;
  },
};

// ========== 对话管理 API ==========
const conversationApi = {
  async list() {
    return resAi.get('/api/conversations');
  },
  async create(data) {
    return resAi.post('/api/conversations', data);
  },
  async get(id) {
    return resAi.get(`/api/conversations/${id}`);
  },
  async update(id, data) {
    return resAi.put(`/api/conversations/${id}`, data);
  },
  async remove(id) {
    return resAi.delete(`/api/conversations/${id}`);
  },
  async togglePin(id) {
    return resAi.put(`/api/conversations/${id}/pin`);
  },
  async summaries(id) {
    return resAi.get(`/api/conversations/${id}/summaries`);
  },
  async clear(id) {
    return resAi.delete(`/api/conversations/${id}/messages`);
  },
};

// ========== 聊天 API ==========
const chatApi = {
  async status() {
    return resAi.get('/api/chat/status');
  },
  async stream(data, options = {}) {
    return fetchStream('/api/chat', data, options);
  },
  async vision(formData, options = {}) {
    return fetchStreamFormData('/api/chat/vision', formData, options);
  },
  async models(providerId, type = 'chat') {
    return resAi.get(`/api/chat/models?provider_id=${providerId}&type=${type}`);
  },
};

// ========== 提示词工具 API（一键人物设定 / 生图改图提示词） ==========
const promptToolApi = {
  async options() {
    return resAi.get('/api/chat/prompt-tool');
  },
  async generate(payload) {
    return resAi.post('/api/chat/prompt-tool', payload);
  },
};

// ========== 图片生成 API（Agnes 文生图 / 图生图） ==========
// 生图/改图上游耗时较长（后端允许 120s），不能用实例默认的 30s 超时，
// 否则图片还在生成就被前端以「超时」中断
const imageApi = {
  async generate(data) {
    return resAi.post('/api/image/generate', data, { timeout: 180000 });
  },
};

// 管理后台专用请求实例：使用独立的管理员令牌（admin_token），避免与普通用户令牌冲突
const adminReq = axios.create({
  baseURL,
  timeout: 30000,
  headers: { "Content-Type": "application/json" },
});
adminReq.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("admin_token");
    if (token) config.headers.Authorization = `Bearer ${token}`;
    return config;
  },
  (error) => Promise.reject(error),
);
adminReq.interceptors.response.use(
  (response) => response.data,
  (error) => {
    logger.error("管理后台请求错误", error);
    if (error.response?.status === 401) {
      localStorage.removeItem("admin_token");
    }
    return Promise.reject(error);
  },
);

// ========== 后台管理 API（管理员） ==========
const adminApi = {
  async login(username, password) {
    return adminReq.post('/api/admin/login', { username, password });
  },
  async status() {
    return adminReq.get('/api/admin/me');
  },
  async stats() {
    return adminReq.get('/api/admin/stats');
  },
  async users(page = 1, perPage = 200, keyword = '') {
    const params = new URLSearchParams({ page: String(page), per_page: String(perPage) });
    if (keyword) params.set('q', keyword);
    return adminReq.get(`/api/admin/users?${params.toString()}`);
  },
  async userConversations(userId) {
    return adminReq.get(`/api/admin/users/${userId}/conversations`);
  },
  async conversationMessages(convId) {
    return adminReq.get(`/api/admin/conversations/${convId}/messages`);
  },
  async deleteConversation(convId) {
    return adminReq.delete(`/api/admin/conversations/${convId}`);
  },
  async batchDeleteConversations(ids) {
    return adminReq.post(`/api/admin/conversations/batch-delete`, { ids });
  },
  async exportConversation(convId) {
    const token = localStorage.getItem("admin_token");
    const response = await fetch(`${baseURL}/api/admin/conversations/${convId}/export`, {
      method: "GET",
      headers: { ...(token && { Authorization: `Bearer ${token}` }) },
    });
    if (!response.ok) {
      let msg = `HTTP ${response.status}`;
      try {
        const body = await response.json();
        if (body && body.message) msg = body.message;
      } catch (e) { /* 非 JSON 响应，保留默认信息 */ }
      throw new Error(msg);
    }
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `conversation_${convId}.md`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  },
  async marketplaceCards(page = 1, extra = {}) {
    const params = new URLSearchParams()
    params.set('page', String(page))
    if (extra.keyword) params.set('keyword', extra.keyword)
    if (extra.gender) params.set('gender', extra.gender)
    if (extra.creator_gender) params.set('creator_gender', extra.creator_gender)
    return adminReq.get(`/api/admin/marketplace?${params.toString()}`);
  },
  async deleteMarketplaceCard(pid) {
    return adminReq.delete(`/api/admin/marketplace/${pid}`);
  },
  async marketplaceCardDetail(pid) {
    return adminReq.get(`/api/admin/marketplace/${pid}`);
  },
  // 管理员编辑任意广场卡片（不受作者归属限制）
  async updateMarketplaceCard(pid, data) {
    return adminReq.put(`/api/admin/marketplace/${pid}`, data);
  },
  // 提示词工具使用记录：谁在何时用了、输入、生成结果
  async promptToolLogs(page = 1, perPage = 20, userId = '', category = '') {
    let url = `/api/admin/prompt-tool-logs?page=${page}&per_page=${perPage}`;
    if (userId) url += `&user_id=${userId}`;
    if (category) url += `&category=${category}`;
    return adminReq.get(url);
  },
  // 提示词记录：单条 / 批量删除
  async deletePromptToolLog(id) {
    return adminReq.delete(`/api/admin/prompt-tool-logs/${id}`);
  },
  async deletePromptToolLogs(ids = []) {
    return adminReq.post('/api/admin/prompt-tool-logs/batch-delete', { ids });
  },
  // 对话素材（背景图/AI头像/用户头像）设置历史：管理员追溯 + 多选删除
  async conversationMediaLogs(page = 1, perPage = 20, userId = '', mediaType = '') {
    let url = `/api/admin/conversation-media-logs?page=${page}&per_page=${perPage}`;
    if (userId) url += `&user_id=${userId}`;
    if (mediaType) url += `&media_type=${mediaType}`;
    return adminReq.get(url);
  },
  async deleteConversationMediaLog(id) {
    return adminReq.delete(`/api/admin/conversation-media-logs/${id}`);
  },
  async deleteConversationMediaLogs(ids = []) {
    return adminReq.post('/api/admin/conversation-media-logs/batch-delete', { ids });
  },
  async feedbackList(page = 1, perPage = 20) {
    return adminReq.get(`/api/feedback?page=${page}&per_page=${perPage}`);
  },
  logout() {
    localStorage.removeItem("admin_token");
    localStorage.removeItem("admin_username");
  },
};

// ========== 音频 API ==========
const audioApi = {
  async speechToText(file, providerId = null) {
    const formData = new FormData();
    formData.append('file', file);
    if (providerId) formData.append('provider_id', providerId);
    const token = tokenStore.getAccess();
    const response = await fetch(`${baseURL}/api/audio/transcriptions`, {
      method: 'POST',
      headers: { ...(token && { Authorization: `Bearer ${token}` }) },
      body: formData,
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  },
  async textToSpeech(text, voice = 'alloy', providerId = null) {
    const token = tokenStore.getAccess();
    const response = await fetch(`${baseURL}/api/audio/speech`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token && { Authorization: `Bearer ${token}` }),
      },
      body: JSON.stringify({ text, voice, provider_id: providerId }),
    });
    if (!response.ok) {
      let msg = `HTTP ${response.status}`;
      try {
        const body = await response.json();
        if (body && body.message) msg = body.message;
      } catch (e) { /* 非 JSON 响应，保留默认信息 */ }
      throw new Error(msg);
    }
    return response.blob();
  },
  async listVoices(providerId = null) {
    const url = providerId
      ? `/api/audio/voices?provider_id=${providerId}`
      : '/api/audio/voices';
    return resAi.get(url);
  },
};

// ========== 反馈 API ==========
const feedbackApi = {
  async submit(data) {
    return resAi.post('/api/feedback', data);
  },
  async list(page = 1, perPage = 20) {
    return resAi.get(`/api/feedback?page=${page}&per_page=${perPage}`);
  },
};

const marketplaceApi = {
  list(sort = 'hot', page = 1, keyword = '', gender = '', perPage = 12) {
    let url = `/api/marketplace?sort=${sort}&page=${page}&per_page=${perPage}`;
    if (keyword) url += `&q=${encodeURIComponent(keyword)}`;
    if (gender) url += `&gender=${encodeURIComponent(gender)}`;
    return resAi.get(url);
  },
  // 广场中实际存在的自定义性别值，用于筛选下拉动态渲染
  genders() {
    return resAi.get('/api/marketplace/genders');
  },
  publicComments(personaId, sort = 'hot', page = 1, perPage = 5) {
    return resAi.get(`/api/marketplace/public/${personaId}/comments?sort=${sort}&page=${page}&per_page=${perPage}`);
  },
  get(id) {
    return resAi.get(`/api/marketplace/${id}`);
  },
  publish(data) {
    return resAi.post('/api/marketplace', data);
  },
  delete(id) {
    return resAi.delete(`/api/marketplace/${id}`);
  },
  // 编辑卡片：创建者与管理员均可调用，未提交的字段保持原值
  update(id, data) {
    return resAi.put(`/api/marketplace/${id}`, data);
  },
  vote(id, voteType) {
    return resAi.post(`/api/marketplace/${id}/vote`, { vote_type: voteType });
  },
  adopt(id) {
    return resAi.post(`/api/marketplace/${id}/adopt`);
  },
  unadopt(id) {
    return resAi.post(`/api/marketplace/${id}/unadopt`);
  },
  comments(personaId, sort = 'hot', page = 1, perPage = 5) {
    return resAi.get(`/api/marketplace/${personaId}/comments?sort=${sort}&page=${page}&per_page=${perPage}`);
  },
  addComment(personaId, content) {
    return resAi.post(`/api/marketplace/${personaId}/comments`, { content });
  },
  // 再次点赞即取消点赞，服务端返回 { likes, liked }
  toggleCommentLike(commentId) {
    return resAi.post(`/api/marketplace/comments/${commentId}/like`);
  },
  checkin() {
    return resAi.post('/api/marketplace/checkin');
  },
  checkinStatus() {
    return resAi.get('/api/marketplace/checkin/status');
  },
};

export {
  resAi,
  fetchStream,
  fetchStreamFormData,
  readStream,
  authApi,
  providersApi,
  personaApi,
  settingsApi,
  uploadApi,
  conversationApi,
  chatApi,
  promptToolApi,
  audioApi,
  imageApi,
  adminApi,
  marketplaceApi,
  feedbackApi,
  baseURL
};
