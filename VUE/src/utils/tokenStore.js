// utils/tokenStore.js - 统一的令牌存取
//
// 安全策略（缓解 XSS 窃取令牌）：
//   - access_token 存 sessionStorage：关闭标签页即清除，降低持久化风险；
//   - refresh_token 存 localStorage：仅在 access_token 过期时用于静默续期；
//   - 兼容旧版：首次读取时若 sessionStorage 无值而 localStorage 有值，自动迁移。
const ACCESS_KEY = 'chatbot_token';
const REFRESH_KEY = 'chatbot_refresh_token';

function safeGet(store, key) {
  try { return store.getItem(key); } catch { return null; }
}
function safeSet(store, key, val) {
  try { if (val == null) store.removeItem(key); else store.setItem(key, val); } catch { /* 隐私模式忽略 */ }
}

export const tokenStore = {
  getAccess() {
    const v = safeGet(sessionStorage, ACCESS_KEY);
    if (v) return v;
    // 兼容迁移：旧版存在 localStorage 的 access token 迁移到 sessionStorage
    const legacy = safeGet(localStorage, ACCESS_KEY);
    if (legacy) {
      safeSet(sessionStorage, ACCESS_KEY, legacy);
      safeSet(localStorage, ACCESS_KEY, null);
    }
    return legacy;
  },
  setAccess(token) {
    safeSet(sessionStorage, ACCESS_KEY, token);
    safeSet(localStorage, ACCESS_KEY, null);
  },
  getRefresh() {
    return safeGet(localStorage, REFRESH_KEY);
  },
  setRefresh(token) {
    safeSet(localStorage, REFRESH_KEY, token);
  },
  clear() {
    safeSet(sessionStorage, ACCESS_KEY, null);
    safeSet(localStorage, ACCESS_KEY, null);
    safeSet(localStorage, REFRESH_KEY, null);
    safeSet(localStorage, 'chatbot_user', null);
  },
};

export default tokenStore;
