"""文件上传路由 - 头像、背景图等"""
import os
import uuid
from flask import Blueprint, request, jsonify, send_from_directory, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.upload_guard import detect_image_type, MAX_IMAGE_SIZE

upload_bp = Blueprint('upload', __name__, url_prefix='/api/upload')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}
MAX_FILE_SIZE = MAX_IMAGE_SIZE


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
    
    return jsonify({
        'code': 200,
        'message': '上传成功',
        'data': {
            'url': f'/api/upload/image/{filename}',
            'filename': filename,
            'size': len(data)
        }
    })


@upload_bp.route('/image/<filename>', methods=['GET'])
def get_image(filename):
    """获取上传的图片"""
    upload_dir = _ensure_upload_dir()
    return send_from_directory(upload_dir, filename)
