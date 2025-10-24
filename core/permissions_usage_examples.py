"""
权限模块使用示例
演示何时使用依赖项 vs 权限检查类
"""
from fastapi import APIRouter, Depends, HTTPException, status
from core.permissions import require_admin, require_premium_or_admin, get_user_with_role, PermissionChecker
from core.authentication import get_current_active_user, User
from database.models import Tasks, UserRole

router = APIRouter()


# ========================================
# 场景 1: 路由级别的权限控制
# 推荐使用：FastAPI 依赖项
# ========================================

@router.get("/admin/dashboard")
async def admin_dashboard(current_user: User = Depends(require_admin)):
    """
    管理员仪表板 - 只有管理员可以访问
    
    优点：
    - 清晰明了，一眼就能看出这个路由需要管理员权限
    - 自动出现在 OpenAPI 文档中
    - 权限验证失败会自动返回 403
    """
    return {
        "message": "欢迎管理员",
        "admin_email": current_user.email,
        "stats": {
            "total_users": 100,
            "total_tasks": 500
        }
    }


@router.post("/optimize/advanced")
async def advanced_optimize(
    params: dict,
    current_user: User = Depends(require_premium_or_admin)
):
    """
    高级优化功能 - 需要高级用户或管理员权限
    """
    return {
        "message": "开始高级优化",
        "user": current_user.email,
        "optimization_level": "advanced"
    }


# ========================================
# 场景 2: 根据角色返回不同的数据
# 推荐使用：get_user_with_role 依赖项
# ========================================

@router.get("/tasks")
async def get_tasks(user_info: tuple = Depends(get_user_with_role)):
    """
    获取任务列表 - 根据用户角色返回不同范围的数据
    
    - 普通用户：只能看自己的任务
    - 高级用户：只能看自己的任务（但可能有更详细的信息）
    - 管理员：可以看所有任务
    """
    current_user, role = user_info
    
    if role == UserRole.ADMIN:
        # 管理员看所有任务
        tasks = await Tasks.all()
        return {
            "role": "admin",
            "message": "显示所有用户的任务",
            "tasks": tasks
        }
    elif role == UserRole.PREMIUM:
        # 高级用户看自己的任务（含详细信息）
        tasks = await Tasks.filter(user_id=current_user.user_id)
        return {
            "role": "premium",
            "message": "显示您的任务（包含高级信息）",
            "tasks": tasks,
            "detailed_stats": True  # 高级用户可以看额外信息
        }
    else:
        # 普通用户看自己的任务
        tasks = await Tasks.filter(user_id=current_user.user_id)
        return {
            "role": "user",
            "message": "显示您的任务",
            "tasks": tasks
        }


# ========================================
# 场景 3: 业务逻辑中的权限检查
# 推荐使用：PermissionChecker 类
# ========================================

@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: int,
    current_user: User = Depends(get_current_active_user)
):
    """
    删除任务 - 用户可以删除自己的任务，管理员可以删除任何任务
    
    这里不适合用依赖项，因为：
    1. 不是简单的"允许/拒绝"，而是需要根据角色执行不同的逻辑
    2. 需要先获取任务信息，再判断权限
    """
    # 获取任务
    task = await Tasks.get_or_none(task_id=task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # 检查权限
    is_admin = await PermissionChecker.is_admin(current_user.email)
    is_owner = task.user_id == current_user.user_id
    
    if not (is_admin or is_owner):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="您没有权限删除此任务"
        )
    
    # 删除任务
    await task.delete()
    
    return {
        "message": "任务已删除",
        "deleted_by": "admin" if is_admin else "owner"
    }


@router.get("/tasks/{task_id}/details")
async def get_task_details(
    task_id: int,
    current_user: User = Depends(get_current_active_user)
):
    """
    获取任务详情 - 根据用户角色返回不同详细程度的信息
    """
    task = await Tasks.get_or_none(task_id=task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # 获取用户角色
    user_role = await PermissionChecker.get_user_role(current_user.email)
    
    # 基础信息（所有人都能看）
    result = {
        "task_id": task.task_id,
        "task_type": task.task_type,
        "status": task.status,
    }
    
    # 任务所有者或管理员可以看更多信息
    is_admin = await PermissionChecker.is_admin(current_user.email)
    is_owner = task.user_id == current_user.user_id
    
    if is_owner or is_admin:
        result.update({
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "conversation_id": task.conversation_id,
        })
    
    # 只有高级用户和管理员可以看性能指标
    if await PermissionChecker.has_minimum_role(current_user.email, UserRole.PREMIUM):
        result["performance_metrics"] = {
            "execution_time": "5.2s",
            "memory_usage": "256MB"
        }
    
    # 只有管理员可以看系统级信息
    if is_admin:
        result["system_info"] = {
            "worker_id": "worker-01",
            "priority": "normal"
        }
    
    return result


# ========================================
# 场景 4: 混合使用
# 结合依赖项和权限检查类
# ========================================

@router.put("/tasks/{task_id}/assign")
async def assign_task_to_user(
    task_id: int,
    target_user_id: int,
    current_user: User = Depends(require_admin)  # 先确保是管理员
):
    """
    将任务分配给其他用户 - 只有管理员可以操作
    
    这里使用依赖项确保只有管理员能调用这个接口
    """
    task = await Tasks.get_or_none(task_id=task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # 更新任务的用户ID
    task.user_id = target_user_id
    await task.save()
    
    return {
        "message": "任务已重新分配",
        "task_id": task_id,
        "new_owner_id": target_user_id,
        "assigned_by": current_user.email
    }


# ========================================
# 总结：何时使用哪种方式
# ========================================

"""
1. **使用 FastAPI 依赖项** (require_admin, require_premium_or_admin):
   - 整个路由需要特定角色才能访问
   - 权限要求简单明确（是/否）
   - 希望在 OpenAPI 文档中显示权限要求
   
   示例：
   - 管理员专属页面
   - 高级功能入口
   - 敏感操作接口

2. **使用 get_user_with_role 依赖项**:
   - 需要根据用户角色执行不同逻辑
   - 不会拒绝访问，而是返回不同的数据
   
   示例：
   - 数据列表（管理员看全部，用户看自己的）
   - 功能开关（不同角色看到不同功能）

3. **使用 PermissionChecker 类**:
   - 业务逻辑中需要动态判断权限
   - 权限检查依赖于业务数据（如资源所有权）
   - 需要组合多个条件判断
   - 不希望抛出异常，只是想知道是否有权限
   
   示例：
   - 检查用户是否可以编辑某个资源
   - 根据角色显示/隐藏某些信息
   - 资源访问控制（所有者或管理员）

4. **不推荐**:
   - 装饰器方式（已移除）- 在 FastAPI 中不如依赖项优雅
   - 工厂函数（已移除）- 过度设计，增加复杂度
"""
