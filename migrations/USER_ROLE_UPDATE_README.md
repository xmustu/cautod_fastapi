# 用户角色管理功能 - 更新说明

## 概述

本次更新为系统添加了用户角色管理功能，将用户分为三个等级：
- **普通用户 (user)**: 基础权限
- **高级用户 (premium)**: 增强权限和更多资源配额
- **管理员 (admin)**: 完全控制权限

## 修改的文件

### 1. 数据库模型 (`database/models.py`)

**修改内容:**
- 添加了 `UserRole` 枚举类，定义三种角色类型
- 在 `Users` 模型中添加了 `role` 字段（CharEnumField 类型）
- 默认角色为 `user`（普通用户）

```python
class UserRole(str, Enum):
    USER = "user"           # 普通用户
    PREMIUM = "premium"     # 高级用户
    ADMIN = "admin"         # 管理员

class Users(Model):
    # ... 其他字段
    role = fields.CharEnumField(UserRole, default=UserRole.USER, description="用户角色")
```

### 2. Pydantic Schemas (`apps/schemas/user.py`)

**新增内容:**
- `UserRole` 枚举类（与数据库模型一致）
- `UserRegisterRequest`: 用户注册请求模型（包含可选的 role 字段）
- `UserLoginRequest`: 用户登录请求模型
- `UserResponse`: 用户响应模型（包含角色信息）
- `UserRoleUpdateRequest`: 更新用户角色请求模型（仅管理员可用）

### 3. 用户路由 (`apps/user.py`)

**修改的接口:**

#### GET `/me` - 获取当前用户信息
- 返回值现在包含 `role` 字段
- 返回类型为 `UserResponse`

#### POST `/register` - 用户注册
- 新增 `role` 参数（可选，默认为 `user`）
- 返回完整的用户信息（包括角色）

#### GET `/{user_id}` - 获取指定用户信息
- 返回值现在包含 `role` 字段

**新增接口:**

#### PUT `/update-role` - 更新用户角色（仅管理员）
- **权限要求**: 仅管理员可以调用
- **请求体**: 
  ```json
  {
    "user_id": 123,
    "role": "premium"
  }
  ```
- **响应**:
  ```json
  {
    "status": "success",
    "message": "用户 xxx 的角色已更新为 premium",
    "user_id": 123,
    "new_role": "premium"
  }
  ```

### 4. 认证模块 (`core/authentication.py`)

**修改内容:**
- `User` Pydantic 模型添加了 `role` 字段
- `get_current_user` 函数现在返回包含角色信息的用户对象

## 数据库迁移

### 方法一：使用 SQL 脚本（推荐）

执行迁移脚本 `migrations/add_user_role.sql`:

```bash
# 对于 SQLite 数据库
sqlite3 db.sqlite3 < migrations/add_user_role.sql
```

### 方法二：手动执行 SQL

```sql
-- 添加 role 字段
ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'user';

-- 更新现有用户
UPDATE users SET role = 'user' WHERE role IS NULL;

-- 创建索引（可选，提高查询性能）
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

-- 设置第一个用户为管理员（示例）
UPDATE users SET role = 'admin' WHERE user_id = 1;
```

### 方法三：使用 Tortoise ORM 迁移工具（如果配置了 Aerich）

```bash
# 生成迁移文件
aerich migrate

# 应用迁移
aerich upgrade
```

## 验证步骤

### 1. 检查表结构

```sql
PRAGMA table_info(users);
```

应该看到新的 `role` 字段。

### 2. 测试用户注册

```bash
curl -X POST "http://localhost:8000/user/register" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=testuser&email=test@example.com&pwd=password123&role=user"
```

### 3. 测试获取用户信息

```bash
curl -X GET "http://localhost:8000/user/me" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

响应应包含 `role` 字段。

### 4. 测试角色更新（管理员）

首先设置一个管理员用户：

```sql
UPDATE users SET role = 'admin' WHERE email = 'admin@example.com';
```

然后使用管理员账号登录并调用：

```bash
curl -X PUT "http://localhost:8000/user/update-role" \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_id": 2, "role": "premium"}'
```

## 角色权限说明

### 普通用户 (user)
- ✅ 创建和管理自己的任务
- ✅ 查看自己的几何建模结果
- ✅ 查看自己的优化结果
- ❌ 无法修改其他用户信息
- ❌ 无法访问管理功能

### 高级用户 (premium)
- ✅ 普通用户的所有权限
- ✅ 更高的资源配额（可在业务逻辑中实现）
- ✅ 优先任务处理（可在 Celery 任务中实现）
- ✅ 访问高级功能（根据业务需求定义）
- ❌ 无法管理其他用户

### 管理员 (admin)
- ✅ 高级用户的所有权限
- ✅ 修改任何用户的角色
- ✅ 查看和管理所有用户的任务
- ✅ 系统配置和维护
- ✅ 访问所有 API 端点

## 实现权限控制示例

在需要权限控制的路由中，可以创建依赖项：

```python
from fastapi import Depends, HTTPException, status
from core.authentication import get_current_active_user, User
from database.models import Users, UserRole

async def require_admin(current_user: User = Depends(get_current_active_user)):
    """要求管理员权限"""
    user = await Users.get(email=current_user.email)
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限"
        )
    return current_user

async def require_premium_or_admin(current_user: User = Depends(get_current_active_user)):
    """要求高级用户或管理员权限"""
    user = await Users.get(email=current_user.email)
    if user.role not in [UserRole.PREMIUM, UserRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要高级用户或管理员权限"
        )
    return current_user

# 使用示例
@router.get("/admin-only")
async def admin_only_route(current_user: User = Depends(require_admin)):
    return {"message": "欢迎，管理员！"}
```

## 注意事项

1. **首次部署**: 执行迁移脚本后，建议手动设置至少一个管理员账户
2. **安全性**: 普通用户注册时不应允许直接注册为管理员，管理员角色应通过现有管理员手动分配
3. **测试**: 在生产环境部署前，请在开发/测试环境充分测试所有角色的权限
4. **备份**: 执行数据库迁移前，请务必备份现有数据库

## 未来扩展建议

1. **权限细粒度控制**: 可以进一步定义每个角色的具体权限列表
2. **资源配额**: 为不同角色设置不同的资源限制（如任务数、文件大小等）
3. **审计日志**: 记录角色变更历史，便于追踪和审计
4. **角色组**: 支持多角色或角色组，实现更灵活的权限管理
5. **前端集成**: 根据用户角色显示/隐藏不同的UI元素

## 问题排查

### 问题：现有用户登录后没有 role 字段
**解决方案**: 执行 SQL 更新语句
```sql
UPDATE users SET role = 'user' WHERE role IS NULL OR role = '';
```

### 问题：权限验证失败
**解决方案**: 检查 JWT token 是否包含最新的用户信息，可能需要重新登录获取新 token

### 问题：迁移脚本执行失败
**解决方案**: 
1. 检查数据库连接
2. 确认数据库类型（SQLite/PostgreSQL/MySQL）
3. 根据实际数据库类型调整 SQL 语法

## 联系支持

如有问题，请联系开发团队或提交 Issue。
