"""
清理现有用户名脚本
运行: python scripts/cleanup_usernames.py
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tortoise import Tortoise
from database.models import Users
from database.settings import TORTOISE_ORM_MYSQL


async def cleanup_usernames():
    """清理用户名(去除空格,转换邮箱为小写)"""
    # 初始化数据库连接
    await Tortoise.init(config=TORTOISE_ORM_MYSQL)
    await Tortoise.generate_schemas()
    
    users = await Users.all()
    updated_count = 0
    
    for user in users:
        modified = False
        
        # 清理用户名
        cleaned_username = user.username.strip()
        if cleaned_username != user.username:
            user.username = cleaned_username
            modified = True
        
        # 邮箱转小写
        lowered_email = user.email.lower()
        if lowered_email != user.email:
            user.email = lowered_email
            modified = True
        
        if modified:
            await user.save()
            updated_count += 1
            print(f"✓ 更新用户: {user.username} ({user.email})")
    
    await Tortoise.close_connections()
    print(f"\n✅ 清理完成,共更新 {updated_count}/{len(users)} 个用户")

if __name__ == "__main__":
    asyncio.run(cleanup_usernames())
