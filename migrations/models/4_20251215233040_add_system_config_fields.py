from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `system_config` ADD `enable_email_notifications` BOOL NOT NULL COMMENT '是否启用邮件通知' DEFAULT 1;
        ALTER TABLE `system_config` ADD `max_file_size_mb` INT NOT NULL COMMENT '最大上传文件大小(MB)' DEFAULT 100;
        ALTER TABLE `system_config` ADD `session_timeout_minutes` INT NOT NULL COMMENT '会话超时时间(分钟)' DEFAULT 60;
        ALTER TABLE `system_config` ADD `default_user_role` VARCHAR(20) NOT NULL COMMENT '默认用户角色' DEFAULT 'user';
        ALTER TABLE `system_config` ADD `api_rate_limit` INT NOT NULL COMMENT 'API请求限制(次/分钟)' DEFAULT 100;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `system_config` DROP COLUMN `enable_email_notifications`;
        ALTER TABLE `system_config` DROP COLUMN `max_file_size_mb`;
        ALTER TABLE `system_config` DROP COLUMN `session_timeout_minutes`;
        ALTER TABLE `system_config` DROP COLUMN `default_user_role`;
        ALTER TABLE `system_config` DROP COLUMN `api_rate_limit`;"""
