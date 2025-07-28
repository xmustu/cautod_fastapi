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





user = APIRouter()

templates = Jinja2Templates(directory="templates")

# class UserIn(BaseModel):
#     user_id : int
#     email : str
#     pwd : str

    #@field_validator('name')
    #def name_must_alpha(cls, v):
    #    assert v.isalpha(), 'name must be alpha'
    #    return v

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

@user.post("/google_login")
async def google_login():
    return {"login": "google login"}

@user.get("/register")
async def register_get(request: Request):
    return {"content":"register page"}
    #return templates.TemplateResponse("auth/register.html", {"request": request})

@user.post("/register", summary="用户注册")
async def register(
    user_id: int = Form(),
    email: str = Form(),
    pwd: str = Form()
):
    # 检查用户ID或邮箱是否已存在
    if await Users.filter(user_id=user_id).exists():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该用户ID已被注册")
    if await Users.filter(email=email).exists():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该邮箱已被注册")

    try:
        # 对密码进行哈希处理并创建用户
        hashed_password = Hasher.get_password_hash(pwd)
        user = await Users.create(
            user_id=user_id,
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
