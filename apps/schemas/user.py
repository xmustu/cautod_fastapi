from pydantic import BaseModel
from config import Settings
from enum import Enum
from datetime import datetime
from typing import Optional

settings = Settings()

# 用户角色枚举
class UserRole(str, Enum):
    USER = "user"           # 普通用户
    PREMIUM = "premium"     # 高级用户
    ADMIN = "admin"         # 管理员

# 用户注册请求模型
class UserRegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    role: Optional[UserRole] = UserRole.USER  # 默认为普通用户

# 用户登录请求模型
class UserLoginRequest(BaseModel):
    email: str
    password: str

# 用户响应模型
class UserResponse(BaseModel):
    user_id: int
    username: str
    email: str
    role: Optional[UserRole] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# 用户更新角色请求模型（仅管理员可用）
class UserRoleUpdateRequest(BaseModel):
    user_id: int
    role: UserRole

# 修改密码请求模型
class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str

# 删除指定用户请求模型（仅管理员可用）
class UserDeleteRequest(BaseModel):
    user_id: int

# 更新用户名请求模型
class UsernameUpdateRequest(BaseModel):
    email: str
    new_username: str

class AuthConfig(BaseModel):
    client_id: str = settings.GITHUB_CLIENT_ID
    client_srecret: str = settings.GITHUB_CLIENT_SECRET
    redirect_url: str = "http://localhost:8080/auth/github/callback"
    token_url: str = "https://github.com/login/oauth/access_token"
    user_url: str = "https://api.github.com/user"