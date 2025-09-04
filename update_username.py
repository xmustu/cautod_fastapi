import asyncio
from tortoise import Tortoise, run_async

from database.models import Users
from database.settings import TORTOISE_ORM_SQLITE

async def update_user():
    """
    更新指定用户的用户名。
    """
    # 初始化数据库连接
    await Tortoise.init(config=TORTOISE_ORM_SQLITE)
    await Tortoise.generate_schemas()

    user_id_to_update = 1
    new_username = "Z.F.Zhang"

    # 查找用户
    user = await Users.get_or_none(user_id=user_id_to_update)

    if user:
        print(f"找到了用户 ID: {user.user_id}，当前昵称: '{user.username}'。")
        user.username = new_username
        await user.save()
        print(f"成功将用户 ID: {user.user_id} 的昵称更新为 '{new_username}'。")
    else:
        print(f"未找到用户 ID: {user_id_to_update}。")

    # 关闭连接
    await Tortoise.close_connections()

if __name__ == "__main__":
    run_async(update_user())
