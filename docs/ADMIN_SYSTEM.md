# CAutoD 管理员系统文档

## 概述

CAutoD 管理员系统提供了完整的后台管理功能，包括用户管理、任务管理、系统统计和配置管理。

## 功能特性

### 1. 管理员控制台 (Dashboard)
- **系统统计概览**
  - 总用户数、任务数、会话数
  - 各状态任务数量（待处理、进行中、已完成、失败）
  - 今日新增用户和任务统计
  
- **数据可视化**
  - 每日统计趋势图（最近7天）
  - 任务类型分布饼图
  - 用户活跃度排行（Top 10）
  - 任务状态统计

### 2. 用户管理
- **用户列表**
  - 分页显示所有用户
  - 搜索功能（用户名、邮箱）
  - 角色筛选（普通用户、高级用户、管理员）
  
- **用户操作**
  - 创建新用户
  - 编辑用户信息（用户名、邮箱、角色）
  - 删除单个用户
  - 批量删除用户
  - 修改用户密码

### 3. 任务管理
- **任务列表**
  - 分页显示所有任务
  - 按任务类型筛选（几何建模、优化、检索）
  - 按状态筛选（待处理、进行中、已完成、失败）
  - 按用户ID筛选
  
- **任务操作**
  - 查看任务详细信息
  - 查看任务结果（几何结果、优化结果）
  - 查看错误日志
  - 删除单个任务
  - 批量删除任务
  - 更新任务状态

### 4. 系统设置
- **用户限制配置**
  - 每个用户最大任务数
  - 每个用户最大会话数
  
- **功能开关**
  - 允许用户注册
  - 启用邮箱验证
  - 维护模式

## 默认管理员账号

系统启动时会自动检查并创建默认管理员账号：

```
用户名: admin
邮箱: Z.F.Zhang@i4ai.org
密码: i4AIi4AI
```

**重要提示**: 首次登录后请立即修改默认密码！

## 访问管理员系统

### 后端 API

管理员 API 端点都在 `/api/admin/` 路径下，需要管理员权限才能访问。

#### 统计 API
- `GET /api/admin/stats/overview` - 获取系统统计概览
- `GET /api/admin/stats/users` - 获取用户统计数据
- `GET /api/admin/stats/tasks/types` - 获取任务类型统计
- `GET /api/admin/stats/daily` - 获取每日统计数据

#### 用户管理 API
- `GET /api/admin/users` - 获取用户列表（分页）
- `GET /api/admin/users/{user_id}` - 获取用户详细信息
- `POST /api/admin/users` - 创建新用户
- `PUT /api/admin/users/{user_id}` - 更新用户信息
- `DELETE /api/admin/users/{user_id}` - 删除用户
- `POST /api/admin/users/batch-delete` - 批量删除用户

#### 任务管理 API
- `GET /api/admin/tasks` - 获取任务列表（分页）
- `GET /api/admin/tasks/{task_id}` - 获取任务详细信息
- `PUT /api/admin/tasks/{task_id}` - 更新任务状态
- `DELETE /api/admin/tasks/{task_id}` - 删除任务
- `POST /api/admin/tasks/batch-delete` - 批量删除任务

#### 系统配置 API
- `GET /api/admin/config` - 获取系统配置
- `PUT /api/admin/config` - 更新系统配置

### 前端页面

管理员登录后可以访问以下页面：

- `/admin/dashboard` - 管理员控制台
- `/admin/users` - 用户管理
- `/admin/tasks` - 任务管理
- `/admin/settings` - 系统设置

## 权限控制

### 后端权限
所有管理员 API 都使用 `require_admin` 依赖项进行权限验证：

```python
from core.permissions import require_admin

@admin_router.get("/stats/overview")
async def get_system_stats(
    current_user: User = Depends(require_admin)
):
    # 只有管理员可以访问
    ...
```

### 前端权限
前端通过检查用户角色来显示管理员菜单：

```javascript
const isAdmin = user?.role === 'admin';

// 只有管理员才能看到管理员路由
{isAdmin && (
  <Route path="/admin" element={<AdminLayout />}>
    ...
  </Route>
)}
```

## 文件结构

### 后端文件
```
cautod_fastapi/
├── apps/
│   ├── routes/
│   │   └── admin.py              # 管理员路由
│   └── schemas/
│       └── admin.py              # 管理员数据模型
├── database/
│   └── models.py                 # 数据库模型（包含 ErrorLogs）
└── main.py                       # 应用启动（包含管理员初始化）
```

### 前端文件
```
CAutoD_SoftWare_Front_End/
├── src/
│   ├── api/
│   │   └── adminApi.js           # 管理员 API 服务
│   ├── layouts/
│   │   └── AdminLayout.jsx       # 管理员布局
│   ├── pages/
│   │   ├── AdminDashboardPage.jsx    # 控制台页面
│   │   ├── UserManagementPage.jsx    # 用户管理页面
│   │   ├── TaskManagementPage.jsx    # 任务管理页面
│   │   └── SystemSettingsPage.jsx    # 系统设置页面
│   └── App.jsx                   # 路由配置
```

## 开发说明

### 添加新的管理员功能

1. **后端**:
   - 在 `apps/schemas/admin.py` 中定义数据模型
   - 在 `apps/routes/admin.py` 中添加新的路由端点
   - 使用 `require_admin` 依赖项保护路由

2. **前端**:
   - 在 `src/api/adminApi.js` 中添加 API 调用函数
   - 创建新的页面组件（如需要）
   - 在 `App.jsx` 中添加路由
   - 在 `AdminLayout.jsx` 中添加导航链接

### 数据库迁移

如果修改了数据模型，需要：

1. 更新 `database/models.py`
2. 运行 Tortoise ORM 迁移（如果配置了 Aerich）
3. 或者手动更新数据库表结构

## 安全建议

1. **修改默认密码**: 首次登录后立即修改管理员密码
2. **启用 HTTPS**: 生产环境中使用 HTTPS 加密通信
3. **定期备份**: 定期备份用户数据和系统配置
4. **日志监控**: 监控管理员操作日志
5. **限制访问**: 通过防火墙限制管理员面板的访问IP

## 故障排除

### 问题：无法访问管理员页面
- 检查用户角色是否为 `admin`
- 检查 token 是否有效
- 检查后端日志是否有权限错误

### 问题：统计数据不更新
- 点击"刷新数据"按钮
- 检查后端数据库连接
- 查看浏览器控制台是否有 API 错误

### 问题：批量操作失败
- 检查是否选中了要操作的项
- 查看后端日志获取详细错误信息
- 确认数据库连接正常

## 更新日志

### v1.0.0 (2025-11-02)
- ✅ 实现管理员控制台（Dashboard）
- ✅ 实现用户管理（CRUD）
- ✅ 实现任务管理（查看、删除）
- ✅ 实现系统统计数据可视化
- ✅ 实现系统配置管理
- ✅ 添加权限控制
- ✅ 自动创建默认管理员账号
- ✅ 添加 ErrorLogs 数据模型

## 许可证

本项目遵循与主项目相同的许可证。
