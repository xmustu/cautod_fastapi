from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `users` ADD `role` VARCHAR(7) NOT NULL COMMENT '用户角色：user-普通用户, premium-高级用户, admin-管理员' DEFAULT 'user';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `users` DROP COLUMN `role`;"""
