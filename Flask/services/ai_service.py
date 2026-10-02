"""AI 服务层 - 统一封装各种 AI API 调用"""
import json
import base64
import os
import time
import uuid
import requests
from flask import current_app
from services.ssrf import block_ssrf


class AIService:
    """AI 服务统一接口"""

    @staticmethod
    def _get_api_config(provider):
        """从模型提供商获取配置"""
        return {
            'api_url': provider.api_url,
            'api_key': provider.api_key,
            'model': provider.model,
            'api_type': provider.api_type,
            'voice': provider.voice,
        }

    @staticmethod
    def _provider_params(provider):
        """获取提供商厂商专属参数（params JSON）"""
        if hasattr(provider, 'get_params'):
            return provider.get_params() or {}
        return {}

    @staticmethod
    def _ssrf_error(provider_url):
        """对用户可控的外部 API 地址做 SSRF 校验，返回错误信息；安全返回 None。"""
        if os.getenv('SSRF_PROTECTION', 'true').lower() != 'true':
            return None
        try:
            block_ssrf(provider_url, True)
        except ValueError as e:
            return str(e)
        return None

    @staticmethod
    def _request_kwargs(provider_params, timeout, override_timeout=None):
        """构造 requests 通用参数（超时、代理）"""
        t = int(override_timeout or provider_params.get('timeout') or timeout)
        kwargs = {'timeout': t}
        proxy = provider_params.get('proxy')
        if proxy:
            kwargs['proxies'] = {'http': proxy, 'https': proxy}
        return kwargs

    @staticmethod
    def _is_versioned_base(url):
        """判断基础地址末尾是否已是版本号路径段（如 /v1 /v2 /v3 /v4）"""
        if not url:
            return False
        seg = url.split('/')[-1]
        return seg.startswith('v') and len(seg) > 1 and seg[1:].isdigit()

    @staticmethod
    def _build_chat_url(api_url):
        """构造 chat/completions URL

        兼容不同厂商：
          - 已含 /chat/completions：原样返回
          - 末尾为版本号路径段（/v1、/v4 等，如智谱 v4）：直接追加 /chat/completions
          - 其它（如裸域名）：追加 /v1/chat/completions
        """
        if not api_url:
            return api_url
        chat_url = api_url.rstrip('/')
        if chat_url.endswith('/chat/completions'):
            return chat_url
        if AIService._is_versioned_base(chat_url):
            return chat_url + '/chat/completions'
        return chat_url + '/v1/chat/completions'

    @staticmethod
    def _resolve_base(api_url):
        """解析出 OpenAI 风格的基础地址（去掉 /chat/completions，保留已带版本号的路径）"""
        if not api_url:
            return api_url
        base_url = api_url
        if base_url.endswith('/chat/completions'):
            base_url = base_url[: -len('/chat/completions')]
        base_url = base_url.rstrip('/')
        if base_url and not AIService._is_versioned_base(base_url):
            base_url += '/v1'
        return base_url

    @staticmethod
    def chat_completions(provider, messages, stream=True,
                         temperature=0.8, frequency_penalty=0.0,
                         presence_penalty=0.0, top_p=0.95,
                         deep_think=False, model=None):
        """
        聊天补全接口
        返回 requests Response 对象（流式）或 JSON（非流式）
        """
        config = AIService._get_api_config(provider)
        model = model or config['model']

        # SSRF 防护
        ssrf_err = AIService._ssrf_error(config['api_url'])
        if ssrf_err:
            return None, ssrf_err

        # 厂商/模型识别（DeepSeek 切换与各家思考参数都依赖，统一提前计算）
        model_lower = (model or config['model'] or '').lower()
        brand = (getattr(provider, 'brand', '') or '').lower()

        # DeepSeek：官方 API 没有「关闭思考」的参数，思考开关靠在
        # deepseek-chat（对话）与 deepseek-reasoner（推理）两个模型间切换。
        # 此前只处理了「开深思 → 切 reasoner」，若用户配置的就是 reasoner，
        # 关掉深思依然是推理模型，导致"默认就在输出思考过程"。
        # 识别规则：api_type=deepseek / brand=deepseek / 模型名含 deepseek，
        # 覆盖中转网关自定义命名的场景。
        is_deepseek = (
            config['api_type'] == 'deepseek' or brand == 'deepseek'
            or 'deepseek' in model_lower
        )
        # 中转网关自定义命名的混合思考模型（如 deepseek-flash）：官方只有
        # deepseek-chat / deepseek-reasoner 两个名字，无法靠改名切换，改为在
        # 请求参数层显式声明思考开关——两种主流约定同时携带（thinking.type 与
        # enable_thinking，覆盖 vLLM/SGLang/NewAPI/GLM 式网关）；网关严格校验
        # 不认这些字段而报 400/422 时，下方自动降级重试（去参重发）。
        extra_thinking_params = None
        if is_deepseek:
            if not deep_think and ('reasoner' in model_lower or 'r1' in model_lower):
                # 关闭深思：推理模型（官方或中转常见命名）切回对话模型
                model = 'deepseek-chat'
            elif deep_think and model_lower == 'deepseek-chat':
                # 开启深思：官方命名的对话模型切到推理模型
                model = 'deepseek-reasoner'
            elif model_lower not in ('deepseek-chat', 'deepseek-reasoner'):
                extra_thinking_params = {
                    'thinking': {'type': 'enabled' if deep_think else 'disabled'},
                    'enable_thinking': bool(deep_think),
                }

        payload = {
            'model': model,
            'messages': messages,
            'stream': stream,
        }
        # 流式场景请求带上 include_usage，让厂商在最后一帧回传 token 用量
        # （部分厂商默认不回传，部分网关不识别该字段会忽略）
        if stream:
            payload['stream_options'] = {'include_usage': True}

        # Qwen3、GLM-4.5/4.7、火山 doubao-seed 等系列默认即进入推理模式，必须在请求里
        # 显式声明关闭深度思考，否则「未启用深思」时模型仍会输出思考过程。
        # 各家参数名不同：阿里 DashScope 用 enable_thinking（布尔），
        # 智谱 GLM 与火山方舟用 thinking.type（enabled/disabled），且 GLM 接口不接受
        # frequency_penalty / presence_penalty，混用会导致 HTTP 400。
        # 识别规则：优先按模型名，其次按厂商 brand（覆盖自建网关/中转改名后的模型）。
        is_zhipu = 'glm' in model_lower or brand == 'zhipu'
        is_qwen_reasoning = (
            ('qwen' in model_lower) or model_lower.startswith('qwq')
            or brand == 'bailian'
        )
        is_glm_reasoning = is_zhipu and any(
            v in model_lower for v in ('4.5', '4.6', '4.7', 'air')
        )
        # 火山方舟 doubao-seed-1.6 等：thinking.type 控制，火山兼容 OpenAI 协议
        is_volc_reasoning = (
            'doubao' in model_lower or 'seed' in model_lower or brand == 'volcengine'
        )
        if is_glm_reasoning or is_volc_reasoning:
            payload['thinking'] = {'type': 'enabled' if deep_think else 'disabled'}
        elif is_qwen_reasoning:
            payload['enable_thinking'] = bool(deep_think)
        if extra_thinking_params:
            payload.update(extra_thinking_params)

        if not deep_think:
            payload.update({
                # 智谱 GLM temperature 取值范围为 [0,1]，超界会返回 400
                'temperature': min(1.0, max(0.0, temperature)) if is_zhipu else temperature,
                'top_p': top_p,
            })
            # 智谱 GLM 接口不支持这两个惩罚参数，发过去会直接 400
            if not is_zhipu:
                payload['frequency_penalty'] = frequency_penalty
                payload['presence_penalty'] = presence_penalty

        chat_url = AIService._build_chat_url(config['api_url'])

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {config["api_key"]}'
        }

        try:
            resp = requests.post(
                chat_url,
                headers=headers,
                json=payload,
                stream=stream,
                timeout=120
            )
            if resp.status_code in (400, 422) and extra_thinking_params:
                # 网关严格校验、不认思考开关字段而拒绝请求：去掉这些字段
                # 原样重试一次；此时无法参数级关思考，由流式过滤层兜底
                try:
                    resp.close()
                except Exception:
                    pass
                retry_payload = {
                    k: v for k, v in payload.items()
                    if k not in ('thinking', 'enable_thinking')
                }
                resp = requests.post(
                    chat_url,
                    headers=headers,
                    json=retry_payload,
                    stream=stream,
                    timeout=120
                )
            return resp, None
        except requests.RequestException as e:
            return None, str(e)

    @staticmethod
    def vision_chat(provider, messages, image_base64, stream=True,
                    temperature=0.7, frequency_penalty=0.0,
                    presence_penalty=0.0, top_p=0.95):
        """
        识图对话接口
        messages: 文本消息列表
        image_base64: base64 编码的图片（不含前缀）
        """
        config = AIService._get_api_config(provider)
        model = config['model']

        # SSRF 防护
        ssrf_err = AIService._ssrf_error(config['api_url'])
        if ssrf_err:
            return None, ssrf_err

        # 构造带图片的消息
        vision_messages = []
        for msg in messages:
            if msg['role'] == 'user':
                vision_messages.append({
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': msg['content']},
                        {
                            'type': 'image_url',
                            'image_url': {
                                'url': f'data:image/jpeg;base64,{image_base64}'
                            }
                        }
                    ]
                })
            else:
                vision_messages.append(msg)

        payload = {
            'model': model,
            'messages': vision_messages,
            'stream': stream,
            'temperature': temperature,
            'top_p': top_p,
        }
        # 智谱 GLM 接口不接受 frequency/presence penalty，发过去会 400
        if 'glm' not in (model or '').lower():
            payload['frequency_penalty'] = frequency_penalty
            payload['presence_penalty'] = presence_penalty

        chat_url = AIService._build_chat_url(config['api_url'])

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {config["api_key"]}'
        }

        try:
            resp = requests.post(
                chat_url,
                headers=headers,
                json=payload,
                stream=stream,
                timeout=120
            )
            return resp, None
        except requests.RequestException as e:
            return None, str(e)

    @staticmethod
    def speech_to_text(provider, audio_data, audio_format='wav'):
        """语音转文字（STT） - OpenAI 兼容接口（阿里百炼 / 火山引擎 compatible-mode）

        使用提供商自身配置的模型 ID（如 qwen3-asr-flash / doubao-asr）。
        """
        config = AIService._get_api_config(provider)
        params = AIService._provider_params(provider)
        model = (provider.model or params.get('model') or 'whisper-1').strip()

        # SSRF 防护
        ssrf_err = AIService._ssrf_error(config['api_url'])
        if ssrf_err:
            return None, ssrf_err

        stt_url = AIService._resolve_base(config['api_url']) + '/audio/transcriptions'

        headers = {'Authorization': f'Bearer {config["api_key"]}'}

        files = {
            'file': ('audio.' + audio_format, audio_data, f'audio/{audio_format}'),
        }
        data = {'model': model}

        try:
            resp = requests.post(
                stt_url,
                headers=headers,
                files=files,
                data=data,
                **AIService._request_kwargs(params, 60)
            )
            if resp.status_code in (200, 201):
                body = resp.json()
                # Openai-compatible 两种返回格式：{text:...} / transcripts[]
                if body.get('text'):
                    return body['text'], None
                arr = body.get('transcripts') or []
                if arr:
                    return ''.join(x.get('text', '') for x in arr), None
                return body, None
            else:
                return None, f"HTTP {resp.status_code}: {resp.text[:300]}"
        except requests.RequestException as e:
            return None, str(e)

    @staticmethod
    def text_to_speech(provider, text, voice=None, format='mp3'):
        """文字转语音（TTS） - 按厂商各自协议调用

        - mimotts / 阿里云百炼（cosyvoice 兼容模式）：OpenAI 兼容 /audio/speech
        - 火山引擎（volcengine）：openspeech 自定义 JSON 接口
        """
        config = AIService._get_api_config(provider)
        params = AIService._provider_params(provider)
        brand = (provider.brand or '').lower()
        # OpenAI 默认音色（alloy 等）只是占位符：用户显式配置的自定义音色应优先，
        # 否则前端默认传 alloy 会覆盖掉厂商专属音色（如百炼 Momo）。
        openai_default_voices = {'alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer'}
        if voice in openai_default_voices:
            voice = params.get('voice') or config.get('voice') or voice
        else:
            voice = voice or params.get('voice') or config.get('voice') or 'alloy'

        # SSRF 防护
        ssrf_err = AIService._ssrf_error(config['api_url'])
        if ssrf_err:
            return None, ssrf_err

        # 火山引擎：openspeech 自定义接口
        if brand == 'volcengine':
            return AIService._volcengine_tts(provider, config, params, text, format, voice)

        # 阿里云百炼：Qwen-TTS / Qwen3-TTS / CosyVoice / Qwen-Audio 系列走 DashScope 原生协议。
        # OpenAI 兼容端点（compatible-mode）不提供 /audio/speech，
        # 原生 /api/v1 地址只能按原生协议调用。
        model = (provider.model or params.get('model') or '').strip()
        model_lower = model.lower()
        if brand == 'bailian' and (
            'tts' in model_lower
            or 'cosyvoice' in model_lower
            or 'qwen-audio' in model_lower
        ):
            return AIService._dashscope_tts(provider, config, params, text, voice)

        # OpenAI 兼容：mimotts / 其它
        resp_format = params.get('output_format') or format

        tts_url = AIService._resolve_base(config['api_url']) + '/audio/speech'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {config["api_key"]}',
        }
        payload = {
            'model': model,
            'input': text,
            'voice': voice,
            'response_format': resp_format,
        }
        # 厂商专属参数（有则附加）
        for k in ('style_prompt', 'dialect', 'seed_text'):
            if params.get(k):
                payload[k] = params[k]

        try:
            resp = requests.post(
                tts_url,
                headers=headers,
                json=payload,
                **AIService._request_kwargs(params, 60)
            )
            if resp.status_code in (200, 201):
                return resp.content, None
            else:
                return None, f"HTTP {resp.status_code}: {resp.text[:300]}"
        except requests.RequestException as e:
            return None, str(e)

    @staticmethod
    def _dashscope_tts(provider, config, params, text, voice):
        """阿里云百炼 TTS 原生协议（OpenAI 兼容端点不支持 /audio/speech）。

        端点按模型族分流：
        - CosyVoice / Qwen-Audio-TTS：POST {base}/services/audio/tts/SpeechSynthesizer
        - Qwen-TTS / Qwen3-TTS：   POST {base}/services/aigc/multimodal-generation/generation

        音频提取兼容三种形态（不同版本/流式返回结构不一致）：
        1. output.audio.url            —— 临时地址，下载后返回字节
        2. output.audio.data            —— base64 内联，直接解码
        3. output.choices[].message.audio.data —— 多模态结构的 base64

        另外支持百炼业务空间专属域名（params.workspace_id）：形如
        https://{workspace_id}.cn-beijing.maas.aliyuncs.com
        """
        model = (provider.model or params.get('model') or '').strip()
        model_lower = model.lower()

        # 业务空间专属域名优先：百炼的 qwen-audio-3.x 只在分配的工作空间域名下可用
        workspace_id = (params.get('workspace_id') or '').strip()
        if workspace_id:
            base = f'https://{workspace_id}.cn-beijing.maas.aliyuncs.com/api/v1'
        else:
            base = (config['api_url'] or 'https://dashscope.aliyuncs.com/api/v1').rstrip('/')

        # 端点分流：SpeechSynthesizer 覆盖 CosyVoice 与 Qwen-Audio（含 3.x）
        is_speech_synth = (
            'cosyvoice' in model_lower
            or 'qwen-audio' in model_lower
            or 'qwen3-tts' in model_lower
            or 'qwen-tts' in model_lower
        )

        if is_speech_synth:
            tts_url = base + '/services/audio/tts/SpeechSynthesizer'
            payload = {
                'model': model,
                'input': {
                    'text': text,
                    'voice': voice,
                    'format': params.get('output_format') or 'mp3',
                },
            }
            if params.get('sample_rate'):
                payload['input']['sample_rate'] = int(params['sample_rate'])
        else:
            tts_url = base + '/services/aigc/multimodal-generation/generation'
            payload = {
                'model': model,
                'input': {
                    'text': text,
                    'voice': voice,
                    'language_type': params.get('language_type') or 'Chinese',
                },
            }
            if params.get('output_format'):
                payload['input']['format'] = params['output_format']
            if params.get('sample_rate'):
                payload['input']['sample_rate'] = int(params['sample_rate'])
            if params.get('instructions'):
                payload['input']['instructions'] = params['instructions']

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {config["api_key"]}',
        }
        # 流式模式：百炼用 SSE 增量返回 base64 音频分片
        stream = str(params.get('stream') or '').lower() in ('1', 'true', 'yes', 'on')
        if stream:
            headers['X-DashScope-SSE'] = 'enable'

        try:
            resp = requests.post(
                tts_url, headers=headers, json=payload,
                **AIService._request_kwargs(params, 90)
            )
            if resp.status_code not in (200, 201):
                return None, f"HTTP {resp.status_code}: {resp.text[:300]}"

            # 流式：逐行解析 data: 事件，拼接 base64 音频分片
            if stream:
                return AIService._collect_dashscope_stream(resp, params)

            body = resp.json()
            output = body.get('output') or {}

            # ① base64 内联（qwen-audio-3.x 非流式直返 data，省一次下载）
            audio_inline = AIService._extract_dashscope_base64(output)
            if audio_inline:
                return audio_inline, None

            # ② 临时音频地址
            audio_url = (output.get('audio') or {}).get('url')
            if not audio_url:
                for ch in output.get('choices') or []:
                    audio_url = ((ch.get('message') or {}).get('audio') or {}).get('url')
                    if audio_url:
                        break
            if not audio_url:
                return None, f'响应缺少音频地址: {resp.text[:300]}'
            audio_resp = requests.get(
                audio_url, **AIService._request_kwargs(params, 60)
            )
            if audio_resp.status_code != 200:
                return None, f'音频下载失败: HTTP {audio_resp.status_code}'
            return audio_resp.content, None
        except requests.RequestException as e:
            return None, str(e)
        except ValueError as e:
            return None, f'响应解析失败: {e}'

    @staticmethod
    def _extract_dashscope_base64(output):
        """从百炼响应里取 base64 内联音频并解码（兼容两种结构）。"""
        candidates = [
            (output.get('audio') or {}).get('data'),
        ]
        for ch in output.get('choices') or []:
            candidates.append(((ch.get('message') or {}).get('audio') or {}).get('data'))
        for data in candidates:
            if not data:
                continue
            try:
                return base64.b64decode(data)
            except (ValueError, TypeError):
                continue
        return None

    @staticmethod
    def _collect_dashscope_stream(resp, params):
        """解析百炼 SSE 流式响应，把各分片的 base64 音频拼成完整字节。

        事件格式：data: {"output":{"audio":{"data":"<base64>"}}} ... data: [DONE]
        注意：分片是「增量音频块」而非完整文件，直接顺序拼接即可播放。
        """
        chunks = []
        for raw in resp.iter_lines(decode_unicode=True):
            if not raw:
                continue
            line = raw.strip()
            if not line.startswith('data:'):
                continue
            payload = line[5:].strip()
            if not payload or payload == '[DONE]':
                continue
            try:
                obj = json.loads(payload)
            except ValueError:
                continue
            data = ((obj.get('output') or {}).get('audio') or {}).get('data')
            if not data:
                continue
            try:
                chunks.append(base64.b64decode(data))
            except (ValueError, TypeError):
                continue
        if not chunks:
            return None, '流式响应未包含音频数据'
        return b''.join(chunks), None

    @staticmethod
    def _volcengine_tts(provider, config, params, text, format, voice):
        """火山引擎 openspeech TTS：
        POST https://openspeech.bytedance.com/api/v1/tts  (JSON)
        """
        tts_url = (config['api_url'] or 'https://openspeech.bytedance.com/api/v1/tts').rstrip('/')
        appid = params.get('appid', '')
        if not appid:
            return None, '缺少 App ID'
        token = config['api_key']
        voice_type = params.get('voice_type') or voice or 'zh_female_wanwanxiaohe_moon_bigtts'

        encoding = {'mp3': 'mp3', 'wav': 'wav', 'pcm': 'raw'}.get(format, format)
        try:
            speed = float(params.get('speed_ratio') or 1.0)
        except (TypeError, ValueError):
            speed = 1.0

        payload = {
            'app': {
                'appid': appid,
                'token': token,
                'cluster': params.get('cluster') or 'volcano_tts',
            },
            'user': {'uid': str(int(time.time() * 1000))},
            'audio': {
                'voice_type': voice_type,
                'encoding': encoding,
                'speed_ratio': speed,
            },
            'request': {
                'reqid': uuid.uuid4().hex,
                'text': text,
                'operation': 'query',
                'with_frontend': 1,
                'frontend_type': 'unitTson',
            },
        }

        try:
            resp = requests.post(
                tts_url,
                json=payload,
                **AIService._request_kwargs(params, 60)
            )
            ctype = resp.headers.get('Content-Type', '')
            if resp.status_code != 200:
                return None, f"HTTP {resp.status_code}: {resp.text[:300]}"
            # 成功也返回 JSON：{"code":3000,"message":"...","data":{...}}
            if 'application/json' in ctype or resp.text.strip().startswith('{'):
                try:
                    body = resp.json()
                except ValueError:
                    body = None
                if body is not None:
                    return None, f"火山引擎返回错误: {body.get('code')}: {body.get('message')}"
            audio = resp.content
            # 跳过 audio 头（若带二进制头）
            if audio[:4] == b'\x01\x00\x00\x00' or len(audio) > 4:
                hlen = int.from_bytes(audio[:4], 'big')
                if 0 < hlen < 1000:
                    audio = audio[4 + hlen:]
            return audio, None
        except requests.RequestException as e:
            return None, str(e)

    @staticmethod
    def list_models(provider):
        """获取模型列表"""
        config = AIService._get_api_config(provider)

        # SSRF 防护
        ssrf_err = AIService._ssrf_error(config['api_url'])
        if ssrf_err:
            return None, ssrf_err

        models_url = AIService._resolve_base(config['api_url']) + '/models'

        headers = {
            'Authorization': f'Bearer {config["api_key"]}'
        }

        try:
            resp = requests.get(
                models_url,
                headers=headers,
                timeout=30
            )
            if resp.status_code == 200:
                return resp.json().get('data', []), None
            else:
                return None, f"HTTP {resp.status_code}: {resp.text[:200]}"
        except requests.RequestException as e:
            return None, str(e)


class FreeAPIProvider:
    """免费 API 提供者（简单的字典对象包装）"""
    def __init__(self, api_url, api_key, model, api_type='openai', name='免费API'):
        self.api_url = api_url
        self.api_key = api_key
        self.model = model
        self.api_type = api_type
        self.name = name
        self.voice = None
