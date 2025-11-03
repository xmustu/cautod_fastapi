"""
邮件工具模块
提供邮件发送、模板渲染、密码重置 token 生成等功能
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt
from jwt.exceptions import InvalidTokenError
from jinja2 import Template

from core.authentication import SECRET_KEY, ALGORITHM

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class EmailData:
    html_content: str
    subject: str


def render_email_template(*, template_name: str, context: dict[str, Any]) -> str:
    """
    渲染邮件模板
    
    Args:
        template_name: 模板文件名（如 reset_password.html）
        context: 模板上下文变量
    
    Returns:
        渲染后的 HTML 内容
    """
    template_path = Path(__file__).parent.parent / "templates" / "email" / template_name
    
    if not template_path.exists():
        # 如果模板文件不存在，返回简单的默认模板
        logger.warning(f"Email template {template_name} not found, using default")
        return f"<html><body><h1>{context.get('subject', 'Notification')}</h1><p>{context.get('content', '')}</p></body></html>"
    
    template_str = template_path.read_text(encoding='utf-8')
    html_content = Template(template_str).render(context)
    return html_content


def send_email(
    *,
    email_to: str,
    subject: str = "",
    html_content: str = "",
) -> None:
    """
    发送邮件
    
    Args:
        email_to: 收件人邮箱
        subject: 邮件主题
        html_content: HTML 邮件内容
    
    Raises:
        Exception: 如果邮件发送失败
    """
    from config import settings
    
    # 检查是否启用邮件功能
    if not settings.EMAILS_ENABLED:
        logger.info(f"[邮件功能未启用 - 模拟发送] To: {email_to}, Subject: {subject}")
        logger.info(f"[邮件内容预览] {html_content[:200]}...")
        return
    
    # 验证必需的配置
    if not all([
        settings.SMTP_HOST,
        settings.SMTP_PORT,
        settings.EMAILS_FROM_EMAIL,
        settings.EMAILS_FROM_NAME
    ]):
        logger.error("邮件配置不完整，无法发送邮件")
        logger.info(f"[配置缺失 - 模拟发送] To: {email_to}, Subject: {subject}")
        return
    
    # 实际发送邮件
    try:
        import emails  # type: ignore
        
        message = emails.Message(
            subject=subject,
            html=html_content,
            mail_from=(settings.EMAILS_FROM_NAME, settings.EMAILS_FROM_EMAIL),
        )
        
        smtp_options = {
            "host": settings.SMTP_HOST,
            "port": settings.SMTP_PORT
        }
        
        if settings.SMTP_TLS:
            smtp_options["tls"] = True
        elif settings.SMTP_SSL:
            smtp_options["ssl"] = True
            
        if settings.SMTP_USER:
            smtp_options["user"] = settings.SMTP_USER
        if settings.SMTP_PASSWORD:
            smtp_options["password"] = settings.SMTP_PASSWORD
            
        response = message.send(to=email_to, smtp=smtp_options)
        logger.info(f"邮件发送成功 - To: {email_to}, Subject: {subject}, Response: {response}")
        
    except ImportError:
        logger.error("未安装 emails 库，请运行: pip install emails")
        logger.info(f"[缺少依赖 - 模拟发送] To: {email_to}, Subject: {subject}")
        
    except Exception as e:
        logger.error(f"邮件发送失败 - To: {email_to}, Error: {e}")
        raise


def generate_test_email(email_to: str) -> EmailData:
    """生成测试邮件"""
    from config import settings
    subject = f"{settings.PROJECT_NAME} - Test email"
    html_content = render_email_template(
        template_name="test_email.html",
        context={"project_name": settings.PROJECT_NAME, "email": email_to},
    )
    return EmailData(html_content=html_content, subject=subject)


def generate_reset_password_email(
    email_to: str, 
    email: str, 
    token: str
) -> EmailData:
    """
    生成密码重置邮件
    
    Args:
        email_to: 收件人邮箱
        email: 用户邮箱（用于显示）
        token: 密码重置 token
    """
    from config import settings
    subject = f"{settings.PROJECT_NAME} - Password recovery for user {email}"
    link = f"{settings.FRONTEND_HOST}/reset-password?token={token}"
    html_content = render_email_template(
        template_name="reset_password.html",
        context={
            "project_name": settings.PROJECT_NAME,
            "username": email,
            "email": email_to,
            "valid_hours": settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS,
            "link": link,
        },
    )
    return EmailData(html_content=html_content, subject=subject)


def generate_new_account_email(
    email_to: str, 
    username: str, 
    password: str
) -> EmailData:
    """生成新账户创建邮件"""
    from config import settings
    subject = f"{settings.PROJECT_NAME} - New account for user {username}"
    html_content = render_email_template(
        template_name="new_account.html",
        context={
            "project_name": settings.PROJECT_NAME,
            "username": username,
            "password": password,
            "email": email_to,
            "link": settings.FRONTEND_HOST,
        },
    )
    return EmailData(html_content=html_content, subject=subject)


def generate_password_reset_token(email: str) -> str:
    """
    生成密码重置 token
    
    Args:
        email: 用户邮箱
    
    Returns:
        JWT token
    """
    from config import settings
    delta = timedelta(hours=settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS)
    now = datetime.now(timezone.utc)
    expires = now + delta
    exp = expires.timestamp()
    encoded_jwt = jwt.encode(
        {"exp": exp, "nbf": now, "sub": email},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
    return encoded_jwt


def verify_password_reset_token(token: str) -> str | None:
    """
    验证密码重置 token
    
    Args:
        token: JWT token
    
    Returns:
        如果有效返回邮箱，否则返回 None
    """
    try:
        decoded_token = jwt.decode(
            token, SECRET_KEY, algorithms=[ALGORITHM]
        )
        return str(decoded_token["sub"])
    except InvalidTokenError:
        return None


def generate_email_verification_token(email: str) -> str:
    """
    生成邮箱验证 token
    
    Args:
        email: 用户邮箱
    
    Returns:
        JWT token
    """
    from config import settings
    delta = timedelta(hours=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS)
    now = datetime.now(timezone.utc)
    expires = now + delta
    exp = expires.timestamp()
    encoded_jwt = jwt.encode(
        {"exp": exp, "nbf": now, "sub": email, "type": "email_verification"},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
    return encoded_jwt


def verify_email_verification_token(token: str) -> str | None:
    """
    验证邮箱验证 token
    
    Args:
        token: JWT token
    
    Returns:
        如果有效返回邮箱，否则返回 None
    """
    try:
        decoded_token = jwt.decode(
            token, SECRET_KEY, algorithms=[ALGORITHM]
        )
        if decoded_token.get("type") == "email_verification":
            return str(decoded_token["sub"])
        return None
    except InvalidTokenError:
        return None


def generate_verification_email(
    email_to: str,
    token: str
) -> EmailData:
    """生成邮箱验证邮件"""
    from config import settings
    subject = f"{settings.PROJECT_NAME} - Verify your email address"
    link = f"{settings.FRONTEND_HOST}/verify-email?token={token}"
    html_content = render_email_template(
        template_name="verify_email.html",
        context={
            "project_name": settings.PROJECT_NAME,
            "email": email_to,
            "valid_hours": settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS,
            "link": link,
        },
    )
    return EmailData(html_content=html_content, subject=subject)
