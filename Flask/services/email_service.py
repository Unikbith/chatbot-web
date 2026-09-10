"""邮箱服务 - 基于 QQ 邮箱 SMTP 发送验证码"""
import os
import smtplib
import random
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr


class EmailService:
    """QQ 邮箱 SMTP 服务"""

    SMTP_HOST = os.getenv('SMTP_HOST', 'smtp.qq.com')
    SMTP_PORT = int(os.getenv('SMTP_PORT', '465'))
    SMTP_USER = os.getenv('SMTP_USER', '')  # QQ 邮箱地址（生产务必通过 .env 配置，禁止写死）
    SMTP_PASS = os.getenv('SMTP_PASS', '')  # QQ 邮箱授权码（生产务必通过 .env 配置，禁止写死）
    SENDER_NAME = os.getenv('SENDER_NAME', '心语')

    @classmethod
    def is_configured(cls):
        """检查是否配置了邮箱服务"""
        return bool(cls.SMTP_USER and cls.SMTP_PASS)

    @classmethod
    def generate_code(cls, length=6):
        """生成随机验证码"""
        return ''.join(random.choices(string.digits, k=length))

    @classmethod
    def send_verification_code(cls, to_email, code, purpose='register'):
        """发送验证码邮件

        Args:
            to_email: 收件人邮箱
            code: 验证码
            purpose: 用途 register/reset_password

        Returns:
            (success: bool, error: str|None)
        """
        if not cls.is_configured():
            return False, '邮箱服务未配置，请联系管理员'

        try:
            purpose_text = '注册验证' if purpose == 'register' else '重置密码'
            subject = f'{cls.SENDER_NAME} - {purpose_text}验证码'

            html = f"""
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; border-radius: 12px 12px 0 0; color: white; text-align: center;">
                    <h2 style="margin: 0; font-size: 24px;">{cls.SENDER_NAME}</h2>
                    <p style="margin: 8px 0 0 0; opacity: 0.9;">{purpose_text}</p>
                </div>
                <div style="background: #f9fafb; padding: 40px 30px; border-radius: 0 0 12px 12px;">
                    <p style="margin: 0 0 20px 0; color: #374151; font-size: 16px;">您好！</p>
                    <p style="margin: 0 0 24px 0; color: #6b7280; font-size: 14px; line-height: 1.6;">
                        您正在进行{purpose_text}操作，验证码为：
                    </p>
                    <div style="background: white; border: 2px solid #667eea; border-radius: 8px; padding: 16px; text-align: center; margin-bottom: 24px;">
                        <span style="font-size: 32px; font-weight: bold; color: #667eea; letter-spacing: 8px;">{code}</span>
                    </div>
                    <p style="margin: 0 0 8px 0; color: #6b7280; font-size: 14px;">
                        验证码有效期为 <strong>5 分钟</strong>，请尽快使用。
                    </p>
                    <p style="margin: 0; color: #9ca3af; font-size: 12px;">
                        如果这不是您本人操作，请忽略此邮件。
                    </p>
                </div>
            </div>
            """

            msg = MIMEMultipart('alternative')
            msg['From'] = formataddr((cls.SENDER_NAME, cls.SMTP_USER))
            msg['To'] = Header(to_email, 'utf-8')
            msg['Subject'] = Header(subject, 'utf-8')

            msg.attach(MIMEText(html, 'html', 'utf-8'))

            server = smtplib.SMTP_SSL(cls.SMTP_HOST, cls.SMTP_PORT)
            server.login(cls.SMTP_USER, cls.SMTP_PASS)
            server.sendmail(cls.SMTP_USER, [to_email], msg.as_string())
            server.quit()

            return True, None

        except Exception as e:
            return False, str(e)
