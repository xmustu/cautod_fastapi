from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `system_config` (
    `config_id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `max_tasks_per_user` INT NOT NULL COMMENT '每个用户最大任务数' DEFAULT 100,
    `max_conversations_per_user` INT NOT NULL COMMENT '每个用户最大会话数' DEFAULT 50,
    `enable_registration` BOOL NOT NULL COMMENT '是否启用注册' DEFAULT 1,
    `enable_email_verification` BOOL NOT NULL COMMENT '是否启用邮箱验证' DEFAULT 1,
    `maintenance_mode` BOOL NOT NULL COMMENT '是否维护模式' DEFAULT 0,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `system_config`;"""
