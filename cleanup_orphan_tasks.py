import asyncio
from tortoise import Tortoise, run_async

from database.models import Tasks, Conversations
from database.settings import TORTOISE_ORM_SQLITE

async def cleanup():
    """
    清理孤立的任务记录。
    """
    # 初始化数据库连接
    await Tortoise.init(config=TORTOISE_ORM_SQLITE)
    await Tortoise.generate_schemas()

    # 1. 获取所有任务中的 conversation_id
    all_task_conv_ids = await Tasks.all().values_list("conversation_id", flat=True)
    unique_task_conv_ids = set(all_task_conv_ids)

    # 2. 获取所有存在的 conversation_id
    existing_conv_ids = await Conversations.all().values_list("conversation_id", flat=True)
    existing_conv_ids_set = set(existing_conv_ids)

    # 3. 找出孤立的 conversation_id (存在于任务中但不存在于会话中)
    orphan_conv_ids = unique_task_conv_ids - existing_conv_ids_set

    if not orphan_conv_ids:
        print("没有发现孤立的任务，无需清理。")
        return

    print(f"发现 {len(orphan_conv_ids)} 个会话的孤立任务: {orphan_conv_ids}")

    # 4. 删除这些孤立的会话ID对应的所有任务
    deleted_count = await Tasks.filter(conversation_id__in=list(orphan_conv_ids)).delete()

    print(f"成功删除了 {deleted_count} 条孤立的任务记录。")

    # 关闭连接
    await Tortoise.close_connections()

if __name__ == "__main__":
    run_async(cleanup())
