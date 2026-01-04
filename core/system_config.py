"""
系统配置检查工具模块
提供系统配置的获取和验证功能
"""
from typing import Optional
from fastapi import Depends, HTTPException, status
from core.authentication import get_current_active_user, User
from database.models import SystemConfig as SystemConfigModel, Users
from core.permissions import require_admin
from config import settings


async def get_system_config_cached() -> SystemConfigModel:
    """
    获取系统配置（带缓存，如果数据库中没有则从配置文件初始化）
    
    注意：这个方法每次都会查询数据库，如果需要更高性能可以考虑添加缓存
    """
    db_config = await SystemConfigModel.first()
    
    if not db_config:
        # 数据库中没有配置，从配置文件读取默认值并初始化
        db_config = await SystemConfigModel.create(
            max_tasks_per_user=settings.SYSTEM_MAX_TASKS_PER_USER,
            max_conversations_per_user=settings.SYSTEM_MAX_CONVERSATIONS_PER_USER,
            enable_registration=settings.SYSTEM_ENABLE_REGISTRATION,
            enable_email_verification=settings.SYSTEM_ENABLE_EMAIL_VERIFICATION,
            enable_email_notifications=getattr(settings, 'SYSTEM_ENABLE_EMAIL_NOTIFICATIONS', True),
            maintenance_mode=settings.SYSTEM_MAINTENANCE_MODE,
            max_file_size_mb=getattr(settings, 'SYSTEM_MAX_FILE_SIZE_MB', 100),
            api_rate_limit=getattr(settings, 'SYSTEM_API_RATE_LIMIT', 100),
            session_timeout_minutes=getattr(settings, 'SYSTEM_SESSION_TIMEOUT_MINUTES', 60),
            default_user_role=getattr(settings, 'SYSTEM_DEFAULT_USER_ROLE', 'user')
        )
    
    return db_config


async def check_maintenance_mode(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """
    检查系统是否处于维护模式
    如果是维护模式且用户不是管理员，则拒绝请求
    
    使用场景：在所有非管理员接口中使用
    示例:
        @router.post("/some-endpoint")
        async def some_endpoint(current_user: User = Depends(check_maintenance_mode)):
            ...
    """
    system_config = await get_system_config_cached()
    
    if system_config.maintenance_mode:
        # 检查用户是否是管理员
        user = await Users.get_or_none(email=current_user.email)
        if not user or user.role.value != "admin":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="系统当前处于维护模式，请稍后再试"
            )
    
    return current_user


async def check_task_limit(user_id: int) -> None:
    """
    检查用户的任务数量是否超过限制
    
    Args:
        user_id: 用户ID
        
    Raises:
        HTTPException: 如果超过限制则抛出异常
    """
    from database.models import Tasks
    
    system_config = await get_system_config_cached()
    task_count = await Tasks.filter(user_id=user_id).count()
    
    if task_count >= system_config.max_tasks_per_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"任务数量已达到上限（{system_config.max_tasks_per_user}），无法创建新任务"
        )


async def check_conversation_limit(user_id: int) -> None:
    """
    检查用户的会话数量是否超过限制
    
    Args:
        user_id: 用户ID
        
    Raises:
        HTTPException: 如果超过限制则抛出异常
    """
    from database.models import Conversations
    
    system_config = await get_system_config_cached()
    conversation_count = await Conversations.filter(user_id=user_id).count()
    
    if conversation_count >= system_config.max_conversations_per_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"会话数量已达到上限（{system_config.max_conversations_per_user}），无法创建新会话"
        )


async def check_registration_enabled() -> None:
    """
    检查系统是否允许注册
    
    Raises:
        HTTPException: 如果注册被禁用则抛出异常
    """
    system_config = await get_system_config_cached()
    
    if not system_config.enable_registration:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="系统当前不允许新用户注册"
        )




async def check_file_size_async(file_size: int) -> None:
    """
    检查文件大小是否超过限制（异步版本）
    
    Args:
        file_size: 文件大小（字节）
        
    Raises:
        HTTPException: 如果文件大小超过限制则抛出异常
    """
    system_config = await get_system_config_cached()
    max_size_bytes = (system_config.max_file_size_mb or 100) * 1024 * 1024
    
    if file_size > max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"文件大小超过限制（最大 {system_config.max_file_size_mb} MB）"
        )


async def get_default_user_role() -> str:
    """
    获取默认用户角色
    
    Returns:
        默认用户角色字符串
    """
    system_config = await get_system_config_cached()
    return system_config.default_user_role or "user"


async def is_email_verification_enabled() -> bool:
    """
    检查是否启用了邮箱验证
    
    Returns:
        True 如果启用，False 如果禁用
    """
    system_config = await get_system_config_cached()
    return system_config.enable_email_verification


async def is_email_notification_enabled() -> bool:
    """
    检查是否启用了邮件通知
    
    Returns:
        True 如果启用，False 如果禁用
    """
    system_config = await get_system_config_cached()
    return getattr(system_config, 'enable_email_notifications', False)

