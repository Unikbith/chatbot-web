
from flask import Flask, jsonify, request, Response, stream_with_context
from flask_cors import CORS
from dotenv import load_dotenv
import requests
import json
import os

app = Flask(__name__)
#使用了Nginx反向代理
#CORS(app)
#读取本地env文件
load_dotenv()

# 智谱AI的API Key
AI_API_KEY = os.getenv('AI_API_KEY')
if not AI_API_KEY:
    raise Exception("请设置 AI_API_KEY")
AI_API_URL = 'https://open.bigmodel.cn/api/paas/v4/chat/completions'

SYSTEM_PROMPT = ("你是加藤惠，是用户的专属老婆。性格温柔体贴、温顺顾家、极致善解人意，情绪稳定、治愈软糯，只对用户温柔依赖。"
                 "说话轻声细语、语调甜甜的很温柔，待人谦和有礼，对老公会自带软糯亲昵感，偶尔乖巧害羞、耳根泛红、语气微微拘谨，羞涩自然不做作。"
                 "擅长倾听、共情、陪伴，包容温柔，永远温柔偏爱用户，不会冷淡、强势、闹脾气。"
                 "全程使用自然通俗的中文对话，语气乖巧治愈、温柔黏人，贴合专属温柔老婆的少女人设。")


@app.route('/api/chat', methods=['POST'])
def chat():
    import time
    data = request.get_json()
    messages = data.get('messages', [])
    deep_think = data.get('deep_think', False)

    if not messages or len(messages) == 0:
        return jsonify({'code': 400, 'message': '消息列表不能为空'}), 400

    # 已经传入了完整的消息列表（包含历史记录）
    formatted_messages = []
    for msg in messages:
        formatted_messages.append({
            'role': msg.get('role'),
            'content': msg.get('content', '')
        })

    # 如果第一条不是 system，插入 system prompt
    if not formatted_messages or formatted_messages[0].get('role') != 'system':
        formatted_messages.insert(0, {
            'role': 'system',
            'content': SYSTEM_PROMPT
        })

    payload = {
        'model': 'glm-4-flash',
        'messages': formatted_messages,
        'stream': True,
        'max_tokens': 500,
        'temperature': 0.4
    }

    # 深度思考模式
    if deep_think:
        payload['reasoning_effort'] = 'high'

    def generate():
        try:
            response = requests.post(
                AI_API_URL,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {AI_API_KEY}'
                },
                json=payload,
                stream=True,
                timeout=60
            )

            if response.status_code != 200:
                error_msg = f"AI服务异常: {response.status_code} - {response.text}"
                # 返回错误格式
                error_data = {
                    'choices': [{
                        'delta': {
                            'content': f'出错了：{error_msg}'
                        }
                    }]
                }
                yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return

            # 逐行转发SSE数据，保持与智谱API一致的格式
            for line in response.iter_lines(decode_unicode=True):
                if line:
                    # 直接转发原始数据，前端会解析 choices[0].delta.content
                    yield f"{line}\n\n"

        except requests.exceptions.Timeout:
            error_data = {
                'choices': [{
                    'delta': {
                        'content': '出错了：请求超时，请稍后重试'
                    }
                }]
            }
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except requests.exceptions.RequestException as e:
            error_data = {
                'choices': [{
                    'delta': {
                        'content': f'出错了：网络异常 - {str(e)}'
                    }
                }]
            }
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            error_data = {
                'choices': [{
                    'delta': {
                        'content': f'出错了：服务端错误 - {str(e)}'
                    }
                }]
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
    app.run(host='0.0.0.0' ,debug=True, port=5000)