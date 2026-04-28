"""
任务工具函数模块
提供任务相关的辅助函数，如终止检查、统一取消与资源释放等。
"""
import json
import time
from typing import Any, Dict


async def check_task_terminated(redis_client, task_id: int) -> bool:
    """
    检查任务是否被终止
    
    Args:
        redis_client: Redis 客户端（可以是 aioredis 或 redis.asyncio）
        task_id: 任务ID
    
    Returns:
        bool: 如果任务被终止返回 True，否则返回 False
    """
    try:
        terminate_key = f"task_terminate:{task_id}"
        is_terminated = await redis_client.get(terminate_key)
        return is_terminated is not None and is_terminated == "1"
    except Exception as e:
        print(f"检查任务终止状态失败: {e}")
        return False


async def set_task_terminated(redis_client, task_id: int, ttl: int = 300):
    """
    设置任务终止标志
    
    Args:
        redis_client: Redis 客户端
        task_id: 任务ID
        ttl: 过期时间（秒），默认5分钟
    """
    try:
        terminate_key = f"task_terminate:{task_id}"
        await redis_client.setex(terminate_key, ttl, "1")
    except Exception as e:
        print(f"设置任务终止标志失败: {e}")


async def clear_task_terminated(redis_client, task_id: int):
    """
    清除任务终止标志
    
    Args:
        redis_client: Redis 客户端
        task_id: 任务ID
    """
    try:
        terminate_key = f"task_terminate:{task_id}"
        await redis_client.delete(terminate_key)
    except Exception as e:
        print(f"清除任务终止标志失败: {e}")


CANCEL_REASONS = {"user_action", "new_task", "page_leave", "timeout", "admin"}
CANCEL_MODES = {"graceful", "force"}
CANCELLED_STATUS = {"cancelled", "canceled"}
TERMINAL_STATUS = {"done", "failed", "cancelled", "canceled"}


def normalize_cancel_reason(reason: str) -> str:
    return reason if reason in CANCEL_REASONS else "user_action"


def normalize_cancel_mode(mode: str) -> str:
    return mode if mode in CANCEL_MODES else "graceful"


async def register_celery_task_mapping(redis_client, task_id: int, celery_task_id: str, ttl: int = 86400):
    """保存 task_id -> celery_task_id 映射，用于后续 revoke。"""
    if not celery_task_id:
        return
    key = f"task_celery_map:{task_id}"
    try:
        await redis_client.setex(key, ttl, celery_task_id)
    except Exception as e:
        print(f"保存 Celery 任务映射失败: task_id={task_id}, err={e}")


async def cancel_task_execution(
    task,
    redis_client,
    reason: str = "user_action",
    mode: str = "graceful",
    actor_user_id: int = None,
):
    """
    统一、幂等的任务取消入口：
    - 写 Redis 终止标志
    - 按任务类型释放资源（含 Celery revoke）
    - 状态统一落库为 cancelled（兼容旧值）
    - 输出审计日志
    """
    started = time.monotonic()
    reason = normalize_cancel_reason(reason)
    mode = normalize_cancel_mode(mode)
    task_id = int(task.task_id)
    release_errors = []
    release_result = "success"
    already_cancelled = task.status in CANCELLED_STATUS

    if task.status in TERMINAL_STATUS:
        if task.status not in CANCELLED_STATUS:
            release_result = "partial"
        elapsed_ms = int((time.monotonic() - started) * 1000)
        print(
            json.dumps(
                {
                    "event": "task_cancel_audit",
                    "task_id": task_id,
                    "user_id": actor_user_id,
                    "reason": reason,
                    "mode": mode,
                    "elapsed_ms": elapsed_ms,
                    "release_result": release_result,
                    "already_cancelled": already_cancelled,
                    "status_before": task.status,
                    "status_after": task.status,
                    "errors": release_errors,
                },
                ensure_ascii=False,
            )
        )
        return {
            "task_id": task_id,
            "status": task.status,
            "already_cancelled": already_cancelled,
            "release_result": release_result,
            "elapsed_ms": elapsed_ms,
            "errors": release_errors,
        }

    try:
        await set_task_terminated(redis_client, task_id, ttl=300)
    except Exception as e:
        release_errors.append(f"set_terminate_flag_failed:{e}")

    if task.task_type == "optimize":
        try:
            await redis_client.lrem("optimize_queue", 0, str(task_id))
        except Exception as e:
            release_errors.append(f"queue_remove_failed:{e}")

        celery_task_id = None
        try:
            celery_task_id = await redis_client.get(f"task_celery_map:{task_id}")
        except Exception as e:
            release_errors.append(f"celery_map_read_failed:{e}")

        try:
            from configs.celery_utils import celery

            target_id = celery_task_id or str(task_id)
            celery.control.revoke(target_id, terminate=True)
            celery.control.revoke(str(task_id), terminate=True)
        except Exception as e:
            release_errors.append(f"celery_revoke_failed:{e}")

        try:
            await redis_client.publish(
                f"optimize_events:{task_id}",
                json.dumps(
                    {
                        "event": "cancelled",
                        "task_id": str(task_id),
                        "reason": reason,
                        "mode": mode,
                    }
                ),
            )
        except Exception as e:
            release_errors.append(f"publish_cancel_event_failed:{e}")

    task.status = "cancelled"
    try:
        await task.save()
    except Exception as e:
        release_errors.append(f"task_save_failed:{e}")

    if release_errors:
        release_result = "partial"
    elapsed_ms = int((time.monotonic() - started) * 1000)
    print(
        json.dumps(
            {
                "event": "task_cancel_audit",
                "task_id": task_id,
                "user_id": actor_user_id,
                "reason": reason,
                "mode": mode,
                "elapsed_ms": elapsed_ms,
                "release_result": release_result,
                "already_cancelled": already_cancelled,
                "status_before": task.status if already_cancelled else "running_or_queued",
                "status_after": "cancelled",
                "errors": release_errors,
            },
            ensure_ascii=False,
        )
    )

    return {
        "task_id": task_id,
        "status": "cancelled",
        "already_cancelled": already_cancelled,
        "release_result": release_result,
        "elapsed_ms": elapsed_ms,
        "errors": release_errors,
    }

