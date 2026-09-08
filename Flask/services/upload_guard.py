"""上传内容安全校验：大小上限 + 魔数真实类型检测。

上传图片、识图、语音识别等接口统一复用，避免各自重复实现且口径不一致。
"""

MAX_IMAGE_SIZE = 5 * 1024 * 1024   # 图片 5MB
MAX_AUDIO_SIZE = 10 * 1024 * 1024  # 音频 10MB


def detect_image_type(data):
    """通过文件头 magic bytes 检测真实图片格式，返回标准扩展名；非图片返回 None。"""
    if not data:
        return None
    # PNG: 89 50 4E 47 0D 0A 1A 0A
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'png'
    # JPEG: FF D8 FF
    if data[:3] == b'\xff\xd8\xff':
        return 'jpg'
    # GIF: GIF87a / GIF89a
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return 'gif'
    # WebP: RIFF....WEBP
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'webp'
    # BMP: BM
    if data[:2] == b'BM':
        return 'bmp'
    return None


def check_upload(file_storage, max_size=MAX_IMAGE_SIZE):
    """读入上传文件并做基础校验。

    返回 (data, error)：成功时 data 为 bytes、error 为 None；
    失败时 data 为 None、error 为提示文案（供前端展示 / 返回 400）。
    """
    if file_storage is None or not file_storage.filename:
        return None, '未选择文件'
    data = file_storage.read()
    if not data:
        return None, '文件内容为空'
    if len(data) > max_size:
        return None, '文件大小不能超过 {}MB'.format(max_size // (1024 * 1024))
    return data, None