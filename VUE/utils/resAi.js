// utils/resAi.js
import axios from "axios";

/* const baseURL = "http://127.0.0.1:5000"; */
// 生产环境为空字符串，请求自动走 /api 相对路径，由Nginx代理转发
const baseURL = import.meta.env.VITE_API_BASE_URL || "";

// 普通请求实例
const resAi = axios.create({
  baseURL,
  timeout: 10000,
  headers: { "Content-Type": "application/json" },
});

// 请求拦截器
resAi.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error),
);

// 响应拦截器
resAi.interceptors.response.use(
  (response) => response.data,
  (error) => {
    console.error("请求错误", error);
    return Promise.reject(error);
  },
);

// 流式请求（使用原生 fetch）
const fetchStream = async (url, data, options = {}) => {
  const token = localStorage.getItem("token");

  const response = await fetch(`${baseURL}${url}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token && { Authorization: `Bearer ${token}` }),
      ...options.headers,
    },
    body: JSON.stringify(data),
    ...options, // 传入 signal
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  return response;
};

//流式数据读取
const readStream = async (response, onChunk) => {
  //逐块读取数据
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  //done表示是否结束(true,false)  value为数据
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    //stream:true 流式解码
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    //处理每行
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || !trimmed.startsWith("data: ")) continue;
      //去掉'data: '
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

export { resAi, fetchStream, readStream };
