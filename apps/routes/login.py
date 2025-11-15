"""
登录相关路由
提供 OAuth2 token 登录、密码重置、邮箱验证等功能
"""
from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from core.authentication import (
    get_current_active_user,
    User,
    create_token,
)
from core.hashing import Hasher
from core.email_utils import (
    generate_password_reset_token,
    generate_reset_password_email,
    send_email,
    verify_password_reset_token,
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


