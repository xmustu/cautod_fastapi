from config import Settings
from enum import Enum
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator
import re
settings = Settings()

# 用户角色枚举
class UserRole(str, Enum):
    USER = "user"           # 普通用户
    PREMIUM = "premium"     # 高级用户
    ADMIN = "admin"         # 管理员

# 改进的用户注册请求模型
class UserRegisterRequest(BaseModel):
    username: str = Field(
        ..., 
        min_length=3, 
        max_length=50,
        description="用户名,3-50个字符,支持字母、数字、下划线、中文"
    )
    email: EmailStr = Field(
        ..., 
        description="有效的邮箱地址"
    )
    password: str = Field(
        ..., 
        min_length=6, 
        max_length=128,
        description="密码,6-128个字符"
    )
    
    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        """验证用户名格式"""
        # 去除首尾空格
        v = v.strip()
        
        # 检查长度
        if len(v) < 3:
            raise ValueError('用户名至少需要3个字符')
        if len(v) > 50:
            raise ValueError('用户名不能超过50个字符')
        
        # 检查格式:允许字母、数字、下划线、中文
        if not re.match(r'^[\w\u4e00-\u9fa5]+$', v):
            raise ValueError('用户名只能包含字母、数字、下划线和中文字符')
        
        # 不允许纯数字
        if v.isdigit():
            raise ValueError('用户名不能为纯数字')
        
        # 检查保留关键词
        reserved_usernames = ['admin', 'root', 'system', 'test', 'guest', 'administrator']
        if v.lower() in reserved_usernames:
            raise ValueError('该用户名为保留名称,无法使用')
        
        return v
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        """验证密码强度"""
        # 检查长度
        if len(v) < 6:
            raise ValueError('密码至少需要6个字符')
        if len(v) > 128:
            raise ValueError('密码不能超过128个字符')
        
        # # 检查是否包含大写字母
        # if not re.search(r'[A-Z]', v):
        #     raise ValueError('密码必须包含至少一个大写字母')
        
        # # 检查是否包含小写字母
        # if not re.search(r'[a-z]', v):
        #     raise ValueError('密码必须包含至少一个小写字母')
        
        # # 检查是否包含数字
        # if not re.search(r'\d', v):
        #     raise ValueError('密码必须包含至少一个数字')
        
        # # 检查是否包含特殊字符
        # if not re.search(r'[!@#$%^&*()_+\-=\[\]{};:\'",.<>?/\\|`~]', v):
        #     raise ValueError('密码必须包含至少一个特殊字符 (!@#$%^&*等)')
        
        # # 检查常见弱密码
        # common_passwords = [
        #     'password', 'Password123!', '12345678', 'qwerty', 'abc123',
        #     'password1', 'Password1!', '123456789', 'Aa123456!', 'Admin123!'
        # ]
        # if v in common_passwords:
        #     raise ValueError('密码过于简单,请使用更复杂的密码')
        
        # # 检查是否包含连续字符(如123, abc)
        # if re.search(r'(012|123|234|345|456|567|678|789|abc|bcd|cde)', v.lower()):
        #     raise ValueError('密码不应包含连续的字符序列')
        
        return v

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


class EmailVerificationCodeRequest(BaseModel):
    """发送邮箱验证码请求"""
    email: EmailStr


class EmailRegisterRequest(UserRegisterRequest):
    """邮箱验证码注册请求"""
    verification_code: Optional[str] = None

    @field_validator("verification_code")
    @classmethod
    def validate_verification_code(cls, value: Optional[str]) -> Optional[str]:
        if value in (None, ""):
            return None
        if not value.isdigit():
            raise ValueError("验证码必须为数字")
        if len(value) not in (4, 6):
            raise ValueError("验证码长度必须为4或6位")
        return value


class PasswordResetWithCodeRequest(BaseModel):
    """验证码密码重置请求"""
    email: EmailStr
    verification_code: str
    new_password: str

    @field_validator("verification_code")
    @classmethod
    def validate_reset_code(cls, value: str) -> str:
        if not value or not value.isdigit() or len(value) not in (4, 6):
            raise ValueError("验证码需为4或6位数字")
        return value

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        if len(value) < 6:
            raise ValueError("密码至少需要6个字符")
        if len(value) > 128:
            raise ValueError("密码不能超过128个字符")
        return value

class AuthConfig(BaseModel):
    client_id: str = settings.GITHUB_CLIENT_ID
    client_srecret: str = settings.GITHUB_CLIENT_SECRET
    redirect_url: str = "http://localhost:8080/auth/github/callback"
    token_url: str = "https://github.com/login/oauth/access_token"
    user_url: str = "https://api.github.com/user"