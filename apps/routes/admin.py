"""
管理员路由模块
提供系统管理功能的 API 端点

功能包括：
- 用户管理（CRUD）
- 任务管理（查看、删除、状态更新）
- 系统统计数据
- 系统配置管理
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
from datetime import datetime, timedelta
from tortoise.expressions import Q
from tortoise.functions import Count

from database.models import Users, Tasks, Conversations, GeometryResults, OptimizationResults, ErrorLogs, UserRole
from apps.schemas.admin import (
    AdminUserListItem, AdminUserDetail, AdminUserUpdate, AdminUserCreate, AdminBatchDeleteUsers,
    AdminTaskListItem, AdminTaskDetail, AdminTaskUpdate, AdminBatchDeleteTasks,
    SystemStats, UserStatsItem, TaskTypeStats, DailyStats,
    SystemConfig, AdminResponse, PaginatedResponse
)
from core.authentication import User, get_current_active_user
from core.permissions import require_admin
from core.hashing import Hasher
import math


admin_router = APIRouter(prefix="/admin", tags=["管理员"])


# ============================================
# 系统统计相关路由
# ============================================

@admin_router.get("/stats/overview", summary="获取系统统计概览", response_model=SystemStats)
async def get_system_stats(
    current_user: User = Depends(require_admin)
):
    """
    获取系统整体统计数据
    - 总用户数、任务数、会话数
    - 各状态任务数量
    - 今日新增数据
    """
    # 基础统计
    total_users = await Users.all().count()
    total_tasks = await Tasks.all().count()
    total_conversations = await Conversations.all().count()
    
    # 任务状态统计
    active_tasks = await Tasks.filter(status="running").count()
    completed_tasks = await Tasks.filter(status="completed").count()
    failed_tasks = await Tasks.filter(status="failed").count()
    pending_tasks = await Tasks.filter(status="pending").count()
    
    # 今日统计
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    users_today = await Users.filter(created_at__gte=today_start).count()
    tasks_today = await Tasks.filter(created_at__gte=today_start).count()
    
    return SystemStats(
        total_users=total_users,
        total_tasks=total_tasks,
        total_conversations=total_conversations,
        active_tasks=active_tasks,
        completed_tasks=completed_tasks,
        failed_tasks=failed_tasks,
        pending_tasks=pending_tasks,
        users_today=users_today,
        tasks_today=tasks_today
    )


@admin_router.get("/stats/users", summary="获取用户统计数据", response_model=List[UserStatsItem])
async def get_user_stats(
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(require_admin)
):
    """
    获取用户统计数据（按任务数排序）
    """
    users = await Users.all().order_by('-created_at').limit(limit)
    
    result = []
    for user in users:
        task_count = await Tasks.filter(user_id=user.user_id).count()
        conversation_count = await Conversations.filter(user_id=user.user_id).count()
        
        result.append(UserStatsItem(
            user_id=user.user_id,
            username=user.username,
            email=user.email,
            role=user.role.value,
            task_count=task_count,
            conversation_count=conversation_count,
            created_at=user.created_at
        ))
    
    return result


@admin_router.get("/stats/tasks/types", summary="获取任务类型统计", response_model=List[TaskTypeStats])
async def get_task_type_stats(
    current_user: User = Depends(require_admin)
):
    """
    获取各类型任务的数量统计
    """
    # 手动统计每种任务类型
    from collections import Counter
    
    tasks = await Tasks.all().values('task_type')
    task_type_counts = Counter(task['task_type'] for task in tasks if task.get('task_type'))
    
    return [TaskTypeStats(task_type=task_type, count=count) for task_type, count in task_type_counts.items()]


@admin_router.get("/stats/daily", summary="获取每日统计数据", response_model=List[DailyStats])
async def get_daily_stats(
    days: int = Query(7, ge=1, le=30),
    current_user: User = Depends(require_admin)
):
    """
    获取最近N天的统计数据
    """
    result = []
    for i in range(days):
        date = datetime.now() - timedelta(days=i)
        date_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        date_end = date_start + timedelta(days=1)
        
        user_count = await Users.filter(created_at__gte=date_start, created_at__lt=date_end).count()
        task_count = await Tasks.filter(created_at__gte=date_start, created_at__lt=date_end).count()
        conversation_count = await Conversations.filter(created_at__gte=date_start, created_at__lt=date_end).count()
        
        result.append(DailyStats(
            date=date_start.strftime("%Y-%m-%d"),
            user_count=user_count,
            task_count=task_count,
            conversation_count=conversation_count
        ))
    
    return list(reversed(result))


# ============================================
# 用户管理相关路由
# ============================================

@admin_router.get("/users", summary="获取用户列表（分页）", response_model=PaginatedResponse)
async def get_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    role: Optional[UserRole] = Query(None),
    current_user: User = Depends(require_admin)
):
    """
    获取用户列表，支持分页、搜索、筛选
    """
    query = Users.all()
    
    # 搜索过滤
    if search:
        query = query.filter(
            Q(username__icontains=search) | Q(email__icontains=search)
        )
    
    # 角色过滤
    if role:
        query = query.filter(role=role)
    
    # 总数
    total = await query.count()
    total_pages = math.ceil(total / page_size)
    
    # 分页查询
    offset = (page - 1) * page_size
    users = await query.offset(offset).limit(page_size).order_by('-created_at')
    
    items = [AdminUserListItem.model_validate(user) for user in users]
    
    return PaginatedResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=[item.model_dump() for item in items]
    )


@admin_router.get("/users/{user_id}", summary="获取用户详细信息", response_model=AdminUserDetail)
async def get_user_detail(
    user_id: int,
    current_user: User = Depends(require_admin)
):
    """
    获取指定用户的详细信息
    """
    user = await Users.get_or_none(user_id=user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    
    task_count = await Tasks.filter(user_id=user_id).count()
    conversation_count = await Conversations.filter(user_id=user_id).count()
    
    return AdminUserDetail(
        user_id=user.user_id,
        username=user.username,
        email=user.email,
        role=user.role,
        created_at=user.created_at,
        task_count=task_count,
        conversation_count=conversation_count
    )


@admin_router.post("/users", summary="创建新用户", response_model=AdminResponse)
async def create_user(
    user_data: AdminUserCreate,
    current_user: User = Depends(require_admin)
):
    """
    管理员创建新用户
    """
    # 检查邮箱是否已存在
    existing_user = await Users.get_or_none(email=user_data.email)
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邮箱已被注册")
    
    # 创建用户
    hashed_password = Hasher.get_password_hash(user_data.password)
    new_user = await Users.create(
        username=user_data.username,
        email=user_data.email,
        password_hash=hashed_password,
        role=user_data.role
    )
    
    return AdminResponse(
        status="success",
        message="用户创建成功",
        data={"user_id": new_user.user_id}
    )


@admin_router.put("/users/{user_id}", summary="更新用户信息", response_model=AdminResponse)
async def update_user(
    user_id: int,
    user_data: AdminUserUpdate,
    current_user: User = Depends(require_admin)
):
    """
    管理员更新用户信息
    """
    user = await Users.get_or_none(user_id=user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    
    # 更新字段
    update_data = user_data.model_dump(exclude_unset=True)
    
    # 检查邮箱唯一性
    if 'email' in update_data:
        existing_user = await Users.get_or_none(email=update_data['email'])
        if existing_user and existing_user.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邮箱已被使用")
    
    await user.update_from_dict(update_data).save()
    
    return AdminResponse(
        status="success",
        message="用户信息更新成功"
    )


@admin_router.delete("/users/{user_id}", summary="删除用户", response_model=AdminResponse)
async def delete_user(
    user_id: int,
    current_user: User = Depends(require_admin)
):
    """
    管理员删除用户（同时删除相关数据）
    """
    user = await Users.get_or_none(user_id=user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    
    # 防止删除自己
    admin_user = await Users.get(email=current_user.email)
    if user.user_id == admin_user.user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除自己")
    
    # 删除用户相关数据
    await Tasks.filter(user_id=user_id).delete()
    await Conversations.filter(user_id=user_id).delete()
    await user.delete()
    
    return AdminResponse(
        status="success",
        message="用户删除成功"
    )


@admin_router.post("/users/batch-delete", summary="批量删除用户", response_model=AdminResponse)
async def batch_delete_users(
    data: AdminBatchDeleteUsers,
    current_user: User = Depends(require_admin)
):
    """
    批量删除用户
    """
    admin_user = await Users.get(email=current_user.email)
    
    # 过滤掉自己的 ID
    user_ids = [uid for uid in data.user_ids if uid != admin_user.user_id]
    
    if not user_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="没有可删除的用户")
    
    # 批量删除
    deleted_count = 0
    for user_id in user_ids:
        user = await Users.get_or_none(user_id=user_id)
        if user:
            await Tasks.filter(user_id=user_id).delete()
            await Conversations.filter(user_id=user_id).delete()
            await user.delete()
            deleted_count += 1
    
    return AdminResponse(
        status="success",
        message=f"成功删除 {deleted_count} 个用户"
    )


# ============================================
# 任务管理相关路由
# ============================================

@admin_router.get("/tasks", summary="获取任务列表（分页）", response_model=PaginatedResponse)
async def get_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    task_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    current_user: User = Depends(require_admin)
):
    """
    获取任务列表，支持分页、筛选
    """
    query = Tasks.all()
    
    # 任务类型过滤
    if task_type:
        query = query.filter(task_type=task_type)
    
    # 状态过滤
    if status:
        query = query.filter(status=status)
    
    # 用户过滤
    if user_id:
        query = query.filter(user_id=user_id)
    
    # 总数
    total = await query.count()
    total_pages = math.ceil(total / page_size)
    
    # 分页查询
    offset = (page - 1) * page_size
    tasks = await query.offset(offset).limit(page_size).order_by('-created_at')
    
    # 获取用户名
    items = []
    for task in tasks:
        user = await Users.get_or_none(user_id=task.user_id)
        item = AdminTaskListItem(
            task_id=task.task_id,
            user_id=task.user_id,
            username=user.username if user else "未知用户",
            task_type=task.task_type,
            status=task.status,
            created_at=task.created_at,
            updated_at=task.updated_at
        )
        items.append(item)
    
    return PaginatedResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=[item.model_dump() for item in items]
    )


@admin_router.get("/tasks/{task_id}", summary="获取任务详细信息", response_model=AdminTaskDetail)
async def get_task_detail(
    task_id: int,
    current_user: User = Depends(require_admin)
):
    """
    获取指定任务的详细信息
    """
    task = await Tasks.get_or_none(task_id=task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    
    # 获取用户信息
    user = await Users.get_or_none(user_id=task.user_id)
    
    # 获取任务结果
    geometry_result = None
    optimization_result = None
    error_logs = None
    
    if task.task_type == "geometry":
        geo_result = await GeometryResults.get_or_none(task_id=task_id)
        if geo_result:
            geometry_result = {
                "geometry_id": geo_result.geometry_id,
                "cad_file_path": geo_result.cad_file_path,
                "code_file_path": geo_result.code_file_path,
                "preview_image_path": geo_result.preview_image_path,
                "created_at": geo_result.created_at.isoformat()
            }
    
    if task.task_type == "optimize":
        opt_result = await OptimizationResults.get_or_none(task_id=task_id)
        if opt_result:
            optimization_result = {
                "optimization_id": opt_result.optimization_id,
                "optimized_cad_file_path": opt_result.optimized_cad_file_path,
                "best_params": opt_result.best_params,
                "final_volume": opt_result.final_volume,
                "final_stress": opt_result.final_stress
            }
    
    # 获取错误日志
    errors = await ErrorLogs.filter(task_id=task_id).all()
    if errors:
        error_logs = [{"error_message": e.error_message, "created_at": e.created_at.isoformat()} for e in errors]
    
    return AdminTaskDetail(
        task_id=task.task_id,
        user_id=task.user_id,
        username=user.username if user else "未知用户",
        conversation_id=task.conversation_id,
        dify_conversation_id=task.dify_conversation_id,
        task_type=task.task_type,
        status=task.status,
        created_at=task.created_at,
        updated_at=task.updated_at,
        geometry_result=geometry_result,
        optimization_result=optimization_result,
        error_logs=error_logs
    )


@admin_router.put("/tasks/{task_id}", summary="更新任务状态", response_model=AdminResponse)
async def update_task(
    task_id: int,
    task_data: AdminTaskUpdate,
    current_user: User = Depends(require_admin)
):
    """
    管理员更新任务状态
    """
    task = await Tasks.get_or_none(task_id=task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    
    update_data = task_data.model_dump(exclude_unset=True)
    await task.update_from_dict(update_data).save()
    
    return AdminResponse(
        status="success",
        message="任务状态更新成功"
    )


@admin_router.delete("/tasks/{task_id}", summary="删除任务", response_model=AdminResponse)
async def delete_task(
    task_id: int,
    current_user: User = Depends(require_admin)
):
    """
    管理员删除任务（同时删除相关结果）
    """
    task = await Tasks.get_or_none(task_id=task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    
    # 删除相关结果
    await GeometryResults.filter(task_id=task_id).delete()
    await OptimizationResults.filter(task_id=task_id).delete()
    await ErrorLogs.filter(task_id=task_id).delete()
    await task.delete()
    
    return AdminResponse(
        status="success",
        message="任务删除成功"
    )


@admin_router.post("/tasks/batch-delete", summary="批量删除任务", response_model=AdminResponse)
async def batch_delete_tasks(
    data: AdminBatchDeleteTasks,
    current_user: User = Depends(require_admin)
):
    """
    批量删除任务
    """
    deleted_count = 0
    for task_id in data.task_ids:
        task = await Tasks.get_or_none(task_id=task_id)
        if task:
            await GeometryResults.filter(task_id=task_id).delete()
            await OptimizationResults.filter(task_id=task_id).delete()
            await ErrorLogs.filter(task_id=task_id).delete()
            await task.delete()
            deleted_count += 1
    
    return AdminResponse(
        status="success",
        message=f"成功删除 {deleted_count} 个任务"
    )


# ============================================
# 系统配置相关路由（预留）
# ============================================

@admin_router.get("/config", summary="获取系统配置", response_model=SystemConfig)
async def get_system_config(
    current_user: User = Depends(require_admin)
):
    """
    获取系统配置（当前为默认值，后续可从数据库或配置文件读取）
    """
    return SystemConfig()


@admin_router.put("/config", summary="更新系统配置", response_model=AdminResponse)
async def update_system_config(
    config: SystemConfig,
    current_user: User = Depends(require_admin)
):
    """
    更新系统配置（后续可实现持久化）
    """
    # TODO: 实现配置持久化到数据库或配置文件
    return AdminResponse(
        status="success",
        message="系统配置更新成功"
    )
