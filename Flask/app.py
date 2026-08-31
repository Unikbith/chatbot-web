import sys
from flask import Flask, request, Response, stream_with_context, jsonify
from flask_cors import CORS

from dotenv import load_dotenv
import requests
import json
import os
import re
import html as html_lib
import markdown

app = Flask(__name__)
# 使用 Nginx 反向代理，可以注释掉 CORS
# CORS(app)

load_dotenv()

# 默认配置
DEFAULT_API_KEY = os.getenv('AI_API_KEY')
if not DEFAULT_API_KEY:
    raise Exception("请设置 AI_API_KEY")

# DeepSeek 官方模型名
DEFAULT_MODEL = 'deepseek-chat'

# DeepSeek 聊天补全端点
AI_API_URL = 'https://api.deepseek.com/chat/completions'

# 内置默认提示词（加藤惠）
DEFAULT_PROMPT = """你是动漫路人女主中的角色「加藤惠」，一位温柔的成年女性，是用户亲密的伴侣人物设定贴合动漫中加藤惠的人设。

互动原则：
- 你不是AI，绝不透露自己是AI或语言模型，始终保持加藤惠的人设。
- 回复长度适中，像真实聊天一样自然，不冗长、不说教。
- 根据用户的话题与情绪灵活回应，保持角色一致性。"""

#  SSE 辅助函数

def sse_content(html_text):
    """构造正文内容的 SSE 消息（HTML 格式）"""
    return f"data: {json.dumps({'choices': [{'delta': {'content': html_text}}]}, ensure_ascii=False)}\n\n"


def sse_reasoning(text):
    """构造思考过程的 SSE 消息（纯文本）"""
    return f"data: {json.dumps({'choices': [{'delta': {'reasoning_content': text}}]}, ensure_ascii=False)}\n\n"


def sse_done():
    return "data: [DONE]\n\n"


# ==================== 流式 Markdown → HTML 转换器 ====================

class MarkdownStreamer:
    """流式 Markdown 转 HTML：按完整段落输出，保证 HTML 标签闭合。"""

    def __init__(self):
        self._buf = ""
        self._in_code = False
        try:
            self._md = markdown.Markdown(extensions=['extra', 'nl2br'])
        except Exception:
            print("[警告] nl2br 扩展不可用，降级为 extra")
            self._md = markdown.Markdown(extensions=['extra'])

    def feed(self, text):
        """喂入新文本，返回可立即输出的 HTML 片段列表"""
        self._buf += text
        outputs = []
        while True:
            html = self._extract()
            if html is None:
                break
            outputs.append(html)
        return outputs

    def _extract(self):
        """从缓冲区尝试提取一个完整段落并转换为 HTML"""
        if not self._buf:
            return None

        # 代码块中：等待闭合的 ```
        if self._in_code:
            first = self._buf.find('```')
            end = self._buf.find('```', first + 3) if first != -1 else -1
            if end == -1:
                return None
            nl = self._buf.find('\n', end)
            if nl == -1:
                return None
            segment = self._buf[:nl + 1]
            self._buf = self._buf[nl + 1:]
            self._in_code = False
            return self._convert(segment)

        # 普通模式：检查是否以 ``` 开头
        stripped = self._buf.lstrip()
        if stripped.startswith('```'):
            if '\n' not in self._buf:
                return None
            self._in_code = True
            return None

        # 普通模式：找空行（段落结束标志）
        para_end = self._buf.find('\n\n')
        if para_end != -1:
            segment = self._buf[:para_end + 2]
            self._buf = self._buf[para_end + 2:]
            return self._convert(segment)

        return None

    def _convert(self, text):
        self._md.reset()
        return self._md.convert(text)

    def flush(self):
        """流结束，输出缓冲区中剩余的所有内容"""
        if self._buf.strip():
            html = self._convert(self._buf)
            self._buf = ""
            return html
        return ""


# 文本处理工具函数

def strip_html_to_text(html_text):
    """将 HTML 还原为纯文本，供模型续写/后续对话使用"""
    if not html_text:
        return ''
    text = html_text
    # 换行类标签先转成换行
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</(p|div|li|h[1-6]|blockquote|pre|tr)>', '\n', text, flags=re.IGNORECASE)
    # 去掉剩余所有标签
    text = re.sub(r'<[^>]+>', '', text)
    # 还原 HTML 实体
    text = html_lib.unescape(text)
    return text.strip()


def make_api_request(payload, api_key, max_retries=2):
    """发起 API 流式请求，自动重试。"""
    last_error = None
    for attempt in range(max_retries):
        try:
            resp = requests.post(
                AI_API_URL,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {api_key}'
                },
                json=payload,
                stream=True,
                timeout=120
            )
            if resp.status_code == 200:
                return resp
            error_text = resp.text[:200] if resp.text else "无响应体"
            last_error = f"HTTP {resp.status_code}: {error_text}"
            print(f"[API 请求失败] 第 {attempt + 1} 次: {last_error}")
        except requests.RequestException as e:
            last_error = str(e)
            print(f"[API 请求异常] 第 {attempt + 1} 次: {last_error}")

        if attempt < max_retries - 1:
            import time
            time.sleep(1)

    return None


def iter_sse_content(response, full_content_holder, streamer):
    """遍历 API 流式响应，提取正文和思考过程。

    返回 (新增原始内容, finish_reason)
    """
    new_content = ""
    finish_reason = None

    try:
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            if line.startswith("data: "):
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    choice = chunk.get("choices", [{}])[0]
                    delta = choice.get("delta", {})

                    if "finish_reason" in choice and choice["finish_reason"] is not None:
                        finish_reason = choice["finish_reason"]

                    content = delta.get("content", "")
                    reasoning = delta.get("reasoning_content", "")

                    if reasoning:
                        yield sse_reasoning(reasoning)

                    if content:
                        new_content += content
                        full_content_holder[0] += content
                        for html_frag in streamer.feed(content):
                            yield sse_content(html_frag)
                except (json.JSONDecodeError, KeyError, IndexError):
                    pass
    except GeneratorExit:
        # 客户端断开连接
        print("[客户端断开] 停止生成")
        raise

    remaining = streamer.flush()
    if remaining:
        yield sse_content(remaining)

    return new_content, finish_reason


def build_system_prompt(base_prompt, target_word_count):
    """在基础系统提示词末尾追加字数要求。"""
    instruction = (
        f"【回复长度建议】\n"
        f"本次回复请尽量详细一些，大约 {target_word_count} 字左右。"
        f"你可以适当展开场景描写、心理活动或对话，让回复更充实。"
        f"如果用户输入较短，可以自行补充合理的细节。"
    )
    return base_prompt + instruction


@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json()
    messages = data.get('messages', [])
    deep_think = data.get('deep_think', False)
    prompt_mode = data.get('prompt_mode', 'default')
    custom_prompt = data.get('custom_prompt', '').strip()
    frequency_penalty = data.get('frequency_penalty', 0.1)
    presence_penalty = data.get('presence_penalty', 0.1)

    user_api_key = data.get('api_key', '').strip()
    user_model = data.get('model', '').strip()
    user_max_tokens = data.get('max_tokens', 0)

    final_api_key = user_api_key if user_api_key else DEFAULT_API_KEY
    final_model = user_model if user_model else DEFAULT_MODEL

    # 目标字数（前端传递的挡位，默认 150）
    target_word_count = user_max_tokens if user_max_tokens > 0 else 150

    # 总 token 预算 = 目标字数 × 2.5 + 余量
    total_tokens = int(target_word_count * 2.5) + 150

    # 确定系统提示词：自定义优先，否则使用内置默认
    if prompt_mode == 'custom' and custom_prompt:
        base_prompt = custom_prompt
        print(f"[自定义] 使用用户自定义提示词，长度: {len(base_prompt)} 字符")
    else:
        base_prompt = DEFAULT_PROMPT
        print(f"[默认] 使用内置加藤惠提示词，长度: {len(base_prompt)} 字符")

    # 在系统提示词末尾追加字数要求
    system_prompt = build_system_prompt(base_prompt, target_word_count)

    print(
        f"[配置] 模型: {final_model}, 目标字数: {target_word_count}, "
        f"深度思考: {deep_think}, 人物设定模式: {prompt_mode}, max_tokens: {total_tokens}"
    )

    if not messages or len(messages) == 0:
        return jsonify({'code': 400, 'message': '消息列表不能为空'}), 400

    # 构建消息列表
    formatted_messages = []
    for msg in messages:
        role = msg.get('role')
        content = msg.get('content', '')

        # 将 assistant 消息中的 HTML 还原为纯文本
        if role == 'assistant' and content:
            content = strip_html_to_text(content)

        formatted_messages.append({
            'role': role,
            'content': content
        })

    # 插入系统提示词（确保首位）
    if not formatted_messages or formatted_messages[0].get('role') != 'system':
        formatted_messages.insert(0, {
            'role': 'system',
            'content': system_prompt
        })
    else:
        formatted_messages[0]['content'] = system_prompt

    def generate():
        full_content_holder = [""]

        try:
            # 构建请求 payload（一次生成，无续写）
            payload = {
                'model': 'deepseek-reasoner' if deep_think else final_model,
                'messages': formatted_messages,
                'stream': True,
                'max_tokens': total_tokens,
            }

            # 普通模型才添加采样参数（deepseek-reasoner 不支持）
            if not deep_think:
                payload.update({
                    'temperature': 0.88,
                    'frequency_penalty': frequency_penalty,
                    'presence_penalty': presence_penalty,
                })

            print(f"[请求] max_tokens={total_tokens}, 目标字数={target_word_count}, "
                  f"模型={payload['model']}, freq_penalty={frequency_penalty}, pres_penalty={presence_penalty}")

            response = make_api_request(payload, final_api_key)

            if response is None:
                yield sse_content('出错了：AI 服务请求失败，请检查 API Key 是否正确')
                yield sse_done()
                return

            streamer = MarkdownStreamer()
            new_content, finish_reason = yield from iter_sse_content(
                response, full_content_holder, streamer
            )
            full_content = full_content_holder[0]
            current_len = len(full_content)  # 粗略字符数
            print(f"[完成] 生成字数: {current_len}, finish_reason: {finish_reason}")

            yield sse_done()

        except GeneratorExit:
            # 客户端主动断开（用户点击停止）
            print("[用户停止] 生成被中断")
        except Exception as e:
            print(f"[错误] {str(e)}")
            yield sse_content(f'出错了：服务端错误 - {str(e)}')
            yield sse_done()

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5000)
