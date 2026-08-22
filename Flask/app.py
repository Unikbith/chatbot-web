import sys
from flask import Flask, request, Response, stream_with_context, jsonify
from flask_cors import CORS

from dotenv import load_dotenv
import requests
import json
import os
import re

app = Flask(__name__)
# 使用 Nginx 反向代理，可以注释掉 CORS
# CORS(app)

load_dotenv()

# 默认配置
DEFAULT_API_KEY = os.getenv('AI_API_KEY')
if not DEFAULT_API_KEY:
    raise Exception("请设置 AI_API_KEY")

DEFAULT_MODEL = 'glm-4.5-flash'

AI_API_URL = 'https://open.bigmodel.cn/api/paas/v4/chat/completions'

# 系统提示词文件路径（普通对话）
SYSTEM_PROMPT_FILE = r'C:\Users\18175\Desktop\deepseek提示词.txt'

# NSFW 提示词文件路径（默认人物设定）
NSFW_PROMPT_FILE = r'C:\Users\18175\Desktop\nsfw提示词.txt'


def load_system_prompt(file_path=SYSTEM_PROMPT_FILE):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read().strip()
        if not content:
            raise ValueError(f"文件 {file_path} 内容为空")
        print(f"成功从 {file_path} 加载系统提示词，长度: {len(content)} 字符")
        return content


def load_nsfw_prompt(file_path=NSFW_PROMPT_FILE):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read().strip()
        if not content:
            raise ValueError(f"文件 {file_path} 内容为空")
        print(f"成功从 {file_path} 加载 NSFW 提示词，长度: {len(content)} 字符")
        return content


# 加载系统提示词
try:
    SYSTEM_PROMPT = load_system_prompt()
except FileNotFoundError as e:
    print(f"错误: {e}")
    print("程序退出")
    sys.exit(1)
except ValueError as e:
    print(f"错误: {e}")
    print("程序退出")
    sys.exit(1)
except Exception as e:
    print(f"错误: 读取系统提示词失败 - {e}")
    print("程序退出")
    sys.exit(1)

# 加载 NSFW 提示词
try:
    NSFW_PROMPT = load_nsfw_prompt()
except FileNotFoundError as e:
    print(f"错误: {e}")
    print("程序退出")
    sys.exit(1)
except ValueError as e:
    print(f"错误: {e}")
    print("程序退出")
    sys.exit(1)
except Exception as e:
    print(f"错误: 读取 NSFW 提示词失败 - {e}")
    print("程序退出")
    sys.exit(1)

MAX_CONTINUE = 8  # 最大续写次数


def calculate_length(text):
    """计算中文字数（包含标点，不含英文空格）"""
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]', text))
    en_chars = len(re.findall(r'[a-zA-Z0-9]', text)) * 0.5
    return int(chinese_chars + en_chars)


def is_natural_ending(text):
    """判断文本是否以自然结尾结束"""
    if not text:
        return False
    end_chars = text[-3:] if len(text) >= 3 else text
    natural_endings = ['。', '？', '！', '…', '」', '』', '”', '）', '.', '!', '?']
    for char in natural_endings:
        if char in end_chars:
            return True
    return False


def build_continue_prompt(current_len, target):
    """根据当前字数动态构建续写提示词（引导到目标字数）"""
    if current_len < 10:
        return (
            "请继续往下写，保持原文风和尺度，不要解释、不要重复，直接输出正文。"
            f"整段控制在{target}字左右，自然地展开内容。"
        )
    elif current_len < target * 0.5:
        return (
            "请继续往下写，保持原来的文风和尺度。"
            "把当前这一段自然地展开，推进剧情，不要着急结束。"
            f"整段控制在{target}字左右，现在才写了一半，请继续。"
        )
    elif current_len < target * 0.8:
        remaining = target - current_len
        return (
            f"请继续往下写，现在字数差不多到了一半多（约{current_len}字）。"
            f"请用大约{remaining}到{remaining + 20}字把当前情节自然收尾，"
            "不要开启新情节，不要重复，写出一个完整、自然的结尾。"
            "结尾要完整、有温度，让人感觉故事圆满结束了。"
        )
    else:
        return (
            "字数已经差不多了，请立即收尾。"
            "用简练的一两句话把当前段落结束，"
            "写出一个完整、自然的结尾句，不要开启新内容。"
            f"总字数控制在{target}字左右。"
        )


@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json()
    messages = data.get('messages', [])
    deep_think = data.get('deep_think', False)
    nsfw_enabled = data.get('nsfw_enabled', False)  # NSFW 开关
    nsfw_mode = data.get('nsfw_mode', 'default')   # NSFW 模式: 'default' 或 'custom'
    nsfw_custom_prompt = data.get('nsfw_custom_prompt', '').strip()  # 自定义提示词

    # 读取前端设置
    user_api_key = data.get('api_key', '').strip()
    user_model = data.get('model', '').strip()
    user_max_tokens = data.get('max_tokens', 0)

    # 确定最终使用的参数
    final_api_key = user_api_key if user_api_key else DEFAULT_API_KEY
    final_model = user_model if user_model else DEFAULT_MODEL

    # 目标字数（前端传递的挡位，默认 30）
    target_word_count = user_max_tokens if user_max_tokens > 0 else 30

    # 转换为 token 数（乘 2.5，再加余量）
    final_max_tokens = int(target_word_count * 2.5) + 50

    #  确定系统提示词
    if nsfw_enabled:
        if nsfw_mode == 'custom' and nsfw_custom_prompt:
            system_prompt = nsfw_custom_prompt
            print(f"[NSFW] 使用自定义提示词，长度: {len(system_prompt)} 字符")
        else:
            system_prompt = NSFW_PROMPT
            print(f"[NSFW] 使用默认提示词（文件），长度: {len(system_prompt)} 字符")
    else:
        system_prompt = SYSTEM_PROMPT
        print(f"[普通] 使用系统提示词，长度: {len(system_prompt)} 字符")

    print(
        f"[配置] 模型: {final_model}, 目标字数: {target_word_count}, NSFW: {nsfw_enabled}, max_tokens: {final_max_tokens}")

    if not messages or len(messages) == 0:
        return jsonify({'code': 400, 'message': '消息列表不能为空'}), 400

    # 构建消息列表
    formatted_messages = []
    for msg in messages:
        formatted_messages.append({
            'role': msg.get('role'),
            'content': msg.get('content', '')
        })

    # 插入系统提示词
    if not formatted_messages or formatted_messages[0].get('role') != 'system':
        formatted_messages.insert(0, {
            'role': 'system',
            'content': system_prompt
        })
    else:
        # 如果已有 system 消息，替换它
        formatted_messages[0]['content'] = system_prompt

    # 基础请求参数（使用动态值）
    payload = {
        'model': final_model,
        'messages': formatted_messages,
        'stream': True,
        'max_tokens': final_max_tokens,
        'temperature': 0.88,
        'thinking': {
            'type': 'enabled' if deep_think else 'disabled'
        }
    }

    def generate():
        full_content = ""

        try:
            #  第一次请求
            response = requests.post(
                AI_API_URL,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {final_api_key}'
                },
                json=payload,
                stream=True,
                timeout=120
            )

            if response.status_code != 200:
                error_msg = f"AI服务异常: {response.status_code} - {response.text}"
                yield f"data: {json.dumps({'choices': [{'delta': {'content': f'出错了：{error_msg}'}}]}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return

            # 第一次请求，先完整收集内容
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            full_content += content
                            yield f"{line}\n\n"
                    except:
                        yield f"{line}\n\n"

            #  如果 NSFW 未开启，直接返回（不续写）
            if not nsfw_enabled:
                print("[NSFW 关闭] 不续写，直接返回")
                yield "data: [DONE]\n\n"
                return

            # NSFW 开启：智能续写逻辑
            print(f"[NSFW 开启] 开始续写，目标字数: {target_word_count}")
            continue_count = 0
            empty_count = 0

            # 动态目标（严格按用户选择）
            TARGET = target_word_count
            # 允许 ±20% 浮动，保证完整结尾
            TARGET_MIN = max(int(TARGET * 0.8), 10)  # 下限：80%，最少10字
            TARGET_MAX = int(TARGET * 1.2) + 10  # 上限：120% + 10字

            print(f"[目标范围] 下限: {TARGET_MIN}, 上限: {TARGET_MAX}")

            while continue_count < MAX_CONTINUE:
                current_len = calculate_length(full_content)
                print(f"[状态] 当前字数: {current_len}, 目标: {TARGET} (允许 {TARGET_MIN}-{TARGET_MAX})")

                # 情况1：已达到目标下限且自然结尾 → 结束
                if current_len >= TARGET_MIN and is_natural_ending(full_content):
                    print(f"[完成] 字数 {current_len}，自然结尾 ✓")
                    break

                # 情况2：达到目标上限 → 强制结束
                if current_len >= TARGET_MAX:
                    print(f"[上限] 字数 {current_len} 达到目标上限 {TARGET_MAX}，强制结束")
                    # 如果结尾不自然，补句号
                    if not is_natural_ending(full_content) and full_content:
                        if full_content[-1] not in ['。', '？', '！', '…', '.', '!', '?']:
                            full_content += '。'
                            yield f"data: {json.dumps({'choices': [{'delta': {'content': '。'}}]}, ensure_ascii=False)}\n\n"
                    break

                # 情况3：需要续写
                need_continue = (
                        current_len < TARGET_MIN or
                        (current_len >= TARGET_MIN and not is_natural_ending(full_content))
                )

                if not need_continue:
                    break

                # 如果内容为空，强制停止
                if not full_content.strip():
                    print("[续写] 内容为空，强制停止")
                    break

                continue_count += 1
                print(f"[续写] 第 {continue_count} 次，当前字数: {current_len}")

                # 构建续写提示词（基于目标字数）
                continue_prompt = build_continue_prompt(current_len, TARGET)

                continue_messages = formatted_messages + [
                    {"role": "assistant", "content": full_content},
                    {"role": "user", "content": continue_prompt}
                ]

                # 续写请求使用相同的模型和 API Key，max_tokens 根据剩余目标调整
                remaining_tokens = int((TARGET - current_len) * 2.5) + 30
                continue_max_tokens = max(min(remaining_tokens, 300), 50)

                continue_payload = {
                    'model': final_model,
                    'messages': continue_messages,
                    'stream': True,
                    'max_tokens': continue_max_tokens,
                    'temperature': 0.85,
                    'thinking': {'type': 'disabled'}
                }

                cont_resp = requests.post(
                    AI_API_URL,
                    headers={
                        'Content-Type': 'application/json',
                        'Authorization': f'Bearer {final_api_key}'
                    },
                    json=continue_payload,
                    stream=True,
                    timeout=120
                )

                if cont_resp.status_code != 200:
                    print(f"[续写] 请求失败: {cont_resp.status_code}")
                    break

                new_content = ""
                for line in cont_resp.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                new_content += content
                                full_content += content
                                yield f"{line}\n\n"
                        except:
                            yield f"{line}\n\n"

                added_len = calculate_length(new_content)
                print(f"[续写] 新增 {added_len} 字，总字数: {calculate_length(full_content)}")

                # 如果续写内容很少，可能是模型觉得已经完整了
                if added_len < 10:
                    empty_count += 1
                    if empty_count >= 2:
                        print("[续写] 连续内容很少，停止")
                        break
                else:
                    empty_count = 0

                # 如果已经达到目标且自然结尾，提前退出
                if calculate_length(full_content) >= TARGET_MIN and is_natural_ending(full_content):
                    print("[完成] 续写后自然结尾 ✓")
                    break

            #  最终检查：如果字数不足目标下限，补一个简短的结尾
            final_len = calculate_length(full_content)
            if final_len < TARGET_MIN and full_content:
                # 如果内容太少，强制补一个句号（虽然不完美，但避免空结尾）
                if not is_natural_ending(full_content):
                    full_content += '。'
                    yield f"data: {json.dumps({'choices': [{'delta': {'content': '。'}}]}, ensure_ascii=False)}\n\n"
            elif final_len >= TARGET_MIN and not is_natural_ending(full_content):
                if full_content and full_content[-1] not in ['。', '？', '！', '…', '.', '!', '?']:
                    full_content += '。'
                    yield f"data: {json.dumps({'choices': [{'delta': {'content': '。'}}]}, ensure_ascii=False)}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            error_data = {
                'choices': [{'delta': {'content': f'出错了：服务端错误 - {str(e)}'}}]
            }
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

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
