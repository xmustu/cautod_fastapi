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
from typing import List, Optional, Dict
from datetime import datetime, timedelta
from tortoise.expressions import Q
from tortoise.functions import Count

from database.models import Users, Tasks, Conversations, GeometryResults, OptimizationResults, ErrorLogs, UserRole, SystemConfig as SystemConfigModel
from apps.schemas.admin import (
    AdminUserListItem, AdminUserDetail, AdminUserUpdate, AdminUserCreate, AdminBatchDeleteUsers,
    AdminTaskListItem, AdminTaskDetail, AdminTaskUpdate, AdminBatchDeleteTasks,
    SystemStats, UserStatsItem, TaskTypeStats, DailyStats,
    SystemConfig, AdminResponse, PaginatedResponse
)
from core.authentication import User, get_current_active_user
from core.permissions import require_admin
from core.hashing import Hasher
from config import settings
import math
import aiohttp

# 尝试导入系统监控库（已废弃，改为从 optimize 服务获取）
# try:
#     import psutil
#     PSUTIL_AVAILABLE = True
# except ImportError:
#     PSUTIL_AVAILABLE = False

# 尝试导入 GPU 监控库（已废弃，改为从 optimize 服务获取）
# try:
#     import pynvml
#     PYNVML_AVAILABLE = True
# except ImportError:
#     PYNVML_AVAILABLE = False


admin_router = APIRouter(prefix="/admin", tags=["管理员"])


# ============================================
# 系统资源监控辅助函数
# ============================================

async def get_system_resources() -> Dict:
    """
    从 optimize 服务获取系统资源使用情况
    返回 CPU、内存、GPU 等信息
    
    注意：由于后端运行在 Docker 容器中，无法直接获取宿主机资源信息，
    因此改为从运行在 Windows 主机上的 optimize 服务间接获取
    """
    resources = {
        "cpu_usage": None,
        "cpu_cores": None,
        "memory_usage": None,
        "memory_total": None,
        "memory_used": None,
        "memory_available": None,
        "gpu_usage": None,
        "gpu_memory_used": None,
        "gpu_memory_total": None,
        "gpu_count": None,
    }
    
    # 从 optimize 服务获取资源信息
    try:
        optimize_url = f"{settings.OPTIMIZE_API_URL}/system/resources"
        print(f"[系统资源] 正在从 optimize 服务获取资源信息: {optimize_url}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(optimize_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    resources = await resp.json()
                    print(f"[系统资源] ✓ 成功获取资源信息")
                else:
                    print(f"[系统资源] ✗ 获取失败，状态码: {resp.status}")
    except aiohttp.ClientError as e:
        print(f"[系统资源] ✗ 连接 optimize 服务失败: {type(e).__name__}: {e}")
    except Exception as e:
        print(f"[系统资源] ✗ 获取资源信息时出错: {type(e).__name__}: {e}")
    
    return resources


# 旧的本地获取方法（已废弃）
# def get_system_resources() -> Dict:
#     """
#     获取系统资源使用情况
#     返回 CPU、内存、GPU 等信息
#     """
#     resources = {
#         "cpu_usage": None,
#         "cpu_cores": None,
#         "memory_usage": None,
#         "memory_total": None,
#         "memory_used": None,
#         "memory_available": None,
#         "gpu_usage": None,
#         "gpu_memory_used": None,
#         "gpu_memory_total": None,
#         "gpu_count": None,
#     }
    
#     # 获取 CPU 和内存信息
#     if PSUTIL_AVAILABLE:
#         try:
#             # CPU 信息
#             resources["cpu_usage"] = round(psutil.cpu_percent(interval=0.1), 2)
#             resources["cpu_cores"] = psutil.cpu_count(logical=False)  # 物理核心数
#             if resources["cpu_cores"] is None:
#                 resources["cpu_cores"] = psutil.cpu_count(logical=True)  # 逻辑核心数
            
    #         # 内存信息
    #         memory = psutil.virtual_memory()
    #         resources["memory_usage"] = round(memory.percent, 2)
    #         resources["memory_total"] = round(memory.total / (1024 * 1024))  # MB
    #         resources["memory_used"] = round(memory.used / (1024 * 1024))  # MB
    #         resources["memory_available"] = round(memory.available / (1024 * 1024))  # MB
    #     except Exception as e:
    #         # 如果获取失败，保持 None 值
    #         pass
    
    # # 获取 GPU 信息（NVIDIA）
    # if PYNVML_AVAILABLE:
    #     try:
    #         pynvml.nvmlInit()
    #         gpu_count = pynvml.nvmlDeviceGetCount()
    #         resources["gpu_count"] = gpu_count
            
    #         if gpu_count > 0:
    #             # 获取第一个 GPU 的信息（可以扩展为多个 GPU）
    #             handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                
    #             # GPU 使用率
    #             util = pynvml.nvmlDeviceGetUtilizationRates(handle)
    #             resources["gpu_usage"] = round(util.gpu, 2)
                
    #             # GPU 显存信息
    #             mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
    #             resources["gpu_memory_used"] = round(mem_info.used / (1024 * 1024))  # MB
    #             resources["gpu_memory_total"] = round(mem_info.total / (1024 * 1024))  # MB
    #     except Exception as e:
    #         # 如果获取失败，保持 None 值
    #         pass
    
    # return resources


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
    - 系统资源使用情况（CPU、内存、显存）
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
    
    # 获取系统资源信息
    system_resources = await get_system_resources()
    print("system_resources: ",system_resources)
    return SystemStats(
        total_users=total_users,
        total_tasks=total_tasks,
        total_conversations=total_conversations,
        active_tasks=active_tasks,
        completed_tasks=completed_tasks,
        failed_tasks=failed_tasks,
        pending_tasks=pending_tasks,
        users_today=users_today,
        tasks_today=tasks_today,
        cpu_usage=system_resources.get("cpu_usage"),
        cpu_cores=system_resources.get("cpu_cores"),
        memory_usage=system_resources.get("memory_usage"),
        memory_total=system_resources.get("memory_total"),
        memory_used=system_resources.get("memory_used"),
        memory_available=system_resources.get("memory_available"),
        gpu_usage=system_resources.get("gpu_usage"),
        gpu_memory_used=system_resources.get("gpu_memory_used"),
        gpu_memory_total=system_resources.get("gpu_memory_total"),
        gpu_count=system_resources.get("gpu_count"),
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
    获取系统配置
    - 优先从数据库读取
    - 如果数据库中没有配置，则从配置文件读取默认值并初始化到数据库
    """
    # 尝试从数据库读取配置
    db_config = await SystemConfigModel.first()
    
    if db_config:
        # 数据库中有配置，直接返回
        # 注意：enable_email_notifications 和 enable_email_verification 同步
        email_notifications = getattr(db_config, 'enable_email_notifications', db_config.enable_email_verification)
        return SystemConfig(
            max_tasks_per_user=db_config.max_tasks_per_user,
            max_conversations_per_user=db_config.max_conversations_per_user,
            enable_registration=db_config.enable_registration,
            enable_email_verification=db_config.enable_email_verification,
            enable_email_notifications=email_notifications,
            maintenance_mode=db_config.maintenance_mode,
            max_file_size_mb=getattr(db_config, 'max_file_size_mb', 100),
            api_rate_limit=getattr(db_config, 'api_rate_limit', 100),
            session_timeout_minutes=getattr(db_config, 'session_timeout_minutes', 60),
            default_user_role=getattr(db_config, 'default_user_role', 'user')
        )
    else:
        # 数据库中没有配置，从配置文件读取默认值并初始化
        default_config = SystemConfig(
            max_tasks_per_user=settings.SYSTEM_MAX_TASKS_PER_USER,
            max_conversations_per_user=settings.SYSTEM_MAX_CONVERSATIONS_PER_USER,
            enable_registration=settings.SYSTEM_ENABLE_REGISTRATION,
            enable_email_verification=settings.SYSTEM_ENABLE_EMAIL_VERIFICATION,
            enable_email_notifications=settings.SYSTEM_ENABLE_EMAIL_NOTIFICATIONS,
            maintenance_mode=settings.SYSTEM_MAINTENANCE_MODE,
            max_file_size_mb=settings.SYSTEM_MAX_FILE_SIZE_MB,
            api_rate_limit=settings.SYSTEM_API_RATE_LIMIT,
            session_timeout_minutes=settings.SYSTEM_SESSION_TIMEOUT_MINUTES,
            default_user_role=settings.SYSTEM_DEFAULT_USER_ROLE
        )
        
        # 将默认配置保存到数据库
        await SystemConfigModel.create(
            max_tasks_per_user=default_config.max_tasks_per_user,
            max_conversations_per_user=default_config.max_conversations_per_user,
            enable_registration=default_config.enable_registration,
            enable_email_verification=default_config.enable_email_verification,
            enable_email_notifications=default_config.enable_email_notifications,
            maintenance_mode=default_config.maintenance_mode,
            max_file_size_mb=default_config.max_file_size_mb,
            api_rate_limit=default_config.api_rate_limit,
            session_timeout_minutes=default_config.session_timeout_minutes,
            default_user_role=default_config.default_user_role
        )
        
        return default_config


@admin_router.post("/config", summary="更新系统配置", response_model=AdminResponse)
async def update_system_config(
    config: SystemConfig,
    current_user: User = Depends(require_admin)
):
    """
    更新系统配置
    - 更新数据库中的配置记录
    - 如果数据库中没有配置，则创建新记录
    - 注意：enable_email_notifications 和 enable_email_verification 会同步更新
    """
    # 获取或创建配置记录（单例模式，只保留一条记录）
    db_config = await SystemConfigModel.first()
    
    # 处理 enable_email_notifications 和 enable_email_verification 的同步
    # 如果前端传了 enable_email_notifications，用它来更新 enable_email_verification
    email_verification = config.enable_email_verification
    if config.enable_email_notifications is not None:
        email_verification = config.enable_email_notifications
    
    if db_config:
        # 更新现有配置（使用 getattr 兼容可能不存在的字段）
        if config.max_tasks_per_user is not None:
            db_config.max_tasks_per_user = config.max_tasks_per_user
        if config.max_conversations_per_user is not None:
            db_config.max_conversations_per_user = config.max_conversations_per_user
        if config.enable_registration is not None:
            db_config.enable_registration = config.enable_registration
        db_config.enable_email_verification = email_verification
        if hasattr(db_config, 'enable_email_notifications'):
            db_config.enable_email_notifications = config.enable_email_notifications if config.enable_email_notifications is not None else email_verification
        if config.maintenance_mode is not None:
            db_config.maintenance_mode = config.maintenance_mode
        if hasattr(db_config, 'max_file_size_mb'):
            db_config.max_file_size_mb = config.max_file_size_mb if config.max_file_size_mb is not None else db_config.max_file_size_mb
        if hasattr(db_config, 'api_rate_limit'):
            db_config.api_rate_limit = config.api_rate_limit if config.api_rate_limit is not None else db_config.api_rate_limit
        if hasattr(db_config, 'session_timeout_minutes'):
            db_config.session_timeout_minutes = config.session_timeout_minutes if config.session_timeout_minutes is not None else db_config.session_timeout_minutes
        if hasattr(db_config, 'default_user_role'):
            db_config.default_user_role = config.default_user_role if config.default_user_role else db_config.default_user_role
        await db_config.save()
    else:
        # 创建新配置记录
        await SystemConfigModel.create(
            max_tasks_per_user=config.max_tasks_per_user or 100,
            max_conversations_per_user=config.max_conversations_per_user or 50,
            enable_registration=config.enable_registration if config.enable_registration is not None else True,
            enable_email_verification=email_verification,
            enable_email_notifications=config.enable_email_notifications if config.enable_email_notifications is not None else email_verification,
            maintenance_mode=config.maintenance_mode if config.maintenance_mode is not None else False,
            max_file_size_mb=config.max_file_size_mb or 100,
            api_rate_limit=config.api_rate_limit or 100,
            session_timeout_minutes=config.session_timeout_minutes or 60,
            default_user_role=config.default_user_role or 'user'
        )
    
    return AdminResponse(
        status="success",
        message="系统配置更新成功"
    )
