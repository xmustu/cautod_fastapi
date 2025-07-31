from fastapi import APIRouter
from fastapi import Request
from fastapi import Form
from fastapi import status
from fastapi import responses
from fastapi import Depends
from fastapi.exceptions import HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, field_validator
from pydantic import ValidationError 
from database.models_1 import *
from core.hashing import Hasher
from core.authentication import create_token
from typing import List, Optional
from core.authentication import Token, User
from core.authentication import get_current_active_user
import json
import httpx
from config import Settings



user = APIRouter()

templates = Jinja2Templates(directory="templates")

settings = Settings()
# class UserIn(BaseModel):
#     user_id : int
#     email : str
#     pwd : str

    #@field_validator('name')
    #def name_must_alpha(cls, v):
    #    assert v.isalpha(), 'name must be alpha'
    #    return v

class AuthConfig(BaseModel):
    client_id: str = settings.GITHUB_CLIENT_ID
    client_srecret: str = settings.GITHUB_CLIENT_SECRET
    redirect_url: str = "http://localhost:8080/auth/github/callback"
    token_url: str = "https://github.com/login/oauth/access_token"
    user_url: str = "https://api.github.com/user"


@user.get("/me", summary="获取当前用户信息")
async def get_me(current_user: User = Depends(get_current_active_user)):
    # current_user 是从 token 中解码出的 Pydantic 模型
    # 我们用它来从数据库中获取最新的、完整的用户信息
    user_info = await Users.get(email=current_user.email).values(
        "user_id", "email", "created_at"
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

    user = await Users.get(email=email)

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if not Hasher.verify_password(plain_password=password, hashed_password=user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password")
    
    access_token = create_token(data={"sub": user.email})
    """
    response = responses.RedirectResponse(
        "/?alert=Successfully Logged In", status_code=status.HTTP_302_FOUND
    )
    response.set_cookie(
        key="access_token", value=f"Bearer {access_token}", httponly=True
    )
    return response
    """
    return {"status":"success", "access_token":access_token}

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

@user.post("/register", summary="用户注册")
async def register(
    #user_id: int = Form(),
    username: str = Form(),
    email: str = Form(),
    pwd: str = Form()
):
    # 检查用户ID或邮箱是否已存在
    #if await Users.filter(user_id=user_id).exists():
    #    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该用户ID已被注册")
    if await Users.filter(email=email).exists():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该邮箱已被注册")

    try:
        # 对密码进行哈希处理并创建用户
        hashed_password = Hasher.get_password_hash(pwd)
        user = await Users.create(
            #user_id=user_id,
            username=username,
            email=email,
            password_hash=hashed_password,
        )
        # 返回JSON响应而不是重定向
        return {"status": "success", "user_id": user.user_id, "email": user.email}
    except Exception as e:
        # 捕获其他潜在的数据库错误
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@user.get("/{user_id}")
async def get_user(user_id: int):
    user = await Users.get(user_id=user_id).values("user_id", "email", "created_at")
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user
