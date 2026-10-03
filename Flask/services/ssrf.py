"""SSRF 防护：阻止后端外发请求指向内网 / 回环 / 云元数据等敏感地址。

用户可自配 AI 提供商 api_url，若指向 169.254.169.254（云元数据）或 127.0.0.1 / 内网
服务，可被利用探测服务器内网。本模块按目标 IP 分类并拦截，可用配置开关关闭。
"""
import ipaddress
import socket
from urllib.parse import urlparse


def resolve_ips(host, with_ports=False):
    """解析主机名到候选 IP（优先 IPv4），解析失败返回空列表。"""
    try:
        infos = socket.getaddrinfo(host, None, socket.AF_INET)
    except (socket.gaierror, OSError):
        return []
    ips = []
    for info in infos:
        ip = info[4][0]
        if ip not in ips:
            ips.append(ip)
    return ips


def _classify_ip(ip_str):
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return f"无法识别的地址: {ip_str}"

    if ip.is_loopback:
        return '回环地址'
    if ip.is_link_local:
        return '链路本地地址（可能为云元数据 169.254.169.254）'
    if ip.is_private:
        return '私网地址'
    if ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        return '保留/组播/未指定地址'
    return None


def classify_url(url):
    """判断 URL 目标是否敏感。安全返回 None，否则返回风险描述。"""
    if not url:
        return None
    parsed = urlparse(url)
    # 协议白名单：仅允许 http/https。file:/// gopher:// 等非 HTTP 协议既无必要
    # 也不安全（file 可读本地文件、gopher 可构造任意 TCP payload），一律拦截。
    scheme = (parsed.scheme or '').lower()
    if scheme and scheme not in ('http', 'https'):
        return f"不支持的协议: {scheme or '(空)'}，仅允许 http/https"
    host = parsed.hostname
    if not host:
        return None
    for ip in resolve_ips(host):
        bad = _classify_ip(ip)
        if bad:
            return f"{host} -> {ip}：{bad}"
    return None


def block_ssrf(url, enabled=True):
    """启用时若目标敏感则抛出 ValueError；禁用或安全时无操作。"""
    if not enabled:
        return
    bad = classify_url(url)
    if bad:
        raise ValueError(f"请求被 SSRF 防护拦截：{bad}")


# 出站请求允许的协议白名单：禁止 file:// / gopher:// / ftp:// 等非 HTTP(S) 协议
ALLOWED_SCHEMES = ('http', 'https')

# 参考图允许的最大数量与单个 Data URI 最大长度（约 8MB base64），避免请求体过大
MAX_REFERENCE_IMAGES = 6
MAX_REFERENCE_DATA_URI_LEN = 8 * 1024 * 1024


def check_scheme(url, schemes=ALLOWED_SCHEMES):
    """校验 URL 协议是否在白名单内。安全返回 None，否则返回风险描述。"""
    if not url:
        return '地址为空'
    scheme = (urlparse(url).scheme or '').lower()
    if scheme not in schemes:
        return f"不支持的协议: {scheme or '(空)'}，仅允许 {'/'.join(schemes)}"
    return None


def validate_reference_images(references, enabled=True):
    """校验图生图参考图列表。

    - 仅接受 ``https://`` / ``http://`` 公网 URL 或 ``data:image/...;base64,`` Data URI；
    - 对 URL 调用 SSRF 校验，拦截内网 / 回环 / 云元数据地址（防止诱导第三方
      平台请求内网，或被当作 OOB 探测通道）；
    - 限制列表长度与单个 Data URI 体积。

    返回规范化后的列表；任一元素非法则抛出 ValueError。
    """
    if references is None:
        return []
    if not isinstance(references, list):
        raise ValueError('参考图格式不合法，应为列表')
    if len(references) > MAX_REFERENCE_IMAGES:
        raise ValueError(f'参考图数量过多，最多 {MAX_REFERENCE_IMAGES} 张')

    cleaned = []
    for raw in references:
        if not raw or not isinstance(raw, str):
            continue
        s = raw.strip()
        if not s:
            continue
        if s.startswith('data:'):
            if not s.startswith('data:image/'):
                raise ValueError('参考图 Data URI 必须为图片类型')
            if len(s) > MAX_REFERENCE_DATA_URI_LEN:
                raise ValueError('参考图体积过大，请压缩后重试')
            cleaned.append(s)
            continue
        bad_scheme = check_scheme(s)
        if bad_scheme:
            raise ValueError(f'参考图地址不合法：{bad_scheme}')
        if enabled:
            bad = classify_url(s)
            if bad:
                raise ValueError(f'参考图地址被 SSRF 防护拦截：{bad}')
        cleaned.append(s)

    return cleaned