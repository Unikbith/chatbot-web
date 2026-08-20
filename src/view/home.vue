<script setup>
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import { fetchStream, readStream } from '@/utils/resAi';

import katoImage from '@/assets/images/加藤惠.jpg';
import natsumeImage from '@/assets/images/夏目贵志.jpg';

// 维护消息数组
const messages = ref([
  { role: 'assistant', content: '你好呀,我是加藤惠~' }
]);
const inputText = ref('');
const loading = ref(false);
const messageList = ref(null);
const deepThink = ref(false);
let abortController = null;

// 滚动最新回复
const scrollToBottom = async () => {
  await nextTick();
  if (!messageList.value) return;
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      messageList.value.scrollTop = messageList.value.scrollHeight;
    });
  });
};

// 发送消息
const handleSend = async () => {
  // 中止回复
  if (loading.value) {
    abortController?.abort();
    abortController = null;
    loading.value = false;
    return;
  }

  const text = inputText.value.trim();
  if (!text) return;

  // 添加用户消息
  messages.value.push({ role: 'user', content: text });
  inputText.value = '';
  await scrollToBottom();

  // 添加 AI 占位
  const aiIndex = messages.value.length;
  messages.value.push({ role: 'assistant', content: '' });
  await scrollToBottom();

  loading.value = true;
  abortController = new AbortController();

  try {
    const response = await fetchStream(
      '/api/chat',
      {
        messages: messages.value.slice(0, -1),
        deep_think: deepThink.value,
      },
      { signal: abortController.signal }
    );

    // 使用封装的 readStream 处理流式数据
    await readStream(response, (data) => {
      const content = data.choices?.[0]?.delta?.content || '';
      if (content) {
        messages.value[aiIndex].content += content;
        scrollToBottom();
      }
    });

  } catch (error) {
    if (error.name === 'AbortError') {
      messages.value[aiIndex].content += '（已中止）';
    } else {
      console.error('发送失败', error);
      messages.value[aiIndex].content = `出错了：${error.message || '网络异常'}`;
    }
  } finally {
    loading.value = false;
    abortController = null;
    await scrollToBottom();
  }
};

// 消息存在本地
const saveMessages = () => {
  localStorage.setItem('chat_history', JSON.stringify(messages.value));
};

const loadMessages = () => {
  const saved = localStorage.getItem('chat_history');
  if (saved) {
    try {
      messages.value = JSON.parse(saved);
    } catch (e) {
      console.warn('历史记录解析失败');
    }
  }
};

let saveTimer = null;
watch(messages, () => {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveMessages, 500);
}, { deep: true });


onMounted(async () => {
  loadMessages();
  await scrollToBottom();
});

onUnmounted(() => {
  abortController?.abort();
  abortController = null;
});
</script>

<template>
  <div class="wrapper">
    <div class="wrapper-head">
      <div class="name">
        <span>贤妻加藤惠</span>
      </div>
      <div>
        <img :src="katoImage" alt="加藤惠" class="avatar-ai">
      </div>
    </div>

    <div class="wrapper-body">
      <ul class="message-list" ref="messageList">
        <li v-for="(item, index) in messages" :key="index"
          :class="item.role === 'assistant' ? 'message-ai' : 'message-user'">
          <img :src="item.role === 'assistant' ? katoImage : natsumeImage"
            alt="avatar" class="avatar">
          <span>{{ item.content || '正在输入...' }}</span>
        </li>
      </ul>
    </div>

    <div class="wrapper-foot">
      <!-- 胶囊式切换按钮 -->
      <label class="deep-think-capsule">
        <input type="checkbox" v-model="deepThink" />
        <span>深度思考</span>
      </label>

      <input type="text" class="input" placeholder="说些什么吧..." v-model="inputText" @keydown.enter="handleSend">
      <button class="btn" @click="handleSend">
        {{ loading ? '停止' : '发送' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

.wrapper {
  display: flex;
  flex-direction: column;
  margin: 30px auto;
  height: 650px;
  width: 800px;
  border-radius: 12px;
  overflow: hidden;
  background-color: #f5f5f5;
  box-shadow: 0 2px 12px 12px rgba(0, 0, 0, 0.1);
}

.wrapper-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 30px;
  height: 80px;
  background: linear-gradient(to right, #fd72e5, #be5cee);
}

.wrapper-head .name {
  display: flex;
  align-items: center;
  height: 100%;
  color: white;
  font-size: 20px;
  font-weight: bold;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.avatar-ai {
  width: 60px;
  height: 60px;
  border-radius: 999px;
  object-fit: cover;
}

.wrapper-body {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
}

.message-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 0;
  margin: 10px;
  list-style: none;
  flex: 1;
  overflow-y: auto;
}

/* 隐藏滚动条 */
.message-list::-webkit-scrollbar {
  width: 0;
  height: 0;
  background: transparent;
  display: none;
}

.avatar {
  width: 42px;
  height: 42px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
  margin-top: 2px;
}

.message-ai {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.message-user {
  display: flex;
  flex-direction: row-reverse;
  gap: 10px;
}

.message-ai span,
.message-user span {
  padding: 10px 16px;
  border-radius: 16px;
  max-width: 70%;
  word-wrap: break-word;
  display: inline-block;
  line-height: 1.6;
  font-size: 15px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.message-ai span {
  background: #f0f0f0;
  color: #333;
  border-bottom-left-radius: 4px;
}

.message-user span {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border-bottom-right-radius: 4px;
}

.wrapper-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 30px;
  margin: 10px auto;
  width: 700px;
  height: 80px;
  border-radius: 12px;
  background-color: #ffffff;
  gap: 12px;
}

/* 深度思考胶囊按钮 */
.deep-think-capsule {
  cursor: pointer;
  user-select: none;
  padding: 7px 14px;
  border-radius: 999px;
  background-color: #e8e8e8;
  font-size: 14px;
  color: #555;
  transition: all 0.24s ease;
}

.deep-think-capsule input {
  display: none;
}

.deep-think-capsule:hover {
  opacity: 0.84;
}

.deep-think-capsule:has(input:checked) {
  background: linear-gradient(to right, #FABAF6, #F678B4);
  color: #fff;
}

.wrapper-foot .input {
  flex: 1;
  height: 50px;
  padding: 0 10px;
  font-size: 16px;
  border-radius: 12px;
  background-color: #f5f5f5;
  border: none;
  outline: none;
}

.wrapper-foot .btn {
  height: 45px;
  width: 80px;
  border-radius: 10px;
  border: none;
  outline: none;
  color: white;
  font-size: 14px;
  letter-spacing: 3px;
  background: linear-gradient(to right, #FABAF6, #F678B4);
  transition: opacity 0.2s;
}

.wrapper-foot .btn:hover:not(:disabled) {
  opacity: 0.85;
}

.wrapper-foot .btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

/* 响应式 */
@media screen and (max-width:768px) {
  .wrapper {
    width: 100%;
    height: 100vh;
    height: 100dvh;
    margin: 0;
    border-radius: 0;
    box-shadow: none;
  }

  .wrapper-head {
    padding: 0 16px;
    height: 60px;
    flex-shrink: 0;
  }

  .wrapper-head .name {
    font-size: 16px;
  }

  .wrapper-head .name span {
    font-size: 16px;
  }

  .avatar-ai {
    width: 44px;
    height: 44px;
  }

  .wrapper-body {
    flex: 1;
    overflow: hidden;
  }

  .message-list {
    gap: 12px;
    padding: 0;
    margin: 8px 12px;
  }

  .avatar {
    width: 32px;
    height: 32px;
  }

  .message-ai {
    gap: 8px;
  }

  .message-user {
    gap: 8px;
  }

  .message-ai span,
  .message-user span {
    max-width: 80%;
    font-size: 14px;
    padding: 8px 12px;
    line-height: 1.5;
  }

  .wrapper-foot {
    width: 100%;
    padding: 8px 12px;
    margin: 0;
    height: auto;
    min-height: 64px;
    border-radius: 0;
    background-color: #ffffff;
    gap: 8px;
    flex-shrink: 0;
    border-top: 1px solid rgba(0, 0, 0, 0.06);
  }

  .deep-think-capsule {
    padding: 5px 10px;
    font-size: 12px;
    flex-shrink: 0;
  }

  .wrapper-foot .input {
    height: 40px;
    font-size: 15px;
    padding: 0 10px;
    border-radius: 20px;
    background-color: #f0f0f0;
  }

  .wrapper-foot .btn {
    height: 40px;
    width: 64px;
    font-size: 13px;
    letter-spacing: 2px;
    border-radius: 20px;
    flex-shrink: 0;
  }
}
</style>
