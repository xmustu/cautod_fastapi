-- 数据库迁移脚本：为 users 表添加 role 字段
-- 创建时间: 2025-10-24
-- 说明: 为用户管理系统添加角色功能，支持三种角色：user(普通用户)、premium(高级用户)、admin(管理员)

-- ========================================
-- SQLite 数据库迁移
-- ========================================

-- 步骤 1: 为 users 表添加 role 字段
-- 默认值为 'user'（普通用户）
ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'user';

-- 步骤 2: 为现有用户设置默认角色
-- 将所有现有用户的角色设置为 'user'
UPDATE users SET role = 'user' WHERE role IS NULL;

-- 步骤 3: 可选 - 将特定用户设置为管理员
-- 示例：将某个邮箱的用户设置为管理员
-- UPDATE users SET role = 'admin' WHERE email = 'admin@example.com';

-- 步骤 4: 添加检查约束（可选，确保只能使用有效的角色值）
-- 注意：SQLite 在 ALTER TABLE 中不支持直接添加 CHECK 约束
-- 如果需要严格的约束，建议在应用层（Pydantic/Tortoise ORM）进行验证

-- 步骤 5: 创建索引以提高角色查询性能（可选）
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

-- ========================================
-- 验证查询
-- ========================================

-- 查看表结构
-- PRAGMA table_info(users);

-- 查看所有用户及其角色
-- SELECT user_id, username, email, role, created_at FROM users;

-- 按角色统计用户数量
-- SELECT role, COUNT(*) as user_count FROM users GROUP BY role;

-- ========================================
-- 回滚脚本（如需撤销更改）
-- ========================================

-- 注意：SQLite 不支持直接删除列，需要重建表
-- 如果需要回滚，请参考以下步骤：

-- 1. 创建新表（不包含 role 字段）
-- CREATE TABLE users_new (
--     user_id INTEGER PRIMARY KEY AUTOINCREMENT,
--     username VARCHAR(255) DEFAULT 'user',
--     email VARCHAR(255) UNIQUE NOT NULL,
--     password_hash VARCHAR(255) NOT NULL,
--     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
-- );

-- 2. 复制数据
-- INSERT INTO users_new (user_id, username, email, password_hash, created_at)
-- SELECT user_id, username, email, password_hash, created_at FROM users;

-- 3. 删除旧表
-- DROP TABLE users;

-- 4. 重命名新表
-- ALTER TABLE users_new RENAME TO users;

-- 5. 删除索引
-- DROP INDEX IF EXISTS idx_users_role;

-- ========================================
-- 角色说明
-- ========================================

-- user: 普通用户
--   - 可以创建和管理自己的任务
--   - 可以查看自己的几何建模和优化结果
--   - 基础功能权限

-- premium: 高级用户
--   - 拥有普通用户的所有权限
--   - 可以访问高级功能
--   - 更高的资源配额（如任务数量、文件大小等）
--   - 优先处理队列

-- admin: 管理员
--   - 拥有系统的完全控制权
--   - 可以管理所有用户（包括修改用户角色）
--   - 可以查看和管理所有任务
--   - 系统配置和维护权限

-- ========================================
-- 使用示例
-- ========================================

-- 创建管理员用户（在用户注册后执行）
-- UPDATE users SET role = 'admin' WHERE email = 'your-admin@example.com';

-- 升级用户为高级用户
-- UPDATE users SET role = 'premium' WHERE user_id = 123;

-- 降级用户为普通用户
-- UPDATE users SET role = 'user' WHERE user_id = 456;

-- 查询所有管理员
-- SELECT * FROM users WHERE role = 'admin';

-- 查询所有高级用户
-- SELECT * FROM users WHERE role = 'premium';
