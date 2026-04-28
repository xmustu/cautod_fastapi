from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `conversations` (
    `conversation_id` VARCHAR(64) NOT NULL PRIMARY KEY,
    `user_id` INT NOT NULL,
    `title` VARCHAR(255) NOT NULL DEFAULT '新会话',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `error_logs` (
    `error_id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `task_id` INT NOT NULL,
    `error_message` LONGTEXT NOT NULL,
    `error_type` VARCHAR(100),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `geometry_results` (
    `geometry_id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `task_id` INT NOT NULL,
    `cad_file_path` LONGTEXT,
    `code_file_path` LONGTEXT,
    `preview_image_path` LONGTEXT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `optimization_results` (
    `optimization_id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `task_id` INT NOT NULL,
    `optimized_cad_file_path` LONGTEXT,
    `best_params` JSON,
    `final_volume` DOUBLE,
    `final_stress` DOUBLE,
    `constraint_satisfied` BOOL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `roles` (
    `role_id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `permissions` VARCHAR(255) NOT NULL DEFAULT 'read,write',
    `user_id` INT NOT NULL COMMENT '用户ID'
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `tasks` (
    `task_id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `user_id` INT NOT NULL,
    `dify_conversation_id` VARCHAR(255),
    `task_type` VARCHAR(50) NOT NULL,
    `status` VARCHAR(20) NOT NULL DEFAULT 'pending',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `conversation_id` VARCHAR(64) NOT NULL,
    CONSTRAINT `fk_tasks_conversa_de825b63` FOREIGN KEY (`conversation_id`) REFERENCES `conversations` (`conversation_id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `users` (
    `user_id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `username` VARCHAR(255) NOT NULL DEFAULT 'user',
    `email` VARCHAR(255) NOT NULL UNIQUE,
    `password_hash` VARCHAR(255) NOT NULL,
    `role` VARCHAR(7) NOT NULL COMMENT '用户角色：user-普通用户, premium-高级用户, admin-管理员' DEFAULT 'user',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `aerich` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `version` VARCHAR(255) NOT NULL,
    `app` VARCHAR(100) NOT NULL,
    `content` JSON NOT NULL
) CHARACTER SET utf8mb4;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """
