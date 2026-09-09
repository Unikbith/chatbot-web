// utils/resAi.js - API 请求封装
import axios from "axios";

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

resAi.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("chatbot_token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error),
);

resAi.interceptors.response.use(
  (response) => response.data,
  (error) => {
    console.error("请求错误", error);
    if (error.response?.status === 401) {
      localStorage.removeItem("chatbot_token");
      localStorage.removeItem("chatbot_refresh_token");
      notifyAuthExpired();
    }
    return Promise.reject(error);
  },
);

// 流式请求
const fetchStream = async (url, data, options = {}) => {
  const token = localStorage.getItem("chatbot_token");
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
      localStorage.removeItem("chatbot_token");
      notifyAuthExpired();
    }
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  return response;
};

// 流式表单请求
const fetchStreamFormData = async (url, formData, options = {}) => {
  const token = localStorage.getItem("chatbot_token");
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
      localStorage.removeItem("chatbot_token");
      notifyAuthExpired();
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
        console.warn("解析失败", e);
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
    const refreshToken = localStorage.getItem("chatbot_refresh_token");
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
    localStorage.removeItem("chatbot_token");
    localStorage.removeItem("chatbot_refresh_token");
    localStorage.removeItem("chatbot_user");
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
  async test(id) {
    return resAi.post(`/api/providers/${id}/test`);
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
  async uploadImage(file) {
    const formData = new FormData();
    formData.append('file', file);
    const token = localStorage.getItem("chatbot_token");
    const response = await fetch(`${baseURL}/api/upload/image`, {
      method: 'POST',
      headers: {
        ...(token && { Authorization: `Bearer ${token}` }),
      },
      body: formData,
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
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
const imageApi = {
  async generate(data) {
    return resAi.post('/api/image/generate', data);
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
    console.error("管理后台请求错误", error);
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
  async users() {
    return adminReq.get('/api/admin/users');
  },
  async userConversations(userId) {
    return adminReq.get(`/api/admin/users/${userId}/conversations`);
  },
  async conversationMessages(convId) {
    return adminReq.get(`/api/admin/conversations/${convId}/messages`);
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
    const token = localStorage.getItem("chatbot_token");
    const response = await fetch(`${baseURL}/api/audio/transcriptions`, {
      method: 'POST',
      headers: { ...(token && { Authorization: `Bearer ${token}` }) },
      body: formData,
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  },
  async textToSpeech(text, voice = 'alloy', providerId = null) {
    const token = localStorage.getItem("chatbot_token");
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
  baseURL
};
