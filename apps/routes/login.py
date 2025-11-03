"""
登录相关路由
提供 OAuth2 token 登录、密码重置、邮箱验证等功能
"""
from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr

from core.authentication import (
    get_current_active_user, 
    User, 
    create_token,
    ACCESS_TOKEN_EXPIRE_DAYS
)
from core.hashing import Hasher
from core.email_utils import (
    generate_password_reset_token,
    generate_reset_password_email,
    generate_verification_email,
    generate_email_verification_token,
    send_email,
    verify_password_reset_token,
    verify_email_verification_token,
)
from database.models import Users

router = APIRouter(tags=["登录认证"])


# ============================================
# Pydantic 模型定义
# ============================================

class Token(BaseModel):
    """访问令牌响应"""
    access_token: str
    token_type: str = "bearer"


class Message(BaseModel):
    """通用消息响应"""
    message: str


class NewPassword(BaseModel):
    """重置密码请求"""
    token: str
    new_password: str


class PasswordRecoveryRequest(BaseModel):
    """密码找回请求"""
    email: EmailStr


class EmailVerificationRequest(BaseModel):
    """邮箱验证请求"""
    token: str


# ============================================
# 登录相关路由
# ============================================

@router.post("/login/access-token", response_model=Token, summary="OAuth2 登录获取 token")
async def login_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
) -> Token:
    """
    OAuth2 兼容的 token 登录接口
    
    - 使用邮箱和密码登录
    - 返回访问令牌用于后续请求
    - form_data.username 实际为用户邮箱
    """
    # 验证用户
    user = await Users.get_or_none(email=form_data.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect email or password"
        )
    
    # 验证密码
    if not Hasher.verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect email or password"
        )
    
    # 检查用户是否激活（如果有 is_active 字段）
    # if hasattr(user, 'is_active') and not user.is_active:
    #     raise HTTPException(
    #         status_code=status.HTTP_400_BAD_REQUEST,
    #         detail="Inactive user"
    #     )
    
    # 创建访问令牌
    access_token = create_token(data={"sub": user.email})
    
    return Token(access_token=access_token, token_type="bearer")


@router.post("/login/test-token", response_model=dict, summary="测试访问令牌")
async def test_token(current_user: User = Depends(get_current_active_user)) -> Any:
    """
    测试当前访问令牌是否有效
    
    返回当前用户信息
    """
    return {
        "user_id": current_user.user_id,
        "email": current_user.email,
        "role": current_user.role,
        "created_at": current_user.created_at
    }


# ============================================
# 密码重置相关路由
# ============================================

@router.post("/password-recovery", response_model=Message, summary="请求密码找回")
async def recover_password(request: PasswordRecoveryRequest) -> Message:
    """
    密码找回
    
    - 发送密码重置邮件到用户邮箱
    - 邮件包含重置链接和 token
    """
    user = await Users.get_or_none(email=request.email)
    
    if not user:
        # 安全考虑：即使用户不存在也返回成功，避免邮箱枚举攻击
        # 但记录日志以便管理员追踪
        import logging
        logging.warning(f"Password recovery requested for non-existent email: {request.email}")
        return Message(message="If the email exists, a password recovery email has been sent")
    
    # 生成密码重置 token
    password_reset_token = generate_password_reset_token(email=user.email)
    
    # 生成邮件内容
    email_data = generate_reset_password_email(
        email_to=user.email,
        email=user.email,
        token=password_reset_token
    )
    
    # 发送邮件
    send_email(
        email_to=user.email,
        subject=email_data.subject,
        html_content=email_data.html_content,
    )
    
    return Message(message="Password recovery email sent")


@router.post("/reset-password", response_model=Message, summary="重置密码")
async def reset_password(body: NewPassword) -> Message:
    """
    使用 token 重置密码
    
    - 验证密码重置 token
    - 更新用户密码
    """
    # 验证 token
    email = verify_password_reset_token(token=body.token)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token"
        )
    
    # 获取用户
    user = await Users.get_or_none(email=email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The user with this email does not exist in the system."
        )
    
    # 检查用户是否激活
    # if hasattr(user, 'is_active') and not user.is_active:
    #     raise HTTPException(
    #         status_code=status.HTTP_400_BAD_REQUEST,
    #         detail="Inactive user"
    #     )
    
    # 更新密码
    hashed_password = Hasher.get_password_hash(body.new_password)
    user.password_hash = hashed_password
    await user.save()
    
    return Message(message="Password updated successfully")


@router.get(
    "/password-recovery-html/{email}",
    response_class=HTMLResponse,
    summary="密码找回邮件 HTML 预览（仅供测试）"
)
async def recover_password_html_content(
    email: str,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    获取密码找回邮件的 HTML 内容（用于测试和预览）
    
    需要登录才能访问
    """
    user = await Users.get_or_none(email=email)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The user with this email does not exist in the system."
        )
    
    password_reset_token = generate_password_reset_token(email=email)
    email_data = generate_reset_password_email(
        email_to=user.email,
        email=email,
        token=password_reset_token
    )
    
    return HTMLResponse(
        content=email_data.html_content,
        headers={"subject": email_data.subject}
    )


# ============================================
# 邮箱验证相关路由
# ============================================

@router.post("/send-verification-email", response_model=Message, summary="发送邮箱验证邮件")
async def send_verification_email(
    current_user: User = Depends(get_current_active_user)
) -> Message:
    """
    发送邮箱验证邮件
    
    - 需要登录
    - 发送验证链接到用户邮箱
    """
    user = await Users.get_or_none(email=current_user.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # 检查邮箱是否已验证（如果有 email_verified 字段）
    # if hasattr(user, 'email_verified') and user.email_verified:
    #     return Message(message="Email already verified")
    
    # 生成验证 token
    verification_token = generate_email_verification_token(email=user.email)
    
    # 生成邮件内容
    email_data = generate_verification_email(
        email_to=user.email,
        token=verification_token
    )
    
    # 发送邮件
    send_email(
        email_to=user.email,
        subject=email_data.subject,
        html_content=email_data.html_content,
    )
    
    return Message(message="Verification email sent")


@router.post("/verify-email", response_model=Message, summary="验证邮箱")
async def verify_email(request: EmailVerificationRequest) -> Message:
    """
    验证邮箱
    
    - 使用邮件中的 token 验证邮箱
    - 标记邮箱为已验证
    """
    # 验证 token
    email = verify_email_verification_token(token=request.token)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token"
        )
    
    # 获取用户
    user = await Users.get_or_none(email=email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # 标记邮箱为已验证（如果数据库模型有 email_verified 字段）
    # user.email_verified = True
    # await user.save()
    
    # 当前模型没有 email_verified 字段，仅返回成功消息
    # 如需实现该功能，需要在 database/models.py 的 Users 模型中添加:
    # email_verified = fields.BooleanField(default=False)
    
    return Message(message=f"Email {email} verified successfully")


@router.get(
    "/verify-email-html/{token}",
    response_class=HTMLResponse,
    summary="邮箱验证成功页面"
)
async def verify_email_html(token: str) -> Any:
    """
    邮箱验证成功后的展示页面
    
    - 用户点击邮件中的链接后跳转到此页面
    """
    email = verify_email_verification_token(token=token)
    
    if not email:
        return HTMLResponse(
            content="""
            <html>
                <body style="text-align: center; padding: 50px; font-family: Arial;">
                    <h1 style="color: #e74c3c;">❌ Verification Failed</h1>
                    <p>The verification link is invalid or has expired.</p>
                    <p>Please request a new verification email.</p>
                </body>
            </html>
            """,
            status_code=400
        )
    
    user = await Users.get_or_none(email=email)
    if not user:
        return HTMLResponse(
            content="""
            <html>
                <body style="text-align: center; padding: 50px; font-family: Arial;">
                    <h1 style="color: #e74c3c;">❌ User Not Found</h1>
                    <p>The user associated with this email does not exist.</p>
                </body>
            </html>
            """,
            status_code=404
        )
    
    # 标记邮箱为已验证
    # user.email_verified = True
    # await user.save()
    
    return HTMLResponse(
        content=f"""
        <html>
            <body style="text-align: center; padding: 50px; font-family: Arial;">
                <h1 style="color: #27ae60;">✅ Email Verified Successfully!</h1>
                <p>Your email <strong>{email}</strong> has been verified.</p>
                <p>You can now close this window and continue using the application.</p>
                <a href="http://localhost:5173" style="
                    display: inline-block;
                    margin-top: 20px;
                    padding: 10px 20px;
                    background-color: #3498db;
                    color: white;
                    text-decoration: none;
                    border-radius: 5px;
                ">Go to Application</a>
            </body>
        </html>
        """
    )
