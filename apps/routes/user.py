import logging

from fastapi import APIRouter
from fastapi import Request
from fastapi import Form
from fastapi import status
from fastapi import responses
from fastapi import Depends
from fastapi.exceptions import HTTPException
from fastapi.templating import Jinja2Templates
from pydantic import EmailStr, ValidationError
import httpx

from database.models import *
from core.hashing import Hasher
from core.authentication import create_token
from core.authentication import  User
from core.authentication import get_current_active_user
from core.permissions import require_admin
from config import settings
from core.email_utils import (
    clear_email_verification_code,
    create_email_verification_code,
    generate_new_account_email,
    generate_password_reset_token,
    generate_reset_password_code_email,
    generate_reset_password_email,
    generate_verification_email,
    send_email,
    verify_email_verification_code,
    verify_password_reset_token,
)

from apps.schemas.user import (
    AuthConfig, 
    UserRegisterRequest,
    UserRole, 
    UserResponse, 
    UserRoleUpdateRequest, 
    PasswordChangeRequest, 
    UserDeleteRequest, 
    UsernameUpdateRequest,
    PasswordRecoveryRequest,
    NewPassword,
    Message,
    EmailVerificationCodeRequest,
    EmailRegisterRequest,
    PasswordResetWithCodeRequest,
)

user = APIRouter()

templates = Jinja2Templates(directory="templates")




@user.get("/me", summary="获取当前用户信息", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_active_user)):
    # current_user 是从 token 中解码出的 Pydantic 模型
    # 我们用它来从数据库中获取最新的、完整的用户信息
    user_info = await Users.get(email=current_user.email).values(
        "user_id", "email", "created_at", "username", "role"
    )
    if not user_info:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user_info

@user.get("/login")
async def login():
    return {"login": "login"}

@user.post("/login",summary="用户登录，获取JWT令牌")
async def login(request: Request,
                email: str = Form(),
                password: str = Form()):

    identifier = email.strip()

    # 允许使用邮箱或用户名登录：先按邮箱查找，不存在再按用户名查找
    user = await Users.get_or_none(email=identifier)
    if not user:
        user = await Users.get_or_none(username=identifier)

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if not Hasher.verify_password(plain_password=password, hashed_password=user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password")
    
    access_token = create_token(data={"sub": user.email})
    return {"status":"success", "access_token":access_token}


# ============================================
# 密码找回相关路由
# ============================================

# @user.post(
#     "/password-recovery-email",
#     response_model=Message,
#     summary="请求密码找回",
# )
# async def recover_password(request: PasswordRecoveryRequest) -> Message:
#     """
#     密码找回流程

#     - 如果邮箱存在则发送密码重置邮件
#     - 如果邮箱不存在返回通用消息，避免被用来枚举邮箱
#     """
#     user = await Users.get_or_none(email=request.email)

#     if not user:
#         logging.warning(
#             "Password recovery requested for non-existent email: %s",
#             request.email,
#         )
#         return Message(message="If the email exists, a password recovery email has been sent")

#     if settings.EMAILS_ENABLED:
#         password_reset_code = create_email_verification_code(email=user.email)
#         email_data = generate_reset_password_code_email(
#             email_to=user.email,
#             code=password_reset_code,
#         )

#         send_email(
#             email_to=user.email,
#             subject=email_data.subject,
#             html_content=email_data.html_content,
#         )
#         return Message(message="Password recovery email sent")

#     password_reset_token = generate_password_reset_token(email=user.email)
#     email_data = generate_reset_password_email(
#         email_to=user.email,
#         email=user.email,
#         token=password_reset_token,
#     )

#     send_email(
#         email_to=user.email,
#         subject=email_data.subject,
#         html_content=email_data.html_content,
#     )

#     return Message(message="Password recovery email sent")


# @user.post(
#     "/reset-password",
#     response_model=Message,
#     summary="重置密码",
# )
# async def reset_password(body: NewPassword) -> Message:
#     """
#     使用邮件中的 token 重置密码

#     - 验证 token
#     - 更新数据库中的密码
#     """
#     email = verify_password_reset_token(token=body.token)
#     if not email:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="Invalid or expired token",
#         )

#     user = await Users.get_or_none(email=email)
#     if not user:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="The user with this email does not exist in the system.",
#         )

#     hashed_password = Hasher.get_password_hash(body.new_password)
#     user.password_hash = hashed_password
#     await user.save()

#     return Message(message="Password updated successfully")


@user.post(
    "/reset-password/code",
    response_model=Message,
    summary="验证码重置密码",
)
async def reset_password_with_code(body: PasswordResetWithCodeRequest) -> Message:
    if not settings.EMAILS_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email verification not enabled",
        )

    if not verify_email_verification_code(body.email, body.verification_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )

    user = await Users.get_or_none(email=body.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The user with this email does not exist in the system.",
        )

    hashed_password = Hasher.get_password_hash(body.new_password)
    user.password_hash = hashed_password
    await user.save()
    clear_email_verification_code(body.email)

    return Message(message="Password updated successfully")

@user.post(
    "/password-recovery/code",
    response_model=Message,
    summary="发送密码重置验证码",
)
async def send_password_reset_code(request: PasswordRecoveryRequest) -> Message:
    """
    发送密码重置验证码
    """
    user = await Users.get_or_none(email=request.email)

    if not user:
        logging.warning(
            "Password reset code requested for non-existent email: %s",
            request.email,
        )
        return Message(message="If the email exists, a reset code has been sent")

    reset_code = create_email_verification_code(email=request.email)
    email_data = generate_reset_password_code_email(
        email_to=request.email,
        code=reset_code,
    )

    send_email(
        email_to=request.email,
        subject=email_data.subject,
        html_content=email_data.html_content,
    )

    return Message(message="Reset code sent")

@user.get("/auth/github", summary="GitHub OAuth2 登录")
async def github_login():
    """重定向到 github OAuth2 授权页面"""
    
    return {
        "auth_url": f"{settings.GITHUB_TOKEN_URL}?client_id={settings.GITHUB_CLIENT_ID}"
    }

@user.get("/auth/github/callback", summary="GitHub OAuth2 回调处理")
async def github_callback(code: str):
    """处理GitHub回调"""
    async with httpx.AsyncClient() as client:
        # 交换访问令牌
        token_response = await client.post(
            settings.GITHUB_TOKEN_URL,
            data={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )
        print("code: ")
        print("token_response: ", token_response)
        access_token = token_response.json().get("access_token")
        if not access_token:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to obtain access token")
        
        # 获取用户信息
        user_response = await client.get(
            settings.GITHUB_USER_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )

        user_data = user_response.json()
        return user_data


@user.get("/auth/google", summary="Google OAuth2 登录")
def google_login():
    """重定向到 Google OAuth2 授权页面"""
    authorization_url = (
        f"{settings.GOOGLE_AUTHORIZATION_URL}?client_id={settings.GOOGLE_CLIENT_ID}&redirect_uri={settings.GOOGLE_REDIRECT_URL}&response_type=code&scope=openid profile email"
    )
    return {"message": "Go to this URL to authorize", "url": authorization_url}

@user.get("/auth/google/callback")
async def google_callback(code: str):
    """接收授权码并交换访问令牌"""
    async with httpx.AsyncClient() as client:
        # 向 Google 请求访问令牌
        token_response = await client.post(
            settings.GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_url": settings.GOOGLE_REDIRECT_URL,
                "grant_type": "authorization_code",
            },
        )
        
        if token_response.status_code != 200:
            raise HTTPException(status_code=token_response.status_code, detail="Error obtaining token")
        
        token_data = token_response.json()
        access_token = token_data["access_token"]

        # 使用访问令牌获取用户信息
        user_info_response = await client.get(
            settings.GOOGLE_USER_INFO_URL, headers={"Authorization": f"Bearer {access_token}"}
        )
        
        if user_info_response.status_code != 200:
            raise HTTPException(status_code=user_info_response.status_code, detail="Error fetching user info")
        
        user_info = user_info_response.json()
        return {"message": "User logged in", "user_info": user_info}


@user.get("/register")
async def register_get(request: Request):
    return {"content":"register page"}
    #return templates.TemplateResponse("auth/register.html", {"request": request})

@user.post("/register", summary="用户注册", response_model=UserResponse)
async def register(request: UserRegisterRequest):
    """
    验证规则:
    - 用户名: 3-50字符, 支持字母/数字/下划线/中文, 不允许纯数字和保留名
    - 邮箱: 标准邮箱格式验证
    - 密码: 8-128字符
    """
    # 1. 检查用户名是否已存在
    if await Users.filter(username=request.username).exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "username_exists",
                "message": "该用户名已被注册",
                "field": "username"
            }
        )
    # 2. 检查邮箱是否已存在
    if await Users.filter(email=request.email).exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "email_exists",
                "message": "该邮箱已被注册",
                "field": "email"
            }
        )
    
    try:
        # 3. 对密码进行哈希处理并创建用户
        hashed_password = Hasher.get_password_hash(request.password)

        # 4. 创建用户
        user = await Users.create(
            #user_id=user_id,
            username=request.username.strip(),  # 去除首尾空格
            email=request.email,
            password_hash=hashed_password,
        )
        # 5. 返回成功响应
        return UserResponse(
            user_id=user.user_id,
            username=user.username,
            email=user.email,
            role=user.role,
            created_at=user.created_at
        )
    except ValidationError as e:
        # Pydantic 验证错误
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "validation_error",
                "message": "输入数据验证失败",
                "details": e.errors()
            }
        )
    except Exception as e:
        # 捕获其他潜在的数据库错误
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail={
                "error": "server_error",
                "message": "注册失败, 请稍后重试",
                "details": str(e)
            }
        )


@user.post(
    "/register/email/send-code",
    response_model=Message,
    summary="发送注册邮箱验证码",
)
async def send_registration_verification_email(
    request: EmailVerificationCodeRequest,
) -> Message:
    """
    发送注册验证码到指定邮箱，用于后续验证。
    """
    if await Users.filter(email=request.email).exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    if not settings.EMAILS_ENABLED:
        return Message(message="Email verification disabled, no code sent")

    verification_code = create_email_verification_code(email=request.email)
    email_data = generate_verification_email(
        email_to=request.email,
        code=verification_code,
    )

    send_email(
        email_to=request.email,
        subject=email_data.subject,
        html_content=email_data.html_content,
    )

    return Message(message="Verification email sent")


@user.post(
    "/register/email",
    response_model=Message,
    status_code=status.HTTP_201_CREATED,
    summary="邮箱验证码注册",
)
async def register_user_with_email(request: EmailRegisterRequest) -> Message:
    """
    通过邮箱验证码完成注册，并发送欢迎邮件。
    """
    username = request.username.strip()

    if await Users.filter(username=username).exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    if await Users.filter(email=request.email).exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    if settings.EMAILS_ENABLED:
        if not request.verification_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verification code is required",
            )
        if not verify_email_verification_code(
            request.email,
            request.verification_code,
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired verification code",
            )
        clear_email_verification_code(request.email)

    hashed_password = Hasher.get_password_hash(request.password)

    try:
        user = await Users.create(
            username=username,
            email=request.email,
            password_hash=hashed_password,
        )
    except Exception as exc:  # pragma: no cover - 数据库异常
        logging.exception("Failed to create user for email registration")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user",
        ) from exc

    try:
        email_data = generate_new_account_email(
            email_to=user.email,
            username=user.username,
            password=request.password,
        )
        send_email(
            email_to=user.email,
            subject=email_data.subject,
            html_content=email_data.html_content,
        )
    except Exception as exc:  # pragma: no cover - 邮件发送异常
        logging.exception("Failed to send registration email, rolling back user creation")
        await user.delete()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send registration email",
        ) from exc

    return Message(message="User registered and welcome email sent")

@user.get("/{user_id}", summary="获取指定用户信息", response_model=UserResponse)
async def get_user(user_id: int,current_user: User = Depends(require_admin)):
    user = await Users.get(user_id=user_id).values("user_id", "email", "created_at", "username", "role")
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@user.put("/update-role", summary="更新用户角色（仅管理员）")
async def update_user_role(
    request: UserRoleUpdateRequest,
    current_user: User = Depends(require_admin)
):
    """
    更新用户角色（仅管理员可操作）
    """
    # 验证当前用户是否为管理员
    admin_user = await Users.get(email=current_user.email)
    if admin_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="权限不足，仅管理员可以修改用户角色"
        )
    
    # 查找要更新的用户
    target_user = await Users.get_or_none(user_id=request.user_id)
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目标用户不存在")
    
    # 更新用户角色
    target_user.role = request.role
    await target_user.save()
    
    return {
        "status": "success",
        "message": f"用户 {target_user.username} 的角色已更新为 {request.role.value}",
        "user_id": target_user.user_id,
        "new_role": request.role.value
    }


@user.delete("/me", summary="删除当前用户（普通用户权限）")
async def delete_current_user(current_user: User = Depends(get_current_active_user)):
    """
    删除当前登录的用户账号
    普通用户只能删除自己的账号
    """
    user_to_delete = await Users.get_or_none(email=current_user.email)
    if not user_to_delete:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    
    # 防止管理员删除自己
    if user_to_delete.role == UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="管理员不能删除自己的账号，请联系其他管理员操作"
        )
    
    # 删除用户
    await user_to_delete.delete()
    
    return {
        "status": "success",
        "message": f"用户 {user_to_delete.username} 已成功删除",
        "deleted_user_id": user_to_delete.user_id
    }


@user.delete("/{user_id}", summary="删除指定用户（仅管理员）")
async def delete_user_by_admin(
    user_id: int,
    current_user: User = Depends(require_admin)
):
    """
    删除指定用户（仅管理员可操作）
    """
    # 验证当前用户是否为管理员
    admin_user = await Users.get(email=current_user.email)
    if admin_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="权限不足，仅管理员可以删除用户"
        )
    
    # 防止管理员删除自己
    if admin_user.user_id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="不能删除自己的账号"
        )
    
    # 查找要删除的用户
    user_to_delete = await Users.get_or_none(user_id=user_id)
    if not user_to_delete:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目标用户不存在")
    
    # 删除用户
    username = user_to_delete.username
    await user_to_delete.delete()
    
    return {
        "status": "success",
        "message": f"用户 {username} 已成功删除",
        "deleted_user_id": user_id
    }


@user.put("/change-password", summary="修改密码（普通用户权限）")
async def change_password(
    request: PasswordChangeRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    修改当前用户的密码
    需要提供旧密码和新密码
    """
    # 获取当前用户完整信息
    user = await Users.get_or_none(email=current_user.email)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    
    # 验证旧密码是否正确
    if not Hasher.verify_password(plain_password=request.old_password, hashed_password=user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="旧密码不正确"
        )
    
    # 检查新密码是否与旧密码相同
    if request.old_password == request.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="新密码不能与旧密码相同"
        )
    
    # 对新密码进行哈希处理并更新
    new_hashed_password = Hasher.get_password_hash(request.new_password)
    user.password_hash = new_hashed_password
    await user.save()
    
    return {
        "status": "success",
        "message": "密码修改成功",
        "user_id": user.user_id
    }


@user.put("/update-username", summary="更新用户名（普通用户权限）")
async def update_username(
    request: UsernameUpdateRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    更新用户名
    用户可以通过提供自己的邮箱来更新用户名
    """
    # 验证请求中的邮箱是否与当前登录用户一致
    if request.email != current_user.email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="只能更新自己的用户名"
        )
    
    # 获取当前用户完整信息
    user = await Users.get_or_none(email=request.email)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    
    # 检查新用户名是否为空
    if not request.new_username or request.new_username.strip() == "":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="用户名不能为空"
        )
    
    # 检查新用户名是否与旧用户名相同
    if user.username == request.new_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="新用户名与当前用户名相同"
        )
    
    # 更新用户名
    old_username = user.username
    user.username = request.new_username
    await user.save()
    
    return {
        "status": "success",
        "message": f"用户名已从 '{old_username}' 更新为 '{request.new_username}'",
        "user_id": user.user_id,
        "old_username": old_username,
        "new_username": request.new_username
    }


