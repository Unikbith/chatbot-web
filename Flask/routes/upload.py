"""文件上传路由 - 头像、背景图等"""
import os
import uuid
from flask import Blueprint, request, jsonify, send_from_directory, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.upload_guard import detect_image_type, MAX_IMAGE_SIZE
from services.media_log import log_media
from extensions import db

upload_bp = Blueprint('upload', __name__, url_prefix='/api/upload')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}
MAX_FILE_SIZE = MAX_IMAGE_SIZE

# 图片属于不可变资源：文件名即 uuid，内容不会变更，可长时间强缓存
IMAGE_CACHE_MAX_AGE = 30 * 24 * 3600  # 30 天


def _allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _ensure_upload_dir():
    """确保上传目录存在"""
    upload_dir = current_app.config.get('UPLOAD_FOLDER')
    if not upload_dir:
        upload_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'uploads')
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir


def save_image_bytes(data, ext, user_id):
    """把图片字节直接存到上传目录，返回可访问 URL。

    供后端接口在「前端未上传 / 上传失败」时兜底落盘使用（识图图片、改图参考图）。
    命名与目录规则与 upload_image 完全一致：uuid + 用户 ID，内容不可变 → 可长缓存。

    :param data: 图片字节
    :param ext: 真实扩展名（由 detect_image_type 得出）
    :param user_id: 所属用户
    :return: 形如 /api/upload/image/<name> 的 URL；data 为空时返回 None
    """
    if not data:
        return None
    ext = (ext or 'jpg').lstrip('.').lower() or 'jpg'
    upload_dir = _ensure_upload_dir()
    filename = f"{uuid.uuid4().hex}_{user_id}.{ext}"
    filepath = os.path.join(upload_dir, filename)
    with open(filepath, 'wb') as f:
        f.write(data)
    return f'/api/upload/image/{filename}'


@upload_bp.route('/image', methods=['POST'])
@jwt_required()
def upload_image():
    """上传图片（头像、背景等）"""
    user_id = int(get_jwt_identity())
    
    if 'file' not in request.files:
        return jsonify({'code': 400, 'message': '未找到文件'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'code': 400, 'message': '未选择文件'}), 400
    
    if not _allowed_file(file.filename):
        return jsonify({'code': 400, 'message': '不支持的图片格式'}), 400
    
    # 先读入内存，校验大小与真实格式（避免先落盘造成脏数据/磁盘占用）
    data = file.read()
    if len(data) == 0:
        return jsonify({'code': 400, 'message': '文件内容为空'}), 400
    if len(data) > MAX_FILE_SIZE:
        return jsonify({'code': 400, 'message': '图片大小不能超过5MB'}), 400
    
    # magic bytes 校验真实图片类型，防止伪装成图片的脚本等危险文件
    detected_ext = detect_image_type(data)
    if detected_ext is None:
        return jsonify({'code': 400, 'message': '文件不是有效的图片'}), 400
    
    upload_dir = _ensure_upload_dir()
    
    # 以检测到的真实类型作为扩展名，避免信任用户文件名
    filename = f"{uuid.uuid4().hex}_{user_id}.{detected_ext}"
    filepath = os.path.join(upload_dir, filename)
    
    with open(filepath, 'wb') as f:
        f.write(data)

    url = f'/api/upload/image/{filename}'

    # 对话素材记录：聊天时发送的图片、头像、背景图最终都走过这个上传接口，
    # 因此这里统一留一条痕迹，管理员在后台能看到用户上传过哪些图。
    # 注意：这里只记录「上传」这一事实，后续用作头像/背景时还会各自再记一条带语义的记录。
    log_media(user_id, 'upload', url)
    db.session.commit()

    return jsonify({
        'code': 200,
        'message': '上传成功',
        'data': {
            'url': url,
            'filename': filename,
            'size': len(data)
        }
    })


@upload_bp.route('/image/<filename>', methods=['GET'])
def get_image(filename):
    """获取上传的图片

    文件名是 uuid，内容不可变，因此开启长缓存 + 条件请求（ETag/Last-Modified），
    避免每次刷新页面都重新下载头像，解决新用户/首次进入时头像加载慢的问题。
    """
    upload_dir = _ensure_upload_dir()
    resp = send_from_directory(
        upload_dir,
        filename,
        max_age=IMAGE_CACHE_MAX_AGE,
        conditional=True,      # 支持 If-None-Match / If-Modified-Since -> 304
        etag=True,
        last_modified=True,
    )
    resp.cache_control.public = True
    resp.cache_control.max_age = IMAGE_CACHE_MAX_AGE
    resp.cache_control.immutable = True
    # 兼容部分代理/调试场景：允许跨域读取图片
    resp.headers.setdefault('Access-Control-Allow-Origin', '*')
    return resp
