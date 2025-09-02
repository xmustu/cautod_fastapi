from tortoise.contrib.fastapi import register_tortoise   # 用于连接数据库
from tortoise import connections                         # 用于关闭数据库
from database.settings import TORTOISE_ORM_SQLITE, TORTOISE_ORM_MYSQL
from contextlib import asynccontextmanager
from fastapi import FastAPI
from config import settings




@asynccontextmanager
async def register_sql(app: FastAPI):
    try:
        print(settings.SQLMODE)
        if settings.SQLMODE == "SQLITE":
            config = TORTOISE_ORM_SQLITE
        elif settings.SQLMODE == "MYSQL":
            config = TORTOISE_ORM_MYSQL
        print(config)
        async with register_tortoise(
            app,
            config=TORTOISE_ORM_SQLITE,  # 使用 SQL 配置
            generate_schemas=True,  # 在应用启动时自动创建数据库表
            add_exception_handlers=True,
        ):
            print("ffffffffff")
            yield print(f"{settings.SQLMODE} 数据库连接成功")


            await connections.close_all()

            print(f"{settings.SQLMODE} 数据库已经关闭")

    except Exception as e:
        print(e)