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
    host = urlparse(url).hostname
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