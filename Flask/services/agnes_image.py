"""Agnes AI 图像生成服务（文生图 / 图生图）

端点：POST {api_base}/images/generations（api_base 默认 https://apihub.agnes-ai.cn/v1）
- 文生图：仅需 model / prompt / size
- 图生图：在 extra_body.image 数组中放参考图（公网 URL 或 Data URI Base64）
- 响应：data[0].url；若请求时返回 base64 则由本服务归一化为 Data URI
"""
import requests
from services.ai_service import AIService
from services.vendor_presets import (
    IMAGE_RESOLUTIONS, IMAGE_ASPECT_RATIOS, IMAGE_QUALITIES,
)


def _to_data_uri(value):
    """将参考图输入规范化为 API 接受的格式（公网 URL 原样返回，裸 base64 补 Data URI 前缀）"""
    s = (value or '').strip()
    if not s:
        return ''
    if s.startswith('data:') or s.startswith('http://') or s.startswith('https://'):
        return s
    return f'data:image/png;base64,{s}'


def _extract_image(data):
    """从响应中提取图像 URL / base64"""
    lst = data.get('data')
    if isinstance(lst, list) and lst:
        first = lst[0]
        if isinstance(first, dict):
            if first.get('url'):
                return first['url']
            if first.get('b64_json'):
                return f"data:image/png;base64,{first['b64_json']}"
    if data.get('url'):
        return data['url']
    if data.get('b64_json'):
        return f"data:image/png;base64,{data['b64_json']}"
    if data.get('image'):
        return data['image']
    return None


def pick_enabled_model(provider):
    """取该图片配置下第一个启用的模型 ID"""
    if provider.models:
        for m in provider.models:
            if m.enabled:
                return m.model_id
    return None


def _parse_image_size(data):
    """从 PNG/JPEG 二进制数据中解析原始宽高。解析失败返回 None。"""
    try:
        if data[:8] == b'\x89PNG\r\n\x1a\n' and len(data) >= 24:
            w = int.from_bytes(data[16:20], 'big')
            h = int.from_bytes(data[20:24], 'big')
            return (w, h)
        if data[:2] == b'\xff\xd8':
            idx = 2
            while idx < len(data) - 9:
                if data[idx] != 0xFF:
                    idx += 1
                    continue
                marker = data[idx + 1]
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                              0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    h = int.from_bytes(data[idx + 5:idx + 7], 'big')
                    w = int.from_bytes(data[idx + 7:idx + 9], 'big')
                    if h and w:
                        return (w, h)
                    return None
                if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                    idx += 2
                else:
                    seg = int.from_bytes(data[idx + 2:idx + 4], 'big')
                    if seg < 2:
                        return None
                    idx += 2 + seg
        return None
    except (IndexError, ValueError):
        return None


def _nearest_aspect_ratio(w, h):
    """把原始宽高比映射到 Agnes 官方支持的最接近比例。"""
    if not w or not h:
        return None
    target = w / h
    ratios = [('1:1', 1), ('16:9', 16/9), ('4:3', 4/3), ('3:2', 3/2),
              ('9:16', 9/16), ('3:4', 3/4), ('2:3', 2/3), ('21:9', 21/9)]
    return min(ratios, key=lambda r: abs(r[1] - target))[0]


def _data_uri_bytes(value):
    """从 Data URI 中提取二进制内容；非 base64 数据返回 None。"""
    s = (value or '').strip()
    if not s.startswith('data:image') or ';base64,' not in s:
        return None
    try:
        import base64
        b64 = s.split(';base64,', 1)[1]
        return base64.b64decode(b64)
    except Exception:
        return None


def generate_image(provider, prompt, model=None, reference_images=None,
                   resolution=None, aspect_ratio=None, quality=None):
    """调用 Agnes 生成图像，返回 (image_url 或 data_uri, error)。"""
    err = AIService._ssrf_error(provider.api_url)
    if err:
        return None, f'地址不合法: {err}'

    params = provider.get_params() or {}
    res = resolution or params.get('resolution') or '2K'
    ratio = aspect_ratio or params.get('aspect_ratio') or '1:1'
    q = quality or params.get('quality') or 'auto'
    timeout = int(params.get('timeout') or 120)

    # 改图按参考图原比例生图（需配置开启，且未显式指定比例）
    refs_raw = [r for r in (reference_images or []) if r]
    refs = [_to_data_uri(r) for r in refs_raw]
    if (not aspect_ratio and params.get('ref_aspect_ratio') and refs):
        for ref in refs:
            raw = _data_uri_bytes(ref)
            if not raw:
                continue
            wh = _parse_image_size(raw)
            if wh:
                ratio = _nearest_aspect_ratio(*wh) or ratio
                break

    use_model = model or params.get('image_model') or pick_enabled_model(provider)
    if not use_model:
        # 未配置/启用模型时，回退到内置默认
        use_model = 'agnes-image-2.1-flash'

    if res not in IMAGE_RESOLUTIONS:
        return None, f'不支持的分辨率: {res}，可选: {" / ".join(IMAGE_RESOLUTIONS)}'
    if ratio not in IMAGE_ASPECT_RATIOS:
        return None, f'不支持的长宽比: {ratio}，可选: {" / ".join(IMAGE_ASPECT_RATIOS)}'

    prompt = (prompt or '').strip()
    if not prompt:
        return None, '请填写图片描述'
    if q and q != 'auto':
        final_prompt = f'{prompt}, {q} quality'
    else:
        final_prompt = prompt

    # 使用官方 2.1 推荐的 size(档位)+ratio(比例) 格式，确保各比例精准输出；
    # 旧的固定 WxH 尺寸字符串会被 Agnes 归一化到自带档位，导致 4:5/21:9 等比例失真
    payload = {
        'model': use_model,
        'prompt': final_prompt,
        'size': res,
        'ratio': ratio,
    }
    refs = [_to_data_uri(r) for r in refs_raw]
    if refs:
        payload['extra_body'] = {'image': refs}

    endpoint = provider.api_url.rstrip('/') + '/images/generations'
    headers = {
        'Authorization': f'Bearer {provider.api_key}',
        'Content-Type': 'application/json',
    }
    proxies = None
    if params.get('proxy'):
        proxies = {'http': params['proxy'], 'https': params['proxy']}

    try:
        resp = requests.post(endpoint, headers=headers, json=payload,
                             timeout=timeout, proxies=proxies)
    except requests.RequestException as e:
        return None, f'网络请求失败: {str(e)}'

    if resp.status_code not in (200, 201):
        try:
            body = resp.json()
            msg = body.get('error', {}).get('message', resp.text[:200])
        except Exception:
            msg = resp.text[:200]
        return None, f'HTTP {resp.status_code}: {msg}'

    try:
        data = resp.json()
    except Exception:
        return None, '响应不是合法 JSON'

    image = _extract_image(data)
    if not image:
        return None, '响应中未找到图像地址，请检查模型与 Key 是否有效'
    return image, None