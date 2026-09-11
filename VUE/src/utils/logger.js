// utils/logger.js - 生产环境静默的日志工具
//
// 开发环境（import.meta.env.DEV）正常输出，便于排查；
// 生产环境（vite build）自动静默，避免控制台泄漏内部状态与请求细节。
const isDev = import.meta.env.DEV;

const noop = () => {};

const logger = {
  log: isDev ? console.log.bind(console) : noop,
  info: isDev ? console.info.bind(console) : noop,
  warn: isDev ? console.warn.bind(console) : noop,
  error: isDev ? console.error.bind(console) : noop,
  debug: isDev ? console.debug.bind(console) : noop,
};

export default logger;
export const { log, info, warn, error, debug } = logger;
