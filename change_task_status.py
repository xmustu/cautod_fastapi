from tortoise import run_async
from database.models import Tasks   # 替换成你的模型路径
from tortoise import Tortoise
from database.settings import TORTOISE_ORM_MYSQL,TORTOISE_ORM_SQLITE  # 或 TORTOISE_ORM_MYSQL，根据你的配置
from config import settings
async def mark_all_done():
    if settings.SQLMODE == "MYSQL":
        config = TORTOISE_ORM_MYSQL
    else:
        config = TORTOISE_ORM_SQLITE
    await Tortoise.init(config=config)
    await Tortoise.generate_schemas()

    rows = await Tasks.filter(
        status__in=["pending", "running"]
    ).update(status="done")
    print(f"已更新 {rows} 条任务状态为 done")

if __name__ == "__main__":
    run_async(mark_all_done())