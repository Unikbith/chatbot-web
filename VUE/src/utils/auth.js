// utils/auth.js - 认证相关工具
import { resAi } from './resAi';

const TOKEN_KEY = 'chatbot_token';
const REFRESH_TOKEN_KEY = 'chatbot_refresh_token';
const USER_KEY = 'chatbot_user';

export const auth = {
  // 登录
  async login(username, password) {
    const res = await resAi.post('/api/auth/login', { username, password });
    if (res.code === 200) {
      this.setToken(res.data.access_token);
      this.setRefreshToken(res.data.refresh_token);
      this.setUser(res.data.user);
    }
    return res;
  },

  // 注册
  async register(username, password, email = '') {
    const res = await resAi.post('/api/auth/register', { username, password, email });
    if (res.code === 200) {
      this.setToken(res.data.access_token);
      this.setRefreshToken(res.data.refresh_token);
      this.setUser(res.data.user);
    }
    return res;
  },

  // 退出登录
  logout() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  },

  // 获取 token
  getToken() {
    return localStorage.getItem(TOKEN_KEY);
  },

  // 设置 token
  setToken(token) {
    localStorage.setItem(TOKEN_KEY, token);
  },

  // 获取 refresh token
  getRefreshToken() {
    return localStorage.getItem(REFRESH_TOKEN_KEY);
  },

  // 设置 refresh token
  setRefreshToken(token) {
    localStorage.setItem(REFRESH_TOKEN_KEY, token);
  },

  // 获取用户信息
  getUser() {
    try {
      const user = localStorage.getItem(USER_KEY);
      return user ? JSON.parse(user) : null;
    } catch {
      return null;
    }
  },

  // 设置用户信息
  setUser(user) {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  },

  // 是否登录
  isLoggedIn() {
    return !!this.getToken();
  },

  // 获取当前用户信息（从服务器）
  async fetchUserInfo() {
    try {
      const res = await resAi.get('/api/auth/userinfo');
      if (res.code === 200) {
        this.setUser(res.data);
        return res.data;
      }
    } catch (e) {
      console.error('获取用户信息失败', e);
    }
    return null;
  },
};

export default auth;
