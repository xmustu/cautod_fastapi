"""
管理员相关的 Pydantic 模型
用于请求和响应的数据验证
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class UserRole(str, Enum):
    """用户角色枚举"""
    USER = "user"
    PREMIUM = "premium"
    ADMIN = "admin"


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# ============================================
# 用户管理相关模型
# ============================================

class AdminUserListItem(BaseModel):
    """用户列表项（管理员视图）"""
    user_id: int
    username: str
    email: EmailStr
    role: UserRole
    created_at: datetime
    
    class Config:
        from_attributes = True


class AdminUserDetail(BaseModel):
    """用户详细信息（管理员视图）"""
    user_id: int
    username: str
    email: EmailStr
    role: UserRole
    created_at: datetime
    task_count: Optional[int] = 0
    conversation_count: Optional[int] = 0
    
    class Config:
        from_attributes = True


class AdminUserUpdate(BaseModel):
    """管理员更新用户信息"""
    username: Optional[str] = Field(None, max_length=255)
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None


class AdminUserCreate(BaseModel):
    """管理员创建用户"""
    username: str = Field(..., max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=6)
    role: UserRole = UserRole.USER


class AdminBatchDeleteUsers(BaseModel):
    """批量删除用户"""
    user_ids: List[int] = Field(..., min_items=1)


# ============================================
# 任务管理相关模型
# ============================================

class AdminTaskListItem(BaseModel):
    """任务列表项（管理员视图）"""
    task_id: int
    user_id: int
    username: Optional[str] = None
    task_type: str
    status: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class AdminTaskDetail(BaseModel):
    """任务详细信息（管理员视图）"""
    task_id: int
    user_id: int
    username: Optional[str] = None
    conversation_id: Optional[str] = None
    dify_conversation_id: Optional[str] = None
    task_type: str
    status: str
    created_at: datetime
    updated_at: datetime
    geometry_result: Optional[dict] = None
    optimization_result: Optional[dict] = None
    error_logs: Optional[List[dict]] = None
    
    class Config:
        from_attributes = True


class AdminTaskUpdate(BaseModel):
    """管理员更新任务状态"""
    status: Optional[TaskStatus] = None


class AdminBatchDeleteTasks(BaseModel):
    """批量删除任务"""
    task_ids: List[int] = Field(..., min_items=1)


# ============================================
# 统计数据相关模型
# ============================================

class SystemStats(BaseModel):
    """系统统计数据"""
    total_users: int = 0
    total_tasks: int = 0
    total_conversations: int = 0
    active_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    pending_tasks: int = 0
    users_today: int = 0
    tasks_today: int = 0
    # 系统资源信息
    cpu_usage: Optional[float] = None  # CPU 使用率 (%)
    cpu_cores: Optional[int] = None  # CPU 核心数
    memory_usage: Optional[float] = None  # 内存使用率 (%)
    memory_total: Optional[int] = None  # 总内存 (MB)
    memory_used: Optional[int] = None  # 已用内存 (MB)
    memory_available: Optional[int] = None  # 可用内存 (MB)
    gpu_usage: Optional[float] = None  # GPU 使用率 (%)
    gpu_memory_used: Optional[int] = None  # GPU 显存已用 (MB)
    gpu_memory_total: Optional[int] = None  # GPU 显存总量 (MB)
    gpu_count: Optional[int] = None  # GPU 数量


class UserStatsItem(BaseModel):
    """用户统计数据项"""
    user_id: int
    username: str
    email: str
    role: str
    task_count: int
    conversation_count: int
    created_at: datetime


class TaskTypeStats(BaseModel):
    """任务类型统计"""
    task_type: str
    count: int


class DailyStats(BaseModel):
    """每日统计数据"""
    date: str
    user_count: int
    task_count: int
    conversation_count: int


# ============================================
# 系统配置相关模型
# ============================================

class SystemConfig(BaseModel):
    """系统配置"""
    max_tasks_per_user: Optional[int] = 100
    max_conversations_per_user: Optional[int] = 50
    enable_registration: Optional[bool] = True
    enable_email_verification: Optional[bool] = False
    maintenance_mode: Optional[bool] = False


# ============================================
# 通用响应模型
# ============================================

class AdminResponse(BaseModel):
    """管理员操作通用响应"""
    status: str = "success"
    message: str
    data: Optional[dict] = None


class PaginatedResponse(BaseModel):
    """分页响应"""
    total: int
    page: int
    page_size: int
    total_pages: int
    items: List[dict]
