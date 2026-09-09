from routes.auth import auth_bp
from routes.chat import chat_bp
from routes.audio import audio_bp
from routes.provider import provider_bp
from routes.conversation import conversation_bp
from routes.settings import settings_bp
from routes.persona import persona_bp
from routes.upload import upload_bp
from routes.admin import admin_bp
from routes.image import image_bp

__all__ = [
    'auth_bp',
    'chat_bp',
    'audio_bp',
    'provider_bp',
    'conversation_bp',
    'settings_bp',
    'persona_bp',
    'upload_bp',
    'admin_bp',
    'image_bp',
]