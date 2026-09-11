// public/theme-init.js - 首屏同步应用缓存主题，消除闪白/闪黑
// 独立为外部文件以满足 CSP（script-src 'self'，禁止内联脚本）
(function () {
  try {
    var t = localStorage.getItem('chatbot_theme') || 'auto';
    var dark = t === 'dark' ||
      (t !== 'light' && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.classList.toggle('dark', dark);
  } catch (e) {}
})();
