"""
用户权限验证依赖模块
提供基于角色的访问控制 (RBAC)

推荐使用方式：
1. 路由级别权限控制：使用 require_admin、require_premium_or_admin 依赖项
2. 业务逻辑权限检查：使用 PermissionChecker 类的静态方法

FastAPI 依赖项是最佳实践，因为：
- 自动集成到 OpenAPI 文档
- 更好的类型提示和 IDE 支持
- 符合 FastAPI 的设计理念
"""
from typing import Optional, Tuple
from fastapi import Depends, HTTPException, status
from core.authentication import get_current_active_user, User
from database.models import Users, UserRole


# ============================================
# FastAPI 依赖项 (推荐用于路由装饰)
# ============================================

async def require_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """
    要求管理员权限的依赖项
    
    使用场景：管理员专属功能（如用户管理、系统配置）
    
    示例:
        @router.get("/admin/users")
        async def list_all_users(current_user: User = Depends(require_admin)):
            return {"users": [...]}
    """
    user = await Users.get(email=current_user.email)
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足，需要管理员权限"
        )
    return current_user


async def require_premium_or_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """
    要求高级用户或管理员权限的依赖项
    
    使用场景：高级功能（如高级优化算法、更多资源配额）
    
    示例:
        @router.post("/optimize/advanced")
        async def advanced_optimize(current_user: User = Depends(require_premium_or_admin)):
            return {"result": "advanced optimization"}
    """
    user = await Users.get(email=current_user.email)
    if user.role not in [UserRole.PREMIUM, UserRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足，需要高级用户或管理员权限"
        )
    return current_user


async def get_user_with_role(current_user: User = Depends(get_current_active_user)) -> Tuple[User, UserRole]:
    """
    获取当前用户及其角色（当你需要根据角色执行不同逻辑时使用）
    
    示例:
        @router.get("/tasks")
        async def get_tasks(user_info: tuple = Depends(get_user_with_role)):
            user, role = user_info
            if role == UserRole.ADMIN:
                # 管理员看所有任务
                return await Tasks.all()
            else:
                # 普通用户只看自己的任务
                return await Tasks.filter(user_id=user.user_id)
    """
    user = await Users.get(email=current_user.email)
    return current_user, user.role


# ============================================
# 权限检查工具类 (用于业务逻辑中的权限判断)
# ============================================

class PermissionChecker:
    """
    权限检查工具类
    
    使用场景：在业务逻辑中需要检查权限但不想抛出异常时使用
    
    示例:
        async def process_task(task_id: int, user_email: str):
            # 管理员可以处理任何任务，普通用户只能处理自己的
            if await PermissionChecker.is_admin(user_email):
                task = await Tasks.get(task_id=task_id)
            else:
                task = await Tasks.get(task_id=task_id, user_email=user_email)
            return task
    """
    
    # 角色等级定义（数字越大权限越高）
    ROLE_HIERARCHY = {
        UserRole.USER: 1,
        UserRole.PREMIUM: 2,
        UserRole.ADMIN: 3
    }
    
    @staticmethod
    async def is_admin(user_email: str) -> bool:
        """检查用户是否为管理员"""
        user = await Users.get_or_none(email=user_email)
        return user is not None and user.role == UserRole.ADMIN
    
    @staticmethod
    async def is_premium_or_admin(user_email: str) -> bool:
        """检查用户是否为高级用户或管理员"""
        user = await Users.get_or_none(email=user_email)
        return user is not None and user.role in [UserRole.PREMIUM, UserRole.ADMIN]
    
    @staticmethod
    async def has_role(user_email: str, role: UserRole) -> bool:
        """检查用户是否具有指定角色"""
        user = await Users.get_or_none(email=user_email)
        return user is not None and user.role == role
    
    @staticmethod
    async def has_minimum_role(user_email: str, minimum_role: UserRole) -> bool:
        """
        检查用户是否具有最低要求的角色等级
        
        角色等级: USER(1) < PREMIUM(2) < ADMIN(3)
        
        示例:
            # 检查用户是否至少是高级用户
            if await PermissionChecker.has_minimum_role(email, UserRole.PREMIUM):
                # 可以是 PREMIUM 或 ADMIN
                allow_advanced_features()
        """
        user = await Users.get_or_none(email=user_email)
        if not user:
            return False
        
        user_level = PermissionChecker.ROLE_HIERARCHY.get(user.role, 0)
        required_level = PermissionChecker.ROLE_HIERARCHY.get(minimum_role, 999)
        
        return user_level >= required_level
    
    @staticmethod
    async def get_user_role(user_email: str) -> Optional[UserRole]:
        """获取用户的角色，如果用户不存在返回 None"""
        user = await Users.get_or_none(email=user_email)
        return user.role if user else None
